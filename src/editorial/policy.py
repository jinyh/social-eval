from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import yaml
from sqlalchemy.orm import Session

from src.editorial.constants import EDITORIAL_POLICY_PATH
from src.knowledge.registry import load_model_set
from src.models.editorial import (
    EditorialPolicyVersion,
    EditorialSubmission,
    EditorialUnit,
)


@dataclass(frozen=True)
class EditorialPolicy:
    """一个已部署、可追溯的编辑单元策略。"""

    key: str
    version: str
    provider_names: tuple[str, ...]
    profile: dict
    band_fallback: dict
    decision_mapping: dict
    journal_fit: dict
    opinion: dict
    model_set_version: str
    review_protocol_version: str
    framework_version: str


def load_editorial_policy(policy_key: str) -> EditorialPolicy:
    """从已部署配置读取策略，未知 key 不允许回退到任意文件路径。"""

    path = Path(EDITORIAL_POLICY_PATH)
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    profiles = payload.get("profiles", {})
    if policy_key not in profiles:
        raise ValueError(f"Unknown deployed editorial policy: {policy_key}")
    return EditorialPolicy(
        key=policy_key,
        version=str(payload["metadata"]["version"]),
        provider_names=tuple(payload["evaluation"]["provider_names"]),
        profile=profiles[policy_key],
        band_fallback=payload["band_fallback"],
        decision_mapping=payload["decision_mapping"],
        journal_fit=payload["journal_fit"],
        opinion=payload["opinion"],
        model_set_version="six-dimension-v1",
        review_protocol_version="six_dimension_cross_review",
        framework_version=str(payload["metadata"]["academic_framework"]),
    )


def deployed_policy_keys() -> list[str]:
    """返回管理员可以选择的已部署策略 key。"""

    payload = yaml.safe_load(Path(EDITORIAL_POLICY_PATH).read_text(encoding="utf-8"))
    return sorted(payload.get("profiles", {}).keys())


def policy_snapshot_digest(snapshot: dict) -> str:
    """返回稳定的期刊策略快照摘要。"""

    payload = json.dumps(
        snapshot,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_policy_snapshot(
    *,
    policy_key: str,
    version: str,
    profile: dict,
    model_set_version: str,
) -> dict:
    """将后台可编辑字段解析为完整且可冻结的策略快照。"""

    base = load_editorial_policy(policy_key)
    model_set = load_model_set(model_set_version)
    return {
        "key": policy_key,
        "version": version,
        "profile": profile,
        "provider_names": model_set["provider_names"],
        "model_set_version": model_set["name"],
        "review_protocol_version": model_set["review_protocol"],
        "framework_version": base.framework_version,
        "band_fallback": base.band_fallback,
        "decision_mapping": base.decision_mapping,
        "journal_fit": base.journal_fit,
        "opinion": base.opinion,
    }


def policy_from_version(row: EditorialPolicyVersion) -> EditorialPolicy:
    """从数据库中的不可变快照恢复运行时策略。"""

    snapshot = row.snapshot
    if isinstance(snapshot, str):
        snapshot = json.loads(snapshot)
    if policy_snapshot_digest(snapshot) != row.content_sha256:
        raise ValueError(f"期刊策略版本 {row.id} 的内容摘要不一致")
    return EditorialPolicy(
        key=str(snapshot["key"]),
        version=str(snapshot["version"]),
        provider_names=tuple(snapshot["provider_names"]),
        profile=dict(snapshot["profile"]),
        band_fallback=dict(snapshot["band_fallback"]),
        decision_mapping=dict(snapshot["decision_mapping"]),
        journal_fit=dict(snapshot["journal_fit"]),
        opinion=dict(snapshot["opinion"]),
        model_set_version=str(snapshot["model_set_version"]),
        review_protocol_version=str(snapshot["review_protocol_version"]),
        framework_version=str(snapshot["framework_version"]),
    )


def unit_policy_version(
    db: Session,
    unit: EditorialUnit,
) -> EditorialPolicyVersion | None:
    """按编辑单元状态选择新投稿使用的策略版本。"""

    version_id = (
        unit.active_policy_version_id
        if unit.rollout_state == "active"
        else unit.trial_policy_version_id
    )
    if version_id is None:
        return None
    row = db.get(EditorialPolicyVersion, version_id)
    if row is None or row.unit_id != unit.id:
        raise ValueError("编辑单元绑定的期刊策略版本不存在")
    expected_status = "active" if unit.rollout_state == "active" else "trial"
    if row.status != expected_status:
        raise ValueError("编辑单元状态与期刊策略版本状态不一致")
    return row


def resolve_unit_policy(
    db: Session,
    unit: EditorialUnit,
) -> tuple[EditorialPolicy, EditorialPolicyVersion | None]:
    """解析新投稿策略；只为尚未迁移的数据库保留配置回退。"""

    row = unit_policy_version(db, unit)
    if row is None:
        return load_editorial_policy(unit.policy_key), None
    return policy_from_version(row), row


def resolve_submission_policy(
    db: Session,
    submission: EditorialSubmission,
) -> EditorialPolicy:
    """始终按投稿创建时绑定的不可变版本解析策略。"""

    if submission.policy_version_id:
        row = db.get(EditorialPolicyVersion, submission.policy_version_id)
        if row is None or row.unit_id != submission.unit_id:
            raise ValueError("投稿绑定的期刊策略版本不存在")
        return policy_from_version(row)
    return load_editorial_policy(submission.policy_key)
