from src.knowledge.law_ontology import parse_law_tree_markdown
from src.knowledge.node_retrieval import retrieve_nodes


SAMPLE_TREE = """# 中国法学自主知识体系 - 树状知识库

```
中国法学自主知识体系
├── 5. 民法学自主知识体系 〔d05〕〔主干学科〕
│   ├── 二、标识性概念
│   │   ├── 1. 占有保护
│   │   └── 2. 民事权利
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


def test_retrieve_nodes_returns_keyword_and_discipline_matches():
    results = retrieve_nodes(
        "本文讨论远程锁定网联物时的占有保护问题。",
        _ontology(),
        discipline_hint="民法学",
        top_k=5,
    )

    labels = [result.label for result in results]

    assert "占有保护" in labels
    assert results[0].score > 0
    assert "keyword" in results[0].match_methods


def test_retrieve_nodes_filters_generic_single_terms():
    results = retrieve_nodes("法律 民法 法治", _ontology(), top_k=5)

    assert results == []


def test_retrieve_nodes_can_use_title_level_business_law_terms():
    results = retrieve_nodes("公司治理中的股东会决议瑕疵", _ontology(), top_k=5)

    labels = [result.label for result in results]

    assert "公司治理" in labels


def test_retrieve_nodes_uses_framework_short_keywords():
    results = retrieve_nodes("物权法中的占有保护", _ontology(), top_k=5)

    labels = [result.label for result in results]

    assert "物权理论（占有保护）" in labels
