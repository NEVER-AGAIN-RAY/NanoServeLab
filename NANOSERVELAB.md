# NanoServeLab

## 项目名称

NanoServeLab：面向混合请求负载的轻量级 LLM 推理评测与调度优化

## 上游项目

本项目基于 GeeeekExplorer/nano-vllm 开发。

- 保留原项目 LICENSE；
- 保留原项目 Git 历史；
- `upstream` 指向官方仓库；
- NanoServeLab 的主要贡献位于 `research/`、`experiments/`、`results/` 和项目文档；
- 后续可能对 `nanovllm` 中 Scheduler、Request、KV Cache 进行小范围研究性修改；
- 所有性能结论必须由真实 benchmark 支持。

## 研究问题

“在单张消费级 GPU 上，面对长短混合的在线 LLM 请求，长度感知、等待时间感知以及 Prefix Cache 感知调度，能否在不显著降低吞吐量的情况下改善 TTFT、TPOT、尾延迟与公平性？”

## 当前阶段

阶段 0：环境整理、源码阅读与基础学习。

## 开发架构

- MacBook M4：代码开发、阅读、数据分析、文档；
- Windows RTX 4060 + WSL2：CUDA 推理与正式 benchmark；
- GitHub Private 仓库：同步代码与实验结果。

## 阶段计划

- 阶段 0：Python/PyTorch 基础
- 阶段 1：nano-vLLM Baseline
- 阶段 2：指标与混合负载
- 阶段 3：调度策略比较
- 阶段 4：Prefix Cache 感知扩展
- 阶段 5：报告与项目交付

## 当前边界

- 尚未修改 nano-vLLM 核心代码；
- 尚未安装 CUDA 依赖；
- 尚未运行 benchmark；
- 不声称已有性能提升。
