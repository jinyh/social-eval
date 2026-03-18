import yaml
import json
import jsonschema
from pathlib import Path

from src.knowledge.schemas import Framework
from src.knowledge.validator import validate_weights

SCHEMA_PATH = Path(__file__).parent.parent.parent / "configs" / "frameworks" / "schema.json"


def load_framework(yaml_path: str | Path) -> Framework:
    schema = json.loads(SCHEMA_PATH.read_text())
    data = yaml.safe_load(Path(yaml_path).read_text(encoding="utf-8"))
    jsonschema.validate(data, schema)
    validate_weights(data["dimensions"])
    return Framework(**data)


def load_framework_from_string(yaml_content: str) -> Framework:
    schema = json.loads(SCHEMA_PATH.read_text())
    data = yaml.safe_load(yaml_content)
    jsonschema.validate(data, schema)
    validate_weights(data["dimensions"])
    return Framework(**data)
