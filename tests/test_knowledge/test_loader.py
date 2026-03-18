import pytest
from src.knowledge.loader import load_framework
from src.core.exceptions import KnowledgeError


def test_load_law_framework_succeeds():
    fw = load_framework("configs/frameworks/law_v1.yaml")
    assert fw.discipline == "law"
    assert len(fw.dimensions) == 6
    assert fw.name == "法学论文评价框架"
    assert fw.std_threshold == 5.0
    # 验证权重之和约为 1.0
    total_weight = sum(d.weight for d in fw.dimensions)
    assert abs(total_weight - 1.0) < 0.01


def test_load_law_framework_dimensions_have_prompts():
    fw = load_framework("configs/frameworks/law_v1.yaml")
    for dim in fw.dimensions:
        assert dim.prompt_template.strip() != ""
        assert "{paper_content}" in dim.prompt_template
        assert "{references}" in dim.prompt_template


def test_weight_sum_must_be_one(tmp_path):
    bad_yaml = tmp_path / "bad.yaml"
    bad_yaml.write_text("""
name: test
discipline: test
version: "1.0"
std_threshold: 5.0
dimensions:
  - key: d1
    name_zh: D1
    name_en: D1
    weight: 0.5
    prompt_template: "{paper_content} {references}"
  - key: d2
    name_zh: D2
    name_en: D2
    weight: 0.6
    prompt_template: "{paper_content} {references}"
""")
    with pytest.raises(KnowledgeError, match="权重之和"):
        load_framework(bad_yaml)


def test_missing_required_field_raises_validation_error(tmp_path):
    bad_yaml = tmp_path / "bad2.yaml"
    bad_yaml.write_text("""
name: test
discipline: test
dimensions: []
""")
    with pytest.raises(Exception):  # jsonschema.ValidationError
        load_framework(bad_yaml)
