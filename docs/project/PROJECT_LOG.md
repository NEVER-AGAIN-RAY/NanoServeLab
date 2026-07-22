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
- 在 `bench.py` 补齐显式 Sampling seed（`--sampling-seed`，默认 0）：新增 `set_sampling_seed()` 用 `torch.manual_seed` 与 `torch.cuda.manual_seed_all` 在创建 `LLM` 之前固定采样 RNG，并在 `workload.sampling.seed` 记录；`--seed` 仍只固定 synthetic workload。未修改 `nanovllm/` 核心，未开启 `torch.use_deterministic_algorithms`，不声称所有 CUDA 算子位级确定。
- 新增 4 个 sampling seed 单测（fake/mock torch 验证 RNG 调用、CLI 默认为 0、显式覆盖默认）；Mac 验证 7 个单测全部通过，`py_compile`、`bench.py --help`、`git diff --check` 均通过；真实 CUDA 采样可复现性仍需今晚 WSL2 验证。
- 完成 WSL2 GPU readiness audit：Ubuntu 24.04.4 的 `/dev/dxg` 存在，RTX 4060 Laptop GPU、驱动 555.97、PyTorch 2.4.0+cu124 和 CUDA 12.4 实际可用；此前 `nvidia-smi: command not found` 确认为 `/usr/lib/wsl/lib` 未进入 PATH，而非驱动故障。
- WSL 仓库同步到 Draft PR #7 的 `8f63bcd` 后，全部 9 个单元测试通过；Qwen3-0.6B 的 9 个下载 metadata 一致指向 revision `c1899de289a04d12100db370d81485cdf75e47ca`。
- 实际创建 `LLM(enforce_eager=False, max_model_len=4096)`，完成内部 warmup 与 CUDA Graph 捕获初始化；1 Token Prefill 冒烟和覆盖一轮 Decode 图回放的 2 Token 冒烟均成功，退出码为 0。未运行正式 baseline，下一目标收敛为三个全新进程的固定 workload 与原始 JSON 验证。
- WSL 直连 GitHub HTTPS 在本次核对时超时；未修改网络或代理，改用 Mac 生成并验证的最小 Git bundle 将 readiness 文档安全 fast-forward 到 WSL。该问题不阻塞当前 baseline，但后续直接 fetch 前需要重新核查网络路径。
- 在 clean commit `fb94f6b46213174718c2c89d11c86180712f3b53` 上完成正式 baseline 预检：GPU 无 compute process，结果目录为空，10 个模型 metadata 一致指向 revision `c1899de289a04d12100db370d81485cdf75e47ca`，固定 workload 为 256 请求、142,827 输入 Token 和 133,966 请求输出 Token。
- 按相同参数串行启动三个全新 Python/`LLM` 进程，三次均正常退出并生成 schema v1 JSON；逐次结果为 1019.165630、1013.041928、1011.091819 output Token/s，对应 elapsed 131.446740、132.241318、132.496374 秒，没有失败或结果剔除。
- 三次输出吞吐的平均值为 1014.433126 Token/s，样本标准差为 4.212859 Token/s，变异系数为 0.415292%。该值只作为当前固定条件的参考 baseline，没有对照组，不构成性能提升结论。
- 三份原始 JSON 已从 WSL 备份到 Mac 的 Git 忽略目录，逐文件 SHA-256 完全一致；另记录模型权重 SHA-256 和固定 workload 规范化指纹。完整证据链、命令、逐次数据、统计方法、限制与后续使用规则写入 `docs/experiments/baseline-results-2026-07-21.md`。
- 三次 measured workload 均出现 PyTorch Dynamo `accumulated_cache_size_limit (256)` 警告，但都成功完成；本轮没有修改 cache limit。stdout/stderr 未单独归档、运行期间未连续采集热状态等限制已如实记录。
- 阶段 1 的正式退出条件已经满足；唯一下一实现目标切换为阶段 2 指标边界合约，先定义 TTFT、TPOT、E2E 与 Queue Time 的生命周期事件、公式和 CPU 可测不变量，不提前改变调度策略或运行新 benchmark。
- 完成阶段 2 指标事件的定向源码映射：请求在 Tokenize 后进入 Scheduler，首次 Chunked Prefill 即算 First Scheduled；只有 `Scheduler.postprocess()` 越过未完成 Prompt 的丢弃分支并调用 `Sequence.append_token()` 才算真实 First Output；完成发生在最后 Token 追加后、KV Block 释放前。
- 新增 `docs/experiments/metrics.md`，固定 Initial Scheduler Queue Time、引擎侧 TTFT、Mean TPOT、E2E 与未来 throughput window；选择可注入 `time.perf_counter_ns()`、write-once timestamp、单 Token TPOT 为 `null`、nearest-rank percentile 和原始记录优先的规则。
- 明确当前 `LLM.generate()` 只在全部请求完成后同步返回，不能报告客户端流式 TTFT；当前引擎也没有 cancel/failed 状态。阶段 2 合约没有新增运行时代码、没有运行 benchmark，真实 CUDA 边界与 instrumentation overhead 仍需未来 WSL2 验证。
- 唯一下一实现目标切换为最小 per-request timing record 与 fake-clock CPU 测试；指标合约分支基于未合并的 PR #7 head，以 stacked change 保持与 baseline PR 隔离。
- 创建 [Draft PR #8](https://github.com/NEVER-AGAIN-RAY/NanoServeLab/pull/8) 提交指标边界合约，base 暂为 `codex/reproducible-baseline-contract`；PR #7 合并后必须 rebase/retarget 到最新 `main`，本轮不转 Ready、不合并。

## 2026-07-22

- 对阶段 1 交付执行最终审计：PR #7 没有待处理 review 或 requested changes，改动范围未触及 `nanovllm/` 核心；Mac 上 7 个 benchmark 合约测试、Python 语法检查、CLI `--help` 与 `git diff --check` 均通过。
- 重新核对 Mac 留存的三份 schema v1 原始 JSON：实验配置、source commit、模型 revision、workload 规模与 seed 一致，逐文件 SHA-256 与实验记录相符，均值 1014.433126 和样本标准差 4.212859 可由原始值重算得到。
- [PR #7](https://github.com/NEVER-AGAIN-RAY/NanoServeLab/pull/7) 转为 Ready 后合并，merge commit 为 `22be4f9c442e2aacfb16682220801416845ce992`。至此阶段 1 的代码、测试、CUDA 实验、原始数据备份、统计与书面记录全部交付；没有据此声称性能提升。
- [Draft PR #8](https://github.com/NEVER-AGAIN-RAY/NanoServeLab/pull/8) 的 base 已从阶段 1 分支调整为 `main`，继续仅承载阶段 2 指标边界合约；它保持 Draft，不在阶段 1 收尾中合并。
- 项目所有者确认阶段 2 第一版混合负载采用 saturated arrival：warmup 后，全部 measured 请求在第一次 Scheduler step 前完成准入，以固定完整混合等待队列。该场景不称为固定速率、Poisson 或真实客户端在线到达；长短请求的精确长度、比例和总数另行冻结。
