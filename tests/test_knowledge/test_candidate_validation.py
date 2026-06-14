from src.knowledge.candidate_validation import (
    validate_candidate_nodes,
    validate_node_matches,
)
from src.knowledge.law_ontology import parse_law_tree_markdown
from src.knowledge.node_retrieval import retrieve_nodes


SAMPLE_TREE = """# 中国法学自主知识体系 - 树状知识库

```
中国法学自主知识体系
├── 5. 民法学自主知识体系 〔d05〕〔主干学科〕
│   ├── 二、标识性概念
│   │   └── 1. 占有保护
│   └── 四、框架结构
│       └── 第二：物权理论（占有保护）
└── 6. 商法学自主知识体系 〔d06〕〔主干学科〕
    ├── 二、标识性概念
    │   └── 1. 公司治理
    └── 三、原创性理论
        └── 1. 中国特色现代企业理论
```
"""


def _ontology():
    return parse_law_tree_markdown(SAMPLE_TREE, source_path="fixture.md")


def test_validate_candidate_nodes_rejects_title_wrappers():
    ontology = _ontology()
    result = validate_candidate_nodes(
        [
            {
                "label": "股权转让中的出资义务承担",
                "match_type": "candidate_new_node",
                "parent_node_id": "d06.concept.001",
                "evidence_quote": "股权转让中的出资义务承担",
            }
        ],
        ontology=ontology,
        retrieved_nodes=[],
        paper_title="股权转让中的出资义务承担——以组织法与行为法融贯为视角",
        paper_text="股权转让中的出资义务承担是本文标题。",
    )

    assert result[0].status == "rejected"
    assert "title_wrapper" in result[0].reasons


def test_validate_candidate_nodes_converts_existing_node_label():
    ontology = _ontology()
    result = validate_candidate_nodes(
        [{"label": "占有保护", "match_type": "candidate_new_node"}],
        ontology=ontology,
        retrieved_nodes=[],
        paper_title="数字私力救济",
        paper_text="本文讨论占有保护。",
    )

    assert result[0].status == "accepted"
    assert result[0].match_type == "existing_node_match"
    assert result[0].matched_node_id == "d05.concept.001"


def test_validate_candidate_nodes_converts_existing_node_id_string():
    ontology = _ontology()
    result = validate_candidate_nodes(
        ["d06.concept.001"],
        ontology=ontology,
        retrieved_nodes=[],
        paper_title="公司决议瑕疵",
        paper_text="本文讨论公司治理。",
    )

    assert result[0].status == "accepted"
    assert result[0].label == "公司治理"
    assert result[0].matched_node_id == "d06.concept.001"


def test_validate_candidate_nodes_accepts_evidenced_extension_node():
    ontology = _ontology()
    result = validate_candidate_nodes(
        [
            {
                "label": "数字私力救济",
                "match_type": "candidate_new_node",
                "parent_node_id": "d05.framework.001",
                "evidence_quote": "本文将远程锁定称为数字私力救济。",
            }
        ],
        ontology=ontology,
        retrieved_nodes=[],
        paper_title="数字私力救济——基于远程控制网联物的权利实现",
        paper_text="本文将远程锁定称为数字私力救济。",
    )

    assert result[0].status == "accepted"
    assert result[0].label == "数字私力救济"


def test_validate_candidate_nodes_normalizes_evidence_spacing():
    ontology = _ontology()
    result = validate_candidate_nodes(
        [
            {
                "label": "法定的不完全免责的债务承担",
                "match_type": "candidate_new_node",
                "parent_node_id": "d05.framework.001",
                "evidence_quote": "公司法第88 条第1 款可称为法定的不完全免责的债务承担。",
            }
        ],
        ontology=ontology,
        retrieved_nodes=[],
        paper_title="股权转让中的出资义务承担",
        paper_text="公司法第88条第1款可称为法定的不完全免责的债务承担。",
    )

    assert result[0].status == "accepted"


def test_validate_candidate_nodes_accepts_ellipsis_in_evidence_quote():
    ontology = _ontology()
    result = validate_candidate_nodes(
        [
            {
                "label": "法定的不完全免责的债务承担",
                "match_type": "candidate_new_node",
                "parent_node_id": "d05.framework.001",
                "evidence_quote": "公司法第88条第1款可解释为法定的不完全免责的债务承担。…不完全免责的债务承担则是指原债务人不从债权债务关系中退出",
            }
        ],
        ontology=ontology,
        retrieved_nodes=[],
        paper_title="股权转让中的出资义务承担",
        paper_text="公司法第88条第1款可解释为法定的不完全免责的债务承担。",
    )

    assert result[0].status == "accepted"


def test_validate_candidate_nodes_marks_missing_parent_for_review():
    ontology = _ontology()
    result = validate_candidate_nodes(
        [
            {
                "label": "数字私力正当程序",
                "match_type": "candidate_new_node",
                "evidence_quote": "数字私力正当程序应当包含通知机制。",
            }
        ],
        ontology=ontology,
        retrieved_nodes=[],
        paper_title="数字私力救济",
        paper_text="数字私力正当程序应当包含通知机制。",
    )

    assert result[0].status == "needs_review"
    assert "missing_parent_node_id" in result[0].reasons


def test_validate_node_matches_rejects_unknown_node_id():
    ontology = _ontology()
    retrieved = retrieve_nodes("占有保护", ontology, top_k=5)

    result = validate_node_matches(
        [
            {"node_id": "d05.concept.001", "evidence_quote": "占有保护"},
            {"node_id": "d99.concept.001", "evidence_quote": "不存在"},
        ],
        ontology=ontology,
        retrieved_nodes=retrieved,
    )

    assert result[0].status == "accepted"
    assert result[1].status == "rejected"
    assert "unknown_node_id" in result[1].reasons


def test_validate_node_matches_accepts_string_path():
    ontology = _ontology()
    result = validate_node_matches(
        ["商法学 > 标识性概念 > 公司治理"],
        ontology=ontology,
        retrieved_nodes=[],
    )

    assert result[0].status == "accepted"
    assert result[0].node_id == "d06.concept.001"
