#!/usr/bin/env python3
"""v2.52 小规模验证脚本（5 篇论文）

验证目标：
- 命中率 ≥ 70%（3 个专家预期 pattern 中至少命中 2 个）
- 误报率 ≤ 10%（6 次检查最多 0 次误报）
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.evaluation.negative_pattern_detector import (
    detect_patterns_individually,
    load_negative_patterns,
)
from src.evaluation.providers import get_provider
from src.ingestion.pdf_processor import process_pdf
import yaml


# 验证样本
SAMPLES = {
    "negative": [
        ("1.邵莉莉-论绿色溯源法律制度的规范构造.pdf", "normative_statement_without_specifics"),
        ("2.杨清望-爱国主义法治建设的理论逻辑与实施体系.pdf", "fixed_framework_mechanical_application"),
        ("10.崔聪聪-个人信息监管沙箱的法理基础与制度构建.pdf", "concept_stacking_without_explanation"),
    ],
    "positive": [
        "比例原则在民法上的适用及展开_郑晓剑.pdf",
        "司法公正与同理心正义_杜宴林.pdf",
    ],
}


async def test_single_paper(paper_path: Path, framework_config: dict, provider):
    """测试单篇论文"""
    print(f"\n{'='*60}")
    print(f"测试: {paper_path.name}")
    print(f"{'='*60}")

    # 处理论文
    paper = await process_pdf(paper_path)

    # 加载 negative patterns
    np_config = load_negative_patterns(framework_config)

    results = {}
    for dim, patterns in np_config.items():
        result = await detect_patterns_individually(
            provider, dim, patterns, paper
        )
        results[dim] = result

        triggered = [f.pattern_id for f in result.pattern_flags if f.triggered]
        if triggered:
            print(f"  {dim}: ✅ 触发 {triggered}")
        else:
            print(f"  {dim}: ⚪ 未触发")

    return results


async def main():
    # 加载框架配置
    config_path = Path("configs/frameworks/law-v2.52-20260517.yaml")
    framework_config = yaml.safe_load(config_path.read_text(encoding="utf-8"))

    # 初始化 provider
    provider = get_provider("dashscope", "qwen-plus")

    base_dir = Path("raw/sample/补充负样本")
    positive_dir = Path("raw/calibration-regression")

    # 测试负样本
    print("\n" + "="*60)
    print("负样本测试（预期触发对应 pattern）")
    print("="*60)

    negative_results = {}
    for filename, expected_pattern in SAMPLES["negative"]:
        paper_path = base_dir / filename
        if not paper_path.exists():
            print(f"❌ 文件不存在: {paper_path}")
            continue

        results = await test_single_paper(paper_path, framework_config, provider)
        negative_results[filename] = {
            "expected": expected_pattern,
            "results": results,
        }

    # 测试正样本
    print("\n" + "="*60)
    print("正样本测试（预期不触发任何 pattern）")
    print("="*60)

    positive_results = {}
    for filename in SAMPLES["positive"]:
        paper_path = positive_dir / filename
        if not paper_path.exists():
            print(f"❌ 文件不存在: {paper_path}")
            continue

        results = await test_single_paper(paper_path, framework_config, provider)
        positive_results[filename] = results

    # 统计结果
    print("\n" + "="*60)
    print("验证结果汇总")
    print("="*60)

    # 命中率
    hit_count = 0
    total_expected = len(SAMPLES["negative"])

    for filename, data in negative_results.items():
        expected = data["expected"]
        results = data["results"]

        # 检查是否命中预期 pattern
        hit = False
        for dim_result in results.values():
            for flag in dim_result.pattern_flags:
                if flag.pattern_id == expected and flag.triggered:
                    hit = True
                    break

        if hit:
            hit_count += 1
            print(f"✅ {filename}: 命中预期 pattern {expected}")
        else:
            print(f"❌ {filename}: 漏报 {expected}")

    hit_rate = hit_count / total_expected if total_expected > 0 else 0
    print(f"\n命中率: {hit_count}/{total_expected} = {hit_rate:.1%}")

    # 误报率
    false_positive_count = 0
    total_checks = 0

    for filename, results in positive_results.items():
        for dim, dim_result in results.items():
            for flag in dim_result.pattern_flags:
                total_checks += 1
                if flag.triggered:
                    false_positive_count += 1
                    print(f"⚠️ {filename} / {dim} / {flag.pattern_id}: 误报")

    fpr = false_positive_count / total_checks if total_checks > 0 else 0
    print(f"\n误报率: {false_positive_count}/{total_checks} = {fpr:.1%}")

    # 验证结论
    print("\n" + "="*60)
    print("验证结论")
    print("="*60)

    hit_pass = hit_rate >= 0.70
    fpr_pass = fpr <= 0.10

    print(f"命中率: {hit_rate:.1%} {'✅ 达标' if hit_pass else '❌ 未达标'} (目标 ≥ 70%)")
    print(f"误报率: {fpr:.1%} {'✅ 达标' if fpr_pass else '❌ 未达标'} (目标 ≤ 10%)")

    if hit_pass and fpr_pass:
        print("\n🎉 验证通过！可以扩展到全部 6 个 pattern + 13 篇论文")
    else:
        print("\n❌ 验证未通过，需要调整 pattern 定义或检测逻辑")


if __name__ == "__main__":
    asyncio.run(main())
