# 阶段 3 调度对照 raw schema 与 driver

本文固定 `NSL-S3-SCHED-v1` 的单次运行入口、raw schema v2 和失败/防覆盖行为。它只定义原始事实记录，不计算 TTFT、TPOT、E2E、吞吐或策略差值；派生指标仍由后续离线聚合完成。

## 复用边界

[`research/stage3_scheduling_driver.py`](../../research/stage3_scheduling_driver.py) 复用已经过 Stage 2 WSL2/CUDA 验证的 saturated admission 核心：

- 同一个 `NSL-S2-SAT-v1` 64 请求 manifest；
- 同一个 warmup；
- 所有 measured `add_request()` 先于第一次 `step()`；
- 同一 recorder 映射、完成态校验和 CUDA 同步边界；
- 同一固定模型、Sampling 与 engine 参数。

Stage 3 外层只增加实验合约、对照组和 Policy 身份。它不修改 Stage 2 raw、aggregator 或冻结 workload，也不在测量循环中实现另一份容易漂移的副本。

## CLI

每个进程必须显式提供 Policy、对照组和策略内 run number：

```bash
python research/stage3_scheduling_driver.py \
  --policy fcfs-v1 \
  --comparison-group prompt-length-YYYYMMDD-a \
  --run-number 1 \
  --output-dir results/raw/stage3/scheduling
```

`--policy` 不设隐式 CLI 默认。合法值来自代码中的版本化支持集合；`--comparison-group` 只允许 1–128 个字母、数字、点、下划线或连字符，且首字符必须是字母或数字；`--run-number` 必须为正整数。

正式六进程顺序仍由阶段 3 合约固定为：

```text
FCFS-1 → Candidate-1 → Candidate-2 → FCFS-2 → FCFS-3 → Candidate-3
```

同一 Policy 的 run number 使用 1、2、3；六份 raw 使用完全相同的 `comparison_group`。

## Schema v2 身份

Stage 3 raw 使用独立 schema v2，至少包含：

```text
schema_version = 2
experiment = NSL-S3-SCHED-v1
experiment_contract = NSL-S3-SCHED-v1
comparison_group
policy.id
policy.definition_version
policy.parameters
policy.runtime_verified
workload.id = NSL-S2-SAT-v1
workload.manifest_sha256
repository.commit
repository.dirty
engine.requested_scheduling_policy
engine.scheduling_policy
```

Policy v1 参数固定为：

| Policy | `parameters` |
| --- | --- |
| `fcfs-v1` | `{}` |
| `prompt-length-v1` | `fresh_request_key=num_prompt_tokens`；`order=ascending`；`stable_ties=arrival_order`；`recovery_prefix=preserved` |

driver 在 warmup 前读取实际 `engine.scheduler.scheduling_policy`。请求 Policy 与实际 Scheduler 不一致、Policy 无法读取、commit 缺失或 tracked worktree 非 clean 时，本次运行直接记为 failed，不开始 warmup 或 measured admission。成功 raw 必须同时满足 `policy.runtime_verified=true` 且 requested/actual Policy 一致。

## 原始事实与失败证据

raw 继续记录 Stage 2 已固定的：

- repository、environment、model、engine；
- workload manifest 与 seed；
- 非 measured warmup timing；
- measurement 单调时钟和 CUDA 同步事实；
- 每个 measured 请求的 index、class、Token 数、outcome 与四个原始时间戳；
- 未映射 timing records；
- status 与结构化 error。

raw 禁止写入 Queue Time、TTFT、TPOT、E2E、吞吐、percentile 或 elapsed 等派生字段。

运行时失败仍保留已经产生的 warmup、映射和请求时间戳。setup 或身份校验失败保留可得的配置和 error，但 `policy.runtime_verified=false`，且不能伪造实际 Scheduler Policy；若 mismatch 检查已经成功读到实际 Policy，则原样记录该值作为失败证据。

## 防覆盖规则

文件名固定为：

```text
scheduling-<UTC>-<comparison_group>-<policy>-run<N>.json
```

JSON 在打开文件前完整序列化并拒绝非有限数；文件以独占创建模式写入。同一路径已存在时立即失败，原文件字节保持不变。正式实验应使用此前不存在或为空的输出目录，不删除、替换或覆盖较差/失败运行。

## 验证边界

Mac CPU 测试可以证明 schema、Policy 一致性检查、Stage 2 生命周期复用、失败证据和防覆盖行为，但不能证明真实 LLM、CUDA Graph 或 GPU 性能。进入正式六次对照前仍必须在同一个 clean commit 上：

1. 在 WSL2 跑完整测试；
2. 对 `fcfs-v1` 和 `prompt-length-v1` 各做一次真实 CUDA smoke；
3. 核对 RTX 4060、模型 revision、权重、manifest、输出目录和 GPU 空闲状态。
