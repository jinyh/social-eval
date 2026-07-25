from __future__ import annotations

INITIAL_EDITORIAL_UNITS = (
    {
        "journal_code": "jiaoda-law",
        "journal_name": "交大法学",
        "unit_code": "default",
        "unit_name": "交大法学编辑部",
        "policy_key": "jiaoda-law-v1",
    },
    {
        "journal_code": "academic-monthly",
        "journal_name": "学术月刊",
        "unit_code": "law",
        "unit_name": "学术月刊法学板块",
        "policy_key": "academic-monthly-law-v1",
    },
    {
        "journal_code": "oriental-law",
        "journal_name": "东方法学",
        "unit_code": "default",
        "unit_name": "东方法学编辑部",
        "policy_key": "oriental-law-v1",
    },
)

EDITORIAL_POLICY_PATH = "configs/frameworks/editorial-law-v1.yaml"

SUBMISSION_STATUS_GROUPS: dict[str, tuple[str, ...]] = {
    "processing": (
        "queued",
        "anonymizing",
        "formal_check",
        "prechecking",
        "journal_fit_check",
        "evaluating",
        "generating_opinions",
        "expert_review",
    ),
    "awaiting_action": (
        "awaiting_anonymization_confirmation",
        "awaiting_formal_check_confirmation",
        "awaiting_precheck_confirmation",
        "awaiting_fit_confirmation",
        "awaiting_editor",
    ),
    "completed": ("sent_for_external_review", "completed"),
    "failed": ("recovering",),
}
