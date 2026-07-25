from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from src.editorial.constants import EDITORIAL_POLICY_PATH


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
    )


def deployed_policy_keys() -> list[str]:
    """返回管理员可以选择的已部署策略 key。"""

    payload = yaml.safe_load(Path(EDITORIAL_POLICY_PATH).read_text(encoding="utf-8"))
    return sorted(payload.get("profiles", {}).keys())
