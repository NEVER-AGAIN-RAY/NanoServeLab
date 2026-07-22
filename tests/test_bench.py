import contextlib
import io
import unittest
from unittest import mock

import bench


class SamplingSeedTest(unittest.TestCase):
    def test_set_sampling_seed_calls_cpu_and_cuda_rng(self):
        fake_torch = mock.Mock()
        fake_torch.cuda.is_available.return_value = True
        bench.set_sampling_seed(fake_torch, 7)
        fake_torch.manual_seed.assert_called_once_with(7)
        fake_torch.cuda.manual_seed_all.assert_called_once_with(7)
        fake_torch.cuda.is_available.assert_called_once_with()

    def test_set_sampling_seed_skips_cuda_when_unavailable(self):
        fake_torch = mock.Mock()
        fake_torch.cuda.is_available.return_value = False
        bench.set_sampling_seed(fake_torch, 3)
        fake_torch.manual_seed.assert_called_once_with(3)
        fake_torch.cuda.manual_seed_all.assert_not_called()

    def test_cli_default_sampling_seed_is_zero(self):
        args = bench.parse_args(["--model-revision", "rev"])
        self.assertEqual(args.sampling_seed, 0)
        self.assertEqual(args.seed, 0)

    def test_cli_explicit_sampling_seed_overrides_default(self):
        args = bench.parse_args(
            ["--model-revision", "rev", "--sampling-seed", "123"]
        )
        self.assertEqual(args.sampling_seed, 123)


class BenchmarkContractTest(unittest.TestCase):
    def test_workload_is_deterministic_and_respects_bounds(self):
        kwargs = {
            "random_seed": 0,
            "num_seqs": 4,
            "min_input_len": 2,
            "max_input_len": 5,
            "min_output_len": 3,
            "max_output_len": 7,
            "max_token_id": 11,
        }

        first = bench.build_workload(**kwargs)
        second = bench.build_workload(**kwargs)

        self.assertEqual(first, second)
        prompts, output_lengths = first
        self.assertEqual(
            first,
            (
                [[6, 0, 4, 8, 7], [4, 7, 5, 9, 3], [4, 2, 1], [8, 11, 9, 2]],
                [5, 3, 3, 5],
            ),
        )
        self.assertEqual(len(prompts), kwargs["num_seqs"])
        self.assertTrue(all(2 <= len(prompt) <= 5 for prompt in prompts))
        self.assertTrue(all(0 <= token <= 11 for prompt in prompts for token in prompt))
        self.assertTrue(all(3 <= length <= 7 for length in output_lengths))

    def test_different_seed_changes_workload(self):
        common = {
            "num_seqs": 4,
            "min_input_len": 2,
            "max_input_len": 5,
            "min_output_len": 3,
            "max_output_len": 7,
            "max_token_id": 11,
        }

        self.assertNotEqual(
            bench.build_workload(random_seed=0, **common),
            bench.build_workload(random_seed=1, **common),
        )

    def test_cli_rejects_context_overflow(self):
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                bench.parse_args(
                    [
                        "--model-revision",
                        "test-revision",
                        "--max-input-len",
                        "1024",
                        "--max-output-len",
                        "1024",
                        "--max-model-len",
                        "1024",
                    ]
                )


if __name__ == "__main__":
    unittest.main()
