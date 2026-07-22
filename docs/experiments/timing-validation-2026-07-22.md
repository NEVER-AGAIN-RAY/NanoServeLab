# 阶段 2：Request Timing WSL2/CUDA 验收记录

本文固定验证 `NSL-S2-TR-20260722-01` 的环境、方法、原始证据、结果与限制。它验证 Draft PR #11 的 request timing 记录层能否通过真实 nano-vLLM CUDA 路径，不是阶段 2 混合负载 benchmark，也不构成性能提升或 recorder 零开销结论。

## 结论

- 验收对象为 clean commit `e0914e23247fe731d6ee1cabce91a1e30c9725bc`（Draft [PR #11](https://github.com/NEVER-AGAIN-RAY/NanoServeLab/pull/11)）。
- WSL2 既有 `.venv` 中全部 18 个单元测试通过。
- `LLM(..., timing_recorder=recorder)` 在真实 Qwen3-0.6B、CUDA Graph、Prefill 与 Decode 路径中成功运行；2 个请求的 Arrival、First Scheduled、First Output、Completion 均齐全且满足单调顺序。
- recorder 关闭时不产生记录；开启和关闭的两个独立行为进程生成 Token 哈希相同。
- `max_tokens` 路径与受控 EOS 分支均完成；EOS 分支使用真实 CUDA 采样 Token 作为测试哨兵，不冒充模型自然生成 tokenizer EOS。
- 3 次 recorder-on 与 3 次 recorder-off 独立进程冒烟均成功，六次生成 Token 哈希相同。成对差值方向不一致，样本与 workload 太小，不能从这些数据推断稳定的性能影响。
- 原始 JSON 和验收 runner 已同时保存在 WSL2 与 Mac 的 Git 忽略目录，双端 SHA-256 一致。

因此 PR #11 的 WSL2/CUDA 行为门槛已经通过；阶段 2 仍未完成，后续还需要派生指标层、固定混合 workload 和正式实验。

## 验收对象与环境

| 项目 | 实际值 |
| --- | --- |
| 验证 ID | `NSL-S2-TR-20260722-01` |
| 时间范围 | 2026-07-22 12:32:22–12:45:12 UTC |
| Source commit | `e0914e23247fe731d6ee1cabce91a1e30c9725bc` |
| WSL 验证分支 | `codex/wsl-pr11-validation` |
| Tracked worktree | clean |
| WSL | Ubuntu 24.04，kernel `6.18.33.2-microsoft-standard-WSL2` |
| Python | 3.12.3 |
| PyTorch | 2.4.0+cu124 |
| CUDA build | 12.4 |
| GPU | NVIDIA GeForce RTX 4060 Laptop GPU，8188 MiB |
| Windows driver | 555.97 |
| 模型 | `Qwen/Qwen3-0.6B` |
| 模型 revision | `c1899de289a04d12100db370d81485cdf75e47ca` |
| Sampling seed | 0；在构造 `LLM` 前设置 CPU 与 CUDA RNG |
| 引擎配置 | `enforce_eager=False`、`max_model_len=512`、`max_num_batched_tokens=512`、`max_num_seqs=8` |

WSL 直连 GitHub 本轮仍未成功 fetch。Mac 生成只包含 `origin/main` 和 PR #11 ref 的完整 Git bundle，校验后传入 WSL；bundle SHA-256 为 `0e3250ce64fa92736f1474650c33ebc257d35550cd0b620148f882071bc12e55`。检出后再次核对 HEAD 和 tracked worktree，没有改动旧 baseline 分支的本地提交。

## 原始数据与 runner

- WSL：`/home/lei/NanoServeLab/results/raw/stage2/timing-validation-20260722/`
- Mac 备份：`results/raw/stage2/timing-validation-20260722/`
- runner：`validation-runner.py`
- runner SHA-256：`6c2fc202823272777ee0a6b08d91b5d1c32f11cce1d98a4aef1512ba9537c189`

runner 只存在于双端 Git 忽略的原始证据目录，不属于运行时代码。每个 scenario 由一个全新的 Python/`LLM` 进程运行；每份 schema v1 JSON 记录 commit、tracked dirty 状态、硬件/软件、模型 revision、引擎配置、workload、输出 Token、输出哈希、原始 timing snapshot 与布尔断言。

## 验收协议

### 1. 完整单元测试

在精确提交的仓库根目录执行：

```bash
.venv/bin/python -m unittest discover -s tests -v
```

结果：`Ran 18 tests in 0.003s / OK`。覆盖 baseline 合约、sampling seed、Scheduler 生命周期、Step Snapshot，以及 request timing 的 fake-clock、Chunked Prefill、write-once、KV 释放后可读性、不可变性和默认关闭行为。

### 2. 真实行为 on/off

两个全新进程使用相同模型、seed 和 workload：

| 请求 | Prompt Token 数 | `max_tokens` | `ignore_eos` |
| --- | ---: | ---: | --- |
| 1 | 32 | 1 | true |
| 2 | 64 | 4 | true |

recorder-on 必须满足：

- 输出数等于请求数；
- 每条记录 `output_tokens` 等于实际返回 Token 数；
- `arrival_ns <= first_scheduled_ns <= first_output_ns <= completed_ns`；
- outcome 均为 `finished`，Scheduler 最终为空；
- 一个请求走单 Token 完成，另一个请求走 Prefill 后多轮 Decode / `max_tokens` 完成。

recorder-off 必须满足 Scheduler 中 recorder 为 `None`，且不生成 timing record。两个进程的输出 Token ID 规范化后必须具有相同 SHA-256。

### 3. 受控 EOS 分支

自然语言 Prompt 无法保证模型在固定短窗口中自然采样 tokenizer EOS，因此本轮不使用不稳定提示词声称覆盖 EOS。协议分为两个全新进程：

1. `eos-probe`：32 Token Prompt，`max_tokens=1`、`ignore_eos=True`，真实 CUDA 采样得到首 Token `66`；
2. `eos-forced`：相同模型、Prompt 和 seed，把 Scheduler 的 EOS 判断值临时设为 `66`，使用 `max_tokens=8`、`ignore_eos=False`。

第二个进程必须再次真实采样 `66`，并在第 1 个输出 Token 后完成。该方法验证 Scheduler 的 EOS 完成顺序、timing 写入和 KV 释放路径；它只把 `66` 当作测试哨兵，不证明模型自然生成了 tokenizer EOS `151645`。

### 4. recorder on/off 开销冒烟

这是一项异常检查，不是正式性能 benchmark。每个进程先运行一个 16 Prompt Token / 2 Output Token 的不计时 warmup，然后同步 CUDA，以 4 个饱和准入请求进行计量：

| Prompt Token 数 | 每请求 Output Token 数 | temperature | `ignore_eos` |
| ---: | ---: | ---: | --- |
| 32、64、96、128 | 16 | 0.6 | true |

计量边界是 warmup 返回后的 `torch.cuda.synchronize()` 到 measured `generate()` 返回后的 `torch.cuda.synchronize()`。运行顺序为 on-1、off-1、off-2、on-2、on-3、off-3；每次都是全新 Python/`LLM` 进程。唯一条件差异是是否向 `LLM` 注入 recorder。

## 结果

### 行为与 EOS

| Scenario | 输出 Token 数 | timing records | 输出 SHA-256 | 结果 |
| --- | --- | ---: | --- | --- |
| behavior-on | 1、4 | 2 | `1d6c3cd5574ecaca2ad7c38bc3b7cdf2e8f05ca3e78204053d7d2c426720c47a` | 全部断言通过 |
| behavior-off | 1、4 | 0 | `1d6c3cd5574ecaca2ad7c38bc3b7cdf2e8f05ca3e78204053d7d2c426720c47a` | 默认关闭、输出一致 |
| eos-probe | 1 | 1 | `3cd4e44bfae4eccabe4c7f9fe2d82805a299c3633a1d27999443f5b6020f8c65` | 探测 Token `66` |
| eos-forced | 1 | 1 | `3cd4e44bfae4eccabe4c7f9fe2d82805a299c3633a1d27999443f5b6020f8c65` | `max_tokens=8` 前经受控 EOS 完成 |

behavior 与 EOS 进程没有显式 generate warmup，其 elapsed 包含首次惰性采样编译，不能拿来比较 recorder 性能。

### 开销冒烟原始值

| Run | recorder-on（ms） | recorder-off（ms） | on − off（ms） |
| ---: | ---: | ---: | ---: |
| 1 | 854.463507 | 753.140861 | +101.322646 |
| 2 | 725.983385 | 873.265205 | −147.281820 |
| 3 | 761.846081 | 820.061441 | −58.215360 |

| 条件 | n | mean（ms） | median（ms） | sample SD（ms） |
| --- | ---: | ---: | ---: | ---: |
| recorder-on | 3 | 780.764324 | 761.846081 | 66.296383 |
| recorder-off | 3 | 815.489169 | 820.061441 | 60.192556 |

六次输出 SHA-256 均为 `ffc79b25ec0ebd206e29890676bc978521ae82490f4a664473dba79928d4e2eb`。on 的样本均值比 off 低 34.724845 ms（−4.258%），但三组成对差值有正有负，且组内样本标准差约 60–66 ms。该现象更符合小 workload 与独立进程噪声，不能解释为 recorder 加速，也不能据此给出精确开销上界；本轮只能结论为“未观察到破坏正确性或一致的异常级退化”。

## 原始文件 SHA-256

下列哈希已在 WSL 与 Mac 分别计算并逐项核对一致：

| 文件 | SHA-256 |
| --- | --- |
| `behavior-off.json` | `bb0e6daed361e6f222f26552a2df152637244e460270a9d382b17dfc8736231d` |
| `behavior-on.json` | `d6ceda31393334555f3253a3f42c0876cfdba815edb42c865eab32da308da962` |
| `eos-forced.json` | `89482e6948971e0b2f664ed7c7269d2af4b60c12bec3743a4ca37b52289bbcbc` |
| `eos-probe.json` | `61160af86d25a17d91eeef35ebd60cfa9d8a83b8b68df0e420571676ecb50b0c` |
| `overhead-off-run1.json` | `0c8ae0209e0c55ef19a941d2e6eb4ab1f127c03c0061ec848fb8508fdd127023` |
| `overhead-off-run2.json` | `c20f0cb70dc1c6b4280db89e6e1b074047e2117a8e2ae6f40dc03b67aa003754` |
| `overhead-off-run3.json` | `73eafd86df4c02f5a112881a937c592bf614d720589e2f3f3af9c3726d2d5959` |
| `overhead-on-run1.json` | `adadaebff75013f84ac475ed3545971279ea14b39ec9d266721fa48294b0620d` |
| `overhead-on-run2.json` | `9977a64c1a289a684a06e8b112c70c3d69ebd4d278236c13982de1c75ecd0347` |
| `overhead-on-run3.json` | `0636ef45917ac5457403c7bff00f3dc3538bedb6598a8ee8635a9fbeee8545dd` |
| `validation-runner.py` | `6c2fc202823272777ee0a6b08d91b5d1c32f11cce1d98a4aef1512ba9537c189` |

## 限制与后续使用规则

- 受控 EOS 使用真实采样 Token 作为判断哨兵，但不是模型自然生成 tokenizer EOS；报告和论文不得混淆二者。
- 开销组只有 4 个请求、每条件 3 次，目的只是发现异常级退化。没有连续记录温度、功耗和 GPU 时钟，也没有单独归档 stdout/stderr，不能据此做显著性检验或性能结论。
- 本轮没有实现指标派生、percentile、JSONL trace、长短混合 workload 或正式阶段 2 benchmark，也没有计算客户端流式 TTFT。
- 本轮确认的是 engine-side Host 记录边界在真实 CUDA 调用链中可用；它不意味着 timestamp 是 GPU kernel 级时间戳。
- 后续若改变 recorder 写入位置、Scheduler 生命周期、ModelRunner 返回边界、模型、workload 或环境，本验收不能自动继承，必须重新运行相关检查。
