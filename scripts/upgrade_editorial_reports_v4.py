#!/usr/bin/env python3
"""为已有编辑报告追加 v4 快照，保留全部历史版本。"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from sqlalchemy.orm import Session

from src.core.database import SessionLocal
from src.editorial.reporting import generate_editorial_report
from src.models.editorial import EditorialDocument, EditorialSubmission

TARGET_SCHEMA_VERSION = "editorial-report-v4"
ENGLISH_BAND_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_])(excellent|good|marginal|unacceptable)(?![A-Za-z0-9_])",
    re.IGNORECASE,
)


def latest_report_requires_upgrade(db: Session, submission_id: str) -> bool:
    """检查报告模式版本及综合摘要中的英文档位残留。"""

    document = (
        db.query(EditorialDocument)
        .filter(
            EditorialDocument.submission_id == submission_id,
            EditorialDocument.kind == "report_json",
        )
        .order_by(EditorialDocument.version.desc())
        .first()
    )
    if document is None:
        return True
    try:
        payload = json.loads(Path(document.file_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return True
    version = payload.get("schema_version")
    if version != TARGET_SCHEMA_VERSION:
        return True
    synthesis_payloads = [
        item.get("content") or {}
        for item in payload.get("ai_opinions", [])
        if item.get("type") == "ai_synthesis"
    ]
    serialized = json.dumps(synthesis_payloads, ensure_ascii=False)
    return ENGLISH_BAND_PATTERN.search(serialized) is not None


def upgrade_reports(
    db: Session,
    *,
    execute: bool,
    submission_id: str | None = None,
) -> tuple[int, int]:
    """返回（待升级数，实际升级数）；重复执行不会新增 v4。"""

    query = db.query(EditorialSubmission).filter(
        EditorialSubmission.current_report_version > 0
    )
    if submission_id:
        query = query.filter(EditorialSubmission.id == submission_id)
    submissions = query.order_by(EditorialSubmission.created_at).all()
    pending = [row for row in submissions if latest_report_requires_upgrade(db, row.id)]
    upgraded = 0
    for submission in pending:
        if not execute:
            print(
                f"submission={submission.id} "
                f"current_version={submission.current_report_version} "
                "action=would_append_v4"
            )
            continue
        version, _ = generate_editorial_report(db, submission.id)
        upgraded += 1
        print(f"submission={submission.id} version={version} action=appended_v4")
    return len(pending), upgraded


def main() -> None:
    parser = argparse.ArgumentParser(
        description="为已有编辑报告追加 editorial-report-v4 快照。"
    )
    parser.add_argument("--submission-id", help="只升级指定投稿")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="实际追加报告；不提供时只列出待升级项",
    )
    args = parser.parse_args()
    db = SessionLocal()
    try:
        pending, upgraded = upgrade_reports(
            db,
            execute=args.execute,
            submission_id=args.submission_id,
        )
        print(f"pending={pending} upgraded={upgraded}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
