# 阶段 3：最小诊断 Trace 合约

本文冻结第一轮调度负结果之后的最小诊断观察面。目标不是继续寻找更好的
Policy 数字，而是回答 `prompt-length-v1` 在相同 workload、批形状和源码身份下，
为什么 run 1 与 run 2/3 出现明显分化。

- Trace 合约 ID：`NSL-S3-DIAG-TRACE-v1`
- Trace schema：`nanovllm.scheduler-step-trace.v1`
- 后续诊断实验合约 ID：`NSL-S3-DIAG-v1`
- 冻结 workload：`NSL-S2-SAT-v1`
- 对照 Policy：`fcfs-v1`
- Candidate Policy：`prompt-length-v1`

本合约不修改 `NSL-S3-SCHED-v1`、正式 comparison group
`prompt-length-20260727-a`、六份正式 raw 或正式 aggregate。任何带 trace 的运行都是
新的诊断证据，不得替换、补写或混入第一轮正式结果。

## 要回答的问题

Trace 只服务以下五个问题：

1. 两个 Policy 以及同一 Policy 的不同 run，逐 step 的模式、请求数和 Token 数是否
   确实一致？
2. Candidate run 2/3 的额外时间集中在哪些 Prefill 或 Decode step，落在
   schedule、model runner call 还是 postprocess 区间？
3. 慢化前后是否出现 KV Block 压力、抢占、恢复或 Prefix Cache 命中差异？
4. Decode 的实际 batch size、eager/CUDA Graph 路径和 Graph bucket 是否一致？
5. 慢 step 是否与独立采集的 GPU temperature、clock、power 或 utilization 同时变化？

即使观察到相关性，本 trace 也不能单独证明某个 CUDA kernel、JIT/autotuning、温度、
Windows/WSL 调度或硬件状态是根因。未被字段直接观察的机制不得写成已证实原因。

## 事件边界

每个 `LLMEngine.step()` 使用同一个单调时钟，固定以下边界：

```text
step_start
  -> schedule_start -> schedule_end
  -> runner_call_start -> runner_call_end
  -> postprocess_start -> postprocess_end
  -> step_end
```

- 时间戳使用 `perf_counter_ns()` 语义，只比较同一进程内的差值。
- `runner_call_start -> runner_call_end` 是 host 观察到的完整 call wall time；它包含输入
  准备、模型执行、采样和返回 CPU 所需同步，但不是 CUDA kernel 专属时间。
- Trace 不得为了测时额外调用 `torch.cuda.synchronize()`；诊断运行仍沿用 driver 既有的
  measurement 双边界同步。
- schema 保存原始整数纳秒，派生毫秒只在离线分析生成。

## 每 step 必需字段

每条不可变 step record 至少包含：

### 身份与模式

- `trace_contract`、`trace_schema_version`；
- `step_ordinal`，从 measured workload 的 1 开始且严格连续；
- `mode`：`prefill` 或 `decode`；
- `scheduling_policy`；
- `scheduled_seq_ids`，保持 Scheduler 返回顺序。

### 分段时间戳

- `step_start_ns`；
- `schedule_start_ns`、`schedule_end_ns`；
- `runner_call_start_ns`、`runner_call_end_ns`；
- `postprocess_start_ns`、`postprocess_end_ns`；
- `step_end_ns`。

所有字段必须非负并满足上述单调顺序。缺失或倒序使该 run 的 trace 无效，不允许静默
删除坏 record。

### 队列、批形状与请求进度

- schedule 前、schedule 后和 postprocess 后的 `waiting_count`、`running_count`；
- `scheduled_sequence_count` 与 `scheduled_token_count`；
- 每个 scheduled sequence 的 `seq_id`、`num_prompt_tokens`、
  `num_completion_tokens_before`、`num_cached_tokens_before_runner`、
  `num_scheduled_tokens` 与 `block_count_before_runner`；
- Prefill 的 `max_query_tokens`、`max_context_tokens`；
- Decode 的实际 `batch_size`。

核心 Trace 不写 `short` / `long` 标签。类别必须由冻结 workload manifest 按
`request_index -> seq_id` 映射离线派生，避免引擎依赖实验专用分类。

### KV、Prefix Cache 与抢占

- schedule 前、schedule 后和 postprocess 后的 `free_block_count` 与
  `used_block_count`；
- 本 step 的 `preemption_count` 与按发生顺序保存的 `preempted_seq_ids`；
- 对 fresh Prefill allocation 记录 `prefix_cache_hit_blocks`；recovery 请求另以
  `is_recovery=true` 标识，不把其既有 cached blocks 冒充新 Prefix Cache 命中；
- record 必须能验证 `free_block_count + used_block_count` 在同一 run 内恒定。

抢占事件只观察已经发生的 `Scheduler.preempt()` 调用，不改变 victim 选择、回队位置或
Block 释放顺序。

### Model Runner 路径

- `execution_path`：`prefill_eager`、`decode_eager` 或 `decode_cuda_graph`；
- Decode 时记录实际 `cuda_graph_bucket`；eager 路径为 `null`；
- `enforce_eager` 与实际路径必须一致；
- 记录 runner 收到的 sequence count 和 input Token count，用于与 Scheduler record
  交叉校验。

`cuda_graph_bucket` 必须来自 `ModelRunner.run_model()` 实际选择，不能由离线代码根据
batch size 重新猜测。

## Artifact 与写入边界

每个诊断 run 独立保存：

```text
run.raw.json
run.trace.jsonl
run.driver.log
```

- `run.raw.json` 使用新的诊断实验身份，并引用 trace 文件名、字节数和 SHA-256；
- `run.trace.jsonl` 第一条是 run identity header，后续每行一个 step record；
- trace 在 measurement 期间只保存在内存，driver 完成 CUDA measurement 结束同步后才
  序列化，避免文件 I/O 混入被观察窗口；
- writer 必须先完成有限 JSON 与身份校验，再独占创建，拒绝覆盖普通文件、符号链接和
  并发写入；
- 失败 run 尽量保留已经完成的 record、失败阶段和错误，但不得伪造缺失 step；
- trace、raw 与 log 一起进入新的 `SHA256SUMS`，并按既有规则保存 WSL 原件和 Mac 备份。

`NSL-S2-SAT-v1` 的 64 请求单次 trace 大小上限为 10 MiB。超过上限时停止进入 WSL
重复诊断实验，先减少冗余字段或改用等价紧凑表示；不得通过丢 step、抽样 step 或删除
慢 step 达标。

## 外部 GPU Telemetry sidecar

GPU temperature、SM/memory clock、power、utilization 和显存占用由独立低频进程采集，
不在 Scheduler 或 ModelRunner 内调用 `nvidia-smi`：

- 目标采样间隔为 200 ms，保存 sidecar 自己的单调时间和 UTC 时间；
- 保存实际采样间隔、命令错误、缺样和进程退出状态；
- telemetry 文件单独哈希，并通过 run 的 UTC/measurement 边界离线对齐；
- telemetry 缺失不使核心 trace schema 伪造 `null` 样本，但使 GPU 状态问题保持未回答；
- 不把低频相关性写成 kernel 级因果证明。

## 实现前 CPU / fake-clock 门槛

第一实现切片只实现 recorder、事件接线和测试，不运行模型或 CUDA。必须通过：

1. recorder 为 `None` 时不调用 trace clock、不采集 snapshot、不改变 Scheduler/runner
   输入、输出、队列顺序、Token 或 KV 状态；
2. fake clock 固定所有时间戳调用次数、顺序和单调验证；
3. 返回的 record 与 snapshots 是不可变历史值，不暴露内部可变容器；
4. Prefill、Decode、Chunked Prefill、Prefix Cache hit、KV pressure/preemption、完成释放
   和 CUDA Graph bucket 选择均有定向测试；
5. trace 开启和关闭时，同一确定性生命周期的输出 Token、调度顺序、抢占顺序及最终
   Block 释放完全一致；
6. malformed、重复 step、缺 step、非法模式、倒序时间和非有限 JSON 被显式拒绝。

不得为了测试方便在 Config 增加模糊布尔开关。观察对象使用显式 keyword-only 可选依赖，
默认 `None`；现有调用方保持兼容。

## WSL diagnostic smoke 与开销门槛

CPU 门槛合并后，先运行不计入性能结论的 `NSL-S3-DIAG-SMOKE-v1`：

- `fcfs-v1` 与 `prompt-length-v1` 各一个全新 trace-on 进程，验证真实 Prefill/Decode、
  Graph bucket、KV 计数、step 连续性、raw/trace 映射和哈希；
- 另用固定小型 smoke workload 做 trace off/on 成对检查，各 3 个全新进程，顺序交错并
  预声明；
- on/off 的请求、输出 Token、Policy、模型、配置和 CUDA 边界必须完全一致；
- trace-on 的 measurement window 中位数相对配对 trace-off 增幅不得超过 5%；任何 record
  丢失、输出差异、计数不变量失败或超过 10 MiB 都直接阻止正式诊断实验。

`5%` 是“是否需要先优化观察层”的工程门槛，不是 trace 精确开销估计，也不允许据此
声称零开销。若 smoke 噪声无法稳定判断，则增加专门的开销验证重复次数，不放宽门槛或
挑选有利样本。

## 后续重复诊断实验身份

只有 CPU 门槛和 WSL smoke 均通过，才允许执行 `NSL-S3-DIAG-v1`：

- 仍使用 `NSL-S2-SAT-v1`、相同模型/版本/engine 固定项；
- 两个 Policy 都开启同版本 trace 与同一 telemetry sidecar；
- 每个 Policy 至少 3 个全新进程，固定交错顺序并在运行前创建新的 comparison group；
- 原有正式六 run 永不进入该诊断组；
- 先检查 step/shape/KV/路径身份，再比较分段时间与 telemetry；
- 诊断结果只用于定位下一实验或实现问题，不升级为通用性能结论。

具体 comparison group、运行日期、固定顺序和证据目录必须在 WSL 运行前另行写入 handoff；
本合约不提前伪造尚未发生的运行身份。

## 明确不做

本轮及紧随其后的 trace 实现不：

- 修改 FCFS 或 `prompt-length-v1` 排序；
- 修改 Prefill/Decode、KV 分配、抢占、CUDA Graph 或采样语义；
- 实现 Priority、Aging 或 Prefix Cache 感知策略；
- 改换 workload、模型参数或正式结果；
- 在 host wall time 上冒充 CUDA kernel duration；
- 因诊断数据不好看而重跑、删除或替换样本。
