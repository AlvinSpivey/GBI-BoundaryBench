"""JSON schema constants for PVE artifacts."""

from __future__ import annotations

from typing import Any

CRITERION_NAMES = ("schema", "exact", "graph", "temporal", "version", "evidence")

CRITERION_RESULT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["name", "passed", "status", "errors", "details"],
    "additionalProperties": False,
    "properties": {
        "name": {"enum": list(CRITERION_NAMES)},
        "passed": {"type": "boolean"},
        "status": {"type": "string"},
        "errors": {"type": "array", "items": {"type": "string"}},
        "details": {"type": "object"},
    },
}

QUARANTINE_RECORD_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["quarantined", "local_slices", "dependency_keys", "closure_task_ids", "reason"],
    "additionalProperties": False,
    "properties": {
        "quarantined": {"type": "boolean"},
        "local_slices": {"type": "array", "items": {"type": "string"}},
        "dependency_keys": {"type": "array", "items": {"type": "string"}},
        "closure_task_ids": {"type": "array", "items": {"type": "string"}},
        "reason": {"type": "string"},
    },
}

VERIFICATION_GRADE_JSON_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://gbi-boundarybench.local/schemas/verification_grade.schema.json",
    "title": "GBI BoundaryBench verification grade",
    "type": "object",
    "required": [
        "schema_version",
        "task_id",
        "parsed",
        "passed",
        "score",
        "status",
        "observed_action",
        "expected_action",
        "criteria",
        "quarantine",
        "errors",
    ],
    "additionalProperties": False,
    "properties": {
        "schema_version": {"const": "boundarybench.verification_grade.v1"},
        "task_id": {"type": "string"},
        "parsed": {"type": "boolean"},
        "passed": {"type": "boolean"},
        "score": {"type": "integer", "minimum": 0, "maximum": 1},
        "status": {"type": "string"},
        "observed_action": {"type": "string"},
        "expected_action": {"type": "string"},
        "criteria": {"type": "array", "items": CRITERION_RESULT_SCHEMA, "minItems": 1},
        "quarantine": QUARANTINE_RECORD_SCHEMA,
        "errors": {"type": "array", "items": {"type": "string"}},
    },
}

VERIFICATION_SUMMARY_JSON_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://gbi-boundarybench.local/schemas/verification_summary.schema.json",
    "title": "GBI BoundaryBench verification summary",
    "type": "object",
    "required": [
        "schema_version",
        "task_count",
        "parsed_count",
        "passed_count",
        "score",
        "coverage",
        "selective_risk",
        "false_accept_count",
        "false_reject_count",
        "abstention_count",
        "quarantine_count",
        "result_file_errors",
        "isolation",
        "diagnostics",
    ],
    "additionalProperties": False,
    "properties": {
        "schema_version": {"const": "boundarybench.verification_summary.v1"},
        "task_count": {"type": "integer", "minimum": 0},
        "parsed_count": {"type": "integer", "minimum": 0},
        "passed_count": {"type": "integer", "minimum": 0},
        "score": {"type": "integer", "minimum": 0},
        "coverage": {"type": "number", "minimum": 0, "maximum": 1},
        "selective_risk": {"type": ["number", "null"], "minimum": 0, "maximum": 1},
        "false_accept_count": {"type": "integer", "minimum": 0},
        "false_reject_count": {"type": "integer", "minimum": 0},
        "abstention_count": {"type": "integer", "minimum": 0},
        "quarantine_count": {"type": "integer", "minimum": 0},
        "result_file_errors": {"type": "array", "items": {"type": "string"}},
        "isolation": {"type": "object"},
        "diagnostics": {"type": "object"},
    },
}

