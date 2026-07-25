from __future__ import annotations

import asyncio

import pytest

from src.core.exceptions import ProviderTimeoutError
from src.evaluation.precheck import run_precheck
from src.evaluation.providers.base import BaseProvider
from src.evaluation.schemas import DimensionResult
from src.ingestion.schemas import ProcessedPaper
from src.knowledge.schemas import Framework, PrecheckConfig


class SlowPrecheckProvider(BaseProvider):
    model_name = "slow-precheck"
    timeout = 0.01

    async def generate_json_response(self, prompt: str) -> dict:
        await asyncio.sleep(1)
        return {"status": "pass"}

    async def evaluate_dimension(self, prompt: str) -> DimensionResult:
        raise NotImplementedError


@pytest.mark.asyncio
async def test_precheck_honors_provider_timeout(monkeypatch):
    failures: list[str] = []
    monkeypatch.setattr(
        "src.evaluation.precheck.log_call",
        lambda *args, **kwargs: failures.append(kwargs["failure_detail"]),
    )
    framework = Framework(
        name="测试框架",
        discipline="law",
        version="test",
        std_threshold=8,
        dimensions=[],
        precheck=PrecheckConfig(
            name="公共预检",
            description="测试",
            criteria=[],
            prompt_template="检查：{paper_content}",
        ),
    )
    paper = ProcessedPaper(
        full_text="测试正文",
        body="测试正文",
        structure_status="detected",
    )

    with pytest.raises(ProviderTimeoutError):
        await run_precheck(
            SlowPrecheckProvider(),
            framework,
            paper,
            task_id="task-timeout",
            db=None,  # type: ignore[arg-type]
            retry_attempts=1,
        )

    assert len(failures) == 1
    assert "0.01s" in failures[0]
