# NanoServeLab Project Log

## 项目信息

- 项目名称：NanoServeLab：面向混合请求负载的轻量级 LLM 推理评测与调度优化
- 创建日期：2026-07-13
- 当前阶段：阶段 0：环境整理、源码阅读与基础学习
- 核心框架：官方 GeeeekExplorer/nano-vllm
- 当前上游源码 commit：`bb823b3e06983d71485a8e1f23715ebd87d98ef8`
- 旧空项目备份：`/Users/lei/Developer/NanoServeLab-bootstrap-backup-20260713-112356`

## 最终目标

- 跑通 nano-vLLM baseline
- 建立 TTFT、TPOT、E2E、Throughput、Queue Time 等指标
- 构造混合长度 workload
- 比较 FCFS、长度优先、Priority、Aging
- 在基础稳定后考虑 Prefix Cache 感知调度
- 完成 README、实验报告和演示

## 当前状态

- 已恢复官方 nano-vLLM 源码、LICENSE 和 Git 历史。
- 当前仅进行恢复和研究工作区初始化。
- 尚未修改核心引擎，尚未运行正式 benchmark。
- 当前没有任何性能优化结果或性能提升结论。

## 当前环境

- macOS：15.5（Build 24F74）
- CPU 架构：arm64
- uv：0.11.11
- Git：2.39.5（Apple Git-154）
- Codex：codex-cli 0.144.1

## 已知约束

- Mac 不用于 nano-vLLM CUDA 正式 benchmark
- Windows RTX 4060 + WSL2 后续作为运行节点
- 12月15日后停止增加新功能
- AI 可以写大量工程代码，但核心调度与实验结论必须理解

## 遇到的问题

- 最初误将项目初始化为空 uv 应用，现已通过保留备份并重新克隆上游安全恢复。
- GitHub CLI 现有认证失效，远程操作尚未执行。

## 下一步

阅读官方 README 和源码结构。
