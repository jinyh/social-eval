from __future__ import annotations

from sqlalchemy.orm import Session

from src.editorial.constants import INITIAL_EDITORIAL_UNITS
from src.editorial.policy import load_editorial_policy
from src.models.editorial import EditorialUnit, Journal


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
        units.append(unit)
    db.commit()
    return units
