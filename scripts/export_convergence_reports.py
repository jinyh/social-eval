#!/usr/bin/env python3
"""将 convergence test 结果 JSON 导出为详细 PDF 报告。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from jinja2 import Template
from weasyprint import HTML

DIMENSION_ORDER = [
    "problem_originality",
    "literature_insight",
    "analytical_framework",
    "logical_coherence",
    "conclusion_consensus",
    "forward_extension",
]

FIELD_LABELS = [
    ("score", "分数"),
    ("summary", "小结"),
    ("core_judgment", "判断"),
    ("score_rationale", "根因"),
    ("evidence_quotes", "证据"),
    ("strengths", "优点"),
    ("weaknesses", "缺点"),
]

PRECHECK_FIELDS = [
    ("status", "结果(status)"),
    ("issues", "问题(issues)"),
    ("review_flags", "风险(review_flags)"),
    ("recommendation", "推荐(recommendation)"),
]

MODEL_DISPLAY_NAMES = {
    "gpt-5.4": "模型一",
    "qwen3.6-plus": "模型二",
    "glm-5.1": "模型三",
}

HTML_TEMPLATE = Template(
    """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <style>
    @page {
      size: A4 landscape;
      margin: 12mm 22mm 12mm 12mm;
      @bottom-center {
        content: "第 " counter(page) " 页";
        font-size: 10px;
        color: #666;
      }
    }
    body {
      font-family: "Songti SC", "STSong", "Hiragino Sans GB", "Arial Unicode MS", serif;
      color: #111;
      font-size: 11px;
      line-height: 1.5;
    }
    h1, h2, h3 {
      margin: 0;
    }
    .title-block {
      margin-bottom: 14px;
      padding-bottom: 10px;
      border-bottom: 2px solid #222;
    }
    .title {
      font-size: 18px;
      font-weight: 700;
      margin-bottom: 6px;
    }
    .meta {
      font-size: 11px;
      color: #444;
    }
    .summary-box {
      margin: 10px 0 18px;
      padding: 8px 12px;
      border: 1px solid #bbb;
      background: #f7f7f7;
    }
    .summary-line {
      margin: 0;
      font-size: 12px;
    }
    .section-title {
      font-size: 15px;
      font-weight: 700;
      margin: 20px 0 8px;
    }
    .dimension-meta {
      margin: 0 0 8px;
      font-size: 11px;
      color: #333;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      table-layout: fixed;
      margin-bottom: 14px;
    }
    th, td {
      border: 1px solid #555;
      padding: 6px 8px;
      vertical-align: top;
      word-break: break-word;
      overflow-wrap: anywhere;
    }
    thead {
      display: table-header-group;
    }
    th {
      background: #ececec;
      font-weight: 700;
      text-align: left;
    }
    .row-label {
      width: 13%;
      background: #f5f5f5;
      font-weight: 700;
    }
    .model-col {
      width: 29%;
    }
    ul {
      margin: 0;
      padding-left: 18px;
    }
    li {
      margin: 0 0 3px;
    }
    .value-list {
      margin: 0;
      padding-left: 18px;
    }
    .mono {
      font-family: "Menlo", "Consolas", monospace;
      font-size: 10px;
    }
    .page-break {
      page-break-before: always;
    }
  </style>
</head>
<body>
  <div class="title-block">
    <div class="title">论文评审结果汇总</div>
    <div><strong>论文题目：</strong>{{ report.paper_title }}</div>
  </div>

  <div class="summary-box">
    <p class="summary-line">
      <strong>版本：</strong>{{ report.framework_version }}　
      <strong>总分：</strong>{{ report.overall.weighted_total }}　
      <strong>平均标准差：</strong>{{ report.overall.avg_std }}
    </p>
  </div>

  <h2 class="section-title">预检</h2>
  <table>
    <thead>
      <tr>
        <th class="row-label"></th>
        {% for model in report.models %}
        <th class="model-col">{{ model.display_name }}</th>
        {% endfor %}
      </tr>
    </thead>
    <tbody>
      {% for row in report.precheck_rows %}
      <tr>
        <td class="row-label">{{ row.label }}</td>
        {% for cell in row.cells %}
        <td>{{ cell|safe }}</td>
        {% endfor %}
      </tr>
      {% endfor %}
    </tbody>
  </table>

  {% for dimension in report.dimensions %}
  <div class="{{ 'page-break' if loop.first else '' }}"></div>
  <h2 class="section-title">维度{{ loop.index }}：{{ dimension.name_zh }}</h2>
  <p class="dimension-meta">
    平均分数(mean): {{ dimension.mean }}　
    标准差(std): {{ dimension.std }}　
    置信度: {{ dimension.confidence }}
  </p>
  <table>
    <thead>
      <tr>
        <th class="row-label"></th>
        {% for model in report.models %}
        <th class="model-col">{{ model.display_name }}</th>
        {% endfor %}
      </tr>
    </thead>
    <tbody>
      {% for row in dimension.rows %}
      <tr>
        <td class="row-label">{{ row.label }}</td>
        {% for cell in row.cells %}
        <td>{{ cell|safe }}</td>
        {% endfor %}
      </tr>
      {% endfor %}
    </tbody>
  </table>
  {% endfor %}
</body>
</html>
"""
)


def _model_alias(model_name: str) -> str:
    return model_name.split("/")[-1]


def _find_model_key(keys: list[str], target: str) -> str:
    if target in keys:
        return target
    target_alias = _model_alias(target)
    for key in keys:
        if _model_alias(key) == target_alias:
            return key
    raise KeyError(f"找不到模型键: {target}")


def _display_model_name(model_name: str, index: int) -> str:
    alias = _model_alias(model_name)
    return MODEL_DISPLAY_NAMES.get(alias, f"模型{_index_to_cn(index + 1)}")


def _index_to_cn(index: int) -> str:
    numerals = {
        1: "一",
        2: "二",
        3: "三",
        4: "四",
        5: "五",
    }
    return numerals.get(index, str(index))


def _to_html(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        if not value:
            return ""
        items = "".join(f"<li>{_escape(str(item))}</li>" for item in value)
        return f"<ul class='value-list'>{items}</ul>"
    return _escape(str(value)).replace("\n", "<br>")


def _escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _build_report_data(source_path: Path) -> dict[str, Any]:
    data = json.loads(source_path.read_text(encoding="utf-8"))
    model_order = data["models"]
    precheck_keys = list(data["precheck"].keys())
    models = [
        {
            "key": _find_model_key(precheck_keys, model_name),
            "display_name": _display_model_name(model_name, index),
        }
        for index, model_name in enumerate(model_order)
    ]

    precheck_rows = []
    for field_key, label in PRECHECK_FIELDS:
        precheck_rows.append(
            {
                "label": label,
                "cells": [
                    _to_html(data["precheck"][model["key"]].get(field_key, "")) for model in models
                ],
            }
        )

    dimensions = []
    for dimension_key in DIMENSION_ORDER:
        dimension = data["dimensions"][dimension_key]
        raw_keys = list(dimension["raw_outputs"].keys())
        rows = []
        for field_key, label in FIELD_LABELS:
            cells = []
            for model in models:
                model_key = _find_model_key(raw_keys, model["key"])
                cell_value = dimension["raw_outputs"][model_key].get(field_key, "")
                if field_key == "score":
                    band = dimension["raw_outputs"][model_key].get("band")
                    if band:
                        cell_value = f"{cell_value} ({band})"
                cells.append(_to_html(cell_value))
            rows.append({"label": label, "cells": cells})
        dimensions.append(
            {
                "name_zh": dimension["name_zh"],
                "mean": dimension["mean"],
                "std": dimension["std"],
                "confidence": dimension["confidence"],
                "rows": rows,
            }
        )

    paper_path = data.get("paper", "")
    paper_title = Path(paper_path).stem if paper_path else source_path.stem
    return {
        "source_name": source_path.name,
        "paper_path": paper_path,
        "paper_title": paper_title,
        "framework": data.get("framework", ""),
        "framework_version": data.get("framework_version", ""),
        "overall": data.get("overall", {}),
        "models": models,
        "precheck_rows": precheck_rows,
        "dimensions": dimensions,
    }


def export_pdf(source_path: Path, output_path: Path) -> None:
    report = _build_report_data(source_path)
    html = HTML_TEMPLATE.render(report=report)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    HTML(string=html, base_url=str(source_path.parent)).write_pdf(output_path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="导出 convergence test PDF 报告")
    parser.add_argument("inputs", nargs="+", type=Path, help="输入 JSON 文件")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("results"),
        help="输出目录，默认 results/",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    for input_path in args.inputs:
        output_path = args.output_dir / f"{input_path.stem}.pdf"
        export_pdf(input_path, output_path)
        print(f"已生成: {output_path}")


if __name__ == "__main__":
    main()
