#!/usr/bin/env python3
"""小规模验证测试（3 篇论文）

验证 4 模型 + 最严格聚合逻辑是否正确工作
"""

import asyncio
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.run_convergence_test import run_convergence_test


async def main():
    # 测试配置
    framework = "configs/frameworks/law-v2.50.2-20260514.yaml"
    models = ["deepseek-v4-pro", "glm-5.1", "kimi-k2.6", "qwen3.6-plus"]
    papers = [
        "raw/phase1-100-papers/001_答复类行政解释的行政诉讼法定位及其司法审查.pdf",
        "raw/phase1-100-papers/002_非典型与典型案件：术语、成因及其关系.pdf",
        "raw/phase1-100-papers/003_滥用市场支配地位理论的司法考量.pdf",
    ]
    output_dir = Path("results/test-strictest-3papers")
    output_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("小规模验证测试（3 篇论文）")
    print("=" * 60)
    print(f"框架: {framework}")
    print(f"模型: {', '.join(models)}")
    print(f"聚合模式: both（同时计算 mean 和 strictest）")
    print(f"论文数: {len(papers)}")
    print("=" * 60 + "\n")

    results = []
    for i, paper_path in enumerate(papers, 1):
        paper_name = Path(paper_path).stem[:50]
        print(f"\n[{i}/{len(papers)}] 评估: {paper_name}")
        print("-" * 60)

        try:
            result = await run_convergence_test(
                framework_path=framework,
                paper_path=paper_path,
                model_names=models,
                aggregation_mode="both",
            )

            # 保存结果
            output_path = output_dir / f"paper-{i:03d}.json"
            output_path.write_text(
                json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
            )

            overall = result["overall"]
            results.append(overall)

            # 打印汇总
            print(f"\n--- 结果汇总 ---")
            print(f"Mean 聚合:")
            print(f"  final_score: {overall['aggregation_mean']['final_score']}")
            print(f"  weighted_total: {overall['aggregation_mean']['weighted_total']}")
            print(f"\nStrictest 聚合:")
            print(f"  final_score: {overall['aggregation_strictest']['final_score']}")
            print(f"  weighted_total: {overall['aggregation_strictest']['weighted_total']}")
            print(f"\n分数差距: {overall['score_gap']} 分")
            print(f"最大 std: {overall['max_std']}")
            print(f"高置信度比例: {overall['high_confidence_pct']}%")

            # 打印各维度的最严格模型
            print(f"\n--- 各维度最严格模型 ---")
            for dim_key, dim_data in result["dimensions"].items():
                if "strictest_model" in dim_data:
                    print(f"  {dim_data['name_zh']}: {dim_data['strictest']} ({dim_data['strictest_model']})")

        except Exception as e:
            print(f"❌ 失败: {e}")
            import traceback
            traceback.print_exc()

    # 最终汇总
    print("\n" + "=" * 60)
    print("验证测试汇总")
    print("=" * 60)

    if results:
        mean_scores = [r["aggregation_mean"]["final_score"] for r in results]
        strictest_scores = [r["aggregation_strictest"]["final_score"] for r in results]

        print(f"\nMean 聚合:")
        print(f"  平均分: {sum(mean_scores) / len(mean_scores):.1f}")
        print(f"  范围: {min(mean_scores):.1f} ~ {max(mean_scores):.1f}")

        print(f"\nStrictest 聚合:")
        print(f"  平均分: {sum(strictest_scores) / len(strictest_scores):.1f}")
        print(f"  范围: {min(strictest_scores):.1f} ~ {max(strictest_scores):.1f}")

        gaps = [r["score_gap"] for r in results]
        print(f"\n分数差距:")
        print(f"  平均: {sum(gaps) / len(gaps):.1f} 分")
        print(f"  范围: {min(gaps):.1f} ~ {max(gaps):.1f} 分")

        print(f"\n✅ 验证测试完成！")
        print(f"结果已保存到: {output_dir}")
    else:
        print("❌ 没有成功的测试结果")

    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
