# 阶段 3 调度策略离线对照 Aggregation

本文固定 `NSL-S3-AGG-v1` 如何只读汇总 `NSL-S3-SCHED-v1` 第一组 FCFS 与 `prompt-length-v1` 对照。实现位于 [`research/stage3_scheduling_aggregate.py`](../../research/stage3_scheduling_aggregate.py)。

它不运行模型、CUDA 或 Scheduler，不修改 raw，也不自动扫描目录。所有输入必须由 CLI 显式列出；输出只是可复算的派生证据，不自动生成性能结论。

## 输入矩阵

聚合器只接受恰好六份 schema v2 raw，Policy/run key 必须精确为：

```text
fcfs-v1/run1
prompt-length-v1/run1
prompt-length-v1/run2
fcfs-v1/run2
fcfs-v1/run3
prompt-length-v1/run3
```

输出和审计顺序固定为合约运行顺序：

```text
FCFS-1 → Candidate-1 → Candidate-2 → FCFS-2 → FCFS-3 → Candidate-3
```

输入路径本身可以任意排列，但上述规范顺序中的 `created_at_utc` 必须严格递增且带时区，从而证明实际进程启动顺序，而不是聚合器事后重新排列出一个看似合规的列表。

整组六份 raw 还必须满足：

- `schema_version == 2`；
- `experiment == experiment_contract == "NSL-S3-SCHED-v1"`；
- 同一个合法 `comparison_group`；
- 全局 `run_id` 唯一，每个 Policy 的 run number 精确为 1、2、3；
- `repository.dirty == false`；
- 同一个 commit、Python/依赖/CUDA/GPU、模型 ID/revision、固定 engine 参数和冻结 workload；
- workload ID 为 `NSL-S2-SAT-v1`，manifest SHA-256 为 `aa1d4e345e0e9f599bd43093bd5b9214476aa3145ee910cc9137d0b62754767d`。

比较兼容键排除两个预期自变量字段：

- `engine.requested_scheduling_policy`
- `engine.scheduling_policy`

除此之外整个固定 engine 对象必须深度相等。`repository.branch`、`model.local_path`、raw 文件名和测量时钟绝对值不是兼容键。

## Policy 身份

每份 raw 的 `policy.id`、definition version 和 parameters 必须精确匹配 raw driver 合约：

- `fcfs-v1` / definition v1 / `{}`；
- `prompt-length-v1` / definition v1 / 固定 Prompt 长度升序、到达顺序并列和 recovery-prefix 参数。

`engine.requested_scheduling_policy` 必须等于 `policy.id`。若 raw 状态为 finished，还必须同时满足：

- `policy.runtime_verified == true`；
- `engine.scheduling_policy == policy.id`。

兼容键仍完整的 failed raw 可以保留 `runtime_verified=false` 和缺失/不匹配的实际 Policy；聚合器会保留它，但整组 comparison 标为 invalid，不能产生可交付的策略结论。若失败早到 environment、model、fixed engine 或 workload 兼容键本身缺失，聚合器拒绝整组输入，因为已无法证明六次运行属于同一受控环境；原 failed raw 仍单独保留，不会被删除或覆盖。

## 单 run 有效性

每个正式 finished run 必须：

- 恰好有 64 个 request；
- 64 个 outcome 全部为 finished；
- request index 精确覆盖 0–63，且 index/seq ID 在 run 内无重复；
- 每个 index 的 short/long class、Prompt Token 数和 requested Output Token 数匹配冻结 manifest；
- 64 个 record 都能通过 `derive_request_metrics()` 的时间顺序与 Token 校验；
- 实际 Output Token 总数为 5,632；
- invalid 与 unmapped 均为 0；
- `error == null`；
- `measurement.cuda_synchronized == true`；
- measurement 窗口为正。

任一条件失败时仍保留该 run、outcome 和可用 request 事实，但 `contract_valid=false`，该 run 的吞吐为 null，comparison 标为 invalid。不能用部分完成请求除以完整窗口伪造吞吐。

## 每个 Policy 的输出

每个 Policy 分别输出：

- 三份 source 的 basename、SHA-256、run ID 和 run number；
- comparison validity 与逐条 invalid reason；
- total、finished/failed/cancelled/incomplete/other、valid、invalid、unmapped 计数；
- short、long、other 的完成与 invalid 分组计数；
- all/short/long 的 Queue Time、TTFT、Mean TPOT、E2E；
- 每个指标的 `n`、mean、sample SD、median、min、max、P50、P95、P99；
- 最大 Queue Time、TTFT、E2E 对应的 Policy 内 run、request class 和 request index；
- 每次 run 的窗口、Request/s、Output Token/s；
- 三次吞吐的 mean、sample SD、median、min、max、P50、P95、P99。

延迟与 percentile 继续复用 Stage 2 的 `RequestTimingRecord`、`derive_request_metrics()`、nearest-rank 和 sample SD 实现，不复制另一套公式。

## Candidate − FCFS 差值

所有差值统一为：

```text
absolute = candidate - fcfs
relative_percent = (candidate - fcfs) / fcfs * 100
```

若 FCFS 为 0，则百分比为 null。输出对两种吞吐以及 all/short/long 的四类延迟分别比较 mean、sample SD、median、min、max、P50、P95、P99。

- 吞吐正值通常更好；
- 延迟负值通常更好。

输出显式保存方向说明，避免把负延迟差误解为负优化。

## 描述性警戒线

warning 只用于一致解释，不是显著性检验：

- Candidate 三次 Output Token/s 均值相对 FCFS 小于 `-5%` 时，`throughput_degradation_over_5_percent=true`；
- Candidate 的 short、long 或 other 出现未完成/invalid，或 short/long 的 P95、P99、max TTFT/E2E 相对 FCFS 上升时，`fairness_risk=true`；
- 每个公平性风险以结构化 item 保留 class、metric、statistic 和实际差值，不能只给一个总分。

即使 warning 为 false，只要任一 run contract 无效，`comparison.valid` 仍为 false。`n=3` 不支持仅凭本文件声明统计显著或普遍提升。

## CLI 与输出

```bash
python research/stage3_scheduling_aggregate.py \
  --raw <fcfs-run1.json> \
  --raw <candidate-run1.json> \
  --raw <candidate-run2.json> \
  --raw <fcfs-run2.json> \
  --raw <fcfs-run3.json> \
  --raw <candidate-run3.json> \
  --output <aggregate.json>
```

每个 raw 只读取一次，解析与 SHA-256 使用同一份 bytes；输出不记录依赖机器的绝对源路径。aggregate schema 为 v1，身份为 `NSL-S3-AGG-v1`。writer 在落盘前校验 Stage 3 aggregate 身份，完整序列化有限 JSON，再以独占创建写入；既有文件、符号链接或并发竞争均拒绝覆盖。

## 验证边界

Mac CPU fixture 覆盖了合法六 run、来源规范顺序、Policy/兼容键、冻结请求形状、failed/invalid/unmapped、差值方向、吞吐与公平性警戒、最坏请求、非法 JSON/编码/非有限数、raw 只读、输出独占以及 import/CLI 不加载 torch。

这些测试证明离线计算和证据边界，不证明真实 LLM 或 CUDA 行为。下一门槛仍是在同一个 clean merge commit 上进入 WSL2：

1. 跑完整测试；
2. 对 `fcfs-v1` 与 `prompt-length-v1` 各做一次真实 CUDA smoke；
3. smoke 均通过后才按固定顺序运行正式六进程对照。
