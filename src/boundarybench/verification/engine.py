"""Programmatic Verification Engine (PVE)."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Any

from boundarybench.tasks.grade import safe_parse_result
from boundarybench.tasks.io import write_jsonl
from boundarybench.tasks.schemas import validate_task
from boundarybench.verification.diagnostics import sheaf_mapping_cone_diagnostic
from boundarybench.verification.graders import run_all_criteria
from boundarybench.verification.metrics import compute_summary
from boundarybench.verification.quarantine import dependency_index, quarantine_record
from boundarybench.verification.references import validate_reference_manifest
from boundarybench.verification.types import CriterionResult, VerificationGrade, VerificationSummary

FORBIDDEN_ENV_PREFIXES = ("OPENAI_", "ANTHROPIC_", "GOOGLE_", "AZURE_", "AWS_", "BOUNDARYBENCH_API")
FORBIDDEN_ENV_NAMES = ("API_KEY", "TOKEN", "PASSWORD", "SECRET")


def isolation_report() -> dict[str, Any]:
    visible = sorted(
        name
        for name in os.environ
        if name.startswith(FORBIDDEN_ENV_PREFIXES) or any(marker in name.upper() for marker in FORBIDDEN_ENV_NAMES)
    )
    return {
        "schema_version": "boundarybench.verifier_isolation.v1",
        "python_isolated_flag": bool(sys.flags.isolated),
        "safe_path_flag": bool(getattr(sys.flags, "safe_path", 0)),
        "forbidden_env_visible": visible,
        "environment_inherited": bool(visible),
        "process_boundary": True,
    }


def _read_results_by_task(results_path: Path) -> tuple[dict[str, dict[str, Any]], list[str]]:
    results: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    if not results_path.exists():
        return results, [f"missing_results_file:{results_path}"]
    for line_number, line in enumerate(results_path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        result, parse_errors = safe_parse_result(line)
        if result is None:
            errors.extend(f"line_{line_number}:{error}" for error in parse_errors)
            continue
        task_id = result.get("task_id")
        if not isinstance(task_id, str) or not task_id:
            errors.append(f"line_{line_number}:missing_task_id")
            continue
        if task_id in results:
            errors.append(f"line_{line_number}:duplicate_task_id:{task_id}")
            continue
        results[task_id] = result
    return results, errors


def _read_tasks_checked(tasks_path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    tasks: list[dict[str, Any]] = []
    errors: list[str] = []
    seen: set[str] = set()
    if not tasks_path.exists():
        return tasks, [f"missing_tasks_file:{tasks_path}"]
    for line_number, line in enumerate(tasks_path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            task = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(f"line_{line_number}:task_json_parse_error:{exc.msg}")
            continue
        if not isinstance(task, dict):
            errors.append(f"line_{line_number}:task_not_object")
            continue
        task_id = task.get("task_id")
        if not isinstance(task_id, str) or not task_id:
            errors.append(f"line_{line_number}:missing_task_id")
            continue
        if task_id in seen:
            errors.append(f"line_{line_number}:duplicate_task_id:{task_id}")
            continue
        seen.add(task_id)
        contract_errors = validate_task(task)
        if contract_errors:
            errors.extend(f"line_{line_number}:{error}" for error in contract_errors)
            continue
        tasks.append(task)
    return tasks, errors


def _grade_status(criteria: tuple[CriterionResult, ...], parsed: bool) -> str:
    if not parsed:
        return criteria[0].status
    if all(criterion.passed for criterion in criteria):
        return "pass"
    failed = [criterion.name for criterion in criteria if not criterion.passed]
    return "fail:" + ",".join(failed)


def verify_task(
    *,
    task: dict[str, Any],
    result: dict[str, Any] | None,
    parse_errors: list[str] | None,
    dependency_lookup: dict[str, tuple[str, ...]],
) -> VerificationGrade:
    criteria = run_all_criteria(task, result, parse_errors)
    parsed = result is not None and criteria[0].passed
    passed = parsed and all(criterion.passed for criterion in criteria)
    quarantine = quarantine_record(
        task=task,
        result=result,
        passed=passed,
        dependency_lookup=dependency_lookup,
    )
    errors = tuple(error for criterion in criteria for error in criterion.errors)
    return VerificationGrade(
        task_id=task.get("task_id", "<invalid-task>"),
        parsed=parsed,
        passed=passed,
        score=1 if passed else 0,
        status=_grade_status(criteria, parsed),
        observed_action=str(result.get("action", "reject")) if isinstance(result, dict) else "reject",
        expected_action=str(task.get("reference", {}).get("action", "")),
        criteria=criteria,
        quarantine=quarantine,
        errors=errors,
    )


def verify_files(
    *,
    tasks_path: Path,
    results_path: Path,
    grades_out: Path,
    summary_out: Path,
    enable_sheaf_diagnostic: bool = False,
    task_manifest_path: Path | None = None,
    trusted_checksums_path: Path | None = None,
) -> VerificationSummary:
    root = Path.cwd()
    manifest_path = task_manifest_path
    if manifest_path is None:
        candidate_manifest = tasks_path.parent / "manifest.json"
        manifest_path = candidate_manifest if candidate_manifest.exists() else None
    if trusted_checksums_path is None:
        candidate_checksums = root / "SHA256SUMS"
        trusted_checksums_path = candidate_checksums if candidate_checksums.exists() else None
    if manifest_path is not None:
        manifest_errors = validate_reference_manifest(
            root=root,
            tasks_path=tasks_path,
            manifest_path=manifest_path,
            trusted_checksums_path=trusted_checksums_path,
        )
        if manifest_errors:
            raise ValueError("reference_manifest_validation_failed:" + ";".join(manifest_errors))

    tasks, task_errors = _read_tasks_checked(tasks_path)
    if task_errors:
        raise ValueError("task_integrity_validation_failed:" + ";".join(task_errors))
    results, result_file_errors = _read_results_by_task(results_path)
    task_ids = {task["task_id"] for task in tasks}
    for result_task_id in sorted(set(results) - task_ids):
        result_file_errors.append(f"orphan_result_task_id:{result_task_id}")
    dependency_lookup = dependency_index(tasks)
    grades = [
        verify_task(
            task=task,
            result=results.get(task["task_id"]),
            parse_errors=None if task["task_id"] in results else ["missing_result"],
            dependency_lookup=dependency_lookup,
        )
        for task in tasks
    ]
    diagnostics = {"sheaf_mapping_cone": sheaf_mapping_cone_diagnostic(enabled=enable_sheaf_diagnostic)}
    summary = compute_summary(
        grades=grades,
        result_file_errors=result_file_errors,
        isolation=isolation_report(),
        diagnostics=diagnostics,
    )
    write_jsonl(grades_out, [grade.as_dict() for grade in grades])
    summary_out.parent.mkdir(parents=True, exist_ok=True)
    summary_out.write_text(json.dumps(summary.as_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tasks", required=True, type=Path)
    parser.add_argument("--results", required=True, type=Path)
    parser.add_argument("--grades-out", required=True, type=Path)
    parser.add_argument("--summary-out", required=True, type=Path)
    parser.add_argument("--enable-sheaf-diagnostic", action="store_true")
    parser.add_argument("--task-manifest", type=Path)
    parser.add_argument("--trusted-checksums", type=Path)
    args = parser.parse_args(argv)
    summary = verify_files(
        tasks_path=args.tasks,
        results_path=args.results,
        grades_out=args.grades_out,
        summary_out=args.summary_out,
        enable_sheaf_diagnostic=args.enable_sheaf_diagnostic,
        task_manifest_path=args.task_manifest,
        trusted_checksums_path=args.trusted_checksums,
    )
    print(json.dumps(summary.as_dict(), sort_keys=True))


if __name__ == "__main__":
    main()
