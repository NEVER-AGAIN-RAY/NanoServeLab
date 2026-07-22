# NanoServeLab 项目导航

> 新对话、新 AI 或中断恢复时先读本文件。它是“当前做到哪里、正在做什么、下一步做什么”的唯一事实入口。

- 最后核对日期：2026-07-22（Asia/Shanghai）
- 当前阶段：阶段 2——指标与混合负载；最小 timing record + 可选 LLMEngine 接线已通过 Mac 与 WSL2/CUDA 验证，尚未合并
- 当前主线：合约已在 `main`；Draft PR #11 的真实 `LLM`、Prefill/Decode、`max_tokens`、受控 EOS、默认关闭和三次 on/off 独立进程冒烟均通过，原始 JSON 与书面记录已归档
- 基线结果：1014.433126 ± 4.212859 output Token/s（mean ± sample SD，`n=3`）；这是当前固定条件的参考值，不是性能提升结论
- 阶段 2 状态：未完成；本切片只交付原始生命周期记录与正常引擎入口，不含指标聚合、混合 workload 或 benchmark

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

- `main` 已包含项目导航、中文核心模块导读、Scheduler 生命周期测试和结构化 Step Snapshot；精确 SHA 应通过实时 Git 检查获取，避免状态文档在自身提交后立即过时。
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

- [PR #8](https://github.com/NEVER-AGAIN-RAY/NanoServeLab/pull/8) 已于 2026-07-22 合并到 `main`，merge commit 为 `a367963`；指标边界合约已就绪。
- 独立分支 `cursor/stage2-request-timing-core`（Draft [PR #11](https://github.com/NEVER-AGAIN-RAY/NanoServeLab/pull/11)）已实现：Scheduler 级 `RequestTimingRecorder`；`snapshots()` 按 `seq_id` 升序返回不可变 tuple；`LLMEngine` / `LLM` 接受显式 keyword-only `timing_recorder=None`，同一对象原样传给 Scheduler；不进入 Config，无额外布尔开关。
- Mac 轻量 package bootstrap 已验证 recorder / Scheduler / bench CPU 语义与 `py_compile`；WSL2 精确提交 `e0914e2` 的完整 18 项单元测试通过，真实 Qwen3-0.6B `LLM(..., timing_recorder=...)`、CUDA Graph、Prefill/Decode、单/多 Token 与 `max_tokens` 路径成功。
- 受控 EOS 用真实采样 Token 作为测试哨兵，在 `max_tokens=8` 前经 EOS 分支完成；它不冒充模型自然生成 tokenizer EOS。recorder on/off 行为进程与 3×on、3×off 冒烟的输出 Token 哈希均一致，所有 timing 记录齐全且单调。
- 3 次 on 与 3 次 off 小 workload 的成对差值方向不一致；只能结论为未观察到一致的异常级退化，不能声称 recorder 加速、零开销或得到正式性能结果。完整方法、原始值、SHA-256 与限制见 `docs/experiments/timing-validation-2026-07-22.md`。
- `docs/experiments/metrics.md` 仍是公式与事件边界的稳定合约；本切片只保存原始时间戳与 Token 计数，不计算 Queue Time、TTFT、TPOT、E2E 或 percentile。

### 环境与阻塞

- Mac 只用于开发、轻量检查、数据分析和文档；不得在仓库根目录运行 `uv sync`，也不安装 CUDA-only 依赖。
- Windows WSL2 readiness 已通过，精简环境事实记录于 `environment/wsl2.md`。
- 此前 `nvidia-smi: command not found` 已确认为 PATH 问题：工具实际位于 `/usr/lib/wsl/lib/nvidia-smi`，GPU、驱动与 PyTorch CUDA 均正常，不需要修改系统配置。
- 阶段 1 已完整交付，没有遗留运行阻塞；WSL 直连 GitHub HTTPS 曾暂时超时，但正式实验所需 commit 已通过 Mac 的验证 bundle 同步。
- 三次 measured workload 均出现 PyTorch Dynamo `accumulated_cache_size_limit (256)` 警告，但都正常完成；本轮没有为了改善数字而改变 cache limit。运行期间未连续记录温度、功耗或时钟，stdout/stderr 也未单独归档，这些限制已写入正式实验记录。
- WSL 直连 GitHub fetch 本轮仍未成功；使用 Mac 生成并验证的最小 Git bundle 将 PR #11 精确提交同步到独立 WSL 验证分支，没有改动旧 baseline 分支。该网络问题未阻塞 CUDA 验收。
- 当前有可复现的参考 baseline 和通过真实 CUDA 路径的原始 timing 记录层，但没有阶段 2 混合 workload、派生指标实验或性能提升结论。

## 全局决策：下一实现目标

### 目标名称

**Pure per-request metric derivation**

### 为什么现在做

可选 `timing_recorder` 已接入 `LLMEngine`，`snapshots()` 提供可枚举不可变入口，真实 WSL2/CUDA 事件边界和默认关闭行为已经验证。下一最小切片应保持运行时只记录原始事实，在独立纯函数层把单条不可变 record 转换为 Queue Time、TTFT、TPOT 和 E2E；先固定错误/空值语义，再进入混合 workload。

### 本轮要回答的问题

- 如何让派生层只读取 `RequestTimingRecord`，不回写或复制修改原始时间戳；
- 如何明确区分成功记录、缺失事件、乱序时间戳和无效 Token 计数；
- 如何按合约处理单 Token 请求的 TPOT `null`，并统一纳秒到毫秒的转换；
- 如何用 fake records 做完全确定的 CPU 测试，不依赖 CUDA 或 wall-clock。

### 明确范围

下一切片只实现单请求派生值和 CPU 测试：

- 不修改调度策略、优先级、KV Cache 分配或 Prefix Cache 行为；
- 不在 Scheduler 或 recorder 内保存派生指标；
- 不实现聚合 percentile、吞吐、混合到达 workload、JSONL、数据库、Dashboard 或可视化；
- 不重新运行已经通过且相关代码未变化的 CUDA 验收，不给出性能结论。

### 完成标准

- 完整成功记录可重算 Queue Time、engine-side TTFT、E2E 和 Mean TPOT；
- `output_tokens == 1` 时 TPOT 明确为 `None`，`output_tokens <= 0` 或事件缺失/乱序不能伪造 0；
- 单位转换、公式和无效输入规则均由确定性 CPU 测试固定；
- 原始 `RequestTimingRecord` 保持不可变，阶段 2 仍不被描述为完成。

## 立即下一步

1. 对 Draft [PR #11](https://github.com/NEVER-AGAIN-RAY/NanoServeLab/pull/11) 的 WSL2 记录提交做最终 GitHub 审阅；行为门槛已通过，可在确认 PR 差异和状态后转 Ready / 合并。
2. PR #11 合并后，从最新 `main` 建立独立分支，实现纯 per-request 指标派生与 CPU 测试。
3. 派生层合并后再冻结 saturated 长短混合 workload 的精确长度、比例、总数和输出格式；不在同一切片并行扩展。

## 已推迟、当前不决策

- Snapshot 是否直接接入 `LLMEngine.step()` 的可选 observer；
- 是否导出 JSONL 作为实验原始 trace，以及长期原始数据的离机归档位置；
- 长短请求的精确长度范围、比例与总请求数；第一版到达模型已固定为 saturated arrival，开放式在线到达留待后续独立切片；
- 第一种自定义调度评分公式；
- 实验结果可视化与论文图表样式。

这些问题在纯 per-request 指标派生完成后再分别决策，当前不提前实现。
