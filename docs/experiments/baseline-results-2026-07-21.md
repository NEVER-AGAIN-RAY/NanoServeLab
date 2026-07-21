# 阶段 1 baseline 正式实验记录（2026-07-21）

本文件是 NanoServeLab 第一组正式 CUDA baseline 的可追溯结果记录，可作为后续书面报告或论文中“实验设置、基线结果与有效性限制”的原始依据。实验合约见 [`baseline.md`](./baseline.md)，当前项目状态仍以 [`docs/project/README.md`](../project/README.md) 为准。

## 结论摘要

- 实验编号：`NSL-S1-BL-20260721-01`
- 三次固定 workload 均在独立 Python 进程中成功完成，没有失败、重跑或结果剔除。
- 三次输出 Token 吞吐的算术平均值为 **1014.433126 Token/s**，样本标准差为 **4.212859 Token/s**，变异系数为 **0.415292%**。
- 观察范围为 **1011.091819–1019.165630 Token/s**；三次测量的固定配置和非时间型 measurement 字段完全一致。
- 本组数据只建立当前环境与当前源码的参考 baseline。没有对照组，因此不能据此声称任何性能提升，也不能回答 TTFT、TPOT、尾延迟或公平性问题。

## 实验身份与证据链

| 项目 | 记录值 |
| --- | --- |
| 实验编号 | `NSL-S1-BL-20260721-01` |
| 数据采集窗口 | 2026-07-21 13:24:57–13:38:24 UTC；Asia/Shanghai 为 21:24:57–21:38:24 |
| Benchmark 名称 | `nano_vllm_upstream_synthetic_throughput` |
| 原始 JSON schema | 1 |
| 源码分支 | `codex/reproducible-baseline-contract` |
| 源码 commit | `fb94f6b46213174718c2c89d11c86180712f3b53` |
| 工作区状态 | 三次 JSON 均记录 `dirty: false` |
| 相关变更 | [Draft PR #7](https://github.com/NEVER-AGAIN-RAY/NanoServeLab/pull/7) |
| WSL 原始数据 | 仓库相对路径 `results/raw/baseline/` |
| Mac 备份 | Mac 工作树中的同一仓库相对路径 `results/raw/baseline/` |
| Git 策略 | `results/raw/` 被 Git 忽略；本文件提交统计与校验证据，原始 JSON 不提交 |

三份原始文件在 WSL 和 Mac 上逐一计算 SHA-256，结果完全一致：

| Run | 原始文件 | SHA-256 |
| --- | --- | --- |
| 1 | `baseline-20260721T133016.390268Z-run1.json` | `df7470398fcb6192709d0d309f7fde1017acb811e589eb0e359b3d0ecea64946` |
| 2 | `baseline-20260721T133424.232884Z-run2.json` | `52fc2375c4d5a1df5fd0ab762c99cabb5389044578e8a5033ff5ff34d59545f2` |
| 3 | `baseline-20260721T133824.195352Z-run3.json` | `4dc6ca5e52b55ef7bab9b09ca4dc5dafbd3859935d492e57d3d9f16a5762ca2a` |

## 硬件与软件环境

| 层级 | 已验证配置 |
| --- | --- |
| 主机 CPU | Intel Core i9-14900HX；WSL 暴露 32 个逻辑 CPU、16 Core、2 Thread/Core |
| WSL 内存 | 16,565,088,256 Bytes；Swap 4,294,967,296 Bytes，运行前 Swap 使用量为 0 |
| 操作系统 | Ubuntu 24.04.4 LTS on WSL2，x86_64 |
| WSL 内核 | `6.18.33.2-microsoft-standard-WSL2` |
| GPU | NVIDIA GeForce RTX 4060 Laptop GPU，8188 MiB |
| NVIDIA 驱动 | 555.97，由 Windows 驱动通过 WSL 暴露 |
| Compute Capability | 8.9 |
| Windows 电源计划 | `381b4222-f694-41f0-9685-ff5bb260df2e`（Balanced） |
| Python | 3.12.3，GCC 13.3.0，项目既有 `.venv` |
| PyTorch | 2.4.0+cu124；CUDA build 12.4 |
| Triton | 3.0.0 |
| Transformers | 5.5.0 |
| Flash Attention | 2.7.4.post1 |
| xxhash | 3.8.1 |

运行前 GPU 空闲且没有 compute process。运行前瞬时状态为 P4、57 °C、16.01 W、Graphics Clock 390 MHz、Memory Clock 6000 MHz；三次进程结束并退出后复查为 P4、55 °C、15.24 W、405 MHz、6000 MHz，且没有残留 compute process。这两个值只是空闲时的前后快照，不是运行期间的连续温度、功耗或时钟采样，不能用来推导热稳定性或能效。

更完整的 WSL2 环境事实见 [`environment/wsl2.md`](../../environment/wsl2.md)。

## 模型身份

| 项目 | 固定值 |
| --- | --- |
| 模型 ID | `Qwen/Qwen3-0.6B` |
| 本地目录 | `/home/lei/huggingface/Qwen3-0.6B` |
| Hugging Face revision | `c1899de289a04d12100db370d81485cdf75e47ca` |
| Metadata 一致性 | 10 个下载 metadata 文件的首行 revision 全部一致 |
| 权重文件 | `model.safetensors`，1,503,300,328 Bytes |
| 权重 SHA-256 | `f47f71177f32bcd101b7573ec9171e6a57f4f4d31148d38e382306f42996874b` |

## Workload 与固定变量

| 变量 | 固定值 |
| --- | --- |
| 请求数 | 256/Run |
| Workload seed | 0；只用于 Python `random.Random` 生成输入与长度 |
| Sampling seed | 0；在创建 `LLM` 前设置 PyTorch CPU/CUDA RNG 起点 |
| 输入长度分布 | `[100, 1024]` 均匀整数分布 |
| 输出长度分布 | `[100, 1024]` 均匀整数分布 |
| Prompt Token ID 分布 | `[0, 10000]` 均匀整数分布 |
| Sampling | temperature 0.6，`ignore_eos=True` |
| 引擎 | `enforce_eager=False`，`max_model_len=4096` |
| 重复方式 | 3 次串行执行；每次是新的 Python 进程和新的 `LLM` 实例 |

seed 0 实际生成的固定 workload 摘要如下。这里区分“配置允许范围”和这一次固定样本中的“实际观察范围”：

| 数据项 | 固定 workload 实际值 |
| --- | ---: |
| 输入 Token 总数 | 142,827 |
| 输入长度最小值 / 最大值 | 107 / 1024 |
| 输入长度平均值 | 557.917969 |
| 请求输出 Token 总数 | 133,966 |
| 输出长度最小值 / 最大值 | 103 / 1024 |
| 输出长度平均值 | 523.304688 |
| Prompt Token ID 实际最小值 / 最大值 | 0 / 10000 |
| 实际出现的不同 Prompt Token ID 数 | 10,001 |

为避免只凭 seed 描述 workload，另对以下规范化 payload 计算了指纹：

```text
{"output_lengths": [...], "prompt_token_ids": [[...], ...]}
```

实际序列化使用 UTF-8、`json.dumps(..., sort_keys=True, separators=(",", ":"))`，共 699,926 Bytes；其 SHA-256 为 `ba5158017eff74f36be1d0f9bfaee7bf39eb88f70fa50fa8aea820ce1e2bd513`。该指纹已在实际 WSL Python 环境中计算，并与 Mac 从同一 commit 重建的结果一致。

## Warmup、计量边界与指标定义

每个进程按以下顺序运行：

1. 在任何 `LLM` 初始化之前设置 workload seed 与 sampling seed。
2. 创建新的 `LLM(enforce_eager=False, max_model_len=4096)`；模型加载、内部 warmup 和 CUDA Graph 捕获不计时。
3. 运行一条 `"Benchmark: "` 请求作为显式 warmup；该请求不计时。
4. warmup 返回后执行 `torch.cuda.synchronize()`。
5. 用 `time.perf_counter()` 包围一次完整的 256 请求 `llm.generate(...)`。
6. `generate` 返回后再次执行 `torch.cuda.synchronize()`，然后停止计时。
7. 用固定的请求输出 Token 总数除以 elapsed wall-clock time：

```text
throughput_output_tok_s = 133966 / elapsed_seconds
```

因此，本文件中的吞吐是“完整固定 batch 的输出 Token/s”，包括 measured `generate` 内的调度、Prefill、Decode、Sampling 与输出处理，但不包括 LLM 创建和显式 warmup。它不是输入加输出的总 Token/s，不是 Request/s，也不是在线请求到达模型。

## 实际运行命令

工作目录为 `/home/lei/NanoServeLab`。下列命令分别将 `<RUN>` 替换为 1、2、3，每次等待前一进程完全退出并确认 GPU 无残留后再启动：

```bash
timeout 1800 env TOKENIZERS_PARALLELISM=false \
  .venv/bin/python -u bench.py \
  --model /home/lei/huggingface/Qwen3-0.6B \
  --model-id Qwen/Qwen3-0.6B \
  --model-revision c1899de289a04d12100db370d81485cdf75e47ca \
  --seed 0 \
  --sampling-seed 0 \
  --run-number <RUN> \
  --num-seqs 256 \
  --min-input-len 100 \
  --max-input-len 1024 \
  --min-output-len 100 \
  --max-output-len 1024 \
  --max-token-id 10000 \
  --max-model-len 4096 \
  --temperature 0.6 \
  --output-dir results/raw/baseline
```

`timeout 1800` 只提供失败保护；三次都在限制内正常退出，退出码均为 0。

## 逐次原始结果

| Run | JSON 创建时间（UTC） | Elapsed（s） | 输出 Token | 输出吞吐（Token/s） |
| ---: | --- | ---: | ---: | ---: |
| 1 | 2026-07-21T13:30:16.390268+00:00 | 131.446740 | 133,966 | 1019.165630 |
| 2 | 2026-07-21T13:34:24.232884+00:00 | 132.241318 | 133,966 | 1013.041928 |
| 3 | 2026-07-21T13:38:24.195352+00:00 | 132.496374 | 133,966 | 1011.091819 |

三次合计执行了 768 个请求和 401,898 个请求输出 Token。这里的“合计”只是三次相同 workload 的重复测量数据量，不能当作 768 个不同 workload 样本。

## 描述性统计

统计单位是三次 Run；吞吐主统计量是三个 per-run throughput 的算术平均值。标准差使用样本标准差（分母 `n - 1`），变异系数为 `sample_stddev / mean × 100%`。由于 `n=3`，本记录不做正态性假设、置信区间或显著性检验。

| 统计量 | Elapsed（s） | 输出吞吐（Token/s） |
| --- | ---: | ---: |
| 样本数 | 3 | 3 |
| 平均值 | 132.061478 | 1014.433126 |
| 中位数 | 132.241318 | 1013.041928 |
| 样本标准差 | 0.547439 | 4.212859 |
| 最小值 | 131.446740 | 1011.091819 |
| 最大值 | 132.496374 | 1019.165630 |
| 极差 | 1.049634 | 8.073811 |
| 变异系数 | 0.414534% | 0.415292% |

后续报告可以把该条件简写为 **1014.43 ± 4.21 output Token/s（mean ± sample SD，n=3）**，但必须同时保留模型、硬件、commit、workload 和计量口径，不能把这个数字泛化为 nano-vLLM、Qwen3 或 RTX 4060 的普遍性能。

## 有效性核对

- 正式运行前，Mac 与 WSL 仓库均为 commit `fb94f6b...`，WSL 工作区 clean，原始结果目录为空，GPU 无 compute process。
- 10 个模型下载 metadata 的 revision 一致；权重文件 SHA-256 与 metadata 中记录的对象哈希一致。
- 三份 JSON 均可解析，schema 为 1，Run Number 依次为 1、2、3。
- 三份 JSON 的 branch、commit、dirty、Python/包版本、CUDA、GPU、模型、引擎、workload、sampling、warmup、时钟、同步状态和输出 Token 总数完全一致。
- 仅 `created_at_utc`、`run_number`、`elapsed_seconds` 与 `throughput_tokens_per_second` 按 Run 变化。
- 三次吞吐均重新按 `total_output_tokens / elapsed_seconds` 计算并与 JSON 数值一致，绝对容差为 `1e-12`。
- 每次运行结束后均检查 GPU compute process；没有残留进程，再开始下一次。
- 三份文件从 WSL 复制到 Mac 后逐一核对 SHA-256；没有传输差异。
- 没有失败运行，没有删除较慢结果，也没有在三次之间更改源码、依赖或参数。

## 运行观察与限制

### 可重复观察

三次 measured workload 都出现相同的 PyTorch Dynamo 警告：`torch._dynamo hit config.accumulated_cache_size_limit (256)`，对应 `add_rms_forward`。三次仍正常完成并生成有效 JSON。本轮将该警告保留为当前软件栈与 workload 的已知条件，没有在重复之间调整 cache limit；未来若专门研究编译行为，应建立新实验并保持单变量比较。

终端进度条显示三次显式 warmup 约为 19.90、20.11 和 20.89 秒。这些只是未单独落盘的控制台观察值，不属于 JSON measurement，也不进入任何性能统计。

### 结论边界

- 这是 synthetic、closed-batch workload，不代表真实文本、在线到达过程或服务并发分布。
- 输入、输出长度与 Prompt Token ID 来自固定伪随机生成器；相同 workload 被重复三次，不是从 workload 分布重新抽样三次。
- 单条短 warmup 不能证明所有长度形状、编译路径或 GPU 热状态都已进入稳态。
- 未连续记录运行期间的温度、功耗、频率、系统后台负载或 Windows 电源状态变化；GPU 时钟和功耗也未锁定。
- 指标只覆盖整批输出 Token 吞吐；没有 per-request 时间戳，因此不能推导 TTFT、TPOT、E2E、Queue Time、P95/P99 或公平性。
- Sampling seed 固定 RNG 起点，但本实验没有保存生成 Token 内容，也没有验证 CUDA 算子的位级确定性。
- 三次新进程隔离了 `LLM`、Scheduler 和 Prefix Cache 的进程内状态，但驱动、操作系统文件缓存及 GPU 的进程外状态可能延续。
- 只有一张 GPU、一个模型、一个源码 commit 和三次重复；统计结果只用于建立参考点，不支持显著性或跨平台泛化。
- stdout/stderr 没有作为独立原始日志文件归档；Dynamo 警告与 warmup 观察已在本文件如实记录。未来正式对照实验应在不改变计量路径的前提下同时保存控制台日志。
- 原始 JSON 当前保存在 WSL 与 Mac 两份本地副本中，但尚未建立离机或不可变归档；论文提交前应增加受控归档，并再次核对本文列出的 SHA-256。

## 阶段判定与后续使用

本组数据满足阶段 1 的正式退出门槛：GPU/CUDA 环境已核实，模型与源码身份已固定，官方形状的 baseline 在三个全新进程中实际跑通，原始数据已保存并完成跨机器哈希核对。

后续任何调度或指标实验都应把 `NSL-S1-BL-20260721-01` 视为明确条件下的参考点，而不是永久常数。只要源码、模型 revision、依赖、驱动、GPU、电源条件、workload 或计量边界变化，就必须使用新的实验编号；比较实验一次只改变一个目标变量，并重新保留全部原始结果。阶段 2 应先定义 TTFT、TPOT、E2E 与 Queue Time 的事件边界和记录格式，再构造长短混合 workload，不能从本组 batch throughput 反推这些指标。
