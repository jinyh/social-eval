import json

from src.knowledge.law_ontology import load_law_ontology, parse_law_tree_markdown


SAMPLE_TREE = """# 中国法学自主知识体系 - 树状知识库

```
中国法学自主知识体系
│
├── 5. 民法学自主知识体系 〔d05〕〔主干学科〕
│   ├── 一、民法学自主知识体系简况
│   ├── 二、标识性概念
│   │   ├── 1. 占有保护
│   │   └── 2. 民事权利
│   ├── 三、原创性理论
│   │   └── 1. 民法典体系化理论
│   └── 四、框架结构
│       ├── 第一：总则理论
│       └── 第二：物权理论（占有保护）
│
└── 6. 商法学自主知识体系 〔d06〕〔主干学科〕
    ├── 二、标识性概念
    │   └── 1. 公司治理
    ├── 三、原创性理论
    │   └── 1. 中国特色现代企业理论
    └── 四、框架结构
        └── 第一：商事主体论
```
"""


def test_parse_law_tree_markdown_builds_stable_node_ids_and_paths():
    ontology = parse_law_tree_markdown(SAMPLE_TREE, source_path="fixture.md")

    node = ontology.find_node("d05.concept.001")

    assert node is not None
    assert node.label == "占有保护"
    assert node.node_type == "concept"
    assert node.discipline_code == "d05"
    assert node.parent_id == "d05.concepts"
    assert node.path == ["中国法学自主知识体系", "民法学", "标识性概念", "占有保护"]


def test_parse_law_tree_markdown_keeps_theory_and_framework_nodes():
    ontology = parse_law_tree_markdown(SAMPLE_TREE, source_path="fixture.md")

    theory = ontology.find_node("d06.theory.001")
    framework = ontology.find_node("d05.framework.002")

    assert theory is not None
    assert theory.label == "中国特色现代企业理论"
    assert theory.node_type == "theory"
    assert framework is not None
    assert framework.label == "物权理论（占有保护）"
    assert framework.node_type == "framework"


def test_load_law_ontology_from_json_roundtrips(tmp_path):
    ontology = parse_law_tree_markdown(SAMPLE_TREE, source_path="fixture.md")
    path = tmp_path / "law_ontology.json"
    path.write_text(
        json.dumps(ontology.to_dict(), ensure_ascii=False), encoding="utf-8"
    )

    loaded = load_law_ontology(path)

    assert loaded.schema_version == "1.0"
    assert loaded.find_node("d05.concept.001").label == "占有保护"
