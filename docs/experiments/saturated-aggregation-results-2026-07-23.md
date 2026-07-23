# 阶段 2：正式 Saturated Aggregation 结果

本文固定 2026-07-23 对三份正式 `NSL-S2-SAT-v1` schema v1 raw 的离线汇总结果、独立复算、证据哈希与结论边界。它是 [`saturated-results-2026-07-23.md`](saturated-results-2026-07-23.md) 原始结果验收的派生结果记录；不回填或修改 raw。

## 实验与汇总身份

| 项目 | 固定事实 |
| --- | --- |
| Workload | `NSL-S2-SAT-v1` |
| Raw source commit | `69c88c252e09bd5d4ffad434c525647d9bf4f207` |
| Workload manifest SHA-256 | `aa1d4e345e0e9f599bd43093bd5b9214476aa3145ee910cc9137d0b62754767d` |
| 模型 | `Qwen/Qwen3-0.6B`；revision `c1899de289a04d12100db370d81485cdf75e47ca` |
| 正式运行环境 | Python 3.12.3；PyTorch 2.4.0+cu124；CUDA 12.4；RTX 4060 Laptop GPU |
| Engine 固定项 | `enforce_eager=false`；model len 4,096；max seqs 512；max batched tokens 16,384；GPU memory 0.9；TP 1；KV block 256 |
| Aggregator | `NSL-S2-AGG-v1` |
| Aggregator PR / merge | [PR #20](https://github.com/NEVER-AGAIN-RAY/NanoServeLab/pull/20) / `a8c2efc0f14901b462a346354c134f3642b448a3` |
| 结果记录 PR / merge | [PR #21](https://github.com/NEVER-AGAIN-RAY/NanoServeLab/pull/21) / `77160a7422dca27a763eb44308bb20c11b91a967` |
| Aggregate 创建时间 | `2026-07-23T14:33:32.221191+00:00` |
| 分析机器 | MacBook M4；macOS 15.5 (`24F74`)；arm64 |
| 分析 Python | `/opt/homebrew/bin/python3`；Python 3.14.6 |
| CUDA / 模型执行 | 未运行；本步骤只读现有 raw，在 Mac 用标准库和纯指标派生离线汇总 |

raw 保持在 Git 忽略的既有双端备份结构：

```text
results/raw/stage2/saturated/
  formal-NSL-S2-SAT-v1-20260723-69c88c2/
```

派生证据保存在 Mac Git 忽略目录：

```text
results/raw/stage2/aggregation/
  formal-NSL-S2-SAT-v1-20260723-69c88c2/
    aggregate-a8c2efc-runs1-3.json
    aggregate-validation.json
    SHA256SUMS
```

## 输入与输出封存

| Artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| run 1 raw `saturated-20260723T130235.305518Z-run1.json` | 28,876 | `8ee9f9fc7879bbae94058804ea721853d5624eda3c4080cf67ba04fffe2c5a46` |
| run 2 raw `saturated-20260723T130555.925041Z-run2.json` | 28,876 | `426416c8a4937e6475a20d1bd099148cdbcabb1b45a37a2d6ace4f9a0034e887` |
| run 3 raw `saturated-20260723T130801.174121Z-run3.json` | 28,876 | `298615cf49ad7fdede5d1b8b3820ae759e3f894b2f7bc119e426c5743a04005e` |
| `aggregate-a8c2efc-runs1-3.json` | 7,744 | `47d31a4074336ab1bf6d2035e09869776847843fb3c33455c473864cd7debbb8` |
| `aggregate-validation.json` | 2,492 | `8530defde11a89da39e0489bcc3e3ee1bd3c816e69038b70b566ca6d25843416` |

aggregation 证据 `SHA256SUMS` 自校验两项均为 `OK`；清单自身 SHA-256：

```text
6b4da18c5fa93944a303f4a009efd00c1be7d1683e7de44746d98493361cf7ee
```

正式汇总前从原始证据目录执行完整 `SHA256SUMS`，26 项全部通过。汇总和所有复验结束后再次核对三份 raw，哈希没有变化。

## 执行与纠正记录

唯一成功写入使用 PR #20 合并后的精确 `origin/main` `a8c2efc`，显式列出 run 1、2、3 三个 raw 路径，并写入此前不存在的新目标文件。没有目录扫描，没有混入 smoke，也没有覆盖已有文件。

成功写入前出现两次命令级错误，均未产生 aggregate 或修改 raw：

1. 第一次 `shasum -a 256 -c` 从仓库根目录执行，但清单条目相对于原始证据目录，因此报告 26 个文件无法读取。随后从正确证据目录重跑，同一清单 26 项全部 `OK`。
2. 第一次 aggregate 写入因 Desktop 忽略目录不在默认沙箱写边界而被拒绝，目标目录和 JSON 均未创建。随后只对新的 aggregation 证据目录授予窄范围写权限，使用同一组显式输入成功写入一次。

这些错误没有触发 CUDA、模型或 benchmark 重跑，也没有替换正式 raw。失败事实同时保存在 `aggregate-validation.json` 的 `execution_corrections`。

## 完整性计数

| 项目 | 结果 |
| --- | ---: |
| Runs | 3 |
| Total requests | 192 |
| Finished | 192 |
| Failed / Cancelled / Incomplete / Other | 0 / 0 / 0 / 0 |
| Valid finished | 192 |
| Invalid records | 0 |
| Unmapped timing records | 0 |
| Short / Long | 144 / 48 |

三次每次均为 64 个 valid finished request、5,632 actual Output Token；没有剔除、替换或重跑。

## 吞吐结果

每个 run 的窗口只使用该进程自己的 `measurement.started_ns` 与 `measurement.ended_ns`。

| Run | Window (s) | Request/s | Output Token/s |
| ---: | ---: | ---: | ---: |
| 1 | 6.815051587 | 9.390978070 | 826.406070167 |
| 2 | 6.510983315 | 9.829544464 | 864.999912843 |
| 3 | 6.516285969 | 9.821545633 | 864.296015674 |

跨 run 把每次吞吐当作一个独立样本：

| Metric | n | Mean | Sample SD | Median | Min | Max | P50 | P95 | P99 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Request/s | 3 | 9.680689389 | 0.250929236 | 9.821545633 | 9.390978070 | 9.829544464 | 9.821545633 | 9.829544464 | 9.829544464 |
| Output Token/s | 3 | 851.900666228 | 22.081772778 | 864.296015674 | 826.406070167 | 864.999912843 | 864.296015674 | 864.999912843 | 864.999912843 |

`n=3` 时 nearest-rank P95/P99 都会落在最大值；它们不能解释为稳定的总体尾分布。run 1 的较低吞吐被完整保留，没有因偏离 run 2/3 而剔除。

## 请求级延迟结果

除 Mean TPOT 为 ms/Token 外，其余指标单位均为 ms。`median` 使用标准中位数；`P50` 使用合约规定的 nearest-rank，因此偶数样本下两者可以不同。

### All requests

| Metric | n | Mean | Sample SD | Median | Min | Max | P50 | P95 | P99 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Queue Time | 192 | 283.153008 | 442.733106 | 0.769322 | 0.492868 | 1153.766360 | 0.768665 | 1153.668851 | 1153.758642 |
| TTFT | 192 | 1058.051365 | 216.978188 | 1153.631954 | 849.168577 | 1509.656369 | 1153.630174 | 1509.633261 | 1509.655841 |
| Mean TPOT | 192 | 30.204347 | 6.680815 | 36.348913 | 20.776233 | 36.416640 | 36.348500 | 36.413154 | 36.415093 |
| E2E | 192 | 3213.172261 | 1973.437175 | 2131.292637 | 1976.336708 | 6814.645233 | 1982.299450 | 6814.411959 | 6814.626177 |

### Short requests

| Metric | n | Mean | Sample SD | Median | Min | Max | P50 | P95 | P99 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Queue Time | 144 | 278.195059 | 440.788903 | 0.765958 | 0.492868 | 1153.758642 | 0.763251 | 1153.659944 | 1153.750605 |
| TTFT | 144 | 1056.189676 | 216.536477 | 1153.624768 | 849.168577 | 1509.648510 | 1153.619363 | 1509.631893 | 1509.647990 |
| Mean TPOT | 144 | 33.017783 | 5.252668 | 36.356179 | 24.832688 | 36.416640 | 36.355710 | 36.413319 | 36.415093 |
| E2E | 144 | 2079.740946 | 142.486299 | 1982.163655 | 1976.336708 | 2280.689367 | 1982.161485 | 2280.644641 | 2280.675453 |

### Long requests

| Metric | n | Mean | Sample SD | Median | Min | Max | P50 | P95 | P99 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Queue Time | 48 | 298.026854 | 452.888691 | 0.779989 | 0.519138 | 1153.766360 | 0.778536 | 1153.679431 | 1153.766360 |
| TTFT | 48 | 1063.636431 | 220.502525 | 1153.648744 | 849.220112 | 1509.656369 | 1153.640978 | 1509.646054 | 1509.656369 |
| Mean TPOT | 48 | 21.764038 | 0.656098 | 22.184520 | 20.776233 | 22.222140 | 22.184451 | 22.221828 | 22.222140 |
| E2E | 48 | 6613.466207 | 143.630848 | 6515.648331 | 6510.070425 | 6814.645233 | 6515.630410 | 6814.604023 | 6814.645233 |

## 独立验证

除汇总器自身的 21 个 CPU tests 与全套 68 tests 外，本次对正式结果执行了两条额外验证链。

第一条不导入 aggregation 实现，只用 Python 标准库：

- 重新读取并核对三份 raw SHA-256；
- 独立计算 192 条请求的 Queue Time、TTFT、Mean TPOT、E2E；
- 独立构造 all / short / long 三组；
- 独立计算 mean、median、min、max、sample SD 与 nearest-rank P50/P95/P99；
- 独立计算三个 measurement window、每 run 吞吐和跨 run 统计；
- 核对 compatibility identity、source identity、计数、有限数、UTF-8 稳定键序与结尾换行。

所有字段均通过。

第二条使用合并后的 `aggregate_raw_paths()`：

- 注入已保存的 `created_at_utc` 重放同一组三份 raw，结果对象与保存的 aggregate 完全相等；
- 再次用 CLI 指向已存在的输出文件，按合约退出码 1 并报告拒绝覆盖；
- 拒绝覆盖前后 aggregate SHA-256 不变；
- 复验三份 raw SHA-256 不变；
- Mac import 路径未加载 torch。

`aggregate-validation.json` 最终记录 `validation="passed"`。

## 观察与结论边界

- 这组结果建立了 baseline scheduler 在固定 saturated 长短混合 workload 下的正式 Queue Time、TTFT、Mean TPOT、E2E 与吞吐参考。
- long 请求 E2E 明显高于 short 请求；两类 Prompt / Output Token 长度本来就不同，因此这是本 workload 下的观测，不是调度策略因果结论。
- Queue Time 的 median 小于 1 ms，而 P95 约 1,154 ms，说明分布存在明显分层。仅凭 aggregate 无法把该形状归因到某个具体 Scheduler 分支；若要解释原因，应在阶段 3 使用已固定的调度 trace / 对照实验。
- 阶段 1 的 1014.433126 output Token/s 与本次 851.900666 output Token/s 使用不同 workload、请求长度和测量 driver，不能据此声称性能退化或提升。
- 请求级 192 条延迟来自 3 个共享执行上下文的 run；pooled percentile 描述本次固定实验样本，不是跨硬件、模型或流量分布的置信区间。
- 当前只有 baseline scheduler，没有长度优先、Priority、Aging 或 Prefix Cache 感知对照，不能声称任何调度策略提升。
- 正式运行没有连续采样 GPU 温度、功耗或时钟；该限制继续保留。

## 阶段 2 退出标准

本交付完成阶段 2 章程中的三项退出标准：

1. TTFT、TPOT、E2E、Throughput 与 Queue Time 的事件边界已经定义，并经 CPU 与 WSL2/CUDA 行为路径验证；
2. 固定长短比例、Token 长度、顺序、seed 与 manifest 的可复现混合 workload 已完成三次独立进程正式运行；
3. warmup、measurement、raw 保存与离线 aggregation 已分离，正式结果经过独立复算、哈希封存和拒绝覆盖验证。

阶段 2 的结论是“测量与混合负载实验基础已经完整建立”，不是“调度性能已经提升”。下一阶段才允许在同一固定基线上一次只改变一种调度策略。
