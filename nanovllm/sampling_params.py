"""单个请求的生成采样参数。

重要参数：
- ``temperature``：控制概率分布平滑程度；当前实现不允许 0 温度贪心采样。
- ``max_tokens``：最多生成的 Completion Token 数，由 Scheduler 判断结束。
- ``ignore_eos``：为 True 时忽略 EOS，只按 max_tokens 停止。

这些参数在创建 Sequence 时复制到请求运行时状态，随后由 ModelRunner 的
Sampler 和 Scheduler.postprocess 分别使用。
"""

from dataclasses import dataclass


@dataclass(slots=True)
class SamplingParams:
    temperature: float = 1.0
    max_tokens: int = 64
    ignore_eos: bool = False

    def __post_init__(self):
        assert self.temperature > 1e-10, "greedy sampling is not permitted"
