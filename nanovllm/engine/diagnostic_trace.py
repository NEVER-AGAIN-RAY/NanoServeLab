"""Optional immutable per-step diagnostic trace for Scheduler experiments."""

from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter_ns
from typing import TYPE_CHECKING, Callable, Literal

if TYPE_CHECKING:
    from nanovllm.engine.scheduler import Scheduler
    from nanovllm.engine.sequence import Sequence


TraceMode = Literal["prefill", "decode"]
ExecutionPath = Literal["prefill_eager", "decode_eager", "decode_cuda_graph"]


@dataclass(frozen=True, slots=True)
class QueueKvState:
    waiting_count: int
    running_count: int
    free_block_count: int
    used_block_count: int


@dataclass(frozen=True, slots=True)
class ScheduledSequenceState:
    seq_id: int
    num_prompt_tokens: int
    num_completion_tokens_before: int
    num_cached_tokens_before_runner: int
    num_scheduled_tokens: int
    block_count_before_runner: int
    prefix_cache_hit_blocks: int
    is_recovery: bool


@dataclass(frozen=True, slots=True)
class RunnerPathState:
    execution_path: ExecutionPath
    enforce_eager: bool
    sequence_count: int
    input_token_count: int
    cuda_graph_bucket: int | None


@dataclass(frozen=True, slots=True)
class DiagnosticStepRecord:
    trace_contract: str
    trace_schema_version: str
    step_ordinal: int
    mode: TraceMode
    scheduling_policy: str
    scheduled_seq_ids: tuple[int, ...]
    scheduled_sequence_count: int
    scheduled_token_count: int
    max_query_tokens: int | None
    max_context_tokens: int | None
    batch_size: int | None
    before_schedule: QueueKvState
    after_schedule: QueueKvState
    after_postprocess: QueueKvState
    scheduled_sequences: tuple[ScheduledSequenceState, ...]
    preemption_count: int
    preempted_seq_ids: tuple[int, ...]
    runner: RunnerPathState
    step_start_ns: int
    schedule_start_ns: int
    schedule_end_ns: int
    runner_call_start_ns: int
    runner_call_end_ns: int
    postprocess_start_ns: int
    postprocess_end_ns: int
    step_end_ns: int

@dataclass(slots=True)
class _PendingStep:
    step_ordinal: int
    scheduling_policy: str
    before_schedule: QueueKvState
    recovery_by_seq_id: dict[int, bool]
    step_start_ns: int
    schedule_start_ns: int
    prefix_hits_by_seq_id: dict[int, int]
    preempted_seq_ids: list[int]
    schedule_end_ns: int | None = None
    runner_call_start_ns: int | None = None
    mode: TraceMode | None = None
    after_schedule: QueueKvState | None = None
    scheduled_sequences: tuple[ScheduledSequenceState, ...] | None = None
    runner: RunnerPathState | None = None
    runner_call_end_ns: int | None = None
    postprocess_start_ns: int | None = None


class DiagnosticTraceRecorder:
    """Collect step records without exposing live Scheduler containers."""

    TRACE_CONTRACT = "NSL-S3-DIAG-TRACE-v1"
    TRACE_SCHEMA_VERSION = "nanovllm.scheduler-step-trace.v1"

    def __init__(self, *, clock_ns: Callable[[], int] = perf_counter_ns):
        self._clock_ns = clock_ns
        self._records: list[DiagnosticStepRecord] = []
        self._pending: _PendingStep | None = None

    @staticmethod
    def _state(scheduler: Scheduler) -> QueueKvState:
        manager = scheduler.block_manager
        return QueueKvState(
            waiting_count=len(scheduler.waiting),
            running_count=len(scheduler.running),
            free_block_count=len(manager.free_block_ids),
            used_block_count=len(manager.used_block_ids),
        )

    def begin_step(self, scheduler: Scheduler) -> None:
        if self._pending is not None:
            raise RuntimeError("diagnostic trace step is already active")
        step_start_ns = self._clock_ns()
        before_schedule = self._state(scheduler)
        recovery_by_seq_id = {
            seq.seq_id: bool(seq.block_table) or seq.num_completion_tokens > 0
            for seq in (*scheduler.waiting, *scheduler.running)
        }
        schedule_start_ns = self._clock_ns()
        self._pending = _PendingStep(
            step_ordinal=len(self._records) + 1,
            scheduling_policy=scheduler.scheduling_policy,
            before_schedule=before_schedule,
            recovery_by_seq_id=recovery_by_seq_id,
            step_start_ns=step_start_ns,
            schedule_start_ns=schedule_start_ns,
            prefix_hits_by_seq_id={},
            preempted_seq_ids=[],
        )

    def record_prefix_cache_hit(self, seq_id: int, block_count: int) -> None:
        if self._pending is not None:
            self._pending.prefix_hits_by_seq_id[seq_id] = block_count

    def record_preemption(self, seq_id: int) -> None:
        if self._pending is not None:
            self._pending.preempted_seq_ids.append(seq_id)

    def after_schedule(
        self,
        scheduler: Scheduler,
        seqs: list[Sequence],
        is_prefill: bool,
    ) -> None:
        pending = self._require_pending()
        pending.schedule_end_ns = self._clock_ns()
        pending.mode = "prefill" if is_prefill else "decode"
        pending.after_schedule = self._state(scheduler)
        pending.scheduled_sequences = tuple(
            ScheduledSequenceState(
                seq_id=seq.seq_id,
                num_prompt_tokens=seq.num_prompt_tokens,
                num_completion_tokens_before=seq.num_completion_tokens,
                num_cached_tokens_before_runner=seq.num_cached_tokens,
                num_scheduled_tokens=seq.num_scheduled_tokens,
                block_count_before_runner=len(seq.block_table),
                prefix_cache_hit_blocks=pending.prefix_hits_by_seq_id.get(seq.seq_id, 0),
                is_recovery=pending.recovery_by_seq_id.get(seq.seq_id, False),
            )
            for seq in seqs
        )
        pending.runner_call_start_ns = self._clock_ns()

    def record_runner_path(
        self,
        *,
        execution_path: ExecutionPath,
        enforce_eager: bool,
        sequence_count: int,
        input_token_count: int,
        cuda_graph_bucket: int | None,
    ) -> None:
        if self._pending is None:
            return
        if self._pending.runner is not None:
            raise RuntimeError("runner path already recorded for diagnostic step")
        self._pending.runner = RunnerPathState(
            execution_path=execution_path,
            enforce_eager=enforce_eager,
            sequence_count=sequence_count,
            input_token_count=input_token_count,
            cuda_graph_bucket=cuda_graph_bucket,
        )

    def after_runner(self) -> None:
        pending = self._require_pending()
        pending.runner_call_end_ns = self._clock_ns()
        pending.postprocess_start_ns = self._clock_ns()

    def finish_step(self, scheduler: Scheduler) -> None:
        pending = self._require_pending()
        postprocess_end_ns = self._clock_ns()
        after_postprocess = self._state(scheduler)
        step_end_ns = self._clock_ns()
        if pending.runner is None:
            raise RuntimeError("runner path is missing from diagnostic step")
        if (
            pending.schedule_end_ns is None
            or pending.runner_call_start_ns is None
            or pending.runner_call_end_ns is None
            or pending.postprocess_start_ns is None
            or pending.mode is None
            or pending.after_schedule is None
            or pending.scheduled_sequences is None
        ):
            raise RuntimeError("diagnostic step is incomplete")
        timestamps = (
            pending.step_start_ns,
            pending.schedule_start_ns,
            pending.schedule_end_ns,
            pending.runner_call_start_ns,
            pending.runner_call_end_ns,
            pending.postprocess_start_ns,
            postprocess_end_ns,
            step_end_ns,
        )
        if any(type(value) is not int for value in timestamps):
            raise ValueError("diagnostic step timestamps must be integers")
        if any(value < 0 for value in timestamps) or any(
            earlier > later for earlier, later in zip(timestamps, timestamps[1:])
        ):
            raise ValueError("diagnostic step timestamps must be non-negative and monotonic")
        scheduled = pending.scheduled_sequences
        mode = pending.mode
        record = DiagnosticStepRecord(
            trace_contract=self.TRACE_CONTRACT,
            trace_schema_version=self.TRACE_SCHEMA_VERSION,
            step_ordinal=pending.step_ordinal,
            mode=mode,
            scheduling_policy=pending.scheduling_policy,
            scheduled_seq_ids=tuple(item.seq_id for item in scheduled),
            scheduled_sequence_count=len(scheduled),
            scheduled_token_count=sum(item.num_scheduled_tokens for item in scheduled),
            max_query_tokens=(
                max(item.num_scheduled_tokens for item in scheduled) if mode == "prefill" else None
            ),
            max_context_tokens=(
                max(
                    item.num_cached_tokens_before_runner + item.num_scheduled_tokens
                    for item in scheduled
                )
                if mode == "prefill"
                else None
            ),
            batch_size=len(scheduled) if mode == "decode" else None,
            before_schedule=pending.before_schedule,
            after_schedule=pending.after_schedule,
            after_postprocess=after_postprocess,
            scheduled_sequences=scheduled,
            preemption_count=len(pending.preempted_seq_ids),
            preempted_seq_ids=tuple(pending.preempted_seq_ids),
            runner=pending.runner,
            step_start_ns=pending.step_start_ns,
            schedule_start_ns=pending.schedule_start_ns,
            schedule_end_ns=pending.schedule_end_ns,
            runner_call_start_ns=pending.runner_call_start_ns,
            runner_call_end_ns=pending.runner_call_end_ns,
            postprocess_start_ns=pending.postprocess_start_ns,
            postprocess_end_ns=postprocess_end_ns,
            step_end_ns=step_end_ns,
        )
        self._records.append(record)
        self._pending = None

    def snapshots(self) -> tuple[DiagnosticStepRecord, ...]:
        return tuple(self._records)

    def _require_pending(self) -> _PendingStep:
        if self._pending is None:
            raise RuntimeError("no active diagnostic trace step")
        return self._pending


def select_runner_path(
    *,
    is_prefill: bool,
    enforce_eager: bool,
    input_token_count: int,
    graph_buckets: tuple[int, ...] | list[int],
) -> tuple[ExecutionPath, int | None]:
    """Return the exact execution branch and Decode graph bucket to use."""

    if is_prefill:
        return "prefill_eager", None
    if enforce_eager or input_token_count > 512:
        return "decode_eager", None
    return "decode_cuda_graph", next(
        bucket for bucket in graph_buckets if bucket >= input_token_count
    )
