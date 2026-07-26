"""NSL-S3-SCHED-v1 scheduling comparison driver and schema v2 writer.

The Stage 2 saturated admission loop remains the single implementation of the
measured workload lifecycle. This module adds the Stage 3 experiment identity,
an explicit policy definition, comparison-group metadata, runtime policy
verification, and exclusive raw-artifact creation.

Importing this module is Mac-safe. Torch, transformers, and real LLM
construction remain delayed until the CLI runtime path.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter_ns
from types import SimpleNamespace
from typing import Any, Callable

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from research.stage2_saturated_driver import (
    DEFAULT_MODEL_PATH,
    ENFORCE_EAGER,
    GPU_MEMORY_UTILIZATION,
    IGNORE_EOS,
    KVCACHE_BLOCK_SIZE,
    MAX_MODEL_LEN,
    MAX_NUM_BATCHED_TOKENS,
    MAX_NUM_SEQS,
    MODEL_ID,
    MODEL_REVISION,
    SAMPLING_SEED,
    TEMPERATURE,
    TENSOR_PARALLEL_SIZE,
    WARMUP_IGNORE_EOS,
    WARMUP_MAX_TOKENS,
    WARMUP_TEMPERATURE,
    EngineLike,
    RecorderLike,
    SaturatedRunState,
    WarmupDefinition,
    _runtime_environment,
    _synchronize_cuda,
    assert_no_derived_metric_fields,
    build_artifact,
    git_metadata,
    run_saturated_admission,
)
from research.stage2_workload import (
    EXPECTED_MANIFEST_SHA256,
    WORKLOAD_ID,
    SaturatedRequest,
    build_saturated_mixed_workload,
    workload_manifest_sha256,
)

SCHEMA_VERSION = 2
EXPERIMENT_CONTRACT = "NSL-S3-SCHED-v1"
POLICY_DEFINITION_VERSION = 1
DEFAULT_OUTPUT_DIR = Path("results/raw/stage3/scheduling")
FCFS_POLICY = "fcfs-v1"
PROMPT_LENGTH_POLICY = "prompt-length-v1"
SUPPORTED_SCHEDULING_POLICIES = (FCFS_POLICY, PROMPT_LENGTH_POLICY)

_COMPARISON_GROUP_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_POLICY_PARAMETERS: dict[str, dict[str, Any]] = {
    FCFS_POLICY: {},
    PROMPT_LENGTH_POLICY: {
        "fresh_request_key": "num_prompt_tokens",
        "order": "ascending",
        "stable_ties": "arrival_order",
        "recovery_prefix": "preserved",
    },
}


class Stage3SchedulingDriverError(RuntimeError):
    """Stage 3 identity or runtime contract failure."""


def normalize_stage3_policy(policy: str) -> str:
    """Return a Policy ID frozen by this experiment contract."""
    if not isinstance(policy, str) or policy not in SUPPORTED_SCHEDULING_POLICIES:
        supported = ", ".join(SUPPORTED_SCHEDULING_POLICIES)
        raise ValueError(
            f"unsupported Stage 3 policy {policy!r}; expected one of: {supported}"
        )
    return policy


def validate_comparison_group(comparison_group: str) -> str:
    """Return a filesystem-safe comparison-group ID or reject it."""
    if (
        not isinstance(comparison_group, str)
        or _COMPARISON_GROUP_PATTERN.fullmatch(comparison_group) is None
    ):
        raise ValueError(
            "comparison_group must be 1-128 characters using only letters, "
            "digits, '.', '_' or '-', and must start with a letter or digit"
        )
    return comparison_group


def policy_metadata(policy: str, *, runtime_verified: bool) -> dict[str, Any]:
    """Build the exact, versioned policy identity stored in every raw artifact."""
    normalized = normalize_stage3_policy(policy)
    return {
        "id": normalized,
        "definition_version": POLICY_DEFINITION_VERSION,
        "parameters": deepcopy(_POLICY_PARAMETERS[normalized]),
        "runtime_verified": runtime_verified,
    }


def _decorate_stage3_artifact(
    stage2_artifact: dict[str, Any],
    *,
    comparison_group: str,
    policy: str,
    runtime_verified: bool,
    actual_policy: str | None,
) -> dict[str, Any]:
    artifact = deepcopy(stage2_artifact)
    artifact["schema_version"] = SCHEMA_VERSION
    artifact["experiment"] = EXPERIMENT_CONTRACT
    artifact["experiment_contract"] = EXPERIMENT_CONTRACT
    artifact["comparison_group"] = validate_comparison_group(comparison_group)
    artifact["policy"] = policy_metadata(
        policy,
        runtime_verified=runtime_verified,
    )
    artifact["workload"]["id"] = WORKLOAD_ID
    artifact["engine"]["requested_scheduling_policy"] = policy
    artifact["engine"]["scheduling_policy"] = actual_policy
    return artifact


def _error_payload(exc: BaseException) -> dict[str, str]:
    return {
        "type": type(exc).__name__,
        "message": str(exc),
    }


def _failed_stage3_artifact(
    exc: BaseException,
    *,
    comparison_group: str,
    policy: str,
    requests: tuple[SaturatedRequest, ...],
    run_number: int,
    run_id: str,
    created_at: datetime,
    repository: dict[str, Any],
    environment: dict[str, Any],
    model: dict[str, Any],
    engine_metadata: dict[str, Any],
    recorder: RecorderLike | None = None,
) -> dict[str, Any]:
    state = SaturatedRunState(
        requests=requests,
        manifest_sha256=workload_manifest_sha256(requests) if requests else "",
        run_id=run_id,
        run_number=run_number,
        created_at_utc=created_at.isoformat(),
        repository=repository,
        environment=environment,
        model=model,
        engine=engine_metadata,
        warmup_definition=WarmupDefinition(),
        warmup_timing_records=[],
        index_to_seq_id={},
        status="failed",
        error=_error_payload(exc),
    )
    return _decorate_stage3_artifact(
        build_artifact(state, recorder),
        comparison_group=comparison_group,
        policy=policy,
        runtime_verified=False,
        actual_policy=None,
    )


def _runtime_policy(engine: EngineLike) -> str:
    scheduler = getattr(engine, "scheduler", None)
    if scheduler is None or not hasattr(scheduler, "scheduling_policy"):
        raise Stage3SchedulingDriverError(
            "engine does not expose scheduler.scheduling_policy"
        )
    try:
        return normalize_stage3_policy(scheduler.scheduling_policy)
    except ValueError as exc:
        raise Stage3SchedulingDriverError(
            f"engine exposes invalid scheduling policy: {scheduler.scheduling_policy!r}"
        ) from exc


def _validate_repository(repository: dict[str, Any]) -> None:
    commit = repository.get("commit")
    if not isinstance(commit, str) or not commit:
        raise Stage3SchedulingDriverError(
            "repository.commit must identify the exact source commit"
        )
    if repository.get("dirty") is not False:
        raise Stage3SchedulingDriverError(
            "tracked worktree must be clean before a Stage 3 measurement"
        )


def write_stage3_scheduling_artifact(
    artifact: dict[str, Any],
    *,
    output_dir: Path,
    comparison_group: str,
    policy: str,
    run_number: int,
    created_at: datetime | None = None,
) -> Path:
    """Create one Stage 3 raw JSON file without ever replacing an existing path."""
    group = validate_comparison_group(comparison_group)
    normalized_policy = normalize_stage3_policy(policy)
    if run_number <= 0:
        raise ValueError("run_number must be positive")
    if artifact.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"Stage 3 artifact schema_version must be {SCHEMA_VERSION}")
    if artifact.get("experiment_contract") != EXPERIMENT_CONTRACT:
        raise ValueError(
            f"Stage 3 artifact experiment_contract must be {EXPERIMENT_CONTRACT}"
        )
    if artifact.get("comparison_group") != group:
        raise ValueError(
            "artifact comparison_group does not match output identity: "
            f"artifact={artifact.get('comparison_group')!r}, output={group!r}"
        )
    artifact_policy = artifact.get("policy")
    if not isinstance(artifact_policy, dict) or artifact_policy.get("id") != normalized_policy:
        raise ValueError(
            "artifact policy.id does not match output identity: "
            f"artifact={artifact_policy!r}, output={normalized_policy!r}"
        )
    if artifact.get("run_number") != run_number:
        raise ValueError(
            "artifact run_number does not match output identity: "
            f"artifact={artifact.get('run_number')!r}, output={run_number!r}"
        )
    assert_no_derived_metric_fields(artifact)
    serialized = json.dumps(
        artifact,
        indent=2,
        sort_keys=True,
        allow_nan=False,
    ) + "\n"

    created = created_at or datetime.now(timezone.utc)
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = created.strftime("%Y%m%dT%H%M%S.%fZ")
    output_path = output_dir / (
        f"scheduling-{timestamp}-{group}-{normalized_policy}-run{run_number}.json"
    )
    with output_path.open("x", encoding="utf-8") as output_file:
        output_file.write(serialized)
    return output_path


def run_stage3_scheduling_admission(
    *,
    engine: EngineLike,
    recorder: RecorderLike,
    policy: str,
    comparison_group: str,
    sampling_params_factory: Callable[[int], Any],
    warmup_sampling_params: Any,
    clock_ns: Callable[[], int] = perf_counter_ns,
    cuda_synchronize: Callable[[], bool] = lambda: False,
    requests: tuple[SaturatedRequest, ...] | None = None,
    run_number: int = 1,
    run_id: str | None = None,
    created_at: datetime | None = None,
    repository: dict[str, Any] | None = None,
    environment: dict[str, Any] | None = None,
    model: dict[str, Any] | None = None,
    engine_metadata: dict[str, Any] | None = None,
    output_dir: Path | None = None,
    write_artifact: bool = False,
    raise_on_failure: bool = True,
) -> dict[str, Any]:
    """Run one policy measurement while preserving the Stage 2 lifecycle."""
    normalized_policy = normalize_stage3_policy(policy)
    group = validate_comparison_group(comparison_group)
    created = created_at or datetime.now(timezone.utc)
    rid = run_id or str(uuid.uuid4())
    workload = requests if requests is not None else build_saturated_mixed_workload()
    repository_metadata = repository if repository is not None else {}
    environment_metadata = environment if environment is not None else {}
    model_metadata = model if model is not None else {}
    fixed_engine_metadata = deepcopy(
        engine_metadata if engine_metadata is not None else {}
    )
    fixed_engine_metadata["requested_scheduling_policy"] = normalized_policy

    try:
        _validate_repository(repository_metadata)
        actual_policy = _runtime_policy(engine)
        if actual_policy != normalized_policy:
            raise Stage3SchedulingDriverError(
                "requested policy does not match runtime Scheduler: "
                f"requested={normalized_policy!r}, actual={actual_policy!r}"
            )
    except Exception as exc:
        artifact = _failed_stage3_artifact(
            exc,
            comparison_group=group,
            policy=normalized_policy,
            requests=workload,
            run_number=run_number,
            run_id=rid,
            created_at=created,
            repository=repository_metadata,
            environment=environment_metadata,
            model=model_metadata,
            engine_metadata=fixed_engine_metadata,
            recorder=recorder,
        )
        if write_artifact and output_dir is not None:
            write_stage3_scheduling_artifact(
                artifact,
                output_dir=output_dir,
                comparison_group=group,
                policy=normalized_policy,
                run_number=run_number,
                created_at=created,
            )
        if raise_on_failure:
            raise
        return artifact

    stage2_artifact = run_saturated_admission(
        engine=engine,
        recorder=recorder,
        sampling_params_factory=sampling_params_factory,
        warmup_sampling_params=warmup_sampling_params,
        clock_ns=clock_ns,
        cuda_synchronize=cuda_synchronize,
        requests=workload,
        expected_manifest_sha256=EXPECTED_MANIFEST_SHA256,
        run_number=run_number,
        run_id=rid,
        created_at=created,
        repository=repository_metadata,
        environment=environment_metadata,
        model=model_metadata,
        engine_metadata=fixed_engine_metadata,
        write_artifact=False,
        raise_on_failure=False,
    )
    artifact = _decorate_stage3_artifact(
        stage2_artifact,
        comparison_group=group,
        policy=normalized_policy,
        runtime_verified=True,
        actual_policy=actual_policy,
    )
    if write_artifact and output_dir is not None:
        write_stage3_scheduling_artifact(
            artifact,
            output_dir=output_dir,
            comparison_group=group,
            policy=normalized_policy,
            run_number=run_number,
            created_at=created,
        )
    if artifact["status"] != "finished" and raise_on_failure:
        error = artifact.get("error") or {}
        raise Stage3SchedulingDriverError(
            "Stage 3 measurement failed: "
            f"{error.get('type', 'UnknownError')}: {error.get('message', '')}"
        )
    return artifact


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run one NSL-S3-SCHED-v1 scheduling-policy measurement and write "
            "one exclusive schema v2 raw JSON artifact."
        )
    )
    parser.add_argument("--model", default=DEFAULT_MODEL_PATH)
    parser.add_argument(
        "--policy",
        required=True,
        choices=SUPPORTED_SCHEDULING_POLICIES,
        help="Explicit Scheduler policy ID; no implicit CLI default is allowed",
    )
    parser.add_argument(
        "--comparison-group",
        required=True,
        help="Shared ID for the six FCFS/candidate processes",
    )
    parser.add_argument("--run-number", type=int, required=True)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args(argv)
    if args.run_number <= 0:
        parser.error("--run-number must be positive")
    try:
        args.comparison_group = validate_comparison_group(args.comparison_group)
    except ValueError as exc:
        parser.error(str(exc))
    return args


def _default_runtime_loader() -> SimpleNamespace:
    import torch

    from nanovllm import LLM, SamplingParams
    from nanovllm.engine.request_timing import RequestTimingRecorder

    return SimpleNamespace(
        torch=torch,
        LLM=LLM,
        SamplingParams=SamplingParams,
        RequestTimingRecorder=RequestTimingRecorder,
    )


def _default_engine_factory(
    runtime: Any,
    model_path: str,
    recorder: Any,
    policy: str,
) -> Any:
    return runtime.LLM(
        model_path,
        timing_recorder=recorder,
        scheduling_policy=policy,
        enforce_eager=ENFORCE_EAGER,
        max_model_len=MAX_MODEL_LEN,
        max_num_seqs=MAX_NUM_SEQS,
        max_num_batched_tokens=MAX_NUM_BATCHED_TOKENS,
        gpu_memory_utilization=GPU_MEMORY_UTILIZATION,
        tensor_parallel_size=TENSOR_PARALLEL_SIZE,
        kvcache_block_size=KVCACHE_BLOCK_SIZE,
    )


def _fixed_engine_metadata(policy: str) -> dict[str, Any]:
    return {
        "requested_scheduling_policy": policy,
        "scheduling_policy": None,
        "enforce_eager": ENFORCE_EAGER,
        "max_model_len": MAX_MODEL_LEN,
        "max_num_seqs": MAX_NUM_SEQS,
        "max_num_batched_tokens": MAX_NUM_BATCHED_TOKENS,
        "gpu_memory_utilization": GPU_MEMORY_UTILIZATION,
        "tensor_parallel_size": TENSOR_PARALLEL_SIZE,
        "kvcache_block_size": KVCACHE_BLOCK_SIZE,
    }


def main(
    argv: list[str] | None = None,
    *,
    runtime_loader: Callable[[], Any] | None = None,
    engine_factory: Callable[[Any, str, Any, str], Any] | None = None,
    clock_ns: Callable[[], int] = perf_counter_ns,
    created_at: datetime | None = None,
    run_id: str | None = None,
) -> int:
    """CLI entry that performs exactly one exclusive raw-artifact write attempt."""
    args = parse_args(argv)
    created = created_at or datetime.now(timezone.utc)
    rid = run_id or str(uuid.uuid4())
    model_path = str(Path(args.model).expanduser().resolve())
    load_runtime = runtime_loader or _default_runtime_loader
    build_engine = engine_factory or _default_engine_factory

    try:
        repository = git_metadata()
    except Exception:
        repository = {"commit": None, "branch": None, "dirty": None}
    model = {
        "id": MODEL_ID,
        "revision": MODEL_REVISION,
        "local_path": model_path,
    }
    engine_metadata = _fixed_engine_metadata(args.policy)
    environment: dict[str, Any] = {}
    recorder: RecorderLike | None = None
    workload: tuple[SaturatedRequest, ...] = ()
    artifact: dict[str, Any]

    try:
        workload = build_saturated_mixed_workload()
        runtime = load_runtime()
        runtime.torch.manual_seed(SAMPLING_SEED)
        if runtime.torch.cuda.is_available():
            runtime.torch.cuda.manual_seed_all(SAMPLING_SEED)
        environment = _runtime_environment(runtime.torch)
        recorder = runtime.RequestTimingRecorder()
        llm = build_engine(runtime, model_path, recorder, args.policy)

        def sampling_params_factory(max_tokens: int) -> Any:
            return runtime.SamplingParams(
                temperature=TEMPERATURE,
                max_tokens=max_tokens,
                ignore_eos=IGNORE_EOS,
            )

        warmup_sampling_params = runtime.SamplingParams(
            temperature=WARMUP_TEMPERATURE,
            max_tokens=WARMUP_MAX_TOKENS,
            ignore_eos=WARMUP_IGNORE_EOS,
        )
        artifact = run_stage3_scheduling_admission(
            engine=llm,
            recorder=recorder,
            policy=args.policy,
            comparison_group=args.comparison_group,
            sampling_params_factory=sampling_params_factory,
            warmup_sampling_params=warmup_sampling_params,
            clock_ns=clock_ns,
            cuda_synchronize=lambda: _synchronize_cuda(runtime.torch),
            requests=workload,
            run_number=args.run_number,
            run_id=rid,
            created_at=created,
            repository=repository,
            environment=environment,
            model=model,
            engine_metadata=engine_metadata,
            write_artifact=False,
            raise_on_failure=False,
        )
    except Exception as exc:
        artifact = _failed_stage3_artifact(
            exc,
            comparison_group=args.comparison_group,
            policy=args.policy,
            requests=workload,
            run_number=args.run_number,
            run_id=rid,
            created_at=created,
            repository=repository,
            environment=environment,
            model=model,
            engine_metadata=engine_metadata,
            recorder=recorder,
        )

    try:
        output_path = write_stage3_scheduling_artifact(
            artifact,
            output_dir=args.output_dir,
            comparison_group=args.comparison_group,
            policy=args.policy,
            run_number=args.run_number,
            created_at=created,
        )
    except Exception as exc:
        print(
            f"stage3 scheduling driver could not write artifact: "
            f"{type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return 1

    if artifact["status"] != "finished":
        error = artifact.get("error") or {}
        print(
            "stage3 scheduling driver failed: "
            f"{error.get('type', 'UnknownError')}: {error.get('message', '')}; "
            f"artifact={output_path}",
            file=sys.stderr,
        )
        return 1

    print(
        f"experiment={artifact['experiment_contract']} "
        f"group={artifact['comparison_group']} policy={artifact['policy']['id']} "
        f"status={artifact['status']} requests={len(artifact['requests'])} "
        f"artifact={output_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
