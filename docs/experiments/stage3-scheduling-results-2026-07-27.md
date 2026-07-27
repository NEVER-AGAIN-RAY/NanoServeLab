# 阶段 3 正式双 Policy raw 结果（2026-07-27）

本文固定 `NSL-S3-SCHED-v1` 第一组正式六进程对照的原始实验事实、运行顺序、验证门槛、文件哈希和限制。本文不计算 TTFT、TPOT、E2E、吞吐、percentile 或 Policy 差值；这些派生量只能由后续 `NSL-S3-AGG-v1` 离线聚合产生。

## 结论范围

- comparison group：`prompt-length-20260727-a`；
- 两个 Policy 各有 3 个全新 Python 进程，严格按预声明顺序完成；
- 六份 schema v2 raw 均为 `finished`，共 384/384 请求完成、33,792 个实际 Output Token、0 unmapped timing record；
- requested / actual Policy 一致，`runtime_verified=true`，CUDA 双边界同步且 saturated admission 成立；
- 六份 raw、六份完整 driver log、preflight/tests、整体 validation 和 `SHA256SUMS` 已在 WSL 与 Mac 双端逐项复验；
- 没有失败运行、重跑、删除、替换或覆盖；
- 尚未执行 aggregation，本文不支持任何性能提升、退化或公平性结论。

## 源码与环境身份

| 项目 | 固定事实 |
| --- | --- |
| repository commit | `42cb476df358718b548aacc61f11487af2fa6615` |
| WSL branch | `codex/wsl-stage3-formal-20260727` |
| Git 状态 | 运行前、逐次运行后及整体审计后 tracked worktree clean |
| GPU | NVIDIA GeForce RTX 4060 Laptop GPU，8,188 MiB |
| Driver | 555.97 |
| Python / PyTorch / CUDA | 3.12.3 / 2.4.0+cu124 / 12.4 |
| Model | `Qwen/Qwen3-0.6B` |
| Model revision | `c1899de289a04d12100db370d81485cdf75e47ca` |
| Model weight | 1,503,300,328 Bytes；SHA-256 `f47f71177f32bcd101b7573ec9171e6a57f4f4d31148d38e382306f42996874b` |
| Workload | `NSL-S2-SAT-v1`，64 请求 |
| Manifest SHA-256 | `aa1d4e345e0e9f599bd43093bd5b9214476aa3145ee910cc9137d0b62754767d` |

PR #31 合并后的 Mac `origin/main` 通过完整 Git bundle 同步到 WSL。bundle 在两端的 SHA-256 为 `0e093d38ec861f68959fdeef9e88d8d2d66494d622fcc5f82b6b3070c9822d70`，`git bundle verify` 确认其包含完整历史和精确 `origin/main`。

正式输出目录在创建前不存在：

```text
results/raw/stage3/scheduling/prompt-length-20260727-a/
```

preflight 重新验证精确 commit、Git clean、GPU、CUDA Tensor、模型、权重、manifest 和 GPU compute process；完整测试为 `Ran 103 tests / OK`。

## 固定运行顺序与原始结果

运行顺序没有根据中途现象调整：

```text
FCFS-1 → Candidate-1 → Candidate-2 → FCFS-2 → FCFS-3 → Candidate-3
```

| 顺序 | Policy / run | `created_at_utc` | run ID | 请求 / Output Token | raw SHA-256 |
| --- | --- | --- | --- | --- | --- |
| 1 | `fcfs-v1` / 1 | `2026-07-27T13:31:30.215082+00:00` | `4a395550-7f75-4c7f-bc50-7a7c4c93946a` | 64 / 5,632 | `69cc63cc6bc4d0f8394dd9c5e39250b7c7161f6cebea20a45a45899f0ee2b3c2` |
| 2 | `prompt-length-v1` / 1 | `2026-07-27T13:34:47.159162+00:00` | `04b91a7e-e044-42a1-902b-4eef494f2880` | 64 / 5,632 | `1d62350d1b773576df4074d98e6b37420dc1e8c72ba2c75fb7bf1e0d3894d02e` |
| 3 | `prompt-length-v1` / 2 | `2026-07-27T13:36:51.039474+00:00` | `2ce609c0-df01-41e7-9522-407768d06786` | 64 / 5,632 | `b19d303ba9571e399023c806e0e56800a19f28b5c517c22dc55f8c2f8a785c88` |
| 4 | `fcfs-v1` / 2 | `2026-07-27T13:38:48.954934+00:00` | `0a4dd59e-3b5c-459e-b9b7-942a0ed541e3` | 64 / 5,632 | `40d3927c741fc843c72eabc272661045bb84c15e7f51962847b8b3fdac57bd39` |
| 5 | `fcfs-v1` / 3 | `2026-07-27T13:40:43.627171+00:00` | `b523cb83-9bb9-4dcd-96c1-827209f7c715` | 64 / 5,632 | `a249f3066e84053f230988387eeb02d7f41b26590a8b5816d6fc9b7a6d0625d2` |
| 6 | `prompt-length-v1` / 3 | `2026-07-27T13:42:40.727589+00:00` | `9fbd743e-060b-4a8a-a2d4-fb9b604794bd` | 64 / 5,632 | `3218a4479b6d992d162a884ac9164f00d081a0375b81262ae840cc170cfc693b` |

每份 raw 的独立门槛均验证：

- schema / experiment / comparison group / run number；
- repository commit、branch 和 dirty=false；
- Policy ID、definition、requested/actual 一致和 runtime verified；
- workload ID、manifest、64 请求和固定 engine 参数；
- status=finished、error=null、CUDA synchronized、0 unmapped；
- 64/64 finished、5,632 actual Output Token；
- arrival ≤ first scheduled ≤ first output ≤ completed；
- `max(arrival_ns) <= min(first_scheduled_ns)`。

整体审计另外确认六个 run ID 唯一，创建时间顺序与冻结顺序一致，repository、environment、model、fixed engine 和 workload 兼容键完全相同。六份 driver log 未发现 traceback、CUDA error、OOM、failed status、NaN 或 Inf。

## 证据封存

`SHA256SUMS` 覆盖 14 个文件：

- 6 份 raw JSON；
- 6 份完整 driver log；
- `preflight-and-tests.log`；
- `validation.log`。

WSL 生成后逐项校验成功，整个目录复制到 Mac 的 Git 忽略路径后再次按同一清单逐项校验成功。`SHA256SUMS` 自身 SHA-256 为：

```text
04b5570d406a97b9d4ea9e34caba2d85f4b199cd71b5b7aa36eb48ac6bbd708c
```

## 命令纠正

`FCFS-1` 成功后，第一次只读 raw 校验一行命令因嵌套引号被 Mac zsh 在建立 SSH 连接前拒绝。随后改用独立标准库只读脚本完成相同校验，并在最终 `validation.log` 中记录该纠正。错误命令没有连接 WSL、构造 LLM、修改 raw 或触发重跑。

## 限制与下一门槛

- saturated admission、固定 synthetic workload 和单卡 8GB 环境不代表开放式在线流量或更大模型；
- `n=3` 只能描述本固定环境下的重复结果，不能证明广泛外推性；
- raw 中虽然含完整时间戳，本文有意不派生或选择性展示性能数字；
- 下一门槛是审阅并合并本 raw 证据切片；随后才允许在新的精确 clean `main` 上对这六份不可变 raw 执行一次 `NSL-S3-AGG-v1` 离线聚合、独立复算和结果记录。
