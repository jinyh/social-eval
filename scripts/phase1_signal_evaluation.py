#!/usr/bin/env python3
"""为 Phase 1 100 篇论文补充自主知识体系信号评价（并发）"""

import asyncio
import json
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.evaluation.prompt_builder import build_signal_check_prompt
from src.evaluation.providers.factory import create_providers
from src.ingestion.preprocessor import process_file
from scripts.run_convergence_test import _load_framework_skip_validation, _call_provider

RESULTS_DIR = Path("results/phase1-100-papers")


async def evaluate_signal_single(
    index: int,
    total: int,
    paper_path: str,
    framework,
    providers,
    output_path: Path,
    semaphore: asyncio.Semaphore,
) -> dict | None:
    """评估单篇论文的自主知识信号"""
    paper_name = Path(paper_path).stem[:50]

    # 断点续传：如果结果文件已有 signal 字段则跳过
    if output_path.exists():
        data = json.load(open(output_path, "r", encoding="utf-8"))
        if data.get("autonomous_knowledge_signals"):
            print(f"[{index}/{total}] {paper_name} → 跳过（已有信号）")
            return data["autonomous_knowledge_signals"]

    async with semaphore:
        print(f"[{index}/{total}] {paper_name} → 评估自主信号...")
        try:
            paper = process_file(paper_path)
            prompt = build_signal_check_prompt(framework, paper)

            results = await asyncio.gather(
                *[_call_provider(p, prompt) for p in providers],
                return_exceptions=False,
            )

            signal_results = {}
            for (raw, error, elapsed), provider in zip(results, providers):
                if error:
                    signal_results[provider.model_name] = {"error": error}
                else:
                    signal_results[provider.model_name] = raw

            # 聚合信号分数
            scores = []
            for model_name, result in signal_results.items():
                if isinstance(result, dict) and "autonomous_signal_score" in result:
                    scores.append(result["autonomous_signal_score"])

            aggregated = {
                "per_model": signal_results,
                "avg_signal_score": round(sum(scores) / len(scores), 1) if scores else None,
                "signal_scores": scores,
            }

            # 写回原始结果文件
            if output_path.exists():
                data = json.load(open(output_path, "r", encoding="utf-8"))
            else:
                data = {}
            data["autonomous_knowledge_signals"] = aggregated
            output_path.write_text(
                json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
            )

            avg = aggregated["avg_signal_score"]
            print(f"[{index}/{total}] {paper_name} → signal_score={avg}")
            return aggregated

        except Exception as e:
            print(f"[{index}/{total}] {paper_name} → 失败: {e}")
            return None


async def main():
    import argparse
    parser = argparse.ArgumentParser(description="为 100 篇论文补充自主知识信号评价")
    parser.add_argument("--framework", default="configs/frameworks/law-v2.50.2-20260514.yaml")
    parser.add_argument("--models", default="qwen3.6-plus,glm-5.1")
    parser.add_argument("--results-dir", default="results/phase1-100-papers")
    parser.add_argument("--concurrency", type=int, default=5, help="论文级并发数（默认 5）")
    args = parser.parse_args()

    results_dir = Path(args.results_dir)
    framework = _load_framework_skip_validation(args.framework)
    model_names = args.models.split(",")
    providers = create_providers(model_names)

    # 加载 manifest 获取论文路径
    manifest_path = Path("raw/phase1-100-papers/manifest.json")
    if not manifest_path.exists():
        print("错误：样本清单不存在")
        return 1

    manifest = json.load(open(manifest_path, "r", encoding="utf-8"))
    samples = manifest["samples"]

    print("=" * 60)
    print("自主知识体系信号评价（100 篇）")
    print("=" * 60)
    print(f"框架: {args.framework}")
    print(f"模型: {args.models}")
    print(f"并发: {args.concurrency}")
    print("=" * 60 + "\n")

    start_time = time.time()
    semaphore = asyncio.Semaphore(args.concurrency)

    tasks = []
    for i, paper in enumerate(samples, 1):
        out_path = results_dir / f"paper-{i:03d}.json"
        tasks.append(
            evaluate_signal_single(
                i, len(samples), paper, framework, providers, out_path, semaphore
            )
        )

    results = await asyncio.gather(*tasks)

    elapsed = time.time() - start_time
    success_count = sum(1 for r in results if r is not None)

    print(f"\n完成: {success_count}/{len(samples)} 篇")
    print(f"耗时: {elapsed/60:.1f} 分钟")

    # 汇总信号分数
    all_signal_scores = []
    for r in results:
        if r and r.get("avg_signal_score") is not None:
            all_signal_scores.append(r["avg_signal_score"])

    if all_signal_scores:
        import statistics
        print(f"信号分数均值: {statistics.mean(all_signal_scores):.1f}/8")
        print(f"信号分数中位数: {statistics.median(all_signal_scores):.1f}/8")
        strong = sum(1 for s in all_signal_scores if s >= 7)
        medium = sum(1 for s in all_signal_scores if 4 <= s < 7)
        weak = sum(1 for s in all_signal_scores if 1 <= s < 4)
        absent = sum(1 for s in all_signal_scores if s < 1)
        print(f"强信号(7-8): {strong} 篇 | 中等(4-6): {medium} 篇 | 弱(1-3): {weak} 篇 | 无(0): {absent} 篇")

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
