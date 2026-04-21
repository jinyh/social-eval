from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import jsonschema
import yaml

from src.knowledge.schemas import Framework
from src.knowledge.validator import validate_weights

FRAMEWORK_DIR = Path(__file__).parent.parent.parent / "configs" / "frameworks"
SCHEMA_V1_PATH = FRAMEWORK_DIR / "schema.json"
SCHEMA_V2_PATH = FRAMEWORK_DIR / "schema_v2.json"
DEFAULT_STD_THRESHOLD = 5.0


def _load_schema(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _is_v2_framework(data: dict[str, Any]) -> bool:
    return "metadata" in data


def _schema_path_for_data(data: dict[str, Any]) -> Path:
    return SCHEMA_V2_PATH if _is_v2_framework(data) else SCHEMA_V1_PATH


def _normalize_framework_data(data: dict[str, Any]) -> dict[str, Any]:
    if not _is_v2_framework(data):
        normalized = dict(data)
        normalized["raw_config"] = data
        return normalized

    metadata = data["metadata"]
    normalized = {
        "name": metadata["name"],
        "discipline": metadata["discipline"],
        "version": metadata["version"],
        "std_threshold": data.get("std_threshold", DEFAULT_STD_THRESHOLD),
        "dimensions": data["dimensions"],
        "metadata": metadata,
        "precheck": data.get("precheck"),
        "scoring_structure": data.get("scoring_structure"),
        "evaluation_chain": data.get("evaluation_chain"),
        "discrimination_threshold": data.get("discrimination_threshold"),
        "expert_review_triggers": data.get("expert_review_triggers"),
        "anchors": data.get("anchors"),
        "raw_config": data,
    }
    return normalized


def _validate_framework_data(data: dict[str, Any]) -> None:
    schema_path = _schema_path_for_data(data)
    schema = _load_schema(schema_path)
    jsonschema.validate(data, schema)
    validate_weights(data["dimensions"])


def _load_yaml_data(yaml_content: str) -> dict[str, Any]:
    return yaml.safe_load(yaml_content)


def load_framework(yaml_path: str | Path) -> Framework:
    data = _load_yaml_data(Path(yaml_path).read_text(encoding="utf-8"))
    _validate_framework_data(data)
    return Framework(**_normalize_framework_data(data))


def load_framework_from_string(yaml_content: str) -> Framework:
    data = _load_yaml_data(yaml_content)
    _validate_framework_data(data)
    return Framework(**_normalize_framework_data(data))
