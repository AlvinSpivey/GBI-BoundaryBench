"""Local surrogate-probe adapter.

The surrogate is intentionally simple and transparent. It learns empirical
action frequencies from declared observable features only. It is not a
reconstruction of hidden model states.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
import json
from typing import Any

from boundarybench.adapters.base import BaseAdapter
from boundarybench.adapters.evidence import full_category_evidence, no_token_top_k_evidence
from boundarybench.adapters.types import AdapterCapabilities, AdapterConfig, AdapterRawOutput, ModelRequest


@dataclass(frozen=True)
class SurrogateExample:
    task_id: str
    features: dict[str, Any]
    label: str


def _feature_key(features: dict[str, Any]) -> str | None:
    family = features.get("family")
    if not isinstance(family, str) or not family:
        return None
    return f"family={family}"


def _probabilities(counts: Counter[str], allowed_actions: tuple[str, ...]) -> dict[str, float]:
    denominator = sum(counts.values()) + len(allowed_actions)
    return {action: (counts[action] + 1) / denominator for action in allowed_actions}


def _brier_score(probabilities: dict[str, float], label: str, allowed_actions: tuple[str, ...]) -> float:
    return sum((probabilities[action] - (1.0 if action == label else 0.0)) ** 2 for action in allowed_actions)


def _expected_calibration_error(confidences: list[float], correct: list[bool], bins: int = 5) -> float | None:
    if not confidences:
        return None
    total = len(confidences)
    ece = 0.0
    for bin_index in range(bins):
        lower = bin_index / bins
        upper = (bin_index + 1) / bins
        in_bin = []
        for index, confidence in enumerate(confidences):
            if bin_index == bins - 1:
                matches_bin = lower <= confidence <= upper
            else:
                matches_bin = lower <= confidence < upper
            if matches_bin:
                in_bin.append(index)
        if not in_bin:
            continue
        avg_confidence = sum(confidences[index] for index in in_bin) / len(in_bin)
        accuracy = sum(1 for index in in_bin if correct[index]) / len(in_bin)
        ece += (len(in_bin) / total) * abs(avg_confidence - accuracy)
    return ece


class LocalSurrogateProbeAdapter(BaseAdapter):
    """Frequency-by-family local surrogate probe."""

    def __init__(
        self,
        *,
        allowed_actions: tuple[str, ...],
        family_counts: dict[str, Counter[str]],
        global_counts: Counter[str],
        report: dict[str, Any],
        model_id: str = "local-surrogate-probe-family-frequency-v0",
    ) -> None:
        super().__init__(
            AdapterConfig(
                provider="local_surrogate",
                model_id=model_id,
                access_mode="local_surrogate_probe",
                extra={
                    "credential_env_vars": [],
                    "feature_names": ["family"],
                    "mock": False,
                    "surrogate_warning": "not_hidden_state_reconstruction",
                },
            ),
            is_mock=False,
        )
        self.allowed_actions = allowed_actions
        self.family_counts = family_counts
        self.global_counts = global_counts
        self.report = report

    @classmethod
    def fit(
        cls,
        *,
        train_examples: list[SurrogateExample],
        validation_examples: list[SurrogateExample],
        allowed_actions: tuple[str, ...],
    ) -> "LocalSurrogateProbeAdapter":
        if not train_examples:
            raise ValueError("train_examples must be non-empty")
        if not allowed_actions:
            raise ValueError("allowed_actions must be non-empty")
        family_counts: dict[str, Counter[str]] = defaultdict(Counter)
        global_counts: Counter[str] = Counter()
        for example in train_examples:
            if example.label not in allowed_actions:
                raise ValueError(f"unsupported surrogate label: {example.label}")
            key = _feature_key(example.features)
            if key is not None:
                family_counts[key][example.label] += 1
            global_counts[example.label] += 1

        report = cls._validation_report(
            validation_examples=validation_examples,
            allowed_actions=allowed_actions,
            family_counts=dict(family_counts),
            global_counts=global_counts,
            train_count=len(train_examples),
        )
        return cls(
            allowed_actions=allowed_actions,
            family_counts=dict(family_counts),
            global_counts=global_counts,
            report=report,
        )

    @staticmethod
    def _predict_from_counts(
        features: dict[str, Any],
        *,
        allowed_actions: tuple[str, ...],
        family_counts: dict[str, Counter[str]],
        global_counts: Counter[str],
    ) -> tuple[dict[str, float], bool, str | None]:
        key = _feature_key(features)
        if key is None:
            return _probabilities(global_counts, allowed_actions), False, "missing_family_feature"
        if key not in family_counts:
            return _probabilities(global_counts, allowed_actions), False, "unseen_family_feature"
        return _probabilities(family_counts[key], allowed_actions), True, None

    @staticmethod
    def _validation_report(
        *,
        validation_examples: list[SurrogateExample],
        allowed_actions: tuple[str, ...],
        family_counts: dict[str, Counter[str]],
        global_counts: Counter[str],
        train_count: int,
    ) -> dict[str, Any]:
        covered = 0
        correct_count = 0
        brier_scores: list[float] = []
        confidences: list[float] = []
        correctness: list[bool] = []
        for example in validation_examples:
            probabilities, is_covered, _ = LocalSurrogateProbeAdapter._predict_from_counts(
                example.features,
                allowed_actions=allowed_actions,
                family_counts=family_counts,
                global_counts=global_counts,
            )
            if not is_covered:
                continue
            covered += 1
            predicted = max(allowed_actions, key=lambda action: probabilities[action])
            is_correct = predicted == example.label
            correct_count += 1 if is_correct else 0
            confidence = probabilities[predicted]
            confidences.append(confidence)
            correctness.append(is_correct)
            brier_scores.append(_brier_score(probabilities, example.label, allowed_actions))
        validation_count = len(validation_examples)
        return {
            "schema_version": "boundarybench.surrogate_report.v1",
            "surrogate_kind": "frequency_by_family",
            "observable_feature_names": ["family"],
            "train_count": train_count,
            "validation_count": validation_count,
            "coverage": covered / validation_count if validation_count else None,
            "held_out_fidelity": correct_count / covered if covered else None,
            "brier_score": sum(brier_scores) / len(brier_scores) if brier_scores else None,
            "expected_calibration_error": _expected_calibration_error(confidences, correctness),
            "invalidation_rules": [
                "missing_family_feature",
                "unseen_family_feature",
            ],
            "limitations": [
                "Uses only declared observable task family features.",
                "Does not reconstruct hidden states.",
                "Out-of-domain requests must abstain.",
            ],
        }

    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            access_mode="local_surrogate_probe",
            supports_full_category_evidence=True,
            supports_token_top_k=False,
            supports_output_only=True,
            supports_surrogate_probe=True,
            requires_credentials=False,
            notes=("Surrogate probabilities are local empirical estimates, not model logits.",),
        )

    def _generate_once(self, request: ModelRequest) -> AdapterRawOutput:
        features = request.metadata.get("surrogate_features", {})
        if not isinstance(features, dict):
            features = {}
        probabilities, covered, invalidation = self._predict_from_counts(
            features,
            allowed_actions=self.allowed_actions,
            family_counts=self.family_counts,
            global_counts=self.global_counts,
        )
        if covered:
            action = max(self.allowed_actions, key=lambda candidate: probabilities[candidate])
            answer = {"surrogate_status": "in_domain", "predicted_action": action}
            errors: tuple[str, ...] = ()
        else:
            action = "abstain" if "abstain" in request.allowed_actions else request.allowed_actions[0]
            answer = {
                "surrogate_status": "out_of_domain",
                "invalidation": invalidation,
            }
            errors = (f"surrogate_out_of_domain:{invalidation}",)
        parsed = {
            "schema_version": "boundarybench.result.v1",
            "task_id": request.task_id,
            "action": action,
            "answer": answer,
            "evidence_refs": [],
            "confidence": probabilities.get(action, 0.0),
        }
        return AdapterRawOutput(
            text=json.dumps(parsed, sort_keys=True),
            parsed_json=parsed,
            category_evidence=full_category_evidence(
                scores=probabilities,
                score_type="surrogate_probability",
                source="local_surrogate_probe",
                note="Local surrogate probabilities from declared observable features; not model internals.",
            ),
            token_top_k_evidence=no_token_top_k_evidence("local surrogate does not expose token logprobs"),
            surrogate_report=self.report,
            errors=errors,
        )
