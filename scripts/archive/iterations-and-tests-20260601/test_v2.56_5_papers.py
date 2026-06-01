#!/usr/bin/env python3
"""
测试 v2.56 框架：从 Phase 2 的 10 篇中选 5 篇重新评审（仅 Round 1）
对比 v2.55 的标准差变化
"""
import asyncio
import json
import sys
import statistics
from pathlib import Path
from datetime import datetime

# 确保项目根目录在 sys.path 中
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.evaluation.providers.factory import create_providers
from src.ingestion.preprocessor import process_file
from src.knowledge.loader import _normalize_framework_data
from src.knowledge.schemas import Framework
from src.reporting.scoring import calculate_weighted_total
import yaml

# 测试配置
FRAMEWORK_PATH = "configs/frameworks/law-v2.56-prompt-aligned.yaml"
PAPER_IDS = [8, 4, 1, 10, 6]  # 排除 paper 7
MODELS = ["deepseek-v4-pro", "glm-5.1", "kimi-k2.6", "qwen3.6-plus"]
OUTPUT_DIR = PROJECT_ROOT / "results" / "v2.56-test-5-papers"
PHASE2_DIR = PROJECT_ROOT / "results" / "phase2-test-10"

def load_framework(path: str) -> Framework:
    """加载框架配置"""
    with open(path, 'r', encoding='utf-8') as f:
        raw = yaml.safe_load(f)
    normalized = _normalize_framework_data(raw)
    return Framework(**normalized)

def _paper_content(paper) -> str:
    """提取论文正文"""
    return paper.body or paper.full_text

def aggregate_scores(scores: dict, strategy: str = "both") -> dict:
    """聚合多模型评分"""
    if not scores:
        return {"mean": 0.0, "std": 0.0, "model_scores": {}}

    values = list(scores.values())
    mean = statistics.mean(values)
    std = statistics.stdev(values) if len(values) > 1 else 0.0

    return {
        "mean": round(mean, 1),
        "std": round(std, 1),
        "model_scores": scores
    }

async def load_paper_data(paper_id: int):
    """从 Phase 2 结果中加载论文数据和路径"""
    # 从 phase2-test-10-papers.json 加载论文路径
    papers_list_file = PROJECT_ROOT / "results" / "phase2-test-10-papers.json"
    with open(papers_list_file, 'r', encoding='utf-8') as f:
        papers_data = json.load(f)

    # 找到对应的论文
    paper_info = None
    for p in papers_data['papers']:
        if p['id'] == paper_id:
            paper_info = p
            break

    if not paper_info:
        raise ValueError(f"Paper {paper_id} not found in phase2-test-10-papers.json")

    # 加载论文文件（路径相对于项目根目录）
    paper_path = paper_info['path']
    paper = process_file(paper_path)
    return paper

async def _call_provider(provider, prompt: str, semaphore):
    """调用单个 provider"""
    async with semaphore:
        try:
            start = asyncio.get_event_loop().time()
            raw = await provider.generate_json_response(prompt)
            elapsed = asyncio.get_event_loop().time() - start
            return (raw, None, elapsed)
        except Exception as e:
            return (None, str(e), 0.0)

def build_prompt(dimension, paper) -> str:
    """构建评估 prompt"""
    from src.evaluation.prompt_builder import build_prompt
    return build_prompt(dimension, paper)

async def evaluate_paper_all_models(paper_id: int, framework, providers, semaphore) -> dict:
    """并发评估单篇论文的所有模型（仅 Round 1）"""
    print(f"\n=== Paper {paper_id} ===")

    # 加载论文数据
    paper = await load_paper_data(paper_id)

    from src.evaluation.prompt_builder import build_prompt

    dimensions = framework.dimensions

    print(f"  Round 1: 评估 {len(dimensions)} 个维度...")

    # 并发评估所有维度
    async def evaluate_dimension(dim):
        prompt = build_prompt(dim, paper)

        # 并发调用所有模型
        results = await asyncio.gather(
            *[_call_provider(p, prompt, semaphore) for p in providers],
            return_exceptions=False,
        )

        scores = {}
        raw_outputs = {}
        errors = {}
        elapsed_times = {}

        for (raw, error, elapsed), provider in zip(results, providers):
            elapsed_times[provider.model_name] = elapsed
            if error:
                errors[provider.model_name] = error
                continue
            raw_outputs[provider.model_name] = raw
            if isinstance(raw, dict):
                score = raw.get("score")
                if score is not None:
                    scores[provider.model_name] = int(score)
            else:
                errors[provider.model_name] = f"Unexpected output type: {type(raw).__name__}"

        # 聚合分数
        aggregated = aggregate_scores(scores, "both")

        # 计算置信度
        std = aggregated.get("std", 0.0)
        if std <= 5.0:
            confidence = "high"
        elif std <= 8.0:
            confidence = "medium"
        elif std <= 12.0:
            confidence = "low"
        else:
            confidence = "critical"

        dim_result = {
            "dimension": dim.key,
            "name_zh": dim.name_zh,
            "confidence": confidence,
            "raw_outputs": raw_outputs,
            "errors": errors,
            "elapsed_times": elapsed_times,
        }
        dim_result.update(aggregated)

        return dim_result

    # 并发评估所有维度
    dim_results_list = await asyncio.gather(*[evaluate_dimension(dim) for dim in dimensions])

    dimension_results = {}
    for dim, dim_result in zip(dimensions, dim_results_list):
        dimension_results[dim.key] = dim_result

        # 打印日志
        scores_str = ", ".join(f"{k}={v}" for k, v in dim_result["model_scores"].items())
        print(f"    {dim.name_zh}: {scores_str} | mean={dim_result.get('mean')} | std={dim_result.get('std')}")

    return {
        "paper_id": paper_id,
        "dimension_results": dimension_results
    }


async def main():
    """主函数：并发评估 5 篇论文"""
    print(f"开始测试 v2.56：5 篇论文 x 4 模型")
    print(f"框架路径：{FRAMEWORK_PATH}")
    print(f"论文 ID：{PAPER_IDS}")
    print(f"模型：{MODELS}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # 加载框架
    print("\n加载框架...")
    framework = load_framework(FRAMEWORK_PATH)
    print(f"框架版本：{framework.metadata.version}")

    # 创建 providers
    providers = create_providers(MODELS)
    semaphore = asyncio.Semaphore(10)  # 并发限制

    # 并发评估所有论文
    print("\n开始评估...")
    all_results = await asyncio.gather(
        *[evaluate_paper_all_models(paper_id, framework, providers, semaphore) for paper_id in PAPER_IDS]
    )

    # 保存原始结果
    output_file = OUTPUT_DIR / f"raw_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)

    print(f"\n原始结果已保存：{output_file}")

    # 分析结果
    analyze_results(all_results)

def analyze_results(results: list):
    """分析评估结果"""
    print("\n" + "="*60)
    print("结果分析")
    print("="*60)

    # 计算每篇论文的标准差
    print("\n各论文标准差：")
    print(f"{'Paper ID':<10} {'模型数':<8} {'平均分':<10} {'最大 std':<10}")
    print("-" * 50)

    all_stds = []
    for paper_result in results:
        paper_id = paper_result['paper_id']
        dimension_results = paper_result['dimension_results']

        # 提取各维度的 std
        dim_stds = [dim_data['std'] for dim_data in dimension_results.values()]
        max_std = max(dim_stds) if dim_stds else 0
        all_stds.append(max_std)

        # 计算平均分（加权）
        dim_scores = {k: v['mean'] for k, v in dimension_results.items()}
        # 这里简化处理，不做加权
        avg_score = statistics.mean(dim_scores.values()) if dim_scores else 0

        model_count = len(MODELS)
        print(f"{paper_id:<10} {model_count:<8} {avg_score:<10.1f} {max_std:<10.1f}")

    # 总体统计
    if all_stds:
        avg_std = statistics.mean(all_stds)
        print("\n" + "="*60)
        print(f"平均最大标准差：{avg_std:.2f}")
        print(f"std > 8 的论文数：{sum(1 for s in all_stds if s > 8)}/{len(all_stds)}")
        print("="*60)

if __name__ == "__main__":
    asyncio.run(main())
