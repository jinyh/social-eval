from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.models.editorial import (
    EditorialDecision,
    EditorialPolicyVersion,
    EditorialSubmission,
    EditorialUnit,
    SubmissionAuthorRelease,
    SubmissionWithdrawalRequest,
)
from src.models.report import Report
from tests.test_api.conftest import create_user


def _login(client: TestClient, email: str) -> None:
    response = client.post(
        "/api/auth/login",
        json={"email": email, "password": "secret123"},
    )
    assert response.status_code == 200


def _active_unit(
    client: TestClient,
    db_session: Session,
) -> tuple[EditorialUnit, str]:
    admin = create_user(db_session, email="admin@example.com", role="admin")
    editor = create_user(db_session, email="editor@example.com", role="editor")
    _login(client, admin.email)
    unit_id = client.post("/api/admin/editorial/bootstrap").json()["items"][0]["id"]
    client.post(
        f"/api/admin/editorial/units/{unit_id}/members",
        json={"user_id": editor.id, "membership_role": "unit_admin"},
    )
    unit = db_session.get(EditorialUnit, unit_id)
    version = db_session.get(EditorialPolicyVersion, unit.trial_policy_version_id)
    version.status = "active"
    unit.active_policy_version_id = version.id
    unit.trial_policy_version_id = None
    unit.rollout_state = "active"
    db_session.commit()
    return unit, editor.id


def test_submitter_selects_active_journal_and_report_requires_editor_release(
    client: TestClient,
    db_session: Session,
    tmp_path: Path,
    monkeypatch,
) -> None:
    import src.core.storage

    monkeypatch.setattr(src.core.storage, "UPLOAD_ROOT", tmp_path / "uploads")
    unit, editor_id = _active_unit(client, db_session)
    submitter = create_user(
        db_session,
        email="author@example.com",
        role="submitter",
        display_name="投稿人甲",
    )

    async def runner(_: str, __: Session) -> None:
        return None

    client.app.state.editorial_pipeline_runner = runner
    client.cookies.clear()
    _login(client, submitter.email)
    journals = client.get("/api/submitter/journals")
    assert journals.status_code == 200
    assert journals.json()[0]["unit_id"] == unit.id
    assert "provider_names" not in journals.json()[0]
    bypass = client.post(
        "/api/papers",
        data={"provider_names": "glm-5.2"},
        files={"file": ("bypass.txt", b"bypass", "text/plain")},
    )
    assert bypass.status_code == 403

    uploaded = client.post(
        "/api/submitter/submissions",
        data={"unit_id": unit.id, "title": "平台治理的法理结构"},
        files={"file": ("paper.txt", ("正文内容" * 80).encode(), "text/plain")},
    )
    assert uploaded.status_code == 202
    submission = db_session.get(
        EditorialSubmission,
        uploaded.json()["submission_id"],
    )
    submission.responsible_editor_id = editor_id
    decision = EditorialDecision(
        submission_id=submission.id,
        version=1,
        decision_stage="pre_review",
        final_decision="revise_resubmit",
        recommendation_state="ready",
        actor_id=editor_id,
        is_locked=True,
    )
    db_session.add(decision)
    db_session.flush()
    report = Report(
        task_id=submission.evaluation_task_id,
        paper_id=submission.paper_id,
        version=1,
        report_type="public",
        is_current=True,
        weighted_total=75,
        report_data={"paper_id": submission.paper_id, "weighted_total": 75},
    )
    db_session.add(report)
    db_session.commit()

    blocked = client.get(f"/api/papers/{submission.paper_id}/report")
    assert blocked.status_code == 409

    client.cookies.clear()
    _login(client, "editor@example.com")
    detail = client.get(f"/api/editorial/submissions/{submission.id}")
    assert detail.status_code == 200
    assert detail.json()["submitter"]["email"] == submitter.email
    released = client.post(
        f"/api/editorial/submissions/{submission.id}/author-release",
        json={
            "decision_id": decision.id,
            "author_message": "请根据编辑意见修改后重新投稿。",
        },
    )
    assert released.status_code == 201
    assert db_session.query(SubmissionAuthorRelease).count() == 1

    client.cookies.clear()
    _login(client, submitter.email)
    visible = client.get(f"/api/papers/{submission.paper_id}/report")
    assert visible.status_code == 200
    assert visible.json()["weighted_total"] == 75
    report.is_current = False
    db_session.add(
        Report(
            task_id=submission.evaluation_task_id,
            paper_id=submission.paper_id,
            version=2,
            report_type="public",
            is_current=True,
            weighted_total=99,
            report_data={"paper_id": submission.paper_id, "weighted_total": 99},
        )
    )
    db_session.commit()
    still_released_snapshot = client.get(f"/api/papers/{submission.paper_id}/report")
    assert still_released_snapshot.status_code == 200
    assert still_released_snapshot.json()["weighted_total"] == 75
    author_row = client.get(f"/api/submitter/submissions/{submission.id}").json()
    assert author_row["report_released"] is True
    assert author_row["public_decision"] == "revise_resubmit"


def test_withdrawal_request_preserves_submission_and_requires_editor_decision(
    client: TestClient,
    db_session: Session,
    tmp_path: Path,
    monkeypatch,
) -> None:
    import src.core.storage

    monkeypatch.setattr(src.core.storage, "UPLOAD_ROOT", tmp_path / "uploads")
    unit, editor_id = _active_unit(client, db_session)
    submitter = create_user(
        db_session,
        email="author@example.com",
        role="submitter",
    )

    async def runner(_: str, __: Session) -> None:
        return None

    client.app.state.editorial_pipeline_runner = runner
    client.cookies.clear()
    _login(client, submitter.email)
    uploaded = client.post(
        "/api/submitter/submissions",
        data={"unit_id": unit.id, "title": "撤稿测试论文"},
        files={"file": ("paper.txt", ("正文内容" * 80).encode(), "text/plain")},
    )
    submission = db_session.get(
        EditorialSubmission,
        uploaded.json()["submission_id"],
    )
    submission.responsible_editor_id = editor_id
    db_session.commit()
    requested = client.post(
        f"/api/submitter/submissions/{submission.id}/withdrawal-requests",
        json={"reason": "作者需要补充关键材料后重新投稿。"},
    )
    assert requested.status_code == 201

    client.cookies.clear()
    _login(client, "editor@example.com")
    decided = client.post(
        f"/api/editorial/submissions/{submission.id}/withdrawal-requests/"
        f"{requested.json()['id']}/decision",
        json={"approved": True, "decision_note": "同意撤回并保留审计记录。"},
    )
    assert decided.status_code == 200
    db_session.refresh(submission)
    assert submission.status == "withdrawn"
    assert db_session.query(SubmissionWithdrawalRequest).one().status == "approved"
    assert db_session.get(EditorialSubmission, submission.id) is not None
