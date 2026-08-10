"""Offline adapter implementations for tests and local smoke checks.

These classes do not call external services and must not be reported as real
model/provider runs. Their provenance records set ``is_mock: true`` and
``execution_status: mock_completed``.
"""

from __future__ import annotations

import json
from math import log
from typing import Any

from boundarybench.adapters.base import BaseAdapter
from boundarybench.adapters.evidence import (
    full_category_evidence,
    no_full_category_evidence,
    no_token_top_k_evidence,
    token_top_k_evidence,
)
from boundarybench.adapters.types import AdapterCapabilities, AdapterConfig, AdapterRawOutput, ModelRequest


def _default_result(request: ModelRequest, action: str, answer: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "schema_version": "boundarybench.result.v1",
        "task_id": request.task_id,
        "action": action,
        "answer": answer or {"adapter_mode": "offline_mock"},
        "evidence_refs": list(request.metadata.get("mock_evidence_refs", [])),
        "confidence": 0.0,
    }


def _mock_action(request: ModelRequest) -> str:
    requested = request.metadata.get("mock_action")
    if isinstance(requested, str) and requested in request.allowed_actions:
        return requested
    if "abstain" in request.allowed_actions:
        return "abstain"
    return request.allowed_actions[0]


class OfflineOpenWeightFullCategoryAdapter(BaseAdapter):
    """Offline stand-in for an open-weight runtime with full action scores."""

    def __init__(self, *, model_id: str = "offline-open-weight-mock-v0") -> None:
        super().__init__(
            AdapterConfig(
                provider="offline_mock",
                model_id=model_id,
                access_mode="open_weight_full_category",
                extra={"credential_env_vars": [], "mock": True},
            ),
            is_mock=True,
        )

    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            access_mode="open_weight_full_category",
            supports_full_category_evidence=True,
            supports_token_top_k=False,
            supports_output_only=True,
            supports_surrogate_probe=False,
            requires_credentials=False,
            notes=("Offline mock evidence is deterministic fixture data, not model logits.",),
        )

    def _generate_once(self, request: ModelRequest) -> AdapterRawOutput:
        action = _mock_action(request)
        scores = {candidate: (4.0 if candidate == action else 0.0) for candidate in request.allowed_actions}
        parsed = _default_result(request, action)
        parsed["confidence"] = 1.0
        return AdapterRawOutput(
            text=json.dumps(parsed, sort_keys=True),
            parsed_json=parsed,
            category_evidence=full_category_evidence(
                scores=scores,
                score_type="logit",
                source="offline_mock",
                note="Offline mock full-category evidence; not observed model internals.",
            ),
            token_top_k_evidence=no_token_top_k_evidence("offline full-category mock does not expose token top-k"),
        )


class OfflineTokenTopKAdapter(BaseAdapter):
    """Offline stand-in for providers that return token-level top-k evidence."""

    def __init__(self, *, model_id: str = "offline-token-top-k-mock-v0", top_k: int = 3) -> None:
        super().__init__(
            AdapterConfig(
                provider="offline_mock",
                model_id=model_id,
                access_mode="token_top_k",
                token_top_k=top_k,
                extra={"credential_env_vars": [], "mock": True},
            ),
            is_mock=True,
        )
        self.top_k = top_k

    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            access_mode="token_top_k",
            supports_full_category_evidence=False,
            supports_token_top_k=True,
            supports_output_only=True,
            supports_surrogate_probe=False,
            requires_credentials=False,
            notes=("Visible top-k probability mass is recorded without tail renormalization.",),
        )

    def _generate_once(self, request: ModelRequest) -> AdapterRawOutput:
        action = _mock_action(request)
        parsed = _default_result(request, action)
        token_candidates = [
            {"token": '{"', "probability": 0.50},
            {"token": "{", "probability": 0.30},
            {"token": "\n{", "probability": 0.05},
        ][: self.top_k]
        for candidate in token_candidates:
            candidate["logprob"] = log(float(candidate["probability"]))
        evidence = token_top_k_evidence(
            positions=[{"position": 0, "candidates": token_candidates}],
            top_k=self.top_k,
            source="offline_mock",
            note="Offline mock token top-k; missing tail mass is preserved.",
        )
        return AdapterRawOutput(
            text=json.dumps(parsed, sort_keys=True),
            parsed_json=parsed,
            category_evidence=no_full_category_evidence("token-top-k mode does not expose full category scores"),
            token_top_k_evidence=evidence,
        )


class OfflineOutputOnlyAdapter(BaseAdapter):
    """Offline stand-in for output-only providers."""

    def __init__(self, *, model_id: str = "offline-output-only-mock-v0") -> None:
        super().__init__(
            AdapterConfig(
                provider="offline_mock",
                model_id=model_id,
                access_mode="output_only",
                extra={"credential_env_vars": [], "mock": True},
            ),
            is_mock=True,
        )

    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            access_mode="output_only",
            supports_full_category_evidence=False,
            supports_token_top_k=False,
            supports_output_only=True,
            supports_surrogate_probe=False,
            requires_credentials=False,
            notes=("No logprob or category-score evidence is observed in output-only mode.",),
        )

    def _generate_once(self, request: ModelRequest) -> AdapterRawOutput:
        action = _mock_action(request)
        parsed = _default_result(request, action)
        return AdapterRawOutput(
            text=json.dumps(parsed, sort_keys=True),
            parsed_json=parsed,
            category_evidence=no_full_category_evidence("output-only mode exposes no logits or category scores"),
            token_top_k_evidence=no_token_top_k_evidence("output-only mode exposes no token logprobs"),
        )

