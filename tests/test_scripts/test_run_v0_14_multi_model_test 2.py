from __future__ import annotations

import sys
import importlib.util
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2] / "scripts" / "run_v0.14_multi_model_test.py"
)


def _load_script_module():
    spec = importlib.util.spec_from_file_location("run_v0_14_multi_model_test", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_default_review_models_use_gpt_5_5() -> None:
    v0_14_test = _load_script_module()

    assert v0_14_test.DEFAULT_REVIEW_MODELS == ["gpt-5.5"]


def test_default_framework_uses_v2_46_large_scale_candidate() -> None:
    v0_14_test = _load_script_module()

    assert v0_14_test.DEFAULT_FRAMEWORK == "configs/frameworks/law-v2.46-20260511.yaml"


def test_parser_accepts_custom_review_models() -> None:
    v0_14_test = _load_script_module()
    parser = v0_14_test.build_arg_parser()

    args = parser.parse_args(
        [
            "--paper",
            "raw/holdout-test/数字法学的理论表达_马长山.pdf",
            "--review-models",
            "fucheers-gpt-5.5,openrouter-gpt-5.4",
        ]
    )

    assert args.review_models == "fucheers-gpt-5.5,openrouter-gpt-5.4"


def test_summary_report_reads_generic_gpt_review_field() -> None:
    v0_14_test = _load_script_module()

    summary = v0_14_test.generate_summary_report(
        [
            {
                "paper": "paper-a.pdf",
                "paper_metadata": {"type": "理论建构型", "signal": "强"},
                "overall": {
                    "avg_std": 7.0,
                    "max_std": 9.0,
                    "weighted_total": 80.0,
                    "high_confidence_pct": 66.7,
                },
                "layered_score": {"final_score": 82.0},
                "gpt_review": {"triggered": True, "model": "gpt-5.4"},
            }
        ]
    )

    assert summary["gpt_review_statistics"]["triggered_count"] == 1
    assert summary["papers"][0]["gpt_review_triggered"] is True
    assert summary["papers"][0]["final_score"] == 82.0
