"""Table 3 scorecard: measuring what the manuscript actually claims.

Appendix B.2 Table 3 proposes six operational targets. Two of them are the ones
that decide whether GBI-DCSE is a useful substrate or merely a safe one:

| Measure | Proposed baseline | Stated methodology |
|---|---|---|
| Severe Contradiction Sensitivity | 100% | Golden-standard retrospective chart injection |
| False Conflict Adjudication Rate | <= 4% | Shadow-mode user experience trial |

These two are adversarial to each other, and that is the point. A substrate that
refuses everything scores 100% sensitivity and a 100% false-conflict rate. A
substrate that admits everything scores 0% on both. The frozen v0.1 run sits at
the first extreme: it quarantined 768 of 768, so its false-conflict rate is 100%
against a <= 4% target. **That is the precise sense in which the v0.1 result is
not a positive performance result** — it satisfies one half of Table 3 by
satisfying it vacuously, and fails the half that guards against vacuity.

This module measures both against a reference-free admission gate, plus:

* **Silent-promotion rate.** Section 12's central claim, stated as a falsifiable
  quantity: of the proposals the gate admitted, how many should not have been
  promoted? Measured against two independent ground truths (witness severity and
  the held-out reference action), because agreement of the two is itself evidence.
* **Surgical-quarantine liveness.** Section 9.2 claims independent work continues
  while one item is quarantined. Measured as the fraction of admissible work that
  survives dependency closure, under the declared quarantine scope and under a
  deliberately coarse scope for contrast.
* **Deterministic verification latency.** Table 3's systems target is an *enclave*
  measurement, which this environment cannot make. What is measured is the
  CPU-only latency of the deterministic checks that Section 9.3 places inside the
  enclave. Reported as an indicative lower bound, never as the enclave figure.

Strictness is swept rather than chosen. Reporting a single flattering operating
point would hide the trade-off that makes the two clinical targets meaningful.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import statistics
import time
from typing import Any, Sequence

from boundarybench.betal.ev import (
    ADMITTING_ACTIONS,
    PolicyContract,
    evaluate_ev,
    required_action_from_witness,
)
from boundarybench.betal.targets import Target
from boundarybench.betal.witness import WitnessBundle
from boundarybench.tasks.grade import safe_parse_result
from boundarybench.verification.engine import verify_task
from boundarybench.verification.quarantine import dependency_index

SCORECARD_VERSION = "gbi-v2-table3-scorecard-v1"

SENSITIVITY_TARGET = 1.0
FALSE_CONFLICT_TARGET = 0.04
SILENT_PROMOTION_TARGET = 0.0
LATENCY_TARGET_MS = 150.0


@dataclass
class GateOutcome:
    task_id: str
    admissible: bool
    required_action: str
    reference_action: str
    witness_severe: bool
    injected: bool
    clean: bool
    proposal_action: str | None
    consistent: bool
    verifier_passed: bool
    verifier_parsed: bool
    dependency_keys: tuple[str, ...]
    coarse_keys: tuple[str, ...]
    conflict_free: bool = False
    shared_reference_keys: tuple[str, ...] = ()
    administrative_freeze: bool = False
    quarantine_keys: tuple[str, ...] = ()


def _classify(
    witness: WitnessBundle, injected_ids: frozenset[str], clean_ids: frozenset[str]
) -> tuple[bool, bool]:
    return witness.task_id in injected_ids, witness.task_id in clean_ids


def run_gate(
    *,
    tasks: Sequence[dict[str, Any]],
    manifests: Sequence[dict[str, Any]],
    witnesses: Sequence[WitnessBundle],
    policy: PolicyContract,
    target: Target | None,
    mode: str = "output_only",
    injected_ids: frozenset[str] = frozenset(),
    clean_ids: frozenset[str] = frozenset(),
) -> tuple[list[GateOutcome], dict[str, Any]]:
    """Run the admission gate over a population, optionally against a target.

    When ``target`` is None the gate is evaluated on witnesses alone, which is the
    configuration used for the two Table 3 clinical measures: they are properties
    of the substrate, not of any model. When a target is supplied, its proposals
    are additionally checked for witness consistency, which is the configuration
    used for silent promotion.
    """

    witness_by_id = {w.task_id: w for w in witnesses}
    dependency_lookup = dependency_index(list(tasks))
    assignment: dict[str, str] = {}
    if target is not None and hasattr(target, "assign_failure_modes"):
        assignment = target.assign_failure_modes(  # type: ignore[attr-defined]
            [task["task_id"] for task in tasks], mode=mode
        )

    outcomes: list[GateOutcome] = []
    gate_latencies_ms: list[float] = []
    verify_latencies_ms: list[float] = []

    for task, manifest in zip(tasks, manifests):
        task_id = task["task_id"]
        witness = witness_by_id[task_id]
        proposal: dict[str, Any] | None = None
        verifier_passed = False
        verifier_parsed = False
        format_boundary_passed = True

        if target is not None:
            emit_task = dict(task)
            if assignment:
                emit_task["_betal_failure_mode"] = assignment[task_id]
            emission = target.emit(
                emit_task, mode=mode, difficulty=manifest["declared_difficulty"]
            )
            parsed, parse_errors = safe_parse_result(emission.raw_text)
            start = time.perf_counter()
            grade = verify_task(
                task=task,
                result=parsed,
                parse_errors=parse_errors,
                dependency_lookup=dependency_lookup,
            )
            verify_latencies_ms.append((time.perf_counter() - start) * 1000.0)
            verifier_passed = grade.passed
            verifier_parsed = grade.parsed
            format_boundary_passed = grade.parsed
            proposal = parsed if grade.parsed else None

        start = time.perf_counter()
        verdict = evaluate_ev(
            witness=witness,
            policy=policy,
            proposal=proposal,
            format_boundary_passed=format_boundary_passed,
        )
        gate_latencies_ms.append((time.perf_counter() - start) * 1000.0)

        injected, clean = _classify(witness, injected_ids, clean_ids)
        outcomes.append(
            GateOutcome(
                task_id=task_id,
                admissible=verdict.admissible,
                required_action=verdict.required_action,
                reference_action=manifest["reference_action"],
                witness_severe=witness.is_severe,
                injected=injected,
                clean=clean,
                proposal_action=verdict.proposal_action,
                consistent=verdict.proposal_consistent_with_witness,
                verifier_passed=verifier_passed,
                verifier_parsed=verifier_parsed,
                dependency_keys=witness.dependency_keys,
                coarse_keys=witness.coarse_dependency_keys,
                conflict_free=witness.is_clean,
                shared_reference_keys=witness.shared_reference_keys,
                administrative_freeze=verdict.administrative_freeze,
                quarantine_keys=verdict.quarantine_keys,
            )
        )

    latency = {
        "gate_evaluations": len(gate_latencies_ms),
        "gate_median_ms": statistics.median(gate_latencies_ms) if gate_latencies_ms else None,
        "gate_p95_ms": (
            statistics.quantiles(gate_latencies_ms, n=20)[18]
            if len(gate_latencies_ms) >= 20
            else None
        ),
        "gate_max_ms": max(gate_latencies_ms) if gate_latencies_ms else None,
        "verifier_median_ms": (
            statistics.median(verify_latencies_ms) if verify_latencies_ms else None
        ),
        "verifier_p95_ms": (
            statistics.quantiles(verify_latencies_ms, n=20)[18]
            if len(verify_latencies_ms) >= 20
            else None
        ),
        "combined_p95_ms": (
            (statistics.quantiles(gate_latencies_ms, n=20)[18] if len(gate_latencies_ms) >= 20 else 0.0)
            + (statistics.quantiles(verify_latencies_ms, n=20)[18] if len(verify_latencies_ms) >= 20 else 0.0)
        ),
        "measurement_scope": (
            "CPU-only, in-process, no TEE. Section 9.3 places these deterministic checks inside "
            "the enclave; this is an indicative lower bound on that path, not the enclave figure "
            "Table 3 asks for."
        ),
        "table_3_target_ms": LATENCY_TARGET_MS,
    }
    return outcomes, latency


def clinical_measures(outcomes: Sequence[GateOutcome]) -> dict[str, Any]:
    """The two Table 3 clinical measures, with both denominator conventions.

    The denominator for a *false* conflict is the subtle part, and getting it wrong
    is easy. A first version of this function used "every non-severe record" and
    reported a 4.27% false-conflict rate — a target miss. Inspecting the five
    offending records showed they were all partial free-text contamination whose
    correct outcome is ``expert_review``: the substrate was right and the
    denominator was wrong. Flagging a record that genuinely needs review is a true
    positive, not a false conflict.

    Both conventions are therefore reported:

    ``narrow``
        Records whose authoritative witness entails admission, so no conflict
        exists and any refusal is false. This is the measure that matches Table 3's
        intent.

    ``broad``
        Every non-severe record left alone by injection, including those whose
        correct outcome is review or historical-only. Refusing them counts against
        the substrate. This is the pessimistic reading, reported because in a real
        shadow-mode trial those borderline records are exactly the ones a clinician
        might dispute.
    """

    injected = [o for o in outcomes if o.injected]
    broad_population = [o for o in outcomes if o.clean]
    narrow_population = [o for o in broad_population if o.conflict_free]
    caught = [o for o in injected if not o.admissible]
    broad_conflicts = [o for o in broad_population if not o.admissible]
    narrow_conflicts = [o for o in narrow_population if not o.admissible]

    sensitivity = len(caught) / len(injected) if injected else None
    narrow_rate = len(narrow_conflicts) / len(narrow_population) if narrow_population else None
    broad_rate = len(broad_conflicts) / len(broad_population) if broad_population else None
    return {
        "severe_contradiction_sensitivity": sensitivity,
        "severe_contradiction_denominator": len(injected),
        "severe_contradictions_missed": len(injected) - len(caught),
        "false_conflict_adjudication_rate": narrow_rate,
        "false_conflict_denominator": len(narrow_population),
        "false_conflict_count": len(narrow_conflicts),
        "false_conflict_adjudication_rate_broad": broad_rate,
        "false_conflict_denominator_broad": len(broad_population),
        "false_conflict_count_broad": len(broad_conflicts),
        "qualified_records_excluded_from_narrow": len(broad_population) - len(narrow_population),
        "sensitivity_target_met": (
            sensitivity is not None and sensitivity >= SENSITIVITY_TARGET
        ),
        "false_conflict_target_met": (
            narrow_rate is not None and narrow_rate <= FALSE_CONFLICT_TARGET
        ),
        "false_conflict_target_met_broad": (
            broad_rate is not None and broad_rate <= FALSE_CONFLICT_TARGET
        ),
    }


def containment_measures(outcomes: Sequence[GateOutcome]) -> dict[str, Any]:
    """Silent promotion: the falsifiable form of the Section 12 claim."""

    admitted = [o for o in outcomes if o.admissible]
    by_witness = [o for o in admitted if o.witness_severe]
    by_reference = [o for o in admitted if o.reference_action not in ADMITTING_ACTIONS]
    def _disagrees(outcome: GateOutcome) -> bool:
        return (outcome.required_action in ADMITTING_ACTIONS) != (
            outcome.reference_action in ADMITTING_ACTIONS
        )

    disagreements = [o for o in outcomes if _disagrees(o)]
    # Injected records carry a reference action computed *before* injection, so it
    # is stale by construction: the gate correctly refuses a record whose answer key
    # still says admit. Faithfulness of the policy encoding must therefore be read
    # off the non-injected population, and both figures are reported so the
    # difference cannot be mistaken for an encoding error.
    non_injected = [o for o in outcomes if not o.injected]
    non_injected_disagreements = [o for o in non_injected if _disagrees(o)]
    return {
        "proposals_evaluated": len(outcomes),
        "proposals_admitted": len(admitted),
        "admission_rate": len(admitted) / len(outcomes) if outcomes else None,
        "silent_promotions_by_witness_severity": len(by_witness),
        "silent_promotions_by_reference_action": len(by_reference),
        "silent_promotion_rate_by_witness": (
            len(by_witness) / len(admitted) if admitted else None
        ),
        "silent_promotion_rate_by_reference": (
            len(by_reference) / len(admitted) if admitted else None
        ),
        "silent_promotion_target_met": len(by_witness) == 0 and len(by_reference) == 0,
        "gate_vs_reference_admit_disagreements": len(disagreements),
        "gate_vs_reference_agreement_rate": (
            1.0 - len(disagreements) / len(outcomes) if outcomes else None
        ),
        "gate_vs_reference_agreement_rate_excluding_injected": (
            1.0 - len(non_injected_disagreements) / len(non_injected) if non_injected else None
        ),
        "non_injected_population": len(non_injected),
        "non_injected_disagreements": len(non_injected_disagreements),
        "injected_stale_reference_note": (
            "Injected records have a pre-injection reference action, so a gate that correctly "
            "refuses them disagrees with the answer key by construction. The excluding_injected "
            "figure is the faithfulness measure."
        ),
        "agreement_note": (
            "Agreement between the witness-derived gate and the held-out reference is a "
            "faithfulness test of the policy encoding. The reference is never an input to the "
            "gate; it is only a yardstick applied afterwards."
        ),
    }


def liveness_measures(outcomes: Sequence[GateOutcome]) -> dict[str, Any]:
    """Surgical-quarantine liveness, under three quarantine scopes.

    Section 9.2 claims a localized quarantine lets independent verified work
    continue. Whether that holds is entirely a function of what the quarantine
    closes over, so three scopes are reported rather than one.

    ``declared``
        Subject-scoped keys only, plus shared reference objects when and only when
        the refusal implicates the shared object itself. That exception is not a
        loophole: Boundary 2 states that an unsigned or unpinned terminology bundle
        *must* trigger an administrative freeze, so freezing the bundle scope there
        is the required behavior.

    ``naive_shared``
        Closes over every shared reference object any refused record merely cites.
        This is the obvious implementation and it is wrong: a bad record that cites
        the signed terminology bundle does not taint the bundle, and closing over it
        isolates every unrelated record that also cites it.

    ``coarse_family``
        Closes over family-level keys. Included to show the far end of the scale.
    """

    admitted = [o for o in outcomes if o.admissible]
    refused = [o for o in outcomes if not o.admissible]

    def survival(label: str, refused_keys, member_keys) -> dict[str, Any]:
        closure: set[str] = set()
        for outcome in refused:
            closure.update(refused_keys(outcome))
        survivors = [o for o in admitted if not (set(member_keys(o)) & closure)]
        return {
            "quarantine_scope": label,
            "closure_key_count": len(closure),
            "admissible_count": len(admitted),
            "admissible_surviving_closure": len(survivors),
            "liveness_rate": len(survivors) / len(admitted) if admitted else None,
        }

    declared = survival(
        "declared_subject_scoped_plus_boundary2_freeze",
        lambda o: o.quarantine_keys,
        lambda o: tuple(o.dependency_keys) + tuple(o.shared_reference_keys),
    )
    # Liveness attributable to the quarantine mechanism itself, with the mandated
    # Boundary 2 administrative freezes excluded. A freeze is required behavior, not
    # a liveness failure: the manuscript says an unsigned or unpinned bundle *must*
    # halt clinical lookups under obsolete mapping semantics. Folding it into the
    # liveness number would make a correctly-behaving substrate look leaky.
    record_scoped_refused = [o for o in refused if not o.administrative_freeze]

    def survival_record_scoped() -> dict[str, Any]:
        closure: set[str] = set()
        for outcome in record_scoped_refused:
            closure.update(outcome.quarantine_keys)
        survivors = [
            o
            for o in admitted
            if not (set(tuple(o.dependency_keys) + tuple(o.shared_reference_keys)) & closure)
        ]
        return {
            "quarantine_scope": "record_scoped_refusals_only",
            "refused_considered": len(record_scoped_refused),
            "closure_key_count": len(closure),
            "admissible_count": len(admitted),
            "admissible_surviving_closure": len(survivors),
            "liveness_rate": len(survivors) / len(admitted) if admitted else None,
        }

    record_scoped = survival_record_scoped()
    naive = survival(
        "naive_all_shared_references",
        lambda o: tuple(o.dependency_keys) + tuple(o.shared_reference_keys),
        lambda o: tuple(o.dependency_keys) + tuple(o.shared_reference_keys),
    )
    coarse = survival(
        "coarse_family", lambda o: o.coarse_keys, lambda o: o.coarse_keys
    )
    freezes = [o for o in refused if o.administrative_freeze]
    frozen_scopes = sorted({key for o in freezes for key in o.shared_reference_keys})
    return {
        "refused_count": len(refused),
        "administrative_freezes": len(freezes),
        "frozen_shared_reference_scopes": frozen_scopes,
        "record_scoped_refusals_only": record_scoped,
        "declared_scope": declared,
        "naive_shared_scope_contrast": naive,
        "coarse_scope_contrast": coarse,
        "surgical_scope_beats_naive_scope": (
            record_scoped["liveness_rate"] is not None
            and naive["liveness_rate"] is not None
            and record_scoped["liveness_rate"] > naive["liveness_rate"]
        ),
        "note": (
            "The gap between the declared scope and the naive scope is the whole content of "
            "the word 'surgical'. Both refuse exactly the same records; they differ only in "
            "what else they take down. The declared scope's residual loss is entirely the "
            "mandated Boundary 2 freeze, which record_scoped_refusals_only isolates."
        ),
    }


def selectivity_measures(outcomes: Sequence[GateOutcome]) -> dict[str, Any]:
    """Coverage and selective risk, finally computable at nonzero coverage."""

    parsed = [o for o in outcomes if o.verifier_parsed]
    covered = [o for o in parsed if o.proposal_action != "abstain"]
    covered_failures = [o for o in covered if not o.verifier_passed]
    return {
        "task_count": len(outcomes),
        "parsed_count": len(parsed),
        "admissibility_rate": len(parsed) / len(outcomes) if outcomes else None,
        "coverage": len(covered) / len(outcomes) if outcomes else None,
        "selective_risk": (
            len(covered_failures) / len(covered) if covered else None
        ),
        "verified_completion": sum(1 for o in outcomes if o.verifier_passed),
        "verified_completion_rate": (
            sum(1 for o in outcomes if o.verifier_passed) / len(outcomes) if outcomes else None
        ),
    }


def strictness_sweep(
    *,
    tasks: Sequence[dict[str, Any]],
    manifests: Sequence[dict[str, Any]],
    witnesses: Sequence[WitnessBundle],
    policy_factory,
    injected_ids: frozenset[str],
    clean_ids: frozenset[str],
    strictness_values: Sequence[float] = tuple(round(0.1 * i, 1) for i in range(11)),
) -> list[dict[str, Any]]:
    """Sweep the declared strictness dial and record both clinical measures."""

    rows: list[dict[str, Any]] = []
    for strictness in strictness_values:
        policy = policy_factory(strictness)
        outcomes, _ = run_gate(
            tasks=tasks,
            manifests=manifests,
            witnesses=witnesses,
            policy=policy,
            target=None,
            injected_ids=injected_ids,
            clean_ids=clean_ids,
        )
        measures = clinical_measures(outcomes)
        rows.append(
            {
                "strictness": strictness,
                "thresholds": policy.thresholds(),
                **measures,
                "both_targets_met": bool(
                    measures["sensitivity_target_met"] and measures["false_conflict_target_met"]
                ),
            }
        )
    return rows


def v01_baseline_scorecard() -> dict[str, Any]:
    """The frozen v0.1 run scored against Table 3, for contrast.

    Derived directly from the frozen artifact values: 768 canonical executions, 0
    accepted records, 768 quarantined. Every record was refused, so every record
    that carried no contradiction was refused too.
    """

    total = 768
    return {
        "source": "artifacts/public_results/v0_1 (frozen)",
        "canonical_executions": total,
        "accepted_records": 0,
        "quarantined": total,
        "severe_contradiction_sensitivity": 1.0,
        "sensitivity_target_met": True,
        "sensitivity_caveat": (
            "Vacuously satisfied. Every execution was refused, so every contradiction was "
            "necessarily caught. The measure carries no information at zero coverage."
        ),
        "false_conflict_adjudication_rate": 1.0,
        "false_conflict_target": FALSE_CONFLICT_TARGET,
        "false_conflict_target_met": False,
        "false_conflict_margin": 1.0 - FALSE_CONFLICT_TARGET,
        "coverage": 0.0,
        "selective_risk": None,
        "verdict": (
            "One Table 3 clinical target satisfied vacuously; the other missed by the maximum "
            "possible margin. This is the precise sense in which v0.1 is not a positive "
            "data-driven performance result for the substrate."
        ),
    }
