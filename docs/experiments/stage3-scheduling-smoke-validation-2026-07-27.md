# 阶段 3：双 Policy WSL2/CUDA Smoke 验收记录

本文固定 `fcfs-v1` 与 `prompt-length-v1` 在真实 nano-vLLM CUDA 路径上的行为门槛。两次 smoke 使用同一个 clean source commit、相同环境和冻结 workload，分别由独立 Python/`LLM` 进程完成。

它不是：

- 正式六进程调度对照中的任意一次；
- `NSL-S3-AGG-v1` 输入；
- throughput、Queue Time、TTFT、TPOT、E2E 或 percentile 比较；
- `prompt-length-v1` 性能提升、性能稳定性或泛化结论。

## 结论

- WSL2 在精确 clean commit `a97ec4dc7970cae1c51d094f1c1276ecb0f987fc` 上通过完整 103 tests。
- RTX 4060 Laptop GPU、PyTorch 2.4.0+cu124、CUDA 12.4、Qwen3-0.6B 固定 revision、模型权重 SHA-256 和冻结 workload manifest 均通过预检。
- `fcfs-v1` 与 `prompt-length-v1` 各由一个独立真实进程完成 tokenizer、模型加载、CUDA Graph、saturated Prefill/Decode、timing recorder 和 schema v2 写出；两次均退出码 0。
- 两份 raw 均为 `status=finished`、`error=null`、`policy.runtime_verified=true`，requested/actual Policy 一致，64/64 请求完成，实际 Output Token 为 5,632，`cuda_synchronized=true`，无 unmapped timing record。
- recorder 时间戳证明两次均在全部 64 个 Arrival 完成后才首次调度。
- `first_scheduled` 时间戳还验证了真实策略差异：FCFS 第一 Prefill 波次为 45 个请求（34 short / 11 long），长度策略第一波次为 58 个请求（48 short / 10 long），与 `max_num_batched_tokens=16384` 下的冻结排序定义一致。
- raw、完整 driver 日志、preflight/tests、独立校验与 SHA-256 清单已在 WSL 和 Mac 的 Git 忽略目录双端保留并逐项复验。

## 身份与范围

| 项目 | 实际值 |
| --- | --- |
| 验证日期 | 2026-07-27（Asia/Shanghai） |
| Experiment contract | `NSL-S3-SCHED-v1` |
| Smoke comparison group | `stage3-smoke-20260727-a` |
| Source commit | `a97ec4dc7970cae1c51d094f1c1276ecb0f987fc` |
| WSL 验证分支 | `codex/wsl-stage3-smoke-20260727` |
| Tracked worktree | 运行前后均为 clean |
| FCFS raw `created_at_utc` | `2026-07-27T13:09:55.723870+00:00` |
| Candidate raw `created_at_utc` | `2026-07-27T13:12:30.946070+00:00` |

两份 raw 的 `run_number=1` 只属于独立 smoke 目录。它们不得重命名、复制或混入未来正式 Policy run 1。

WSL 直连 GitHub fetch 本轮未更新远端引用。Mac 因此从 clean `main` 生成完整 Git bundle；Mac 与 WSL 复验 bundle SHA-256 均为：

```text
226aef5b79db1870ebdfe1337264d0b2dc77bc8ede61c73590646c12d35b2165
```

WSL 只用该 bundle 更新 `origin/main` 并从精确提交创建独立验证分支，没有修改或覆盖阶段 2 历史分支。

## 环境与预检

| 项目 | 实际值 |
| --- | --- |
| WSL | Ubuntu 24.04.4；kernel `6.18.33.2-microsoft-standard-WSL2` |
| Python | 3.12.3 |
| PyTorch | 2.4.0+cu124 |
| CUDA build | 12.4 |
| GPU | NVIDIA GeForce RTX 4060 Laptop GPU；8,188 MiB |
| Windows driver | 555.97 |
| Transformers | 5.5.0 |
| Flash Attention | 2.7.4.post1 |
| Triton | 3.0.0 |
| xxhash | 3.8.1 |
| 模型 | `Qwen/Qwen3-0.6B` |
| 模型 revision | `c1899de289a04d12100db370d81485cdf75e47ca` |
| `model.safetensors` size | 1,503,300,328 Bytes |
| `model.safetensors` SHA-256 | `f47f71177f32bcd101b7573ec9171e6a57f4f4d31148d38e382306f42996874b` |
| Workload manifest SHA-256 | `aa1d4e345e0e9f599bd43093bd5b9214476aa3145ee910cc9137d0b62754767d` |

运行前：

- `nvidia-smi` 没有 compute process；
- 最小 CUDA Tensor 运算与同步成功；
- 模型目录、revision、权重大小和 SHA-256 通过；
- 冻结 workload 重建为 64 个请求，manifest 与预期一致；
- `.venv/bin/python -m unittest discover -s tests -v` 为 `Ran 103 tests / OK`；
- Git HEAD、clean worktree 与 `git diff --check` 通过。

第一次 preflight 命令在模型启动前错误引用了不存在的 `WORKLOAD_MANIFEST_SHA256`；实际公开常量为 `EXPECTED_MANIFEST_SHA256`。纠正后完整门槛通过。该命令错误没有构造 LLM、生成 raw 或修改仓库。

FCFS raw 核心校验通过后，第一次打印 SHA-256 的 shell 命令因缺少闭合引号而在哈希步骤前停止；核心 JSON 校验已经完成，随后独立补跑哈希、GPU 空闲和 Git clean 检查。没有修改或替换 raw。

## 运行结果

| 项目 | `fcfs-v1` | `prompt-length-v1` |
| --- | --- | --- |
| 独立进程退出码 | 0 | 0 |
| `status` / `error` | `finished` / `null` | `finished` / `null` |
| `run_id` | `54755e5e-64d9-4445-94ad-32ad18391afc` | `b8e9ae0a-2e2a-4110-9a30-e517eae84155` |
| requested / actual Policy | `fcfs-v1` / `fcfs-v1` | `prompt-length-v1` / `prompt-length-v1` |
| `policy.runtime_verified` | `true` | `true` |
| measured requests | 64 | 64 |
| short / long | 48 / 16 | 48 / 16 |
| actual Output Token | 5,632 | 5,632 |
| outcome | 64 `finished` | 64 `finished` |
| unmapped timing records | 0 | 0 |
| `cuda_synchronized` | `true` | `true` |
| measurement start / end ns | 923366620624 / 930283732833 | 1083028472352 / 1089745952786 |

两次进程都包含一个不进入 measured workload 的固定 warmup request：3 Prompt Token、64 Output Token、`ignore_eos=true`。

## Saturated admission 与真实策略行为

| 项目 | `fcfs-v1` | `prompt-length-v1` |
| --- | ---: | ---: |
| max measured `arrival_ns` | 923367430816 | 1083029344239 |
| min measured `first_scheduled_ns` | 923367749428 | 1083029646096 |
| 第一 Prefill 波次请求数 | 45 | 58 |
| 第一波次 short / long | 34 / 11 | 48 / 10 |
| 第二波次 short / long | 14 / 5 | 0 / 6 |

两次均满足：

```text
max(arrival_ns) <= min(first_scheduled_ns)
```

因此全部 measured Arrival 发生在第一次 Scheduler 调度之前。

独立校验按 `first_scheduled_ns` 排序，并用相邻时间戳的最大间隔识别两个 Prefill 波次。结果与冻结输入和 Token 预算的静态推导一致：

- FCFS 前 45 个原始顺序请求累计 15,616 Prompt Token；下一个 long 请求无法继续装入同一 16,384 Token 批次；
- 长度策略先排 48 个 short，再排 10 个 long，第一批恰好为 16,384 Prompt Token。

这只证明真实 Scheduler 执行了预期的不同选择语义，不证明任一 Policy 性能更好。

## 证据存储与 SHA-256

- WSL：`/home/lei/NanoServeLab/results/raw/stage3/scheduling/smoke-NSL-S3-SCHED-v1-20260727-a/`
- Mac Git 忽略备份：`results/raw/stage3/scheduling/smoke-NSL-S3-SCHED-v1-20260727-a/`

Mac 已按 WSL 生成的同一份 `SHA256SUMS` 逐项复验通过。清单自身 SHA-256：

```text
f6499fb6c63f4e91a57eb1e174f0bd6a8c14f5bdc411556adbd4005b1d9eb4bb
```

| 文件 | Bytes | SHA-256 |
| --- | ---: | --- |
| FCFS raw | 28,937 | `5062da22bad18818cfe231ea40d1269c69f7a104c20319a3ca1054588625f912` |
| FCFS `driver.log` | — | `3df9ed89468894cca9fd1c7778d4bfd02f072747c6b6272a96804edfb7a7d070` |
| Candidate raw | 29,382 | `51a7b698598319061031f57a4da253072f1ff822762cac303ae8892edd3544c7` |
| Candidate `driver.log` | — | `2f21bf6754fa4b6b93ad6b610622d04cc0e5e6a5130f6aa7612a897b92f4afbb` |
| `preflight-and-tests.log` | — | `4430bdc75b4a2b117b6e81f08902de39997510e48fa872fe5cf42d0153711ef4` |
| `validation.log` | — | `09c13853a62946fe3fa5cb611a0a8b5ef5cd94fe7ed451d48ca335d92660b916` |

raw 和完整日志只存在于 Git 忽略证据目录，不提交进仓库。

## 限制与下一门槛

- 两次 smoke 是行为门槛，不是可用于统计或性能比较的重复实验。
- 本文不从 measurement 时间戳派生或发布吞吐、延迟、percentile 或 Policy 差值。
- 两次运行不是按正式六进程交错顺序执行，不能用它们估计运行顺序、热状态或后台负载影响。
- 运行前后只核对 GPU compute process 和离散状态，没有连续采样温度、功耗或时钟。
- 结果只证明当前精确提交、模型、硬件与 frozen workload 的真实运行路径有效，不外推到其他模型、GPU、到达模型或 workload。

下一门槛是审阅并合并本纯文档证据切片。合并后必须同步新的精确 clean `main`，重新执行正式 preflight，再严格按：

```text
FCFS-1 → Candidate-1 → Candidate-2 → FCFS-2 → FCFS-3 → Candidate-3
```

运行六个全新进程。六份 raw 全部验证并双端封存前，不运行正式 aggregation，也不产生策略性能结论。
