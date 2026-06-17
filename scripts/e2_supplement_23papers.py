#!/usr/bin/env python3
"""E2 增强评价：为 Top 102 候选池中 23 篇新增论文补跑两轮评审

用法：
    # 先跑 5 篇测试
    uv run python scripts/e2_supplement_23papers.py --concurrency 5 --limit 5

    # 跑全部 23 篇
    uv run python scripts/e2_supplement_23papers.py --concurrency 5

特性：
    - 断点续传：已完成的论文自动跳过
    - Round 1 → Round 2 串行（同一篇论文），论文间并发
    - 4 模型 × 6 维度 × 2 轮 = 48 次 API 调用/篇
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
    build_cross_review_prompt, A_GROUP, B_GROUP,
)
from src.evaluation.providers.factory import create_providers
from src.ingestion.preprocessor import process_file
from src.knowledge.loader import _normalize_framework_data, DEFAULT_STD_THRESHOLD
from src.knowledge.schemas import Framework

import yaml

# === 配置 ===
FRAMEWORK_PATH = "configs/frameworks/law-v2.55-cross-review.yaml"
RANKING_PATH = "results/top101/ranking_v4_102.json"
E1_DIR = Path("results/fullevaluation/round2")
OUTPUT_DIR = Path("results/e2-top102")
ROUND1_DIR = OUTPUT_DIR / "round1"
ROUND2_DIR = OUTPUT_DIR / "round2"
MODELS = A_GROUP + B_GROUP  # glm-5.1, qwen3.6-plus, deepseek-v4-pro, kimi-k2.6


def setup_logging():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    log_file = OUTPUT_DIR / "execution.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )
    return logging.getLogger("e2-supplement")


def load_framework() -> Framework:
    data = yaml.safe_load(Path(FRAMEWORK_PATH).read_text(encoding="utf-8"))
    if "std_threshold" not in data:
        data["std_threshold"] = DEFAULT_STD_THRESHOLD
    normalized = _normalize_framework_data(data)
    return Framework(**normalized)


def get_new_paper_ids() -> list[int]:
    """从 ranking_v4_102.json 中提取 source=E1 的论文 PID"""
    with open(RANKING_PATH) as f:
        ranking = json.load(f)
    return [p["pid"] for p in ranking["papers"] if p["source"] == "E1"]


def get_paper_path(pid: int) -> str | None:
    """从 E1 结果中获取论文 PDF 路径"""
    e1_file = E1_DIR / f"paper-{pid}.json"
    if not e1_file.exists():
        return None
    with open(e1_file) as f:
        data = json.load(f)
    return data.get("paper")


# === Round 1 ===

async def run_round1(
    pid: int,
    paper_path: str,
    sem: asyncio.Semaphore,
    logger: logging.Logger,
) -> dict | None:
    """单篇论文 Round 1：4 模型独立评审 6 维度"""
    out = ROUND1_DIR / f"paper-{pid}.json"
    if out.exists():
        logger.info(f"[R1] PID {pid} → 跳过（已完成）")
        with open(out) as f:
            return json.load(f)

    async with sem:
        logger.info(f"[R1] PID {pid} → 开始 ({Path(paper_path).stem[:40]})")
        t0 = time.time()
        try:
            result = await run_convergence_test(
                framework_path=FRAMEWORK_PATH,
                paper_path=paper_path,
                model_names=MODELS,
                aggregation_mode="both",
            )
            elapsed = time.time() - t0
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

            overall = result.get("overall", {})
            mean_score = overall.get("aggregation_mean", {}).get("final_score", "?")
            max_std = overall.get("max_std", "?")
            logger.info(f"[R1] PID {pid} → mean={mean_score} max_std={max_std} ({elapsed:.0f}s)")
            return result

        except Exception as e:
            logger.error(f"[R1] PID {pid} → 失败: {e}")
            return None


# === Round 2 ===

async def run_round2(
    pid: int,
    paper_path: str,
    round1_result: dict,
    framework: Framework,
    providers: dict,
    sem: asyncio.Semaphore,
    logger: logging.Logger,
) -> dict | None:
    """单篇论文 Round 2：4 模型交叉评审 6 维度"""
    out = ROUND2_DIR / f"paper-{pid}.json"
    if out.exists():
        logger.info(f"[R2] PID {pid} → 跳过（已完成）")
        with open(out) as f:
            return json.load(f)

    async with sem:
        logger.info(f"[R2] PID {pid} → 开始交叉评审")
        t0 = time.time()
        try:
            paper = process_file(paper_path)
            r2 = {"paper": paper_path, "paper_id": pid, "framework": FRAMEWORK_PATH,
                  "models": MODELS, "dimensions": {}, "overall": {}}

            for dim in framework.dimensions:
                r1_dim = round1_result.get("dimensions", {}).get(dim.key)
                if not r1_dim:
                    continue

                raw_outputs = r1_dim.get("raw_outputs", {})
                r1_scores = {m: raw_outputs[m].get("score", 0) for m in MODELS if m in raw_outputs}

                r2_scores = {}
                for model in MODELS:
                    if model not in raw_outputs:
                        continue
                    other_group = B_GROUP if model in A_GROUP else A_GROUP
                    other_outputs = [raw_outputs[m] for m in other_group if m in raw_outputs]
                    if not other_outputs:
                        continue

                    prompt = build_cross_review_prompt(
                        dimension_name=dim.name_zh,
                        dimension_key=dim.key,
                        self_output=raw_outputs[model],
                        other_group_outputs=other_outputs,
                        paper=paper,
                    )

                    provider = providers.get(model)
                    if not provider:
                        continue
                    try:
                        resp = await provider.generate_json_response(prompt)
                        revised = resp.get("revised_score")
                        if revised is not None:
                            r2_scores[model] = int(revised)
                    except Exception as e:
                        logger.warning(f"[R2] PID {pid} dim={dim.key} model={model} → {e}")

                if r2_scores:
                    r2_mean = statistics.mean(r2_scores.values())
                    r2_std = statistics.stdev(r2_scores.values()) if len(r2_scores) > 1 else 0
                    r1_mean = r1_dim.get("mean", statistics.mean(r1_scores.values()) if r1_scores else 0)
                    r1_std = r1_dim.get("std", statistics.stdev(r1_scores.values()) if len(r1_scores) > 1 else 0)
                    r2["dimensions"][dim.key] = {
                        "dimension": dim.key,
                        "name_zh": dim.name_zh,
                        "round1_scores": r1_scores,
                        "round2_scores": r2_scores,
                        "round1_mean": round(r1_mean, 1),
                        "round2_mean": round(r2_mean, 1),
                        "round1_std": round(r1_std, 1),
                        "round2_std": round(r2_std, 1),
                        "convergence_improvement": round(r1_std - r2_std, 1),
                    }

            # Overall
            if r2["dimensions"]:
                r2_means = [d["round2_mean"] for d in r2["dimensions"].values()]
                r1_means = [d["round1_mean"] for d in r2["dimensions"].values()]
                r2["overall"] = {
                    "round1_avg_std": round(statistics.mean([d["round1_std"] for d in r2["dimensions"].values()]), 2),
                    "round2_avg_std": round(statistics.mean([d["round2_std"] for d in r2["dimensions"].values()]), 2),
                    "std_improvement": round(
                        statistics.mean([d["round1_std"] for d in r2["dimensions"].values()])
                        - statistics.mean([d["round2_std"] for d in r2["dimensions"].values()]), 2),
                    "round1_final_score_mean": round(statistics.mean(r1_means), 2),
                    "round2_final_score_mean": round(statistics.mean(r2_means), 2),
                    "dimensions_converged": sum(1 for d in r2["dimensions"].values() if d["round2_std"] <= 8),
                    "dimensions_total": len(r2["dimensions"]),
                }

            elapsed = time.time() - t0
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(r2, indent=2, ensure_ascii=False), encoding="utf-8")

            o = r2.get("overall", {})
            logger.info(
                f"[R2] PID {pid} → R1_std={o.get('round1_avg_std','?')} "
                f"R2_std={o.get('round2_avg_std','?')} "
                f"converged={o.get('dimensions_converged','?')}/{o.get('dimensions_total','?')} "
                f"({elapsed:.0f}s)"
            )
            return r2

        except Exception as e:
            import traceback
            logger.error(f"[R2] PID {pid} → 失败: {e}")
            logger.debug(traceback.format_exc())
            return None


# === 主流程 ===

async def evaluate_paper(
    pid: int,
    paper_path: str,
    framework: Framework,
    providers: dict,
    paper_sem: asyncio.Semaphore,
    api_sem: asyncio.Semaphore,
    logger: logging.Logger,
) -> tuple[int, bool]:
    """单篇论文完整 R1→R2 流程"""
    r1 = await run_round1(pid, paper_path, api_sem, logger)
    if not r1:
        return pid, False
    r2 = await run_round2(pid, paper_path, r1, framework, providers, api_sem, logger)
    return pid, r2 is not None


async def main():
    parser = argparse.ArgumentParser(description="E2 增强评价：23 篇新增论文补跑")
    parser.add_argument("--concurrency", type=int, default=5, help="论文并发数（默认 5）")
    parser.add_argument("--limit", type=int, default=0, help="限制篇数（0=全部）")
    args = parser.parse_args()

    logger = setup_logging()
    framework = load_framework()

    # 获取待评测论文
    new_pids = get_new_paper_ids()
    if args.limit > 0:
        new_pids = new_pids[: args.limit]
    total = len(new_pids)

    logger.info(f"{'='*60}")
    logger.info(f"E2 增强评价开始")
    logger.info(f"  框架: {FRAMEWORK_PATH}")
    logger.info(f"  模型: {MODELS}")
    logger.info(f"  待评测: {total} 篇")
    logger.info(f"  并发: {args.concurrency} 篇论文")
    logger.info(f"  输出: {OUTPUT_DIR}")
    logger.info(f"{'='*60}")

    # 创建 providers
    providers_list = create_providers(MODELS)
    providers = {p.model_name: p for p in providers_list}

    # 构建任务
    paper_sem = asyncio.Semaphore(args.concurrency)
    api_sem = asyncio.Semaphore(20)  # API 总并发

    tasks = []
    for pid in new_pids:
        paper_path = get_paper_path(pid)
        if not paper_path:
            logger.warning(f"PID {pid}: 找不到论文 PDF，跳过")
            continue
        tasks.append(
            evaluate_paper(pid, paper_path, framework, providers, paper_sem, api_sem, logger)
        )

    # 执行
    t0 = time.time()
    results = await asyncio.gather(*tasks, return_exceptions=False)
    elapsed = time.time() - t0

    # 统计
    success = sum(1 for _, ok in results if ok)
    failed = sum(1 for _, ok in results if not ok)

    logger.info(f"\n{'='*60}")
    logger.info(f"E2 增强评价完成")
    logger.info(f"  成功: {success}/{total}")
    logger.info(f"  失败: {failed}/{total}")
    logger.info(f"  耗时: {elapsed/60:.1f} 分钟")
    logger.info(f"  输出: {OUTPUT_DIR}")
    logger.info(f"{'='*60}")


if __name__ == "__main__":
    asyncio.run(main())
