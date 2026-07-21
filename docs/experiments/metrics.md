# 阶段 2：推理延迟指标边界合约

本文件固定 NanoServeLab 阶段 2 的指标语义、生命周期事件和未来实现不变量。它不是当前状态入口，也不代表指标代码或 CUDA 开销已经验证；实时进度仍以 [`docs/project/README.md`](../project/README.md) 为准。

本次源码事件映射核对基线为 `eb12a2ac1ebb35fae9fd76bf8c6ca02e042576fa`。后续实现若移动或改变这些事件，必须同步审阅本合约，不能让文档继续引用已经失效的生命周期语义。

## 目标与范围

阶段 1 只测量完整 synthetic batch 的输出 Token 吞吐，没有 per-request 时间戳。阶段 2 第一切片先回答“时间从哪里开始、在哪里结束”，再实现记录代码和混合 workload，避免把不同层级的延迟混用。

本合约定义：

- Initial Scheduler Queue Time；
- 引擎侧 TTFT（Time To First Token）；
- 引擎侧 Mean TPOT（Time Per Output Token）；
- 引擎侧 E2E（End-to-End Latency）；
- 后续混合 workload 使用的 Request Throughput 与 Output Token Throughput 边界。

本合约暂不定义客户端网络延迟、客户端可见流式 TTFT、逐 Token 抖动、累计抢占等待、公平性公式或调度评分。当前 `LLM.generate()` 是同步接口，只有所有请求完成后才统一返回，因此任何首 Token 指标都必须明确标为“引擎侧”。

## 当前源码事件地图

下表只描述当前源码中已经存在的事实，不等于已经实现时间戳。

| 生命周期事件 | 当前源码位置 | 已确认行为 |
| --- | --- | --- |
| 文本 Tokenize | `nanovllm/engine/llm_engine.py::LLMEngine.add_request` | 字符串 Prompt 先经 tokenizer 编码；Token ID 列表跳过该步骤 |
| 构造请求 | `nanovllm/engine/llm_engine.py::LLMEngine.add_request` | 创建 `Sequence`，初始状态为 `WAITING` |
| 加入等待队列 | `nanovllm/engine/scheduler.py::Scheduler.add` | `Sequence` 追加到 `waiting` 队尾 |
| Prefill 首次/再次调度 | `nanovllm/engine/scheduler.py::Scheduler.schedule` | 从 `waiting` 队首选择请求；Chunked Prefill 可能只调度部分 Prompt，状态仍为 `WAITING` |
| Prompt 完整后进入运行态 | `nanovllm/engine/scheduler.py::Scheduler.schedule` | 已缓存 Token 与本轮 Token 覆盖完整 Prompt 时转为 `RUNNING` |
| Decode 调度 | `nanovllm/engine/scheduler.py::Scheduler.schedule` | 从 `running` 取请求，每轮调度一个 Token；必要时可能抢占请求 |
| GPU 执行与采样 | `nanovllm/engine/model_runner.py::ModelRunner.run` | 模型前向后 Sampling；rank 0 的 CUDA Tensor 经 `.tolist()` 物化为 Host Token ID 再返回引擎 |
| 丢弃不完整 Prefill 的临时采样 | `nanovllm/engine/scheduler.py::Scheduler.postprocess` | 如果 Prefill 后仍未覆盖完整 Prompt，执行 `continue`，不会调用 `append_token()` |
| 提交真实 Completion Token | `nanovllm/engine/scheduler.py::Scheduler.postprocess` → `Sequence.append_token` | 越过上述 `continue` 后才追加 Token；完整 Prompt 末尾的采样是第一个 Completion Token |
| 请求完成 | `nanovllm/engine/scheduler.py::Scheduler.postprocess` | 先追加最后一个 Token，再因 EOS 或 `max_tokens` 转为 `FINISHED` |
| KV Block 释放 | `Scheduler.postprocess` → `BlockManager.deallocate` | 状态转为 `FINISHED` 后释放 Block、清零缓存进度并移出 `running` |
| Step 输出 | `nanovllm/engine/llm_engine.py::LLMEngine.step` | 只返回本轮已经 `FINISHED` 的请求，不返回仍在生成中的首 Token |
| API 返回 | `nanovllm/engine/llm_engine.py::LLMEngine.generate` | 循环到 Scheduler 全空，解码所有完成结果后一次性返回，不提供流式输出 |

当前 `SequenceStatus` 只有 `WAITING`、`RUNNING` 和 `FINISHED`。源码没有 per-request `CANCELLED` 或 `FAILED` 状态，也没有取消 API；未来 schema 可以保留这些 outcome，但实现前不得声称当前引擎已经支持。

## 规范时间事件

所有 duration 事件必须在 rank 0 的同一 Python 进程中使用同一个 monotonic clock。首选原始时钟为可注入的 `time.perf_counter_ns()`，原始值保存为整数纳秒；展示时再换算为毫秒。UTC 只能作为实验创建时间元数据，不能与 monotonic timestamp 相减。

### `arrival_ns`

定义为：`Sequence` 已构造、字符串 Tokenize 已完成，即将调用 `Scheduler.add()` 的时刻。

这个选择把 Arrival 固定在 Scheduler 的引擎准入边界，因此：

- 不包含网络、客户端排队或文本 Tokenize；
- Token ID Prompt 与字符串 Prompt 使用同一调度起点；
- 当前 batch `generate()` 会先逐个加入所有请求再执行第一步，所以较早加入的请求会包含“等待同批后续请求完成准入”的时间；该数值不能冒充真实在线到达队列时间。

### `first_scheduled_ns`

定义为：某个请求第一次出现在 `Scheduler.schedule()` 返回的 `scheduled_seqs` 中、尚未调用 `ModelRunner.run` 的时刻。

这是 write-once 事件。第一次 Chunked Prefill 即算首次调度，即使请求仍保持 `WAITING`；后续 Prefill、Decode 或抢占后重新调度都不能覆盖它。

### `first_output_ns`

定义为：`Scheduler.postprocess()` 首次把一个真实 Completion Token 提交给 `Sequence.append_token()` 的时刻。

必须满足：

- 本轮采样 Token 已从 rank 0 CUDA Tensor 物化为 Host Token ID；
- Chunked Prefill 尚未完成 Prompt 时被丢弃的临时采样不触发该事件；
- 写入前 `num_completion_tokens == 0`，写入后为 1；
- Prefix Cache 命中只会改变到达此事件所需的 Prefill 工作量，不改变事件定义。

这个时间表示 Token 已被引擎 CPU 控制面提交到请求状态，不表示客户端已经收到 Token，也不证明所有无关 CUDA 工作都已全局同步。

### `completed_ns`

定义为：最后一个真实 Completion Token 已追加，并且请求因 EOS 或 `max_tokens` 首次转为 `FINISHED` 的时刻。

规范顺序为：追加最后 Token → 设置 `FINISHED` → 记录完成事件 → 释放 KV Block。完成记录不能依赖仍然存在的 Block Table；KV 释放后必须继续可读。

如果 EOS 触发完成，EOS Token 已经先被追加，因此计入 `output_tokens`。当前 `SamplingParams` 没有校验 `max_tokens > 0`，而 Scheduler 的完成判断发生在 Token 追加之后；指标记录层必须把非正 `max_tokens` 视为 invalid，或由明确的准入校验拒绝，不能生成“零输出成功请求”。本指标切片不顺带重构 SamplingParams 或生成策略。

### 非主指标事件

同步 `generate()` 的最终返回发生在所有请求完成、结果排序并 Decode 之后。若未来需要 API-call latency，应另设 `generate_returned_ns` 或客户端时钟，不能用它替换某个请求的 `first_output_ns` 或 `completed_ns`。

## 指标公式

令：

- `A = arrival_ns`
- `S = first_scheduled_ns`
- `F = first_output_ns`
- `C = completed_ns`
- `N = output_tokens`

成功请求必须满足：

```text
A <= S <= F <= C
```

| 指标 | 公式 | 单位 | 语义 |
| --- | --- | --- | --- |
| Initial Scheduler Queue Time | `(S - A) / 1e6` | ms | 从引擎准入到第一次被 Scheduler 选中 |
| Engine-side TTFT | `(F - A) / 1e6` | ms | 从引擎准入到第一个真实 Completion Token 提交 |
| Engine-side E2E | `(C - A) / 1e6` | ms | 从引擎准入到请求转为完成 |
| Engine-side Mean TPOT | `(C - F) / (N - 1) / 1e6` | ms/Token | 首 Token 之后，相邻输出 Token 间隔的请求内平均值 |

Mean TPOT 的空值规则：

- `N >= 2`：按公式计算；
- `N == 1`：返回 `null`，因为没有首 Token 之后的间隔；
- `N <= 0`：请求记录无效，不能填 0，也不能进入成功请求汇总。

只保存 `F` 和 `C` 可以得到请求级 Mean TPOT，但不能观察单个 Decode 间隔的抖动或最大间隔。逐 Token timestamp 属于未来独立扩展，不能把请求级 Mean TPOT 的 P95 解释成“所有 Token 间隔的 P95”。

## Queue Time 与抢占边界

本阶段 Queue Time 明确指 **Initial Scheduler Queue Time**。请求第一次被调度后，`first_scheduled_ns` 永不覆盖。

当前 Scheduler 可能因 KV Block 不足把 `RUNNING` 请求抢占回 `WAITING`，释放其 Block，并在之后重新 Prefill。由此产生的重新等待会增加 TTFT、TPOT 或 E2E，但不会增加 Initial Queue Time 的单独计数。若研究累计调度等待，应在未来定义成新的 `scheduler_wait_total_ns`，记录每次进入/离开等待态的区间；不得悄悄改变本合约中的 Queue Time 公式。

## Throughput 的测量窗口

阶段 1 的 batch output throughput 定义保持不变。未来混合 workload 需要由 workload driver 显式记录：

- `measurement_started_ns`：warmup 完成、正式到达过程开始前；
- `measurement_ended_ns`：正式到达过程结束且纳入测量的请求均进入终态后。

在固定窗口内：

```text
request_throughput = finished_request_count / window_seconds
output_token_throughput = sum(finished_output_tokens) / window_seconds
```

不能用最早 Arrival 和最晚 Completion 自动缩短窗口，也不能把 warmup、模型加载或失败后重试混入窗口。失败、取消和未完成请求不进入吞吐分子，但其数量必须单独报告，不能静默消失。

## 最小原始记录草案

阶段 2 下一切片可以实现一个只读、write-once 的 per-request 记录。下列是合约草案，不是当前已存在的 API：

```json
{
  "schema_version": 1,
  "run_id": "experiment-run-id",
  "request_id": 0,
  "outcome": "finished",
  "prompt_tokens": 128,
  "output_tokens": 64,
  "clock": "time.perf_counter_ns",
  "timestamps_ns": {
    "arrival": 1000000000,
    "first_scheduled": 1000100000,
    "first_output": 1010000000,
    "completed": 1060000000
  },
  "error": null
}
```

记录规则：

- `(run_id, request_id)` 才是跨进程/跨运行唯一键；当前 `Sequence.seq_id` 只在进程内递增。
- 原始证据是 Token 数、outcome 与 monotonic timestamps。Queue Time、TTFT、TPOT、E2E 应由汇总器重新计算，避免重复字段互相矛盾。
- `arrival` 必须存在于所有已准入请求；从未被调度的请求允许 `first_scheduled` 为 `null`，其他字段也按 outcome 和实际生命周期保持 `null`。
- 当前引擎只能自然产生 `finished`。未来 wrapper 捕获进程/请求错误后才可写 `failed`；实现取消路径后才可写 `cancelled`。
- measurement 截止时仍无终态的请求写为 `incomplete`，不得补写 Completion 或零延迟。
- 时间戳必须 write-once；重复写入应触发测试失败，而不是覆盖历史事件。
- 记录的生命周期必须独立于 `Sequence.block_table`，确保完成释放 KV 后仍能导出。

## Outcome 与聚合规则

延迟汇总只使用同时满足以下条件的成功请求：

- `outcome == "finished"`；
- `output_tokens >= 1`；
- 公式所需 timestamp 齐全并满足单调不变量。

每个实验组必须同时报告：总请求数、finished、failed、cancelled、incomplete 和 invalid 数量。不能为了得到更好延迟而删除慢请求；任何排除都必须按预先固定规则分类并保留原始记录。

对每个非空指标集合报告：

- 样本数 `n`；
- mean、median、min、max；
- `n >= 2` 时报告 sample standard deviation，否则为 `null`；
- P50、P95、P99 使用 nearest-rank：排序后取第 `ceil(p × n)` 个值（从 1 开始）。

当样本很少时，P95/P99 很可能只是最大值，必须同时展示 `n`，不能把它包装成稳定的总体尾延迟。不同源码、模型、硬件、workload、seed、到达分布或指标 schema 不得混为同一统计组。

## 未来 CPU 测试矩阵

下一切片应使用 injected/fake monotonic clock，不使用 `sleep`，并继续使用小型 Scheduler 生命周期场景。

| 测试场景 | 必须固定的不变量 |
| --- | --- |
| 普通 Prefill → Decode → Finish | `A <= S <= F <= C`，四个指标公式可重算 |
| 两轮 Chunked Prefill | 第一轮记录 `S`，临时采样不记录 `F`；Prompt 完整后的真实 Token 才记录 `F` |
| 重复 Schedule | `first_scheduled_ns` 保持第一次值，不被后续 Prefill/Decode 覆盖 |
| 两个及以上输出 Token | Mean TPOT 使用 `(C-F)/(N-1)` |
| 单 Token 输出 | TTFT/E2E 有值，TPOT 为 `null` |
| 非正 `max_tokens` | 准入失败或明确 invalid，不产生伪造成功记录 |
| EOS 完成 | EOS 已计入输出数，完成事件只写一次 |
| Prefix Cache 命中 | 事件顺序不变，命中只影响实际 duration |
| 抢占后重新 Prefill | Initial Queue Time 不重置；E2E 自然包含额外等待 |
| Finish 后释放 KV | 记录保持可读、不可变，不引用已清空的 Block Table |
| failed/cancelled/incomplete | 缺失事件保持 `null`，不进入成功延迟汇总，outcome 计数保留 |
| 重复事件写入 | 明确拒绝或忽略重复写入，但绝不覆盖首次 timestamp |

CPU 测试只能证明记录语义和 Scheduler 行为不变量，不能证明 CUDA 时间准确或 instrumentation 没有性能开销。

## 未来 WSL2 验证门槛

时间记录代码完成后，必须在 WSL2 单独验证：

- 真实 Prefill、Decode、EOS/max_tokens 完成路径的 timestamp 齐全且单调；
- rank 0 Sampling Token 物化与 Host 记录点没有异步边界误判；
- 开启记录前后生成结果、Scheduler 顺序、KV 生命周期和完成数量不变；
- 用相同模型、workload、seed 和独立进程比较 instrumentation on/off，一次只改变记录开关；
- 重要开销比较至少各运行三次，保存全部原始结果后再汇总；
- 记录开销若不可忽略，应如实报告，不能从结果中扣除或隐藏；
- 当前同步 API 仍只能报告引擎侧指标，除非另行实现并验证流式返回路径。

在完成这些验证前，只能声称指标合约和 CPU 语义通过，不能声称真实 CUDA TTFT/TPOT 已验证。

## 实施不变量与下一切片

下一切片应只实现最小 per-request timing record 和 CPU 测试。无论最终选择由 `LLMEngine`、`Scheduler` 回调还是独立 recorder 持有状态，都必须满足：

- 记录层只观察事件，不参与调度排序、抢占、KV 分配或 Prefix Cache 决策；
- 时间源可注入，生产环境默认 monotonic nanosecond clock；
- 首次事件 write-once，完成记录在 KV 释放后仍独立存在；
- 当前无取消/失败状态的事实不通过虚构字段赋值掩盖；
- 不在同一切片中同时实现混合到达 workload、JSONL 框架、可视化或调度策略。
