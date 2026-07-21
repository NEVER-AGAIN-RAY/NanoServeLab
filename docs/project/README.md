# NanoServeLab 项目导航

> 新对话、新 AI 或中断恢复时先读本文件。它是“当前做到哪里、正在做什么、下一步做什么”的唯一事实入口。

- 最后核对日期：2026-07-21（Asia/Shanghai）
- 当前阶段：阶段 1——可复现 nano-vLLM baseline
- 当前主线：白天已建立 baseline 实验合约与原始结果入口；今晚在 WSL2 先完成 GPU readiness，再做三次独立 CUDA 验证
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

- 独立分支 `codex/reproducible-baseline-contract` 正在完成阶段 1 第一切片。
- 已保留官方 `bench.py` 的 synthetic workload 与推理路径，只增加显式实验参数、确定性 workload 构造、单次进程计量、环境元数据和每次运行一个原始 JSON。
- `docs/experiments/baseline.md` 已固定模型、revision、workload、seed、warmup/测量边界、三次独立进程重复规则、原始结果格式与晚间入口。
- Mac 已通过新增 benchmark 合约单测、Python 语法检查、CLI `--help` 和 diff whitespace 检查；没有运行模型、CUDA 或 benchmark。
- 2026-07-21 开始任务时 `HEAD`、本地 `main` 与 `origin/main` 均为 `dbaeea1`；`gh` 本地凭据失效，因此开放 PR 列表需要在恢复认证后再次核对。

### 环境与阻塞

- Mac 只用于开发、轻量检查、数据分析和文档；不得在仓库根目录运行 `uv sync`，也不安装 CUDA-only 依赖。
- Windows WSL2 既有虚拟环境可以运行 CPU Scheduler 单元测试。
- WSL2 中直接执行 `nvidia-smi` 曾返回 `command not found`。这不阻塞当前 CPU 测试，但在阶段 1 CUDA baseline 前必须单独核查 GPU 驱动暴露与 PATH。
- benchmark 合约目前只在 Mac 验证了纯 Python 边界；创建 `LLM`、warmup、CUDA 同步、三次完整 workload 和原始 JSON 都必须留到今晚 WSL2 验证。
- 当前没有可以报告的 benchmark 结果，也没有性能提升结论。

## 全局决策：下一实现目标

### 目标名称

**WSL2 baseline validation gate**

### 为什么现在做

阶段 1 的 Mac 开发入口已经完成：实验变量、三次独立重复、计量边界和原始结果格式不再依赖临场决定。当前唯一未知项转为真实 WSL2/CUDA 验证。今晚先解释 `nvidia-smi` 失败层级；若 GPU 与 PyTorch 已就绪，再严格按 `docs/experiments/baseline.md` 运行三次。readiness 失败时保留诊断证据并停止，不临时改环境或 workload。

### 本轮要回答的问题

- Windows/WSL2 是否把 RTX 4060 正确暴露给 Linux；
- `/dev/dxg` 是否存在，WSL 内核与发行版信息是否正常；
- `nvidia-smi` 是单纯不在 PATH，还是驱动接口确实不可用；
- 既有 `.venv` 中 PyTorch 的版本、CUDA build、`torch.cuda.is_available()` 和设备名称；
- 当前环境是否已经具备运行 nano-vLLM baseline 的条件，若不具备，阻塞位于哪一层；
- 若 readiness 通过，三次全新进程是否都能完成 warmup、计量并生成 schema v1 原始 JSON。

### 明确范围

今晚只做只读诊断和固定 baseline 验证：

- 不安装或升级 Windows 驱动、CUDA Toolkit、PyTorch 或项目依赖；
- 不修改 PATH、WSL 配置、系统服务或仓库代码；
- readiness 未通过时不运行 benchmark；通过后只运行已经固定的 baseline，不临时改变参数；
- 不把机器地址、令牌或大段原始系统输出提交进仓库。

如诊断确认需要安装或修改系统配置，必须先记录根因与最小修复方案，再单独获得用户授权。

### 实施顺序

1. 在 Windows/WSL2 在线后，只读采集发行版、内核、GPU 设备节点、NVIDIA 工具路径和既有 `.venv` 的 PyTorch/CUDA 可见性。
2. 将 readiness 证据归类为：GPU 暴露正常、仅 PATH 问题、驱动/WSL 暴露问题、或 Python/PyTorch 环境问题。
3. 仅在 readiness 通过后，按 `docs/experiments/baseline.md` 用三个全新 Python 进程运行固定 workload。
4. 核对三个成功运行的原始 JSON 的 commit、dirty、模型 revision、CUDA/GPU、workload 和 run number；失败时保留命令错误证据并停止。
5. 在 `environment/wsl2.md` 记录精简环境事实，并更新本入口与项目日志；原始结果留在 `results/raw/`，不粘贴进状态文档。

### 完成标准

- 能明确回答 RTX 4060 是否对 WSL2 和 PyTorch 可见；
- 能解释 `nvidia-smi` 失败发生在哪一层；
- 所有结论都有真实命令证据，不把推测写成事实；
- 若环境未就绪，给出一个最小、分层的修复建议，但不擅自执行；
- 若环境就绪，三次独立运行均生成配置一致的 schema v1 原始 JSON；
- 不根据单次结果或未汇总的三次结果声称性能提升。

## 立即下一步

1. 今晚 WSL2 在线后，先执行只读 GPU readiness audit。
2. readiness 通过则按 baseline 合约运行三次；不通过则停止并记录分层阻塞。
3. 核对并保留原始 JSON，记录 `environment/wsl2.md`，再更新本入口与项目日志。

## 已推迟、当前不决策

- Snapshot 是否接入 `LLMEngine.step()` 的可选 observer；
- 是否导出 JSONL 作为实验原始 trace；
- TTFT、TPOT、Queue Time 的计时边界；
- baseline 三次原始结果的统计汇总与可视化；
- 第一种自定义调度评分公式。

这些问题等待 GPU baseline 环境就绪后再分别决策，当前不提前实现。
