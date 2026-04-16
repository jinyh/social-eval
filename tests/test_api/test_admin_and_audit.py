from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.test_api.conftest import create_user
from tests.test_api.test_papers_router import FakeProvider, _install_sync_pipeline


def _login(client: TestClient, email: str, password: str = "secret123") -> None:
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200


def _safe_runner_with_providers(client: TestClient, providers: list[FakeProvider]) -> None:
    from src.evaluation.orchestrator import run_evaluation_pipeline

    async def runner(task_id: str, db: Session) -> None:
        try:
            await run_evaluation_pipeline(task_id, db, provider_factory=lambda _: providers)
        except Exception:
            pass

    client.app.state.pipeline_runner = runner


def test_internal_report_access_creates_audit_log(
    client: TestClient, db_session: Session
) -> None:
    from src.models.audit import AuditLog

    create_user(db_session, email="submitter@example.com", role="submitter")
    create_user(db_session, email="editor@example.com", role="editor")

    _login(client, "submitter@example.com")
    _install_sync_pipeline(client, [FakeProvider("mock-a", 80), FakeProvider("mock-b", 82), FakeProvider("mock-c", 84)])
    upload_response = client.post(
        "/api/papers",
        files={"file": ("paper.txt", "正文".encode("utf-8"), "text/plain")},
        data={"provider_names": "mock-a,mock-b,mock-c"},
    )
    assert upload_response.status_code == 202
    paper_id = upload_response.json()["paper_id"]

    client.cookies.clear()
    _login(client, "editor@example.com")
    report_response = client.get(f"/api/papers/{paper_id}/internal-report")
    assert report_response.status_code == 200

    audit_logs = db_session.query(AuditLog).all()
    assert audit_logs[0].action == "internal_report_access"


def test_admin_can_retry_failed_task_and_close_task(
    client: TestClient, db_session: Session
) -> None:
    create_user(db_session, email="submitter@example.com", role="submitter")
    create_user(db_session, email="admin@example.com", role="admin")

    class FailingProvider(FakeProvider):
        async def evaluate_dimension(self, prompt: str):
            raise RuntimeError("provider failure")

        async def generate_json_response(self, prompt: str) -> dict:
            return {"status": "pass", "issues": [], "recommendation": "continue"}

    _login(client, "submitter@example.com")
    _safe_runner_with_providers(client, [FailingProvider("mock-a", 0), FailingProvider("mock-b", 0), FailingProvider("mock-c", 0)])
    upload_response = client.post(
        "/api/papers",
        files={"file": ("paper.txt", "正文".encode("utf-8"), "text/plain")},
        data={"provider_names": "mock-a,mock-b,mock-c"},
    )
    assert upload_response.status_code == 202
    payload = upload_response.json()

    status_response = client.get(f"/api/papers/{payload['paper_id']}/status")
    assert status_response.status_code == 200
    assert status_response.json()["task_status"] == "recovering"

    client.cookies.clear()
    _login(client, "admin@example.com")
    _install_sync_pipeline(client, [FakeProvider("mock-a", 75), FakeProvider("mock-b", 78), FakeProvider("mock-c", 81)])
    retry_response = client.post(f"/api/admin/tasks/{payload['task_id']}/retry")
    assert retry_response.status_code == 200
    assert retry_response.json()["task_status"] == "completed"

    close_response = client.post(f"/api/admin/tasks/{payload['task_id']}/close")
    assert close_response.status_code == 200
    assert close_response.json()["task_status"] == "closed"


def test_batch_status_aggregates_child_tasks(
    client: TestClient, db_session: Session
) -> None:
    create_user(db_session, email="submitter@example.com", role="submitter")

    _login(client, "submitter@example.com")
    _install_sync_pipeline(client, [FakeProvider("mock-a", 80), FakeProvider("mock-b", 81), FakeProvider("mock-c", 82)])
    batch_response = client.post(
        "/api/papers/batch",
        files=[
            ("files", ("one.txt", "正文一".encode("utf-8"), "text/plain")),
            ("files", ("two.txt", "正文二".encode("utf-8"), "text/plain")),
        ],
        data={"provider_names": "mock-a,mock-b,mock-c"},
    )
    assert batch_response.status_code == 202
    batch_id = batch_response.json()["batch_id"]

    status_response = client.get(f"/api/papers/batch/{batch_id}/status")
    assert status_response.status_code == 200
    body = status_response.json()
    assert body["total"] == 2
    assert body["completed"] == 2
    assert body["failed"] == 0
