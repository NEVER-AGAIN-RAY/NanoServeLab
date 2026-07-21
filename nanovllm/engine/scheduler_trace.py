"""Scheduler 状态的只读结构化快照。

本模块不参与调度，也不自动打印或持久化数据。调用方只在需要观察时
显式采集，并得到与后续 Scheduler 变化隔离的不可变历史值。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Iterable, Literal

if TYPE_CHECKING:
    from nanovllm.engine.scheduler import Scheduler
    from nanovllm.engine.sequence import Sequence


SnapshotPhase = Literal["after_schedule", "after_postprocess"]
SnapshotMode = Literal["prefill", "decode"]


@dataclass(frozen=True, slots=True)
class SequenceSnapshot:
    """一个 Sequence 在某个调度边界上的不可变状态。"""

    seq_id: int
    status: str
    num_prompt_tokens: int
    num_tokens: int
    num_completion_tokens: int
    num_cached_tokens: int
    num_scheduled_tokens: int
    block_count: int
    block_table: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class SchedulerStepSnapshot:
    """一次 Scheduler Step 在指定边界上的不可变状态。"""

    step: int
    phase: SnapshotPhase
    mode: SnapshotMode
    scheduled_seq_ids: tuple[int, ...]
    waiting_seq_ids: tuple[int, ...]
    running_seq_ids: tuple[int, ...]
    used_block_ids: tuple[int, ...]
    free_block_count: int
    sequences: tuple[SequenceSnapshot, ...]


def _capture_sequence(seq: Sequence) -> SequenceSnapshot:
    return SequenceSnapshot(
        seq_id=seq.seq_id,
        status=seq.status.name,
        num_prompt_tokens=seq.num_prompt_tokens,
        num_tokens=seq.num_tokens,
        num_completion_tokens=seq.num_completion_tokens,
        num_cached_tokens=seq.num_cached_tokens,
        num_scheduled_tokens=seq.num_scheduled_tokens,
        block_count=len(seq.block_table),
        block_table=tuple(seq.block_table),
    )


def capture_scheduler_snapshot(
    scheduler: Scheduler,
    scheduled_seqs: Iterable[Sequence],
    *,
    step: int,
    phase: SnapshotPhase,
    is_prefill: bool,
) -> SchedulerStepSnapshot:
    """复制一个调度边界上的队列、Sequence 和 KV Block 状态。"""

    scheduled = tuple(scheduled_seqs)
    waiting = tuple(scheduler.waiting)
    running = tuple(scheduler.running)

    observed = []
    observed_seq_ids = set()
    for seq in (*scheduled, *waiting, *running):
        if seq.seq_id in observed_seq_ids:
            continue
        observed.append(seq)
        observed_seq_ids.add(seq.seq_id)

    return SchedulerStepSnapshot(
        step=step,
        phase=phase,
        mode="prefill" if is_prefill else "decode",
        scheduled_seq_ids=tuple(seq.seq_id for seq in scheduled),
        waiting_seq_ids=tuple(seq.seq_id for seq in waiting),
        running_seq_ids=tuple(seq.seq_id for seq in running),
        used_block_ids=tuple(sorted(scheduler.block_manager.used_block_ids)),
        free_block_count=len(scheduler.block_manager.free_block_ids),
        sequences=tuple(_capture_sequence(seq) for seq in observed),
    )
