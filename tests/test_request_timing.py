"""Scheduler 级 per-request timing record 的 fake-clock CPU 测试。"""

import unittest
from dataclasses import FrozenInstanceError
from types import SimpleNamespace

from nanovllm.engine.request_timing import RequestTimingRecorder
from nanovllm.engine.scheduler import Scheduler
from nanovllm.engine.sequence import Sequence, SequenceStatus
from nanovllm.sampling_params import SamplingParams


class FakeClock:
    """完全确定的 monotonic 时钟；每次调用返回递增纳秒，不使用 sleep。"""

    def __init__(self, start_ns: int = 1_000):
        self._now = start_ns

    def __call__(self) -> int:
        value = self._now
        self._now += 100
        return value


class RequestTimingTest(unittest.TestCase):

    def setUp(self):
        self.original_block_size = Sequence.block_size
        Sequence.block_size = 4
        self.clock = FakeClock()
        self.recorder = RequestTimingRecorder(clock_ns=self.clock)
        self.config = SimpleNamespace(
            max_num_seqs=1,
            max_num_batched_tokens=4,
            eos=-1,
            kvcache_block_size=4,
            num_kvcache_blocks=8,
        )
        self.scheduler = Scheduler(self.config, timing_recorder=self.recorder)
        self.seq = Sequence(
            token_ids=[10, 11, 12, 13, 14, 15],
            sampling_params=SamplingParams(
                temperature=1.0,
                max_tokens=2,
                ignore_eos=True,
            ),
        )

    def tearDown(self):
        Sequence.block_size = self.original_block_size

    def test_arrival_records_prompt_tokens_on_add(self):
        self.scheduler.add(self.seq)

        record = self.recorder.get(self.seq.seq_id)
        self.assertEqual(record.seq_id, self.seq.seq_id)
        self.assertEqual(record.prompt_tokens, 6)
        self.assertEqual(record.output_tokens, 0)
        self.assertIsNone(record.outcome)
        self.assertEqual(record.arrival_ns, 1_000)
        self.assertIsNone(record.first_scheduled_ns)
        self.assertIsNone(record.first_output_ns)
        self.assertIsNone(record.completed_ns)
        self.assertEqual(list(self.scheduler.waiting), [self.seq])

    def test_chunked_prefill_first_scheduled_and_first_output(self):
        self.scheduler.add(self.seq)
        arrival_ns = self.recorder.get(self.seq.seq_id).arrival_ns

        # Round 1：首轮 Prefill 写入 first_scheduled；临时采样被丢弃。
        seqs, is_prefill = self.scheduler.schedule()
        first_scheduled_ns = self.recorder.get(self.seq.seq_id).first_scheduled_ns
        self.assertTrue(is_prefill)
        self.assertEqual(seqs, [self.seq])
        self.assertIsNotNone(first_scheduled_ns)
        self.assertGreaterEqual(first_scheduled_ns, arrival_ns)

        self.scheduler.postprocess(seqs, [90], is_prefill)
        after_discard = self.recorder.get(self.seq.seq_id)
        self.assertIsNone(after_discard.first_output_ns)
        self.assertEqual(after_discard.output_tokens, 0)
        self.assertEqual(self.seq.completion_token_ids, [])

        # Round 2：再次 schedule 不得覆盖 first_scheduled；真实 Token 才写 first_output。
        clock_before_reschedule = self.clock._now
        seqs, is_prefill = self.scheduler.schedule()
        after_reschedule = self.recorder.get(self.seq.seq_id)
        self.assertEqual(after_reschedule.first_scheduled_ns, first_scheduled_ns)
        self.assertEqual(self.clock._now, clock_before_reschedule)

        self.scheduler.postprocess(seqs, [91], is_prefill)
        after_first_token = self.recorder.get(self.seq.seq_id)
        self.assertEqual(self.seq.completion_token_ids, [91])
        self.assertEqual(after_first_token.output_tokens, 1)
        self.assertIsNotNone(after_first_token.first_output_ns)
        self.assertGreaterEqual(
            after_first_token.first_output_ns,
            first_scheduled_ns,
        )

    def test_decode_completion_preserves_write_once_timestamps(self):
        self.scheduler.add(self.seq)

        seqs, is_prefill = self.scheduler.schedule()
        self.scheduler.postprocess(seqs, [90], is_prefill)
        seqs, is_prefill = self.scheduler.schedule()
        self.scheduler.postprocess(seqs, [91], is_prefill)

        before_decode = self.recorder.get(self.seq.seq_id)
        first_scheduled_ns = before_decode.first_scheduled_ns
        first_output_ns = before_decode.first_output_ns
        self.assertIsNotNone(first_scheduled_ns)
        self.assertIsNotNone(first_output_ns)

        clock_before_decode_schedule = self.clock._now
        seqs, is_prefill = self.scheduler.schedule()
        self.assertFalse(is_prefill)
        after_decode_schedule = self.recorder.get(self.seq.seq_id)
        self.assertEqual(after_decode_schedule.first_scheduled_ns, first_scheduled_ns)
        self.assertEqual(self.clock._now, clock_before_decode_schedule)

        self.scheduler.postprocess(seqs, [92], is_prefill)
        finished = self.recorder.get(self.seq.seq_id)

        self.assertEqual(finished.first_output_ns, first_output_ns)
        self.assertEqual(finished.output_tokens, 2)
        self.assertEqual(finished.outcome, "finished")
        self.assertIsNotNone(finished.completed_ns)
        self.assertGreaterEqual(finished.completed_ns, first_output_ns)
        self.assertEqual(self.seq.status, SequenceStatus.FINISHED)
        self.assertTrue(self.scheduler.is_finished())

    def test_record_survives_kv_release_and_is_immutable(self):
        self.scheduler.add(self.seq)

        seqs, is_prefill = self.scheduler.schedule()
        self.scheduler.postprocess(seqs, [90], is_prefill)
        seqs, is_prefill = self.scheduler.schedule()
        self.scheduler.postprocess(seqs, [91], is_prefill)
        seqs, is_prefill = self.scheduler.schedule()
        self.scheduler.postprocess(seqs, [92], is_prefill)

        self.assertEqual(self.seq.block_table, [])
        self.assertEqual(self.scheduler.block_manager.used_block_ids, set())
        self.assertEqual(len(self.scheduler.block_manager.free_block_ids), 8)

        snapshot = self.recorder.get(self.seq.seq_id)
        self.assertEqual(snapshot.outcome, "finished")
        self.assertEqual(snapshot.output_tokens, 2)
        self.assertIsNotNone(snapshot.completed_ns)
        self.assertLessEqual(snapshot.arrival_ns, snapshot.first_scheduled_ns)
        self.assertLessEqual(snapshot.first_scheduled_ns, snapshot.first_output_ns)
        self.assertLessEqual(snapshot.first_output_ns, snapshot.completed_ns)

        with self.assertRaises(FrozenInstanceError):
            snapshot.output_tokens = 99
        self.assertEqual(self.recorder.get(self.seq.seq_id).output_tokens, 2)

    def test_duplicate_arrival_is_rejected(self):
        self.scheduler.add(self.seq)
        with self.assertRaises(ValueError):
            self.recorder.record_arrival(self.seq.seq_id, self.seq.num_prompt_tokens)

    def test_default_scheduler_without_recorder_keeps_lifecycle(self):
        scheduler = Scheduler(self.config)
        seq = Sequence(
            token_ids=[10, 11, 12, 13, 14, 15],
            sampling_params=SamplingParams(
                temperature=1.0,
                max_tokens=2,
                ignore_eos=True,
            ),
        )
        scheduler.add(seq)

        seqs, is_prefill = scheduler.schedule()
        scheduler.postprocess(seqs, [90], is_prefill)
        seqs, is_prefill = scheduler.schedule()
        scheduler.postprocess(seqs, [91], is_prefill)
        seqs, is_prefill = scheduler.schedule()
        scheduler.postprocess(seqs, [92], is_prefill)

        self.assertEqual(seq.status, SequenceStatus.FINISHED)
        self.assertTrue(scheduler.is_finished())
        self.assertEqual(seq.block_table, [])
        self.assertEqual(scheduler.block_manager.used_block_ids, set())
        self.assertIsNone(scheduler.timing_recorder)


class RequestTimingSnapshotsTest(unittest.TestCase):
    """``snapshots()`` 语义：排序、不可变、不调用时钟。"""

    def test_empty_snapshots_is_empty_tuple(self):
        recorder = RequestTimingRecorder(clock_ns=FakeClock())
        snapshots = recorder.snapshots()
        self.assertIsInstance(snapshots, tuple)
        self.assertEqual(snapshots, ())

    def test_snapshots_sorted_by_seq_id_without_clock(self):
        clock = FakeClock(start_ns=5_000)
        recorder = RequestTimingRecorder(clock_ns=clock)
        recorder.record_arrival(30, prompt_tokens=3)
        recorder.record_arrival(10, prompt_tokens=1)
        recorder.record_arrival(20, prompt_tokens=2)

        clock_before = clock._now
        snapshots = recorder.snapshots()
        self.assertEqual(clock._now, clock_before)
        self.assertEqual([record.seq_id for record in snapshots], [10, 20, 30])
        self.assertEqual([record.prompt_tokens for record in snapshots], [1, 2, 3])

    def test_early_snapshots_keep_history_and_are_immutable(self):
        clock = FakeClock()
        recorder = RequestTimingRecorder(clock_ns=clock)
        recorder.record_arrival(7, prompt_tokens=4)

        early = recorder.snapshots()
        self.assertEqual(len(early), 1)
        early_record = early[0]
        self.assertIsNone(early_record.first_scheduled_ns)
        self.assertIsNone(early_record.first_output_ns)
        self.assertEqual(early_record.output_tokens, 0)

        recorder.record_first_scheduled(7)
        recorder.record_output_token(7, output_tokens=1)
        later = recorder.snapshots()

        self.assertIsNone(early_record.first_scheduled_ns)
        self.assertIsNone(early_record.first_output_ns)
        self.assertEqual(early_record.output_tokens, 0)
        self.assertIsNotNone(later[0].first_scheduled_ns)
        self.assertIsNotNone(later[0].first_output_ns)
        self.assertEqual(later[0].output_tokens, 1)

        with self.assertRaises(TypeError):
            early[0] = later[0]
        with self.assertRaises(FrozenInstanceError):
            early_record.output_tokens = 99
        self.assertEqual(early_record.output_tokens, 0)


if __name__ == "__main__":
    unittest.main()
