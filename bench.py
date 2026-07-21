"""Run one reproducible nano-vLLM synthetic throughput measurement.

The workload keeps the official upstream benchmark shape.  This entry point runs
exactly one measured batch per process so that repeated experiments can start
from a fresh engine and prefix-cache state.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import platform
import random
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
DEFAULT_MODEL_PATH = "~/huggingface/Qwen3-0.6B/"
DEFAULT_MODEL_ID = "Qwen/Qwen3-0.6B"


def build_workload(
    *,
    random_seed: int,
    num_seqs: int,
    min_input_len: int,
    max_input_len: int,
    min_output_len: int,
    max_output_len: int,
    max_token_id: int,
) -> tuple[list[list[int]], list[int]]:
    """Build the deterministic workload used by the upstream benchmark."""
    rng = random.Random(random_seed)
    prompt_token_ids = [
        [
            rng.randint(0, max_token_id)
            for _ in range(rng.randint(min_input_len, max_input_len))
        ]
        for _ in range(num_seqs)
    ]
    output_lengths = [
        rng.randint(min_output_len, max_output_len) for _ in range(num_seqs)
    ]
    return prompt_token_ids, output_lengths


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=DEFAULT_MODEL_PATH, help="Local model directory")
    parser.add_argument("--model-id", default=DEFAULT_MODEL_ID, help="Stable model identifier")
    parser.add_argument(
        "--model-revision",
        required=True,
        help="Exact model commit/revision; recorded in the raw artifact",
    )
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--run-number", type=int, default=1)
    parser.add_argument("--num-seqs", type=int, default=256)
    parser.add_argument("--min-input-len", type=int, default=100)
    parser.add_argument("--max-input-len", type=int, default=1024)
    parser.add_argument("--min-output-len", type=int, default=100)
    parser.add_argument("--max-output-len", type=int, default=1024)
    parser.add_argument("--max-token-id", type=int, default=10000)
    parser.add_argument("--max-model-len", type=int, default=4096)
    parser.add_argument("--temperature", type=float, default=0.6)
    parser.add_argument("--output-dir", type=Path, default=Path("results/raw/baseline"))
    args = parser.parse_args(argv)

    positive_names = (
        "run_number",
        "num_seqs",
        "min_input_len",
        "max_input_len",
        "min_output_len",
        "max_output_len",
        "max_model_len",
    )
    for name in positive_names:
        if getattr(args, name) <= 0:
            parser.error(f"--{name.replace('_', '-')} must be positive")
    if args.min_input_len > args.max_input_len:
        parser.error("--min-input-len must not exceed --max-input-len")
    if args.min_output_len > args.max_output_len:
        parser.error("--min-output-len must not exceed --max-output-len")
    if args.max_input_len + args.max_output_len > args.max_model_len:
        parser.error("maximum input + output lengths must not exceed --max-model-len")
    if args.max_token_id < 0:
        parser.error("--max-token-id must be non-negative")
    if not args.model_revision.strip():
        parser.error("--model-revision must not be empty")
    return args


def package_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def git_metadata() -> dict[str, Any]:
    def git(*args: str) -> str | None:
        completed = subprocess.run(
            ["git", *args],
            check=False,
            capture_output=True,
            text=True,
        )
        return completed.stdout.strip() if completed.returncode == 0 else None

    status = git("status", "--porcelain")
    return {
        "commit": git("rev-parse", "HEAD"),
        "branch": git("branch", "--show-current"),
        "dirty": bool(status) if status is not None else None,
    }


def synchronize_cuda(torch_module: Any) -> None:
    if torch_module.cuda.is_available():
        torch_module.cuda.synchronize()


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    # Delayed imports keep CLI validation and Mac-side unit tests CUDA-independent.
    import torch

    from nanovllm import LLM, SamplingParams

    prompt_token_ids, output_lengths = build_workload(
        random_seed=args.seed,
        num_seqs=args.num_seqs,
        min_input_len=args.min_input_len,
        max_input_len=args.max_input_len,
        min_output_len=args.min_output_len,
        max_output_len=args.max_output_len,
        max_token_id=args.max_token_id,
    )
    sampling_params = [
        SamplingParams(temperature=args.temperature, ignore_eos=True, max_tokens=length)
        for length in output_lengths
    ]

    model_path = str(Path(os.path.expanduser(args.model)).resolve())
    llm = LLM(model_path, enforce_eager=False, max_model_len=args.max_model_len)

    # Preserve upstream's single, untimed warmup request.
    llm.generate(["Benchmark: "], SamplingParams())
    synchronize_cuda(torch)
    started = time.perf_counter()
    llm.generate(prompt_token_ids, sampling_params, use_tqdm=False)
    synchronize_cuda(torch)
    elapsed_seconds = time.perf_counter() - started

    total_output_tokens = sum(output_lengths)
    throughput = total_output_tokens / elapsed_seconds
    created_at = datetime.now(timezone.utc)
    device_name = torch.cuda.get_device_name(0) if torch.cuda.is_available() else None
    artifact = {
        "schema_version": SCHEMA_VERSION,
        "benchmark": "nano_vllm_upstream_synthetic_throughput",
        "created_at_utc": created_at.isoformat(),
        "run_number": args.run_number,
        "repository": git_metadata(),
        "environment": {
            "platform": platform.platform(),
            "python": sys.version,
            "packages": {
                "torch": package_version("torch"),
                "triton": package_version("triton"),
                "transformers": package_version("transformers"),
                "flash-attn": package_version("flash-attn"),
                "xxhash": package_version("xxhash"),
            },
            "torch_cuda_build": torch.version.cuda,
            "cuda_available": torch.cuda.is_available(),
            "cuda_device": device_name,
        },
        "model": {
            "id": args.model_id,
            "revision": args.model_revision,
            "local_path": model_path,
        },
        "engine": {
            "enforce_eager": False,
            "max_model_len": args.max_model_len,
        },
        "workload": {
            "seed": args.seed,
            "num_seqs": args.num_seqs,
            "input_length": {
                "distribution": "uniform_integer",
                "min": args.min_input_len,
                "max": args.max_input_len,
            },
            "output_length": {
                "distribution": "uniform_integer",
                "min": args.min_output_len,
                "max": args.max_output_len,
            },
            "token_id": {
                "distribution": "uniform_integer",
                "min": 0,
                "max": args.max_token_id,
            },
            "sampling": {"temperature": args.temperature, "ignore_eos": True},
        },
        "warmup": {
            "measured": False,
            "requests": 1,
            "prompt": "Benchmark: ",
        },
        "measurement": {
            "clock": "time.perf_counter",
            "cuda_synchronized": torch.cuda.is_available(),
            "elapsed_seconds": elapsed_seconds,
            "total_output_tokens": total_output_tokens,
            "throughput_tokens_per_second": throughput,
        },
    }

    args.output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = created_at.strftime("%Y%m%dT%H%M%S.%fZ")
    output_path = args.output_dir / f"baseline-{timestamp}-run{args.run_number}.json"
    output_path.write_text(
        json.dumps(artifact, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    print(
        f"Total: {total_output_tokens}tok, Time: {elapsed_seconds:.2f}s, "
        f"Throughput: {throughput:.2f}tok/s"
    )
    print(f"Raw result: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
