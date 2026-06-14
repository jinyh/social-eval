"""Validation helpers for ontology matches and proposed candidate nodes."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

from src.knowledge.law_ontology import LawOntology, LawOntologyNode
from src.knowledge.node_retrieval import RetrievedNode


NODE_ID_PATTERN = re.compile(
    r"\b(d\d{2}\.(?:concept|theory|framework|framework_layer)\.\d{3}|"
    r"d\d{2}\.(?:concepts|theories|frameworks)|d\d{2}|root)\b"
)

VALID_MATCH_TYPES = {
    "existing_node",
    "existing_node_match",
    "extension_node",
    "cross_node",
    "candidate_new_node",
}


@dataclass(frozen=True)
class ValidatedCandidateNode:
    label: str
    status: str
    match_type: str
    parent_node_id: str | None
    matched_node_id: str | None
    evidence_quote: str
    rationale: str
    reasons: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ValidatedNodeMatch:
    node_id: str
    label: str
    status: str
    match_type: str
    evidence_quote: str
    rationale: str
    reasons: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def validate_node_matches(
    node_matches: list[Any],
    *,
    ontology: LawOntology,
    retrieved_nodes: list[RetrievedNode],
) -> list[ValidatedNodeMatch]:
    retrieved_ids = {node.node_id for node in retrieved_nodes}
    validated: list[ValidatedNodeMatch] = []
    for raw in node_matches:
        payload = _coerce_node_match(raw, ontology)
        if payload is None:
            continue

        node_id = payload["node_id"]
        label = payload["label"]
        evidence = payload["evidence_quote"]
        rationale = payload["rationale"]
        node = ontology.find_node(node_id) if node_id else None
        reasons: list[str] = []
        if not node_id or node is None:
            reasons.append("unknown_node_id")
            validated.append(
                ValidatedNodeMatch(
                    node_id=node_id,
                    label=label,
                    status="rejected",
                    match_type="existing_node",
                    evidence_quote=evidence,
                    rationale=rationale,
                    reasons=reasons,
                )
            )
            continue
        if node_id not in retrieved_ids:
            reasons.append("not_in_retrieved_candidates")
        validated.append(
            ValidatedNodeMatch(
                node_id=node_id,
                label=node.label,
                status="accepted",
                match_type="existing_node",
                evidence_quote=evidence,
                rationale=rationale,
                reasons=reasons,
            )
        )
    return validated


def validate_candidate_nodes(
    candidate_nodes: list[dict[str, Any]],
    *,
    ontology: LawOntology,
    retrieved_nodes: list[RetrievedNode],
    paper_title: str,
    paper_text: str,
) -> list[ValidatedCandidateNode]:
    _ = retrieved_nodes
    label_index = ontology.nodes_by_label()
    validated: list[ValidatedCandidateNode] = []
    for raw in candidate_nodes:
        payload = _coerce_candidate(raw)
        if not payload:
            continue

        label = payload["label"]
        match_type = payload["match_type"]
        parent_node_id = payload["parent_node_id"]
        evidence = payload["evidence_quote"]
        rationale = payload["rationale"]
        reasons: list[str] = []

        existing_node = _node_from_text(label, ontology)
        if existing_node is not None:
            validated.append(
                ValidatedCandidateNode(
                    label=existing_node.label,
                    status="accepted",
                    match_type="existing_node_match",
                    parent_node_id=existing_node.parent_id,
                    matched_node_id=existing_node.node_id,
                    evidence_quote=evidence,
                    rationale=rationale,
                    reasons=["converted_existing_node_id"],
                )
            )
            continue

        label_tail = _label_tail(label)
        existing_nodes = label_index.get(_normalize(label_tail), [])
        if existing_nodes:
            node = existing_nodes[0]
            validated.append(
                ValidatedCandidateNode(
                    label=node.label,
                    status="accepted",
                    match_type="existing_node_match",
                    parent_node_id=node.parent_id,
                    matched_node_id=node.node_id,
                    evidence_quote=evidence,
                    rationale=rationale,
                    reasons=["converted_existing_node_label"],
                )
            )
            continue

        if len(label) < 2 or len(label) > 24:
            reasons.append("invalid_label_length")
        if _looks_like_title_wrapper(label, paper_title):
            reasons.append("title_wrapper")
        if match_type not in VALID_MATCH_TYPES:
            reasons.append("invalid_match_type")
        if not parent_node_id:
            reasons.append("missing_parent_node_id")
        elif ontology.find_node(parent_node_id) is None:
            reasons.append("unknown_parent_node_id")
        if not evidence:
            reasons.append("missing_evidence_quote")
        elif paper_text and not _evidence_in_text(evidence, paper_text):
            reasons.append("evidence_not_found_in_text")

        status = _status_for_reasons(reasons)
        validated.append(
            ValidatedCandidateNode(
                label=label,
                status=status,
                match_type=match_type,
                parent_node_id=parent_node_id or None,
                matched_node_id=None,
                evidence_quote=evidence,
                rationale=rationale,
                reasons=reasons,
            )
        )
    return validated


def _coerce_node_match(raw: Any, ontology: LawOntology) -> dict[str, str] | None:
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return None
        node = _node_from_text(text, ontology)
        return {
            "node_id": node.node_id if node else _extract_node_id(text),
            "label": node.label if node else text,
            "evidence_quote": "",
            "rationale": "",
        }
    if not isinstance(raw, dict):
        return None

    text_candidates = [
        str(raw.get("node_id") or ""),
        str(raw.get("matched_node_id") or ""),
        str(raw.get("label") or ""),
        str(raw.get("name") or ""),
        str(raw.get("node") or ""),
        str(raw.get("path") or ""),
    ]
    node = next(
        (
            matched
            for text in text_candidates
            if (matched := _node_from_text(text, ontology))
        ),
        None,
    )
    node_id = (
        node.node_id
        if node
        else next(
            (
                node_id
                for text in text_candidates
                if (node_id := _extract_node_id(text))
            ),
            "",
        )
    )
    label = (
        node.label
        if node
        else next(
            (text.strip() for text in text_candidates if text.strip()),
            "",
        )
    )
    return {
        "node_id": node_id,
        "label": label,
        "evidence_quote": _evidence(raw),
        "rationale": str(raw.get("rationale", "") or ""),
    }


def _coerce_candidate(raw: Any) -> dict[str, str] | None:
    if isinstance(raw, str):
        label = raw.strip()
        if not label:
            return None
        return {
            "label": label,
            "match_type": "candidate_new_node",
            "parent_node_id": "",
            "evidence_quote": "",
            "rationale": "",
        }
    if not isinstance(raw, dict):
        return None
    label = str(
        raw.get("label") or raw.get("name") or raw.get("node_label") or ""
    ).strip()
    if not label:
        return None
    return {
        "label": label,
        "match_type": str(raw.get("match_type") or "candidate_new_node").strip(),
        "parent_node_id": str(raw.get("parent_node_id") or "").strip(),
        "evidence_quote": _evidence(raw),
        "rationale": str(raw.get("rationale") or raw.get("description") or "").strip(),
    }


def _evidence(raw: dict[str, Any]) -> str:
    return str(
        raw.get("evidence_quote") or raw.get("evidence") or raw.get("quote") or ""
    ).strip()


def _status_for_reasons(reasons: list[str]) -> str:
    hard_rejections = {
        "invalid_label_length",
        "title_wrapper",
        "invalid_match_type",
        "unknown_parent_node_id",
    }
    if any(reason in hard_rejections for reason in reasons):
        return "rejected"
    if reasons:
        return "needs_review"
    return "accepted"


def _looks_like_title_wrapper(label: str, paper_title: str) -> bool:
    normalized_label = _normalize(label)
    normalized_title = _normalize(paper_title)
    if len(normalized_label) < 8:
        return False
    title_head = re.split(r"[—\-:：——]", normalized_title, maxsplit=1)[0]
    return normalized_title == normalized_label or title_head == normalized_label


def _node_from_text(text: str, ontology: LawOntology) -> LawOntologyNode | None:
    text = str(text or "").strip()
    if not text:
        return None
    node_id = _extract_node_id(text)
    if node_id:
        node = ontology.find_node(node_id)
        if node:
            return node
    return _node_from_label(_label_tail(text), ontology)


def _node_from_label(label: str, ontology: LawOntology) -> LawOntologyNode | None:
    matches = ontology.nodes_by_label().get(_normalize(label), [])
    return matches[0] if matches else None


def _extract_node_id(text: str) -> str:
    match = NODE_ID_PATTERN.search(str(text or ""))
    return match.group(1) if match else ""


def _label_tail(text: str) -> str:
    text = str(text or "").strip()
    if ">" in text:
        return text.rsplit(">", 1)[-1].strip()
    return re.sub(r"^\[[^\]]+\]\s*", "", text).strip()


def _evidence_in_text(evidence: str, paper_text: str) -> bool:
    if "..." in evidence or "…" in evidence:
        return True
    evidence_norm = _normalize_evidence(evidence)
    text_norm = _normalize_evidence(paper_text)
    if not evidence_norm:
        return False
    return evidence_norm in text_norm


def _normalize_evidence(text: str) -> str:
    text = re.sub(r"\s+", "", str(text))
    text = re.sub(r"[“”\"'‘’（）()，,。；;：:、]", "", text)
    return text.strip().lower()


def _normalize(text: str) -> str:
    return re.sub(r"\s+", "", str(text)).strip().lower()
