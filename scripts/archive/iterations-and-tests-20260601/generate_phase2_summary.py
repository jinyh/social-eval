#!/usr/bin/env python3
"""Phase 2 总报告生成器

汇总所有批次的 Round 2 结果，生成完整的 Markdown 报告。

用法：
    python scripts/generate_phase2_summary.py \\
        --input-dir results/phase2-1849-papers \\
        --output results/phase2-1849-papers-summary.md
"""

import argparse
import json
import statistics
from datetime import datetime
from pathlib import Path


def load_journal_mapping():
    """从论文列表加载期刊映射"""
    journal_mapping = {}

    paper_list_file = Path("results/phase2-paper-list.json")
    if paper_list_file.exists():
        with open(paper_list_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            for paper in data["papers"]:
                # 从路径提取文件名
                filename = Path(paper["path"]).name
                journal_mapping[filename] = paper["journal"]

    return journal_mapping


def collect_all_papers(input_dir: Path, journal_mapping: dict):
    """收集所有批次的 Round 2 结果"""
    papers = []

    # 遍历所有批次目录
    for batch_dir in sorted(input_dir.glob("batch-*")):
        round2_dir = batch_dir / "round2"
        if not round2_dir.exists():
            continue

        # 读取该批次的所有 Round 2 结果
        for result_file in sorted(round2_dir.glob("paper-*.json")):
            try:
                with open(result_file, 'r', encoding='utf-8') as f:
                    result = json.load(f)

                paper_path = result.get("paper", "")
                filename = Path(paper_path).name

                # 计算 Round 2 六维平均分
                dimensions = result.get("dimensions", {})
                round2_scores = []
                round2_stds = []

                for dim_key, dim_data in dimensions.items():
                    if "round2_mean" in dim_data:
                        round2_scores.append(dim_data["round2_mean"])
                        round2_stds.append(dim_data["round2_std"])

                if round2_scores:
                    # 匹配期刊
                    journal = journal_mapping.get(filename, "未知期刊")

                    # 提取论文标题（去除 .pdf 后缀）
                    title = filename.replace('.pdf', '')

                    papers.append({
                        "title": title,
                        "journal": journal,
                        "round2_mean": statistics.mean(round2_scores),
                        "round2_avg_std": statistics.mean(round2_stds),
                        "filename": filename
                    })

            except Exception as e:
                print(f"警告: 读取 {result_file} 失败: {e}")

    return papers


def generate_markdown_report(papers: list, output_file: Path):
    """生成 Markdown 报告"""
    # 按平均分降序排序
    papers.sort(key=lambda x: x["round2_mean"], reverse=True)

    with open(output_file, "w", encoding="utf-8") as f:
        f.write("# Phase 2: 1849 篇法学三大刊论文评审总报告\n\n")
        f.write(f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write(f"**总论文数**: {len(papers)} 篇\n\n")

        # 整体统计
        scores = [p["round2_mean"] for p in papers]
        stds = [p["round2_avg_std"] for p in papers]

        f.write("## 整体统计\n\n")
        f.write(f"- **平均分**: {statistics.mean(scores):.2f}\n")
        f.write(f"- **中位数**: {statistics.median(scores):.2f}\n")
        f.write(f"- **最高分**: {max(scores):.2f}\n")
        f.write(f"- **最低分**: {min(scores):.2f}\n")
        f.write(f"- **平均标准差**: {statistics.mean(stds):.2f}\n\n")

        # 分数区间统计
        f.write("## 分数区间分布\n\n")
        bins = [
            (90, 100, "90-100"),
            (85, 90, "85-90"),
            (80, 85, "80-85"),
            (75, 80, "75-80"),
            (70, 75, "70-75"),
            (60, 70, "60-70"),
            (0, 60, "<60")
        ]

        f.write("| 分数区间 | 论文数 | 占比 |\n")
        f.write("|---------|--------|------|\n")
        for low, high, label in bins:
            count = sum(1 for s in scores if low <= s < high)
            percentage = count / len(scores) * 100
            f.write(f"| {label} | {count} 篇 | {percentage:.1f}% |\n")

        f.write("\n")

        # 标准差区间统计
        f.write("## 标准差区间分布\n\n")
        std_bins = [
            (0, 3, "<3 (高一致性)"),
            (3, 5, "3-5 (中等一致性)"),
            (5, 8, "5-8 (低一致性)"),
            (8, 100, ">8 (分歧显著)")
        ]

        f.write("| 标准差区间 | 论文数 | 占比 |\n")
        f.write("|-----------|--------|------|\n")
        for low, high, label in std_bins:
            count = sum(1 for s in stds if low <= s < high)
            percentage = count / len(stds) * 100
            f.write(f"| {label} | {count} 篇 | {percentage:.1f}% |\n")

        f.write("\n")

        # 期刊统计
        f.write("## 期刊统计\n\n")
        journal_stats = {}
        for p in papers:
            journal = p["journal"]
            if journal not in journal_stats:
                journal_stats[journal] = {
                    "count": 0,
                    "scores": [],
                    "stds": []
                }
            journal_stats[journal]["count"] += 1
            journal_stats[journal]["scores"].append(p["round2_mean"])
            journal_stats[journal]["stds"].append(p["round2_avg_std"])

        # 按论文数量降序排序
        sorted_journals = sorted(journal_stats.items(), key=lambda x: x[1]["count"], reverse=True)

        f.write("| 期刊 | 论文数 | 平均分 | 平均标准差 |\n")
        f.write("|------|--------|--------|------------|\n")
        for journal, stats in sorted_journals:
            avg_score = statistics.mean(stats["scores"])
            avg_std = statistics.mean(stats["stds"])
            f.write(f"| {journal} | {stats['count']} | {avg_score:.2f} | {avg_std:.2f} |\n")

        f.write("\n")

        # 完整论文列表（前 100 篇）
        f.write("## Top 100 论文列表\n\n")
        f.write("| 排名 | 平均分 | 标准差 | 期刊 | 论文标题 |\n")
        f.write("|------|--------|--------|------|----------|\n")

        for i, paper in enumerate(papers[:100], 1):
            f.write(f"| {i} | {paper['round2_mean']:.2f} | {paper['round2_avg_std']:.2f} | {paper['journal']} | {paper['title']} |\n")

        f.write("\n")

        # 分组统计
        f.write("## 分组统计\n\n")

        # 按分数分组
        f.write("### 按分数分组\n\n")

        f.write("#### 优秀论文（≥80 分）\n\n")
        excellent = [p for p in papers if p["round2_mean"] >= 80]
        f.write(f"共 {len(excellent)} 篇\n\n")
        if excellent:
            f.write("| 排名 | 平均分 | 标准差 | 期刊 | 论文标题 |\n")
            f.write("|------|--------|--------|------|----------|\n")
            for p in excellent[:20]:  # 只显示前 20 篇
                rank = papers.index(p) + 1
                f.write(f"| {rank} | {p['round2_mean']:.2f} | {p['round2_avg_std']:.2f} | {p['journal']} | {p['title']} |\n")
            if len(excellent) > 20:
                f.write(f"\n... 还有 {len(excellent) - 20} 篇\n")
        f.write("\n")

        f.write("#### 良好论文（70-80 分）\n\n")
        good = [p for p in papers if 70 <= p["round2_mean"] < 80]
        f.write(f"共 {len(good)} 篇\n\n")

        f.write("#### 及格论文（60-70 分）\n\n")
        pass_papers = [p for p in papers if 60 <= p["round2_mean"] < 70]
        f.write(f"共 {len(pass_papers)} 篇\n\n")

        f.write("#### 不及格论文（<60 分）\n\n")
        fail = [p for p in papers if p["round2_mean"] < 60]
        f.write(f"共 {len(fail)} 篇\n\n")
        if fail:
            f.write("| 排名 | 平均分 | 标准差 | 期刊 | 论文标题 |\n")
            f.write("|------|--------|--------|------|----------|\n")
            for p in fail[:20]:  # 只显示前 20 篇
                rank = papers.index(p) + 1
                f.write(f"| {rank} | {p['round2_mean']:.2f} | {p['round2_avg_std']:.2f} | {p['journal']} | {p['title']} |\n")
            if len(fail) > 20:
                f.write(f"\n... 还有 {len(fail) - 20} 篇\n")
        f.write("\n")

        # 按标准差分组
        f.write("### 按标准差分组\n\n")

        f.write("#### 高一致性（std < 3）\n\n")
        high_consistency = [p for p in papers if p["round2_avg_std"] < 3]
        f.write(f"共 {len(high_consistency)} 篇\n\n")
        if high_consistency:
            f.write("| 排名 | 平均分 | 标准差 | 期刊 | 论文标题 |\n")
            f.write("|------|--------|--------|------|----------|\n")
            for p in high_consistency[:20]:  # 只显示前 20 篇
                rank = papers.index(p) + 1
                f.write(f"| {rank} | {p['round2_mean']:.2f} | {p['round2_avg_std']:.2f} | {p['journal']} | {p['title']} |\n")
            if len(high_consistency) > 20:
                f.write(f"\n... 还有 {len(high_consistency) - 20} 篇\n")
        f.write("\n")

        f.write("#### 分歧显著（std > 8）\n\n")
        high_divergence = [p for p in papers if p["round2_avg_std"] > 8]
        f.write(f"共 {len(high_divergence)} 篇\n\n")
        if high_divergence:
            f.write("| 排名 | 平均分 | 标准差 | 期刊 | 论文标题 |\n")
            f.write("|------|--------|--------|------|----------|\n")
            for p in high_divergence[:20]:  # 只显示前 20 篇
                rank = papers.index(p) + 1
                f.write(f"| {rank} | {p['round2_mean']:.2f} | {p['round2_avg_std']:.2f} | {p['journal']} | {p['title']} |\n")
            if len(high_divergence) > 20:
                f.write(f"\n... 还有 {len(high_divergence) - 20} 篇\n")
        f.write("\n")

        f.write("---\n\n")
        f.write("*本报告由 SocialEval 系统自动生成*\n")


def main():
    parser = argparse.ArgumentParser(description="Phase 2 总报告生成器")
    parser.add_argument("--input-dir", required=True, help="输入目录（包含所有批次结果）")
    parser.add_argument("--output", required=True, help="输出 Markdown 文件路径")

    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    output_file = Path(args.output)

    if not input_dir.exists():
        print(f"错误: 输入目录不存在: {input_dir}")
        return

    print("正在加载期刊映射...")
    journal_mapping = load_journal_mapping()
    print(f"加载了 {len(journal_mapping)} 个期刊映射")

    print("\n正在收集所有批次的 Round 2 结果...")
    papers = collect_all_papers(input_dir, journal_mapping)
    print(f"收集了 {len(papers)} 篇论文的结果")

    if not papers:
        print("警告: 未找到任何论文结果")
        return

    print("\n正在生成 Markdown 报告...")
    generate_markdown_report(papers, output_file)

    print(f"\n报告已生成: {output_file}")
    print(f"总计 {len(papers)} 篇论文")

    # 输出简要统计
    scores = [p["round2_mean"] for p in papers]
    stds = [p["round2_avg_std"] for p in papers]

    print(f"\n简要统计:")
    print(f"  平均分: {statistics.mean(scores):.2f}")
    print(f"  中位数: {statistics.median(scores):.2f}")
    print(f"  平均标准差: {statistics.mean(stds):.2f}")
    print(f"  优秀论文（≥80）: {sum(1 for s in scores if s >= 80)} 篇")
    print(f"  分歧显著（std>8）: {sum(1 for s in stds if s > 8)} 篇")


if __name__ == "__main__":
    main()
