"""Offline FCFS versus prompt-length aggregation for NSL-S3-SCHED-v1.

This module reads exactly six explicit Stage 3 schema v2 raw artifacts. It
reuses the Stage 2 request-metric derivation and statistical helpers while
adding strict policy/run-matrix validation, per-policy summaries, direct
candidate-minus-FCFS deltas, worst-request evidence, and predeclared warnings.

Import and CLI help remain Mac-safe and do not load torch.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from research.stage2_aggregate import (
    AggregateError,
    _reject_json_constant,
    _require_int,
    _require_non_empty_string,
    _require_object,
    _validate_finite_json,
    build_latency_group,
    classify_request,
    extract_compatibility,
    measurement_window_seconds,
    summarize_values,
    write_aggregate_document,
)
from research.stage2_workload import (
    EXPECTED_MANIFEST_SHA256,
    REQUEST_COUNT,
    WORKLOAD_ID,
    build_saturated_mixed_workload,
)
from research.stage3_scheduling_driver import (
    EXPERIMENT_CONTRACT,
    FCFS_POLICY,
    POLICY_DEFINITION_VERSION,
    PROMPT_LENGTH_POLICY,
    SCHEMA_VERSION as RAW_SCHEMA_VERSION,
    policy_metadata,
    validate_comparison_group,
)

AGGREGATE_SCHEMA_VERSION = 1
AGGREGATOR_ID = "NSL-S3-AGG-v1"
CANDIDATE_POLICY = PROMPT_LENGTH_POLICY
EXPECTED_RAW_COUNT = 6
RUN_NUMBERS = frozenset({1, 2, 3})
EXECUTION_ORDER = (
    (FCFS_POLICY, 1),
    (CANDIDATE_POLICY, 1),
    (CANDIDATE_POLICY, 2),
    (FCFS_POLICY, 2),
    (FCFS_POLICY, 3),
    (CANDIDATE_POLICY, 3),
)

_KNOWN_OUTCOMES = ("finished", "failed", "cancelled", "incomplete", "other")
_LATENCY_METRICS = ("queue_time_ms", "ttft_ms", "mean_tpot_ms", "e2e_ms")
_DELTA_STATS = ("mean", "median", "min", "max", "sample_std", "p50", "p95", "p99")
_EXPECTED_REQUESTS = {
    request.request_index: request for request in build_saturated_mixed_workload()
}
_EXPECTED_OUTPUT_TOKENS = sum(
    request.max_tokens for request in _EXPECTED_REQUESTS.values()
)


class Stage3AggregateError(AggregateError):
    """Invalid Stage 3 raw set or comparison contract."""


def _strict_int(value: Any, label: str) -> int:
    try:
        return _require_int(value, label)
    except AggregateError as exc:
        raise Stage3AggregateError(str(exc)) from exc


def _strict_string(value: Any, label: str) -> str:
    try:
        return _require_non_empty_string(value, label)
    except AggregateError as exc:
        raise Stage3AggregateError(str(exc)) from exc


def _strict_object(value: Any, label: str) -> dict[str, Any]:
    try:
        return _require_object(value, label)
    except AggregateError as exc:
        raise Stage3AggregateError(str(exc)) from exc


def _created_at(value: Any, label: str) -> datetime:
    timestamp = _strict_string(value, label)
    try:
        parsed = datetime.fromisoformat(timestamp)
    except ValueError as exc:
        raise Stage3AggregateError(f"{label} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise Stage3AggregateError(f"{label} must include a UTC offset")
    return parsed


def _validate_policy_identity(payload: dict[str, Any], path: Path) -> str:
    policy = _strict_object(payload.get("policy"), f"{path.name}: policy")
    policy_id = _strict_string(policy.get("id"), f"{path.name}: policy.id")
    if policy_id not in (FCFS_POLICY, CANDIDATE_POLICY):
        raise Stage3AggregateError(
            f"{path.name}: unsupported comparison policy {policy_id!r}"
        )
    definition_version = _strict_int(
        policy.get("definition_version"),
        f"{path.name}: policy.definition_version",
    )
    if definition_version != POLICY_DEFINITION_VERSION:
        raise Stage3AggregateError(
            f"{path.name}: policy.definition_version must be "
            f"{POLICY_DEFINITION_VERSION}"
        )
    expected = policy_metadata(policy_id, runtime_verified=True)
    if policy.get("parameters") != expected["parameters"]:
        raise Stage3AggregateError(
            f"{path.name}: policy.parameters do not match {policy_id} definition"
        )
    if not isinstance(policy.get("runtime_verified"), bool):
        raise Stage3AggregateError(
            f"{path.name}: policy.runtime_verified must be a boolean"
        )

    engine = _strict_object(payload.get("engine"), f"{path.name}: engine")
    if engine.get("requested_scheduling_policy") != policy_id:
        raise Stage3AggregateError(
            f"{path.name}: engine.requested_scheduling_policy must match policy.id"
        )
    actual = engine.get("scheduling_policy")
    if actual is not None and actual not in (FCFS_POLICY, CANDIDATE_POLICY):
        raise Stage3AggregateError(
            f"{path.name}: engine.scheduling_policy is invalid: {actual!r}"
        )
    if payload.get("status") == "finished":
        if policy["runtime_verified"] is not True or actual != policy_id:
            raise Stage3AggregateError(
                f"{path.name}: finished raw requires verified requested/actual "
                "Scheduler policy identity"
            )
    return policy_id


def _load_stage3_raw(path: Path) -> tuple[dict[str, Any], str, str]:
    try:
        raw_bytes = path.read_bytes()
    except OSError as exc:
        raise Stage3AggregateError(f"cannot read raw file {path.name}: {exc}") from exc
    try:
        text = raw_bytes.decode("utf-8")
    except UnicodeError as exc:
        raise Stage3AggregateError(
            f"cannot decode raw file {path.name}: {exc}"
        ) from exc
    try:
        payload = json.loads(text, parse_constant=_reject_json_constant)
    except (json.JSONDecodeError, AggregateError) as exc:
        raise Stage3AggregateError(
            f"malformed JSON in {path.name}: {exc}"
        ) from exc
    try:
        _validate_finite_json(payload)
    except AggregateError as exc:
        raise Stage3AggregateError(f"{path.name}: {exc}") from exc
    if not isinstance(payload, dict):
        raise Stage3AggregateError(f"{path.name}: top-level JSON must be an object")
    schema_version = payload.get("schema_version")
    if (
        not isinstance(schema_version, int)
        or isinstance(schema_version, bool)
        or schema_version != RAW_SCHEMA_VERSION
    ):
        raise Stage3AggregateError(
            f"{path.name}: schema_version must be {RAW_SCHEMA_VERSION}, "
            f"got {schema_version!r}"
        )
    for key in (
        "experiment",
        "experiment_contract",
        "comparison_group",
        "run_id",
        "run_number",
        "status",
        "error",
        "repository",
        "environment",
        "model",
        "engine",
        "workload",
        "warmup",
        "measurement",
        "requests",
        "unmapped_timing_records",
        "policy",
    ):
        if key not in payload:
            raise Stage3AggregateError(
                f"{path.name}: missing required field {key!r}"
            )
    if payload["experiment"] != EXPERIMENT_CONTRACT:
        raise Stage3AggregateError(
            f"{path.name}: experiment must be {EXPERIMENT_CONTRACT!r}"
        )
    if payload["experiment_contract"] != EXPERIMENT_CONTRACT:
        raise Stage3AggregateError(
            f"{path.name}: experiment_contract must be {EXPERIMENT_CONTRACT!r}"
        )
    try:
        comparison_group = validate_comparison_group(payload["comparison_group"])
    except ValueError as exc:
        raise Stage3AggregateError(f"{path.name}: {exc}") from exc
    repository = _strict_object(
        payload.get("repository"),
        f"{path.name}: repository",
    )
    if repository.get("dirty") is not False:
        raise Stage3AggregateError(
            f"{path.name}: repository.dirty must be false"
        )
    if payload["status"] not in ("finished", "failed"):
        raise Stage3AggregateError(
            f"{path.name}: status must be 'finished' or 'failed'"
        )
    for key in ("requests", "unmapped_timing_records"):
        if not isinstance(payload[key], list):
            raise Stage3AggregateError(f"{path.name}: {key} must be a list")
    for key in ("measurement", "workload", "model", "engine", "environment", "warmup"):
        if not isinstance(payload[key], dict):
            raise Stage3AggregateError(f"{path.name}: {key} must be an object")
    workload = payload["workload"]
    if workload.get("id") != WORKLOAD_ID:
        raise Stage3AggregateError(
            f"{path.name}: workload.id must be {WORKLOAD_ID!r}"
        )
    policy_id = _validate_policy_identity(payload, path)
    return payload, hashlib.sha256(raw_bytes).hexdigest(), policy_id


def _extract_stage3_compatibility(raw: dict[str, Any]) -> dict[str, Any]:
    try:
        compatibility = extract_compatibility(raw)
    except AggregateError as exc:
        raise Stage3AggregateError(str(exc)) from exc
    if raw["workload"].get("id") != WORKLOAD_ID:
        raise Stage3AggregateError(
            f"workload.id does not match frozen {WORKLOAD_ID} contract"
        )
    if raw["workload"].get("manifest_sha256") != EXPECTED_MANIFEST_SHA256:
        raise Stage3AggregateError(
            "workload manifest does not match frozen Stage 3 contract"
        )
    fixed_engine = dict(compatibility["engine"])
    if "requested_scheduling_policy" not in fixed_engine:
        raise Stage3AggregateError(
            "engine missing requested_scheduling_policy"
        )
    if "scheduling_policy" not in fixed_engine:
        raise Stage3AggregateError("engine missing scheduling_policy")
    fixed_engine.pop("requested_scheduling_policy")
    fixed_engine.pop("scheduling_policy")
    compatibility["engine"] = fixed_engine
    compatibility["workload"] = {
        "id": WORKLOAD_ID,
        **compatibility["workload"],
    }
    return compatibility


def _empty_outcomes() -> dict[str, int]:
    return {name: 0 for name in _KNOWN_OUTCOMES}


def _request_shape_is_frozen(request: dict[str, Any]) -> bool:
    try:
        request_index = _strict_int(request.get("request_index"), "request_index")
        prompt_tokens = _strict_int(request.get("prompt_tokens"), "prompt_tokens")
        requested_output_tokens = _strict_int(
            request.get("requested_output_tokens"),
            "requested_output_tokens",
        )
    except Stage3AggregateError:
        return False
    expected = _EXPECTED_REQUESTS.get(request_index)
    return bool(
        expected is not None
        and request.get("request_class") == expected.request_class
        and prompt_tokens == len(expected.prompt_token_ids)
        and requested_output_tokens == expected.max_tokens
    )


def _worst_entry(
    current: dict[str, Any] | None,
    *,
    value_ms: float,
    request: dict[str, Any],
    run_number: int,
    run_id: str,
) -> dict[str, Any]:
    candidate = {
        "value_ms": value_ms,
        "request_class": request["request_class"],
        "request_index": request["request_index"],
        "run_number": run_number,
        "run_id": run_id,
    }
    if current is None or value_ms > current["value_ms"]:
        return candidate
    return current


def _aggregate_policy(
    loaded: list[tuple[Path, dict[str, Any], str, str]],
    *,
    policy_id: str,
) -> dict[str, Any]:
    outcomes = _empty_outcomes()
    class_counts = {
        name: {
            "total_requests": 0,
            "outcomes": _empty_outcomes(),
            "invalid_records": 0,
            "valid_finished": 0,
        }
        for name in ("short", "long", "other")
    }
    latency_rows: dict[str, list[tuple[str, dict[str, float | None]]]] = {
        "all": [],
        "short": [],
        "long": [],
    }
    worst_requests: dict[str, dict[str, Any] | None] = {
        "queue_time_ms": None,
        "ttft_ms": None,
        "e2e_ms": None,
    }
    total_requests = 0
    valid_finished = 0
    invalid_records = 0
    unmapped_total = 0
    sources: list[dict[str, Any]] = []
    per_run: list[dict[str, Any]] = []
    invalid_reasons: list[str] = []

    for path, document, digest, _loaded_policy in sorted(
        loaded,
        key=lambda item: (item[1]["run_number"], item[1]["run_id"]),
    ):
        requests = document["requests"]
        unmapped = document["unmapped_timing_records"]
        total_requests += len(requests)
        unmapped_total += len(unmapped)
        run_number = document["run_number"]
        run_id = document["run_id"]
        run_outcomes = _empty_outcomes()
        run_valid = 0
        run_invalid = 0
        run_output_tokens = 0
        valid_indexes: set[int] = set()
        seen_request_indexes: set[int] = set()
        seen_seq_ids: set[int] = set()

        for request in requests:
            if not isinstance(request, dict):
                raise Stage3AggregateError(
                    f"{path.name}: each request must be an object"
                )
            bucket, metrics, classifier_invalid = classify_request(request)
            outcomes[bucket] += 1
            run_outcomes[bucket] += 1
            raw_class = request.get("request_class")
            class_key = raw_class if raw_class in ("short", "long") else "other"
            class_counts[class_key]["total_requests"] += 1
            class_counts[class_key]["outcomes"][bucket] += 1

            shape_invalid = bucket == "finished" and not _request_shape_is_frozen(
                request
            )
            if classifier_invalid or shape_invalid:
                invalid_records += 1
                run_invalid += 1
                class_counts[class_key]["invalid_records"] += 1
                continue
            if metrics is None:
                continue

            request_index = request["request_index"]
            seq_id = request["seq_id"]
            if request_index in seen_request_indexes or seq_id in seen_seq_ids:
                invalid_records += 1
                run_invalid += 1
                class_counts[class_key]["invalid_records"] += 1
                continue
            seen_request_indexes.add(request_index)
            seen_seq_ids.add(seq_id)
            valid_indexes.add(request_index)
            valid_finished += 1
            run_valid += 1
            class_counts[class_key]["valid_finished"] += 1
            output_tokens = _strict_int(request["output_tokens"], "output_tokens")
            run_output_tokens += output_tokens
            latency_rows["all"].append((class_key, metrics))
            latency_rows[class_key].append((class_key, metrics))
            for metric_name in worst_requests:
                value = metrics[metric_name]
                if value is None:
                    continue
                worst_requests[metric_name] = _worst_entry(
                    worst_requests[metric_name],
                    value_ms=float(value),
                    request=request,
                    run_number=run_number,
                    run_id=run_id,
                )

        window = measurement_window_seconds(
            document["measurement"],
            run_status=document["status"],
        )
        run_reasons: list[str] = []
        if document["status"] != "finished":
            run_reasons.append(f"status={document['status']}")
        if document["error"] is not None:
            run_reasons.append("error is not null")
        if document["policy"]["runtime_verified"] is not True:
            run_reasons.append("policy.runtime_verified is not true")
        if document["engine"]["scheduling_policy"] != policy_id:
            run_reasons.append("actual Scheduler policy does not match")
        if len(requests) != REQUEST_COUNT:
            run_reasons.append(
                f"request_count={len(requests)}, expected={REQUEST_COUNT}"
            )
        if run_outcomes != {
            "finished": REQUEST_COUNT,
            "failed": 0,
            "cancelled": 0,
            "incomplete": 0,
            "other": 0,
        }:
            run_reasons.append(f"outcomes={run_outcomes}")
        if run_invalid:
            run_reasons.append(f"invalid_records={run_invalid}")
        if valid_indexes != set(_EXPECTED_REQUESTS):
            run_reasons.append("valid request_index set is incomplete")
        if len(unmapped):
            run_reasons.append(f"unmapped_timing_records={len(unmapped)}")
        if run_output_tokens != _EXPECTED_OUTPUT_TOKENS:
            run_reasons.append(
                f"output_tokens={run_output_tokens}, "
                f"expected={_EXPECTED_OUTPUT_TOKENS}"
            )
        if document["measurement"].get("cuda_synchronized") is not True:
            run_reasons.append("measurement.cuda_synchronized is not true")
        if window is None:
            run_reasons.append("measurement window is invalid")

        run_contract_valid = not run_reasons
        if run_contract_valid:
            request_throughput = run_valid / window
            output_token_throughput = run_output_tokens / window
        else:
            request_throughput = None
            output_token_throughput = None
            invalid_reasons.extend(
                f"{policy_id}/run{run_number}: {reason}" for reason in run_reasons
            )

        per_run.append(
            {
                "run_number": run_number,
                "run_id": run_id,
                "status": document["status"],
                "contract_valid": run_contract_valid,
                "invalid_reasons": run_reasons,
                "valid_finished": run_valid,
                "valid_finished_output_tokens": run_output_tokens,
                "window_seconds": window if run_contract_valid else None,
                "request_throughput": request_throughput,
                "output_token_throughput": output_token_throughput,
            }
        )
        sources.append(
            {
                "basename": path.name,
                "sha256": digest,
                "policy": policy_id,
                "run_id": run_id,
                "run_number": run_number,
            }
        )

    aggregate_policy_metadata = policy_metadata(
        policy_id,
        runtime_verified=True,
    )
    aggregate_policy_metadata["runtime_verification_scope"] = "all_sources"
    return {
        "policy": aggregate_policy_metadata,
        "sources": sources,
        "validity": {
            "valid": not invalid_reasons,
            "invalid_reasons": invalid_reasons,
        },
        "counts": {
            "total_requests": total_requests,
            "outcomes": outcomes,
            "valid_finished": valid_finished,
            "invalid_records": invalid_records,
            "unmapped_timing_records": unmapped_total,
            "by_request_class": class_counts,
        },
        "latency_ms": {
            group: build_latency_group(rows)
            for group, rows in latency_rows.items()
        },
        "worst_requests": worst_requests,
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


def _delta(fcfs: Any, candidate: Any) -> dict[str, Any]:
    if fcfs is None or candidate is None:
        return {
            "fcfs": fcfs,
            "candidate": candidate,
            "absolute": None,
            "relative_percent": None,
        }
    absolute = float(candidate) - float(fcfs)
    relative = None if float(fcfs) == 0.0 else absolute / float(fcfs) * 100.0
    return {
        "fcfs": fcfs,
        "candidate": candidate,
        "absolute": absolute,
        "relative_percent": relative,
    }


def _summary_deltas(
    fcfs_summary: dict[str, Any],
    candidate_summary: dict[str, Any],
) -> dict[str, Any]:
    return {
        statistic: _delta(
            fcfs_summary.get(statistic),
            candidate_summary.get(statistic),
        )
        for statistic in _DELTA_STATS
    }


def _comparison(
    fcfs: dict[str, Any],
    candidate: dict[str, Any],
) -> dict[str, Any]:
    throughput_deltas = {
        metric: _summary_deltas(
            fcfs["throughput"]["across_runs"][metric],
            candidate["throughput"]["across_runs"][metric],
        )
        for metric in ("request_throughput", "output_token_throughput")
    }
    latency_deltas = {
        group: {
            metric: _summary_deltas(
                fcfs["latency_ms"][group][metric],
                candidate["latency_ms"][group][metric],
            )
            for metric in _LATENCY_METRICS
        }
        for group in ("all", "short", "long")
    }
    count_deltas = {
        key: int(candidate["counts"][key]) - int(fcfs["counts"][key])
        for key in (
            "total_requests",
            "valid_finished",
            "invalid_records",
            "unmapped_timing_records",
        )
    }
    count_deltas["outcomes"] = {
        outcome: (
            candidate["counts"]["outcomes"][outcome]
            - fcfs["counts"]["outcomes"][outcome]
        )
        for outcome in _KNOWN_OUTCOMES
    }

    output_mean_delta = throughput_deltas["output_token_throughput"]["mean"]
    throughput_warning = bool(
        output_mean_delta["relative_percent"] is not None
        and output_mean_delta["relative_percent"] < -5.0
    )
    fairness_items: list[dict[str, Any]] = []
    for request_class in ("short", "long", "other"):
        class_counts = candidate["counts"]["by_request_class"][request_class]
        incomplete = sum(
            class_counts["outcomes"][outcome]
            for outcome in ("failed", "cancelled", "incomplete", "other")
        )
        if incomplete or class_counts["invalid_records"]:
            fairness_items.append(
                {
                    "kind": "request_completion",
                    "request_class": request_class,
                    "non_finished": incomplete,
                    "invalid_records": class_counts["invalid_records"],
                }
            )
        if request_class == "other":
            continue
        for metric in ("ttft_ms", "e2e_ms"):
            for statistic in ("p95", "p99", "max"):
                delta = latency_deltas[request_class][metric][statistic]
                if delta["absolute"] is not None and delta["absolute"] > 0.0:
                    fairness_items.append(
                        {
                            "kind": "latency_increase",
                            "request_class": request_class,
                            "metric": metric,
                            "statistic": statistic,
                            **delta,
                        }
                    )

    invalid_reasons = (
        list(fcfs["validity"]["invalid_reasons"])
        + list(candidate["validity"]["invalid_reasons"])
    )
    return {
        "baseline_policy": FCFS_POLICY,
        "candidate_policy": CANDIDATE_POLICY,
        "valid": not invalid_reasons,
        "invalid_reasons": invalid_reasons,
        "direction": {
            "formula": "(candidate - fcfs) / fcfs * 100",
            "throughput": "positive_is_better",
            "latency": "negative_is_better",
        },
        "count_deltas": count_deltas,
        "throughput_deltas": throughput_deltas,
        "latency_ms_deltas": latency_deltas,
        "warnings": {
            "throughput_degradation_over_5_percent": throughput_warning,
            "fairness_risk": bool(fairness_items),
            "fairness_items": fairness_items,
        },
    }


def aggregate_stage3_raw_paths(
    raw_paths: list[Path],
    *,
    created_at: datetime | None = None,
) -> dict[str, Any]:
    if len(raw_paths) != EXPECTED_RAW_COUNT:
        raise Stage3AggregateError(
            f"exactly {EXPECTED_RAW_COUNT} raw paths are required, "
            f"got {len(raw_paths)}"
        )
    resolved: list[Path] = []
    seen_paths: set[Path] = set()
    for path in raw_paths:
        try:
            resolved_path = path.expanduser().resolve()
        except (OSError, RuntimeError) as exc:
            raise Stage3AggregateError(
                f"cannot resolve raw file {path.name}: {exc}"
            ) from exc
        if resolved_path in seen_paths:
            raise Stage3AggregateError(f"duplicate source file: {path.name}")
        if not resolved_path.is_file():
            raise Stage3AggregateError(f"raw file not found: {path.name}")
        seen_paths.add(resolved_path)
        resolved.append(resolved_path)

    loaded: list[tuple[Path, dict[str, Any], str, str]] = []
    run_ids: set[str] = set()
    run_keys: set[tuple[str, int]] = set()
    comparison_group: str | None = None
    compatibility: dict[str, Any] | None = None
    for path in resolved:
        document, digest, policy_id = _load_stage3_raw(path)
        run_id = _strict_string(document["run_id"], f"{path.name}: run_id")
        run_number = _strict_int(document["run_number"], f"{path.name}: run_number")
        if run_number not in RUN_NUMBERS:
            raise Stage3AggregateError(
                f"{path.name}: run_number must be one of {sorted(RUN_NUMBERS)}"
            )
        if run_id in run_ids:
            raise Stage3AggregateError(f"duplicate run_id: {run_id}")
        run_key = (policy_id, run_number)
        if run_key in run_keys:
            raise Stage3AggregateError(
                f"duplicate policy/run_number: {policy_id}/run{run_number}"
            )
        run_ids.add(run_id)
        run_keys.add(run_key)

        group = document["comparison_group"]
        if comparison_group is None:
            comparison_group = group
        elif group != comparison_group:
            raise Stage3AggregateError(
                f"incompatible comparison_group involving {path.name}"
            )
        current_compatibility = _extract_stage3_compatibility(document)
        if compatibility is None:
            compatibility = current_compatibility
        elif current_compatibility != compatibility:
            raise Stage3AggregateError(
                f"incompatible raw mix involving {path.name}: "
                "commit/model/fixed-engine/workload/environment mismatch"
            )
        loaded.append((path, document, digest, policy_id))

    expected_keys = set(EXECUTION_ORDER)
    if run_keys != expected_keys:
        missing = sorted(expected_keys - run_keys)
        extra = sorted(run_keys - expected_keys)
        raise Stage3AggregateError(
            f"policy/run matrix mismatch: missing={missing}, extra={extra}"
        )
    assert comparison_group is not None
    assert compatibility is not None

    by_key = {
        (policy_id, document["run_number"]): (path, document, digest, policy_id)
        for path, document, digest, policy_id in loaded
    }
    canonical_loaded = [by_key[key] for key in EXECUTION_ORDER]
    canonical_created_at = [
        _created_at(
            item[1]["created_at_utc"],
            f"{item[0].name}: created_at_utc",
        )
        for item in canonical_loaded
    ]
    for previous, current in zip(
        canonical_created_at,
        canonical_created_at[1:],
    ):
        if current <= previous:
            raise Stage3AggregateError(
                "raw created_at_utc values do not prove the fixed execution order"
            )
    policy_results = {
        policy_id: _aggregate_policy(
            [
                item
                for item in canonical_loaded
                if item[3] == policy_id
            ],
            policy_id=policy_id,
        )
        for policy_id in (FCFS_POLICY, CANDIDATE_POLICY)
    }
    comparison = _comparison(
        policy_results[FCFS_POLICY],
        policy_results[CANDIDATE_POLICY],
    )
    created = created_at or datetime.now(timezone.utc)
    return {
        "schema_version": AGGREGATE_SCHEMA_VERSION,
        "aggregator": AGGREGATOR_ID,
        "experiment_contract": EXPERIMENT_CONTRACT,
        "created_at_utc": created.isoformat(),
        "comparison_group": comparison_group,
        "execution_order": [
            {"position": position, "policy": policy, "run_number": run_number}
            for position, (policy, run_number) in enumerate(EXECUTION_ORDER, start=1)
        ],
        "sources": [
            {
                "basename": path.name,
                "sha256": digest,
                "policy": policy_id,
                "run_id": document["run_id"],
                "run_number": document["run_number"],
            }
            for path, document, digest, policy_id in canonical_loaded
        ],
        "compatibility": compatibility,
        "policies": policy_results,
        "comparison": comparison,
    }


def write_stage3_aggregate_document(
    document: dict[str, Any],
    output_path: Path,
) -> Path:
    if document.get("schema_version") != AGGREGATE_SCHEMA_VERSION:
        raise Stage3AggregateError(
            f"aggregate schema_version must be {AGGREGATE_SCHEMA_VERSION}"
        )
    if document.get("aggregator") != AGGREGATOR_ID:
        raise Stage3AggregateError(
            f"aggregator must be {AGGREGATOR_ID!r}"
        )
    if document.get("experiment_contract") != EXPERIMENT_CONTRACT:
        raise Stage3AggregateError(
            f"experiment_contract must be {EXPERIMENT_CONTRACT!r}"
        )
    try:
        validate_comparison_group(document.get("comparison_group"))
    except ValueError as exc:
        raise Stage3AggregateError(str(exc)) from exc
    policies = document.get("policies")
    if not isinstance(policies, dict) or set(policies) != {
        FCFS_POLICY,
        CANDIDATE_POLICY,
    }:
        raise Stage3AggregateError(
            "aggregate policies must contain exactly FCFS and prompt-length"
        )
    try:
        return write_aggregate_document(document, output_path)
    except AggregateError as exc:
        raise Stage3AggregateError(str(exc)) from exc


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Offline NSL-S3-AGG-v1 FCFS versus prompt-length comparison over "
            "exactly six explicit Stage 3 schema v2 raw JSON paths."
        )
    )
    parser.add_argument(
        "--raw",
        action="append",
        dest="raw_paths",
        required=True,
        type=Path,
        help="Path to one schema v2 raw JSON (repeat exactly six times)",
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
        document = aggregate_stage3_raw_paths(list(args.raw_paths))
        write_stage3_aggregate_document(document, args.output)
    except AggregateError as exc:
        print(f"Stage 3 aggregation failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
