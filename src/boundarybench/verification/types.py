"""Typed records for the Programmatic Verification Engine."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

CriterionName = Literal["schema", "exact", "graph", "temporal", "version", "evidence"]


@dataclass(frozen=True)
class CriterionResult:
    name: CriterionName
    passed: bool
    status: str
    errors: tuple[str, ...] = ()
    details: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "passed": self.passed,
            "status": self.status,
            "errors": list(self.errors),
            "details": self.details or {},
        }


@dataclass(frozen=True)
class QuarantineRecord:
    quarantined: bool
    local_slices: tuple[str, ...]
    dependency_keys: tuple[str, ...]
    closure_task_ids: tuple[str, ...]
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "quarantined": self.quarantined,
            "local_slices": list(self.local_slices),
            "dependency_keys": list(self.dependency_keys),
            "closure_task_ids": list(self.closure_task_ids),
            "reason": self.reason,
        }


@dataclass(frozen=True)
class VerificationGrade:
    task_id: str
    parsed: bool
    passed: bool
    score: int
    status: str
    observed_action: str
    expected_action: str
    criteria: tuple[CriterionResult, ...]
    quarantine: QuarantineRecord
    errors: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "boundarybench.verification_grade.v1",
            "task_id": self.task_id,
            "parsed": self.parsed,
            "passed": self.passed,
            "score": self.score,
            "status": self.status,
            "observed_action": self.observed_action,
            "expected_action": self.expected_action,
            "criteria": [criterion.as_dict() for criterion in self.criteria],
            "quarantine": self.quarantine.as_dict(),
            "errors": list(self.errors),
        }


@dataclass(frozen=True)
class VerificationSummary:
    task_count: int
    parsed_count: int
    passed_count: int
    score: int
    coverage: float
    selective_risk: float | None
    false_accept_count: int
    false_reject_count: int
    abstention_count: int
    quarantine_count: int
    result_file_errors: tuple[str, ...]
    result_file_valid: bool
    metrics_valid: bool
    invalid_reason: str | None
    isolation: dict[str, Any]
    diagnostics: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "boundarybench.verification_summary.v1",
            "task_count": self.task_count,
            "parsed_count": self.parsed_count,
            "passed_count": self.passed_count,
            "score": self.score,
            "coverage": self.coverage,
            "selective_risk": self.selective_risk,
            "false_accept_count": self.false_accept_count,
            "false_reject_count": self.false_reject_count,
            "abstention_count": self.abstention_count,
            "quarantine_count": self.quarantine_count,
            "result_file_errors": list(self.result_file_errors),
            "result_file_valid": self.result_file_valid,
            "metrics_valid": self.metrics_valid,
            "invalid_reason": self.invalid_reason,
            "isolation": self.isolation,
            "diagnostics": self.diagnostics,
        }
