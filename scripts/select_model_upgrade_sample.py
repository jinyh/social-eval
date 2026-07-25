#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

JOURNALS = ("中国法学", "法学研究", "中国社会科学")


def _quartiles(rows: list[dict]) -> dict[int, int]:
    ordered = sorted(rows, key=lambda item: (item["ccb_score"], item["paper_id"]))
    count = len(ordered)
    return {
        row["paper_id"]: min(4, (index * 4 // count) + 1)
        for index, row in enumerate(ordered)
    }


def _stable_order(seed: str, paper_id: int) -> str:
    return hashlib.sha256(f"{seed}:{paper_id}".encode()).hexdigest()


def select_sample(
    metadata_path: Path,
    ranking_path: Path,
    results_dir: Path,
    *,
    seed: str,
    per_journal: int = 8,
) -> list[dict]:
    metadata = {
        int(row["编号"]): row
        for row in csv.DictReader(metadata_path.open(encoding="utf-8-sig"))
        if row.get("analysis_included", "yes") == "yes"
    }
    ranking = json.loads(ranking_path.read_text(encoding="utf-8"))
    candidates_by_journal: dict[str, list[dict]] = defaultdict(list)
    for item in ranking["papers"]:
        paper_id = int(item["pid"])
        meta = metadata.get(paper_id)
        result_path = results_dir / f"paper-{paper_id}.json"
        if meta is None or meta["期刊"] not in JOURNALS or not result_path.exists():
            continue
        historical = json.loads(result_path.read_text(encoding="utf-8"))
        max_std = float(historical.get("overall", {}).get("round2_max_std") or 0)
        candidates_by_journal[meta["期刊"]].append(
            {
                "paper_id": paper_id,
                "journal": meta["期刊"],
                "year": int(meta["年份"]),
                "title": meta["题目"],
                "ccb_score": float(item["weighted_score"]),
                "historical_max_std": max_std,
                "high_divergence": max_std > 8,
                "historical_result_path": str(result_path),
                "source_path": historical["paper"],
            }
        )

    targets = {
        journal: min(per_journal, len(candidates_by_journal[journal]))
        for journal in JOURNALS
    }
    deficit = per_journal * len(JOURNALS) - sum(targets.values())
    for journal in JOURNALS:
        if deficit == 0:
            break
        spare = len(candidates_by_journal[journal]) - targets[journal]
        addition = min(spare, deficit)
        targets[journal] += addition
        deficit -= addition
    if deficit:
        raise ValueError("三大刊候选池不足以组成 24 篇样本")

    selected: list[dict] = []
    for journal in JOURNALS:
        pool = candidates_by_journal[journal]
        quartiles = _quartiles(pool)
        strata: dict[tuple[int, bool], list[dict]] = defaultdict(list)
        for row in pool:
            row["ccb_quartile"] = quartiles[row["paper_id"]]
            strata[(row["ccb_quartile"], row["high_divergence"])].append(row)
        for rows in strata.values():
            rows.sort(key=lambda item: _stable_order(seed, item["paper_id"]))
        journal_rows = []
        keys = [
            (quartile, divergence)
            for quartile in range(1, 5)
            for divergence in (True, False)
        ]
        while len(journal_rows) < targets[journal]:
            progressed = False
            for key in keys:
                if strata[key] and len(journal_rows) < targets[journal]:
                    journal_rows.append(strata[key].pop(0))
                    progressed = True
            if not progressed:
                raise ValueError(f"{journal} 没有足够候选样本")
        selected.extend(journal_rows)

    selected.sort(key=lambda item: (JOURNALS.index(item["journal"]), item["paper_id"]))
    for journal in JOURNALS:
        journal_rows = [row for row in selected if row["journal"] == journal]
        for index, row in enumerate(journal_rows):
            row["execution_batch"] = 1 if index < 2 else 2 if index < 5 else 3
            row["full_framework_closure"] = index < 2
    return selected


def main() -> None:
    parser = argparse.ArgumentParser(
        description="按权威元数据、综合参考分四分位和历史分歧抽取三大刊配对样本。"
    )
    parser.add_argument(
        "--metadata",
        type=Path,
        default=Path("results/datasets/three-journals/metadata.csv"),
    )
    parser.add_argument(
        "--ranking",
        type=Path,
        default=Path("results/rankings/e2-ccb-v5/ranking.json"),
    )
    parser.add_argument(
        "--results-dir",
        type=Path,
        default=Path(
            "results/datasets/three-journals/six-dimension/phase2-r2-v2.55/per-paper"
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("output/model-upgrade/paired-sample-manifest.json"),
    )
    parser.add_argument("--seed", default="socialeval-model-upgrade-2026-07")
    args = parser.parse_args()
    rows = select_sample(
        args.metadata,
        args.ranking,
        args.results_dir,
        seed=args.seed,
    )
    payload = {
        "schema_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "purpose": "三大刊新旧模型配对对比",
        "authoritative_metadata": str(args.metadata),
        "selection_seed": args.seed,
        "sample_count": len(rows),
        "journal_counts": {
            journal: sum(row["journal"] == journal for row in rows)
            for journal in JOURNALS
        },
        "journal_balance_note": (
            "E2 候选池中中国社会科学仅 7 篇，缺额按冻结规则顺延至"
            "候选池充足的期刊；未伪造或补算 E2 候选。"
        ),
        "framework_isolation": "configs/frameworks/law-v2.55-cross-review.yaml",
        "framework_closure": "configs/frameworks/law-v2.56.6-20260522.yaml",
        "baseline_models": ["glm-5.1", "qwen3.6-plus"],
        "candidate_models": ["glm-5.2", "qwen3.7-max-2026-06-08"],
        "candidate_model_parameters": {
            "glm-5.2": {
                "temperature": 0.3,
            },
            "qwen3.7-max-2026-06-08": {
                "temperature": 0.3,
                "enable_thinking": True,
                "thinking_budget": 4096,
                "max_completion_tokens": 8192,
            },
        },
        "execution_batches": [6, 9, 9],
        "records": rows,
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()
    payload["manifest_sha256"] = hashlib.sha256(canonical).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"selected={len(rows)} output={args.output}")


if __name__ == "__main__":
    main()
