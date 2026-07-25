from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy.orm import Session

from src.core.config import settings
from src.core.time import utc_now
from src.models.evaluation import EvaluationTask, EvaluationWorkUnit


PHASE_LABELS = {
    "anonymization": "匿名化处理",
    "formal_check": "形式完整性检查",
    "precheck": "公共预检",
    "journal_fit": "期刊适配性检查",
    "six_dimension_r1": "第一轮独立评审",
    "six_dimension_r2": "第二轮交叉复核",
    "signal_check": "自主知识体系信号校验",
    "position_r1": "五轴第一轮位置归属评价",
    "position_r2": "五轴第二轮位置归属复核",
    "opinion_synthesis": "生成智能辅助综合摘要",
    "report": "生成报告",
}

TERMINAL_STATUSES = {"completed", "skipped"}


def ensure_work_unit(
    db: Session,
    task_id: str,
    *,
    unit_key: str,
    phase: str,
    dimension_key: str | None = None,
    model_name: str | None = None,
    model_slot: int | None = None,
    round_number: int | None = None,
) -> EvaluationWorkUnit:
    row = (
        db.query(EvaluationWorkUnit)
        .filter(
            EvaluationWorkUnit.task_id == task_id,
            EvaluationWorkUnit.unit_key == unit_key,
        )
        .first()
    )
    if row is not None:
        return row
    row = EvaluationWorkUnit(
        task_id=task_id,
        unit_key=unit_key,
        phase=phase,
        dimension_key=dimension_key,
        model_name=model_name,
        model_slot=model_slot,
        round_number=round_number,
    )
    db.add(row)
    return row


def plan_evaluation_work(
    db: Session,
    task: EvaluationTask,
    *,
    dimension_keys: Iterable[str],
    provider_names: list[str],
    include_cross_review: bool,
    include_signal_check: bool,
    include_editorial: bool,
) -> None:
    """建立完整逻辑工作单元，重试时保持幂等。"""

    if include_editorial:
        for phase in ("anonymization", "formal_check", "journal_fit"):
            ensure_work_unit(
                db,
                task.id,
                unit_key=phase,
                phase=phase,
            )
    ensure_work_unit(db, task.id, unit_key="precheck", phase="precheck")
    for dimension_key in dimension_keys:
        for slot, model_name in enumerate(provider_names, start=1):
            ensure_work_unit(
                db,
                task.id,
                unit_key=f"r1:{dimension_key}:{model_name}",
                phase="six_dimension_r1",
                dimension_key=dimension_key,
                model_name=model_name,
                model_slot=slot,
                round_number=1,
            )
            if include_cross_review:
                ensure_work_unit(
                    db,
                    task.id,
                    unit_key=f"r2:{dimension_key}:{model_name}",
                    phase="six_dimension_r2",
                    dimension_key=dimension_key,
                    model_name=model_name,
                    model_slot=slot,
                    round_number=2,
                )
    if include_signal_check:
        for slot, model_name in enumerate(provider_names, start=1):
            ensure_work_unit(
                db,
                task.id,
                unit_key=f"signal:{model_name}",
                phase="signal_check",
                model_name=model_name,
                model_slot=slot,
            )
    if include_editorial:
        for phase, model_count in (("position_r1", 2), ("position_r2", 2)):
            for slot in range(1, model_count + 1):
                ensure_work_unit(
                    db,
                    task.id,
                    unit_key=f"{phase}:model-{slot}",
                    phase=phase,
                    model_slot=slot,
                    round_number=1 if phase == "position_r1" else 2,
                )
        ensure_work_unit(
            db,
            task.id,
            unit_key="opinion-synthesis",
            phase="opinion_synthesis",
        )
    ensure_work_unit(db, task.id, unit_key="report", phase="report")
    db.commit()


def set_work_status(
    db: Session,
    task_id: str,
    unit_key: str,
    status: str,
    *,
    failure_detail: str | None = None,
    commit: bool = True,
) -> None:
    row = (
        db.query(EvaluationWorkUnit)
        .filter(
            EvaluationWorkUnit.task_id == task_id,
            EvaluationWorkUnit.unit_key == unit_key,
        )
        .first()
    )
    if row is None:
        return
    now = utc_now()
    if status == "running":
        if row.status != "running":
            row.attempt_count += 1
        row.started_at = row.started_at or now
        row.heartbeat_at = now
        row.failure_detail = None
    elif status in TERMINAL_STATUSES:
        row.completed_at = now
        row.heartbeat_at = now
        row.failure_detail = None
    elif status == "failed":
        row.heartbeat_at = now
        row.failure_detail = (failure_detail or "处理失败")[:1000]
    row.status = status
    db.add(row)
    if commit:
        db.commit()


def mark_model_results(
    db: Session,
    task_id: str,
    *,
    phase: str,
    dimension_key: str,
    model_names: Iterable[str],
) -> None:
    prefix = "r1" if phase == "six_dimension_r1" else "r2"
    for model_name in model_names:
        set_work_status(
            db,
            task_id,
            f"{prefix}:{dimension_key}:{model_name}",
            "completed",
            commit=False,
        )
    db.commit()


def progress_summary(db: Session, task_id: str) -> dict:
    rows = (
        db.query(EvaluationWorkUnit)
        .filter(EvaluationWorkUnit.task_id == task_id)
        .order_by(EvaluationWorkUnit.created_at, EvaluationWorkUnit.unit_key)
        .all()
    )
    if not rows:
        return {
            "stage": "queued",
            "stage_label": "排队中",
            "completed": 0,
            "total": 0,
            "percent": 0,
            "current_dimension": None,
            "heartbeat_at": None,
            "is_stalled": False,
        }
    completed = sum(row.status in TERMINAL_STATUSES for row in rows)
    active = next((row for row in rows if row.status == "running"), None)
    failed = next((row for row in rows if row.status == "failed"), None)
    current = (
        active
        or failed
        or next((row for row in rows if row.status == "pending"), rows[-1])
    )
    heartbeats = [row.heartbeat_at for row in rows if row.heartbeat_at is not None]
    heartbeat = max(heartbeats) if heartbeats else None
    stalled = bool(
        active
        and heartbeat
        and (utc_now() - heartbeat).total_seconds() > settings.task_stale_seconds
    )
    return {
        "stage": current.phase,
        "stage_label": PHASE_LABELS.get(current.phase, "处理中"),
        "completed": completed,
        "total": len(rows),
        "percent": round(completed * 100 / len(rows)),
        "current_dimension": current.dimension_key,
        "current_model_slot": current.model_slot,
        "heartbeat_at": heartbeat,
        "is_stalled": stalled,
        "failure_detail": current.failure_detail
        if current.status == "failed"
        else None,
    }
