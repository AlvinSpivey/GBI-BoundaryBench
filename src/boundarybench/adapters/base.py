"""Base classes for provider-neutral model adapters."""

from __future__ import annotations

from collections.abc import Callable
from time import perf_counter
from typing import Protocol

from boundarybench.adapters.provenance import capture_provenance
from boundarybench.adapters.retry import run_with_retries
from boundarybench.adapters.types import (
    AdapterCapabilities,
    AdapterConfig,
    AdapterRawOutput,
    ModelRequest,
    ModelResponse,
    RetryPolicy,
)


class ModelAdapter(Protocol):
    """Provider-neutral adapter protocol."""

    config: AdapterConfig
    retry_policy: RetryPolicy

    def capabilities(self) -> AdapterCapabilities:
        """Return declared adapter capabilities."""

    def generate(self, request: ModelRequest) -> ModelResponse:
        """Generate a model response for ``request``."""


class BaseAdapter:
    """Shared provenance/retry wrapper for adapters."""

    def __init__(
        self,
        config: AdapterConfig,
        *,
        retry_policy: RetryPolicy | None = None,
        is_mock: bool = False,
        sleeper: Callable[[float], None] | None = None,
    ) -> None:
        self.config = config
        self.retry_policy = retry_policy or RetryPolicy()
        self.is_mock = is_mock
        self._sleeper = sleeper

    def capabilities(self) -> AdapterCapabilities:
        raise NotImplementedError

    def _generate_once(self, request: ModelRequest) -> AdapterRawOutput:
        raise NotImplementedError

    def generate(self, request: ModelRequest) -> ModelResponse:
        start = perf_counter()
        execution_status = "mock_completed" if self.is_mock else "completed"
        try:
            raw, attempt_count = run_with_retries(
                lambda: self._generate_once(request),
                self.retry_policy,
                sleeper=self._sleeper,
            )
        except Exception as exc:
            latency_ms = (perf_counter() - start) * 1000.0
            provenance = capture_provenance(
                request=request,
                config=self.config,
                adapter_class=self.__class__.__name__,
                retry_policy=self.retry_policy,
                attempt_count=self.retry_policy.max_attempts,
                latency_ms=latency_ms,
                is_mock=self.is_mock,
                execution_status="failed",
                full_category_evidence_observed=False,
                token_top_k_evidence_observed=False,
                output_text_observed=False,
            )
            return ModelResponse(
                request=request,
                text="",
                parsed_json=None,
                category_evidence=None,
                token_top_k_evidence=None,
                surrogate_report=None,
                provenance=provenance,
                errors=(f"{exc.__class__.__name__}:{exc}",),
            )
        latency_ms = (perf_counter() - start) * 1000.0
        provenance = capture_provenance(
            request=request,
            config=self.config,
            adapter_class=self.__class__.__name__,
            retry_policy=self.retry_policy,
            attempt_count=attempt_count,
            latency_ms=latency_ms,
            is_mock=self.is_mock,
            execution_status=execution_status,
            full_category_evidence_observed=bool(
                raw.category_evidence and raw.category_evidence.get("observed") is True
            ),
            token_top_k_evidence_observed=bool(
                raw.token_top_k_evidence and raw.token_top_k_evidence.get("observed") is True
            ),
            output_text_observed=bool(raw.text),
            external_request_id=raw.external_request_id,
            usage=raw.usage,
            cost_usd=raw.cost_usd,
        )
        return ModelResponse(
            request=request,
            text=raw.text,
            parsed_json=raw.parsed_json,
            category_evidence=raw.category_evidence,
            token_top_k_evidence=raw.token_top_k_evidence,
            surrogate_report=raw.surrogate_report,
            provenance=provenance,
            errors=raw.errors,
        )

