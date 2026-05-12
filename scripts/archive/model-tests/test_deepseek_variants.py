"""测试不同 DeepSeek 模型的评分表现

对比：
1. deepseek-chat (当前使用，可能路由到 reasoner)
2. deepseek-reasoner (显式推理模型)
3. deepseek-v4-flash (快速模型，无推理)

用法：
    python scripts/test_deepseek_variants.py \
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
from src.ingestion.preprocessor import process_file
from src.knowledge.loader import load_framework
from src.core.config import settings

import openai


class DeepSeekVariantProvider:
    """DeepSeek 变体 Provider"""

    def __init__(self, model_name: str):
        self.model_name = model_name
        self._client = openai.AsyncOpenAI(
            api_key=settings.deepseek_api_key,
            base_url="https://api.deepseek.com/v1"
        )

    async def generate_json_response(self, prompt: str) -> tuple[dict | None, str | None, float, dict]:
        """返回 (result, error, elapsed, metadata)"""
        start = time.time()
        metadata = {}

        try:
            response = await self._client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
            )

            elapsed = time.time() - start

            # 收集元数据
            metadata['model_returned'] = response.model
            metadata['usage'] = response.usage.model_dump() if response.usage else {}

            # 检查是否有推理内容
            if hasattr(response.choices[0].message, 'reasoning_content'):
                reasoning = response.choices[0].message.reasoning_content
                metadata['has_reasoning'] = True
                metadata['reasoning_length'] = len(reasoning) if reasoning else 0
            else:
                metadata['has_reasoning'] = False

            result = json.loads(response.choices[0].message.content)
            return result, None, elapsed, metadata

        except Exception as e:
            elapsed = time.time() - start
            return None, str(e), elapsed, metadata


async def test_deepseek_variants(paper_path: str, framework_path: str):
    """测试不同 DeepSeek 模型变体"""

    print(f"=== DeepSeek 模型变体对比测试 ===")
    print(f"论文: {paper_path}")
    print(f"框架: {framework_path}")
    print()

    # 加载框架和论文
    framework = load_framework(framework_path)
    paper = process_file(paper_path)

    # 测试的模型变体
    models = [
        ("deepseek-chat", "当前使用（可能路由到 reasoner）"),
        ("deepseek-reasoner", "显式推理模型"),
        ("deepseek-v4-flash", "快速模型（无推理）"),
    ]

    results = {}

    for model_name, description in models:
        print(f"\n{'='*80}")
        print(f"测试模型: {model_name}")
        print(f"说明: {description}")
        print(f"{'='*80}\n")

        provider = DeepSeekVariantProvider(model_name)
        model_results = {}

        for dimension in framework.dimensions:
            print(f"  评价维度: {dimension.name_zh}...", end=" ", flush=True)

            prompt = build_prompt(dimension, paper)
            result, error, elapsed, metadata = await provider.generate_json_response(prompt)

            if error:
                print(f"❌ 错误: {error}")
                model_results[dimension.key] = {
                    "error": error,
                    "elapsed": elapsed
                }
            elif result and isinstance(result, dict) and "score" in result:
                score = int(result["score"])

                # 显示推理信息
                reasoning_info = ""
                if metadata.get('has_reasoning'):
                    reasoning_info = f" [推理: {metadata['reasoning_length']}字]"

                print(f"✓ {score} 分 ({elapsed:.1f}s){reasoning_info}")

                model_results[dimension.key] = {
                    "score": score,
                    "raw": result,
                    "elapsed": elapsed,
                    "metadata": metadata
                }
            else:
                print(f"❌ 无效输出")
                model_results[dimension.key] = {
                    "error": "Invalid output",
                    "elapsed": elapsed
                }

        results[model_name] = model_results

    # 对比分析
    print(f"\n{'='*80}")
    print("对比分析")
    print(f"{'='*80}\n")

    # 提取分数
    scores_by_model = {}
    for model_name, model_results in results.items():
        scores = []
        for dim in framework.dimensions:
            if dim.key in model_results and "score" in model_results[dim.key]:
                scores.append(model_results[dim.key]["score"])
        scores_by_model[model_name] = scores

    # 打印对比表格
    print(f"{'维度':<15s}", end="")
    for model_name, _ in models:
        print(f"{model_name:<25s}", end="")
    print()
    print("-" * 100)

    for dimension in framework.dimensions:
        print(f"{dimension.name_zh:<15s}", end="")
        for model_name, _ in models:
            if dimension.key in results[model_name] and "score" in results[model_name][dimension.key]:
                score = results[model_name][dimension.key]["score"]
                has_reasoning = results[model_name][dimension.key].get("metadata", {}).get("has_reasoning", False)
                reasoning_mark = "🧠" if has_reasoning else "  "
                print(f"{score:>3d} {reasoning_mark:<20s}", end="")
            else:
                print(f"{'N/A':<25s}", end="")
        print()

    # 计算统计数据
    print(f"\n{'='*80}")
    print("统计数据")
    print(f"{'='*80}\n")

    print(f"{'模型':<25s} {'平均分':>10s} {'推理标记':>10s}")
    print("-" * 50)

    for model_name, _ in models:
        scores = scores_by_model.get(model_name, [])
        if scores:
            avg_score = statistics.mean(scores)
            has_reasoning = any(
                results[model_name][dim.key].get("metadata", {}).get("has_reasoning", False)
                for dim in framework.dimensions
                if dim.key in results[model_name] and "score" in results[model_name][dim.key]
            )
            reasoning_mark = "是" if has_reasoning else "否"
            print(f"{model_name:<25s} {avg_score:>10.1f} {reasoning_mark:>10s}")

    # 与 GLM/Qwen 对比
    print(f"\n{'='*80}")
    print("与 GLM-5.1/Qwen3.6-Plus 的差异")
    print(f"{'='*80}\n")

    # 从之前的测试结果中读取 GLM/Qwen 的分数
    reference_scores = {
        "problem_originality": 88,
        "literature_insight": 90,
        "analytical_framework": 90,  # 平均 GLM=88, Qwen=92
        "logical_coherence": 88,
        "conclusion_consensus": 88,
        "forward_extension": 50
    }

    print(f"{'维度':<15s} {'GLM/Qwen':>10s}", end="")
    for model_name, _ in models:
        print(f"{model_name:<25s}", end="")
    print()
    print("-" * 100)

    for dimension in framework.dimensions:
        ref_score = reference_scores.get(dimension.key, 0)
        print(f"{dimension.name_zh:<15s} {ref_score:>10d}", end="")

        for model_name, _ in models:
            if dimension.key in results[model_name] and "score" in results[model_name][dimension.key]:
                score = results[model_name][dimension.key]["score"]
                diff = score - ref_score
                print(f"{score:>3d} ({diff:+3d}){'':>15s}", end="")
            else:
                print(f"{'N/A':<25s}", end="")
        print()

    # 保存结果
    output_path = f"results/deepseek-variants-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump({
            "test_info": {
                "paper": paper_path,
                "framework": framework_path,
                "models": [m[0] for m in models],
                "timestamp": datetime.now().isoformat()
            },
            "results": results,
            "reference_scores": reference_scores
        }, f, ensure_ascii=False, indent=2)

    print(f"\n结果已保存到: {output_path}")


def main():
    parser = argparse.ArgumentParser(description="DeepSeek 模型变体对比测试")
    parser.add_argument("--paper", required=True, help="论文路径")
    parser.add_argument("--framework", required=True, help="框架配置路径")

    args = parser.parse_args()

    asyncio.run(test_deepseek_variants(args.paper, args.framework))


if __name__ == "__main__":
    main()
