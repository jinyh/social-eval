"""测试 DashScope 上不同 DeepSeek 模型的评分表现

通过阿里云百炼平台测试 DeepSeek 模型变体

用法：
    python scripts/test_deepseek_dashscope.py \
        --paper raw/calibration-regression/司法公正与同理心正义_杜宴林.pdf \
        --framework configs/frameworks/law-v2.42-20260507.yaml
"""

import argparse
import asyncio
import json
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.evaluation.prompt_builder import build_prompt
from src.evaluation.providers.dashscope_provider import DashScopeProvider
from src.ingestion.preprocessor import process_file
from src.knowledge.loader import load_framework


async def evaluate_single_run(provider, dimension, paper) -> tuple[dict | None, str | None, float]:
    """单次评价"""
    prompt = build_prompt(dimension, paper)
    start = time.time()
    try:
        raw = await provider.generate_json_response(prompt)
        elapsed = time.time() - start
        return raw, None, elapsed
    except Exception as e:
        elapsed = time.time() - start
        return None, str(e), elapsed


async def test_deepseek_dashscope(paper_path: str, framework_path: str):
    """测试 DashScope 上的 DeepSeek 模型"""

    print(f"=== DashScope DeepSeek 模型对比测试 ===")
    print(f"论文: {paper_path}")
    print(f"框架: {framework_path}")
    print()

    # 加载框架和论文
    framework = load_framework(framework_path)
    paper = process_file(paper_path)

    # 测试的模型（DashScope 上可用的 DeepSeek 模型）
    # 注意：这些模型名称需要根据 DashScope 实际支持的模型调整
    models_to_test = [
        ("deepseek-v4-pro", "当前使用的模型"),
        ("deepseek-v4", "标准版本（如果存在）"),
        ("deepseek-chat", "对话版本（如果存在）"),
    ]

    results = {}
    successful_models = []

    for model_name, description in models_to_test:
        print(f"\n{'='*80}")
        print(f"测试模型: {model_name}")
        print(f"说明: {description}")
        print(f"{'='*80}\n")

        try:
            provider = DashScopeProvider(model_name)
            model_results = {}
            all_success = True

            for dimension in framework.dimensions:
                print(f"  评价维度: {dimension.name_zh}...", end=" ", flush=True)

                raw, error, elapsed = await evaluate_single_run(provider, dimension, paper)

                if error:
                    print(f"❌ 错误: {error}")
                    model_results[dimension.key] = {
                        "error": error,
                        "elapsed": elapsed
                    }
                    all_success = False
                elif raw and isinstance(raw, dict) and "score" in raw:
                    score = int(raw["score"])
                    print(f"✓ {score} 分 ({elapsed:.1f}s)")
                    model_results[dimension.key] = {
                        "score": score,
                        "raw": raw,
                        "elapsed": elapsed
                    }
                else:
                    print(f"❌ 无效输出")
                    model_results[dimension.key] = {
                        "error": "Invalid output",
                        "elapsed": elapsed
                    }
                    all_success = False

            results[model_name] = model_results
            if all_success:
                successful_models.append((model_name, description))

        except Exception as e:
            print(f"  ❌ 模型初始化失败: {e}")
            print(f"  提示: 模型 {model_name} 可能在 DashScope 上不可用")

    # 如果没有成功的模型，提前退出
    if not successful_models:
        print("\n❌ 所有模型测试失败，无法生成对比分析")
        return

    # 对比分析
    print(f"\n{'='*80}")
    print("对比分析")
    print(f"{'='*80}\n")

    # 提取分数
    scores_by_model = {}
    for model_name, _ in successful_models:
        scores = []
        for dim in framework.dimensions:
            if dim.key in results[model_name] and "score" in results[model_name][dim.key]:
                scores.append(results[model_name][dim.key]["score"])
        scores_by_model[model_name] = scores

    # 打印对比表格
    print(f"{'维度':<15s}", end="")
    for model_name, _ in successful_models:
        print(f"{model_name:<20s}", end="")
    print()
    print("-" * (15 + 20 * len(successful_models)))

    for dimension in framework.dimensions:
        print(f"{dimension.name_zh:<15s}", end="")
        for model_name, _ in successful_models:
            if dimension.key in results[model_name] and "score" in results[model_name][dimension.key]:
                score = results[model_name][dimension.key]["score"]
                print(f"{score:>3d}{'':>17s}", end="")
            else:
                print(f"{'N/A':<20s}", end="")
        print()

    # 计算统计数据
    print(f"\n{'='*80}")
    print("统计数据")
    print(f"{'='*80}\n")

    print(f"{'模型':<20s} {'平均分':>10s} {'最低分':>10s} {'最高分':>10s}")
    print("-" * 50)

    for model_name, _ in successful_models:
        scores = scores_by_model.get(model_name, [])
        if scores:
            avg_score = statistics.mean(scores)
            min_score = min(scores)
            max_score = max(scores)
            print(f"{model_name:<20s} {avg_score:>10.1f} {min_score:>10d} {max_score:>10d}")

    # 与 GLM/Qwen 对比
    print(f"\n{'='*80}")
    print("与 GLM-5.1/Qwen3.6-Plus 的差异")
    print(f"{'='*80}\n")

    # 从之前的测试结果中读取 GLM/Qwen 的分数
    reference_scores = {
        "problem_originality": 88,
        "literature_insight": 90,
        "analytical_framework": 90,
        "logical_coherence": 88,
        "conclusion_consensus": 88,
        "forward_extension": 50
    }

    print(f"{'维度':<15s} {'GLM/Qwen':>10s}", end="")
    for model_name, _ in successful_models:
        print(f"{model_name:<20s}", end="")
    print()
    print("-" * (25 + 20 * len(successful_models)))

    for dimension in framework.dimensions:
        ref_score = reference_scores.get(dimension.key, 0)
        print(f"{dimension.name_zh:<15s} {ref_score:>10d}", end="")

        for model_name, _ in successful_models:
            if dimension.key in results[model_name] and "score" in results[model_name][dimension.key]:
                score = results[model_name][dimension.key]["score"]
                diff = score - ref_score
                print(f"{score:>3d} ({diff:+3d}){'':>10s}", end="")
            else:
                print(f"{'N/A':<20s}", end="")
        print()

    # 计算整体差异
    print(f"\n{'='*80}")
    print("整体差异统计")
    print(f"{'='*80}\n")

    print(f"{'模型':<20s} {'平均差异':>12s} {'最大负差':>12s}")
    print("-" * 50)

    for model_name, _ in successful_models:
        diffs = []
        for dimension in framework.dimensions:
            ref_score = reference_scores.get(dimension.key, 0)
            if dimension.key in results[model_name] and "score" in results[model_name][dimension.key]:
                score = results[model_name][dimension.key]["score"]
                diffs.append(score - ref_score)

        if diffs:
            avg_diff = statistics.mean(diffs)
            max_neg_diff = min(diffs)
            print(f"{model_name:<20s} {avg_diff:>12.1f} {max_neg_diff:>12d}")

    # 保存结果
    output_path = f"results/deepseek-dashscope-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump({
            "test_info": {
                "paper": paper_path,
                "framework": framework_path,
                "models": [m[0] for m in successful_models],
                "timestamp": datetime.now().isoformat()
            },
            "results": results,
            "reference_scores": reference_scores
        }, f, ensure_ascii=False, indent=2)

    print(f"\n结果已保存到: {output_path}")


def main():
    parser = argparse.ArgumentParser(description="DashScope DeepSeek 模型对比测试")
    parser.add_argument("--paper", required=True, help="论文路径")
    parser.add_argument("--framework", required=True, help="框架配置路径")

    args = parser.parse_args()

    asyncio.run(test_deepseek_dashscope(args.paper, args.framework))


if __name__ == "__main__":
    main()
