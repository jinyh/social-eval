import asyncio
import time
from sqlalchemy.orm import Session

from src.core.config import settings
from src.core.exceptions import (
    ProviderResponseValidationError,
    ProviderTimeoutError,
)
from src.evaluation.providers.base import BaseProvider
from src.evaluation.result_validator import normalize_dimension_result
from src.evaluation.schemas import DimensionResult
from src.knowledge.schemas import Dimension
from src.ingestion.schemas import ProcessedPaper
from src.evaluation.prompt_builder import build_prompt
from src.evaluation.call_logger import log_call


def _get_timeout(provider: BaseProvider) -> float:
    val = getattr(provider, "timeout", None)
    return val if isinstance(val, (int, float)) else settings.provider_timeout


def _corrective_retry_prompt(
    original_prompt: str,
    error: ProviderResponseValidationError,
) -> str:
    """为结构校验失败的重试明确指出字段问题，仍要求重新返回完整 JSON。"""

    fields = "、".join(error.invalid_fields) or "一个或多个必填字段"
    return (
        f"{original_prompt}\n\n"
        "【结构化输出纠错】上一次输出未通过系统校验。"
        f"问题字段：{fields}。请重新阅读上面的完整输出契约，"
        "重新返回一份完整 JSON；不得只补充缺失字段，也不要输出解释文字。"
    )


async def _call_with_timing(
    provider: BaseProvider,
    prompt: str,
    task_id: str | None = None,
    dimension_key: str | None = None,
    db: Session | None = None,
    retry_attempts: int = 3,
) -> tuple[DimensionResult | Exception, float, str]:
    last_error: Exception | None = None
    attempt_prompt = prompt
    for _ in range(retry_attempts):
        start = time.time()
        try:
            timeout = _get_timeout(provider)
            result = await asyncio.wait_for(
                provider.evaluate_dimension(attempt_prompt),
                timeout=timeout,
            )
            return result, start, attempt_prompt
        except asyncio.TimeoutError:
            last_error = ProviderTimeoutError(
                provider.model_name, _get_timeout(provider)
            )
        except Exception as exc:
            last_error = exc
        if (
            last_error is not None
            and db is not None
            and task_id is not None
            and dimension_key is not None
        ):
            log_call(
                db,
                task_id,
                provider.model_name,
                dimension_key,
                attempt_prompt,
                str(getattr(last_error, "raw_response", None) or last_error),
                start,
                provider_name=provider.__class__.__name__,
                status="failed",
                failure_detail=str(last_error),
            )
        if isinstance(last_error, ProviderResponseValidationError):
            attempt_prompt = _corrective_retry_prompt(prompt, last_error)
    return (
        last_error or RuntimeError("Unknown evaluation failure"),
        start,
        attempt_prompt,
    )


async def evaluate_dimension_concurrent(
    providers: list[BaseProvider],
    dimension: Dimension,
    paper: ProcessedPaper,
    task_id: str,
    db: Session,
) -> list[DimensionResult]:
    """并发调用所有 Provider 评估单个维度，记录每次调用日志，返回成功结果列表"""
    prompt = build_prompt(dimension, paper)
    raw_results = await asyncio.gather(
        *[
            _call_with_timing(
                p,
                prompt,
                task_id,
                dimension.key,
                db,
            )
            for p in providers
        ],
        return_exceptions=False,
    )
    results = []
    for (outcome, start_time, used_prompt), provider in zip(raw_results, providers):
        raw_response_text = (
            outcome.model_dump_json()
            if isinstance(outcome, DimensionResult)
            else str(outcome)
        )
        response_text = raw_response_text

        if isinstance(outcome, DimensionResult):
            try:
                outcome = normalize_dimension_result(outcome, dimension)
                response_text = outcome.model_dump_json()
            except Exception as exc:
                response_text = f"{raw_response_text}\n\nVALIDATION_ERROR: {exc}"
                log_call(
                    db,
                    task_id,
                    provider.model_name,
                    dimension.key,
                    used_prompt,
                    response_text,
                    start_time,
                    provider_name=provider.__class__.__name__,
                    status="failed",
                    failure_detail=str(exc),
                )
                continue

        if isinstance(outcome, DimensionResult):
            log_call(
                db,
                task_id,
                provider.model_name,
                dimension.key,
                used_prompt,
                response_text,
                start_time,
                provider_name=provider.__class__.__name__,
            )
            results.append(outcome)
    return results
