"""Deterministic stage-2 saturated mixed workload definition.

The workload is deliberately separate from ``bench.py``: the latter remains the
stage-1 upstream-shaped throughput baseline.  This module only constructs an
immutable request manifest; it does not load a model, admit requests, measure
time, aggregate metrics, or write result files.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import random
from typing import Literal


RequestClass = Literal["short", "long"]

WORKLOAD_ID = "NSL-S2-SAT-v1"
WORKLOAD_SEED = 0
MAX_TOKEN_ID = 10_000
CLASS_PATTERN: tuple[RequestClass, ...] = ("short", "long", "short", "short")
PATTERN_REPETITIONS = 16
SHORT_REQUESTS = CLASS_PATTERN.count("short") * PATTERN_REPETITIONS
LONG_REQUESTS = CLASS_PATTERN.count("long") * PATTERN_REPETITIONS
REQUEST_COUNT = SHORT_REQUESTS + LONG_REQUESTS
SHORT_PROMPT_TOKENS = 128
SHORT_OUTPUT_TOKENS = 32
LONG_PROMPT_TOKENS = 1_024
LONG_OUTPUT_TOKENS = 256
EXPECTED_MANIFEST_SHA256 = (
    "aa1d4e345e0e9f599bd43093bd5b9214476aa3145ee910cc9137d0b62754767d"
)


@dataclass(frozen=True, slots=True)
class SaturatedRequest:
    """One immutable request in the fixed stage-2 manifest."""

    request_index: int
    request_class: RequestClass
    prompt_token_ids: tuple[int, ...]
    max_tokens: int


def build_saturated_mixed_workload() -> tuple[SaturatedRequest, ...]:
    """Return the exact ``NSL-S2-SAT-v1`` request order and token contents."""
    rng = random.Random(WORKLOAD_SEED)
    request_classes = CLASS_PATTERN * PATTERN_REPETITIONS
    requests = []
    for request_index, request_class in enumerate(request_classes):
        if request_class == "short":
            prompt_tokens = SHORT_PROMPT_TOKENS
            max_tokens = SHORT_OUTPUT_TOKENS
        else:
            prompt_tokens = LONG_PROMPT_TOKENS
            max_tokens = LONG_OUTPUT_TOKENS
        prompt_token_ids = tuple(
            rng.randint(0, MAX_TOKEN_ID) for _ in range(prompt_tokens)
        )
        requests.append(
            SaturatedRequest(
                request_index=request_index,
                request_class=request_class,
                prompt_token_ids=prompt_token_ids,
                max_tokens=max_tokens,
            )
        )
    return tuple(requests)


def workload_manifest_sha256(requests: tuple[SaturatedRequest, ...]) -> str:
    """Hash the canonical JSON manifest used to verify future experiment runs."""
    manifest = [
        {
            "request_index": request.request_index,
            "request_class": request.request_class,
            "prompt_token_ids": request.prompt_token_ids,
            "max_tokens": request.max_tokens,
        }
        for request in requests
    ]
    canonical = json.dumps(
        manifest,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()
