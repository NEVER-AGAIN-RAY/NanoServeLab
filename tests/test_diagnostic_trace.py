"""Deterministic CPU tests for the optional per-step diagnostic trace."""

import unittest
from dataclasses import FrozenInstanceError
from types import SimpleNamespace

from nanovllm.engine.diagnostic_trace import DiagnosticTraceRecorder, select_runner_path
from nanovllm.engine.scheduler import Scheduler
from nanovllm.engine.sequence import Sequence, SequenceStatus
from nanovllm.sampling_params import SamplingParams


class FakeClock:
    def __init__(self, start_ns: int = 1_000):
        self.now = start_ns
        self.calls = 0

    def __call__(self) -> int:
        value = self.now
        self.now += 100
        self.calls += 1
        return value


class DiagnosticTraceTest(unittest.TestCase):

    def setUp(self):
        self.original_block_size = Sequence.block_size
        Sequence.block_size = 4

    def tearDown(self):
        Sequence.block_size = self.original_block_size

    @staticmethod
    def make_scheduler(
        recorder=None,
        *,
        max_num_seqs=2,
        max_num_batched_tokens=16,
        num_kvcache_blocks=8,
    ):
        config = SimpleNamespace(
            max_num_seqs=max_num_seqs,
            max_num_batched_tokens=max_num_batched_tokens,
            eos=-1,
            kvcache_block_size=4,
            num_kvcache_blocks=num_kvcache_blocks,
        )
        return Scheduler(config, diagnostic_trace_recorder=recorder)

    @staticmethod
    def make_sequence(tokens, *, max_tokens=3):
        return Sequence(
            list(tokens),
            SamplingParams(temperature=1.0, max_tokens=max_tokens, ignore_eos=True),
        )

    def finish_trace_step(self, recorder, scheduler, seqs, is_prefill, token_ids):
        recorder.after_schedule(scheduler, seqs, is_prefill)
        recorder.record_runner_path(
            execution_path="prefill_eager" if is_prefill else "decode_cuda_graph",
            enforce_eager=False,
            sequence_count=len(seqs),
            input_token_count=(
                sum(seq.num_scheduled_tokens for seq in seqs)
                if is_prefill
                else len(seqs)
            ),
            cuda_graph_bucket=None if is_prefill else 1,
        )
        recorder.after_runner()
        scheduler.postprocess(seqs, token_ids, is_prefill)
        recorder.finish_step(scheduler)

    def test_prefill_record_is_complete_immutable_and_historical(self):
        clock = FakeClock()
        recorder = DiagnosticTraceRecorder(clock_ns=clock)
        scheduler = self.make_scheduler(recorder, max_num_batched_tokens=4)
        seq = self.make_sequence(range(6), max_tokens=2)
        scheduler.add(seq)

        recorder.begin_step(scheduler)
        seqs, is_prefill = scheduler.schedule()
        self.finish_trace_step(recorder, scheduler, seqs, is_prefill, [90])

        self.assertEqual(clock.calls, 8)
        snapshots = recorder.snapshots()
        self.assertIsInstance(snapshots, tuple)
        self.assertEqual(len(snapshots), 1)
        record = snapshots[0]
        self.assertEqual(record.step_ordinal, 1)
        self.assertEqual(record.mode, "prefill")
        self.assertEqual(record.scheduled_seq_ids, (seq.seq_id,))
        self.assertEqual(record.scheduled_token_count, 4)
        self.assertEqual(record.max_query_tokens, 4)
        self.assertEqual(record.max_context_tokens, 4)
        self.assertIsNone(record.batch_size)
        self.assertEqual(record.before_schedule.waiting_count, 1)
        self.assertEqual(record.after_schedule.waiting_count, 1)
        self.assertEqual(record.after_postprocess.waiting_count, 1)
        self.assertEqual(record.runner.execution_path, "prefill_eager")
        self.assertFalse(record.runner.enforce_eager)
        self.assertEqual(record.runner.input_token_count, 4)
        self.assertEqual(
            (
                record.step_start_ns,
                record.schedule_start_ns,
                record.schedule_end_ns,
                record.runner_call_start_ns,
                record.runner_call_end_ns,
                record.postprocess_start_ns,
                record.postprocess_end_ns,
                record.step_end_ns,
            ),
            tuple(range(1_000, 1_800, 100)),
        )

        with self.assertRaises(FrozenInstanceError):
            record.mode = "decode"

        scheduler.postprocess([], [], True)
        self.assertEqual(snapshots[0].scheduled_token_count, 4)

    def test_prefix_hit_is_separate_from_recovery(self):
        clock = FakeClock()
        recorder = DiagnosticTraceRecorder(clock_ns=clock)
        scheduler = self.make_scheduler(recorder)

        source = self.make_sequence([1, 2, 3, 4, 20, 21, 22, 23])
        scheduler.block_manager.allocate(source, num_cached_blocks=0)
        source.num_scheduled_tokens = source.num_tokens
        scheduler.block_manager.hash_blocks(source)
        scheduler.block_manager.deallocate(source)

        candidate = self.make_sequence([1, 2, 3, 4, 30, 31, 32, 33])
        scheduler.add(candidate)
        recorder.begin_step(scheduler)
        seqs, is_prefill = scheduler.schedule()
        self.finish_trace_step(recorder, scheduler, seqs, is_prefill, [99])

        state = recorder.snapshots()[0].scheduled_sequences[0]
        self.assertEqual(state.prefix_cache_hit_blocks, 1)
        self.assertFalse(state.is_recovery)
        self.assertEqual(state.num_cached_tokens_before_runner, 4)

    def test_decode_pressure_records_preempted_victim_and_graph_bucket(self):
        clock = FakeClock()
        recorder = DiagnosticTraceRecorder(clock_ns=clock)
        scheduler = self.make_scheduler(recorder, num_kvcache_blocks=2)
        current = self.make_sequence([10, 11, 12, 13])
        victim = self.make_sequence([30, 31, 32, 33])

        for seq, token_id in ((current, 100), (victim, 200)):
            scheduler.block_manager.allocate(seq, num_cached_blocks=0)
            seq.num_cached_tokens = 4
            seq.append_token(token_id)
            seq.status = SequenceStatus.RUNNING
            seq.is_prefill = False
            scheduler.running.append(seq)

        recorder.begin_step(scheduler)
        seqs, is_prefill = scheduler.schedule()
        self.finish_trace_step(recorder, scheduler, seqs, is_prefill, [101])

        record = recorder.snapshots()[0]
        self.assertEqual(record.mode, "decode")
        self.assertEqual(record.preempted_seq_ids, (victim.seq_id,))
        self.assertEqual(record.preemption_count, 1)
        self.assertEqual(record.batch_size, 1)
        self.assertEqual(record.runner.execution_path, "decode_cuda_graph")
        self.assertEqual(record.runner.cuda_graph_bucket, 1)
        self.assertEqual(record.after_schedule.waiting_count, 1)
        self.assertEqual(record.after_schedule.free_block_count, 0)
        self.assertEqual(record.after_schedule.used_block_count, 2)

    def test_non_monotonic_clock_is_rejected(self):
        clock_values = iter((100, 200, 300, 400, 350, 600, 700, 800))
        recorder = DiagnosticTraceRecorder(clock_ns=lambda: next(clock_values))
        scheduler = self.make_scheduler(recorder)
        scheduler.add(self.make_sequence([1, 2, 3, 4]))

        recorder.begin_step(scheduler)
        seqs, is_prefill = scheduler.schedule()
        recorder.after_schedule(scheduler, seqs, is_prefill)
        recorder.record_runner_path(
            execution_path="prefill_eager",
            enforce_eager=False,
            sequence_count=1,
            input_token_count=4,
            cuda_graph_bucket=None,
        )
        recorder.after_runner()
        scheduler.postprocess(seqs, [9], is_prefill)
        with self.assertRaisesRegex(ValueError, "monotonic"):
            recorder.finish_step(scheduler)

    def test_missing_runner_path_is_rejected(self):
        recorder = DiagnosticTraceRecorder(clock_ns=FakeClock())
        scheduler = self.make_scheduler(recorder)
        scheduler.add(self.make_sequence([1, 2, 3, 4]))

        recorder.begin_step(scheduler)
        seqs, is_prefill = scheduler.schedule()
        recorder.after_schedule(scheduler, seqs, is_prefill)
        recorder.after_runner()
        scheduler.postprocess(seqs, [9], is_prefill)
        with self.assertRaisesRegex(RuntimeError, "runner path"):
            recorder.finish_step(scheduler)

    def test_no_recorder_keeps_scheduler_default_path(self):
        scheduler = self.make_scheduler()
        seq = self.make_sequence([1, 2, 3, 4], max_tokens=1)
        scheduler.add(seq)
        seqs, is_prefill = scheduler.schedule()
        scheduler.postprocess(seqs, [9], is_prefill)

        self.assertTrue(scheduler.is_finished())
        self.assertIsNone(scheduler.diagnostic_trace_recorder)
        self.assertEqual(seq.completion_token_ids, [9])

    def test_runner_path_uses_actual_decode_graph_bucket_selection(self):
        self.assertEqual(
            select_runner_path(
                is_prefill=True,
                enforce_eager=False,
                input_token_count=16_384,
                graph_buckets=(),
            ),
            ("prefill_eager", None),
        )
        self.assertEqual(
            select_runner_path(
                is_prefill=False,
                enforce_eager=True,
                input_token_count=7,
                graph_buckets=(1, 2, 4, 8),
            ),
            ("decode_eager", None),
        )
        self.assertEqual(
            select_runner_path(
                is_prefill=False,
                enforce_eager=False,
                input_token_count=7,
                graph_buckets=(1, 2, 4, 8, 16),
            ),
            ("decode_cuda_graph", 8),
        )


if __name__ == "__main__":
    unittest.main()
