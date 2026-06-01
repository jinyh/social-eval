#!/usr/bin/env python3
"""生成 Phase 1 100 篇论文评测详细报告（Markdown 格式）"""

import json
import statistics
from pathlib import Path

RESULTS_DIR = Path("results/phase1-100-papers")
OUTPUT_PATH = RESULTS_DIR / "phase1-100-report.md"

DIM_KEYS = [
    "problem_originality",
    "literature_insight",
    "analytical_framework",
    "logical_coherence",
    "conclusion_consensus",
    "forward_extension",
]
DIM_NAMES = ["问题创新性", "文献洞察力", "分析框架", "逻辑连贯性", "结论可接受性", "前瞻延展性"]


def extract_source(paper_path: str) -> str:
    """从路径提取来源期刊"""
    parts = paper_path.split("/")
    if len(parts) >= 2:
        return parts[1]
    return "未知"


def extract_title(paper_path: str) -> str:
    """从路径提取论文标题"""
    return Path(paper_path).stem


def load_all_results():
    """加载所有结果文件"""
    results = []
    for i in range(1, 101):
        path = RESULTS_DIR / f"paper-{i:03d}.json"
        if path.exists():
            data = json.load(open(path, "r", encoding="utf-8"))
            data["_index"] = i
            results.append(data)
    return results


def format_dim_score(dim_data: dict) -> str:
    """格式化维度分数：mean(±std)"""
    mean = dim_data["mean"]
    std = dim_data["std"]
    if std == 0:
        return f"{mean:.0f}"
    return f"{mean:.0f}(±{std:.1f})"


def generate_report():
    results = load_all_results()
    if not results:
        print("没有找到结果文件")
        return

    # 按总分降序排列
    results.sort(key=lambda r: r.get("overall", {}).get("final_score", 0), reverse=True)

    lines = []
    lines.append("# Phase 1: 100 篇论文评测详细报告")
    lines.append("")
    lines.append(f"- 框架: `{results[0].get('framework', '?')}`")
    lines.append(f"- 模型: {', '.join(results[0].get('models', []))}")
    lines.append(f"- 论文数: {len(results)}")
    lines.append(f"- 排序: 总分降序")
    lines.append("")

    # === 汇总统计 ===
    all_scores = [r["overall"]["final_score"] for r in results if r.get("overall", {}).get("final_score") is not None]
    dim_means = {k: [] for k in DIM_KEYS}
    dim_stds = {k: [] for k in DIM_KEYS}

    for r in results:
        for k in DIM_KEYS:
            if k in r.get("dimensions", {}):
                dim_means[k].append(r["dimensions"][k]["mean"])
                dim_stds[k].append(r["dimensions"][k]["std"])

    lines.append("## 汇总统计")
    lines.append("")
    lines.append(f"| 指标 | 值 |")
    lines.append(f"|------|-----|")
    lines.append(f"| 论文总数 | {len(all_scores)} |")
    lines.append(f"| 整体均值 | {statistics.mean(all_scores):.1f} |")
    lines.append(f"| 中位数 | {statistics.median(all_scores):.1f} |")
    lines.append(f"| 标准差 | {statistics.stdev(all_scores):.1f} |")
    lines.append(f"| 最高分 | {max(all_scores):.1f} |")
    lines.append(f"| 最低分 | {min(all_scores):.1f} |")
    lines.append(f"| 90+ 分 | {sum(1 for s in all_scores if s >= 90)} 篇 ({sum(1 for s in all_scores if s >= 90)/len(all_scores)*100:.0f}%) |")
    lines.append(f"| 80-90 分 | {sum(1 for s in all_scores if 80 <= s < 90)} 篇 ({sum(1 for s in all_scores if 80 <= s < 90)/len(all_scores)*100:.0f}%) |")
    lines.append(f"| 70-80 分 | {sum(1 for s in all_scores if 70 <= s < 80)} 篇 ({sum(1 for s in all_scores if 70 <= s < 80)/len(all_scores)*100:.0f}%) |")
    lines.append(f"| < 70 分 | {sum(1 for s in all_scores if s < 70)} 篇 ({sum(1 for s in all_scores if s < 70)/len(all_scores)*100:.0f}%) |")
    lines.append("")

    # 各维度均值
    lines.append("### 各维度均值")
    lines.append("")
    lines.append("| 维度 | 均值 | 平均std | std>8 比例 |")
    lines.append("|------|------|---------|-----------|")
    for k, name in zip(DIM_KEYS, DIM_NAMES):
        avg = statistics.mean(dim_means[k]) if dim_means[k] else 0
        avg_std = statistics.mean(dim_stds[k]) if dim_stds[k] else 0
        std_over_8 = sum(1 for s in dim_stds[k] if s > 8)
        ratio = std_over_8 / len(dim_stds[k]) * 100 if dim_stds[k] else 0
        lines.append(f"| {name} | {avg:.1f} | {avg_std:.1f} | {ratio:.1f}% |")
    lines.append("")

    # 按来源分组
    source_scores = {}
    for r in results:
        source = extract_source(r.get("paper", ""))
        score = r.get("overall", {}).get("final_score")
        if score is not None:
            source_scores.setdefault(source, []).append(score)

    lines.append("### 按来源分组")
    lines.append("")
    lines.append("| 来源 | 篇数 | 均值 | 中位数 | 最低 | 最高 |")
    lines.append("|------|------|------|--------|------|------|")
    for source, scores in sorted(source_scores.items()):
        lines.append(f"| {source} | {len(scores)} | {statistics.mean(scores):.1f} | {statistics.median(scores):.1f} | {min(scores):.1f} | {max(scores):.1f} |")
    lines.append("")

    # === 主表 ===
    lines.append("## 详细评分表")
    lines.append("")
    lines.append("| # | 论文 | 来源 | 问题创新性 | 文献洞察力 | 分析框架 | 逻辑连贯性 | 结论可接受性 | 前瞻延展性 | 总分 | 平均std | 最大std | 置信度 | 预检 |")
    lines.append("|---|------|------|-----------|-----------|---------|-----------|------------|-----------|------|---------|---------|--------|------|")

    for rank, r in enumerate(results, 1):
        idx = r["_index"]
        title = extract_title(r.get("paper", ""))
        source = extract_source(r.get("paper", ""))
        overall = r.get("overall", {})
        dims = r.get("dimensions", {})

        dim_cols = []
        for k in DIM_KEYS:
            if k in dims:
                dim_cols.append(format_dim_score(dims[k]))
            else:
                dim_cols.append("-")

        final_score = overall.get("final_score", "-")
        avg_std = overall.get("avg_std", "-")
        max_std = overall.get("max_std", "-")
        high_conf = overall.get("high_confidence_pct", "-")
        if isinstance(high_conf, (int, float)):
            high_conf = f"{high_conf:.0f}%"

        # 预检状态
        precheck = r.get("precheck", {})
        precheck_statuses = set()
        if precheck:
            for model_result in precheck.values():
                if isinstance(model_result, dict):
                    precheck_statuses.add(model_result.get("status", "?"))
        precheck_str = "/".join(sorted(precheck_statuses)) if precheck_statuses else "-"

        lines.append(f"| {rank} | {title} | {source} | {' | '.join(dim_cols)} | {final_score} | {avg_std} | {max_std} | {high_conf} | {precheck_str} |")

    lines.append("")
    lines.append("---")
    lines.append(f"*生成时间: 基于 results/phase1-100-papers/ 数据*")

    # 写入文件
    OUTPUT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"报告已生成: {OUTPUT_PATH}")
    print(f"共 {len(results)} 篇论文")


if __name__ == "__main__":
    generate_report()
