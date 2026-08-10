"""Evidence-record helpers for adapter outputs."""

from __future__ import annotations

from math import exp
from typing import Any


def softmax(scores: dict[str, float]) -> dict[str, float]:
    if not scores:
        return {}
    max_score = max(scores.values())
    numerators = {key: exp(value - max_score) for key, value in scores.items()}
    denominator = sum(numerators.values())
    return {key: value / denominator for key, value in numerators.items()}


def full_category_evidence(
    *,
    scores: dict[str, float],
    score_type: str,
    source: str,
    note: str,
) -> dict[str, Any]:
    probabilities = softmax(scores) if score_type in {"logit", "logprob"} else scores
    return {
        "schema_version": "boundarybench.full_category_evidence.v1",
        "kind": "full_category",
        "observed": True,
        "source": source,
        "complete": True,
        "score_type": score_type,
        "categories": list(scores),
        "scores": [
            {
                "category": category,
                "score": scores[category],
                "normalized_probability": probabilities.get(category),
            }
            for category in scores
        ],
        "note": note,
    }


def no_full_category_evidence(reason: str) -> dict[str, Any]:
    return {
        "schema_version": "boundarybench.full_category_evidence.v1",
        "kind": "full_category",
        "observed": False,
        "complete": False,
        "scores": [],
        "reason": reason,
    }


def token_top_k_evidence(
    *,
    positions: list[dict[str, Any]],
    top_k: int,
    source: str,
    note: str,
) -> dict[str, Any]:
    normalized_positions = []
    for position in positions:
        candidates = position["candidates"]
        visible_mass = sum(float(candidate["probability"]) for candidate in candidates)
        missing_tail_mass = max(0.0, 1.0 - visible_mass)
        normalized_positions.append(
            {
                "position": int(position["position"]),
                "candidates": candidates,
                "visible_probability_mass": visible_mass,
                "missing_tail_mass": missing_tail_mass,
            }
        )
    return {
        "schema_version": "boundarybench.token_top_k_evidence.v1",
        "kind": "token_top_k",
        "observed": True,
        "source": source,
        "top_k": top_k,
        "renormalized_visible_mass": False,
        "positions": normalized_positions,
        "note": note,
    }


def no_token_top_k_evidence(reason: str) -> dict[str, Any]:
    return {
        "schema_version": "boundarybench.token_top_k_evidence.v1",
        "kind": "token_top_k",
        "observed": False,
        "renormalized_visible_mass": False,
        "positions": [],
        "reason": reason,
    }

