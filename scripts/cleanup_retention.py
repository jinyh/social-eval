from __future__ import annotations

import argparse
from datetime import timedelta
from pathlib import Path

from sqlalchemy.orm import Session

from src.core.audit import record_audit_log
from src.core.config import settings
from src.core.database import SessionLocal
from src.core.time import utc_now
from src.models.editorial import (
    EditorialDecision,
    EditorialDocument,
    EditorialOpinion,
    EditorialSubmission,
    PositionAssessment,
)
from src.models.audit import AuditLog
from src.models.evaluation import AICallLog, DimensionScore
from src.models.paper import Paper
from src.models.reliability import ReliabilityResult
from src.models.report import Report, ReportExport
from src.models.review import ExpertReview, ReviewComment


DATA_ROOT = Path("data").resolve()


def _safe_unlink(raw_path: str | None) -> None:
    if not raw_path:
        return
    path = Path(raw_path).resolve()
    if path != DATA_ROOT and DATA_ROOT not in path.parents:
        raise ValueError(f"拒绝删除数据目录之外的文件：{path}")
    path.unlink(missing_ok=True)


def purge_submission(db: Session, submission: EditorialSubmission) -> None:
    """删除到期稿件内容，保留投稿、决定和访问审计的最小元数据。"""

    paper = db.get(Paper, submission.paper_id)
    task_id = submission.evaluation_task_id

    documents = (
        db.query(EditorialDocument)
        .filter(EditorialDocument.submission_id == submission.id)
        .all()
    )
    for document in documents:
        _safe_unlink(document.file_path)
        db.delete(document)

    if task_id:
        reports = db.query(Report).filter(Report.task_id == task_id).all()
        report_ids = [row.id for row in reports]
        exports = (
            db.query(ReportExport).filter(ReportExport.report_id.in_(report_ids)).all()
            if report_ids
            else []
        )
        for export in exports:
            _safe_unlink(export.file_path)
            db.delete(export)
        for report in reports:
            db.delete(report)

        review_ids = [
            row.id
            for row in db.query(ExpertReview.id)
            .filter(ExpertReview.task_id == task_id)
            .all()
        ]
        if review_ids:
            db.query(ReviewComment).filter(
                ReviewComment.review_id.in_(review_ids)
            ).delete(synchronize_session=False)
        db.query(AICallLog).filter(AICallLog.task_id == task_id).delete()
        db.query(DimensionScore).filter(DimensionScore.task_id == task_id).delete()
        db.query(ReliabilityResult).filter(
            ReliabilityResult.task_id == task_id
        ).delete()

    db.query(PositionAssessment).filter(
        PositionAssessment.submission_id == submission.id
    ).delete()
    db.query(EditorialOpinion).filter(
        EditorialOpinion.submission_id == submission.id
    ).delete()
    for decision in (
        db.query(EditorialDecision)
        .filter(EditorialDecision.submission_id == submission.id)
        .all()
    ):
        decision.rationale = None
        db.add(decision)

    if paper is not None:
        _safe_unlink(paper.file_path)
        paper.file_path = None
        paper.title = None
        paper.precheck_result = None
        paper.signal_check_result = None
        paper.aggregate_result = None
        db.add(paper)
    submission.title = None
    submission.anonymization_result = None
    submission.formal_check_result = None
    submission.fit_result = None
    submission.content_deleted_at = utc_now()
    db.add(submission)


def main() -> None:
    parser = argparse.ArgumentParser(description="清理超过保留期的稿件内容")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        rows = (
            db.query(EditorialSubmission)
            .filter(
                EditorialSubmission.retention_due_at.is_not(None),
                EditorialSubmission.retention_due_at <= utc_now(),
                EditorialSubmission.retention_hold_at.is_(None),
                EditorialSubmission.content_deleted_at.is_(None),
            )
            .all()
        )
        print(f"待清理稿件：{len(rows)}")
        if not args.execute:
            return
        for row in rows:
            purge_submission(db, row)
            db.commit()
            record_audit_log(
                db,
                actor_id=None,
                object_type="editorial_submission",
                object_id=row.id,
                action="retention_content_deleted",
                result="success",
                details={
                    "policy": (f"manuscript-{settings.retention_manuscript_days}-days")
                },
            )
        audit_cutoff = utc_now() - timedelta(days=settings.retention_audit_days)
        deleted_audits = (
            db.query(AuditLog)
            .filter(AuditLog.created_at < audit_cutoff)
            .delete(synchronize_session=False)
        )
        db.commit()
        print(f"已清理稿件：{len(rows)}")
        print(f"已清理过期审计：{deleted_audits}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
