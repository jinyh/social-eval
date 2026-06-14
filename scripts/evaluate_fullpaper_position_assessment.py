#!/usr/bin/env python3
"""1920 篇全量五轴位置归属度两轮评估。

路线来自：
docs/evaluation/four-signals-vs-five-axes-comprehensive-report-20260613.md

关键约束：
- 不用六维分或旧四信号预筛，默认从 results/merged-metadata.csv 全量读取。
- 五轴 prompt 不读取六维分、六维评语或排名；六维和预检只在合并结果中后置 join。
- 复用 Top101 已验证的五轴 v0.2 prompt、条件 Round 2 和保守聚合逻辑。

用法：
    # Stage 0：抽 120 篇分层校准样本
    python scripts/evaluate_fullpaper_position_assessment.py \
        --stage0-sample-size 120 \
        --output-dir results/fullpaper-position-assessment-stage0

    # 单篇 dry-run
    python scripts/evaluate_fullpaper_position_assessment.py --pid 1510 --limit 1

    # 全量 Stage A
    python scripts/evaluate_fullpaper_position_assessment.py
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import logging
import sys
from collections import Counter, defaultdict, deque
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.evaluate_top101_position_assessment_two_rounds import (  # noqa: E402
    CONCURRENT_PAPERS,
    MAX_TEXT_CHARS,
    METADATA_PATH,
    MODELS,
    ONTOLOGY_PATH,
    ROUND2_MODES,
    ROUND2_POLICIES,
    decide_round2_policy,
    find_pdf,
    load_or_build_ontology,
    merge_paper_result,
    run_round1_paper,
    run_round2_paper,
    write_round2_skip_marker,
)

KNOWLEDGE_PATH = Path("knowledge/中国法学自主知识体系-树状知识库.md")
PAPER_DIR = Path("raw/fullpaper")
SIX_DIM_EVAL_DIR = Path("results/fullevaluation/round2")
SIX_DIM_ROUND1_DIR = Path("results/fullevaluation/round1")
SIX_DIM_ROUND1_ERR_DIR = Path("results/fullevaluation/round1-err")
OUTPUT_DIR = Path("results/fullpaper-position-assessment")

logger = logging.getLogger("fullpaper-position-assessment")


def setup_logging(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler(output_dir / "execution.log", encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _load_six_dimension_context(eval_dir: Path, pid: int) -> dict[str, Any]:
    data = _read_json(eval_dir / f"paper-{pid}.json")
    if not data:
        return {"final_score": None, "result_path": None}
    overall = data.get("overall", {})
    final_score = overall.get("round2_final_score_mean")
    if final_score is None:
        final_score = overall.get("round1_final_score_mean")
    return {
        "final_score": final_score,
        "round1_avg_std": overall.get("round1_avg_std"),
        "round2_avg_std": overall.get("round2_avg_std"),
        "result_path": str(eval_dir / f"paper-{pid}.json"),
    }


def _paper_id_from_path(path: Path) -> int | None:
    stem = path.stem
    if stem.startswith("paper-"):
        stem = stem.removeprefix("paper-")
    else:
        stem = stem.split("-", 1)[0]
    try:
        return int(stem)
    except ValueError:
        return None


def build_pdf_index(paper_dir: Path) -> dict[int, Path]:
    index: dict[int, Path] = {}
    for path in sorted(paper_dir.glob("*.pdf")):
        pid = _paper_id_from_path(path)
        if pid is not None:
            index.setdefault(pid, path)
    return index


def _precheck_status_from_error_category(category: str) -> str:
    return {
        "2-all-reject": "obviously_ineligible",
        "3-majority-reject": "majority_reject",
        "4-single-reject": "single_reject",
        "5-boundary-only": "boundary_review",
        "1-empty-status": "incomplete_precheck",
    }.get(category, category)


def _model_conclusions_from_error_item(item: dict[str, Any]) -> dict[str, int]:
    return {
        "enter_six_dimension_review": int(item.get("pass_count", 0) or 0),
        "boundary_review": int(item.get("boundary_count", 0) or 0),
        "obviously_ineligible": int(item.get("reject_count", 0) or 0),
        "empty": int(item.get("empty_count", 0) or 0),
    }


def build_precheck_index(
    round1_dir: Path,
    round1_err_dir: Path,
) -> dict[int, dict[str, Any]]:
    """Build a lightweight precheck index without reading every large R1 JSON."""

    index: dict[int, dict[str, Any]] = {}
    for path in sorted(round1_dir.glob("paper-*.json")):
        pid = _paper_id_from_path(path)
        if pid is None:
            continue
        index[pid] = {
            "status": "enter_six_dimension_review",
            "result_path": str(path),
            "model_conclusions": {"enter_six_dimension_review": len(MODELS)},
        }

    summary = _read_json(round1_err_dir / "error-summary.json") or {}
    papers_by_category = summary.get("papers", {})
    if not isinstance(papers_by_category, dict):
        return index

    for category, items in papers_by_category.items():
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            paper_id = str(item.get("paper_id", ""))
            if not paper_id.startswith("paper-"):
                continue
            try:
                pid = int(paper_id.removeprefix("paper-"))
            except ValueError:
                continue
            # round1 中已有文件说明该论文已补测成功，不再用旧的 error-summary 覆盖
            if pid in index and index[pid]["status"] == "enter_six_dimension_review":
                continue
            err_path = round1_err_dir / str(category) / f"paper-{pid}.json"
            index[pid] = {
                "status": _precheck_status_from_error_category(str(category)),
                "error_category": str(category),
                "result_path": str(err_path) if err_path.exists() else None,
                "model_conclusions": _model_conclusions_from_error_item(item),
            }
    return index


def load_fullpaper_papers(
    metadata_path: Path,
    paper_dir: Path,
    eval_dir: Path,
    round1_dir: Path = SIX_DIM_ROUND1_DIR,
    round1_err_dir: Path = SIX_DIM_ROUND1_ERR_DIR,
) -> list[dict[str, Any]]:
    """Load all evaluable fullpaper records keyed by merged-metadata.csv IDs.

    This intentionally does not filter by six-dimensional score. The score is
    attached only as post-hoc context for cross-analysis.
    """

    papers: list[dict[str, Any]] = []
    pdf_index = build_pdf_index(paper_dir)
    precheck_index = build_precheck_index(round1_dir, round1_err_dir)
    with metadata_path.open("r", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            pid = int(row["编号"])
            pdf_path = pdf_index.get(pid) or find_pdf(pid, paper_dir)
            if pdf_path is None:
                logger.warning("PID=%s PDF 未找到，跳过", pid)
                continue
            papers.append(
                {
                    "pid": pid,
                    "pdf_path": pdf_path,
                    "meta": row,
                    "six_dimension": _load_six_dimension_context(eval_dir, pid),
                    "precheck": precheck_index.get(
                        pid,
                        {
                            "status": "unknown",
                            "result_path": None,
                            "model_conclusions": {},
                        },
                    ),
                }
            )
    papers.sort(key=lambda item: item["pid"])
    return papers


def select_stage0_sample(
    papers: list[dict[str, Any]], sample_size: int
) -> list[dict[str, Any]]:
    """Return a deterministic year-discipline stratified calibration sample."""

    if sample_size <= 0 or sample_size >= len(papers):
        return list(papers)

    groups: dict[tuple[str, str], deque[dict[str, Any]]] = defaultdict(deque)
    for paper in sorted(papers, key=lambda item: item["pid"]):
        meta = paper.get("meta", {})
        year = str(meta.get("年份") or meta.get("year") or "")
        discipline = str(
            meta.get("分类")
            or meta.get("专家审阅学科")
            or meta.get("discipline")
            or ""
        )
        groups[(year, discipline)].append(paper)

    selected: list[dict[str, Any]] = []
    ordered_keys = sorted(groups)
    while len(selected) < sample_size and ordered_keys:
        next_keys: list[tuple[str, str]] = []
        for key in ordered_keys:
            bucket = groups[key]
            if bucket and len(selected) < sample_size:
                selected.append(bucket.popleft())
            if bucket:
                next_keys.append(key)
        ordered_keys = next_keys
    return selected


def filter_papers_by_journal(
    papers: list[dict[str, Any]],
    journals: list[str] | None,
) -> list[dict[str, Any]]:
    if not journals:
        return papers
    wanted = set(journals)
    return [paper for paper in papers if paper.get("meta", {}).get("期刊") in wanted]


def remove_papers_already_in_output(
    papers: list[dict[str, Any]],
    output_dirs: list[Path] | None,
) -> list[dict[str, Any]]:
    if not output_dirs:
        return papers

    done: set[int] = set()
    for output_dir in output_dirs:
        merged_dir = output_dir / "merged"
        for path in merged_dir.glob("paper-*.json"):
            pid = _paper_id_from_path(path)
            if pid is not None:
                done.add(pid)
    return [paper for paper in papers if paper["pid"] not in done]


def build_fullpaper_merge_record(
    merged: dict[str, Any], paper: dict[str, Any]
) -> dict[str, Any]:
    """Attach post-hoc context without changing the final five-axis assessment."""

    record = dict(merged)
    record["paper_meta"] = paper["meta"]
    record["six_dimension"] = paper.get("six_dimension", {})
    record["precheck"] = paper.get("precheck", {})
    return record


def _provider_map(model_names: list[str]) -> dict[str, Any]:
    from src.evaluation.providers.factory import create_providers

    providers = create_providers(model_names)
    return {provider.model_name: provider for provider in providers}


def _apply_selection(args: argparse.Namespace, papers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    selected = papers
    selected = filter_papers_by_journal(selected, args.journal)
    selected = remove_papers_already_in_output(selected, args.exclude_output_dir)
    if args.pid is not None:
        selected = [paper for paper in selected if paper["pid"] == args.pid]
        if not selected:
            raise SystemExit(f"PID {args.pid} 未找到或缺少 PDF")
    if args.paper_range:
        start, end = map(int, args.paper_range.split("-"))
        selected = selected[start - 1:end]
    if args.stage0_sample_size:
        selected = select_stage0_sample(selected, args.stage0_sample_size)
    if args.limit:
        selected = selected[: args.limit]
    return selected


def _r2_policy_from_args(args: argparse.Namespace, r1_result: dict[str, Any]) -> dict[str, Any]:
    if args.r2_policy == "all":
        return {
            "mode": "full",
            "reason": "forced_full_round2",
            "reasons": ["forced_full_round2"],
            "axis_disagreements": [],
        }
    if args.r2_policy == "skip":
        return {
            "mode": "skip",
            "reason": "forced_skip_round2",
            "reasons": ["forced_skip_round2"],
            "axis_disagreements": [],
        }
    return decide_round2_policy(r1_result)


def generate_summary(merged_records: list[dict[str, Any]]) -> dict[str, Any]:
    score_dist: Counter[int] = Counter()
    strength_dist: Counter[str] = Counter()
    route_dist: Counter[str] = Counter()
    r2_mode_dist: Counter[str] = Counter()
    precheck_dist: Counter[str] = Counter()
    review_required = 0
    completed = 0

    for record in merged_records:
        r2_mode_dist[record.get("round2_mode", "not_run")] += 1
        precheck_dist[record.get("precheck", {}).get("status", "unknown")] += 1
        final = record.get("final")
        if not final:
            continue
        completed += 1
        score_dist[int(final.get("total_score", 0))] += 1
        strength_dist[str(final.get("strength", "unknown"))] += 1
        route = (final.get("research_route") or {}).get("primary", "unknown")
        route_dist[str(route)] += 1
        review_required += int(bool(final.get("review_required")))

    return {
        "generated_at": datetime.now().isoformat(),
        "method": "position_assessment_v0.2_two_models_conditional_round2_fullpaper",
        "total_records": len(merged_records),
        "completed": completed,
        "models": MODELS,
        "score_distribution": dict(score_dist),
        "strength_distribution": dict(strength_dist),
        "route_distribution": dict(route_dist),
        "round2_mode_distribution": dict(r2_mode_dist),
        "precheck_status_distribution": dict(precheck_dist),
        "review_required": review_required,
        "note": "六维和预检字段仅为后置 join，不作为五轴模型输入。",
    }


def generate_report(merged_records: list[dict[str, Any]], summary: dict[str, Any]) -> str:
    lines = [
        "# 1920 篇全量五轴位置归属度评估摘要",
        "",
        f"生成时间：{summary['generated_at']}",
        f"完成：{summary['completed']}/{summary['total_records']}",
        f"模型：{', '.join(MODELS)}",
        "",
        "## 分布",
        "",
        f"- 五轴分分布：{summary['score_distribution']}",
        f"- 强度分布：{summary['strength_distribution']}",
        f"- 路径分布：{summary['route_distribution']}",
        f"- R2 模式分布：{summary['round2_mode_distribution']}",
        f"- 预检状态分布：{summary['precheck_status_distribution']}",
        f"- 需专家复核：{summary['review_required']}",
        "",
        "## 逐篇结果",
        "",
        "| PID | 年份 | 期刊 | 六维分 | 五轴分 | 强度 | 路径 | R2 | 预检 | 复核 | 题目 |",
        "|---:|---:|---|---:|---:|---|---|---|---|---|---|",
    ]
    for record in sorted(merged_records, key=lambda item: item["paper_id"]):
        meta = record.get("paper_meta", {})
        final = record.get("final") or {}
        six_dim = record.get("six_dimension", {})
        route = (final.get("research_route") or {}).get("primary", "")
        lines.append(
            "| {pid} | {year} | {journal} | {six_score} | {pos_score} | "
            "{strength} | {route} | {r2} | {precheck} | {review} | {title} |".format(
                pid=record.get("paper_id", ""),
                year=meta.get("年份", ""),
                journal=meta.get("期刊", ""),
                six_score=six_dim.get("final_score", ""),
                pos_score=final.get("total_score", ""),
                strength=final.get("strength", ""),
                route=route,
                r2=record.get("round2_mode", ""),
                precheck=record.get("precheck", {}).get("status", ""),
                review="是" if final.get("review_required") else "否",
                title=str(meta.get("题目", ""))[:40],
            )
        )
    return "\n".join(lines) + "\n"


async def run_evaluation(args: argparse.Namespace) -> None:
    output_dir = args.output_dir
    setup_logging(output_dir)
    logger.info("1920 全量五轴位置归属度评估启动")
    logger.info("R2 策略：%s", args.r2_policy)
    logger.info("论文并发：%s", args.concurrency)

    all_papers = load_fullpaper_papers(
        metadata_path=args.metadata,
        paper_dir=args.paper_dir,
        eval_dir=args.eval_dir,
        round1_dir=args.round1_dir,
        round1_err_dir=args.round1_err_dir,
    )
    papers = _apply_selection(args, all_papers)
    logger.info("待评估论文：%d/%d", len(papers), len(all_papers))
    if not papers:
        return

    ontology = load_or_build_ontology(
        args.knowledge,
        args.ontology,
        rebuild=args.rebuild_ontology,
    )
    logger.info("Ontology 节点数：%s", len(ontology.nodes))
    provider_map = _provider_map(MODELS)

    r1_dir = output_dir / "round1"
    r2_dir = output_dir / "round2"
    merged_dir = output_dir / "merged"
    for directory in (r1_dir, r2_dir, merged_dir):
        directory.mkdir(parents=True, exist_ok=True)

    semaphore = asyncio.Semaphore(args.concurrency)

    if args.round in (None, 1):
        r1_results = await asyncio.gather(
            *[
                run_round1_paper(
                    pid=paper["pid"],
                    pdf_path=paper["pdf_path"],
                    paper_meta=paper["meta"],
                    ontology=ontology,
                    provider_map=provider_map,
                    output_dir=r1_dir,
                    semaphore=semaphore,
                    max_text_chars=args.max_text_chars,
                    node_top_k=args.node_top_k,
                )
                for paper in papers
            ]
        )
        logger.info("[R1] 完成 %s/%s", sum(r is not None for r in r1_results), len(papers))

    if args.round in (None, 2):
        r2_jobs = []
        for paper in papers:
            pid = paper["pid"]
            r1_path = r1_dir / f"paper-{pid}.json"
            if not r1_path.exists():
                logger.warning("[R2] PID=%s 缺少 R1，跳过", pid)
                r2_jobs.append(asyncio.sleep(0, result=None))
                continue
            r1_result = json.loads(r1_path.read_text(encoding="utf-8"))
            policy = _r2_policy_from_args(args, r1_result)
            mode = policy.get("mode")
            if mode not in ROUND2_MODES:
                policy["mode"] = "full"
                mode = "full"

            if mode == "skip":
                r2_jobs.append(
                    write_round2_skip_marker(
                        pid=pid,
                        pdf_path=paper["pdf_path"],
                        r1_result=r1_result,
                        output_dir=r2_dir,
                        policy=policy,
                    )
                )
            else:
                r2_jobs.append(
                    run_round2_paper(
                        pid=pid,
                        pdf_path=paper["pdf_path"],
                        paper_meta=paper["meta"],
                        ontology=ontology,
                        r1_result=r1_result,
                        provider_map=provider_map,
                        output_dir=r2_dir,
                        semaphore=semaphore,
                        max_text_chars=args.max_text_chars,
                        policy=policy,
                        node_top_k=args.node_top_k,
                    )
                )

        r2_results = await asyncio.gather(*r2_jobs)
        logger.info("[R2] 完成 %s/%s", sum(r is not None for r in r2_results), len(papers))

    merged_records: list[dict[str, Any]] = []
    for paper in papers:
        pid = paper["pid"]
        r1_path = r1_dir / f"paper-{pid}.json"
        r2_path = r2_dir / f"paper-{pid}.json"
        r1_result = _read_json(r1_path) if r1_path.exists() else None
        r2_result = _read_json(r2_path) if r2_path.exists() else None
        if r1_result is None:
            continue
        merged = merge_paper_result(pid, paper["pdf_path"], r1_result, r2_result)
        record = build_fullpaper_merge_record(merged, paper)
        merged_records.append(record)
        (merged_dir / f"paper-{pid}.json").write_text(
            json.dumps(record, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    summary = generate_summary(merged_records)
    (output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output_dir / "report.md").write_text(
        generate_report(merged_records, summary),
        encoding="utf-8",
    )
    logger.info("输出目录：%s", output_dir)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="1920 篇全量五轴位置归属度两轮评估")
    parser.add_argument("--round", type=int, choices=[1, 2], default=None)
    parser.add_argument("--pid", type=int)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--paper-range", type=str, default=None)
    parser.add_argument("--stage0-sample-size", type=int, default=None)
    parser.add_argument(
        "--journal",
        action="append",
        default=None,
        help="按期刊筛选，可重复传入",
    )
    parser.add_argument(
        "--exclude-output-dir",
        action="append",
        type=Path,
        default=None,
        help="排除该输出目录 merged/ 中已存在的 paper-*.json，可重复传入",
    )
    parser.add_argument("--concurrency", type=int, default=CONCURRENT_PAPERS)
    parser.add_argument("--r2-policy", choices=sorted(ROUND2_POLICIES), default="auto")
    parser.add_argument("--metadata", type=Path, default=METADATA_PATH)
    parser.add_argument("--paper-dir", type=Path, default=PAPER_DIR)
    parser.add_argument("--eval-dir", type=Path, default=SIX_DIM_EVAL_DIR)
    parser.add_argument("--round1-dir", type=Path, default=SIX_DIM_ROUND1_DIR)
    parser.add_argument("--round1-err-dir", type=Path, default=SIX_DIM_ROUND1_ERR_DIR)
    parser.add_argument("--knowledge", type=Path, default=KNOWLEDGE_PATH)
    parser.add_argument("--ontology", type=Path, default=ONTOLOGY_PATH)
    parser.add_argument("--rebuild-ontology", action="store_true")
    parser.add_argument("--node-top-k", type=int, default=30)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--max-text-chars", type=int, default=MAX_TEXT_CHARS)
    return parser.parse_args()


def main() -> None:
    asyncio.run(run_evaluation(parse_args()))


if __name__ == "__main__":
    main()
