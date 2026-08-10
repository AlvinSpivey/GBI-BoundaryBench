"""Deterministic task result parsing and grading."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from boundarybench.tasks.io import read_jsonl, write_jsonl
from boundarybench.tasks.schemas import validate_result, validate_task


@dataclass(frozen=True)
class Grade:
    task_id: str
    parsed: bool
    passed: bool
    score: int
    status: str
    observed_action: str
    expected_action: str
    errors: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "parsed": self.parsed,
            "passed": self.passed,
            "score": self.score,
            "status": self.status,
            "observed_action": self.observed_action,
            "expected_action": self.expected_action,
            "errors": list(self.errors),
        }


def _reject_duplicate_json_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    decoded: dict[str, Any] = {}
    for key, value in pairs:
        if key in decoded:
            raise ValueError(f"duplicate_json_key:{key}")
        decoded[key] = value
    return decoded


def safe_parse_result(payload: str) -> tuple[dict[str, Any] | None, list[str]]:
    """Parse result JSON safely.

    Malformed or non-object payloads are rejected. They never imply success.
    """

    try:
        decoded = json.loads(payload, object_pairs_hook=_reject_duplicate_json_keys)
    except json.JSONDecodeError as exc:
        return None, [f"json_parse_error:{exc.msg}"]
    except ValueError as exc:
        return None, [str(exc)]
    if not isinstance(decoded, dict):
        return None, ["result_not_object"]
    return decoded, []


def grade_result(task: dict[str, Any], result: dict[str, Any] | None, parse_errors: list[str] | None = None) -> Grade:
    task_errors = validate_task(task)
    if task_errors:
        return Grade(
            task_id=str(task.get("task_id", "<invalid-task>")),
            parsed=False,
            passed=False,
            score=0,
            status="invalid_task_contract",
            observed_action="reject",
            expected_action=str(task.get("reference", {}).get("action", "")),
            errors=tuple(task_errors),
        )
    if result is None:
        return Grade(
            task_id=task["task_id"],
            parsed=False,
            passed=False,
            score=0,
            status="safe_parse_reject",
            observed_action="reject",
            expected_action=task["reference"]["action"],
            errors=tuple(parse_errors or ["missing_result"]),
        )
    result_errors = validate_result(result, task)
    if result_errors:
        return Grade(
            task_id=task["task_id"],
            parsed=False,
            passed=False,
            score=0,
            status="safe_schema_reject",
            observed_action=str(result.get("action", "reject")),
            expected_action=task["reference"]["action"],
            errors=tuple(result_errors),
        )
    required_evidence = set(task["reference"]["required_evidence"])
    observed_evidence = set(result["evidence_refs"])
    missing_evidence = sorted(required_evidence - observed_evidence)
    action_ok = result["action"] == task["reference"]["action"]
    answer_ok = result["answer"] == task["reference"]["answer"]
    evidence_ok = not missing_evidence
    passed = action_ok and answer_ok and evidence_ok
    errors = []
    if not action_ok:
        errors.append("wrong_action")
    if not answer_ok:
        errors.append("wrong_answer")
    if not evidence_ok:
        errors.append(f"missing_evidence:{','.join(missing_evidence)}")
    return Grade(
        task_id=task["task_id"],
        parsed=True,
        passed=passed,
        score=1 if passed else 0,
        status="pass" if passed else "fail",
        observed_action=result["action"],
        expected_action=task["reference"]["action"],
        errors=tuple(errors),
    )


def oracle_result(task: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "boundarybench.result.v1",
        "task_id": task["task_id"],
        "action": task["reference"]["action"],
        "answer": task["reference"]["answer"],
        "evidence_refs": task["reference"]["required_evidence"],
        "confidence": 1.0,
    }


def noop_result(task: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "boundarybench.result.v1",
        "task_id": task["task_id"],
        "action": "abstain",
        "answer": {},
        "evidence_refs": [],
        "confidence": 0.0,
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


def grade_files(tasks_path: Path, results_path: Path, out_path: Path) -> dict[str, Any]:
    tasks = {task["task_id"]: task for task in read_jsonl(tasks_path)}
    results, result_file_errors = _read_results_by_task(results_path)
    grades = []
    for task_id, task in tasks.items():
        result = results.get(task_id)
        grades.append(grade_result(task, result).as_dict())
    summary = {
        "tasks": len(tasks),
        "passed": sum(1 for grade in grades if grade["passed"]),
        "score": sum(grade["score"] for grade in grades),
        "result_file_errors": result_file_errors,
    }
    write_jsonl(out_path, grades)
    return summary


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tasks", required=True, type=Path)
    parser.add_argument("--results", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)
    print(json.dumps(grade_files(args.tasks, args.results, args.out), sort_keys=True))


if __name__ == "__main__":
    main()
