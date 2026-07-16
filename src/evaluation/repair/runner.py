"""可恢复、受控并发的模型槽位调度器。"""

from __future__ import annotations

import asyncio
import json
import os
import time
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.evaluation.repair.models import Gap

GapCaller = Callable[[Gap], Awaitable[dict[str, Any]]]


@dataclass(frozen=True, slots=True)
class RunResult:
    """一次调度执行的汇总。"""

    succeeded: int
    failed: int
    responses: dict[str, dict[str, Any]]
    errors: dict[str, str]


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    """在同一目录写临时文件后原子替换 JSON。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(temporary, path)


class RepairRunner:
    """按 R1→R2 屏障调度缺失槽位，并为每个槽位写 checkpoint。"""

    def __init__(
        self,
        *,
        checkpoint_path: Path,
        api_concurrency: int,
        max_attempts: int = 2,
        retry_delay_seconds: float = 1.0,
    ) -> None:
        if api_concurrency < 1:
            raise ValueError("api_concurrency 必须大于 0")
        if max_attempts < 1:
            raise ValueError("max_attempts 必须大于 0")
        self.checkpoint_path = checkpoint_path
        self.max_attempts = max_attempts
        self.retry_delay_seconds = retry_delay_seconds
        self._semaphore = asyncio.Semaphore(api_concurrency)
        self._checkpoint_lock = asyncio.Lock()
        self._checkpoint = self._load_checkpoint()

    def _load_checkpoint(self) -> dict[str, Any]:
        if not self.checkpoint_path.exists():
            return {"version": 1, "slots": {}}
        try:
            payload = json.loads(self.checkpoint_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"checkpoint 无法读取：{self.checkpoint_path}") from exc
        if not isinstance(payload.get("slots"), dict):
            raise ValueError("checkpoint 缺少 slots 对象")
        return payload

    async def _save_slot(self, slot_key: str, record: dict[str, Any]) -> None:
        async with self._checkpoint_lock:
            self._checkpoint["slots"][slot_key] = record
            atomic_write_json(self.checkpoint_path, self._checkpoint)

    def _successful_response(self, gap: Gap) -> dict[str, Any] | None:
        record = self._checkpoint["slots"].get(gap.slot_key, {})
        response = record.get("response")
        if record.get("status") == "success" and isinstance(response, dict):
            return response
        return None

    async def _run_gap(self, gap: Gap, caller: GapCaller) -> None:
        if self._successful_response(gap) is not None:
            return
        last_error = ""
        for attempt in range(1, self.max_attempts + 1):
            started = time.monotonic()
            try:
                async with self._semaphore:
                    response = await caller(gap)
                if not isinstance(response, dict):
                    raise TypeError("模型调用必须返回 JSON object")
                await self._save_slot(
                    gap.slot_key,
                    {
                        "status": "success",
                        "response": response,
                        "attempts": attempt,
                        "elapsed_seconds": round(time.monotonic() - started, 3),
                    },
                )
                return
            except Exception as exc:  # noqa: BLE001 - 调度器必须记录供应商错误
                last_error = str(exc)
                await self._save_slot(
                    gap.slot_key,
                    {
                        "status": "failed",
                        "error": last_error,
                        "attempts": attempt,
                        "elapsed_seconds": round(time.monotonic() - started, 3),
                    },
                )
                if attempt < self.max_attempts and self.retry_delay_seconds > 0:
                    await asyncio.sleep(self.retry_delay_seconds * attempt)
        if not last_error:
            raise RuntimeError(f"槽位未执行：{gap.slot_key}")

    async def _run_phase(self, gaps: list[Gap], caller: GapCaller) -> None:
        await asyncio.gather(*(self._run_gap(gap, caller) for gap in gaps))

    async def run(self, gaps: Iterable[Gap], caller: GapCaller) -> RunResult:
        """先完成全部 R1，再调度 R2；成功 checkpoint 自动跳过。"""

        unique = {gap.slot_key: gap for gap in gaps}
        ordered = [unique[key] for key in sorted(unique)]
        round1 = [gap for gap in ordered if gap.round_number == 1]
        round2 = [gap for gap in ordered if gap.round_number == 2]
        await self._run_phase(round1, caller)
        await self._run_phase(round2, caller)

        responses: dict[str, dict[str, Any]] = {}
        errors: dict[str, str] = {}
        for gap in ordered:
            record = self._checkpoint["slots"].get(gap.slot_key, {})
            response = record.get("response")
            if record.get("status") == "success" and isinstance(response, dict):
                responses[gap.slot_key] = response
            else:
                errors[gap.slot_key] = str(record.get("error", "unknown error"))
        return RunResult(
            succeeded=len(responses),
            failed=len(errors),
            responses=responses,
            errors=errors,
        )

