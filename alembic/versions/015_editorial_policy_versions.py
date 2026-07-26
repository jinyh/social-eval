"""add immutable editorial policy versions

Revision ID: 015
Revises: 014
Create Date: 2026-07-26
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime
from pathlib import Path

from alembic import op
import sqlalchemy as sa
import yaml


revision = "015"
down_revision = "014"
branch_labels = None
depends_on = None


def _configuration() -> tuple[dict, dict]:
    root = Path(__file__).resolve().parents[2]
    editorial = yaml.safe_load(
        (root / "configs/frameworks/editorial-law-v1.yaml").read_text(encoding="utf-8")
    )
    registry = yaml.safe_load(
        (root / "configs/frameworks/registry.yaml").read_text(encoding="utf-8")
    )
    return editorial, registry


def _snapshot(
    editorial: dict,
    registry: dict,
    *,
    policy_key: str,
    version: str,
    model_set_version: str,
) -> dict:
    profile = dict(
        editorial["profiles"].get(
            policy_key,
            editorial["profiles"]["law-general-v1"],
        )
    )
    profile.setdefault("accepted_scope", [str(profile["fit_focus"])])
    profile.setdefault("excluded_scope", [])
    profile.setdefault("column_positioning", [])
    profile.setdefault("article_types", ["法学研究论文"])
    profile.setdefault("target_readers", ["法学研究者与法律实务工作者"])
    profile.setdefault("special_notes", "")
    model_set = registry["model_sets"][model_set_version]
    return {
        "key": policy_key,
        "version": version,
        "profile": profile,
        "provider_names": model_set["provider_names"],
        "model_set_version": model_set_version,
        "review_protocol_version": model_set["review_protocol"],
        "framework_version": editorial["metadata"]["academic_framework"],
        "band_fallback": editorial["band_fallback"],
        "decision_mapping": editorial["decision_mapping"],
        "journal_fit": editorial["journal_fit"],
        "opinion": editorial["opinion"],
    }


def _digest(snapshot: dict) -> str:
    payload = json.dumps(
        snapshot,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def upgrade() -> None:
    op.create_table(
        "editorial_policy_versions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("unit_id", sa.String(length=36), nullable=False),
        sa.Column("policy_key", sa.String(length=120), nullable=False),
        sa.Column("version", sa.String(length=50), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="draft",
        ),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("based_on_id", sa.String(length=36), nullable=True),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("activated_by", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("frozen_at", sa.DateTime(), nullable=True),
        sa.Column("activated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["activated_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["based_on_id"], ["editorial_policy_versions.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["unit_id"], ["editorial_units.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "unit_id",
            "version",
            name="uq_unit_policy_version",
        ),
    )
    op.add_column(
        "editorial_units",
        sa.Column("trial_policy_version_id", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "editorial_units",
        sa.Column("active_policy_version_id", sa.String(length=36), nullable=True),
    )
    op.create_foreign_key(
        "fk_unit_trial_policy_version",
        "editorial_units",
        "editorial_policy_versions",
        ["trial_policy_version_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_unit_active_policy_version",
        "editorial_units",
        "editorial_policy_versions",
        ["active_policy_version_id"],
        ["id"],
    )
    op.add_column(
        "editorial_submissions",
        sa.Column("policy_version_id", sa.String(length=36), nullable=True),
    )
    op.create_foreign_key(
        "fk_submission_policy_version",
        "editorial_submissions",
        "editorial_policy_versions",
        ["policy_version_id"],
        ["id"],
    )
    op.add_column(
        "validation_runs",
        sa.Column("policy_version_id", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "validation_runs",
        sa.Column("signer_membership_role", sa.String(length=30), nullable=True),
    )
    op.add_column(
        "validation_runs",
        sa.Column("rejection_reason", sa.Text(), nullable=True),
    )
    op.create_foreign_key(
        "fk_validation_policy_version",
        "validation_runs",
        "editorial_policy_versions",
        ["policy_version_id"],
        ["id"],
    )

    editorial, registry = _configuration()
    connection = op.get_bind()
    now = datetime(2026, 7, 26)
    units = connection.execute(
        sa.text(
            "SELECT id, policy_key, policy_version, rollout_state FROM editorial_units"
        )
    ).mappings()
    for unit in units:
        historical_id = str(uuid.uuid4())
        historical_snapshot = _snapshot(
            editorial,
            registry,
            policy_key=unit["policy_key"],
            version=unit["policy_version"],
            model_set_version="six-dimension-v1",
        )
        historical_status = "active" if unit["rollout_state"] == "active" else "retired"
        connection.execute(
            sa.text(
                "INSERT INTO editorial_policy_versions "
                "(id, unit_id, policy_key, version, status, snapshot, "
                "content_sha256, based_on_id, created_by, activated_by, "
                "created_at, frozen_at, activated_at) "
                "VALUES (:id, :unit_id, :policy_key, :version, :status, "
                ":snapshot, :content_sha256, NULL, NULL, NULL, :created_at, "
                ":frozen_at, :activated_at)"
            ),
            {
                "id": historical_id,
                "unit_id": unit["id"],
                "policy_key": unit["policy_key"],
                "version": unit["policy_version"],
                "status": historical_status,
                "snapshot": json.dumps(historical_snapshot, ensure_ascii=False),
                "content_sha256": _digest(historical_snapshot),
                "created_at": now,
                "frozen_at": now,
                "activated_at": now if historical_status == "active" else None,
            },
        )
        connection.execute(
            sa.text(
                "UPDATE editorial_submissions SET policy_version_id = :version_id "
                "WHERE unit_id = :unit_id"
            ),
            {"version_id": historical_id, "unit_id": unit["id"]},
        )
        if unit["rollout_state"] == "active":
            connection.execute(
                sa.text(
                    "UPDATE editorial_units SET active_policy_version_id = :version_id "
                    "WHERE id = :unit_id"
                ),
                {"version_id": historical_id, "unit_id": unit["id"]},
            )
            continue

        trial_id = str(uuid.uuid4())
        trial_version = (
            "1.1"
            if unit["policy_version"] == "1.0"
            else f"{unit['policy_version']}-trial-1"
        )
        trial_snapshot = _snapshot(
            editorial,
            registry,
            policy_key=unit["policy_key"],
            version=trial_version,
            model_set_version="six-dimension-v2-candidate",
        )
        connection.execute(
            sa.text(
                "INSERT INTO editorial_policy_versions "
                "(id, unit_id, policy_key, version, status, snapshot, "
                "content_sha256, based_on_id, created_by, activated_by, "
                "created_at, frozen_at, activated_at) "
                "VALUES (:id, :unit_id, :policy_key, :version, 'trial', "
                ":snapshot, :content_sha256, :based_on_id, NULL, NULL, "
                ":created_at, :frozen_at, NULL)"
            ),
            {
                "id": trial_id,
                "unit_id": unit["id"],
                "policy_key": unit["policy_key"],
                "version": trial_version,
                "snapshot": json.dumps(trial_snapshot, ensure_ascii=False),
                "content_sha256": _digest(trial_snapshot),
                "based_on_id": historical_id,
                "created_at": now,
                "frozen_at": now,
            },
        )
        connection.execute(
            sa.text(
                "UPDATE editorial_units SET trial_policy_version_id = :version_id, "
                "policy_version = :policy_version WHERE id = :unit_id"
            ),
            {
                "version_id": trial_id,
                "policy_version": trial_version,
                "unit_id": unit["id"],
            },
        )


def downgrade() -> None:
    op.drop_constraint(
        "fk_validation_policy_version",
        "validation_runs",
        type_="foreignkey",
    )
    op.drop_column("validation_runs", "rejection_reason")
    op.drop_column("validation_runs", "signer_membership_role")
    op.drop_column("validation_runs", "policy_version_id")
    op.drop_constraint(
        "fk_submission_policy_version",
        "editorial_submissions",
        type_="foreignkey",
    )
    op.drop_column("editorial_submissions", "policy_version_id")
    op.drop_constraint(
        "fk_unit_active_policy_version",
        "editorial_units",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_unit_trial_policy_version",
        "editorial_units",
        type_="foreignkey",
    )
    op.drop_column("editorial_units", "active_policy_version_id")
    op.drop_column("editorial_units", "trial_policy_version_id")
    op.drop_table("editorial_policy_versions")
