# tests/test_reporting/test_simple_pdf_builder.py
from src.reporting.simple_pdf_builder import build_simple_pdf


def test_build_simple_pdf_returns_bytes():
    report_data = {
        "title": "测试论文标题",
        "weighted_total": 85,
        "conclusion": "通过",
        "dimensions": [
            {"name_zh": "问题创新性", "ai": {"mean_score": 90}, "summary": "问题具有创新性"},
            {"name_zh": "逻辑严密性", "ai": {"mean_score": 80}, "summary": "逻辑较为严密"},
        ],
    }

    pdf_bytes = build_simple_pdf(report_data)

    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 0
    # PDF 文件头
    assert pdf_bytes.startswith(b"%PDF")


def test_build_simple_pdf_handles_missing_summary():
    """测试缺失 summary 时使用兜底逻辑"""
    report_data = {
        "title": "测试论文",
        "weighted_total": 75,
        "conclusion": "待改进",
        "dimensions": [
            {"name_zh": "问题创新性", "ai": {"mean_score": 70}, "analysis": "这是一段分析文本。"},
        ],
    }

    pdf_bytes = build_simple_pdf(report_data)

    assert isinstance(pdf_bytes, bytes)


def test_build_simple_pdf_handles_expert_conclusion():
    """测试包含专家复核结论的情况"""
    report_data = {
        "title": "测试论文",
        "weighted_total": 85,
        "conclusion": "通过",
        "dimensions": [],
        "expert_conclusion": "专家认为论文具有较高学术价值",
    }

    pdf_bytes = build_simple_pdf(report_data)

    assert isinstance(pdf_bytes, bytes)
