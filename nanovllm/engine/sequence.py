"""单个生成请求在推理引擎中的运行时状态。

``Sequence`` 不只是 Token 容器，还同时保存调度进度、采样参数和 KV Cache
映射，是 Scheduler、BlockManager 与 ModelRunner 之间共享的核心状态对象。

重要字段：
- ``status``：WAITING、RUNNING 或 FINISHED。
- ``token_ids`` / ``num_tokens``：当前已知的全部 Token 及其数量。
- ``num_prompt_tokens``：固定的 Prompt 边界，用于切分最终输出。
- ``num_cached_tokens``：已经写入 KV Cache 的 Token 数。
- ``num_scheduled_tokens``：本轮将执行的 Token 数。
- ``block_table``：逻辑 KV Block 到物理 Block ID 的映射。
- ``is_prefill``：决定执行模式，也决定多进程序列化时发送完整 Token 还是
  只发送最后一个 Token。

关键不变量：正常 Decode 阶段，新采样 Token 尚未经过模型前向，因此通常有
``num_tokens == num_cached_tokens + 1``。``block_size`` 必须与 Config 和
BlockManager 使用的 KV Block 大小保持一致。
"""

from copy import copy
from enum import Enum, auto
from itertools import count

from nanovllm.sampling_params import SamplingParams


class SequenceStatus(Enum):
    WAITING = auto()
    RUNNING = auto()
    FINISHED = auto()


class Sequence:
    block_size = 256
    counter = count()

    def __init__(self, token_ids: list[int], sampling_params = SamplingParams()):
        self.seq_id = next(Sequence.counter)
        self.status = SequenceStatus.WAITING
        self.token_ids = copy(token_ids)
        self.last_token = token_ids[-1]
        self.num_tokens = len(self.token_ids)
        self.num_prompt_tokens = len(token_ids)
        self.num_cached_tokens = 0
        self.num_scheduled_tokens = 0
        self.is_prefill = True
        self.block_table = []
        self.temperature = sampling_params.temperature
        self.max_tokens = sampling_params.max_tokens
        self.ignore_eos = sampling_params.ignore_eos

    def __len__(self):
        return self.num_tokens

    def __getitem__(self, key):
        return self.token_ids[key]

    @property
    def is_finished(self):
        return self.status == SequenceStatus.FINISHED

    @property
    def num_completion_tokens(self):
        return self.num_tokens - self.num_prompt_tokens

    @property
    def prompt_token_ids(self):
        return self.token_ids[:self.num_prompt_tokens]

    @property
    def completion_token_ids(self):
        return self.token_ids[self.num_prompt_tokens:]

    @property
    def num_blocks(self):
        return (self.num_tokens + self.block_size - 1) // self.block_size

    @property
    def last_block_num_tokens(self):
        return self.num_tokens - (self.num_blocks - 1) * self.block_size

    def block(self, i):
        assert 0 <= i < self.num_blocks
        return self.token_ids[i*self.block_size: (i+1)*self.block_size]

    def append_token(self, token_id: int):
        self.token_ids.append(token_id)
        self.last_token = token_id
        self.num_tokens += 1

    def __getstate__(self):
        last_state = self.last_token if not self.is_prefill else self.token_ids
        return (self.num_tokens, self.num_prompt_tokens, self.num_cached_tokens, self.num_scheduled_tokens, self.block_table, last_state)

    def __setstate__(self, state):
        self.num_tokens, self.num_prompt_tokens, self.num_cached_tokens, self.num_scheduled_tokens, self.block_table, last_state = state
        if isinstance(last_state, list):
            self.token_ids = last_state
            self.last_token = self.token_ids[-1]
        else:
            self.token_ids = []
            self.last_token = last_state
