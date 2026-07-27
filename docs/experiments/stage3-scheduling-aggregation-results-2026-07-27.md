# 阶段 3：正式双 Policy Aggregation 结果

本文固定 2026-07-27 对 `prompt-length-20260727-a` 六份正式 schema v2 raw 的 `NSL-S3-AGG-v1` 离线汇总、独立复算、证据哈希和结论边界。它是 [`stage3-scheduling-results-2026-07-27.md`](stage3-scheduling-results-2026-07-27.md) 的派生结果记录；不回填或修改 raw。

## 核心结论

在本次固定 Qwen3-0.6B、RTX 4060、64 请求 saturated 长短混合 workload 下：

- FCFS 三次平均为 `745.100559 ± 2.158375` Output Token/s；
- `prompt-length-v1` 三次平均为 `625.431076 ± 109.583382` Output Token/s；
- Candidate − FCFS 的平均 Output Token/s 差值为 `-16.060850%`；
- Candidate 的 all-request 平均 TTFT、Mean TPOT、E2E 分别增加 `59.534286%`、`32.442823%`、`32.896890%`；
- 预声明的 `throughput_degradation_over_5_percent` 与 `fairness_risk` 均为 `true`；
- comparison 合同有效，384/384 请求都进入统计，没有 invalid、unmapped 或剔除样本。

因此，`prompt-length-v1` 在本实验中**没有证明收益，且观察到明显退化与高重复间波动**。这是一个有效的负结果，不应改写或隐藏。

该结论只适用于本固定实验。Candidate run 1 为 `751.922572` Output Token/s，而 run 2/3 为 `559.279522`、`565.091133`，所以 `n=3` 不足以把均值差解释为稳定、普遍或统计显著的因果效应。下一步应解释这种分化及 Queue Time 与 TTFT 的关系，而不是立即增加新策略。

## 实验与汇总身份

| 项目 | 固定事实 |
| --- | --- |
| Comparison group | `prompt-length-20260727-a` |
| Raw experiment | `NSL-S3-SCHED-v1` |
| Raw source commit | `42cb476df358718b548aacc61f11487af2fa6615` |
| Raw evidence PR / merge | [PR #32](https://github.com/NEVER-AGAIN-RAY/NanoServeLab/pull/32) / `2cd80a804fba9a3a29d3405937436916cd19775f` |
| Workload | `NSL-S2-SAT-v1`；manifest `aa1d4e345e0e9f599bd43093bd5b9214476aa3145ee910cc9137d0b62754767d` |
| Model | `Qwen/Qwen3-0.6B`；revision `c1899de289a04d12100db370d81485cdf75e47ca` |
| 正式运行环境 | Python 3.12.3；PyTorch 2.4.0+cu124；CUDA 12.4；RTX 4060 Laptop GPU |
| Engine 固定项 | eager=false；model len 4,096；max seqs 512；max batched tokens 16,384；GPU memory 0.9；TP 1；KV block 256 |
| Aggregator | `NSL-S3-AGG-v1` |
| Aggregate 创建时间 | `2026-07-27T13:53:40.714630+00:00` |
| 分析源码 | clean `main` `2cd80a804fba9a3a29d3405937436916cd19775f` |
| 分析机器 | MacBook M4；macOS 15.5 (`24F74`)；arm64 |
| 分析 Python | Python 3.14.6 |
| CUDA / 模型执行 | 未运行；本步骤只读六份既有 raw |

正式 aggregate 是对此前不存在文件的唯一成功写入：

```text
results/raw/stage3/aggregation/prompt-length-20260727-a/aggregate.json
```

## 完整性计数

| Policy | Runs | Total | Finished | Valid | Invalid | Unmapped | Short / Long |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `fcfs-v1` | 3 | 192 | 192 | 192 | 0 | 0 | 144 / 48 |
| `prompt-length-v1` | 3 | 192 | 192 | 192 | 0 | 0 | 144 / 48 |

comparison 的 Policy/run 矩阵、创建时间顺序、唯一 run ID、repository、environment、model、fixed engine 和 workload 兼容性全部通过，`comparison.valid=true`。

## 吞吐结果

| Policy | Run | Window (s) | Request/s | Output Token/s |
| --- | ---: | ---: | ---: | ---: |
| FCFS | 1 | 7.575914112 | 8.447825 | 743.408639 |
| FCFS | 2 | 7.566214075 | 8.458656 | 744.361704 |
| FCFS | 3 | 7.534132347 | 8.494674 | 747.531333 |
| Candidate | 1 | 7.490132904 | 8.544575 | 751.922572 |
| Candidate | 2 | 10.070098714 | 6.355449 | 559.279522 |
| Candidate | 3 | 9.966534023 | 6.421490 | 565.091133 |

| Policy / Metric | n | Mean | Sample SD | Median | Min | Max | P50 | P95 | P99 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| FCFS Request/s | 3 | 8.467052 | 0.024527 | 8.458656 | 8.447825 | 8.494674 | 8.458656 | 8.494674 | 8.494674 |
| FCFS Output Token/s | 3 | 745.100559 | 2.158375 | 744.361704 | 743.408639 | 747.531333 | 744.361704 | 747.531333 | 747.531333 |
| Candidate Request/s | 3 | 7.107171 | 1.245266 | 6.421490 | 6.355449 | 8.544575 | 6.421490 | 8.544575 | 8.544575 |
| Candidate Output Token/s | 3 | 625.431076 | 109.583382 | 565.091133 | 559.279522 | 751.922572 | 565.091133 | 751.922572 | 751.922572 |

`n=3` 时 nearest-rank P95/P99 等于最大值，不能把它们解释为跨运行的稳定尾分布。Candidate run 1 与 run 2/3 的分化被完整保留。

## 请求级延迟结果

除 Mean TPOT 为 ms/Token 外，其余单位为 ms。以下表格完整列出 aggregate 的 all / short / long 统计。

### FCFS

| Group / Metric | n | Mean | Sample SD | Median | Min | Max | P50 | P95 | P99 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| All Queue Time | 192 | 296.667415 | 456.966778 | 0.820604 | 0.529346 | 1044.560714 | 0.819289 | 1044.463560 | 1044.552105 |
| All TTFT | 192 | 1119.893487 | 191.805556 | 1044.455228 | 968.504479 | 1454.920367 | 1044.454002 | 1454.900627 | 1454.919530 |
| All Mean TPOT | 192 | 34.859416 | 7.673012 | 41.705101 | 24.000292 | 42.203856 | 41.704577 | 42.199584 | 42.202030 |
| All E2E | 192 | 3612.990249 | 2283.862149 | 2316.168623 | 2261.194135 | 7575.504763 | 2287.591857 | 7575.245898 | 7575.483705 |
| Short Queue Time | 144 | 291.472798 | 455.009135 | 0.817584 | 0.529346 | 1044.552105 | 0.815879 | 1044.452703 | 1044.542892 |
| Short TTFT | 144 | 1117.741819 | 191.015933 | 1044.449861 | 968.504479 | 1454.909910 | 1044.447960 | 1454.899506 | 1454.908926 |
| Short Mean TPOT | 144 | 38.071751 | 6.072973 | 41.714521 | 28.491090 | 42.203856 | 41.713937 | 42.199677 | 42.202030 |
| Short E2E | 144 | 2297.966112 | 35.029610 | 2287.445646 | 2261.194135 | 2345.194183 | 2287.443494 | 2345.148993 | 2345.183890 |
| Long Queue Time | 48 | 312.251267 | 467.293085 | 0.836488 | 0.560057 | 1044.560714 | 0.829349 | 1044.475238 | 1044.560714 |
| Long TTFT | 48 | 1126.348491 | 196.048727 | 1044.473342 | 968.545510 | 1454.920367 | 1044.466649 | 1454.917223 | 1454.920367 |
| Long Mean TPOT | 48 | 25.222409 | 0.763006 | 25.611757 | 24.000292 | 25.829103 | 25.611682 | 25.828770 | 25.829103 |
| Long E2E | 48 | 7558.062662 | 18.094838 | 7565.557461 | 7533.058107 | 7575.504763 | 7565.541081 | 7575.458836 | 7575.504763 |

### Prompt length

| Group / Metric | n | Mean | Sample SD | Median | Min | Max | P50 | P95 | P99 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| All Queue Time | 192 | 162.767946 | 531.478696 | 0.905662 | 0.342487 | 2295.519990 | 0.905092 | 1890.856368 | 2295.462530 |
| All TTFT | 192 | 1786.614077 | 589.442927 | 1890.712188 | 997.015509 | 2911.707800 | 1890.700950 | 2784.741334 | 2911.693716 |
| All Mean TPOT | 192 | 46.168794 | 13.093134 | 46.710967 | 23.998301 | 62.974163 | 40.731293 | 62.973604 | 62.974101 |
| All E2E | 192 | 4801.551681 | 2685.094164 | 3885.581219 | 2259.685602 | 10069.705516 | 3842.966728 | 10069.324960 | 10069.672251 |
| Short Queue Time | 144 | 0.810280 | 0.240886 | 0.826071 | 0.342487 | 1.299945 | 0.822962 | 1.175084 | 1.246887 |
| Short TTFT | 144 | 1727.698655 | 544.046592 | 1890.607929 | 997.015509 | 2295.502770 | 1890.603598 | 2295.390101 | 2295.454555 |
| Short Mean TPOT | 144 | 52.131577 | 9.120393 | 52.692402 | 40.729280 | 62.974163 | 52.692384 | 62.973721 | 62.974101 |
| Short E2E | 144 | 3343.777534 | 769.782840 | 3842.739977 | 2259.685602 | 3928.912639 | 3842.736300 | 3928.826916 | 3928.878072 |
| Long Queue Time | 48 | 648.640942 | 909.091687 | 1.164775 | 0.754963 | 2295.519990 | 1.146410 | 2295.402682 | 2295.519990 |
| Long TTFT | 48 | 1963.360345 | 684.730066 | 1891.072189 | 997.880072 | 2911.707800 | 1891.063998 | 2911.670122 | 2911.707800 |
| Long Mean TPOT | 48 | 28.280446 | 2.800623 | 28.566074 | 23.998301 | 32.073016 | 28.566007 | 32.072783 | 32.073016 |
| Long E2E | 48 | 9174.874121 | 1205.139063 | 9965.787465 | 7489.059227 | 10069.705516 | 9965.765650 | 10069.623582 | 10069.705516 |

## Candidate − FCFS

所有百分比均为 `(Candidate − FCFS) / FCFS × 100`；吞吐正值通常更好，延迟负值通常更好。

| Group / Metric | Mean | P95 | P99 | Max |
| --- | ---: | ---: | ---: | ---: |
| All Queue Time | -45.134539% | +81.036126% | +119.755675% | +119.759365% |
| All TTFT | +59.534286% | +91.404229% | +100.127475% | +100.128328% |
| All Mean TPOT | +32.442823% | +49.228021% | +49.220548% | +49.214240% |
| All E2E | +32.896890% | +32.924067% | +32.924479% | +32.924549% |
| Short Queue Time | -99.722005% | -99.887493% | -99.880628% | -99.875550% |
| Short TTFT | +54.570458% | +57.769667% | +57.773075% | +57.776283% |
| Short Mean TPOT | +36.929810% | +49.227971% | +49.220548% | +49.214240% |
| Short E2E | +45.510307% | +67.529949% | +67.529638% | +67.530376% |
| Long Queue Time | +107.730443% | +119.766118% | +119.759365% | +119.759365% |
| Long TTFT | +74.311979% | +100.126170% | +100.128328% | +100.128328% |
| Long Mean TPOT | +12.124289% | +24.174642% | +24.173943% | +24.173943% |
| Long E2E | +21.391877% | +32.924273% | +32.924549% | +32.924549% |

Short Queue Time 大幅下降但 TTFT、TPOT 和 E2E 上升，说明“更早第一次被 Scheduler 选中”不等于“更早产生首个输出”。在 saturated admission、Prefill 批预算、Chunked Prefill、KV 分配和 Decode 共享条件下，只优化 waiting 排序键不足以保证端到端收益。

## 预声明警戒与最坏请求

- `throughput_degradation_over_5_percent=true`；
- `fairness_risk=true`；
- 12 个 fairness item 全部来自 short / long 的 TTFT、E2E P95/P99/max 上升；
- 没有 incomplete、invalid 或 other-class 风险项。

最坏 E2E：

| Policy | Class / index | Run | E2E |
| --- | --- | ---: | ---: |
| FCFS | long / 1 | 1 | 7,575.504763 ms |
| Candidate | long / 1 | 2 | 10,069.705516 ms |

最坏 TTFT：

| Policy | Class / index | Run | TTFT |
| --- | --- | ---: | ---: |
| FCFS | long / 53 | 1 | 1,454.920367 ms |
| Candidate | long / 41 | 3 | 2,911.707800 ms |

## 独立验证与证据

不导入项目 aggregation 实现的标准库脚本重新计算：

- 384 个请求的 Queue Time、TTFT、Mean TPOT、E2E；
- all / short / long 分组；
- mean、sample SD、median、min、max、nearest-rank P50/P95/P99；
- 六个 measurement window 与每次吞吐；
- 两个 Policy 的跨 run 汇总和 Candidate − FCFS 差值；
- 5% 吞吐警戒与 12 个公平性 item。

所有 Policy 统计、吞吐差值和 warning 与 `aggregate.json` 一致；补充校验又逐字段核对 96 个 latency delta 及全部 count delta。随后使用相同 `created_at_utc` 重放合并后的聚合器，`replay.json` 与正式 aggregate 字节完全相同；再次指向既有 `aggregate.json` 时退出并拒绝覆盖，拒绝前后哈希不变。

| Artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| `aggregate.json` | 51,275 | `2f1408c4c265962c5ec6a9ebd3628248f63d77f1b0e4662781d8d8d9371a51b7` |
| `independent-validation.json` | 12,355 | `dacd92c1c90b3beea5d10ea676a03ffa19bb1a712d64b7a4fb3a9230ff3b74d6` |
| `independent-delta-validation.json` | 336 | `5d7ffcad1b7c38d8f5659cff5c6cdef40335cee0d7ef06b7ead357604657ff97` |
| `replay.json` | 51,275 | `2f1408c4c265962c5ec6a9ebd3628248f63d77f1b0e4662781d8d8d9371a51b7` |
| `overwrite-rejection.log` | 82 | `e6f83b1da9f2417073cac9613c6b64e3a7754111faebb36baeb52c8f7a2e9f55` |
| `validation-notes.log` | 817 | `0fb14dfdf515ceffeaa584e548df54a83b6accabdaac9f48a162bcd4f34b0932` |

六项证据按 `SHA256SUMS` 全部通过；清单自身 SHA-256：

```text
c38101abca87100a0bf04bcf30a33aebb3a07def74fdf31489b928e0692d9f67
```

aggregation 前后正式 raw 的 14 项原始清单再次全部通过，原始证据没有变化。

## 命令纠正

1. 第一次 CLI help 检查仍位于 raw 证据子目录，Python 找不到仓库根目录的 `research/stage3_scheduling_aggregate.py`，在创建输出目录和读取 raw 前停止。纠正工作目录后才发生唯一一次正式 aggregate 写入。
2. 第一次确定性重放从 `/private/tmp` 启动，缺少仓库根目录 import path，在创建 replay 前停止。显式设置 `PYTHONPATH` 后，成功 replay 与 aggregate 字节一致。

两次错误都没有修改 raw、覆盖 aggregate、运行模型或触发 CUDA。

## 解释与结论边界

- 这是一轮完整独立研究的有效负结果：问题、合约、实现、真实运行、raw、聚合、独立复算和诚实结论均已形成闭环。
- 结果反驳了“总 Prompt 更短或短请求更早入队就必然改善 TTFT”的简单假设。Scheduler 的第一次选中、Chunked Prefill、批内共享和 Decode 完成必须结合解释。
- Candidate 的高重复间波动是必须保留的事实。当前没有 GPU 温度、功耗或时钟连续记录，也没有 step-level 正式 trace，不能把 run 1 与 run 2/3 的分化归因到某个具体机制。
- pooled 192-request percentile 描述本次三个共享执行上下文的样本，不是置信区间；`n=3` 不支持统计显著性或跨机器、模型、负载的普遍结论。
- 阶段 2 mixed baseline 与本实验使用不同 commit、driver 身份和运行批次，不应跨实验直接宣称退化。
- 在解释首轮结果前，不新增 Priority、Aging 或 Prefix Cache 感知策略，也不为了得到“更好看”的结果更换 workload、删除 Candidate run 2/3 或补跑替代。

## 下一门槛

先审阅并合并本正式 aggregate 结果。随后使用现有 raw 与 Scheduler 行为知识做一次只读机制复盘，重点回答：

1. 为什么 short Queue Time 几乎归零，但 short TTFT 和 E2E 反而上升；
2. Candidate run 1 与 run 2/3 的窗口差异来自可观察的哪一阶段；
3. 现有 raw 能回答到什么程度，哪些问题必须通过预先声明的新 trace 实验才能回答。

完成该理解门槛前，不实现下一种调度策略。
