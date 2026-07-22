"""Scheduler 级 per-request 原始生命周期计时记录。

本模块只保存合约定义的原始事件时间戳与 Token 计数，不计算 Queue Time、
TTFT、TPOT、E2E 或任何聚合统计。记录独立于 KV Block 生命周期：请求完成并
释放 Block 后，snapshot 仍可读取。

``RequestTimingRecorder`` 由 Scheduler 可选注入；默认关闭时 Scheduler 不
创建记录、不调用时钟。
"""

from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter_ns
from typing import Callable


@dataclass(frozen=True, slots=True)
class RequestTimingRecord:
    """对外返回的不可变 per-request timing snapshot。"""

    seq_id: int
    prompt_tokens: int
    output_tokens: int
    outcome: str | None
    arrival_ns: int
    first_scheduled_ns: int | None
    first_output_ns: int | None
    completed_ns: int | None


class RequestTimingRecorder:
    """按 seq_id 保存原始生命周期事实的只读观察层。"""

    def __init__(self, clock_ns: Callable[[], int] = perf_counter_ns):
        self._clock_ns = clock_ns
        self._records: dict[int, RequestTimingRecord] = {}

    def get(self, seq_id: int) -> RequestTimingRecord:
        try:
            return self._records[seq_id]
        except KeyError as exc:
            raise KeyError(f"no timing record for seq_id={seq_id}") from exc

    def record_arrival(self, seq_id: int, prompt_tokens: int) -> None:
        if seq_id in self._records:
            raise ValueError(f"duplicate arrival for seq_id={seq_id}")
        self._records[seq_id] = RequestTimingRecord(
            seq_id=seq_id,
            prompt_tokens=prompt_tokens,
            output_tokens=0,
            outcome=None,
            arrival_ns=self._clock_ns(),
            first_scheduled_ns=None,
            first_output_ns=None,
            completed_ns=None,
        )

    def record_first_scheduled(self, seq_id: int) -> None:
        record = self._require(seq_id)
        if record.first_scheduled_ns is not None:
            return
        self._records[seq_id] = RequestTimingRecord(
            seq_id=record.seq_id,
            prompt_tokens=record.prompt_tokens,
            output_tokens=record.output_tokens,
            outcome=record.outcome,
            arrival_ns=record.arrival_ns,
            first_scheduled_ns=self._clock_ns(),
            first_output_ns=record.first_output_ns,
            completed_ns=record.completed_ns,
        )

    def record_output_token(self, seq_id: int, output_tokens: int) -> None:
        """在真实 Completion Token 已 append 后调用。

        首次写入 ``first_output_ns``（write-once）；每次调用更新
        ``output_tokens``。不得在 Chunked Prefill 丢弃临时采样的路径调用。
        """
        record = self._require(seq_id)
        first_output_ns = record.first_output_ns
        if first_output_ns is None:
            first_output_ns = self._clock_ns()
        self._records[seq_id] = RequestTimingRecord(
            seq_id=record.seq_id,
            prompt_tokens=record.prompt_tokens,
            output_tokens=output_tokens,
            outcome=record.outcome,
            arrival_ns=record.arrival_ns,
            first_scheduled_ns=record.first_scheduled_ns,
            first_output_ns=first_output_ns,
            completed_ns=record.completed_ns,
        )

    def record_completed(self, seq_id: int, output_tokens: int) -> None:
        """在状态已设为 FINISHED、释放 KV Block 之前调用。write-once。"""
        record = self._require(seq_id)
        if record.completed_ns is not None:
            return
        self._records[seq_id] = RequestTimingRecord(
            seq_id=record.seq_id,
            prompt_tokens=record.prompt_tokens,
            output_tokens=output_tokens,
            outcome="finished",
            arrival_ns=record.arrival_ns,
            first_scheduled_ns=record.first_scheduled_ns,
            first_output_ns=record.first_output_ns,
            completed_ns=self._clock_ns(),
        )

    def _require(self, seq_id: int) -> RequestTimingRecord:
        try:
            return self._records[seq_id]
        except KeyError as exc:
            raise KeyError(f"no timing record for seq_id={seq_id}") from exc
