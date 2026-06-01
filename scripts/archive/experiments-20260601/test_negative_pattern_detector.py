#!/usr/bin/env python3
"""Stage A 负面模式检测器 dry-run 测试脚本

只运行 Stage A 检测，不运行六维评分。输出：
- 每篇论文的 pattern 命中矩阵
- 误报/漏报分析
- evidence quote 汇总

用法：
    # 测试全部负样本
    .venv/bin/python scripts/test_negative_pattern_detector.py

    # 测试单篇
    .venv/bin/python scripts/test_negative_pattern_detector.py \
        --paper "raw/sample/补充负样本/1.邵莉莉 - 2025 - 论绿色溯源法律制度的规范构造.pdf"

    # 包含正样本误报检查
    .venv/bin/python scripts/test_negative_pattern_detector.py --include-positive
"""

import argparse
import asyncio
import json
import sys
import time
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import yaml

from src.evaluation.negative_pattern_detector import (
    load_negative_patterns,
    run_stage_a,
    aggregate_stage_a_results,
)
from src.evaluation.providers.factory import create_providers
from src.ingestion.preprocessor import process_file

NEGATIVE_SAMPLES = [
    "raw/sample/补充负样本/1.邵莉莉 - 2025 - 论绿色溯源法律制度的规范构造.pdf",
    "raw/sample/补充负样本/2.杨清望 - 2025 - 爱国主义法治建设的理论逻辑与实施体系.pdf",
    "raw/sample/补充负样本/3.李雪 - 2026 - 比例原则视角下家庭教育指导令的制度完善.pdf",
    "raw/sample/补充负样本/4.伍德志 - 2023 - 网络社会道德的普泛化及其法律规制.pdf",
    "raw/sample/补充负样本/5.李姝卉 - 2025 - 算法伦理的法律表达.pdf",
    "raw/sample/补充负样本/6.陆青和万子怡 - 2026 - 数字时代人格权商业化利用的法理重构：身份分层理论的展开.pdf",
    "raw/sample/补充负样本/7.包晓丽 - 2025 - 数据产权登记制度的体系构建.pdf",
    "raw/sample/补充负样本/8.娄金炜 - 2026 - 数字化治理背景下行政参与权遮蔽的生成逻辑与制度因应.pdf",
    "raw/sample/补充负样本/9.张涛 - 2024 - 通过算法审计规制自动化决策以社会技术系统理论为视角.pdf",
    "raw/sample/补充负样本/10.崔聪聪 - 2024 - 个人信息监管沙箱的法理基础与制度构建.pdf",
]

POSITIVE_SAMPLES = [
    "raw/calibration-regression/司法公正与同理心正义_杜宴林.pdf",
    "raw/calibration-regression/比例原则在民法上的适用及展开_郑晓剑.pdf",
    "raw/calibration-regression/国体的起源、构造和选择_中西暗合与差异_佀化强.pdf",
]

# 专家意见中明确指出的负面模式（用于计算命中率）
EXPERT_EXPECTED = {
    "1.邵莉莉": {"analytical_framework": ["slogan_advocacy"]},
    "2.杨清望": {"analytical_framework": ["slogan_advocacy"], "conclusion_consensus": ["mechanical_application"]},
    "3.李雪": {"analytical_framework": ["head_heavy_tail_light"]},
    "4.伍德志": {"analytical_framework": ["head_heavy_tail_light"]},
    "5.李姝卉": {"conclusion_consensus": ["direction_only_suggestion"]},
    "6.陆青和万子怡": {"conclusion_consensus": ["insufficient_justification"]},
    "7.包晓丽": {},
    "8.娄金炜": {},
    "9.张涛": {},
    "10.崔聪聪": {"analytical_framework": ["concept_stacking"], "conclusion_consensus": ["insufficient_justification"]},
}


async def test_single_paper(
    paper_path: str,
    providers,
    np_config: dict,
) -> dict:
    """对单篇论文运行 Stage A 检测"""
    paper = process_file(paper_path)
    paper_name = Path(paper_path).stem

    results_by_dim = {}
    for dim_key, patterns in np_config["dimensions"].items():
        dim_results = await run_stage_a(
            providers=providers,
            dimension_key=dim_key,
            patterns=patterns,
            paper=paper,
            mode=np_config["mode"],
        )
        agg_ceiling, review = aggregate_stage_a_results(dim_results)
        results_by_dim[dim_key] = {
            "per_model": [r.model_dump() for r in dim_results],
            "aggregated_ceiling": agg_ceiling,
            "requires_manual_review": review,
            "triggered_patterns": [],
        }
        for r in dim_results:
            for flag in r.pattern_flags:
                if flag.triggered:
                    pid = flag.pattern_id
                    if pid not in results_by_dim[dim_key]["triggered_patterns"]:
                        results_by_dim[dim_key]["triggered_patterns"].append(pid)

    return {
        "paper": paper_name,
        "paper_path": paper_path,
        "dimensions": results_by_dim,
    }


def compute_hit_rate(all_results: list[dict], sample_type: str) -> dict:
    """计算命中率统计"""
    if sample_type == "negative":
        total_expected = 0
        total_hit = 0
        total_false_negative = 0
        details = []

        for result in all_results:
            paper_key = result["paper"].split(" - ")[0] if " - " in result["paper"] else result["paper"]
            expected = EXPERT_EXPECTED.get(paper_key, {})

            for dim_key, expected_patterns in expected.items():
                for pid in expected_patterns:
                    total_expected += 1
                    triggered = result["dimensions"].get(dim_key, {}).get("triggered_patterns", [])
                    if pid in triggered:
                        total_hit += 1
                    else:
                        total_false_negative += 1
                        details.append(f"漏报: {paper_key} / {dim_key} / {pid}")

        hit_rate = total_hit / total_expected if total_expected > 0 else 0.0
        return {
            "total_expected": total_expected,
            "total_hit": total_hit,
            "hit_rate": round(hit_rate, 3),
            "false_negatives": total_false_negative,
            "details": details,
        }
    else:
        # 正样本误报率
        total_checks = 0
        false_positives = 0
        details = []

        for result in all_results:
            for dim_key, dim_data in result["dimensions"].items():
                total_checks += 1
                triggered = dim_data.get("triggered_patterns", [])
                if triggered:
                    false_positives += 1
                    details.append(f"误报: {result['paper']} / {dim_key} / {triggered}")

        fpr = false_positives / total_checks if total_checks > 0 else 0.0
        return {
            "total_checks": total_checks,
            "false_positives": false_positives,
            "false_positive_rate": round(fpr, 3),
            "details": details,
        }


async def main_async(args):
    framework_path = args.framework
    data = yaml.safe_load(Path(framework_path).read_text(encoding="utf-8"))
    np_config = load_negative_patterns(data)
    if not np_config:
        print("❌ 框架未配置 negative_patterns 或 mode=disabled")
        return 1

    model_names = args.models.split(",")
    providers = create_providers(model_names)

    print("=" * 60)
    print("Stage A 负面模式检测器 dry-run 测试")
    print(f"框架: {framework_path}")
    print(f"模型: {model_names}")
    print(f"模式: {np_config['mode']}")
    print("=" * 60)

    # 确定测试样本
    if args.paper:
        papers = [args.paper]
        sample_type = "single"
    else:
        papers = list(NEGATIVE_SAMPLES)
        sample_type = "negative"

    positive_papers = POSITIVE_SAMPLES if args.include_positive else []

    # 运行负样本/指定样本
    all_results = []
    start_time = time.time()

    print(f"\n--- 负样本检测（{len(papers)} 篇）---")
    for i, paper_path in enumerate(papers, 1):
        paper_name = Path(paper_path).name[:40]
        print(f"\n[{i}/{len(papers)}] {paper_name}")
        result = await test_single_paper(paper_path, providers, np_config)
        all_results.append(result)

        for dim_key, dim_data in result["dimensions"].items():
            triggered = dim_data["triggered_patterns"]
            ceiling = dim_data["aggregated_ceiling"]
            if triggered:
                print(f"  {dim_key}: 触发 {triggered}, ceiling={ceiling}")
            else:
                print(f"  {dim_key}: 未触发")

    # 运行正样本
    positive_results = []
    if positive_papers:
        print(f"\n--- 正样本误报检查（{len(positive_papers)} 篇）---")
        for i, paper_path in enumerate(positive_papers, 1):
            paper_name = Path(paper_path).name[:40]
            print(f"\n[正{i}/{len(positive_papers)}] {paper_name}")
            result = await test_single_paper(paper_path, providers, np_config)
            positive_results.append(result)

            for dim_key, dim_data in result["dimensions"].items():
                triggered = dim_data["triggered_patterns"]
                if triggered:
                    print(f"  ⚠️ 误报! {dim_key}: {triggered}")
                else:
                    print(f"  {dim_key}: ✅ 未触发")

    elapsed = time.time() - start_time

    # 统计
    print("\n" + "=" * 60)
    print("检测结果汇总")
    print("=" * 60)

    if sample_type == "negative":
        hit_stats = compute_hit_rate(all_results, "negative")
        print("\n负样本命中率:")
        print(f"  专家预期 pattern 总数: {hit_stats['total_expected']}")
        print(f"  Stage A 命中数: {hit_stats['total_hit']}")
        print(f"  命中率: {hit_stats['hit_rate']:.1%}")
        if hit_stats["details"]:
            print("  漏报详情:")
            for d in hit_stats["details"]:
                print(f"    - {d}")

    if positive_results:
        fpr_stats = compute_hit_rate(positive_results, "positive")
        print("\n正样本误报率:")
        print(f"  检查总数: {fpr_stats['total_checks']}")
        print(f"  误报数: {fpr_stats['false_positives']}")
        print(f"  误报率: {fpr_stats['false_positive_rate']:.1%}")
        if fpr_stats["details"]:
            for d in fpr_stats["details"]:
                print(f"    - {d}")

    # 命中矩阵
    print("\n--- Pattern 命中矩阵 ---")
    all_patterns = []
    for dim_patterns in np_config["dimensions"].values():
        all_patterns.extend(p["pattern_id"] for p in dim_patterns)

    header = f"{'论文':<12}" + "".join(f"{p:<24}" for p in all_patterns)
    print(header)
    print("-" * len(header))

    for result in all_results:
        paper_key = result["paper"].split(" - ")[0] if " - " in result["paper"] else result["paper"][:12]
        row = f"{paper_key:<12}"
        for pid in all_patterns:
            hit = False
            for dim_data in result["dimensions"].values():
                if pid in dim_data.get("triggered_patterns", []):
                    hit = True
                    break
            row += f"{'✓':<24}" if hit else f"{'·':<24}"
        print(row)

    print(f"\n耗时: {elapsed:.0f} 秒")

    # 保存结果
    output_dir = PROJECT_ROOT / "results" / "stage-a-dryrun"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"dryrun-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump({
            "test_time": datetime.now().isoformat(),
            "framework": framework_path,
            "models": model_names,
            "mode": np_config["mode"],
            "elapsed_seconds": round(elapsed, 1),
            "negative_results": all_results,
            "positive_results": positive_results,
        }, f, ensure_ascii=False, indent=2)

    print(f"\n结果已保存: {output_path}")
    return 0


def main():
    parser = argparse.ArgumentParser(description="Stage A 负面模式检测器 dry-run 测试")
    parser.add_argument(
        "--framework",
        default="configs/frameworks/law-v2.51-20260515.yaml",
        help="评价框架 YAML 路径",
    )
    parser.add_argument("--paper", default=None, help="测试单篇论文路径")
    parser.add_argument("--models", default="qwen3.6-plus,glm-5.1", help="模型列表")
    parser.add_argument("--include-positive", action="store_true", help="包含正样本误报检查")
    args = parser.parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    sys.exit(main())
