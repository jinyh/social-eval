"""v2.42 vs v2.43 回归测试

验证 v2.43 相对 v2.42 的评分结果严格一致（±0 分差异）。

用法：
    python scripts/regression_v2.42_vs_v2.43.py
"""

import asyncio
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.evaluation.prompt_builder import build_prompt
from src.evaluation.providers.factory import create_providers
from src.ingestion.preprocessor import process_file
from src.knowledge.loader import load_framework


CALIBRATION_SAMPLES = [
    "raw/calibration-regression/国体的起源、构造和选择_中西暗合与差异_佀化强.pdf",
    "raw/calibration-regression/比例原则在民法上的适用及展开_郑晓剑.pdf",
    "raw/calibration-regression/司法公正与同理心正义_杜宴林.pdf",
]


async def evaluate_single(paper_path: str, framework_path: str, provider_name: str = "qwen3.6-plus"):
    """对单篇论文用指定框架评价，返回六维分数"""
    fw = load_framework(framework_path)
    paper_text = process_file(paper_path)

    providers = create_providers([provider_name])
    provider = providers[0]

    results = {}
    for dim in fw.dimensions:
        prompt = build_prompt(fw, dim.key, paper_text)
        response = await provider.generate(prompt)

        # 简单解析 JSON（假设返回格式正确）
        try:
            data = json.loads(response)
            results[dim.key] = data.get("score", -1)
        except:
            results[dim.key] = -999  # 解析失败标记

    return results


async def main():
    print("=" * 80)
    print("v2.42 vs v2.43 回归测试")
    print("=" * 80)
    print()
    print("样本集: raw/calibration-regression/ (3 篇)")
    print("模型  : qwen3.6-plus (单模型，避免随机性)")
    print("红线  : 六维分数 ±0 差异")
    print()

    all_pass = True

    for paper in CALIBRATION_SAMPLES:
        paper_name = Path(paper).stem
        print(f"[{paper_name}]")

        # 跑 v2.42
        print("  v2.42 评分中...", end="", flush=True)
        scores_42 = await evaluate_single(
            paper,
            "configs/frameworks/law-v2.42-20260507.yaml"
        )
        print(" 完成")

        # 跑 v2.43
        print("  v2.43 评分中...", end="", flush=True)
        scores_43 = await evaluate_single(
            paper,
            "configs/frameworks/law-v2.43-20260508.yaml"
        )
        print(" 完成")

        # 比对
        print("  比对结果:")
        has_diff = False
        for dim_key in scores_42.keys():
            s42 = scores_42[dim_key]
            s43 = scores_43[dim_key]
            diff = abs(s43 - s42)

            if diff > 0:
                has_diff = True
                all_pass = False
                print(f"    {dim_key:30s} v2.42={s42:3d}  v2.43={s43:3d}  diff={diff:+3d}  ❌")
            else:
                print(f"    {dim_key:30s} v2.42={s42:3d}  v2.43={s43:3d}  diff= 0  ✓")

        if not has_diff:
            print("  ✅ 该论文六维分数完全一致")
        else:
            print("  ❌ 该论文存在分数偏移")
        print()

    print("=" * 80)
    if all_pass:
        print("✅ 回归测试通过：v2.43 与 v2.42 评分结果严格一致")
        return 0
    else:
        print("❌ 回归测试失败：v2.43 与 v2.42 存在分数偏移")
        print("   请检查 v2.43 是否意外修改了 prompt 或评分逻辑")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
