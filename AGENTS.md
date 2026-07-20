# NanoServeLab Development Guidelines

## Project Navigation

At the beginning of every new conversation or AI handoff:

1. Read `docs/project/README.md` first. It is the single source of truth for the current stage, verified progress, active work, and next implementation target.
2. Read only the stable or historical documents linked from that entry when the task requires them.
3. Verify live Git and pull-request state before changing code; the status document records the last verified snapshot, not a substitute for live checks.
4. Do not repeat completed source analysis or validated tests unless relevant code, dependencies, or environment facts changed.

Whenever a milestone, validation result, blocker, or next target changes, update `docs/project/README.md` and append the durable event to `docs/project/PROJECT_LOG.md` in the same scoped change. Do not create competing current-status documents elsewhere.

## Project Goal

NanoServeLab is a lightweight LLM inference evaluation and scheduling research project built on the official GeeeekExplorer/nano-vllm engine.

## User Level

The project owner is completing a research project independently for the first time and is rebuilding Python skills while learning PyTorch and LLM Infra.

## Upstream

- The core engine is based on GeeeekExplorer/nano-vllm.
- Preserve upstream history and LICENSE.
- The `upstream` remote points to the official repository.
- Never push to upstream.
- Do not rewrite the engine from scratch.
- Do not replace working upstream components with AI-generated alternatives.

## AI Coding Rules

- Do not generate the entire project.
- Make small, reviewable diffs.
- Explain core concepts before changing scheduler or KV-cache code.
- Preserve baseline behavior unless explicitly changing it.
- Add tests for behavior-changing code.
- Never fabricate benchmark results.
- Do not claim performance gains without repeated experiments.
- Keep changes scoped to the active milestone.

## Critical Code

The project owner must understand:

- Request lifecycle
- Scheduler decisions
- Prefill and decode
- KV-cache allocation and release
- Prefix-cache matching
- TTFT and TPOT
- Custom scheduling score
- Experiment variable control

## Environment

- Mac is for development and lightweight testing.
- Windows WSL2 with RTX 4060 is for CUDA benchmark.
- Do not attempt to install CUDA-only nano-vLLM dependencies on macOS.
- Do not run `uv sync` at repository root on macOS.
- Do not alter upstream pyproject.toml only to force macOS compatibility.

## Experiment Rules

- Record hardware and software versions.
- Keep one variable changed at a time.
- Use fixed random seeds.
- Run important benchmarks at least three times.
- Save raw results before drawing conclusions.
- Report negative results honestly.
