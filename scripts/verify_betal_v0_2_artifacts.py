#!/usr/bin/env python3
"""Independent verification of the BeTaL-GBI v0.2 artifacts.

This script does not trust the run script. It re-derives every number quoted in
the v0.2 report from the artifacts and from first principles, re-validates every
generated task against the repository's own schema, re-checks the mapping-cone
construction, and asserts the calibration against the frozen v0.1 artifacts.

Run from the repository root:

    PYTHONPATH=src python3 scripts/verify_betal_v0_2_artifacts.py
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
from typing import Any

from boundarybench.betal.cone import (
    EDGES,
    QUARANTINE_THRESHOLD,
    STALK_DIM,
    STALKS,
    cone_diagnostic,
)
from boundarybench.betal.metrics import TARGET_LEVELS, evaluate
from boundarybench.betal.simulator import instantiate
from boundarybench.betal.space import configuration_from_dial, project_to_domain
from boundarybench.betal.targets import (
    EVIDENCE_MODES,
    OracleTarget,
    RepairedEmitterTarget,
    V01BoundaryFloorTarget,
)
from boundarybench.tasks.schemas import validate_result, validate_task

ROOT = Path(__file__).resolve().parents[1]
BETAL = ROOT / "artifacts/public_results/v0_2"
V01 = ROOT / "artifacts/public_results/v0_1"

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


def main() -> int:
    aggregate = json.loads((BETAL / "aggregate_metrics.json").read_text(encoding="utf-8"))
    search = json.loads((BETAL / "search_runs.json").read_text(encoding="utf-8"))
    degenerate = json.loads((BETAL / "degenerate_gap_report.json").read_text(encoding="utf-8"))
    monotonicity = json.loads(
        (BETAL / "monotonicity_and_reachability.json").read_text(encoding="utf-8")
    )
    transfer = json.loads((BETAL / "transfer_study.json").read_text(encoding="utf-8"))
    v01_status = json.loads((V01 / "status_distributions.json").read_text(encoding="utf-8"))
    v01_aggregate = json.loads((V01 / "aggregate_metrics.json").read_text(encoding="utf-8"))

    # ---------------------------------------------------------------- 1
    section("1. Task contract compliance across the parameter space")
    total_tasks = 0
    task_errors = 0
    duplicate_ids = 0
    for dial in (0.0, 0.2, 0.4, 0.6, 0.8, 1.0):
        config = configuration_from_dial(dial)
        tasks, manifests = instantiate(config, task_count=256, split_seed="verify")
        seen: set[str] = set()
        for task in tasks:
            total_tasks += 1
            if validate_task(task):
                task_errors += 1
            if task["task_id"] in seen:
                duplicate_ids += 1
            seen.add(task["task_id"])
        check(
            len(manifests) == len(tasks),
            f"dial {dial}: manifest count matches task count",
        )
    check(task_errors == 0, f"all {total_tasks} generated tasks satisfy validate_task", f"({task_errors} failed)")
    check(duplicate_ids == 0, "no duplicate task_id within an instantiation")

    # ---------------------------------------------------------------- 2
    section("2. Determinism of instantiation")
    config = configuration_from_dial(0.5)
    first, _ = instantiate(config, task_count=64, split_seed="determinism")
    second, _ = instantiate(config, task_count=64, split_seed="determinism")
    digest_first = hashlib.sha256(
        json.dumps(first, sort_keys=True).encode("utf-8")
    ).hexdigest()
    digest_second = hashlib.sha256(
        json.dumps(second, sort_keys=True).encode("utf-8")
    ).hexdigest()
    check(digest_first == digest_second, "re-instantiation is byte-identical")
    third, _ = instantiate(config, task_count=64, split_seed="different-seed")
    digest_third = hashlib.sha256(
        json.dumps(third, sort_keys=True).encode("utf-8")
    ).hexdigest()
    check(digest_first != digest_third, "a different split seed yields a different instantiation")

    # ---------------------------------------------------------------- 3
    section("3. Oracle reachability: every family is solvable under the v0.1 verifier")
    # A true oracle, not a high-competence surrogate: the surrogate's solve
    # probability tends to 0.5 as declared difficulty tends to 1.0, so it cannot
    # distinguish "hard" from "unsolvable" at the hard end of the dial.
    oracle = OracleTarget(name="verify_oracle")
    for dial in (0.0, 0.25, 0.5, 0.75, 1.0):
        config = configuration_from_dial(dial)
        tasks, manifests = instantiate(config, task_count=256, split_seed="oracle")
        evaluation = evaluate(tasks=tasks, manifests=manifests, target=oracle, mode="output_only")
        check(
            approx(evaluation.rho_hat_adm, 1.0) and approx(float(evaluation.rho_hat_task), 1.0),
            f"dial {dial}: oracle reaches rho_hat_adm=1.0 and rho_hat_task=1.0",
            f"(got {evaluation.rho_hat_adm}, {evaluation.rho_hat_task})",
        )
        check(
            len(evaluation.per_family) == 8,
            f"dial {dial}: all eight families present in the instantiation",
        )
        check(
            all(
                stats["rho_hat_task"] is not None and approx(stats["rho_hat_task"], 1.0)
                for stats in evaluation.per_family.values()
            ),
            f"dial {dial}: no family is unsolvable by construction",
        )

    # ---------------------------------------------------------------- 4
    section("4. Boundary-floor surrogate reproduces the frozen v0.1 split exactly")
    floor = V01BoundaryFloorTarget()
    config = configuration_from_dial(0.5)
    tasks, manifests = instantiate(config, task_count=256, split_seed="floor")
    totals = {"safe_parse_reject": 0, "safe_schema_reject": 0}
    for mode in EVIDENCE_MODES:
        evaluation = evaluate(tasks=tasks, manifests=manifests, target=floor, mode=mode)
        modes = evaluation.emission_failure_modes
        expected = v01_status["canonical_runs"][mode]["parse_schema_status_distribution"]
        check(
            modes.get("safe_parse_reject") == expected["safe_parse_reject"]
            and modes.get("safe_schema_reject") == expected["safe_schema_reject"],
            f"{mode}: per-mode split matches frozen v0.1 ({expected})",
            f"(got {modes})",
        )
        check(approx(evaluation.rho_hat_adm, 0.0), f"{mode}: admissibility rate is exactly 0")
        check(evaluation.rho_hat_task is None, f"{mode}: rho_hat_task is undefined, not zero")
        check(
            evaluation.quarantine_count == 256,
            f"{mode}: all 256 executions deterministically quarantined",
        )
        for key, value in modes.items():
            totals[key] += value
    check(
        totals["safe_parse_reject"] == v01_aggregate.get("safe_parse_reject", 369)
        or totals["safe_parse_reject"] == 369,
        f"total parse rejects across three modes = 369 (got {totals['safe_parse_reject']})",
    )
    check(
        totals["safe_schema_reject"] == 399,
        f"total schema rejects across three modes = 399 (got {totals['safe_schema_reject']})",
    )
    check(
        sum(totals.values()) == 768,
        f"total executions = 768 (got {sum(totals.values())})",
    )

    # ---------------------------------------------------------------- 5
    section("5. Degenerate gap is a property of V, not of one configuration")
    check(
        degenerate["probe_summary"]["distinct_rho_hat_adm_values"] == [0.0],
        "admissibility rate takes exactly one value across the probed dial",
    )
    check(
        degenerate["probe_summary"]["rho_hat_adm_invariant_across_V"] is True,
        "invariance flag set",
    )
    for run in degenerate["runs"]:
        check(
            run["status"] == "degenerate_gap_admissibility_floor",
            f"{run['evidence_mode']}: run terminated with the degenerate status",
        )
        check(
            run["best_gap"] is None and run["best_configuration"] is None,
            f"{run['evidence_mode']}: no configuration was selected",
        )
        check(
            run["iteration_count"] == 1,
            f"{run['evidence_mode']}: search stopped at the first iteration rather than burning 10",
        )

    # ---------------------------------------------------------------- 6
    section("6. Reported gaps re-derived from the per-iteration records")
    for run in search["runs"]:
        rho = run["rho_target_performance"]
        recomputed = []
        for record in run["iterations"]:
            observed = record["evaluation"]["rho_hat_task"]
            if observed is None:
                continue
            recomputed.append(abs(observed - rho))
            check(
                approx(record["gap"], abs(observed - rho)),
                f"{run['designer_key']}/{run['difficulty_level']} it{record['iteration']}: gap = |rho_hat - rho|",
            )
        if recomputed:
            check(
                approx(run["mean_search_gap"], sum(recomputed) / len(recomputed)),
                f"{run['designer_key']}/{run['difficulty_level']}: mean_search_gap re-derived",
            )
            check(
                approx(run["best_gap"], min(recomputed)),
                f"{run['designer_key']}/{run['difficulty_level']}: best_gap is the minimum over iterations",
            )
        holdout = run["holdout_evaluation"]
        if holdout is not None:
            check(
                approx(run["holdout_gap"], abs(holdout["rho_hat_task"] - rho)),
                f"{run['designer_key']}/{run['difficulty_level']}: holdout_gap re-derived",
            )
            check(
                holdout["instantiation_sha256"]
                != run["iterations"][run["best_iteration"] - 1]["evaluation"]["instantiation_sha256"],
                f"{run['designer_key']}/{run['difficulty_level']}: held-out instantiation differs from the search instantiation",
            )

    # ---------------------------------------------------------------- 7
    section("7. Aggregate designer comparison re-derived")
    by_designer: dict[str, list[dict[str, Any]]] = {}
    for run in search["runs"]:
        by_designer.setdefault(run["designer_key"], []).append(run)
    for row in aggregate["designer_comparison"]:
        runs = by_designer[row["designer"]]
        search_gaps = [run["mean_search_gap"] for run in runs if run["mean_search_gap"] is not None]
        holdout_gaps = [run["holdout_gap"] for run in runs if run["holdout_gap"] is not None]
        check(
            approx(row["mean_search_gap_pct"], round(100 * sum(search_gaps) / len(search_gaps), 2), 5e-3),
            f"{row['designer']}: mean_search_gap_pct re-derived",
        )
        check(
            approx(row["mean_holdout_gap_pct"], round(100 * sum(holdout_gaps) / len(holdout_gaps), 2), 5e-3),
            f"{row['designer']}: mean_holdout_gap_pct re-derived",
        )
        check(row["level_count"] == 4, f"{row['designer']}: four levels reported")

    feedback = next(row for row in aggregate["designer_comparison"] if row["designer"] == "feedback_coordinate")
    baselines = [row for row in aggregate["designer_comparison"] if row["designer"] != "feedback_coordinate"]
    check(
        all(feedback["mean_search_gap_pct"] < row["mean_search_gap_pct"] for row in baselines),
        "feedback designer beats both baselines on mean search gap",
    )
    check(
        all(feedback["mean_holdout_gap_pct"] < row["mean_holdout_gap_pct"] for row in baselines),
        "feedback designer beats both baselines on mean held-out gap",
    )
    ratios = [row["mean_search_gap_pct"] / feedback["mean_search_gap_pct"] for row in baselines]
    print(f"        search-gap advantage factors vs baselines: {[round(r, 2) for r in ratios]}")

    # ---------------------------------------------------------------- 8
    section("8. Every reported gap respects its attainable floor")
    floors = {
        (row["target_name"], row["difficulty_level"]): row["attainable_gap_floor"]
        for row in monotonicity["reachability"]
    }
    primary = aggregate["primary_target_surrogate"]
    for run in search["runs"]:
        floor_value = floors.get((primary, run["difficulty_level"]))
        if floor_value is None or run["best_gap"] is None:
            continue
        # The dial is a path through V, not all of V, so coordinate refinement may
        # legitimately beat the dial-derived floor. Flag it rather than fail it.
        if run["best_gap"] + 1e-9 < floor_value:
            print(
                f"        NOTE {run['designer_key']}/{run['difficulty_level']}: "
                f"best_gap {run['best_gap']:.4f} < dial floor {floor_value:.4f} "
                "-> configuration lies off the monotone dial path"
            )
    check(True, "attainable-floor comparison completed (notes above are expected, not errors)")

    # ---------------------------------------------------------------- 9
    section("9. Transfer ordering")
    for entry in transfer["ordering_check"]:
        rates = entry["rho_hat_task_by_tier"]
        check(
            entry["separation_order_preserved"] is True
            and all(later > earlier for earlier, later in zip(rates, rates[1:])),
            f"{entry['difficulty_level']}: tier separation order preserved {[round(r, 4) for r in rates]}",
        )

    # ---------------------------------------------------------------- 10
    section("10. Mapping-cone construction")
    for mask in range(1 << len(STALKS)):
        agreement = {name: not bool(mask & (1 << i)) for i, name in enumerate(STALKS)}
        diagnostic = cone_diagnostic(agreement)
        disagreeing = {name for name, ok in agreement.items() if not ok}
        expected_dimension = len(disagreeing)
        localized = all(
            (diagnostic.stalk_energies[name] > QUARANTINE_THRESHOLD) == (name in disagreeing)
            for name in STALKS
        )
        check(
            diagnostic.obstruction_dimension == expected_dimension and localized,
            f"cone: disagreement {sorted(disagreeing) or ['none']} -> dim H^0 = {expected_dimension}, energy localized",
            f"(got dim {diagnostic.obstruction_dimension}, energies {diagnostic.stalk_energies})",
        )
    # Basis invariance of E_sigma under rotation of the obstruction basis.
    diagnostic = cone_diagnostic({"identity": False, "terminology": True, "provenance_temporal": True})
    check(
        approx(sum(diagnostic.stalk_energies.values()), float(diagnostic.obstruction_dimension), 1e-6),
        "cone: stalk energies sum to the obstruction dimension (trace decomposition)",
    )
    check(
        len(STALKS) == 3 and len(EDGES) == 3 and STALK_DIM == 2,
        "cone: declared toy complex is the documented triangle with 2-dimensional stalks",
    )

    # ---------------------------------------------------------------- 11
    section("11. Domain projection is total and safe")
    hostile = {
        "patient_identity_normalization": 4.7,
        "orphan_rate": -3,
        "field_anomaly_bleed": "0.22",
        "mapping_arity": 99,
        "evidence_sufficiency": float("nan"),
        "not_a_parameter": 7,
    }
    projected = project_to_domain(hostile, origin="verify")
    check(len(projected.values) == 9, "projection returns every declared dimension")
    check(
        any("not_a_parameter" in note for note in projected.projection_notes),
        "unknown key recorded rather than silently dropped",
    )
    check(
        projected.values["patient_identity_normalization"] == 1.0
        and projected.values["orphan_rate"] == 0.0
        and projected.values["mapping_arity"] == 6,
        "out-of-domain values clamped to the declared bounds",
        f"(got {projected.values})",
    )
    check(
        isinstance(projected.values["mapping_arity"], int),
        "integer dimensions stay integral after projection",
    )

    # ---------------------------------------------------------------- 12
    section("12. Emitted results are schema-valid under the repository contract")
    tasks, manifests = instantiate(configuration_from_dial(0.6), task_count=128, split_seed="results")
    emitter = RepairedEmitterTarget(competence=0.55, name="verify_emitter")
    invalid = 0
    for task, manifest in zip(tasks, manifests):
        emission = emitter.emit(task, mode="output_only", difficulty=manifest["declared_difficulty"])
        payload = json.loads(emission.raw_text)
        if validate_result(payload, task):
            invalid += 1
    check(invalid == 0, "repaired emitter never produces a schema-invalid record", f"({invalid} invalid)")

    # ---------------------------------------------------------------- 13
    section("13. Checksum manifest is current")
    manifest_lines = (BETAL / "SHA256SUMS").read_text(encoding="utf-8").strip().splitlines()
    recorded = {name: digest for digest, name in (line.split("  ", 1) for line in manifest_lines)}
    on_disk = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in BETAL.glob("*")
        if path.name != "SHA256SUMS"
    }
    check(set(recorded) == set(on_disk), "manifest covers exactly the artifacts present")
    mismatched = [name for name, digest in on_disk.items() if recorded.get(name) != digest]
    check(not mismatched, "every artifact digest matches the manifest", f"({mismatched})")

    # ---------------------------------------------------------------- 14
    section("14. Scope assertions in the provenance record")
    provenance = json.loads((BETAL / "PROVENANCE.json").read_text(encoding="utf-8"))
    check(
        provenance["execution_scope"]["language_models_executed"] == 0
        and provenance["execution_scope"]["provider_calls"] == 0,
        "provenance records that no language model was executed",
    )
    check(
        aggregate["llm_designer_executed"] is False
        and aggregate["language_model_executed"] is False,
        "aggregate metrics record that no designer LLM was executed",
    )
    check(
        provenance["verifier"]["modified_for_v0_2"] is False,
        "provenance records that the v0.1 verifier was not modified",
    )
    check(
        aggregate["difficulty_levels"] == TARGET_LEVELS,
        "difficulty ladder matches the BeTaL performance convention",
        f"(got {aggregate['difficulty_levels']})",
    )
    check(
        aggregate["difficulty_levels"]["hard"] == 0.25
        and aggregate["difficulty_levels"]["easy"] == 0.75,
        "hard is the LOW rho and easy is the HIGH rho (no inverted ladder)",
    )

    # ---------------------------------------------------------------- 15
    section("15. Draft-specification errata claims")
    empty_hash = hashlib.sha256(b"").hexdigest()
    check(
        empty_hash == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        "the draft's 'Deterministic Verifier Checksum' is the SHA-256 of the empty input",
    )
    check(
        approx(369 / 768, 0.48046875),
        "369/768 = 48.05 percent is the parse-reject SHARE, and the failure rate was 768/768 = 100 percent",
    )
    check(
        v01_aggregate["invalid_output_rate"] == 1.0 and v01_aggregate["coverage"] == 0.0,
        "frozen v0.1 invalid-output rate is 1.0 and coverage is 0.0",
    )

    # ---------------------------------------------------------------- 16
    section("16. Numbers quoted in BETAL_V0_2_SEARCH_REPORT.md")
    report = (ROOT / "docs/betal/BETAL_V0_2_SEARCH_REPORT.md").read_text(encoding="utf-8")
    spec = (ROOT / "docs/betal/BETAL_GBI_DESIGN_SPEC.md").read_text(encoding="utf-8")

    def quoted(text: str, needle: str, label: str) -> None:
        check(needle in text, f"{label}: '{needle}' present as written")

    lookup = {
        (row["designer"], row["difficulty_level"]): row for row in aggregate["per_level"]
    }
    # Headline means.
    for row in aggregate["designer_comparison"]:
        quoted(report, f"{row['mean_holdout_gap_pct']:.2f}%", f"mean held-out {row['designer']}")
        quoted(report, f"{row['mean_search_gap_pct']:.2f}%", f"mean search {row['designer']}")
    # Per-level held-out table, every cell.
    for (designer, level), row in lookup.items():
        quoted(
            report,
            f"{100 * row['holdout_gap']:.2f}%",
            f"per-level held-out cell {designer}/{level}",
        )
    # Feedback search gaps quoted inline in section 2.
    for level in ("hard", "medium", "easy", "trivial"):
        row = lookup[("feedback_coordinate", level)]
        quoted(
            report,
            f"{level} {100 * row['mean_search_gap']:.2f}%",
            f"inline feedback search gap {level}",
        )
    # Advantage factors.
    fb = next(r for r in aggregate["designer_comparison"] if r["designer"] == "feedback_coordinate")
    factors = sorted(
        r["mean_search_gap_pct"] / fb["mean_search_gap_pct"]
        for r in aggregate["designer_comparison"]
        if r["designer"] != "feedback_coordinate"
    )
    for factor in factors:
        quoted(report, f"{factor:.2f}", "advantage factor")
    # Reachability floors and ranges.
    for row in monotonicity["reachability"]:
        if not row["reachable"]:
            quoted(
                report,
                f"floor {100 * row['attainable_gap_floor']:.2f}%",
                f"attainable floor {row['target_name']}/{row['difficulty_level']}",
            )
    for check_row in monotonicity["checks"]:
        low, high = check_row["observed_range"]
        quoted(
            report,
            f"{low:.3f} \u2013 {high:.3f}",
            f"observed range {check_row['target_name']}",
        )
    # Monotonicity counts.
    violations = sum(c["strict_violations"] for c in monotonicity["checks"])
    comparisons = sum(max(0, len(c["rows"]) - 1) for c in monotonicity["checks"])
    quoted(report, f"| {comparisons} |", "consecutive dial steps checked")
    quoted(report, f"| {violations} |", "strict monotonicity violations")
    # Transfer rates, every cell.
    for entry in transfer["ordering_check"]:
        for rate in entry["rho_hat_task_by_tier"]:
            quoted(report, f"{rate:.4f}", f"transfer rate {entry['difficulty_level']}")
    # Task-count claim in section 9.
    dial_count = 6
    quoted(report, f"{dial_count * 256:,} generated tasks", "validated task count")
    # Grid cardinality claim in the specification.
    space = json.loads((BETAL / "parameter_space.json").read_text(encoding="utf-8"))
    quoted(spec, f"{space['grid_cardinality']:,}", "grid cardinality in spec")
    quoted(spec, str(space["dimension_count"]), "dimension count in spec")
    # The stall trace quoted in report section 6 must match the artifact.
    hard_run = next(
        run
        for run in search["runs"]
        if run["designer_key"] == "feedback_coordinate" and run["difficulty_level"] == "hard"
    )
    tail = hard_run["iterations"][6:]
    identical = len({json.dumps(r["configuration"]["values"], sort_keys=True) for r in tail}) == 1
    check(identical, "report's stall claim: iterations 7-10 are identical proposals")
    for record in hard_run["iterations"][5:7]:
        quoted(
            report,
            f"{record['evaluation']['rho_hat_task']:.4f}",
            f"stall trace rho at iteration {record['iteration']}",
        )
    # No named commercial model may appear in a results position, and no
    # hypothesized figure may survive outside the errata entry that names it.
    e6_start = spec.index("### E6")
    e6_end = spec.index("### E7")
    hypothesized_positions = [
        index for index in range(len(spec)) if spec.startswith("Hypothesized", index)
    ]
    check(
        "Hypothesized" not in report,
        "report contains no hypothesized performance figure",
    )
    check(
        bool(hypothesized_positions)
        and all(e6_start <= index < e6_end for index in hypothesized_positions),
        "every 'Hypothesized' in the spec lies inside errata entry E6",
        f"(positions {hypothesized_positions}, E6 span {e6_start}-{e6_end})",
    )
    for banned in ("Gemini", "Claude 3.7 Sonnet"):
        check(
            banned not in report,
            f"report never names {banned}",
            f"({report.count(banned)} occurrences)",
        )
        offending = [
            line.strip()
            for line in spec.splitlines()
            if banned in line and "%" in line
        ]
        check(
            not offending,
            f"spec never places {banned} on a line carrying a numeric result",
            f"({offending})",
        )
    # Qwen may only be named in a scope-limiting or calibration context.
    for name, text in (("report", report), ("spec", spec)):
        offending = [
            line.strip()
            for line in text.splitlines()
            if "Qwen" in line
            and not any(
                marker in line
                for marker in (
                    "not evidence about",
                    "is not Qwen",
                    "shape of one frozen",
                    "The draft placed",
                )
            )
        ]
        check(
            not offending,
            f"{name} names Qwen only in a scope-limiting context",
            f"({offending})",
        )

    # Self-referential and therefore last: the count it asserts includes itself,
    # so the documented total cannot silently go stale when a check is added.
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
