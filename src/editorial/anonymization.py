from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from src.ingestion.preprocessor import process_file

EMAIL_RE = re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"(?<!\d)(?:\+?86[- ]?)?1[3-9]\d{9}(?!\d)")
LABELED_IDENTITY_RE = re.compile(
    r"(?im)^(?:作者|姓名|单位|机构|学校|学院|通讯作者|联系方式|基金项目)"
    r"\s*[:：].*$"
)
REMAINING_MARKERS = re.compile(
    r"(?i)(?:作者简介|通讯作者|e-?mail|电子邮箱|作者单位|基金项目)"
)


@dataclass(frozen=True)
class AnonymizationResult:
    """匿名化派生文本及可审计摘要。"""

    text: str
    redaction_counts: dict[str, int]
    requires_confirmation: bool
    remaining_markers: list[str]


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
        requires_confirmation=bool(remaining) or len(text.strip()) < 200,
        remaining_markers=remaining,
    )


def create_anonymized_document(
    source_path: str, submission_id: str, *, root: Path = Path("data/editorial")
) -> tuple[Path, AnonymizationResult, str]:
    """解析原稿并创建供模型使用的匿名 TXT 派生文档。"""

    processed = process_file(source_path)
    result = anonymize_text(processed.full_text)
    destination_dir = root / submission_id
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / "anonymized-v1.txt"
    destination.write_text(result.text, encoding="utf-8")
    digest = hashlib.sha256(destination.read_bytes()).hexdigest()
    return destination, result, digest
