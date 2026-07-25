from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


PRE_REVIEW_DECISIONS = {
    "decline_without_review",
    "revise_resubmit",
    "send_external_review",
    "priority_external_review",
}
FINAL_DECISIONS = {
    "reject",
    "major_revision",
    "minor_accept",
    "direct_accept",
}


class EditorialUnitResponse(BaseModel):
    id: str
    journal_id: str
    journal_name: str
    code: str
    name: str
    policy_key: str
    policy_version: str
    rollout_state: str


class EditorialUnitListResponse(BaseModel):
    items: list[EditorialUnitResponse]


class EditorialSubmissionCreateResponse(BaseModel):
    submission_id: str
    paper_id: str
    task_id: str
    status: str


class EditorialBatchCreateResponse(BaseModel):
    total: int
    items: list[EditorialSubmissionCreateResponse]


class EditorialSubmissionListItem(BaseModel):
    id: str
    unit_id: str
    external_manuscript_id: str | None
    title: str | None
    status: str
    responsible_editor_id: str | None
    recommendation_state: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class EditorialSubmissionListResponse(BaseModel):
    items: list[EditorialSubmissionListItem]


class EditorialOpinionResponse(BaseModel):
    id: str
    opinion_type: str
    version: int
    sequence: int
    content: dict
    model_name: str | None
    created_by: str | None
    is_locked: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class EditorialDecisionResponse(BaseModel):
    id: str
    version: int
    decision_stage: str
    suggested_decision: str | None
    final_decision: str
    recommendation_state: str
    rationale: str | None
    bypassed_expert_gate: bool
    actor_id: str
    is_locked: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class EditorialSubmissionDetailResponse(EditorialSubmissionListItem):
    paper_id: str
    task_id: str
    anonymization_status: str
    anonymization_result: dict | None
    formal_check_status: str | None
    formal_check_result: dict | None
    precheck_status: str | None
    precheck_result: dict | None
    fit_status: str | None
    fit_result: dict | None
    internal_candidate_decision: str | None
    manual_review_requested: bool
    six_dimension: list[dict]
    six_dimension_summary: dict
    ccb_summary: dict | None
    position_summary: dict | None
    position_assessment: dict | None
    model_set_version: str
    progress: dict
    documents: dict[str, str]
    expert_reviews: list[dict]
    opinions: list[EditorialOpinionResponse]
    decisions: list[EditorialDecisionResponse]


class AssignmentRequest(BaseModel):
    responsible_editor_id: str
    reason: str = Field(min_length=2, max_length=1000)


class GateContinueRequest(BaseModel):
    stage: str = Field(pattern="^(formal_check|precheck|journal_fit)$")
    reason: str = Field(min_length=5, max_length=2000)


class AnonymizationConfirmRequest(BaseModel):
    reason: str = Field(default="编辑确认匿名化结果", min_length=2, max_length=1000)


class EditorialDecisionCreateRequest(BaseModel):
    decision_stage: str = Field(default="pre_review", pattern="^(pre_review|final)$")
    final_decision: str
    rationale: str | None = Field(default=None, max_length=5000)
    bypass_expert_gate: bool = False

    @model_validator(mode="after")
    def validate_decision_for_stage(self) -> "EditorialDecisionCreateRequest":
        allowed = (
            PRE_REVIEW_DECISIONS
            if self.decision_stage == "pre_review"
            else FINAL_DECISIONS
        )
        if self.final_decision not in allowed:
            raise ValueError("决定类型与当前决定阶段不匹配")
        return self


class EditorOpinionRequest(BaseModel):
    content: dict
    submit: bool = False


class JournalCreateRequest(BaseModel):
    code: str = Field(pattern=r"^[a-z0-9-]+$", max_length=80)
    name: str = Field(min_length=2, max_length=255)


class EditorialUnitCreateRequest(BaseModel):
    journal_id: str
    code: str = Field(pattern=r"^[a-z0-9-]+$", max_length=80)
    name: str = Field(min_length=2, max_length=255)
    policy_key: str


class MembershipCreateRequest(BaseModel):
    user_id: str
    membership_role: str = Field(default="editor", pattern="^(editor|unit_admin)$")


class RolloutStateRequest(BaseModel):
    rollout_state: str = Field(pattern="^(shadow|active)$")
    reason: str = Field(min_length=5, max_length=2000)
    validation_summary: dict | None = None
    validation_run_id: str | None = None
    editor_signoff: bool = False


class ValidationRunCreateRequest(BaseModel):
    unit_id: str | None = None
    validation_type: str = Field(
        pattern="^(calibration|holdout|final_validation|model_upgrade)$"
    )
    framework_version: str = Field(min_length=2, max_length=100)
    model_set_version: str = Field(min_length=2, max_length=100)
    sample_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    sample_count: int = Field(gt=0, le=100000)
    metrics: dict


class ReopenDecisionRequest(BaseModel):
    reason: str = Field(min_length=5, max_length=2000)
