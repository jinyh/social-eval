from __future__ import annotations

import hashlib
import json
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

import fitz
from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph
from docx.oxml.ns import qn

from src.core.exceptions import IngestionError

EMAIL_RE = re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"(?<!\d)(?:\+?86[- ]?)?1[3-9]\d{9}(?!\d)")
LABELED_IDENTITY_RE = re.compile(
    r"(?im)^(?:作者|姓名|单位|机构|学校|学院|通讯作者|联系方式|基金项目)"
    r"\s*[:：].*$"
)
REMAINING_MARKERS = re.compile(
    r"(?i)(?:作者简介|通讯作者|e-?mail|电子邮箱|作者单位|基金项目)"
)
ORCID_RE = re.compile(r"(?i)\b(?:https?://orcid\.org/)?\d{4}-\d{4}-\d{4}-[\dX]{4}\b")
INSTITUTION_RE = re.compile(r"(?:大学|学院|研究院|研究所|法院|检察院|律师事务所|中心)")


@dataclass(frozen=True)
class AnonymizationResult:
    """匿名化派生文本及可审计摘要。"""

    text: str
    redaction_counts: dict[str, int]
    requires_confirmation: bool
    remaining_markers: list[str]
    risk_flags: list[str] | None = None
    omitted_content_types: list[str] | None = None


def anonymize_text(text: str) -> AnonymizationResult:
    """以保守规则移除常见身份信息；可疑残留交编辑确认。"""

    redaction_counts: dict[str, int] = {}
    text, redaction_counts["email"] = EMAIL_RE.subn("[已隐去邮箱]", text)
    text, redaction_counts["phone"] = PHONE_RE.subn("[已隐去电话]", text)
    text, redaction_counts["labeled_identity"] = LABELED_IDENTITY_RE.subn(
        "[已隐去身份信息]", text
    )
    remaining = sorted(set(REMAINING_MARKERS.findall(text)))
    return AnonymizationResult(
        text=text,
        redaction_counts=redaction_counts,
        requires_confirmation=True,
        remaining_markers=remaining,
        risk_flags=[],
        omitted_content_types=[],
    )


def _paragraph_block(paragraph: Paragraph) -> dict[str, Any] | None:
    text = paragraph.text.strip()
    if not text:
        return None
    style = paragraph.style.name if paragraph.style is not None else ""
    if style.lower().startswith("heading") or style.startswith("标题"):
        match = re.search(r"(\d+)", style)
        return {
            "type": "heading",
            "level": int(match.group(1)) if match else 2,
            "text": text,
        }
    return {"type": "paragraph", "text": text}


def _docx_blocks(source_path: str) -> tuple[list[dict[str, Any]], list[str], int]:
    document = Document(source_path)
    blocks: list[dict[str, Any]] = []
    for child in document.element.body.iterchildren():
        if child.tag == qn("w:p"):
            block = _paragraph_block(Paragraph(child, document))
            if block:
                blocks.append(block)
        elif child.tag == qn("w:tbl"):
            table = Table(child, document)
            rows = [[cell.text.strip() for cell in row.cells] for row in table.rows]
            if any(any(cell for cell in row) for row in rows):
                blocks.append({"type": "table", "rows": rows})

    try:
        with zipfile.ZipFile(source_path) as archive:
            footnotes_xml = archive.read("word/footnotes.xml")
    except (KeyError, zipfile.BadZipFile):
        footnotes_xml = b""
    if footnotes_xml:
        root = ElementTree.fromstring(footnotes_xml)
        word_id = f"{{{root.tag.split('}')[0].lstrip('{')}}}id"
        for footnote in root:
            raw_id = footnote.attrib.get(word_id, "")
            if raw_id.startswith("-"):
                continue
            text = "".join(
                node.text or "" for node in footnote.iter() if node.tag.endswith("}t")
            ).strip()
            if text:
                blocks.append({"type": "footnote", "number": raw_id, "text": text})

    candidates = [
        value.strip()
        for value in (
            document.core_properties.author,
            document.core_properties.last_modified_by,
        )
        if value and value.strip()
    ]
    return blocks, candidates, len(document.inline_shapes)


def _pdf_blocks(source_path: str) -> tuple[list[dict[str, Any]], list[str], int]:
    blocks: list[dict[str, Any]] = []
    candidates: list[str] = []
    image_count = 0
    try:
        with fitz.open(source_path) as document:
            metadata = document.metadata or {}
            for key in ("author", "creator"):
                value = str(metadata.get(key) or "").strip()
                if value:
                    candidates.append(value)
            for page_number, page in enumerate(document, start=1):
                blocks.append({"type": "page_break", "page": page_number})
                for raw_block in page.get_text("blocks"):
                    if len(raw_block) > 6 and raw_block[6] != 0:
                        continue
                    text = str(raw_block[4]).strip()
                    if text:
                        blocks.append({"type": "paragraph", "text": text})
                image_count += len(page.get_images(full=True))
    except Exception as exc:
        raise IngestionError(f"PDF 结构化解析失败：{exc}") from exc
    return blocks, candidates, image_count


def _text_blocks(source_path: str) -> tuple[list[dict[str, Any]], list[str], int]:
    text = Path(source_path).read_text(encoding="utf-8", errors="replace")
    blocks = [
        {"type": "paragraph", "text": item.strip()}
        for item in re.split(r"\n\s*\n", text)
        if item.strip()
    ]
    return blocks, [], 0


def _extract_blocks(
    source_path: str,
) -> tuple[list[dict[str, Any]], list[str], int]:
    suffix = Path(source_path).suffix.lower()
    if suffix == ".docx":
        return _docx_blocks(source_path)
    if suffix == ".pdf":
        return _pdf_blocks(source_path)
    if suffix in {".txt", ".md"}:
        return _text_blocks(source_path)
    raise IngestionError(f"不支持的匿名稿类型：{suffix or '未知'}")


def _redact_block_text(
    text: str,
    *,
    candidates: list[str],
    early_block: bool,
    counts: dict[str, int],
) -> str:
    text, count = EMAIL_RE.subn("[已隐去邮箱]", text)
    counts["email"] += count
    text, count = PHONE_RE.subn("[已隐去电话]", text)
    counts["phone"] += count
    text, count = LABELED_IDENTITY_RE.subn("[已隐去身份信息]", text)
    counts["labeled_identity"] += count
    text, count = ORCID_RE.subn("[已隐去 ORCID]", text)
    counts["orcid"] += count
    if REMAINING_MARKERS.search(text):
        counts["labeled_identity"] += 1
        return "[已隐去身份说明]"
    for candidate in candidates:
        if len(candidate) < 2:
            continue
        text, count = re.subn(re.escape(candidate), "[已隐去姓名]", text)
        counts["metadata_identity"] += count
    if (
        early_block
        and len(text.strip()) <= 40
        and INSTITUTION_RE.search(text)
        and not re.search(r"[。！？；]", text)
    ):
        counts["suspected_affiliation"] += 1
        return "[已隐去机构信息]"
    return text


def _sanitize_blocks(
    blocks: list[dict[str, Any]],
    candidates: list[str],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    counts = {
        "email": 0,
        "phone": 0,
        "labeled_identity": 0,
        "orcid": 0,
        "metadata_identity": 0,
        "suspected_affiliation": 0,
    }
    sanitized: list[dict[str, Any]] = []
    textual_index = 0
    for block in blocks:
        next_block = dict(block)
        if isinstance(block.get("text"), str):
            next_block["text"] = _redact_block_text(
                block["text"],
                candidates=candidates,
                early_block=textual_index < 8,
                counts=counts,
            )
            textual_index += 1
        elif block.get("type") == "table":
            next_block["rows"] = [
                [
                    _redact_block_text(
                        str(cell),
                        candidates=candidates,
                        early_block=textual_index < 8,
                        counts=counts,
                    )
                    for cell in row
                ]
                for row in block.get("rows", [])
            ]
            textual_index += 1
        sanitized.append(next_block)
    return sanitized, counts


def _blocks_to_text(blocks: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for block in blocks:
        block_type = block.get("type")
        if block_type == "table":
            parts.extend(
                "\t".join(str(cell) for cell in row) for row in block.get("rows", [])
            )
        elif block_type == "footnote":
            parts.append(f"脚注 {block.get('number', '')}：{block.get('text', '')}")
        elif block_type == "page_break":
            parts.append(f"第 {block.get('page', '')} 页")
        elif block.get("text"):
            parts.append(str(block["text"]))
    return "\n\n".join(parts)


def create_anonymized_artifacts(
    source_path: str,
    submission_id: str,
    *,
    version: int = 1,
    root: Path = Path("data/editorial"),
) -> tuple[Path, Path, AnonymizationResult, str, str]:
    """创建同版本的模型文本和网页结构化匿名稿。"""

    blocks, candidates, image_count = _extract_blocks(source_path)
    sanitized_blocks, redaction_counts = _sanitize_blocks(blocks, candidates)
    text = _blocks_to_text(sanitized_blocks)
    remaining = sorted(set(REMAINING_MARKERS.findall(text)))
    risk_flags: list[str] = []
    if not any(redaction_counts.values()):
        risk_flags.append("未检测到可自动隐去的身份信息，请重点核对首页署名和作者单位")
    if remaining:
        risk_flags.append("仍检测到可能的身份标记")
    omitted_content_types: list[str] = []
    if image_count:
        omitted_content_types.append("内嵌图片")
        risk_flags.append(f"匿名网页未展示 {image_count} 个内嵌图片，请编辑核对")
    result = AnonymizationResult(
        text=text,
        redaction_counts=redaction_counts,
        requires_confirmation=True,
        remaining_markers=remaining,
        risk_flags=risk_flags,
        omitted_content_types=omitted_content_types,
    )
    destination_dir = root / submission_id
    destination_dir.mkdir(parents=True, exist_ok=True)
    text_path = destination_dir / f"anonymized-v{version}.txt"
    view_path = destination_dir / f"anonymized-view-v{version}.json"
    text_path.write_text(text, encoding="utf-8")
    view_payload = {
        "schema_version": "anonymous-manuscript-v1",
        "document_version": version,
        "blocks": sanitized_blocks,
        "risk_flags": risk_flags,
        "omitted_content_types": omitted_content_types,
    }
    view_path.write_text(
        json.dumps(view_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    text_digest = hashlib.sha256(text_path.read_bytes()).hexdigest()
    view_digest = hashlib.sha256(view_path.read_bytes()).hexdigest()
    return text_path, view_path, result, text_digest, view_digest


def create_anonymized_document(
    source_path: str, submission_id: str, *, root: Path = Path("data/editorial")
) -> tuple[Path, AnonymizationResult, str]:
    """解析原稿并创建供模型使用的匿名 TXT 派生文档。"""

    path, _, result, digest, _ = create_anonymized_artifacts(
        source_path,
        submission_id,
        root=root,
    )
    return path, result, digest
