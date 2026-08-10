"""Generate the small public dev split for the eight v0.1 task families."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from boundarybench.stage1.constants import FREE_TEXT_SNIPPETS, RPMS_FIELDS
from boundarybench.tasks.grade import oracle_result
from boundarybench.tasks.io import read_jsonl, read_rpms, write_jsonl
from boundarybench.tasks.schemas import ACTION_SEMANTICS, validate_task


def _artifact(path: Path, root: Path) -> str:
    return str(path.resolve().relative_to(root.resolve()))


def _normalize_patient_id(value: str) -> str:
    digits = re.sub(r"\D", "", value or "")
    return str(int(digits)) if digits else ""


def _ref(
    ref_id: str,
    artifact: str,
    table: str,
    row_id: str,
    source_record_id: str,
    column_name: str | None = None,
    event_id: str | None = None,
    field_path: str | None = None,
) -> dict[str, str]:
    out = {
        "ref_id": ref_id,
        "artifact": artifact,
        "table": table,
        "row_id": row_id,
        "source_record_id": source_record_id,
    }
    if column_name is not None:
        out["column_name"] = column_name
    if event_id is not None:
        out["event_id"] = event_id
    if field_path is not None:
        out["field_path"] = field_path
    return out


def _task(
    *,
    task_id: str,
    family: str,
    prompt: str,
    task_input: dict[str, Any],
    evidence_refs: list[dict[str, str]],
    failure_slices: list[str],
    action: str,
    answer: dict[str, Any],
    rationale: str,
) -> dict[str, Any]:
    task = {
        "schema_version": "boundarybench.task.v1",
        "task_id": task_id,
        "split": "public_dev",
        "family": family,
        "prompt": prompt,
        "input": task_input,
        "allowed_actions": [
            "admit",
            "admit_historical_only",
            "quarantine_slice",
            "abstain",
            "expert_review",
            "reject",
        ],
        "action_semantics": ACTION_SEMANTICS,
        "abstention": {
            "allowed": True,
            "rewarded_when": "Required evidence is absent, ambiguous, unsupported, or unsafe to coerce.",
            "unsafe_when": "Required evidence is present and deterministic policy requires a non-abstain action.",
        },
        "evidence_refs": evidence_refs,
        "failure_slices": failure_slices,
        "reference": {
            "action": action,
            "answer": answer,
            "required_evidence": [ref["ref_id"] for ref in evidence_refs],
            "rationale": rationale,
        },
    }
    errors = validate_task(task)
    if errors:
        raise ValueError(f"Invalid task {task_id}: {errors}")
    return task


def _row_object(table: str, row: list[str]) -> dict[str, str]:
    return {field: row[index] for index, field in enumerate(RPMS_FIELDS[table])}


def _load_stage1(stage1_dir: Path) -> dict[str, Any]:
    root = stage1_dir
    clean = {table: read_rpms(root / "views" / "rpms_clean" / f"{table}.txt") for table in RPMS_FIELDS}
    corrupt = {table: read_rpms(root / "views" / "rpms_corrupt" / f"{table}.txt") for table in RPMS_FIELDS}
    row_index = read_jsonl(root / "metadata" / "row_index.jsonl")
    row_lookup = {(row["table"], row["row_id"]): row for row in row_index}
    events = read_jsonl(root / "corruptions" / "events.jsonl")
    event_by_type: dict[str, list[dict[str, Any]]] = {}
    for event in events:
        event_by_type.setdefault(event["corruption_type"], []).append(event)
    dem_hrns = {row[1] for row in clean["DEM"]}
    return {
        "root": root,
        "clean": clean,
        "corrupt": corrupt,
        "row_lookup": row_lookup,
        "events": events,
        "event_by_type": event_by_type,
        "dem_hrns": sorted(dem_hrns),
    }


def _repo_relative(path: Path, repo_root: Path) -> str:
    resolved_path = path.resolve()
    resolved_root = repo_root.resolve()
    try:
        return str(resolved_path.relative_to(resolved_root))
    except ValueError:
        return str(resolved_path)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def generate_public_dev(stage1_dir: Path, out_dir: Path, repo_root: Path | None = None) -> dict[str, Any]:
    data = _load_stage1(stage1_dir)
    root = data["root"]
    tasks: list[dict[str, Any]] = []

    id_variant = data["event_by_type"]["identity_format_variant"][0]
    table = id_variant["table"]
    row_id = id_variant["row_id"]
    source_record_id = id_variant["source_record_id"]
    tasks.append(
        _task(
            task_id="public-dev-identity-001",
            family="patient_identity_normalization",
            prompt="Normalize the messy RPMS patient identifier and decide whether it links to DEM.",
            task_input={
                "table": table,
                "row_id": row_id,
                "patient_id": id_variant["after"],
                "known_dem_hrns": data["dem_hrns"],
            },
            evidence_refs=[
                _ref(
                    "ev1",
                    _artifact(root / "corruptions" / "events.jsonl", Path(".")),
                    table,
                    row_id,
                    source_record_id,
                    "PATIENT_ID",
                    id_variant["event_id"],
                    id_variant["field_path"],
                )
            ],
            failure_slices=["identity_format_variant", table],
            action="admit",
            answer={"normalized_hrn": id_variant["before"], "link_status": "linked"},
            rationale="Formatting noise normalizes to an existing DEM HRN.",
        )
    )

    orphan = data["event_by_type"]["identity_orphan"][0]
    tasks.append(
        _task(
            task_id="public-dev-orphan-001",
            family="orphan_duplicate_detection",
            prompt="Determine whether this linked RPMS row references a known DEM patient or must be quarantined.",
            task_input={
                "table": orphan["table"],
                "row_id": orphan["row_id"],
                "patient_id": orphan["after"],
                "known_dem_hrns": data["dem_hrns"],
                "duplicate_count": 1,
            },
            evidence_refs=[
                _ref(
                    "ev1",
                    _artifact(root / "corruptions" / "events.jsonl", Path(".")),
                    orphan["table"],
                    orphan["row_id"],
                    orphan["source_record_id"],
                    "PATIENT_ID",
                    orphan["event_id"],
                    orphan["field_path"],
                )
            ],
            failure_slices=["identity_orphan", orphan["table"]],
            action="quarantine_slice",
            answer={"issue": "orphan_patient_id", "normalized_hrn": _normalize_patient_id(orphan["after"])},
            rationale="The normalized orphan identifier is not present in DEM.",
        )
    )

    bleed = next(event for event in data["event_by_type"]["free_text_bleed"] if event["after"] in FREE_TEXT_SNIPPETS)
    tasks.append(
        _task(
            task_id="public-dev-bleed-001",
            family="field_anomaly_bleed",
            prompt="Classify whether a structured RPMS field contains free-text bleed.",
            task_input={
                "table": bleed["table"],
                "row_id": bleed["row_id"],
                "field": bleed["column_name"],
                "cell_value": bleed["after"],
                "known_free_text_snippets": FREE_TEXT_SNIPPETS,
            },
            evidence_refs=[
                _ref(
                    "ev1",
                    _artifact(root / "corruptions" / "events.jsonl", Path(".")),
                    bleed["table"],
                    bleed["row_id"],
                    bleed["source_record_id"],
                    bleed["column_name"],
                    bleed["event_id"],
                    bleed["field_path"],
                )
            ],
            failure_slices=["free_text_bleed", bleed["table"], bleed["column_name"]],
            action="expert_review",
            answer={"issue": "free_text_bleed", "field": bleed["column_name"]},
            rationale="The value is a known note fragment in a structured field.",
        )
    )

    legacy = data["event_by_type"]["legacy_icd9"][0]
    tasks.append(
        _task(
            task_id="public-dev-code-001",
            family="code_system_version_validation",
            prompt="Validate the code system version and decide whether the diagnosis can be admitted as current normalized evidence.",
            task_input={
                "table": legacy["table"],
                "row_id": legacy["row_id"],
                "code": legacy["after"],
                "code_version": "9",
            },
            evidence_refs=[
                _ref(
                    "ev1",
                    _artifact(root / "corruptions" / "events.jsonl", Path(".")),
                    legacy["table"],
                    legacy["row_id"],
                    legacy["source_record_id"],
                    legacy["column_name"],
                    legacy["event_id"],
                    legacy["field_path"],
                )
            ],
            failure_slices=["legacy_icd9", legacy["table"]],
            action="admit_historical_only",
            answer={"code_system": "ICD-9-CM", "code": legacy["after"]},
            rationale="ICD-9-CM is legacy evidence and must not be silently treated as current ICD-10-CM.",
        )
    )

    lab_row = data["clean"]["LAB"][0]
    lab_index = data["row_lookup"][("LAB", lab_row[0])]
    tasks.append(
        _task(
            task_id="public-dev-map-001",
            family="rpms_to_fhir_mapping",
            prompt="Map the clean RPMS LAB row to its expected FHIR resource type and source record.",
            task_input={
                "table": "LAB",
                "row": lab_row,
                "row_object": _row_object("LAB", lab_row),
                "source_record_id": lab_index["source_record_id"],
            },
            evidence_refs=[
                _ref(
                    "ev1",
                    _artifact(root / "views" / "rpms_clean" / "LAB.txt", Path(".")),
                    "LAB",
                    lab_row[0],
                    lab_index["source_record_id"],
                ),
                _ref(
                    "ev2",
                    _artifact(root / "normalized" / "fhir_expected.jsonl", Path(".")),
                    "LAB",
                    lab_row[0],
                    lab_index["source_record_id"],
                ),
            ],
            failure_slices=["rpms_to_fhir_mapping", "LAB"],
            action="admit",
            answer={
                "resource_type": "Observation",
                "source_record_id": lab_index["source_record_id"],
                "rpms_row_id": lab_row[0],
            },
            rationale="LAB rows map to Observation provenance entries.",
        )
    )

    inactive_problem = next(row for row in data["clean"]["PROB"] if row[6] == "INACTIVE")
    inactive_index = data["row_lookup"][("PROB", inactive_problem[0])]
    tasks.append(
        _task(
            task_id="public-dev-temporal-001",
            family="temporal_status_classification",
            prompt="Classify whether this problem-list item should be admitted as active or historical-only.",
            task_input={
                "table": "PROB",
                "row_id": inactive_problem[0],
                "status": inactive_problem[6],
                "onset_date": inactive_problem[5],
            },
            evidence_refs=[
                _ref(
                    "ev1",
                    _artifact(root / "views" / "rpms_clean" / "PROB.txt", Path(".")),
                    "PROB",
                    inactive_problem[0],
                    inactive_index["source_record_id"],
                    "STATUS",
                )
            ],
            failure_slices=["temporal_status", "historical_problem"],
            action="admit_historical_only",
            answer={"temporal_status": "historical"},
            rationale="Inactive problem-list evidence should not be admitted as active current truth.",
        )
    )

    pxx_no_dx = next(row for row in data["clean"]["PXX"] if row[7] == "" and row[8] == "")
    pxx_index = data["row_lookup"][("PXX", pxx_no_dx[0])]
    tasks.append(
        _task(
            task_id="public-dev-evidence-001",
            family="evidence_sufficiency",
            prompt="Decide whether an ICD diagnosis can be asserted for this encounter from the provided evidence.",
            task_input={
                "table": "PXX",
                "row_id": pxx_no_dx[0],
                "required_evidence_present": False,
                "missing_evidence": ["POV_ICD", "POV_ICD_VERSION"],
                "row_object": _row_object("PXX", pxx_no_dx),
            },
            evidence_refs=[
                _ref(
                    "ev1",
                    _artifact(root / "views" / "rpms_clean" / "PXX.txt", Path(".")),
                    "PXX",
                    pxx_no_dx[0],
                    pxx_index["source_record_id"],
                    "POV_ICD",
                )
            ],
            failure_slices=["evidence_sufficiency", "missing_diagnosis"],
            action="abstain",
            answer={"evidence_status": "insufficient", "missing": ["POV_ICD", "POV_ICD_VERSION"]},
            rationale="The encounter has no diagnosis code evidence, so a confident code assertion would fabricate evidence.",
        )
    )

    tasks.append(
        _task(
            task_id="public-dev-policy-001",
            family="policy_action_selection",
            prompt="Select the deterministic policy action for a malformed FileMan date in an otherwise parseable RPMS row.",
            task_input={
                "issue": "invalid_fileman_date",
                "table": "PXX",
                "row_id": pxx_no_dx[0],
                "field": "VISIT_DATETIME",
                "cell_value": "9999999.999999",
            },
            evidence_refs=[
                _ref(
                    "ev1",
                    _artifact(root / "views" / "rpms_clean" / "PXX.txt", Path(".")),
                    "PXX",
                    pxx_no_dx[0],
                    pxx_index["source_record_id"],
                    "VISIT_DATETIME",
                )
            ],
            failure_slices=["policy_action", "invalid_fileman_date"],
            action="reject",
            answer={"policy_effect": "reject", "issue": "invalid_fileman_date"},
            rationale="Invalid dates fail closed and must not be normalized implicitly.",
        )
    )

    out_dir.mkdir(parents=True, exist_ok=True)
    tasks_path = out_dir / "tasks.jsonl"
    oracle_path = out_dir / "oracle_results.jsonl"
    write_jsonl(tasks_path, tasks)
    write_jsonl(oracle_path, [oracle_result(task) for task in tasks])
    root_for_manifest = repo_root or Path.cwd()
    manifest = {
        "schema_version": "boundarybench.task_split_manifest.v1",
        "split": "public_dev",
        "task_count": len(tasks),
        "families": sorted({task["family"] for task in tasks}),
        "tasks_path": _repo_relative(tasks_path, root_for_manifest),
        "tasks_sha256": _sha256_file(tasks_path),
        "oracle_results_path": _repo_relative(oracle_path, root_for_manifest),
        "oracle_results_sha256": _sha256_file(oracle_path),
        "stage1_source": _repo_relative(stage1_dir, root_for_manifest),
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return manifest


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage1-dir", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    args = parser.parse_args(argv)
    print(json.dumps(generate_public_dev(args.stage1_dir, args.out_dir), sort_keys=True))


if __name__ == "__main__":
    main()
