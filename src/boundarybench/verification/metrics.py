"""Selective-risk and safety metrics for verifier summaries."""

from __future__ import annotations

from typing import Any

from boundarybench.verification.graders import ADMITTING_ACTIONS, NON_ADMIT_ACTIONS
from boundarybench.verification.types import VerificationGrade, VerificationSummary


def compute_summary(
    *,
    grades: list[VerificationGrade],
    result_file_errors: list[str],
    isolation: dict[str, Any],
    diagnostics: dict[str, Any],
) -> VerificationSummary:
    task_count = len(grades)
    parsed = [grade for grade in grades if grade.parsed]
    covered = [grade for grade in parsed if grade.observed_action != "abstain"]
    covered_failures = [grade for grade in covered if not grade.passed]
    false_accepts = [
        grade
        for grade in parsed
        if grade.observed_action in ADMITTING_ACTIONS and grade.expected_action in NON_ADMIT_ACTIONS
    ]
    false_rejects = [
        grade
        for grade in parsed
        if grade.observed_action in NON_ADMIT_ACTIONS and grade.expected_action in ADMITTING_ACTIONS
    ]
    abstentions = [grade for grade in parsed if grade.observed_action == "abstain"]
    quarantined = [grade for grade in grades if grade.quarantine.quarantined]
    result_file_valid = not result_file_errors
    metrics_valid = result_file_valid
    coverage = len(covered) / task_count if task_count else 0.0
    selective_risk = len(covered_failures) / len(covered) if covered else None
    passed_count = sum(1 for grade in grades if grade.passed)
    score = sum(grade.score for grade in grades)
    invalid_reason = None
    if not result_file_valid:
        passed_count = 0
        score = 0
        coverage = 0.0
        selective_risk = None
        invalid_reason = "result_file_errors"
    return VerificationSummary(
        task_count=task_count,
        parsed_count=len(parsed),
        passed_count=passed_count,
        score=score,
        coverage=coverage,
        selective_risk=selective_risk,
        false_accept_count=len(false_accepts),
        false_reject_count=len(false_rejects),
        abstention_count=len(abstentions),
        quarantine_count=len(quarantined),
        result_file_errors=tuple(result_file_errors),
        result_file_valid=result_file_valid,
        metrics_valid=metrics_valid,
        invalid_reason=invalid_reason,
        isolation=isolation,
        diagnostics=diagnostics,
    )
