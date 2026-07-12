#!/usr/bin/env python3
"""
Match the current expert-review Top50 papers to the law knowledge tree.

This script uses the current Top50 source file as the paper-ID authority:
results/e2-pool/top50-proportional.json

Outputs:
- results/top101/top50-knowledge-matching-v2.csv
- results/top101/top50-knowledge-matching-v2-summary.json
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

import fitz
import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.core.config import settings  # noqa: E402
from src.evaluation.providers.factory import create_providers  # noqa: E402


KNOWLEDGE_MD = PROJECT_ROOT / "knowledge" / "中国法学自主知识体系-树状知识库.md"
TOP50_JSON = PROJECT_ROOT / "results" / "top101" / "top50-proportional.json"
PAPER_DIR = PROJECT_ROOT / "raw" / "fullpaper"
OUTPUT_CSV = PROJECT_ROOT / "results" / "top101" / "top50-knowledge-matching-v2.csv"
OUTPUT_SUMMARY = (
    PROJECT_ROOT / "results" / "top101" / "top50-knowledge-matching-v2-summary.json"
)
OUTPUT_AUDIT = (
    PROJECT_ROOT / "results" / "top101" / "top50-knowledge-matching-v2-audit.jsonl"
)
CACHE_DIR = PROJECT_ROOT / ".cache" / "embeddings"

EMBEDDING_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"
DEFAULT_LLM_MODEL = "qwen3.6-plus"

SEMANTIC_THRESHOLDS = {
    "标识性概念": 0.72,
    "原创性理论": 0.68,
    "框架结构": 0.65,
}

GENERIC_BLACKLIST = {
    "法",
    "礼",
    "刑",
    "法律",
    "法理",
    "政理",
    "法治",
    "政法",
    "行政法",
    "经济法",
    "社会法",
    "刑法",
    "民法",
}

CSV_COLUMNS = [
    "专家清单序号",
    "论文编号",
    "期刊",
    "年份",
    "期",
    "题目",
    "作者",
    "作者机构",
    "专家审阅学科",
    "AI辅助内容评价分",
    "AI辅助内容评价分区间",
    "分歧值（以标准差衡量）",
    "分歧区间",
    "候选来源",
    "核验模型",
    "主要对应学科",
    "次要对应学科",
    "标识性概念对应",
    "原创性理论对应",
    "框架结构对应",
    "对应条目总数",
    "匹配方法统计",
    "模型核验明细",
    "备注",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Match current Top50 papers to the Chinese law knowledge tree."
    )
    parser.add_argument("--top50", type=Path, default=TOP50_JSON)
    parser.add_argument("--knowledge", type=Path, default=KNOWLEDGE_MD)
    parser.add_argument("--paper-dir", type=Path, default=PAPER_DIR)
    parser.add_argument("--output-csv", type=Path, default=OUTPUT_CSV)
    parser.add_argument("--output-summary", type=Path, default=OUTPUT_SUMMARY)
    parser.add_argument("--output-audit", type=Path, default=OUTPUT_AUDIT)
    parser.add_argument("--model", default=DEFAULT_LLM_MODEL)
    parser.add_argument("--models", nargs="+", default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--concurrency", type=int, default=5)
    parser.add_argument("--model-concurrency", type=int, default=None)
    parser.add_argument("--no-llm", action="store_true")
    return parser.parse_args()


def parse_knowledge_base(md_path: Path) -> dict[str, dict[str, list[str]]]:
    text = md_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    discipline_pattern = re.compile(
        r"[├└]──\s*(\d+)\.\s*(.+?)自主知识体系\s*〔(d\d+)〕"
    )

    disciplines: list[dict[str, Any]] = []
    for line_no, line in enumerate(lines):
        match = discipline_pattern.search(line)
        if match:
            disciplines.append(
                {
                    "num": match.group(1),
                    "name": match.group(2).strip(),
                    "code": match.group(3),
                    "line": line_no,
                    "key": f"{match.group(3)}_{match.group(2).strip()}",
                }
            )

    soul_match = next(
        (
            (line_no, line)
            for line_no, line in enumerate(lines)
            if re.search(r"[├└]──\s*★\s*灵魂", line)
        ),
        None,
    )
    if soul_match:
        disciplines.insert(
            0,
            {
                "num": "0",
                "name": "习近平法治思想",
                "code": "d00",
                "line": soul_match[0],
                "key": "d00_习近平法治思想",
            },
        )

    knowledge: dict[str, dict[str, list[str]]] = {}
    for index, discipline in enumerate(disciplines):
        start_line = discipline["line"]
        end_line = disciplines[index + 1]["line"] if index + 1 < len(disciplines) else len(lines)
        section_lines = lines[start_line:end_line]
        entry = {"标识性概念": [], "原创性理论": [], "框架结构": []}
        current_section: str | None = None

        for line in section_lines:
            if "标识性概念" in line and re.search(r"[一二三四]、|\([一二三四]\)", line):
                current_section = "标识性概念"
                continue
            if "原创性理论" in line and re.search(r"[一二三四]、|\([一二三四]\)", line):
                current_section = "原创性理论"
                continue
            if "框架结构" in line and re.search(r"[一二三四]、|\([一二三四]\)", line):
                current_section = "框架结构"
                continue
            if re.search(r"[├└]──\s*[一二三四五六七八九十]+、", line):
                current_section = None
                continue

            if current_section is None:
                continue

            item_match = re.search(r"[├└]──\s*(?:\d+\.\s*|\(\S+?\)\s*)?(.+)", line)
            if not item_match:
                continue
            item_text = item_match.group(1).strip()
            if item_text:
                entry[current_section].append(item_text)

        knowledge[discipline["key"]] = entry

    return knowledge


def _term_candidates(item: str, category: str) -> list[str]:
    if category == "标识性概念":
        return [
            part.strip()
            for part in re.split(r"[、，,；;]", item)
            if len(part.strip()) >= 2
        ]
    return [item]


def _generate_keywords(item: str, category: str) -> list[str]:
    keywords: set[str] = set()
    for term in _term_candidates(item, category):
        clean = re.sub(r"[（(].+?[）)]", "", term).strip()
        clean = clean.strip("“”「」『』")
        if len(clean) <= 2 or clean in GENERIC_BLACKLIST:
            continue

        if category == "标识性概念":
            if 3 <= len(clean) <= 12:
                keywords.add(clean)
        elif category == "原创性理论":
            keywords.add(clean)
            for suffix in ["理论", "理念", "命题", "论"]:
                if clean.endswith(suffix) and len(clean) > len(suffix) + 2:
                    keywords.add(clean[: -len(suffix)])
        elif category == "框架结构":
            paren_match = re.search(r"[（(](.+?)[）)]", term)
            if paren_match:
                for part in re.split(r"[、，,；;]", paren_match.group(1)):
                    part = part.strip()
                    if len(part) >= 3:
                        keywords.add(part)
            main = re.sub(r"[（(].+?[）)]", "", term)
            main = re.sub(r"^[第\d一二三四五六七八九十]+[部分：、]*", "", main)
            main = re.sub(r"^\([一二三四五六七八九十\d]+\)\s*", "", main)
            main = main.strip()
            if len(main) >= 3:
                keywords.add(main)

    return sorted(keywords)


def build_keyword_index(
    knowledge: dict[str, dict[str, list[str]]],
) -> dict[str, list[tuple[str, str, str]]]:
    index: dict[str, list[tuple[str, str, str]]] = {}
    for discipline, sections in knowledge.items():
        for category, items in sections.items():
            for item in items:
                for keyword in _generate_keywords(item, category):
                    index.setdefault(keyword, []).append((discipline, category, item))
    return index


def build_semantic_index(
    knowledge: dict[str, dict[str, list[str]]],
    model: SentenceTransformer,
    cache_path: Path,
) -> tuple[list[tuple[str, str, str]], np.ndarray]:
    if cache_path.exists():
        data = np.load(cache_path, allow_pickle=True)
        return data["items"].tolist(), data["embeddings"]

    items: list[tuple[str, str, str]] = []
    texts: list[str] = []
    for discipline, sections in knowledge.items():
        for category in ["标识性概念", "原创性理论", "框架结构"]:
            for item in sections.get(category, []):
                if category == "标识性概念" and len(item) < 5:
                    continue
                if category == "框架结构":
                    paren_match = re.search(r"[（(](.+?)[）)]", item)
                    text = paren_match.group(1) if paren_match else item
                    text = re.sub(r"^[第\d一二三四五六七八九十]+[部分：、]*", "", text)
                    text = re.sub(r"^\([一二三四五六七八九十\d]+\)\s*", "", text)
                else:
                    text = item
                items.append((discipline, category, item))
                texts.append(text)

    embeddings = model.encode(texts, show_progress_bar=True, convert_to_numpy=True)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(cache_path, items=np.array(items, dtype=object), embeddings=embeddings)
    return items, embeddings


def extract_paper_text(pdf_path: Path, head_pages: int = 3, tail_pages: int = 2) -> str:
    doc = fitz.open(str(pdf_path))
    try:
        total_pages = len(doc)
        if total_pages <= head_pages + tail_pages + 2:
            pages = [page.get_text() for page in doc]
        else:
            head = [doc[index].get_text() for index in range(min(head_pages, total_pages))]
            tail_start = max(total_pages - tail_pages, head_pages)
            tail = [doc[index].get_text() for index in range(tail_start, total_pages)]
            pages = head + tail
    finally:
        doc.close()
    return re.sub(r"\n{3,}", "\n\n", "\n".join(pages))


def keyword_prefilter(
    text: str,
    keyword_index: dict[str, list[tuple[str, str, str]]],
) -> dict[str, Any]:
    discipline_hits: Counter[str] = Counter()
    discipline_items: dict[str, dict[str, set[str]]] = {}

    for keyword, entries in keyword_index.items():
        if keyword not in text:
            continue
        for discipline, category, item in entries:
            discipline_hits[discipline] += 1
            discipline_items.setdefault(
                discipline,
                {"标识性概念": set(), "原创性理论": set(), "框架结构": set()},
            )
            discipline_items[discipline][category].add(item)

    top_disciplines = discipline_hits.most_common(5)
    candidate_items = {
        discipline: {
            category: sorted(items)
            for category, items in discipline_items.get(discipline, {}).items()
        }
        for discipline, _ in top_disciplines
    }
    return {"top_disciplines": top_disciplines, "candidate_items": candidate_items}


def semantic_match(
    paper_text: str,
    items: list[tuple[str, str, str]],
    embeddings: np.ndarray,
    model: SentenceTransformer,
    top_k: int = 30,
) -> dict[str, dict[str, list[tuple[str, float]]]]:
    paragraphs = [p.strip() for p in paper_text.split("\n\n") if len(p.strip()) > 50]
    if not paragraphs:
        return {}

    para_embeddings = model.encode(paragraphs, show_progress_bar=False, convert_to_numpy=True)
    similarities = cosine_similarity(para_embeddings, embeddings)
    max_similarities = similarities.max(axis=0)

    matches: list[tuple[str, str, str, float]] = []
    for index, similarity in enumerate(max_similarities):
        discipline, category, item = items[index]
        if similarity >= SEMANTIC_THRESHOLDS.get(category, 0.70):
            matches.append((discipline, category, item, float(similarity)))

    result: dict[str, dict[str, list[tuple[str, float]]]] = {}
    for discipline, category, item, similarity in sorted(
        matches, key=lambda row: row[3], reverse=True
    )[:top_k]:
        result.setdefault(
            discipline,
            {"标识性概念": [], "原创性理论": [], "框架结构": []},
        )
        result[discipline][category].append((item, similarity))
    return result


def merge_matches(keyword_result: dict[str, Any], semantic_result: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, dict[str, dict[str, dict[str, Any]]]] = {}
    for discipline, categories in keyword_result["candidate_items"].items():
        merged.setdefault(
            discipline,
            {"标识性概念": {}, "原创性理论": {}, "框架结构": {}},
        )
        for category, items in categories.items():
            for item in items:
                merged[discipline][category][item] = {"method": "keyword", "score": None}

    for discipline, categories in semantic_result.items():
        merged.setdefault(
            discipline,
            {"标识性概念": {}, "原创性理论": {}, "框架结构": {}},
        )
        for category, item_scores in categories.items():
            for item, score in item_scores:
                method = "semantic"
                if item in merged[discipline][category]:
                    method = "keyword+semantic"
                merged[discipline][category][item] = {"method": method, "score": score}
    return merged


def paper_meta_from_top50(paper: dict[str, Any]) -> dict[str, Any]:
    source_label = {
        "E1+E2": "经过候选复评",
        "E1+E2+E3": "经过候选复评与重点复核",
    }.get(str(paper.get("source", "")), str(paper.get("source", "")))
    score = float(paper.get("weighted_score_full", paper.get("score", 0)) or 0)
    disagreement = float(paper.get("weighted_std_full", paper.get("std", 0)) or 0)
    return {
        "专家清单序号": paper.get("rank", ""),
        "论文编号": str(paper.get("pid_padded") or f"{int(paper['pid']):04d}"),
        "期刊": paper.get("journal", ""),
        "年份": paper.get("year", ""),
        "期": paper.get("issue", ""),
        "题目": paper.get("title", ""),
        "作者": paper.get("author", ""),
        "作者机构": paper.get("institution", ""),
        "专家审阅学科": paper.get("category", ""),
        "AI辅助内容评价分": f"{score:.3f}".rstrip("0").rstrip("."),
        "AI辅助内容评价分区间": score_band(score),
        "分歧值（以标准差衡量）": f"{disagreement:.2f}".rstrip("0").rstrip("."),
        "分歧区间": disagreement_band(disagreement),
        "候选来源": source_label,
    }


def score_band(score: float) -> str:
    if score >= 88:
        return "88分及以上"
    if score >= 85:
        return "85-88分"
    if score >= 82:
        return "82-85分"
    return "82分以下"


def disagreement_band(value: float) -> str:
    if value <= 5:
        return "低分歧（分歧值≤5）"
    if value <= 8:
        return "中等分歧（5<分歧值≤8）"
    return "较高分歧（分歧值>8）"


def find_pdf(paper_dir: Path, paper: dict[str, Any]) -> Path | None:
    pid = str(paper.get("pid_padded") or f"{int(paper['pid']):04d}")
    matches = sorted(paper_dir.glob(f"{pid}-*.pdf"))
    return matches[0] if matches else None


def build_llm_prompt(
    paper_meta: dict[str, Any],
    paper_text: str,
    merged_matches: dict[str, Any],
) -> str:
    candidate_text = ""
    for discipline, categories in merged_matches.items():
        discipline_name = discipline.split("_", 1)[1] if "_" in discipline else discipline
        candidate_text += f"\n### {discipline_name}\n"
        for category, items_dict in categories.items():
            if not items_dict:
                continue
            labels = []
            for item, info in items_dict.items():
                score = info["score"]
                method = info["method"]
                if score is None:
                    labels.append(f"{item} [{method}]")
                else:
                    labels.append(f"{item} [{method}, 相似度:{score:.2f}]")
            candidate_text += f"- {category}：{'；'.join(labels)}\n"

    paper_excerpt = paper_text[:6500]
    if len(paper_text) > len(paper_excerpt):
        paper_excerpt += "\n……（文本已截断）"

    return (
        "你是一位法学学术评价专家。请判断以下论文与《中国法学自主知识体系》"
        "树状知识库条目的实质对应关系。\n\n"
        "## 论文信息\n"
        f"- 题目：{paper_meta['题目']}\n"
        f"- 期刊：{paper_meta['期刊']}\n"
        f"- 作者：{paper_meta['作者']}\n"
        f"- 专家审阅学科：{paper_meta['专家审阅学科']}\n\n"
        "## 论文关键文本\n"
        f"{paper_excerpt}\n\n"
        "## 候选知识库条目\n"
        f"{candidate_text or '（未形成候选条目）'}\n\n"
        "## 判断要求\n"
        "1. 只确认论文核心论证中实际涉及的条目，不能只凭词语偶然出现。\n"
        "2. 标识性概念需要有明确文本证据；通用词应从严判断。\n"
        "3. 原创性理论可以识别简称或等价表述，但必须说明其理论关联。\n"
        "4. 框架结构可根据论文论证结构判断，不要求原文出现“本体论”等字样。\n"
        "5. 可以对应多个学科，但须区分主要对应学科和次要对应学科。\n\n"
        "请只输出 JSON，结构如下：\n"
        "{\n"
        '  "primary_discipline": "主要对应学科",\n'
        '  "secondary_disciplines": ["次要对应学科"],\n'
        '  "matches": [\n'
        "    {\n"
        '      "category": "标识性概念 或 原创性理论 或 框架结构",\n'
        '      "discipline": "条目所属学科",\n'
        '      "item": "知识库条目原文",\n'
        '      "evidence": "论文证据片段，30字以内",\n'
        '      "reasoning": "对应理由，60字以内"\n'
        "    }\n"
        "  ],\n"
        '  "confidence": "high/medium/low",\n'
        '  "note": "补充说明"\n'
        "}\n"
    )


async def call_llm(provider: Any, prompt: str) -> dict[str, Any] | None:
    try:
        return await provider.generate_json_response(prompt)
    except Exception as exc:  # noqa: BLE001
        message = str(exc).replace("\n", " ")[:180]
        print(f"    AI辅助语义核验失败：{exc.__class__.__name__}: {message}")
        return None


def model_names_from_args(args: argparse.Namespace) -> list[str]:
    names = args.models if args.models else [args.model]
    return [name.strip() for name in names if name.strip()]


async def call_model_validation(
    model_name: str,
    provider: Any,
    prompt: str,
    paper_meta: dict[str, Any],
    model_semaphore: asyncio.Semaphore,
) -> tuple[str, dict[str, Any] | None, dict[str, Any]]:
    started_at = datetime.now().isoformat(timespec="seconds")
    async with model_semaphore:
        error = ""
        result = None
        try:
            result = await provider.generate_json_response(prompt)
        except Exception as exc:  # noqa: BLE001
            error = f"{exc.__class__.__name__}: {str(exc).replace(chr(10), ' ')[:300]}"
            print(f"    {model_name} 核验失败：{error}")
        finished_at = datetime.now().isoformat(timespec="seconds")

    audit_record = {
        "paper_id": paper_meta.get("论文编号"),
        "paper_title": paper_meta.get("题目"),
        "model": model_name,
        "started_at": started_at,
        "finished_at": finished_at,
        "prompt": prompt,
        "response": result,
        "error": error,
    }
    return model_name, result, audit_record


def _format_match_label(match: dict[str, Any]) -> str:
    item = str(match.get("item", "")).strip()
    discipline = str(match.get("discipline", "")).strip()
    evidence = str(match.get("evidence", "")).strip()
    label = item
    if discipline:
        label += f"[{discipline}]"
    if evidence:
        label += f"（证据：{evidence[:30]}）"
    return label


def _model_match_label(match: dict[str, Any], models: set[str]) -> str:
    label = _format_match_label(match)
    if models:
        label += f"{{{'+'.join(sorted(models))}}}"
    return label


def format_multi_model_result(
    model_results: list[tuple[str, dict[str, Any] | None]],
    merged_matches: dict[str, Any],
) -> dict[str, Any]:
    successful = [(model, result) for model, result in model_results if result is not None]
    if not successful:
        fallback = format_result(None, merged_matches)
        return {
            **fallback,
            "核验模型": "；".join(model for model, _ in model_results),
            "模型核验明细": "全部模型核验失败，已回退到关键词和语义匹配",
        }

    primary_counter: Counter[str] = Counter()
    secondary_counter: Counter[str] = Counter()
    confidence_counter: Counter[str] = Counter()
    notes: list[str] = []
    match_index: dict[tuple[str, str, str], dict[str, Any]] = {}

    for model_name, result in successful:
        primary = str(result.get("primary_discipline", "")).strip()
        if primary:
            primary_counter[primary] += 1
        for discipline in result.get("secondary_disciplines", []):
            discipline = str(discipline).strip()
            if discipline:
                secondary_counter[discipline] += 1
        confidence = str(result.get("confidence", "")).strip()
        if confidence:
            confidence_counter[confidence] += 1
        note = str(result.get("note", "")).strip()
        if note:
            notes.append(f"{model_name}:{note[:80]}")

        for match in result.get("matches", []):
            category = str(match.get("category", "")).strip()
            discipline = str(match.get("discipline", "")).strip()
            item = str(match.get("item", "")).strip()
            if not category or not item:
                continue
            key = (category, discipline, item)
            if key not in match_index:
                match_index[key] = {
                    "match": match,
                    "models": set(),
                }
            match_index[key]["models"].add(model_name)

    concepts: list[str] = []
    theories: list[str] = []
    frameworks: list[str] = []
    for (category, _, _), payload in match_index.items():
        label = _model_match_label(payload["match"], payload["models"])
        if "概念" in category:
            concepts.append(label)
        elif "理论" in category:
            theories.append(label)
        elif "框架" in category:
            frameworks.append(label)

    method_stats: Counter[str] = Counter()
    for categories in merged_matches.values():
        for items_dict in categories.values():
            for info in items_dict.values():
                method_stats[info["method"]] += 1

    primary = primary_counter.most_common(1)[0][0] if primary_counter else ""
    secondary_items = [
        discipline
        for discipline, _ in secondary_counter.most_common()
        if discipline and discipline != primary
    ]
    detail = "；".join(
        f"{model}:{result.get('primary_discipline', '')}/{len(result.get('matches', []))}项"
        for model, result in successful
    )
    failed = [model for model, result in model_results if result is None]
    if failed:
        detail += f"；失败:{'、'.join(failed)}"
    confidence = ""
    if confidence_counter:
        confidence = f"置信度分布:{dict(confidence_counter)}"
    note_parts = [confidence] if confidence else []
    note_parts.extend(notes[:3])

    return {
        "核验模型": "；".join(model for model, _ in model_results),
        "主要对应学科": primary,
        "次要对应学科": "；".join(secondary_items[:5]),
        "标识性概念对应": "；".join(concepts),
        "原创性理论对应": "；".join(theories),
        "框架结构对应": "；".join(frameworks),
        "对应条目总数": len(match_index),
        "匹配方法统计": format_method_stats(
            method_stats,
            llm_verified=sum(len(result.get("matches", [])) for _, result in successful),
        ),
        "模型核验明细": detail,
        "备注": "；".join(note_parts),
    }


def format_result(
    llm_result: dict[str, Any] | None,
    merged_matches: dict[str, Any],
) -> dict[str, Any]:
    if llm_result is None:
        concepts: list[str] = []
        theories: list[str] = []
        frameworks: list[str] = []
        disciplines: list[str] = []
        method_stats: Counter[str] = Counter()

        for discipline, categories in merged_matches.items():
            discipline_name = discipline.split("_", 1)[1] if "_" in discipline else discipline
            disciplines.append(discipline_name)
            for category, items_dict in categories.items():
                for item, info in items_dict.items():
                    method_stats[info["method"]] += 1
                    if category == "标识性概念":
                        concepts.append(item)
                    elif category == "原创性理论":
                        theories.append(item)
                    elif category == "框架结构":
                        frameworks.append(item)

        return {
            "主要对应学科": "；".join(disciplines[:1]),
            "次要对应学科": "；".join(disciplines[1:4]),
            "标识性概念对应": "；".join(concepts[:12]),
            "原创性理论对应": "；".join(theories[:12]),
            "框架结构对应": "；".join(frameworks[:12]),
            "对应条目总数": len(concepts) + len(theories) + len(frameworks),
            "匹配方法统计": format_method_stats(method_stats, llm_verified=0),
            "备注": "仅关键词和语义匹配，未经过AI辅助语义核验",
        }

    matches = llm_result.get("matches", [])
    concepts: list[str] = []
    theories: list[str] = []
    frameworks: list[str] = []
    for match in matches:
        category = str(match.get("category", ""))
        label = _format_match_label(match)
        if "概念" in category:
            concepts.append(label)
        elif "理论" in category:
            theories.append(label)
        elif "框架" in category:
            frameworks.append(label)

    method_stats: Counter[str] = Counter()
    for categories in merged_matches.values():
        for items_dict in categories.values():
            for info in items_dict.values():
                method_stats[info["method"]] += 1

    primary = str(llm_result.get("primary_discipline", "")).strip()
    secondary = [
        str(item).strip()
        for item in llm_result.get("secondary_disciplines", [])
        if str(item).strip()
    ]
    confidence = str(llm_result.get("confidence", "")).strip()
    note = str(llm_result.get("note", "")).strip()
    if confidence:
        note = f"置信度:{confidence}" + (f"；{note}" if note else "")

    return {
        "主要对应学科": primary,
        "次要对应学科": "；".join(secondary),
        "标识性概念对应": "；".join(concepts),
        "原创性理论对应": "；".join(theories),
        "框架结构对应": "；".join(frameworks),
        "对应条目总数": len(concepts) + len(theories) + len(frameworks),
        "匹配方法统计": format_method_stats(method_stats, llm_verified=len(matches)),
        "备注": note,
    }


def format_method_stats(method_stats: Counter[str], llm_verified: int) -> str:
    return (
        f"关键词:{method_stats.get('keyword', 0)}, "
        f"语义:{method_stats.get('semantic', 0)}, "
        f"双重:{method_stats.get('keyword+semantic', 0)}, "
        f"AI核验:{llm_verified}"
    )


def write_csv(rows: list[dict[str, Any]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows([{column: row.get(column, "") for column in CSV_COLUMNS} for row in rows])


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def build_summary(
    rows: list[dict[str, Any]],
    args: argparse.Namespace,
    knowledge_stats: dict[str, int],
    missing_pdfs: list[str],
    llm_enabled: bool,
    model_names: list[str],
    audit_records: list[dict[str, Any]],
) -> dict[str, Any]:
    primary_counts: Counter[str] = Counter()
    source_counts: Counter[str] = Counter()
    category_totals = Counter({"标识性概念": 0, "原创性理论": 0, "框架结构": 0})
    total_matches = 0

    for row in rows:
        primary = str(row.get("主要对应学科", "")).strip()
        if primary:
            primary_counts[primary] += 1
        source = str(row.get("候选来源", "")).strip()
        if source:
            source_counts[source] += 1
        for column, label in [
            ("标识性概念对应", "标识性概念"),
            ("原创性理论对应", "原创性理论"),
            ("框架结构对应", "框架结构"),
        ]:
            text = str(row.get(column, "")).strip()
            if text:
                category_totals[label] += len([item for item in text.split("；") if item])
        total_matches += int(row.get("对应条目总数") or 0)

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_top50": display_path(args.top50),
        "knowledge_base": display_path(args.knowledge),
        "paper_dir": display_path(args.paper_dir),
        "output_csv": display_path(args.output_csv),
        "output_audit": display_path(args.output_audit),
        "total_papers": len(rows),
        "missing_pdfs": missing_pdfs,
        "llm_enabled": llm_enabled,
        "llm_model": args.model if llm_enabled and len(model_names) == 1 else None,
        "llm_models": model_names if llm_enabled else [],
        "audit_records": len(audit_records),
        "knowledge_stats": knowledge_stats,
        "match_stats": {
            "total_matches": total_matches,
            "avg_matches_per_paper": round(total_matches / len(rows), 2) if rows else 0,
            "category_totals": dict(category_totals),
            "primary_discipline_counts": dict(primary_counts.most_common()),
            "source_counts": dict(source_counts.most_common()),
        },
        "method_note": (
            "关键词预筛与中文句向量语义匹配形成候选条目；"
            "启用模型时，通过项目统一 provider 做AI辅助语义核验。"
        ),
    }


def build_paper_matching_context(
    paper: dict[str, Any],
    paper_dir: Path,
    keyword_index: dict[str, list[tuple[str, str, str]]],
    semantic_items: list[tuple[str, str, str]],
    semantic_embeddings: np.ndarray,
    semantic_model: SentenceTransformer,
) -> dict[str, Any]:
    meta = paper_meta_from_top50(paper)
    pdf_path = find_pdf(paper_dir, paper)
    if pdf_path is None:
        return {
            "meta": meta,
            "row": {
                **meta,
                "主要对应学科": "",
                "次要对应学科": "",
                "标识性概念对应": "",
                "原创性理论对应": "",
                "框架结构对应": "",
                "对应条目总数": 0,
                "匹配方法统计": "",
                "备注": "未找到PDF",
            },
            "missing_pdf": meta["论文编号"],
            "log": ["未找到PDF"],
        }

    try:
        paper_text = extract_paper_text(pdf_path)
    except Exception as exc:  # noqa: BLE001
        return {
            "meta": meta,
            "row": {
                **meta,
                "主要对应学科": "",
                "次要对应学科": "",
                "标识性概念对应": "",
                "原创性理论对应": "",
                "框架结构对应": "",
                "对应条目总数": 0,
                "匹配方法统计": "",
                "备注": f"PDF解析失败:{exc}",
            },
            "missing_pdf": None,
            "log": [f"PDF解析失败:{exc}"],
        }

    keyword_result = keyword_prefilter(paper_text, keyword_index)
    semantic_result = semantic_match(
        paper_text,
        semantic_items,
        semantic_embeddings,
        semantic_model,
    )
    merged = merge_matches(keyword_result, semantic_result)
    total_candidates = sum(
        len(items_dict)
        for categories in merged.values()
        for items_dict in categories.values()
    )
    return {
        "meta": meta,
        "paper_text": paper_text,
        "merged": merged,
        "missing_pdf": None,
        "log": [
            f"文本:{len(paper_text)}字",
            (
                f"候选学科:关键词{len(keyword_result['candidate_items'])} "
                f"语义{len(semantic_result)} 候选条目{total_candidates}"
            ),
        ],
    }


async def process_paper(
    index: int,
    total: int,
    paper: dict[str, Any],
    args: argparse.Namespace,
    semaphore: asyncio.Semaphore,
    providers: dict[str, Any],
    model_semaphore: asyncio.Semaphore,
    keyword_index: dict[str, list[tuple[str, str, str]]],
    semantic_items: list[tuple[str, str, str]],
    semantic_embeddings: np.ndarray,
    semantic_model: SentenceTransformer,
) -> tuple[int, dict[str, Any], str | None, list[dict[str, Any]]]:
    async with semaphore:
        meta = paper_meta_from_top50(paper)
        print(f"\n[{index}/{total}] {meta['论文编号']} {meta['题目'][:34]}")
        context = await asyncio.to_thread(
            build_paper_matching_context,
            paper,
            args.paper_dir,
            keyword_index,
            semantic_items,
            semantic_embeddings,
            semantic_model,
        )
        for message in context.get("log", []):
            print(f"  {message}")

        if "row" in context:
            return index, context["row"], context.get("missing_pdf"), []

        audit_records: list[dict[str, Any]] = []
        model_results: list[tuple[str, dict[str, Any] | None]] = []
        if providers:
            prompt = build_llm_prompt(
                context["meta"],
                context["paper_text"],
                context["merged"],
            )
            model_payloads = await asyncio.gather(
                *[
                    call_model_validation(
                        model_name,
                        provider,
                        prompt,
                        context["meta"],
                        model_semaphore,
                    )
                    for model_name, provider in providers.items()
                ]
            )
            for model_name, llm_result, audit_record in model_payloads:
                audit_records.append(audit_record)
                model_results.append((model_name, llm_result))
                if llm_result is not None:
                    print(
                        "  AI核验:"
                        f"{model_name} -> {llm_result.get('primary_discipline', '')} "
                        f"{len(llm_result.get('matches', []))}项"
                    )
            await asyncio.sleep(0.4)

        formatted = (
            format_multi_model_result(model_results, context["merged"])
            if providers
            else format_result(None, context["merged"])
        )
        return (
            index,
            {**context["meta"], **formatted},
            None,
            audit_records,
        )


async def run(args: argparse.Namespace) -> None:
    print("=" * 72)
    print("新 Top50 × 中国法学自主知识体系树状知识库对应分析")
    print("=" * 72)

    print("\n读取知识库...")
    knowledge = parse_knowledge_base(args.knowledge)
    knowledge_stats = {
        "disciplines": len(knowledge),
        "concepts": sum(len(sections["标识性概念"]) for sections in knowledge.values()),
        "theories": sum(len(sections["原创性理论"]) for sections in knowledge.values()),
        "frameworks": sum(len(sections["框架结构"]) for sections in knowledge.values()),
    }
    print(
        "  学科:{disciplines} 标识性概念:{concepts} "
        "原创性理论:{theories} 框架结构:{frameworks}".format(**knowledge_stats)
    )

    keyword_index = build_keyword_index(knowledge)
    print(f"  关键词索引:{len(keyword_index)}")

    print("\n加载语义匹配模型...")
    semantic_model = SentenceTransformer(EMBEDDING_MODEL)
    semantic_items, semantic_embeddings = build_semantic_index(
        knowledge,
        semantic_model,
        CACHE_DIR / "knowledge_embeddings_law_tree_v2.npz",
    )
    print(f"  语义索引:{len(semantic_items)}")

    payload = json.loads(args.top50.read_text(encoding="utf-8"))
    papers = payload.get("papers", [])
    if args.limit is not None:
        papers = papers[: args.limit]
    print(f"\n处理论文:{len(papers)}")

    model_names = model_names_from_args(args)
    llm_enabled = bool(model_names) and not args.no_llm
    providers = (
        dict(zip(model_names, create_providers(model_names), strict=True))
        if llm_enabled
        else {}
    )
    if llm_enabled:
        print(f"  AI辅助语义核验模型:{'、'.join(model_names)}")
    else:
        print("  AI辅助语义核验:未启用，使用关键词+语义匹配结果")

    concurrency = max(1, args.concurrency)
    model_concurrency = (
        max(1, args.model_concurrency)
        if args.model_concurrency is not None
        else max(1, concurrency * max(1, len(model_names)))
    )
    print(f"  论文级并发:{concurrency}")
    print(f"  模型调用并发:{model_concurrency}")
    semaphore = asyncio.Semaphore(concurrency)
    model_semaphore = asyncio.Semaphore(model_concurrency)
    task_results = await asyncio.gather(
        *[
            process_paper(
                index,
                len(papers),
                paper,
                args,
                semaphore,
                providers,
                model_semaphore,
                keyword_index,
                semantic_items,
                semantic_embeddings,
                semantic_model,
            )
            for index, paper in enumerate(papers, start=1)
        ]
    )

    ordered_results = sorted(task_results, key=lambda item: item[0])
    rows = [row for _, row, _, _ in ordered_results]
    missing_pdfs = [pid for _, _, pid, _ in ordered_results if pid]
    audit_records = [
        audit_record
        for _, _, _, paper_audit_records in ordered_results
        for audit_record in paper_audit_records
    ]

    print("\n写入结果...")
    write_csv(rows, args.output_csv)
    if audit_records:
        args.output_audit.parent.mkdir(parents=True, exist_ok=True)
        with args.output_audit.open("w", encoding="utf-8") as file:
            for record in audit_records:
                file.write(json.dumps(record, ensure_ascii=False) + "\n")
    summary = build_summary(
        rows,
        args,
        knowledge_stats,
        missing_pdfs,
        llm_enabled,
        model_names,
        audit_records,
    )
    args.output_summary.parent.mkdir(parents=True, exist_ok=True)
    args.output_summary.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"  CSV:{args.output_csv}")
    print(f"  Summary:{args.output_summary}")
    if audit_records:
        print(f"  Audit:{args.output_audit}")
    print(
        "  完成:"
        f"{summary['total_papers']}篇，"
        f"总对应条目{summary['match_stats']['total_matches']}，"
        f"平均{summary['match_stats']['avg_matches_per_paper']}项/篇，"
        f"缺失PDF{len(missing_pdfs)}篇"
    )


def main() -> None:
    asyncio.run(run(parse_args()))


if __name__ == "__main__":
    main()
