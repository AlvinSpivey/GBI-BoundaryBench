"""Typed task and result contracts for BoundaryBench v0.1 tasks."""

from __future__ import annotations

from typing import Any, Literal, TypedDict

Action = Literal[
    "admit",
    "admit_historical_only",
    "quarantine_slice",
    "abstain",
    "expert_review",
    "reject",
]

TaskFamily = Literal[
    "patient_identity_normalization",
    "orphan_duplicate_detection",
    "field_anomaly_bleed",
    "code_system_version_validation",
    "rpms_to_fhir_mapping",
    "temporal_status_classification",
    "evidence_sufficiency",
    "policy_action_selection",
]

ALLOWED_ACTIONS: tuple[Action, ...] = (
    "admit",
    "admit_historical_only",
    "quarantine_slice",
    "abstain",
    "expert_review",
    "reject",
)

TASK_FAMILIES: tuple[TaskFamily, ...] = (
    "patient_identity_normalization",
    "orphan_duplicate_detection",
    "field_anomaly_bleed",
    "code_system_version_validation",
    "rpms_to_fhir_mapping",
    "temporal_status_classification",
    "evidence_sufficiency",
    "policy_action_selection",
)

ACTION_SEMANTICS: dict[Action, str] = {
    "admit": "Accept the slice because required evidence is present and policy gates pass.",
    "admit_historical_only": "Accept only as historical/legacy evidence; do not treat as current normalized truth.",
    "quarantine_slice": "Localize the failure to this record/slice and exclude it from admitted output.",
    "abstain": "Return no asserted mapping/action because required evidence is absent or ambiguous.",
    "expert_review": "Escalate to deterministic review queue; do not silently coerce the value.",
    "reject": "Reject malformed, unsupported, or unsafe evidence/output.",
}


class EvidenceRef(TypedDict, total=False):
    ref_id: str
    artifact: str
    table: str
    row_id: str
    column_name: str
    source_record_id: str
    event_id: str
    field_path: str


class Reference(TypedDict):
    action: Action
    answer: dict[str, Any]
    required_evidence: list[str]
    rationale: str


class AbstentionPolicy(TypedDict):
    allowed: bool
    rewarded_when: str
    unsafe_when: str


class Task(TypedDict):
    schema_version: str
    task_id: str
    split: str
    family: TaskFamily
    prompt: str
    input: dict[str, Any]
    allowed_actions: list[Action]
    action_semantics: dict[str, str]
    abstention: AbstentionPolicy
    evidence_refs: list[EvidenceRef]
    failure_slices: list[str]
    reference: Reference


class Result(TypedDict, total=False):
    schema_version: str
    task_id: str
    action: Action
    answer: dict[str, Any]
    evidence_refs: list[str]
    confidence: float


TASK_JSON_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://gbi-boundarybench.local/schemas/task.schema.json",
    "title": "GBI BoundaryBench task",
    "type": "object",
    "required": [
        "schema_version",
        "task_id",
        "split",
        "family",
        "prompt",
        "input",
        "allowed_actions",
        "action_semantics",
        "abstention",
        "evidence_refs",
        "failure_slices",
        "reference",
    ],
    "additionalProperties": False,
    "properties": {
        "schema_version": {"const": "boundarybench.task.v1"},
        "task_id": {"type": "string", "minLength": 1},
        "split": {"enum": ["public_dev", "public_validation", "sealed_test"]},
        "family": {"enum": list(TASK_FAMILIES)},
        "prompt": {"type": "string", "minLength": 1},
        "input": {"type": "object"},
        "allowed_actions": {
            "type": "array",
            "items": {"enum": list(ALLOWED_ACTIONS)},
            "minItems": 1,
            "uniqueItems": True,
        },
        "action_semantics": {
            "type": "object",
            "required": list(ALLOWED_ACTIONS),
            "additionalProperties": False,
            "properties": {action: {"type": "string", "minLength": 1} for action in ALLOWED_ACTIONS},
        },
        "abstention": {
            "type": "object",
            "required": ["allowed", "rewarded_when", "unsafe_when"],
            "additionalProperties": False,
            "properties": {
                "allowed": {"type": "boolean"},
                "rewarded_when": {"type": "string"},
                "unsafe_when": {"type": "string"},
            },
        },
        "evidence_refs": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["ref_id", "artifact", "table", "row_id", "source_record_id"],
                "additionalProperties": False,
                "properties": {
                    "ref_id": {"type": "string", "minLength": 1},
                    "artifact": {"type": "string", "minLength": 1},
                    "table": {"type": "string", "minLength": 1},
                    "row_id": {"type": "string", "minLength": 1},
                    "column_name": {"type": "string"},
                    "source_record_id": {"type": "string", "minLength": 1},
                    "event_id": {"type": "string"},
                    "field_path": {"type": "string"},
                },
            },
            "minItems": 1,
        },
        "failure_slices": {"type": "array", "items": {"type": "string"}, "minItems": 1},
        "reference": {
            "type": "object",
            "required": ["action", "answer", "required_evidence", "rationale"],
            "additionalProperties": False,
            "properties": {
                "action": {"enum": list(ALLOWED_ACTIONS)},
                "answer": {"type": "object"},
                "required_evidence": {"type": "array", "items": {"type": "string"}},
                "rationale": {"type": "string"},
            },
        },
    },
}

RESULT_JSON_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://gbi-boundarybench.local/schemas/result.schema.json",
    "title": "GBI BoundaryBench result",
    "type": "object",
    "required": ["schema_version", "task_id", "action", "answer", "evidence_refs"],
    "additionalProperties": False,
    "properties": {
        "schema_version": {"const": "boundarybench.result.v1"},
        "task_id": {"type": "string", "minLength": 1},
        "action": {"enum": list(ALLOWED_ACTIONS)},
        "answer": {"type": "object"},
        "evidence_refs": {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
    },
}


def validate_task(task: dict[str, Any]) -> list[str]:
    """Return schema/contract errors for a task. Empty means valid."""

    errors: list[str] = []
    allowed_task_keys = set(TASK_JSON_SCHEMA["properties"])
    extra_task_keys = sorted(set(task) - allowed_task_keys)
    if extra_task_keys:
        errors.append(f"unexpected task keys:{','.join(extra_task_keys)}")
    required = TASK_JSON_SCHEMA["required"]
    for key in required:
        if key not in task:
            errors.append(f"missing task.{key}")
    if errors:
        return errors
    if task["schema_version"] != "boundarybench.task.v1":
        errors.append("invalid task schema_version")
    if task["family"] not in TASK_FAMILIES:
        errors.append("invalid task family")
    if not task["task_id"]:
        errors.append("empty task_id")
    if not task["prompt"]:
        errors.append("empty prompt")
    if not isinstance(task["input"], dict):
        errors.append("input must be object")
    actions = task["allowed_actions"]
    if (
        not isinstance(actions, list)
        or not actions
        or any(action not in ALLOWED_ACTIONS for action in actions)
    ):
        errors.append("allowed_actions must be non-empty valid actions")
        actions = []
    elif len(actions) != len(set(actions)):
        errors.append("allowed_actions must be unique")
    semantics = task["action_semantics"]
    if not isinstance(semantics, dict) or any(action not in semantics for action in actions):
        errors.append("action_semantics must define each allowed action")
    reference = task["reference"]
    if not isinstance(reference, dict):
        errors.append("reference must be object")
        reference = {}
    for key in ("action", "answer", "required_evidence", "rationale"):
        if key not in reference:
            errors.append(f"missing task.reference.{key}")
    if errors:
        return errors
    if reference["action"] not in actions:
        errors.append("reference action not allowed")
    if not isinstance(reference["answer"], dict):
        errors.append("reference answer must be object")
    evidence_refs = task["evidence_refs"]
    if not isinstance(evidence_refs, list) or not evidence_refs:
        errors.append("evidence_refs must be non-empty list")
        evidence_ids = set()
    elif not all(isinstance(ref, dict) for ref in evidence_refs):
        errors.append("evidence_refs entries must be objects")
        evidence_ids = set()
    else:
        evidence_ids_list = [ref.get("ref_id") for ref in evidence_refs]
        evidence_ids = set(evidence_ids_list)
        duplicate_evidence_ids = sorted(
            ref_id
            for ref_id in evidence_ids
            if ref_id is not None and evidence_ids_list.count(ref_id) > 1
        )
        if duplicate_evidence_ids:
            errors.append(f"duplicate evidence ref_id:{','.join(duplicate_evidence_ids)}")
    if not evidence_ids or None in evidence_ids:
        errors.append("evidence_refs require ref_id")
    required_evidence = reference["required_evidence"]
    if not isinstance(required_evidence, list) or not all(isinstance(ref_id, str) for ref_id in required_evidence):
        errors.append("reference.required_evidence must be list[str]")
        required_evidence = []
    elif len(required_evidence) != len(set(required_evidence)):
        errors.append("reference.required_evidence must be unique")
    for required_ref in required_evidence:
        if required_ref not in evidence_ids:
            errors.append(f"reference requires unknown evidence ref {required_ref}")
    if not task["failure_slices"]:
        errors.append("failure_slices must be non-empty")
    abstention = task["abstention"]
    if not isinstance(abstention, dict):
        errors.append("abstention must be object")
        abstention = {}
    if not isinstance(abstention.get("allowed"), bool):
        errors.append("abstention.allowed must be boolean")
    return errors


def validate_result(result: dict[str, Any], task: dict[str, Any] | None = None) -> list[str]:
    """Return schema/contract errors for a candidate result. Empty means valid."""

    errors: list[str] = []
    allowed_keys = set(RESULT_JSON_SCHEMA["properties"])
    extra_keys = sorted(set(result) - allowed_keys)
    if extra_keys:
        errors.append(f"unexpected result keys:{','.join(extra_keys)}")
    required = RESULT_JSON_SCHEMA["required"]
    for key in required:
        if key not in result:
            errors.append(f"missing result.{key}")
    if errors:
        return errors
    if result["schema_version"] != "boundarybench.result.v1":
        errors.append("invalid result schema_version")
    if not result["task_id"]:
        errors.append("empty task_id")
    if result["action"] not in ALLOWED_ACTIONS:
        errors.append("invalid action")
    if not isinstance(result["answer"], dict):
        errors.append("answer must be object")
    if not isinstance(result["evidence_refs"], list) or not all(
        isinstance(ref, str) for ref in result["evidence_refs"]
    ):
        errors.append("evidence_refs must be list[str]")
    if "confidence" in result:
        confidence = result["confidence"]
        if isinstance(confidence, bool) or not isinstance(confidence, int | float):
            errors.append("confidence must be number")
        elif not 0.0 <= confidence <= 1.0:
            errors.append("confidence outside [0,1]")
    if task is not None:
        if result["task_id"] != task["task_id"]:
            errors.append("result task_id mismatch")
        if result["action"] not in task["allowed_actions"]:
            errors.append("result action not allowed for task")
    return errors
