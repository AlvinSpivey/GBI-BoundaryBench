"""BeTaL Algorithm 1, instantiated over the GBI admission boundary.

The loop follows the published algorithm step for step:

  1. prompt the designer with the environment, the parameter set, the target rate
     rho, and (after the first iteration) a summary of previous iterations
  2. take the designer's proposal v_i
  3. project v_i onto the declared domain V
  4. instantiate the simulator at v_i to get a task set with reference answers
  5. evaluate the target and record the observed rate
  6. compute the gap g_i = | rho_hat_i - rho |
  7. append (v_i, rho_hat_i) to the feedback summary
  8. keep the configuration with the smallest gap

and returns the best configuration after I iterations.

One addition is load-bearing: **the admissibility gate**. Before the loop treats
an observed rate as a difficulty signal, it requires that emissions actually
reached the judgment substrate. When the admissibility rate is zero, the gap is
undefined rather than large, and the run terminates with an explicit degenerate
status after a probe sweep that demonstrates the invariance. Reporting a
"converged" configuration in that regime would be a measurement error: it would
credit parameter search for a number that no parameter can move.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import statistics
from typing import Any, Sequence

from boundarybench.betal.cone import energy_profile_for_failure_families
from boundarybench.betal.designer import Designer, Observation
from boundarybench.betal.metrics import (
    DEGENERATE_GAP_STATUS,
    Evaluation,
    TARGET_LEVELS,
    evaluate,
    failure_rate_view,
)
from boundarybench.betal.simulator import instantiate
from boundarybench.betal.space import Configuration, configuration_from_dial, space_manifest
from boundarybench.betal.targets import Target

LOOP_VERSION = "betal-gbi-loop-v0.2"

ADMISSIBILITY_GATE_MINIMUM = 0.05
PROBE_DIALS: tuple[float, ...] = (0.0, 0.25, 0.5, 0.75, 1.0)


@dataclass
class IterationRecord:
    index: int
    config: Configuration
    evaluation: Evaluation
    gap: float | None
    designer_note: str | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "iteration": self.index,
            "configuration": self.config.as_dict(),
            "gap": self.gap,
            "designer_note": self.designer_note,
            "evaluation": self.evaluation.as_dict(),
        }


@dataclass
class SearchRun:
    level: str
    rho: float
    target_name: str
    designer_name: str
    designer_kind: str
    evidence_mode: str
    task_count: int
    iterations: list[IterationRecord] = field(default_factory=list)
    status: str = "COMPLETED"
    best_index: int | None = None
    best_gap: float | None = None
    best_config: Configuration | None = None
    holdout_evaluation: Evaluation | None = None
    holdout_gap: float | None = None
    admissibility_probe: list[dict[str, Any]] = field(default_factory=list)

    def gaps(self) -> list[float]:
        return [record.gap for record in self.iterations if record.gap is not None]

    def mean_search_gap(self) -> float | None:
        gaps = self.gaps()
        return sum(gaps) / len(gaps) if gaps else None

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "boundarybench.betal_search_run.v1",
            "loop_version": LOOP_VERSION,
            "status": self.status,
            "difficulty_level": self.level,
            "rho_target_performance": self.rho,
            "rho_target_failure_rate_view": failure_rate_view(self.rho),
            "target_name": self.target_name,
            "designer_name": self.designer_name,
            "designer_kind": self.designer_kind,
            "evidence_mode": self.evidence_mode,
            "task_count": self.task_count,
            "iteration_count": len(self.iterations),
            "best_iteration": self.best_index,
            "best_gap": self.best_gap,
            "best_configuration": self.best_config.as_dict() if self.best_config else None,
            "mean_search_gap": self.mean_search_gap(),
            "holdout_gap": self.holdout_gap,
            "holdout_evaluation": (
                self.holdout_evaluation.as_dict() if self.holdout_evaluation else None
            ),
            "admissibility_probe": self.admissibility_probe,
            "iterations": [record.as_dict() for record in self.iterations],
        }


def _per_family_rho_task(evaluation: Evaluation) -> dict[str, float | None]:
    return {family: stats["rho_hat_task"] for family, stats in evaluation.per_family.items()}


def _observation(index: int, config: Configuration, evaluation: Evaluation, rho: float) -> Observation:
    return Observation(
        index=index,
        config=config,
        rho_hat_adm=evaluation.rho_hat_adm,
        rho_hat_task=evaluation.rho_hat_task,
        gap=evaluation.gap(rho),
        per_family_rho_task=_per_family_rho_task(evaluation),
    )


def _run_admissibility_probe(
    *, target: Target, mode: str, task_count: int, split_seed: str
) -> list[dict[str, Any]]:
    """Sweep the declared dial and record whether the admissibility rate responds.

    This is the evidence that a zero observed rate is a boundary property and not
    a difficulty property. If the admissibility rate is invariant across the full
    dial, no configuration in V can raise it.
    """

    probe: list[dict[str, Any]] = []
    for dial in PROBE_DIALS:
        config = configuration_from_dial(dial, origin="admissibility_probe")
        tasks, manifests = instantiate(config, task_count=task_count, split_seed=split_seed)
        evaluation = evaluate(tasks=tasks, manifests=manifests, target=target, mode=mode)
        probe.append(
            {
                "dial": dial,
                "config_sha256": config.digest(),
                "rho_hat_adm": evaluation.rho_hat_adm,
                "rho_hat_task": evaluation.rho_hat_task,
                "invalid_output_rate": evaluation.invalid_output_rate,
                "verifier_status_distribution": dict(sorted(evaluation.status_distribution.items())),
                "declared_emission_failure_modes": dict(
                    sorted(evaluation.emission_failure_modes.items())
                ),
            }
        )
    return probe


def run_search(
    *,
    designer: Designer,
    target: Target,
    level: str,
    iterations: int = 10,
    task_count: int = 256,
    evidence_mode: str = "output_only",
    search_seed: str = "search",
    holdout_seed: str = "holdout",
) -> SearchRun:
    """Execute BeTaL Algorithm 1 and then evaluate the winner on a held-out instantiation."""

    if level not in TARGET_LEVELS:
        raise KeyError(f"unknown difficulty level: {level}")
    rho = TARGET_LEVELS[level]
    run = SearchRun(
        level=level,
        rho=rho,
        target_name=target.name,
        designer_name=designer.name,
        designer_kind=designer.kind,
        evidence_mode=evidence_mode,
        task_count=task_count,
    )
    history: list[Observation] = []

    for index in range(1, iterations + 1):
        config = designer.propose(rho=rho, history=history, iteration=index)
        tasks, manifests = instantiate(config, task_count=task_count, split_seed=search_seed)
        evaluation = evaluate(tasks=tasks, manifests=manifests, target=target, mode=evidence_mode)
        gap = evaluation.gap(rho)
        note = getattr(designer, "notes", None)
        run.iterations.append(
            IterationRecord(
                index=index,
                config=config,
                evaluation=evaluation,
                gap=gap,
                designer_note=note[-1] if note else None,
            )
        )

        if evaluation.rho_hat_adm < ADMISSIBILITY_GATE_MINIMUM:
            # The gate is shut. Stop searching and prove the invariance instead.
            run.status = DEGENERATE_GAP_STATUS
            run.admissibility_probe = _run_admissibility_probe(
                target=target, mode=evidence_mode, task_count=task_count, split_seed=search_seed
            )
            return run

        history.append(_observation(index, config, evaluation, rho))
        if gap is not None and (run.best_gap is None or gap < run.best_gap):
            run.best_gap = gap
            run.best_index = index
            run.best_config = config

    if run.best_config is not None:
        tasks, manifests = instantiate(
            run.best_config, task_count=task_count, split_seed=holdout_seed
        )
        holdout = evaluate(tasks=tasks, manifests=manifests, target=target, mode=evidence_mode)
        run.holdout_evaluation = holdout
        run.holdout_gap = holdout.gap(rho)
    return run


def transfer_study(
    *,
    config: Configuration,
    targets: Sequence[Target],
    rho: float,
    task_count: int = 256,
    evidence_mode: str = "output_only",
    split_seed: str = "transfer",
) -> list[dict[str, Any]]:
    """Evaluate one selected configuration against several declared target surrogates.

    BeTaL's transferability claim is that a benchmark tuned against one target
    still separates other targets in a consistent order. This function measures
    exactly that ordering property, and nothing about any named commercial model.
    """

    tasks, manifests = instantiate(config, task_count=task_count, split_seed=split_seed)
    rows: list[dict[str, Any]] = []
    for target in targets:
        evaluation = evaluate(tasks=tasks, manifests=manifests, target=target, mode=evidence_mode)
        failing_families = {
            family
            for family, stats in evaluation.per_family.items()
            if stats["rho_hat_task"] is not None and stats["rho_hat_task"] < 0.5
        }
        diagnostic = energy_profile_for_failure_families(failing_families)
        rows.append(
            {
                "target_name": target.name,
                "target_kind": target.kind,
                "rho_hat_adm": evaluation.rho_hat_adm,
                "rho_hat_task": evaluation.rho_hat_task,
                "gap_vs_rho": evaluation.gap(rho),
                "coverage": evaluation.coverage,
                "selective_risk": evaluation.selective_risk,
                "false_acceptance_count": evaluation.false_accept_count,
                "false_rejection_count": evaluation.false_reject_count,
                "abstention_count": evaluation.abstention_count,
                "per_family_rho_task": _per_family_rho_task(evaluation),
                "cone_diagnostic": diagnostic.as_dict(),
            }
        )
    return rows


def monotonicity_check(
    *, target: Target, task_count: int = 256, evidence_mode: str = "output_only", split_seed: str = "monotone"
) -> dict[str, Any]:
    """Verify the declared monotonicity claim empirically along the dial.

    A parameter space whose declared harder_direction does not actually lower the
    observed rate is a defective search space, and the defect should be reported
    rather than absorbed by the optimizer.
    """

    rows = []
    for dial in (0.0, 0.125, 0.25, 0.375, 0.5, 0.625, 0.75, 0.875, 1.0):
        config = configuration_from_dial(dial, origin="monotonicity_check")
        tasks, manifests = instantiate(config, task_count=task_count, split_seed=split_seed)
        evaluation = evaluate(tasks=tasks, manifests=manifests, target=target, mode=evidence_mode)
        rows.append(
            {
                "dial": dial,
                "rho_hat_adm": evaluation.rho_hat_adm,
                "rho_hat_task": evaluation.rho_hat_task,
            }
        )
    rates = [row["rho_hat_task"] for row in rows if row["rho_hat_task"] is not None]
    violations = sum(
        1 for earlier, later in zip(rates, rates[1:]) if later > earlier + 1e-9
    )
    return {
        "schema_version": "boundarybench.betal_monotonicity_check.v1",
        "target_name": target.name,
        "rows": rows,
        "observed_range": (min(rates), max(rates)) if rates else None,
        "strict_violations": violations,
        "monotone_non_increasing": violations == 0,
        "note": (
            "Sampling noise at this task count can produce small local violations. "
            "The reported range is the usable dynamic range of the dial for this target."
        ),
    }


def space_and_versions() -> dict[str, Any]:
    return {
        "loop_version": LOOP_VERSION,
        "parameter_space": space_manifest(),
        "admissibility_gate_minimum": ADMISSIBILITY_GATE_MINIMUM,
        "probe_dials": list(PROBE_DIALS),
    }
