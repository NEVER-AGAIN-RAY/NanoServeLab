"""Offline NSL-S2-SAT-v1 schema v1 aggregation.

Reads raw JSON only. Reuses RequestTimingRecord + derive_request_metrics().
Import and CLI --help stay Mac-safe: no torch, no nanovllm package __init__.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import sys
import types
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

SCHEMA_VERSION = 1
AGGREGATOR_ID = "NSL-S2-AGG-v1"
EXPERIMENT_ID = "NSL-S2-SAT-v1"
WORKLOAD_MANIFEST_SHA256 = (
    "aa1d4e345e0e9f599bd43093bd5b9214476aa3145ee910cc9137d0b62754767d"
)

_KNOWN_OUTCOMES = frozenset({"finished", "failed", "cancelled", "incomplete"})
_KNOWN_RUN_STATUSES = frozenset({"finished", "failed"})


class AggregateError(ValueError):
    """Invalid aggregation input or output contract failure."""


def _ensure_nanovllm_engine_namespace() -> None:
    """Allow importing engine submodules without nanovllm/__init__.py (torch)."""
    if "nanovllm" not in sys.modules or not hasattr(sys.modules["nanovllm"], "__path__"):
        pkg = types.ModuleType("nanovllm")
        pkg.__path__ = [str(_REPO_ROOT / "nanovllm")]
        pkg.__package__ = "nanovllm"
        sys.modules["nanovllm"] = pkg
    if "nanovllm.engine" not in sys.modules or not hasattr(
        sys.modules["nanovllm.engine"], "__path__"
    ):
        engine = types.ModuleType("nanovllm.engine")
        engine.__path__ = [str(_REPO_ROOT / "nanovllm" / "engine")]
        engine.__package__ = "nanovllm.engine"
        sys.modules["nanovllm.engine"] = engine


_ensure_nanovllm_engine_namespace()
from nanovllm.engine.request_metrics import derive_request_metrics  # noqa: E402
from nanovllm.engine.request_timing import RequestTimingRecord  # noqa: E402


def _reject_json_constant(value: str) -> None:
    raise AggregateError(f"non-finite JSON number is not allowed: {value}")


def _validate_finite_json(value: Any, path: str = "$") -> None:
    if isinstance(value, float):
        if not math.isfinite(value):
            raise AggregateError(f"{path}: non-finite number is not allowed")
        return
    if isinstance(value, dict):
        for key, child in value.items():
            _validate_finite_json(child, f"{path}.{key}")
        return
    if isinstance(value, list):
        for index, child in enumerate(value):
            _validate_finite_json(child, f"{path}[{index}]")


def _require_object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise AggregateError(f"{label} must be an object")
    return value


def _require_key(mapping: dict[str, Any], key: str, label: str) -> Any:
    if key not in mapping:
        raise AggregateError(f"{label} missing required field {key!r}")
    return mapping[key]


def _require_int(value: Any, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise AggregateError(f"{label} must be an integer")
    return value


def _require_non_empty_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise AggregateError(f"{label} must be a non-empty string")
    return value


def nearest_rank(sorted_values: list[float], p: float) -> float:
    """1-based nearest-rank: value at index ceil(p * n)."""
    if not sorted_values:
        raise AggregateError("nearest-rank requires a non-empty sample")
    if not 0.0 < p <= 1.0:
        raise AggregateError(f"percentile p must be in (0, 1], got {p}")
    n = len(sorted_values)
    rank = math.ceil(p * n)
    return sorted_values[rank - 1]


def summarize_values(values: list[float]) -> dict[str, Any]:
    if not values:
        return {
            "n": 0,
            "mean": None,
            "median": None,
            "min": None,
            "max": None,
            "sample_std": None,
            "p50": None,
            "p95": None,
            "p99": None,
        }
    ordered = sorted(values)
    n = len(ordered)
    return {
        "n": n,
        "mean": statistics.fmean(ordered),
        "median": statistics.median(ordered),
        "min": ordered[0],
        "max": ordered[-1],
        "sample_std": statistics.stdev(ordered) if n >= 2 else None,
        "p50": nearest_rank(ordered, 0.50),
        "p95": nearest_rank(ordered, 0.95),
        "p99": nearest_rank(ordered, 0.99),
    }


def extract_compatibility(raw: dict[str, Any]) -> dict[str, Any]:
    repository = _require_object(raw.get("repository"), "repository")
    environment = _require_object(raw.get("environment"), "environment")
    packages = _require_object(environment.get("packages"), "environment.packages")
    model = _require_object(raw.get("model"), "model")
    engine = _require_object(raw.get("engine"), "engine")
    workload = _require_object(raw.get("workload"), "workload")

    package_versions = {
        name: _require_non_empty_string(
            _require_key(packages, name, "environment.packages"),
            f"environment.packages.{name}",
        )
        for name in ("torch", "triton", "transformers", "flash-attn", "xxhash")
    }
    cuda_available = _require_key(environment, "cuda_available", "environment")
    if not isinstance(cuda_available, bool):
        raise AggregateError("environment.cuda_available must be a boolean")

    workload_identity = {
        "arrival_model": _require_non_empty_string(
            _require_key(workload, "arrival_model", "workload"),
            "workload.arrival_model",
        ),
        "seed": _require_int(
            _require_key(workload, "seed", "workload"), "workload.seed"
        ),
        "sampling_seed": _require_int(
            _require_key(workload, "sampling_seed", "workload"),
            "workload.sampling_seed",
        ),
        "request_count": _require_int(
            _require_key(workload, "request_count", "workload"),
            "workload.request_count",
        ),
        "manifest_sha256": _require_non_empty_string(
            _require_key(workload, "manifest_sha256", "workload"),
            "workload.manifest_sha256",
        ),
    }
    expected_workload = {
        "arrival_model": "saturated_batch",
        "seed": 0,
        "sampling_seed": 0,
        "request_count": 64,
        "manifest_sha256": WORKLOAD_MANIFEST_SHA256,
    }
    if workload_identity != expected_workload:
        raise AggregateError(
            "workload identity does not match frozen NSL-S2-SAT-v1 contract"
        )

    return {
        "repository_commit": _require_non_empty_string(
            _require_key(repository, "commit", "repository"),
            "repository.commit",
        ),
        "environment": {
            "python": _require_non_empty_string(
                _require_key(environment, "python", "environment"),
                "environment.python",
            ),
            "packages": package_versions,
            "torch_cuda_build": _require_non_empty_string(
                _require_key(environment, "torch_cuda_build", "environment"),
                "environment.torch_cuda_build",
            ),
            "cuda_available": cuda_available,
            "cuda_device": _require_non_empty_string(
                _require_key(environment, "cuda_device", "environment"),
                "environment.cuda_device",
            ),
        },
        "model": {
            "id": _require_non_empty_string(
                _require_key(model, "id", "model"), "model.id"
            ),
            "revision": _require_non_empty_string(
                _require_key(model, "revision", "model"), "model.revision"
            ),
        },
        "engine": dict(engine),
        "workload": workload_identity,
    }


def _load_raw_source(path: Path) -> tuple[dict[str, Any], str]:
    try:
        raw_bytes = path.read_bytes()
    except OSError as exc:
        raise AggregateError(f"cannot read raw file {path.name}: {exc}") from exc
    try:
        text = raw_bytes.decode("utf-8")
    except UnicodeError as exc:
        raise AggregateError(f"cannot decode raw file {path.name}: {exc}") from exc
    try:
        payload = json.loads(text, parse_constant=_reject_json_constant)
    except json.JSONDecodeError as exc:
        raise AggregateError(f"malformed JSON in {path.name}: {exc}") from exc
    _validate_finite_json(payload)
    if not isinstance(payload, dict):
        raise AggregateError(f"{path.name}: top-level JSON must be an object")
    schema_version = payload.get("schema_version")
    if (
        not isinstance(schema_version, int)
        or isinstance(schema_version, bool)
        or schema_version != SCHEMA_VERSION
    ):
        raise AggregateError(
            f"{path.name}: schema_version must be {SCHEMA_VERSION}, "
            f"got {schema_version!r}"
        )
    if payload.get("experiment") != EXPERIMENT_ID:
        raise AggregateError(
            f"{path.name}: experiment must be {EXPERIMENT_ID!r}, "
            f"got {payload.get('experiment')!r}"
        )
    repository = _require_object(payload.get("repository"), "repository")
    if repository.get("dirty") is not False:
        raise AggregateError(
            f"{path.name}: repository.dirty must be false, got {repository.get('dirty')!r}"
        )
    for key in (
        "run_id",
        "run_number",
        "status",
        "requests",
        "measurement",
        "unmapped_timing_records",
        "workload",
        "model",
        "engine",
        "environment",
    ):
        if key not in payload:
            raise AggregateError(f"{path.name}: missing required field {key!r}")
    if payload["status"] not in _KNOWN_RUN_STATUSES:
        raise AggregateError(
            f"{path.name}: status must be 'finished' or 'failed', "
            f"got {payload['status']!r}"
        )
    if not isinstance(payload["requests"], list):
        raise AggregateError(f"{path.name}: requests must be a list")
    if not isinstance(payload["measurement"], dict):
        raise AggregateError(f"{path.name}: measurement must be an object")
    if not isinstance(payload["unmapped_timing_records"], list):
        raise AggregateError(
            f"{path.name}: unmapped_timing_records must be a list"
        )
    return payload, hashlib.sha256(raw_bytes).hexdigest()


def request_to_timing_record(request: dict[str, Any]) -> RequestTimingRecord:
    timestamps = request.get("timestamps_ns")
    if not isinstance(timestamps, dict):
        raise AggregateError("timestamps_ns must be an object")
    arrival = timestamps.get("arrival")
    if arrival is None:
        raise AggregateError("arrival timestamp is missing")
    return RequestTimingRecord(
        seq_id=_require_int(_require_key(request, "seq_id", "request"), "seq_id"),
        prompt_tokens=_require_int(
            _require_key(request, "prompt_tokens", "request"), "prompt_tokens"
        ),
        output_tokens=_require_int(
            _require_key(request, "output_tokens", "request"), "output_tokens"
        ),
        outcome=request.get("outcome"),
        arrival_ns=_require_int(arrival, "timestamps_ns.arrival"),
        first_scheduled_ns=(
            None
            if timestamps.get("first_scheduled") is None
            else _require_int(
                timestamps["first_scheduled"], "timestamps_ns.first_scheduled"
            )
        ),
        first_output_ns=(
            None
            if timestamps.get("first_output") is None
            else _require_int(timestamps["first_output"], "timestamps_ns.first_output")
        ),
        completed_ns=(
            None
            if timestamps.get("completed") is None
            else _require_int(timestamps["completed"], "timestamps_ns.completed")
        ),
    )


def classify_request(
    request: dict[str, Any],
) -> tuple[str, dict[str, float | None] | None, bool]:
    """Return (outcome_bucket, latency_metrics_or_none, is_invalid)."""
    outcome = request.get("outcome")
    if outcome in _KNOWN_OUTCOMES:
        bucket = str(outcome)
    else:
        bucket = "other"

    if bucket != "finished":
        return bucket, None, False

    try:
        request_class = request.get("request_class")
        if request_class not in ("short", "long"):
            raise AggregateError("finished request_class must be 'short' or 'long'")
        requested_output_tokens = _require_int(
            _require_key(request, "requested_output_tokens", "request"),
            "requested_output_tokens",
        )
        if requested_output_tokens <= 0:
            raise AggregateError("requested_output_tokens must be > 0")
        request_index = _require_int(
            _require_key(request, "request_index", "request"), "request_index"
        )
        if request_index < 0:
            raise AggregateError("request_index must be >= 0")
        record = request_to_timing_record(request)
        if record.seq_id < 0:
            raise AggregateError("seq_id must be >= 0")
        if record.prompt_tokens <= 0:
            raise AggregateError("prompt_tokens must be > 0")
        if record.output_tokens != requested_output_tokens:
            raise AggregateError(
                "finished output_tokens must equal requested_output_tokens"
            )
        metrics = derive_request_metrics(record)
    except (AggregateError, ValueError, TypeError, KeyError, OverflowError):
        return bucket, None, True

    return (
        bucket,
        {
            "queue_time_ms": metrics.queue_time_ms,
            "ttft_ms": metrics.ttft_ms,
            "e2e_ms": metrics.e2e_ms,
            "mean_tpot_ms": metrics.mean_tpot_ms,
        },
        False,
    )


def measurement_window_seconds(
    measurement: dict[str, Any], *, run_status: str
) -> float | None:
    if run_status != "finished":
        return None
    started = measurement.get("started_ns")
    ended = measurement.get("ended_ns")
    if started is None or ended is None:
        return None
    try:
        started_ns = _require_int(started, "measurement.started_ns")
        ended_ns = _require_int(ended, "measurement.ended_ns")
    except AggregateError:
        return None
    try:
        window = (ended_ns - started_ns) / 1_000_000_000
    except OverflowError:
        return None
    if window <= 0:
        return None
    return window


def build_latency_group(
    rows: list[tuple[str, dict[str, float | None]]],
) -> dict[str, Any]:
    metric_names = ("queue_time_ms", "ttft_ms", "e2e_ms", "mean_tpot_ms")
    result: dict[str, Any] = {}
    for name in metric_names:
        values: list[float] = []
        for _request_class, metrics in rows:
            value = metrics[name]
            if value is None:
                continue
            values.append(float(value))
        result[name] = summarize_values(values)
    return result


def aggregate_raw_paths(
    raw_paths: list[Path],
    *,
    created_at: datetime | None = None,
) -> dict[str, Any]:
    if not raw_paths:
        raise AggregateError("at least one raw JSON path is required")

    resolved: list[Path] = []
    seen_resolved: set[Path] = set()
    for path in raw_paths:
        try:
            resolved_path = path.expanduser().resolve()
        except (OSError, RuntimeError) as exc:
            raise AggregateError(f"cannot resolve raw file {path.name}: {exc}") from exc
        if resolved_path in seen_resolved:
            raise AggregateError(f"duplicate source file: {path.name}")
        seen_resolved.add(resolved_path)
        if not resolved_path.is_file():
            raise AggregateError(f"raw file not found: {path.name}")
        resolved.append(resolved_path)

    loaded: list[tuple[Path, dict[str, Any], str]] = []
    run_ids: set[str] = set()
    run_numbers: set[int] = set()
    compatibility: dict[str, Any] | None = None

    for path in resolved:
        document, digest = _load_raw_source(path)
        run_id = document["run_id"]
        run_number = document["run_number"]
        if not isinstance(run_id, str) or not run_id:
            raise AggregateError(f"{path.name}: run_id must be a non-empty string")
        if not isinstance(run_number, int) or isinstance(run_number, bool):
            raise AggregateError(f"{path.name}: run_number must be an int")
        if run_id in run_ids:
            raise AggregateError(f"duplicate run_id: {run_id}")
        if run_number in run_numbers:
            raise AggregateError(f"duplicate run_number: {run_number}")
        run_ids.add(run_id)
        run_numbers.add(run_number)

        compat = extract_compatibility(document)
        if compatibility is None:
            compatibility = compat
        elif compat != compatibility:
            raise AggregateError(
                f"incompatible raw mix involving {path.name}: "
                "commit/model/engine/workload/environment mismatch"
            )
        loaded.append((path, document, digest))

    assert compatibility is not None
    loaded.sort(key=lambda item: (item[1]["run_number"], item[1]["run_id"]))

    outcomes = {
        "finished": 0,
        "failed": 0,
        "cancelled": 0,
        "incomplete": 0,
        "other": 0,
    }
    valid_finished = 0
    invalid_records = 0
    unmapped_total = 0
    total_requests = 0

    latency_rows: dict[str, list[tuple[str, dict[str, float | None]]]] = {
        "all": [],
        "short": [],
        "long": [],
    }
    per_run: list[dict[str, Any]] = []
    sources: list[dict[str, Any]] = []

    for path, document, digest in loaded:
        requests = document["requests"]
        total_requests += len(requests)
        unmapped = document["unmapped_timing_records"]
        unmapped_total += len(unmapped)

        run_valid = 0
        run_output_tokens = 0
        seen_request_indexes: set[int] = set()
        seen_seq_ids: set[int] = set()
        for request in requests:
            if not isinstance(request, dict):
                raise AggregateError(f"{path.name}: each request must be an object")
            bucket, metrics, is_invalid = classify_request(request)
            outcomes[bucket] += 1
            if is_invalid:
                invalid_records += 1
                continue
            if metrics is None:
                continue
            request_index = request["request_index"]
            seq_id = request["seq_id"]
            if request_index in seen_request_indexes or seq_id in seen_seq_ids:
                invalid_records += 1
                continue
            seen_request_indexes.add(request_index)
            seen_seq_ids.add(seq_id)
            valid_finished += 1
            run_valid += 1
            output_tokens = _require_int(request["output_tokens"], "output_tokens")
            run_output_tokens += output_tokens
            request_class = request["request_class"]
            latency_rows["all"].append((request_class, metrics))
            latency_rows[request_class].append((request_class, metrics))

        window = measurement_window_seconds(
            document["measurement"], run_status=document["status"]
        )
        if window is None:
            request_tp = None
            output_tp = None
        else:
            request_tp = run_valid / window
            output_tp = run_output_tokens / window

        per_run.append(
            {
                "run_number": document["run_number"],
                "run_id": document["run_id"],
                "status": document["status"],
                "valid_finished": run_valid,
                "valid_finished_output_tokens": run_output_tokens,
                "window_seconds": window,
                "request_throughput": request_tp,
                "output_token_throughput": output_tp,
            }
        )
        sources.append(
            {
                "basename": path.name,
                "sha256": digest,
                "run_id": document["run_id"],
                "run_number": document["run_number"],
            }
        )

    created = created_at or datetime.now(timezone.utc)
    return {
        "schema_version": SCHEMA_VERSION,
        "aggregator": AGGREGATOR_ID,
        "experiment": EXPERIMENT_ID,
        "created_at_utc": created.isoformat(),
        "sources": sources,
        "compatibility": compatibility,
        "counts": {
            "total_requests": total_requests,
            "outcomes": outcomes,
            "valid_finished": valid_finished,
            "invalid_records": invalid_records,
            "unmapped_timing_records": unmapped_total,
        },
        "latency_ms": {
            "all": build_latency_group(latency_rows["all"]),
            "short": build_latency_group(latency_rows["short"]),
            "long": build_latency_group(latency_rows["long"]),
        },
        "throughput": {
            "per_run": per_run,
            "across_runs": {
                "request_throughput": summarize_values(
                    [
                        float(row["request_throughput"])
                        for row in per_run
                        if row["request_throughput"] is not None
                    ]
                ),
                "output_token_throughput": summarize_values(
                    [
                        float(row["output_token_throughput"])
                        for row in per_run
                        if row["output_token_throughput"] is not None
                    ]
                ),
            },
        },
    }


def write_aggregate_document(document: dict[str, Any], output_path: Path) -> Path:
    output_path = output_path.expanduser()
    try:
        payload = (
            json.dumps(
                document,
                indent=2,
                sort_keys=True,
                ensure_ascii=False,
                allow_nan=False,
            )
            + "\n"
        )
    except (TypeError, ValueError) as exc:
        raise AggregateError(f"aggregate document is not valid JSON: {exc}") from exc
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("x", encoding="utf-8") as handle:
            handle.write(payload)
    except FileExistsError as exc:
        raise AggregateError(
            f"refusing to overwrite existing output: {output_path.name}"
        ) from exc
    except OSError as exc:
        raise AggregateError(
            f"cannot write aggregate output {output_path.name}: {exc}"
        ) from exc
    return output_path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Offline NSL-S2-AGG-v1 aggregation over explicit NSL-S2-SAT-v1 "
            "schema v1 raw JSON paths. Does not scan directories or modify raw."
        )
    )
    parser.add_argument(
        "--raw",
        action="append",
        dest="raw_paths",
        required=True,
        type=Path,
        help="Path to one schema v1 raw JSON (repeat for each run)",
    )
    parser.add_argument(
        "--output",
        required=True,
        type=Path,
        help="Destination aggregate JSON path (must not already exist)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        document = aggregate_raw_paths(list(args.raw_paths))
        write_aggregate_document(document, args.output)
    except AggregateError as exc:
        print(f"aggregation failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
