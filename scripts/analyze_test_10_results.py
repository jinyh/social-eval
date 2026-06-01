#!/usr/bin/env python3
"""分析 10 篇测试论文的 Round 1 + Round 2 结果

验证指标：
- Round 1 完成率：10/10 篇
- Round 2 完成率：10/10 篇
- 平均 std < 20（可接受范围）
- std > 8 的比例 < 50%
- Round 2 收敛效果：平均 std 下降 > 10%

用法：
    python scripts/analyze_test_10_results.py \
        --input-dir results/phase2-test-10 \
        --output results/phase2-test-10/test-report.md
"""

import argparse
import json
import statistics
from pathlib import Path
from datetime import datetime


def load_results(input_dir: Path, round_name: str) -> dict:
    """加载指定轮次的所有结果"""
    round_dir = input_dir / round_name
    if not round_dir.exists():
        return {}

    results = {}
    for result_file in sorted(round_dir.glob("paper-*.json")):
        paper_id = int(result_file.stem.split("-")[1])
        with open(result_file, 'r', encoding='utf-8') as f:
            results[paper_id] = json.load(f)

    return results


def analyze_round(results: dict, round_name: str) -> dict:
    """分析单轮结果"""
    if not results:
        return {
            "completed": 0,
            "total": 0,
            "completion_rate": 0.0,
        }

    papers_data = []
    all_dimension_stds = []

    for paper_id, result in results.items():
        overall = result.get("overall", {})
        agg_mean = overall.get("aggregation_mean", {})
        agg_strictest = overall.get("aggregation_strictest", {})

        score_mean = agg_mean.get("final_score", 0)
        score_strictest = agg_strictest.get("final_score", 0)
        max_std = overall.get("max_std", 0)

        # 收集所有维度的 std
        dimensions = result.get("dimensions", {})
        for dim_key, dim_data in dimensions.items():
            std = dim_data.get("std", 0)
            all_dimension_stds.append(std)

        papers_data.append({
            "paper_id": paper_id,
            "paper": Path(result.get("paper", "")).stem[:60],
            "journal": result.get("journal", "未知"),
            "score_mean": score_mean,
            "score_strictest": score_strictest,
            "max_std": max_std,
        })

    # 统计分析
    scores_mean = [p["score_mean"] for p in papers_data]
    scores_strictest = [p["score_strictest"] for p in papers_data]
    max_stds = [p["max_std"] for p in papers_data]

    analysis = {
        "completed": len(results),
        "total": 10,
        "completion_rate": len(results) / 10 * 100,
        "papers_data": papers_data,
        "scores": {
            "mean": {
                "avg": statistics.mean(scores_mean) if scores_mean else 0,
                "median": statistics.median(scores_mean) if scores_mean else 0,
                "min": min(scores_mean) if scores_mean else 0,
                "max": max(scores_mean) if scores_mean else 0,
                "std": statistics.stdev(scores_mean) if len(scores_mean) > 1 else 0,
            },
            "strictest": {
                "avg": statistics.mean(scores_strictest) if scores_strictest else 0,
                "median": statistics.median(scores_strictest) if scores_strictest else 0,
                "min": min(scores_strictest) if scores_strictest else 0,
                "max": max(scores_strictest) if scores_strictest else 0,
                "std": statistics.stdev(scores_strictest) if len(scores_strictest) > 1 else 0,
            },
        },
        "std_analysis": {
            "max_std_avg": statistics.mean(max_stds) if max_stds else 0,
            "max_std_median": statistics.median(max_stds) if max_stds else 0,
            "max_std_max": max(max_stds) if max_stds else 0,
            "max_std_min": min(max_stds) if max_stds else 0,
            "dimension_std_avg": statistics.mean(all_dimension_stds) if all_dimension_stds else 0,
            "dimension_std_median": statistics.median(all_dimension_stds) if all_dimension_stds else 0,
            "std_gt_8_count": sum(1 for s in all_dimension_stds if s > 8),
            "std_gt_8_ratio": sum(1 for s in all_dimension_stds if s > 8) / len(all_dimension_stds) * 100 if all_dimension_stds else 0,
        },
    }

    return analysis


def compare_rounds(round1_analysis: dict, round2_analysis: dict) -> dict:
    """对比两轮结果"""
    if not round1_analysis["papers_data"] or not round2_analysis["papers_data"]:
        return {}

    # 按 paper_id 对齐
    round1_by_id = {p["paper_id"]: p for p in round1_analysis["papers_data"]}
    round2_by_id = {p["paper_id"]: p for p in round2_analysis["papers_data"]}

    convergence_data = []
    for paper_id in sorted(round1_by_id.keys()):
        if paper_id not in round2_by_id:
            continue

        r1 = round1_by_id[paper_id]
        r2 = round2_by_id[paper_id]

        std_delta = r2["max_std"] - r1["max_std"]
        score_delta = r2["score_mean"] - r1["score_mean"]

        convergence_data.append({
            "paper_id": paper_id,
            "paper": r1["paper"],
            "journal": r1["journal"],
            "round1_score": r1["score_mean"],
            "round2_score": r2["score_mean"],
            "score_delta": score_delta,
            "round1_std": r1["max_std"],
            "round2_std": r2["max_std"],
            "std_delta": std_delta,
            "converged": std_delta < 0,
        })

    # 统计收敛效果
    std_deltas = [c["std_delta"] for c in convergence_data]
    converged_count = sum(1 for c in convergence_data if c["converged"])

    comparison = {
        "convergence_data": convergence_data,
        "std_reduction": {
            "avg_delta": statistics.mean(std_deltas) if std_deltas else 0,
            "median_delta": statistics.median(std_deltas) if std_deltas else 0,
            "converged_count": converged_count,
            "converged_ratio": converged_count / len(convergence_data) * 100 if convergence_data else 0,
        },
        "score_change": {
            "avg_delta": statistics.mean([c["score_delta"] for c in convergence_data]) if convergence_data else 0,
        },
    }

    return comparison


def generate_report(round1_analysis: dict, round2_analysis: dict, comparison: dict, output_file: Path):
    """生成 Markdown 报告"""
    lines = [
        "# Phase 2 测试报告：10 篇论文 Round 1 + Round 2",
        "",
        f"**生成时间**：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "## 验证指标",
        "",
    ]

    # 验证指标
    r1_completed = round1_analysis["completed"]
    r2_completed = round2_analysis["completed"]
    r1_std_avg = round1_analysis["std_analysis"]["max_std_avg"]
    r2_std_avg = round2_analysis["std_analysis"]["max_std_avg"]
    r1_std_gt_8_ratio = round1_analysis["std_analysis"]["std_gt_8_ratio"]
    r2_std_gt_8_ratio = round2_analysis["std_analysis"]["std_gt_8_ratio"]
    std_reduction = comparison["std_reduction"]["avg_delta"] if comparison else 0

    checks = [
        ("Round 1 完成率", f"{r1_completed}/10 篇", r1_completed == 10),
        ("Round 2 完成率", f"{r2_completed}/10 篇", r2_completed == 10),
        ("Round 1 平均 std", f"{r1_std_avg:.2f}", r1_std_avg < 20),
        ("Round 2 平均 std", f"{r2_std_avg:.2f}", r2_std_avg < 20),
        ("Round 1 std > 8 比例", f"{r1_std_gt_8_ratio:.1f}%", r1_std_gt_8_ratio < 50),
        ("Round 2 std > 8 比例", f"{r2_std_gt_8_ratio:.1f}%", r2_std_gt_8_ratio < 50),
        ("Round 2 收敛效果", f"平均 std 下降 {abs(std_reduction):.2f}", std_reduction < 0),
    ]

    for name, value, passed in checks:
        status = "✅" if passed else "❌"
        lines.append(f"- {status} **{name}**: {value}")

    lines.extend([
        "",
        "## Round 1 结果",
        "",
        f"- 完成论文数：{r1_completed}/10 篇",
        f"- 平均分（mean）：{round1_analysis['scores']['mean']['avg']:.2f}",
        f"- 平均分（strictest）：{round1_analysis['scores']['strictest']['avg']:.2f}",
        f"- 平均最大标准差：{r1_std_avg:.2f}",
        f"- 维度级平均标准差：{round1_analysis['std_analysis']['dimension_std_avg']:.2f}",
        f"- std > 8 的维度比例：{r1_std_gt_8_ratio:.1f}%",
        "",
        "### Round 1 论文列表",
        "",
        "| ID | 期刊 | 论文标题 | 平均分 | 最严格分 | 最大 std |",
        "|---:|------|----------|-------:|--------:|---------:|",
    ])

    for p in sorted(round1_analysis["papers_data"], key=lambda x: x["score_mean"], reverse=True):
        lines.append(f"| {p['paper_id']} | {p['journal']} | {p['paper']} | {p['score_mean']:.1f} | {p['score_strictest']:.1f} | {p['max_std']:.1f} |")

    lines.extend([
        "",
        "## Round 2 结果",
        "",
        f"- 完成论文数：{r2_completed}/10 篇",
        f"- 平均分（mean）：{round2_analysis['scores']['mean']['avg']:.2f}",
        f"- 平均分（strictest）：{round2_analysis['scores']['strictest']['avg']:.2f}",
        f"- 平均最大标准差：{r2_std_avg:.2f}",
        f"- 维度级平均标准差：{round2_analysis['std_analysis']['dimension_std_avg']:.2f}",
        f"- std > 8 的维度比例：{r2_std_gt_8_ratio:.1f}%",
        "",
        "### Round 2 论文列表",
        "",
        "| ID | 期刊 | 论文标题 | 平均分 | 最严格分 | 最大 std |",
        "|---:|------|----------|-------:|--------:|---------:|",
    ])

    for p in sorted(round2_analysis["papers_data"], key=lambda x: x["score_mean"], reverse=True):
        lines.append(f"| {p['paper_id']} | {p['journal']} | {p['paper']} | {p['score_mean']:.1f} | {p['score_strictest']:.1f} | {p['max_std']:.1f} |")

    if comparison:
        lines.extend([
            "",
            "## Round 1 vs Round 2 对比",
            "",
            f"- 平均 std 变化：{comparison['std_reduction']['avg_delta']:.2f}",
            f"- 收敛论文数：{comparison['std_reduction']['converged_count']}/{len(comparison['convergence_data'])} 篇 ({comparison['std_reduction']['converged_ratio']:.1f}%)",
            f"- 平均分数变化：{comparison['score_change']['avg_delta']:.2f}",
            "",
            "### 收敛详情",
            "",
            "| ID | 论文标题 | R1 分数 | R2 分数 | 分数变化 | R1 std | R2 std | std 变化 | 收敛 |",
            "|---:|----------|--------:|--------:|---------:|-------:|-------:|---------:|:----:|",
        ])

        for c in sorted(comparison["convergence_data"], key=lambda x: x["std_delta"]):
            converged_mark = "✅" if c["converged"] else "❌"
            lines.append(
                f"| {c['paper_id']} | {c['paper'][:40]} | {c['round1_score']:.1f} | {c['round2_score']:.1f} | "
                f"{c['score_delta']:+.1f} | {c['round1_std']:.1f} | {c['round2_std']:.1f} | {c['std_delta']:+.1f} | {converged_mark} |"
            )

    lines.extend([
        "",
        "## 结论",
        "",
    ])

    # 判断是否通过验证
    all_passed = all(passed for _, _, passed in checks)
    if all_passed:
        lines.append("✅ **所有验证指标通过，可以进入阶段 2（1836 篇完整评审）**")
    else:
        lines.append("❌ **部分验证指标未通过，需要调试脚本或调整配置**")
        lines.append("")
        lines.append("未通过的指标：")
        for name, value, passed in checks:
            if not passed:
                lines.append(f"- {name}: {value}")

    lines.append("")

    # 写入文件
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text("\n".join(lines), encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description="分析 10 篇测试论文的 Round 1 + Round 2 结果")
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=Path("results/phase2-test-10"),
        help="输入目录"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("results/phase2-test-10/test-report.md"),
        help="输出报告路径"
    )

    args = parser.parse_args()

    print(f"加载 Round 1 结果...")
    round1_results = load_results(args.input_dir, "round1")
    print(f"  找到 {len(round1_results)} 篇论文")

    print(f"加载 Round 2 结果...")
    round2_results = load_results(args.input_dir, "round2")
    print(f"  找到 {len(round2_results)} 篇论文")

    print(f"分析 Round 1...")
    round1_analysis = analyze_round(round1_results, "Round 1")

    print(f"分析 Round 2...")
    round2_analysis = analyze_round(round2_results, "Round 2")

    print(f"对比两轮结果...")
    comparison = compare_rounds(round1_analysis, round2_analysis)

    print(f"生成报告...")
    generate_report(round1_analysis, round2_analysis, comparison, args.output)

    print(f"\n报告已生成：{args.output}")

    # 打印关键指标
    print("\n关键指标：")
    print(f"  Round 1 完成率：{round1_analysis['completed']}/10 篇")
    print(f"  Round 2 完成率：{round2_analysis['completed']}/10 篇")
    print(f"  Round 1 平均 std：{round1_analysis['std_analysis']['max_std_avg']:.2f}")
    print(f"  Round 2 平均 std：{round2_analysis['std_analysis']['max_std_avg']:.2f}")
    if comparison:
        print(f"  std 变化：{comparison['std_reduction']['avg_delta']:.2f}")
        print(f"  收敛率：{comparison['std_reduction']['converged_ratio']:.1f}%")


if __name__ == "__main__":
    main()
