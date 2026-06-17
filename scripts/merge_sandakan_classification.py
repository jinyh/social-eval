#!/usr/bin/env python3
"""
融合 LLM 分类结果与专家修正，生成最终的主/次分类字段。

输入:
  - results/sandakan-ai-classification.json  (LLM 分类中间结果)
  - results/e2-top102/学科归类错误条目.md     (专家修正文件1，17条)
  - results/e2-top102/学科错误条目6-15.md     (专家修正文件2，8条)
  - results/sandakan-new-metadata.csv         (原始 CSV)

输出:
  - results/sandakan-new-metadata.csv         (更新后的 CSV，14列)

用法: uv run python scripts/merge_sandakan_classification.py
"""

import csv
import json
import re
from pathlib import Path

CSV_PATH = Path("results/sandakan-new-metadata.csv")
LLM_PATH = Path("results/sandakan-ai-classification.json")
EXPERT1_PATH = Path("results/e2-top102/学科归类错误条目.md")
EXPERT2_PATH = Path("results/e2-top102/学科错误条目6-15.md")

VALID_CATEGORIES = {
    "民商法学", "刑法学", "宪法学与行政法学", "诉讼法学", "法学理论",
    "环境与资源保护法学", "国际法学", "经济法学", "知识产权法学",
    "法律史", "党内法规学",
}

CATEGORY_MAPPING = {"劳动法与社会保障法学": "民商法学"}


def parse_expert1(path: Path) -> list[dict]:
    """解析学科归类错误条目.md（按标题匹配）。"""
    corrections = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line.startswith("|") or line.startswith("| #") or line.startswith("|---"):
                continue
            parts = [p.strip() for p in line.split("|")[1:-1]]
            if len(parts) >= 9 and parts[0].isdigit():
                target = parts[8].replace("应当归类于", "").strip()
                target = CATEGORY_MAPPING.get(target, target)
                corrections.append({
                    "expert_orig": parts[2],
                    "title": parts[5],
                    "author": parts[6],
                    "target": target,
                })
    return corrections


def parse_expert2(path: Path) -> list[dict]:
    """解析学科错误条目6-15.md（按PID匹配）。"""
    corrections = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line.startswith("|") or line.startswith("| 排名") or line.startswith("| ---"):
                continue
            parts = [p.strip() for p in line.split("|")[1:-1]]
            if len(parts) >= 10 and parts[0].strip().isdigit():
                pid = int(parts[1])
                target = parts[9]
                target = CATEGORY_MAPPING.get(target, target)
                corrections.append({
                    "pid": pid,
                    "expert_orig": parts[7],
                    "target": target,
                    "title": parts[2],
                })
    return corrections


def build_expert_map(papers: list[dict], exp1: list[dict], exp2: list[dict]) -> dict:
    """构建 PID → 专家修正的映射。"""
    title_to_pid = {r["题目"].strip(): int(r["编号"]) for r in papers}
    expert_map = {}  # pid -> {target, expert_orig, source}

    # 文件1：按标题匹配
    matched = 0
    for corr in exp1:
        pid = title_to_pid.get(corr["title"])
        if pid is not None:
            expert_map[pid] = {
                "target": corr["target"],
                "expert_orig": corr["expert_orig"],
                "source": "expert1",
            }
            matched += 1
        else:
            print(f"  ⚠️ 专家文件1未匹配: {corr['title'][:30]}...")
    print(f"  专家文件1: {matched}/{len(exp1)} 条匹配成功")

    # 文件2：按PID直接匹配
    for corr in exp2:
        expert_map[corr["pid"]] = {
            "target": corr["target"],
            "expert_orig": corr["expert_orig"],
            "source": "expert2",
        }
    print(f"  专家文件2: {len(exp2)} 条直接匹配")

    return expert_map


def fuse(llm_result: dict, expert: dict | None, csv_class: str) -> dict:
    """
    融合 LLM 分类与专家修正。

    返回: {主分类, 主分类概率, 次分类, 次分类概率, 情形}
    """
    llm_main = llm_result["主分类"]
    llm_main_p = float(llm_result["主分类概率"])
    llm_sec = llm_result["次分类"]
    llm_sec_p = float(llm_result["次分类概率"])

    if expert is None:
        # 情形 D：无专家审阅
        return {
            "主分类": llm_main,
            "主分类概率": llm_main_p,
            "次分类": llm_sec,
            "次分类概率": llm_sec_p,
            "情形": "D",
        }

    target = expert["target"]
    expert_orig = expert["expert_orig"]

    if llm_main == target:
        # 情形 A：LLM 与专家一致
        boosted_p = min(llm_main_p + 0.10, 0.95)
        return {
            "主分类": llm_main,
            "主分类概率": round(boosted_p, 3),
            "次分类": llm_sec,
            "次分类概率": llm_sec_p,
            "情形": "A",
        }

    if csv_class == target and csv_class != expert_orig:
        # 情形 C：历史已修正（CSV 已=目标，专家记录了原分类）
        boosted_p = min(llm_main_p + 0.10, 0.95)
        return {
            "主分类": llm_main,  # LLM 独立判断
            "主分类概率": round(boosted_p, 3),
            "次分类": llm_sec,
            "次分类概率": llm_sec_p,
            "情形": "C",
        }

    # 情形 B：LLM 与专家不一致
    adjusted_sec_p = min(llm_main_p * 0.3, 0.20)
    main_p = max(llm_main_p, 0.75)
    # 约束校验
    if main_p + adjusted_sec_p > 1.0:
        adjusted_sec_p = 1.0 - main_p - 0.02
    adjusted_sec_p = max(0.0, round(adjusted_sec_p, 3))

    return {
        "主分类": target,
        "主分类概率": round(main_p, 3),
        "次分类": llm_main,
        "次分类概率": adjusted_sec_p,
        "情形": "B",
    }


def main():
    print("=" * 60)
    print("融合 LLM 分类与专家修正")
    print("=" * 60)

    # 1. 读取数据
    print("\n1. 读取数据...")
    with open(CSV_PATH, "r", encoding="utf-8-sig") as f:
        papers = list(csv.DictReader(f))
    print(f"  CSV: {len(papers)} 篇")

    with open(LLM_PATH, "r", encoding="utf-8") as f:
        llm_results = {int(k): v for k, v in json.load(f).items()}
    print(f"  LLM 结果: {len(llm_results)} 篇")

    exp1 = parse_expert1(EXPERT1_PATH)
    exp2 = parse_expert2(EXPERT2_PATH)
    print(f"  专家修正: {len(exp1)} + {len(exp2)} = {len(exp1)+len(exp2)} 条")

    # 2. 构建专家映射
    print("\n2. 构建专家映射...")
    expert_map = build_expert_map(papers, exp1, exp2)
    print(f"  有效专家修正: {len(expert_map)} 条")

    # 3. 融合
    print("\n3. 融合 LLM + 专家...")
    fields = list(csv.DictReader(open(CSV_PATH, "r", encoding="utf-8-sig")).fieldnames)
    new_fields = fields + ["主分类", "主分类概率", "次分类", "次分类概率", "分类情形"]

    scenario_count = {"A": 0, "B": 0, "C": 0, "D": 0}
    output_rows = []
    fallback_count = 0

    for paper in papers:
        pid = int(paper["编号"])
        csv_class = paper["分类"]

        if pid in llm_results:
            llm_result = llm_results[pid]
        else:
            # Fallback: LLM 未返回结果
            llm_result = {
                "主分类": csv_class,
                "主分类概率": 0.60,
                "次分类": "",
                "次分类概率": 0.0,
            }
            fallback_count += 1

        expert = expert_map.get(pid)
        fused = fuse(llm_result, expert, csv_class)
        scenario_count[fused["情形"]] += 1

        paper["主分类"] = fused["主分类"]
        paper["主分类概率"] = fused["主分类概率"]
        paper["次分类"] = fused["次分类"]
        paper["次分类概率"] = fused["次分类概率"]
        paper["分类情形"] = fused["情形"]
        output_rows.append(paper)

    print(f"  情形分布: A(一致)={scenario_count['A']}, B(不一致)={scenario_count['B']}, "
          f"C(历史)={scenario_count['C']}, D(无专家)={scenario_count['D']}")
    if fallback_count:
        print(f"  ⚠️ LLM fallback: {fallback_count} 篇")

    # 4. 写入 CSV
    print(f"\n4. 写入 {CSV_PATH}...")
    with open(CSV_PATH, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=new_fields)
        writer.writeheader()
        writer.writerows(output_rows)
    print(f"  列数: {len(new_fields)}, 行数: {len(output_rows)}")

    # 5. 验证
    print("\n5. 验证...")
    from collections import Counter

    main_dist = Counter(r["主分类"] for r in output_rows)
    sec_dist = Counter(r["次分类"] for r in output_rows if r["次分类"])
    print("\n  主分类分布:")
    for cls, cnt in main_dist.most_common():
        print(f"    {cls:20s} {cnt:4d} ({cnt/len(output_rows)*100:.1f}%)")
    print(f"\n  次分类分布 (非空 {sum(1 for r in output_rows if r['次分类'])} 篇):")
    for cls, cnt in sec_dist.most_common():
        print(f"    {cls:20s} {cnt:4d}")

    # 概率约束检查
    violations = []
    for r in output_rows:
        p1 = float(r["主分类概率"])
        p2 = float(r["次分类概率"])
        if p1 + p2 > 1.001:  # 浮点容差
            violations.append((int(r["编号"]), p1, p2, p1 + p2))
    print(f"\n  概率约束违规: {len(violations)} 条")
    for pid, p1, p2, total in violations[:5]:
        print(f"    PID {pid}: {p1} + {p2} = {total:.3f}")

    # LLM 主分类 vs 原始分类 一致率
    agree = sum(1 for r in output_rows if r["主分类"] == r["分类"])
    print(f"\n  主分类 vs 原始分类 一致率: {agree}/{len(output_rows)} ({agree/len(output_rows)*100:.1f}%)")

    # 专家条目逐条检查
    print("\n  专家修正条目检查:")
    for r in output_rows:
        pid = int(r["编号"])
        if pid in expert_map:
            exp = expert_map[pid]
            match_mark = "✅" if r["主分类"] == exp["target"] else "⚠️"
            print(f"    PID {pid:4d} [{r['分类情形']}] {match_mark} "
                  f"主={r['主分类']}({r['主分类概率']}) "
                  f"次={r['次分类'] or '(空)'}({r['次分类概率']}) "
                  f"| 原={r['分类']} 专家目标={exp['target']}")

    print("\n完成!")


if __name__ == "__main__":
    main()
