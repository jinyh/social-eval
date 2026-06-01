#!/usr/bin/env python3
"""Generate CSV and Markdown reports for Phase 2 Round 1 error categories 2-5."""

from __future__ import annotations

import argparse
import csv
import json
import re
import statistics
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET
from zipfile import BadZipFile, ZipFile


XML_NS = {
    "main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "rel": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "pkgrel": "http://schemas.openxmlformats.org/package/2006/relationships",
}

CATEGORY_ORDER = [
    "2-all-reject",
    "3-majority-reject",
    "4-single-reject",
    "5-boundary-only",
]

CATEGORY_NAMES = {
    "2-all-reject": "4 个模型全部拒绝",
    "3-majority-reject": "2-3 个模型拒绝",
    "4-single-reject": "1 个模型拒绝",
    "5-boundary-only": "仅边界判断",
}

CATEGORY_ACTIONS = {
    "2-all-reject": "建议直接排除，不进入后续六维评审。",
    "3-majority-reject": "建议人工复核，重点判断是否仍需进入六维评审。",
    "4-single-reject": "建议人工复核拒绝模型意见，必要时保留进入六维评审。",
    "5-boundary-only": "建议专家确认项目口径边界后决定是否进入六维评审。",
}

MODEL_ORDER = [
    "deepseek-v4-pro",
    "glm-5.1",
    "kimi-k2.6",
    "qwen3.6-plus",
]

CSV_FIELDS = [
    "category",
    "category_name",
    "paper_id",
    "title",
    "journal",
    "publication_time",
    "year",
    "issue",
    "paper_path",
    "reject_models",
    "boundary_models",
    "pass_models",
    "reject_count",
    "boundary_count",
    "pass_count",
    "failure_summary",
    "recommended_action",
    "text_quality_issues",
    "missing_dimension_models",
]

for model_name in MODEL_ORDER:
    model_prefix = model_name.replace("-", "_").replace(".", "_")
    CSV_FIELDS.extend(
        [
            f"{model_prefix}_status",
            f"{model_prefix}_conclusion",
            f"{model_prefix}_reasons",
            f"{model_prefix}_recommendation",
        ]
    )


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def column_index(cell_ref: str | None) -> int | None:
    if not cell_ref:
        return None
    match = re.match(r"([A-Z]+)", cell_ref)
    if not match:
        return None
    value = 0
    for char in match.group(1):
        value = value * 26 + ord(char) - ord("A") + 1
    return value - 1


def load_shared_strings(workbook: ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in workbook.namelist():
        return []

    root = ET.fromstring(workbook.read("xl/sharedStrings.xml"))
    strings = []
    for item in root.findall("main:si", XML_NS):
        text_parts = [node.text or "" for node in item.findall(".//main:t", XML_NS)]
        strings.append("".join(text_parts))
    return strings


def cell_value(cell: ET.Element, shared_strings: list[str]) -> str | None:
    cell_type = cell.get("t")

    if cell_type == "inlineStr":
        text_parts = [node.text or "" for node in cell.findall(".//main:t", XML_NS)]
        return "".join(text_parts)

    value_node = cell.find("main:v", XML_NS)
    if value_node is None:
        return None

    raw_value = value_node.text or ""
    if cell_type == "s":
        try:
            return shared_strings[int(raw_value)]
        except (IndexError, ValueError):
            return raw_value

    return raw_value


def worksheet_paths(workbook: ZipFile) -> list[tuple[str, str]]:
    workbook_root = ET.fromstring(workbook.read("xl/workbook.xml"))
    rel_root = ET.fromstring(workbook.read("xl/_rels/workbook.xml.rels"))
    rel_map = {
        rel.get("Id"): rel.get("Target")
        for rel in rel_root.findall("pkgrel:Relationship", XML_NS)
    }

    paths = []
    for sheet in workbook_root.findall("main:sheets/main:sheet", XML_NS):
        rel_id = sheet.get(f"{{{XML_NS['rel']}}}id")
        target = rel_map.get(rel_id)
        if not target:
            continue
        if not target.startswith("xl/"):
            target = f"xl/{target}"
        paths.append((sheet.get("name") or "", target))
    return paths


def read_xlsx_first_sheet(path: Path) -> list[dict[str, str | None]]:
    """Read the first worksheet from a simple .xlsx file using only stdlib."""
    try:
        with ZipFile(path) as workbook:
            shared_strings = load_shared_strings(workbook)
            sheets = worksheet_paths(workbook)
            if not sheets:
                return []

            _, first_sheet_path = sheets[0]
            root = ET.fromstring(workbook.read(first_sheet_path))
            raw_rows = []
            for row in root.findall("main:sheetData/main:row", XML_NS):
                values: list[str | None] = []
                for cell in row.findall("main:c", XML_NS):
                    idx = column_index(cell.get("r"))
                    if idx is not None:
                        while len(values) < idx:
                            values.append(None)
                    values.append(cell_value(cell, shared_strings))
                raw_rows.append(values)
    except BadZipFile as exc:
        raise ValueError(f"Cannot read xlsx file {path}: {exc}") from exc

    if not raw_rows:
        return []

    headers = [str(value) if value is not None else "" for value in raw_rows[0]]
    rows: list[dict[str, str | None]] = []
    for raw_row in raw_rows[1:]:
        row = {
            header: raw_row[idx] if idx < len(raw_row) else None
            for idx, header in enumerate(headers)
        }
        if any(value is not None for value in row.values()):
            rows.append(row)

    return rows


def normalize_title(value: str | None) -> str:
    if not value:
        return ""
    normalized = unicodedata.normalize("NFKC", str(value))
    normalized = normalized.replace("_", "")
    return "".join(char for char in normalized if char.isalnum())


def clean_excel_list_value(value: str | None) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    match = re.fullmatch(r"\['(.+)'\]", text)
    if match:
        return match.group(1).strip()
    return text


def normalize_year_issue(value: str | None, year: str | None, issue: str | None) -> str:
    cleaned = clean_excel_list_value(value)
    if cleaned:
        return cleaned

    year_text = clean_excel_list_value(year)
    issue_text = clean_excel_list_value(issue)
    if year_text and issue_text:
        return f"{year_text}年 第{issue_text}期"
    return ""


def extract_year_issue(
    publication_time: str, year: str | None, issue: str | None
) -> tuple[str, str]:
    year_text = clean_excel_list_value(year)
    issue_text = clean_excel_list_value(issue)

    year_match = re.search(r"(\d{4})年", publication_time)
    if year_match:
        year_text = year_match.group(1)

    issue_match = re.search(r"第\s*([0-9]+)\s*期", publication_time)
    if issue_match:
        issue_text = issue_match.group(1)

    return year_text, issue_text


def load_metadata(metadata_dir: Path) -> dict[str, dict[str, str]]:
    metadata_files = [
        metadata_dir / "4_中国法学_论文信息.xlsx",
        metadata_dir / "8_中国社会科学_论文信息.xlsx",
        metadata_dir / "11_法学研究_论文信息.xlsx",
        metadata_dir / "三大刊合并_原文.xlsx",
    ]

    index: dict[str, dict[str, str]] = {}
    for metadata_file in metadata_files:
        if not metadata_file.exists():
            continue

        for row in read_xlsx_first_sheet(metadata_file):
            if "论文名" in row:
                title_original = row.get("论文名") or ""
                title_clean = title_original
                journal = row.get("杂志") or ""
                raw_year_issue = None
                raw_year = row.get("年份")
                raw_issue = row.get("期数")
                lngid = row.get("原文维普ID号") or ""
            else:
                title_original = row.get("原始篇名") or row.get("titlec") or ""
                title_clean = row.get("篇名") or title_original
                journal = row.get("mediac") or ""
                raw_year_issue = row.get("年期")
                raw_year = row.get("years")
                raw_issue = row.get("num")
                lngid = row.get("lngid") or ""

            publication_time = normalize_year_issue(raw_year_issue, raw_year, raw_issue)
            year, issue = extract_year_issue(publication_time, raw_year, raw_issue)
            metadata = {
                "title_original": str(title_original),
                "title_clean": str(title_clean),
                "journal": str(journal),
                "publication_time": publication_time,
                "year": year,
                "issue": issue,
                "lngid": str(lngid),
                "metadata_source": str(metadata_file),
            }

            for key in (title_original, title_clean):
                normalized_key = normalize_title(str(key))
                if normalized_key and normalized_key not in index:
                    index[normalized_key] = metadata

    return index


def unique_join(values: list[str]) -> str:
    seen = set()
    result = []
    for value in values:
        text = str(value).strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return "；".join(result)


def value_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    return [str(value).strip()]


def model_reason_parts(precheck: dict[str, Any]) -> list[str]:
    parts: list[str] = []
    parts.extend(value_list(precheck.get("issues")))
    parts.extend(value_list(precheck.get("obviously_ineligible_reasons")))
    parts.extend(value_list(precheck.get("boundary_reasons")))

    text_quality = precheck.get("text_quality_gate")
    if isinstance(text_quality, dict):
        parts.extend(value_list(text_quality.get("issues")))

    return parts


def text_quality_issues(precheck_by_model: dict[str, Any]) -> str:
    issues = []
    for model in MODEL_ORDER:
        data = precheck_by_model.get(model)
        if not isinstance(data, dict):
            continue
        text_quality = data.get("text_quality_gate")
        if not isinstance(text_quality, dict):
            continue
        for issue in value_list(text_quality.get("issues")):
            issues.append(f"{model}: {issue}")
    return unique_join(issues)


def load_missing_dimension_index(dimension_report_path: Path) -> dict[str, str]:
    if not dimension_report_path.exists():
        return {}

    report = load_json(dimension_report_path)
    missing_by_paper: dict[str, list[str]] = defaultdict(list)
    for category in CATEGORY_ORDER:
        for paper in report.get(category, {}).get("papers", []):
            paper_id = paper.get("paper_id")
            if not paper_id:
                continue
            for model, model_data in paper.get("models", {}).items():
                if isinstance(model_data, dict) and not model_data.get(
                    "has_dimensions", True
                ):
                    missing_by_paper[paper_id].append(model)

    return {
        paper_id: "；".join(sorted(set(models)))
        for paper_id, models in missing_by_paper.items()
    }


def summarize_failure(
    category: str, paper_summary: dict[str, Any], precheck_by_model: dict[str, Any]
) -> str:
    reject_models = paper_summary.get("reject_models", [])
    boundary_models = paper_summary.get("boundary_models", [])
    pass_models = paper_summary.get("pass_models", [])

    reason_texts = []
    for model in MODEL_ORDER:
        data = precheck_by_model.get(model)
        if not isinstance(data, dict):
            continue
        conclusion = data.get("conclusion")
        if conclusion in {"obviously_ineligible", "boundary_review"}:
            reason_texts.extend(model_reason_parts(data)[:2])

    reason_summary = unique_join(reason_texts[:6])

    if category == "2-all-reject":
        prefix = "四个模型均判定为明显不适格"
    elif category == "3-majority-reject":
        prefix = (
            f"多数模型拒绝（拒绝：{', '.join(reject_models)}；"
            f"边界：{', '.join(boundary_models) or '无'}；"
            f"通过：{', '.join(pass_models) or '无'}）"
        )
    elif category == "4-single-reject":
        prefix = (
            f"单模型拒绝（拒绝：{', '.join(reject_models)}；"
            f"边界：{', '.join(boundary_models) or '无'}；"
            f"通过：{', '.join(pass_models) or '无'}）"
        )
    else:
        prefix = f"无模型拒绝，但存在边界判断（边界：{', '.join(boundary_models)}）"

    if reason_summary:
        return f"{prefix}。主要原因：{reason_summary}"
    return prefix


def recommended_action(category: str, precheck_by_model: dict[str, Any]) -> str:
    recommendations = []
    for model in MODEL_ORDER:
        data = precheck_by_model.get(model)
        if isinstance(data, dict) and data.get("recommendation"):
            recommendations.append(f"{model}: {data['recommendation']}")

    if recommendations:
        return f"{CATEGORY_ACTIONS[category]} 模型建议：{unique_join(recommendations)}"
    return CATEGORY_ACTIONS[category]


def build_records(
    round1_err_dir: Path,
    metadata_index: dict[str, dict[str, str]],
    missing_dimension_index: dict[str, str],
) -> list[dict[str, str]]:
    summary_path = round1_err_dir / "error-summary.json"
    summary = load_json(summary_path)
    records: list[dict[str, str]] = []
    missing_metadata = []

    for category in CATEGORY_ORDER:
        papers = sorted(
            summary.get("papers", {}).get(category, []),
            key=lambda item: int(str(item["paper_id"]).split("-")[-1]),
        )
        for paper_summary in papers:
            paper_id = str(paper_summary["paper_id"])
            detail_path = round1_err_dir / category / f"{paper_id}.json"
            detail = load_json(detail_path)

            paper_path = paper_summary.get("paper_name") or detail.get("paper") or ""
            title = Path(paper_path).stem
            metadata = metadata_index.get(normalize_title(title))
            if metadata is None:
                missing_metadata.append((paper_id, title))
                metadata = {
                    "journal": "",
                    "publication_time": "",
                    "year": "",
                    "issue": "",
                }

            precheck_by_model = detail.get("precheck", {})
            if not isinstance(precheck_by_model, dict):
                precheck_by_model = {}

            record: dict[str, str] = {
                "category": category,
                "category_name": CATEGORY_NAMES[category],
                "paper_id": paper_id,
                "title": title,
                "journal": metadata.get("journal", ""),
                "publication_time": metadata.get("publication_time", ""),
                "year": metadata.get("year", ""),
                "issue": metadata.get("issue", ""),
                "paper_path": str(paper_path),
                "reject_models": "；".join(paper_summary.get("reject_models", [])),
                "boundary_models": "；".join(paper_summary.get("boundary_models", [])),
                "pass_models": "；".join(paper_summary.get("pass_models", [])),
                "reject_count": str(paper_summary.get("reject_count", 0)),
                "boundary_count": str(paper_summary.get("boundary_count", 0)),
                "pass_count": str(paper_summary.get("pass_count", 0)),
                "failure_summary": summarize_failure(
                    category, paper_summary, precheck_by_model
                ),
                "recommended_action": recommended_action(category, precheck_by_model),
                "text_quality_issues": text_quality_issues(precheck_by_model),
                "missing_dimension_models": missing_dimension_index.get(paper_id, ""),
            }

            for model_name in MODEL_ORDER:
                model_prefix = model_name.replace("-", "_").replace(".", "_")
                model_data = precheck_by_model.get(model_name)
                if not isinstance(model_data, dict):
                    model_data = {}

                record[f"{model_prefix}_status"] = str(model_data.get("status", ""))
                record[f"{model_prefix}_conclusion"] = str(
                    model_data.get("conclusion", "")
                )
                record[f"{model_prefix}_reasons"] = unique_join(
                    model_reason_parts(model_data)
                )
                record[f"{model_prefix}_recommendation"] = str(
                    model_data.get("recommendation", "")
                )

            records.append(record)

    if missing_metadata:
        formatted = ", ".join(
            f"{paper_id}:{title}" for paper_id, title in missing_metadata
        )
        raise ValueError(
            f"Missing metadata for {len(missing_metadata)} papers: {formatted}"
        )

    return records


def write_csv(records: list[dict[str, str]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(records)


def md_cell(value: Any) -> str:
    text = str(value or "").replace("\n", " ").replace("\r", " ")
    return text.replace("|", "\\|")


def model_stats(records: list[dict[str, str]], conclusion: str) -> Counter[str]:
    stats: Counter[str] = Counter()
    for record in records:
        for model_name in MODEL_ORDER:
            model_prefix = model_name.replace("-", "_").replace(".", "_")
            if record.get(f"{model_prefix}_conclusion") == conclusion:
                stats[model_name] += 1
    return stats


def category_summary(records: list[dict[str, str]]) -> str:
    lines = ["| 类别 | 数量 | 占比 | 建议 |", "|---|---:|---:|---|"]
    total = len(records)
    counts = Counter(record["category"] for record in records)
    for category in CATEGORY_ORDER:
        count = counts[category]
        percentage = count / total * 100 if total else 0
        lines.append(
            f"| {category} {CATEGORY_NAMES[category]} | {count} | {percentage:.1f}% | "
            f"{CATEGORY_ACTIONS[category]} |"
        )
    return "\n".join(lines)


def counter_table(title: str, counter: Counter[str]) -> str:
    lines = [f"### {title}", "", "| 项目 | 数量 |", "|---|---:|"]
    for key, count in counter.most_common():
        lines.append(f"| {md_cell(key)} | {count} |")
    return "\n".join(lines)


def write_markdown(records: list[dict[str, str]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    category_counts = Counter(record["category"] for record in records)
    journal_counts = Counter(record["journal"] for record in records)
    year_counts = Counter(record["year"] for record in records)
    reject_stats = model_stats(records, "obviously_ineligible")
    boundary_stats = model_stats(records, "boundary_review")
    missing_dimension_records = [
        record for record in records if record.get("missing_dimension_models")
    ]
    text_quality_records = [
        record for record in records if record.get("text_quality_issues")
    ]

    lines = [
        "# Phase 2 Round 1 失败文献 2-5 类清单与分析",
        "",
        f"**生成时间**：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "## 执行摘要",
        "",
        (
            f"本报告覆盖 `results/phase2-evaluation/round1-err` 中 2-5 类失败文献，"
            f"共 **{len(records)}** 篇。"
        ),
        "",
        category_summary(records),
        "",
        "## 完整列表",
        "",
    ]

    for category in CATEGORY_ORDER:
        category_records = [
            record for record in records if record["category"] == category
        ]
        lines.extend(
            [
                f"### {category} {CATEGORY_NAMES[category]}（{len(category_records)} 篇）",
                "",
                "| paper_id | 文章 | 期刊 | 发表时间 | 拒绝模型 | 边界模型 | 失败原因 |",
                "|---|---|---|---|---|---|---|",
            ]
        )
        for record in category_records:
            lines.append(
                "| "
                f"{md_cell(record['paper_id'])} | "
                f"{md_cell(record['title'])} | "
                f"{md_cell(record['journal'])} | "
                f"{md_cell(record['publication_time'])} | "
                f"{md_cell(record['reject_models'] or '无')} | "
                f"{md_cell(record['boundary_models'] or '无')} | "
                f"{md_cell(record['failure_summary'])} |"
            )
        lines.append("")

    lines.extend(
        [
            "## 统计分析",
            "",
            counter_table("期刊分布", journal_counts),
            "",
            counter_table("年份分布", year_counts),
            "",
            counter_table("拒绝模型分布", reject_stats),
            "",
            counter_table("边界模型分布", boundary_stats),
            "",
            "## 总结分析",
            "",
            (
                f"- 2-5 类失败文献以《中国法学》为主："
                f"{journal_counts.get('中国法学', 0)}/{len(records)} 篇；"
                f"另有《中国社会科学》{journal_counts.get('中国社会科学', 0)} 篇。"
            ),
            (
                f"- 类别结构显示，`5-boundary-only` 最多（{category_counts['5-boundary-only']} 篇），"
                "说明较多论文不是技术失败，而是项目口径边界需要人工确认。"
            ),
            (
                f"- 拒绝判断主要集中在 `3-majority-reject` 与 `4-single-reject`，"
                f"拒绝模型分布为：{unique_join([f'{k} {v} 篇' for k, v in reject_stats.most_common()])}。"
            ),
            (
                f"- 有 {len(text_quality_records)} 篇至少一个模型报告 OCR、页码、脚注或参考文献抽取等文本工程风险；"
                "这些风险通常与项目口径判断并存，人工复核时应区分文本质量问题与学术口径问题。"
            ),
            (
                f"- 有 {len(missing_dimension_records)} 篇存在部分模型六维结果缺失记录，"
                "主要出现在被拒绝或边界判断的模型上；这类缺失与预检未进入六维评审有关，"
                "不应直接视为评分数据丢失。"
            ),
            "",
            "## 处理建议",
            "",
            "- `2-all-reject`：四个模型均拒绝，建议直接排除并保留拒绝理由备查。",
            "- `3-majority-reject`：多数模型拒绝但存在分歧，建议由专家判定是否属于政策阐释、宣传性文本或仍有可争辩法学命题。",
            "- `4-single-reject`：单个模型拒绝，建议优先检查该模型理由是否过度严格；若其他模型均能定位法学问题，可保留进入后续评审。",
            "- `5-boundary-only`：无拒绝但有边界判断，建议重点确认“中国问题中心性”和“理论转化/可复核命题”是否足够。",
            "",
            "## 机器可读文件",
            "",
            f"- CSV：`{output_path.with_suffix('.csv')}`",
            "",
            "---",
            "",
            "*本报告由 `scripts/generate_round1_err_2_5_report.py` 自动生成。*",
        ]
    )

    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def validate(records: list[dict[str, str]], expected_counts: dict[str, int]) -> None:
    actual_counts = Counter(record["category"] for record in records)
    errors = []

    for category, expected_count in expected_counts.items():
        actual_count = actual_counts.get(category, 0)
        if actual_count != expected_count:
            errors.append(
                f"{category} expected {expected_count} records, got {actual_count}"
            )

    if len(records) != sum(expected_counts.values()):
        errors.append(
            f"total expected {sum(expected_counts.values())} records, got {len(records)}"
        )

    for record in records:
        for field in ("title", "journal", "publication_time"):
            if not record.get(field):
                errors.append(f"{record['paper_id']} missing {field}")

    if errors:
        raise ValueError("Validation failed:\n" + "\n".join(errors))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate Round 1 error category 2-5 CSV and Markdown reports."
    )
    parser.add_argument(
        "--round1-err-dir",
        type=Path,
        default=Path("results/phase2-evaluation/round1-err"),
        help="Round 1 error directory.",
    )
    parser.add_argument(
        "--metadata-dir",
        type=Path,
        default=Path("法学三大刊论文"),
        help="Directory containing journal metadata xlsx files.",
    )
    parser.add_argument(
        "--csv-output",
        type=Path,
        default=Path("results/phase2-evaluation/round1-err/round1-failures-2-5.csv"),
        help="CSV output path.",
    )
    parser.add_argument(
        "--markdown-output",
        type=Path,
        default=Path("results/phase2-evaluation/round1-err/round1-failures-2-5.md"),
        help="Markdown output path.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    metadata_index = load_metadata(args.metadata_dir)
    missing_dimension_index = load_missing_dimension_index(
        args.round1_err_dir / "dimension-check-report.json"
    )
    records = build_records(
        args.round1_err_dir, metadata_index, missing_dimension_index
    )

    expected_counts = {
        "2-all-reject": 5,
        "3-majority-reject": 19,
        "4-single-reject": 15,
        "5-boundary-only": 25,
    }
    validate(records, expected_counts)

    write_csv(records, args.csv_output)
    write_markdown(records, args.markdown_output)

    avg_rejects = statistics.mean(int(record["reject_count"]) for record in records)
    print(f"Generated {args.csv_output}")
    print(f"Generated {args.markdown_output}")
    print(f"Records: {len(records)}; average reject count: {avg_rejects:.2f}")


if __name__ == "__main__":
    main()
