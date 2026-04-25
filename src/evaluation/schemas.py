from pydantic import BaseModel, Field


class LimitRuleTriggered(BaseModel):
    rule_id: str
    rule: str
    score_ceiling: int
    priority: int
    evidence: str


class DimensionResult(BaseModel):
    dimension: str
    score: int  # 0-100
    evidence_quotes: list[str]
    analysis: str | None = None
    band: str | None = None
    summary: str | None = Field(default=None, description="AI 生成的一句话总结，不超过 50 字")
    core_judgment: str | None = None
    score_rationale: str | None = None
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    limit_rule_triggered: list[LimitRuleTriggered] = Field(default_factory=list)
    boundary_note: str | None = None
    review_flags: list[str] = Field(default_factory=list)
    model_name: str
