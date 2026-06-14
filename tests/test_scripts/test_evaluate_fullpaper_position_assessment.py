import csv
import json
from pathlib import Path

from scripts.evaluate_fullpaper_position_assessment import (
    build_fullpaper_merge_record,
    filter_papers_by_journal,
    load_fullpaper_papers,
    remove_papers_already_in_output,
    select_stage0_sample,
)


def _write_metadata(path: Path, rows: list[dict[str, str]]) -> None:
    fieldnames = ["编号", "期刊", "年份", "题目", "作者", "分类", "主题词"]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def test_load_fullpaper_papers_uses_metadata_ids_without_score_filtering(tmp_path):
    metadata_path = tmp_path / "merged-metadata.csv"
    paper_dir = tmp_path / "fullpaper"
    eval_dir = tmp_path / "round2"
    paper_dir.mkdir()
    eval_dir.mkdir()

    _write_metadata(
        metadata_path,
        [
            {
                "编号": "1",
                "期刊": "中国法学",
                "年份": "2025",
                "题目": "高分论文",
                "作者": "甲",
                "分类": "知识产权法学",
                "主题词": "AIGC",
            },
            {
                "编号": "2",
                "期刊": "法学研究",
                "年份": "2016",
                "题目": "低分但强归属论文",
                "作者": "乙",
                "分类": "国际法学",
                "主题词": "中国实践",
            },
        ],
    )
    (paper_dir / "0001-中国法学-2025-2-高分论文-甲.pdf").write_text("x")
    (paper_dir / "0002-法学研究-2016-2-低分但强归属论文-乙.pdf").write_text("x")
    (eval_dir / "paper-1.json").write_text(
        json.dumps({"overall": {"round2_final_score_mean": 91.0}}),
        encoding="utf-8",
    )
    (eval_dir / "paper-2.json").write_text(
        json.dumps({"overall": {"round2_final_score_mean": 40.0}}),
        encoding="utf-8",
    )

    papers = load_fullpaper_papers(metadata_path, paper_dir, eval_dir)

    assert [paper["pid"] for paper in papers] == [1, 2]
    assert [paper["six_dimension"]["final_score"] for paper in papers] == [91.0, 40.0]


def test_select_stage0_sample_is_stratified_without_using_scores(tmp_path):
    rows = []
    for pid, year, discipline in [
        (1, "2024", "民法学"),
        (2, "2024", "民法学"),
        (3, "2024", "刑法学"),
        (4, "2023", "民法学"),
    ]:
        rows.append(
            {
                "pid": pid,
                "pdf_path": tmp_path / f"{pid:04d}-x.pdf",
                "meta": {"年份": year, "分类": discipline},
                "six_dimension": {"final_score": 100 - pid},
            }
        )

    sample = select_stage0_sample(rows, sample_size=3)

    assert [paper["pid"] for paper in sample] == [4, 3, 1]


def test_build_fullpaper_merge_record_keeps_context_outside_final_assessment(tmp_path):
    merged = {
        "paper_id": 2,
        "paper": "0002-x.pdf",
        "final": {"total_score": 8},
    }
    paper = {
        "pid": 2,
        "meta": {"题目": "低分但强归属论文"},
        "pdf_path": tmp_path / "0002-x.pdf",
        "six_dimension": {"final_score": 40.0},
        "precheck": {"status": "boundary_review"},
    }

    record = build_fullpaper_merge_record(merged, paper)

    assert record["final"] == {"total_score": 8}
    assert record["paper_meta"]["题目"] == "低分但强归属论文"
    assert record["six_dimension"]["final_score"] == 40.0
    assert record["precheck"]["status"] == "boundary_review"


def test_filter_papers_by_journal_accepts_one_or_more_journals():
    papers = [
        {"pid": 1, "meta": {"期刊": "中国法学"}},
        {"pid": 2, "meta": {"期刊": "中国社会科学"}},
        {"pid": 3, "meta": {"期刊": "法学研究"}},
    ]

    filtered = filter_papers_by_journal(papers, ["中国社会科学", "法学研究"])

    assert [paper["pid"] for paper in filtered] == [2, 3]


def test_remove_papers_already_in_output_uses_merged_results(tmp_path):
    output_dir = tmp_path / "stage0"
    merged_dir = output_dir / "merged"
    merged_dir.mkdir(parents=True)
    (merged_dir / "paper-2.json").write_text("{}", encoding="utf-8")
    papers = [{"pid": 1}, {"pid": 2}, {"pid": 3}]

    remaining = remove_papers_already_in_output(papers, [output_dir])

    assert [paper["pid"] for paper in remaining] == [1, 3]
