# tests/test_evaluation/test_schemas.py
from src.evaluation.schemas import DimensionResult


def test_dimension_result_has_summary_field():
    result = DimensionResult(
        dimension="problem_originality",
        score=85,
        evidence_quotes=["证据1", "证据2"],
        analysis="这是详细分析内容",
        summary="问题具有创新性",
        model_name="gpt-4o",
    )
    assert result.summary == "问题具有创新性"


def test_dimension_result_summary_is_optional_for_backward_compatibility():
    result = DimensionResult(
        dimension="problem_originality",
        score=85,
        evidence_quotes=["证据1"],
        analysis="分析内容",
        model_name="gpt-4o",
    )
    # 旧数据没有 summary，应该能正常加载
    assert result.summary is None
