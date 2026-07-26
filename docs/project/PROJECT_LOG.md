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
- 完成 PR #8 最终技术审阅：合约映射的 `LLMEngine`、`Scheduler`、`Sequence`、`ModelRunner` 与 `SamplingParams` 自源码核对基线后未变化，四个时间事件、TPOT 空值、抢占、Prefix Cache、同步 API 和聚合规则均能由当前生命周期唯一实现；PR 无评论、审阅或检查阻塞，`git diff --check` 通过。
- [PR #8](https://github.com/NEVER-AGAIN-RAY/NanoServeLab/pull/8) 转为 Ready 后合并，merge commit 为 `a3679634bdc065a11eb645be099ddc2f94c84fe1`。该 PR 只有指标合约与状态文档，没有运行时代码或 benchmark；唯一下一目标切换为最小 per-request timing record 与 fake-clock CPU 测试。
- 在独立分支 `cursor/stage2-request-timing-core` 实现 Scheduler 级最小 per-request timing record：新增 `nanovllm/engine/request_timing.py`，`Scheduler(..., timing_recorder=None)` 可选注入；默认关闭时不调用时钟、不创建记录。
- 事件写入位置按合约落地：`add()` 入口记录 Arrival；`schedule()` 返回前 write-once First Scheduled；`postprocess()` 在真实 `append_token` 后写 First Output / 更新 `output_tokens`；状态置 `FINISHED` 后、KV 释放前写 Completion（`outcome="finished"`）。
- 记录独立于 KV Block 生命周期，不参与排序/准入/抢占/分配；未修改 `LLMEngine`、`Sequence`、`BlockManager`、`ModelRunner`、`Config`、`bench.py` 或调度策略。
- 新增 `tests/test_request_timing.py`（fake monotonic clock，无 sleep）。Mac 轻量 package bootstrap 下与 lifecycle、snapshot、bench 合约测试共 15 个全部通过（绕过 `nanovllm/__init__.py` eager import；普通包导入需完整运行时依赖，当前 Mac 未安装）。`py_compile` 与 `git diff --check` 通过。未安装新依赖，未接入公开引擎开关，未做 WSL2/CUDA 验证，未运行 benchmark，无性能结论；阶段 2 未完成。
- 审阅修订：不可变性测试改为精确断言 `FrozenInstanceError`；文档与 PR 证据改为明确写出 Mac 轻量 package bootstrap 验证方式，避免把普通 `python -m unittest` 误记为已通过。
- 接入引擎入口：`RequestTimingRecorder.snapshots()` 按 `seq_id` 升序返回不可变 tuple；`LLMEngine` 增加 keyword-only `timing_recorder=None`，原样传给 `Scheduler`，不进入 Config。Mac bootstrap 仅验证 recorder 语义与语法（未构造真实 LLMEngine）；未做 WSL2/CUDA，未跑 benchmark，无性能结论；PR #11 保持 Draft。
- 完成 Draft PR #11 精确提交 `e0914e23247fe731d6ee1cabce91a1e30c9725bc` 的 WSL2/CUDA 验收。WSL 直连 GitHub fetch 仍未成功，改用 SHA-256 已校验的最小 Git bundle 同步到独立分支 `codex/wsl-pr11-validation`；没有改动旧 baseline 分支或安装依赖。
- 环境复核为 Ubuntu 24.04、Python 3.12.3、PyTorch 2.4.0+cu124、CUDA 12.4、RTX 4060 Laptop GPU 与驱动 555.97；Qwen3-0.6B revision 仍为 `c1899de289a04d12100db370d81485cdf75e47ca`。完整 18 项单元测试通过。
- 真实 `LLM(..., timing_recorder=recorder)`、CUDA Graph、Prefill/Decode、单/多 Token 和 `max_tokens` 路径通过；recorder-on 的四个时间事件齐全单调，recorder-off 不产生记录，两个独立进程输出 Token 哈希一致。
- 通过“真实 CUDA 探测首 Token，再在独立进程将相同 Token 作为 EOS 判断哨兵”的方法覆盖 EOS 完成分支：`max_tokens=8` 的请求在第 1 Token 后完成。该结果明确标为受控 EOS，不冒充模型自然生成 tokenizer EOS。
- 完成 3 次 recorder-on 与 3 次 recorder-off 全新进程冒烟。六次输出 Token 哈希一致；on/off measured elapsed 的样本均值分别为 780.764324 ms 和 815.489169 ms，但成对差值方向不一致且样本标准差约 60–66 ms，只能说明未观察到一致的异常级退化，不构成 recorder 加速、零开销或正式性能结论。
- 10 份 schema v1 原始 JSON 与验收 runner 已保留在 WSL，并备份到 Mac 的 Git 忽略目录；双端逐文件 SHA-256 一致。完整协议、原始值、哈希、解释边界和限制记录在 `docs/experiments/timing-validation-2026-07-22.md`。
- PR #11 的 WSL2/CUDA 行为门槛已满足，但阶段 2 仍未完成；下一实现目标切换为纯 per-request 指标派生，用确定性 CPU 测试固定 Queue Time、TTFT、E2E、TPOT 和无效/空值规则，不同时实现混合 workload 或聚合框架。
- [PR #11](https://github.com/NEVER-AGAIN-RAY/NanoServeLab/pull/11) 在最终实时核对 HEAD `1cc8cca`、无评论/审阅阻塞且 GitHub 判定 `CLEAN / MERGEABLE` 后转为 Ready，并以 merge commit `5f72b60b167c3204375b0549f67a9bdb147d7325` 合并到 `main`。阶段 2 的最小原始 timing 记录层至此完成；下一目标保持为纯 per-request 指标派生。
- 在独立分支 `cursor/stage2-request-metrics`（基于 `origin/main` `634222c`）实现纯 per-request 指标派生：新增 `nanovllm/engine/request_metrics.py` 的 `RequestMetrics` 与 `derive_request_metrics()`；按合约计算 Queue Time / TTFT / E2E / Mean TPOT；`N==1` 时 TPOT 为 `None`；`outcome` 非 finished、`output_tokens<=0`、缺失时间戳或乱序抛 `ValueError`。未修改 Scheduler、LLMEngine、recorder 或事件写入位置。
- 新增 `tests/test_request_metrics.py`。Mac 轻量 package bootstrap 下与 timing/lifecycle/snapshot/bench 共 33 个测试全部通过；`py_compile` 与 `git diff --check` 通过。未运行 CUDA 或 benchmark，无性能结论；阶段 2 未完成。下一目标：审阅合并本切片后，再冻结 saturated 混合 workload。
- [PR #13](https://github.com/NEVER-AGAIN-RAY/NanoServeLab/pull/13) 经独立审查确认公式、TPOT 空值、异常顺序、不可变性和范围均符合 `metrics.md`，Mac 33 个测试复现通过；实时状态为 `CLEAN / MERGEABLE` 后转 Ready，并以 merge commit `5e38dbc683a2678c50a4b2f3b2677dd2062e3a2d` 合并到 `main`。
- 在独立分支 `codex/stage2-saturated-workload` 冻结 `NSL-S2-SAT-v1`：64 个请求按 `[short, long, short, short] * 16` saturated 准入；48 个 short 为 128 Prompt / 32 Output Token，16 个 long 为 1024 Prompt / 256 Output Token；seed 0、Token ID `[0,10000]`，总 Prompt 22,528、请求 Output 5,632，最大上下文 1,280。
- 新增不可变 manifest builder、SHA-256 规范和 `docs/experiments/saturated-workload.md`；固定 manifest 指纹 `aa1d4e345e0e9f599bd43093bd5b9214476aa3145ee910cc9137d0b62754767d`。3 个新 CPU 测试与既有测试合计 36 个通过，`py_compile` 通过；未实现 driver，未运行 CUDA 或 benchmark，无性能结论。
- 项目所有者本人明确接受 `NSL-S2-SAT-v1` 的 64 请求、3:1 长短比例、两类长度、固定交错顺序与 saturated batch admission；该取舍记为所有者的研究设计决策，不记为 nano-vLLM 默认值、真实流量分布或实验所得最优值。实验合约补充每组参数的作用与版本化变更步骤；代码将裸 `* 16` 命名为 `PATTERN_REPETITIONS`，不改变请求、Token、manifest 指纹或运行行为。补强后 Mac 轻量 bootstrap 全部 36 个测试通过，相关 `py_compile`、指纹重算与 `git diff --check` 通过。
- [PR #14](https://github.com/NEVER-AGAIN-RAY/NanoServeLab/pull/14) 最终 HEAD `df899b506eba039b6a69dc0813fb62024017d8ea` 经核对为 Conversation 0、Checks 0、与 `main` 无冲突并可自动合并；项目所有者确认研究设计门槛后转 Ready，以 merge commit `888aef1a4db5189cf42856b982855bd6ad7d60e6` 合并到 `main`。未运行 CUDA 或 benchmark，无性能结论；唯一下一目标切换为 saturated admission driver 与 schema v1 原始 JSON 写出。
- 完成 Mac GitHub 双链路故障排查。Git / `gh` 失败的根因是 `~/.gitconfig` 残留未监听的 `127.0.0.1:7897` 全局代理，而非 OAuth token 失效；删除代理后 `git ls-remote`、`gh auth status`、`gh api user` 均成功。Codex GitHub 连接器 404 的独立根因是 OAuth 身份为 `NEVER-AGAIN-RAY`，但 GitHub App 只安装在 `consid-yan`；现已将 `ChatGPT Codex Connector` 以单仓库范围安装到 `NEVER-AGAIN-RAY/NanoServeLab`。连接器账户、安装、仓库元数据及 PR #15 读取全部通过。
- 在独立分支 `cursor/stage2-saturated-driver`（基于 `origin/main` `cbe11c6`）实现 saturated admission driver 与 schema v1 writer：`research/stage2_saturated_driver.py`。固定 warmup、64 次 `add_request` 先于第一次 `step`、recorder snapshot diff 映射 `request_index↔seq_id`、成功/失败原始 JSON；未修改 `nanovllm` 核心、`bench.py` 或 `research/stage2_workload.py` 指纹。
- Mac 轻量 package bootstrap 下新增 driver 测试与既有测试共 44 个全部通过；`py_compile`、CLI `--help`（不触发 torch）、manifest 指纹重算与 `git diff --check` 通过。未运行 CUDA/WSL2，未创建 PR，无性能结论；阶段 2 未完成。下一门槛仍是审阅本切片并做 WSL2/CUDA smoke，不提前进入聚合。
- 同分支按 Codex 审查修订 driver：setup 失败唯一 artifact、`unmapped_timing_records`、成功终态不变量、`cuda_synchronized` 真实 CUDA 语义、mismatch 保留实际 digest、torch 隔离改为 fresh subprocess。Mac bootstrap 复跑共 47 个测试通过；`py_compile`、CLI `--help`、fresh import 无 torch、指纹与 `git diff --check` 通过。未 commit/push/建 PR，未跑 WSL2/CUDA。

## 2026-07-23

- Draft [PR #17](https://github.com/NEVER-AGAIN-RAY/NanoServeLab/pull/17) 精确提交 `59d4d9a5bc2c550097e77d24b8f75aff6e335454` 在 WSL 验证分支 `codex/wsl-pr17-smoke` 完成一次行为/CUDA smoke：Ubuntu 24.04.4 + RTX 4060、PyTorch 2.4.0+cu124、既有 `.venv`；运行前后 tracked worktree clean；本轮 WSL 直连 GitHub fetch 已成功。
- 预检 `Ran 47 tests in 0.344s / OK`；一次真实 LLM smoke 退出码 0，`status=finished`，`cuda_synchronized=true`，64 请求全部 finished，actual Output Token 5,632，`unmapped_timing_records` 为空。
- recorder 证明 saturated admission：`max(arrival_ns)=15213159684880 <= min(first_scheduled_ns)=15213160050903`。
- raw JSON `saturated-20260722T161450.289961Z-run1.json`（29,126 Bytes，SHA-256 `0a61e1defd4532eaef37f0eca8b48df235d364fc5fc5d87bddfc647614f81e90`）与日志/审计脚本双端备份；完整事实见 `docs/experiments/saturated-smoke-validation-2026-07-23.md`。不计入正式三次实验，无性能结论。
- 下一门槛改为审查并合并 PR #17；合并后才启动三个全新进程正式 `NSL-S2-SAT-v1` 实验；aggregation 仍推迟。
- PR #17 完整实现与 smoke 证据审查通过；smoke 文档提交为 `96783e452be3f5ec2f85f137491a7ffd99193045`。
- PR 转 Ready 时 GitHub 状态 CLEAN，无评论、review 或 CI check。
- [PR #17](https://github.com/NEVER-AGAIN-RAY/NanoServeLab/pull/17) 以 merge commit `f4daf0e55ad213093b215fc4fd713b546951609c` 合并到 `main`；saturated admission driver 切片正式进入 `main`。
- 没有运行三次正式实验，没有 aggregation，没有性能结论。
- 唯一下一目标为三次全新进程正式 `NSL-S2-SAT-v1`。
- 纯文档收口 [PR #18](https://github.com/NEVER-AGAIN-RAY/NanoServeLab/pull/18) 经远端差异复核为 5 个预期文件、`CLEAN / MERGEABLE`、无评论/review/check 后，以 merge commit `69c88c252e09bd5d4ffad434c525647d9bf4f207` 合并到 `main`。
- WSL 在新分支 `codex/wsl-stage2-formal-20260723` 同步到精确 `69c88c2`；Git clean、GPU 空闲、模型 revision/权重 SHA、manifest、47 个单元测试与静态门槛通过。
- 三个全新 Python 进程串行完成正式 `NSL-S2-SAT-v1` run 1、2、3；均退出码 0、`status=finished`、64 请求、5,632 actual Output Token、无 unmapped record、CUDA 双边界同步且 saturated admission 成立。没有重跑或替换。
- 三份 raw SHA-256 分别为 `8ee9f9fc7879bbae94058804ea721853d5624eda3c4080cf67ba04fffe2c5a46`、`426416c8a4937e6475a20d1bd099148cdbcabb1b45a37a2d6ace4f9a0034e887`、`298615cf49ad7fdede5d1b8b3820ae759e3f894b2f7bc119e426c5743a04005e`；标准库逐字段/跨 run 审计通过，完整日志异常扫描无匹配。
- 证据目录已从 WSL 备份到 Mac Git 忽略目录，两端按 `SHA256SUMS` 逐文件验证通过；清单自身 SHA-256 为 `f64d4f4e09851354ad94cdfeb9ca79fb4bdac9a7fc09854163a4e3c16738921d`。
- preflight helper 名、run 1 快速审计字段形状和 postflight 展示计数各出现一次验证命令错误；原失败日志与纠正日志均保留，均未触发实验重跑或 raw 覆盖。完整事实见 `docs/experiments/saturated-results-2026-07-23.md`。
- 正式 raw 门槛已完成；尚未 aggregation、未发布延迟/吞吐统计、无性能提升结论。唯一下一目标切换为离线 schema v1 aggregation 小切片。
- 独立分支 `cursor/stage2-offline-aggregation`（基于精确 `origin/main` `16d4f12b9b799bfbd8fcf23cf6fc35660e4f94bf`）实现离线 schema v1 aggregation：新增 `docs/experiments/aggregation.md`、`research/stage2_aggregate.py`、`tests/test_stage2_aggregate.py`。
- 汇总器只读显式 raw 路径，复用 `RequestTimingRecord` 与 `derive_request_metrics()`；拒绝 dirty/malformed/混组/重复源；保留 outcome 与 invalid 计数；输出 all/short/long 延迟统计与 per-run / across-runs 吞吐；默认拒绝覆盖输出。
- Mac 轻量 package bootstrap 共 60 个测试通过（其中 aggregation 13 个）；`py_compile`、CLI `--help`、fresh import 不加载 torch、`git diff --check` 通过。未改 scheduler / recorder / driver / `bench.py` / workload；未在正式 raw 上运行 aggregation；未发布统计数字；无性能结论。
- 独立对抗审查发现 Cursor 初版会给 failed / 缺失 status 的 run 计算吞吐、用 `int()` 接受或截断 bool/string/float、弱化错误容器、漏收未知 request class、让非法 UTF-8 等异常逃出 CLI，并以 `exists()` + `write_text()` 留下覆盖竞态。上述问题均在本分支修复，未触碰正式 raw。
- 修复后 loader 严格要求 schema/status/container/integer，单源也必须匹配冻结 `NSL-S2-SAT-v1` workload 与 manifest；finished record 校验 short/long、Token 一致性和时间事实；failed run 吞吐强制为 null；同一份源 bytes 同时用于解析和 SHA-256；输出以独占创建拒绝文件、符号链接和并发覆盖，并拒绝非有限 JSON。
- 新增对抗性回归后 aggregation 21 tests、Mac 全套轻量 package bootstrap 68 tests 全部通过；静态门槛复验结果见本分支最终审查记录。仍未在正式 raw 上运行 aggregation，未发布任何正式延迟/吞吐统计。
- aggregation 以提交 `2d1abaf78704326ecd1faa3aeae8e2be54ff1f0c` 推送并创建 Draft [PR #20](https://github.com/NEVER-AGAIN-RAY/NanoServeLab/pull/20)；首次远端核对为 `OPEN / DRAFT / MERGEABLE`，1 个提交、6 个预期文件、无评论/review，仓库未报告 checks。PR 明确指向 `NEVER-AGAIN-RAY/NanoServeLab:main`，未向 upstream 写入。
- PR #20 在重新通过 Mac 68 tests、`py_compile`、CLI/import、diff 检查与正式 raw 哈希复验后转 Ready；远端仍为 6 个预期文件、无评论/review/check，以 merge commit `a8c2efc0f14901b462a346354c134f3642b448a3` 合并。
- 从精确 `origin/main` `a8c2efc` 创建 `codex/stage2-aggregation-results`，在 Mac 对三份正式 raw 做一次唯一成功写入的只读 aggregation。aggregate 为 7,744 Bytes，SHA-256 `47d31a4074336ab1bf6d2035e09869776847843fb3c33455c473864cd7debbb8`。
- 正式写入前有两次未产生输出的命令错误：`SHA256SUMS` 首次从错误工作目录执行，以及默认沙箱拒绝创建新忽略目录。纠正后原始证据 26 项全清单通过，并以窄范围权限写入此前不存在的输出；没有修改 raw、运行 CUDA 或重跑 benchmark。
- 标准库独立复算与同 `created_at_utc` 汇总器重放均通过；再次指向同一输出时正确拒绝覆盖。结果为 192 total / 192 valid finished / 0 invalid / 0 unmapped，short 144、long 48；三次 output Token/s 为 826.406070、864.999913、864.296016，跨 run mean ± sample SD 为 851.900666 ± 22.081773。
- aggregation 证据目录保存 aggregate、`aggregate-validation.json` 与 `SHA256SUMS`；两项自校验通过，清单自身 SHA-256 为 `6b4da18c5fa93944a303f4a009efd00c1be7d1683e7de44746d98493361cf7ee`。完整统计与结论边界见 `docs/experiments/saturated-aggregation-results-2026-07-23.md`。
- 正式 aggregation 结果以提交 `df4e7477077c820bbfc56259c265769716c6a2ca` 推送并创建 Draft [PR #21](https://github.com/NEVER-AGAIN-RAY/NanoServeLab/pull/21)，基于 PR #20 合并后的 `main` `a8c2efc`；初始范围为 4 个结果文档、207 additions / 17 deletions，不包含 Git 忽略 raw 或 aggregate。
- PR #21 最终为 5 个结果/状态文档；原始证据 26 项、aggregation 证据 2 项、文档对封存 JSON 的逐表一致性均复验通过。远端无评论/review/check 且为 `MERGEABLE` 后转 Ready，以 merge commit `77160a7422dca27a763eb44308bb20c11b91a967` 合并。
- 阶段 2 至此满足章程退出标准：指标边界及真实 CUDA 事件路径已验证；冻结长短混合 workload 已完成三个独立进程；warmup、measurement、raw 与 aggregation 已分离并有哈希封存和独立复算。阶段结论只确认实验基础完整，不声称调度策略性能提升。
- 当前阶段切换到阶段 3“调度策略比较”。唯一下一小切片是先冻结 FCFS 对照身份、单变量比较、指标/公平性与重复实验合约；在该合约审阅前不修改 Scheduler 或运行新策略实验。
- 阶段 2 纯文档收口以提交 `f9c4fd8d4a79b900ee77577a2845655b63ddd62f` 创建 [PR #22](https://github.com/NEVER-AGAIN-RAY/NanoServeLab/pull/22)，基于 PR #21 合并后的 `main` `77160a7`；初始范围为 4 个状态文档，不包含代码或实验产物。

## 2026-07-26

- 从 clean `main` `4a98031` 创建独立分支 `codex/stage3-fcfs-contract`，起草 `docs/experiments/stage3-scheduling-contract.md`；本切片只改文档，没有修改 Scheduler、KV Cache、driver、workload 或阶段 2 raw，也没有运行 CUDA benchmark。
- 合约将现有 `fcfs-v1` 精确定义为 waiting 队首准入、running 一 Token 稳定轮转，并保留 Prefill 优先、Chunked Prefill、Prefix Cache、资源预算以及抢占回 waiting 队首等不变量；明确它不是串行完成式 FCFS。
- 第一候选 `prompt-length-v1` 只允许按 `num_prompt_tokens` 改变新到达请求在 waiting 中的稳定插入位置；相同长度保持到达顺序，不动态重排已开始 Chunked Prefill 或被抢占请求，不改变 Decode、抢占、KV 或完成语义。
- 阶段 2 mixed baseline 只作为历史锚点；阶段 3 正式对照必须在同一 clean commit 与环境下显式记录 Policy ID，并为 FCFS 和 Candidate 各运行 3 个全新进程。合约固定复用 `NSL-S2-SAT-v1`，保留 all/short/long 指标、最坏等待与尾延迟证据，不引入复杂公平性综合分数。
- 项目所有者授权按上述默认方向继续。合约以提交 `f5acb600ebd946dfe8f9716e5c0aea2282641b44` 推送并创建 Draft [PR #23](https://github.com/NEVER-AGAIN-RAY/NanoServeLab/pull/23)，目标为 `main`，初始范围为 3 个纯文档文件、357 additions / 17 deletions；没有向 `upstream` 写入。下一门槛是完成 PR 远端审查与合并，随后用独立切片补齐 FCFS 多请求顺序测试，不在当前文档 PR 实现策略。
- PR #23 更新后仍为 3 个预期文档文件、2 个提交，无评论、review 或 CI check；转 Ready 后 GitHub 判定 `CLEAN / MERGEABLE`，以 merge commit `5cf7beb60c2fbf76bb71509de6d1ec2d2b9f8b4c` 合并到 `main`。
- 在后续 `fcfs-v1` 多请求特征测试设计中发现合约技术误述：`Scheduler.schedule()` 通过 `running.extendleft(reversed(scheduled_seqs))` 把入选请求恢复到队首；当 running 数量超过 `max_num_seqs` 时，同一队首批次会继续被选择，队尾不会 round-robin。当前独立分支 `codex/stage3-fcfs-order-tests` 纠正合约并用测试固定真实行为，不修改 Scheduler。
- 新增 `tests/test_scheduler_fcfs_order.py` 的 4 个确定性 CPU 特征测试：固定 waiting 到达顺序与 Chunked Prefill 队首、不可分配队首不绕过后续可分配请求、waiting Prefill 相对 running Decode 的 step 级优先、running 稳定队首批次以及 KV 压力下 running 队尾抢占回 waiting 队首。
- 普通 Mac `unittest` 因项目未安装完整运行时依赖而在 import 阶段分别缺少 `tqdm`、`xxhash`；没有为此运行根目录 `uv sync` 或安装 CUDA-only 依赖。按既有轻量 package bootstrap 注入包 namespace 和最小 hash/array 替身后，新增 4 tests 与全套 72 tests 全部通过；新增测试 `py_compile` 和 `git diff --check` 通过。替身只服务 Scheduler CPU 语义，真实依赖与 CUDA 路径仍留给后续 WSL2 门槛。
- 特征测试与合约纠正以提交 `5c9f9992b57f71797392bacfbef86429bafda861` 推送并创建 Draft [PR #24](https://github.com/NEVER-AGAIN-RAY/NanoServeLab/pull/24)，目标为 `main`，初始范围为 4 个文件、223 additions / 28 deletions；没有运行 CUDA、修改 Scheduler 或向 `upstream` 写入。
- PR #24 最终为 4 个预期文件、2 个提交，无评论、review 或 CI check；转 Ready 后 GitHub 判定 `CLEAN / MERGEABLE`，以 merge commit `30beb3decd675ef5b240c5edc6bf14b91a5f713e` 合并到 `main`。
- 从该合并提交创建独立分支 `codex/stage3-policy-entry`：新增 `nanovllm/engine/scheduling_policy.py` 的 `FCFS_POLICY`、支持集合与严格规范化；Config 增加默认 `scheduling_policy=fcfs-v1`；Scheduler 对 Config 显式值和旧 fake config 缺省值统一规范化并暴露身份。当前支持集合只有 FCFS，没有改变 waiting、`schedule()`、抢占或 KV 行为。
- 在既有 FCFS 特征测试中新增显式/隐式 `fcfs-v1` 首批调度等价和未知 Policy 拒绝测试。相关 6 tests 与 Mac 轻量全套 74 tests 全部通过，`scheduling_policy.py`、Config、Scheduler 和测试的 `py_compile` 通过；未构造真实 LLM、运行 CUDA 或产生策略结果。
- 显式 Policy 入口以提交 `45bd3fe984af063050744e3413e7809b017cfaff` 推送并创建 Draft [PR #25](https://github.com/NEVER-AGAIN-RAY/NanoServeLab/pull/25)，目标为 `main`，初始范围为 6 个文件、110 additions / 21 deletions；没有实现长度排序、运行 CUDA 或向 `upstream` 写入。
- PR #25 最终为 6 个预期文件、2 个提交，无评论、review 或 CI check；转 Ready 后 GitHub 判定 `CLEAN / MERGEABLE`，以 merge commit `e0a69abe1eceac55d3188a2c52f652bc116150b2` 合并到 `main`。
- 从该合并提交创建独立分支 `codex/stage3-prompt-length-policy`：将 `prompt-length-v1` 加入支持集合；`Scheduler.add()` 在 FCFS 下仍直接 append，在长度策略下先跳过 recovery prefix，再按 `num_prompt_tokens` 升序稳定插入 fresh 请求。recovery 由仍有 `block_table` 的 Chunked Prefill 请求或已有 Completion Token 的被抢占请求识别；`schedule()`、Decode、抢占、KV 和完成路径未改。
- 新增长度顺序/稳定并列、Chunked Prefill recovery、被抢占 recovery 三个策略测试。相关 9 tests 与 Mac 轻量全套 77 tests 全部通过，策略模块、Scheduler 和测试 `py_compile` 通过；没有构造真实 LLM、运行 CUDA 或产生性能结论。
- `prompt-length-v1` 以提交 `77b2bf6f76e51769b99484920715a63041f1c22d` 推送并创建 Draft [PR #26](https://github.com/NEVER-AGAIN-RAY/NanoServeLab/pull/26)，目标为 `main`，初始范围为 5 个文件、142 additions / 24 deletions；没有运行 CUDA、修改 KV/Decode 或向 `upstream` 写入。
- PR #26 最终为 5 个预期文件、2 个提交，无评论、review 或 CI check；转 Ready 后 GitHub 判定 `CLEAN / MERGEABLE`，以 merge commit `0c80123a3078e59e1a405a417a330efe79c12bbd` 合并到 `main`。
- 从该合并提交创建独立分支 `codex/stage3-scheduling-driver`。新增 `research/stage3_scheduling_driver.py`、`docs/experiments/stage3-scheduling-raw.md` 与 12 个 CPU 合约测试；Stage 3 外层复用 Stage 2 saturated admission 核心，不修改阶段 2 raw/schema/aggregator。
- raw 使用独立 schema v2 和 `NSL-S3-SCHED-v1` 身份，记录 comparison group、Policy definition v1/parameters、`NSL-S2-SAT-v1` workload ID，以及 requested/actual Scheduler Policy。缺失 commit、dirty worktree、Policy 无法读取或 requested/actual 不一致均在 warmup 前失败。
- writer 在创建文件前完成严格身份检查和有限 JSON 序列化，再使用独占创建；同一路径存在时不覆盖原字节。Mac Stage 3 定向 12 tests、轻量全套 89 tests、相关 `py_compile`、fresh import/CLI help 不加载 torch 与 `git diff --check` 通过；没有运行 CUDA、真实 LLM 或产生性能结论。
- Stage 3 raw driver 以提交 `19e55788813a813eb651301d157fd3025751e797` 推送并创建 Draft [PR #27](https://github.com/NEVER-AGAIN-RAY/NanoServeLab/pull/27)，目标为 `main`，初始范围为 5 个文件、1,206 additions / 21 deletions；没有向 `upstream` 写入。
- PR #27 本地第二轮审查补强 mismatch 证据：请求 Policy 与实际 Scheduler 不同时仍在 warmup 前失败，但 raw 的 `engine.scheduling_policy` 保留已经读到的实际值，`policy.runtime_verified` 保持 false；Mac 全套 89 tests 复验通过。
- PR #27 最终为 5 个预期文件、3 个提交，无评论、review 或 CI check；转 Ready 后 GitHub 判定 `CLEAN / MERGEABLE`，以 merge commit `6b9b4bb1b2478c7ddd05f64b0587a02b053b935d` 合并到 `main`。
- 从该合并提交创建独立分支 `codex/stage3-scheduling-aggregate`，新增 `NSL-S3-AGG-v1` 严格离线对照：只接受六份显式 schema v2 raw，验证 Policy/run 矩阵、comparison group、commit/environment/model/fixed engine/workload 和固定 UTC 创建顺序；Policy requested/actual 是唯一排除的 engine 自变量。
- 聚合器复用 Stage 2 request 指标、nearest-rank、sample SD 和独占 writer；按 Policy 输出 outcome/invalid/unmapped、all/short/long 延迟、三次吞吐、最坏请求，以及 candidate−FCFS 差值、5% 吞吐警戒和结构化公平性风险。任一 run 不完整时保留证据但 comparison 无效且吞吐为 null。
- 对抗性审查补上实际 `created_at_utc` 顺序证明和 Stage 3 aggregate writer 身份校验。新增 aggregation 14 tests；Mac 轻量全套 103 tests、相关 `py_compile`、fresh import/CLI help 不加载 torch 与 `git diff --check` 通过。没有运行 CUDA、读取正式 Stage 3 raw 或产生性能结论。
