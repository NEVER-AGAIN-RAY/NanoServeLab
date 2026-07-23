# 阶段 2：Saturated Driver WSL2/CUDA Smoke 验收记录

本文固定验证 Draft [PR #17](https://github.com/NEVER-AGAIN-RAY/NanoServeLab/pull/17) 的 saturated admission driver 在真实 nano-vLLM CUDA 路径上的行为门槛。它证明精确提交能按 `NSL-S2-SAT-v1` 冻结合约完成一次完整运行并写出有效 schema v1 原始 JSON。

它不是：

- 正式 `n=3` benchmark；
- 未来三次正式实验中的任意一次；
- throughput / Queue Time / TTFT / TPOT / E2E / percentile 计算；
- 与阶段 1 baseline 的性能比较；
- 性能提升、性能稳定性或零开销结论。

## 结论

- 验收对象为 clean commit `59d4d9a5bc2c550097e77d24b8f75aff6e335454`（Draft PR #17）。
- WSL2 既有 `.venv` 中全部 47 个单元测试通过；静态预检、CLI `--help`、fresh subprocess import（不加载 torch）与 manifest 指纹均通过。
- 真实 `LLM(..., timing_recorder=...)` 在 Qwen3-0.6B、CUDA Graph、Prefill 与 Decode 路径上完成固定 warmup 与完整 64 请求 saturated measured workload；进程退出码 0，`status=finished`，`error=null`，`cuda_synchronized=true`。
- recorder 证据满足 `max(arrival_ns) <= min(first_scheduled_ns)`，确认全部 64 次 Arrival 完成之后才出现第一次 Scheduler 调度；不依赖 `Sequence.counter` 或连续 ID 假设。
- 独立标准库审计脚本校验 schema、环境、模型、引擎、manifest、warmup、请求顺序、Token 总量、outcome、时间戳单调性、measurement 边界、无 unmapped records 与无派生指标字段。
- 原始 JSON、日志、审计脚本与 SHA-256 已双端保留；本轮不产生正式性能结论。PR #17 的 WSL2/CUDA smoke 门槛已通过，PR 仍保持 Draft，等待证据文档审查后再决定是否合并。

## 身份与时间

| 项目 | 实际值 |
| --- | --- |
| 验证日期 | 2026-07-23（Asia/Shanghai） |
| raw `created_at_utc` | `2026-07-22T16:14:50.289961+00:00` |
| PR | [#17](https://github.com/NEVER-AGAIN-RAY/NanoServeLab/pull/17)，Draft |
| Source commit | `59d4d9a5bc2c550097e77d24b8f75aff6e335454` |
| WSL 验证分支 | `codex/wsl-pr17-smoke` |
| Tracked worktree | 运行前后均为 clean |
| GitHub 同步 | 本轮 WSL 直连 GitHub fetch 已成功，不再需要 bundle |

本次 `run_number=1` 只属于独立 smoke 目录，不是未来正式实验的 run 1。

## 环境

| 项目 | 实际值 |
| --- | --- |
| WSL | Ubuntu 24.04.4，kernel `6.18.33.2-microsoft-standard-WSL2` |
| Python | 3.12.3 |
| PyTorch | 2.4.0+cu124 |
| CUDA build | 12.4 |
| GPU | NVIDIA GeForce RTX 4060 Laptop GPU，8188 MiB |
| Windows driver | 555.97 |
| Transformers | 5.5.0 |
| Triton | 3.0.0 |
| xxhash | 3.8.1 |
| 模型 | `Qwen/Qwen3-0.6B` |
| 模型 revision | `c1899de289a04d12100db370d81485cdf75e47ca` |
| `model.safetensors` size | 1,503,300,328 Bytes |
| `model.safetensors` SHA-256 | `f47f71177f32bcd101b7573ec9171e6a57f4f4d31148d38e382306f42996874b` |

## 预检

- GPU 启动前约 1511 MiB、61°C、P4；`nvidia-smi` 没有列出 compute process。
- 磁盘剩余约 947 GiB。
- 完整 `unittest discover`：`Ran 47 tests in 0.344s / OK`。
- `py_compile` 通过；CLI `--help` 通过。
- fresh subprocess import `research.stage2_saturated_driver` 后未加载 torch。
- manifest SHA-256：`aa1d4e345e0e9f599bd43093bd5b9214476aa3145ee910cc9137d0b62754767d`。
- `git diff --check` 通过；Git clean、精确 HEAD 已核对。

## 运行方法

- 每个进程构造一个真实 `LLM`。
- 固定 warmup prompt：`"Benchmark: "`；sampling：`temperature=0.6`、`max_tokens=64`、`ignore_eos=true`。
- measured workload 使用完整 `NSL-S2-SAT-v1`；64 次 `add_request` 全部完成后才进入 `step`。
- 输出目录：`results/raw/stage2/saturated/smoke-pr17-59d4d9a/`。
- 完整 stdout/stderr 保存为 `driver-smoke.log`。

## 结果

| 项目 | 实际值 |
| --- | --- |
| 进程退出码 | 0 |
| `status` | `finished` |
| `error` | `null` |
| `run_id` | `4916a09e-a352-47f6-8e96-9264092c4be5` |
| raw 文件 | `saturated-20260722T161450.289961Z-run1.json` |
| raw size | 29,126 Bytes |
| raw SHA-256 | `0a61e1defd4532eaef37f0eca8b48df235d364fc5fc5d87bddfc647614f81e90` |
| warmup timing records | 1 |
| warmup `seq_id` | 4 |
| warmup prompt / output tokens | 3 / 64 |
| measured requests | 64 |
| measured `seq_id` | 5..68，全部唯一 |
| short / long | 48 / 16 |
| Prompt Token 总数 | 22,528 |
| requested Output Token 总数 | 5,632 |
| actual Output Token 总数 | 5,632 |
| outcome | 全部 `finished` |
| request `error` | 全部 `null` |
| `unmapped_timing_records` | 0 |
| `measurement_started_ns` | 15213158479695 |
| `measurement_ended_ns` | 15224099916744 |
| `cuda_synchronized` | `true` |

## Saturated admission 的独立证明

| 项目 | 实际值 |
| --- | --- |
| max measured `arrival_ns` | 15213159684880 |
| min measured `first_scheduled_ns` | 15213160050903 |

因为 `max(arrival_ns) <= min(first_scheduled_ns)`，recorder 证据确认全部 64 请求完成 Arrival 后才发生第一次 Scheduler 调度。该证明不依赖 `Sequence.counter` 或连续 ID 假设。

## 验证方式

- 使用只依赖 Python 标准库的独立 `validate_smoke.py` 审计 JSON：schema、提交、环境、模型、引擎、manifest、warmup、64 请求顺序、Token 总量、outcome、时间戳单调性、measurement 边界、CUDA 同步、无 unmapped records、无派生指标字段。
- WSL 没有 `rg`；日志异常扫描改用 `grep -Eni`。
- driver 日志未匹配 `Traceback`、`ERROR`、`WARNING`、`OOM`、`Dynamo`、`cache_size_limit`、`NaN` 或 `Inf`。
- 运行后 GPU 约 1310 MiB、63°C、P4，没有 compute process。
- Git 运行后仍 clean，HEAD 未变化。

## 证据存储

- WSL：`/home/lei/NanoServeLab/results/raw/stage2/saturated/smoke-pr17-59d4d9a/`
- Mac Git 忽略备份：`results/raw/stage2/saturated/smoke-pr17-59d4d9a/`
- Mac 已用 `SHA256SUMS` 逐文件复验通过。
- `SHA256SUMS` 自身 SHA-256：`f7f5bc1b0415514cf0e3925bc4e359f1bfd918e17d56bca7782f388459f83655`

逐文件 SHA-256：

| 文件 | SHA-256 |
| --- | --- |
| `contract-validation.log` | `788f9391acb74702c652ed864b0593e9e25e5f94c0f8b4a220f5b4c5aa86901c` |
| `driver-log-anomaly-scan.log` | `bcf31ee20bf491c88c2c0bf3edf8fd4dab7e1105b90032c6725b25e99a2c96b9` |
| `driver-smoke.log` | `7c26ce5ab83af9a478dfed45fecbeaeb47928562d9577a213b8d0f94bf736e50` |
| raw JSON | `0a61e1defd4532eaef37f0eca8b48df235d364fc5fc5d87bddfc647614f81e90` |
| `static-preflight.log` | `8a17a846dd81165f6679ec7bac71af59915540a7567b9451091bec24410b99d9` |
| `unit-tests.log` | `6eb42b864f26956ad8dbe21dcfcc557d653863b7843d1128517d16465be03aea` |
| `validate_smoke.py` | `e2222c38a42a80aa100e21ebe69151fb7049fc31e0cf94bc9ec8d93775ed05b2` |

审计脚本与原始日志只存在于 Git 忽略的证据目录，不属于运行时代码，也不得提交进仓库。

## 限制与结论

- 这是一次行为 / CUDA smoke，不是 `n=3` 正式实验，也不计入未来三次正式实验。
- 不计算 throughput、Queue Time、TTFT、TPOT、E2E 或 percentile。
- 不与阶段 1 baseline 比较。
- 不声称性能提升、性能稳定性或零开销。
- smoke 只证明当前精确提交在该 WSL2/CUDA 环境中能够按冻结合约完整运行并生成有效原始 JSON。

下一门槛是审查并合并 Draft PR #17；合并后才启动三个全新 Python 进程的正式 `NSL-S2-SAT-v1` 实验。aggregation 仍推迟到三份正式 raw JSON 验证之后。
