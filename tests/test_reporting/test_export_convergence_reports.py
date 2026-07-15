from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def _load_export_module():
    module_path = Path(__file__).resolve().parents[2] / "scripts" / "export_convergence_reports.py"
    spec = importlib.util.spec_from_file_location("export_convergence_reports", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_rendered_html_hides_raw_model_names(tmp_path):
    module = _load_export_module()
    models = ["gpt-5.4", "qwen3.6-plus", "glm-5.1"]
    model_payload = {
        model: {"score": 80, "band": "good", "summary": "摘要"}
        for model in models
    }
    source_path = tmp_path / "convergence.json"
    source_path.write_text(
        json.dumps(
            {
                "models": models,
                "precheck": {model: {"status": "pass"} for model in models},
                "dimensions": {
                    key: {
                        "name_zh": key,
                        "mean": 80,
                        "std": 0,
                        "confidence": "high",
                        "raw_outputs": model_payload,
                    }
                    for key in module.DIMENSION_ORDER
                },
            }
        ),
        encoding="utf-8",
    )

    report = module._build_report_data(source_path)
    html = module.HTML_TEMPLATE.render(report=report)

    assert "模型一" in html
    assert "模型二" in html
    assert "模型三" in html
    assert "gpt-5.4" not in html
    assert "qwen3.6-plus" not in html
    assert "glm-5.1" not in html
