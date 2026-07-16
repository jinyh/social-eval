from pathlib import Path


FORBIDDEN_ACTIVE_ROOTS = (
    "results/report_paper_master",
    "results/unified_rankings",
    "results/fullevaluation",
    "results/fullpaper-position-assessment-stage0",
    "results/xueshuyuekan/round2",
    "results/merged-metadata",
    "results/e2-pool",
)


def test_active_scripts_do_not_reference_removed_result_roots():
    exceptions = {"build_results_catalog.py"}  # migrated_from 审计字段
    violations: list[str] = []
    for path in sorted(Path("scripts").glob("*.py")):
        if path.name in exceptions:
            continue
        text = path.read_text(encoding="utf-8")
        for root in FORBIDDEN_ACTIVE_ROOTS:
            if root in text:
                violations.append(f"{path}:{root}")

    assert violations == []
