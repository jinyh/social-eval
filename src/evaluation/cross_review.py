"""配置驱动的六维第二轮交叉评审共享服务。"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from src.core.config import settings
from src.evaluation.call_logger import log_call
from src.evaluation.schemas import DimensionResult
from src.ingestion.schemas import ProcessedPaper
from src.knowledge.registry import load_review_protocol
from src.knowledge.schemas import Dimension


@dataclass(frozen=True, slots=True)
class CrossReviewOutcome:
    """一个模型的第二轮标准结果及完整审计载荷。"""

    result: DimensionResult
    raw_payload: dict[str, Any]
    prompt: str


class CrossReviewService:
    """让宽松组与严格组只参考对方组意见完成第二轮复评。"""

    def __init__(self, protocol: dict[str, Any] | None = None) -> None:
        self.protocol = protocol or load_review_protocol()
        groups = self.protocol["model_groups"]
        self.lenient = tuple(groups["lenient"])
        self.strict = tuple(groups["strict"])
        self._semaphore = asyncio.Semaphore(
            int(self.protocol["execution"]["max_api_concurrency"])
        )

    def validate_provider_names(self, provider_names: list[str]) -> None:
        """启用 R2 时必须同时存在宽松组和严格组模型。"""

        names = set(provider_names)
        if not names.intersection(self.lenient) or not names.intersection(self.strict):
            raise ValueError("启用交叉评审必须同时配置宽松组和严格组模型")
        known = set(self.lenient) | set(self.strict)
        unknown = names - known
        if unknown:
            raise ValueError(f"交叉评审存在未分组模型: {', '.join(sorted(unknown))}")

    def requires_expert_review(self, std_score: float) -> bool:
        threshold = float(self.protocol["unresolved_disagreement"]["std_threshold"])
        return std_score > threshold

    def _opposite_group(self, model_name: str) -> tuple[str, ...]:
        if model_name in self.lenient:
            return self.strict
        if model_name in self.strict:
            return self.lenient
        raise ValueError(f"模型未在交叉评审协议中分组: {model_name}")

    def build_prompt(
        self,
        dimension: Dimension,
        paper: ProcessedPaper,
        self_result: DimensionResult,
        opposite_results: list[DimensionResult],
    ) -> str:
        body = paper.body or paper.full_text or ""
        return self.protocol["prompt_template"].format(
            dimension_name=dimension.name_zh,
            self_review=self_result.model_dump_json(),
            opposite_reviews=json.dumps(
                [result.model_dump() for result in opposite_results],
                ensure_ascii=False,
            ),
            paper_content=body,
        )

    async def _evaluate_one(
        self,
        provider: Any,
        dimension: Dimension,
        paper: ProcessedPaper,
        r1_results: dict[str, DimensionResult],
        *,
        task_id: str | None,
        db: Session | None,
    ) -> CrossReviewOutcome:
        self_result = r1_results[provider.model_name]
        opposite = [
            r1_results[name]
            for name in self._opposite_group(provider.model_name)
            if name in r1_results
        ]
        if not opposite:
            raise ValueError(f"{provider.model_name} 缺少对方组第一轮意见")
        prompt = self.build_prompt(dimension, paper, self_result, opposite)
        started = time.time()
        configured_timeout = getattr(provider, "timeout", None)
        timeout = (
            configured_timeout
            if isinstance(configured_timeout, (int, float))
            else settings.provider_timeout
        )
        async with self._semaphore:
            raw = await asyncio.wait_for(
                provider.generate_json_response(prompt), timeout=timeout
            )
        revised = raw.get("revised_score")
        if (
            isinstance(revised, bool)
            or not isinstance(revised, (int, float))
            or not 0 <= revised <= 100
        ):
            raise ValueError(f"R2 revised_score 无效: {revised!r}")
        if db is not None and task_id is not None:
            log_call(
                db,
                task_id,
                provider.model_name,
                dimension.key,
                prompt,
                json.dumps(raw, ensure_ascii=False),
                started,
                round_number=2,
                call_type="cross_review",
            )
        result = DimensionResult(
            dimension=dimension.key,
            score=float(revised),
            evidence_quotes=list(raw.get("new_evidence_found", [])),
            analysis=str(raw.get("revision_rationale", "")),
            model_name=provider.model_name,
        )
        return CrossReviewOutcome(result=result, raw_payload=dict(raw), prompt=prompt)

    async def evaluate_dimension(
        self,
        providers: list[Any],
        dimension: Dimension,
        paper: ProcessedPaper,
        r1_results: dict[str, DimensionResult],
        *,
        task_id: str | None = None,
        db: Session | None = None,
    ) -> list[CrossReviewOutcome]:
        """并发执行一个维度的 R2；单次 API 并发受协议上限约束。"""

        self.validate_provider_names([provider.model_name for provider in providers])
        eligible = [
            provider for provider in providers if provider.model_name in r1_results
        ]
        return list(
            await asyncio.gather(
                *(
                    self._evaluate_one(
                        provider,
                        dimension,
                        paper,
                        r1_results,
                        task_id=task_id,
                        db=db,
                    )
                    for provider in eligible
                )
            )
        )
