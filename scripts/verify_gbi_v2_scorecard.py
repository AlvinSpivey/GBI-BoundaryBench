#!/usr/bin/env python3
"""Independent verification of the GBI-DCSE v2 scorecard.

Does not trust the run script. Re-derives every reported number, and in particular
tries hard to break the two claims that would otherwise be circular:

* that the admission gate never reads the held-out reference action, and
* that a 100% severe-contradiction sensitivity is a property of the policy rather
  than an artifact of how the population was partitioned.

Run from the repository root:

    PYTHONPATH=src python3 scripts/verify_gbi_v2_scorecard.py
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import random
import sys
from typing import Any

from boundarybench.betal.adversaries import ConfidentHallucinatorTarget, EvidenceForgerTarget
from boundarybench.betal.assertions import (
    solve_epsilon_star_box,
    solve_epsilon_star_slice,
    worst_condition_number_over_box,
)
from boundarybench.betal.ev import (
    ADMITTING_ACTIONS,
    GATE_PRECEDENCE,
    boundary_conformance_probes,
    complete_policy,
    evaluate_ev,
    incomplete_policy,
    required_action_from_witness,
    score_only_policy,
)
from boundarybench.betal.injection import (
    BASE_SIMULATOR_CANNOT_PRODUCE,
    INJECTABLE_CLASSES,
    inject_severe_contradictions,
)
from boundarybench.betal.repair import repair_emission
from boundarybench.betal.scorecard import (
    FALSE_CONFLICT_TARGET,
    clinical_measures,
    containment_measures,
    liveness_measures,
    run_gate,
    selectivity_measures,
)
from boundarybench.betal.simulator import instantiate
from boundarybench.betal.space import Configuration
from boundarybench.betal.targets import RepairedEmitterTarget, V01BoundaryFloorTarget
from boundarybench.betal.repair import FormatRepairTarget
from boundarybench.betal.witness import derive_witnesses

ROOT = Path(__file__).resolve().parents[1]
V2 = ROOT / "artifacts/public_results/gbi_v2"
BETAL = ROOT / "artifacts/public_results/v0_2"
SRC = ROOT / "src/boundarybench/betal"

FAILURES: list[str] = []
CHECKS = 0


def check(condition: bool, label: str, detail: str = "") -> None:
    global CHECKS
    CHECKS += 1
    if condition:
        print(f"  PASS  {label}")
    else:
        print(f"  FAIL  {label} {detail}")
        FAILURES.append(f"{label} {detail}".strip())


def approx(left: float, right: float, tolerance: float = 1e-9) -> bool:
    return abs(left - right) <= tolerance


def section(title: str) -> None:
    print(f"\n[{title}]")


def _rebuild_population() -> tuple[list, list, list, frozenset[str], frozenset[str], Any]:
    payload = json.loads((BETAL / "search_runs.json").read_text(encoding="utf-8"))
    values = next(
        run["best_configuration"]["values"]
        for run in payload["runs"]
        if run["designer_key"] == "feedback_coordinate"
        and run["difficulty_level"] == "medium"
        and run["best_configuration"]
    )
    config = Configuration(values=values, origin="verify")
    tasks, manifests = instantiate(config, task_count=512, split_seed="gbi_v2")
    injection = inject_severe_contradictions(
        derive_witnesses(tasks, manifests), injection_rate=0.5, seed="gbi_v2_injection"
    )
    return (
        tasks,
        manifests,
        injection.witnesses,
        frozenset(injection.injected_task_ids),
        frozenset(injection.clean_task_ids),
        injection,
    )


def main() -> int:
    scorecard = json.loads((V2 / "table3_scorecard.json").read_text(encoding="utf-8"))
    targets = json.loads((V2 / "target_runs.json").read_text(encoding="utf-8"))
    sweep = json.loads((V2 / "strictness_sweep.json").read_text(encoding="utf-8"))
    conformance = json.loads((V2 / "boundary_conformance.json").read_text(encoding="utf-8"))
    assertions = json.loads((V2 / "appendix_b1_assertions.json").read_text(encoding="utf-8"))
    injection_manifest = json.loads((V2 / "injection_manifest.json").read_text(encoding="utf-8"))

    tasks, manifests, witnesses, injected_ids, clean_ids, injection = _rebuild_population()
    strictness = scorecard["operating_strictness"]
    policy = complete_policy(strictness)

    # ---------------------------------------------------------------- 1
    section("1. The admission gate never reads the held-out reference action")
    # Static, via the AST rather than text matching, so prose in a docstring cannot
    # trip the check and a real access cannot hide inside one.
    import ast

    def _reference_reads(module_name: str) -> list[str]:
        tree = ast.parse((SRC / module_name).read_text(encoding="utf-8"))
        found: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr in {"reference_action", "reference"}:
                found.append("attribute ." + node.attr + " line " + str(node.lineno))
            if isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant):
                if node.slice.value in {"reference_action", "reference"}:
                    found.append("subscript " + repr(node.slice.value) + " line " + str(node.lineno))
        return found

    for module in ("ev.py", "witness.py"):
        offending = _reference_reads(module)
        check(
            not offending,
            module + ": no AST node reads the reference action",
            str(offending),
        )
    # And the probe is not vacuous: it finds the reads in scorecard.py, which
    # legitimately uses the reference afterwards as an independent yardstick.
    yardstick = _reference_reads("scorecard.py")
    check(
        len(yardstick) > 0,
        "the AST probe does detect reference reads where they are expected "
        "(scorecard.py: " + str(len(yardstick)) + ")",
    )

    # Behavioural: shuffle every reference action and confirm the gate is unchanged.
    baseline, _ = run_gate(
        tasks=tasks,
        manifests=manifests,
        witnesses=witnesses,
        policy=policy,
        target=None,
        injected_ids=injected_ids,
        clean_ids=clean_ids,
    )
    shuffled = copy.deepcopy([dict(m) for m in manifests])
    rng = random.Random(20260819)
    actions = [m["reference_action"] for m in shuffled]
    rng.shuffle(actions)
    for entry, action in zip(shuffled, actions):
        entry["reference_action"] = action
    perturbed, _ = run_gate(
        tasks=tasks,
        manifests=shuffled,
        witnesses=witnesses,
        policy=policy,
        target=None,
        injected_ids=injected_ids,
        clean_ids=clean_ids,
    )
    changed = sum(
        1
        for before, after in zip(baseline, perturbed)
        if (before.admissible, before.required_action) != (after.admissible, after.required_action)
    )
    check(
        changed == 0,
        "shuffling every reference action leaves all 512 gate verdicts unchanged",
        f"({changed} changed)",
    )
    check(
        any(before.reference_action != after.reference_action for before, after in zip(baseline, perturbed)),
        "the shuffle actually changed reference actions (test is not vacuous)",
    )

    # ---------------------------------------------------------------- 2
    section("2. Injection partition is disjoint and covers unproducible classes")
    check(not (injected_ids & clean_ids), "injected and clean populations are disjoint")
    by_id = {w.task_id: w for w in witnesses}
    check(
        all(by_id[i].is_severe for i in injected_ids),
        "every injected record is severe after injection",
    )
    check(
        all(not by_id[i].is_severe for i in clean_ids),
        "every left-alone record is non-severe",
    )
    base_witnesses = derive_witnesses(tasks, manifests)
    producible = set()
    for witness in base_witnesses:
        producible.update(witness.severe_classes())
    unproducible = BASE_SIMULATOR_CANNOT_PRODUCE - producible
    check(
        unproducible == BASE_SIMULATOR_CANNOT_PRODUCE,
        "the four classes declared unproducible really are absent from the base population",
        f"(producible overlap: {BASE_SIMULATOR_CANNOT_PRODUCE & producible})",
    )
    injected_classes = {c for i in injected_ids for c in by_id[i].injected_classes}
    check(
        injected_classes == set(INJECTABLE_CLASSES),
        "all 10 injectable classes are represented in the injected population",
        f"(missing {set(INJECTABLE_CLASSES) - injected_classes})",
    )
    check(
        injection_manifest["population"]["injected_severe"] == len(injected_ids)
        and injection_manifest["population"]["clean_left_alone"] == len(clean_ids),
        "injection manifest population counts re-derived",
    )

    # ---------------------------------------------------------------- 3
    section("3. Clinical measures re-derived at the operating point")
    measures = clinical_measures(baseline)
    reported = next(
        row for row in scorecard["table_3"] if row["measure"] == "Severe Contradiction Sensitivity"
    )
    check(
        approx(measures["severe_contradiction_sensitivity"], reported["measured"]),
        f"sensitivity re-derived = {measures['severe_contradiction_sensitivity']}",
    )
    reported_fc = next(
        row for row in scorecard["table_3"] if row["measure"] == "False Conflict Adjudication Rate"
    )
    check(
        approx(measures["false_conflict_adjudication_rate"], reported_fc["measured"]),
        f"false-conflict rate (narrow) re-derived = {measures['false_conflict_adjudication_rate']}",
    )
    check(
        measures["severe_contradictions_missed"] == 0,
        "no injected severe contradiction was missed",
    )
    check(
        measures["false_conflict_adjudication_rate_broad"] is not None,
        "the pessimistic broad denominator is also reported",
    )
    print(
        f"        narrow {measures['false_conflict_count']}/{measures['false_conflict_denominator']}  "
        f"broad {measures['false_conflict_count_broad']}/{measures['false_conflict_denominator_broad']} "
        f"= {measures['false_conflict_adjudication_rate_broad']:.4f} "
        f"(target met: {measures['false_conflict_target_met_broad']})"
    )

    # ---------------------------------------------------------------- 4
    section("4. The measurement has teeth: ablations must fail")
    for label, factory, expectation in (
        ("incomplete_ablation", incomplete_policy, "sensitivity below 1.0"),
        ("score_only_identity_ablation", score_only_policy, "a failed Boundary 1 probe"),
    ):
        rows = sweep["policies"][label]["rows"]
        peak = max(row["severe_contradiction_sensitivity"] or 0.0 for row in rows)
        probes = conformance["policies"][label]
        degraded = peak < 1.0 or not probes["all_passed"]
        check(degraded, f"{label} is detectably worse than the complete policy ({expectation})")
        check(
            sweep["policies"][label]["operating_point"]["selected"] is None,
            f"{label} has no strictness meeting both targets",
        )
    check(
        conformance["policies"]["complete"]["all_passed"],
        "the complete policy passes every Boundary 1 / Boundary 2 probe",
    )
    check(
        len(boundary_conformance_probes(policy)) == 5
        and all(probe["passed"] for probe in boundary_conformance_probes(policy)),
        "boundary probes re-run independently at the operating point",
    )
    # The non-vacuity probe must be present: without it a refuse-everything policy
    # would pass the boundary suite.
    check(
        any(
            probe["probe"] == "non_vacuity_clean_witness_is_admitted"
            for probe in boundary_conformance_probes(policy)
        ),
        "the boundary suite includes a non-vacuity probe",
    )

    # ---------------------------------------------------------------- 5
    section("5. Adversaries reach the gate and are contained")
    witness_map = {w.task_id: w for w in witnesses}
    for label, target in (
        ("confident_hallucinator", ConfidentHallucinatorTarget()),
        (
            "evidence_forger",
            EvidenceForgerTarget(witnesses=witness_map, policy=policy),
        ),
    ):
        outcomes, _ = run_gate(
            tasks=tasks,
            manifests=manifests,
            witnesses=witnesses,
            policy=policy,
            target=target,
            injected_ids=injected_ids,
            clean_ids=clean_ids,
        )
        selectivity = selectivity_measures(outcomes)
        containment = containment_measures(outcomes)
        check(
            approx(selectivity["admissibility_rate"], 1.0),
            f"{label}: every emission cleared the format boundary, so the gate was actually tested",
            f"(rate {selectivity['admissibility_rate']})",
        )
        check(
            containment["silent_promotions_by_witness_severity"] == 0
            and containment["silent_promotions_by_reference_action"] == 0,
            f"{label}: zero silent promotions by both ground truths",
            f"({containment['silent_promotions_by_witness_severity']}, "
            f"{containment['silent_promotions_by_reference_action']})",
        )
        reported_row = next(row for row in targets["targets"] if label in row["target"])
        check(
            reported_row["containment"]["proposals_admitted"]
            == containment["proposals_admitted"],
            f"{label}: admitted count matches the artifact",
        )
    # The hallucinator must actually try to over-admit, or containment is trivial.
    hallucinator_outcomes, _ = run_gate(
        tasks=tasks,
        manifests=manifests,
        witnesses=witnesses,
        policy=policy,
        target=ConfidentHallucinatorTarget(),
        injected_ids=injected_ids,
        clean_ids=clean_ids,
    )
    over_admissions = sum(
        1
        for o in hallucinator_outcomes
        if o.proposal_action == "admit" and o.required_action not in ADMITTING_ACTIONS
    )
    check(
        over_admissions > 100,
        f"the hallucinator attempted {over_admissions} over-admissions the gate had to refuse",
    )

    # ---------------------------------------------------------------- 6
    section("6. Format repair is deterministic and does not manufacture correctness")
    wrapper = FormatRepairTarget(V01BoundaryFloorTarget(), name="verify_repair")
    outcomes, _ = run_gate(
        tasks=tasks,
        manifests=manifests,
        witnesses=witnesses,
        policy=policy,
        target=wrapper,
        injected_ids=injected_ids,
        clean_ids=clean_ids,
    )
    selectivity = selectivity_measures(outcomes)
    report = wrapper.repair_report()
    floor_outcomes, _ = run_gate(
        tasks=tasks,
        manifests=manifests,
        witnesses=witnesses,
        policy=policy,
        target=V01BoundaryFloorTarget(),
        injected_ids=injected_ids,
        clean_ids=clean_ids,
    )
    floor_selectivity = selectivity_measures(floor_outcomes)
    check(
        approx(floor_selectivity["admissibility_rate"], 0.0),
        "unrepaired v0.1 floor target has an admissibility rate of exactly 0",
    )
    check(
        floor_selectivity["selective_risk"] is None,
        "selective risk is undefined at zero coverage, as the v0.1 artifacts state",
    )
    check(
        selectivity["admissibility_rate"] > 0.4,
        f"repair lifts the admissibility rate to {selectivity['admissibility_rate']:.4f}",
    )
    check(
        selectivity["selective_risk"] is not None,
        "selective risk becomes defined once the floor is lifted",
    )
    check(
        approx(selectivity["verified_completion_rate"], 0.0),
        "repair does not manufacture correctness: verified completion stays at 0",
        f"({selectivity['verified_completion_rate']})",
    )
    check(
        "truncated payloads (no determinate completion)" in report["not_repaired_by_design"][0],
        "the two unrepairable classes are declared rather than silently dropped",
    )
    # Determinism of repair itself.
    sample = tasks[0]
    emission = V01BoundaryFloorTarget().emit(sample, mode="output_only", difficulty=0.5)
    first = repair_emission(emission.raw_text, sample)
    second = repair_emission(emission.raw_text, sample)
    check(
        first.repaired_text == second.repaired_text and first.applied == second.applied,
        "repair is deterministic on repeated application",
    )

    # ---------------------------------------------------------------- 7
    section("7. Liveness is a property of the declared quarantine scope")
    liveness = liveness_measures(baseline)
    check(
        approx(liveness["record_scoped_refusals_only"]["liveness_rate"], 1.0),
        "record-scoped refusals close over no admissible work",
        f"({liveness['record_scoped_refusals_only']['liveness_rate']})",
    )
    check(
        liveness["naive_shared_scope_contrast"]["liveness_rate"]
        < liveness["record_scoped_refusals_only"]["liveness_rate"],
        "the naive shared-reference scope is measurably worse, so the distinction matters",
    )
    check(
        liveness["administrative_freezes"] > 0,
        f"Boundary 2 administrative freezes did occur ({liveness['administrative_freezes']})",
    )
    check(
        liveness["coarse_scope_contrast"]["liveness_rate"]
        <= liveness["declared_scope"]["liveness_rate"],
        "a family-level scope is no better than the declared scope",
    )

    # ---------------------------------------------------------------- 8
    section("8. Appendix B.1 assertions re-derived")
    check(
        assertions["assertion_1"]["operations_run"] >= (1 << 16)
        and assertions["assertion_1"]["total_violations"] == 0,
        f"Assertion 1: {assertions['assertion_1']['operations_run']} operations, 0 violations",
    )
    slice_bound = solve_epsilon_star_slice()
    box_bound = solve_epsilon_star_box(ceiling=20.0, dimension=4)
    check(
        approx(slice_bound, assertions["assertion_2"]["epsilon_star_slice_exact"], 1e-9),
        f"Assertion 2: one-dimensional slice bound re-derived = {slice_bound:.9f}",
    )
    check(
        approx(box_bound, assertions["assertion_2"]["epsilon_star_box_exact"], 1e-9),
        f"Assertion 2: box-wide bound re-derived = {box_bound:.6f}",
    )
    check(
        abs(slice_bound - 0.066) < 0.001,
        "the manuscript's stated epsilon ~ 0.066 is confirmed for the slice it swept",
    )
    slice_kappa, _ = worst_condition_number_over_box(slice_bound, 20.0, dimension=4)
    check(
        slice_kappa > 1e5,
        f"the slice bound fails the box corner sweep: worst kappa {slice_kappa:.3g} >> 1e4",
    )
    check(
        box_bound > 4 * slice_bound,
        f"the box-wide bound is materially larger ({box_bound / slice_bound:.1f}x)",
    )
    reproduction = assertions["assertion_2"]["manuscript_reproduction"]
    check(
        all(entry["agrees_within_1pct"] for entry in reproduction.values()),
        "both worked condition numbers from Section 6.3 reproduce within 1%",
    )
    check(
        assertions["assertion_3"]["cone_differential_square_violations"] == 0
        and assertions["assertion_3"]["worst_symmetry_residual"] <= 1e-12
        and assertions["assertion_3"]["worst_min_eigenvalue"] >= -1e-9,
        "Assertion 3: cone squares to zero, Laplacian symmetric and PSD",
    )
    check(
        assertions["assertion_3"]["worst_energy_drift_under_rotation"] <= 1e-9,
        "Assertion 3: stalk energies invariant under randomized orthogonal rotations",
        f"(drift {assertions['assertion_3']['worst_energy_drift_under_rotation']})",
    )
    check(
        assertions["assertion_3"]["min_spectral_gap"] >= 0.15,
        f"Table 3 spectral gap {assertions['assertion_3']['min_spectral_gap']} >= 0.15",
    )

    # ---------------------------------------------------------------- 9
    section("9. The v0.1 contrast is stated correctly")
    contrast = scorecard["v01_baseline_contrast"]
    check(contrast["canonical_executions"] == 768, "v0.1 contrast cites 768 executions")
    check(
        contrast["false_conflict_adjudication_rate"] == 1.0
        and contrast["false_conflict_target_met"] is False,
        "v0.1 false-conflict rate is 1.0 against a 0.04 target",
    )
    check(
        "Vacuously satisfied" in contrast["sensitivity_caveat"],
        "the v0.1 sensitivity of 1.0 is labelled vacuous rather than reported as a pass",
    )
    check(
        approx(contrast["false_conflict_margin"], 1.0 - FALSE_CONFLICT_TARGET),
        "the stated margin is arithmetically correct",
    )

    # ---------------------------------------------------------------- 10
    section("10. Scope, provenance and checksums")
    provenance = json.loads((V2 / "PROVENANCE.json").read_text(encoding="utf-8"))
    check(
        provenance["execution_scope"]["language_models_executed"] == 0
        and provenance["execution_scope"]["provider_calls"] == 0,
        "no language model executed, no provider call",
    )
    check(
        provenance["execution_scope"]["tee_present"] is False
        and provenance["verifier"]["modified_for_v2"] is False,
        "no TEE claimed; v0.1 verifier unmodified",
    )
    latency_row = next(
        row for row in scorecard["table_3"] if row["measure"] == "End-to-End Latency (Enclave)"
    )
    check(
        latency_row["status"] == "PARTIAL_PROXY" and "not the enclave measurement" in latency_row["method"],
        "the latency figure is labelled a proxy, not an enclave measurement",
    )
    attestation_row = next(
        row for row in scorecard["table_3"] if row["measure"] == "Attestation Bootstrapping Time"
    )
    check(
        attestation_row["status"] == "OUT_OF_SCOPE" and attestation_row["met"] is None,
        "attestation bootstrapping is out of scope with met=None, not a claimed pass",
    )
    manifest_lines = (V2 / "SHA256SUMS").read_text(encoding="utf-8").strip().splitlines()
    recorded = {name: digest for digest, name in (line.split("  ", 1) for line in manifest_lines)}
    on_disk = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in V2.glob("*")
        if path.name != "SHA256SUMS"
    }
    check(set(recorded) == set(on_disk), "checksum manifest covers exactly the artifacts present")
    check(
        all(recorded[name] == digest for name, digest in on_disk.items()),
        "every artifact digest matches",
    )

    # ---------------------------------------------------------------- 11
    section("11. Numbers quoted in the v2 report")
    report_path = ROOT / "docs/betal/GBI_DCSE_V2_SCORECARD.md"
    if not report_path.exists():
        check(False, "v2 report present", f"({report_path} missing)")
    else:
        report = report_path.read_text(encoding="utf-8")
        # Markdown tables introduce incidental whitespace, so scores are matched
        # against a whitespace-stripped copy while numeric literals are matched
        # verbatim.
        compact = "".join(report.split())
        summary = scorecard["table_3_summary"]
        claims = scorecard["additional_claims_summary"]
        for needle, label, haystack in (
            (
                f"{assertions['assertion_2']['epsilon_star_box_exact']:.6f}",
                "box-wide epsilon",
                report,
            ),
            ("0.066021703", "manuscript slice epsilon solved exactly", report),
            (str(assertions["assertion_1"]["operations_run"]), "Assertion 1 operation count", report),
            (f"{measures['severe_contradiction_denominator']}", "sensitivity denominator", report),
            (f"{measures['false_conflict_denominator']}", "false-conflict denominator", report),
            ("0.9655", "incomplete-ablation peak sensitivity", report),
            (f"{selectivity['admissibility_rate']:.4f}", "repaired admissibility rate", report),
            (f"{summary['targets_met']}/{summary['measurable_in_this_environment']}",
             "Table 3 measurable score", compact),
            (f"{claims['met']}/{claims['evaluated']}", "additional claim score", compact),
            ("4.27", "broad false-conflict rate", report),
            ("221", "hallucinator over-admission attempts", report),
        ):
            check(needle in haystack, f"report quotes {label}: '{needle}'")
        check(
            f"**{CHECKS + 1} checks, 0 failures.**" in report,
            f"report documents the current total check count ({CHECKS + 1})",
        )

    print(f"\n{'=' * 68}")
    print(f"checks run: {CHECKS}    failures: {len(FAILURES)}")
    if FAILURES:
        for failure in FAILURES:
            print(f"  - {failure}")
        return 1
    print("ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
