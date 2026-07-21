# NanoServeLab 项目导航

> 新对话、新 AI 或中断恢复时先读本文件。它是“当前做到哪里、正在做什么、下一步做什么”的唯一事实入口。

- 最后核对日期：2026-07-21（Asia/Shanghai）
- 当前阶段：阶段 1 入口——WSL2 GPU readiness 与 baseline 准备
- 当前主线：先确认 GPU、驱动和 PyTorch CUDA 可见性，再运行 nano-vLLM baseline
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

- `main` 已包含项目导航、中文核心模块导读、Scheduler 生命周期测试和结构化 Step Snapshot；精确 SHA 应通过实时 Git 检查获取，避免状态文档在自身提交后立即过时。
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
- 已完成只读、不可变的 Scheduler Step Snapshot，并在 WSL2 验证原生命周期测试与新 Snapshot 测试共 2 个全部通过。
- 项目所有者已完成 Snapshot 复盘，能够区分实时 Scheduler 状态、历史快照以及 `scheduled_seqs` 在请求离队后的观察作用。

### 已合并里程碑

| 工作项 | 状态 | 证据 | 说明 |
| --- | --- | --- | --- |
| 项目导航与文档治理 | 已合并 | [PR #3](https://github.com/NEVER-AGAIN-RAY/NanoServeLab/pull/3)，merge `9230325` | 统一当前入口、稳定章程和历史日志 |
| Scheduler 生命周期测试 | 已合并 | [PR #2](https://github.com/NEVER-AGAIN-RAY/NanoServeLab/pull/2)，merge `b4da09f` | WSL2 已验证，已成为 `main` baseline |
| 中文核心模块导读 | 已合并 | [PR #1](https://github.com/NEVER-AGAIN-RAY/NanoServeLab/pull/1)，merge `be4506a` | 仅模块级 docstring，无行为变化 |
| Scheduler Step Snapshot | 已合并 | [PR #5](https://github.com/NEVER-AGAIN-RAY/NanoServeLab/pull/5)，merge `2588827` | 只读观察层；WSL2 全部 2 个测试通过 |

### 当前活动工作

- [PR #5](https://github.com/NEVER-AGAIN-RAY/NanoServeLab/pull/5) 已合并，Snapshot 第一纵向切片完成。
- 2026-07-21 核对时没有开放 PR，本地与远端 `main` 已同步。
- 下一目标切换为 WSL2 GPU readiness audit；目前只做诊断，不修改驱动、CUDA、依赖或系统配置。

### 环境与阻塞

- Mac 只用于开发、轻量检查、数据分析和文档；不得在仓库根目录运行 `uv sync`，也不安装 CUDA-only 依赖。
- Windows WSL2 既有虚拟环境可以运行 CPU Scheduler 单元测试。
- WSL2 中直接执行 `nvidia-smi` 曾返回 `command not found`。这不阻塞当前 CPU 测试，但在阶段 1 CUDA baseline 前必须单独核查 GPU 驱动暴露与 PATH。
- 当前没有可以报告的 benchmark 结果，也没有性能提升结论。

## 全局决策：下一实现目标

### 目标名称

**WSL2 GPU readiness audit**

### 为什么现在做

阶段 0 已经建立请求生命周期 baseline、中文导读和结构化观察基础。进入正式 nano-vLLM baseline 前，当前最直接的未知项是 WSL2 中 `nvidia-smi` 曾返回 `command not found`。在 GPU 可见性未确认前继续扩展 observer、指标或 benchmark 都会增加无效工作。

### 本轮要回答的问题

- Windows/WSL2 是否把 RTX 4060 正确暴露给 Linux；
- `/dev/dxg` 是否存在，WSL 内核与发行版信息是否正常；
- `nvidia-smi` 是单纯不在 PATH，还是驱动接口确实不可用；
- 既有 `.venv` 中 PyTorch 的版本、CUDA build、`torch.cuda.is_available()` 和设备名称；
- 当前环境是否已经具备运行 nano-vLLM baseline 的条件，若不具备，阻塞位于哪一层。

### 明确范围

本轮只做只读诊断和事实记录：

- 不安装或升级 Windows 驱动、CUDA Toolkit、PyTorch 或项目依赖；
- 不修改 PATH、WSL 配置、系统服务或仓库代码；
- 不运行 nano-vLLM benchmark，不生成性能结论；
- 不把机器地址、令牌或大段原始系统输出提交进仓库。

如诊断确认需要安装或修改系统配置，必须先记录根因与最小修复方案，再单独获得用户授权。

### 实施顺序

1. 通过既有 Tailscale SSH 只读采集 WSL 发行版、内核、GPU 设备节点和 NVIDIA 工具路径。
2. 使用既有 `.venv` 读取 Python、PyTorch、CUDA build 与设备可见性，不安装依赖。
3. 将证据归类为：GPU 暴露正常、仅 PATH 问题、驱动/WSL 暴露问题、或 Python/PyTorch 环境问题。
4. 在 `environment/wsl2.md` 记录精简且可复现的环境事实，不保存敏感连接信息。
5. 更新本入口与项目日志，给出是否可以进入 baseline 的明确结论。

### 完成标准

- 能明确回答 RTX 4060 是否对 WSL2 和 PyTorch 可见；
- 能解释 `nvidia-smi` 失败发生在哪一层；
- 所有结论都有真实命令证据，不把推测写成事实；
- 若环境未就绪，给出一个最小、分层的修复建议，但不擅自执行；
- 不产生 benchmark 或性能提升结论。

## 立即下一步

1. 使用 `diagnose` 流程对在线 WSL2 节点执行只读 GPU readiness audit。
2. 记录 `environment/wsl2.md`，区分已验证事实、阻塞和待用户授权的修复。
3. 根据诊断结果决定进入 baseline，或先做一个独立环境修复任务。

## 已推迟、当前不决策

- Snapshot 是否接入 `LLMEngine.step()` 的可选 observer；
- 是否导出 JSONL 作为实验原始 trace；
- TTFT、TPOT、Queue Time 的计时边界与时钟选择；
- 第一种自定义调度评分公式。

这些问题等待 GPU baseline 环境就绪后再分别决策，当前不提前实现。
