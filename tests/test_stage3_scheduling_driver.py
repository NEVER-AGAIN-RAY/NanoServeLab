"""CPU contract tests for the NSL-S3-SCHED-v1 scheduling driver."""

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
from unittest.mock import patch

from nanovllm.engine.request_timing import RequestTimingRecorder
from nanovllm.engine.scheduling_policy import FCFS_POLICY, PROMPT_LENGTH_POLICY
from research.stage2_workload import (
    EXPECTED_MANIFEST_SHA256,
    REQUEST_COUNT,
    WORKLOAD_ID,
    build_saturated_mixed_workload,
)
from research.stage3_scheduling_driver import (
    EXPERIMENT_CONTRACT,
    MODEL_REVISION,
    SCHEMA_VERSION,
    Stage3SchedulingDriverError,
    _default_engine_factory,
    main,
    parse_args,
    policy_metadata,
    run_stage3_scheduling_admission,
    validate_comparison_group,
    write_stage3_scheduling_artifact,
)


class FakeClock:
    def __init__(self):
        self.now = 1_000_000

    def __call__(self) -> int:
        value = self.now
        self.now += 1_000
        return value


@dataclass
class FakeRequest:
    seq_id: int
    max_tokens: int
    output_tokens: int = 0
    finished: bool = False


class FakeEngine:
    def __init__(
        self,
        recorder: RequestTimingRecorder,
        *,
        policy: str,
        fail_after_steps: int | None = None,
    ):
        self.recorder = recorder
        self.scheduler = SimpleNamespace(scheduling_policy=policy)
        self.fail_after_steps = fail_after_steps
        self.generate_count = 0
        self.add_count = 0
        self.step_count = 0
        self.pending: list[FakeRequest] = []

    def generate(self, prompts, sampling_params):
        self.generate_count += 1
        self.recorder.record_arrival(10_000, 2)
        self.recorder.record_first_scheduled(10_000)
        self.recorder.record_output_token(10_000, 1)
        self.recorder.record_completed(10_000, 1)
        return [{"text": "warmup"}]

    def add_request(self, prompt, sampling_params):
        seq_id = 100 + self.add_count * 3
        self.add_count += 1
        self.recorder.record_arrival(seq_id, len(prompt))
        self.pending.append(FakeRequest(seq_id, sampling_params.max_tokens))

    def step(self):
        self.step_count += 1
        if self.fail_after_steps is not None and self.step_count > self.fail_after_steps:
            raise RuntimeError("injected Stage 3 step failure")
        request = next(item for item in self.pending if not item.finished)
        self.recorder.record_first_scheduled(request.seq_id)
        while request.output_tokens < request.max_tokens:
            request.output_tokens += 1
            self.recorder.record_output_token(request.seq_id, request.output_tokens)
        self.recorder.record_completed(request.seq_id, request.output_tokens)
        request.finished = True
        return [], 0

    def is_finished(self):
        return bool(self.pending) and all(item.finished for item in self.pending)


class Stage3SchedulingDriverTest(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.recorder = RequestTimingRecorder(clock_ns=self.clock)
        self.workload = build_saturated_mixed_workload()
        self.created = datetime(2026, 7, 26, 12, 0, 0, tzinfo=timezone.utc)

    @staticmethod
    def _sampling_params(max_tokens: int):
        return SimpleNamespace(
            max_tokens=max_tokens,
            temperature=0.6,
            ignore_eos=True,
        )

    def _run(self, policy: str = FCFS_POLICY, **overrides):
        engine = overrides.pop(
            "engine",
            FakeEngine(self.recorder, policy=policy),
        )
        kwargs = dict(
            engine=engine,
            recorder=self.recorder,
            policy=policy,
            comparison_group="prompt-length-20260726-a",
            sampling_params_factory=self._sampling_params,
            warmup_sampling_params=self._sampling_params(64),
            clock_ns=self.clock,
            requests=self.workload,
            run_number=2,
            run_id="stage3-test-run",
            created_at=self.created,
            repository={"commit": "deadbeef", "branch": "test", "dirty": False},
            environment={"python": "test"},
            model={"id": "Qwen/Qwen3-0.6B", "revision": MODEL_REVISION},
            engine_metadata={"max_model_len": 4096},
            raise_on_failure=True,
        )
        kwargs.update(overrides)
        return run_stage3_scheduling_admission(**kwargs)

    def test_success_artifact_has_independent_stage3_identity(self):
        artifact = self._run()

        self.assertEqual(artifact["schema_version"], SCHEMA_VERSION)
        self.assertEqual(artifact["experiment"], EXPERIMENT_CONTRACT)
        self.assertEqual(artifact["experiment_contract"], EXPERIMENT_CONTRACT)
        self.assertEqual(
            artifact["comparison_group"],
            "prompt-length-20260726-a",
        )
        self.assertEqual(
            artifact["policy"],
            {
                "id": FCFS_POLICY,
                "definition_version": 1,
                "parameters": {},
                "runtime_verified": True,
            },
        )
        self.assertEqual(artifact["workload"]["id"], WORKLOAD_ID)
        self.assertEqual(
            artifact["workload"]["manifest_sha256"],
            EXPECTED_MANIFEST_SHA256,
        )
        self.assertEqual(
            artifact["engine"]["requested_scheduling_policy"],
            FCFS_POLICY,
        )
        self.assertEqual(artifact["engine"]["scheduling_policy"], FCFS_POLICY)
        self.assertEqual(len(artifact["requests"]), REQUEST_COUNT)
        self.assertEqual(artifact["status"], "finished")

    def test_prompt_length_policy_metadata_is_exact(self):
        artifact = self._run(policy=PROMPT_LENGTH_POLICY)
        self.assertEqual(
            artifact["policy"],
            {
                "id": PROMPT_LENGTH_POLICY,
                "definition_version": 1,
                "parameters": {
                    "fresh_request_key": "num_prompt_tokens",
                    "order": "ascending",
                    "stable_ties": "arrival_order",
                    "recovery_prefix": "preserved",
                },
                "runtime_verified": True,
            },
        )
        self.assertEqual(
            policy_metadata(PROMPT_LENGTH_POLICY, runtime_verified=True),
            artifact["policy"],
        )

    def test_runtime_policy_mismatch_fails_before_warmup(self):
        engine = FakeEngine(self.recorder, policy=PROMPT_LENGTH_POLICY)
        artifact = self._run(
            policy=FCFS_POLICY,
            engine=engine,
            raise_on_failure=False,
        )

        self.assertEqual(artifact["status"], "failed")
        self.assertEqual(artifact["error"]["type"], "Stage3SchedulingDriverError")
        self.assertIn("does not match", artifact["error"]["message"])
        self.assertFalse(artifact["policy"]["runtime_verified"])
        self.assertIsNone(artifact["engine"]["scheduling_policy"])
        self.assertEqual(engine.generate_count, 0)
        self.assertEqual(engine.add_count, 0)

    def test_missing_or_dirty_repository_fails_before_warmup(self):
        for repository in (
            {},
            {"commit": "deadbeef", "branch": "test", "dirty": True},
            {"commit": "deadbeef", "branch": "test", "dirty": None},
        ):
            with self.subTest(repository=repository):
                recorder = RequestTimingRecorder(clock_ns=FakeClock())
                engine = FakeEngine(recorder, policy=FCFS_POLICY)
                artifact = run_stage3_scheduling_admission(
                    engine=engine,
                    recorder=recorder,
                    policy=FCFS_POLICY,
                    comparison_group="group-a",
                    sampling_params_factory=self._sampling_params,
                    warmup_sampling_params=self._sampling_params(64),
                    requests=self.workload,
                    repository=repository,
                    raise_on_failure=False,
                )
                self.assertEqual(artifact["status"], "failed")
                self.assertEqual(engine.generate_count, 0)

    def test_stage2_runtime_failure_keeps_stage3_identity(self):
        engine = FakeEngine(
            self.recorder,
            policy=FCFS_POLICY,
            fail_after_steps=1,
        )
        artifact = self._run(engine=engine, raise_on_failure=False)
        self.assertEqual(artifact["status"], "failed")
        self.assertEqual(artifact["schema_version"], 2)
        self.assertEqual(artifact["experiment_contract"], EXPERIMENT_CONTRACT)
        self.assertTrue(artifact["policy"]["runtime_verified"])
        self.assertEqual(artifact["error"]["type"], "RuntimeError")
        self.assertIsNone(artifact["measurement"]["ended_ns"])
        self.assertEqual(len(artifact["requests"]), REQUEST_COUNT)

    def test_raise_on_failure_reports_stage2_runtime_failure(self):
        engine = FakeEngine(
            self.recorder,
            policy=FCFS_POLICY,
            fail_after_steps=1,
        )
        with self.assertRaises(Stage3SchedulingDriverError) as ctx:
            self._run(engine=engine)
        self.assertIn("injected Stage 3 step failure", str(ctx.exception))

    def test_writer_is_exclusive_and_preserves_existing_bytes(self):
        artifact = self._run()
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            path = write_stage3_scheduling_artifact(
                artifact,
                output_dir=output_dir,
                comparison_group=artifact["comparison_group"],
                policy=FCFS_POLICY,
                run_number=2,
                created_at=self.created,
            )
            original = path.read_bytes()
            self.assertTrue(original.endswith(b"\n"))
            loaded = json.loads(original)
            self.assertEqual(loaded["schema_version"], 2)
            with self.assertRaises(FileExistsError):
                write_stage3_scheduling_artifact(
                    artifact,
                    output_dir=output_dir,
                    comparison_group=artifact["comparison_group"],
                    policy=FCFS_POLICY,
                    run_number=2,
                    created_at=self.created,
                )
            self.assertEqual(path.read_bytes(), original)

    def test_writer_rejects_filename_identity_mismatch(self):
        artifact = self._run()
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            for overrides in (
                {"comparison_group": "different-group"},
                {"policy": PROMPT_LENGTH_POLICY},
                {"run_number": 3},
            ):
                kwargs = {
                    "output_dir": output_dir,
                    "comparison_group": artifact["comparison_group"],
                    "policy": FCFS_POLICY,
                    "run_number": 2,
                    "created_at": self.created,
                }
                kwargs.update(overrides)
                with self.subTest(overrides=overrides):
                    with self.assertRaises(ValueError):
                        write_stage3_scheduling_artifact(artifact, **kwargs)
            self.assertEqual(list(output_dir.iterdir()), [])

    def test_engine_factory_forwards_requested_policy(self):
        calls: list[tuple[tuple, dict]] = []

        class FakeLLM:
            def __init__(self, *args, **kwargs):
                calls.append((args, kwargs))

        runtime = SimpleNamespace(LLM=FakeLLM)
        _default_engine_factory(
            runtime,
            "/model",
            self.recorder,
            PROMPT_LENGTH_POLICY,
        )
        self.assertEqual(calls[0][0], ("/model",))
        self.assertIs(calls[0][1]["timing_recorder"], self.recorder)
        self.assertEqual(
            calls[0][1]["scheduling_policy"],
            PROMPT_LENGTH_POLICY,
        )

    def test_cli_requires_explicit_policy_group_and_run_number(self):
        args = parse_args(
            [
                "--policy",
                FCFS_POLICY,
                "--comparison-group",
                "group.a-1",
                "--run-number",
                "3",
            ]
        )
        self.assertEqual(args.policy, FCFS_POLICY)
        self.assertEqual(args.comparison_group, "group.a-1")
        self.assertEqual(args.run_number, 3)
        with self.assertRaises(SystemExit):
            parse_args([])
        with self.assertRaises(SystemExit):
            parse_args(
                [
                    "--policy",
                    FCFS_POLICY,
                    "--comparison-group",
                    "../escape",
                    "--run-number",
                    "1",
                ]
            )
        with self.assertRaises(SystemExit):
            parse_args(
                [
                    "--policy",
                    FCFS_POLICY,
                    "--comparison-group",
                    "group",
                    "--run-number",
                    "0",
                ]
            )

    def test_main_setup_failure_writes_one_stage3_artifact(self):
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
                SamplingParams=lambda **kwargs: SimpleNamespace(**kwargs),
                RequestTimingRecorder=RequestTimingRecorder,
            )

        def engine_factory(_runtime, _model_path, _recorder, policy):
            self.assertEqual(policy, PROMPT_LENGTH_POLICY)
            raise RuntimeError("injected Stage 3 engine setup failure")

        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            with patch(
                "research.stage3_scheduling_driver.git_metadata",
                return_value={
                    "commit": "deadbeef",
                    "branch": "test",
                    "dirty": False,
                },
            ):
                code = main(
                    [
                        "--model",
                        str(output_dir / "model"),
                        "--policy",
                        PROMPT_LENGTH_POLICY,
                        "--comparison-group",
                        "setup-failure-group",
                        "--run-number",
                        "1",
                        "--output-dir",
                        str(output_dir),
                    ],
                    runtime_loader=runtime_loader,
                    engine_factory=engine_factory,
                    created_at=self.created,
                    run_id="setup-failure-run",
                )
            self.assertEqual(code, 1)
            paths = list(output_dir.glob("scheduling-*.json"))
            self.assertEqual(len(paths), 1)
            artifact = json.loads(paths[0].read_text(encoding="utf-8"))
            self.assertEqual(artifact["schema_version"], 2)
            self.assertEqual(artifact["experiment_contract"], EXPERIMENT_CONTRACT)
            self.assertEqual(artifact["status"], "failed")
            self.assertEqual(artifact["error"]["type"], "RuntimeError")
            self.assertFalse(artifact["policy"]["runtime_verified"])
            self.assertEqual(artifact["requests"], [])

    def test_group_validator_and_fresh_import_are_strict_and_mac_safe(self):
        self.assertEqual(validate_comparison_group("A.1_test-x"), "A.1_test-x")
        for value in ("", ".hidden", "/tmp", "a/b", "a b", "a" * 129):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    validate_comparison_group(value)

        probe = textwrap.dedent(
            """
            import sys
            import research.stage3_scheduling_driver as driver
            assert "torch" not in sys.modules, sorted(sys.modules)
            assert driver.SCHEMA_VERSION == 2
            print("stage3-import-ok")
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
        self.assertIn("stage3-import-ok", imported.stdout)

        helped = subprocess.run(
            [sys.executable, "research/stage3_scheduling_driver.py", "--help"],
            check=False,
            capture_output=True,
            text=True,
            cwd=str(Path(__file__).resolve().parents[1]),
        )
        self.assertEqual(helped.returncode, 0, helped.stderr)
        self.assertIn(EXPERIMENT_CONTRACT, helped.stdout)
        self.assertNotIn("torch", helped.stderr.lower())


if __name__ == "__main__":
    unittest.main()
