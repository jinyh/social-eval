#!/usr/bin/env python3
"""诊断 evaluate_fullpaper_position_assessment.py 启动卡死问题。

逐步执行每个阶段，打印耗时，定位瓶颈。

用法：
    uv run python scripts/diagnose_fullpaper_startup.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def timed(label: str):
    """计时装饰器。"""
    def decorator(fn):
        def wrapper(*args, **kwargs):
            t0 = time.monotonic()
            print(f"[{label}] 开始...", flush=True)
            result = fn(*args, **kwargs)
            elapsed = time.monotonic() - t0
            print(f"[{label}] 完成，耗时 {elapsed:.1f}s", flush=True)
            return result
        return wrapper
    return decorator


@timed("1/6 build_pdf_index")
def step1():
    from scripts.evaluate_fullpaper_position_assessment import build_pdf_index
    idx = build_pdf_index(Path("raw/fullpaper"))
    print(f"  → {len(idx)} 个 PDF", flush=True)
    return idx


@timed("2/6 build_precheck_index")
def step2():
    from scripts.evaluate_fullpaper_position_assessment import build_precheck_index
    idx = build_precheck_index(
        Path("results/fullevaluation/round1"),
        Path("results/fullevaluation/round1-err"),
    )
    print(f"  → {len(idx)} 条记录", flush=True)
    from collections import Counter
    dist = Counter(v.get("status", "unknown") for v in idx.values())
    print(f"  → 状态分布: {dict(dist)}", flush=True)
    return idx


@timed("3/6 读取 merged-metadata.csv")
def step3():
    import csv
    rows = []
    with open("results/merged-metadata.csv", "r", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            rows.append(row)
    print(f"  → {len(rows)} 行", flush=True)
    return rows


@timed("4/6 读取 1920 个 round2 JSON（_load_six_dimension_context）")
def step4(metadata_rows):
    """这是最可能的瓶颈：逐个读取 1920 个 JSON 文件。"""
    import json
    eval_dir = Path("results/fullevaluation/round2")
    found = 0
    missing = 0
    t0 = time.monotonic()
    for i, row in enumerate(metadata_rows):
        pid = int(row["编号"])
        path = eval_dir / f"paper-{pid}.json"
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            found += 1
        else:
            missing += 1
        # 每 200 篇报告一次进度
        if (i + 1) % 200 == 0:
            elapsed = time.monotonic() - t0
            print(f"  → 进度 {i+1}/{len(metadata_rows)}，耗时 {elapsed:.1f}s", flush=True)
    print(f"  → 找到 {found}，缺失 {missing}", flush=True)


@timed("5/6 load_or_build_ontology")
def step5():
    from scripts.evaluate_top101_position_assessment_two_rounds import load_or_build_ontology
    ontology = load_or_build_ontology(
        Path("knowledge/中国法学自主知识体系-树状知识库.md"),
        Path("knowledge/law_ontology.json"),
        rebuild=False,
    )
    print(f"  → 节点数: {len(ontology.nodes)}", flush=True)
    return ontology


@timed("6/6 _provider_map（创建 API provider）")
def step6():
    from scripts.evaluate_fullpaper_position_assessment import _provider_map
    from scripts.evaluate_top101_position_assessment_two_rounds import MODELS
    print(f"  → 模型: {MODELS}", flush=True)
    pm = _provider_map(MODELS)
    print(f"  → {len(pm)} 个 provider: {list(pm.keys())}", flush=True)
    return pm


def main():
    print("=" * 60, flush=True)
    print("诊断 fullpaper position assessment 启动流程", flush=True)
    print("=" * 60, flush=True)

    step1()
    step2()
    rows = step3()
    step4(rows)
    step5()
    step6()

    print("\n" + "=" * 60, flush=True)
    print("✅ 所有步骤完成，脚本可以正常启动", flush=True)
    print("=" * 60, flush=True)


if __name__ == "__main__":
    main()
