"""Scheduler 最小请求生命周期测试。"""

import unittest
from types import SimpleNamespace

from nanovllm.engine.scheduler import Scheduler
from nanovllm.engine.sequence import Sequence, SequenceStatus
from nanovllm.sampling_params import SamplingParams


class SchedulerLifecycleTest(unittest.TestCase):

    def setUp(self):
        # 使用较小的 Block，便于用少量 Token 观察跨 Block 和缓存进度。
        self.original_block_size = Sequence.block_size
        Sequence.block_size = 4

        # 避免构造会读取真实模型目录的 Config，只提供 Scheduler 所需字段。
        config = SimpleNamespace(
            max_num_seqs=1,
            max_num_batched_tokens=4,
            eos=-1,
            kvcache_block_size=4,
            num_kvcache_blocks=8,
        )
        self.scheduler = Scheduler(config)

        sampling_params = SamplingParams(
            temperature=1.0,
            max_tokens=2,
            ignore_eos=True,
        )
        self.seq = Sequence(
            token_ids=[10, 11, 12, 13, 14, 15],
            sampling_params=sampling_params,
        )
        self.scheduler.add(self.seq)

    def tearDown(self):
        # Sequence.block_size 是类变量，测试结束后恢复以隔离其他测试。
        Sequence.block_size = self.original_block_size

    def test_chunked_prefill_then_decode_until_finished(self):
        # Step 1：首轮预算只能处理前 4 个 Prompt Token。
        seqs, is_prefill = self.scheduler.schedule()

        self.assertTrue(is_prefill)
        self.assertEqual(seqs, [self.seq])
        self.assertEqual(self.seq.num_scheduled_tokens, 4)
        self.assertEqual(self.seq.status, SequenceStatus.WAITING)

        # Prompt 尚未完成，因此当前分块末尾采样出的 90 会被丢弃。
        self.scheduler.postprocess(
            seqs=seqs,
            token_ids=[90],
            is_prefill=is_prefill,
        )

        self.assertEqual(self.seq.num_cached_tokens, 4)
        self.assertEqual(self.seq.num_scheduled_tokens, 0)
        self.assertEqual(self.seq.num_tokens, 6)
        self.assertEqual(self.seq.completion_token_ids, [])
        self.assertEqual(list(self.scheduler.waiting), [self.seq])
        self.assertEqual(list(self.scheduler.running), [])

        # Step 2：处理剩余 2 个 Prompt Token，并进入 RUNNING。
        seqs, is_prefill = self.scheduler.schedule()

        self.assertTrue(is_prefill)
        self.assertEqual(seqs, [self.seq])
        self.assertEqual(self.seq.num_scheduled_tokens, 2)
        self.assertEqual(self.seq.status, SequenceStatus.RUNNING)
        self.assertEqual(list(self.scheduler.waiting), [])
        self.assertEqual(list(self.scheduler.running), [self.seq])

        # 完整 Prompt 末尾采样出的 91 是第一个 Completion Token。
        self.scheduler.postprocess(
            seqs=seqs,
            token_ids=[91],
            is_prefill=is_prefill,
        )

        self.assertEqual(self.seq.num_cached_tokens, 6)
        self.assertEqual(self.seq.num_tokens, 7)
        self.assertEqual(self.seq.completion_token_ids, [91])
        self.assertEqual(
            self.seq.num_tokens,
            self.seq.num_cached_tokens + 1,
        )

        # Step 3：Decode 处理 Token 91，再采样出 Token 92。
        seqs, is_prefill = self.scheduler.schedule()

        self.assertFalse(is_prefill)
        self.assertEqual(seqs, [self.seq])
        self.assertEqual(self.seq.num_scheduled_tokens, 1)

        self.scheduler.postprocess(
            seqs=seqs,
            token_ids=[92],
            is_prefill=is_prefill,
        )

        self.assertEqual(self.seq.completion_token_ids, [91, 92])
        self.assertEqual(self.seq.status, SequenceStatus.FINISHED)
        self.assertTrue(self.scheduler.is_finished())

        # 请求结束后，Sequence 和 BlockManager 都不应继续占用 KV Block。
        self.assertEqual(self.seq.block_table, [])
        self.assertEqual(self.scheduler.block_manager.used_block_ids, set())
        self.assertEqual(
            len(self.scheduler.block_manager.free_block_ids),
            8,
        )


if __name__ == "__main__":
    unittest.main()
