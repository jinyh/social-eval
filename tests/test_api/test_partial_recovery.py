from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.evaluation.orchestrator import run_evaluation_pipeline
from src.evaluation.schemas import DimensionResult
from src.models.evaluation import DimensionScore
from tests.test_api.conftest import create_user
from tests.test_api.test_papers_router import FakeProvider, _install_sync_pipeline


def _login(client: TestClient, email: str) -> None:
    response = client.post(
        "/api/auth/login",
        json={"email": email, "password": "secret123"},
    )
    assert response.status_code == 200


def test_retry_only_reruns_missing_first_round_models(
    client: TestClient, db_session: Session
) -> None:
    create_user(db_session, email="submitter@example.com", role="submitter")
    create_user(db_session, email="admin@example.com", role="admin")

    class PartialProvider(FakeProvider):
        fail_analytical_framework = False
        analytical_framework_calls = 0

        async def evaluate_dimension(self, prompt: str) -> DimensionResult:
            if '"dimension": "analytical_framework"' in prompt:
                self.analytical_framework_calls += 1
                if self.fail_analytical_framework:
                    raise RuntimeError("模拟理论建构力模型失败")
            return await super().evaluate_dimension(prompt)

    stable_a = PartialProvider("mock-a", 75)
    stable_b = PartialProvider("mock-b", 78)
    recovering = PartialProvider("mock-c", 81)
    recovering.fail_analytical_framework = True
    providers = [stable_a, stable_b, recovering]

    async def safe_runner(task_id: str, db: Session) -> None:
        try:
            await run_evaluation_pipeline(
                task_id,
                db,
                provider_factory=lambda _: providers,
            )
        except Exception:
            pass

    _login(client, "submitter@example.com")
    client.app.state.pipeline_runner = safe_runner
    upload_response = client.post(
        "/api/papers",
        files={"file": ("paper.txt", "摘要\n正文".encode(), "text/plain")},
        data={"provider_names": "mock-a,mock-b,mock-c"},
    )
    assert upload_response.status_code == 202
    payload = upload_response.json()
    assert (
        db_session.query(DimensionScore)
        .filter_by(
            task_id=payload["task_id"],
            dimension_key="analytical_framework",
            round_number=1,
        )
        .count()
        == 2
    )
    stable_call_counts = (
        stable_a.analytical_framework_calls,
        stable_b.analytical_framework_calls,
    )

    recovering.fail_analytical_framework = False
    client.cookies.clear()
    _login(client, "admin@example.com")
    _install_sync_pipeline(client, providers)
    retry_response = client.post(f"/api/admin/tasks/{payload['task_id']}/retry")

    assert retry_response.status_code == 200
    assert retry_response.json()["task_status"] == "completed"
    assert (
        db_session.query(DimensionScore)
        .filter_by(
            task_id=payload["task_id"],
            dimension_key="analytical_framework",
            round_number=1,
        )
        .count()
        == 3
    )
    assert (
        stable_a.analytical_framework_calls,
        stable_b.analytical_framework_calls,
    ) == stable_call_counts
