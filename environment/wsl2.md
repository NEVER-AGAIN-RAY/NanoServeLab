# Windows WSL2 CUDA 环境记录

- 核对日期：2026-07-21（Asia/Shanghai）
- 发行版：Ubuntu 24.04.4 LTS，WSL2
- 内核：`6.18.33.2-microsoft-standard-WSL2`
- 架构：x86_64
- Python：3.12.3，使用项目既有 `/home/lei/NanoServeLab/.venv`

## GPU 与 CUDA

- `/dev/dxg` 存在，权限允许 WSL 进程访问 Windows GPU 接口。
- GPU：NVIDIA GeForce RTX 4060 Laptop GPU，8188 MiB。
- Windows 暴露的 NVIDIA 驱动版本：555.97。
- `nvidia-smi` 位于 `/usr/lib/wsl/lib/nvidia-smi`；该目录不在当前 PATH，因此此前的 `command not found` 只是 PATH 问题，不是 GPU 或驱动不可用。
- PyTorch：2.4.0+cu124，CUDA build 12.4；`torch.cuda.is_available()` 为 True，设备数为 1，Compute Capability 为 8.9。
- 最小 CUDA Tensor 运算实际通过，结果正确且同步成功。

关键 Python 包：

| 包 | 已验证版本 |
| --- | --- |
| Triton | 3.0.0 |
| Transformers | 5.5.0 |
| Flash Attention | 2.7.4.post1 |
| xxhash | 3.8.1 |

既有 `.venv` 没有安装 `pip` 模块，WSL PATH 中也没有 `uv`。这不影响当前已安装依赖、单元测试、模型导入或 CUDA 运行，因此本轮没有安装或修改包管理工具。

## 仓库与模型

- WSL 仓库已同步到 Draft PR #7 的 `codex/reproducible-baseline-contract` 分支。
- 正式 baseline 所用源码 commit：`fb94f6b46213174718c2c89d11c86180712f3b53`；三次运行前后工作区均为 clean。
- 模型：`Qwen/Qwen3-0.6B`；`model.safetensors` 为 1,503,300,328 Bytes，SHA-256 为 `f47f71177f32bcd101b7573ec9171e6a57f4f4d31148d38e382306f42996874b`。
- 10 个 Hugging Face 下载 metadata 文件一致记录 revision `c1899de289a04d12100db370d81485cdf75e47ca`。
- 模型配置、Tokenizer、nano-vLLM 入口和 SamplingParams 均可从既有 `.venv` 成功导入。

## 已完成验证

- 全部 9 个单元测试通过：7 个 benchmark 合约测试、Scheduler 生命周期测试和 Snapshot 测试。
- 使用 `enforce_eager=False`、`max_model_len=4096` 实际创建 `LLM`，完成内部 warmup 与 CUDA Graph 捕获初始化；1 Token Prefill 冒烟和 2 Token Prefill→Decode 冒烟均成功，后者实际覆盖一轮 Decode 图回放。两个进程退出码均为 0，退出后无残留 GPU 进程。
- 固定 256 请求 workload 已在三个全新 Python 进程中正式完成，三份 schema v1 JSON 的源码、模型、环境、workload 与计量配置一致；平均输出吞吐为 1014.433126 Token/s，样本标准差为 4.212859 Token/s（`n=3`）。逐次数据、哈希、统计方法和限制见 [`docs/experiments/baseline-results-2026-07-21.md`](../docs/experiments/baseline-results-2026-07-21.md)。该结果是参考 baseline，不是性能提升结论。

## 已知观察项

- WSL 内核日志中存在少量 `dxg` 查询警告，但在最小 CUDA 运算、nano-vLLM Prefill/Decode 冒烟和正式 baseline 期间没有导致失败。若后续 CUDA 实验异常，应优先保留并关联当时的内核日志；当前不据此修改驱动或 WSL 配置。
- 三次正式 measured workload 均出现 PyTorch Dynamo `accumulated_cache_size_limit (256)` 警告，但进程均正常完成并生成有效 JSON。本轮没有修改 cache limit；该现象作为当前软件栈的测量条件保留在正式实验记录中。
- 不需要为了方便调用 `nvidia-smi` 修改 PATH；readiness 与后续诊断可继续使用绝对路径。
- 本次核对时，WSL 到 GitHub HTTPS 的连接停在 `SYN-SENT` 并超时；这不阻塞已经同步到本地的 baseline，但会阻塞后续直接 `git fetch`。本轮没有修改 Windows/WSL 网络或代理，而是从 Mac 通过已验证的 Git bundle 同步单个文档 commit。
