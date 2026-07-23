"""Deterministic CPU tests for offline NSL-S2-SAT-v1 aggregation."""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import math
import subprocess
import sys
import tempfile
import textwrap
import unittest
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from research.stage2_aggregate import (
    AggregateError,
    aggregate_raw_paths,
    main,
    nearest_rank,
    parse_args,
    summarize_values,
    write_aggregate_document,
)

_COMPAT_ENV = {
    "python": "3.12.3 (fixture)",
    "packages": {
        "torch": "2.4.0+cu124",
        "triton": "3.0.0",
        "transformers": "5.5.0",
        "flash-attn": "2.7.4.post1",
        "xxhash": "3.8.1",
    },
    "torch_cuda_build": "12.4",
    "cuda_available": True,
    "cuda_device": "NVIDIA GeForce RTX 4060 Laptop GPU",
    "platform": "Linux-fixture",
}

_COMPAT_ENGINE = {
    "enforce_eager": False,
    "max_model_len": 4096,
    "max_num_seqs": 512,
    "max_num_batched_tokens": 16384,
    "gpu_memory_utilization": 0.9,
    "tensor_parallel_size": 1,
    "kvcache_block_size": 256,
}

_COMPAT_WORKLOAD = {
    "arrival_model": "saturated_batch",
    "seed": 0,
    "sampling_seed": 0,
    "request_count": 64,
    "manifest_sha256": "aa1d4e345e0e9f599bd43093bd5b9214476aa3145ee910cc9137d0b62754767d",
}


def _finished_request(
    *,
    request_index: int,
    seq_id: int,
    request_class: str,
    prompt_tokens: int,
    output_tokens: int,
    arrival: int,
    first_scheduled: int,
    first_output: int,
    completed: int,
) -> dict:
    return {
        "request_index": request_index,
        "seq_id": seq_id,
        "request_class": request_class,
        "prompt_tokens": prompt_tokens,
        "requested_output_tokens": output_tokens,
        "output_tokens": output_tokens,
        "outcome": "finished",
        "timestamps_ns": {
            "arrival": arrival,
            "first_scheduled": first_scheduled,
            "first_output": first_output,
            "completed": completed,
        },
        "error": None,
    }


def _base_raw(
    *,
    run_id: str,
    run_number: int,
    requests: list[dict],
    started_ns: int,
    ended_ns: int | None,
    branch: str = "fixture-branch",
    commit: str = "commit-aaa",
    unmapped: list | None = None,
) -> dict:
    return {
        "schema_version": 1,
        "experiment": "NSL-S2-SAT-v1",
        "run_id": run_id,
        "run_number": run_number,
        "created_at_utc": f"2026-07-23T13:0{run_number}:00+00:00",
        "status": "finished" if ended_ns is not None else "failed",
        "error": None,
        "repository": {
            "commit": commit,
            "branch": branch,
            "dirty": False,
        },
        "environment": deepcopy(_COMPAT_ENV),
        "model": {
            "id": "Qwen/Qwen3-0.6B",
            "revision": "c1899de289a04d12100db370d81485cdf75e47ca",
            "local_path": f"/tmp/fixture-run{run_number}/model",
        },
        "engine": deepcopy(_COMPAT_ENGINE),
        "workload": deepcopy(_COMPAT_WORKLOAD),
        "warmup": {"measured": False, "timing_records": []},
        "measurement": {
            "clock": "time.perf_counter_ns",
            "started_ns": started_ns,
            "ended_ns": ended_ns,
            "cuda_synchronized": True,
        },
        "requests": requests,
        "unmapped_timing_records": list(unmapped or []),
    }


def _three_compatible_raws() -> list[dict]:
    # Run 1: 2 short + 1 long, all multi-token finished.
    run1_requests = [
        _finished_request(
            request_index=0,
            seq_id=10,
            request_class="short",
            prompt_tokens=128,
            output_tokens=2,
            arrival=1_000_000_000,
            first_scheduled=1_100_000_000,
            first_output=1_300_000_000,
            completed=1_500_000_000,
        ),
        _finished_request(
            request_index=1,
            seq_id=11,
            request_class="long",
            prompt_tokens=1024,
            output_tokens=3,
            arrival=1_010_000_000,
            first_scheduled=1_200_000_000,
            first_output=1_400_000_000,
            completed=1_800_000_000,
        ),
        _finished_request(
            request_index=2,
            seq_id=12,
            request_class="short",
            prompt_tokens=128,
            output_tokens=2,
            arrival=1_020_000_000,
            first_scheduled=1_220_000_000,
            first_output=1_420_000_000,
            completed=1_620_000_000,
        ),
    ]
    # Run 2: one single-token short (TPOT null) + one long.
    run2_requests = [
        _finished_request(
            request_index=0,
            seq_id=20,
            request_class="short",
            prompt_tokens=128,
            output_tokens=1,
            arrival=2_000_000_000,
            first_scheduled=2_050_000_000,
            first_output=2_100_000_000,
            completed=2_100_000_000,
        ),
        _finished_request(
            request_index=1,
            seq_id=21,
            request_class="long",
            prompt_tokens=1024,
            output_tokens=2,
            arrival=2_010_000_000,
            first_scheduled=2_100_000_000,
            first_output=2_300_000_000,
            completed=2_500_000_000,
        ),
    ]
    # Run 3: one valid short + one invalid finished (bad order) + one failed.
    run3_requests = [
        _finished_request(
            request_index=0,
            seq_id=30,
            request_class="short",
            prompt_tokens=128,
            output_tokens=2,
            arrival=3_000_000_000,
            first_scheduled=3_100_000_000,
            first_output=3_200_000_000,
            completed=3_400_000_000,
        ),
        {
            "request_index": 1,
            "seq_id": 31,
            "request_class": "long",
            "prompt_tokens": 1024,
            "requested_output_tokens": 2,
            "output_tokens": 2,
            "outcome": "finished",
            "timestamps_ns": {
                "arrival": 3_010_000_000,
                "first_scheduled": 3_400_000_000,
                "first_output": 3_200_000_000,
                "completed": 3_500_000_000,
            },
            "error": None,
        },
        {
            "request_index": 2,
            "seq_id": 32,
            "request_class": "short",
            "prompt_tokens": 128,
            "requested_output_tokens": 2,
            "output_tokens": 0,
            "outcome": "failed",
            "timestamps_ns": {
                "arrival": 3_020_000_000,
                "first_scheduled": None,
                "first_output": None,
                "completed": None,
            },
            "error": {"type": "RuntimeError", "message": "injected"},
        },
    ]
    return [
        _base_raw(
            run_id="run-id-1",
            run_number=1,
            requests=run1_requests,
            started_ns=1_000_000_000,
            ended_ns=2_000_000_000,
            branch="branch-a",
            unmapped=[{"seq_id": 99}],
        ),
        _base_raw(
            run_id="run-id-2",
            run_number=2,
            requests=run2_requests,
            started_ns=2_000_000_000,
            ended_ns=2_500_000_000,
            branch="branch-b",
        ),
        _base_raw(
            run_id="run-id-3",
            run_number=3,
            requests=run3_requests,
            started_ns=3_000_000_000,
            ended_ns=4_000_000_000,
            branch="branch-c",
        ),
    ]


def _write_raws(directory: Path, documents: list[dict]) -> list[Path]:
    paths: list[Path] = []
    for document in documents:
        path = directory / f"fixture-run{document['run_number']}.json"
        path.write_text(
            json.dumps(document, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        paths.append(path)
    return paths


class NearestRankAndSummaryTest(unittest.TestCase):
    def test_nearest_rank_small_n(self):
        values = [10.0, 20.0, 30.0]
        self.assertEqual(nearest_rank(values, 0.50), 20.0)
        self.assertEqual(nearest_rank(values, 0.95), 30.0)
        self.assertEqual(nearest_rank(values, 0.99), 30.0)
        self.assertEqual(nearest_rank([7.0], 0.50), 7.0)
        self.assertEqual(nearest_rank([7.0], 0.99), 7.0)
        self.assertEqual(math.ceil(0.95 * 2), 2)
        self.assertEqual(nearest_rank([1.0, 2.0], 0.95), 2.0)

    def test_sample_std_null_when_n_is_one(self):
        summary = summarize_values([42.0])
        self.assertEqual(summary["n"], 1)
        self.assertEqual(summary["mean"], 42.0)
        self.assertIsNone(summary["sample_std"])
        self.assertEqual(summary["p50"], 42.0)
        self.assertEqual(summary["p99"], 42.0)

    def test_mean_median_min_max_sample_std(self):
        summary = summarize_values([1.0, 2.0, 3.0, 4.0])
        self.assertEqual(summary["n"], 4)
        self.assertEqual(summary["mean"], 2.5)
        self.assertEqual(summary["median"], 2.5)
        self.assertEqual(summary["min"], 1.0)
        self.assertEqual(summary["max"], 4.0)
        self.assertAlmostEqual(summary["sample_std"], 1.2909944487358056)


class Stage2AggregateTest(unittest.TestCase):
    def test_three_compatible_runs_deterministic_aggregation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = _write_raws(root, _three_compatible_raws())
            created = datetime(2026, 7, 23, tzinfo=timezone.utc)
            first = aggregate_raw_paths(paths, created_at=created)
            second = aggregate_raw_paths(paths, created_at=created)
            self.assertEqual(
                json.dumps(first, sort_keys=True),
                json.dumps(second, sort_keys=True),
            )
            self.assertEqual(first["schema_version"], 1)
            self.assertEqual(first["aggregator"], "NSL-S2-AGG-v1")
            self.assertEqual(first["experiment"], "NSL-S2-SAT-v1")
            self.assertEqual(len(first["sources"]), 3)
            self.assertEqual(
                [item["run_number"] for item in first["sources"]],
                [1, 2, 3],
            )
            for source, path in zip(first["sources"], paths, strict=True):
                self.assertEqual(source["basename"], path.name)
                self.assertNotIn("/", source["basename"])
                expected = hashlib.sha256(path.read_bytes()).hexdigest()
                self.assertEqual(source["sha256"], expected)

            counts = first["counts"]
            self.assertEqual(counts["total_requests"], 8)
            self.assertEqual(counts["outcomes"]["finished"], 7)
            self.assertEqual(counts["outcomes"]["failed"], 1)
            self.assertEqual(counts["outcomes"]["cancelled"], 0)
            self.assertEqual(counts["outcomes"]["incomplete"], 0)
            self.assertEqual(counts["outcomes"]["other"], 0)
            self.assertEqual(counts["valid_finished"], 6)
            self.assertEqual(counts["invalid_records"], 1)
            self.assertEqual(counts["unmapped_timing_records"], 1)

            # all/short/long grouping
            self.assertEqual(first["latency_ms"]["all"]["queue_time_ms"]["n"], 6)
            self.assertEqual(first["latency_ms"]["short"]["queue_time_ms"]["n"], 4)
            self.assertEqual(first["latency_ms"]["long"]["queue_time_ms"]["n"], 2)

            # TPOT null excluded from numeric set but reflected in n
            self.assertEqual(first["latency_ms"]["all"]["mean_tpot_ms"]["n"], 5)
            self.assertEqual(first["latency_ms"]["short"]["mean_tpot_ms"]["n"], 3)

            # per-run throughput uses only that run's window
            per_run = first["throughput"]["per_run"]
            self.assertEqual([row["status"] for row in per_run], ["finished"] * 3)
            self.assertEqual(per_run[0]["window_seconds"], 1.0)
            self.assertEqual(per_run[0]["valid_finished"], 3)
            self.assertEqual(per_run[0]["request_throughput"], 3.0)
            self.assertEqual(per_run[0]["valid_finished_output_tokens"], 7)
            self.assertEqual(per_run[0]["output_token_throughput"], 7.0)
            self.assertEqual(per_run[1]["window_seconds"], 0.5)
            self.assertEqual(per_run[1]["request_throughput"], 4.0)
            self.assertEqual(
                first["throughput"]["across_runs"]["request_throughput"]["n"],
                3,
            )

    def test_outcome_buckets_and_invalid_preserved(self):
        document = _base_raw(
            run_id="only",
            run_number=1,
            started_ns=10,
            ended_ns=20,
            requests=[
                _finished_request(
                    request_index=0,
                    seq_id=1,
                    request_class="short",
                    prompt_tokens=8,
                    output_tokens=2,
                    arrival=1,
                    first_scheduled=2,
                    first_output=3,
                    completed=4,
                ),
                {
                    "request_index": 1,
                    "seq_id": 2,
                    "request_class": "short",
                    "prompt_tokens": 8,
                    "requested_output_tokens": 2,
                    "output_tokens": 0,
                    "outcome": "cancelled",
                    "timestamps_ns": {
                        "arrival": 1,
                        "first_scheduled": None,
                        "first_output": None,
                        "completed": None,
                    },
                    "error": None,
                },
                {
                    "request_index": 2,
                    "seq_id": 3,
                    "request_class": "long",
                    "prompt_tokens": 8,
                    "requested_output_tokens": 2,
                    "output_tokens": 1,
                    "outcome": "incomplete",
                    "timestamps_ns": {
                        "arrival": 1,
                        "first_scheduled": 2,
                        "first_output": 3,
                        "completed": None,
                    },
                    "error": None,
                },
                {
                    "request_index": 3,
                    "seq_id": 4,
                    "request_class": "short",
                    "prompt_tokens": 8,
                    "requested_output_tokens": 2,
                    "output_tokens": 2,
                    "outcome": "weird",
                    "timestamps_ns": {
                        "arrival": 1,
                        "first_scheduled": 2,
                        "first_output": 3,
                        "completed": 4,
                    },
                    "error": None,
                },
                {
                    "request_index": 4,
                    "seq_id": 5,
                    "request_class": "short",
                    "prompt_tokens": 8,
                    "requested_output_tokens": 0,
                    "output_tokens": 0,
                    "outcome": "finished",
                    "timestamps_ns": {
                        "arrival": 1,
                        "first_scheduled": 2,
                        "first_output": 3,
                        "completed": 4,
                    },
                    "error": None,
                },
            ],
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "one.json"
            path.write_text(json.dumps(document) + "\n", encoding="utf-8")
            result = aggregate_raw_paths([path])
            outcomes = result["counts"]["outcomes"]
            self.assertEqual(outcomes["finished"], 2)
            self.assertEqual(outcomes["cancelled"], 1)
            self.assertEqual(outcomes["incomplete"], 1)
            self.assertEqual(outcomes["other"], 1)
            self.assertEqual(result["counts"]["valid_finished"], 1)
            self.assertEqual(result["counts"]["invalid_records"], 1)
            self.assertEqual(result["counts"]["total_requests"], 5)

    def test_malformed_and_identity_rejections(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bad_json = root / "bad.json"
            bad_json.write_text("{not-json", encoding="utf-8")
            with self.assertRaises(AggregateError):
                aggregate_raw_paths([bad_json])

            docs = _three_compatible_raws()
            docs[0]["schema_version"] = 2
            path = root / "schema.json"
            path.write_text(json.dumps(docs[0]) + "\n", encoding="utf-8")
            with self.assertRaises(AggregateError):
                aggregate_raw_paths([path])

            docs = _three_compatible_raws()
            docs[0]["schema_version"] = True
            path = root / "schema-bool.json"
            path.write_text(json.dumps(docs[0]) + "\n", encoding="utf-8")
            with self.assertRaises(AggregateError):
                aggregate_raw_paths([path])

    def test_run_status_is_required_and_failed_run_has_no_throughput(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            document = _three_compatible_raws()[0]
            document["status"] = "failed"
            path = _write_raws(root, [document])[0]
            result = aggregate_raw_paths([path])
            row = result["throughput"]["per_run"][0]
            self.assertEqual(row["status"], "failed")
            self.assertIsNone(row["window_seconds"])
            self.assertIsNone(row["request_throughput"])
            self.assertIsNone(row["output_token_throughput"])
            self.assertEqual(
                result["throughput"]["across_runs"]["request_throughput"]["n"], 0
            )

            for status in (None, "running", True):
                invalid = deepcopy(document)
                if status is None:
                    invalid.pop("status")
                else:
                    invalid["status"] = status
                invalid_path = root / f"status-{status!s}.json"
                invalid_path.write_text(json.dumps(invalid) + "\n", encoding="utf-8")
                with self.subTest(status=status), self.assertRaises(AggregateError):
                    aggregate_raw_paths([invalid_path])

    def test_finished_request_uses_strict_integer_and_class_contract(self):
        mutations = {
            "fractional timestamp": lambda request: request["timestamps_ns"].update(
                {"completed": 4.5}
            ),
            "boolean output": lambda request: request.update({"output_tokens": True}),
            "string output": lambda request: request.update({"output_tokens": "2"}),
            "unknown class": lambda request: request.update(
                {"request_class": "medium"}
            ),
            "missing class": lambda request: request.pop("request_class"),
            "missing request index": lambda request: request.pop("request_index"),
            "requested mismatch": lambda request: request.update(
                {"requested_output_tokens": 3}
            ),
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for index, (label, mutate) in enumerate(mutations.items(), start=1):
                request = _finished_request(
                    request_index=0,
                    seq_id=1,
                    request_class="short",
                    prompt_tokens=8,
                    output_tokens=2,
                    arrival=1,
                    first_scheduled=2,
                    first_output=3,
                    completed=4,
                )
                mutate(request)
                document = _base_raw(
                    run_id=f"strict-{index}",
                    run_number=index,
                    requests=[request],
                    started_ns=1,
                    ended_ns=10,
                )
                path = _write_raws(root, [document])[0]
                with self.subTest(case=label):
                    result = aggregate_raw_paths([path])
                    self.assertEqual(result["counts"]["valid_finished"], 0)
                    self.assertEqual(result["counts"]["invalid_records"], 1)
                    self.assertEqual(
                        result["latency_ms"]["all"]["queue_time_ms"]["n"], 0
                    )

    def test_duplicate_finished_request_identity_is_invalid(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            requests = [
                _finished_request(
                    request_index=0,
                    seq_id=10,
                    request_class="short",
                    prompt_tokens=8,
                    output_tokens=2,
                    arrival=1,
                    first_scheduled=2,
                    first_output=3,
                    completed=4,
                ),
                _finished_request(
                    request_index=0,
                    seq_id=11,
                    request_class="short",
                    prompt_tokens=8,
                    output_tokens=2,
                    arrival=1,
                    first_scheduled=2,
                    first_output=3,
                    completed=4,
                ),
                _finished_request(
                    request_index=2,
                    seq_id=10,
                    request_class="long",
                    prompt_tokens=8,
                    output_tokens=2,
                    arrival=1,
                    first_scheduled=2,
                    first_output=3,
                    completed=4,
                ),
            ]
            document = _base_raw(
                run_id="duplicates",
                run_number=1,
                requests=requests,
                started_ns=1,
                ended_ns=10,
            )
            path = _write_raws(root, [document])[0]
            result = aggregate_raw_paths([path])
            self.assertEqual(result["counts"]["outcomes"]["finished"], 3)
            self.assertEqual(result["counts"]["valid_finished"], 1)
            self.assertEqual(result["counts"]["invalid_records"], 2)
            self.assertEqual(
                result["latency_ms"]["all"]["queue_time_ms"]["n"], 1
            )

    def test_measurement_timestamps_are_strict_integers(self):
        invalid_values = (1.5, True, "1")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for index, value in enumerate(invalid_values, start=1):
                document = _three_compatible_raws()[0]
                document["run_id"] = f"measurement-{index}"
                document["run_number"] = index
                document["measurement"]["started_ns"] = value
                path = _write_raws(root, [document])[0]
                with self.subTest(value=value):
                    row = aggregate_raw_paths([path])["throughput"]["per_run"][0]
                    self.assertIsNone(row["window_seconds"])
                    self.assertIsNone(row["request_throughput"])

    def test_required_container_shapes_and_package_versions_rejected(self):
        mutations = {
            "unmapped object": lambda document: document.update(
                {"unmapped_timing_records": {}}
            ),
            "packages list": lambda document: document["environment"].update(
                {"packages": []}
            ),
            "packages strings": lambda document: document["environment"].update(
                {"packages": ["bad"]}
            ),
            "missing package": lambda document: document["environment"][
                "packages"
            ].pop("torch"),
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for index, (label, mutate) in enumerate(mutations.items(), start=1):
                document = _three_compatible_raws()[0]
                document["run_id"] = f"shape-{index}"
                document["run_number"] = index
                mutate(document)
                path = _write_raws(root, [document])[0]
                with self.subTest(case=label), self.assertRaises(AggregateError):
                    aggregate_raw_paths([path])

    def test_invalid_encoding_and_non_finite_json_fail_cleanly(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            invalid_utf8 = root / "invalid-utf8.json"
            invalid_utf8.write_bytes(b"\xff\xfe")
            non_finite = root / "nan.json"
            non_finite.write_text('{"value": NaN}', encoding="utf-8")

            for path in (invalid_utf8, non_finite):
                with self.subTest(path=path.name), self.assertRaises(AggregateError):
                    aggregate_raw_paths([path])
                stderr = io.StringIO()
                with contextlib.redirect_stderr(stderr):
                    code = main(
                        [
                            "--raw",
                            str(path),
                            "--output",
                            str(root / f"{path.stem}-out.json"),
                        ]
                    )
                self.assertEqual(code, 1)
                self.assertIn("aggregation failed:", stderr.getvalue())
                self.assertNotIn("Traceback", stderr.getvalue())

            docs = _three_compatible_raws()
            docs[0]["experiment"] = "OTHER"
            path = root / "experiment.json"
            path.write_text(json.dumps(docs[0]) + "\n", encoding="utf-8")
            with self.assertRaises(AggregateError):
                aggregate_raw_paths([path])

            docs = _three_compatible_raws()
            docs[0]["repository"]["dirty"] = True
            path = root / "dirty.json"
            path.write_text(json.dumps(docs[0]) + "\n", encoding="utf-8")
            with self.assertRaises(AggregateError):
                aggregate_raw_paths([path])

    def test_compatibility_mix_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            docs = _three_compatible_raws()[:2]
            docs[1]["repository"]["commit"] = "other-commit"
            paths = _write_raws(root, docs)
            with self.assertRaises(AggregateError):
                aggregate_raw_paths(paths)

            docs = _three_compatible_raws()[:2]
            docs[1]["model"]["revision"] = "different"
            model_dir = root / "model"
            model_dir.mkdir()
            paths = _write_raws(model_dir, docs)
            with self.assertRaises(AggregateError):
                aggregate_raw_paths(paths)

            docs = _three_compatible_raws()[:2]
            docs[1]["engine"]["max_num_seqs"] = 1
            engine_dir = root / "engine"
            engine_dir.mkdir()
            paths = _write_raws(engine_dir, docs)
            with self.assertRaises(AggregateError):
                aggregate_raw_paths(paths)

            docs = _three_compatible_raws()[:2]
            docs[1]["workload"]["manifest_sha256"] = "0" * 64
            workload_dir = root / "workload"
            workload_dir.mkdir()
            paths = _write_raws(workload_dir, docs)
            with self.assertRaises(AggregateError):
                aggregate_raw_paths(paths)

            docs = _three_compatible_raws()[:2]
            docs[1]["environment"]["cuda_device"] = "other-gpu"
            env_dir = root / "env"
            env_dir.mkdir()
            paths = _write_raws(env_dir, docs)
            with self.assertRaises(AggregateError):
                aggregate_raw_paths(paths)

            # branch / local_path / created_at differences must NOT reject
            docs = _three_compatible_raws()[:2]
            docs[0]["repository"]["branch"] = "one"
            docs[1]["repository"]["branch"] = "two"
            docs[1]["model"]["local_path"] = "/other/path"
            docs[1]["created_at_utc"] = "2099-01-01T00:00:00+00:00"
            ok_dir = root / "ok-identity"
            ok_dir.mkdir()
            paths = _write_raws(ok_dir, docs)
            result = aggregate_raw_paths(paths)
            self.assertEqual(result["counts"]["valid_finished"], 5)

    def test_single_source_must_match_frozen_workload_identity(self):
        mutations = {
            "arrival": ("arrival_model", "offline"),
            "seed": ("seed", 1),
            "sampling seed": ("sampling_seed", 1),
            "request count": ("request_count", 63),
            "manifest": ("manifest_sha256", "0" * 64),
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for index, (label, (key, value)) in enumerate(
                mutations.items(), start=1
            ):
                document = _three_compatible_raws()[0]
                document["run_id"] = f"workload-{index}"
                document["run_number"] = index
                document["workload"][key] = value
                path = _write_raws(root, [document])[0]
                with self.subTest(case=label), self.assertRaises(AggregateError):
                    aggregate_raw_paths([path])

    def test_duplicate_run_id_number_source_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            docs = _three_compatible_raws()[:2]
            docs[1]["run_id"] = docs[0]["run_id"]
            dup_id = root / "dup-id"
            dup_id.mkdir()
            paths = _write_raws(dup_id, docs)
            with self.assertRaises(AggregateError):
                aggregate_raw_paths(paths)

            docs = _three_compatible_raws()[:2]
            docs[1]["run_number"] = docs[0]["run_number"]
            dup_num = root / "dup-num"
            dup_num.mkdir()
            paths = _write_raws(dup_num, docs)
            with self.assertRaises(AggregateError):
                aggregate_raw_paths(paths)

            docs = _three_compatible_raws()[:1]
            dup_src = root / "dup-src"
            dup_src.mkdir()
            paths = _write_raws(dup_src, docs)
            with self.assertRaises(AggregateError):
                aggregate_raw_paths([paths[0], paths[0]])

    def test_measurement_window_invalid_yields_null_throughput(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            missing_end = _base_raw(
                run_id="a",
                run_number=1,
                requests=[
                    _finished_request(
                        request_index=0,
                        seq_id=1,
                        request_class="short",
                        prompt_tokens=8,
                        output_tokens=2,
                        arrival=1,
                        first_scheduled=2,
                        first_output=3,
                        completed=4,
                    )
                ],
                started_ns=100,
                ended_ns=None,
            )
            non_positive = _base_raw(
                run_id="b",
                run_number=2,
                requests=[
                    _finished_request(
                        request_index=0,
                        seq_id=2,
                        request_class="short",
                        prompt_tokens=8,
                        output_tokens=2,
                        arrival=1,
                        first_scheduled=2,
                        first_output=3,
                        completed=4,
                    )
                ],
                started_ns=200,
                ended_ns=200,
            )
            paths = _write_raws(root, [missing_end, non_positive])
            result = aggregate_raw_paths(paths)
            self.assertEqual(len(result["throughput"]["per_run"]), 2)
            self.assertIsNone(result["throughput"]["per_run"][0]["window_seconds"])
            self.assertIsNone(result["throughput"]["per_run"][0]["request_throughput"])
            self.assertIsNone(result["throughput"]["per_run"][1]["window_seconds"])
            self.assertEqual(
                result["throughput"]["across_runs"]["request_throughput"]["n"],
                0,
            )

    def test_raw_inputs_are_not_modified(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = _write_raws(root, _three_compatible_raws())
            before = {path: path.read_bytes() for path in paths}
            aggregate_raw_paths(paths)
            after = {path: path.read_bytes() for path in paths}
            self.assertEqual(before, after)

    def test_output_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = _write_raws(root, _three_compatible_raws()[:1])
            document = aggregate_raw_paths(paths)
            output = root / "agg.json"
            write_aggregate_document(document, output)
            text = output.read_text(encoding="utf-8")
            self.assertTrue(text.endswith("\n"))
            self.assertEqual(json.loads(text)["aggregator"], "NSL-S2-AGG-v1")
            with self.assertRaises(AggregateError):
                write_aggregate_document(document, output)

    def test_output_rejects_dangling_symlink_and_non_finite_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "target.json"
            output = root / "aggregate.json"
            output.symlink_to(target)
            with self.assertRaises(AggregateError):
                write_aggregate_document({"ok": True}, output)
            self.assertFalse(target.exists())

            with self.assertRaises(AggregateError):
                write_aggregate_document({"bad": float("nan")}, root / "nan.json")

    def test_cli_help_and_import_do_not_load_torch_in_fresh_subprocess(self):
        previous_torch = sys.modules.get("torch")
        sys.modules["torch"] = SimpleNamespace(__name__="torch")
        try:
            self.assertIn("torch", sys.modules)
            namespace = parse_args(
                ["--raw", "a.json", "--raw", "b.json", "--output", "out.json"]
            )
            self.assertEqual(len(namespace.raw_paths), 2)

            import_probe = textwrap.dedent(
                """
                import sys
                import research.stage2_aggregate as agg
                assert "torch" not in sys.modules, sorted(sys.modules)
                assert agg.SCHEMA_VERSION == 1
                assert agg.AGGREGATOR_ID == "NSL-S2-AGG-v1"
                print("import-ok")
                """
            )
            imported = subprocess.run(
                [sys.executable, "-c", import_probe],
                check=False,
                capture_output=True,
                text=True,
                cwd=str(Path(__file__).resolve().parents[1]),
            )
            self.assertEqual(imported.returncode, 0, imported.stderr)
            self.assertIn("import-ok", imported.stdout)

            helped = subprocess.run(
                [sys.executable, "research/stage2_aggregate.py", "--help"],
                check=False,
                capture_output=True,
                text=True,
                cwd=str(Path(__file__).resolve().parents[1]),
            )
            self.assertEqual(helped.returncode, 0, helped.stderr)
            self.assertIn("NSL-S2-AGG-v1", helped.stdout)
            self.assertNotIn("ModuleNotFoundError", helped.stderr)
            self.assertNotIn("torch", helped.stderr.lower())
        finally:
            if previous_torch is None:
                sys.modules.pop("torch", None)
            else:
                sys.modules["torch"] = previous_torch

    def test_cli_main_writes_aggregate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = _write_raws(root, _three_compatible_raws())
            output = root / "out.json"
            code = main(
                [
                    "--raw",
                    str(paths[0]),
                    "--raw",
                    str(paths[1]),
                    "--raw",
                    str(paths[2]),
                    "--output",
                    str(output),
                ]
            )
            self.assertEqual(code, 0)
            self.assertTrue(output.is_file())
            loaded = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(loaded["counts"]["valid_finished"], 6)


if __name__ == "__main__":
    unittest.main()
