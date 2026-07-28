from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.editorial.opinions import generate_editorial_opinions
from src.editorial.policy import load_editorial_policy
from src.evaluation.providers.base import BaseProvider
from src.evaluation.schemas import DimensionResult
from src.models.audit import AuditLog
from src.models.editorial import (
    EditorialDocument,
    EditorialPolicyVersion,
    EditorialSubmission,
)
from src.models.evaluation import EvaluationTask
from tests.test_api.conftest import create_user


def _login(client: TestClient, email: str) -> None:
    response = client.post(
        "/api/auth/login",
        json={"email": email, "password": "secret123"},
    )
    assert response.status_code == 200


def _noop_editorial_runner(client: TestClient) -> None:
    async def runner(_: str, __: Session) -> None:
        return None

    client.app.state.editorial_pipeline_runner = runner


class _OpinionProvider(BaseProvider):
    def __init__(self, model_name: str) -> None:
        self.model_name = model_name
        self.calls = 0

    async def generate_json_response(self, prompt: str) -> dict:
        self.calls += 1
        return {
            "synthesis": "四模型综合摘要",
            "consensus_points": ["共同认可问题意识"],
            "disagreement_points": ["一方为 excellent，另一方为 good"],
            "priority_issues": ["补充关键法条依据"],
            "modification_suggestions": ["逐项回应反对观点"],
        }

    async def evaluate_dimension(self, prompt: str) -> DimensionResult:
        raise NotImplementedError


def _bootstrap_and_add_editor(
    client: TestClient,
    db_session: Session,
) -> tuple[str, str]:
    admin = create_user(db_session, email="admin-editorial@example.com", role="admin")
    editor = create_user(db_session, email="editor-one@example.com", role="editor")
    _login(client, admin.email)
    response = client.post("/api/admin/editorial/bootstrap")
    assert response.status_code == 200
    unit_id = response.json()["items"][0]["id"]
    member_response = client.post(
        f"/api/admin/editorial/units/{unit_id}/members",
        json={"user_id": editor.id, "membership_role": "unit_admin"},
    )
    assert member_response.status_code == 201
    return unit_id, editor.id


def test_invitation_with_unit_ids_binds_membership_on_accept(
    client: TestClient,
    db_session: Session,
) -> None:
    """邀请时指定编辑单元，激活后编辑立即看到所属单元（兼任多期刊闭环）。"""
    admin = create_user(db_session, email="admin-invite@example.com", role="admin")
    _login(client, admin.email)
    bootstrap = client.post("/api/admin/editorial/bootstrap")
    assert bootstrap.status_code == 200
    unit_ids = [item["id"] for item in bootstrap.json()["items"][:2]]

    invite = client.post(
        "/api/users/invitations",
        json={
            "email": "editor-invite@example.com",
            "display_name": "Invite Editor",
            "role": "editor",
            "unit_ids": unit_ids,
            "membership_role": "editor",
        },
    )
    assert invite.status_code == 201
    assert invite.json()["unit_ids"] == unit_ids
    token = invite.json()["token"]

    client.cookies.clear()
    accept = client.post(
        "/api/auth/invitations/accept",
        json={
            "token": token,
            "password": "new-password-123",
        },
    )
    assert accept.status_code == 201

    login = client.post(
        "/api/auth/login",
        json={"email": "editor-invite@example.com", "password": "new-password-123"},
    )
    assert login.status_code == 200
    units_response = client.get("/api/editorial/units")
    assert units_response.status_code == 200
    assert [item["id"] for item in units_response.json()["items"]] == unit_ids


def test_invitation_without_unit_ids_stays_empty(
    client: TestClient,
    db_session: Session,
) -> None:
    """邀请不带 unit_ids 时激活后编辑看不到任何单元（向后兼容）。"""
    admin = create_user(db_session, email="admin-nounit@example.com", role="admin")
    _login(client, admin.email)
    client.post("/api/admin/editorial/bootstrap")
    invite = client.post(
        "/api/users/invitations",
        json={"email": "editor-nounit@example.com", "role": "editor", "display_name": "No Unit Editor"},
    )
    assert invite.status_code == 201
    token = invite.json()["token"]

    client.cookies.clear()
    accept = client.post(
        "/api/auth/invitations/accept",
        json={
            "token": token,
            "password": "new-password-123",
        },
    )
    assert accept.status_code == 201
    login = client.post(
        "/api/auth/login",
        json={"email": "editor-nounit@example.com", "password": "new-password-123"},
    )
    assert login.status_code == 200
    units_response = client.get("/api/editorial/units")
    assert units_response.status_code == 200
    assert units_response.json()["items"] == []


def test_remove_membership_revokes_unit_access(
    client: TestClient,
    db_session: Session,
) -> None:
    """DELETE membership 后编辑不再看到该单元，其它单元仍可见。"""
    admin = create_user(db_session, email="admin-rm@example.com", role="admin")
    editor = create_user(db_session, email="editor-rm@example.com", role="editor")
    _login(client, admin.email)
    bootstrap = client.post("/api/admin/editorial/bootstrap")
    assert bootstrap.status_code == 200
    items = bootstrap.json()["items"]
    unit_a, unit_b = items[0]["id"], items[1]["id"]
    for uid in (unit_a, unit_b):
        member_response = client.post(
            f"/api/admin/editorial/units/{uid}/members",
            json={"user_id": editor.id, "membership_role": "editor"},
        )
        assert member_response.status_code == 201

    client.cookies.clear()
    _login(client, editor.email)
    before = client.get("/api/editorial/units")
    before_ids = [i["id"] for i in before.json()["items"]]
    assert unit_a in before_ids
    assert unit_b in before_ids

    client.cookies.clear()
    _login(client, admin.email)
    delete = client.delete(f"/api/admin/editorial/units/{unit_a}/members/{editor.id}")
    assert delete.status_code == 200

    client.cookies.clear()
    _login(client, editor.email)
    after = client.get("/api/editorial/units")
    after_ids = [i["id"] for i in after.json()["items"]]
    assert unit_a not in after_ids
    assert unit_b in after_ids


def test_editor_only_lists_member_units(
    client: TestClient,
    db_session: Session,
) -> None:
    unit_id, _ = _bootstrap_and_add_editor(client, db_session)

    client.cookies.clear()
    _login(client, "editor-one@example.com")
    response = client.get("/api/editorial/units")

    assert response.status_code == 200
    assert [item["id"] for item in response.json()["items"]] == [unit_id]


def test_submission_is_row_scoped_and_external_id_is_unique_per_unit(
    client: TestClient,
    db_session: Session,
    tmp_path: Path,
    monkeypatch,
) -> None:
    import src.core.storage

    monkeypatch.setattr(src.core.storage, "UPLOAD_ROOT", tmp_path / "uploads")
    unit_id, _ = _bootstrap_and_add_editor(client, db_session)
    other_editor = create_user(
        db_session, email="editor-two@example.com", role="editor"
    )
    _noop_editorial_runner(client)

    client.cookies.clear()
    _login(client, "editor-one@example.com")
    first = client.post(
        "/api/editorial/submissions",
        data={"unit_id": unit_id, "external_manuscript_id": "JD-2026-001"},
        files={"file": ("paper.txt", ("正文内容" * 80).encode(), "text/plain")},
    )
    assert first.status_code == 202
    submission_id = first.json()["submission_id"]
    paper_id = first.json()["paper_id"]

    duplicate = client.post(
        "/api/editorial/submissions",
        data={"unit_id": unit_id, "external_manuscript_id": "JD-2026-001"},
        files={"file": ("other.txt", ("另一正文" * 80).encode(), "text/plain")},
    )
    assert duplicate.status_code == 409

    client.cookies.clear()
    _login(client, other_editor.email)
    assert client.get(f"/api/editorial/submissions/{submission_id}").status_code == 404
    assert client.get(f"/api/papers/{paper_id}/status").status_code == 404


def test_submission_list_supports_server_filters_pagination_and_status_counts(
    client: TestClient,
    db_session: Session,
    tmp_path: Path,
    monkeypatch,
) -> None:
    import src.core.storage

    monkeypatch.setattr(src.core.storage, "UPLOAD_ROOT", tmp_path / "uploads")
    unit_id, _ = _bootstrap_and_add_editor(client, db_session)
    _noop_editorial_runner(client)
    client.cookies.clear()
    _login(client, "editor-one@example.com")

    submission_ids = []
    for index, name in enumerate(("平台治理", "规范结构", "判例研究"), start=1):
        response = client.post(
            "/api/editorial/submissions",
            data={
                "unit_id": unit_id,
                "external_manuscript_id": f"JD-2026-00{index}",
            },
            files={
                "file": (
                    f"{name}.txt",
                    ("正文内容" * 80).encode(),
                    "text/plain",
                )
            },
        )
        submission_ids.append(response.json()["submission_id"])

    rows = [
        db_session.get(EditorialSubmission, submission_id)
        for submission_id in submission_ids
    ]
    rows[0].status = "completed"
    rows[0].created_at = datetime(2026, 7, 24, 16, 0)
    rows[1].status = "evaluating"
    rows[1].created_at = datetime(2026, 7, 25, 8, 0)
    rows[2].status = "awaiting_editor"
    rows[2].created_at = datetime(2026, 7, 26, 8, 0)
    db_session.commit()

    first_page = client.get(
        "/api/editorial/submissions",
        params={
            "unit_id": unit_id,
            "q": "JD-2026",
            "page": 1,
            "page_size": 1,
        },
    )
    payload = first_page.json()
    assert first_page.status_code == 200
    assert payload["total"] == 3
    assert len(payload["items"]) == 1
    assert payload["status_counts"] == {
        "processing": 1,
        "awaiting_action": 1,
        "completed": 1,
        "failed": 0,
    }

    pending = client.get(
        "/api/editorial/submissions",
        params={
            "unit_id": unit_id,
            "status_group": "awaiting_action",
            "submitted_from": "2026-07-26",
            "submitted_to": "2026-07-26",
        },
    )
    assert pending.status_code == 200
    assert pending.json()["total"] == 1
    assert pending.json()["items"][0]["status"] == "awaiting_editor"

    invalid = client.get(
        "/api/editorial/submissions",
        params={"unit_id": unit_id, "status_group": "unknown"},
    )
    assert invalid.status_code == 422


def test_responsible_editor_decision_locks_and_admin_can_reopen(
    client: TestClient,
    db_session: Session,
    tmp_path: Path,
    monkeypatch,
) -> None:
    import src.core.storage
    import src.editorial.reporting

    monkeypatch.setattr(src.core.storage, "UPLOAD_ROOT", tmp_path / "uploads")
    monkeypatch.setattr(src.editorial.reporting, "REPORT_ROOT", tmp_path / "reports")
    unit_id, _ = _bootstrap_and_add_editor(client, db_session)
    _noop_editorial_runner(client)

    client.cookies.clear()
    _login(client, "editor-one@example.com")
    uploaded = client.post(
        "/api/editorial/submissions",
        data={"unit_id": unit_id},
        files={"file": ("paper.txt", ("正文内容" * 80).encode(), "text/plain")},
    )
    submission_id = uploaded.json()["submission_id"]
    submission = db_session.get(EditorialSubmission, submission_id)
    submission.internal_candidate_decision = "revise_resubmit"
    submission.recommendation_state = "ready"
    submission.status = "awaiting_editor"
    db_session.commit()

    decided = client.post(
        f"/api/editorial/submissions/{submission_id}/decision",
        json={
            "decision_stage": "pre_review",
            "final_decision": "revise_resubmit",
        },
    )
    assert decided.status_code == 200
    assert decided.json()["version"] == 1
    json_report = client.get(
        f"/api/editorial/submissions/{submission_id}/report?format=json"
    )
    assert json_report.status_code == 200
    assert json_report.json()["schema_version"] == "editorial-report-v4"
    assert json_report.json()["report_metadata"]["report_version"] == 1
    assert json_report.json()["report_metadata"]["journal_name"]
    assert json_report.json()["evaluation"]["display_order"] == [
        "ai_synthesis",
        "five_axis",
        "six_dimension",
        "expert_review",
        "editorial_decision",
    ]
    listed = client.get(
        "/api/editorial/submissions",
        params={"unit_id": unit_id},
    )
    assert listed.status_code == 200
    assert listed.json()["items"][0]["current_report_version"] == 1
    pdf_report = client.get(
        f"/api/editorial/submissions/{submission_id}/report?format=pdf"
    )
    assert pdf_report.status_code == 200
    assert pdf_report.content.startswith(b"%PDF")
    assert (
        client.post(
            f"/api/editorial/submissions/{submission_id}/decision",
            json={
                "decision_stage": "pre_review",
                "final_decision": "revise_resubmit",
            },
        ).status_code
        == 409
    )

    client.cookies.clear()
    _login(client, "admin-editorial@example.com")
    reopened = client.post(
        f"/api/admin/editorial/submissions/{submission_id}/reopen",
        json={"reason": "责任编辑申请更正正式决定"},
    )
    assert reopened.status_code == 200
    assert reopened.json()["status"] == "awaiting_editor"


def test_final_decision_requires_a_locked_send_for_external_review_decision(
    client: TestClient,
    db_session: Session,
    tmp_path: Path,
    monkeypatch,
) -> None:
    import src.core.storage
    import src.editorial.reporting

    monkeypatch.setattr(src.core.storage, "UPLOAD_ROOT", tmp_path / "uploads")
    monkeypatch.setattr(src.editorial.reporting, "REPORT_ROOT", tmp_path / "reports")
    unit_id, _ = _bootstrap_and_add_editor(client, db_session)
    _noop_editorial_runner(client)

    client.cookies.clear()
    _login(client, "editor-one@example.com")
    uploaded = client.post(
        "/api/editorial/submissions",
        data={"unit_id": unit_id},
        files={"file": ("paper.txt", ("正文内容" * 80).encode(), "text/plain")},
    )
    submission_id = uploaded.json()["submission_id"]
    submission = db_session.get(EditorialSubmission, submission_id)
    submission.internal_candidate_decision = "send_external_review"
    submission.recommendation_state = "ready"
    submission.status = "awaiting_editor"
    db_session.commit()

    too_early = client.post(
        f"/api/editorial/submissions/{submission_id}/decision",
        json={"decision_stage": "final", "final_decision": "major_revision"},
    )
    assert too_early.status_code == 409

    pre_review = client.post(
        f"/api/editorial/submissions/{submission_id}/decision",
        json={
            "decision_stage": "pre_review",
            "final_decision": "send_external_review",
        },
    )
    assert pre_review.status_code == 200
    assert pre_review.json()["version"] == 1

    final = client.post(
        f"/api/editorial/submissions/{submission_id}/decision",
        json={"decision_stage": "final", "final_decision": "major_revision"},
    )
    assert final.status_code == 200
    assert final.json()["version"] == 2
    assert final.json()["decision_stage"] == "final"


def test_admin_content_access_is_audited(
    client: TestClient,
    db_session: Session,
    tmp_path: Path,
    monkeypatch,
) -> None:
    import src.core.storage

    monkeypatch.setattr(src.core.storage, "UPLOAD_ROOT", tmp_path / "uploads")
    unit_id, _ = _bootstrap_and_add_editor(client, db_session)
    _noop_editorial_runner(client)
    client.cookies.clear()
    _login(client, "editor-one@example.com")
    uploaded = client.post(
        "/api/editorial/submissions",
        data={"unit_id": unit_id},
        files={"file": ("paper.txt", ("正文内容" * 80).encode(), "text/plain")},
    )

    client.cookies.clear()
    _login(client, "admin-editorial@example.com")
    response = client.get(
        f"/api/editorial/submissions/{uploaded.json()['submission_id']}"
    )

    assert response.status_code == 200
    assert (
        db_session.query(AuditLog)
        .filter(AuditLog.action == "admin_submission_content_access")
        .count()
        == 1
    )


def test_unit_activation_requires_validation_and_signoff(
    client: TestClient,
    db_session: Session,
) -> None:
    unit_id, _ = _bootstrap_and_add_editor(client, db_session)
    unit_payload = client.get("/api/admin/editorial/policies")
    assert unit_payload.status_code == 200
    versions = client.get(
        f"/api/admin/editorial/units/{unit_id}/policy-versions"
    ).json()["items"]
    trial = next(version for version in versions if version["status"] == "trial")

    denied = client.post(
        f"/api/admin/editorial/units/{unit_id}/rollout",
        json={
            "rollout_state": "active",
            "reason": "准备启用正式建议",
            "editor_signoff": False,
        },
    )
    assert denied.status_code == 400

    validation = client.post(
        "/api/admin/editorial/validation-runs",
        json={
            "unit_id": unit_id,
            "validation_type": "final_validation",
            "framework_version": trial["framework_version"],
            "model_set_version": trial["model_set_version"],
            "policy_version_id": trial["id"],
            "sample_manifest_sha256": "a" * 64,
            "sample_count": 20,
            "metrics": {"conclusion": "样本验证通过"},
        },
    )
    assert validation.status_code == 201
    validation_id = validation.json()["id"]
    admin_sign = client.post(
        f"/api/admin/editorial/validation-runs/{validation_id}/sign"
    )
    assert admin_sign.status_code == 403

    client.cookies.clear()
    _login(client, "editor-one@example.com")
    signed = client.post(
        f"/api/editorial/validation-runs/{validation_id}/decision",
        json={"approved": True, "reason": "已核对样本与期刊适配口径"},
    )
    assert signed.status_code == 200
    assert signed.json()["signer_membership_role"] == "unit_admin"

    client.cookies.clear()
    _login(client, "admin-editorial@example.com")
    activated = client.post(
        f"/api/admin/editorial/units/{unit_id}/rollout",
        json={
            "rollout_state": "active",
            "reason": "样本验证和编辑复核均已完成",
            "validation_run_id": validation_id,
            "policy_version_id": trial["id"],
        },
    )
    assert activated.status_code == 200
    assert activated.json()["rollout_state"] == "active"

    returned = client.post(
        f"/api/admin/editorial/units/{unit_id}/rollout",
        json={
            "rollout_state": "shadow",
            "reason": "发现关键验证异常，暂停正式建议",
            "editor_signoff": False,
        },
    )
    assert returned.status_code == 200
    assert returned.json()["rollout_state"] == "shadow"


def test_trial_submission_uses_frozen_candidate_model_strategy(
    client: TestClient,
    db_session: Session,
    tmp_path: Path,
    monkeypatch,
) -> None:
    import json

    import src.core.storage

    monkeypatch.setattr(src.core.storage, "UPLOAD_ROOT", tmp_path / "uploads")
    unit_id, _ = _bootstrap_and_add_editor(client, db_session)
    _noop_editorial_runner(client)

    client.cookies.clear()
    _login(client, "editor-one@example.com")
    uploaded = client.post(
        "/api/editorial/submissions",
        data={"unit_id": unit_id},
        files={"file": ("paper.txt", ("正文内容" * 80).encode(), "text/plain")},
    )
    assert uploaded.status_code == 202
    submission = db_session.get(
        EditorialSubmission,
        uploaded.json()["submission_id"],
    )
    task = db_session.get(EvaluationTask, submission.evaluation_task_id)
    policy_version = db_session.get(
        EditorialPolicyVersion,
        submission.policy_version_id,
    )

    assert task.model_set_version == "six-dimension-v2-candidate"
    assert task.review_protocol_version == "six_dimension_peer_review"
    assert json.loads(task.provider_names) == [
        "glm-5.2",
        "qwen3.7-max-2026-06-08",
        "deepseek-v4-pro",
        "kimi-k2.6",
    ]
    assert policy_version.status == "trial"
    assert submission.policy_version == policy_version.version


def test_policy_draft_is_editable_but_trial_snapshot_is_immutable(
    client: TestClient,
    db_session: Session,
) -> None:
    unit_id, _ = _bootstrap_and_add_editor(client, db_session)
    versions = client.get(
        f"/api/admin/editorial/units/{unit_id}/policy-versions"
    ).json()["items"]
    trial = next(version for version in versions if version["status"] == "trial")
    payload = {
        "version": "1.2",
        "based_on_id": trial["id"],
        "model_set_version": "six-dimension-v2-candidate",
        "profile": {
            "fit_focus": "中国法治实践中的原创法学问题与制度解释",
            "accepted_scope": ["法学理论", "部门法制度研究"],
            "excluded_scope": ["不具有法学问题意识的泛社会评论"],
            "column_positioning": ["专题论文"],
            "article_types": ["研究论文"],
            "target_readers": ["法学研究者", "法律实务工作者"],
            "special_notes": "比较法研究须说明中国法语境的解释价值",
        },
    }
    created = client.post(
        f"/api/admin/editorial/units/{unit_id}/policy-versions",
        json=payload,
    )
    assert created.status_code == 201
    draft_id = created.json()["id"]

    payload["profile"]["fit_focus"] = "经编辑部确认的中国法学原创问题"
    updated = client.put(
        f"/api/admin/editorial/policy-versions/{draft_id}",
        json=payload,
    )
    assert updated.status_code == 200
    frozen = client.post(f"/api/admin/editorial/policy-versions/{draft_id}/trial")
    assert frozen.status_code == 200
    assert frozen.json()["status"] == "trial"

    immutable = client.put(
        f"/api/admin/editorial/policy-versions/{draft_id}",
        json=payload,
    )
    assert immutable.status_code == 409
    assert (
        db_session.get(EditorialPolicyVersion, draft_id).content_sha256
        == frozen.json()["content_sha256"]
    )


def test_admin_candidate_model_run_is_separate_from_production_snapshot(
    client: TestClient,
    db_session: Session,
    tmp_path: Path,
    monkeypatch,
) -> None:
    import json

    import src.core.storage

    monkeypatch.setattr(src.core.storage, "UPLOAD_ROOT", tmp_path / "uploads")
    unit_id, _ = _bootstrap_and_add_editor(client, db_session)
    _noop_editorial_runner(client)

    client.cookies.clear()
    _login(client, "editor-one@example.com")
    uploaded = client.post(
        "/api/editorial/submissions",
        data={"unit_id": unit_id},
        files={"file": ("paper.txt", ("正文内容" * 80).encode(), "text/plain")},
    )
    assert uploaded.status_code == 202
    submission_id = uploaded.json()["submission_id"]
    anonymous_path = tmp_path / "anonymous.txt"
    anonymous_path.write_text("匿名稿正文", encoding="utf-8")
    submission = db_session.get(EditorialSubmission, submission_id)
    baseline = db_session.get(EvaluationTask, submission.evaluation_task_id)
    baseline.input_file_path = str(anonymous_path)
    baseline.model_set_version = "six-dimension-v1"
    baseline.review_protocol_version = "six_dimension_cross_review"
    baseline.provider_names = json.dumps(
        ["glm-5.1", "qwen3.6-plus", "deepseek-v4-pro", "kimi-k2.6"]
    )
    db_session.add(
        EditorialDocument(
            submission_id=submission_id,
            kind="anonymized",
            version=1,
            file_path=str(anonymous_path),
            sha256="test-anonymous-sha256",
        )
    )
    db_session.add(baseline)
    db_session.commit()

    async def candidate_runner(_: str, __: Session) -> None:
        return None

    client.app.state.pipeline_runner = candidate_runner
    client.cookies.clear()
    _login(client, "admin-editorial@example.com")
    response = client.post(
        f"/api/admin/editorial/submissions/{submission_id}/candidate-run"
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["model_set_version"] == "six-dimension-v2-candidate"
    assert payload["review_protocol_version"] == "six_dimension_peer_review"
    baseline = db_session.get(EvaluationTask, payload["baseline_task_id"])
    candidate = db_session.get(EvaluationTask, payload["task_id"])
    assert baseline is not None
    assert candidate is not None
    assert baseline.run_role == "baseline"
    assert candidate.run_role == "candidate"
    assert candidate.review_protocol_version == "six_dimension_peer_review"
    assert candidate.id != baseline.id
    assert candidate.comparison_group_id == baseline.comparison_group_id
    assert candidate.input_file_path == str(anonymous_path)

    duplicate = client.post(
        f"/api/admin/editorial/submissions/{submission_id}/candidate-run"
    )
    assert duplicate.status_code == 409


@pytest.mark.asyncio
async def test_opinion_generation_reuses_four_model_results_without_duplicate_calls(
    db_session: Session,
) -> None:
    first = _OpinionProvider("glm-5.1")
    second = _OpinionProvider("qwen3.6-plus")

    records = await generate_editorial_opinions(
        db_session,
        submission_id="submission-retry",
        task_id="task-retry",
        providers=[first, second],
        policy=load_editorial_policy("jiaoda-law-v1"),
        anonymized_text="匿名稿正文",
        evaluation_context={},
    )

    assert len(records) == 1
    assert records[0].opinion_type == "ai_synthesis"
    assert records[0].content["synthesis"] == "四模型综合摘要"
    assert records[0].content["disagreement_points"] == ["一方为 优，另一方为 良"]
    assert first.calls == 1
    assert second.calls == 0

    await generate_editorial_opinions(
        db_session,
        submission_id="submission-retry",
        task_id="task-retry",
        providers=[first, second],
        policy=load_editorial_policy("jiaoda-law-v1"),
        anonymized_text="匿名稿正文",
        evaluation_context={},
    )
    assert first.calls == 1
    assert second.calls == 0
