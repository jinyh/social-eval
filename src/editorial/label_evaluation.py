from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

HUMAN_DECISIONS = {
    "reject",
    "major_revision",
    "minor_accept",
    "direct_accept",
    "accept_unspecified",
    "decline_without_review",
    "revise_resubmit",
    "send_external_review",
    "priority_external_review",
}
AI_DECISIONS = {
    "reject",
    "major_revision",
    "minor_accept",
    "direct_accept",
    "decline_without_review",
    "revise_resubmit",
    "send_external_review",
    "priority_external_review",
}


@dataclass(frozen=True)
class IssueAlignment:
    """AI 与人工问题点的离线对齐指标。"""

    mean_best_match: float
    coverage_at_03: float
    coverage_at_05: float
    issue_count_difference: int
    matched_pairs: tuple[tuple[int, int, float], ...]


def load_label_manifest(path: Path) -> list[dict]:
    """读取人工确认的标签 manifest；不从文件名推断决定。"""

    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    records = payload.get("records", [])
    if not isinstance(records, list):
        raise ValueError("label manifest records must be a list")
    seen: set[str] = set()
    normalized = []
    for item in records:
        if not isinstance(item, dict):
            raise ValueError("label manifest record must be an object")
        record_id = str(item.get("id", "")).strip()
        decision = str(item.get("human_decision", "")).strip()
        if not record_id or record_id in seen:
            raise ValueError(f"invalid or duplicate label id: {record_id}")
        if decision not in HUMAN_DECISIONS:
            raise ValueError(f"invalid human decision: {decision}")
        seen.add(record_id)
        normalized.append(dict(item))
    return normalized


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", "", text).lower()


def _char_ngrams(text: str, minimum: int = 2, maximum: int = 4) -> Counter[str]:
    normalized = _normalize_text(text)
    grams: Counter[str] = Counter()
    for size in range(minimum, maximum + 1):
        grams.update(
            normalized[index : index + size]
            for index in range(max(0, len(normalized) - size + 1))
        )
    return grams


def _tfidf_vectors(texts: list[str]) -> list[dict[str, float]]:
    term_counts = [_char_ngrams(text) for text in texts]
    document_frequency: Counter[str] = Counter()
    for counts in term_counts:
        document_frequency.update(counts.keys())
    total = len(texts)
    vectors: list[dict[str, float]] = []
    for counts in term_counts:
        norm_count = sum(counts.values()) or 1
        vector = {
            term: (count / norm_count)
            * (math.log((1 + total) / (1 + document_frequency[term])) + 1)
            for term, count in counts.items()
        }
        vectors.append(vector)
    return vectors


def _cosine(left: dict[str, float], right: dict[str, float]) -> float:
    if not left or not right:
        return 0.0
    common = left.keys() & right.keys()
    numerator = sum(left[key] * right[key] for key in common)
    left_norm = math.sqrt(sum(value * value for value in left.values()))
    right_norm = math.sqrt(sum(value * value for value in right.values()))
    return numerator / (left_norm * right_norm) if left_norm and right_norm else 0.0


def _maximum_one_to_one(
    matrix: list[list[float]],
) -> tuple[tuple[int, int, float], ...]:
    if not matrix or not matrix[0]:
        return ()
    rows = len(matrix)
    columns = len(matrix[0])
    transposed = False
    working = matrix
    if columns > rows:
        transposed = True
        working = [list(row) for row in zip(*matrix, strict=True)]
        rows, columns = columns, rows
    if columns > 20:
        raise ValueError("exact issue matching supports at most 20 issues per side")

    @lru_cache(maxsize=None)
    def solve(row: int, used: int) -> tuple[float, tuple[tuple[int, int, float], ...]]:
        if row == rows:
            return 0.0, ()
        best_score, best_pairs = solve(row + 1, used)
        for column in range(columns):
            if used & (1 << column):
                continue
            suffix_score, suffix_pairs = solve(row + 1, used | (1 << column))
            score = working[row][column] + suffix_score
            if score > best_score:
                best_score = score
                best_pairs = ((row, column, working[row][column]),) + suffix_pairs
        return best_score, best_pairs

    pairs = solve(0, 0)[1]
    if transposed:
        return tuple((column, row, score) for row, column, score in pairs)
    return pairs


def align_issue_lists(ai_issues: list[str], human_issues: list[str]) -> IssueAlignment:
    """以字符 n-gram TF-IDF 和最大一对一匹配计算问题点重合度。"""

    if not ai_issues or not human_issues:
        return IssueAlignment(
            mean_best_match=0.0,
            coverage_at_03=0.0,
            coverage_at_05=0.0,
            issue_count_difference=len(ai_issues) - len(human_issues),
            matched_pairs=(),
        )
    vectors = _tfidf_vectors([*ai_issues, *human_issues])
    ai_vectors = vectors[: len(ai_issues)]
    human_vectors = vectors[len(ai_issues) :]
    matrix = [
        [_cosine(ai_vector, human_vector) for human_vector in human_vectors]
        for ai_vector in ai_vectors
    ]
    pairs = _maximum_one_to_one(matrix)
    human_scores = {human: score for _, human, score in pairs}
    best_per_human = [
        max(matrix[ai][human] for ai in range(len(ai_issues)))
        for human in range(len(human_issues))
    ]
    mean_best = sum(best_per_human) / len(best_per_human)
    return IssueAlignment(
        mean_best_match=mean_best,
        coverage_at_03=sum(
            human_scores.get(index, 0.0) >= 0.3 for index in range(len(human_issues))
        )
        / len(human_issues),
        coverage_at_05=sum(
            human_scores.get(index, 0.0) >= 0.5 for index in range(len(human_issues))
        )
        / len(human_issues),
        issue_count_difference=len(ai_issues) - len(human_issues),
        matched_pairs=pairs,
    )


def evaluate_decision_alignment(records: list[dict]) -> dict:
    """计算跨历史终审与当前编辑预审口径的三分类及同口径四分类准确率。"""

    collapsed = {
        "reject": "reject",
        "major_revision": "revise",
        "minor_accept": "accept",
        "direct_accept": "accept",
        "accept_unspecified": "accept",
        "decline_without_review": "reject",
        "revise_resubmit": "revise",
        "send_external_review": "accept",
        "priority_external_review": "accept",
    }
    final_taxonomy = {
        "reject",
        "major_revision",
        "minor_accept",
        "direct_accept",
    }
    pre_review_taxonomy = {
        "decline_without_review",
        "revise_resubmit",
        "send_external_review",
        "priority_external_review",
    }
    valid = [
        record
        for record in records
        if record.get("human_decision") in HUMAN_DECISIONS
        and record.get("ai_decision") in AI_DECISIONS
    ]
    three_correct = sum(
        collapsed[record["human_decision"]] == collapsed[record["ai_decision"]]
        for record in valid
    )
    adjudicated = []
    for record in valid:
        human = record["human_decision"]
        ai = record["ai_decision"]
        same_final_taxonomy = human in final_taxonomy and ai in final_taxonomy
        same_pre_review_taxonomy = (
            human in pre_review_taxonomy and ai in pre_review_taxonomy
        )
        if same_final_taxonomy or same_pre_review_taxonomy:
            adjudicated.append(record)
    four_correct = sum(
        record["human_decision"] == record["ai_decision"] for record in adjudicated
    )
    return {
        "three_class": {
            "sample_count": len(valid),
            "accuracy": three_correct / len(valid) if valid else None,
        },
        "four_class": {
            "sample_count": len(adjudicated),
            "accuracy": (four_correct / len(adjudicated) if adjudicated else None),
        },
    }
