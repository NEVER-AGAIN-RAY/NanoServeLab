"""Characterization tests for the Stage 3 ``fcfs-v1`` Scheduler contract."""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from nanovllm.engine.scheduler import Scheduler
from nanovllm.engine.sequence import Sequence, SequenceStatus
from nanovllm.sampling_params import SamplingParams


class SchedulerFcfsOrderTest(unittest.TestCase):

    def setUp(self):
        self.original_block_size = Sequence.block_size
        Sequence.block_size = 4

    def tearDown(self):
        Sequence.block_size = self.original_block_size

    @staticmethod
    def make_scheduler(
        *,
        max_num_seqs: int = 3,
        max_num_batched_tokens: int = 8,
        num_kvcache_blocks: int = 16,
    ) -> Scheduler:
        config = SimpleNamespace(
            max_num_seqs=max_num_seqs,
            max_num_batched_tokens=max_num_batched_tokens,
            eos=-1,
            kvcache_block_size=4,
            num_kvcache_blocks=num_kvcache_blocks,
        )
        return Scheduler(config)

    @staticmethod
    def make_sequence(
        token_count: int,
        *,
        token_base: int,
        max_tokens: int = 4,
    ) -> Sequence:
        return Sequence(
            token_ids=list(range(token_base, token_base + token_count)),
            sampling_params=SamplingParams(
                temperature=1.0,
                max_tokens=max_tokens,
                ignore_eos=True,
            ),
        )

    def test_waiting_order_chunked_prefill_and_prefill_priority(self):
        scheduler = self.make_scheduler(max_num_batched_tokens=4)
        first = self.make_sequence(6, token_base=10)
        second = self.make_sequence(2, token_base=30)
        third = self.make_sequence(3, token_base=50)
        for seq in (first, second, third):
            scheduler.add(seq)

        self.assertEqual(list(scheduler.waiting), [first, second, third])

        # The first request owns the initial chunk and remains at the queue head.
        seqs, is_prefill = scheduler.schedule()
        self.assertTrue(is_prefill)
        self.assertEqual(seqs, [first])
        self.assertEqual(first.num_scheduled_tokens, 4)
        self.assertEqual(list(scheduler.waiting), [first, second, third])
        scheduler.postprocess(seqs, [100], is_prefill)

        # Its remaining Prompt is admitted before the following short request.
        # The remaining token budget then admits the second request in FIFO order.
        seqs, is_prefill = scheduler.schedule()
        self.assertTrue(is_prefill)
        self.assertEqual(seqs, [first, second])
        self.assertEqual(
            [seq.num_scheduled_tokens for seq in seqs],
            [2, 2],
        )
        self.assertEqual(list(scheduler.waiting), [third])
        self.assertEqual(list(scheduler.running), [first, second])
        scheduler.postprocess(seqs, [101, 201], is_prefill)

        # A waiting Prefill is selected before Decode even with running requests.
        seqs, is_prefill = scheduler.schedule()
        self.assertTrue(is_prefill)
        self.assertEqual(seqs, [third])
        self.assertEqual(list(scheduler.running), [first, second, third])

    def test_unallocatable_waiting_head_is_not_bypassed(self):
        scheduler = self.make_scheduler(num_kvcache_blocks=2)
        running = self.make_sequence(2, token_base=10)
        scheduler.add(running)
        seqs, is_prefill = scheduler.schedule()
        scheduler.postprocess(seqs, [100], is_prefill)

        # The running request owns one of two Blocks. The waiting head needs two
        # new Blocks, while the following request would fit in the one free Block.
        blocked_head = self.make_sequence(8, token_base=30)
        fitting_follower = self.make_sequence(2, token_base=60)
        scheduler.add(blocked_head)
        scheduler.add(fitting_follower)

        seqs, is_prefill = scheduler.schedule()

        # Scheduler does Decode rather than bypassing the blocked waiting head.
        self.assertFalse(is_prefill)
        self.assertEqual(seqs, [running])
        self.assertEqual(
            list(scheduler.waiting),
            [blocked_head, fitting_follower],
        )
        self.assertEqual(blocked_head.block_table, [])
        self.assertEqual(fitting_follower.block_table, [])

    def test_running_uses_stable_head_batches_not_round_robin(self):
        scheduler = self.make_scheduler(
            max_num_seqs=2,
            max_num_batched_tokens=16,
        )
        first = self.make_sequence(2, token_base=10, max_tokens=3)
        second = self.make_sequence(2, token_base=30, max_tokens=3)
        third = self.make_sequence(2, token_base=50, max_tokens=3)
        for seq in (first, second, third):
            scheduler.add(seq)

        seqs, is_prefill = scheduler.schedule()
        self.assertEqual(seqs, [first, second])
        scheduler.postprocess(seqs, [101, 201], is_prefill)

        seqs, is_prefill = scheduler.schedule()
        self.assertEqual(seqs, [third])
        scheduler.postprocess(seqs, [301], is_prefill)
        self.assertEqual(list(scheduler.running), [first, second, third])

        # Capacity is two, so the same stable head batch is selected repeatedly.
        seqs, is_prefill = scheduler.schedule()
        self.assertFalse(is_prefill)
        self.assertEqual(seqs, [first, second])
        self.assertEqual(list(scheduler.running), [first, second, third])
        scheduler.postprocess(seqs, [102, 202], is_prefill)

        seqs, is_prefill = scheduler.schedule()
        self.assertFalse(is_prefill)
        self.assertEqual(seqs, [first, second])
        scheduler.postprocess(seqs, [103, 203], is_prefill)
        self.assertEqual(first.status, SequenceStatus.FINISHED)
        self.assertEqual(second.status, SequenceStatus.FINISHED)
        self.assertEqual(list(scheduler.running), [third])

        # The tail request is decoded only after the stable head batch finishes.
        seqs, is_prefill = scheduler.schedule()
        self.assertFalse(is_prefill)
        self.assertEqual(seqs, [third])

    def test_decode_pressure_preempts_running_tail_to_waiting_head(self):
        scheduler = self.make_scheduler(
            max_num_seqs=2,
            num_kvcache_blocks=2,
        )
        current = self.make_sequence(4, token_base=10)
        victim = self.make_sequence(4, token_base=30)

        for seq, sampled_token in ((current, 100), (victim, 200)):
            scheduler.block_manager.allocate(seq, num_cached_blocks=0)
            seq.num_cached_tokens = 4
            seq.append_token(sampled_token)
            seq.status = SequenceStatus.RUNNING
            seq.is_prefill = False
            scheduler.running.append(seq)

        self.assertEqual(len(scheduler.block_manager.free_block_ids), 0)

        seqs, is_prefill = scheduler.schedule()

        self.assertFalse(is_prefill)
        self.assertEqual(seqs, [current])
        self.assertEqual(list(scheduler.running), [current])
        self.assertEqual(list(scheduler.waiting), [victim])
        self.assertEqual(victim.status, SequenceStatus.WAITING)
        self.assertTrue(victim.is_prefill)
        self.assertEqual(victim.block_table, [])
        self.assertEqual(current.status, SequenceStatus.RUNNING)


if __name__ == "__main__":
    unittest.main()
