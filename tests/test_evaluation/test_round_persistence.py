from src.models.evaluation import AICallLog, DimensionScore, EvaluationTask
from src.models.reliability import ReliabilityResult


def test_round_and_structured_audit_columns_exist_on_orm_models():
    assert hasattr(EvaluationTask, "cross_review_enabled")
    assert hasattr(EvaluationTask, "review_protocol_version")
    assert hasattr(EvaluationTask, "final_round")
    assert hasattr(DimensionScore, "structured_payload")
    assert hasattr(DimensionScore, "round_number")
    assert hasattr(AICallLog, "round_number")
    assert hasattr(AICallLog, "call_type")
    assert hasattr(ReliabilityResult, "confidence_level")
    assert hasattr(ReliabilityResult, "requires_evidence_supplement")
    assert hasattr(ReliabilityResult, "divergence_description")
    assert hasattr(ReliabilityResult, "round_number")
