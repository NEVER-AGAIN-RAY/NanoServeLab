"""纯 per-request 指标派生的确定性 CPU 测试。"""

import unittest
from dataclasses import FrozenInstanceError, replace

from nanovllm.engine.request_metrics import RequestMetrics, derive_request_metrics
from nanovllm.engine.request_timing import RequestTimingRecord


def _finished_record(**overrides) -> RequestTimingRecord:
    base = dict(
        seq_id=42,
        prompt_tokens=8,
        output_tokens=3,
        outcome="finished",
        arrival_ns=1_000_000,
        first_scheduled_ns=1_500_000,
        first_output_ns=3_000_000,
        completed_ns=5_000_000,
    )
    base.update(overrides)
    return RequestTimingRecord(**base)


class DeriveRequestMetricsTest(unittest.TestCase):

    def test_multi_token_formulas(self):
        record = _finished_record()
        metrics = derive_request_metrics(record)

        self.assertIsInstance(metrics, RequestMetrics)
        self.assertEqual(metrics.seq_id, 42)
        self.assertEqual(metrics.queue_time_ms, 0.5)
        self.assertEqual(metrics.ttft_ms, 2.0)
        self.assertEqual(metrics.e2e_ms, 4.0)
        self.assertEqual(metrics.mean_tpot_ms, 1.0)

    def test_single_token_mean_tpot_is_none(self):
        record = _finished_record(
            output_tokens=1,
            first_scheduled_ns=1_200_000,
            first_output_ns=2_000_000,
            completed_ns=2_500_000,
        )
        metrics = derive_request_metrics(record)

        self.assertEqual(metrics.seq_id, 42)
        self.assertEqual(metrics.queue_time_ms, 0.2)
        self.assertEqual(metrics.ttft_ms, 1.0)
        self.assertEqual(metrics.e2e_ms, 1.5)
        self.assertIsNone(metrics.mean_tpot_ms)

    def test_equal_timestamps_yield_zero_ms(self):
        record = _finished_record(
            output_tokens=2,
            arrival_ns=7_000_000,
            first_scheduled_ns=7_000_000,
            first_output_ns=7_000_000,
            completed_ns=7_000_000,
        )
        metrics = derive_request_metrics(record)

        self.assertEqual(metrics.queue_time_ms, 0.0)
        self.assertEqual(metrics.ttft_ms, 0.0)
        self.assertEqual(metrics.e2e_ms, 0.0)
        self.assertEqual(metrics.mean_tpot_ms, 0.0)

    def test_metrics_are_immutable(self):
        metrics = derive_request_metrics(_finished_record())
        with self.assertRaises(FrozenInstanceError):
            metrics.ttft_ms = 99.0

    def test_derivation_does_not_mutate_record(self):
        record = _finished_record()
        before = replace(record)
        metrics = derive_request_metrics(record)

        self.assertEqual(record, before)
        self.assertEqual(metrics.seq_id, record.seq_id)
        self.assertIs(record.outcome, before.outcome)

    def test_non_finished_outcome_raises(self):
        record = _finished_record(outcome=None)
        with self.assertRaises(ValueError) as ctx:
            derive_request_metrics(record)
        self.assertIn("outcome", str(ctx.exception))

    def test_zero_output_tokens_raises(self):
        record = _finished_record(output_tokens=0)
        with self.assertRaises(ValueError) as ctx:
            derive_request_metrics(record)
        self.assertIn("output_tokens", str(ctx.exception))

    def test_negative_output_tokens_raises(self):
        record = _finished_record(output_tokens=-1)
        with self.assertRaises(ValueError) as ctx:
            derive_request_metrics(record)
        self.assertIn("output_tokens", str(ctx.exception))

    def test_missing_first_scheduled_raises(self):
        record = _finished_record(first_scheduled_ns=None)
        with self.assertRaises(ValueError) as ctx:
            derive_request_metrics(record)
        self.assertIn("first_scheduled_ns", str(ctx.exception))

    def test_missing_first_output_raises(self):
        record = _finished_record(first_output_ns=None)
        with self.assertRaises(ValueError) as ctx:
            derive_request_metrics(record)
        self.assertIn("first_output_ns", str(ctx.exception))

    def test_missing_completed_raises(self):
        record = _finished_record(completed_ns=None)
        with self.assertRaises(ValueError) as ctx:
            derive_request_metrics(record)
        self.assertIn("completed_ns", str(ctx.exception))

    def test_scheduled_before_arrival_raises(self):
        record = _finished_record(
            arrival_ns=2_000_000,
            first_scheduled_ns=1_000_000,
        )
        with self.assertRaises(ValueError) as ctx:
            derive_request_metrics(record)
        self.assertIn("timestamps", str(ctx.exception))

    def test_first_output_before_scheduled_raises(self):
        record = _finished_record(
            first_scheduled_ns=3_000_000,
            first_output_ns=2_000_000,
        )
        with self.assertRaises(ValueError) as ctx:
            derive_request_metrics(record)
        self.assertIn("timestamps", str(ctx.exception))

    def test_completed_before_first_output_raises(self):
        record = _finished_record(
            first_output_ns=4_000_000,
            completed_ns=3_000_000,
        )
        with self.assertRaises(ValueError) as ctx:
            derive_request_metrics(record)
        self.assertIn("timestamps", str(ctx.exception))

    def test_seq_id_preserved(self):
        record = _finished_record(seq_id=99)
        metrics = derive_request_metrics(record)
        self.assertEqual(metrics.seq_id, 99)


if __name__ == "__main__":
    unittest.main()
