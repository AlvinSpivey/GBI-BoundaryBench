"""Retry utilities for model adapters."""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

from boundarybench.adapters.types import RetryPolicy, TransientAdapterError

T = TypeVar("T")


def run_with_retries(
    operation: Callable[[], T],
    policy: RetryPolicy,
    sleeper: Callable[[float], None] | None = None,
) -> tuple[T, int]:
    """Run ``operation`` with bounded retries for transient adapter failures."""

    delay = policy.initial_delay_seconds
    attempt = 1
    while True:
        try:
            return operation(), attempt
        except TransientAdapterError:
            if attempt >= policy.max_attempts:
                raise
            if sleeper is not None and delay > 0:
                sleeper(min(delay, policy.max_delay_seconds))
            delay = min(delay * policy.backoff_multiplier, policy.max_delay_seconds)
            attempt += 1

