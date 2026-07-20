"""推理引擎的集中配置定义。

参数可分为四组：
- 批处理预算：``max_num_batched_tokens``、``max_num_seqs``。
- 上下文限制：``max_model_len``，最终不会超过模型自身的位置上限。
- GPU/并行：``gpu_memory_utilization``、``tensor_parallel_size``、
  ``enforce_eager``。
- KV Cache：``kvcache_block_size``、``num_kvcache_blocks``。

运行期字段：
- ``hf_config`` 由 ``__post_init__`` 从模型目录加载。
- ``num_kvcache_blocks`` 初始为 -1，随后由 ModelRunner 根据真实显存写回。
- ``eos`` 初始为 -1，随后由 LLMEngine 从 tokenizer 写回。

因此 Config 既包含用户配置，也承载初始化阶段产生的运行时信息；阅读组件
构造顺序时要特别留意后两项何时被赋值。
"""

import os
from dataclasses import dataclass
from transformers import AutoConfig


@dataclass(slots=True)
class Config:
    model: str
    max_num_batched_tokens: int = 16384
    max_num_seqs: int = 512
    max_model_len: int = 4096
    gpu_memory_utilization: float = 0.9
    tensor_parallel_size: int = 1
    enforce_eager: bool = False
    hf_config: AutoConfig | None = None
    eos: int = -1
    kvcache_block_size: int = 256
    num_kvcache_blocks: int = -1

    def __post_init__(self):
        assert os.path.isdir(self.model)
        assert self.kvcache_block_size % 256 == 0
        assert 1 <= self.tensor_parallel_size <= 8
        self.hf_config = AutoConfig.from_pretrained(self.model)
        self.max_model_len = min(self.max_model_len, self.hf_config.max_position_embeddings)
