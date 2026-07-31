# 阶段 3：首轮调度结果机制复盘

本文只读复盘 `prompt-length-20260727-a` 已封存的六份正式 raw，回答为什么 `prompt-length-v1` 的 Short Queue Time 显著下降，但 TTFT、TPOT、E2E 和吞吐反而退化，以及现有证据能否解释 Candidate run 1 与 run 2/3 的分化。

本复盘没有运行模型、CUDA、Scheduler 或新 benchmark，没有修改 raw/aggregate，也不产生替代结果。

## 先给结论

1. **Queue Time 改善是真实的，但只代表更早被 Scheduler 首次选中。** `prompt-length-v1` 把 48 个 short 请求全部放进第一 Prefill 波次，因此它们在约 1 ms 内获得 `first_scheduled`。
2. **`first_scheduled` 发生在 GPU Prefill 之前。** 第一波次的模型执行时间进入 TTFT 而不进入 Queue Time。Candidate 的第一波次为 58 请求、16,384 Token；三次从首次调度到首 Token 分别约为 997、1,890、2,294 ms。
3. **因此“Short Queue 几乎归零”和“Short TTFT 变差”并不矛盾。** 排序策略把等待时间移出了 Queue 区间，却没有保证 Prefill 和后续 Decode 更快。
4. **Prefix Cache 不是本组差异来源。** 16 个 long Prompt 的 64 个完整 256-Token Block 全部唯一，short Prompt 不满一个 Block；不存在共享完整 Prefix Block。
5. **现有 raw 能定位退化发生在 Prefill 和后续执行两段，但不能确定根因。** Candidate 三次的 workload、排序和批形状完全相同，仍出现明显分化；raw 没有逐 step 执行时间、KV/preemption 事件或 GPU 时钟、功耗、温度与利用率。

因此，下一步不是添加 Priority/Aging，而是预先声明一个最小诊断 trace，补足因果定位所需的观察量。

## 事件边界

每个请求现有四个时间戳可拆成：

```text
arrival
  ├─ Queue Time ──────────────► first_scheduled
  ├─ TTFT ─────────────────────────────────────► first_output
  └─ E2E ─────────────────────────────────────────────────────► completed

first_scheduled ─► first_output = 首次被选中后到首 Token
first_output ─► completed = 首 Token 后到完成
```

[`Scheduler.schedule()`](../../nanovllm/engine/scheduler.py) 在返回批次前记录 `first_scheduled`；随后 [`LLMEngine.step()`](../../nanovllm/engine/llm_engine.py) 才调用 `model_runner.run()`。因此 Queue Time 不包含该批次的模型执行时间。

Prefill 只要成功选中请求就立即返回纯 Prefill 批次，waiting 仍有请求时不会运行 Decode。Prefill 在 [`ModelRunner.run_model()`](../../nanovllm/engine/model_runner.py) 中走 eager model path，并通过 varlen Flash Attention 使用 sequence-count、每个序列长度和累计长度形状。Decode 才使用按 batch size 捕获的 CUDA Graph。

## 固定批形状

| Policy | 第一 Prefill 波次 | Prompt Token | 第二波次 | Prompt Token |
| --- | --- | ---: | --- | ---: |
| FCFS | 45 请求：34 short / 11 long | 15,616 | 19 请求：14 short / 5 long | 6,912 |
| Prompt length | 58 请求：48 short / 10 long | 16,384 | 6 请求：0 short / 6 long | 6,144 |

两个 Policy 总 Prompt 都是 22,528 Token。Candidate 的第一波次正好占满 `max_num_batched_tokens=16,384`；FCFS 因下一个 long 请求无法放入剩余预算，在 15,616 Token 停止。

这说明策略实际改变的不只是“谁先”，还改变了每个 Prefill step 的 sequence-count 和 per-sequence length 组合。它仍是合约允许的单变量行为后果，但不能用总 Token 相同假定单步成本相同。

## 逐 run 阶段拆分

以下时间均从现有 raw 重算，单位 ms。“波次耗时”是该波 `first_output` 起点减该波 `first_scheduled` 起点；“全部 Prefill 后到最后完成”从第二波首 Token 到本 run 最后完成。

| Policy / run | Window | 第一波 | 第二波 | 全部 Prefill 后到最后完成 |
| --- | ---: | ---: | ---: | ---: |
| FCFS / 1 | 7,575.914 | 1,043.465 | 410.337 | 6,120.295 |
| Candidate / 1 | 7,490.133 | 996.587 | 371.716 | 6,119.751 |
| Candidate / 2 | 10,070.099 | 1,889.771 | 893.762 | 7,284.504 |
| FCFS / 2 | 7,566.214 | 978.379 | 416.939 | 6,168.887 |
| FCFS / 3 | 7,534.132 | 967.462 | 409.290 | 6,155.269 |
| Candidate / 3 | 9,966.534 | 2,294.203 | 616.188 | 7,053.984 |

FCFS 三次各段相对稳定。Candidate run 1 的三段与 FCFS 接近；Candidate run 2/3 同时在第一 Prefill、第二 Prefill 和全部 Prefill 后阶段变慢。退化不是只来自 long 请求在第二波等待。

### Short 请求均值

| Policy / run | Queue | 首次调度→首 Token | 首 Token→完成 |
| --- | ---: | ---: | ---: |
| FCFS / 1 | 305.165 | 859.018 | 1,180.820 |
| Candidate / 1 | 0.787 | 996.628 | 1,262.645 |
| Candidate / 2 | 0.772 | 1,889.802 | 1,952.128 |
| FCFS / 2 | 286.200 | 814.871 | 1,186.356 |
| FCFS / 3 | 283.054 | 804.918 | 1,173.497 |
| Candidate / 3 | 0.872 | 2,294.235 | 1,633.464 |

Candidate 的所有 short 都在第一波，因此 Queue 约 1 ms；它们的 TTFT 几乎完全由第一 Prefill 波次耗时决定。Queue Time 的优化没有消失，而是被更大的“首次调度后到首 Token”成本超过。

### Long 请求均值

| Policy / run | Queue | 首次调度→首 Token | 首 Token→完成 |
| --- | ---: | ---: | ---: |
| FCFS / 1 | 326.920 | 845.829 | 6,402.529 |
| Candidate / 1 | 374.784 | 762.499 | 6,352.175 |
| Candidate / 2 | 709.695 | 1,516.487 | 7,843.198 |
| FCFS / 2 | 306.603 | 803.173 | 6,455.759 |
| FCFS / 3 | 303.231 | 793.290 | 6,436.854 |
| Candidate / 3 | 861.444 | 1,665.172 | 7,439.168 |

Candidate 把 6 个 long 请求推到第二波，直接增加其 Queue；run 2/3 的 post-scheduling 和 completion 阶段又同时变慢，所以 long TTFT/E2E 尾部风险成立。

## Prefix Cache 排除

冻结 workload 使用独立随机 Token：

- 48 个 short Prompt 各 128 Token，不形成完整 256-Token Prefix Block；
- 16 个 long Prompt 各 4 个完整 Block，共 64 Block；
- 64 个完整 Block 全部唯一，重复数为 0；
- Prefix Cache 从第一个完整 Block 就无法匹配，因此没有共享命中。

这比仅观察 Policy 名称更强：`prompt-length-v1` 的结果不是 Prefix Cache 命中差异造成的，也不能借 Prefix Cache 解释 Candidate run 之间的波动。

## Warmup 能说明什么

现有 warmup 是单个 3-Token Prompt、64 输出 Token。Warmup 首 Token 后阶段在六个进程中为约 700–806 ms，没有出现 Candidate run 2/3 那样的 measured 分化。

但该 warmup 与正式第一 Prefill 波的 15,616/16,384 Token、45/58 sequences 形状完全不同。它证明基本模型和 Decode 路径可用，不能证明大型 varlen Prefill 形状已经预热，也不能排除 shape-specific JIT、kernel、GPU power/clock 或主机调度影响。

## 现有证据能回答到哪里

可以确认：

- Policy 的两波 Prefill 身份和 Token/类别组成；
- Queue 改善来自 short 全部进入第一波；
- TTFT 退化主要落在首次调度后到首 Token；
- Candidate run 2/3 在 Prefill 之后仍有额外慢化；
- 相同 Policy 三次的 workload、批形状、输出 Token 和源码身份一致；
- Prefix Cache 没有混入。

不能确认：

- 每个 Decode step 的模型执行时间及其分布；
- 是否发生 KV 压力、抢占或 recovery，以及具体 step；
- Prefill/Decode 的 CUDA kernel、JIT/autotuning 是否变化；
- GPU 温度、时钟、功耗、利用率或 Windows/WSL 主机干扰；
- Candidate run 1 与 run 2/3 分化的单一根因。

不能把“可能是温度”“可能是 CUDA Graph”“可能是 JIT”中的任何一项写成已证实原因。

## 最小诊断 trace 应记录什么

新诊断实验必须使用新 ID，并与本次正式结果分离；不得替换或补写 `prompt-length-20260727-a`。

每个 Scheduler step 至少需要：

- step ordinal、Prefill/Decode 模式；
- Scheduler 选择前后的 waiting/running 数；
- scheduled sequence 数、Prompt class 数和 scheduled Token 总数；
- host-side step start/end，以及 `model_runner.call()` 前后时间；
- Prefix Cache 命中 Block、KV free/used Block 和 preemption 数；
- Decode 实际 batch size 与选择的 CUDA Graph bucket；
- 可选低频外部 GPU temperature / clock / power / utilization 采样。

先用 CPU/fake-clock 测试固定 trace 的只读性、不可变性和 recorder-off 等价；再做一组不计入性能结论的 WSL diagnostic smoke，确认 trace 开销和事件语义。只有这些门槛通过，才决定是否预声明新的重复诊断实验。

## 证据封存

只读机制分析保存在 Mac Git 忽略目录：

```text
results/raw/stage3/analysis/prompt-length-20260727-a/
  mechanism-analysis.json
  SHA256SUMS
```

`mechanism-analysis.json` 为 18,786 Bytes，SHA-256 为 `f04c11296161874d0ca739452152ee7b12300a74dd9269e3b0b60fe87dbfd54b`。`SHA256SUMS` 自身 SHA-256：

```text
e86198623c779ea6ef43e39be6557ea065299551095ae957b79170a09320c999
```

机制分析前后，正式 raw 的 14 项清单和正式 aggregate 的 6 项清单均保持通过。

第一次复验这两个旧清单时从仓库根目录执行，而清单条目相对于各自证据目录，因此只读命令报告文件无法读取。随后分别从 scheduling 与 aggregation 证据目录纠正执行，14 项和 6 项全部为 `OK`，清单自身哈希仍与正式结果记录一致。该命令错误没有修改任何证据。

## 对项目方向的意义

本轮已经完成一次独立研究闭环，并得到有解释价值的负结果。最重要的下一步不是包装创新性，而是把“排序事件”和“GPU 实际执行”之间的边界理解清楚。

在最小诊断 trace 和所有者复盘完成前：

- 不实现 Priority、Aging 或 Prefix Cache 感知；
- 不更换 workload 来寻找更好看的结果；
- 不补跑或删除正式 Candidate 样本；
- 不把当前机制假设写成因果结论。
