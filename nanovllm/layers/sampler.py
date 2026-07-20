"""根据模型 logits 为每个 Sequence 采样下一个 Token。

``Sampler.forward`` 先用各请求的 ``temperature`` 缩放 logits，再计算
softmax 概率，并使用指数噪声形式的 Gumbel-Max/指数竞赛采样得到 Token ID。
该函数由 ``torch.compile`` 编译，输入批次大小应与 Scheduler 返回的 Sequence
数量一致；当前实现不包含 top-k、top-p 或贪心采样。
"""

import torch
from torch import nn


class Sampler(nn.Module):

    @torch.compile
    def forward(self, logits: torch.Tensor, temperatures: torch.Tensor):
        logits = logits.float().div_(temperatures.unsqueeze(dim=1))
        probs = torch.softmax(logits, dim=-1)
        sample_tokens = probs.div_(torch.empty_like(probs).exponential_(1).clamp_min_(1e-10)).argmax(dim=-1)
        return sample_tokens
