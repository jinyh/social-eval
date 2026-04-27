from __future__ import annotations

DEFAULT_FRAMEWORK_PATH = "configs/frameworks/law-v2.40-20260426.yaml"
DEFAULT_PROVIDER_NAMES = ["gpt-5.4", "glm-5.1", "qwen3.6-plus"]
MANUAL_REVIEW_PRECHECK_STATUSES = {"conditional_pass", "manual_review"}
MANDATORY_REVIEW_FLAGS = {
    "mandatory_expert_review",
    "external_context_conflict",
    "material_novelty_overclaim",
    "evidence_thin",
    "future_claim_thin",
}
