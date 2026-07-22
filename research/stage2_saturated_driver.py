"""NSL-S2-SAT-v1 saturated admission driver and schema v1 raw JSON writer.

This research-layer module admits the frozen mixed workload through an injected
engine without changing nano-vLLM core APIs. Module import stays Mac-safe: torch,
transformers, and real LLM construction are delayed to the CLI/runtime path.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import platform
import subprocess
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter_ns
from types import SimpleNamespace
from typing import Any, Callable, Protocol

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from research.stage2_workload import (
    EXPECTED_MANIFEST_SHA256,
    REQUEST_COUNT,
    WORKLOAD_ID,
    WORKLOAD_SEED,
    SaturatedRequest,
    build_saturated_mixed_workload,
    workload_manifest_sha256,
)

SCHEMA_VERSION = 1
EXPERIMENT_ID = WORKLOAD_ID
DEFAULT_OUTPUT_DIR = Path("results/raw/stage2/saturated")
DEFAULT_MODEL_PATH = "~/huggingface/Qwen3-0.6B/"
MODEL_ID = "Qwen/Qwen3-0.6B"
MODEL_REVISION = "c1899de289a04d12100db370d81485cdf75e47ca"
SAMPLING_SEED = 0
TEMPERATURE = 0.6
IGNORE_EOS = True
ENFORCE_EAGER = False
MAX_MODEL_LEN = 4096
MAX_NUM_SEQS = 512
MAX_NUM_BATCHED_TOKENS = 16384
GPU_MEMORY_UTILIZATION = 0.9
TENSOR_PARALLEL_SIZE = 1
KVCACHE_BLOCK_SIZE = 256

WARMUP_PROMPT = "Benchmark: "
WARMUP_TEMPERATURE = 0.6
WARMUP_MAX_TOKENS = 64
WARMUP_IGNORE_EOS = True

FORBIDDEN_DERIVED_KEYS = frozenset(
    {
        "queue_time",
        "queue_time_ms",
        "ttft",
        "ttft_ms",
        "tpot",
        "mean_tpot",
        "mean_tpot_ms",
        "e2e",
        "e2e_ms",
        "throughput",
        "throughput_tokens_per_second",
        "percentile",
        "elapsed",
        "elapsed_seconds",
    }
)


class SaturatedDriverError(RuntimeError):
    """Driver-contract failure that should produce a failed raw artifact."""


class EngineLike(Protocol):
    def add_request(self, prompt: str | list[int], sampling_params: Any) -> None: ...

    def step(self) -> Any: ...

    def is_finished(self) -> bool: ...

    def generate(self, prompts: Any, sampling_params: Any) -> Any: ...


class RecorderLike(Protocol):
    def snapshots(self) -> tuple[Any, ...]: ...


@dataclass(frozen=True, slots=True)
class WarmupDefinition:
    prompt: str = WARMUP_PROMPT
    temperature: float = WARMUP_TEMPERATURE
    max_tokens: int = WARMUP_MAX_TOKENS
    ignore_eos: bool = WARMUP_IGNORE_EOS


@dataclass(slots=True)
class SaturatedRunState:
    """Mutable capture buffer used for success and failure artifacts."""

    requests: tuple[SaturatedRequest, ...]
    manifest_sha256: str
    run_id: str
    run_number: int
    created_at_utc: str
    repository: dict[str, Any]
    environment: dict[str, Any]
    model: dict[str, Any]
    engine: dict[str, Any]
    warmup_definition: WarmupDefinition
    warmup_timing_records: list[dict[str, Any]]
    index_to_seq_id: dict[int, int]
    measurement_started_ns: int | None = None
    measurement_ended_ns: int | None = None
    cuda_synchronized: bool = False
    status: str = "finished"
    error: dict[str, Any] | None = None


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


def verify_manifest_fingerprint(
    requests: tuple[SaturatedRequest, ...],
    *,
    expected_sha256: str = EXPECTED_MANIFEST_SHA256,
) -> str:
    digest = workload_manifest_sha256(requests)
    if digest != expected_sha256:
        raise SaturatedDriverError(
            "manifest fingerprint mismatch: "
            f"got {digest}, expected {expected_sha256}"
        )
    return digest


def recorder_seq_ids(recorder: RecorderLike) -> set[int]:
    return {record.seq_id for record in recorder.snapshots()}


def timing_record_to_dict(record: Any) -> dict[str, Any]:
    return {
        "seq_id": record.seq_id,
        "prompt_tokens": record.prompt_tokens,
        "output_tokens": record.output_tokens,
        "outcome": record.outcome,
        "timestamps_ns": {
            "arrival": record.arrival_ns,
            "first_scheduled": record.first_scheduled_ns,
            "first_output": record.first_output_ns,
            "completed": record.completed_ns,
        },
    }


def collect_unmapped_timing_records(
    state: SaturatedRunState,
    recorder: RecorderLike | None,
) -> list[dict[str, Any]]:
    """Raw recorder rows that are neither warmup nor successfully mapped."""
    if recorder is None:
        return []
    warmup_ids = {item["seq_id"] for item in state.warmup_timing_records}
    mapped_ids = set(state.index_to_seq_id.values())
    return [
        timing_record_to_dict(record)
        for record in recorder.snapshots()
        if record.seq_id not in warmup_ids and record.seq_id not in mapped_ids
    ]


def validate_successful_terminal_state(
    state: SaturatedRunState,
    recorder: RecorderLike,
) -> None:
    """Reject success unless every measured request finished with consistent facts."""
    if len(state.index_to_seq_id) != REQUEST_COUNT:
        raise SaturatedDriverError(
            "successful terminal state requires exactly "
            f"{REQUEST_COUNT} mapped requests, got {len(state.index_to_seq_id)}"
        )
    if len(state.requests) != REQUEST_COUNT:
        raise SaturatedDriverError(
            "successful terminal state requires "
            f"{REQUEST_COUNT} workload requests, got {len(state.requests)}"
        )

    records_by_seq = {record.seq_id: record for record in recorder.snapshots()}
    for request in state.requests:
        seq_id = state.index_to_seq_id.get(request.request_index)
        if seq_id is None:
            raise SaturatedDriverError(
                "successful terminal state missing mapping for "
                f"request_index={request.request_index}"
            )
        record = records_by_seq.get(seq_id)
        if record is None:
            raise SaturatedDriverError(
                "successful terminal state missing timing record for "
                f"seq_id={seq_id} (request_index={request.request_index})"
            )
        expected_prompt = len(request.prompt_token_ids)
        if record.prompt_tokens != expected_prompt:
            raise SaturatedDriverError(
                "successful terminal state prompt_tokens mismatch for "
                f"request_index={request.request_index}: "
                f"record={record.prompt_tokens}, expected={expected_prompt}"
            )
        if record.outcome != "finished":
            raise SaturatedDriverError(
                "successful terminal state requires outcome='finished' for "
                f"request_index={request.request_index}, got {record.outcome!r}"
            )
        if record.completed_ns is None:
            raise SaturatedDriverError(
                "successful terminal state requires completed_ns for "
                f"request_index={request.request_index}"
            )
        if record.output_tokens != request.max_tokens:
            raise SaturatedDriverError(
                "successful terminal state output_tokens mismatch for "
                f"request_index={request.request_index}: "
                f"record={record.output_tokens}, "
                f"requested={request.max_tokens}"
            )
        arrival = record.arrival_ns
        first_scheduled = record.first_scheduled_ns
        first_output = record.first_output_ns
        completed = record.completed_ns
        if first_scheduled is None or first_output is None:
            raise SaturatedDriverError(
                "successful terminal state missing required timestamps for "
                f"request_index={request.request_index}"
            )
        if not (arrival <= first_scheduled <= first_output <= completed):
            raise SaturatedDriverError(
                "successful terminal state timestamp order violated for "
                f"request_index={request.request_index}: "
                f"arrival={arrival}, first_scheduled={first_scheduled}, "
                f"first_output={first_output}, completed={completed}"
            )


def map_new_seq_id(
    *,
    recorder: RecorderLike,
    before_ids: set[int],
    request_index: int,
) -> int:
    after_ids = recorder_seq_ids(recorder)
    new_ids = after_ids - before_ids
    if len(new_ids) != 1:
        raise SaturatedDriverError(
            "request_index↔seq_id mapping failed for "
            f"request_index={request_index}: expected exactly one new timing "
            f"record, got {sorted(new_ids)} "
            f"(before={sorted(before_ids)}, after={sorted(after_ids)})"
        )
    return next(iter(new_ids))


def build_measured_request_entry(
    request: SaturatedRequest,
    seq_id: int,
    record: Any | None,
) -> dict[str, Any]:
    if record is None:
        return {
            "request_index": request.request_index,
            "seq_id": seq_id,
            "request_class": request.request_class,
            "prompt_tokens": len(request.prompt_token_ids),
            "requested_output_tokens": request.max_tokens,
            "output_tokens": None,
            "outcome": "incomplete",
            "timestamps_ns": {
                "arrival": None,
                "first_scheduled": None,
                "first_output": None,
                "completed": None,
            },
            "error": None,
        }

    outcome = record.outcome if record.outcome == "finished" else "incomplete"
    return {
        "request_index": request.request_index,
        "seq_id": seq_id,
        "request_class": request.request_class,
        "prompt_tokens": len(request.prompt_token_ids),
        "requested_output_tokens": request.max_tokens,
        "output_tokens": record.output_tokens,
        "outcome": outcome,
        "timestamps_ns": {
            "arrival": record.arrival_ns,
            "first_scheduled": record.first_scheduled_ns,
            "first_output": record.first_output_ns,
            "completed": record.completed_ns if outcome == "finished" else None,
        },
        "error": None,
    }


def build_artifact(state: SaturatedRunState, recorder: RecorderLike | None) -> dict[str, Any]:
    records_by_seq: dict[int, Any] = {}
    if recorder is not None:
        records_by_seq = {record.seq_id: record for record in recorder.snapshots()}

    measured_requests = []
    for request in state.requests:
        seq_id = state.index_to_seq_id.get(request.request_index)
        if seq_id is None:
            continue
        measured_requests.append(
            build_measured_request_entry(
                request,
                seq_id,
                records_by_seq.get(seq_id),
            )
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "experiment": EXPERIMENT_ID,
        "run_id": state.run_id,
        "run_number": state.run_number,
        "created_at_utc": state.created_at_utc,
        "status": state.status,
        "error": state.error,
        "repository": state.repository,
        "environment": state.environment,
        "model": state.model,
        "engine": state.engine,
        "workload": {
            "arrival_model": "saturated_batch",
            "seed": WORKLOAD_SEED,
            "sampling_seed": SAMPLING_SEED,
            "request_count": REQUEST_COUNT,
            "manifest_sha256": state.manifest_sha256,
        },
        "warmup": {
            "measured": False,
            "prompt": state.warmup_definition.prompt,
            "sampling": {
                "temperature": state.warmup_definition.temperature,
                "max_tokens": state.warmup_definition.max_tokens,
                "ignore_eos": state.warmup_definition.ignore_eos,
            },
            "timing_records": list(state.warmup_timing_records),
        },
        "measurement": {
            "clock": "time.perf_counter_ns",
            "started_ns": state.measurement_started_ns,
            "ended_ns": state.measurement_ended_ns,
            "cuda_synchronized": state.cuda_synchronized,
        },
        "requests": measured_requests,
        "unmapped_timing_records": collect_unmapped_timing_records(state, recorder),
    }


def write_saturated_artifact(
    artifact: dict[str, Any],
    *,
    output_dir: Path,
    run_number: int,
    created_at: datetime | None = None,
) -> Path:
    created = created_at or datetime.now(timezone.utc)
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = created.strftime("%Y%m%dT%H%M%S.%fZ")
    output_path = output_dir / f"saturated-{timestamp}-run{run_number}.json"
    output_path.write_text(
        json.dumps(artifact, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return output_path


def assert_no_derived_metric_fields(payload: Any, path: str = "$") -> None:
    if isinstance(payload, dict):
        for key, value in payload.items():
            lowered = str(key).lower()
            if key in FORBIDDEN_DERIVED_KEYS or lowered in FORBIDDEN_DERIVED_KEYS:
                raise AssertionError(f"forbidden derived field at {path}.{key}")
            assert_no_derived_metric_fields(value, f"{path}.{key}")
    elif isinstance(payload, list):
        for index, item in enumerate(payload):
            assert_no_derived_metric_fields(item, f"{path}[{index}]")


def _error_payload(exc: BaseException) -> dict[str, str]:
    return {
        "type": type(exc).__name__,
        "message": str(exc),
    }


def run_saturated_admission(
    *,
    engine: EngineLike,
    recorder: RecorderLike,
    sampling_params_factory: Callable[[int], Any],
    warmup_sampling_params: Any,
    clock_ns: Callable[[], int] = perf_counter_ns,
    cuda_synchronize: Callable[[], bool] = lambda: False,
    requests: tuple[SaturatedRequest, ...] | None = None,
    expected_manifest_sha256: str = EXPECTED_MANIFEST_SHA256,
    run_number: int = 1,
    run_id: str | None = None,
    created_at: datetime | None = None,
    repository: dict[str, Any] | None = None,
    environment: dict[str, Any] | None = None,
    model: dict[str, Any] | None = None,
    engine_metadata: dict[str, Any] | None = None,
    warmup_definition: WarmupDefinition | None = None,
    output_dir: Path | None = None,
    write_artifact: bool = False,
    raise_on_failure: bool = True,
) -> dict[str, Any]:
    """Execute warmup + saturated admission and build a schema v1 artifact.

    On contract or runtime failure the returned artifact has ``status="failed"``
    and preserves as much warmup/mapping/timing evidence as possible.
    ``measurement.ended_ns`` is only set after every measured request finishes
    and the trailing CUDA synchronize completes. ``cuda_synchronized`` is true
    only when both measurement-boundary sync callbacks report real CUDA sync.
    When ``raise_on_failure`` is true (default), the original exception is
    re-raised after the failed artifact is built/written so CLI exits non-zero.
    """
    created = created_at or datetime.now(timezone.utc)
    workload = requests if requests is not None else build_saturated_mixed_workload()
    warmup_def = warmup_definition or WarmupDefinition()
    state = SaturatedRunState(
        requests=workload,
        manifest_sha256=workload_manifest_sha256(workload),
        run_id=run_id or str(uuid.uuid4()),
        run_number=run_number,
        created_at_utc=created.isoformat(),
        repository=repository if repository is not None else {},
        environment=environment if environment is not None else {},
        model=model if model is not None else {},
        engine=engine_metadata if engine_metadata is not None else {},
        warmup_definition=warmup_def,
        warmup_timing_records=[],
        index_to_seq_id={},
    )
    failure: Exception | None = None
    start_cuda_synced = False
    end_cuda_synced = False

    try:
        if state.manifest_sha256 != expected_manifest_sha256:
            raise SaturatedDriverError(
                "manifest fingerprint mismatch: "
                f"got {state.manifest_sha256}, expected {expected_manifest_sha256}"
            )
        if len(workload) != REQUEST_COUNT:
            raise SaturatedDriverError(
                f"workload request_count must be {REQUEST_COUNT}, got {len(workload)}"
            )

        engine.generate([warmup_def.prompt], warmup_sampling_params)
        state.warmup_timing_records = [
            timing_record_to_dict(record) for record in recorder.snapshots()
        ]
        warmup_seq_ids = {item["seq_id"] for item in state.warmup_timing_records}

        start_cuda_synced = bool(cuda_synchronize())
        state.measurement_started_ns = clock_ns()

        for request in workload:
            before_ids = recorder_seq_ids(recorder)
            engine.add_request(
                list(request.prompt_token_ids),
                sampling_params_factory(request.max_tokens),
            )
            seq_id = map_new_seq_id(
                recorder=recorder,
                before_ids=before_ids,
                request_index=request.request_index,
            )
            if seq_id in warmup_seq_ids:
                raise SaturatedDriverError(
                    f"measured request_index={request.request_index} reused "
                    f"warmup seq_id={seq_id}"
                )
            state.index_to_seq_id[request.request_index] = seq_id

        if len(state.index_to_seq_id) != REQUEST_COUNT:
            raise SaturatedDriverError(
                "saturated admission mapped "
                f"{len(state.index_to_seq_id)} requests, expected {REQUEST_COUNT}"
            )

        while not engine.is_finished():
            engine.step()

        validate_successful_terminal_state(state, recorder)

        end_cuda_synced = bool(cuda_synchronize())
        state.measurement_ended_ns = clock_ns()
        state.cuda_synchronized = bool(start_cuda_synced and end_cuda_synced)
        state.status = "finished"
        state.error = None
    except Exception as exc:
        failure = exc
        state.status = "failed"
        state.error = _error_payload(exc)
        state.measurement_ended_ns = None
        state.cuda_synchronized = False

    artifact = build_artifact(state, recorder)
    if write_artifact and output_dir is not None:
        write_saturated_artifact(
            artifact,
            output_dir=output_dir,
            run_number=run_number,
            created_at=created,
        )
    if failure is not None and raise_on_failure:
        raise failure
    return artifact


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run one NSL-S2-SAT-v1 saturated admission measurement and write a "
            "schema v1 raw JSON artifact. Workload shape is frozen and not "
            "overridable via CLI."
        )
    )
    parser.add_argument("--model", default=DEFAULT_MODEL_PATH, help="Local model directory")
    parser.add_argument("--run-number", type=int, default=1)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory for saturated-<UTC>-run<N>.json",
    )
    args = parser.parse_args(argv)
    if args.run_number <= 0:
        parser.error("--run-number must be positive")
    return args


def _runtime_environment(torch_module: Any) -> dict[str, Any]:
    device_name = (
        torch_module.cuda.get_device_name(0)
        if torch_module.cuda.is_available()
        else None
    )
    return {
        "platform": platform.platform(),
        "python": sys.version,
        "packages": {
            "torch": package_version("torch"),
            "triton": package_version("triton"),
            "transformers": package_version("transformers"),
            "flash-attn": package_version("flash-attn"),
            "xxhash": package_version("xxhash"),
        },
        "torch_cuda_build": torch_module.version.cuda,
        "cuda_available": torch_module.cuda.is_available(),
        "cuda_device": device_name,
    }


def _synchronize_cuda(torch_module: Any) -> bool:
    """Return True only when CUDA is available and synchronize() succeeds."""
    if not torch_module.cuda.is_available():
        return False
    torch_module.cuda.synchronize()
    return True


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
) -> Any:
    return runtime.LLM(
        model_path,
        timing_recorder=recorder,
        enforce_eager=ENFORCE_EAGER,
        max_model_len=MAX_MODEL_LEN,
        max_num_seqs=MAX_NUM_SEQS,
        max_num_batched_tokens=MAX_NUM_BATCHED_TOKENS,
        gpu_memory_utilization=GPU_MEMORY_UTILIZATION,
        tensor_parallel_size=TENSOR_PARALLEL_SIZE,
        kvcache_block_size=KVCACHE_BLOCK_SIZE,
    )


def _fixed_engine_metadata() -> dict[str, Any]:
    return {
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
    engine_factory: Callable[[Any, str, Any], Any] | None = None,
    clock_ns: Callable[[], int] = perf_counter_ns,
    created_at: datetime | None = None,
    run_id: str | None = None,
) -> int:
    """CLI entry. Setup and measurement failures write at most one schema v1 JSON."""
    args = parse_args(argv)
    created = created_at or datetime.now(timezone.utc)
    rid = run_id or str(uuid.uuid4())
    model_path = str(Path(args.model).expanduser().resolve())
    output_dir = args.output_dir
    load_runtime = runtime_loader or _default_runtime_loader
    build_engine = engine_factory or _default_engine_factory

    repository: dict[str, Any]
    try:
        repository = git_metadata()
    except Exception:
        repository = {"commit": None, "branch": None, "dirty": None}

    model = {
        "id": MODEL_ID,
        "revision": MODEL_REVISION,
        "local_path": model_path,
    }
    engine_metadata = _fixed_engine_metadata()

    workload: tuple[SaturatedRequest, ...] = ()
    manifest_sha256 = ""
    try:
        workload = build_saturated_mixed_workload()
        manifest_sha256 = workload_manifest_sha256(workload)
    except Exception:
        workload = ()
        manifest_sha256 = ""

    environment: dict[str, Any] = {}
    recorder: RecorderLike | None = None
    artifact_written = False

    def write_setup_failure(exc: BaseException) -> None:
        nonlocal artifact_written
        if artifact_written:
            return
        state = SaturatedRunState(
            requests=workload,
            manifest_sha256=manifest_sha256,
            run_id=rid,
            run_number=args.run_number,
            created_at_utc=created.isoformat(),
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
        artifact = build_artifact(state, recorder)
        write_saturated_artifact(
            artifact,
            output_dir=output_dir,
            run_number=args.run_number,
            created_at=created,
        )
        artifact_written = True

    try:
        runtime = load_runtime()
        runtime.torch.manual_seed(SAMPLING_SEED)
        if runtime.torch.cuda.is_available():
            runtime.torch.cuda.manual_seed_all(SAMPLING_SEED)
        environment = _runtime_environment(runtime.torch)
        recorder = runtime.RequestTimingRecorder()
        llm = build_engine(runtime, model_path, recorder)

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

        try:
            artifact = run_saturated_admission(
                engine=llm,
                recorder=recorder,
                sampling_params_factory=sampling_params_factory,
                warmup_sampling_params=warmup_sampling_params,
                clock_ns=clock_ns,
                cuda_synchronize=lambda: _synchronize_cuda(runtime.torch),
                requests=workload if workload else None,
                run_number=args.run_number,
                run_id=rid,
                created_at=created,
                repository=repository,
                environment=environment,
                model=model,
                engine_metadata=engine_metadata,
                output_dir=output_dir,
                write_artifact=True,
                raise_on_failure=True,
            )
        except Exception:
            # Admission always writes when write_artifact=True before re-raising.
            artifact_written = True
            raise
        artifact_written = True
    except Exception as exc:
        write_setup_failure(exc)
        print(f"saturated driver failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    print(
        f"experiment={artifact['experiment']} status={artifact['status']} "
        f"requests={len(artifact['requests'])}"
    )
    return 0 if artifact["status"] == "finished" else 1


if __name__ == "__main__":
    raise SystemExit(main())
