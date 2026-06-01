#!/usr/bin/env python3
"""重测 Top 60 中需要重测的 50 篇论文

Tier 1（10 篇，直接入选）不参与重测：
  1260, 1428, 1238, 1200, 1266, 946, 101, 1574, 820, 1764

Tier 2-4（50 篇）执行完整 R1→R2 流程：
  - 并发数：5（论文级）
  - 记录 round1 和 round2 结果
  - 计算评测置信度

用法：
    python scripts/retest_top60.py \
        --framework configs/frameworks/law-v2.55-cross-review.yaml \
        --output-dir results/retest-top60 \
        --concurrency 5
"""

import argparse
import asyncio
import json
import logging
import math
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

# Tier 1: 直接入选的 10 篇（不参与重测）
TIER1_IDS = {1260, 1428, 1238, 1200, 1266, 946, 101, 1574, 820, 1764}

# 需要重测的 50 篇（Top 60 中排除 Tier 1）
RETEST_IDS = [
    # Tier 2: 高分歧（std > 8 的维度）
    1865, 1023, 1860, 1606, 1168, 1218, 1571, 901, 1586, 319, 1194,
    # Tier 3: 常规（85.0-86.0，无极端分歧）
    1493, 1510, 1337, 21, 1820, 1885, 1919, 619, 956, 1501,
    1553, 1602, 1763, 1711, 1824, 1852, 1575, 1450, 1779, 1864, 1618, 1519,
    # Tier 4: 边界（84.5-85.0）
    407, 1330, 1307, 1412, 1347, 1909, 1620, 1012,
    1387, 1821, 882, 1767, 1448, 1106, 1577, 1915, 1481,
]


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
    """计算单维度评测置信度

    基于 4 个模型的评分：
    - SE = std / sqrt(n)  （均值的标准误）
    - 95% CI = mean ± 1.96 * SE
    - 置信等级：high(SE < 1.5), medium(1.5-3), low(3-5), critical(>5)
    """
    if isinstance(scores, dict):
        vals = [v for v in scores.values() if v is not None]
    else:
        vals = [v for v in scores if v is not None]

    if len(vals) < 2:
        return {'confidence': 'unknown', 'se': 0, 'std': 0, 'mean': 0, 'ci_lo': 0, 'ci_hi': 0, 'n': 0}

    mean = statistics.mean(vals)
    std = statistics.stdev(vals)
    n = len(vals)
    se = std / math.sqrt(n)
    ci_lo = mean - 1.96 * se
    ci_hi = mean + 1.96 * se

    if se < 1.5:
        confidence = 'high'
    elif se < 3:
        confidence = 'medium'
    elif se < 5:
        confidence = 'low'
    else:
        confidence = 'critical'

    return {
        'confidence': confidence,
        'se': round(se, 2),
        'std': round(std, 2),
        'mean': round(mean, 2),
        'ci_lo': round(ci_lo, 2),
        'ci_hi': round(ci_hi, 2),
        'n': n,
    }


def calculate_overall_confidence(round2_dimensions: dict) -> dict:
    """计算总体置信度（误差传播法）

    总分 = mean(dim1_mean, dim2_mean, ..., dim6_mean)
    根据误差传播公式：
      Var(总分) = Σ Var(dim_mean_i) / 36
      其中 Var(dim_mean_i) = dim_std_i² / n_models
    因此：
      SE(总分) = sqrt(Σ dim_std_i² / n_models) / 6
    """
    dim_stds = []
    dim_means = []
    n_models = 4

    for dk, dd in round2_dimensions.items():
        scores = dd.get('round2_scores', {})
        vals = [v for v in scores.values() if v is not None]
        if len(vals) >= 2:
            dim_stds.append(statistics.stdev(vals))
            dim_means.append(statistics.mean(vals))

    if not dim_means:
        return {'confidence': 'unknown', 'se': 0, 'std': 0, 'mean': 0, 'ci_lo': 0, 'ci_hi': 0, 'n_dims': 0}

    total_mean = statistics.mean(dim_means)
    n_dims = len(dim_means)

    # 误差传播
    sum_var = sum(s ** 2 / n_models for s in dim_stds)
    total_var = sum_var / (n_dims ** 2)
    total_se = math.sqrt(total_var)
    ci_lo = total_mean - 1.96 * total_se
    ci_hi = total_mean + 1.96 * total_se

    if total_se < 1.0:
        confidence = 'high'
    elif total_se < 2.0:
        confidence = 'medium'
    elif total_se < 3.0:
        confidence = 'low'
    else:
        confidence = 'critical'

    return {
        'confidence': confidence,
        'se': round(total_se, 2),
        'mean': round(total_mean, 2),
        'ci_lo': round(ci_lo, 2),
        'ci_hi': round(ci_hi, 2),
        'ci_width': round(ci_hi - ci_lo, 2),
        'n_dims': n_dims,
    }


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
        logger.error(f"[R1] id={paper_id} {paper_name} → 失败 ({elapsed:.0f}s): {e}")
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

    if r2_output_path.exists():
        logger.info(f"[R2] id={paper_id} {paper_name} → 跳过（已完成）")
        with open(r2_output_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    logger.info(f"[R2] id={paper_id} {paper_name} → 开始交叉评审...")
    start_time = time.time()

    try:
        paper_obj = process_file(paper_path)
        semaphore = asyncio.Semaphore(10)

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

        # 构建 R2 完整结果（含置信度）
        all_round2_stds = [d['round2_std'] for d in round2_dimensions.values()]
        all_round1_stds = [d['round1_std'] for d in round2_dimensions.values()]

        all_r1_scores = []
        all_r2_scores = []
        for dim_data in round2_dimensions.values():
            all_r1_scores.extend(dim_data['round1_scores'].values())
            all_r2_scores.extend(dim_data['round2_scores'].values())

        r1_final_mean = round(statistics.mean(all_r1_scores), 2) if all_r1_scores else 0
        r2_final_mean = round(statistics.mean(all_r2_scores), 2) if all_r2_scores else 0

        # 计算各维度置信度
        dim_confidence = {}
        for dk, dd in round2_dimensions.items():
            dim_confidence[dk] = calculate_confidence(dd.get('round2_scores', {}))

        # 总体置信度（误差传播法）
        overall_confidence = calculate_overall_confidence(round2_dimensions)

        round2_result = {
            "paper": paper_path,
            "framework": DEFAULT_FRAMEWORK,
            "models": MODELS,
            "dimensions": round2_dimensions,
            "dimension_confidence": dim_confidence,
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
        conf = r2_overall.get("confidence", {}).get("confidence", "?")
        logger.info(
            f"[R2] id={paper_id} {paper_name} → "
            f"完成 avg_std {r2_overall['round1_avg_std']}→{r2_overall['round2_avg_std']} "
            f"converged={r2_overall['dimensions_converged']}/{r2_overall['total_dimensions']} "
            f"confidence={conf} 耗时={elapsed:.0f}s"
        )
        return round2_result

    except Exception as e:
        elapsed = time.time() - start_time
        logger.error(f"[R2] id={paper_id} {paper_name} → 失败 ({elapsed:.0f}s): {e}")
        return None


def build_paper_list():
    """构建重测论文列表"""
    import csv
    meta = {}
    with open(PROJECT_ROOT / "results" / "merged-metadata.csv",
              'r', encoding='utf-8-sig') as f:
        for r in csv.DictReader(f):
            meta[int(r['编号'])] = r

    papers = []
    for pid in RETEST_IDS:
        if pid in meta:
            m = meta[pid]
            # 从 raw/fullpaper 找新路径
            import os, re
            raw_path = None
            for fn in os.listdir(PROJECT_ROOT / "raw" / "fullpaper"):
                if fn.startswith(f"{pid:04d}-") and fn.endswith('.pdf'):
                    raw_path = f"raw/fullpaper/{fn}"
                    break
            if raw_path:
                papers.append({
                    'id': pid,
                    'path': raw_path,
                    'filename': os.path.basename(raw_path),
                })
            else:
                print(f"⚠️ paper-{pid}: raw/fullpaper 中未找到文件")
        else:
            print(f"⚠️ paper-{pid}: metadata 中未找到")

    return papers


async def main():
    parser = argparse.ArgumentParser(description="重测 Top 60 论文")
    parser.add_argument("--framework", default=DEFAULT_FRAMEWORK)
    parser.add_argument("--output-dir", default="results/retest-top60")
    parser.add_argument("--concurrency", type=int, default=5)
    parser.add_argument("--rounds", choices=["r1", "r2", "both"], default="both")

    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    r1_dir = output_dir / "round1"
    r2_dir = output_dir / "round2"
    r1_dir.mkdir(parents=True, exist_ok=True)
    r2_dir.mkdir(parents=True, exist_ok=True)

    logger = setup_logging(output_dir)

    papers = build_paper_list()
    logger.info(f"重测论文列表：{len(papers)} 篇")
    logger.info(f"Tier 1（直接入选，不重测）：{TIER1_IDS}")
    logger.info(f"框架：{args.framework}")
    logger.info(f"模型：{', '.join(MODELS)}")
    logger.info(f"并发数：{args.concurrency}")
    logger.info(f"执行阶段：{args.rounds}")
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
                result = await run_round1_single(paper, args.framework, r1_path, logger)
                return paper['id'], result

        tasks = [run_r1(p) for p in papers]
        results = await asyncio.gather(*tasks)
        round1_results = dict(results)

        r1_success = sum(1 for _, r in results if r is not None)
        logger.info(f"[R1 批次] 完成：{r1_success}/{len(papers)} 成功")

    # Round 2
    if args.rounds in ("r2", "both"):
        # 加载框架和 providers
        framework = _load_framework(args.framework)
        providers_list = create_providers(MODELS)
        providers = {p.model_name: p for p in providers_list}

        # 如果没跑 R1，从文件加载
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
                result = await run_round2_single(
                    paper, r1, framework, providers, r2_path, logger
                )
                return paper['id'], result

        tasks = [run_r2(p, r1) for p, r1 in r1_ok]
        results = await asyncio.gather(*tasks)

        r2_success = sum(1 for _, r in results if r is not None)
        logger.info(f"[R2 批次] 完成：{r2_success}/{len(r1_ok)} 成功")

    elapsed_total = time.time() - start_total
    elapsed_str = f"{int(elapsed_total // 3600)}h {int((elapsed_total % 3600) // 60)}m"

    # ── 差异检测：对比本次重测与第一次 R2 ──
    DIFF_THRESHOLD_WARN = 3    # 总分差异 > 3 分：标记关注
    DIFF_THRESHOLD_RETEST = 5  # 总分差异 > 5 分：需要第 3 次重测
    DIM_DIFF_THRESHOLD = 10    # 单维度差异 > 10 分：标记该维度

    original_r2_dir = PROJECT_ROOT / "results" / "fullevaluation" / "round2"
    comparison_results = {}

    logger.info("\n[差异检测] 对比重测 R2 与原始 R2...")
    for r2_file in sorted(r2_dir.glob("paper-*.json")):
        pid = int(r2_file.stem.replace("paper-", ""))
        orig_file = original_r2_dir / f"paper-{pid}.json"
        if not orig_file.exists():
            continue

        with open(r2_file, 'r', encoding='utf-8') as f:
            new_data = json.load(f)
        with open(orig_file, 'r', encoding='utf-8') as f:
            orig_data = json.load(f)

        new_score = new_data.get("overall", {}).get("round2_final_score_mean", 0)
        orig_score = orig_data.get("overall", {}).get("round2_final_score_mean", 0)
        score_diff = abs(new_score - orig_score)

        # 维度级对比
        dim_diffs = {}
        for dk in ['problem_originality', 'literature_insight', 'analytical_framework',
                    'logical_coherence', 'conclusion_consensus', 'forward_extension']:
            new_dim = new_data.get("dimensions", {}).get(dk, {})
            orig_dim = orig_data.get("dimensions", {}).get(dk, {})
            new_mean = new_dim.get("round2_mean", 0)
            orig_mean = orig_dim.get("round2_mean", 0)
            if new_mean and orig_mean:
                diff = abs(new_mean - orig_mean)
                dim_diffs[dk] = {
                    'orig': round(orig_mean, 1),
                    'new': round(new_mean, 1),
                    'diff': round(diff, 1),
                    'flag': diff > DIM_DIFF_THRESHOLD,
                }

        flagged_dims = [dk for dk, dd in dim_diffs.items() if dd['flag']]

        if score_diff > DIFF_THRESHOLD_RETEST:
            status = 'NEEDS_R3'
        elif score_diff > DIFF_THRESHOLD_WARN:
            status = 'WARN'
        else:
            status = 'OK'

        comparison_results[f"paper-{pid}"] = {
            'orig_score': round(orig_score, 2),
            'new_score': round(new_score, 2),
            'score_diff': round(score_diff, 2),
            'status': status,
            'dim_diffs': dim_diffs,
            'flagged_dims': flagged_dims,
        }

        if status != 'OK':
            logger.info(
                f"  paper-{pid}: {status} | "
                f"原={orig_score:.1f} 新={new_score:.1f} Δ={score_diff:.1f} "
                f"flagged_dims={flagged_dims}"
            )

    # 统计
    n_ok = sum(1 for v in comparison_results.values() if v['status'] == 'OK')
    n_warn = sum(1 for v in comparison_results.values() if v['status'] == 'WARN')
    n_r3 = sum(1 for v in comparison_results.values() if v['status'] == 'NEEDS_R3')
    logger.info(f"  差异检测：OK={n_ok}, WARN(Δ>{DIFF_THRESHOLD_WARN})={n_warn}, NEEDS_R3(Δ>{DIFF_THRESHOLD_RETEST})={n_r3}")

    # 生成报告
    report = {
        "total": len(papers),
        "tier1_ids": sorted(TIER1_IDS),
        "tier1_count": len(TIER1_IDS),
        "r1_success": sum(1 for r in round1_results.values() if r is not None),
        "r2_success": sum(1 for r in round1_results.values() if r is not None),
        "elapsed": elapsed_str,
        "timestamp": datetime.now().isoformat(),
        "diff_thresholds": {
            "warn": DIFF_THRESHOLD_WARN,
            "retest": DIFF_THRESHOLD_RETEST,
            "dim_flag": DIM_DIFF_THRESHOLD,
        },
    }

    # 汇总置信度 + 最终分数（两次 R2 均值）
    final_scores = {}
    confidence_summary = {}
    for r2_file in sorted(r2_dir.glob("paper-*.json")):
        with open(r2_file, 'r', encoding='utf-8') as f:
            d = json.load(f)
        pid = int(r2_file.stem.replace("paper-", ""))
        pid_key = f"paper-{pid}"

        # 置信度
        conf = d.get("overall", {}).get("confidence", {})
        dim_conf = d.get("dimension_confidence", {})
        confidence_summary[pid_key] = {
            "overall_confidence": conf.get("confidence", "unknown"),
            "overall_se": conf.get("se", 0),
            "overall_ci": [conf.get("ci_lo", 0), conf.get("ci_hi", 0)],
            "overall_ci_width": conf.get("ci_width", 0),
            "dimension_confidence": {
                dk: {"confidence": dc.get("confidence"), "se": dc.get("se")}
                for dk, dc in dim_conf.items()
            }
        }

        # 最终分数：两次 R2 均值
        new_score = d.get("overall", {}).get("round2_final_score_mean", 0)
        comp = comparison_results.get(pid_key, {})
        orig_score = comp.get("orig_score", 0)

        if orig_score:
            final_score = round((orig_score + new_score) / 2, 2)
        else:
            final_score = round(new_score, 2)

        final_scores[pid_key] = {
            "orig_r2_score": orig_score,
            "retest_r2_score": round(new_score, 2),
            "final_score": final_score,
            "score_diff": comp.get("score_diff", 0),
            "status": comp.get("status", "NEW"),
            "flagged_dims": comp.get("flagged_dims", []),
        }

    report["confidence_summary"] = confidence_summary
    report["final_scores"] = final_scores

    report_path = output_dir / "report.json"
    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    logger.info("")
    logger.info("=" * 60)
    logger.info("重测完成")
    logger.info(f"  Tier 1（直接入选）: {len(TIER1_IDS)} 篇")
    logger.info(f"  R1: {report['r1_success']}/{report['total']} 成功")
    logger.info(f"  R2: 见 round2/ 目录")
    logger.info(f"  差异检测: OK={n_ok}  WARN(Δ>{DIFF_THRESHOLD_WARN})={n_warn}  NEEDS_R3(Δ>{DIFF_THRESHOLD_RETEST})={n_r3}")
    logger.info(f"  总耗时: {elapsed_str}")
    logger.info(f"  报告: {report_path}")
    logger.info("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
