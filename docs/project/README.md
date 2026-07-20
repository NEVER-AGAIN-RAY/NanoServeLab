# NanoServeLab 项目导航

> 新对话、新 AI 或中断恢复时先读本文件。它是“当前做到哪里、正在做什么、下一步做什么”的唯一事实入口。

- 最后核对日期：2026-07-20（Asia/Shanghai）
- 当前阶段：阶段 0 后半段——Scheduler baseline 理解与可观测性基础
- 当前主线：实现结构化 Scheduler Step Snapshot，再讨论调度策略变化
- 性能结论：无；尚未运行正式 CUDA benchmark

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
| `environment/mac.md` | macOS 开发环境事实 | 环境事实变化时更新 |
| PR、提交与测试输出 | 具体代码差异和验证证据 | 通过链接或提交号引用，不在文档中复制大段内容 |

维护原则：

- 仓库中只允许本文件描述“当前状态”，避免多份文档互相矛盾。
- 每个阶段只保留一个明确的下一实现目标；其他想法进入“稍后”而不是并行开工。
- 完成任务时，同时更新本文件和项目日志；过时事实应删除、改写或标明验证日期。
- 不把临时聊天交接、机器地址、令牌、密码或大段命令输出提交进仓库。
- benchmark 原始数据未来应进入专门的 `results/` 结构，不写进状态文档。

## 当前状态

### 仓库基线

- `main` 已包含项目导航、Scheduler 生命周期测试和中文核心模块导读；精确 SHA 应通过实时 Git 检查获取，避免状态文档在自身提交后立即过时。
- 上游基线：`GeeeekExplorer/nano-vllm` 的 `bb823b3`
- `origin` 是 `NEVER-AGAIN-RAY/NanoServeLab`；`upstream` 只用于跟踪官方仓库，禁止推送。
- 根目录 `README.md` 保留上游 nano-vLLM 说明；NanoServeLab 自有文档统一放在 `docs/project/`。

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

### 已合并里程碑

| 工作项 | 状态 | 证据 | 说明 |
| --- | --- | --- | --- |
| 项目导航与文档治理 | 已合并 | [PR #3](https://github.com/NEVER-AGAIN-RAY/NanoServeLab/pull/3)，merge `9230325` | 统一当前入口、稳定章程和历史日志 |
| Scheduler 生命周期测试 | 已合并 | [PR #2](https://github.com/NEVER-AGAIN-RAY/NanoServeLab/pull/2)，merge `b4da09f` | WSL2 已验证，已成为 `main` baseline |
| 中文核心模块导读 | 已合并 | [PR #1](https://github.com/NEVER-AGAIN-RAY/NanoServeLab/pull/1)，merge `be4506a` | 仅模块级 docstring，无行为变化 |

### 当前活动工作

- 2026-07-20 核对时没有开放 PR。
- 下一实现目标已经确定为“结构化 Scheduler Step Snapshot（第一纵向切片）”，尚未开始代码实现。
- 创建新分支前仍须实时复核 `main` 和 GitHub 状态。

### 环境与阻塞

- Mac 只用于开发、轻量检查、数据分析和文档；不得在仓库根目录运行 `uv sync`，也不安装 CUDA-only 依赖。
- Windows WSL2 既有虚拟环境可以运行 CPU Scheduler 单元测试。
- WSL2 中直接执行 `nvidia-smi` 曾返回 `command not found`。这不阻塞当前 CPU 测试，但在阶段 1 CUDA baseline 前必须单独核查 GPU 驱动暴露与 PATH。
- 当前没有可以报告的 benchmark 结果，也没有性能提升结论。

## 全局决策：下一实现目标

### 目标名称

**结构化 Scheduler Step Snapshot（第一纵向切片）**

### 为什么现在做

生命周期测试已经证明我们能用断言观察最终状态，但下一阶段需要把每一轮调度中的队列、Token 进度与 KV Block 占用变成明确、可复用的数据。先建立只读观察层，可以：

- 把刚掌握的生命周期知识变成可检查的状态快照；
- 为后续 TTFT、TPOT、Queue Time 和调度策略比较建立统一词汇；
- 在修改调度策略前形成回归证据；
- 避免现在就把日志、性能计时或研究策略混进核心 Scheduler。

### 第一切片的成果

新增一个纯读取、不可变的 Scheduler 快照模型，并在 CPU 单元测试中于 `schedule()` 与 `postprocess()` 之后显式采集。建议落点为：

- `nanovllm/engine/scheduler_trace.py`：快照数据结构与纯采集函数；
- `tests/test_scheduler_trace.py`：复用最小生命周期，验证每一阶段的快照内容。

计划中的快照字段：

- Step 级：步骤编号、阶段、Prefill/Decode 模式、已调度请求 ID；
- Queue 级：`waiting` 与 `running` 请求 ID；
- Sequence 级：状态、Prompt/Completion/总 Token 数、已缓存与本轮已调度 Token 数、Block 数；
- KV Block 级：已用 Block ID 的不可变副本、空闲 Block 数。

快照必须复制可变集合为 tuple 等不可变值，避免后续 Scheduler 状态变化反向修改历史快照。状态名称使用稳定、可读的字符串，不直接暴露可变 Enum 或队列对象。

### 明确范围

本切片包含：

- 新增独立的只读快照模块；
- 在测试中手动采集并断言三步生命周期；
- 记录 `WAITING`、Chunked Prefill、`RUNNING`、Decode、`FINISHED` 和 KV Block 释放；
- 在 WSL2 既有环境运行完整单元测试。

本切片不包含：

- 不修改 `Scheduler.schedule()`、`postprocess()`、`BlockManager` 或调度决策；
- 不给 `Config` 增加开关，不接入 `LLMEngine.step()` 回调；
- 不打印日志、不落 JSON 文件、不引入日志框架；
- 不实现 TTFT、TPOT 或 benchmark 指标；
- 不修改 FCFS、抢占、Prefix Cache 或任何调度评分；
- 不在 macOS 安装或运行 CUDA 依赖。

### 实施顺序

1. 从已包含生命周期 baseline 的 `main` 创建 `codex/scheduler-step-snapshot`。
2. 定义不可变的 Step、Sequence 快照数据结构和无副作用采集函数。
3. 用三步生命周期测试验证以下状态序列：
   - 首轮 Prefill 后仍为 `WAITING`，缓存进度为 4；
   - 次轮 Prefill 后进入 `RUNNING`，生成第一个 Completion Token；
   - Decode 后达到 `max_tokens`，进入 `FINISHED`，KV Block 全部释放。
4. 保留原生命周期测试作为行为基线，确认它未被改写成只测试快照实现。
5. 在 WSL2 既有 `.venv` 中运行全部单元测试，保存真实输出后创建独立 Draft PR。
6. 由项目所有者根据快照逐步复述状态变化；理解通过后，再决定是否做第二切片的可选 `LLMEngine.step()` observer。

### 完成标准

- 不调用快照函数时，运行时行为、输出和开销路径完全不变。
- 每个快照都是历史值，不会随 Scheduler 后续运行而变化。
- 测试能清楚区分 `num_tokens`、`num_cached_tokens` 与 `num_scheduled_tokens`。
- 完成后的快照能证明请求结束时队列为空且 KV Block 已释放。
- 原生命周期测试与新快照测试都在 WSL2 通过。
- PR 只包含本切片，不夹带策略、性能指标或无关重构。

### 风险与控制

| 风险 | 控制方式 |
| --- | --- |
| 快照保存可变列表，历史记录被后续步骤污染 | 采集时复制为不可变 tuple，并增加回归断言 |
| 已完成请求从队列移除后无法观察 | 采集函数显式接收本轮 `scheduled_seqs`，同时记录队列和本轮对象 |
| 过早把 trace 变成生产日志系统 | 第一切片只返回结构化数据，不输出、不持久化 |
| 为了测试 trace 而改写 Scheduler 行为 | 原生命周期测试保持独立，核心调度文件不在本切片修改范围内 |
| Block ID 断言过度耦合实现细节 | 主要断言占用数量、释放结果和不可变性；仅在确有语义需要时检查具体 ID |

## 立即下一步

1. 从最新 `main` 创建 `codex/scheduler-step-snapshot`。
2. 只实现纯读取快照模块及其 CPU 测试，不修改 Scheduler 策略。
3. 在 WSL2 既有 `.venv` 中验证后，创建独立 Draft PR 并进行下一轮理解复盘。

## 已推迟、当前不决策

- 快照是否接入 `LLMEngine.step()` 的可选 observer；
- 是否导出 JSONL 作为实验原始 trace；
- TTFT、TPOT、Queue Time 的计时边界与时钟选择；
- 第一种自定义调度评分公式。

这些问题在第一切片完成并经过理解复盘后再分别决策，当前不应提前实现。
