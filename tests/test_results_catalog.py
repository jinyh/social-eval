import csv
import json
import re
from collections import Counter
from pathlib import Path

import yaml

RESULTS = Path("results")


def _csv_count(path: Path) -> int:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return sum(1 for _ in csv.DictReader(handle))


def test_dataset_catalog_counts_match_materialized_summaries():
    expected = {"three-journals": 1920, "jiaodafaxue": 642, "xueshuyuekan": 149}

    for dataset, count in expected.items():
        base = RESULTS / "datasets" / dataset
        manifest = yaml.safe_load((base / "manifest.yaml").read_text(encoding="utf-8"))
        assert manifest["six_dimension"]["count"] == count
        assert manifest["five_axis"]["count"] == count
        assert _csv_count(base / manifest["six_dimension"]["summary"]) == count
        assert _csv_count(base / manifest["five_axis"]["summary"]) == count


def test_all_papers_ranking_has_canonical_and_deduplicated_views():
    ranking_dir = RESULTS / "rankings" / "all-papers-ccb-v1"
    historical = json.loads((ranking_dir / "ranking.json").read_text(encoding="utf-8"))
    analysis = json.loads(
        (ranking_dir / "ranking-deduplicated.json").read_text(encoding="utf-8")
    )

    assert len(historical["papers"]) == 1920
    assert len(analysis["papers"]) == 1916
    assert Counter(row["source"] for row in historical["papers"]) == {
        "E1": 1815,
        "E1+E2": 105,
    }
    assert max(row["ccb_score"] for row in historical["papers"]) <= 100


def test_r1_linkage_audit_records_known_mismatches_without_rerun():
    audit = json.loads(
        (RESULTS / "reports/current/r1-linkage-audit.json").read_text(encoding="utf-8")
    )

    assert audit["exact_matches"] == 1760
    assert audit["mismatches"] == 160
    assert audit["missing"] == 0
    assert len(audit["mismatch_paper_ids"]) == 160


def test_e2_ranking_uses_complete_e1_e2_pool_for_every_dimension():
    ranking = json.loads(
        (RESULTS / "rankings/e2-ccb-v5/ranking.json").read_text(encoding="utf-8")
    )
    pool = json.loads(
        (RESULTS / "rankings/e2-ccb-v5/pool.json").read_text(encoding="utf-8")
    )

    assert {paper["pid"] for paper in ranking["papers"]} == {
        paper["id"] for paper in pool
    }
    assert len(ranking["papers"]) == 105
    for paper in ranking["papers"]:
        assert len(paper["dimensions"]) == 6
        for dimension in paper["dimensions"].values():
            assert dimension["pooled_n"] == 8
            assert dimension["method"] == "median(8) [E1+E2]"


def test_top50_json_and_expert_markdown_have_identical_order():
    base = RESULTS / "rankings/e2-ccb-v5"
    top50 = json.loads((base / "top50-proportional.json").read_text(encoding="utf-8"))
    markdown = (base / "top50-ccb-list.md").read_text(encoding="utf-8")
    markdown_ids: list[int] = []
    for line in markdown.splitlines():
        match = re.match(r"\|\s*(\d+)\s*\|\s*(\d+)\s*\|", line)
        if match and int(match.group(1)) == len(markdown_ids) + 1:
            markdown_ids.append(int(match.group(2)))
            if len(markdown_ids) == 50:
                break

    assert markdown_ids == [paper["pid"] for paper in top50["papers"]]


def test_model_upgrade_summary_records_complete_pairing_and_open_closure_gate():
    summary = json.loads(
        (RESULTS / "reports/current/model-upgrade-paired-24-summary.json").read_text(
            encoding="utf-8"
        )
    )

    assert summary["sample_count"] == 24
    assert summary["completed_paper_count"] == 24
    assert summary["missing_paper_count"] == 0
    assert summary["full_framework_closure"] == {
        "required_sample_count": 6,
        "completed_sample_count": 1,
        "status": "incomplete",
    }
