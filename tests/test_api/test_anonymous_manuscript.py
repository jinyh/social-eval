from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.models.audit import AuditLog
from src.models.editorial import EditorialDocument, EditorialSubmission
from src.models.evaluation import EvaluationTask
from src.models.review import ExpertReview
from tests.test_api.conftest import create_user


def _login(client: TestClient, email: str) -> None:
    response = client.post(
        "/api/auth/login",
        json={"email": email, "password": "secret123"},
    )
    assert response.status_code == 200


def _create_editorial_submission(
    client: TestClient,
    db: Session,
    tmp_path: Path,
    monkeypatch,
) -> tuple[EditorialSubmission, EvaluationTask]:
    import src.core.storage

    monkeypatch.setattr(src.core.storage, "UPLOAD_ROOT", tmp_path / "uploads")

    async def runner(_: str, __: Session) -> None:
        return None

    client.app.state.editorial_pipeline_runner = runner
    admin = create_user(db, email="anonymous-admin@example.com", role="admin")
    editor = create_user(db, email="anonymous-editor@example.com", role="editor")
    _login(client, admin.email)
    bootstrapped = client.post("/api/admin/editorial/bootstrap")
    unit_id = bootstrapped.json()["items"][0]["id"]
    client.post(
        f"/api/admin/editorial/units/{unit_id}/members",
        json={"user_id": editor.id, "membership_role": "editor"},
    )
    client.cookies.clear()
    _login(client, editor.email)
    uploaded = client.post(
        "/api/editorial/submissions",
        data={
            "unit_id": unit_id,
            "external_manuscript_id": "ANON-001",
        },
        files={
            "file": (
                "张三投稿.txt",
                ("匿名正文内容" * 80).encode(),
                "text/plain",
            )
        },
    )
    submission = db.get(EditorialSubmission, uploaded.json()["submission_id"])
    task = db.get(EvaluationTask, uploaded.json()["task_id"])
    assert submission is not None
    assert task is not None
    return submission, task


def test_expert_reads_only_human_confirmed_task_bound_manuscript(
    client: TestClient,
    db_session: Session,
    tmp_path: Path,
    monkeypatch,
) -> None:
    submission, task = _create_editorial_submission(
        client,
        db_session,
        tmp_path,
        monkeypatch,
    )
    text_path = tmp_path / "anonymous-v1.txt"
    text_path.write_text("匿名稿正文", encoding="utf-8")
    view_path = tmp_path / "anonymous-view-v1.json"
    view_path.write_text(
        json.dumps(
            {
                "blocks": [
                    {"type": "heading", "level": 1, "text": "匿名标题"},
                    {"type": "paragraph", "text": "匿名稿正文"},
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    db_session.add_all(
        [
            EditorialDocument(
                submission_id=submission.id,
                kind="anonymized",
                version=1,
                file_path=str(text_path),
                sha256="text-sha",
            ),
            EditorialDocument(
                submission_id=submission.id,
                kind="anonymized_view",
                version=1,
                file_path=str(view_path),
                sha256="view-sha",
            ),
        ]
    )
    task.input_file_path = str(text_path)
    submission.anonymization_result = {
        "policy_version": "anonymous-manuscript-v1",
        "human_confirmed": False,
    }
    expert = create_user(
        db_session,
        email="assigned-expert@example.com",
        role="expert",
    )
    other_expert = create_user(
        db_session,
        email="other-expert@example.com",
        role="expert",
    )
    review = ExpertReview(task_id=task.id, expert_id=expert.id)
    db_session.add_all([task, submission, review])
    db_session.commit()
    db_session.refresh(review)

    client.cookies.clear()
    _login(client, expert.email)
    blocked = client.get(f"/api/reviews/{review.id}/manuscript")
    assert blocked.status_code == 409

    submission.anonymization_result = {
        "policy_version": "anonymous-manuscript-v1",
        "human_confirmed": True,
    }
    db_session.commit()
    response = client.get(f"/api/reviews/{review.id}/manuscript")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    payload = response.json()
    assert payload["manuscript_id"] == "ANON-001"
    assert payload["document_version"] == 1
    assert payload["blocks"][0]["text"] == "匿名标题"
    assert "张三投稿.txt" not in response.text

    mine = client.get("/api/reviews/mine")
    assert mine.status_code == 200
    assert mine.json()["items"][0]["paper_title"] == "匿名稿件 ANON-001"

    client.cookies.clear()
    _login(client, other_expert.email)
    assert client.get(f"/api/reviews/{review.id}/manuscript").status_code == 404
    audit = (
        db_session.query(AuditLog)
        .filter(AuditLog.action == "view_anonymized_review_document")
        .one()
    )
    assert audit.actor_id == expert.id
