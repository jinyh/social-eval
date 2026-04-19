from pydantic import BaseModel, Field


class DimensionResult(BaseModel):
    dimension: str
    score: int  # 0-100
    evidence_quotes: list[str]
    analysis: str
    summary: str | None = Field(default=None, description="AI 生成的一句话总结，不超过 50 字")
    model_name: str
