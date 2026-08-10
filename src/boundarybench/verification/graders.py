"""Deterministic criterion graders for the PVE."""

from __future__ import annotations

from typing import Any

from boundarybench.tasks.schemas import validate_result, validate_task
from boundarybench.verification.types import CriterionResult

TABLE_TO_RESOURCE = {
    "DEM": "Patient",
    "PXX": "Encounter",
    "LAB": "Observation",
    "PROB": "Condition",
}

ADMITTING_ACTIONS = {"admit", "admit_historical_only"}
NON_ADMIT_ACTIONS = {"abstain", "expert_review", "quarantine_slice", "reject"}


def schema_criterion(
    task: dict[str, Any],
    result: dict[str, Any] | None,
    parse_errors: list[str] | None = None,
) -> CriterionResult:
    task_errors = validate_task(task)
    if task_errors:
        return CriterionResult("schema", False, "invalid_task_contract", tuple(task_errors))
    if result is None:
        return CriterionResult("schema", False, "safe_parse_reject", tuple(parse_errors or ["missing_result"]))
    result_errors = validate_result(result, task)
    if result_errors:
        return CriterionResult("schema", False, "safe_schema_reject", tuple(result_errors))
    return CriterionResult("schema", True, "pass")


def exact_criterion(task: dict[str, Any], result: dict[str, Any]) -> CriterionResult:
    errors: list[str] = []
    if result["action"] != task["reference"]["action"]:
        errors.append("wrong_action")
    if result["answer"] != task["reference"]["answer"]:
        errors.append("wrong_answer")
    return CriterionResult("exact", not errors, "pass" if not errors else "fail", tuple(errors))


def evidence_criterion(task: dict[str, Any], result: dict[str, Any]) -> CriterionResult:
    evidence_ids = {ref["ref_id"] for ref in task["evidence_refs"]}
    required = set(task["reference"]["required_evidence"])
    observed = set(result["evidence_refs"])
    errors: list[str] = []
    missing = sorted(required - observed)
    unknown = sorted(observed - evidence_ids)
    if missing:
        errors.append(f"missing_evidence:{','.join(missing)}")
    if unknown:
        errors.append(f"unknown_evidence:{','.join(unknown)}")
    return CriterionResult(
        "evidence",
        not errors,
        "pass" if not errors else "fail",
        tuple(errors),
        {"required": sorted(required), "observed": sorted(observed), "known": sorted(evidence_ids)},
    )


def graph_criterion(task: dict[str, Any], result: dict[str, Any]) -> CriterionResult:
    """Check provenance graph consistency for fields that make graph claims."""

    evidence_by_id = {ref["ref_id"]: ref for ref in task["evidence_refs"]}
    observed_refs = [evidence_by_id[ref_id] for ref_id in result["evidence_refs"] if ref_id in evidence_by_id]
    evidence_source_ids = {ref["source_record_id"] for ref in observed_refs if "source_record_id" in ref}
    evidence_row_ids = {ref["row_id"] for ref in observed_refs if "row_id" in ref}
    answer = result["answer"]
    errors: list[str] = []

    claimed_source = answer.get("source_record_id")
    if claimed_source is not None and claimed_source not in evidence_source_ids:
        errors.append("source_record_id_not_supported_by_evidence")

    claimed_row = answer.get("rpms_row_id")
    input_row = task["input"].get("row")
    input_row_id = input_row[0] if isinstance(input_row, list) and input_row else task["input"].get("row_id")
    supported_row_ids = set(evidence_row_ids)
    if input_row_id is not None:
        supported_row_ids.add(str(input_row_id))
    if claimed_row is not None and str(claimed_row) not in supported_row_ids:
        errors.append("rpms_row_id_not_supported_by_evidence")

    family = task["family"]
    if family == "rpms_to_fhir_mapping":
        table = task["input"].get("table")
        expected_resource = TABLE_TO_RESOURCE.get(str(table))
        if answer.get("resource_type") != expected_resource:
            errors.append("resource_type_graph_mismatch")
        if claimed_source is None:
            errors.append("missing_source_record_id")
        if claimed_row is None:
            errors.append("missing_rpms_row_id")

    return CriterionResult(
        "graph",
        not errors,
        "pass" if not errors else "fail",
        tuple(errors),
        {
            "evidence_source_record_ids": sorted(evidence_source_ids),
            "evidence_row_ids": sorted(evidence_row_ids),
        },
    )


def temporal_criterion(task: dict[str, Any], result: dict[str, Any]) -> CriterionResult:
    family = task["family"]
    if family != "temporal_status_classification":
        return CriterionResult("temporal", True, "not_applicable")

    status = str(task["input"].get("status", "")).upper()
    answer = result["answer"]
    errors: list[str] = []
    if status == "ACTIVE":
        if result["action"] != "admit":
            errors.append("active_status_requires_admit")
        if answer.get("temporal_status") != "active":
            errors.append("active_status_answer_mismatch")
    else:
        if result["action"] != "admit_historical_only":
            errors.append("inactive_status_requires_historical_only")
        if answer.get("temporal_status") != "historical":
            errors.append("inactive_status_answer_mismatch")
    return CriterionResult("temporal", not errors, "pass" if not errors else "fail", tuple(errors))


def version_criterion(task: dict[str, Any], result: dict[str, Any]) -> CriterionResult:
    family = task["family"]
    if family != "code_system_version_validation":
        return CriterionResult("version", True, "not_applicable")

    version = str(task["input"].get("code_version", ""))
    code = task["input"].get("code")
    answer = result["answer"]
    errors: list[str] = []
    if version == "9":
        if result["action"] != "admit_historical_only":
            errors.append("icd9_requires_historical_only")
        if answer.get("code_system") != "ICD-9-CM":
            errors.append("icd9_code_system_mismatch")
    elif version == "10":
        if result["action"] != "admit":
            errors.append("icd10_requires_admit")
        if answer.get("code_system") != "ICD-10-CM":
            errors.append("icd10_code_system_mismatch")
    else:
        if result["action"] != "reject":
            errors.append("unsupported_code_version_requires_reject")
    if answer.get("code") != code:
        errors.append("code_value_mismatch")
    return CriterionResult("version", not errors, "pass" if not errors else "fail", tuple(errors))


def run_all_criteria(
    task: dict[str, Any],
    result: dict[str, Any] | None,
    parse_errors: list[str] | None = None,
) -> tuple[CriterionResult, ...]:
    schema = schema_criterion(task, result, parse_errors)
    if not schema.passed or result is None:
        return (schema,)
    return (
        schema,
        exact_criterion(task, result),
        graph_criterion(task, result),
        temporal_criterion(task, result),
        version_criterion(task, result),
        evidence_criterion(task, result),
    )

