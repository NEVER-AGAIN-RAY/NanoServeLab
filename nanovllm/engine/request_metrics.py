"""纯函数：把单条不可变 RequestTimingRecord 派生为请求级延迟指标。

本模块不写入 recorder、不修改原始记录、不做 batch 聚合或 percentile。
公式与空值规则遵循 ``docs/experiments/metrics.md``。
"""

from __future__ import annotations

from dataclasses import dataclass

from nanovllm.engine.request_timing import RequestTimingRecord

_NS_PER_MS = 1_000_000


@dataclass(frozen=True, slots=True)
class RequestMetrics:
    """单请求引擎侧延迟指标（毫秒）。"""

    seq_id: int
    queue_time_ms: float
    ttft_ms: float
    e2e_ms: float
    mean_tpot_ms: float | None


def derive_request_metrics(record: RequestTimingRecord) -> RequestMetrics:
    """从已完成请求的原始时间戳派生 Queue Time / TTFT / E2E / Mean TPOT。"""
    if record.outcome != "finished":
        raise ValueError(
            f"seq_id={record.seq_id}: outcome must be 'finished', got {record.outcome!r}"
        )
    if record.output_tokens <= 0:
        raise ValueError(
            f"seq_id={record.seq_id}: output_tokens must be > 0, got {record.output_tokens}"
        )
    if record.first_scheduled_ns is None:
        raise ValueError(f"seq_id={record.seq_id}: first_scheduled_ns is missing")
    if record.first_output_ns is None:
        raise ValueError(f"seq_id={record.seq_id}: first_output_ns is missing")
    if record.completed_ns is None:
        raise ValueError(f"seq_id={record.seq_id}: completed_ns is missing")

    arrival_ns = record.arrival_ns
    first_scheduled_ns = record.first_scheduled_ns
    first_output_ns = record.first_output_ns
    completed_ns = record.completed_ns

    if not (
        arrival_ns
        <= first_scheduled_ns
        <= first_output_ns
        <= completed_ns
    ):
        raise ValueError(
            f"seq_id={record.seq_id}: timestamps must satisfy "
            f"arrival_ns <= first_scheduled_ns <= first_output_ns <= completed_ns, "
            f"got arrival_ns={arrival_ns}, first_scheduled_ns={first_scheduled_ns}, "
            f"first_output_ns={first_output_ns}, completed_ns={completed_ns}"
        )

    queue_time_ms = (first_scheduled_ns - arrival_ns) / _NS_PER_MS
    ttft_ms = (first_output_ns - arrival_ns) / _NS_PER_MS
    e2e_ms = (completed_ns - arrival_ns) / _NS_PER_MS
    if record.output_tokens >= 2:
        mean_tpot_ms = (
            (completed_ns - first_output_ns) / (record.output_tokens - 1) / _NS_PER_MS
        )
    else:
        mean_tpot_ms = None

    return RequestMetrics(
        seq_id=record.seq_id,
        queue_time_ms=queue_time_ms,
        ttft_ms=ttft_ms,
        e2e_ms=e2e_ms,
        mean_tpot_ms=mean_tpot_ms,
    )
