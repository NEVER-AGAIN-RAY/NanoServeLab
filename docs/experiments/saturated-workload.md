# 阶段 2：Saturated 长短混合 Workload 合约

本文冻结 NanoServeLab 阶段 2 第一版长短混合 workload：`NSL-S2-SAT-v1`。它规定请求类别、顺序、Token 构造、准入模型、warmup、测量边界、重复规则和未来原始结果格式。当前切片只实现确定性 manifest 构造与 CPU 合约测试，不运行模型、CUDA 或 benchmark。

## 研究用途与限制

该 workload 用于在同一个完整等待队列中观察长短请求的 engine-side Queue Time、TTFT、Mean TPOT 和 E2E，并为后续调度策略提供固定对照输入。

它不是：

- 真实线上流量分布；
- Poisson、固定速率或带网络延迟的开放式到达；
- 客户端可见流式延迟测试；
- Prefix Cache 专项实验；
- 阶段 1 官方 synthetic throughput baseline 的替代品。

阶段 1 的 `bench.py` 保持不变。不同 workload 的吞吐或延迟不得直接混为同一个实验组，也不得把结果差异自动解释为性能提升。

## 固定 workload

| 项目 | 固定值 |
| --- | --- |
| Workload ID | `NSL-S2-SAT-v1` |
| 总请求数 | 64 |
| 短请求 | 48（75%） |
| 长请求 | 16（25%） |
| Workload seed | 0 |
| Sampling seed | 0 |
| Token ID 范围 | `[0, 10000]`，两端包含 |
| 请求顺序 | `[short, long, short, short]` 重复 16 次 |
| 到达模型 | saturated batch admission |

请求类别：

| 类别 | Prompt Token | 请求 Output Token | 最大上下文 | 数量 |
| --- | ---: | ---: | ---: | ---: |
| short | 128 | 32 | 160 | 48 |
| long | 1024 | 256 | 1280 | 16 |

总量：

- Prompt Token：22,528；
- 请求 Output Token：5,632；
- Prompt + 请求 Output Token：28,160；
- 单请求最大上下文：1,280，小于固定 `max_model_len=4096`。

选择 3:1 而不是 1:1，是为了让短请求保持多数，同时用 16 个长请求持续制造 Prefill、Decode 和 KV 占用压力。固定交错顺序避免“所有短请求在前”或“所有长请求在前”成为额外变量。该比例只是第一版合成研究场景，不声称代表真实用户流量。

## Token 构造与指纹

实现位于 `research/stage2_workload.py`：

1. 使用局部 `random.Random(0)`，不读取或修改进程全局 Python RNG；
2. 类别顺序固定为 `[short, long, short, short] * 16`；
3. 不随机生成长度；每个请求按其固定 Prompt 长度顺序调用 `randint(0, 10000)`；
4. Output Token 数只来自请求类别，不消耗 workload RNG；
5. 返回不可变 `tuple[SaturatedRequest, ...]`，每个请求和 Prompt Token 序列也不可变。

规范 manifest 是包含 64 个对象的 JSON array。每个对象依次包含：

- `request_index`；
- `request_class`；
- `prompt_token_ids`；
- `max_tokens`。

指纹编码规则：`json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")`，再计算 SHA-256。固定结果为：

```text
aa1d4e345e0e9f599bd43093bd5b9214476aa3145ee910cc9137d0b62754767d
```

正式运行前必须重算并核对该指纹。指纹不一致的运行不能归入 `NSL-S2-SAT-v1`，也不能通过修改文档中的预期值来迁就实现。

## Saturated admission 的精确定义

warmup 完成后：

1. 记录 `measurement_started_ns`；
2. 按固定 `request_index` 顺序依次准入全部 64 个 measured 请求；
3. 在最后一个请求完成准入前，不得调用第一次 `Scheduler.schedule()`、`LLMEngine.step()` 或 `ModelRunner.run()`；
4. 64 个请求全部进入等待队列后才开始第一轮 Scheduler step；
5. 循环 step，直到全部 measured 请求终止；
6. CUDA 同步后记录 `measurement_ended_ns`。

因此“saturated”表示第一次调度面对完整的 64 请求长短混合队列，不表示这些请求拥有完全相同的 `arrival_ns`。请求仍然顺序调用 `Scheduler.add()`，较早请求的 engine-side latency 会包含同批后续请求的准入时间；该数值不得称为客户端或网络到达延迟。

## 模型、采样与引擎固定项

后续 WSL2 driver 必须固定并记录：

| 项目 | 固定值 |
| --- | --- |
| 模型 | `Qwen/Qwen3-0.6B` |
| 模型 revision | `c1899de289a04d12100db370d81485cdf75e47ca` |
| temperature | 0.6 |
| `ignore_eos` | true |
| Sampling seed | 0，在构造 `LLM` 前设置 CPU/CUDA RNG |
| `enforce_eager` | false |
| `max_model_len` | 4096 |
| `max_num_seqs` | 512 |
| `max_num_batched_tokens` | 16384 |
| `gpu_memory_utilization` | 0.9 |
| `tensor_parallel_size` | 1 |
| `kvcache_block_size` | 256 |

`ignore_eos=true` 确保实际 Output Token 数等于类别请求值，使每次运行的工作量一致。设置 sampling seed 只固定 RNG 起点，不声称所有 CUDA kernel 位级确定。

## Warmup 与计量边界

- 每个独立进程只构造一个 `LLM`；
- 在 measured admission 前执行一条固定 warmup 请求；
- warmup 不进入 measured 请求数、吞吐分子或延迟汇总；
- recorder 若在 LLM 构造时已经启用，warmup timing record 必须原样保留在原始结果的 `warmup.timing_records`，不能静默删除或混入 measured `requests`；
- warmup 返回后先同步 CUDA，再开始 `measurement_started_ns`；
- `measurement_ended_ns` 只能在所有 measured 请求完成并再次同步 CUDA后写入；
- 模型加载、CUDA Graph 捕获和 warmup 不属于 measured window。

正式实验至少运行 3 次，每次使用全新 Python 进程和全新 `LLM`，不能在同一进程循环三次。任一次失败必须保留，不能只重跑失败或较慢的一次来替换原结果。

## 未来原始结果格式

未来 driver 每次运行写一个 Git 忽略的：

```text
results/raw/stage2/saturated/saturated-<UTC>-run<N>.json
```

schema v1 至少包含：

```json
{
  "schema_version": 1,
  "experiment": "NSL-S2-SAT-v1",
  "run_id": "unique-run-id",
  "run_number": 1,
  "created_at_utc": "...",
  "repository": {},
  "environment": {},
  "model": {},
  "engine": {},
  "workload": {
    "arrival_model": "saturated_batch",
    "seed": 0,
    "sampling_seed": 0,
    "request_count": 64,
    "manifest_sha256": "aa1d4e345e0e9f599bd43093bd5b9214476aa3145ee910cc9137d0b62754767d"
  },
  "warmup": {
    "measured": false,
    "timing_records": []
  },
  "measurement": {
    "clock": "time.perf_counter_ns",
    "started_ns": 0,
    "ended_ns": 0,
    "cuda_synchronized": true
  },
  "requests": []
}
```

每个 measured request 至少保存：

- `request_index` 和进程内 `seq_id`；
- `request_class`；
- Prompt Token 数和请求 Output Token 数；
- 实际 Output Token 数和 outcome；
- Arrival、First Scheduled、First Output、Completion 原始纳秒时间戳；
- 错误字段（没有错误时为 `null`）。

原始 JSON 不保存 Queue Time、TTFT、TPOT、E2E 或 percentile；这些值必须从原始记录通过已验证的派生/聚合层重算，避免重复字段互相矛盾。`request_index` 是跨运行对齐 workload 位置的键，`seq_id` 只记录当次进程事实，不能单独作为跨运行 ID。

## 当前交付与下一门槛

当前切片只交付：

- 固定 workload 合约；
- 不可变、确定性的 manifest builder；
- 类别顺序、长度、总量、Token 边界和 SHA-256 CPU 测试。

当前没有实现 WSL2 driver、原始 JSON writer、指标聚合或正式实验。下一切片应只实现 saturated admission driver 与 schema v1 原始写出，并用 CPU fake engine 测试“全部准入先于第一次 step”；通过 Mac 审阅后，再到 WSL2 做真实 CUDA 冒烟和三次独立进程实验。
