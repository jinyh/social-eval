#!/usr/bin/env python3
"""选择性第 3 次评测：仅针对不稳定维度（std > 5）

基于前两次评测的分析，13 篇 Top 30 论文共有 17 个维度-论文组合不稳定。
本脚本仅评测这些不稳定维度，节省 78% 的 API 调用。

用法：
    python scripts/selective_retest_top30.py \
        --framework configs/frameworks/law-v2.55-cross-review.yaml \
        --output-dir results/retest-top60/round3 \
        --concurrency 3
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

# 选择性评测清单：{论文ID: [不稳定维度key]}
# 基于两次评测 R2 合并 8 分数 std > 5 的维度
SELECTIVE_RETEST = {
    1023: ['problem_originality'],                              # 创新性 std=12.1
    1337: ['problem_originality'],                              # 创新性 std=6.0
    956:  ['forward_extension'],                                # 延展性 std=5.6
    1553: ['problem_originality'],                              # 创新性 std=6.2
    1519: ['problem_originality', 'forward_extension'],         # 创新性 std=5.7, 延展性 std=6.2
    1493: ['literature_insight', 'analytical_framework'],       # 洞察度 std=5.0, 建构力 std=6.4
    1194: ['analytical_framework'],                             # 建构力 std=9.4
    1501: ['problem_originality'],                              # 创新性 std=6.0
    1885: ['problem_originality'],                              # 创新性 std=10.4
    1767: ['problem_originality'],                              # 创新性 std=6.1
    882:  ['literature_insight'],                               # 洞察度 std=6.0
    1852: ['problem_originality', 'literature_insight'],        # 创新性 std=6.0, 洞察度 std=6.3
    1824: ['literature_insight', 'analytical_framework'],       # 洞察度 std=13.0, 建构力 std=6.2
}

DIM_ZH = {
    'problem_originality': '创新性',
    'literature_insight': '洞察度',
    'analytical_framework': '建构力',
    'logical_coherence': '连贯性',
    'conclusion_consensus': '共识度',
    'forward_extension': '延展性',
}


def setup_logging(output_dir: Path) -> logging.Logger:
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


def calculate_confidence(scores: dict | list) -> dict:
    """计算单维度评测置信度"""
    if isinstance(scores, dict):
        vals = list(scores.values())
    else:
        vals = list(scores)

    if len(vals) < 2:
        return {"confidence": "low", "se": 0, "mean": vals[0] if vals else 0}

    mean = statistics.mean(vals)
    std = statistics.stdev(vals)
    n = len(vals)
    se = std / (n ** 0.5)

    if se <= 2:
        conf = "high"
    elif se <= 4:
        conf = "medium"
    else:
        conf = "low"

    return {
        "confidence": conf,
        "se": round(se, 2),
        "mean": round(mean, 2),
        "ci_lo": round(mean - 1.96 * se, 2),
        "ci_hi": round(mean + 1.96 * se, 2),
        "ci_width": round(3.92 * se, 2),
        "n_dims": n,
    }


def calculate_overall_confidence(round2_dimensions: dict) -> dict:
    """计算总体置信度（误差传播法）"""
    weights = {
        'problem_originality': 0.30,
        'literature_insight': 0.20,
        'analytical_framework': 0.15,
        'logical_coherence': 0.20,
        'conclusion_consensus': 0.10,
        'forward_extension': 0.05,
    }

    weighted_sum = 0
    se_squared_sum = 0

    for dk, dd in round2_dimensions.items():
        w = weights.get(dk, 1 / len(round2_dimensions))
        scores = dd.get('round2_scores', {})
        vals = list(scores.values()) if isinstance(scores, dict) else list(scores)
        if len(vals) >= 2:
            mean = statistics.mean(vals)
            se = statistics.stdev(vals) / (len(vals) ** 0.5)
        else:
            mean = vals[0] if vals else 0
            se = 0

        weighted_sum += w * mean
        se_squared_sum += (w * se) ** 2

    overall_se = se_squared_sum ** 0.5

    if overall_se <= 1:
        conf = "high"
    elif overall_se <= 2:
        conf = "medium"
    else:
        conf = "low"

    return {
        "confidence": conf,
        "se": round(overall_se, 2),
        "mean": round(weighted_sum, 2),
        "ci_lo": round(weighted_sum - 1.96 * overall_se, 2),
        "ci_hi": round(weighted_sum + 1.96 * overall_se, 2),
        "ci_width": round(3.92 * overall_se, 2),
        "n_dims": len(round2_dimensions),
    }


def build_paper_list():
    """构建选择性重测论文列表"""
    import csv
    import os

    meta = {}
    with open(PROJECT_ROOT / "results" / "merged-metadata.csv",
              'r', encoding='utf-8-sig') as f:
        for r in csv.DictReader(f):
            meta[int(r['编号'])] = r

    papers = []
    for pid, target_dims in SELECTIVE_RETEST.items():
        if pid not in meta:
            print(f"⚠️ paper-{pid}: metadata 中未找到")
            continue

        raw_path = None
        for fn in os.listdir(PROJECT_ROOT / "raw" / "fullpaper"):
            if fn.startswith(f"{pid:04d}-") and fn.endswith('.pdf'):
                raw_path = f"raw/fullpaper/{fn}"
                break

        if not raw_path:
            print(f"⚠️ paper-{pid}: raw/fullpaper 中未找到文件")
            continue

        papers.append({
            'id': pid,
            'path': raw_path,
            'filename': os.path.basename(raw_path),
            'target_dims': target_dims,
        })

    return papers


async def run_selective_r1(
    paper: dict,
    framework_path: str,
    r1_output_path: Path,
    logger: logging.Logger,
) -> dict | None:
    """执行选择性 R1：仅评测目标维度"""
    paper_id = paper['id']
    target_dims = paper['target_dims']
    dims_str = ', '.join(DIM_ZH.get(d, d) for d in target_dims)
    paper_name = paper['filename'][:50]

    if r1_output_path.exists():
        logger.info(f"[R1] id={paper_id} {paper_name} [{dims_str}] → 跳过（已完成）")
        with open(r1_output_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    logger.info(f"[R1] id={paper_id} {paper_name} [{dims_str}] → 开始...")
    start_time = time.time()

    try:
        result = await run_convergence_test(
            framework_path=framework_path,
            paper_path=paper['path'],
            model_names=MODELS,
            dimension_keys=target_dims,
            aggregation_mode="both",
        )
        elapsed = time.time() - start_time

        r1_output_path.parent.mkdir(parents=True, exist_ok=True)
        r1_output_path.write_text(
            json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8'
        )

        logger.info(
            f"[R1] id={paper_id} {paper_name} [{dims_str}] → "
            f"完成 耗时={elapsed:.0f}s"
        )
        return result

    except Exception as e:
        elapsed = time.time() - start_time
        logger.error(f"[R1] id={paper_id} {paper_name} → 失败 ({elapsed:.0f}s): {e}")
        return None


async def run_selective_r2(
    paper: dict,
    round1_result: dict,
    framework,
    providers: dict,
    r2_output_path: Path,
    logger: logging.Logger,
) -> dict | None:
    """执行选择性 R2：仅对目标维度做交叉评审"""
    paper_id = paper['id']
    target_dims = paper['target_dims']
    dims_str = ', '.join(DIM_ZH.get(d, d) for d in target_dims)
    paper_name = paper['filename'][:50]

    if r2_output_path.exists():
        logger.info(f"[R2] id={paper_id} {paper_name} [{dims_str}] → 跳过（已完成）")
        with open(r2_output_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    logger.info(f"[R2] id={paper_id} {paper_name} [{dims_str}] → 开始交叉评审...")
    start_time = time.time()

    try:
        paper_obj = process_file(paper['path'])
        semaphore = asyncio.Semaphore(10)

        round2_dimensions = {}
        for dim in framework.dimensions:
            if dim.key not in target_dims:
                continue

            round1_dim = round1_result.get("dimensions", {}).get(dim.key)
            if not round1_dim:
                logger.warning(f"[R2] id={paper_id} {dim.name_zh}: R1 数据缺失，跳过")
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

        # 构建 R2 结果
        all_round2_stds = [d['round2_std'] for d in round2_dimensions.values()]
        all_round1_stds = [d['round1_std'] for d in round2_dimensions.values()]

        all_r1_scores = []
        all_r2_scores = []
        for dim_data in round2_dimensions.values():
            all_r1_scores.extend(dim_data['round1_scores'].values())
            all_r2_scores.extend(dim_data['round2_scores'].values())

        r1_final_mean = round(statistics.mean(all_r1_scores), 2) if all_r1_scores else 0
        r2_final_mean = round(statistics.mean(all_r2_scores), 2) if all_r2_scores else 0

        dim_confidence = {}
        for dk, dd in round2_dimensions.items():
            dim_confidence[dk] = calculate_confidence(dd.get('round2_scores', {}))

        overall_confidence = calculate_overall_confidence(round2_dimensions)

        round2_result = {
            "paper": paper['path'],
            "framework": DEFAULT_FRAMEWORK,
            "models": MODELS,
            "dimensions": round2_dimensions,
            "dimension_confidence": dim_confidence,
            "selective": True,
            "target_dims": target_dims,
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
                "confidence": overall_confidence,
            },
        }

        r2_output_path.parent.mkdir(parents=True, exist_ok=True)
        r2_output_path.write_text(
            json.dumps(round2_result, indent=2, ensure_ascii=False), encoding='utf-8'
        )

        r2_overall = round2_result["overall"]
        logger.info(
            f"[R2] id={paper_id} {paper_name} [{dims_str}] → "
            f"完成 avg_std {r2_overall['round1_avg_std']}→{r2_overall['round2_avg_std']} "
            f"converged={r2_overall['dimensions_converged']}/{r2_overall['total_dimensions']} "
            f"耗时={elapsed:.0f}s"
        )
        return round2_result

    except Exception as e:
        elapsed = time.time() - start_time
        logger.error(f"[R2] id={paper_id} {paper_name} → 失败 ({elapsed:.0f}s): {e}")
        return None


async def main():
    parser = argparse.ArgumentParser(description="选择性第 3 次评测（仅不稳定维度）")
    parser.add_argument("--framework", default=DEFAULT_FRAMEWORK)
    parser.add_argument("--output-dir", default="results/retest-top60/round3")
    parser.add_argument("--concurrency", type=int, default=3)
    parser.add_argument("--rounds", choices=["r1", "r2", "both"], default="both")

    args = parser.parse_args()

    output_dir = PROJECT_ROOT / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    r1_dir = output_dir / "round1"
    r2_dir = output_dir / "round2"
    r1_dir.mkdir(parents=True, exist_ok=True)
    r2_dir.mkdir(parents=True, exist_ok=True)

    logger = setup_logging(output_dir)

    papers = build_paper_list()
    total_dims = sum(len(p['target_dims']) for p in papers)

    logger.info(f"选择性第 3 次评测")
    logger.info(f"论文数：{len(papers)} 篇")
    logger.info(f"维度-论文组合：{total_dims} 个")
    logger.info(f"框架：{args.framework}")
    logger.info(f"模型：{', '.join(MODELS)}")
    logger.info(f"并发数：{args.concurrency}")
    logger.info(f"执行阶段：{args.rounds}")
    for p in papers:
        dims_str = ', '.join(DIM_ZH.get(d, d) for d in p['target_dims'])
        logger.info(f"  paper-{p['id']}: [{dims_str}]")
    logger.info("")

    start_total = time.time()
    concurrency = args.concurrency

    # Round 1
    round1_results = {}
    if args.rounds in ("r1", "both"):
        logger.info(f"[R1 批次] 开始，共 {len(papers)} 篇，并发={concurrency}")
        semaphore = asyncio.Semaphore(concurrency)

        async def run_r1(paper):
            async with semaphore:
                r1_path = r1_dir / f"paper-{paper['id']}.json"
                result = await run_selective_r1(paper, args.framework, r1_path, logger)
                return paper['id'], result

        tasks = [run_r1(p) for p in papers]
        results = await asyncio.gather(*tasks)
        round1_results = dict(results)

        r1_success = sum(1 for _, r in results if r is not None)
        logger.info(f"[R1 批次] 完成：{r1_success}/{len(papers)} 成功")

    # Round 2
    if args.rounds in ("r2", "both"):
        framework = _load_framework(args.framework)
        providers_list = create_providers(MODELS)
        providers = {p.model_name: p for p in providers_list}

        if not round1_results:
            for paper in papers:
                r1_path = r1_dir / f"paper-{paper['id']}.json"
                if r1_path.exists():
                    with open(r1_path, 'r', encoding='utf-8') as f:
                        round1_results[paper['id']] = json.load(f)

        r1_ok = [(p, round1_results.get(p['id'])) for p in papers
                 if round1_results.get(p['id']) is not None]
        r1_failed = len(papers) - len(r1_ok)
        if r1_failed:
            logger.warning(f"[R2 批次] 跳过 {r1_failed} 篇（R1 失败）")

        logger.info(f"[R2 批次] 开始，共 {len(r1_ok)} 篇，并发={concurrency}")
        semaphore = asyncio.Semaphore(concurrency)

        async def run_r2(paper, r1):
            async with semaphore:
                r2_path = r2_dir / f"paper-{paper['id']}.json"
                result = await run_selective_r2(
                    paper, r1, framework, providers, r2_path, logger
                )
                return paper['id'], result

        tasks = [run_r2(p, r1) for p, r1 in r1_ok]
        results = await asyncio.gather(*tasks)

        r2_success = sum(1 for _, r in results if r is not None)
        logger.info(f"[R2 批次] 完成：{r2_success}/{len(r1_ok)} 成功")

    elapsed_total = time.time() - start_total
    elapsed_str = f"{int(elapsed_total // 3600)}h {int((elapsed_total % 3600) // 60)}m"
    logger.info(f"\n选择性第 3 次评测完成，总耗时 {elapsed_str}")

    # 汇总
    logger.info("\n[汇总]")
    for r2_file in sorted(r2_dir.glob("paper-*.json")):
        pid = int(r2_file.stem.replace("paper-", ""))
        with open(r2_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        target_dims = data.get('target_dims', [])
        for dk in target_dims:
            dim_data = data.get('dimensions', {}).get(dk, {})
            r1_std = dim_data.get('round1_std', '?')
            r2_std = dim_data.get('round2_std', '?')
            r1_mean = dim_data.get('round1_mean', '?')
            r2_mean = dim_data.get('round2_mean', '?')
            logger.info(
                f"  paper-{pid} {DIM_ZH.get(dk, dk)}: "
                f"R1 mean={r1_mean} std={r1_std} → R2 mean={r2_mean} std={r2_std}"
            )


if __name__ == "__main__":
    asyncio.run(main())
