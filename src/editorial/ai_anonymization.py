from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.orm import Session

from src.evaluation.call_logger import log_call
from src.evaluation.providers.base import BaseProvider

CONFIG_PATH = Path("configs/frameworks/editorial-anonymization-v1.yaml")
IDENTITY_HINT_RE = re.compile(
    r"作者|姓名|单位|学院|大学|研究院|邮箱|电话|手机|通讯作者|"
    r"ORCID|基金|项目|简介|致谢"
)


class IdentityFinding(BaseModel):
    """模型识别出的单个投稿作者身份片段。"""

    block_index: int = Field(ge=0)
    category: Literal[
        "person_name",
        "affiliation",
        "contact",
        "orcid",
        "author_bio",
        "acknowledgement",
    ]
    exact_text: str = Field(min_length=2, max_length=500)
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str = Field(min_length=2, max_length=1000)


class IdentityDetectionPayload(BaseModel):
    """GLM 身份检测的结构化输出。"""

    findings: list[IdentityFinding] = Field(default_factory=list, max_length=100)
    needs_manual_review: bool = False
    uncertainty_reasons: list[str] = Field(default_factory=list, max_length=20)
    summary: str = Field(min_length=2, max_length=2000)


@dataclass(frozen=True)
class AIAnonymizationOutcome:
    """一次模型辅助匿名处理的可持久化结果。"""

    model_name: str
    status: str
    applied_count: int
    requires_manual_review: bool
    uncertainty_reasons: list[str]
    summary: str
    text_sha256: str | None = None
    view_sha256: str | None = None
    failure_detail: str | None = None


def load_anonymization_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    """加载模型、阈值与提示词配置。"""

    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("匿名检测配置格式无效")
    return payload


def _block_text(block: dict[str, Any]) -> str:
    if isinstance(block.get("text"), str):
        return str(block["text"])
    if block.get("type") == "table":
        return "\n".join(
            "\t".join(str(cell) for cell in row) for row in block.get("rows", [])
        )
    return ""


def candidate_blocks(
    blocks: list[dict[str, Any]],
    *,
    max_blocks: int,
    max_characters: int,
) -> list[dict[str, Any]]:
    """选择首页及身份高风险段落，避免把整篇论文交给匿名检测模型。"""

    selected: list[dict[str, Any]] = []
    textual_position = 0
    for block_index, block in enumerate(blocks):
        text = _block_text(block).strip()
        if not text:
            continue
        is_early = textual_position < 12
        textual_position += 1
        if not is_early and not IDENTITY_HINT_RE.search(text):
            continue
        selected.append(
            {
                "block_index": block_index,
                "text": text[:max_characters],
            }
        )
        if len(selected) >= max_blocks:
            break
    return selected


def build_identity_prompt(
    candidates: list[dict[str, Any]],
    config: dict[str, Any],
) -> str:
    """按配置构造只允许返回身份片段的 JSON 提示。"""

    return (
        f"{str(config['instructions']).strip()}\n\n"
        f"输出契约：\n{str(config['output_contract']).strip()}\n\n"
        "待检测段落（JSON）：\n"
        f"{json.dumps(candidates, ensure_ascii=False)}"
    )


def _placeholder(category: str) -> str:
    return {
        "person_name": "[已隐去姓名]",
        "affiliation": "[已隐去机构信息]",
        "contact": "[已隐去联系方式]",
        "orcid": "[已隐去 ORCID]",
        "author_bio": "[已隐去作者简介]",
        "acknowledgement": "[已隐去身份相关致谢]",
    }[category]


def _redact_finding(block: dict[str, Any], finding: IdentityFinding) -> int:
    exact_text = finding.exact_text.strip()
    placeholder = _placeholder(finding.category)
    if isinstance(block.get("text"), str):
        count = str(block["text"]).count(exact_text)
        block["text"] = str(block["text"]).replace(exact_text, placeholder)
        return count
    if block.get("type") != "table":
        return 0
    count = 0
    rows: list[list[str]] = []
    for row in block.get("rows", []):
        next_row: list[str] = []
        for cell in row:
            value = str(cell)
            count += value.count(exact_text)
            next_row.append(value.replace(exact_text, placeholder))
        rows.append(next_row)
    block["rows"] = rows
    return count


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


def apply_identity_findings(
    *,
    text_path: Path,
    view_path: Path,
    findings: list[IdentityFinding],
    minimum_confidence: float,
) -> tuple[int, list[str], str, str]:
    """仅在指定段落精确替换高可信身份片段，并同步两个匿名制品。"""

    payload = json.loads(view_path.read_text(encoding="utf-8"))
    blocks = payload.get("blocks")
    if not isinstance(blocks, list):
        raise ValueError("匿名稿网页制品缺少段落")

    applied_count = 0
    uncertainties: list[str] = []
    handled: set[tuple[int, str]] = set()
    for finding in findings:
        key = (finding.block_index, finding.exact_text)
        if key in handled:
            continue
        handled.add(key)
        if finding.confidence < minimum_confidence:
            uncertainties.append(f"段落 {finding.block_index} 的身份判断可信程度不足")
            continue
        if finding.block_index >= len(blocks):
            uncertainties.append(f"模型返回了不存在的段落 {finding.block_index}")
            continue
        count = _redact_finding(blocks[finding.block_index], finding)
        if count == 0:
            uncertainties.append(
                f"段落 {finding.block_index} 中找不到模型返回的精确片段"
            )
            continue
        applied_count += count

    text_path.write_text(_blocks_to_text(blocks), encoding="utf-8")
    payload["blocks"] = blocks
    view_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return (
        applied_count,
        uncertainties,
        hashlib.sha256(text_path.read_bytes()).hexdigest(),
        hashlib.sha256(view_path.read_bytes()).hexdigest(),
    )


async def run_ai_anonymization(
    *,
    provider: BaseProvider,
    task_id: str,
    db: Session,
    text_path: Path,
    view_path: Path,
    config: dict[str, Any] | None = None,
) -> AIAnonymizationOutcome:
    """调用统一 Provider 检测身份片段，失败时安全降级到人工门禁。"""

    selected_config = config or load_anonymization_config()
    view_payload = json.loads(view_path.read_text(encoding="utf-8"))
    blocks = view_payload.get("blocks")
    if not isinstance(blocks, list):
        raise ValueError("匿名稿网页制品缺少段落")
    candidates = candidate_blocks(
        blocks,
        max_blocks=int(selected_config["max_candidate_blocks"]),
        max_characters=int(selected_config["max_block_characters"]),
    )
    prompt = build_identity_prompt(candidates, selected_config)
    start = time.time()
    raw: dict[str, Any] | None = None
    try:
        raw = await provider.call_with_timeout(provider.generate_json_response(prompt))
        payload = IdentityDetectionPayload.model_validate(raw)
        applied, apply_uncertainties, text_digest, view_digest = (
            apply_identity_findings(
                text_path=text_path,
                view_path=view_path,
                findings=payload.findings,
                minimum_confidence=float(selected_config["minimum_confidence"]),
            )
        )
        log_call(
            db,
            task_id,
            provider.model_name,
            "__anonymization__",
            prompt,
            json.dumps(raw, ensure_ascii=False),
            start,
            call_type="anonymization_identity_detection",
            provider_name=provider.__class__.__name__,
        )
        uncertainties = [
            *payload.uncertainty_reasons,
            *apply_uncertainties,
        ]
        return AIAnonymizationOutcome(
            model_name=provider.model_name,
            status="completed",
            applied_count=applied,
            requires_manual_review=payload.needs_manual_review or bool(uncertainties),
            uncertainty_reasons=uncertainties,
            summary=payload.summary,
            text_sha256=text_digest,
            view_sha256=view_digest,
        )
    except Exception as exc:
        raw_response = str(getattr(exc, "raw_response", "") or "")
        if not raw_response and raw is not None:
            raw_response = json.dumps(raw, ensure_ascii=False)
        log_call(
            db,
            task_id,
            provider.model_name,
            "__anonymization__",
            prompt,
            raw_response,
            start,
            call_type="anonymization_identity_detection",
            provider_name=provider.__class__.__name__,
            status="failed",
            failure_detail=str(exc),
        )
        failure = (
            "模型身份检测失败，已安全转为人工确认"
            if isinstance(exc, ValidationError)
            else f"模型身份检测失败，已安全转为人工确认：{exc}"
        )
        return AIAnonymizationOutcome(
            model_name=provider.model_name,
            status="failed",
            applied_count=0,
            requires_manual_review=True,
            uncertainty_reasons=[failure],
            summary="模型辅助匿名未完成",
            failure_detail=str(exc),
        )
