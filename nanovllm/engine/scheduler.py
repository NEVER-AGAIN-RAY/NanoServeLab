"""请求调度器：把队列状态编译成一次可执行的 GPU 批次。

核心职责：
- 维护 ``waiting`` 与 ``running`` 两个请求队列及其状态迁移。
- 在 ``max_num_seqs`` 和 ``max_num_batched_tokens`` 预算内选择请求。
- 通过 ``BlockManager`` 完成 KV Block 准入、Prefix Cache 命中与抢占释放。
- 在 ``postprocess()`` 中提交缓存进度、追加采样 Token 并结束请求。

关键状态：
- ``num_tokens``：当前已知的 Prompt + Completion Token 总数。
- ``num_cached_tokens``：已经完成前向并写入 KV Cache 的 Token 数。
- ``num_scheduled_tokens``：本轮准备送入模型的 Token 数。
- ``block_table``：Sequence 的逻辑 Block 到物理 KV Block ID 的映射。

主要部分：
1. Prefill：严格从 waiting 队首准入，支持 Prefix Cache 和 Chunked Prefill。
2. Decode：每个 Sequence 每轮处理 1 个 Token，必要时抢占队尾请求。
3. Postprocess：登记完整 Block、推进缓存进度、处理 EOS/max_tokens。

重要约束：当前每个批次只能是纯 Prefill 或纯 Decode；只要成功调度
Prefill 就会立即返回，因此该文件的队列策略会直接影响 TTFT、TPOT 和公平性。

可选 ``timing_recorder`` 观察请求生命周期，可选 ``diagnostic_trace_recorder``
观察逐 step 的 Prefix 命中与抢占事件；二者都不参与排序、准入、抢占或 KV
决策，默认 ``None`` 时行为与上游一致。
"""

from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING

from nanovllm.engine.sequence import Sequence, SequenceStatus
from nanovllm.engine.block_manager import BlockManager
from nanovllm.engine.scheduling_policy import (
    FCFS_POLICY,
    PROMPT_LENGTH_POLICY,
    normalize_scheduling_policy,
)

if TYPE_CHECKING:
    from nanovllm.config import Config


class Scheduler:

    def __init__(self, config: Config, *, timing_recorder=None, diagnostic_trace_recorder=None):
        self.max_num_seqs = config.max_num_seqs
        self.max_num_batched_tokens = config.max_num_batched_tokens
        self.eos = config.eos
        self.block_size = config.kvcache_block_size
        self.block_manager = BlockManager(config.num_kvcache_blocks, config.kvcache_block_size)
        self.waiting: deque[Sequence] = deque()
        self.running: deque[Sequence] = deque()
        self.timing_recorder = timing_recorder
        self.diagnostic_trace_recorder = diagnostic_trace_recorder
        self.scheduling_policy = normalize_scheduling_policy(
            getattr(config, "scheduling_policy", FCFS_POLICY)
        )

    def is_finished(self):
        return not self.waiting and not self.running

    def add(self, seq: Sequence):
        if self.timing_recorder is not None:
            self.timing_recorder.record_arrival(seq.seq_id, seq.num_prompt_tokens)
        if self.scheduling_policy == FCFS_POLICY:
            self.waiting.append(seq)
            return
        if self.scheduling_policy == PROMPT_LENGTH_POLICY:
            self._insert_by_prompt_length(seq)
            return
        raise AssertionError(
            f"normalized scheduling policy is not implemented: {self.scheduling_policy}"
        )

    def schedule(self) -> tuple[list[Sequence], bool]:
        scheduled_seqs = []
        num_batched_tokens = 0

        # prefill
        while self.waiting and len(scheduled_seqs) < self.max_num_seqs:
            seq = self.waiting[0]
            remaining = self.max_num_batched_tokens - num_batched_tokens
            if remaining == 0:
                break
            if not seq.block_table:
                num_cached_blocks = self.block_manager.can_allocate(seq)
                if num_cached_blocks == -1:
                    break
                if self.diagnostic_trace_recorder is not None:
                    self.diagnostic_trace_recorder.record_prefix_cache_hit(
                        seq.seq_id,
                        num_cached_blocks,
                    )
                num_tokens = seq.num_tokens - num_cached_blocks * self.block_size
            else:
                num_tokens = seq.num_tokens - seq.num_cached_tokens
            if remaining < num_tokens and scheduled_seqs:  # only allow chunked prefill for the first seq
                break
            if not seq.block_table:
                self.block_manager.allocate(seq, num_cached_blocks)
            seq.num_scheduled_tokens = min(num_tokens, remaining)
            num_batched_tokens += seq.num_scheduled_tokens
            if seq.num_cached_tokens + seq.num_scheduled_tokens == seq.num_tokens:
                seq.status = SequenceStatus.RUNNING
                self.waiting.popleft()
                self.running.append(seq)
            scheduled_seqs.append(seq)

        if scheduled_seqs:
            self._record_first_scheduled(scheduled_seqs)
            return scheduled_seqs, True

        # decode
        while self.running and len(scheduled_seqs) < self.max_num_seqs:
            seq = self.running.popleft()
            while not self.block_manager.can_append(seq):
                if self.running:
                    self.preempt(self.running.pop())
                else:
                    self.preempt(seq)
                    break
            else:
                seq.num_scheduled_tokens = 1
                seq.is_prefill = False
                self.block_manager.may_append(seq)
                scheduled_seqs.append(seq)
        assert scheduled_seqs
        self.running.extendleft(reversed(scheduled_seqs))
        self._record_first_scheduled(scheduled_seqs)
        return scheduled_seqs, False

    def preempt(self, seq: Sequence):
        if self.diagnostic_trace_recorder is not None:
            self.diagnostic_trace_recorder.record_preemption(seq.seq_id)
        seq.status = SequenceStatus.WAITING
        seq.is_prefill = True
        self.block_manager.deallocate(seq)
        self.waiting.appendleft(seq)

    def postprocess(self, seqs: list[Sequence], token_ids: list[int], is_prefill: bool):
        for seq, token_id in zip(seqs, token_ids):
            self.block_manager.hash_blocks(seq)
            seq.num_cached_tokens += seq.num_scheduled_tokens
            seq.num_scheduled_tokens = 0
            if is_prefill and seq.num_cached_tokens < seq.num_tokens:
                continue
            seq.append_token(token_id)
            if self.timing_recorder is not None:
                self.timing_recorder.record_output_token(
                    seq.seq_id,
                    seq.num_completion_tokens,
                )
            if (not seq.ignore_eos and token_id == self.eos) or seq.num_completion_tokens == seq.max_tokens:
                seq.status = SequenceStatus.FINISHED
                if self.timing_recorder is not None:
                    self.timing_recorder.record_completed(
                        seq.seq_id,
                        seq.num_completion_tokens,
                    )
                self.block_manager.deallocate(seq)
                self.running.remove(seq)

    def _record_first_scheduled(self, scheduled_seqs: list[Sequence]) -> None:
        if self.timing_recorder is None:
            return
        for seq in scheduled_seqs:
            self.timing_recorder.record_first_scheduled(seq.seq_id)

    def _insert_by_prompt_length(self, seq: Sequence) -> None:
        """Insert a fresh request after recovery work, preserving stable ties."""
        insert_at = 0
        while insert_at < len(self.waiting):
            waiting_seq = self.waiting[insert_at]
            is_recovery = (
                bool(waiting_seq.block_table)
                or waiting_seq.num_completion_tokens > 0
            )
            if not is_recovery:
                break
            insert_at += 1

        while insert_at < len(self.waiting):
            waiting_seq = self.waiting[insert_at]
            if waiting_seq.num_prompt_tokens > seq.num_prompt_tokens:
                break
            insert_at += 1
        self.waiting.insert(insert_at, seq)
