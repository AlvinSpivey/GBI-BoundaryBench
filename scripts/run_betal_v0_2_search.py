#!/usr/bin/env python3
"""Execute the BeTaL-GBI v0.2 parameter search and write public-safe artifacts.

Run from the repository root:

    PYTHONPATH=src python3 scripts/run_betal_v0_2_search.py

Everything this script writes is derived from declared target surrogates and the
deterministic simulator. It executes no language model, contacts no provider, and
reads no held-out reference material.
"""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import statistics
import sys
from typing import Any

from boundarybench.betal.cone import reference_table
from boundarybench.betal.designer import (
    BestOfNDesigner,
    DESIGNER_SYSTEM_PROMPT,
    FeedbackCoordinateDesigner,
    RandomSamplingPPRDesigner,
    render_designer_prompt,
)
from boundarybench.betal.loop import (
    LOOP_VERSION,
    monotonicity_check,
    run_search,
    space_and_versions,
    transfer_study,
)
from boundarybench.betal.metrics import LEVEL_ORDER, TARGET_LEVELS, failure_rate_view
from boundarybench.betal.simulator import SIMULATOR_VERSION
from boundarybench.betal.space import SPACE_VERSION, grid_cardinality, space_manifest
from boundarybench.betal.targets import (
    EVIDENCE_MODES,
    RepairedEmitterTarget,
    TARGETS_VERSION,
    TRANSFER_TIERS,
    V01BoundaryFloorTarget,
)

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts/public_results/v0_2"

TASK_COUNT = 256
ITERATIONS = 10
PRIMARY_COMPETENCE = 0.55
PRIMARY_TIER = "tier_mid"
RUN_PLAN = "betal-search-plan-v0.2.0"
CONTRACT = "benchmark-contract-v0.1"

DESIGNERS = (
    ("feedback_coordinate", FeedbackCoordinateDesigner),
    ("random_sampling_ppr", RandomSamplingPPRDesigner),
    ("best_of_n", BestOfNDesigner),
)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"  wrote {path.relative_to(ROOT)}")


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _stdev(values: list[float]) -> float | None:
    return statistics.stdev(values) if len(values) > 1 else 0.0 if values else None


def main() -> int:
    print("BeTaL-GBI v0.2 search")
    OUT.mkdir(parents=True, exist_ok=True)

    primary_target = RepairedEmitterTarget(competence=PRIMARY_COMPETENCE)
    tier_targets = [RepairedEmitterTarget(competence=value, name=name) for name, value in TRANSFER_TIERS]

    # --- 1. Declared parameter space -------------------------------------
    print("[1/7] parameter space manifest")
    manifest = space_manifest()
    manifest["grid_cardinality"] = grid_cardinality()
    _write_json(OUT / "parameter_space.json", manifest)

    # --- 2. Monotonicity of the declared space ---------------------------
    print("[2/7] monotonicity checks")
    monotonicity = {
        "schema_version": "boundarybench.betal_monotonicity_report.v1",
        "task_count": TASK_COUNT,
        "checks": [monotonicity_check(target=target, task_count=TASK_COUNT) for target in tier_targets],
    }
    # Reachability: which target levels lie inside each tier's observed range.
    reachability = []
    for check in monotonicity["checks"]:
        low, high = check["observed_range"]
        for level in LEVEL_ORDER:
            rho = TARGET_LEVELS[level]
            reachable = low - 1e-9 <= rho <= high + 1e-9
            floor = 0.0 if reachable else min(abs(rho - low), abs(rho - high))
            reachability.append(
                {
                    "target_name": check["target_name"],
                    "difficulty_level": level,
                    "rho_target_performance": rho,
                    "observed_range_low": round(low, 6),
                    "observed_range_high": round(high, 6),
                    "reachable": reachable,
                    "attainable_gap_floor": round(floor, 6),
                }
            )
    monotonicity["reachability"] = reachability
    _write_json(OUT / "monotonicity_and_reachability.json", monotonicity)

    # --- 3. Degenerate-gap demonstration ---------------------------------
    print("[3/7] admissibility-floor (degenerate gap) demonstration")
    floor_target = V01BoundaryFloorTarget()
    degenerate = {
        "schema_version": "boundarybench.betal_degenerate_gap_report.v1",
        "purpose": (
            "Demonstrate mechanically that BeTaL's gap signal is undefined, not merely "
            "large, against a target pinned at the admissibility floor."
        ),
        "target_surrogate": floor_target.manifest(),
        "runs": [],
    }
    for mode in EVIDENCE_MODES:
        run = run_search(
            designer=FeedbackCoordinateDesigner(iterations=ITERATIONS, seed=f"degenerate|{mode}"),
            target=floor_target,
            level="medium",
            iterations=ITERATIONS,
            task_count=TASK_COUNT,
            evidence_mode=mode,
        )
        degenerate["runs"].append(run.as_dict())
    probe_rates = {
        entry["dial"]
        for run in degenerate["runs"]
        for entry in run["admissibility_probe"]
    }
    all_adm = [
        entry["rho_hat_adm"]
        for run in degenerate["runs"]
        for entry in run["admissibility_probe"]
    ]
    degenerate["probe_summary"] = {
        "dials_probed": sorted(probe_rates),
        "distinct_rho_hat_adm_values": sorted(set(all_adm)),
        "rho_hat_adm_invariant_across_V": len(set(all_adm)) == 1,
        "conclusion": (
            "The admissibility rate is invariant across the probed dial, so no point in V "
            "can raise it. rho_hat_task is undefined at every point and the BeTaL gap "
            "cannot be computed. The correct response is to repair the output-format "
            "boundary, not to tune difficulty."
        ),
    }
    _write_json(OUT / "degenerate_gap_report.json", degenerate)

    # --- 4. Main search: designers x levels ------------------------------
    print("[4/7] parameter search")
    search_runs: list[dict[str, Any]] = []
    best_configs: dict[str, Any] = {}
    for designer_key, designer_cls in DESIGNERS:
        for level in LEVEL_ORDER:
            kwargs: dict[str, Any] = {"seed": f"{RUN_PLAN}|{designer_key}|{level}"}
            if designer_cls is FeedbackCoordinateDesigner:
                kwargs["iterations"] = ITERATIONS
            designer = designer_cls(**kwargs)
            run = run_search(
                designer=designer,
                target=primary_target,
                level=level,
                iterations=ITERATIONS,
                task_count=TASK_COUNT,
                evidence_mode="output_only",
            )
            record = run.as_dict()
            record["designer_key"] = designer_key
            search_runs.append(record)
            print(
                f"  {designer_key:22s} {level:8s} "
                f"best_gap={run.best_gap if run.best_gap is None else round(run.best_gap, 4)} "
                f"mean_gap={None if run.mean_search_gap() is None else round(run.mean_search_gap(), 4)} "
                f"holdout_gap={None if run.holdout_gap is None else round(run.holdout_gap, 4)}"
            )
            if designer_key == "feedback_coordinate" and run.best_config is not None:
                best_configs[level] = run.best_config
    _write_json(
        OUT / "search_runs.json",
        {
            "schema_version": "boundarybench.betal_search_runs.v1",
            "run_plan": RUN_PLAN,
            "benchmark_contract": CONTRACT,
            "task_count": TASK_COUNT,
            "iterations_per_run": ITERATIONS,
            "primary_target": primary_target.manifest(),
            "runs": search_runs,
        },
    )

    # --- 5. Aggregate comparison table -----------------------------------
    print("[5/7] aggregate comparison")
    rows: list[dict[str, Any]] = []
    for designer_key, _ in DESIGNERS:
        matching = [run for run in search_runs if run["designer_key"] == designer_key]
        search_gaps = [run["mean_search_gap"] for run in matching if run["mean_search_gap"] is not None]
        best_gaps = [run["best_gap"] for run in matching if run["best_gap"] is not None]
        holdout_gaps = [run["holdout_gap"] for run in matching if run["holdout_gap"] is not None]
        rows.append(
            {
                "designer": designer_key,
                "level_count": len(matching),
                "mean_search_gap_pct": round(100 * _mean(search_gaps), 2) if search_gaps else None,
                "mean_search_gap_stdev_pct": round(100 * _stdev(search_gaps), 2) if search_gaps else None,
                "mean_best_gap_pct": round(100 * _mean(best_gaps), 2) if best_gaps else None,
                "mean_holdout_gap_pct": round(100 * _mean(holdout_gaps), 2) if holdout_gaps else None,
                "mean_holdout_gap_stdev_pct": round(100 * _stdev(holdout_gaps), 2) if holdout_gaps else None,
            }
        )
    per_level_rows: list[dict[str, Any]] = []
    for run in search_runs:
        per_level_rows.append(
            {
                "designer": run["designer_key"],
                "difficulty_level": run["difficulty_level"],
                "rho_target_performance": run["rho_target_performance"],
                "rho_target_failure_rate_view": run["rho_target_failure_rate_view"],
                "best_iteration": run["best_iteration"],
                "best_gap": run["best_gap"],
                "mean_search_gap": run["mean_search_gap"],
                "holdout_gap": run["holdout_gap"],
                "best_rho_hat_task": (
                    run["iterations"][run["best_iteration"] - 1]["evaluation"]["rho_hat_task"]
                    if run["best_iteration"]
                    else None
                ),
                "holdout_rho_hat_task": (
                    run["holdout_evaluation"]["rho_hat_task"] if run["holdout_evaluation"] else None
                ),
                "holdout_coverage": (
                    run["holdout_evaluation"]["coverage"] if run["holdout_evaluation"] else None
                ),
                "holdout_selective_risk": (
                    run["holdout_evaluation"]["selective_risk"] if run["holdout_evaluation"] else None
                ),
                "holdout_false_acceptance_count": (
                    run["holdout_evaluation"]["false_acceptance_count"]
                    if run["holdout_evaluation"]
                    else None
                ),
                "status": run["status"],
            }
        )
    aggregate = {
        "schema_version": "boundarybench.betal_aggregate_metrics.v1",
        "run_plan": RUN_PLAN,
        "benchmark_contract": CONTRACT,
        "loop_version": LOOP_VERSION,
        "space_version": SPACE_VERSION,
        "simulator_version": SIMULATOR_VERSION,
        "targets_version": TARGETS_VERSION,
        "task_count_per_instantiation": TASK_COUNT,
        "iterations_per_run": ITERATIONS,
        "difficulty_levels": {level: TARGET_LEVELS[level] for level in LEVEL_ORDER},
        "rho_convention": "target verified-completion rate given admission (BeTaL performance convention)",
        "primary_target_surrogate": primary_target.name,
        "designer_comparison": rows,
        "per_level": per_level_rows,
        "confidence_intervals": "NOT_RUN",
        "repeat_run_stability": "NOT_RUN",
        "reported_provider_cost_usd": "NOT_RUN",
        "llm_designer_executed": False,
        "language_model_executed": False,
        "scoring_status": "COMPLETED",
    }
    _write_json(OUT / "aggregate_metrics.json", aggregate)

    with (OUT / "per_level_metrics.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(per_level_rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(per_level_rows)
    print(f"  wrote {(OUT / 'per_level_metrics.csv').relative_to(ROOT)}")

    # --- 6. Transfer study + cone diagnostics ----------------------------
    print("[6/7] transfer study and cone diagnostics")
    transfer_rows: list[dict[str, Any]] = []
    for level, config in best_configs.items():
        rows_for_level = transfer_study(
            config=config,
            targets=tier_targets,
            rho=TARGET_LEVELS[level],
            task_count=TASK_COUNT,
        )
        for row in rows_for_level:
            row["difficulty_level"] = level
            row["tuned_against"] = primary_target.name
            row["configuration_sha256"] = config.digest()
        transfer_rows.extend(rows_for_level)
    ordering_preserved = []
    for level in best_configs:
        level_rows = [row for row in transfer_rows if row["difficulty_level"] == level]
        by_tier = {row["target_name"]: row["rho_hat_task"] for row in level_rows}
        ordered = [by_tier.get(name) for name, _ in TRANSFER_TIERS]
        strictly_increasing = all(
            earlier is not None and later is not None and later > earlier
            for earlier, later in zip(ordered, ordered[1:])
        )
        ordering_preserved.append(
            {
                "difficulty_level": level,
                "tier_order": [name for name, _ in TRANSFER_TIERS],
                "rho_hat_task_by_tier": ordered,
                "separation_order_preserved": strictly_increasing,
            }
        )
    _write_json(
        OUT / "transfer_study.json",
        {
            "schema_version": "boundarybench.betal_transfer_study.v1",
            "note": (
                "Tiers are declared surrogate competence constants. They are ordered labels "
                "for a simulator parameter and do not correspond to any named commercial model. "
                "No language model was executed."
            ),
            "tiers": [{"name": name, "competence": value} for name, value in TRANSFER_TIERS],
            "rows": transfer_rows,
            "ordering_check": ordering_preserved,
        },
    )
    _write_json(OUT / "cone_reference_table.json", reference_table())

    # --- 7. Designer prompt contract + provenance ------------------------
    print("[7/7] designer prompt contract and provenance")
    example_prompt = render_designer_prompt(
        rho=TARGET_LEVELS["hard"], level_name="hard", history=[], task_count=TASK_COUNT
    )
    prompt_payload = {
        "schema_version": "boundarybench.betal_designer_contract.v1",
        "designer_system_prompt": DESIGNER_SYSTEM_PROMPT,
        "designer_system_prompt_sha256": hashlib.sha256(
            DESIGNER_SYSTEM_PROMPT.encode("utf-8")
        ).hexdigest(),
        "example_first_iteration_user_prompt": example_prompt,
        "example_first_iteration_user_prompt_sha256": hashlib.sha256(
            example_prompt.encode("utf-8")
        ).hexdigest(),
        "declared_llm_designer_settings": {
            "status": "NOT_RUN",
            "intended_temperature": 0.5,
            "intended_reasoning_budget_tokens": 4096,
            "note": (
                "These settings mirror the BeTaL paper's designer configuration. No designer "
                "LLM was executed for the v0.2 artifacts in this directory."
            ),
        },
        "versions": space_and_versions(),
    }
    _write_json(OUT / "designer_contract.json", prompt_payload)

    provenance = {
        "schema_version": "boundarybench.betal_provenance.v1",
        "run_plan": RUN_PLAN,
        "benchmark_contract": CONTRACT,
        "component_versions": {
            "loop": LOOP_VERSION,
            "parameter_space": SPACE_VERSION,
            "simulator": SIMULATOR_VERSION,
            "target_surrogates": TARGETS_VERSION,
        },
        "verifier": {
            "source": "boundarybench.verification (v0.1 Programmatic Verification Engine)",
            "modified_for_v0_2": False,
            "note": (
                "All grading is performed by the unmodified v0.1 verifier. The BeTaL layer "
                "generates tasks and evaluates surrogates; it does not re-implement a criterion."
            ),
        },
        "execution_scope": {
            "language_models_executed": 0,
            "provider_calls": 0,
            "held_out_references_read": 0,
            "synthetic_data_only": True,
            "clinical_data_used": False,
        },
        "calibration_source": {
            "artifact": "artifacts/public_results/v0_1/status_distributions.json",
            "per_mode_safe_parse_reject": 123,
            "per_mode_safe_schema_reject": 133,
            "raw_freeze": "empirical-raw-v0.1",
        },
        "reproduce": "PYTHONPATH=src python3 scripts/run_betal_v0_2_search.py",
    }
    _write_json(OUT / "PROVENANCE.json", provenance)

    # Checksum manifest over every artifact written above.
    lines = []
    for path in sorted(OUT.glob("*")):
        if path.name == "SHA256SUMS":
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        lines.append(f"{digest}  {path.name}")
    (OUT / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"  wrote {(OUT / 'SHA256SUMS').relative_to(ROOT)}")
    print("done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
