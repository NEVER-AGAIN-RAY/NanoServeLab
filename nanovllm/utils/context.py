"""一次模型前向所需的 Attention 执行上下文。

ModelRunner 在执行前调用 ``set_context()``，Attention/LM Head 在各层前向中
调用 ``get_context()``，执行结束后再由 ``reset_context()`` 清理。它避免把
大量调度元数据逐层穿过模型 ``forward`` 参数。

Prefill 重点字段：``cu_seqlens_q``、``cu_seqlens_k``、``max_seqlen_q``、
``max_seqlen_k``，用于变长 Flash Attention。

KV Cache 重点字段：
- ``slot_mapping``：本轮各 Token 的 K/V 应写入哪个物理槽位。
- ``block_tables``：各 Sequence 的逻辑 Block 到物理 Block 映射。
- ``context_lens``：Decode 时每个 Sequence 的有效上下文长度。

该上下文是进程内全局可变状态，只描述“当前这一轮”模型执行，不应跨 step
持有或并发复用。
"""

from dataclasses import dataclass
import torch


@dataclass(slots=True)
class Context:
    is_prefill: bool = False
    cu_seqlens_q: torch.Tensor | None = None
    cu_seqlens_k: torch.Tensor | None = None
    max_seqlen_q: int = 0
    max_seqlen_k: int = 0
    slot_mapping: torch.Tensor | None = None
    context_lens: torch.Tensor | None = None
    block_tables: torch.Tensor | None = None

_CONTEXT = Context()

def get_context():
    return _CONTEXT

def set_context(is_prefill, cu_seqlens_q=None, cu_seqlens_k=None, max_seqlen_q=0, max_seqlen_k=0, slot_mapping=None, context_lens=None, block_tables=None):
    global _CONTEXT
    _CONTEXT = Context(is_prefill, cu_seqlens_q, cu_seqlens_k, max_seqlen_q, max_seqlen_k, slot_mapping, context_lens, block_tables)

def reset_context():
    global _CONTEXT
    _CONTEXT = Context()
