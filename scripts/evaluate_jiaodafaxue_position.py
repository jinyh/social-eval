#!/usr/bin/env python3
"""交大法学期刊五轴位置归属度两轮评价（R1 + R2）

对 raw/jiaodafaxue/ 下 final_score > 阈值的论文执行五轴位置归属度评估：
- Round 1：deepseek-v4-pro / qwen3.7-max-2026-06-08 独立五轴评估
- Round 2：按 R1 分歧条件触发（skip / light / full）
- Merge：逐轴保守聚合

评估口径来自：
docs/evaluation/autonomous-knowledge-system-position-assessment-v0.2.md

用法：
    # 全量执行（R1 + R2）
    python scripts/evaluate_jiaodafaxue_position.py

    # 只跑前 5 篇测试
    python scripts/evaluate_jiaodafaxue_position.py --limit 5

    # 指定分数阈值（默认 55）
    python scripts/evaluate_jiaodafaxue_position.py --min-score 60

    # 只跑 R1
    python scripts/evaluate_jiaodafaxue_position.py --round 1

    # 只跑 R2（R1 已完成）
    python scripts/evaluate_jiaodafaxue_position.py --round 2

    # Dry-run 单篇
    python scripts/evaluate_jiaodafaxue_position.py --dry-run --pid 586

    # 强制所有论文做 R2
    python scripts/evaluate_jiaodafaxue_position.py --r2-policy all
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.evaluation.position.workflow import (
    AXIS_KEYS,
    ROUTE_VALUES,
    SEVERE_DISPUTE_AXES,
    ROUND2_MODES,
    MAX_KNOWLEDGE_CHARS,
    aggregate_final_assessment,
    build_round1_prompt,
    build_round2_prompt,
    build_light_round2_prompt,
    decide_round2_policy,
    merge_paper_result,
    normalize_assessment,
    retrieved_nodes_from_result,
    write_round2_skip_marker,
)
from src.knowledge.law_ontology import (
    LawOntology,
    load_law_ontology,
    parse_law_tree_markdown,
    write_law_ontology,
)
from src.knowledge.node_retrieval import RetrievedNode, retrieve_nodes

# ── 配置 ──────────────────────────────────────────────

PAPER_LIST_PATH = Path("results/datasets/jiaodafaxue/metadata.json")
EVAL_DIR = Path(
    "results/datasets/jiaodafaxue/six-dimension/phase2-r2-v2.55/per-paper"
)
KNOWLEDGE_PATH = Path("knowledge/中国法学自主知识体系-树状知识库.md")
ONTOLOGY_PATH = Path("knowledge/law_ontology.json")
OUTPUT_DIR = Path("results/runs/jiaodafaxue-position")

MODELS = ["deepseek-v4-pro", "qwen3.7-max-2026-06-08"]
CONCURRENT_PAPERS = 5
MAX_TEXT_CHARS = 50_000
DEFAULT_MIN_SCORE = 55

logger = logging.getLogger("jiaodafaxue-position")


# ── 日志 ──────────────────────────────────────────────


def setup_logging(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    log_file = output_dir / "execution.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )


# ── 数据加载 ─────────────────────────────────────────


def parse_md_filename(filename: str) -> dict[str, str]:
    """从 md 文件名提取元数据。

    格式1: {numeric_id}_{authors}_{year}_{journal}_{title}.md
    格式2: {JDFX_id}_{authors}_{year}_{journal}_{title}.md
    """
    stem = filename.replace(".md", "")
    parts = stem.split("_", 4)
    if len(parts) >= 5:
        return {
            "file_id": parts[0],
            "作者": parts[1],
            "年份": parts[2],
            "期刊": parts[3],
            "题目": parts[4],
        }
    return {"题目": stem}


def load_eligible_papers(
    paper_list_path: Path,
    eval_dir: Path,
    min_score: float,
    paper_range: str | None = None,
    limit: int | None = None,
    dry_run_pid: int | None = None,
) -> list[dict[str, Any]]:
    """加载满足分数阈值的论文列表。"""
    with open(paper_list_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    papers = data["papers"]

    # 构建 eval 分数索引
    score_index: dict[int, float] = {}
    for eval_file in eval_dir.glob("paper-*.json"):
        pid = int(eval_file.stem.replace("paper-", ""))
        try:
            result = json.loads(eval_file.read_text(encoding="utf-8"))
            score = result.get("overall", {}).get("round2_final_score_mean")
            if score is None:
                score = result.get("overall", {}).get("round1_final_score_mean")
            if score is not None:
                score_index[pid] = float(score)
        except (json.JSONDecodeError, OSError):
            continue

    eligible = []
    for paper in papers:
        pid = paper["id"]
        score = score_index.get(pid)
        if score is None or score <= min_score:
            continue
        meta = parse_md_filename(paper["filename"])
        eligible.append({
            "pid": pid,
            "path": paper["path"],
            "score": score,
            "meta": meta,
        })

    eligible.sort(key=lambda x: x["score"], reverse=True)

    logger.info(
        "论文筛选：%d/%d 篇满足 final_score > %.1f",
        len(eligible), len(papers), min_score,
    )

    if dry_run_pid:
        eligible = [p for p in eligible if p["pid"] == dry_run_pid]
        if not eligible:
            raise SystemExit(f"PID {dry_run_pid} 不满足条件或未找到")
    elif paper_range:
        start, end = map(int, paper_range.split("-"))
        eligible = eligible[start - 1:end]
    elif limit:
        eligible = eligible[:limit]

    return eligible


# ── 知识库 ────────────────────────────────────────────


def load_or_build_ontology(
    knowledge_path: Path,
    ontology_path: Path,
    rebuild: bool = False,
) -> LawOntology:
    if not rebuild and ontology_path.exists():
        return load_law_ontology(ontology_path)
    md_text = knowledge_path.read_text(encoding="utf-8")
    ontology = parse_law_tree_markdown(md_text)
    write_law_ontology(ontology, ontology_path)
    return ontology


# ── 文本读取 ──────────────────────────────────────────


def read_md_text(path: Path, max_chars: int = MAX_TEXT_CHARS) -> str:
    text = path.read_text(encoding="utf-8")
    if len(text) > max_chars:
        text = text[:max_chars]
    return text


# ── 模型调用 ──────────────────────────────────────────


def _provider_map(model_names: list[str]) -> dict[str, Any]:
    from src.evaluation.providers.factory import create_providers

    providers = create_providers(model_names)
    return {provider.model_name: provider for provider in providers}


async def call_model(
    model_name: str,
    prompt: str,
    provider_map: dict[str, Any],
) -> dict[str, Any]:
    provider = provider_map.get(model_name)
    if provider is None:
        return {"error": f"Provider {model_name} 未找到", "model": model_name}
    start = time.time()
    try:
        result = await provider.generate_json_response(prompt)
        normalized = normalize_assessment(result)
        normalized["elapsed_seconds"] = round(time.time() - start, 1)
        return normalized
    except Exception as exc:  # noqa: BLE001
        logger.error("模型 %s 调用失败：%s", model_name, exc)
        return {
            "error": str(exc),
            "model": model_name,
            "elapsed_seconds": round(time.time() - start, 1),
        }


# ── 节点检索辅助 ──────────────────────────────────────


def query_text_for_retrieval(meta: dict[str, str], paper_text: str) -> str:
    title = meta.get("题目", "")
    snippet = paper_text[:500]
    return f"{title}\n{snippet}"


def discipline_hint_from_meta(meta: dict[str, str]) -> str | None:
    return meta.get("专家审阅学科") or meta.get("discipline")


def format_retrieved_nodes_for_prompt(nodes: list[RetrievedNode]) -> str:
    if not nodes:
        return "（未检索到候选知识体系节点）"
    lines = []
    for i, node in enumerate(nodes[:15], 1):
        label = node.label or node.node_id
        path_str = " > ".join(node.path) if node.path else ""
        lines.append(f"{i}. [{node.node_id}] {label}（{path_str}）")
    return "\n".join(lines)


# ── Round 1 ───────────────────────────────────────────


async def run_round1_paper(
    pid: int,
    paper_path: Path,
    meta: dict[str, str],
    ontology: LawOntology,
    provider_map: dict[str, Any],
    output_dir: Path,
    semaphore: asyncio.Semaphore,
    max_text_chars: int,
    node_top_k: int,
) -> dict[str, Any] | None:
    output_path = output_dir / f"paper-{pid}.json"
    if output_path.exists():
        logger.info("[R1] PID=%s 跳过（已存在）", pid)
        return json.loads(output_path.read_text(encoding="utf-8"))

    async with semaphore:
        logger.info("[R1] PID=%s %s 开始", pid, paper_path.name[:60])
        start = time.time()

        try:
            paper_text = read_md_text(paper_path, max_text_chars)
        except Exception as exc:  # noqa: BLE001
            logger.error("[R1] PID=%s 读取失败：%s", pid, exc)
            return None

        if not paper_text.strip():
            logger.error("[R1] PID=%s 文本为空", pid)
            return None

        retrieved_nodes = retrieve_nodes(
            query_text_for_retrieval(meta, paper_text),
            ontology,
            discipline_hint=discipline_hint_from_meta(meta),
            top_k=node_top_k,
        )
        node_candidates_text = format_retrieved_nodes_for_prompt(retrieved_nodes)

        prompt = build_round1_prompt(
            paper_meta=meta,
            paper_text=paper_text,
            knowledge_excerpt="",
            max_text_chars=max_text_chars,
            node_candidates_text=node_candidates_text,
        )

        outputs = await asyncio.gather(
            *[call_model(model, prompt, provider_map) for model in MODELS]
        )

        result = {
            "paper_id": pid,
            "paper": paper_path.name,
            "timestamp": datetime.now().isoformat(),
            "node_retrieval_candidates": [n.to_dict() for n in retrieved_nodes],
            "models": dict(zip(MODELS, outputs, strict=False)),
            "elapsed_seconds": round(time.time() - start, 1),
        }

        valid = {m: o for m, o in result["models"].items() if "error" not in o}
        if valid:
            result["aggregate_preview"] = aggregate_final_assessment(valid)

        output_dir.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info("[R1] PID=%s 完成 (%.1fs)", pid, result["elapsed_seconds"])
        return result


# ── Round 2 ───────────────────────────────────────────


async def run_round2_paper(
    pid: int,
    paper_path: Path,
    meta: dict[str, str],
    ontology: LawOntology,
    r1_result: dict[str, Any],
    provider_map: dict[str, Any],
    output_dir: Path,
    semaphore: asyncio.Semaphore,
    max_text_chars: int,
    policy: dict[str, Any],
    node_top_k: int,
) -> dict[str, Any] | None:
    """R2 交叉评审（适配 .md 文件）。"""
    mode = str(policy.get("mode", "full"))
    if mode not in ROUND2_MODES:
        mode = "full"

    output_path = output_dir / f"paper-{pid}.json"
    if output_path.exists():
        logger.info("[R2] PID=%s 跳过（已存在）", pid)
        return json.loads(output_path.read_text(encoding="utf-8"))

    r1_models = r1_result.get("models", {})
    if any("error" in r1_models.get(model, {"error": "missing"}) for model in MODELS):
        logger.warning("[R2] PID=%s R1 不完整，跳过", pid)
        return None

    async with semaphore:
        logger.info("[R2:%s] PID=%s %s 开始", mode, pid, paper_path.name[:60])
        start = time.time()
        prompts = []

        if mode == "light":
            retrieved_nodes = retrieved_nodes_from_result(r1_result)
            node_candidates_text = format_retrieved_nodes_for_prompt(retrieved_nodes)
            for index, model_name in enumerate(MODELS):
                other_model_name = MODELS[1 - index]
                prompts.append(
                    build_light_round2_prompt(
                        paper_meta=meta,
                        knowledge_excerpt="",
                        self_r1_output=r1_models[model_name],
                        other_r1_output=r1_models[other_model_name],
                        model_name=model_name,
                        other_model_name=other_model_name,
                        node_candidates_text=node_candidates_text,
                    )
                )
        else:  # full
            try:
                paper_text = read_md_text(paper_path, max_text_chars)
            except Exception as exc:  # noqa: BLE001
                logger.error("[R2] PID=%s 读取失败：%s", pid, exc)
                return None
            if not paper_text.strip():
                logger.error("[R2] PID=%s 文本为空", pid)
                return None

            retrieved_nodes = retrieve_nodes(
                query_text_for_retrieval(meta, paper_text),
                ontology,
                discipline_hint=discipline_hint_from_meta(meta),
                top_k=node_top_k,
            )
            node_candidates_text = format_retrieved_nodes_for_prompt(retrieved_nodes)
            for index, model_name in enumerate(MODELS):
                other_model_name = MODELS[1 - index]
                prompts.append(
                    build_round2_prompt(
                        paper_meta=meta,
                        paper_text=paper_text,
                        knowledge_excerpt="",
                        self_r1_output=r1_models[model_name],
                        other_r1_output=r1_models[other_model_name],
                        model_name=model_name,
                        other_model_name=other_model_name,
                        max_text_chars=max_text_chars,
                        node_candidates_text=node_candidates_text,
                    )
                )

        outputs = await asyncio.gather(
            *[call_model(model, prompt, provider_map)
              for model, prompt in zip(MODELS, prompts)]
        )

        result = {
            "paper_id": pid,
            "paper": paper_path.name,
            "timestamp": datetime.now().isoformat(),
            "round2_mode": mode,
            "round2_policy": policy,
            "node_retrieval_candidates": [
                n.to_dict() if hasattr(n, "to_dict") else n
                for n in retrieved_nodes
            ],
            "models": dict(zip(MODELS, outputs, strict=False)),
            "elapsed_seconds": round(time.time() - start, 1),
        }

        valid = {m: o for m, o in result["models"].items() if "error" not in o}
        if valid:
            result["aggregate_preview"] = aggregate_final_assessment(valid)

        output_dir.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info("[R2:%s] PID=%s 完成 (%.1fs)", mode, pid, result["elapsed_seconds"])
        return result


# ── 汇总报告 ──────────────────────────────────────────


def generate_summary_report(
    merged_dir: Path,
    papers: list[dict[str, Any]],
) -> None:
    """生成分布摘要 markdown 和 JSON。"""
    results = []
    for paper in papers:
        pid = paper["pid"]
        path = merged_dir / f"paper-{pid}.json"
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        final = data.get("final") or {}
        r2_mode = data.get("round2_mode", "not_run")
        results.append({
            "pid": pid,
            "six_dim_score": paper["score"],
            "total_score": final.get("total_score", 0),
            "strength": final.get("strength", "absent"),
            "route": final.get("research_route", {}).get("primary", ""),
            "r2_mode": r2_mode,
            "review_required": final.get("review_required", False),
            "title": paper["meta"].get("题目", "")[:40],
        })

    if not results:
        logger.warning("无合并结果，跳过摘要生成")
        return

    results.sort(key=lambda x: x["total_score"], reverse=True)

    score_dist = Counter(r["total_score"] for r in results)
    strength_dist = Counter(r["strength"] for r in results)
    route_dist = Counter(r["route"] for r in results)
    r2_mode_dist = Counter(r["r2_mode"] for r in results)

    lines = [
        "# 交大法学期刊五轴位置归属度评估摘要",
        "",
        f"评估时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"论文总数：{len(results)} 篇",
        f"模型：{', '.join(MODELS)}",
        "方法论：position_assessment_v0.3",
        "",
        "## 分数分布",
        "",
        "| 总分 | 数量 |",
        "|------|------|",
    ]
    for score in sorted(score_dist.keys(), reverse=True):
        lines.append(f"| {score} | {score_dist[score]} |")

    lines += [
        "",
        "## 强度分档分布",
        "",
        "| 强度 | 分数范围 | 数量 | 占比 |",
        "|------|----------|------|------|",
    ]
    for band, range_label in [("strong", "8-10"), ("medium", "5-7"), ("weak", "2-4"), ("absent", "0-1")]:
        count = strength_dist.get(band, 0)
        pct = count / len(results) * 100 if results else 0
        lines.append(f"| {band} | {range_label} | {count} | {pct:.1f}% |")

    lines += [
        "",
        "## R2 策略分布",
        "",
        "| 策略 | 数量 | 占比 |",
        "|------|------|------|",
    ]
    for mode in ("skip", "light", "full", "not_run"):
        count = r2_mode_dist.get(mode, 0)
        if count > 0:
            pct = count / len(results) * 100
            lines.append(f"| {mode} | {count} | {pct:.1f}% |")

    lines += [
        "",
        "## 研究路径分布",
        "",
        "| 路径 | 数量 | 占比 |",
        "|------|------|------|",
    ]
    for route, count in route_dist.most_common():
        pct = count / len(results) * 100
        lines.append(f"| {route} | {count} | {pct:.1f}% |")

    lines += [
        "",
        "## 论文明细",
        "",
        "| # | PID | 六维分 | 五轴分 | 强度 | 路径 | R2 | 题目 |",
        "|---|-----|--------|--------|------|------|----|------|",
    ]
    for i, r in enumerate(results, 1):
        lines.append(
            f"| {i} | {r['pid']} | {r['six_dim_score']:.1f} | "
            f"{r['total_score']} | {r['strength']} | "
            f"{r['route']} | {r['r2_mode']} | {r['title']} |"
        )

    summary_md = merged_dir / "summary.md"
    summary_md.write_text("\n".join(lines), encoding="utf-8")
    logger.info("摘要 Markdown：%s", summary_md)

    summary_json = {
        "total_papers": len(results),
        "timestamp": datetime.now().isoformat(),
        "score_distribution": dict(score_dist),
        "strength_distribution": dict(strength_dist),
        "route_distribution": dict(route_dist),
        "r2_mode_distribution": dict(r2_mode_dist),
        "avg_total_score": round(sum(r["total_score"] for r in results) / len(results), 2),
        "avg_six_dim_score": round(sum(r["six_dim_score"] for r in results) / len(results), 2),
    }
    summary_json_path = merged_dir / "summary.json"
    summary_json_path.write_text(
        json.dumps(summary_json, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info("摘要 JSON：%s", summary_json_path)


# ── 主流程 ────────────────────────────────────────────


async def run_evaluation(args: argparse.Namespace) -> None:
    output_dir = args.output_dir
    r1_dir = output_dir / "round1"
    r2_dir = output_dir / "round2"
    merged_dir = output_dir / "merged"
    for d in (r1_dir, r2_dir, merged_dir):
        d.mkdir(parents=True, exist_ok=True)

    setup_logging(output_dir)

    logger.info("交大法学期刊五轴位置归属度评估启动")
    logger.info("模型：%s", ", ".join(MODELS))
    logger.info("论文并发：%s", args.concurrency)
    logger.info("分数阈值：> %.1f", args.min_score)
    logger.info("R2 策略：%s", args.r2_policy)

    papers = load_eligible_papers(
        paper_list_path=args.paper_list,
        eval_dir=args.eval_dir,
        min_score=args.min_score,
        paper_range=args.paper_range,
        limit=args.limit,
        dry_run_pid=args.pid if args.dry_run else None,
    )
    logger.info("待评估论文：%d 篇", len(papers))
    if not papers:
        logger.warning("无满足条件的论文，退出")
        return

    ontology = load_or_build_ontology(
        args.knowledge, args.ontology, rebuild=args.rebuild_ontology,
    )
    logger.info("Ontology 节点数：%s", len(ontology.nodes))

    provider_map = _provider_map(MODELS)
    semaphore = asyncio.Semaphore(args.concurrency)

    # ── Round 1 ──
    r1_results: dict[int, dict[str, Any] | None] = {}

    if args.round in (None, 1):
        r1_list = await asyncio.gather(
            *[
                run_round1_paper(
                    pid=paper["pid"],
                    paper_path=Path(paper["path"]),
                    meta=paper["meta"],
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
        r1_results = {
            paper["pid"]: result
            for paper, result in zip(papers, r1_list)
        }
        success = sum(r is not None for r in r1_results.values())
        logger.info("[R1] 完成 %d/%d", success, len(papers))

    # ── Round 2 ──
    if args.round in (None, 2):
        r2_jobs = []
        for paper in papers:
            pid = paper["pid"]
            paper_path = Path(paper["path"])

            r1_path = r1_dir / f"paper-{pid}.json"
            if not r1_path.exists():
                logger.warning("[R2] PID=%s 缺少 R1，跳过", pid)
                r2_jobs.append(asyncio.sleep(0, result=None))
                continue

            r1_data = json.loads(r1_path.read_text(encoding="utf-8"))

            if args.r2_policy == "all":
                policy = {
                    "mode": "full",
                    "reason": "forced_full_round2",
                    "reasons": ["forced_full_round2"],
                    "axis_disagreements": [],
                }
            elif args.r2_policy == "skip":
                policy = {
                    "mode": "skip",
                    "reason": "forced_skip_round2",
                    "reasons": ["forced_skip_round2"],
                    "axis_disagreements": [],
                }
            else:
                policy = decide_round2_policy(r1_data)

            mode = policy.get("mode")
            if mode == "skip":
                r2_jobs.append(
                    write_round2_skip_marker(
                        pid=pid,
                        pdf_path=paper_path,
                        r1_result=r1_data,
                        output_dir=r2_dir,
                        policy=policy,
                    )
                )
                continue

            r2_jobs.append(
                run_round2_paper(
                    pid=pid,
                    paper_path=paper_path,
                    meta=paper["meta"],
                    ontology=ontology,
                    r1_result=r1_data,
                    provider_map=provider_map,
                    output_dir=r2_dir,
                    semaphore=semaphore,
                    max_text_chars=args.max_text_chars,
                    policy=policy,
                    node_top_k=args.node_top_k,
                )
            )

        r2_list = await asyncio.gather(*r2_jobs)
        r2_success = sum(r is not None for r in r2_list)
        logger.info("[R2] 完成 %d/%d", r2_success, len(papers))

    # ── Merge ──
    merge_count = 0
    merged_results = []
    for paper in papers:
        pid = paper["pid"]
        paper_path = Path(paper["path"])

        r1_path = r1_dir / f"paper-{pid}.json"
        r2_path = r2_dir / f"paper-{pid}.json"

        r1_data = None
        r2_data = None
        if r1_path.exists():
            r1_data = json.loads(r1_path.read_text(encoding="utf-8"))
        if r2_path.exists():
            r2_data = json.loads(r2_path.read_text(encoding="utf-8"))

        if r1_data is None:
            continue

        merged = merge_paper_result(
            pid=pid,
            pdf_path=paper_path,
            r1_result=r1_data,
            r2_result=r2_data,
        )

        merged_path = merged_dir / f"paper-{pid}.json"
        merged_path.write_text(
            json.dumps(merged, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        merged_results.append(merged)
        merge_count += 1

    logger.info("[Merge] 合并 %d 篇", merge_count)

    generate_summary_report(merged_dir, papers)


def main() -> None:
    parser = argparse.ArgumentParser(description="交大法学期刊五轴位置归属度两轮评估")
    parser.add_argument(
        "--paper-list", type=Path, default=PAPER_LIST_PATH,
        help="论文列表 JSON",
    )
    parser.add_argument(
        "--eval-dir", type=Path, default=EVAL_DIR,
        help="六维评审结果目录（用于分数过滤）",
    )
    parser.add_argument(
        "--output-dir", type=Path, default=OUTPUT_DIR,
        help="输出目录",
    )
    parser.add_argument(
        "--knowledge", type=Path, default=KNOWLEDGE_PATH,
        help="知识体系 Markdown",
    )
    parser.add_argument(
        "--ontology", type=Path, default=ONTOLOGY_PATH,
        help="Ontology JSON 缓存",
    )
    parser.add_argument(
        "--rebuild-ontology", action="store_true",
        help="强制重建 ontology 缓存",
    )
    parser.add_argument(
        "--min-score", type=float, default=DEFAULT_MIN_SCORE,
        help="六维评审分数阈值（默认 55）",
    )
    parser.add_argument(
        "--concurrency", type=int, default=CONCURRENT_PAPERS,
        help="论文并发数（默认 5）",
    )
    parser.add_argument(
        "--max-text-chars", type=int, default=MAX_TEXT_CHARS,
        help="论文正文截断字符数",
    )
    parser.add_argument(
        "--node-top-k", type=int, default=10,
        help="知识体系节点检索 Top-K",
    )
    parser.add_argument(
        "--round", type=int, choices=[1, 2], default=None,
        help="只跑指定轮次（1=R1, 2=R2）",
    )
    parser.add_argument(
        "--r2-policy", choices=["auto", "all", "skip"], default="auto",
        help="R2 策略：auto=按分歧触发, all=全跑, skip=全跳过",
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="只评估前 N 篇（按六维分降序）",
    )
    parser.add_argument(
        "--paper-range", type=str, default=None,
        help="按排序位置范围选择，如 1-10",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="单篇测试模式",
    )
    parser.add_argument(
        "--pid", type=int, default=None,
        help="dry-run 时指定 PID",
    )
    args = parser.parse_args()
    asyncio.run(run_evaluation(args))


if __name__ == "__main__":
    main()
