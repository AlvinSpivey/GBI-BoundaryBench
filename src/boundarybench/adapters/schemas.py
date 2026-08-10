"""JSON schema constants and lightweight validators for adapter artifacts."""

from __future__ import annotations

from typing import Any

ADAPTER_MODES = (
    "open_weight_full_category",
    "token_top_k",
    "output_only",
    "local_surrogate_probe",
)

MODEL_REQUEST_JSON_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://gbi-boundarybench.local/schemas/model_request.schema.json",
    "title": "GBI BoundaryBench model request",
    "type": "object",
    "required": [
        "schema_version",
        "task_id",
        "prompt",
        "allowed_actions",
        "seed",
        "temperature",
        "max_output_tokens",
        "metadata",
    ],
    "additionalProperties": False,
    "properties": {
        "schema_version": {"const": "boundarybench.model_request.v1"},
        "task_id": {"type": "string", "minLength": 1},
        "prompt": {"type": "string", "minLength": 1},
        "allowed_actions": {"type": "array", "items": {"type": "string"}, "minItems": 1},
        "seed": {"type": ["integer", "null"]},
        "temperature": {"type": "number"},
        "max_output_tokens": {"type": "integer", "minimum": 1},
        "metadata": {"type": "object"},
    },
}

MODEL_PROVENANCE_JSON_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://gbi-boundarybench.local/schemas/model_provenance.schema.json",
    "title": "GBI BoundaryBench model provenance",
    "type": "object",
    "required": [
        "schema_version",
        "adapter_api_version",
        "provider",
        "model_id",
        "access_mode",
        "adapter_class",
        "access_time_utc",
        "prompt_sha256",
        "request_config_sha256",
        "seed",
        "code_commit",
        "data_manifest_sha256",
        "runtime",
        "retry_policy",
        "attempt_count",
        "latency_ms",
        "usage",
        "cost_usd",
        "external_request_id",
        "is_mock",
        "execution_status",
        "observed_evidence",
    ],
    "additionalProperties": False,
    "properties": {
        "schema_version": {"const": "boundarybench.model_provenance.v1"},
        "adapter_api_version": {"type": "string"},
        "provider": {"type": "string"},
        "model_id": {"type": "string"},
        "access_mode": {"enum": list(ADAPTER_MODES)},
        "adapter_class": {"type": "string"},
        "access_time_utc": {"type": "string"},
        "prompt_sha256": {"type": "string", "minLength": 64, "maxLength": 64},
        "request_config_sha256": {"type": "string", "minLength": 64, "maxLength": 64},
        "seed": {"type": ["integer", "null"]},
        "code_commit": {"type": ["string", "null"]},
        "data_manifest_sha256": {"type": ["string", "null"]},
        "runtime": {"type": "object"},
        "retry_policy": {"type": "object"},
        "attempt_count": {"type": "integer", "minimum": 1},
        "latency_ms": {"type": "number", "minimum": 0},
        "usage": {"type": ["object", "null"]},
        "cost_usd": {"type": ["number", "null"]},
        "external_request_id": {"type": ["string", "null"]},
        "is_mock": {"type": "boolean"},
        "execution_status": {"enum": ["completed", "mock_completed", "failed"]},
        "observed_evidence": {
            "type": "object",
            "required": ["full_category", "token_top_k", "output_text"],
            "additionalProperties": False,
            "properties": {
                "full_category": {"type": "boolean"},
                "token_top_k": {"type": "boolean"},
                "output_text": {"type": "boolean"},
            },
        },
    },
}

MODEL_RESPONSE_JSON_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://gbi-boundarybench.local/schemas/model_response.schema.json",
    "title": "GBI BoundaryBench model response",
    "type": "object",
    "required": [
        "schema_version",
        "request",
        "text",
        "parsed_json",
        "category_evidence",
        "token_top_k_evidence",
        "surrogate_report",
        "provenance",
        "errors",
    ],
    "additionalProperties": False,
    "properties": {
        "schema_version": {"const": "boundarybench.model_response.v1"},
        "request": MODEL_REQUEST_JSON_SCHEMA,
        "text": {"type": "string"},
        "parsed_json": {"type": ["object", "null"]},
        "category_evidence": {"type": ["object", "null"]},
        "token_top_k_evidence": {"type": ["object", "null"]},
        "surrogate_report": {"type": ["object", "null"]},
        "provenance": MODEL_PROVENANCE_JSON_SCHEMA,
        "errors": {"type": "array", "items": {"type": "string"}},
    },
}


def validate_model_request(request: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    required = MODEL_REQUEST_JSON_SCHEMA["required"]
    for key in required:
        if key not in request:
            errors.append(f"missing request.{key}")
    if errors:
        return errors
    if request["schema_version"] != "boundarybench.model_request.v1":
        errors.append("invalid model request schema_version")
    if not isinstance(request["task_id"], str) or not request["task_id"]:
        errors.append("invalid model request task_id")
    if not isinstance(request["prompt"], str) or not request["prompt"]:
        errors.append("invalid model request prompt")
    if not isinstance(request["allowed_actions"], list) or not request["allowed_actions"]:
        errors.append("allowed_actions must be non-empty list")
    if not isinstance(request["max_output_tokens"], int) or request["max_output_tokens"] < 1:
        errors.append("max_output_tokens must be positive integer")
    if not isinstance(request["metadata"], dict):
        errors.append("metadata must be object")
    return errors


def validate_model_provenance(provenance: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    required = MODEL_PROVENANCE_JSON_SCHEMA["required"]
    for key in required:
        if key not in provenance:
            errors.append(f"missing provenance.{key}")
    if errors:
        return errors
    if provenance["schema_version"] != "boundarybench.model_provenance.v1":
        errors.append("invalid model provenance schema_version")
    if provenance["access_mode"] not in ADAPTER_MODES:
        errors.append("invalid access_mode")
    if len(provenance["prompt_sha256"]) != 64:
        errors.append("invalid prompt_sha256")
    if len(provenance["request_config_sha256"]) != 64:
        errors.append("invalid request_config_sha256")
    if not isinstance(provenance["attempt_count"], int) or provenance["attempt_count"] < 1:
        errors.append("invalid attempt_count")
    if not isinstance(provenance["observed_evidence"], dict):
        errors.append("observed_evidence must be object")
    else:
        for key in ("full_category", "token_top_k", "output_text"):
            if not isinstance(provenance["observed_evidence"].get(key), bool):
                errors.append(f"observed_evidence.{key} must be boolean")
    return errors


def validate_model_response(response: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    required = MODEL_RESPONSE_JSON_SCHEMA["required"]
    for key in required:
        if key not in response:
            errors.append(f"missing response.{key}")
    if errors:
        return errors
    extra_keys = sorted(set(response) - set(MODEL_RESPONSE_JSON_SCHEMA["properties"]))
    if extra_keys:
        errors.append(f"unexpected response keys:{','.join(extra_keys)}")
    if response["schema_version"] != "boundarybench.model_response.v1":
        errors.append("invalid model response schema_version")
    if not isinstance(response["text"], str):
        errors.append("response text must be string")
    if not isinstance(response["errors"], list) or not all(isinstance(error, str) for error in response["errors"]):
        errors.append("errors must be list[str]")
    if not isinstance(response["request"], dict):
        errors.append("request must be object")
    else:
        errors.extend(validate_model_request(response["request"]))
    if not isinstance(response["provenance"], dict):
        errors.append("provenance must be object")
    else:
        errors.extend(validate_model_provenance(response["provenance"]))
    return errors

