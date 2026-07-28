import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from src.core.exceptions import ProviderTimeoutError
from src.editorial.ai_anonymization import (
    apply_identity_findings,
    candidate_blocks,
    IdentityFinding,
    run_ai_anonymization,
)
from src.evaluation.providers.base import BaseProvider


class FakeAnonymizationProvider(BaseProvider):
    model_name = "glm-5.2"
    timeout = 1.0

    def __init__(self, payload: dict) -> None:
        self.payload = payload

    async def generate_json_response(self, prompt: str) -> dict:
        assert "待检测段落" in prompt
        return self.payload

    async def evaluate_dimension(self, prompt: str):
        raise NotImplementedError


def _write_artifacts(tmp_path: Path) -> tuple[Path, Path]:
    blocks = [
        {"type": "paragraph", "text": "张三"},
        {"type": "paragraph", "text": "上海交通大学凯原法学院"},
        {
            "type": "paragraph",
            "text": "正文引用上海交通大学发布的研究报告，但这不是作者单位。",
        },
    ]
    text_path = tmp_path / "anonymized.txt"
    view_path = tmp_path / "anonymized.json"
    text_path.write_text(
        "\n\n".join(block["text"] for block in blocks), encoding="utf-8"
    )
    view_path.write_text(
        json.dumps({"blocks": blocks}, ensure_ascii=False),
        encoding="utf-8",
    )
    return text_path, view_path


def test_candidate_blocks_keep_stable_source_indexes() -> None:
    blocks = [
        {"type": "page_break", "page": 1},
        {"type": "paragraph", "text": "论文标题"},
        {"type": "paragraph", "text": "作者简介：张三"},
    ]

    selected = candidate_blocks(blocks, max_blocks=10, max_characters=100)

    assert [row["block_index"] for row in selected] == [1, 2]


def test_apply_identity_findings_only_changes_the_selected_block(
    tmp_path: Path,
) -> None:
    text_path, view_path = _write_artifacts(tmp_path)

    applied, uncertainties, _, _ = apply_identity_findings(
        text_path=text_path,
        view_path=view_path,
        findings=[
            IdentityFinding(
                block_index=1,
                category="affiliation",
                exact_text="上海交通大学凯原法学院",
                confidence=0.99,
                reason="首页作者单位",
            )
        ],
        minimum_confidence=0.85,
    )

    view = json.loads(view_path.read_text(encoding="utf-8"))
    assert applied == 1
    assert uncertainties == []
    assert view["blocks"][1]["text"] == "[已隐去机构信息]"
    assert "上海交通大学发布的研究报告" in view["blocks"][2]["text"]


@pytest.mark.asyncio
async def test_glm_identity_detection_is_audited_and_applied(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    text_path, view_path = _write_artifacts(tmp_path)
    calls: list[dict] = []
    monkeypatch.setattr(
        "src.editorial.ai_anonymization.log_call",
        lambda *args, **kwargs: calls.append(kwargs),
    )
    provider = FakeAnonymizationProvider(
        {
            "findings": [
                {
                    "block_index": 0,
                    "category": "person_name",
                    "exact_text": "张三",
                    "confidence": 0.99,
                    "reason": "首页独立姓名行",
                },
                {
                    "block_index": 1,
                    "category": "affiliation",
                    "exact_text": "上海交通大学凯原法学院",
                    "confidence": 0.98,
                    "reason": "姓名后的作者单位",
                },
            ],
            "needs_manual_review": False,
            "uncertainty_reasons": [],
            "summary": "发现并处理姓名及作者单位",
        }
    )

    outcome = await run_ai_anonymization(
        provider=provider,
        task_id="task-1",
        db=Mock(),
        text_path=text_path,
        view_path=view_path,
        config={
            "minimum_confidence": 0.85,
            "max_candidate_blocks": 40,
            "max_block_characters": 1600,
            "instructions": "只识别投稿作者身份。",
            "output_contract": '{"findings": []}',
        },
    )

    assert outcome.status == "completed"
    assert outcome.applied_count == 2
    assert outcome.requires_manual_review is False
    assert "张三" not in text_path.read_text(encoding="utf-8")
    assert len(calls) == 1
    assert calls[0]["call_type"] == "anonymization_identity_detection"


class FlakyAnonymizationProvider(BaseProvider):
    """前 fail_times 次抛 ProviderTimeoutError，之后返回 payload。"""

    model_name = "glm-5.2"
    timeout = 1.0

    def __init__(self, fail_times: int, payload: dict) -> None:
        self.fail_times = fail_times
        self.calls = 0
        self.payload = payload

    async def generate_json_response(self, prompt: str) -> dict:
        self.calls += 1
        if self.calls <= self.fail_times:
            raise ProviderTimeoutError(self.model_name, self.timeout)
        return self.payload

    async def evaluate_dimension(self, prompt: str):
        raise NotImplementedError


def _anonymization_config() -> dict:
    return {
        "minimum_confidence": 0.85,
        "max_candidate_blocks": 40,
        "max_block_characters": 1600,
        "instructions": "只识别投稿作者身份。",
        "output_contract": '{"findings": []}',
    }


def _success_payload() -> dict:
    return {
        "findings": [],
        "needs_manual_review": False,
        "uncertainty_reasons": [],
        "summary": "未发现需要隐去的身份信息",
    }


@pytest.mark.asyncio
async def test_anonymization_retries_on_transient_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    text_path, view_path = _write_artifacts(tmp_path)
    calls: list[dict] = []
    monkeypatch.setattr(
        "src.editorial.ai_anonymization.log_call",
        lambda *args, **kwargs: calls.append(kwargs),
    )

    async def _no_sleep(_n: float) -> None:
        return None

    monkeypatch.setattr("src.editorial.ai_anonymization.asyncio.sleep", _no_sleep)

    provider = FlakyAnonymizationProvider(fail_times=2, payload=_success_payload())
    outcome = await run_ai_anonymization(
        provider=provider,
        task_id="task-retry",
        db=Mock(),
        text_path=text_path,
        view_path=view_path,
        config=_anonymization_config(),
    )

    assert outcome.status == "completed"
    assert provider.calls == 3
    assert len(calls) == 3
    assert [c.get("status", "success") for c in calls] == [
        "failed",
        "failed",
        "success",
    ]


@pytest.mark.asyncio
async def test_anonymization_fails_after_all_retries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    text_path, view_path = _write_artifacts(tmp_path)
    calls: list[dict] = []
    monkeypatch.setattr(
        "src.editorial.ai_anonymization.log_call",
        lambda *args, **kwargs: calls.append(kwargs),
    )

    async def _no_sleep(_n: float) -> None:
        return None

    monkeypatch.setattr("src.editorial.ai_anonymization.asyncio.sleep", _no_sleep)

    provider = FlakyAnonymizationProvider(fail_times=99, payload=_success_payload())
    outcome = await run_ai_anonymization(
        provider=provider,
        task_id="task-retry-fail",
        db=Mock(),
        text_path=text_path,
        view_path=view_path,
        config=_anonymization_config(),
    )

    assert outcome.status == "failed"
    assert outcome.requires_manual_review is True
    assert provider.calls == 3
    assert len(calls) == 3
    assert all(c["status"] == "failed" for c in calls)
    assert any("已重试 3 次" in reason for reason in outcome.uncertainty_reasons)
