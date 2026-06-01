#!/usr/bin/env python3
"""模型稳定性测试：4 个国产模型 × 10 篇论文 × 3 次重复

测试目标：
- 评估同一模型对同一论文多次评分的一致性（intra-model std）
- 对比 4 个国产模型的稳定性差异
- 为生产环境模型选择提供数据支撑

模型：DeepSeek V4 Pro, GLM 5.1, Qwen 3.6 Plus, Kimi K2.6
框架：v2.50.2（生产推荐）
样本：从 phase1-100-papers 随机选 10 篇

执行策略（规避缓存）：
- 交错执行：先对所有论文做第 1 轮，再做第 2 轮，最后第 3 轮
- 目的：拉长同一论文的评估间隔（目标 ≥ 5 分钟），规避 API prompt cache
- 验证：记录每次评估的时间戳，计算实际间隔
"""

import asyncio
import json
import random
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.evaluation.prompt_builder import build_prompt, build_precheck_prompt
from src.evaluation.providers.factory import create_providers
from src.ingestion.preprocessor import process_file
from src.knowledge.loader import _normalize_framework_data, DEFAULT_STD_THRESHOLD
from src.knowledge.schemas import Framework
from src.reporting.scoring import calculate_weighted_total

import yaml

# ============================================================
# 配置
# ============================================================

FRAMEWORK_PATH = "configs/frameworks/law-v2.50.2-20260514.yaml"
MODELS = ["deepseek-v4-pro", "glm-5.1", "qwen3.6-plus", "kimi-k2.6"]
REPEAT_COUNT = 3
SAMPLE_COUNT = 10
RANDOM_SEED = 42
CONCURRENCY_LIMIT = 3  # 全局同时评估的论文数（跨模型共享）

PAPER_DIR = Path("raw/phase1-100-papers")


# ============================================================
# 核心逻辑
# ============================================================


def load_framework(path: str) -> Framework:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if "std_threshold" not in data:
        data["std_threshold"] = DEFAULT_STD_THRESHOLD
    normalized = _normalize_framework_data(data)
    return Framework(**normalized)


def select_papers(n: int, seed: int) -> list[Path]:
    """从 phase1-100-papers 随机选 n 篇"""
    all_papers = sorted(PAPER_DIR.glob("*.pdf"))
    rng = random.Random(seed)
    selected = rng.sample(all_papers, min(n, len(all_papers)))
    return selected


async def evaluate_paper_single_run(
    provider, framework: Framework, paper, run_id: int
) -> dict:
    """单次评估一篇论文的所有维度，返回各维度得分"""
    dimension_scores = {}
    errors = {}

    semaphore = asyncio.Semaphore(4)

    async def eval_dim(dim):
        async with semaphore:
            prompt = build_prompt(dim, paper)
            start = time.time()
            try:
                raw = await provider.generate_json_response(prompt)
                elapsed = time.time() - start
                if isinstance(raw, dict) and raw.get("score") is not None:
                    return dim.key, int(raw["score"]), elapsed, None
                else:
                    return dim.key, None, elapsed, f"无效输出: {type(raw).__name__}"
            except Exception as e:
                elapsed = time.time() - start
                return dim.key, None, elapsed, str(e)

    tasks = [eval_dim(dim) for dim in framework.dimensions]
    results = await asyncio.gather(*tasks)

    total_elapsed = 0.0
    for key, score, elapsed, error in results:
        total_elapsed += elapsed
        if error:
            errors[key] = error
        elif score is not None:
            dimension_scores[key] = score

    # 计算 final_score
    scoring_protocol = framework.raw_config.get("scoring_protocol")
    final_score = None
    if dimension_scores:
        final_score = calculate_weighted_total(
            dimension_scores={k: float(v) for k, v in dimension_scores.items()},
            scoring_protocol=scoring_protocol,
        )

    return {
        "run_id": run_id,
        "dimension_scores": dimension_scores,
        "final_score": final_score,
        "errors": errors,
        "elapsed_seconds": round(total_elapsed, 1),
    }


async def evaluate_model_paper_single_run(
    model_name: str, framework: Framework, paper_path: Path, run_id: int
) -> dict:
    """对一篇论文用指定模型执行单次评估"""
    paper = process_file(str(paper_path))
    provider = create_providers([model_name])[0]

    result = await evaluate_paper_single_run(provider, framework, paper, run_id)
    result["timestamp"] = datetime.now().isoformat()
    result["model"] = model_name
    result["paper"] = paper_path.name

    return result


def aggregate_runs(model_name: str, paper_name: str, runs: list[dict]) -> dict:
    """聚合同一模型对同一论文的多次评估结果"""
    # 计算 final_score 的 std
    final_scores = [r["final_score"] for r in runs if r["final_score"] is not None]
    final_mean = statistics.mean(final_scores) if final_scores else None
    final_std = statistics.stdev(final_scores) if len(final_scores) > 1 else 0.0

    # 各维度的 std
    dim_stds = {}
    all_dim_keys = set()
    for r in runs:
        all_dim_keys.update(r["dimension_scores"].keys())

    for key in sorted(all_dim_keys):
        scores = [r["dimension_scores"][key] for r in runs if key in r["dimension_scores"]]
        if len(scores) > 1:
            dim_stds[key] = round(statistics.stdev(scores), 1)
        elif len(scores) == 1:
            dim_stds[key] = 0.0

    # 计算时间间隔（验证缓存规避）
    timestamps = [datetime.fromisoformat(r["timestamp"]) for r in runs]
    if len(timestamps) > 1:
        intervals = [(timestamps[i+1] - timestamps[i]).total_seconds() / 60
                     for i in range(len(timestamps) - 1)]
        min_interval = round(min(intervals), 1)
        avg_interval = round(statistics.mean(intervals), 1)
    else:
        min_interval = avg_interval = None

    return {
        "model": model_name,
        "paper": paper_name,
        "runs": runs,
        "final_scores": final_scores,
        "final_mean": round(final_mean, 1) if final_mean else None,
        "final_std": round(final_std, 1),
        "dimension_stds": dim_stds,
        "avg_dim_std": round(statistics.mean(dim_stds.values()), 1) if dim_stds else None,
        "min_interval_minutes": min_interval,
        "avg_interval_minutes": avg_interval,
    }


async def run_stability_test():
    """主测试流程（交错执行以规避缓存）"""
    print("=" * 70)
    print("模型稳定性测试（交错执行模式）")
    print(f"框架: {FRAMEWORK_PATH}")
    print(f"模型: {', '.join(MODELS)}")
    print(f"样本: {SAMPLE_COUNT} 篇（随机种子 {RANDOM_SEED}）")
    print(f"重复: {REPEAT_COUNT} 次/模型/论文")
    print(f"总调用: {len(MODELS)} × {SAMPLE_COUNT} × {REPEAT_COUNT} × 6维 = {len(MODELS) * SAMPLE_COUNT * REPEAT_COUNT * 6} 次")
    print("=" * 70)
    print("\n⚠️  执行策略：先对所有论文做第 1 轮，再做第 2 轮，最后第 3 轮")
    print("   目的：拉长同一论文的评估间隔，规避 API prompt cache")
    print("=" * 70)

    framework = load_framework(FRAMEWORK_PATH)
    papers = select_papers(SAMPLE_COUNT, RANDOM_SEED)

    print(f"\n选中论文:")
    for i, p in enumerate(papers, 1):
        print(f"  {i:2d}. {p.name}")

    start_time = datetime.now()

    # 存储所有原始评估结果：key = (model, paper), value = [run1, run2, run3]
    raw_runs = {(model, paper.name): [] for model in MODELS for paper in papers}

    semaphore = asyncio.Semaphore(CONCURRENCY_LIMIT)

    # 交错执行：先所有论文的第 1 轮，再第 2 轮，最后第 3 轮
    for run_id in range(1, REPEAT_COUNT + 1):
        print(f"\n{'='*70}")
        print(f"开始第 {run_id}/{REPEAT_COUNT} 轮评估")
        print(f"{'='*70}")

        tasks = []
        for model_name in MODELS:
            for paper_path in papers:
                async def eval_task(m=model_name, p=paper_path, rid=run_id):
                    async with semaphore:
                        print(f"  [{m}] {p.name[:40]}... (轮次 {rid})")
                        result = await evaluate_model_paper_single_run(m, framework, p, rid)
                        raw_runs[(m, p.name)].append(result)
                        if result["final_score"] is not None:
                            print(f"    [{m}] → {result['final_score']}")
                        return result
                tasks.append(eval_task())

        await asyncio.gather(*tasks)

        # 轮次间短暂休息（可选，进一步降低缓存风险）
        if run_id < REPEAT_COUNT:
            print(f"\n⏸️  轮次 {run_id} 完成，休息 10 秒后开始下一轮...")
            await asyncio.sleep(10)

    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()

    # 聚合结果
    print(f"\n{'='*70}")
    print("聚合评估结果...")
    print(f"{'='*70}")

    all_results = []
    for model_name in MODELS:
        for paper_path in papers:
            runs = raw_runs[(model_name, paper_path.name)]
            if runs:
                aggregated = aggregate_runs(model_name, paper_path.name, runs)
                all_results.append(aggregated)

                # 打印时间间隔验证
                if aggregated["min_interval_minutes"]:
                    interval_status = "✅" if aggregated["min_interval_minutes"] >= 5 else "⚠️"
                    print(f"  {interval_status} [{model_name}] {paper_path.name[:30]}: "
                          f"std={aggregated['final_std']}, "
                          f"间隔={aggregated['min_interval_minutes']}-{aggregated['avg_interval_minutes']}分钟")

    # ============================================================
    # 汇总分析
    # ============================================================
    print("\n" + "=" * 70)
    print("稳定性分析汇总")
    print("=" * 70)

    # 按模型汇总
    model_summary = {}
    for model_name in MODELS:
        model_data = [r for r in all_results if r["model"] == model_name]
        final_stds = [r["final_std"] for r in model_data if r["final_std"] is not None]
        avg_dim_stds = [r["avg_dim_std"] for r in model_data if r["avg_dim_std"] is not None]

        # 缓存规避验证
        min_intervals = [r["min_interval_minutes"] for r in model_data if r["min_interval_minutes"] is not None]
        avg_intervals = [r["avg_interval_minutes"] for r in model_data if r["avg_interval_minutes"] is not None]

        summary = {
            "papers_tested": len(model_data),
            "avg_final_std": round(statistics.mean(final_stds), 2) if final_stds else None,
            "max_final_std": round(max(final_stds), 1) if final_stds else None,
            "avg_dim_std": round(statistics.mean(avg_dim_stds), 2) if avg_dim_stds else None,
            "stable_papers": sum(1 for s in final_stds if s <= 3.0),
            "unstable_papers": sum(1 for s in final_stds if s > 5.0),
            "min_interval_minutes": round(min(min_intervals), 1) if min_intervals else None,
            "avg_interval_minutes": round(statistics.mean(avg_intervals), 1) if avg_intervals else None,
            "cache_safe_papers": sum(1 for i in min_intervals if i >= 5.0),
        }
        model_summary[model_name] = summary

        print(f"\n{model_name}:")
        print(f"  final_score std 均值: {summary['avg_final_std']}")
        print(f"  final_score std 最大: {summary['max_final_std']}")
        print(f"  维度 std 均值: {summary['avg_dim_std']}")
        print(f"  稳定论文 (std≤3): {summary['stable_papers']}/{len(model_data)}")
        print(f"  不稳定论文 (std>5): {summary['unstable_papers']}/{len(model_data)}")
        print(f"  最小评估间隔: {summary['min_interval_minutes']} 分钟")
        print(f"  平均评估间隔: {summary['avg_interval_minutes']} 分钟")
        print(f"  缓存安全论文 (间隔≥5分钟): {summary['cache_safe_papers']}/{len(model_data)}")

    # 排名
    print("\n--- 稳定性排名（按 avg_final_std 升序）---")
    ranked = sorted(model_summary.items(), key=lambda x: x[1]["avg_final_std"] or 999)
    for i, (name, s) in enumerate(ranked, 1):
        print(f"  {i}. {name}: avg_std={s['avg_final_std']}")

    print(f"\n总耗时: {duration:.0f} 秒 ({duration/60:.1f} 分钟)")

    # 缓存规避验证总结
    total_cache_safe = sum(s["cache_safe_papers"] for s in model_summary.values())
    total_papers = len(MODELS) * SAMPLE_COUNT
    cache_safe_rate = (total_cache_safe / total_papers * 100) if total_papers > 0 else 0
    print(f"\n✅ 缓存规避验证: {total_cache_safe}/{total_papers} 篇论文的评估间隔 ≥ 5 分钟 ({cache_safe_rate:.1f}%)")

    if cache_safe_rate < 80:
        print(f"⚠️  警告：缓存规避率低于 80%，部分结果可能受 prompt cache 影响")

    # 保存结果
    output_dir = Path("results/model-stability-test")
    output_dir.mkdir(parents=True, exist_ok=True)

    output = {
        "test_time": start_time.isoformat(),
        "duration_seconds": round(duration, 1),
        "execution_mode": "interleaved",  # 标记执行模式
        "cache_mitigation": {
            "strategy": "interleaved_rounds",
            "description": "先对所有论文做第 1 轮，再做第 2 轮，最后第 3 轮，拉长同一论文的评估间隔",
            "target_interval_minutes": 5.0,
            "inter_round_delay_seconds": 10,
        },
        "config": {
            "framework": FRAMEWORK_PATH,
            "models": MODELS,
            "repeat_count": REPEAT_COUNT,
            "sample_count": SAMPLE_COUNT,
            "random_seed": RANDOM_SEED,
        },
        "papers": [p.name for p in papers],
        "model_summary": model_summary,
        "detailed_results": all_results,
    }

    output_path = output_dir / f"stability-interleaved-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\n结果已保存: {output_path}")
    print(f"执行模式: interleaved（交错执行，规避缓存）")
    print(f"对比基线: 查找文件名包含 'stability-2026' 但不含 'interleaved' 的结果文件")

    return output


if __name__ == "__main__":
    asyncio.run(run_stability_test())
