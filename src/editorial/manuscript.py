"""匿名稿网页阅读制品的加载与版本绑定。"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from src.models.audit import AuditLog
from src.models.editorial import EditorialDocument, EditorialSubmission
from src.models.evaluation import EvaluationTask


def has_human_anonymization_confirmation(
    db: Session,
    submission: EditorialSubmission,
) -> bool:
    """兼容新确认标记与已有人工确认审计记录。"""

    result = submission.anonymization_result or {}
    if result.get("human_confirmed") is True:
        return True
    return (
        db.query(AuditLog.id)
        .filter(
            AuditLog.object_type == "editorial_submission",
            AuditLog.object_id == submission.id,
            AuditLog.action == "confirm_anonymization",
            AuditLog.result == "confirmed",
        )
        .first()
        is not None
    )


def _bound_text_document(
    db: Session,
    submission: EditorialSubmission,
    task: EvaluationTask | None,
) -> EditorialDocument | None:
    query = db.query(EditorialDocument).filter(
        EditorialDocument.submission_id == submission.id,
        EditorialDocument.kind == "anonymized",
    )
    if task is not None:
        if not task.input_file_path:
            return None
        return query.filter(EditorialDocument.file_path == task.input_file_path).first()
    return query.order_by(EditorialDocument.version.desc()).first()


def _fallback_blocks(text: str) -> list[dict[str, Any]]:
    return [
        {"type": "paragraph", "text": part.strip()}
        for part in re.split(r"\n\s*\n", text)
        if part.strip()
    ]


def load_anonymous_manuscript(
    db: Session,
    *,
    submission: EditorialSubmission,
    task: EvaluationTask | None = None,
) -> dict[str, Any]:
    """读取与评价任务绑定的结构化匿名稿，旧稿回退为段落文本。"""

    text_document = _bound_text_document(db, submission, task)
    if text_document is None or not Path(text_document.file_path).exists():
        raise FileNotFoundError("匿名稿文件不存在")
    view_document = (
        db.query(EditorialDocument)
        .filter(
            EditorialDocument.submission_id == submission.id,
            EditorialDocument.kind == "anonymized_view",
            EditorialDocument.version == text_document.version,
        )
        .first()
    )
    payload: dict[str, Any] = {}
    if view_document is not None and Path(view_document.file_path).exists():
        try:
            payload = json.loads(
                Path(view_document.file_path).read_text(encoding="utf-8")
            )
        except (OSError, ValueError):
            payload = {}
    if not isinstance(payload.get("blocks"), list):
        text = Path(text_document.file_path).read_text(
            encoding="utf-8",
            errors="replace",
        )
        payload["blocks"] = _fallback_blocks(text)
    result = submission.anonymization_result or {}
    confidentiality_notice = "匿名稿仅供本次评审使用，严禁转发或用于其他目的。"
    processing_notice = str(result.get("notice") or "").strip()
    return {
        "manuscript_id": submission.external_manuscript_id or submission.id,
        "document_version": text_document.version,
        "blocks": payload["blocks"],
        "risk_flags": list(payload.get("risk_flags") or result.get("risk_flags") or []),
        "omitted_content_types": list(
            payload.get("omitted_content_types")
            or result.get("omitted_content_types")
            or []
        ),
        "notice": (
            f"{processing_notice} {confidentiality_notice}"
            if processing_notice
            else confidentiality_notice
        ),
    }
