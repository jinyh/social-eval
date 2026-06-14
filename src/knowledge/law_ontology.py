"""Structured ontology helpers for the Chinese law knowledge tree."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "1.0"

SECTION_MAP = {
    "标识性概念": ("concepts", "concept", "标识性概念"),
    "原创性理论": ("theories", "theory", "原创性理论"),
    "框架结构": ("frameworks", "framework", "框架结构"),
}


@dataclass(frozen=True)
class LawOntologyNode:
    node_id: str
    label: str
    node_type: str
    discipline_code: str
    discipline_label: str
    parent_id: str | None
    path: list[str]
    level: int
    aliases: list[str]
    keywords: list[str]
    source_line: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LawOntology:
    schema_version: str
    source_path: str
    source_sha256: str
    nodes: list[LawOntologyNode]

    def find_node(self, node_id: str) -> LawOntologyNode | None:
        return self.node_index().get(node_id)

    def node_index(self) -> dict[str, LawOntologyNode]:
        return {node.node_id: node for node in self.nodes}

    def nodes_by_label(self) -> dict[str, list[LawOntologyNode]]:
        index: dict[str, list[LawOntologyNode]] = {}
        for node in self.nodes:
            index.setdefault(_normalize_label(node.label), []).append(node)
        return index

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "source_path": self.source_path,
            "source_sha256": self.source_sha256,
            "nodes": [node.to_dict() for node in self.nodes],
        }


def load_law_ontology(path: Path) -> LawOntology:
    data = json.loads(path.read_text(encoding="utf-8"))
    return LawOntology(
        schema_version=str(data.get("schema_version", SCHEMA_VERSION)),
        source_path=str(data.get("source_path", "")),
        source_sha256=str(data.get("source_sha256", "")),
        nodes=[LawOntologyNode(**node) for node in data.get("nodes", [])],
    )


def write_law_ontology(ontology: LawOntology, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(ontology.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def parse_law_tree_markdown(text: str, source_path: str) -> LawOntology:
    """Parse the handbook-derived tree markdown into stable ontology nodes."""

    lines = text.splitlines()
    source_sha256 = hashlib.sha256(text.encode("utf-8")).hexdigest()
    nodes: list[LawOntologyNode] = [
        LawOntologyNode(
            node_id="root",
            label="中国法学自主知识体系",
            node_type="root",
            discipline_code="",
            discipline_label="",
            parent_id=None,
            path=["中国法学自主知识体系"],
            level=0,
            aliases=[],
            keywords=["中国法学自主知识体系"],
            source_line=None,
        )
    ]

    current_discipline: dict[str, str] | None = None
    current_section: tuple[str, str, str] | None = None
    counters: dict[tuple[str, str], int] = {}
    section_created: set[str] = set()

    discipline_pattern = re.compile(
        r"[├└]──\s*(\d+)\.\s*(.+?)自主知识体系\s*〔(d\d+)〕"
    )

    for line_no, line in enumerate(lines, start=1):
        discipline_match = discipline_pattern.search(line)
        if discipline_match:
            code = discipline_match.group(3)
            label = discipline_match.group(2).strip()
            current_discipline = {"code": code, "label": label}
            current_section = None
            nodes.append(
                LawOntologyNode(
                    node_id=code,
                    label=label,
                    node_type="discipline",
                    discipline_code=code,
                    discipline_label=label,
                    parent_id="root",
                    path=["中国法学自主知识体系", label],
                    level=1,
                    aliases=[],
                    keywords=_keywords_for_label(label),
                    source_line=line_no,
                )
            )
            continue

        if current_discipline is None:
            continue

        section = _detect_section(line)
        if section:
            current_section = section
            section_suffix, _node_type, section_label = section
            section_id = f"{current_discipline['code']}.{section_suffix}"
            if section_id not in section_created:
                section_created.add(section_id)
                nodes.append(
                    LawOntologyNode(
                        node_id=section_id,
                        label=section_label,
                        node_type="section",
                        discipline_code=current_discipline["code"],
                        discipline_label=current_discipline["label"],
                        parent_id=current_discipline["code"],
                        path=[
                            "中国法学自主知识体系",
                            current_discipline["label"],
                            section_label,
                        ],
                        level=2,
                        aliases=[],
                        keywords=[section_label],
                        source_line=line_no,
                    )
                )
            continue

        if current_section is None:
            continue

        if _starts_non_target_section(line):
            current_section = None
            continue

        label = _extract_tree_item_label(line)
        if not label:
            continue

        section_suffix, node_type, section_label = current_section
        key = (current_discipline["code"], node_type)
        counters[key] = counters.get(key, 0) + 1
        node_id = f"{current_discipline['code']}.{node_type}.{counters[key]:03d}"
        nodes.append(
            LawOntologyNode(
                node_id=node_id,
                label=label,
                node_type=node_type,
                discipline_code=current_discipline["code"],
                discipline_label=current_discipline["label"],
                parent_id=f"{current_discipline['code']}.{section_suffix}",
                path=[
                    "中国法学自主知识体系",
                    current_discipline["label"],
                    section_label,
                    label,
                ],
                level=3,
                aliases=[],
                keywords=_keywords_for_label(label),
                source_line=line_no,
            )
        )

    return LawOntology(
        schema_version=SCHEMA_VERSION,
        source_path=source_path,
        source_sha256=source_sha256,
        nodes=nodes,
    )


def _detect_section(line: str) -> tuple[str, str, str] | None:
    for title, section in SECTION_MAP.items():
        if title in line and re.search(
            r"[一二三四五六七八九十]、|\([一二三四]\)", line
        ):
            return section
    return None


def _starts_non_target_section(line: str) -> bool:
    return bool(
        re.search(r"[├└]──\s*[一二三四五六七八九十]+、", line)
        and not any(title in line for title in SECTION_MAP)
    )


def _extract_tree_item_label(line: str) -> str:
    match = re.search(r"[├└]──\s*(.+)", line)
    if not match:
        return ""
    label = match.group(1).strip()
    label = re.sub(r"^\d+\.\s*", "", label)
    label = re.sub(r"^\([一二三四五六七八九十\d]+\)\s*", "", label)
    label = re.sub(r"^第[一二三四五六七八九十\d]+[部分]*[：:、]\s*", "", label)
    return label.strip()


def _keywords_for_label(label: str) -> list[str]:
    raw_terms = re.split(r"[、，,；;]", label)
    keywords: set[str] = set()
    for term in raw_terms:
        clean = term.strip().strip("“”「」『』")
        if clean:
            keywords.add(clean)
        no_paren = re.sub(r"[（(].+?[）)]", "", clean).strip()
        if no_paren:
            keywords.add(no_paren)
            for suffix in (
                "理论",
                "体系",
                "原则",
                "制度",
                "机制",
                "治理",
                "保护",
                "论",
            ):
                if no_paren.endswith(suffix) and len(no_paren) > len(suffix) + 1:
                    keywords.add(no_paren[: -len(suffix)])
        paren_match = re.search(r"[（(](.+?)[）)]", clean)
        if paren_match:
            for part in re.split(r"[、，,；;]", paren_match.group(1)):
                part = part.strip()
                if part:
                    keywords.add(part)
    return sorted(keyword for keyword in keywords if len(keyword) >= 2)


def _normalize_label(label: str) -> str:
    return re.sub(r"\s+", "", label).strip().lower()
