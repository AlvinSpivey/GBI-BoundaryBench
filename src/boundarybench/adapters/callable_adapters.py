"""Callable-backed adapter implementations.

These adapters are the provider-neutral integration seam for real runtimes.
They do not know about any specific provider SDK and do not read credentials.
Callers provide functions that execute a local model, SDK call, or HTTP call.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from boundarybench.adapters.base import BaseAdapter
from boundarybench.adapters.evidence import (
    full_category_evidence,
    no_full_category_evidence,
    no_token_top_k_evidence,
    token_top_k_evidence,
)
from boundarybench.adapters.types import AdapterCapabilities, AdapterConfig, AdapterRawOutput, ModelRequest

GenerationFn = Callable[[ModelRequest], tuple[str, dict[str, Any] | None]]
CategoryScoreFn = Callable[[ModelRequest, str], dict[str, float] | None]
TokenTopKFn = Callable[[ModelRequest, str], list[dict[str, Any]] | None]


class CallableOpenWeightFullCategoryAdapter(BaseAdapter):
    """Open-weight mode with full action/category evidence when exposed."""

    def __init__(
        self,
        *,
        provider: str,
        model_id: str,
        generate_fn: GenerationFn,
        category_score_fn: CategoryScoreFn,
        is_mock: bool = False,
    ) -> None:
        super().__init__(
            AdapterConfig(
                provider=provider,
                model_id=model_id,
                access_mode="open_weight_full_category",
                extra={"credential_env_vars": [], "callable_adapter": True},
            ),
            is_mock=is_mock,
        )
        self._generate_fn = generate_fn
        self._category_score_fn = category_score_fn

    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            access_mode="open_weight_full_category",
            supports_full_category_evidence=True,
            supports_token_top_k=False,
            supports_output_only=True,
            supports_surrogate_probe=False,
            requires_credentials=False,
            notes=("Requires supplied runtime callable to expose full action/category scores.",),
        )

    def _generate_once(self, request: ModelRequest) -> AdapterRawOutput:
        text, parsed = self._generate_fn(request)
        scores = self._category_score_fn(request, text)
        if scores is None:
            return AdapterRawOutput(
                text=text,
                parsed_json=parsed,
                category_evidence=no_full_category_evidence("runtime did not expose full category scores"),
                token_top_k_evidence=no_token_top_k_evidence("full-category callable adapter did not request token top-k"),
                errors=("missing_full_category_evidence",),
            )
        missing = sorted(set(request.allowed_actions) - set(scores))
        extra = sorted(set(scores) - set(request.allowed_actions))
        if missing or extra:
            return AdapterRawOutput(
                text=text,
                parsed_json=parsed,
                category_evidence=no_full_category_evidence("category scores did not match allowed actions"),
                token_top_k_evidence=no_token_top_k_evidence("full-category callable adapter did not request token top-k"),
                errors=(f"category_score_mismatch:missing={missing}:extra={extra}",),
            )
        return AdapterRawOutput(
            text=text,
            parsed_json=parsed,
            category_evidence=full_category_evidence(
                scores={action: float(scores[action]) for action in request.allowed_actions},
                score_type="logit",
                source="runtime_callable",
                note="Full action/category scores supplied by the runtime callable.",
            ),
            token_top_k_evidence=no_token_top_k_evidence("full-category callable adapter did not request token top-k"),
        )


class CallableTokenTopKAdapter(BaseAdapter):
    """Mode for providers/runtimes that may return token top-k evidence."""

    def __init__(
        self,
        *,
        provider: str,
        model_id: str,
        generate_fn: GenerationFn,
        token_top_k_fn: TokenTopKFn,
        top_k: int,
        is_mock: bool = False,
    ) -> None:
        super().__init__(
            AdapterConfig(
                provider=provider,
                model_id=model_id,
                access_mode="token_top_k",
                token_top_k=top_k,
                extra={"credential_env_vars": [], "callable_adapter": True},
            ),
            is_mock=is_mock,
        )
        self._generate_fn = generate_fn
        self._token_top_k_fn = token_top_k_fn
        self._top_k = top_k

    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            access_mode="token_top_k",
            supports_full_category_evidence=False,
            supports_token_top_k=True,
            supports_output_only=True,
            supports_surrogate_probe=False,
            requires_credentials=False,
            notes=("Records top-k only when the supplied runtime callable returns it.",),
        )

    def _generate_once(self, request: ModelRequest) -> AdapterRawOutput:
        text, parsed = self._generate_fn(request)
        positions = self._token_top_k_fn(request, text)
        if positions is None:
            top_k = no_token_top_k_evidence("runtime did not return token top-k logprobs")
        else:
            top_k = token_top_k_evidence(
                positions=positions,
                top_k=self._top_k,
                source="runtime_callable",
                note="Visible token top-k mass is recorded without renormalization.",
            )
        return AdapterRawOutput(
            text=text,
            parsed_json=parsed,
            category_evidence=no_full_category_evidence("token-top-k mode does not expose full category scores"),
            token_top_k_evidence=top_k,
        )


class CallableOutputOnlyAdapter(BaseAdapter):
    """Output-only mode for providers/runtimes that expose text only."""

    def __init__(
        self,
        *,
        provider: str,
        model_id: str,
        generate_fn: GenerationFn,
        is_mock: bool = False,
    ) -> None:
        super().__init__(
            AdapterConfig(
                provider=provider,
                model_id=model_id,
                access_mode="output_only",
                extra={"credential_env_vars": [], "callable_adapter": True},
            ),
            is_mock=is_mock,
        )
        self._generate_fn = generate_fn

    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            access_mode="output_only",
            supports_full_category_evidence=False,
            supports_token_top_k=False,
            supports_output_only=True,
            supports_surrogate_probe=False,
            requires_credentials=False,
            notes=("No logits, category scores, or token top-k evidence are assumed.",),
        )

    def _generate_once(self, request: ModelRequest) -> AdapterRawOutput:
        text, parsed = self._generate_fn(request)
        return AdapterRawOutput(
            text=text,
            parsed_json=parsed,
            category_evidence=no_full_category_evidence("output-only runtime exposed no logits or category scores"),
            token_top_k_evidence=no_token_top_k_evidence("output-only runtime exposed no token logprobs"),
        )

