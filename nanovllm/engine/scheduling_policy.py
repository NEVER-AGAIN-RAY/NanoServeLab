"""Versioned Scheduler policy identities used by Stage 3 experiments."""

from __future__ import annotations


FCFS_POLICY = "fcfs-v1"
SUPPORTED_SCHEDULING_POLICIES = (FCFS_POLICY,)


def normalize_scheduling_policy(policy: str) -> str:
    """Return a supported canonical policy ID or reject the configuration."""
    if not isinstance(policy, str) or policy not in SUPPORTED_SCHEDULING_POLICIES:
        supported = ", ".join(SUPPORTED_SCHEDULING_POLICIES)
        raise ValueError(
            f"unsupported scheduling_policy {policy!r}; expected one of: {supported}"
        )
    return policy
