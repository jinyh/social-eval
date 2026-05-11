from pydantic import BaseModel, Field

# =====================================================================
# 降级策略说明
# =====================================================================
# YAML output_contract 中标为 required_fields 的字段，在正常评估路径下必须存在。
# Pydantic 模型使用 Optional / Field(default=...) 是为了兼容以下降级场景：
#   1. Provider 部分失败（超时/异常），仅部分字段可用
#   2. 旧框架（v2.0-v2.44）输出结构不含新增字段
#   3. 信号校验失败时返回 triggers_review=True 的最小结构
# 校验层（result_validator）在聚合时会检查关键字段是否存在，
# 缺失时走降级路径而非抛异常，确保 pipeline 不因单点失败整体中断。
# =====================================================================


class LimitRuleTriggered(BaseModel):
    rule_id: str
    rule: str
    score_ceiling: int
    priority: int
    evidence: str


class SignalJudgment(BaseModel):
    signal_key: str
    judgment: str
    evidence_quote: str | None = None


class SignalCheckResult(BaseModel):
    """第 3 阶段（自主知识体系信号校验）结构化输出。

    对应 v0.14 规程 §7.3 autonomous_knowledge_signals.output_contract。
    """

    # 四类核心信号（对应 v2.44 autonomous_knowledge_signals.signals）
    china_problem_centered: str | None = None
    china_practice_explanation_attempted: str | None = None
    external_theory_transformation: str | None = None
    verifiable_concept_or_thesis: str | None = None

    # 辅助元数据（对应 auxiliary_metadata）
    involves_special_chinese_institutional_issue: str | None = None
    issue_types: list[str] = Field(default_factory=list)
    uses_traditional_cultural_resource: str | None = None

    # 证据与复核
    evidence_quotes: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    triggers_review: bool = False
    review_reason: str | None = None

    # v2.46 / v0.16: 阶段3显式量化，只用于排序、分层和复核优先级。
    # 不进入六维基础分，也不改变 final_score。
    signal_scores: dict[str, int] = Field(default_factory=dict)
    autonomous_signal_score: int | None = None
    autonomous_signal_strength: str | None = None

    # 多模型信号聚合元数据
    signal_model_agreement: bool | None = None
    per_model_signal_scores: dict[str, dict[str, int]] | None = None

    # 兼容字段：legacy 简化结构（已有测试可能依赖）
    signals: list[SignalJudgment] = Field(default_factory=list)


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
