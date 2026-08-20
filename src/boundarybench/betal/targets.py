"""Declared target-model surrogates for BeTaL-GBI parameter search.

None of these is a language model. Each is a transparent, deterministic emitter
whose behavior is a declared function of the task and a small number of named
constants. They exist so that the *search harness* can be exercised and its
properties measured without attributing any result to a real model.

Two families are provided.

``V01BoundaryFloorTarget``
    Reproduces the qualitative and quantitative shape of the frozen
    GBI BoundaryBench v0.1 result: every execution completes, and every emission
    fails at the parse or schema gate in the frozen 123/133 per-mode proportion.
    Its purpose is to demonstrate, mechanically, that BeTaL's gap signal is
    identically zero against a boundary-floor target.

``RepairedEmitterTarget``
    Emits schema-valid ``boundarybench.result.v1`` records always, and resolves
    the task correctly with a probability that depends on a declared competence
    constant and the simulator's declared task difficulty. Its purpose is to give
    the search a real, non-degenerate response surface.

The word "competence" here names a surrogate constant. It is not a measurement
of any model and must not be reported as one.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from typing import Any, Iterable

TARGETS_VERSION = "betal-gbi-target-surrogates-v0.2"

EVIDENCE_MODES: tuple[str, ...] = ("output_only", "token_top_k", "full_category_evidence")

# Frozen v0.1 per-mode emission split, from
# artifacts/public_results/v0_1/status_distributions.json
V01_PARSE_REJECTS_PER_MODE = 123
V01_SCHEMA_REJECTS_PER_MODE = 133
V01_TASKS_PER_MODE = 256


def _stable_unit(*parts: str) -> float:
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).digest()
    return int.from_bytes(digest[:7], "big") / float(1 << 56)


def _stable_rank(*parts: str) -> int:
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


@dataclass(frozen=True)
class Emission:
    """One raw target emission, before any verification."""

    task_id: str
    raw_text: str
    declared_failure_mode: str


class Target:
    """Interface for a declared target surrogate."""

    name: str
    kind: str

    def emit(self, task: dict[str, Any], *, mode: str, difficulty: float) -> Emission:
        raise NotImplementedError

    def manifest(self) -> dict[str, Any]:
        raise NotImplementedError


class V01BoundaryFloorTarget(Target):
    """Boundary-floor surrogate calibrated to the frozen v0.1 emission split."""

    kind = "boundary_floor"

    def __init__(self, *, name: str = "v01_boundary_floor_surrogate") -> None:
        self.name = name

    @staticmethod
    def _split_counts(task_count: int) -> tuple[int, int]:
        """Largest-remainder allocation preserving the frozen 123:133 proportion."""

        parse_share = V01_PARSE_REJECTS_PER_MODE / V01_TASKS_PER_MODE
        parse_exact = task_count * parse_share
        parse_count = int(math.floor(parse_exact))
        # Assign the remaining unit to whichever class has the larger remainder.
        if (parse_exact - parse_count) >= 0.5 and parse_count < task_count:
            parse_count += 1
        return parse_count, task_count - parse_count

    def assign_failure_modes(self, task_ids: Iterable[str], *, mode: str) -> dict[str, str]:
        """Deterministically split task ids into parse-reject and schema-reject sets."""

        ordered = sorted(task_ids, key=lambda task_id: _stable_rank(self.name, mode, task_id))
        parse_count, _ = self._split_counts(len(ordered))
        assignment = {task_id: "safe_schema_reject" for task_id in ordered}
        for task_id in ordered[:parse_count]:
            assignment[task_id] = "safe_parse_reject"
        return assignment

    def emit(self, task: dict[str, Any], *, mode: str, difficulty: float) -> Emission:
        # Caller supplies the assignment via task metadata; fall back to a local draw.
        failure_mode = task.get("_betal_failure_mode")
        if failure_mode not in {"safe_parse_reject", "safe_schema_reject"}:
            parse_share = V01_PARSE_REJECTS_PER_MODE / V01_TASKS_PER_MODE
            failure_mode = (
                "safe_parse_reject"
                if _stable_unit(self.name, mode, task["task_id"]) < parse_share
                else "safe_schema_reject"
            )
        task_id = task["task_id"]
        action = task["allowed_actions"][0]
        if failure_mode == "safe_parse_reject":
            variant = int(_stable_rank(self.name, "variant", task_id) % 4)
            if variant == 0:
                raw = (
                    "```json\n{\"schema_version\": \"boundarybench.result.v1\", \"task_id\": \""
                    + task_id
                    + "\"}\n```\nThis is my analysis of the record."
                )
            elif variant == 1:
                raw = (
                    "{\"schema_version\": \"boundarybench.result.v1\", \"task_id\": \""
                    + task_id
                    + "\", \"action\": \""
                    + action
                    + "\", \"answer\": {"
                )
            elif variant == 2:
                raw = (
                    "{\"task_id\": \""
                    + task_id
                    + "\", \"action\": \""
                    + action
                    + "\", \"action\": \""
                    + action
                    + "\", \"answer\": {}, \"evidence_refs\": [], "
                    + "\"schema_version\": \"boundarybench.result.v1\"}"
                )
            else:
                raw = (
                    "Based on the evidence I would "
                    + action
                    + ". JSON: {schema_version: boundarybench.result.v1, task_id: "
                    + task_id
                    + "}"
                )
            return Emission(task_id=task_id, raw_text=raw, declared_failure_mode=failure_mode)

        variant = int(_stable_rank(self.name, "schema_variant", task_id) % 4)
        if variant == 0:
            payload = {"task_id": task_id, "action": action, "answer": {}, "evidence_refs": []}
        elif variant == 1:
            payload = {
                "schema_version": "boundarybench.result.v1",
                "task_id": task_id,
                "action": "APPROVE",
                "answer": {},
                "evidence_refs": [],
            }
        elif variant == 2:
            payload = {
                "schema_version": "boundarybench.result.v1",
                "task_id": task_id,
                "action": action,
                "answer": {},
                "evidence_refs": [],
                "reasoning": "chain of thought retained in the payload",
            }
        else:
            payload = {
                "schema_version": "boundarybench.result.v1",
                "task_id": task_id,
                "action": action,
                "answer": "not-an-object",
                "evidence_refs": [],
            }
        return Emission(
            task_id=task_id,
            raw_text=json.dumps(payload, sort_keys=True),
            declared_failure_mode=failure_mode,
        )

    def manifest(self) -> dict[str, Any]:
        return {
            "schema_version": "boundarybench.betal_target_surrogate.v1",
            "targets_version": TARGETS_VERSION,
            "name": self.name,
            "kind": self.kind,
            "calibrated_to": {
                "raw_freeze": "empirical-raw-v0.1",
                "per_mode_safe_parse_reject": V01_PARSE_REJECTS_PER_MODE,
                "per_mode_safe_schema_reject": V01_SCHEMA_REJECTS_PER_MODE,
                "per_mode_task_count": V01_TASKS_PER_MODE,
            },
            "declared_behavior": (
                "Every execution completes and every emission fails at the parse or schema gate, "
                "in the frozen v0.1 proportion. Admissibility rate is identically zero and is "
                "independent of the configuration v."
            ),
            "not_a_model_claim": (
                "This surrogate reproduces the shape of one frozen v0.1 run. It is not "
                "Qwen3-4B-Instruct-2507, is not a re-execution of that model, and no result "
                "obtained from it may be attributed to any language model."
            ),
        }


class RepairedEmitterTarget(Target):
    """Schema-compliant surrogate whose accuracy responds to declared difficulty."""

    kind = "repaired_emitter"

    def __init__(
        self,
        *,
        competence: float,
        sharpness: float = 5.0,
        name: str | None = None,
    ) -> None:
        if not 0.0 <= competence <= 1.0:
            raise ValueError("competence must lie in [0,1]")
        self.competence = float(competence)
        self.sharpness = float(sharpness)
        self.name = name or f"repaired_emitter_c{int(round(competence * 100)):03d}"

    def solve_probability(self, difficulty: float) -> float:
        """Declared logistic response: p = sigma(k * (competence - difficulty))."""

        exponent = -self.sharpness * (self.competence - difficulty)
        return 1.0 / (1.0 + math.exp(exponent))

    def emit(self, task: dict[str, Any], *, mode: str, difficulty: float) -> Emission:
        task_id = task["task_id"]
        reference = task["reference"]
        probability = self.solve_probability(difficulty)
        draw = _stable_unit(self.name, mode, task_id)
        if draw < probability:
            payload = {
                "schema_version": "boundarybench.result.v1",
                "task_id": task_id,
                "action": reference["action"],
                "answer": reference["answer"],
                "evidence_refs": list(reference["required_evidence"]),
                "confidence": round(min(0.99, 0.55 + 0.4 * probability), 4),
            }
            failure_mode = "none"
        else:
            payload, failure_mode = self._plausible_error(task, probability)
        return Emission(
            task_id=task_id,
            raw_text=json.dumps(payload, sort_keys=True),
            declared_failure_mode=failure_mode,
        )

    def _plausible_error(
        self, task: dict[str, Any], probability: float
    ) -> tuple[dict[str, Any], str]:
        """Produce a schema-valid but incorrect record.

        Errors are drawn from the failure classes the GBI admission boundary is
        designed to separate: wrong action, unsupported evidence, and
        over-assertion in place of abstention.
        """

        task_id = task["task_id"]
        reference = task["reference"]
        allowed = [action for action in task["allowed_actions"] if action != reference["action"]]
        selector = int(_stable_rank(self.name, "error", task_id) % 3)
        answer = dict(reference["answer"])
        evidence = list(reference["required_evidence"])
        if selector == 0 and allowed:
            action = allowed[int(_stable_rank(self.name, "alt", task_id) % len(allowed))]
            failure_mode = "wrong_action"
        elif selector == 1:
            action = reference["action"]
            evidence = evidence[:-1] if len(evidence) > 1 else []
            failure_mode = "missing_required_evidence"
        else:
            action = reference["action"]
            # Perturb exactly one answer field so exact_criterion fails.
            if answer:
                key = sorted(answer)[0]
                value = answer[key]
                if isinstance(value, bool):
                    answer[key] = not value
                elif isinstance(value, (int, float)):
                    answer[key] = value + 1
                elif isinstance(value, str):
                    answer[key] = value + "-UNVERIFIED"
                elif isinstance(value, list):
                    answer[key] = list(value) + ["UNVERIFIED"]
                else:
                    answer[key] = "UNVERIFIED"
            else:
                answer = {"unsupported_assertion": True}
            failure_mode = "wrong_answer"
        payload = {
            "schema_version": "boundarybench.result.v1",
            "task_id": task_id,
            "action": action,
            "answer": answer,
            "evidence_refs": evidence,
            "confidence": round(min(0.99, 0.5 + 0.4 * probability), 4),
        }
        return payload, failure_mode

    def manifest(self) -> dict[str, Any]:
        return {
            "schema_version": "boundarybench.betal_target_surrogate.v1",
            "targets_version": TARGETS_VERSION,
            "name": self.name,
            "kind": self.kind,
            "declared_constants": {"competence": self.competence, "sharpness": self.sharpness},
            "declared_behavior": (
                "Always emits a schema-valid boundarybench.result.v1 record. Resolves the task "
                "correctly with probability sigma(sharpness * (competence - declared_difficulty)); "
                "otherwise emits a schema-valid but incorrect record drawn from wrong_action, "
                "missing_required_evidence, or wrong_answer."
            ),
            "not_a_model_claim": (
                "Competence is a declared surrogate constant. It is not a measurement of any "
                "language model and must not be presented as one."
            ),
        }


class OracleTarget(Target):
    """Emits the reference record for every task, unconditionally.

    This exists as an instrument, not as a baseline. It answers exactly one
    question: is every task the simulator can produce actually *solvable* under
    the unmodified v0.1 verifier, at every point in V?

    That question cannot be answered with ``RepairedEmitterTarget(competence=1.0)``.
    That surrogate's solve probability is ``sigma(k * (competence - difficulty))``,
    which tends to 0.5 as declared difficulty approaches 1.0 no matter how large
    the competence and sharpness constants are. A shortfall there measures the
    response function, not the task set. Conflating the two would let an
    unsolvable-by-construction task escape detection at the hard end of the dial.
    """

    kind = "oracle"

    def __init__(self, *, name: str = "reference_oracle") -> None:
        self.name = name

    def emit(self, task: dict[str, Any], *, mode: str, difficulty: float) -> Emission:
        reference = task["reference"]
        payload = {
            "schema_version": "boundarybench.result.v1",
            "task_id": task["task_id"],
            "action": reference["action"],
            "answer": reference["answer"],
            "evidence_refs": list(reference["required_evidence"]),
        }
        return Emission(
            task_id=task["task_id"],
            raw_text=json.dumps(payload, sort_keys=True),
            declared_failure_mode="none",
        )

    def manifest(self) -> dict[str, Any]:
        return {
            "schema_version": "boundarybench.betal_target_surrogate.v1",
            "targets_version": TARGETS_VERSION,
            "name": self.name,
            "kind": self.kind,
            "declared_behavior": "Emits the manifest-derived reference record for every task.",
            "purpose": (
                "Solvability instrument for the task set. Not a baseline and not a model; "
                "a rho_hat_task below 1.0 here indicates a defective task generator, not a "
                "difficult benchmark."
            ),
        }


# Declared surrogate competence tiers used for the cross-target transfer study.
# These are ordered labels for a surrogate constant. They do not correspond to,
# and are not proxies for, any named commercial model.
TRANSFER_TIERS: tuple[tuple[str, float], ...] = (
    ("tier_low", 0.35),
    ("tier_mid", 0.55),
    ("tier_high", 0.75),
)
