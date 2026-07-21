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
- readiness 验证所用源码 commit：`8f63bcd`；运行前工作区为 clean。
- 模型：`Qwen/Qwen3-0.6B`，本地权重约 1.5 GB。
- 9 个 Hugging Face 下载 metadata 文件一致记录 revision `c1899de289a04d12100db370d81485cdf75e47ca`。
- 模型配置、Tokenizer、nano-vLLM 入口和 SamplingParams 均可从既有 `.venv` 成功导入。

## 已完成验证

- 全部 9 个单元测试通过：7 个 benchmark 合约测试、Scheduler 生命周期测试和 Snapshot 测试。
- 使用 `enforce_eager=False`、`max_model_len=4096` 实际创建 `LLM`，完成内部 warmup 与 CUDA Graph 捕获初始化；1 Token Prefill 冒烟和 2 Token Prefill→Decode 冒烟均成功，后者实际覆盖一轮 Decode 图回放。两个进程退出码均为 0，退出后无残留 GPU 进程。
- 未运行正式 baseline benchmark，未生成性能结论。

## 已知观察项

- WSL 内核日志中存在少量 `dxg` 查询警告，但在最小 CUDA 运算和 nano-vLLM Prefill/Decode 冒烟期间没有导致失败。若正式 baseline 异常，应优先保留并关联当时的内核日志；当前不据此修改驱动或 WSL 配置。
- 不需要为了方便调用 `nvidia-smi` 修改 PATH；readiness 与后续诊断可继续使用绝对路径。
