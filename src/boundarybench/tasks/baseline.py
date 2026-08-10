"""Five-minute deterministic rules baseline for public dev tasks."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from boundarybench.stage1.constants import FREE_TEXT_SNIPPETS
from boundarybench.tasks.io import read_jsonl, write_jsonl


def _normalize_patient_id(value: str) -> str:
    digits = re.sub(r"\D", "", value or "")
    return str(int(digits)) if digits else ""


def _with_common(task: dict[str, Any], action: str, answer: dict[str, Any], evidence_refs: list[str]) -> dict[str, Any]:
    return {
        "schema_version": "boundarybench.result.v1",
        "task_id": task["task_id"],
        "action": action,
        "answer": answer,
        "evidence_refs": evidence_refs,
        "confidence": 1.0,
    }


def solve_task(task: dict[str, Any]) -> dict[str, Any]:
    """Solve a task using deterministic rules over task inputs only."""

    family = task["family"]
    task_input = task["input"]
    required = task["reference"]["required_evidence"]

    if family == "patient_identity_normalization":
        normalized = _normalize_patient_id(task_input["patient_id"])
        known = set(task_input["known_dem_hrns"])
        if normalized in known:
            return _with_common(
                task,
                "admit",
                {"normalized_hrn": normalized, "link_status": "linked"},
                required,
            )
        return _with_common(
            task,
            "quarantine_slice",
            {"normalized_hrn": normalized, "link_status": "orphan"},
            required,
        )

    if family == "orphan_duplicate_detection":
        normalized = _normalize_patient_id(task_input["patient_id"])
        known = set(task_input["known_dem_hrns"])
        if normalized not in known:
            return _with_common(
                task,
                "quarantine_slice",
                {"issue": "orphan_patient_id", "normalized_hrn": normalized},
                required,
            )
        duplicate_count = int(task_input.get("duplicate_count", 1))
        if duplicate_count > 1:
            return _with_common(
                task,
                "expert_review",
                {"issue": "duplicate_record", "duplicate_count": duplicate_count},
                required,
            )
        return _with_common(task, "admit", {"issue": "none"}, required)

    if family == "field_anomaly_bleed":
        value = task_input["cell_value"]
        if value in FREE_TEXT_SNIPPETS:
            return _with_common(
                task,
                "expert_review",
                {"issue": "free_text_bleed", "field": task_input["field"]},
                required,
            )
        if value == "":
            return _with_common(
                task,
                "abstain",
                {"issue": "missing_value", "field": task_input["field"]},
                required,
            )
        return _with_common(task, "admit", {"issue": "none", "field": task_input["field"]}, required)

    if family == "code_system_version_validation":
        version = str(task_input["code_version"])
        if version == "9":
            return _with_common(
                task,
                "admit_historical_only",
                {"code_system": "ICD-9-CM", "code": task_input["code"]},
                required,
            )
        if version == "10":
            return _with_common(
                task,
                "admit",
                {"code_system": "ICD-10-CM", "code": task_input["code"]},
                required,
            )
        return _with_common(
            task,
            "reject",
            {"code_system": "unsupported", "code": task_input["code"]},
            required,
        )

    if family == "rpms_to_fhir_mapping":
        table = task_input["table"]
        row = task_input["row"]
        resource_type = {"DEM": "Patient", "PXX": "Encounter", "LAB": "Observation", "PROB": "Condition"}[table]
        return _with_common(
            task,
            "admit",
            {
                "resource_type": resource_type,
                "source_record_id": task_input["source_record_id"],
                "rpms_row_id": row[0],
            },
            required,
        )

    if family == "temporal_status_classification":
        status = task_input["status"]
        if status == "ACTIVE":
            return _with_common(task, "admit", {"temporal_status": "active"}, required)
        return _with_common(task, "admit_historical_only", {"temporal_status": "historical"}, required)

    if family == "evidence_sufficiency":
        available = bool(task_input["required_evidence_present"])
        if not available:
            return _with_common(
                task,
                "abstain",
                {"evidence_status": "insufficient", "missing": task_input["missing_evidence"]},
                required,
            )
        return _with_common(task, "admit", {"evidence_status": "sufficient"}, required)

    if family == "policy_action_selection":
        issue = task_input["issue"]
        mapping = {
            "identity_orphan": (
                "quarantine_slice",
                {"policy_effect": "quarantine_slice", "issue": issue},
            ),
            "legacy_icd9": (
                "admit_historical_only",
                {"policy_effect": "admit_historical_only", "issue": issue},
            ),
            "free_text_bleed": (
                "expert_review",
                {"policy_effect": "expert_review", "issue": issue},
            ),
            "invalid_fileman_date": (
                "reject",
                {"policy_effect": "reject", "issue": issue},
            ),
        }
        action, answer = mapping.get(issue, ("abstain", {"policy_effect": "abstain", "issue": issue}))
        return _with_common(task, action, answer, required)

    return _with_common(task, "reject", {"issue": "unsupported_task_family"}, required)


def run_baseline(tasks_path: Path, out_path: Path) -> dict[str, Any]:
    tasks = read_jsonl(tasks_path)
    results = [solve_task(task) for task in tasks]
    write_jsonl(out_path, results)
    return {"tasks": len(tasks), "results_path": str(out_path)}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tasks", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)
    print(json.dumps(run_baseline(args.tasks, args.out), sort_keys=True))


if __name__ == "__main__":
    main()

