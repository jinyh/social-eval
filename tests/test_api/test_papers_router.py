from __future__ import annotations

from dataclasses import dataclass

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.evaluation.schemas import DimensionResult
from src.models.evaluation import DimensionScore
from src.models.reliability import ReliabilityResult
from tests.test_api.conftest import create_user


@dataclass
class FakeProvider:
    model_name: str
    score: int
    precheck_status: str = "pass"
    review_flags: list[str] | None = None

    async def evaluate_dimension(self, prompt: str) -> DimensionResult:
        return DimensionResult(
            dimension="placeholder",
            score=self.score,
            evidence_quotes=["引文"],
            analysis=f"{self.model_name} analysis",
            review_flags=self.review_flags or [],
            model_name=self.model_name,
        )

    async def generate_json_response(self, prompt: str) -> dict:
        return {
            "status": self.precheck_status,
            "issues": [] if self.precheck_status == "pass" else ["写作规范性不足"],
            "recommendation": "continue" if self.precheck_status == "pass" else "reject",
        }


def _install_sync_pipeline(client: TestClient, providers: list[FakeProvider]) -> None:
    from src.evaluation.orchestrator import run_evaluation_pipeline

    async def pipeline_runner(task_id: str, db: Session) -> None:
        await run_evaluation_pipeline(
            task_id,
            db,
            provider_factory=lambda _: providers,
        )

    client.app.state.pipeline_runner = pipeline_runner


def _login_submitter(client: TestClient, db_session: Session) -> None:
    create_user(
        db_session,
        email="submitter@example.com",
        role="submitter",
        display_name="Submitter",
    )
    login_response = client.post(
        "/api/auth/login",
        json={"email": "submitter@example.com", "password": "secret123"},
    )
    assert login_response.status_code == 200


def test_upload_txt_file_runs_pipeline_and_persists_results(
    client: TestClient, db_session: Session
) -> None:
    _login_submitter(client, db_session)
    _install_sync_pipeline(
        client,
        [
            FakeProvider("mock-a", 80),
            FakeProvider("mock-b", 82),
            FakeProvider("mock-c", 84),
        ],
    )

    upload_response = client.post(
        "/api/papers",
        files={"file": ("paper.txt", "摘要\n正文内容\n参考文献\n[1] 文献".encode("utf-8"), "text/plain")},
        data={"provider_names": "mock-a,mock-b,mock-c"},
    )
    assert upload_response.status_code == 202

    payload = upload_response.json()
    status_response = client.get(f"/api/papers/{payload['paper_id']}/status")
    assert status_response.status_code == 200
    body = status_response.json()
    assert body["paper_status"] == "completed"
    assert body["task_status"] == "completed"
    assert body["precheck_status"] == "pass"
    assert body["reliability_summary"]["total_dimensions"] == 6
    assert body["reliability_summary"]["overall_high_confidence"] is True

    assert db_session.query(DimensionScore).count() == 18
    assert db_session.query(ReliabilityResult).count() == 6


def test_precheck_reject_short_circuits_dimension_scoring(
    client: TestClient, db_session: Session
) -> None:
    _login_submitter(client, db_session)
    _install_sync_pipeline(
        client,
        [
            FakeProvider("mock-a", 10, precheck_status="reject"),
            FakeProvider("mock-b", 20, precheck_status="reject"),
            FakeProvider("mock-c", 30, precheck_status="reject"),
        ],
    )

    upload_response = client.post(
        "/api/papers",
        files={"file": ("paper.txt", "正文".encode("utf-8"), "text/plain")},
        data={"provider_names": "mock-a,mock-b,mock-c"},
    )
    assert upload_response.status_code == 202

    payload = upload_response.json()
    status_response = client.get(f"/api/papers/{payload['paper_id']}/status")
    assert status_response.status_code == 200
    body = status_response.json()
    assert body["precheck_status"] == "reject"
    assert body["task_status"] == "completed"
    assert body["reliability_summary"] is None
    assert db_session.query(DimensionScore).count() == 0


def test_upload_rejects_unsupported_file_type(
    client: TestClient, db_session: Session
) -> None:
    _login_submitter(client, db_session)

    response = client.post(
        "/api/papers",
        files={"file": ("paper.doc", b"binary", "application/msword")},
    )

    assert response.status_code == 400


def test_batch_upload_returns_multiple_tasks(
    client: TestClient, db_session: Session
) -> None:
    _login_submitter(client, db_session)
    _install_sync_pipeline(
        client,
        [
            FakeProvider("mock-a", 75),
            FakeProvider("mock-b", 78),
            FakeProvider("mock-c", 81),
        ],
    )

    response = client.post(
        "/api/papers/batch",
        files=[
            ("files", ("one.txt", "正文一".encode("utf-8"), "text/plain")),
            ("files", ("two.txt", "正文二".encode("utf-8"), "text/plain")),
        ],
        data={"provider_names": "mock-a,mock-b,mock-c"},
    )

    assert response.status_code == 202
    body = response.json()
    assert body["total"] == 2
    assert len(body["items"]) == 2
