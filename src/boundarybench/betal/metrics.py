"""Decomposed performance metrics for BeTaL-GBI.

The central design decision of this module is the decomposition of the observed
performance rate.

BeTaL searches over V to minimize the gap

    g_hat = | rho_hat - rho |

between an observed performance rate and a target performance rate. That search
has a well-posed gradient only if rho_hat actually responds to v. Against the
frozen GBI BoundaryBench v0.1 baseline it does not: every one of the 768
executions failed at the parse or schema gate, so rho_hat = 0 for every point in
V and g_hat = rho identically. The search signal vanishes, and it vanishes for a
reason that has nothing to do with task difficulty.

So a single scalar rate is the wrong instrument. This module splits it:

    rho_hat_adm  = admitted / task_count
                   the fraction of emissions that cleared safe parsing and
                   schema validation, i.e. entered the judgment substrate at all

    rho_hat_task = verified_completion / admitted
                   the fraction of *admitted* emissions that satisfied every
                   deterministic criterion, i.e. actual task performance

    rho_hat      = rho_hat_task, defined only when admitted > 0

BeTaL tunes rho_hat_task and is gated on rho_hat_adm > 0. When the gate is shut,
the run terminates with an explicit ``degenerate_gap`` status rather than
reporting a spuriously converged parameter set. The admissibility floor is a
prerequisite to be repaired, not a difficulty dial to be tuned.

All grading is delegated to the authoritative v0.1 Programmatic Verification
Engine (``boundarybench.verification``). This module never re-implements a
criterion.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from boundarybench.betal.simulator import instantiation_digest
from boundarybench.betal.targets import Target
from boundarybench.tasks.grade import safe_parse_result
from boundarybench.verification.engine import verify_task
from boundarybench.verification.graders import ADMITTING_ACTIONS, NON_ADMIT_ACTIONS
from boundarybench.verification.quarantine import dependency_index

METRICS_VERSION = "betal-gbi-metrics-v0.2"

DEGENERATE_GAP_STATUS = "degenerate_gap_admissibility_floor"


@dataclass
class Evaluation:
    """Result of evaluating one target against one instantiation."""

    task_count: int
    admitted_count: int
    verified_count: int
    rho_hat_adm: float
    rho_hat_task: float | None
    coverage: float
    selective_risk: float | None
    false_accept_count: int
    false_reject_count: int
    abstention_count: int
    quarantine_count: int
    invalid_output_rate: float
    status_distribution: dict[str, int]
    emission_failure_modes: dict[str, int]
    per_family: dict[str, dict[str, Any]]
    instantiation_sha256: str
    mode: str
    target_name: str

    @property
    def rho_hat(self) -> float | None:
        """The tuned quantity. ``None`` means the admissibility gate is shut."""

        return self.rho_hat_task

    def gap(self, rho: float) -> float | None:
        if self.rho_hat_task is None:
            return None
        return abs(self.rho_hat_task - rho)

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "boundarybench.betal_evaluation.v1",
            "metrics_version": METRICS_VERSION,
            "target_name": self.target_name,
            "evidence_mode": self.mode,
            "task_count": self.task_count,
            "admitted_count": self.admitted_count,
            "verified_completion": self.verified_count,
            "rho_hat_adm": self.rho_hat_adm,
            "rho_hat_task": self.rho_hat_task,
            "coverage": self.coverage,
            "selective_risk": self.selective_risk,
            "false_acceptance_count": self.false_accept_count,
            "false_rejection_count": self.false_reject_count,
            "abstention_count": self.abstention_count,
            "quarantine_count": self.quarantine_count,
            "invalid_output_rate": self.invalid_output_rate,
            "verifier_status_distribution": dict(sorted(self.status_distribution.items())),
            "declared_emission_failure_modes": dict(sorted(self.emission_failure_modes.items())),
            "per_family": self.per_family,
            "instantiation_sha256": self.instantiation_sha256,
        }


def evaluate(
    *,
    tasks: list[dict[str, Any]],
    manifests: list[dict[str, Any]],
    target: Target,
    mode: str,
) -> Evaluation:
    """BeTaL Algorithm 1 step 5: ``EvaluateModel(M_t, D_i)``.

    Grading is performed by the v0.1 PVE. The only thing this function adds is
    the admissibility/task decomposition and per-family slicing.
    """

    if len(tasks) != len(manifests):
        raise ValueError("tasks and manifests must be the same length")

    difficulty_by_id = {entry["task_id"]: entry["declared_difficulty"] for entry in manifests}
    dependency_lookup = dependency_index(tasks)

    # The boundary-floor surrogate needs a global assignment to reproduce the
    # frozen per-mode split exactly rather than in expectation.
    assignment: dict[str, str] = {}
    if hasattr(target, "assign_failure_modes"):
        assignment = target.assign_failure_modes(  # type: ignore[attr-defined]
            [task["task_id"] for task in tasks], mode=mode
        )

    status_counter: Counter[str] = Counter()
    emission_counter: Counter[str] = Counter()
    admitted = 0
    verified = 0
    covered = 0
    covered_failures = 0
    false_accepts = 0
    false_rejects = 0
    abstentions = 0
    quarantined = 0
    family_stats: dict[str, dict[str, Any]] = {}

    for task, manifest in zip(tasks, manifests):
        task_id = task["task_id"]
        family = task["family"]
        difficulty = difficulty_by_id[task_id]
        emit_task = dict(task)
        if assignment:
            emit_task["_betal_failure_mode"] = assignment[task_id]
        emission = target.emit(emit_task, mode=mode, difficulty=difficulty)
        emission_counter[emission.declared_failure_mode] += 1

        parsed_result, parse_errors = safe_parse_result(emission.raw_text)
        grade = verify_task(
            task=task,
            result=parsed_result,
            parse_errors=parse_errors,
            dependency_lookup=dependency_lookup,
        )
        status_counter[grade.status] += 1

        slot = family_stats.setdefault(
            family,
            {
                "task_count": 0,
                "admitted_count": 0,
                "verified_completion": 0,
                "declared_difficulty_mean": 0.0,
                "reference_action_distribution": {},
            },
        )
        slot["task_count"] += 1
        slot["declared_difficulty_mean"] += difficulty
        reference_action = manifest["reference_action"]
        slot["reference_action_distribution"][reference_action] = (
            slot["reference_action_distribution"].get(reference_action, 0) + 1
        )

        if grade.parsed:
            admitted += 1
            slot["admitted_count"] += 1
            if grade.observed_action != "abstain":
                covered += 1
                if not grade.passed:
                    covered_failures += 1
            else:
                abstentions += 1
            if (
                grade.observed_action in ADMITTING_ACTIONS
                and grade.expected_action in NON_ADMIT_ACTIONS
            ):
                false_accepts += 1
            if (
                grade.observed_action in NON_ADMIT_ACTIONS
                and grade.expected_action in ADMITTING_ACTIONS
            ):
                false_rejects += 1
        if grade.passed:
            verified += 1
            slot["verified_completion"] += 1
        if grade.quarantine.quarantined:
            quarantined += 1

    task_count = len(tasks)
    for slot in family_stats.values():
        slot["declared_difficulty_mean"] = round(
            slot["declared_difficulty_mean"] / slot["task_count"], 6
        )
        slot["rho_hat_adm"] = slot["admitted_count"] / slot["task_count"]
        slot["rho_hat_task"] = (
            slot["verified_completion"] / slot["admitted_count"] if slot["admitted_count"] else None
        )

    return Evaluation(
        task_count=task_count,
        admitted_count=admitted,
        verified_count=verified,
        rho_hat_adm=admitted / task_count if task_count else 0.0,
        rho_hat_task=(verified / admitted) if admitted else None,
        coverage=covered / task_count if task_count else 0.0,
        selective_risk=(covered_failures / covered) if covered else None,
        false_accept_count=false_accepts,
        false_reject_count=false_rejects,
        abstention_count=abstentions,
        quarantine_count=quarantined,
        invalid_output_rate=(task_count - admitted) / task_count if task_count else 0.0,
        status_distribution=dict(status_counter),
        emission_failure_modes=dict(emission_counter),
        per_family={family: family_stats[family] for family in sorted(family_stats)},
        instantiation_sha256=instantiation_digest(tasks),
        mode=mode,
        target_name=target.name,
    )


# --- Target performance ladder ----------------------------------------------
#
# rho is a target *performance* rate (verified completion given admission), which
# is the BeTaL convention. Under this convention lower rho means a harder
# benchmark. A failure-rate reading of these same numbers inverts the ladder;
# see the errata note in the design specification.

TARGET_LEVELS: dict[str, float] = {
    "hard": 0.25,
    "medium": 0.50,
    "easy": 0.75,
    "trivial": 0.90,
}

LEVEL_ORDER: tuple[str, ...] = ("hard", "medium", "easy", "trivial")


def failure_rate_view(rho_performance: float) -> float:
    """Translate a target performance rate into the failure-rate convention."""

    return round(1.0 - rho_performance, 10)
