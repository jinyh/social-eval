#!/usr/bin/env python3
"""交大法学六维度两轮评审（R1 + R2 交叉评审）

对 raw/jiaodafaxue/ 下的 .md 论文执行完整两轮评审：
- Round 1：4 模型并发 × 6 维度，复用 run_convergence_test()
- Round 2：交叉评审（A/B 组互评），复用 evaluate_dimension_cross_review()

支持断点续传、分批执行、内容审查容错。

用法：
    # 全量执行（R1 + R2），5 篇并发
    python scripts/evaluate_jiaodafaxue.py \
        --paper-list results/datasets/jiaodafaxue/metadata.json \
        --output-dir results/runs/jiaodafaxue-six-dimension \
        --concurrency 5 \
        --rounds both

    # 分批执行（先跑前 50 篇测试）
    python scripts/evaluate_jiaodafaxue.py \
        --paper-list results/datasets/jiaodafaxue/metadata.json \
        --output-dir results/runs/jiaodafaxue-six-dimension \
        --concurrency 5 \
        --rounds both \
        --paper-range 1-50

    # 只跑 Round 2（R1 结果已存在）
    python scripts/evaluate_jiaodafaxue.py \
        --paper-range 1-50 --rounds r2 --concurrency 5
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

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.run_convergence_test import run_convergence_test
from scripts.run_cross_review import (
    evaluate_dimension_cross_review,
    A_GROUP,
    B_GROUP,
    _load_framework,
)
from src.evaluation.providers.factory import create_providers
from src.ingestion.preprocessor import process_file


MODELS = ['deepseek-v4-pro', 'glm-5.1', 'kimi-k2.6', 'qwen3.6-plus']
DEFAULT_FRAMEWORK = 'configs/frameworks/law-v2.55-cross-review.yaml'


def setup_logging(output_dir: Path) -> logging.Logger:
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
    logger = logging.getLogger(__name__)
    return logger


def load_paper_list(paper_list_path: str, paper_range: str | None = None) -> list[dict]:
    """加载论文列表，可选按 id 范围过滤"""
    with open(paper_list_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    papers = data['papers']

    if paper_range:
        start, end = map(int, paper_range.split('-'))
        papers = [p for p in papers if start <= p['id'] <= end]

    return papers


def save_progress(output_dir: Path, progress: dict):
    """保存进度"""
    progress_path = output_dir / "progress.json"
    progress_path.write_text(
        json.dumps(progress, indent=2, ensure_ascii=False), encoding='utf-8'
    )


def log_content_inspection(output_dir: Path, paper_id: int, paper_path: str, model: str, error: str):
    """记录内容审查问题"""
    issues_path = output_dir / "content_inspection_issues.jsonl"
    record = {
        "paper_id": paper_id,
        "paper_path": paper_path,
        "model": model,
        "error": error,
        "timestamp": datetime.now().isoformat()
    }
    with open(issues_path, 'a', encoding='utf-8') as f:
        f.write(json.dumps(record, ensure_ascii=False) + '\n')


async def run_round1_single(
    paper: dict,
    framework_path: str,
    r1_output_path: Path,
    logger: logging.Logger,
) -> dict | None:
    """执行单篇论文 Round 1"""
    paper_id = paper['id']
    paper_path = paper['path']
    paper_name = paper['filename'][:50]

    # 断点续传
    if r1_output_path.exists():
        logger.info(f"[R1] id={paper_id} {paper_name} → 跳过（已完成）")
        with open(r1_output_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    logger.info(f"[R1] id={paper_id} {paper_name} → 开始...")
    start_time = time.time()

    try:
        result = await run_convergence_test(
            framework_path=framework_path,
            paper_path=paper_path,
            model_names=MODELS,
            aggregation_mode="both",
        )
        elapsed = time.time() - start_time

        r1_output_path.parent.mkdir(parents=True, exist_ok=True)
        r1_output_path.write_text(
            json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8'
        )

        overall = result.get("overall", {})
        score_mean = overall.get("aggregation_mean", {}).get("final_score")
        max_std = overall.get("max_std", "?")

        logger.info(
            f"[R1] id={paper_id} {paper_name} → "
            f"完成 mean={score_mean} max_std={max_std} 耗时={elapsed:.0f}s"
        )
        return result

    except Exception as e:
        elapsed = time.time() - start_time
        error_msg = str(e)
        logger.error(f"[R1] id={paper_id} {paper_name} → 失败 ({elapsed:.0f}s): {error_msg}")

        if "data_inspection_failed" in error_msg or "content_policy" in error_msg:
            log_content_inspection(r1_output_path.parent.parent, paper_id, paper_path, "all", error_msg)

        return None


async def run_round2_single(
    paper: dict,
    round1_result: dict,
    framework,
    providers: dict,
    r2_output_path: Path,
    logger: logging.Logger,
) -> dict | None:
    """执行单篇论文 Round 2（交叉评审）"""
    paper_id = paper['id']
    paper_path = paper['path']
    paper_name = paper['filename'][:50]

    # 断点续传
    if r2_output_path.exists():
        logger.info(f"[R2] id={paper_id} {paper_name} → 跳过（已完成）")
        with open(r2_output_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    logger.info(f"[R2] id={paper_id} {paper_name} → 开始交叉评审...")
    start_time = time.time()

    try:
        # 加载论文原文
        paper_obj = process_file(paper_path)

        # 并发控制（API 级别）
        semaphore = asyncio.Semaphore(10)

        # 对每个维度顺序执行交叉评审
        round2_dimensions = {}
        for dim in framework.dimensions:
            round1_dim = round1_result.get("dimensions", {}).get(dim.key)
            if not round1_dim:
                continue

            dim_result = await evaluate_dimension_cross_review(
                dimension_key=dim.key,
                dimension_name=dim.name_zh,
                round1_dim_result=round1_dim,
                paper=paper_obj,
                providers=providers,
                semaphore=semaphore,
            )
            round2_dimensions[dim.key] = dim_result

            r1_std = dim_result['round1_std']
            r2_std = dim_result['round2_std']
            logger.info(
                f"[R2] id={paper_id} {dim.name_zh}: "
                f"std {r1_std} → {r2_std} ({r2_std - r1_std:+.1f})"
            )

        elapsed = time.time() - start_time

        # 构建 R2 完整结果
        all_round2_stds = [d['round2_std'] for d in round2_dimensions.values()]
        all_round1_stds = [d['round1_std'] for d in round2_dimensions.values()]

        # 计算 R2 总分
        all_r1_scores = []
        all_r2_scores = []
        for dim_data in round2_dimensions.values():
            all_r1_scores.extend(dim_data['round1_scores'].values())
            all_r2_scores.extend(dim_data['round2_scores'].values())

        r1_final_mean = round(statistics.mean(all_r1_scores), 2) if all_r1_scores else 0
        r2_final_mean = round(statistics.mean(all_r2_scores), 2) if all_r2_scores else 0

        round2_result = {
            "paper": paper_path,
            "framework": DEFAULT_FRAMEWORK,
            "models": MODELS,
            "dimensions": round2_dimensions,
            "overall": {
                "round1_avg_std": round(statistics.mean(all_round1_stds), 2) if all_round1_stds else 0,
                "round2_avg_std": round(statistics.mean(all_round2_stds), 2) if all_round2_stds else 0,
                "std_improvement": round(
                    statistics.mean(all_round1_stds) - statistics.mean(all_round2_stds), 2
                ) if all_round1_stds and all_round2_stds else 0,
                "round1_max_std": round(max(all_round1_stds), 2) if all_round1_stds else 0,
                "round2_max_std": round(max(all_round2_stds), 2) if all_round2_stds else 0,
                "dimensions_converged": sum(1 for s in all_round2_stds if s <= 8),
                "total_dimensions": len(all_round2_stds),
                "round1_final_score_mean": r1_final_mean,
                "round2_final_score_mean": r2_final_mean,
            },
        }

        r2_output_path.parent.mkdir(parents=True, exist_ok=True)
        r2_output_path.write_text(
            json.dumps(round2_result, indent=2, ensure_ascii=False), encoding='utf-8'
        )

        r2_overall = round2_result["overall"]
        logger.info(
            f"[R2] id={paper_id} {paper_name} → "
            f"完成 avg_std {r2_overall['round1_avg_std']}→{r2_overall['round2_avg_std']} "
            f"converged={r2_overall['dimensions_converged']}/{r2_overall['total_dimensions']} "
            f"耗时={elapsed:.0f}s"
        )
        return round2_result

    except Exception as e:
        elapsed = time.time() - start_time
        error_msg = str(e)
        logger.error(f"[R2] id={paper_id} {paper_name} → 失败 ({elapsed:.0f}s): {error_msg}")

        if "data_inspection_failed" in error_msg or "content_policy" in error_msg:
            log_content_inspection(r2_output_path.parent.parent, paper_id, paper_path, "all", error_msg)

        return None


async def run_round1_batch(
    papers: list[dict],
    framework_path: str,
    output_dir: Path,
    concurrency: int,
    logger: logging.Logger,
) -> list[tuple[dict, dict | None]]:
    """批量执行 Round 1"""
    r1_dir = output_dir / "round1"
    r1_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"[R1 批次] 开始，共 {len(papers)} 篇，并发={concurrency}")
    start_time = time.time()

    semaphore = asyncio.Semaphore(concurrency)

    async def run_with_limit(paper):
        async with semaphore:
            r1_path = r1_dir / f"paper-{paper['id']}.json"
            result = await run_round1_single(paper, framework_path, r1_path, logger)
            return paper, result

    tasks = [run_with_limit(p) for p in papers]
    results = await asyncio.gather(*tasks, return_exceptions=False)

    elapsed = time.time() - start_time
    success = sum(1 for _, r in results if r is not None)
    failed = len(results) - success

    logger.info(
        f"[R1 批次] 完成：{success}/{len(papers)} 成功，{failed} 失败，"
        f"耗时={elapsed/3600:.1f}h"
    )

    return results


async def run_round2_batch(
    papers: list[dict],
    round1_results: list[tuple[dict, dict | None]],
    framework_path: str,
    output_dir: Path,
    concurrency: int,
    logger: logging.Logger,
) -> list[tuple[dict, dict | None]]:
    """批量执行 Round 2"""
    r2_dir = output_dir / "round2"
    r2_dir.mkdir(parents=True, exist_ok=True)

    # 过滤 R1 成功的论文
    r1_success = [(paper, r1) for paper, r1 in round1_results if r1 is not None]
    r1_failed_count = len(round1_results) - len(r1_success)

    if r1_failed_count > 0:
        logger.warning(f"[R2 批次] 跳过 {r1_failed_count} 篇（R1 失败）")

    logger.info(f"[R2 批次] 开始，共 {len(r1_success)} 篇，并发={concurrency}")
    start_time = time.time()

    # 加载框架和 providers
    framework = _load_framework(framework_path)
    providers_list = create_providers(MODELS)
    providers = {p.model_name: p for p in providers_list}

    semaphore = asyncio.Semaphore(concurrency)

    async def run_with_limit(paper, r1_result):
        async with semaphore:
            r2_path = r2_dir / f"paper-{paper['id']}.json"
            result = await run_round2_single(
                paper, r1_result, framework, providers, r2_path, logger
            )
            return paper, result

    tasks = [run_with_limit(paper, r1) for paper, r1 in r1_success]
    results = await asyncio.gather(*tasks, return_exceptions=False)

    elapsed = time.time() - start_time
    success = sum(1 for _, r in results if r is not None)
    failed = len(results) - success

    logger.info(
        f"[R2 批次] 完成：{success}/{len(r1_success)} 成功，{failed} 失败，"
        f"耗时={elapsed/3600:.1f}h"
    )

    return results


def generate_batch_report(
    papers: list[dict],
    round1_results: list[tuple[dict, dict | None]],
    round2_results: list[tuple[dict, dict | None]] | None,
    elapsed_total: float,
    output_dir: Path,
):
    """生成批次报告"""
    # R1 统计
    r1_scores = []
    r1_max_stds = []
    r1_success = 0

    for _, r1 in round1_results:
        if r1 is not None:
            r1_success += 1
            overall = r1.get("overall", {})
            score = overall.get("aggregation_mean", {}).get("final_score")
            if score is not None:
                r1_scores.append(score)
            max_std = overall.get("max_std")
            if max_std is not None:
                r1_max_stds.append(max_std)

    # R2 统计
    r2_success = 0
    r2_avg_stds = []
    r2_converged = 0
    r2_total_dims = 0

    if round2_results:
        for _, r2 in round2_results:
            if r2 is not None:
                r2_success += 1
                overall = r2.get("overall", {})
                avg_std = overall.get("round2_avg_std")
                if avg_std is not None:
                    r2_avg_stds.append(avg_std)
                r2_converged += overall.get("dimensions_converged", 0)
                r2_total_dims += overall.get("total_dimensions", 0)

    # 内容审查问题统计
    issues_path = output_dir / "content_inspection_issues.jsonl"
    content_issues = 0
    if issues_path.exists():
        with open(issues_path, 'r', encoding='utf-8') as f:
            content_issues = sum(1 for _ in f)

    elapsed_str = f"{int(elapsed_total // 3600)}h {int((elapsed_total % 3600) // 60)}m"

    report = {
        "total": len(papers),
        "r1_completed": r1_success,
        "r1_failed": len(papers) - r1_success,
        "r2_completed": r2_success,
        "r2_failed": (len(round2_results) - r2_success) if round2_results else 0,
        "r1_avg_score_mean": round(statistics.mean(r1_scores), 2) if r1_scores else None,
        "r1_avg_max_std": round(statistics.mean(r1_max_stds), 2) if r1_max_stds else None,
        "r2_avg_std": round(statistics.mean(r2_avg_stds), 2) if r2_avg_stds else None,
        "r2_convergence_rate": (
            f"{r2_converged/r2_total_dims*100:.1f}%" if r2_total_dims > 0 else None
        ),
        "content_inspection_issues": content_issues,
        "elapsed_time": elapsed_str,
        "elapsed_seconds": round(elapsed_total),
        "timestamp": datetime.now().isoformat(),
    }

    report_path = output_dir / "batch-report.json"
    report_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8'
    )

    return report


async def main():
    parser = argparse.ArgumentParser(description="交大法学六维度两轮评审")
    parser.add_argument(
        "--paper-list",
        default="results/datasets/jiaodafaxue/metadata.json",
        help="论文列表 JSON 路径",
    )
    parser.add_argument(
        "--framework",
        default=DEFAULT_FRAMEWORK,
        help="框架配置文件路径",
    )
    parser.add_argument(
        "--output-dir",
        default="results/runs/jiaodafaxue-six-dimension",
        help="输出目录",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=5,
        help="论文级并发数（默认 5）",
    )
    parser.add_argument(
        "--rounds",
        choices=["r1", "r2", "both"],
        default="both",
        help="执行阶段：r1=仅 Round 1，r2=仅 Round 2，both=两轮都跑",
    )
    parser.add_argument(
        "--paper-range",
        default=None,
        help="论文 id 范围，如 1-50（默认全部）",
    )

    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    logger = setup_logging(output_dir)

    # 加载论文列表
    papers = load_paper_list(args.paper_list, args.paper_range)
    logger.info(f"加载论文列表：{len(papers)} 篇")
    logger.info(f"框架：{args.framework}")
    logger.info(f"模型：{', '.join(MODELS)}")
    logger.info(f"并发数：{args.concurrency}")
    logger.info(f"执行阶段：{args.rounds}")
    if args.paper_range:
        logger.info(f"论文范围：id {args.paper_range}")
    logger.info("")

    start_total = time.time()

    # Round 1
    round1_results = None
    if args.rounds in ("r1", "both"):
        round1_results = await run_round1_batch(
            papers, args.framework, output_dir, args.concurrency, logger
        )

        # 保存 R1 进度
        r1_success = sum(1 for _, r in round1_results if r is not None)
        save_progress(output_dir, {
            "phase": "r1",
            "total": len(papers),
            "completed": r1_success,
            "failed": len(papers) - r1_success,
            "timestamp": datetime.now().isoformat(),
        })

    # Round 2
    round2_results = None
    if args.rounds in ("r2", "both"):
        # 如果没跑 R1，从文件加载 R1 结果
        if round1_results is None:
            r1_dir = output_dir / "round1"
            round1_results = []
            for paper in papers:
                r1_path = r1_dir / f"paper-{paper['id']}.json"
                if r1_path.exists():
                    with open(r1_path, 'r', encoding='utf-8') as f:
                        round1_results.append((paper, json.load(f)))
                else:
                    round1_results.append((paper, None))

        round2_results = await run_round2_batch(
            papers, round1_results, args.framework, output_dir, args.concurrency, logger
        )

        # 保存 R2 进度
        r2_success = sum(1 for _, r in round2_results if r is not None)
        save_progress(output_dir, {
            "phase": "r2",
            "total": len(papers),
            "completed": r2_success,
            "failed": len(round2_results) - r2_success,
            "timestamp": datetime.now().isoformat(),
        })

    # 生成批次报告
    elapsed_total = time.time() - start_total
    report = generate_batch_report(
        papers, round1_results or [], round2_results, elapsed_total, output_dir
    )

    logger.info("")
    logger.info("=" * 60)
    logger.info("批次完成")
    logger.info(f"  R1: {report['r1_completed']}/{report['total']} 成功")
    if round2_results is not None:
        logger.info(f"  R2: {report['r2_completed']}/{report['total']} 成功")
        logger.info(f"  R2 avg_std: {report['r2_avg_std']}")
        logger.info(f"  R2 收敛率: {report['r2_convergence_rate']}")
    logger.info(f"  总耗时: {report['elapsed_time']}")
    logger.info(f"  内容审查问题: {report['content_inspection_issues']}")
    logger.info("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
