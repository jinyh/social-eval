#!/usr/bin/env python3
"""Phase 2: 1849 篇论文两轮评审（分批执行）

自动执行 Round 1 → Round 2 流程，支持分批执行和断点续传。

用法：
    # 执行第 1 批（300 篇）
    python scripts/phase2_batch_two_rounds.py \\
        --framework configs/frameworks/law-v2.55-cross-review.yaml \\
        --paper-list results/phase2-paper-list.json \\
        --batch-size 300 \\
        --start-batch 1 \\
        --end-batch 1 \\
        --output-dir results/phase2-1849-papers \\
        --concurrency 5

    # 执行所有批次
    python scripts/phase2_batch_two_rounds.py \\
        --framework configs/frameworks/law-v2.55-cross-review.yaml \\
        --paper-list results/phase2-paper-list.json \\
        --batch-size 300 \\
        --start-batch 1 \\
        --end-batch 7 \\
        --output-dir results/phase2-1849-papers \\
        --concurrency 5
"""

import argparse
import asyncio
import json
import logging
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List

# 确保项目根目录在 sys.path 中
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.run_convergence_test import run_convergence_test
from scripts.run_cross_review import (
    build_cross_review_prompt,
    A_GROUP,
    B_GROUP,
    _paper_content,
    _reference_content
)
from src.evaluation.providers.factory import create_providers
from src.ingestion.preprocessor import process_file
from src.knowledge.loader import load_framework


# 配置日志
def setup_logging(output_dir: Path):
    """配置日志"""
    log_file = output_dir / "execution.log"
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger(__name__)


async def run_round1_single_paper(
    paper_id: int,
    paper_path: str,
    framework_path: str,
    models: List[str],
    output_path: Path,
    semaphore: asyncio.Semaphore,
    logger: logging.Logger
) -> dict | None:
    """执行单篇论文的 Round 1 评审"""
    paper_name = Path(paper_path).stem[:50]

    # 断点续传：跳过已完成的
    if output_path.exists():
        logger.info(f"[Round 1] Paper {paper_id}: {paper_name} → 跳过（已完成）")
        with open(output_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    async with semaphore:
        logger.info(f"[Round 1] Paper {paper_id}: {paper_name} → 开始评估...")
        try:
            result = await run_convergence_test(
                framework_path=framework_path,
                paper_path=paper_path,
                model_names=models,
                aggregation_mode="both",
            )

            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(
                json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
            )

            overall = result.get("overall", {})
            score_mean = overall.get("aggregation_mean", {}).get("final_score")
            score_strictest = overall.get("aggregation_strictest", {}).get("final_score")
            max_std = overall.get("max_std", "?")

            logger.info(
                f"[Round 1] Paper {paper_id}: {paper_name} → "
                f"mean={score_mean}, strictest={score_strictest}, max_std={max_std}"
            )

            return result

        except Exception as e:
            logger.error(f"[Round 1] Paper {paper_id}: {paper_name} → 失败: {e}")
            return None


async def run_round2_single_paper(
    paper_id: int,
    paper_path: str,
    round1_result: dict,
    framework: Framework,
    providers: dict,
    output_path: Path,
    semaphore: asyncio.Semaphore,
    logger: logging.Logger
) -> dict | None:
    """执行单篇论文的 Round 2 交叉评审"""
    paper_name = Path(paper_path).stem[:50]

    # 断点续传：跳过已完成的
    if output_path.exists():
        logger.info(f"[Round 2] Paper {paper_id}: {paper_name} → 跳过（已完成）")
        with open(output_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    async with semaphore:
        logger.info(f"[Round 2] Paper {paper_id}: {paper_name} → 开始交叉评审...")
        try:
            # 加载论文
            paper = process_file(paper_path)

            # 提取 Round 1 的各模型评分
            dimensions_data = round1_result.get("dimensions", {})

            # 构建 Round 2 结果
            round2_result = {
                "paper": paper_path,
                "dimensions": {},
                "overall": {}
            }

            # 对每个维度执行交叉评审
            for dim_key, dim_data in dimensions_data.items():
                if dim_key == "autonomous_knowledge_signals":
                    continue

                dim_config = next(
                    (d for d in framework.dimensions if d.key == dim_key), None
                )
                if not dim_config:
                    continue

                # 提取各模型的 Round 1 评分
                raw_outputs = dim_data.get("raw_outputs", {})

                # A 组和 B 组的交叉评审
                round2_scores = {}

                for model_name in A_GROUP + B_GROUP:
                    if model_name not in raw_outputs:
                        continue

                    self_output = raw_outputs[model_name]

                    # 确定对方组
                    if model_name in A_GROUP:
                        other_group = B_GROUP
                    else:
                        other_group = A_GROUP

                    # 获取对方组的评价
                    other_outputs = [
                        raw_outputs[m] for m in other_group if m in raw_outputs
                    ]

                    if not other_outputs:
                        continue

                    # 构建交叉评审 prompt
                    prompt = build_cross_review_prompt(
                        dimension_name=dim_config.name_zh,
                        dimension_key=dim_key,
                        self_output=self_output,
                        other_group_outputs=other_outputs,
                        paper=paper
                    )

                    # 调用模型
                    provider = providers.get(model_name)
                    if not provider:
                        continue

                    try:
                        response_dict = await provider.generate_json_response(prompt)
                        revised_score = response_dict.get("revised_score")

                        if revised_score is not None:
                            round2_scores[model_name] = revised_score

                    except Exception as e:
                        logger.warning(
                            f"[Round 2] Paper {paper_id}, Dim {dim_key}, Model {model_name} → 失败: {e}"
                        )

                # 计算 Round 2 统计
                if round2_scores:
                    round2_mean = statistics.mean(round2_scores.values())
                    round2_std = statistics.stdev(round2_scores.values()) if len(round2_scores) > 1 else 0

                    round2_result["dimensions"][dim_key] = {
                        "round1_scores": {k: v.get("score") for k, v in raw_outputs.items()},
                        "round2_scores": round2_scores,
                        "round1_mean": dim_data.get("mean"),
                        "round2_mean": round2_mean,
                        "round1_std": dim_data.get("std"),
                        "round2_std": round2_std,
                        "convergence_improvement": dim_data.get("std", 0) - round2_std
                    }

            # 计算总分
            if round2_result["dimensions"]:
                all_round2_means = [
                    d["round2_mean"] for d in round2_result["dimensions"].values()
                ]
                round2_result["overall"]["round2_final_score_mean"] = statistics.mean(all_round2_means)

            # 保存结果
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(
                json.dumps(round2_result, indent=2, ensure_ascii=False), encoding="utf-8"
            )

            final_score = round2_result["overall"].get("round2_final_score_mean", 0)
            logger.info(f"[Round 2] Paper {paper_id}: {paper_name} → final_score={final_score:.2f}")

            return round2_result

        except Exception as e:
            import traceback
            logger.error(f"[Round 2] Paper {paper_id}: {paper_name} → 失败: {e}")
            logger.error(f"详细错误:\n{traceback.format_exc()}")
            return None


async def process_batch(
    batch_num: int,
    papers: List[dict],
    framework_path: str,
    models: List[str],
    output_dir: Path,
    concurrency: int,
    logger: logging.Logger
):
    """处理一个批次的论文"""
    batch_dir = output_dir / f"batch-{batch_num}"
    round1_dir = batch_dir / "round1"
    round2_dir = batch_dir / "round2"

    round1_dir.mkdir(parents=True, exist_ok=True)
    round2_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"\n{'='*80}")
    logger.info(f"开始处理批次 {batch_num}：{len(papers)} 篇论文")
    logger.info(f"{'='*80}\n")

    start_time = time.time()
    semaphore = asyncio.Semaphore(concurrency)

    # Round 1: 并发评审
    logger.info(f"[批次 {batch_num}] Round 1 开始...")
    round1_tasks = []
    for paper in papers:
        paper_id = paper["id"]
        paper_path = paper["path"]
        output_path = round1_dir / f"paper-{paper_id}.json"

        task = run_round1_single_paper(
            paper_id, paper_path, framework_path, models,
            output_path, semaphore, logger
        )
        round1_tasks.append(task)

    round1_results = await asyncio.gather(*round1_tasks)
    round1_success = sum(1 for r in round1_results if r is not None)
    logger.info(f"[批次 {batch_num}] Round 1 完成：{round1_success}/{len(papers)} 篇成功\n")

    # Round 2: 交叉评审
    logger.info(f"[批次 {batch_num}] Round 2 开始...")

    # 加载框架和 providers
    framework = load_framework(framework_path)

    providers_list = create_providers(models)
    providers = {p.model_name: p for p in providers_list}

    round2_tasks = []
    for i, paper in enumerate(papers):
        if round1_results[i] is None:
            continue

        paper_id = paper["id"]
        paper_path = paper["path"]
        output_path = round2_dir / f"paper-{paper_id}.json"

        task = run_round2_single_paper(
            paper_id, paper_path, round1_results[i], framework,
            providers, output_path, semaphore, logger
        )
        round2_tasks.append(task)

    round2_results = await asyncio.gather(*round2_tasks)
    round2_success = sum(1 for r in round2_results if r is not None)
    logger.info(f"[批次 {batch_num}] Round 2 完成：{round2_success}/{len(papers)} 篇成功\n")

    # 生成批次报告
    elapsed = time.time() - start_time
    elapsed_str = f"{int(elapsed // 3600)}h {int((elapsed % 3600) // 60)}m"

    # 统计 Round 1
    round1_scores_mean = []
    round1_scores_strictest = []
    round1_max_stds = []

    for result in round1_results:
        if result:
            overall = result.get("overall", {})
            if "aggregation_mean" in overall:
                score = overall["aggregation_mean"].get("final_score")
                if score:
                    round1_scores_mean.append(score)
            if "aggregation_strictest" in overall:
                score = overall["aggregation_strictest"].get("final_score")
                if score:
                    round1_scores_strictest.append(score)
            max_std = overall.get("max_std")
            if max_std:
                round1_max_stds.append(max_std)

    # 统计 Round 2
    round2_scores = []
    for result in round2_results:
        if result:
            score = result.get("overall", {}).get("round2_final_score_mean")
            if score:
                round2_scores.append(score)

    batch_report = {
        "batch": batch_num,
        "papers": len(papers),
        "completed": round2_success,
        "failed": len(papers) - round2_success,
        "round1": {
            "avg_score_mean": round(statistics.mean(round1_scores_mean), 2) if round1_scores_mean else None,
            "avg_score_strictest": round(statistics.mean(round1_scores_strictest), 2) if round1_scores_strictest else None,
            "avg_max_std": round(statistics.mean(round1_max_stds), 2) if round1_max_stds else None,
            "std_over_8_count": sum(1 for s in round1_max_stds if s > 8)
        },
        "round2": {
            "avg_score": round(statistics.mean(round2_scores), 2) if round2_scores else None,
        },
        "elapsed_time": elapsed_str,
        "timestamp": datetime.now().isoformat()
    }

    report_path = batch_dir / "batch-report.json"
    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump(batch_report, f, indent=2, ensure_ascii=False)

    logger.info(f"\n{'='*80}")
    logger.info(f"批次 {batch_num} 完成")
    logger.info(f"  完成: {round2_success}/{len(papers)} 篇")
    logger.info(f"  Round 1 平均分: {batch_report['round1']['avg_score_mean']}")
    logger.info(f"  Round 2 平均分: {batch_report['round2']['avg_score']}")
    logger.info(f"  耗时: {elapsed_str}")
    logger.info(f"{'='*80}\n")

    return batch_report


async def main():
    parser = argparse.ArgumentParser(description="Phase 2: 1849 篇论文两轮评审")
    parser.add_argument("--framework", required=True, help="框架配置文件路径")
    parser.add_argument("--paper-list", required=True, help="论文列表 JSON 文件")
    parser.add_argument("--batch-size", type=int, default=300, help="每批论文数量")
    parser.add_argument("--start-batch", type=int, default=1, help="起始批次")
    parser.add_argument("--end-batch", type=int, default=7, help="结束批次")
    parser.add_argument("--output-dir", required=True, help="输出目录")
    parser.add_argument("--concurrency", type=int, default=5, help="并发数")

    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    logger = setup_logging(output_dir)

    # 加载论文列表
    with open(args.paper_list, 'r', encoding='utf-8') as f:
        paper_data = json.load(f)

    all_papers = paper_data["papers"]
    total_papers = len(all_papers)

    logger.info(f"加载论文列表：{total_papers} 篇")
    logger.info(f"批次大小：{args.batch_size}")
    logger.info(f"执行批次：{args.start_batch} - {args.end_batch}")
    logger.info(f"并发数：{args.concurrency}\n")

    # 模型配置
    models = ['deepseek-v4-pro', 'glm-5.1', 'kimi-k2.6', 'qwen3.6-plus']

    # 分批处理
    batch_reports = []
    for batch_num in range(args.start_batch, args.end_batch + 1):
        start_idx = (batch_num - 1) * args.batch_size
        end_idx = min(start_idx + args.batch_size, total_papers)

        if start_idx >= total_papers:
            break

        batch_papers = all_papers[start_idx:end_idx]

        report = await process_batch(
            batch_num, batch_papers, args.framework, models,
            output_dir, args.concurrency, logger
        )
        batch_reports.append(report)

    # 保存总进度
    progress = {
        "total_papers": total_papers,
        "completed_batches": len(batch_reports),
        "batch_reports": batch_reports,
        "timestamp": datetime.now().isoformat()
    }

    progress_path = output_dir / "progress.json"
    with open(progress_path, 'w', encoding='utf-8') as f:
        json.dump(progress, f, indent=2, ensure_ascii=False)

    logger.info(f"\n所有批次完成！进度已保存到: {progress_path}")


if __name__ == "__main__":
    asyncio.run(main())
