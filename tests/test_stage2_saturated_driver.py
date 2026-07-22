"""CPU fake-engine tests for the NSL-S2-SAT-v1 saturated admission driver."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import textwrap
import unittest
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from nanovllm.engine.request_timing import RequestTimingRecorder
from research.stage2_saturated_driver import (
    EXPECTED_MANIFEST_SHA256,
    MODEL_REVISION,
    REQUEST_COUNT,
    SaturatedDriverError,
    assert_no_derived_metric_fields,
    main,
    parse_args,
    run_saturated_admission,
    verify_manifest_fingerprint,
    write_saturated_artifact,
)
from research.stage2_workload import (
    CLASS_PATTERN,
    PATTERN_REPETITIONS,
    build_saturated_mixed_workload,
    workload_manifest_sha256,
)


class FakeClock:
    def __init__(self, start_ns: int = 1_000_000):
        self._now = start_ns
        self.events: list[str] | None = None

    def __call__(self) -> int:
        if self.events is not None:
            self.events.append("clock")
        value = self._now
        self._now += 1_000
        return value


@dataclass
class FakeRequest:
    seq_id: int
    prompt_token_ids: list[int]
    max_tokens: int
    output_tokens: int = 0
    finished: bool = False


class FakeEngine:
    """Records call order and drives RequestTimingRecorder with odd seq_ids."""

    def __init__(
        self,
        recorder: RequestTimingRecorder,
        *,
        events: list[str],
        measured_seq_ids: list[int],
        warmup_seq_id: int = 1000,
        fail_after_steps: int | None = None,
        duplicate_on_add: bool = False,
        skip_record_on_add: bool = False,
        raise_after_arrival: bool = False,
        pretend_finished: bool = False,
    ):
        self.recorder = recorder
        self.events = events
        self.measured_seq_ids = list(measured_seq_ids)
        self._next_measured = 0
        self.warmup_seq_id = warmup_seq_id
        self.fail_after_steps = fail_after_steps
        self.duplicate_on_add = duplicate_on_add
        self.skip_record_on_add = skip_record_on_add
        self.raise_after_arrival = raise_after_arrival
        self.pretend_finished = pretend_finished
        self._step_count = 0
        self._pending: list[FakeRequest] = []
        self.add_count = 0
        self.step_count = 0
        self.generate_count = 0

    def generate(self, prompts, sampling_params):
        self.events.append("generate")
        self.generate_count += 1
        prompt = prompts[0]
        prompt_tokens = len(prompt) if not isinstance(prompt, str) else 2
        self.recorder.record_arrival(self.warmup_seq_id, prompt_tokens)
        self.recorder.record_first_scheduled(self.warmup_seq_id)
        self.recorder.record_output_token(self.warmup_seq_id, 1)
        self.recorder.record_completed(self.warmup_seq_id, 1)
        return [{"text": "warmup"}]

    def add_request(self, prompt, sampling_params):
        self.events.append("add")
        self.add_count += 1
        if self.skip_record_on_add:
            return
        if self._next_measured >= len(self.measured_seq_ids):
            raise RuntimeError("no remaining measured seq_ids")
        seq_id = self.measured_seq_ids[self._next_measured]
        self._next_measured += 1
        self.recorder.record_arrival(seq_id, len(prompt))
        if self.raise_after_arrival:
            raise RuntimeError("injected add failure after arrival")
        if self.duplicate_on_add:
            extra = seq_id + 10_000
            self.recorder.record_arrival(extra, len(prompt))
        self._pending.append(
            FakeRequest(
                seq_id=seq_id,
                prompt_token_ids=list(prompt),
                max_tokens=sampling_params.max_tokens,
            )
        )

    def step(self):
        self.events.append("step")
        self.step_count += 1
        self._step_count += 1
        if self.fail_after_steps is not None and self._step_count > self.fail_after_steps:
            raise RuntimeError("injected step failure")

        for request in self._pending:
            if request.finished:
                continue
            if self.recorder.get(request.seq_id).first_scheduled_ns is None:
                self.recorder.record_first_scheduled(request.seq_id)
            # Complete one request fully per step so mid-run failures leave a
            # mix of finished and incomplete measured entries.
            while request.output_tokens < request.max_tokens:
                request.output_tokens += 1
                self.recorder.record_output_token(request.seq_id, request.output_tokens)
            self.recorder.record_completed(request.seq_id, request.output_tokens)
            request.finished = True
            break
        return [], 0

    def is_finished(self) -> bool:
        if self.pretend_finished:
            return True
        return bool(self._pending) and all(request.finished for request in self._pending)


class Stage2SaturatedDriverTest(unittest.TestCase):
    def setUp(self):
        self.events: list[str] = []
        self.clock = FakeClock()
        self.clock.events = self.events
        self.recorder = RequestTimingRecorder(clock_ns=self.clock)
        # Non-zero, non-contiguous process seq_ids prove no Sequence.counter dependency.
        self.measured_seq_ids = [
            5 + ((i * 17) % 97) + (i * 3)
            for i in range(REQUEST_COUNT)
        ]
        self.assertNotEqual(self.measured_seq_ids[0], 0)
        self.assertNotEqual(
            self.measured_seq_ids,
            list(range(REQUEST_COUNT)),
        )
        self.engine = FakeEngine(
            self.recorder,
            events=self.events,
            measured_seq_ids=self.measured_seq_ids,
            warmup_seq_id=1000,
        )
        self.workload = build_saturated_mixed_workload()

    def _sync(self) -> bool:
        self.events.append("sync")
        return False

    def _sampling_params_factory(self, max_tokens: int):
        return SimpleNamespace(max_tokens=max_tokens, temperature=0.6, ignore_eos=True)

    def _run(self, **overrides):
        kwargs = dict(
            engine=self.engine,
            recorder=self.recorder,
            sampling_params_factory=self._sampling_params_factory,
            warmup_sampling_params=SimpleNamespace(
                max_tokens=64,
                temperature=0.6,
                ignore_eos=True,
            ),
            clock_ns=self.clock,
            cuda_synchronize=self._sync,
            requests=self.workload,
            run_number=3,
            run_id="test-run-id",
            created_at=datetime(2026, 7, 22, 12, 0, 0, tzinfo=timezone.utc),
            repository={"commit": "deadbeef", "branch": "test", "dirty": False},
            environment={"python": "test"},
            model={"id": "Qwen/Qwen3-0.6B", "revision": MODEL_REVISION},
            engine_metadata={"enforce_eager": False},
            raise_on_failure=True,
        )
        kwargs.update(overrides)
        return run_saturated_admission(**kwargs)

    def test_successful_saturated_run_contract(self):
        artifact = self._run()

        self.assertEqual(artifact["status"], "finished")
        self.assertIsNone(artifact["error"])
        self.assertEqual(artifact["schema_version"], 1)
        self.assertEqual(artifact["experiment"], "NSL-S2-SAT-v1")
        self.assertEqual(artifact["run_id"], "test-run-id")
        self.assertEqual(artifact["workload"]["manifest_sha256"], EXPECTED_MANIFEST_SHA256)
        self.assertEqual(artifact["workload"]["request_count"], 64)
        self.assertEqual(artifact["unmapped_timing_records"], [])

        # 1) Warmup records preserved and excluded from measured requests.
        self.assertEqual(len(artifact["warmup"]["timing_records"]), 1)
        warmup_seq = artifact["warmup"]["timing_records"][0]["seq_id"]
        self.assertEqual(warmup_seq, 1000)
        measured_seq_ids = {item["seq_id"] for item in artifact["requests"]}
        self.assertNotIn(warmup_seq, measured_seq_ids)

        # 2/3) Exactly 64 adds, all before the first step.
        self.assertEqual(self.engine.add_count, 64)
        self.assertEqual(self.events.count("add"), 64)
        first_step = self.events.index("step")
        add_indexes = [index for index, name in enumerate(self.events) if name == "add"]
        self.assertEqual(len(add_indexes), 64)
        self.assertTrue(all(index < first_step for index in add_indexes))

        # 4) Fixed short/long order matches manifest.
        expected_classes = CLASS_PATTERN * PATTERN_REPETITIONS
        self.assertEqual(
            [item["request_class"] for item in artifact["requests"]],
            list(expected_classes),
        )
        self.assertEqual(
            [item["request_index"] for item in artifact["requests"]],
            list(range(64)),
        )

        # 5/6) Measurement bounds relative to sync/admission/completion.
        started = artifact["measurement"]["started_ns"]
        ended = artifact["measurement"]["ended_ns"]
        self.assertIsNotNone(started)
        self.assertIsNotNone(ended)
        self.assertGreater(ended, started)
        # Fake/CPU sync callbacks are invoked but do not claim real CUDA sync.
        self.assertFalse(artifact["measurement"]["cuda_synchronized"])

        generate_i = self.events.index("generate")
        first_sync = self.events.index("sync")
        self.assertGreater(first_sync, generate_i)
        # started clock is the first clock after the first sync.
        clock_after_first_sync = next(
            index
            for index, name in enumerate(self.events)
            if name == "clock" and index > first_sync
        )
        first_add = add_indexes[0]
        self.assertLess(clock_after_first_sync, first_add)
        last_sync = max(index for index, name in enumerate(self.events) if name == "sync")
        last_clock = max(index for index, name in enumerate(self.events) if name == "clock")
        self.assertGreater(last_clock, last_sync)
        self.assertGreater(last_sync, first_step)
        self.assertEqual(self.events.count("sync"), 2)

        # 7/8) Mapping uses odd non-contiguous seq_ids.
        for request_index, seq_id in enumerate(self.measured_seq_ids):
            self.assertEqual(artifact["requests"][request_index]["seq_id"], seq_id)

        # 9) Prompt / requested / actual output / outcome / timestamps.
        for request, item in zip(self.workload, artifact["requests"], strict=True):
            self.assertEqual(item["prompt_tokens"], len(request.prompt_token_ids))
            self.assertEqual(item["requested_output_tokens"], request.max_tokens)
            self.assertEqual(item["output_tokens"], request.max_tokens)
            self.assertEqual(item["outcome"], "finished")
            stamps = item["timestamps_ns"]
            self.assertLessEqual(stamps["arrival"], stamps["first_scheduled"])
            self.assertLessEqual(stamps["first_scheduled"], stamps["first_output"])
            self.assertLessEqual(stamps["first_output"], stamps["completed"])

        # 10) No overlap between warmup and measured records.
        self.assertTrue(measured_seq_ids.isdisjoint({warmup_seq}))

        assert_no_derived_metric_fields(artifact)

    def test_manifest_fingerprint_mismatch_rejects_run(self):
        with self.assertRaises(SaturatedDriverError) as ctx:
            self._run(
                expected_manifest_sha256="0" * 64,
                raise_on_failure=True,
            )
        self.assertIn("manifest fingerprint mismatch", str(ctx.exception))
        self.assertEqual(self.engine.generate_count, 0)
        self.assertEqual(self.engine.add_count, 0)

        artifact = self._run(
            expected_manifest_sha256="0" * 64,
            raise_on_failure=False,
        )
        self.assertEqual(artifact["status"], "failed")
        self.assertIn("manifest fingerprint mismatch", artifact["error"]["message"])
        self.assertEqual(artifact["requests"], [])
        self.assertIsNone(artifact["measurement"]["ended_ns"])
        # Failed mismatch artifacts must keep the actual recomputed digest.
        self.assertEqual(artifact["workload"]["manifest_sha256"], EXPECTED_MANIFEST_SHA256)
        self.assertEqual(artifact["unmapped_timing_records"], [])

    def test_mapping_fails_when_add_creates_no_record(self):
        self.engine = FakeEngine(
            self.recorder,
            events=self.events,
            measured_seq_ids=self.measured_seq_ids,
            skip_record_on_add=True,
        )
        artifact = self._run(raise_on_failure=False)
        self.assertEqual(artifact["status"], "failed")
        self.assertIn("mapping failed", artifact["error"]["message"])
        self.assertIsNone(artifact["measurement"]["ended_ns"])
        self.assertEqual(len(artifact["warmup"]["timing_records"]), 1)

    def test_mapping_fails_when_add_creates_multiple_records(self):
        self.engine = FakeEngine(
            self.recorder,
            events=self.events,
            measured_seq_ids=self.measured_seq_ids,
            duplicate_on_add=True,
        )
        artifact = self._run(raise_on_failure=False)
        self.assertEqual(artifact["status"], "failed")
        self.assertIn("mapping failed", artifact["error"]["message"])
        self.assertIsNone(artifact["measurement"]["ended_ns"])
        # Mapping was never established for the failing add; do not invent rows.
        self.assertEqual(artifact["requests"], [])
        unmapped = artifact["unmapped_timing_records"]
        self.assertEqual(len(unmapped), 2)
        expected_ids = sorted(
            [self.measured_seq_ids[0], self.measured_seq_ids[0] + 10_000]
        )
        self.assertEqual([item["seq_id"] for item in unmapped], expected_ids)

    def test_add_failure_after_arrival_keeps_unmapped_record(self):
        self.engine = FakeEngine(
            self.recorder,
            events=self.events,
            measured_seq_ids=self.measured_seq_ids,
            raise_after_arrival=True,
        )
        artifact = self._run(raise_on_failure=False)
        self.assertEqual(artifact["status"], "failed")
        self.assertEqual(artifact["error"]["type"], "RuntimeError")
        self.assertIn("injected add failure after arrival", artifact["error"]["message"])
        self.assertEqual(artifact["requests"], [])
        self.assertEqual(len(artifact["unmapped_timing_records"]), 1)
        self.assertEqual(
            artifact["unmapped_timing_records"][0]["seq_id"],
            self.measured_seq_ids[0],
        )

    def test_step_failure_writes_failed_artifact_without_ended_ns(self):
        self.engine = FakeEngine(
            self.recorder,
            events=self.events,
            measured_seq_ids=self.measured_seq_ids,
            fail_after_steps=1,
        )
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            artifact = self._run(
                raise_on_failure=False,
                write_artifact=True,
                output_dir=output_dir,
            )
            self.assertEqual(artifact["status"], "failed")
            self.assertEqual(artifact["error"]["type"], "RuntimeError")
            self.assertIn("injected step failure", artifact["error"]["message"])
            self.assertIsNone(artifact["measurement"]["ended_ns"])
            self.assertFalse(artifact["measurement"]["cuda_synchronized"])
            self.assertEqual(len(artifact["warmup"]["timing_records"]), 1)
            self.assertEqual(len(artifact["requests"]), 64)
            self.assertEqual(artifact["unmapped_timing_records"], [])

            finished = [item for item in artifact["requests"] if item["outcome"] == "finished"]
            incomplete = [
                item for item in artifact["requests"] if item["outcome"] == "incomplete"
            ]
            self.assertGreater(len(finished), 0)
            self.assertGreater(len(incomplete), 0)
            for item in incomplete:
                self.assertIsNone(item["timestamps_ns"]["completed"])

            paths = list(output_dir.glob("saturated-*-run3.json"))
            self.assertEqual(len(paths), 1)
            loaded = json.loads(paths[0].read_text(encoding="utf-8"))
            self.assertEqual(loaded["status"], "failed")
            self.assertTrue(paths[0].read_text(encoding="utf-8").endswith("\n"))

    def test_early_is_finished_rejects_success(self):
        self.engine = FakeEngine(
            self.recorder,
            events=self.events,
            measured_seq_ids=self.measured_seq_ids,
            pretend_finished=True,
        )
        artifact = self._run(raise_on_failure=False)
        self.assertEqual(artifact["status"], "failed")
        self.assertIn("successful terminal state", artifact["error"]["message"])
        self.assertIsNone(artifact["measurement"]["ended_ns"])
        self.assertFalse(artifact["measurement"]["cuda_synchronized"])
        self.assertEqual(len(artifact["requests"]), 64)
        incomplete = [
            item for item in artifact["requests"] if item["outcome"] == "incomplete"
        ]
        self.assertEqual(len(incomplete), 64)
        self.assertEqual(self.engine.step_count, 0)

    def test_writer_schema_filename_run_id_and_no_derived_fields(self):
        artifact = self._run()
        created = datetime(2026, 7, 22, 15, 30, 0, 123456, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            path = write_saturated_artifact(
                artifact,
                output_dir=Path(tmp),
                run_number=7,
                created_at=created,
            )
            self.assertEqual(path.name, "saturated-20260722T153000.123456Z-run7.json")
            text = path.read_text(encoding="utf-8")
            self.assertTrue(text.endswith("\n"))
            loaded = json.loads(text)
            self.assertEqual(loaded["run_id"], "test-run-id")
            self.assertEqual(loaded["run_number"], 3)
            self.assertIn("unmapped_timing_records", loaded)
            assert_no_derived_metric_fields(loaded)

    def test_verify_manifest_helper_matches_frozen_digest(self):
        digest = verify_manifest_fingerprint(self.workload)
        self.assertEqual(digest, EXPECTED_MANIFEST_SHA256)
        self.assertEqual(digest, workload_manifest_sha256(self.workload))

    def test_engine_factory_failure_writes_single_failed_artifact(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            fake_cuda = SimpleNamespace(
                is_available=lambda: False,
                manual_seed_all=lambda _seed: None,
                synchronize=lambda: None,
                get_device_name=lambda _idx: None,
            )
            fake_torch = SimpleNamespace(
                manual_seed=lambda _seed: None,
                cuda=fake_cuda,
                version=SimpleNamespace(cuda=None),
            )

            def runtime_loader():
                return SimpleNamespace(
                    torch=fake_torch,
                    LLM=object,
                    SamplingParams=lambda **kwargs: SimpleNamespace(**kwargs),
                    RequestTimingRecorder=RequestTimingRecorder,
                )

            def engine_factory(_runtime, _model_path, _recorder):
                raise RuntimeError("injected engine init failure")

            code = main(
                [
                    "--model",
                    str(Path(tmp) / "missing-model"),
                    "--run-number",
                    "9",
                    "--output-dir",
                    str(output_dir),
                ],
                runtime_loader=runtime_loader,
                engine_factory=engine_factory,
                created_at=datetime(2026, 7, 22, 16, 0, 0, tzinfo=timezone.utc),
                run_id="setup-fail-run",
            )
            self.assertEqual(code, 1)
            paths = list(output_dir.glob("saturated-*-run9.json"))
            self.assertEqual(len(paths), 1)
            loaded = json.loads(paths[0].read_text(encoding="utf-8"))
            self.assertEqual(loaded["status"], "failed")
            self.assertEqual(loaded["error"]["type"], "RuntimeError")
            self.assertIn("injected engine init failure", loaded["error"]["message"])
            self.assertEqual(loaded["run_id"], "setup-fail-run")
            self.assertEqual(loaded["workload"]["manifest_sha256"], EXPECTED_MANIFEST_SHA256)
            self.assertEqual(loaded["model"]["revision"], MODEL_REVISION)
            self.assertEqual(loaded["engine"]["max_model_len"], 4096)
            self.assertEqual(loaded["warmup"]["timing_records"], [])
            self.assertEqual(loaded["requests"], [])
            self.assertIsNone(loaded["measurement"]["ended_ns"])
            self.assertFalse(loaded["measurement"]["cuda_synchronized"])

    def test_cli_help_and_import_do_not_load_torch_in_fresh_subprocess(self):
        # Parent may already have torch (or a temporary fake); isolation is
        # proven only in a brand-new interpreter.
        previous_torch = sys.modules.get("torch")
        sys.modules["torch"] = SimpleNamespace(__name__="torch")
        try:
            self.assertIn("torch", sys.modules)
            namespace = parse_args([])
            self.assertEqual(namespace.run_number, 1)

            import_probe = textwrap.dedent(
                """
                import sys
                import research.stage2_saturated_driver as driver
                assert "torch" not in sys.modules, sorted(sys.modules)
                assert driver.SCHEMA_VERSION == 1
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
                [sys.executable, "research/stage2_saturated_driver.py", "--help"],
                check=False,
                capture_output=True,
                text=True,
                cwd=str(Path(__file__).resolve().parents[1]),
            )
            self.assertEqual(helped.returncode, 0, helped.stderr)
            self.assertIn("NSL-S2-SAT-v1", helped.stdout)
            self.assertNotIn("ModuleNotFoundError", helped.stderr)
            self.assertNotIn("torch", helped.stderr.lower())
        finally:
            if previous_torch is None:
                sys.modules.pop("torch", None)
            else:
                sys.modules["torch"] = previous_torch


if __name__ == "__main__":
    unittest.main()
