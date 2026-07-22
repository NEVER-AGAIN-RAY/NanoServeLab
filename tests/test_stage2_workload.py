"""Deterministic CPU tests for the fixed stage-2 saturated workload."""

import unittest
from dataclasses import FrozenInstanceError

from research.stage2_workload import (
    CLASS_PATTERN,
    EXPECTED_MANIFEST_SHA256,
    LONG_OUTPUT_TOKENS,
    LONG_PROMPT_TOKENS,
    LONG_REQUESTS,
    MAX_TOKEN_ID,
    REQUEST_COUNT,
    SHORT_OUTPUT_TOKENS,
    SHORT_PROMPT_TOKENS,
    SHORT_REQUESTS,
    build_saturated_mixed_workload,
    workload_manifest_sha256,
)


class Stage2SaturatedWorkloadTest(unittest.TestCase):

    def test_exact_counts_and_interleaved_order(self):
        requests = build_saturated_mixed_workload()

        self.assertEqual(len(requests), REQUEST_COUNT)
        classes = tuple(request.request_class for request in requests)
        self.assertEqual(classes, CLASS_PATTERN * 16)
        self.assertEqual(classes.count("short"), SHORT_REQUESTS)
        self.assertEqual(classes.count("long"), LONG_REQUESTS)
        self.assertEqual(
            tuple(request.request_index for request in requests),
            tuple(range(REQUEST_COUNT)),
        )

    def test_class_lengths_token_bounds_and_totals(self):
        requests = build_saturated_mixed_workload()

        for request in requests:
            if request.request_class == "short":
                self.assertEqual(len(request.prompt_token_ids), SHORT_PROMPT_TOKENS)
                self.assertEqual(request.max_tokens, SHORT_OUTPUT_TOKENS)
            else:
                self.assertEqual(len(request.prompt_token_ids), LONG_PROMPT_TOKENS)
                self.assertEqual(request.max_tokens, LONG_OUTPUT_TOKENS)
            self.assertTrue(
                all(
                    0 <= token_id <= MAX_TOKEN_ID
                    for token_id in request.prompt_token_ids
                )
            )

        self.assertEqual(
            sum(len(request.prompt_token_ids) for request in requests),
            22_528,
        )
        self.assertEqual(sum(request.max_tokens for request in requests), 5_632)
        self.assertEqual(
            max(
                len(request.prompt_token_ids) + request.max_tokens
                for request in requests
            ),
            1_280,
        )

    def test_manifest_is_deterministic_immutable_and_fingerprinted(self):
        first = build_saturated_mixed_workload()
        second = build_saturated_mixed_workload()

        self.assertEqual(first, second)
        self.assertIsNot(first, second)
        self.assertEqual(workload_manifest_sha256(first), EXPECTED_MANIFEST_SHA256)
        with self.assertRaises(TypeError):
            first[0] = first[1]
        with self.assertRaises(FrozenInstanceError):
            first[0].max_tokens = 1


if __name__ == "__main__":
    unittest.main()
