"""Deterministic retrieval for law ontology nodes."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

from src.knowledge.law_ontology import LawOntology, LawOntologyNode


RETRIEVABLE_NODE_TYPES = {"concept", "theory", "framework", "framework_layer"}
GENERIC_BLACKLIST = {
    "法",
    "法律",
    "法理",
    "政理",
    "法治",
    "民法",
    "刑法",
    "商法",
    "行政法",
    "经济法",
    "社会法",
    "理论",
    "制度",
    "原则",
    "人权",
    "社会",
    "政法",
    "法人",
    "立法",
    "作品",
    "商标",
    "专利",
    "保护",
    "治理",
}


@dataclass(frozen=True)
class RetrievedNode:
    node_id: str
    label: str
    path: str
    node_type: str
    score: float
    match_methods: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def retrieve_nodes(
    query_text: str,
    ontology: LawOntology,
    *,
    discipline_hint: str | None = None,
    top_k: int = 30,
) -> list[RetrievedNode]:
    """Return top ontology nodes matched by deterministic keyword evidence."""

    normalized_text = _normalize_text(query_text)
    if not normalized_text:
        return []

    results: list[RetrievedNode] = []
    for node in ontology.nodes:
        if node.node_type not in RETRIEVABLE_NODE_TYPES:
            continue
        score, methods = _score_node(node, normalized_text, discipline_hint)
        if score <= 0:
            continue
        results.append(
            RetrievedNode(
                node_id=node.node_id,
                label=node.label,
                path=" > ".join(node.path[1:]),
                node_type=node.node_type,
                score=round(score, 4),
                match_methods=methods,
            )
        )

    return sorted(results, key=lambda item: (-item.score, item.path, item.node_id))[
        :top_k
    ]


def _score_node(
    node: LawOntologyNode,
    normalized_text: str,
    discipline_hint: str | None,
) -> tuple[float, list[str]]:
    score = 0.0
    methods: list[str] = []
    matched_keyword = False

    for keyword in node.keywords:
        keyword_norm = _normalize_text(keyword)
        if not keyword_norm or keyword_norm in GENERIC_BLACKLIST:
            continue
        if keyword_norm in normalized_text:
            matched_keyword = True
            score += min(0.75, 0.35 + len(keyword_norm) * 0.03)
            if "keyword" not in methods:
                methods.append("keyword")

    label_norm = _normalize_text(node.label)
    if (
        len(label_norm) >= 2
        and label_norm not in GENERIC_BLACKLIST
        and label_norm in normalized_text
    ):
        matched_keyword = True
        score += 0.2
        if "label" not in methods:
            methods.append("label")

    if not matched_keyword:
        fallback_score = _discipline_fallback_score(node, discipline_hint)
        if fallback_score <= 0:
            return 0.0, []
        return fallback_score, ["discipline_hint"]

    if discipline_hint and _discipline_matches(discipline_hint, node.discipline_label):
        score += 0.1
        methods.append("discipline_hint")
    elif discipline_hint:
        score = min(score - 0.12, 0.28)

    return max(0.0, min(score, 1.0)), methods


def _discipline_fallback_score(
    node: LawOntologyNode,
    discipline_hint: str | None,
) -> float:
    if not discipline_hint or not _discipline_matches(
        discipline_hint, node.discipline_label
    ):
        return 0.0
    label_norm = _normalize_text(node.label)
    if node.node_type == "framework":
        return 0.18
    if node.node_type == "theory":
        return 0.14
    if node.node_type == "framework_layer":
        return 0.12
    if (
        node.node_type == "concept"
        and len(label_norm) >= 3
        and label_norm not in GENERIC_BLACKLIST
    ):
        return 0.1
    return 0.0


def _discipline_matches(hint: str, discipline_label: str) -> bool:
    hint_norm = _normalize_text(hint)
    discipline_norm = _normalize_text(discipline_label)
    if not hint_norm or not discipline_norm:
        return False
    if hint_norm in discipline_norm or discipline_norm in hint_norm:
        return True
    if "民商" in hint_norm and discipline_norm in {"民法学", "商法学"}:
        return True
    if "诉讼" in hint_norm and discipline_norm in {"民事诉讼法学", "刑事诉讼法学"}:
        return True
    return False


def _normalize_text(text: str) -> str:
    text = re.sub(r"\s+", "", str(text))
    return text.strip().lower()
