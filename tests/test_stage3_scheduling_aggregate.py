"""Deterministic CPU tests for NSL-S3-SCHED-v1 policy aggregation."""

from __future__ import annotations

import contextlib
import io
import json
import subprocess
import sys
import tempfile
import textwrap
import unittest
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from research.stage2_workload import (
    EXPECTED_MANIFEST_SHA256,
    WORKLOAD_ID,
    build_saturated_mixed_workload,
)
from research.stage3_scheduling_aggregate import (
    AGGREGATOR_ID,
    EXECUTION_ORDER,
    FCFS_POLICY,
    PROMPT_LENGTH_POLICY,
    Stage3AggregateError,
    aggregate_stage3_raw_paths,
    main,
    parse_args,
    write_stage3_aggregate_document,
)
from research.stage3_scheduling_driver import (
    EXPERIMENT_CONTRACT,
    policy_metadata,
)

_ENVIRONMENT = {
    "platform": "Linux-fixture",
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
}
_FIXED_ENGINE = {
    "enforce_eager": False,
    "max_model_len": 4096,
    "max_num_seqs": 512,
    "max_num_batched_tokens": 16384,
    "gpu_memory_utilization": 0.9,
    "tensor_parallel_size": 1,
    "kvcache_block_size": 256,
}
_WORKLOAD = build_saturated_mixed_workload()


def _request_entry(policy: str, run_number: int, request_index: int) -> dict:
    request = _WORKLOAD[request_index]
    base = run_number * 100_000_000_000 + request_index * 10_000
    queue_ms = 100.0 + request_index
    if policy == PROMPT_LENGTH_POLICY and request.request_class == "short":
        queue_ms -= 25.0
    first_scheduled = base + int(queue_ms * 1_000_000)
    first_output = first_scheduled + 10_000_000
    completed = first_output + (request.max_tokens - 1) * 1_000_000
    return {
        "request_index": request.request_index,
        "seq_id": run_number * 1_000 + request_index,
        "request_class": request.request_class,
        "prompt_tokens": len(request.prompt_token_ids),
        "requested_output_tokens": request.max_tokens,
        "output_tokens": request.max_tokens,
        "outcome": "finished",
        "timestamps_ns": {
            "arrival": base,
            "first_scheduled": first_scheduled,
            "first_output": first_output,
            "completed": completed,
        },
        "error": None,
    }


def _raw(policy: str, run_number: int) -> dict:
    started = run_number * 100_000_000_000
    return {
        "schema_version": 2,
        "experiment": EXPERIMENT_CONTRACT,
        "experiment_contract": EXPERIMENT_CONTRACT,
        "comparison_group": "prompt-length-fixture-a",
        "run_id": f"{policy}-run-{run_number}",
        "run_number": run_number,
        "created_at_utc": f"2026-07-26T12:0{run_number}:00+00:00",
        "status": "finished",
        "error": None,
        "repository": {
            "commit": "same-clean-commit",
            "branch": f"fixture-{policy}",
            "dirty": False,
        },
        "environment": deepcopy(_ENVIRONMENT),
        "model": {
            "id": "Qwen/Qwen3-0.6B",
            "revision": "c1899de289a04d12100db370d81485cdf75e47ca",
            "local_path": f"/fixture/{policy}/model",
        },
        "engine": {
            **deepcopy(_FIXED_ENGINE),
            "requested_scheduling_policy": policy,
            "scheduling_policy": policy,
        },
        "workload": {
            "id": WORKLOAD_ID,
            "arrival_model": "saturated_batch",
            "seed": 0,
            "sampling_seed": 0,
            "request_count": 64,
            "manifest_sha256": EXPECTED_MANIFEST_SHA256,
        },
        "policy": policy_metadata(policy, runtime_verified=True),
        "warmup": {
            "measured": False,
            "timing_records": [],
        },
        "measurement": {
            "clock": "time.perf_counter_ns",
            "started_ns": started,
            "ended_ns": started + 10_000_000_000,
            "cuda_synchronized": True,
        },
        "requests": [
            _request_entry(policy, run_number, request_index)
            for request_index in range(64)
        ],
        "unmapped_timing_records": [],
    }


def _six_raws() -> list[dict]:
    documents = [
        _raw(policy, run_number)
        for policy, run_number in EXECUTION_ORDER
    ]
    for position, document in enumerate(documents, start=1):
        document["created_at_utc"] = (
            f"2026-07-26T12:00:0{position}+00:00"
        )
    return documents


def _write_raws(directory: Path, documents: list[dict]) -> list[Path]:
    paths: list[Path] = []
    for index, document in enumerate(documents, start=1):
        path = directory / (
            f"{index}-{document.get('policy', {}).get('id', 'bad')}-"
            f"run{document.get('run_number', 'bad')}.json"
        )
        path.write_text(
            json.dumps(document, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        paths.append(path)
    return paths


class Stage3SchedulingAggregateTest(unittest.TestCase):
    def test_valid_six_run_comparison_and_deltas(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = _write_raws(Path(tmp), _six_raws())
            created = datetime(2026, 7, 26, 14, 0, 0, tzinfo=timezone.utc)
            result = aggregate_stage3_raw_paths(paths, created_at=created)

        self.assertEqual(result["schema_version"], 1)
        self.assertEqual(result["aggregator"], AGGREGATOR_ID)
        self.assertEqual(result["experiment_contract"], EXPERIMENT_CONTRACT)
        self.assertEqual(result["comparison_group"], "prompt-length-fixture-a")
        self.assertEqual(
            [
                (item["policy"], item["run_number"])
                for item in result["sources"]
            ],
            list(EXECUTION_ORDER),
        )
        self.assertEqual(
            result["compatibility"]["workload"]["id"],
            WORKLOAD_ID,
        )
        for policy in (FCFS_POLICY, PROMPT_LENGTH_POLICY):
            policy_result = result["policies"][policy]
            self.assertTrue(policy_result["validity"]["valid"])
            self.assertIs(
                policy_result["policy"]["runtime_verified"],
                True,
            )
            self.assertEqual(
                policy_result["policy"]["runtime_verification_scope"],
                "all_sources",
            )
            self.assertEqual(policy_result["counts"]["total_requests"], 192)
            self.assertEqual(policy_result["counts"]["valid_finished"], 192)
            self.assertEqual(policy_result["counts"]["invalid_records"], 0)
            self.assertEqual(
                policy_result["latency_ms"]["short"]["ttft_ms"]["n"],
                144,
            )
            self.assertEqual(
                policy_result["latency_ms"]["long"]["ttft_ms"]["n"],
                48,
            )
            self.assertEqual(
                policy_result["throughput"]["across_runs"][
                    "output_token_throughput"
                ]["mean"],
                563.2,
            )
            self.assertIsNotNone(
                policy_result["worst_requests"]["e2e_ms"]
            )

        comparison = result["comparison"]
        self.assertTrue(comparison["valid"])
        short_ttft = comparison["latency_ms_deltas"]["short"]["ttft_ms"]["mean"]
        self.assertLess(short_ttft["absolute"], 0)
        self.assertLess(short_ttft["relative_percent"], 0)
        long_ttft = comparison["latency_ms_deltas"]["long"]["ttft_ms"]["mean"]
        self.assertEqual(long_ttft["absolute"], 0.0)
        self.assertFalse(
            comparison["warnings"]["throughput_degradation_over_5_percent"]
        )
        self.assertFalse(comparison["warnings"]["fairness_risk"])

    def test_input_order_is_canonicalized_and_raws_are_read_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = _write_raws(Path(tmp), _six_raws())
            before = {path: path.read_bytes() for path in paths}
            result = aggregate_stage3_raw_paths(list(reversed(paths)))
            after = {path: path.read_bytes() for path in paths}
        self.assertEqual(before, after)
        self.assertEqual(
            [
                (item["policy"], item["run_number"])
                for item in result["sources"]
            ],
            list(EXECUTION_ORDER),
        )

    def test_throughput_degradation_warning_uses_predeclared_five_percent(self):
        documents = _six_raws()
        for document in documents:
            if document["policy"]["id"] == PROMPT_LENGTH_POLICY:
                document["measurement"]["ended_ns"] = (
                    document["measurement"]["started_ns"] + 11_000_000_000
                )
        with tempfile.TemporaryDirectory() as tmp:
            paths = _write_raws(Path(tmp), documents)
            result = aggregate_stage3_raw_paths(paths)
        delta = result["comparison"]["throughput_deltas"][
            "output_token_throughput"
        ]["mean"]
        self.assertLess(delta["relative_percent"], -5.0)
        self.assertTrue(
            result["comparison"]["warnings"][
                "throughput_degradation_over_5_percent"
            ]
        )

    def test_long_tail_increase_is_reported_as_direct_fairness_risk(self):
        documents = _six_raws()
        for document in documents:
            if document["policy"]["id"] != PROMPT_LENGTH_POLICY:
                continue
            for request in document["requests"]:
                if request["request_class"] != "long":
                    continue
                for key in ("first_scheduled", "first_output", "completed"):
                    request["timestamps_ns"][key] += 50_000_000
        with tempfile.TemporaryDirectory() as tmp:
            result = aggregate_stage3_raw_paths(
                _write_raws(Path(tmp), documents)
            )
        warnings = result["comparison"]["warnings"]
        self.assertTrue(warnings["fairness_risk"])
        self.assertTrue(
            any(
                item["kind"] == "latency_increase"
                and item["request_class"] == "long"
                and item["metric"] == "e2e_ms"
                and item["statistic"] == "p95"
                for item in warnings["fairness_items"]
            )
        )

    def test_exact_policy_run_matrix_and_unique_run_ids_required(self):
        cases: dict[str, list[dict]] = {}
        cases["missing"] = _six_raws()[:-1]
        duplicate_key = _six_raws()
        duplicate_key[-1]["run_number"] = 2
        duplicate_key[-1]["run_id"] = "unique-but-duplicate-key"
        cases["duplicate key"] = duplicate_key
        duplicate_id = _six_raws()
        duplicate_id[-1]["run_id"] = duplicate_id[0]["run_id"]
        cases["duplicate id"] = duplicate_id

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for index, (label, documents) in enumerate(cases.items(), start=1):
                directory = root / str(index)
                directory.mkdir()
                paths = _write_raws(directory, documents)
                with self.subTest(case=label), self.assertRaises(
                    Stage3AggregateError
                ):
                    aggregate_stage3_raw_paths(paths)

    def test_created_at_must_prove_fixed_execution_order(self):
        documents = _six_raws()
        documents[1]["created_at_utc"] = documents[0]["created_at_utc"]
        with tempfile.TemporaryDirectory() as tmp:
            paths = _write_raws(Path(tmp), documents)
            with self.assertRaises(Stage3AggregateError):
                aggregate_stage3_raw_paths(paths)

    def test_comparison_group_and_compatibility_mix_rejected(self):
        mutations = {
            "group": lambda document: document.update(
                {"comparison_group": "other-group"}
            ),
            "commit": lambda document: document["repository"].update(
                {"commit": "different"}
            ),
            "environment": lambda document: document["environment"].update(
                {"cuda_device": "different"}
            ),
            "model": lambda document: document["model"].update(
                {"revision": "different"}
            ),
            "fixed engine": lambda document: document["engine"].update(
                {"max_num_seqs": 1}
            ),
            "workload": lambda document: document["workload"].update(
                {"manifest_sha256": "0" * 64}
            ),
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for index, (label, mutate) in enumerate(mutations.items(), start=1):
                documents = _six_raws()
                mutate(documents[-1])
                directory = root / str(index)
                directory.mkdir()
                paths = _write_raws(directory, documents)
                with self.subTest(case=label), self.assertRaises(
                    Stage3AggregateError
                ):
                    aggregate_stage3_raw_paths(paths)

    def test_stage3_schema_and_policy_identity_are_strict(self):
        mutations = {
            "schema": lambda document: document.update({"schema_version": 1}),
            "experiment": lambda document: document.update({"experiment": "other"}),
            "contract": lambda document: document.update(
                {"experiment_contract": "other"}
            ),
            "dirty": lambda document: document["repository"].update({"dirty": True}),
            "workload id": lambda document: document["workload"].update({"id": "other"}),
            "policy version": lambda document: document["policy"].update(
                {"definition_version": 2}
            ),
            "policy parameters": lambda document: document["policy"].update(
                {"parameters": {"changed": True}}
            ),
            "actual policy": lambda document: document["engine"].update(
                {"scheduling_policy": PROMPT_LENGTH_POLICY}
            ),
            "runtime verified": lambda document: document["policy"].update(
                {"runtime_verified": False}
            ),
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for index, (label, mutate) in enumerate(mutations.items(), start=1):
                documents = _six_raws()
                mutate(documents[0])
                directory = root / str(index)
                directory.mkdir()
                paths = _write_raws(directory, documents)
                with self.subTest(case=label), self.assertRaises(
                    Stage3AggregateError
                ):
                    aggregate_stage3_raw_paths(paths)

    def test_failed_run_is_preserved_but_comparison_is_invalid(self):
        documents = _six_raws()
        failed = documents[1]
        failed["status"] = "failed"
        failed["error"] = {"type": "RuntimeError", "message": "fixture"}
        failed["policy"]["runtime_verified"] = False
        failed["engine"]["scheduling_policy"] = None
        failed["requests"] = []
        failed["measurement"]["ended_ns"] = None
        failed["measurement"]["cuda_synchronized"] = False
        with tempfile.TemporaryDirectory() as tmp:
            result = aggregate_stage3_raw_paths(
                _write_raws(Path(tmp), documents)
            )
        self.assertFalse(result["comparison"]["valid"])
        candidate = result["policies"][PROMPT_LENGTH_POLICY]
        failed_row = next(
            row for row in candidate["throughput"]["per_run"]
            if row["run_number"] == 1
        )
        self.assertFalse(failed_row["contract_valid"])
        self.assertIsNone(failed_row["output_token_throughput"])
        self.assertTrue(
            any("status=failed" in reason for reason in failed_row["invalid_reasons"])
        )

    def test_bad_request_shape_is_counted_invalid_not_silently_used(self):
        documents = _six_raws()
        bad = documents[1]["requests"][0]
        bad["prompt_tokens"] += 1
        with tempfile.TemporaryDirectory() as tmp:
            result = aggregate_stage3_raw_paths(
                _write_raws(Path(tmp), documents)
            )
        candidate = result["policies"][PROMPT_LENGTH_POLICY]
        self.assertEqual(candidate["counts"]["invalid_records"], 1)
        self.assertEqual(candidate["counts"]["valid_finished"], 191)
        self.assertFalse(result["comparison"]["valid"])

    def test_candidate_incomplete_request_sets_completion_fairness_risk(self):
        documents = _six_raws()
        incomplete = documents[1]["requests"][1]
        incomplete["outcome"] = "incomplete"
        incomplete["output_tokens"] = 0
        incomplete["timestamps_ns"]["completed"] = None
        with tempfile.TemporaryDirectory() as tmp:
            result = aggregate_stage3_raw_paths(
                _write_raws(Path(tmp), documents)
            )
        warnings = result["comparison"]["warnings"]
        self.assertFalse(result["comparison"]["valid"])
        self.assertTrue(warnings["fairness_risk"])
        self.assertTrue(
            any(
                item["kind"] == "request_completion"
                for item in warnings["fairness_items"]
            )
        )

    def test_malformed_encoding_non_finite_and_container_fail_cleanly(self):
        bad_payloads = {
            "utf8": b"\xff\xfe",
            "nan": b'{"value": NaN}',
            "array": b"[]",
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for index, (label, bad_bytes) in enumerate(
                bad_payloads.items(),
                start=1,
            ):
                directory = root / str(index)
                directory.mkdir()
                valid_paths = _write_raws(directory, _six_raws()[:5])
                bad_path = directory / f"{label}.json"
                bad_path.write_bytes(bad_bytes)
                paths = valid_paths + [bad_path]
                with self.subTest(case=label), self.assertRaises(
                    Stage3AggregateError
                ):
                    aggregate_stage3_raw_paths(paths)

                stderr = io.StringIO()
                with contextlib.redirect_stderr(stderr):
                    code = main(
                        [
                            argument
                            for path in paths
                            for argument in ("--raw", str(path))
                        ]
                        + ["--output", str(directory / "out.json")]
                    )
                self.assertEqual(code, 1)
                self.assertIn("Stage 3 aggregation failed:", stderr.getvalue())
                self.assertNotIn("Traceback", stderr.getvalue())

    def test_output_is_exclusive_and_rejects_non_finite_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            document = aggregate_stage3_raw_paths(
                _write_raws(root, _six_raws())
            )
            output = root / "aggregate.json"
            write_stage3_aggregate_document(document, output)
            original = output.read_bytes()
            self.assertTrue(original.endswith(b"\n"))
            self.assertEqual(json.loads(original)["aggregator"], AGGREGATOR_ID)
            with self.assertRaises(Stage3AggregateError):
                write_stage3_aggregate_document(document, output)
            self.assertEqual(output.read_bytes(), original)
            with self.assertRaises(Stage3AggregateError):
                write_stage3_aggregate_document(
                    {"bad": float("nan")},
                    root / "nan.json",
                )
            wrong = deepcopy(document)
            wrong["aggregator"] = "other"
            with self.assertRaises(Stage3AggregateError):
                write_stage3_aggregate_document(
                    wrong,
                    root / "wrong.json",
                )

    def test_cli_help_and_import_do_not_load_torch(self):
        args = parse_args(
            [
                argument
                for index in range(6)
                for argument in ("--raw", f"run-{index}.json")
            ]
            + ["--output", "aggregate.json"]
        )
        self.assertEqual(len(args.raw_paths), 6)

        previous_torch = sys.modules.get("torch")
        sys.modules.pop("torch", None)
        try:
            probe = textwrap.dedent(
                """
                import sys
                import research.stage3_scheduling_aggregate as aggregate
                assert "torch" not in sys.modules, sorted(sys.modules)
                assert aggregate.AGGREGATOR_ID == "NSL-S3-AGG-v1"
                print("stage3-aggregate-import-ok")
                """
            )
            imported = subprocess.run(
                [sys.executable, "-c", probe],
                check=False,
                capture_output=True,
                text=True,
                cwd=str(Path(__file__).resolve().parents[1]),
            )
            self.assertEqual(imported.returncode, 0, imported.stderr)
            self.assertIn("stage3-aggregate-import-ok", imported.stdout)

            helped = subprocess.run(
                [
                    sys.executable,
                    "research/stage3_scheduling_aggregate.py",
                    "--help",
                ],
                check=False,
                capture_output=True,
                text=True,
                cwd=str(Path(__file__).resolve().parents[1]),
            )
            self.assertEqual(helped.returncode, 0, helped.stderr)
            self.assertIn(AGGREGATOR_ID, helped.stdout)
            self.assertNotIn("torch", helped.stderr.lower())
        finally:
            if previous_torch is not None:
                sys.modules["torch"] = previous_torch


if __name__ == "__main__":
    unittest.main()
