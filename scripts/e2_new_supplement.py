#!/usr/bin/env python3
"""E2 新候选池补跑脚本 — 5 论文并发, 4 模型 × 6 维度 × 2 轮

用法:
    uv run python scripts/e2_new_supplement.py
    uv run python scripts/e2_new_supplement.py --concurrency 3
    uv run python scripts/e2_new_supplement.py --pids 56 124 295

特性:
    - 默认 4 篇论文并发执行（可 --concurrency 调整）
    - 断点续传: 已完成的 round1/round2 自动跳过
    - 输出到 results/rankings/e2-ccb-v5/per-paper/round1/ 和 round2/
"""
import argparse
import asyncio
import json
import logging
import statistics
import sys
import time
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.run_convergence_test import run_convergence_test  # noqa: E402
from src.evaluation.cross_review import CrossReviewService  # noqa: E402
from src.evaluation.providers.factory import create_providers  # noqa: E402
from src.evaluation.schemas import DimensionResult  # noqa: E402
from src.ingestion.preprocessor import process_file  # noqa: E402
from src.knowledge.loader import (  # noqa: E402
    load_framework as load_validated_framework,
)
from src.knowledge.schemas import Framework  # noqa: E402

# === 配置 ===
FRAMEWORK_PATH = "configs/frameworks/law-v2.55-cross-review.yaml"
REVIEW_PROTOCOL = CrossReviewService().protocol
MODELS = (
    REVIEW_PROTOCOL["model_groups"]["lenient"]
    + REVIEW_PROTOCOL["model_groups"]["strict"]
)
R1_DIR = Path("results/rankings/e2-ccb-v5/per-paper/round1")
R2_DIR = Path("results/rankings/e2-ccb-v5/per-paper/round2")
POOL_FILE = "results/rankings/e2-ccb-v5/pool.json"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("e2-new-supplement")


class ConcurrencyLimitedProvider:
    """让 R1/R2 的所有供应商调用共用同一个全局并发闸门。"""

    def __init__(self, provider: Any, semaphore: asyncio.Semaphore) -> None:
        self._provider = provider
        self._semaphore = semaphore
        self.model_name = provider.model_name
        self.timeout = getattr(provider, "timeout", None)

    async def evaluate_dimension(self, prompt: str) -> Any:
        async with self._semaphore:
            return await self._provider.evaluate_dimension(prompt)

    async def generate_json_response(self, prompt: str) -> dict:
        async with self._semaphore:
            return await self._provider.generate_json_response(prompt)


def load_framework():
    return load_validated_framework(FRAMEWORK_PATH)


def get_pdf_path(pid: int) -> str:
    with open(f"results/datasets/three-journals/six-dimension/phase2-r2-v2.55/per-paper/paper-{pid}.json") as f:
        return json.load(f)["paper"]


def get_todo_pids() -> list[int]:
    """从候选池文件中读取所有 PID，已完成的会被断点续传跳过"""
    with open(POOL_FILE) as f:
        pool = json.load(f)
    return sorted(p["id"] for p in pool)


# === Round 1: 4 模型独立评审 6 维度 ===

async def run_round1(
    pid: int,
    paper_path: str,
    providers: list[Any],
) -> dict | None:
    out = R1_DIR / f"paper-{pid}.json"
    if out.exists():
        log.info(f"[R1] PID {pid} → 跳过（已完成）")
        with open(out) as f:
            return json.load(f)

    log.info(f"[R1] PID {pid} → 开始")
    t0 = time.time()
    try:
        result = await run_convergence_test(
            FRAMEWORK_PATH,
            paper_path,
            MODELS,
            aggregation_mode="both",
            provider_instances=providers,
        )
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        elapsed = time.time() - t0
        overall = result.get("overall", {})
        max_std = overall.get("max_std", "?")
        log.info(f"[R1] PID {pid} → 完成 max_std={max_std} ({elapsed:.0f}s)")
        return result
    except Exception as e:
        log.error(f"[R1] PID {pid} → 失败: {e}")
        return None


# === Round 2: 交叉评审 ===

async def run_round2(
    pid: int,
    paper_path: str,
    r1_result: dict,
    framework: Framework,
    providers: dict,
    sem: asyncio.Semaphore,
) -> dict | None:
    out = R2_DIR / f"paper-{pid}.json"
    if out.exists():
        log.info(f"[R2] PID {pid} → 跳过（已完成）")
        with open(out) as f:
            return json.load(f)

    async with sem:
        log.info(f"[R2] PID {pid} → 开始交叉评审")
        t0 = time.time()
        try:
            paper = process_file(paper_path)
            r2 = {
                "paper": paper_path,
                "paper_id": pid,
                "framework": FRAMEWORK_PATH,
                "models": MODELS,
                "dimensions": {},
                "overall": {},
            }

            cross_review = CrossReviewService()
            provider_list = list(providers.values())
            for dim in framework.dimensions:
                r1d = r1_result.get("dimensions", {}).get(dim.key)
                if not r1d:
                    continue

                raw = r1d.get("raw_outputs", {})
                r1_scores = dict(r1d.get("model_scores", {}))
                r1_results = {
                    model: DimensionResult(
                        dimension=dim.key,
                        score=score,
                        evidence_quotes=list(raw.get(model, {}).get("evidence_quotes", [])),
                        analysis=str(
                            raw.get(model, {}).get("score_rationale")
                            or raw.get(model, {}).get("analysis", "")
                        ),
                        model_name=model,
                    )
                    for model, score in r1_scores.items()
                    if model in providers
                }
                outcomes = await cross_review.evaluate_dimension(
                    provider_list,
                    dim,
                    paper,
                    r1_results,
                )
                r2_scores = {
                    outcome.result.model_name: outcome.result.score
                    for outcome in outcomes
                }
                r2_raw = {
                    outcome.result.model_name: outcome.raw_payload
                    for outcome in outcomes
                }
                changes = {
                    model: {
                        "original": r1_scores.get(model),
                        "revised": score,
                        "changed": score != r1_scores.get(model),
                    }
                    for model, score in r2_scores.items()
                }

                if r2_scores:
                    r1_vals = list(r1_scores.values())
                    r2_vals = list(r2_scores.values())
                    r2["dimensions"][dim.key] = {
                        "dimension": dim.key,
                        "name_zh": dim.name_zh,
                        "round1_scores": r1_scores,
                        "round2_scores": r2_scores,
                        "raw_outputs": raw,
                        "round2_raw_outputs": r2_raw,
                        "changes": changes,
                        "round1_mean": round(statistics.mean(r1_vals), 1) if r1_vals else 0,
                        "round2_mean": round(statistics.mean(r2_vals), 1),
                        "round1_std": round(statistics.stdev(r1_vals), 1) if len(r1_vals) > 1 else 0,
                        "round2_std": round(statistics.stdev(r2_vals), 1) if len(r2_vals) > 1 else 0,
                        "convergence_improvement": round(
                            (statistics.stdev(r1_vals) if len(r1_vals) > 1 else 0)
                            - (statistics.stdev(r2_vals) if len(r2_vals) > 1 else 0),
                            1,
                        ),
                    }

            # Overall
            if r2["dimensions"]:
                r1_stds = [d["round1_std"] for d in r2["dimensions"].values()]
                r2_stds = [d["round2_std"] for d in r2["dimensions"].values()]
                converged = sum(1 for s in r2_stds if s <= 8)
                r2["overall"] = {
                    "round1_avg_std": round(statistics.mean(r1_stds), 2),
                    "round2_avg_std": round(statistics.mean(r2_stds), 2),
                    "std_improvement": round(
                        statistics.mean(r1_stds) - statistics.mean(r2_stds), 2
                    ),
                    "dimensions_converged": converged,
                    "dimensions_total": len(r2["dimensions"]),
                }

            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(r2, indent=2, ensure_ascii=False), encoding="utf-8")

            elapsed = time.time() - t0
            o = r2.get("overall", {})
            log.info(
                f"[R2] PID {pid} → R1_std={o.get('round1_avg_std','?')} "
                f"R2_std={o.get('round2_avg_std','?')} "
                f"converged={o.get('dimensions_converged','?')}/{o.get('dimensions_total','?')} "
                f"({elapsed:.0f}s)"
            )
            return r2

        except Exception as e:
            import traceback
            log.error(f"[R2] PID {pid} → 失败: {e}")
            log.debug(traceback.format_exc())
            return None


# === 单篇完整流程 ===

async def evaluate_paper(
    pid: int,
    framework: Framework,
    providers: dict,
    api_sem: asyncio.Semaphore,
) -> tuple[int, bool]:
    """单篇论文 R1→R2 完整流程"""
    try:
        paper_path = get_pdf_path(pid)
    except Exception as e:
        log.error(f"PID {pid}: 找不到论文 PDF: {e}")
        return pid, False

    r1 = await run_round1(pid, paper_path, list(providers.values()))
    if not r1:
        return pid, False

    r2 = await run_round2(pid, paper_path, r1, framework, providers, api_sem)
    return pid, r2 is not None


# === 主流程 ===

async def main():
    parser = argparse.ArgumentParser(description="E2 新候选池补跑 — 多论文并发")
    parser.add_argument(
        "--concurrency", type=int, default=4, help="论文并发数（默认 4）"
    )
    parser.add_argument(
        "--api-concurrency",
        type=int,
        default=5,
        choices=range(1, 6),
        metavar="1..5",
        help="所有 R1/R2 模型调用共享的并发上限（默认 5）",
    )
    parser.add_argument(
        "--pids", nargs="+", type=int, default=None, help="指定 PID（默认从候选池读取）"
    )
    args = parser.parse_args()

    pids = args.pids if args.pids else get_todo_pids()
    total = len(pids)

    log.info("=" * 60)
    log.info("E2 新候选池补跑开始")
    log.info(f"  框架: {FRAMEWORK_PATH}")
    log.info(f"  模型: {MODELS}")
    log.info(f"  待评测: {total} 篇")
    log.info(f"  论文并发: {args.concurrency}")
    log.info(f"  API 全局并发: {args.api_concurrency}")
    log.info("  输出: results/rankings/e2-ccb-v5/per-paper/")
    log.info("=" * 60)

    framework = load_framework()
    api_gate = asyncio.Semaphore(args.api_concurrency)
    providers_list = [
        ConcurrencyLimitedProvider(provider, api_gate)
        for provider in create_providers(MODELS)
    ]
    providers = {p.model_name: p for p in providers_list}

    paper_sem = asyncio.Semaphore(args.concurrency)
    round2_paper_sem = asyncio.Semaphore(args.concurrency)

    async def run_with_paper_sem(pid):
        async with paper_sem:
            return await evaluate_paper(pid, framework, providers, round2_paper_sem)

    t0 = time.time()
    results = await asyncio.gather(
        *[run_with_paper_sem(pid) for pid in pids],
        return_exceptions=False,
    )
    elapsed = time.time() - t0

    success = sum(1 for _, ok in results if ok)
    failed = [(pid, ok) for pid, ok in results if not ok]

    log.info("")
    log.info("=" * 60)
    log.info("E2 新候选池补跑完成")
    log.info(f"  成功: {success}/{total}")
    log.info(f"  失败: {len(failed)}/{total}")
    if failed:
        for pid, _ in failed:
            log.info(f"    ❌ PID {pid}")
    log.info(f"  耗时: {elapsed / 60:.1f} 分钟")
    log.info("  输出: results/rankings/e2-ccb-v5/per-paper/")
    log.info("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
