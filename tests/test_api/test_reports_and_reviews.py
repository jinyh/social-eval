from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.test_api.conftest import create_user
from tests.test_api.test_papers_router import FakeProvider, _install_sync_pipeline


def _login(client: TestClient, email: str, password: str = "secret123") -> None:
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200


def _upload_with_scores(
    client: TestClient,
    provider_scores: list[int],
) -> dict:
    providers = [
        FakeProvider(f"mock-{index}", score)
        for index, score in enumerate(provider_scores, start=1)
    ]
    _install_sync_pipeline(client, providers)
    response = client.post(
        "/api/papers",
        files={"file": ("paper.txt", "正文内容".encode("utf-8"), "text/plain")},
        data={"provider_names": ",".join(provider.model_name for provider in providers)},
    )
    assert response.status_code == 202
    return response.json()


def test_internal_and_public_report_endpoints_expose_different_detail_levels(
    client: TestClient, db_session: Session
) -> None:
    create_user(db_session, email="submitter@example.com", role="submitter", display_name="Submitter")
    create_user(db_session, email="editor@example.com", role="editor", display_name="Editor")

    _login(client, "submitter@example.com")
    payload = _upload_with_scores(client, [80, 82, 84])

    client.cookies.clear()
    _login(client, "editor@example.com")
    internal_response = client.get(f"/api/papers/{payload['paper_id']}/internal-report")
    assert internal_response.status_code == 200
    task_scoped_response = client.get(
        f"/api/papers/{payload['paper_id']}/internal-report",
        params={"task_id": payload["task_id"]},
    )
    assert task_scoped_response.status_code == 200
    assert task_scoped_response.json()["task_id"] == payload["task_id"]
    wrong_task_response = client.get(
        f"/api/papers/{payload['paper_id']}/internal-report",
        params={"task_id": "not-a-task"},
    )
    assert wrong_task_response.status_code == 404
    internal_body = internal_response.json()
    assert internal_body["report_type"] == "internal"
    assert "model_scores" in internal_body["dimensions"][0]["ai"]

    client.cookies.clear()
    _login(client, "submitter@example.com")
    public_response = client.get(f"/api/papers/{payload['paper_id']}/report")
    assert public_response.status_code == 200
    public_body = public_response.json()
    assert public_body["report_type"] == "public"
    assert "model_scores" not in public_body["dimensions"][0]["ai"]


def test_report_export_supports_json_and_pdf(
    client: TestClient, db_session: Session
) -> None:
    create_user(db_session, email="submitter@example.com", role="submitter")
    create_user(db_session, email="editor@example.com", role="editor")

    _login(client, "submitter@example.com")
    payload = _upload_with_scores(client, [78, 79, 80])

    client.cookies.clear()
    _login(client, "editor@example.com")
    json_export = client.get(
        f"/api/papers/{payload['paper_id']}/report/export",
        params={"format": "json", "report_type": "internal"},
    )
    assert json_export.status_code == 200
    assert json_export.headers["content-type"].startswith("application/json")

    pdf_export = client.get(
        f"/api/papers/{payload['paper_id']}/report/export",
        params={"format": "pdf", "report_type": "internal"},
    )
    assert pdf_export.status_code == 200
    assert pdf_export.headers["content-type"].startswith("application/pdf")
    assert pdf_export.content.startswith(b"%PDF")


def test_low_confidence_task_appears_in_review_queue_and_editor_can_assign_expert(
    client: TestClient, db_session: Session
) -> None:
    create_user(db_session, email="submitter@example.com", role="submitter")
    editor = create_user(db_session, email="editor@example.com", role="editor")
    expert = create_user(db_session, email="expert@example.com", role="expert")
    sent_notifications: list[dict] = []
    client.app.state.email_sender = lambda **kwargs: sent_notifications.append(kwargs)

    _login(client, "submitter@example.com")
    payload = _upload_with_scores(client, [40, 75, 95])

    client.cookies.clear()
    _login(client, "editor@example.com")
    queue_response = client.get("/api/reviews/queue")
    assert queue_response.status_code == 200
    assert queue_response.json()["items"][0]["task_id"] == payload["task_id"]

    assign_response = client.post(
        f"/api/reviews/{payload['task_id']}/assign",
        json={"expert_ids": [expert.id]},
    )
    assert assign_response.status_code == 201
    assert assign_response.json()["assigned_count"] == 1
    assert sent_notifications[0]["expert_email"] == "expert@example.com"


def test_expert_can_submit_review_and_internal_report_contains_feedback(
    client: TestClient, db_session: Session
) -> None:
    create_user(db_session, email="submitter@example.com", role="submitter")
    create_user(db_session, email="editor@example.com", role="editor")
    expert = create_user(db_session, email="expert@example.com", role="expert")
    client.app.state.email_sender = lambda **kwargs: None

    _login(client, "submitter@example.com")
    payload = _upload_with_scores(client, [45, 70, 95])

    client.cookies.clear()
    _login(client, "editor@example.com")
    assign_response = client.post(
        f"/api/reviews/{payload['task_id']}/assign",
        json={"expert_ids": [expert.id]},
    )
    assert assign_response.status_code == 201

    client.cookies.clear()
    _login(client, "expert@example.com")
    mine_response = client.get("/api/reviews/mine")
    assert mine_response.status_code == 200
    mine_item = mine_response.json()["items"][0]
    review_id = mine_item["review_id"]
    assert mine_item["paper_id"] == payload["paper_id"]
    assert mine_item["paper_title"] == "paper"

    expert_internal_response = client.get(
        f"/api/papers/{mine_item['paper_id']}/internal-report",
        params={"task_id": mine_item["task_id"]},
    )
    assert expert_internal_response.status_code == 200
    assert expert_internal_response.json()["task_id"] == mine_item["task_id"]

    submit_response = client.post(
        f"/api/reviews/{review_id}/submit",
        json={
            "comments": [
                {
                    "dimension_key": key,
                    "ai_score": 70,
                    "expert_score": 72,
                    "reason": "专家修正意见",
                }
                for key in [
                    "problem_originality",
                    "literature_insight",
                    "analytical_framework",
                    "logical_coherence",
                    "conclusion_consensus",
                    "forward_extension",
                ]
            ]
        },
    )
    assert submit_response.status_code == 200

    client.cookies.clear()
    _login(client, "editor@example.com")
    internal_response = client.get(f"/api/papers/{payload['paper_id']}/internal-report")
    assert internal_response.status_code == 200
    assert internal_response.json()["expert_reviews"][0]["expert_id"] == expert.id


def test_unassigned_expert_cannot_access_other_paper_reports_or_status(
    client: TestClient, db_session: Session
) -> None:
    create_user(db_session, email="submitter@example.com", role="submitter")
    create_user(db_session, email="expert@example.com", role="expert")

    _login(client, "submitter@example.com")
    payload = _upload_with_scores(client, [78, 79, 80])

    client.cookies.clear()
    _login(client, "expert@example.com")

    report_response = client.get(f"/api/papers/{payload['paper_id']}/report")
    assert report_response.status_code == 403

    export_response = client.get(f"/api/papers/{payload['paper_id']}/export/simple")
    assert export_response.status_code == 403

    status_response = client.get(f"/api/papers/{payload['paper_id']}/status")
    assert status_response.status_code == 403


def test_submit_review_rejects_out_of_range_scores(
    client: TestClient, db_session: Session
) -> None:
    create_user(db_session, email="submitter@example.com", role="submitter")
    create_user(db_session, email="editor@example.com", role="editor")
    expert = create_user(db_session, email="expert@example.com", role="expert")
    client.app.state.email_sender = lambda **kwargs: None

    _login(client, "submitter@example.com")
    payload = _upload_with_scores(client, [45, 70, 95])

    client.cookies.clear()
    _login(client, "editor@example.com")
    assign_response = client.post(
        f"/api/reviews/{payload['task_id']}/assign",
        json={"expert_ids": [expert.id]},
    )
    assert assign_response.status_code == 201

    client.cookies.clear()
    _login(client, "expert@example.com")
    review_id = client.get("/api/reviews/mine").json()["items"][0]["review_id"]
    response = client.post(
        f"/api/reviews/{review_id}/submit",
        json={
            "comments": [
                {
                    "dimension_key": "problem_originality",
                    "ai_score": 70,
                    "expert_score": 120,
                    "reason": "invalid score",
                }
            ]
        },
    )
    assert response.status_code == 422
