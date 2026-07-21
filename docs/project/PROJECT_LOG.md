# NanoServeLab 项目日志

本文件按日期记录已经发生且值得长期保留的事件。它不描述实时状态；当前进度统一查看 `docs/project/README.md`。

## 2026-07-13

- 从官方 `GeeeekExplorer/nano-vllm` 恢复源码、LICENSE 和 Git 历史，修正最初误初始化为空 uv 应用的问题。
- 建立 NanoServeLab 研究工作区，`upstream` 指向官方仓库，`origin` 指向项目仓库。
- 确定 Mac 用于开发与文档，Windows WSL2 + RTX 4060 用于 CUDA 推理与正式 benchmark。
- 记录 Mac 环境，并明确不在 macOS 根目录执行 `uv sync` 或安装 CUDA-only 依赖。
- 当时的上游基线为 `bb823b3e06983d71485a8e1f23715ebd87d98ef8`。

## 2026-07-20

- 完成 Scheduler 架构、请求生命周期、Prefill/Decode、KV Block 与 Prefix Cache 的中文讲解。
- 在独立分支 `agent/chinese-module-guides` 为 13 个核心模块增加中文模块级导读，commit `41e0433`；创建 [Draft PR #1](https://github.com/NEVER-AGAIN-RAY/NanoServeLab/pull/1)。该变更只涉及文档字符串，没有行为变化。
- 在独立分支 `codex/scheduler-lifecycle-test` 新增 `tests/test_scheduler_lifecycle.py`，commit `785f0a4`；创建 [Draft PR #2](https://github.com/NEVER-AGAIN-RAY/NanoServeLab/pull/2)。两个分支均基于 `main`，没有互相混入。
- Scheduler 生命周期测试在 Windows WSL2 的既有 Python 3.12.3 `.venv` 中实际通过：`Ran 1 test / OK`。
- 测试固定了两轮 Chunked Prefill、临时采样丢弃、`WAITING → RUNNING`、Decode 一 Token 落后、`max_tokens` 完成和 KV Block 释放。
- 项目所有者完成逐段复盘，能够解释为什么 Token 在生成后要到下一轮作为输入时才产生自己的 KV Cache。
- 记录环境待核查项：WSL2 中直接执行 `nvidia-smi` 曾返回 `command not found`；这不影响 CPU Scheduler 测试，但必须在 CUDA baseline 前解决或解释。
- 建立 `docs/project/` 项目文档中心，清理根目录中过时且重复的当前状态，规定新会话以 `docs/project/README.md` 为唯一入口。
- 决定下一实现目标为“结构化 Scheduler Step Snapshot”的第一纵向切片：只读采集、CPU 可测、不修改调度策略，不提前接入日志、指标或 CUDA benchmark。
- [PR #3](https://github.com/NEVER-AGAIN-RAY/NanoServeLab/pull/3) 合并为 `9230325`，项目导航与文档治理正式进入 `main`。
- [PR #2](https://github.com/NEVER-AGAIN-RAY/NanoServeLab/pull/2) 合并为 `b4da09f`，WSL2 已验证的 Scheduler 生命周期测试成为 baseline。
- [PR #1](https://github.com/NEVER-AGAIN-RAY/NanoServeLab/pull/1) 合并为 `be4506a`，13 个核心模块的中文导读进入 `main`；差异仅为模块级 docstring。
- 三个阶段 0 基础 PR 全部收口，开始准备结构化 Scheduler Step Snapshot 第一纵向切片。
- 在分支 `codex/scheduler-step-snapshot` 完成第一切片实现提交 `f4e9457`：新增只读、不可变的 Scheduler/Sequence 快照和独立生命周期快照测试，未修改核心调度路径。
- 通过 Tailscale SSH 在 WSL2 既有 Python 3.12.3 `.venv` 中运行全部单元测试；原生命周期测试与新 Snapshot 测试共 2 个，全部通过，结果为 `OK`。

## 2026-07-21

- 项目所有者完成 Scheduler Step Snapshot 逐段复盘，能够解释实时状态、不可变历史快照和 `scheduled_seqs` 对刚完成请求的观察作用。
- [PR #5](https://github.com/NEVER-AGAIN-RAY/NanoServeLab/pull/5) 合并为 `2588827`，结构化 Scheduler Step Snapshot 第一纵向切片进入 `main`。
- 决定阶段 0 的观察基础已经满足，暂不扩展 `LLMEngine.step()` observer；下一目标切换为只读 WSL2 GPU readiness audit，为 nano-vLLM baseline 确认环境前置条件。
- 按白天 Mac、晚间 WSL2 的固定节奏，将阶段 1 第一切片选为“可复现 baseline 实验合约”，避免把 GPU readiness 当作白天开发阻塞。
- 保留上游 `bench.py` 的模型调用与 synthetic workload 语义，增加显式模型 revision、固定 seed/长度边界、单次进程测量、CUDA 边界同步、环境元数据和每次运行一个 schema v1 原始 JSON；未修改 Scheduler、KV Cache 或模型执行组件。
- 新增 `docs/experiments/baseline.md`，固定 Qwen3-0.6B、256 请求、seed 0、warmup/计量边界、三次全新进程重复规则、原始结果格式和晚间 WSL2 入口。
- Mac 静态验证通过：`bench.py` 与新增测试可编译，benchmark 合约 3 个单元测试通过，CLI help 可解析，`git diff --check` 通过；没有运行模型、CUDA 或 benchmark，真实行为验证留到今晚 WSL2。
- 创建 [Draft PR #7](https://github.com/NEVER-AGAIN-RAY/NanoServeLab/pull/7)；明确在 WSL2 readiness、warmup、三次全新进程运行与原始 JSON 均验证前不得转 Ready 或合并。
