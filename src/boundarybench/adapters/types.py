"""Provider-neutral model adapter contracts.

The adapter layer intentionally separates model access from deterministic
grading. It records what evidence was actually observed and never assumes that
token log probabilities or full-category scores exist.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

AdapterMode = Literal[
    "open_weight_full_category",
    "token_top_k",
    "output_only",
    "local_surrogate_probe",
]

ExecutionStatus = Literal["completed", "mock_completed", "failed"]

EvidenceKind = Literal["full_category", "token_top_k", "output_only", "surrogate_probe"]


@dataclass(frozen=True)
class AdapterCapabilities:
    """Capabilities exposed by a model adapter implementation."""

    access_mode: AdapterMode
    supports_full_category_evidence: bool
    supports_token_top_k: bool
    supports_output_only: bool
    supports_surrogate_probe: bool
    requires_credentials: bool
    notes: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "access_mode": self.access_mode,
            "supports_full_category_evidence": self.supports_full_category_evidence,
            "supports_token_top_k": self.supports_token_top_k,
            "supports_output_only": self.supports_output_only,
            "supports_surrogate_probe": self.supports_surrogate_probe,
            "requires_credentials": self.requires_credentials,
            "notes": list(self.notes),
        }


@dataclass(frozen=True)
class RetryPolicy:
    """Bounded retry policy for transient model-access failures."""

    max_attempts: int = 3
    initial_delay_seconds: float = 0.25
    backoff_multiplier: float = 2.0
    max_delay_seconds: float = 2.0

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")
        if self.initial_delay_seconds < 0:
            raise ValueError("initial_delay_seconds must be >= 0")
        if self.backoff_multiplier < 1:
            raise ValueError("backoff_multiplier must be >= 1")
        if self.max_delay_seconds < 0:
            raise ValueError("max_delay_seconds must be >= 0")

    def as_dict(self) -> dict[str, Any]:
        return {
            "max_attempts": self.max_attempts,
            "initial_delay_seconds": self.initial_delay_seconds,
            "backoff_multiplier": self.backoff_multiplier,
            "max_delay_seconds": self.max_delay_seconds,
        }


@dataclass(frozen=True)
class AdapterConfig:
    """Configuration that is safe to hash and record.

    Do not put credential values in ``extra``. Store only non-secret names of
    environment variables, boolean capability flags, or public model/runtime
    configuration.
    """

    provider: str
    model_id: str
    access_mode: AdapterMode
    temperature: float = 0.0
    max_output_tokens: int = 512
    token_top_k: int | None = None
    timeout_seconds: float = 30.0
    extra: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "model_id": self.model_id,
            "access_mode": self.access_mode,
            "temperature": self.temperature,
            "max_output_tokens": self.max_output_tokens,
            "token_top_k": self.token_top_k,
            "timeout_seconds": self.timeout_seconds,
            "extra": self.extra,
        }


@dataclass(frozen=True)
class ModelRequest:
    """Provider-neutral generation request."""

    task_id: str
    prompt: str
    allowed_actions: tuple[str, ...]
    seed: int | None = None
    temperature: float = 0.0
    max_output_tokens: int = 512
    metadata: dict[str, Any] = field(default_factory=dict)
    schema_version: str = "boundarybench.model_request.v1"

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "task_id": self.task_id,
            "prompt": self.prompt,
            "allowed_actions": list(self.allowed_actions),
            "seed": self.seed,
            "temperature": self.temperature,
            "max_output_tokens": self.max_output_tokens,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class AdapterRawOutput:
    """Raw output returned by an adapter before common provenance is attached."""

    text: str
    parsed_json: dict[str, Any] | None = None
    category_evidence: dict[str, Any] | None = None
    token_top_k_evidence: dict[str, Any] | None = None
    surrogate_report: dict[str, Any] | None = None
    usage: dict[str, Any] | None = None
    external_request_id: str | None = None
    cost_usd: float | None = None
    errors: tuple[str, ...] = ()


@dataclass(frozen=True)
class ModelResponse:
    """Provider-neutral model response plus provenance."""

    request: ModelRequest
    text: str
    provenance: dict[str, Any]
    parsed_json: dict[str, Any] | None = None
    category_evidence: dict[str, Any] | None = None
    token_top_k_evidence: dict[str, Any] | None = None
    surrogate_report: dict[str, Any] | None = None
    errors: tuple[str, ...] = ()
    schema_version: str = "boundarybench.model_response.v1"

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "schema_version": self.schema_version,
            "request": self.request.as_dict(),
            "text": self.text,
            "parsed_json": self.parsed_json,
            "category_evidence": self.category_evidence,
            "token_top_k_evidence": self.token_top_k_evidence,
            "surrogate_report": self.surrogate_report,
            "provenance": self.provenance,
            "errors": list(self.errors),
        }
        return out


class AdapterError(RuntimeError):
    """Base exception for adapter failures."""


class TransientAdapterError(AdapterError):
    """Exception type that can be retried under ``RetryPolicy``."""

