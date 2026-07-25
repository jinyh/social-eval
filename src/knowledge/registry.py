from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import jsonschema
import yaml

from src.knowledge.loader import load_framework

PROJECT_ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = PROJECT_ROOT / "configs" / "frameworks" / "registry.yaml"
DEFAULT_FRAMEWORK_ROLE = "six_dimension_default"
POSITION_SCHEMA_PATH = REGISTRY_PATH.parent / "schema_position_v0.2.json"
CROSS_REVIEW_SCHEMA_PATH = REGISTRY_PATH.parent / "schema_cross_review_v1.json"


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


def _load_registered_config(
    section: str,
    name: str,
    schema_path: Path,
    registry_path: Path,
) -> dict[str, Any]:
    registry = load_registry(registry_path)
    try:
        relative = registry[section][name]["path"]
    except (KeyError, TypeError) as exc:
        raise KeyError(f"未知配置角色: {section}.{name}") from exc
    path = (registry_path.parent / str(relative)).resolve()
    payload = _load_yaml(path)
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    jsonschema.validate(payload, schema)
    payload["source_path"] = str(path)
    return payload


def load_position_framework(
    role: str = "five_axis_default", registry_path: Path = REGISTRY_PATH
) -> dict[str, Any]:
    """加载并校验五轴位置评价配置。"""

    return _load_registered_config(
        "frameworks", role, POSITION_SCHEMA_PATH, registry_path
    )


def load_review_protocol(
    name: str = "six_dimension_cross_review",
    registry_path: Path = REGISTRY_PATH,
) -> dict[str, Any]:
    """加载并校验六维第二轮交叉评审协议。"""

    protocol = _load_registered_config(
        "review_protocols", name, CROSS_REVIEW_SCHEMA_PATH, registry_path
    )
    lenient = set(protocol["model_groups"]["lenient"])
    strict = set(protocol["model_groups"]["strict"])
    if lenient & strict:
        raise ValueError("交叉评审模型组不得重叠")
    return protocol


def load_model_set(
    name: str,
    registry_path: Path = REGISTRY_PATH,
) -> dict[str, Any]:
    """加载并校验版本化四模型集合。"""

    registry = load_registry(registry_path)
    try:
        payload = registry["model_sets"][name]
    except (KeyError, TypeError) as exc:
        raise KeyError(f"未知模型集: {name}") from exc
    provider_names = payload.get("provider_names")
    groups = payload.get("model_groups")
    if not isinstance(provider_names, list) or len(provider_names) != 4:
        raise ValueError(f"模型集 {name} 必须包含四个模型")
    if not isinstance(groups, dict):
        raise ValueError(f"模型集 {name} 缺少交叉评审分组")
    lenient = set(groups.get("lenient", []))
    strict = set(groups.get("strict", []))
    if lenient & strict or lenient | strict != set(provider_names):
        raise ValueError(f"模型集 {name} 的交叉评审分组不完整")
    return {
        "name": name,
        "status": str(payload.get("status", "")),
        "provider_names": list(provider_names),
        "model_groups": {
            "lenient": list(groups["lenient"]),
            "strict": list(groups["strict"]),
        },
    }


def _scoring_semantics(protocol: dict[str, Any]) -> dict[str, Any]:
    return {
        key: protocol.get(key)
        for key in (
            "mode",
            "core_dimensions",
            "ceiling_dimension",
            "bonus_dimension",
        )
    }


def assert_embedded_scoring_protocols_match(
    registry_path: Path = REGISTRY_PATH,
) -> list[str]:
    """返回与独立 CCB 真源计算语义不一致的框架角色。"""

    canonical = _scoring_semantics(load_scoring_protocol(registry_path=registry_path))
    registry = load_registry(registry_path)
    mismatches: list[str] = []
    for role, entry in registry.get("frameworks", {}).items():
        if not str(role).startswith("six_dimension_"):
            continue
        path = (registry_path.parent / str(entry["path"])).resolve()
        embedded = load_framework(path).raw_config.get("scoring_protocol", {})
        if _scoring_semantics(embedded) != canonical:
            mismatches.append(str(role))
    return mismatches
