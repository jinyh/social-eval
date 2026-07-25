#!/usr/bin/env python3
"""为已有编辑报告追加 v3 快照，保留全部历史版本。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sqlalchemy.orm import Session

from src.core.database import SessionLocal
from src.editorial.reporting import generate_editorial_report
from src.models.editorial import EditorialDocument, EditorialSubmission

TARGET_SCHEMA_VERSION = "editorial-report-v3"


def latest_report_schema(db: Session, submission_id: str) -> str | None:
    """读取当前 JSON 报告的模式版本；文件异常时视为待升级。"""

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
        return None
    try:
        payload = json.loads(Path(document.file_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    version = payload.get("schema_version")
    return str(version) if version else None


def upgrade_reports(
    db: Session,
    *,
    execute: bool,
    submission_id: str | None = None,
) -> tuple[int, int]:
    """返回（待升级数，实际升级数）；重复执行不会新增 v3。"""

    query = db.query(EditorialSubmission).filter(
        EditorialSubmission.current_report_version > 0
    )
    if submission_id:
        query = query.filter(EditorialSubmission.id == submission_id)
    submissions = query.order_by(EditorialSubmission.created_at).all()
    pending = [
        row
        for row in submissions
        if latest_report_schema(db, row.id) != TARGET_SCHEMA_VERSION
    ]
    upgraded = 0
    for submission in pending:
        if not execute:
            print(
                f"submission={submission.id} "
                f"current_version={submission.current_report_version} "
                "action=would_append_v3"
            )
            continue
        version, _ = generate_editorial_report(db, submission.id)
        upgraded += 1
        print(f"submission={submission.id} version={version} action=appended_v3")
    return len(pending), upgraded


def main() -> None:
    parser = argparse.ArgumentParser(
        description="为已有编辑报告追加 editorial-report-v3 快照。"
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
