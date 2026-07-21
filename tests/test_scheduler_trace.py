"""Scheduler 结构化 Step Snapshot 测试。"""

import unittest
from types import SimpleNamespace

from nanovllm.engine.scheduler import Scheduler
from nanovllm.engine.scheduler_trace import capture_scheduler_snapshot
from nanovllm.engine.sequence import Sequence
from nanovllm.sampling_params import SamplingParams


class SchedulerTraceTest(unittest.TestCase):

    def setUp(self):
        self.original_block_size = Sequence.block_size
        Sequence.block_size = 4

        config = SimpleNamespace(
            max_num_seqs=1,
            max_num_batched_tokens=4,
            eos=-1,
            kvcache_block_size=4,
            num_kvcache_blocks=8,
        )
        self.scheduler = Scheduler(config)
        self.seq = Sequence(
            token_ids=[10, 11, 12, 13, 14, 15],
            sampling_params=SamplingParams(
                temperature=1.0,
                max_tokens=2,
                ignore_eos=True,
            ),
        )
        self.scheduler.add(self.seq)

    def tearDown(self):
        Sequence.block_size = self.original_block_size

    def capture(self, seqs, is_prefill, step, phase):
        return capture_scheduler_snapshot(
            scheduler=self.scheduler,
            scheduled_seqs=seqs,
            step=step,
            phase=phase,
            is_prefill=is_prefill,
        )

    def test_snapshots_follow_lifecycle_and_remain_historical(self):
        # Step 1：首轮只调度 4 个 Prompt Token，请求仍在 WAITING。
        seqs, is_prefill = self.scheduler.schedule()
        step_1_scheduled = self.capture(
            seqs, is_prefill, step=1, phase="after_schedule"
        )

        self.assertEqual(step_1_scheduled.phase, "after_schedule")
        self.assertEqual(step_1_scheduled.mode, "prefill")
        self.assertEqual(step_1_scheduled.scheduled_seq_ids, (self.seq.seq_id,))
        self.assertEqual(step_1_scheduled.waiting_seq_ids, (self.seq.seq_id,))
        self.assertEqual(step_1_scheduled.running_seq_ids, ())
        self.assertEqual(len(step_1_scheduled.used_block_ids), 2)
        self.assertEqual(step_1_scheduled.free_block_count, 6)

        seq_snapshot = step_1_scheduled.sequences[0]
        self.assertEqual(seq_snapshot.status, "WAITING")
        self.assertEqual(seq_snapshot.num_tokens, 6)
        self.assertEqual(seq_snapshot.num_cached_tokens, 0)
        self.assertEqual(seq_snapshot.num_scheduled_tokens, 4)
        self.assertEqual(seq_snapshot.block_count, 2)

        self.scheduler.postprocess(seqs, [90], is_prefill)
        step_1_committed = self.capture(
            seqs, is_prefill, step=1, phase="after_postprocess"
        )

        seq_snapshot = step_1_committed.sequences[0]
        self.assertEqual(seq_snapshot.status, "WAITING")
        self.assertEqual(seq_snapshot.num_cached_tokens, 4)
        self.assertEqual(seq_snapshot.num_scheduled_tokens, 0)
        self.assertEqual(seq_snapshot.num_completion_tokens, 0)

        # Step 2：剩余 Prompt 完成，进入 RUNNING 并保留 Token 91。
        seqs, is_prefill = self.scheduler.schedule()
        step_2_scheduled = self.capture(
            seqs, is_prefill, step=2, phase="after_schedule"
        )

        seq_snapshot = step_2_scheduled.sequences[0]
        self.assertEqual(step_2_scheduled.waiting_seq_ids, ())
        self.assertEqual(step_2_scheduled.running_seq_ids, (self.seq.seq_id,))
        self.assertEqual(seq_snapshot.status, "RUNNING")
        self.assertEqual(seq_snapshot.num_cached_tokens, 4)
        self.assertEqual(seq_snapshot.num_scheduled_tokens, 2)

        self.scheduler.postprocess(seqs, [91], is_prefill)
        step_2_committed = self.capture(
            seqs, is_prefill, step=2, phase="after_postprocess"
        )

        seq_snapshot = step_2_committed.sequences[0]
        self.assertEqual(seq_snapshot.num_tokens, 7)
        self.assertEqual(seq_snapshot.num_completion_tokens, 1)
        self.assertEqual(seq_snapshot.num_cached_tokens, 6)
        self.assertEqual(
            seq_snapshot.num_tokens,
            seq_snapshot.num_cached_tokens + 1,
        )

        # Step 3：Decode Token 91，采样 92 后结束并释放 KV Block。
        seqs, is_prefill = self.scheduler.schedule()
        step_3_scheduled = self.capture(
            seqs, is_prefill, step=3, phase="after_schedule"
        )

        self.assertEqual(step_3_scheduled.mode, "decode")
        self.assertEqual(step_3_scheduled.sequences[0].num_scheduled_tokens, 1)

        self.scheduler.postprocess(seqs, [92], is_prefill)
        step_3_committed = self.capture(
            seqs, is_prefill, step=3, phase="after_postprocess"
        )

        self.assertEqual(step_3_committed.waiting_seq_ids, ())
        self.assertEqual(step_3_committed.running_seq_ids, ())
        self.assertEqual(step_3_committed.phase, "after_postprocess")
        self.assertEqual(step_3_committed.used_block_ids, ())
        self.assertEqual(step_3_committed.free_block_count, 8)

        finished_snapshot = step_3_committed.sequences[0]
        self.assertEqual(finished_snapshot.status, "FINISHED")
        self.assertEqual(finished_snapshot.num_tokens, 8)
        self.assertEqual(finished_snapshot.num_completion_tokens, 2)
        self.assertEqual(finished_snapshot.num_cached_tokens, 0)
        self.assertEqual(finished_snapshot.block_count, 0)

        # Scheduler 已变化，但首轮历史快照必须仍保持采集时的旧值。
        first_snapshot = step_1_scheduled.sequences[0]
        self.assertEqual(first_snapshot.status, "WAITING")
        self.assertEqual(first_snapshot.num_cached_tokens, 0)
        self.assertEqual(first_snapshot.num_scheduled_tokens, 4)
        self.assertEqual(len(first_snapshot.block_table), 2)
        self.assertEqual(len(step_1_scheduled.used_block_ids), 2)
        self.assertEqual(self.seq.block_table, [])


if __name__ == "__main__":
    unittest.main()
