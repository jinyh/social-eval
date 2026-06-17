#!/usr/bin/env python3
"""
对比 AI 学科分类和专家确认分类，分析不一致情况。

输入：
- results/sandakan-ai-classification.json（AI 分类结果，1920 篇）
- results/e2-top102/专家确认.csv（102 篇专家确认分类）
- results/e2-top102/expert-corrections-25.csv（25 篇专家纠正）

输出：
- results/e2-top102/ai-expert-comparison-report.md（分析报告）
- results/e2-top102/ai-expert-mismatch-detailed.csv（详细不一致列表）
"""

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

# ── 配置 ──
AI_CLASSIFICATION_PATH = Path("results/sandakan-ai-classification.json")
EXPERT_CONFIRM_PATH = Path("results/e2-top102/专家确认.csv")
EXPERT_CORRECTION_PATH = Path("results/e2-top102/expert-corrections-25.csv")
MERGED_METADATA_PATH = Path("results/merged-metadata.csv")

OUTPUT_REPORT = Path("results/e2-top102/ai-expert-comparison-report.md")
OUTPUT_MISMATCH_CSV = Path("results/e2-top102/ai-expert-mismatch-detailed.csv")


def load_ai_classification() -> dict[int, dict]:
    """加载 AI 分类结果。"""
    with open(AI_CLASSIFICATION_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    return {int(k): v for k, v in data.items()}


def load_expert_confirm() -> dict[int, str]:
    """加载专家确认分类（102 篇）。"""
    result = {}
    with open(EXPERT_CONFIRM_PATH, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            pid = int(row["编号"])
            result[pid] = row["专家分类"]
    return result


def load_expert_corrections() -> dict[int, str]:
    """加载专家纠正分类（25 篇）。"""
    result = {}
    with open(EXPERT_CORRECTION_PATH, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # expert-corrections-25.csv 使用 pid 字段
            pid = int(row["pid"])
            result[pid] = row["专家分类"]
    return result


def load_metadata() -> dict[int, dict]:
    """加载论文元数据。"""
    result = {}
    with open(MERGED_METADATA_PATH, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            pid = int(row["编号"])
            result[pid] = {
                "题目": row["题目"],
                "作者": row["作者"],
                "机构": row["作者机构"],
                "期刊": row["期刊"],
                "年份": row["年份"],
            }
    return result


def analyze_mismatch(ai_class: dict, expert_class: dict, metadata: dict):
    """分析 AI 和专家分类的不一致情况。"""
    # 合并专家分类（专家确认 + 专家纠正）
    all_expert = {**expert_class}

    # 统计
    total_expert = len(all_expert)
    match_primary = 0  # AI 主分类 == 专家分类
    match_secondary = 0  # AI 次分类 == 专家分类
    mismatch = 0  # 完全不匹配

    # 详细不一致列表
    mismatches = []

    # 按不一致类型分组
    mismatch_by_type = defaultdict(list)

    for pid, expert in all_expert.items():
        if pid not in ai_class:
            print(f"  ⚠️  PID {pid} 在 AI 分类中缺失")
            continue

        ai = ai_class[pid]
        ai_primary = ai["主分类"]
        ai_secondary = ai["次分类"]
        ai_p1 = ai["主分类概率"]
        ai_p2 = ai["次分类概率"]

        if ai_primary == expert:
            match_primary += 1
        elif ai_secondary == expert:
            match_secondary += 1
        else:
            mismatch += 1
            meta = metadata.get(pid, {})
            mismatches.append(
                {
                    "编号": pid,
                    "题目": meta.get("题目", ""),
                    "作者": meta.get("作者", ""),
                    "机构": meta.get("机构", ""),
                    "期刊": meta.get("期刊", ""),
                    "年份": meta.get("年份", ""),
                    "AI主分类": ai_primary,
                    "AI次分类": ai_secondary,
                    "AI主分类概率": ai_p1,
                    "AI次分类概率": ai_p2,
                    "专家分类": expert,
                }
            )
            # 记录不一致类型
            key = f"{ai_primary} → {expert}"
            mismatch_by_type[key].append(pid)

    # 计算准确率
    accuracy_primary = match_primary / total_expert * 100
    accuracy_top2 = (match_primary + match_secondary) / total_expert * 100
    mismatch_rate = mismatch / total_expert * 100

    # 生成报告
    report_lines = [
        "# AI 学科分类与专家确认对比报告",
        "",
        f"生成时间：{Path(__file__).stat().st_mtime}",
        "",
        "## 数据来源",
        "",
        f"- AI 分类结果：`{AI_CLASSIFICATION_PATH}`（1920 篇）",
        f"- 专家确认分类：`{EXPERT_CONFIRM_PATH}`（102 篇）",
        f"- 专家纠正分类：`{EXPERT_CORRECTION_PATH}`（25 篇）",
        f"- 合并后专家分类总数：**{total_expert} 篇**",
        "",
        "## 整体准确率",
        "",
        f"- **主分类准确率**：{match_primary}/{total_expert} = **{accuracy_primary:.1f}%**",
        f"- **Top-2 准确率**（主或次匹配）：{match_primary + match_secondary}/{total_expert} = **{accuracy_top2:.1f}%**",
        f"- **完全不匹配**：{mismatch}/{total_expert} = **{mismatch_rate:.1f}%**",
        "",
        "## 不匹配类型分布",
        "",
        "| AI 主分类 → 专家分类 | 数量 | 论文编号 |",
        "|---------------------|------|----------|",
    ]

    for key, pids in sorted(
        mismatch_by_type.items(), key=lambda x: len(x[1]), reverse=True
    ):
        pids_str = ", ".join(str(p) for p in sorted(pids))
        report_lines.append(f"| {key} | {len(pids)} | {pids_str} |")

    report_lines.extend(
        [
            "",
            "## 详细不匹配列表",
            "",
            f"详见：`{OUTPUT_MISMATCH_CSV}`",
            "",
            "## 问题分析",
            "",
            "### 高频不匹配模式",
            "",
        ]
    )

    # 分析高频不匹配
    top_mismatches = sorted(
        mismatch_by_type.items(), key=lambda x: len(x[1]), reverse=True
    )[:5]

    for key, pids in top_mismatches:
        ai_cat, expert_cat = key.split(" → ")
        report_lines.append(f"#### {key} ({len(pids)} 篇)")
        report_lines.append("")
        report_lines.append("可能原因：")
        report_lines.append("")

        # 分析具体论文
        for pid in pids[:3]:  # 只展示前 3 篇
            meta = metadata.get(pid, {})
            title = meta.get("题目", "")
            report_lines.append(f"- **论文 {pid}**：{title}")

        report_lines.append("")

    # 写入报告
    OUTPUT_REPORT.write_text("\n".join(report_lines), encoding="utf-8")
    print(f"✅ 报告已保存：{OUTPUT_REPORT}")

    # 写入详细 CSV
    if mismatches:
        with open(OUTPUT_MISMATCH_CSV, "w", encoding="utf-8-sig", newline="") as f:
            fieldnames = [
                "编号",
                "期刊",
                "年份",
                "题目",
                "作者",
                "机构",
                "AI主分类",
                "AI次分类",
                "AI主分类概率",
                "AI次分类概率",
                "专家分类",
            ]
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for row in mismatches:
                writer.writerow(row)
        print(f"✅ 详细不匹配列表已保存：{OUTPUT_MISMATCH_CSV}")

    # 打印摘要
    print(f"\n主分类准确率：{accuracy_primary:.1f}%")
    print(f"Top-2 准确率：{accuracy_top2:.1f}%")
    print(f"完全不匹配：{mismatch_rate:.1f}%")
    print(f"\n详细报告：{OUTPUT_REPORT}")


def main():
    print("加载数据...")
    ai_class = load_ai_classification()
    expert_confirm = load_expert_confirm()
    expert_corrections = load_expert_corrections()
    metadata = load_metadata()

    # 合并专家分类
    all_expert = {**expert_confirm, **expert_corrections}

    print(f"AI 分类：{len(ai_class)} 篇")
    print(f"专家确认：{len(expert_confirm)} 篇")
    print(f"专家纠正：{len(expert_corrections)} 篇")
    print(f"合并后专家分类：{len(all_expert)} 篇")

    print("\n开始对比分析...")
    analyze_mismatch(ai_class, all_expert, metadata)


if __name__ == "__main__":
    main()
