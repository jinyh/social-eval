"""把缺口清单连接到现有 prompt/provider，并维护可暂存的结果副本。"""

from __future__ import annotations

import asyncio
import csv
import json
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml

from scripts.run_cross_review import A_GROUP, B_GROUP, build_cross_review_prompt
from src.evaluation.position.workflow import (
    build_light_round2_prompt,
    build_round1_prompt,
    build_round2_prompt,
    decide_round2_policy,
    format_retrieved_nodes_for_prompt,
    retrieved_nodes_from_result,
)
from src.evaluation.prompt_builder import _paper_content, build_prompt
from src.evaluation.providers.factory import create_providers
from src.evaluation.repair.five_axis import (
    build_skip_round2,
    is_valid_position_output,
    merge_five_axis_response,
    rebuild_five_axis_record,
)
from src.evaluation.repair.models import FIVE_AXIS_MODELS, Gap, SIX_DIMENSION_MODELS
from src.evaluation.repair.registry import target_registry
from src.evaluation.repair.runner import atomic_write_json
from src.evaluation.repair.six_dimension import (
    is_valid_score,
    merge_model_response,
    recompute_result_statistics,
    round_scores,
)
from src.ingestion.preprocessor import process_file
from src.knowledge.loader import DEFAULT_STD_THRESHOLD, _normalize_framework_data
from src.knowledge.schemas import Framework

FRAMEWORK_RELATIVE_PATH = Path("configs/frameworks/law-v2.55-cross-review.yaml")
CONTENT_INSPECTION_HEAD_CHARS = 3_000
CONTENT_INSPECTION_TAIL_CHARS = 7_000


def _load_framework(project_root: Path) -> Framework:
    data = yaml.safe_load(
        (project_root / FRAMEWORK_RELATIVE_PATH).read_text(encoding="utf-8")
    )
    if "std_threshold" not in data:
        data["std_threshold"] = DEFAULT_STD_THRESHOLD
    return Framework(**_normalize_framework_data(data))


def _resolve_project_path(project_root: Path, path_value: str) -> Path:
    path = Path(path_value)
    return path if path.is_absolute() else project_root / path


def _parse_md_meta(path: Path) -> dict[str, Any]:
    parts = path.stem.split("_", 4)
    if len(parts) == 5:
        return {
            "作者": parts[1],
            "年份": parts[2],
            "期刊": parts[3],
            "题目": parts[4],
        }
    return {"题目": path.stem}


def compact_paper_for_content_inspection(paper: Any) -> Any:
    """保留摘要、正文开头和结论区，缩短内容审查拒绝后的重试上下文。"""

    body = str(getattr(paper, "body", "") or "")
    compact_body = (
        body
        if len(body) <= CONTENT_INSPECTION_HEAD_CHARS + CONTENT_INSPECTION_TAIL_CHARS
        else (
            body[:CONTENT_INSPECTION_HEAD_CHARS]
            + "\n\n……（内容审查重试：中间论证已省略）……\n\n"
            + body[-CONTENT_INSPECTION_TAIL_CHARS:]
        )
    )
    return paper.model_copy(
        update={
            "body": compact_body,
            "introduction": str(getattr(paper, "introduction", "") or "")[:2_000],
        }
    )


class RepairRuntime:
    """为一次修复运行缓存论文、结果副本和 provider。"""

    def __init__(
        self,
        project_root: Path,
        gaps: list[Gap],
        *,
        providers: Mapping[str, Any] | None = None,
    ) -> None:
        self.project_root = project_root.resolve()
        self.registry = target_registry(self.project_root)
        self.framework = _load_framework(self.project_root)
        self.dimensions = {dimension.key: dimension for dimension in self.framework.dimensions}
        provider_list = create_providers(list(SIX_DIMENSION_MODELS)) if providers is None else []
        self.providers = (
            {provider.model_name: provider for provider in provider_list}
            if providers is None
            else dict(providers)
        )
        self.gaps = list(gaps)
        self.states: dict[tuple[str, int], dict[str, Any]] = {}
        self.originals: dict[tuple[str, int], dict[str, Any]] = {}
        self.dirty_keys: set[tuple[str, int]] = set()
        self.paper_tasks: dict[Path, asyncio.Task[Any]] = {}
        self._three_meta: dict[int, dict[str, Any]] | None = None
        self._json_meta: dict[str, dict[int, dict[str, Any]]] = {}
        for gap in self.gaps:
            self.ensure_state(gap.target_key, gap.paper_id)
            if gap.target_key == "e2-r2":
                self.ensure_state("e2-r1", gap.paper_id)

    def ensure_state(self, target_key: str, paper_id: int) -> dict[str, Any]:
        key = (target_key, paper_id)
        if key in self.states:
            return self.states[key]
        target = self.registry[target_key]
        path = target.per_paper_dir / f"paper-{paper_id}.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        self.originals[key] = json.loads(json.dumps(payload, ensure_ascii=False))
        self.states[key] = payload
        return payload

    def _paper_path(self, gap: Gap) -> Path:
        state = self.ensure_state(gap.target_key, gap.paper_id)
        paper_value = str(state.get("paper", ""))
        direct = _resolve_project_path(self.project_root, paper_value)
        if direct.exists():
            return direct
        target = self.registry[gap.target_key]
        if target.dataset == "three-journals":
            matches = sorted(
                (self.project_root / "raw" / "fullpaper").glob(
                    f"{gap.paper_id:04d}-*.pdf"
                )
            )
            if matches:
                return matches[0]
        if target.family == "five_axis":
            if target.dataset in {"jiaodafaxue", "xueshuyuekan"}:
                meta = self._load_json_meta(target.dataset).get(gap.paper_id, {})
                candidate = _resolve_project_path(self.project_root, str(meta.get("path", "")))
                if candidate.exists():
                    return candidate
            six = self.ensure_state(f"{target.dataset}-six", gap.paper_id)
            candidate = _resolve_project_path(self.project_root, str(six.get("paper", "")))
            if candidate.exists():
                return candidate
        raise FileNotFoundError(f"找不到论文原文：{gap.slot_key} ({paper_value})")

    def _load_json_meta(self, dataset: str) -> dict[int, dict[str, Any]]:
        if dataset not in self._json_meta:
            path = self.project_root / "results" / "datasets" / dataset / "metadata.json"
            data = json.loads(path.read_text(encoding="utf-8"))
            self._json_meta[dataset] = {
                int(item["id"]): item for item in data.get("papers", [])
            }
        return self._json_meta[dataset]

    def _load_three_meta(self) -> dict[int, dict[str, Any]]:
        if self._three_meta is None:
            path = self.project_root / "results/datasets/three-journals/metadata.csv"
            with path.open(encoding="utf-8-sig") as handle:
                self._three_meta = {
                    int(row["编号"]): row for row in csv.DictReader(handle)
                }
        return self._three_meta

    def _paper_meta(self, gap: Gap, paper_path: Path) -> dict[str, Any]:
        dataset = self.registry[gap.target_key].dataset
        if dataset == "three-journals":
            return self._load_three_meta().get(gap.paper_id, {"题目": paper_path.stem})
        item = self._load_json_meta(dataset).get(gap.paper_id, {})
        return {**_parse_md_meta(paper_path), **item}

    async def _paper(self, path: Path) -> Any:
        resolved = path.resolve()
        task = self.paper_tasks.get(resolved)
        if task is None:
            task = asyncio.create_task(asyncio.to_thread(process_file, str(resolved)))
            self.paper_tasks[resolved] = task
        return await task

    def _r1_dimension(self, gap: Gap) -> dict[str, Any]:
        target_key = "e2-r1" if gap.target_key == "e2-r2" else gap.target_key
        state = self.ensure_state(target_key, gap.paper_id)
        return state["dimensions"][gap.dimension]

    @staticmethod
    def _raw_or_score(dimension: Mapping[str, Any], model: str) -> dict[str, Any]:
        raw = dimension.get("raw_outputs", {})
        if isinstance(raw, Mapping) and isinstance(raw.get(model), Mapping):
            return dict(raw[model])
        score = round_scores(dimension, 1).get(model)
        if not is_valid_score(score):
            raise ValueError(f"R2 缺少 {model} 的 R1 评分与原始响应")
        return {
            "score": score,
            "rationale": "历史 R1 原始响应缺失；本次交叉评审沿用已持久化评分。",
        }

    def _merge_response(
        self,
        gap: Gap,
        response: Mapping[str, Any],
        elapsed_seconds: float,
    ) -> None:
        state = self.ensure_state(gap.target_key, gap.paper_id)
        family = self.registry[gap.target_key].family
        if family == "five_axis":
            self.states[(gap.target_key, gap.paper_id)] = merge_five_axis_response(
                state,
                gap,
                response,
                elapsed_seconds=elapsed_seconds,
            )
            self.dirty_keys.add((gap.target_key, gap.paper_id))
            return
        if gap.target_key == "e2-r2" and gap.round_number == 2:
            r1_dimension = self._r1_dimension(gap)
            target_dimension = state["dimensions"][gap.dimension]
            target_r1 = target_dimension.setdefault("round1_scores", {})
            for model, score in round_scores(r1_dimension, 1).items():
                if model not in target_r1 and is_valid_score(score):
                    target_r1[model] = score
        merged = merge_model_response(
            state,
            gap,
            response,
            elapsed_seconds=elapsed_seconds,
        )
        self.states[(gap.target_key, gap.paper_id)] = recompute_result_statistics(
            merged,
            scoring_protocol=self.framework.raw_config.get("scoring_protocol"),
        )
        self.dirty_keys.add((gap.target_key, gap.paper_id))

    def _build_gap_prompt(self, gap: Gap, paper_path: Path, paper: Any) -> str:
        family = self.registry[gap.target_key].family
        if family == "five_axis":
            return self._five_axis_prompt(gap, paper_path, _paper_content(paper))
        dimension = self.dimensions[gap.dimension]
        if gap.round_number == 1:
            return build_prompt(dimension, paper)
        r1_dimension = self._r1_dimension(gap)
        self_output = self._raw_or_score(r1_dimension, gap.model)
        other_group = B_GROUP if gap.model in A_GROUP else A_GROUP
        other_outputs = [
            self._raw_or_score(r1_dimension, model) for model in other_group
        ]
        return build_cross_review_prompt(
            dimension.name_zh,
            dimension.key,
            self_output,
            other_outputs,
            paper,
        )

    async def call_gap(self, gap: Gap) -> dict[str, Any]:
        """为单槽位构造原项目 prompt、调用 provider 并更新内存副本。"""

        provider = self.providers.get(gap.model)
        if provider is None:
            raise ValueError(f"Provider 不存在：{gap.model}")
        paper_path = self._paper_path(gap)
        paper = await self._paper(paper_path)
        prompt = self._build_gap_prompt(gap, paper_path, paper)
        started = time.monotonic()
        try:
            response = await provider.call_with_timeout(
                provider.generate_json_response(prompt)
            )
        except Exception as exc:
            error = str(exc).lower()
            if "datainspectionfailed" not in error and "data_inspection_failed" not in error:
                raise
            compact_paper = compact_paper_for_content_inspection(paper)
            compact_prompt = self._build_gap_prompt(gap, paper_path, compact_paper)
            response = await provider.call_with_timeout(
                provider.generate_json_response(compact_prompt)
            )
            response.setdefault("_repair_metadata", {}).update(
                {
                    "content_inspection_fallback": True,
                    "context_strategy": "abstract_head3000_tail7000",
                    "original_error": str(exc),
                }
            )
        elapsed = time.monotonic() - started
        self._merge_response(gap, response, elapsed)
        return response

    def _five_axis_prompt(self, gap: Gap, paper_path: Path, paper_text: str) -> str:
        state = self.ensure_state(gap.target_key, gap.paper_id)
        meta = self._paper_meta(gap, paper_path)
        round1 = state.get("round1") or {}
        nodes = retrieved_nodes_from_result(round1)
        node_text = format_retrieved_nodes_for_prompt(nodes)
        if gap.round_number == 1:
            return build_round1_prompt(
                paper_meta=meta,
                paper_text=paper_text,
                knowledge_excerpt="",
                node_candidates_text=node_text,
            )
        policy = state.get("round2_policy") or {}
        mode = policy.get("mode", state.get("round2_mode", "full"))
        models = round1.get("models", {})
        other_model = next(model for model in FIVE_AXIS_MODELS if model != gap.model)
        kwargs = {
            "paper_meta": meta,
            "knowledge_excerpt": "",
            "self_r1_output": models[gap.model],
            "other_r1_output": models[other_model],
            "model_name": gap.model,
            "other_model_name": other_model,
            "node_candidates_text": node_text,
        }
        if mode == "light":
            return build_light_round2_prompt(**kwargs)
        return build_round2_prompt(paper_text=paper_text, **kwargs)

    def apply_checkpoint(self, gaps: list[Gap], checkpoint_path: Path) -> None:
        """把已成功 checkpoint 先合入内存，供续跑的 R2 构造上下文。"""

        if not checkpoint_path.exists():
            return
        checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        slots = checkpoint.get("slots", {})
        for gap in sorted(gaps, key=lambda item: item.round_number):
            record = slots.get(gap.slot_key, {})
            response = record.get("response")
            if record.get("status") != "success" or not isinstance(response, Mapping):
                continue
            state = self.ensure_state(gap.target_key, gap.paper_id)
            if self.registry[gap.target_key].family == "five_axis":
                round_key = "round1" if gap.round_number == 1 else "round2"
                existing = (state.get(round_key) or {}).get("models", {}).get(gap.model)
                if is_valid_position_output(existing):
                    continue
            else:
                dimension = state["dimensions"][gap.dimension]
                if is_valid_score(round_scores(dimension, gap.round_number).get(gap.model)):
                    continue
            self._merge_response(
                gap,
                response,
                float(record.get("elapsed_seconds", 0)),
            )

    def prepare_five_axis_round2(self) -> list[Gap]:
        """R1 补齐后重新路由五轴，并返回动态 R2 缺口。"""

        dynamic: list[Gap] = []
        five_keys = {
            (gap.target_key, gap.paper_id)
            for gap in self.gaps
            if self.registry[gap.target_key].family == "five_axis"
        }
        for key in sorted(five_keys):
            state = self.states[key]
            round1 = state.get("round1") or {}
            policy = decide_round2_policy(round1)
            if policy["mode"] == "skip":
                self.states[key] = rebuild_five_axis_record(build_skip_round2(state))
                self.dirty_keys.add(key)
                continue
            state["round2_mode"] = policy["mode"]
            state["round2_policy"] = policy
            round2 = state.get("round2")
            if not isinstance(round2, dict):
                round2 = {
                    "paper_id": key[1],
                    "paper": state.get("paper", ""),
                    "round2_mode": policy["mode"],
                    "round2_policy": policy,
                    "models": {},
                }
                state["round2"] = round2
            for model in FIVE_AXIS_MODELS:
                if is_valid_position_output(round2.get("models", {}).get(model)):
                    continue
                dynamic.append(
                    Gap(
                        target_key=key[0],
                        paper_id=key[1],
                        dimension="position_assessment",
                        round_number=2,
                        model=model,
                        reason="r2_required_after_r1_repair",
                    )
                )
        return dynamic

    def finalize(self) -> None:
        """重算统计并重建已触发的五轴 merged/final。"""

        for key in sorted(self.dirty_keys):
            state = self.states[key]
            family = self.registry[key[0]].family
            if family == "five_axis":
                self.states[key] = rebuild_five_axis_record(state)
            else:
                self.states[key] = recompute_result_statistics(
                    state,
                    scoring_protocol=self.framework.raw_config.get("scoring_protocol"),
                )

    def write_staged(self, output_dir: Path) -> list[dict[str, Any]]:
        """只写发生变化的结果副本，返回暂存索引。"""

        entries: list[dict[str, Any]] = []
        for target_key, paper_id in sorted(self.dirty_keys):
            state = self.states[(target_key, paper_id)]
            original = self.originals[(target_key, paper_id)]
            if state == original:
                continue
            path = output_dir / "staged" / target_key / f"paper-{paper_id}.json"
            atomic_write_json(path, state)
            entries.append(
                {
                    "target_key": target_key,
                    "paper_id": paper_id,
                    "staged_path": str(path),
                }
            )
        return entries
