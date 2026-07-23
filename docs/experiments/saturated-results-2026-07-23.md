# 阶段 2：正式 Saturated 实验原始结果验收

本文固定 2026-07-23 在 WSL2 / RTX 4060 上完成的三次正式 `NSL-S2-SAT-v1` 原始运行与验收事实。本文只确认实验身份、原始记录完整性、saturated admission、双端备份和已知限制；尚未执行 Queue Time、TTFT、TPOT、E2E、throughput 或 percentile 聚合，也不产生性能提升结论。

## 实验身份

| 项目 | 固定事实 |
| --- | --- |
| Workload | `NSL-S2-SAT-v1` |
| Source commit | `69c88c252e09bd5d4ffad434c525647d9bf4f207` |
| WSL branch | `codex/wsl-stage2-formal-20260723`，tracked worktree clean |
| Manifest SHA-256 | `aa1d4e345e0e9f599bd43093bd5b9214476aa3145ee910cc9137d0b62754767d` |
| 模型 | `Qwen/Qwen3-0.6B` |
| 模型 revision | `c1899de289a04d12100db370d81485cdf75e47ca` |
| 权重 | 1,503,300,328 Bytes；SHA-256 `f47f71177f32bcd101b7573ec9171e6a57f4f4d31148d38e382306f42996874b` |
| 运行环境 | Ubuntu 24.04.4；Python 3.12.3；PyTorch 2.4.0+cu124；CUDA 12.4；RTX 4060 Laptop GPU；driver 555.97 |
| 重复规则 | run 1、2、3 各使用一个全新 Python 进程和独立目录，串行执行；没有重跑或替换 |
| 聚合状态 | 未执行 |

证据目录：

- WSL：`/home/lei/NanoServeLab/results/raw/stage2/saturated/formal-NSL-S2-SAT-v1-20260723-69c88c2/`
- Mac Git 忽略备份：`results/raw/stage2/saturated/formal-NSL-S2-SAT-v1-20260723-69c88c2/`

## 运行前门槛

- WSL 通过 GitHub fetch 同步到精确 `origin/main` `69c88c252e09bd5d4ffad434c525647d9bf4f207`，在新分支运行；开始前 tracked worktree clean。
- GPU 查询没有 compute process；根文件系统约 947 GiB 可用。
- 10 个 Hugging Face download metadata 文件的 revision 全部为 `c1899de289a04d12100db370d81485cdf75e47ca`；权重大小与 SHA-256 与既有记录一致。
- 冻结 manifest 重算结果与预期一致。
- WSL 完整单元测试 `Ran 47 tests in 0.307s / OK`。
- `py_compile`、CLI `--help`、fresh import 不加载 torch、`git diff --check` 与 Git clean 检查通过。

第一次 preflight 在模型运行前因审计命令使用了不存在的 helper 名 `build_saturated_workload` 而停止；实际公开 helper 为 `build_saturated_mixed_workload`。同一命令中的 metadata count 因过度转义误显示为 0，但随后 revision 扫描已列出 10 个文件。原 `preflight-environment.log` 未被覆盖；纠正后的 helper、metadata count、manifest、47 tests 和静态门槛分别保存在 `preflight-correction.log`、`unit-tests.log` 与 `static-preflight.log`。此次失误没有启动 driver，也没有生成或替换正式 raw。

## 三次原始运行

三次均为 `status=finished`、driver 退出码 0、`cuda_synchronized=true`；每次包含 64 个 measured request、48 short / 16 long、22,528 Prompt Token、5,632 requested Output Token 和 5,632 actual Output Token。全部请求 `outcome=finished`，`unmapped_timing_records=[]`。

| Run | Run ID | Raw JSON | Bytes | Raw SHA-256 |
| ---: | --- | --- | ---: | --- |
| 1 | `f7e448ec-df29-4134-a63d-b521ac30a2de` | `saturated-20260723T130235.305518Z-run1.json` | 28,876 | `8ee9f9fc7879bbae94058804ea721853d5624eda3c4080cf67ba04fffe2c5a46` |
| 2 | `9d2563e9-a62f-4aab-a5cf-82d1c6f0ef27` | `saturated-20260723T130555.925041Z-run2.json` | 28,876 | `426416c8a4937e6475a20d1bd099148cdbcabb1b45a37a2d6ace4f9a0034e887` |
| 3 | `908f9e6f-cf7f-45cd-bbb4-31ef74b171ee` | `saturated-20260723T130801.174121Z-run3.json` | 28,876 | `298615cf49ad7fdede5d1b8b3820ae759e3f894b2f7bc119e426c5743a04005e` |

原始计量边界与 admission 证明：

| Run | `measurement_started_ns` | `max(arrival_ns)` | `min(first_scheduled_ns)` | `measurement_ended_ns` |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 1,976,590,801,115 | 1,976,591,441,548 | 1,976,591,660,301 | 1,983,405,852,702 |
| 2 | 2,185,021,255,859 | 2,185,021,895,050 | 2,185,022,131,736 | 2,191,532,239,174 |
| 3 | 2,321,743,293,655 | 2,321,744,001,622 | 2,321,744,235,919 | 2,328,259,579,624 |

每次均满足：

```text
measurement_started_ns
<= max(arrival_ns)
<= min(first_scheduled_ns)
<= measurement_ended_ns
```

其中 `max(arrival_ns) <= min(first_scheduled_ns)` 证明 64 个 measured `add_request` 全部完成后才发生第一次调度。

## 独立审计与封存

Git 忽略证据中的 `validate_formal.py` 只依赖 Python 标准库，逐次验证：

- schema v1、实验 ID、run number、唯一 run ID、finished/error 终态；
- 精确 commit、Git clean、CUDA / PyTorch / GPU、模型与 engine 固定字段；
- workload seed、sampling seed、64 请求、manifest 和固定类别顺序；
- warmup 与 measured records 隔离；
- `request_index ↔ seq_id` 完整且进程内唯一；
- 每条请求的类别、Prompt / requested Output / actual Output Token；
- `arrival <= first_scheduled <= first_output <= completed`；
- measurement 起止边界与 saturated admission；
- raw JSON 不含 Queue Time、TTFT、TPOT、E2E、throughput、percentile 等派生或聚合字段。

跨 run 审计确认三次固定环境、模型、引擎、workload 与 warmup 参数一致，三个 run ID 唯一；`formal-validation.json` 为 `validation=passed` 且明确记录 `aggregation_performed=false`。

第一次 run 1 快速校验错误地要求 `repository` 对象只能包含 `commit` 与 `dirty`，但 schema 合法地还包含 `branch`，因此断言失败。原失败说明保存在 `run1/quick-validation-attempt.log`；随后仅修正验证假设并重读同一份 raw，通过后保存为 `run1/quick-validation.log`。没有重跑 run 1。

第一次 postflight 展示命令因模式被过度转义，把 driver 退出码 0 数量和 raw 数量误显示为 0；同一 shell 中未过度转义的硬门槛实际已要求两者都为 3。原 `postflight.log` 保留，正确计数、原因、Git clean 和 GPU 无残留 compute process 另存于 `postflight-correction.log`。

三份完整 `driver.log` 的异常扫描没有匹配 `Traceback`、Runtime/CUDA OOM、warning、Dynamo/cache limit 或 NaN/Inf。证据目录的 `SHA256SUMS` 已在 WSL 自校验，再复制到 Mac；Mac 按同一清单逐文件复验全部通过。最终 `SHA256SUMS` 自身 SHA-256 为：

```text
f64d4f4e09851354ad94cdfeb9ca79fb4bdac9a7fc09854163a4e3c16738921d
```

首次 Mac 复制因目标父目录尚不存在而在写入目标前失败；创建 Git 忽略的 `results/raw/stage2/saturated/` 父目录后完成一次复制与全清单验证，没有覆盖既有实验目录。

## 有效性与限制

- 本组满足冻结 workload、三个全新进程、原始 JSON、完整 stdout/stderr、独立验证和双端备份门槛。
- 本文没有运行聚合器，也没有从 raw 计算或发布 Queue Time、TTFT、TPOT、E2E、throughput、percentile、均值或标准差。
- 三次运行前后记录了 GPU memory、温度和功耗快照，但没有连续采样热状态、时钟或整机功耗；后续解释结果时必须保留该限制。
- 运行只覆盖当前 WSL2 / RTX 4060 / Qwen3-0.6B / `69c88c2` / `NSL-S2-SAT-v1` 条件，不能外推为其他硬件、模型、workload 或调度策略的结论。
- 当前仍只有 baseline scheduler；没有对照调度策略，不能声称性能提升。

## 下一门槛

三份正式 raw 已独立验证并双端备份，因此下一唯一小切片可以开始实现离线 schema v1 aggregation：

- 只读取原始 JSON，不修改 Scheduler、driver、`bench.py` 或冻结 workload；
- 复用 `derive_request_metrics()` 重算每请求 Queue Time、TTFT、E2E 与 Mean TPOT；
- 按 `docs/experiments/metrics.md` 固定 outcome/invalid 计数、吞吐窗口、sample SD 与 nearest-rank P50/P95/P99；
- 用确定性 CPU fixture 测试单 run 与三 run 汇总、空值、小样本和拒绝混组；
- 在聚合实现与测试审查通过前，不发布性能数字或结论。

## 后续完成

上述门槛随后由 [PR #20](https://github.com/NEVER-AGAIN-RAY/NanoServeLab/pull/20) 的 `NSL-S2-AGG-v1` 完成并以 merge commit `a8c2efc0f14901b462a346354c134f3642b448a3` 进入 `main`。三份 raw 的正式只读汇总、独立复算、派生证据哈希、完整统计与限制见 [`saturated-aggregation-results-2026-07-23.md`](saturated-aggregation-results-2026-07-23.md)；原始 JSON 未被回填或修改。
