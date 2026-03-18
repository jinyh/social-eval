from pydantic import BaseModel


class DimensionResult(BaseModel):
    dimension: str
    score: int  # 0-100
    evidence_quotes: list[str]
    analysis: str
    model_name: str
