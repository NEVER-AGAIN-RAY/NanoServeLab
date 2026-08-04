# NanoServeLab 项目导航

> 新对话、新 AI 或中断恢复时先读本文件。它是“当前做到哪里、正在做什么、下一步做什么”的唯一事实入口。

- 最后核对日期：2026-08-04（Asia/Shanghai）
- 当前阶段：阶段 3——调度策略比较；第一轮正式对照与只读机制复盘已完整收口，正在冻结最小诊断 trace 合约
- 当前主线：[PR #34](https://github.com/NEVER-AGAIN-RAY/NanoServeLab/pull/34) 已以 merge commit `9aa2106` 合并；Candidate 负结果与现有证据边界已固定，当前独立分支只定义 `NSL-S3-DIAG-TRACE-v1`，不插桩或运行新实验
- 基线结果：1014.433126 ± 4.212859 output Token/s（mean ± sample SD，`n=3`）；这是当前固定条件的参考值，不是性能提升结论
- 阶段 2 mixed baseline：851.900666 ± 22.081773 output Token/s（mean ± sample SD，`n=3`，`NSL-S2-SAT-v1`）；与阶段 1 workload 不同，不能直接比较
- 阶段 2 状态：已完成；指标、workload、driver、正式 `n=3` raw、aggregation、独立复算和固定结果记录均已交付

## 60 秒恢复流程

1. 阅读仓库根目录的 `AGENTS.md`，确认开发、环境和实验约束。
2. 阅读本文件的“当前状态”和“下一实现目标”。
3. 执行只读检查，确认当前分支、工作区以及相关 PR 的实时状态。
4. 只打开当前目标直接引用的代码、测试或文档，不重新进行已经完成且未失效的源码分析。
5. 开始改动前确认范围仍属于当前阶段，并保持独立分支、小提交和可验证测试。

## 文档地图与维护规则

| 文档 | 职责 | 更新方式 |
| --- | --- | --- |
| `docs/project/README.md` | 当前阶段、已验证进度、活动工作、阻塞和唯一下一目标 | 状态变化时直接更新，旧状态应被替换而不是继续堆叠 |
| `docs/project/CHARTER.md` | 稳定的研究问题、阶段路线、项目边界和完成标准 | 仅在项目方向或阶段定义发生变化时更新 |
| `docs/project/PROJECT_LOG.md` | 已发生的重要事件、验证结果和决策 | 按日期追加，不承载“当前状态” |
| `docs/experiments/baseline.md` | 阶段 1 固定 workload、seed、warmup、测量与重复实验合约 | 只在实验定义变化时更新 |
| `docs/experiments/baseline-results-2026-07-21.md` | 第一组正式 CUDA baseline 的逐次数据、统计、哈希、有效性与限制 | 作为实验 `NSL-S1-BL-20260721-01` 的固定记录，不覆盖改写为新实验 |
| `docs/experiments/metrics.md` | 阶段 2 的事件边界、指标公式、空值/聚合规则和验证门槛 | 指标语义或实际生命周期事件变化时同步审阅 |
| `docs/experiments/timing-validation-2026-07-22.md` | PR #11 的 WSL2/CUDA 行为、受控 EOS、on/off 冒烟、原始文件哈希和限制 | 固定验证 `NSL-S2-TR-20260722-01`，不覆盖改写为正式 benchmark |
| `docs/experiments/saturated-workload.md` | 阶段 2 第一版 saturated 长短混合 workload 的请求、顺序、指纹、测量与原始格式合约 | 固定 `NSL-S2-SAT-v1`；改变任一固定项必须使用新 workload ID |
| `docs/experiments/saturated-smoke-validation-2026-07-23.md` | PR #17 的 WSL2/CUDA saturated driver smoke、admission 时间戳证明、原始哈希与限制 | 固定行为门槛，不计入正式三次实验，不产生性能结论 |
| `docs/experiments/saturated-results-2026-07-23.md` | 正式三次 `NSL-S2-SAT-v1` raw、独立审计、哈希、双端备份、验证失误与限制 | 固定原始实验事实；聚合结果另行生成，不回填或改写 raw |
| `docs/experiments/aggregation.md` | 离线 schema v1 aggregation 的兼容键、record 分类、统计规则与输出 schema | 聚合合约变化时更新；不承载正式 raw 数字 |
| `docs/experiments/saturated-aggregation-results-2026-07-23.md` | 三次正式 raw 的 aggregate、独立复算、完整统计、哈希与结论边界 | 固定阶段 2 派生结果；不回填 raw，不作为调度策略提升结论 |
| `docs/experiments/stage3-scheduling-contract.md` | 阶段 3 的 FCFS 身份、单变量策略矩阵、重复运行、指标/公平性和证据边界 | 固定 `NSL-S3-SCHED-v1`；策略定义或实验规则改变时必须版本化 |
| `docs/experiments/stage3-scheduling-raw.md` | 阶段 3 单次运行 CLI、schema v2 Policy/对照组身份、失败证据与防覆盖行为 | raw 合约变化时更新；不写派生指标或正式结果 |
| `docs/experiments/stage3-scheduling-aggregation.md` | 六份 schema v2 raw 的 Policy 分组、兼容键、差值、最坏请求、警戒线与 aggregate 输出 | 固定 `NSL-S3-AGG-v1`；不承载尚未运行的 CUDA 结果 |
| `docs/experiments/stage3-scheduling-smoke-validation-2026-07-27.md` | FCFS/Candidate 真实 CUDA smoke、Policy 身份、Prefill 波次、raw/log/hash 与限制 | 固定行为门槛；不计入正式六进程对照，不产生性能结论 |
| `docs/experiments/stage3-scheduling-results-2026-07-27.md` | 正式六进程 raw、固定顺序、逐次身份、验证、双端哈希与限制 | 固定原始实验事实；不派生指标，不产生性能结论 |
| `docs/experiments/stage3-scheduling-aggregation-results-2026-07-27.md` | 正式 aggregate、完整统计、Policy 差值、警戒、独立复算、哈希与结论边界 | 固定第一轮调度对照结果；保留负结果，不作普遍外推 |
| `docs/experiments/stage3-scheduling-mechanism-review-2026-07-27.md` | Queue/Prefill-to-first-output/完成阶段拆分、批形状、Prefix Cache 排除与证据缺口 | 只读解释现有结果；不冒充因果证明或新实验 |
| `docs/experiments/stage3-diagnostic-trace-contract.md` | 逐 step 分段时钟、批形状、KV/抢占、Runner 路径、telemetry、开销与新诊断身份 | 固定 `NSL-S3-DIAG-TRACE-v1`；字段或事件语义变化必须版本化 |
| `environment/mac.md` | macOS 开发环境事实 | 环境事实变化时更新 |
| `environment/wsl2.md` | WSL2、GPU、CUDA、Python 与模型环境事实 | readiness 或环境事实变化时更新 |
| PR、提交与测试输出 | 具体代码差异和验证证据 | 通过链接或提交号引用，不在文档中复制大段内容 |

维护原则：

- 仓库中只允许本文件描述“当前状态”，避免多份文档互相矛盾。
- 每个阶段只保留一个明确的下一实现目标；其他想法进入“稍后”而不是并行开工。
- 完成任务时，同时更新本文件和项目日志；过时事实应删除、改写或标明验证日期。
- 不把临时聊天交接、机器地址、令牌、密码或大段命令输出提交进仓库。
- benchmark 原始数据保存在 Git 忽略的 `results/raw/` 结构中；状态文档只写结论并链接专门实验记录，不复制整份原始 JSON。

## 当前状态

### 仓库基线

- `main` 已包含项目导航、中文核心模块导读、Scheduler 生命周期测试、结构化 Step Snapshot、阶段 1 baseline、阶段 2 指标合约、request timing 记录层、纯 per-request 指标派生、`NSL-S2-SAT-v1` workload，以及 saturated admission driver 与 schema v1 writer；精确 SHA 应通过实时 Git 检查获取，避免状态文档在自身提交后立即过时。
- 上游基线：`GeeeekExplorer/nano-vllm` 的 `bb823b3`
- `origin` 是 `NEVER-AGAIN-RAY/NanoServeLab`；`upstream` 只用于跟踪官方仓库，禁止推送。
- 根目录 `README.md` 保留上游 nano-vLLM 说明；NanoServeLab 自有状态、实验与环境文档分别放在 `docs/project/`、`docs/experiments/` 与 `environment/`。

### 已验证完成

- 已恢复官方源码、LICENSE 和 Git 历史，并建立 Mac 开发、WSL2 运行的环境分工。
- 已完成 Scheduler、请求生命周期、Prefill/Decode、KV Block 与 Prefix Cache 的中文讲解。
- 已为 13 个核心模块编写中文模块级导读；改动只涉及文档字符串，没有行为变化。
- 已新增一个最小 Scheduler 生命周期测试，覆盖：
  - 两轮 Chunked Prefill；
  - 未完成 Prompt 时丢弃临时采样；
  - `WAITING → RUNNING → FINISHED`；
  - Decode 的一 Token 落后不变量；
  - 达到 `max_tokens` 后释放 KV Block。
- 上述测试已在 Windows WSL2 的既有 Python 3.12.3 `.venv` 中通过：`Ran 1 test / OK`。
- 项目所有者已完成逐段复盘，能够解释最小请求生命周期以及 `num_tokens = num_cached_tokens + 1` 的原因。
- 已完成只读、不可变的 Scheduler Step Snapshot，并在 WSL2 验证原生命周期测试与新 Snapshot 测试共 2 个全部通过。
- 项目所有者已完成 Snapshot 复盘，能够区分实时 Scheduler 状态、历史快照以及 `scheduled_seqs` 在请求离队后的观察作用。

### 已合并里程碑

| 工作项 | 状态 | 证据 | 说明 |
| --- | --- | --- | --- |
| 项目导航与文档治理 | 已合并 | [PR #3](https://github.com/NEVER-AGAIN-RAY/NanoServeLab/pull/3)，merge `9230325` | 统一当前入口、稳定章程和历史日志 |
| Scheduler 生命周期测试 | 已合并 | [PR #2](https://github.com/NEVER-AGAIN-RAY/NanoServeLab/pull/2)，merge `b4da09f` | WSL2 已验证，已成为 `main` baseline |
| 中文核心模块导读 | 已合并 | [PR #1](https://github.com/NEVER-AGAIN-RAY/NanoServeLab/pull/1)，merge `be4506a` | 仅模块级 docstring，无行为变化 |
| Scheduler Step Snapshot | 已合并 | [PR #5](https://github.com/NEVER-AGAIN-RAY/NanoServeLab/pull/5)，merge `2588827` | 只读观察层；WSL2 全部 2 个测试通过 |
| 阶段 1 可复现 nano-vLLM baseline | 已合并 | [PR #7](https://github.com/NEVER-AGAIN-RAY/NanoServeLab/pull/7)，merge `22be4f9` | WSL2 三次独立进程完成；原始 JSON、统计与限制均已归档 |
| 阶段 2 指标边界合约 | 已合并 | [PR #8](https://github.com/NEVER-AGAIN-RAY/NanoServeLab/pull/8)，merge `a367963` | 固定 engine-side TTFT、TPOT、E2E、Queue Time 与验证门槛；无运行时代码 |
| 阶段 2 request timing 记录层 | 已合并 | [PR #11](https://github.com/NEVER-AGAIN-RAY/NanoServeLab/pull/11)，merge `5f72b60` | 默认关闭的原始事件记录；Mac CPU 与 WSL2/CUDA 行为门槛均通过 |
| 阶段 2 per-request 指标派生 | 已合并 | [PR #13](https://github.com/NEVER-AGAIN-RAY/NanoServeLab/pull/13)，merge `5e38dbc` | 纯函数重算 Queue Time、TTFT、E2E、Mean TPOT；33 个 Mac 测试通过 |
| 阶段 2 saturated 混合 workload | 已合并 | [PR #14](https://github.com/NEVER-AGAIN-RAY/NanoServeLab/pull/14)，merge `888aef1` | 所有者确认的 `NSL-S2-SAT-v1` 合约、不可变 manifest 与指纹；36 个 Mac 测试通过 |
| 阶段 2 saturated admission driver | 已合并 | [PR #17](https://github.com/NEVER-AGAIN-RAY/NanoServeLab/pull/17)，merge `f4daf0e` | schema v1 writer、Mac 47 tests、WSL2/CUDA smoke；后续正式 `n=3` 已完成 |
| 阶段 2 offline aggregation | 已合并 | [PR #20](https://github.com/NEVER-AGAIN-RAY/NanoServeLab/pull/20)，merge `a8c2efc` | schema v1 只读汇总、严格输入/输出边界、Mac 68 tests；正式结果另行记录 |
| 阶段 2 formal aggregation results | 已合并 | [PR #21](https://github.com/NEVER-AGAIN-RAY/NanoServeLab/pull/21)，merge `77160a7` | 192/192 valid、独立复算、派生证据哈希与完整结论边界；阶段 2 正式结果 |
| 阶段 3 FCFS 与单变量实验合约 | 已合并 | [PR #23](https://github.com/NEVER-AGAIN-RAY/NanoServeLab/pull/23)，merge `5cf7beb` | 固定 `NSL-S3-SCHED-v1`；后续发现的 running 表述错误已由 PR #24 纠正 |
| 阶段 3 FCFS 多请求特征测试 | 已合并 | [PR #24](https://github.com/NEVER-AGAIN-RAY/NanoServeLab/pull/24)，merge `30beb3d` | 4 个新测试固定 waiting、Prefill、running 稳定队首批次和队尾抢占；Mac 全套 72 tests |
| 阶段 3 显式 Policy 入口 | 已合并 | [PR #25](https://github.com/NEVER-AGAIN-RAY/NanoServeLab/pull/25)，merge `e0a69ab` | Config/Scheduler 显式 `fcfs-v1` 身份、默认等价和未知值拒绝；Mac 全套 74 tests |
| 阶段 3 Prompt 长度策略 | 已合并 | [PR #26](https://github.com/NEVER-AGAIN-RAY/NanoServeLab/pull/26)，merge `0c80123` | recovery prefix 后按 Prompt 长度稳定插入；Mac 全套 77 tests |
| 阶段 3 raw schema 与 driver | 已合并 | [PR #27](https://github.com/NEVER-AGAIN-RAY/NanoServeLab/pull/27)，merge `6b9b4bb` | schema v2 Policy/对照组身份、clean/mismatch 门槛与独占写入；Mac 全套 89 tests |
| 阶段 3 offline Policy aggregation | 已合并 | [PR #28](https://github.com/NEVER-AGAIN-RAY/NanoServeLab/pull/28)，merge `21e3f75` | 严格六 run 对照、差值、最坏请求和预声明警戒线；Mac 全套 103 tests |
| 阶段 3 双 Policy CUDA smoke | 已合并 | [PR #30](https://github.com/NEVER-AGAIN-RAY/NanoServeLab/pull/30)，merge `b330ede` | 两种 Policy 真实 CUDA 路径和行为门槛 |
| 阶段 3 正式六进程 raw | 已合并 | [PR #32](https://github.com/NEVER-AGAIN-RAY/NanoServeLab/pull/32)，merge `2cd80a8` | 384/384 finished、固定顺序、双端 raw/log/hash |
| 阶段 3 首轮正式对照结果 | 已合并 | [PR #33](https://github.com/NEVER-AGAIN-RAY/NanoServeLab/pull/33)，merge `d881f92` | Candidate 负结果、完整统计、独立复算与结论边界 |

### 阶段 1 最终交付

- [PR #7](https://github.com/NEVER-AGAIN-RAY/NanoServeLab/pull/7) 已于 2026-07-22 合并到 `main`，merge commit 为 `22be4f9`；阶段 1 没有剩余代码、实验或文档交付项。
- 已保留官方 `bench.py` 的 synthetic workload 与推理路径，只增加显式实验参数、确定性 workload 构造、单次进程计量、环境元数据和每次运行一个原始 JSON。
- 已补齐显式 Sampling seed（`--sampling-seed`，默认 0）：在创建 `LLM` 之前用 `torch.manual_seed` 与 `torch.cuda.manual_seed_all` 固定采样 RNG 起点，与只固定 synthetic workload 的 `--seed` 分开记录。未修改 `nanovllm/` 核心，未开启 `torch.use_deterministic_algorithms`；不声称所有 CUDA 算子位级确定。
- `docs/experiments/baseline.md` 已固定模型、revision、workload、seed、sampling seed、warmup/测量边界、三次独立进程重复规则、原始结果格式与 WSL2 入口。
- Mac 已通过 benchmark 合约单测、新增 sampling seed 单测、Python 语法检查、CLI `--help` 和 diff whitespace 检查；没有运行模型、CUDA 或 benchmark。
- WSL2 已确认 `/dev/dxg`、RTX 4060、PyTorch CUDA 和既有 `.venv` 可用；全部 9 个测试通过，`enforce_eager=False` 的 `LLM` 初始化、内部 warmup、CUDA Graph 捕获以及 Prefill→Decode 实际成功。
- 2026-07-21 在 clean commit `fb94f6b46213174718c2c89d11c86180712f3b53` 上用三个全新进程完成固定 256 请求 CUDA baseline；三份 schema v1 JSON 的固定字段一致，逐次吞吐为 1019.165630、1013.041928、1011.091819 output Token/s。
- 三份原始 JSON 已保留在 WSL，并备份到 Mac 的 Git 忽略目录；两端 SHA-256 逐一一致。完整方法、逐次数据、统计、workload 指纹、异常观察和结论限制记录在 `docs/experiments/baseline-results-2026-07-21.md`。

### 当前活动工作

- [PR #11](https://github.com/NEVER-AGAIN-RAY/NanoServeLab/pull/11) 已于 2026-07-22 合并到 `main`，merge commit 为 `5f72b60`。它实现 Scheduler 级 `RequestTimingRecorder`；`snapshots()` 按 `seq_id` 升序返回不可变 tuple；`LLMEngine` / `LLM` 接受显式 keyword-only `timing_recorder=None`，同一对象原样传给 Scheduler；不进入 Config，无额外布尔开关。
- Mac 轻量 package bootstrap 已验证 recorder / Scheduler / bench CPU 语义与 `py_compile`；WSL2 精确提交 `e0914e2` 的完整 18 项单元测试通过，真实 Qwen3-0.6B `LLM(..., timing_recorder=...)`、CUDA Graph、Prefill/Decode、单/多 Token 与 `max_tokens` 路径成功。
- 受控 EOS 用真实采样 Token 作为测试哨兵，在 `max_tokens=8` 前经 EOS 分支完成；它不冒充模型自然生成 tokenizer EOS。recorder on/off 行为进程与 3×on、3×off 冒烟的输出 Token 哈希均一致，所有 timing 记录齐全且单调。
- 3 次 on 与 3 次 off 小 workload 的成对差值方向不一致；只能结论为未观察到一致的异常级退化，不能声称 recorder 加速、零开销或得到正式性能结果。完整方法、原始值、SHA-256 与限制见 `docs/experiments/timing-validation-2026-07-22.md`。
- [PR #13](https://github.com/NEVER-AGAIN-RAY/NanoServeLab/pull/13) 已于 2026-07-22 合并到 `main`，merge commit 为 `5e38dbc`。`derive_request_metrics(record) -> RequestMetrics` 以纯函数重算 Queue Time、TTFT、E2E 和 Mean TPOT；单 Token TPOT 为 `None`，缺失/乱序/未完成记录抛 `ValueError`；Mac 共 33 个测试通过。
- [PR #14](https://github.com/NEVER-AGAIN-RAY/NanoServeLab/pull/14) 已于 2026-07-22 合并到 `main`，merge commit 为 `888aef1`。`research/stage2_workload.py` 固定 64 个请求，类别顺序 `[short, long, short, short] * 16`；short 为 128→32 Token（48 个），long 为 1024→256 Token（16 个）；manifest SHA-256 为 `aa1d4e345e0e9f599bd43093bd5b9214476aa3145ee910cc9137d0b62754767d`。
- saturated workload 合约和 3 个确定性 CPU 测试已进入主线；与既有测试合计 36 个全部通过，`py_compile`、指纹重算与 `git diff --check` 通过。未运行 CUDA 或 benchmark，无性能结论。
- 2026-07-22 项目所有者本人明确接受 `NSL-S2-SAT-v1` 的规模、3:1 比例、长度、顺序和 saturated 准入设定。`docs/experiments/saturated-workload.md` 已记录该决策的归属、每组参数决定的实验条件以及未来必须通过新 workload ID 修改的流程；这些设定不代表上游默认值、真实流量或已验证最优值。
- [PR #17](https://github.com/NEVER-AGAIN-RAY/NanoServeLab/pull/17) 已于 2026-07-23 合并到 `main`，merge commit 为 `f4daf0e55ad213093b215fc4fd713b546951609c`。交付 `research/stage2_saturated_driver.py`：固定 warmup、64 次 measured `add_request` 全部先于第一次 `step`、recorder snapshot diff 建立 `request_index↔seq_id`、schema v1 原始 JSON（成功/失败均尽量落盘）。未改 `nanovllm` 核心、`bench.py` 或冻结 manifest。
- Mac 轻量 package bootstrap：driver 与既有测试共 47 个全部通过；`py_compile`、CLI `--help`、fresh subprocess import 不加载 torch、manifest 指纹重算与 `git diff --check` 通过。
- WSL2/CUDA smoke 源码仍是精确提交 `59d4d9a5bc2c550097e77d24b8f75aff6e335454`（smoke 时 PR #17 为 Draft，属历史事实）：47 个测试 OK，一次真实 LLM smoke `status=finished`，`cuda_synchronized=true`，`max(arrival_ns) <= min(first_scheduled_ns)` 证明 saturated admission；原始 JSON / 哈希 / 双端备份见 [`docs/experiments/saturated-smoke-validation-2026-07-23.md`](../experiments/saturated-smoke-validation-2026-07-23.md)。该 smoke 不是正式三次实验，无性能结论；不声称已在 merge commit `f4daf0e` 上跑过模型。
- [PR #18](https://github.com/NEVER-AGAIN-RAY/NanoServeLab/pull/18) 纯文档收口已以 merge commit `69c88c252e09bd5d4ffad434c525647d9bf4f207` 合并；随后 WSL 在该精确 `main` 上通过 Git clean、环境/模型/manifest、47 tests 与静态 preflight。
- 三个全新 Python 进程串行完成正式 `NSL-S2-SAT-v1` run 1、2、3；每次均退出码 0、`status=finished`、64 请求全部完成、actual Output Token 5,632、无 unmapped record、CUDA 双边界同步且全部准入先于第一次调度。没有重跑或替换。
- 三份 schema v1 raw、完整 driver 日志、标准库逐字段/跨 run 审计和纠正日志已保留于 WSL，并备份到 Mac Git 忽略目录；两端按同一 `SHA256SUMS` 全部通过，清单自身 SHA-256 为 `f64d4f4e09851354ad94cdfeb9ca79fb4bdac9a7fc09854163a4e3c16738921d`。完整事实见 [`docs/experiments/saturated-results-2026-07-23.md`](../experiments/saturated-results-2026-07-23.md)。
- 独立分支 `cursor/stage2-offline-aggregation`（基于 `origin/main` `16d4f12`）新增离线 schema v1 aggregation：`docs/experiments/aggregation.md`、`research/stage2_aggregate.py`、`tests/test_stage2_aggregate.py`。只读显式 raw 路径；复用 `RequestTimingRecord` + `derive_request_metrics()`；兼容键/混组拒绝、outcome/invalid 计数、all/short/long 统计、measurement 窗口吞吐与 nearest-rank / sample SD 按冻结合约实现。未改 scheduler、recorder、driver、`bench.py` 或 workload manifest。
- Cursor 初版经独立对抗审查后已修复：failed run 吞吐隔离、严格 JSON integer / 容器校验、冻结 workload 单源身份、重复 request 身份隔离、非法编码与非有限数错误归一、解析 bytes 与 SHA-256 同源、独占创建输出及悬空符号链接拒绝。Mac 轻量 package bootstrap：aggregation 21 个、全套共 68 个测试全部通过；`py_compile`、CLI `--help`、fresh subprocess import 不加载 torch、`git diff --check` 通过。未在三份正式 raw 上运行 aggregation，未发布延迟/吞吐数字，无性能结论。
- [PR #20](https://github.com/NEVER-AGAIN-RAY/NanoServeLab/pull/20) 在 68 tests 与正式 raw 哈希复验后以 merge commit `a8c2efc0f14901b462a346354c134f3642b448a3` 合并；未修改 Scheduler、driver、`bench.py` 或冻结 workload。
- 三份正式 raw 已从合并后的 `NSL-S2-AGG-v1` 只读汇总：192/192 valid finished、0 invalid、0 unmapped；三次 Output Token/s 为 826.406070、864.999913、864.296016，mean ± sample SD 为 851.900666 ± 22.081773。完整延迟、分位数与限制见 [`saturated-aggregation-results-2026-07-23.md`](../experiments/saturated-aggregation-results-2026-07-23.md)。
- 标准库逐字段独立复算、相同创建时间重放、拒绝覆盖、raw/aggregate 哈希回验全部通过；aggregate SHA-256 为 `47d31a4074336ab1bf6d2035e09869776847843fb3c33455c473864cd7debbb8`。
- 正式结果、完整统计、两次命令纠正与结论边界已由 [PR #21](https://github.com/NEVER-AGAIN-RAY/NanoServeLab/pull/21) 以 merge commit `77160a7422dca27a763eb44308bb20c11b91a967` 合并。阶段 2 没有剩余代码、实验或结果文档交付项。
- 阶段 2 完成状态与阶段 3 唯一下一目标由 [PR #22](https://github.com/NEVER-AGAIN-RAY/NanoServeLab/pull/22) 收口；该收口只改状态文档，不实现调度策略。
- [PR #23](https://github.com/NEVER-AGAIN-RAY/NanoServeLab/pull/23) 经远端差异、评论、review、检查和可合并性核对后，以 merge commit `5cf7beb60c2fbf76bb71509de6d1ec2d2b9f8b4c` 合并。合约固定 waiting FCFS、Prefill 优先、抢占回队首、资源不变量、Prompt 长度第一候选、Policy ID 和新 FCFS 对照规则；没有修改 Scheduler、运行 CUDA 或产生策略结果。
- 合并后的多请求定向分析发现合约把 running 错写成“一 Token 轮转”：源码会把入选请求恢复到队首，所以 `running > max_num_seqs` 时实际是稳定队首批次优先。分支 `codex/stage3-fcfs-order-tests` 已纠正文档并新增 4 个确定性 CPU 特征测试，覆盖 waiting/Chunked Prefill/Head-of-Line blocking/Prefill 优先、running 稳定队首批次和 KV 压力下队尾抢占；Mac 轻量全套 72 tests、`py_compile` 与 `git diff --check` 通过，未修改 Scheduler。
- [PR #24](https://github.com/NEVER-AGAIN-RAY/NanoServeLab/pull/24) 经远端范围与 `CLEAN / MERGEABLE` 核对后，以 merge commit `30beb3decd675ef5b240c5edc6bf14b91a5f713e` 合并；FCFS 特征测试和合约纠正进入 `main`。
- 分支 `codex/stage3-policy-entry` 新增轻量 `scheduling_policy` 身份层：Config 增加默认 `fcfs-v1` 字段，Scheduler 对显式值和旧 fake config 缺省值统一规范化；未知策略在调度前抛 `ValueError`。显式和隐式 FCFS 首批调度等价测试通过，尚无长度排序分支；Mac 新增相关测试 6 个、全套 74 tests 与 `py_compile` 通过。
- [PR #25](https://github.com/NEVER-AGAIN-RAY/NanoServeLab/pull/25) 经远端范围与 `CLEAN / MERGEABLE` 核对后，以 merge commit `e0a69abe1eceac55d3188a2c52f652bc116150b2` 合并；显式 Policy 入口进入 `main`。
- 分支 `codex/stage3-prompt-length-policy` 增加 `prompt-length-v1`：fresh waiting 请求在 recovery prefix 后按 `num_prompt_tokens` 升序稳定插入；相同长度保持到达顺序，Chunked Prefill 和被抢占请求保持恢复优先。只修改策略常量和 `Scheduler.add()` 插入路径，不改 `schedule()`、Decode、抢占或 KV；3 个新策略边界测试、相关 9 tests、Mac 全套 77 tests 与 `py_compile` 通过。
- [PR #26](https://github.com/NEVER-AGAIN-RAY/NanoServeLab/pull/26) 经远端范围与 `CLEAN / MERGEABLE` 核对后，以 merge commit `0c80123a3078e59e1a405a417a330efe79c12bbd` 合并；`prompt-length-v1` 第一候选策略进入 `main`。
- 从该合并提交创建独立分支 `codex/stage3-scheduling-driver`：新增 Stage 3 schema v2 外层，复用 Stage 2 saturated admission 核心但不修改阶段 2 raw/aggregator；显式记录 `experiment_contract`、`comparison_group`、版本化 Policy 参数、workload ID 与 requested/actual Scheduler Policy。
- driver 在 warmup 前拒绝缺失 commit、dirty worktree、无法读取 Policy 或请求/实际 Policy 不一致；成功与运行失败 raw 均保留 Stage 3 身份，setup 失败不伪造实际 Policy，mismatch 失败则保留已经读到的实际 Policy。JSON 先完整序列化，再以独占创建写入，文件身份与 artifact 的 group/Policy/run number 必须一致。
- 新增 12 个 Stage 3 driver CPU 合约测试；Mac 轻量全套 89 tests、相关 `py_compile`、fresh import/CLI help 不加载 torch 和 `git diff --check` 通过。没有构造真实 LLM、运行 CUDA 或产生策略结果。
- 上述切片以提交 `19e55788813a813eb651301d157fd3025751e797` 推送并创建 Draft [PR #27](https://github.com/NEVER-AGAIN-RAY/NanoServeLab/pull/27)，目标为 `main`，初始范围为 5 个文件；没有向 `upstream` 写入。
- PR #27 经本地第二轮证据审查和远端范围核对后，GitHub 为 `CLEAN / MERGEABLE`、无评论/review/check，以 merge commit `6b9b4bb1b2478c7ddd05f64b0587a02b053b935d` 合并到 `main`。
- 从该合并提交创建 `codex/stage3-scheduling-aggregate`：只读恰好六份 schema v2 raw，严格要求 FCFS/Candidate 各 run 1–3、同 group/commit/environment/model/fixed engine/workload，并用 UTC 创建时间验证固定执行顺序。Policy 字段是唯一排除的 engine 自变量。
- `NSL-S3-AGG-v1` 为每个 Policy 输出 outcome/invalid/unmapped、all/short/long 延迟、三次吞吐和最坏请求定位；统一计算 candidate−FCFS 绝对/百分比差值，并结构化报告 5% 吞吐退化与完成率/尾延迟公平性风险。任一 run 不满足 64 请求、5,632 Token、CUDA 同步和完整时间事实时保留证据但 comparison 无效、吞吐为 null。
- 新增 14 个 Stage 3 aggregation CPU 合约测试；Mac 轻量全套 103 tests、相关 `py_compile`、fresh import/CLI help 不加载 torch 与 `git diff --check` 通过。没有读取正式 Stage 3 raw、运行 CUDA 或产生策略性能结论。
- 上述切片以提交 `62938a9fd273a4a1f8daff5fd360295970b6088e` 推送并创建 Draft [PR #28](https://github.com/NEVER-AGAIN-RAY/NanoServeLab/pull/28)，目标为 `main`，初始范围为 5 个文件；没有向 `upstream` 写入。
- PR #28 经第二轮边界审查和远端范围核对后，GitHub 为 `CLEAN / MERGEABLE`、无评论/review/check，以 merge commit `21e3f755cb403d5c0fb632cd91676dcee3071753` 合并到 `main`。
- 合并后的 clean `main` 再次通过 Mac 轻量全套 103 tests、Stage 3 相关 `py_compile`、raw driver/aggregator CLI help、fresh import 不加载 torch、冻结 manifest SHA-256 重算和 `git diff --check`；远端没有遗留 open PR，GitHub keyring 登录正常。Mac 可完成的阶段 3 工作至此全部交付。
- 最终状态切换以提交 `8668625164bb0a84c2c8cd27d80eedaac6f3204e` 创建纯文档 Draft [PR #29](https://github.com/NEVER-AGAIN-RAY/NanoServeLab/pull/29)，只把唯一下一目标改为 WSL2 双 Policy CUDA smoke，没有代码、CUDA、raw 或结果改动。
- [PR #29](https://github.com/NEVER-AGAIN-RAY/NanoServeLab/pull/29) 已以 merge commit `a97ec4dc7970cae1c51d094f1c1276ecb0f987fc` 合并。WSL 直连 GitHub fetch 未更新引用，改用 Mac 生成并由两端 SHA-256 验证的完整 Git bundle 同步该精确提交；独立分支 `codex/wsl-stage3-smoke-20260727` 运行前后 clean。
- WSL2 复验 RTX 4060、PyTorch 2.4.0+cu124、CUDA 12.4、Qwen3-0.6B revision/权重和冻结 manifest；完整 103 tests 通过。`fcfs-v1` 与 `prompt-length-v1` 各由一个全新进程完成真实 CUDA smoke，两份 raw 均为 finished、64/64 请求、5,632 Token、requested/actual Policy 一致、`runtime_verified=true`、CUDA synchronized、0 unmapped。
- 独立时间戳审计确认 saturated admission，并识别第一 Prefill 波次：FCFS 为 45 个请求（34 short / 11 long），Candidate 为 58 个请求（48 short / 10 long），与冻结 Policy 和 16,384 Token 预算一致。完整 raw、driver log、preflight/tests、validation 与 `SHA256SUMS` 已双端复验；清单自身 SHA-256 为 `f6499fb6c63f4e91a57eb1e174f0bd6a8c14f5bdc411556adbd4005b1d9eb4bb`。该 smoke 不计入正式六次实验，不产生性能结论。
- [PR #30](https://github.com/NEVER-AGAIN-RAY/NanoServeLab/pull/30) 以 merge commit `b330ede84fc3a155299c252749e3e6dbdb19ac96` 固定 smoke 证据；纯文档 [PR #31](https://github.com/NEVER-AGAIN-RAY/NanoServeLab/pull/31) 以 merge commit `42cb476df358718b548aacc61f11487af2fa6615` 把唯一目标切换为正式六进程对照。
- WSL 通过两端 SHA-256 一致的完整 Git bundle 同步到精确 `42cb476`，重新通过 Git clean、RTX 4060、PyTorch/CUDA、模型 revision/权重、manifest、CUDA Tensor 和完整 103 tests preflight；此前不存在的 comparison group 为 `prompt-length-20260727-a`。
- 六个全新进程严格按 `FCFS-1 → Candidate-1 → Candidate-2 → FCFS-2 → FCFS-3 → Candidate-3` 一次完成，没有失败、重跑、替换或覆盖。六份 raw 均为 64/64 finished、5,632 Token、Policy/runtime verified、CUDA synchronized、0 unmapped；合计 384/384 请求和 33,792 Token。
- 整体审计确认固定顺序和全部兼容键；6 raw、6 完整 driver log、preflight/tests 与 validation 已双端复验，`SHA256SUMS` 自身 SHA-256 为 `04b5570d406a97b9d4ea9e34caba2d85f4b199cd71b5b7aa36eb48ac6bbd708c`。尚未 aggregation，无性能结论。
- [PR #32](https://github.com/NEVER-AGAIN-RAY/NanoServeLab/pull/32) 经远端范围核对后以 merge commit `2cd80a804fba9a3a29d3405937436916cd19775f` 合并；从该 clean main 创建 `codex/stage3-aggregation-results`，复验 14 项 raw 证据后对六份显式输入执行一次正式 `NSL-S3-AGG-v1` 独占写入。
- comparison 有效，FCFS 与 Candidate 均为 192/192 valid、0 invalid、0 unmapped。FCFS Output Token/s 为 `745.100559 ± 2.158375`，Candidate 为 `625.431076 ± 109.583382`；Candidate − FCFS 平均差值 `-16.060850%`，吞吐退化和公平性警戒均为 true。
- 独立标准库重算全部请求指标、吞吐、统计、差值和 12 个 fairness item 均一致，补充校验逐字段覆盖 96 个 latency delta；相同创建时间重放字节一致，既有输出拒绝覆盖。aggregate SHA-256 为 `2f1408c4c265962c5ec6a9ebd3628248f63d77f1b0e4662781d8d8d9371a51b7`，派生证据清单自身 SHA-256 为 `c38101abca87100a0bf04bcf30a33aebb3a07def74fdf31489b928e0692d9f67`。
- [PR #33](https://github.com/NEVER-AGAIN-RAY/NanoServeLab/pull/33) 经远端范围核对后以 merge commit `d881f92675cf69b082f137c91f42cc10b7c7ba1b` 合并；从该 clean main 创建 `codex/stage3-mechanism-review`，只读拆分六份 raw 的 Queue、首次调度→首 Token 和首 Token→完成阶段。
- Candidate 48 个 short 全部进入第一 Prefill 波，所以其 Queue 约 1 ms；该波为 58 请求/16,384 Token，GPU 执行发生在 `first_scheduled` 之后并计入 TTFT。Candidate 三次第一波约 997/1,890/2,294 ms，而 FCFS 固定 45 请求/15,616 Token且约 1,043/978/967 ms。
- workload 的 64 个完整 256-Token Prompt Block 全部唯一，Prefix Cache 命中被排除。Candidate run 2/3 在第二 Prefill 和全部 Prefill 后阶段也变慢；现有 raw 缺少逐 step、KV/preemption 和 GPU telemetry，不能把分化归因到 JIT、kernel、温度、时钟或某个 Scheduler 分支。

### 环境与阻塞

- Mac 只用于开发、轻量检查、数据分析和文档；不得在仓库根目录运行 `uv sync`，也不安装 CUDA-only 依赖。
- Windows WSL2 readiness 已通过，精简环境事实记录于 `environment/wsl2.md`。
- 此前 `nvidia-smi: command not found` 已确认为 PATH 问题：工具实际位于 `/usr/lib/wsl/lib/nvidia-smi`，GPU、驱动与 PyTorch CUDA 均正常，不需要修改系统配置。
- 阶段 1 已完整交付，没有遗留运行阻塞；WSL 直连 GitHub HTTPS 曾暂时超时，但正式实验所需 commit 已通过 Mac 的验证 bundle 同步。
- 阶段 1 的三次 measured workload 均出现 PyTorch Dynamo `accumulated_cache_size_limit (256)` 警告，但都正常完成；当时没有为了改善数字而改变 cache limit。阶段 1 运行期间未连续记录温度、功耗或时钟，stdout/stderr 也未单独归档；阶段 2 正式 `n=3` 已单独保存完整日志，其限制见对应实验记录。
- WSL 直连 GitHub fetch 曾在 2026-07-22 及更早轮次失败，当时用 Mac 生成的最小 Git bundle 同步 PR #11 精确提交；**2026-07-23 PR #17 smoke 轮次 WSL 直连 GitHub fetch 已成功**，不再需要 bundle。此前失败事实保留为历史，不表示当前仍阻塞。
- Mac 的 GitHub 连接已于 2026-07-22 修复并复验：删除未监听的 `127.0.0.1:7897` 全局 Git 代理后，Git HTTPS 与 `gh` 恢复；`ChatGPT Codex Connector` 已安装到 `NEVER-AGAIN-RAY` 且仅授权 NanoServeLab，连接器仓库与 PR 读取通过。完整根因与恢复规则见 `environment/mac.md`。
- 当前已有可复现 baseline、真实 CUDA timing 层、冻结 mixed workload、首个 Candidate 正式负结果和只读机制边界。一次独立研究闭环已经成立。
- 当前阻塞不是代码或环境，而是观察粒度不足：现有四时间戳不能解释相同 Candidate 批形状的跨 run 分化。机制复盘与所有者的最小理解门槛已完成，当前门槛是先审阅合并 trace 合约，再实现只读观察层与 CPU/fake-clock 测试。

## 全局决策：下一实现目标

### 目标名称

**阶段 3 第十三切片：冻结最小 diagnostic trace 合约**

### 为什么现在做

机制复盘已经确认 Queue 改善被首次调度后的 Prefill 与后续成本超过，也排除了本 workload 的 Prefix Cache 共享命中；但现有 raw 没有逐 step 时间、KV/抢占或 Runner 路径。现在先冻结观察问题和证据边界，避免边看结果边增删字段。

### 本轮实现

- 冻结 `NSL-S3-DIAG-TRACE-v1` 的五个诊断问题和逐 step 事件边界；
- 固定分段 host 时钟、队列/批形状、KV/Prefix/抢占、Runner 路径与 Graph bucket 字段；
- 固定 JSONL/raw 写入、10 MiB 单 run 上限、外部 GPU telemetry sidecar 与哈希边界；
- 固定 recorder-off 等价、CPU/fake-clock 测试和 WSL trace-on/off 5% 开销门槛；
- 预留独立 `NSL-S3-DIAG-v1` 身份，但不实现 trace 或运行诊断实验。

### 明确范围

本切片只定义 trace 合约：

- 不修改 Scheduler、ModelRunner、driver、aggregation、模型参数或冻结 workload；
- 两份 smoke 永不计入正式六次实验；
- 不因 smoke 的运行时间或进度显示预判 Policy 性能；
- 不修改、删除、替换或重跑正式 raw/aggregate；
- 不把 JIT、CUDA Graph、温度或 GPU 时钟猜测写成原因；
- 不在合约审阅前插桩或运行新诊断实验；
- 不实现 Priority、Aging 或 Prefix Cache 感知。

### 完成标准

- 合约中的每个字段都对应现有 Scheduler、BlockManager、LLMEngine 或 ModelRunner 的明确事件；
- host wall time、CUDA kernel time 和外部 telemetry 的证据边界不混淆；
- recorder-off 等价、不可变记录、fake clock、写入与开销门槛均可测试；
- 新诊断身份与第一轮正式 raw/aggregate 完全隔离；
- 合约审阅合并后，唯一下一切片切换为 trace recorder 与 CPU 测试实现。

## 立即下一步

1. 审阅 `stage3-diagnostic-trace-contract.md` 的问题、字段、5% 开销门槛和 10 MiB 上限。
2. 创建并合并独立 trace 合约 PR；本 PR 不修改运行时代码或运行实验。
3. 合并后以独立切片实现可选 recorder、事件接线和 CPU/fake-clock 定向测试。

## 已推迟、当前不决策

- Snapshot 是否直接接入 `LLMEngine.step()` 的可选 observer；
- 是否导出 JSONL 作为实验原始 trace，以及长期原始数据的离机归档位置；
- 开放式在线到达、Poisson 或固定速率 workload；
- 第一种自定义调度评分公式；
- 实验结果可视化与论文图表样式。

这些问题在 `prompt-length-v1` 第一轮正式对照和阶段 3 实验证据链收口后再决策，当前不提前实现。
