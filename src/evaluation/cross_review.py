"""配置驱动的六维第二轮交叉评审共享服务。"""

from __future__ import annotations

import asyncio
import copy
import json
import time
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from src.core.config import settings
from src.evaluation.call_logger import log_call
from src.evaluation.schemas import DimensionResult
from src.ingestion.schemas import ProcessedPaper
from src.knowledge.registry import load_model_set, load_review_protocol
from src.knowledge.schemas import Dimension


@dataclass(frozen=True, slots=True)
class CrossReviewOutcome:
    """一个模型的第二轮标准结果及完整审计载荷。"""

    result: DimensionResult
    raw_payload: dict[str, Any]
    prompt: str


def _normalize_evidence_quotes(value: Any) -> list[str]:
    """兼容模型把证据返回为字符串或带 quote 字段的对象。"""

    if not isinstance(value, list):
        return []
    normalized: list[str] = []
    for item in value:
        if isinstance(item, str) and item.strip():
            normalized.append(item)
            continue
        if not isinstance(item, dict):
            continue
        quote = next(
            (
                item.get(key)
                for key in ("quote", "evidence_quote", "evidence", "text")
                if isinstance(item.get(key), str) and item.get(key).strip()
            ),
            None,
        )
        if quote:
            normalized.append(quote)
    return normalized


class CrossReviewService:
    """按版本化协议执行分组交叉复核或四模型同级匿名互评。"""

    def __init__(
        self,
        protocol: dict[str, Any] | None = None,
        participant_names: list[str] | None = None,
    ) -> None:
        self.protocol = protocol or load_review_protocol()
        self.review_mode = str(self.protocol.get("review_mode", "opposite_groups"))
        groups = self.protocol.get("model_groups", {})
        self.lenient = tuple(groups.get("lenient", ()))
        self.strict = tuple(groups.get("strict", ()))
        self.participant_names = tuple(
            participant_names or (*self.lenient, *self.strict)
        )
        self._semaphore = asyncio.Semaphore(
            int(self.protocol["execution"]["max_api_concurrency"])
        )

    @classmethod
    def for_model_set(
        cls,
        model_set_version: str,
        review_protocol_name: str | None = None,
    ) -> "CrossReviewService":
        """按模型集及任务冻结的协议版本构建第二轮服务。"""

        model_set = load_model_set(model_set_version)
        protocol_name = review_protocol_name or str(model_set["review_protocol"])
        protocol = copy.deepcopy(load_review_protocol(protocol_name))
        if protocol.get("review_mode", "opposite_groups") == "opposite_groups":
            groups = model_set.get("model_groups") or model_set.get(
                "legacy_model_groups"
            )
            if not groups:
                raise ValueError(f"模型集 {model_set_version} 缺少历史交叉评审分组")
            protocol["model_groups"] = groups
        protocol["metadata"] = {
            **protocol["metadata"],
            "model_set_version": model_set_version,
        }
        return cls(protocol, participant_names=model_set["provider_names"])

    def validate_provider_names(self, provider_names: list[str]) -> None:
        """校验启用第二轮时的模型成员是否符合冻结协议。"""

        names = set(provider_names)
        if self.review_mode == "all_peers":
            expected = set(self.participant_names)
            if len(provider_names) != len(names) or names != expected:
                missing = expected - names
                extra = names - expected
                detail = []
                if missing:
                    detail.append("缺少：" + "、".join(sorted(missing)))
                if extra:
                    detail.append("未登记：" + "、".join(sorted(extra)))
                raise ValueError(
                    "四模型匿名互评必须使用完整候选模型集"
                    + ("；" + "；".join(detail) if detail else "")
                )
            return
        if not names.intersection(self.lenient) or not names.intersection(self.strict):
            raise ValueError("启用交叉评审必须同时配置宽松组和严格组模型")
        known = set(self.lenient) | set(self.strict)
        unknown = names - known
        if unknown:
            raise ValueError(f"交叉评审存在未分组模型: {', '.join(sorted(unknown))}")

    def requires_expert_review(self, std_score: float) -> bool:
        threshold = float(self.protocol["unresolved_disagreement"]["std_threshold"])
        return std_score > threshold

    def _peer_names(self, model_name: str) -> tuple[str, ...]:
        if self.review_mode == "all_peers":
            if model_name not in self.participant_names:
                raise ValueError(f"模型未在匿名互评协议中登记: {model_name}")
            return tuple(name for name in self.participant_names if name != model_name)
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
        peer_results: list[DimensionResult],
    ) -> str:
        if self.review_mode == "all_peers":
            self_review = self_result.model_dump(exclude={"model_name"})
            peer_reviews = [
                {
                    "review_label": f"评审意见{index}",
                    "review": result.model_dump(exclude={"model_name"}),
                }
                for index, result in enumerate(peer_results, start=1)
            ]
        else:
            self_review = self_result.model_dump()
            peer_reviews = [result.model_dump() for result in peer_results]
        return self.render_prompt(
            dimension_name=dimension.name_zh,
            paper_content=paper.body or paper.full_text or "",
            self_review=self_review,
            peer_reviews=peer_reviews,
        )

    def _compact_paper_for_content_inspection(
        self, paper: ProcessedPaper
    ) -> ProcessedPaper:
        fallback = self.protocol["execution"].get("content_inspection_fallback", {})
        head_chars = int(fallback.get("head_chars", 3_000))
        tail_chars = int(fallback.get("tail_chars", 7_000))
        content = paper.body or paper.full_text or ""
        if len(content) <= head_chars + tail_chars:
            compact = content
        else:
            compact = (
                content[:head_chars]
                + "\n\n……（内容审查重试：中间论证已省略）……\n\n"
                + content[-tail_chars:]
            )
        return paper.model_copy(
            update={
                "body": compact,
                "full_text": compact,
                "introduction": paper.introduction[:2_000],
            }
        )

    def render_prompt(
        self,
        *,
        dimension_name: str,
        paper_content: str,
        self_review: dict[str, Any],
        peer_reviews: list[dict[str, Any]],
    ) -> str:
        """供 API 与历史 CLI 共同使用的唯一 R2 prompt 渲染入口。"""

        serialized_reviews = json.dumps(peer_reviews, ensure_ascii=False)
        return self.protocol["prompt_template"].format(
            dimension_name=dimension_name,
            self_review=json.dumps(self_review, ensure_ascii=False),
            opposite_reviews=serialized_reviews,
            peer_reviews=serialized_reviews,
            paper_content=paper_content,
            output_contract=json.dumps(
                self.protocol["output_contract"], ensure_ascii=False
            ),
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
        peer_names = self._peer_names(provider.model_name)
        peers = [r1_results[name] for name in peer_names if name in r1_results]
        if self.review_mode == "all_peers" and len(peers) != len(peer_names):
            missing = [name for name in peer_names if name not in r1_results]
            raise ValueError(
                f"{provider.model_name} 等待第一轮评价：{'、'.join(missing)}"
            )
        if not peers:
            raise ValueError(f"{provider.model_name} 缺少对方组第一轮意见")
        prompt = self.build_prompt(dimension, paper, self_result, peers)
        configured_timeout = getattr(provider, "timeout", None)
        timeout = (
            configured_timeout
            if isinstance(configured_timeout, (int, float))
            else settings.provider_timeout
        )
        raw: dict[str, Any] | None = None
        last_error: Exception | None = None
        content_inspection_error: Exception | None = None
        for attempt in range(1, 4):
            started = time.time()
            try:
                async with self._semaphore:
                    candidate = await asyncio.wait_for(
                        provider.generate_json_response(prompt), timeout=timeout
                    )
                revised = candidate.get("revised_score")
                if (
                    isinstance(revised, bool)
                    or not isinstance(revised, (int, float))
                    or not 0 <= revised <= 100
                ):
                    raise ValueError(f"R2 revised_score 无效: {revised!r}")
                raw = candidate
                break
            except Exception as exc:  # noqa: BLE001 - 供应商瞬时错误需受控重试
                last_error = exc
                if db is not None and task_id is not None:
                    log_call(
                        db,
                        task_id,
                        provider.model_name,
                        dimension.key,
                        prompt,
                        str(getattr(exc, "raw_response", None) or ""),
                        started,
                        round_number=2,
                        call_type="cross_review",
                        provider_name=provider.__class__.__name__,
                        status="failed",
                        failure_detail=str(exc),
                    )
                normalized_error = str(exc).lower()
                fallback = self.protocol["execution"].get(
                    "content_inspection_fallback", {}
                )
                if (
                    fallback.get("enabled", True)
                    and content_inspection_error is None
                    and (
                        "datainspectionfailed" in normalized_error
                        or "data_inspection_failed" in normalized_error
                    )
                ):
                    content_inspection_error = exc
                    compact_paper = self._compact_paper_for_content_inspection(paper)
                    prompt = self.build_prompt(
                        dimension, compact_paper, self_result, peers
                    )
                if attempt < 3:
                    await asyncio.sleep(0.5 * attempt)
        if raw is None:
            raise RuntimeError(
                f"R2 模型 {provider.model_name} 连续失败 3 次: {last_error}"
            ) from last_error
        if content_inspection_error is not None:
            raw.setdefault("_cross_review_metadata", {}).update(
                {
                    "content_inspection_fallback": True,
                    "context_strategy": "abstract_head_tail",
                    "original_error": str(content_inspection_error),
                }
            )
        metadata = raw.setdefault("_cross_review_metadata", {})
        metadata.update(
            {
                "review_protocol": self.protocol.get("registry_name"),
                "review_mode": self.review_mode,
            }
        )
        if self.review_mode == "all_peers":
            metadata["anonymous_peer_mapping"] = {
                f"评审意见{index}": name
                for index, name in enumerate(peer_names, start=1)
            }
        revised = raw["revised_score"]
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
                provider_name=provider.__class__.__name__,
            )
        evidence_quotes = _normalize_evidence_quotes(raw.get("new_evidence_found"))
        result = DimensionResult(
            dimension=dimension.key,
            score=float(revised),
            evidence_quotes=evidence_quotes,
            analysis=str(raw.get("revision_rationale", "")),
            band=str(raw.get("revised_band", "") or "") or None,
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

        provider_names = [provider.model_name for provider in providers]
        self.validate_provider_names(provider_names)
        if self.review_mode == "all_peers":
            missing = [
                name for name in self.participant_names if name not in r1_results
            ]
            if missing:
                raise ValueError(
                    "等待四模型第一轮评价齐全；缺少：" + "、".join(missing)
                )
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
