from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_export_module():
    module_path = Path(__file__).resolve().parents[2] / "scripts" / "export_convergence_reports.py"
    spec = importlib.util.spec_from_file_location("export_convergence_reports", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_rendered_html_hides_raw_model_names():
    module = _load_export_module()
    source_path = (
        Path(__file__).resolve().parents[2] / "results" / "convergence-test-full-v214.json"
    )

    report = module._build_report_data(source_path)
    html = module.HTML_TEMPLATE.render(report=report)

    assert "模型一" in html
    assert "模型二" in html
    assert "模型三" in html
    assert "gpt-5.4" not in html
    assert "qwen3.6-plus" not in html
    assert "glm-5.1" not in html
