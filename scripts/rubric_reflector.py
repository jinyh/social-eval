"""框架反思优化器 — 轻量级 GEPA reflection + mutate

读取收敛测试结果，诊断多模型分歧维度，调用反思 LLM 生成 rubric 改进建议，
输出 Markdown 反思报告供人工审核。

用法：
    uv run python scripts/rubric_reflector.py \
        --result results/convergence-test-full-v217.json \
        --framework configs/frameworks/law-v2.17-20260424.yaml

    # 对比前一版本
    uv run python scripts/rubric_reflector.py \
        --result results/convergence-test-full-v217.json \
        --previous results/convergence-test-full-v215-rerun2.json \
        --framework configs/frameworks/law-v2.17-20260424.yaml

    # 只诊断指定维度
    uv run python scripts/rubric_reflector.py \
        --result results/convergence-test-full-v217.json \
        --dimensions analytical_framework,literature_insight \
        --framework configs/frameworks/law-v2.17-20260424.yaml
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import yaml

from src.evaluation.providers.zenmux_provider import ZenmuxProvider
from src.knowledge.loader import _normalize_framework_data, DEFAULT_STD_THRESHOLD
from src.knowledge.schemas import Framework

DIMENSION_ORDER = [
    "problem_originality",
    "literature_insight",
    "analytical_framework",
    "logical_coherence",
    "conclusion_consensus",
    "forward_extension",
]

STD_THRESHOLD = 5.0


# ─── Step 1: 加载收敛测试结果 + 框架配置 ──────────────────────────


def load_test_result(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_framework_yaml(path: str) -> dict:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if "std_threshold" not in data:
        data["std_threshold"] = DEFAULT_STD_THRESHOLD
    return data


def extract_dimension_prompt(yaml_data: dict, dim_key: str) -> str | None:
    for dim in yaml_data.get("dimensions", []):
        if dim.get("key") == dim_key:
            return dim.get("prompt_template", "")
    return None


def extract_dimension_scoring(yaml_data: dict, dim_key: str) -> dict:
    for dim in yaml_data.get("dimensions", []):
        if dim.get("key") == dim_key:
            return {
                "scoring_criteria": dim.get("scoring_criteria", {}),
                "ceiling_rules": dim.get("ceiling_rules", []),
                "weight": dim.get("weight", 0),
                "ai_difficulty": dim.get("ai_difficulty", ""),
            }
    return {}


# ─── Step 2: 诊断分歧维度 ────────────────────────────────────────


def diagnose_divergent_dimensions(result: dict, dimension_keys: list[str] | None = None) -> list[dict]:
    divergent = []
    dims = result.get("dimensions", {})

    for dim_key in dimension_keys or DIMENSION_ORDER:
        if dim_key not in dims:
            continue
        dim_data = dims[dim_key]
        std = dim_data["std"]

        if std <= STD_THRESHOLD:
            continue

        raw_outputs = dim_data.get("raw_outputs", {})
        scores = dim_data.get("scores", {})

        # 收集各模型的核心输出
        model_details = {}
        for model_name, output in raw_outputs.items():
            alias = model_name.split("/")[-1]
            model_details[alias] = {
                "score": output.get("score"),
                "band": output.get("band"),
                "core_judgment": output.get("core_judgment", ""),
                "score_rationale": output.get("score_rationale", ""),
                "review_flags": output.get("review_flags", []),
                "strengths": output.get("strengths", []),
                "weaknesses": output.get("weaknesses", []),
            }

        divergent.append({
            "dimension": dim_key,
            "name_zh": dim_data["name_zh"],
            "std": std,
            "mean": dim_data["mean"],
            "confidence": dim_data["confidence"],
            "scores": {m.split("/")[-1]: s for m, s in scores.items()},
            "model_details": model_details,
        })

    return divergent


def format_divergence_summary(divergent: list[dict]) -> str:
    lines = []
    for dim in divergent:
        lines.append(f"### {dim['name_zh']} ({dim['dimension']}) — std={dim['std']}, confidence={dim['confidence']}")
        lines.append("")
        scores_str = ", ".join(f"{m}={s}" for m, s in dim["scores"].items())
        lines.append(f"分数：{scores_str} | mean={dim['mean']}")
        lines.append("")
        for model, detail in dim["model_details"].items():
            lines.append(f"**{model}** (score={detail['score']}, band={detail['band']}):")
            lines.append(f"- core_judgment: {detail['core_judgment']}")
            lines.append(f"- score_rationale: {detail['score_rationale']}")
            if detail["review_flags"] != ["none"]:
                lines.append(f"- review_flags: {detail['review_flags']}")
            lines.append("")
        lines.append("---")
        lines.append("")
    return "\n".join(lines)


# ─── Step 3: LLM 反思 ────────────────────────────────────────────


REFLECTION_PROMPT_PREFIX = """你是一位法学评价框架（rubric）优化专家。你的任务是分析多模型评审结果中的分歧，诊断根因，并提出改进建议。

## 背景

我们正在迭代法学论文六维度评价框架。当前版本存在部分维度多模型评分分歧较大的问题（std > 5），需要你帮助诊断原因并提出针对性的 rubric 改进方案。

## 分歧维度数据

"""

REFLECTION_PROMPT_SUFFIX = """

## 你的任务

请逐一分析每个分歧维度，输出以下内容：

### 1. 分歧根因诊断
- 各模型对锚定指标的理解差异是什么？（如"可操作性得分"的定义理解不一致）
- 是 prompt_template 中的概念界定模糊？还是评分锚定规则的边界不清？
- 还是 ceiling_rules 的触发条件描述不够精确？

### 2. 具体改进建议
- 只针对分歧维度提出改进，不要动已稳定的维度（std <= 5 的维度）
- 每个建议必须精确到需要修改的段落，给出修改前后的对比
- 如果建议修改 prompt_template，给出完整的新段落（不是模糊描述）
- 如果建议新增/修改 ceiling_rules 或 scoring_criteria，给出完整的规则定义

### 3. 风险评估
- 改动是否可能影响已稳定的维度？（如修改了通用措辞导致溢出）
- 改动是否可能改变评分分布的形状？（如收窄某个分档范围）
- 改动是否需要法学专业知识来最终判断？（标注"需法学专家确认"）

## 输出格式

请输出 JSON（注意：字段名用英文，内容用中文）：
{
  "dimensions": [
    {
      "dimension": "维度key",
      "name_zh": "维度中文名",
      "root_cause": "分歧根因诊断（2-3句话）",
      "suggestions": [
        {
          "target": "prompt_template|scoring_criteria|ceiling_rules",
          "section": "修改的具体段落标识",
          "old_text": "需要修改的原文本片段",
          "new_text": "建议的新文本片段",
          "rationale": "为什么这样改（1句话）",
          "risk_level": "low|medium|high",
          "needs_legal_review": true,
          "scope": "仅本维度|可能溢出到其他维度"
        }
      ],
      "risk_assessment": "整体风险评估（2-3句话）"
    }
  ]
}"""


async def run_reflection(
    divergent: list[dict],
    yaml_data: dict,
    reflection_model: str = "gpt-5.4",
) -> dict:
    provider = ZenmuxProvider(reflection_model)

    # 为每个分歧维度构建反思 prompt 并调用 LLM
    all_reflections = []

    for dim in divergent:
        dim_key = dim["dimension"]
        prompt_content = extract_dimension_prompt(yaml_data, dim_key) or "（未找到 prompt_template）"
        scoring_info = extract_dimension_scoring(yaml_data, dim_key)

        divergence_data = format_divergence_summary([dim])
        scoring_rules = json.dumps(scoring_info, ensure_ascii=False, indent=2)

        # 用字符串拼接代替 .format()，避免 prompt 内 JSON 的 { 被 Python 误解读
        reflection_prompt = (
            REFLECTION_PROMPT_PREFIX
            + divergence_data
            + "\n\n## 当前维度的评分 prompt（模型实际看到的完整指令）\n\n"
            + prompt_content
            + "\n\n## 当前维度的评分规则\n\n"
            + scoring_rules
            + REFLECTION_PROMPT_SUFFIX
        )

        print(f"反思维度：{dim['name_zh']} ({dim_key})...")
        raw = await provider.generate_json_response(reflection_prompt)

        # 确保输出包含 dimensions 数组
        if "dimensions" not in raw:
            raw = {"dimensions": [raw]}

        all_reflections.extend(raw.get("dimensions", []))

    return {"dimensions": all_reflections}


# ─── Step 4: Pareto 多目标追踪 ────────────────────────────────────


def compute_pareto_metrics(result: dict) -> dict:
    dims = result.get("dimensions", {})
    all_stds = [d["std"] for d in dims.values()]
    overall = result.get("overall", {})

    avg_std = overall.get("avg_std", 0)
    high_conf_pct = overall.get("high_confidence_pct", 0)
    weighted_total = overall.get("weighted_total", 0)

    # 区分度：如果有多篇论文的数据可以计算，否则标注为 "单篇测试，无法计算"
    discrimination = "单篇测试，无法计算"

    return {
        "avg_std": avg_std,
        "high_confidence_pct": high_conf_pct,
        "weighted_total": weighted_total,
        "discrimination": discrimination,
        "dimension_stds": {k: v["std"] for k, v in dims.items()},
    }


def format_pareto_comparison(current: dict, previous: dict | None) -> str:
    lines = ["## Pareto 多目标追踪", "", "| 指标 | 当前版本 | 前一版本 | 变化 |", "|------|---------|---------|------|"]

    c = current
    p = previous or {}

    def _arrow(cur, prev):
        if prev is None:
            return "—"
        if cur < prev:
            return "↓（改善）"
        if cur > prev:
            return "↑（恶化）"
        return "→（持平）"

    # avg_std: 越低越好
    lines.append(f"| 平均 std | {c['avg_std']} | {p.get('avg_std', '—')} | {_arrow(c['avg_std'], p.get('avg_std'))} |")
    # high_conf_pct: 越高越好（箭头反转）
    h_cur = c['high_confidence_pct']
    h_prev = p.get('high_confidence_pct')
    h_arrow = "—" if h_prev is None else ("↑（改善）" if h_cur > h_prev else "↓（恶化）" if h_cur < h_prev else "→（持平）")
    lines.append(f"| 高置信度比例 | {h_cur}% | {h_prev if h_prev is not None else '—'}% | {h_arrow} |")
    lines.append(f"| 加权总分 | {c['weighted_total']} | {p.get('weighted_total', '—')} | {_arrow_up_good(c['weighted_total'], p.get('weighted_total'))} |")
    lines.append(f"| 区分度 | {c['discrimination']} | {p.get('discrimination', '—')} | — |")
    lines.append("")
    lines.append("### 逐维度 std 对比")
    lines.append("")
    lines.append("| 维度 | 当前 std | 前一 std | 变化 |")
    lines.append("|------|---------|---------|------|")

    for dim_key in DIMENSION_ORDER:
        cur_std = c["dimension_stds"].get(dim_key, "—")
        prev_std = p.get("dimension_stds", {}).get(dim_key, "—")
        if isinstance(cur_std, (int, float)) and isinstance(prev_std, (int, float)):
            arrow = _arrow(cur_std, prev_std)
        else:
            arrow = "—"
        lines.append(f"| {dim_key} | {cur_std} | {prev_std} | {arrow} |")

    return "\n".join(lines)


def _arrow_up_good(cur, prev):
    if prev is None:
        return "—"
    if cur > prev:
        return "↑"
    if cur < prev:
        return "↓"
    return "→"


# ─── Step 5: 生成反思报告 ──────────────────────────────────────────


def generate_report(
    divergent: list[dict],
    reflections: dict,
    pareto_current: dict,
    pareto_previous: dict | None,
    result: dict,
    yaml_path: str,
) -> str:
    version = result.get("framework_version", "unknown")
    paper = result.get("paper", "")
    models = result.get("models", [])

    lines = [
        f"# 框架反思报告 — v{version}",
        "",
        f"**框架**: `{yaml_path}`",
        f"**论文**: `{paper}`",
        f"**模型**: {', '.join(models)}",
        f"**生成时间**: {time.strftime('%Y-%m-%d %H:%M')}",
        "",
    ]

    # 汇总
    overall = result.get("overall", {})
    lines.extend([
        "## 汇总",
        "",
        f"- 平均 std: **{overall.get('avg_std', 0)}**",
        f"- 高置信度比例: **{overall.get('high_confidence_pct', 0)}%**",
        f"- 加权总分: **{overall.get('weighted_total', 0)}**",
        f"- 分歧维度数: **{len(divergent)}**（共 {len(result.get('dimensions', {}))} 个维度）",
        "",
    ])

    # Pareto 对比
    lines.append(format_pareto_comparison(pareto_current, pareto_previous))
    lines.append("")

    # 逐维度诊断 + 反思
    lines.append("## 分歧维度诊断与改进建议")
    lines.append("")

    for dim in divergent:
        dim_key = dim["dimension"]
        lines.append(f"### {dim['name_zh']} ({dim_key})")
        lines.append("")
        lines.append(f"**std = {dim['std']}**, confidence = {dim['confidence']}")
        scores_str = ", ".join(f"{m}={s}" for m, s in dim["scores"].items())
        lines.append(f"模型分数：{scores_str}")
        lines.append("")

        # 找对应的反思结果
        reflection = None
        for r in reflections.get("dimensions", []):
            if r.get("dimension") == dim_key or r.get("name_zh") == dim["name_zh"]:
                reflection = r
                break

        if reflection:
            lines.append(f"**根因诊断**: {reflection.get('root_cause', '（无）')}")
            lines.append("")
            lines.append(f"**风险评估**: {reflection.get('risk_assessment', '（无）')}")
            lines.append("")
            suggestions = reflection.get("suggestions", [])
            if suggestions:
                lines.append("**改进建议**:")
                lines.append("")
                for i, s in enumerate(suggestions, 1):
                    risk_label = s.get("risk_level", "unknown")
                    legal_review = "需法学专家确认" if s.get("needs_legal_review") else "可直接采纳"
                    scope_label = s.get("scope", "未知")
                    lines.append(f"{i}. **[{s.get('target', '?')}] {s.get('section', '?')}** (风险={risk_label}, {legal_review}, 影响范围={scope_label})")
                    lines.append(f"   - 改动理由: {s.get('rationale', '（无）')}")
                    if s.get("old_text"):
                        lines.append(f"   - 原文本:")
                        lines.append(f"     ```")
                        for line in s["old_text"].split("\n"):
                            lines.append(f"     {line}")
                        lines.append(f"     ```")
                    if s.get("new_text"):
                        lines.append(f"   - 建议新文本:")
                        lines.append(f"     ```")
                        for line in s["new_text"].split("\n"):
                            lines.append(f"     {line}")
                        lines.append(f"     ```")
                    lines.append("")
        else:
            lines.append("（未获得反思 LLM 输出）")
            lines.append("")

        lines.append("---")
        lines.append("")

    # 稳定维度列表
    stable_dims = []
    for dim_key in DIMENSION_ORDER:
        dim_data = result.get("dimensions", {}).get(dim_key)
        if dim_data and dim_data["std"] <= STD_THRESHOLD:
            stable_dims.append(f"{dim_data['name_zh']} ({dim_key}): std={dim_data['std']}")

    if stable_dims:
        lines.append("## 已稳定维度（不建议修改）")
        lines.append("")
        for s in stable_dims:
            lines.append(f"- {s}")
        lines.append("")

    # 人工审核指引
    lines.append("## 人工审核指引")
    lines.append("")
    if reflections.get("dimensions"):
        auto_accept = []
        needs_review = []
        for r in reflections["dimensions"]:
            for s in r.get("suggestions", []):
                if s.get("needs_legal_review"):
                    needs_review.append(f"{r.get('name_zh', '?')} → {s.get('section', '?')}")
                else:
                    auto_accept.append(f"{r.get('name_zh', '?')} → {s.get('section', '?')}")

        if auto_accept:
            lines.append("**可直接采纳的建议**:")
            for item in auto_accept:
                lines.append(f"- {item}")
            lines.append("")

        if needs_review:
            lines.append("**需法学专家确认的建议**:")
            for item in needs_review:
                lines.append(f"- {item}")
            lines.append("")
    else:
        lines.append("（未获得反思 LLM 建议）")
        lines.append("")

    return "\n".join(lines)


# ─── 主流程 ────────────────────────────────────────────────────────


async def main_async(args: argparse.Namespace) -> None:
    # 加载当前收敛测试结果
    result = load_test_result(args.result)
    yaml_data = load_framework_yaml(args.framework)

    # 加载前一版本结果（可选）
    previous_result = None
    if args.previous:
        previous_result = load_test_result(args.previous)

    # 诊断分歧维度
    dimension_keys = args.dimensions.split(",") if args.dimensions else None
    divergent = diagnose_divergent_dimensions(result, dimension_keys)

    if not divergent:
        print("所有维度 std ≤ 5，无分歧需要反思。")
        pareto_current = compute_pareto_metrics(result)
        pareto_previous = compute_pareto_metrics(previous_result) if previous_result else None
        report = generate_report([], {"dimensions": []}, pareto_current, pareto_previous, result, args.framework)
    else:
        print(f"发现 {len(divergent)} 个分歧维度：")
        for dim in divergent:
            print(f"  - {dim['name_zh']} ({dim['dimension']}): std={dim['std']}")

        # LLM 反思
        reflections = await run_reflection(divergent, yaml_data, args.reflection_model)

        # Pareto 计算
        pareto_current = compute_pareto_metrics(result)
        pareto_previous = compute_pareto_metrics(previous_result) if previous_result else None

        # 生成报告
        report = generate_report(divergent, reflections, pareto_current, pareto_previous, result, args.framework)

    # 输出
    version = result.get("framework_version", "unknown")
    ts = time.strftime("%Y%m%d-%H%M%S")
    output_dir = PROJECT_ROOT / "results"
    output_dir.mkdir(exist_ok=True)

    if args.output:
        output_path = Path(args.output)
    else:
        output_path = output_dir / f"reflection-report-v{version}-{ts}.md"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report, encoding="utf-8")
    print(f"\n反思报告已保存到：{output_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="框架反思优化器 — 诊断分歧维度并生成 rubric 改进建议")
    parser.add_argument("--result", required=True, help="收敛测试结果 JSON 文件路径")
    parser.add_argument("--framework", required=True, help="评价框架 YAML 路径")
    parser.add_argument("--previous", default=None, help="前一版本收敛测试结果 JSON（可选，用于 Pareto 对比）")
    parser.add_argument("--dimensions", default=None, help="只诊断指定维度，逗号分隔；默认诊断所有 std > 5 的维度")
    parser.add_argument("--reflection-model", default="gpt-5.4", help="反思 LLM 模型名称（默认 gpt-5.4）")
    parser.add_argument("--output", default=None, help="输出 Markdown 文件路径；默认自动生成")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()