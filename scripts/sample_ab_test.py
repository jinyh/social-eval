#!/usr/bin/env python3
"""
抽样 A/B 测试：用旧/新 prompt 对低置信度论文做对比分类。

从 1920 篇中抽取 50 篇低置信度论文，对比新旧 prompt 的分类差异。
用于判断是否需要全量重跑。

用法: uv run python scripts/sample_ab_test.py
"""

import asyncio
import csv
import json
import os
import random
from pathlib import Path

import openai
from dotenv import load_dotenv

load_dotenv()

MODEL = "qwen3.7-max"
TEMPERATURE = 0.3
TIMEOUT = 60
SAMPLE_SIZE = 50

# 导入 prompt（从 test_prompt_enhancement 复用）
import sys
sys.path.insert(0, str(Path(__file__).parent))
from test_prompt_enhancement import OLD_PROMPT, NEW_PROMPT, CATEGORY_LIST, CATEGORY_MAPPING, extract_json

CSV_PATH = Path("results/sandakan-new-metadata.csv")
LLM_PATH = Path("results/sandakan-ai-classification.json")


async def classify(client, prompt_template, title, institution):
    prompt = prompt_template.format(
        categories=CATEGORY_LIST, title=title, institution=institution,
    )
    resp = await asyncio.wait_for(
        client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=TEMPERATURE,
        ),
        timeout=TIMEOUT,
    )
    result = extract_json(resp.choices[0].message.content)
    result["主分类"] = CATEGORY_MAPPING.get(result["主分类"], result["主分类"])
    result["次分类"] = CATEGORY_MAPPING.get(result["次分类"], result["次分类"])
    return result


async def main():
    # 加载数据
    with open(LLM_PATH, "r", encoding="utf-8") as f:
        ai = {int(k): v for k, v in json.load(f).items()}
    with open(CSV_PATH, "r", encoding="utf-8-sig") as f:
        papers = {int(r["编号"]): r for r in csv.DictReader(f)}

    # 按置信度分层抽样
    low = [(pid, d) for pid, d in ai.items() if d["主分类概率"] < 0.80]
    mid = [(pid, d) for pid, d in ai.items() if 0.80 <= d["主分类概率"] < 0.90]
    high = [(pid, d) for pid, d in ai.items() if d["主分类概率"] >= 0.90]

    random.seed(42)
    sample = (
        random.sample(low, min(25, len(low)))
        + random.sample(mid, min(15, len(mid)))
        + random.sample(high, min(10, len(high)))
    )

    client = openai.AsyncOpenAI(
        api_key=os.getenv("DASHSCOPE_API_KEY", ""),
        base_url=os.getenv(
            "DASHSCOPE_BASE_URL",
            "https://dashscope.aliyuncs.com/compatible-mode/v1",
        ),
    )

    print(f"{'='*100}")
    print(f"抽样 A/B 测试: {len(sample)} 篇 (低={min(25,len(low))} 中={min(15,len(mid))} 高={min(10,len(high))})")
    print(f"{'='*100}")
    print(f"{'PID':>5} | {'旧分类':^12} {'旧P':>4} | {'新分类':^12} {'新P':>4} | 变化 | 题目")
    print("-" * 100)

    changed = 0
    unchanged = 0
    changes_detail = []

    for pid, old_result in sample:
        p = papers[pid]
        title = p["题目"]
        inst = p.get("作者机构", "")

        new_result = await classify(client, NEW_PROMPT, title, inst)

        old_main = old_result["主分类"]
        new_main = new_result["主分类"]
        is_changed = old_main != new_main

        if is_changed:
            changed += 1
            changes_detail.append((pid, title, old_main, new_main, old_result["主分类概率"], new_result["主分类概率"]))
        else:
            unchanged += 1

        mark = "🔄" if is_changed else "  "
        print(
            f"{pid:5d} | {old_main:12s} {old_result['主分类概率']:>4} | "
            f"{new_main:12s} {new_result['主分类概率']:>4} | {mark}    | {title[:35]}"
        )

    print(f"\n{'='*100}")
    print(f"结果:")
    print(f"  变化: {changed}/{len(sample)} ({changed/len(sample)*100:.0f}%)")
    print(f"  不变: {unchanged}/{len(sample)} ({unchanged/len(sample)*100:.0f}%)")

    # 按置信度层分析变化率
    low_changed = sum(1 for pid, _, om, nm, _, _ in changes_detail if ai[pid]["主分类概率"] < 0.80)
    mid_changed = sum(1 for pid, _, om, nm, _, _ in changes_detail if 0.80 <= ai[pid]["主分类概率"] < 0.90)
    high_changed = sum(1 for pid, _, om, nm, _, _ in changes_detail if ai[pid]["主分类概率"] >= 0.90)

    print(f"\n按置信度层:")
    print(f"  低 (<0.80): {low_changed}/{min(25,len(low))} 变化")
    print(f"  中 (0.80-0.89): {mid_changed}/{min(15,len(mid))} 变化")
    print(f"  高 (>=0.90): {high_changed}/{min(10,len(high))} 变化")

    if changes_detail:
        print(f"\n变化明细:")
        for pid, title, old, new, old_p, new_p in changes_detail:
            print(f"  PID {pid}: {old}({old_p}) → {new}({new_p}) | {title[:45]}")

    # 估算全量影响
    if changed > 0:
        est_total = int(changed / len(sample) * len(ai))
        print(f"\n估算全量影响: ~{est_total} 篇可能变化 (基于 {len(sample)} 篇抽样)")
        if est_total > 50:
            print("  → 建议全量重跑")
        elif est_total > 10:
            print("  → 可选择性重跑（仅低置信度层）")
        else:
            print("  → 不建议全量重跑，收益太小")


if __name__ == "__main__":
    asyncio.run(main())
