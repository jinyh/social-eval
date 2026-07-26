from __future__ import annotations

from sqlalchemy.orm import Session

from src.editorial.constants import INITIAL_EDITORIAL_UNITS
from src.core.time import utc_now
from src.editorial.policy import (
    build_policy_snapshot,
    load_editorial_policy,
    policy_snapshot_digest,
)
from src.models.editorial import EditorialPolicyVersion, EditorialUnit, Journal


def ensure_initial_editorial_units(db: Session) -> list[EditorialUnit]:
    """幂等创建三个初始编辑单元，全部保持 shadow。"""

    units: list[EditorialUnit] = []
    for item in INITIAL_EDITORIAL_UNITS:
        journal = db.query(Journal).filter(Journal.code == item["journal_code"]).first()
        if journal is None:
            journal = Journal(
                code=item["journal_code"],
                name=item["journal_name"],
                is_active=True,
            )
            db.add(journal)
            db.flush()
        unit = (
            db.query(EditorialUnit)
            .filter(
                EditorialUnit.journal_id == journal.id,
                EditorialUnit.code == item["unit_code"],
            )
            .first()
        )
        if unit is None:
            policy = load_editorial_policy(item["policy_key"])
            unit = EditorialUnit(
                journal_id=journal.id,
                code=item["unit_code"],
                name=item["unit_name"],
                policy_key=policy.key,
                policy_version=policy.version,
                rollout_state="shadow",
            )
            db.add(unit)
            db.flush()
        if unit.rollout_state != "active" and unit.trial_policy_version_id is None:
            policy = load_editorial_policy(item["policy_key"])
            version = "1.1"
            profile = {
                **policy.profile,
                "accepted_scope": [str(policy.profile["fit_focus"])],
                "excluded_scope": [],
                "column_positioning": [],
                "article_types": ["法学研究论文"],
                "target_readers": ["法学研究者与法律实务工作者"],
                "special_notes": "",
            }
            snapshot = build_policy_snapshot(
                policy_key=policy.key,
                version=version,
                profile=profile,
                model_set_version="six-dimension-v2-candidate",
            )
            policy_version = EditorialPolicyVersion(
                unit_id=unit.id,
                policy_key=policy.key,
                version=version,
                status="trial",
                snapshot=snapshot,
                content_sha256=policy_snapshot_digest(snapshot),
                frozen_at=utc_now(),
            )
            db.add(policy_version)
            db.flush()
            unit.trial_policy_version_id = policy_version.id
            unit.policy_version = version
            db.add(unit)
        units.append(unit)
    db.commit()
    return units
