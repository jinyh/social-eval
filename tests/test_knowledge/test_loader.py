from pathlib import Path

import pytest
import yaml

from src.core.exceptions import KnowledgeError
from src.knowledge.loader import load_framework

ACTIVE_FRAMEWORK = Path("configs/frameworks/law-v2.56.6-20260522.yaml")


def test_load_active_law_framework_succeeds():
    framework = load_framework(ACTIVE_FRAMEWORK)

    assert framework.discipline == "法学"
    assert framework.version == "2.56.6"
    assert len(framework.dimensions) == 6
    assert framework.precheck is not None
    assert framework.raw_config["scoring_protocol"]["mode"] == "core_ceiling_bonus"


def test_active_framework_dimensions_have_prompts():
    framework = load_framework(ACTIVE_FRAMEWORK)

    for dimension in framework.dimensions:
        assert dimension.prompt_template.strip()
        assert '"dimension"' in dimension.prompt_template
        assert '"score"' in dimension.prompt_template


def test_weight_sum_must_be_one(tmp_path):
    data = yaml.safe_load(ACTIVE_FRAMEWORK.read_text(encoding="utf-8"))
    data["dimensions"][0]["weight"] = 0.99
    path = tmp_path / "bad-weight.yaml"
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")

    with pytest.raises(KnowledgeError, match="权重之和"):
        load_framework(path)


def test_missing_required_field_raises_validation_error(tmp_path):
    data = yaml.safe_load(ACTIVE_FRAMEWORK.read_text(encoding="utf-8"))
    del data["metadata"]["name"]
    path = tmp_path / "missing-name.yaml"
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")

    with pytest.raises(Exception):
        load_framework(path)
