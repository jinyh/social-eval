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
from src.models.editorial import EditorialDocument, EditorialSubmission
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
        json={"user_id": editor.id, "membership_role": "editor"},
    )
    assert member_response.status_code == 201
    return unit_id, editor.id


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

    denied = client.post(
        f"/api/admin/editorial/units/{unit_id}/rollout",
        json={
            "rollout_state": "active",
            "reason": "准备启用正式建议",
            "editor_signoff": False,
        },
    )
    assert denied.status_code == 400

    activated = client.post(
        f"/api/admin/editorial/units/{unit_id}/rollout",
        json={
            "rollout_state": "active",
            "reason": "样本验证和编辑复核均已完成",
            "validation_summary": {"sample_count": 20, "approved": True},
            "editor_signoff": True,
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


def test_admin_candidate_model_run_is_separate_from_production_snapshot(
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
    assert uploaded.status_code == 202
    submission_id = uploaded.json()["submission_id"]
    anonymous_path = tmp_path / "anonymous.txt"
    anonymous_path.write_text("匿名稿正文", encoding="utf-8")
    submission = db_session.get(EditorialSubmission, submission_id)
    baseline = db_session.get(EvaluationTask, submission.evaluation_task_id)
    baseline.input_file_path = str(anonymous_path)
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
