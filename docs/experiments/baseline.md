# 阶段 1：nano-vLLM baseline 实验合约

本文件固定阶段 1 baseline 的可复现条件。它不记录当前进度；当前状态仍以 `docs/project/README.md` 为准。

## 为什么沿用官方 workload

`bench.py` 来自上游 nano-vLLM，生成 256 个 synthetic 请求，输入和输出长度都在 100–1024 Token 间均匀随机。阶段 1 先固定这条官方吞吐 baseline，而不提前引入真实数据集、混合到达过程、TTFT 或 TPOT。这样每次实验只回答一个问题：同一版本和配置能否稳定跑通，并得到可重复的总输出吞吐。

本切片没有修改 `LLM`、Scheduler、KV Cache 或模型执行路径。`bench.py` 只增加实验参数、边界校验、环境元数据和原始结果落盘。

## Workload seed 与 Sampling seed 的区别

阶段 1 把随机性拆成两类种子，职责不重叠：

- **Workload seed（`--seed`，固定 0）**：只喂给 Python `random.Random`，用来生成 256 条 synthetic 请求的 prompt token id、输入长度和输出长度。它固定的是 benchmark 的输入与输出形状，与模型内部的采样随机无关。同一 workload seed 下，三条进程看到的请求数据逐字节一致。
- **Sampling seed（`--sampling-seed`，固定 0）**：喂给 PyTorch 的 `torch.manual_seed` 和（CUDA 可用时）`torch.cuda.manual_seed_all`，固定 nano-vLLM Sampler 采样时的 CPU/CUDA RNG 起点。它必须在创建 `LLM` 之前设置，使三条新进程经历一致的 RNG 消耗顺序，覆盖 LLM 初始化、内部 warmup、CUDA Graph 捕获和显式 warmup。

设置 sampling seed 只是把采样 RNG 的起点固定到同一状态，不等于保证所有 CUDA 运算位级确定。`bench.py` 不调用 `torch.use_deterministic_algorithms`；非确定性的 CUDA kernel、原子归约以及并发 kernel 的执行顺序仍可能让两次运行的中间张量不完全一致。阶段 1 只要求三条进程的 RNG 起点和消耗顺序一致，不把生成 Token 的位级一致性作为本 baseline 的结论；若后续研究该问题，必须另建保存输出内容的专项实验。

## 固定变量

| 项目 | 阶段 1 固定值 |
| --- | --- |
| 引擎 | 当前 NanoServeLab commit，运行前工作区必须干净 |
| 模型 | `Qwen/Qwen3-0.6B`，本地目录另行传入 |
| 模型版本 | 必须用 `--model-revision` 记录精确 Hugging Face commit/revision |
| 请求数 | 256 |
| Workload 随机种子 | 0，通过 `--seed` 传入；固定 synthetic 请求的输入长度、输出长度和 prompt token id |
| Sampling 随机种子 | 0，通过 `--sampling-seed` 传入；固定 PyTorch/CUDA 采样 RNG 的起点 |
| 输入长度 | `[100, 1024]` 均匀整数分布 |
| 输出长度 | `[100, 1024]` 均匀整数分布 |
| Token ID | `[0, 10000]` 均匀整数分布 |
| Sampling | temperature 0.6、ignore EOS |
| 引擎配置 | `enforce_eager=False`、`max_model_len=4096` |
| 重复次数 | 3；每次使用新的 Python 进程和新的 `LLM` 实例 |

输入与输出长度之和最大为 2048，小于 `max_model_len=4096`。阶段 1 不改变上述任一变量；若必须改变，实验应使用不同名称，不能与本 baseline 混为一组。

## warmup 与测量边界

每个独立进程先执行上游原有的一条 `"Benchmark: "` 请求作为 warmup。warmup 不计时；它只用于触发模型初始化和惰性准备，不代表完整 workload 的稳态预热。

warmup 返回后先同步 CUDA，再用 `time.perf_counter()` 包围完整的 256 请求 `llm.generate(...)`，返回后再次同步 CUDA。计量值只包含这一个 batch 的墙钟时间。总输出 Token 数来自固定的 `max_tokens` 之和，因为 `ignore_eos=True`。

三次重复必须分别启动 `bench.py`，不能在同一 `LLM` 实例中循环；否则后续运行可能复用 Prefix Cache 或其他进程内状态，重复实验不再独立。

## 原始结果格式

每次运行写入一个 `results/raw/baseline/baseline-<UTC>-run<N>.json`。`results/raw/` 已被 Git 忽略，原始数据必须先保留在运行机器上，再备份到不会覆盖旧文件的位置。

JSON schema 版本当前为 1，包含：

- 仓库 commit、分支与 dirty 状态；
- Python、操作系统、关键包版本、PyTorch CUDA build 与 GPU 名称；
- 模型 ID、精确 revision 和本地路径；
- 引擎、workload、warmup 与时钟边界；
- 本次 elapsed time、总输出 Token 和吞吐量。

一次 JSON 只是一条原始观测，不代表性能结论。三次结果都成功并核对配置一致后，才允许另做汇总；阶段 1 不删除失败或较慢的运行。

## WSL2 运行入口

先完成只读 GPU readiness audit，并确认 `torch.cuda.is_available()` 为真。不要安装或升级依赖作为本命令的一部分。将 `<MODEL_REVISION>` 替换为本地模型对应的精确 revision，然后在仓库根目录、既有 `.venv` 中执行：

```bash
for run in 1 2 3; do
  .venv/bin/python bench.py \
    --model ~/huggingface/Qwen3-0.6B/ \
    --model-id Qwen/Qwen3-0.6B \
    --model-revision <MODEL_REVISION> \
    --run-number "$run"
done
```

如果任一次失败，停止并保存错误，不用安装依赖或更改实验参数来“凑齐”三次。运行后逐个核对 JSON 中的 commit、dirty、模型 revision、CUDA、GPU、workload 和 run number；只有三次配置相同且工作区干净，才能把它们视为同一 baseline 重复组。

## 必须在 WSL2 验证、Mac 无法代替的项目

- WSL2 是否能看到 RTX 4060，PyTorch CUDA 是否可用；
- 当前 CUDA 依赖能否创建 nano-vLLM `LLM` 并完成 warmup；
- 256 请求 workload 能否完成三次独立运行；
- 三个原始 JSON 是否实际生成且元数据正确；
- CUDA 同步、计量边界和吞吐计算是否在真实运行中无异常。

这些项目的实时完成状态不写入本合约，统一查看 `docs/project/README.md`；每组正式数据另建结果记录。对任何尚未完成上述验证的新 commit 或新环境，只能声称 Mac 上的语法、CLI 和确定性 workload 合约通过，不能声称 CUDA baseline 已跑通，更不能声称有性能提升。
