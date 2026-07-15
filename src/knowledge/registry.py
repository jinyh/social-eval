from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = PROJECT_ROOT / "configs" / "frameworks" / "registry.yaml"
DEFAULT_FRAMEWORK_ROLE = "six_dimension_default"


def _load_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"配置必须是 YAML 对象: {path}")
    return data


def load_registry(path: Path = REGISTRY_PATH) -> dict[str, Any]:
    """加载框架角色注册表。"""

    return _load_yaml(path)


def resolve_framework_path(
    role: str = DEFAULT_FRAMEWORK_ROLE, registry_path: Path = REGISTRY_PATH
) -> Path:
    """把稳定角色名解析为具体框架文件。"""

    registry = load_registry(registry_path)
    try:
        relative = registry["frameworks"][role]["path"]
    except (KeyError, TypeError) as exc:
        raise KeyError(f"未知框架角色: {role}") from exc
    return (registry_path.parent / str(relative)).resolve()


def load_scoring_protocol(
    name: str = "default", registry_path: Path = REGISTRY_PATH
) -> dict[str, Any]:
    """加载独立、可版本化的评分协议。"""

    registry = load_registry(registry_path)
    try:
        relative = registry["scoring_protocols"][name]["path"]
    except (KeyError, TypeError) as exc:
        raise KeyError(f"未知评分协议: {name}") from exc
    path = (registry_path.parent / str(relative)).resolve()
    protocol = _load_yaml(path)
    protocol["source_path"] = str(path)
    return protocol
