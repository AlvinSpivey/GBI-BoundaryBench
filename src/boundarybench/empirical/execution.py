"""Stage 10.5 empirical model execution infrastructure.

This module executes model calls only from answer-key-free model-input tasks.
It deliberately does not import or read the trusted verifier package, oracle
results, hidden generation seeds, or held-out references.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import importlib
import json
import os
from pathlib import Path
import re
import subprocess
import time
from typing import Any, Protocol, TextIO
import urllib.error
import urllib.request

from boundarybench.empirical.freeze import (
    FREEZE_VALIDATION_EXECUTION_ISOLATED,
    FREEZE_VALIDATION_FULL,
    validate_freeze_manifest,
)
from boundarybench.tasks.grade import safe_parse_result
from boundarybench.tasks.io import read_jsonl, write_jsonl
from boundarybench.tasks.schemas import ALLOWED_ACTIONS, TASK_FAMILIES, validate_result
from boundarybench.verification.references import sha256_file


EMPIRICAL_RESULT_SCHEMA_VERSION = "boundarybench.empirical_result.v1"
MODEL_RUN_MANIFEST_SCHEMA_VERSION = "boundarybench.empirical_model_run_manifest.v1"
MODEL_INPUT_SPLIT_MANIFEST_SCHEMA_VERSION = "boundarybench.model_input_split_manifest.v1"
ALLOWED_EVIDENCE_MODES = ("output_only", "token_top_k", "full_category_evidence")
OPEN_WEIGHT_FAMILIES = ("open_weight_family_a", "open_weight_family_b")
CLOSED_PROVIDER_FAMILIES = ("closed_provider_a", "closed_provider_b")
COMMIT_SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")


@dataclass(frozen=True)
class GenerationConfig:
    """Generation settings persisted with each task provenance record."""

    temperature: float = 0.0
    max_output_tokens: int = 512
    token_top_k: int = 5
    seed: int | None = None
    timeout_seconds: float = 120.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "temperature": self.temperature,
            "max_output_tokens": self.max_output_tokens,
            "token_top_k": self.token_top_k,
            "seed": self.seed,
            "timeout_seconds": self.timeout_seconds,
        }


@dataclass(frozen=True)
class RuntimeResponse:
    """Raw runtime/provider response plus normalized metadata."""

    text: str
    raw_response: dict[str, Any]
    provider_request_id: str | None = None
    usage: dict[str, Any] | None = None
    provider_reported_cost_usd: float | None = None
    model_revision_or_digest: str | None = None
    evidence: dict[str, Any] | None = None
    runtime_metadata: dict[str, Any] | None = None
    generated_token_count: int | None = None


class TaskRunner(Protocol):
    """Minimal execution protocol for provider/runtime implementations."""

    def execute(self, *, task: dict[str, Any], prompt: str, config: GenerationConfig) -> RuntimeResponse:
        """Execute one answer-key-free task."""


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def prompt_hash_for_task(task: dict[str, Any]) -> str:
    return sha256_text(build_prompt(task))


def build_prompt(task: dict[str, Any]) -> str:
    """Build the model prompt from answer-key-free task content only."""

    allowed = ", ".join(task.get("allowed_actions", []))
    payload = {
        "schema_version": task.get("schema_version"),
        "task_id": task.get("task_id"),
        "split": task.get("split"),
        "family": task.get("family"),
        "prompt": task.get("prompt"),
        "input": task.get("input"),
        "allowed_actions": task.get("allowed_actions"),
        "action_semantics": task.get("action_semantics"),
        "abstention": task.get("abstention"),
        "evidence_refs": task.get("evidence_refs"),
        "failure_slices": task.get("failure_slices"),
    }
    return (
        "You are completing a synthetic BoundaryBench legacy-EHR boundary task.\n"
        "Return exactly one JSON object and no surrounding prose.\n"
        "The object must conform to boundarybench.result.v1 with keys:\n"
        "schema_version, task_id, action, answer, evidence_refs, and optional confidence.\n"
        f"The action must be one of: {allowed}.\n"
        "Use only the task content below. Do not use tools, browsing, retrieval, or external context.\n"
        "Task JSON:\n"
        f"{json.dumps(payload, sort_keys=True, separators=(',', ':'))}"
    )


FORBIDDEN_ANSWER_KEY_FIELDS = frozenset(
    {
        "reference",
        "reference_action",
        "reference_answer",
        "reference_rationale",
        "oracle",
        "oracle_result",
        "expected_action",
        "expected_answer",
        "gold",
        "gold_answer",
        "gold_label",
        "hidden_generation_seed",
    }
)


def forbidden_answer_key_field_paths(value: Any, path: str = "$") -> list[str]:
    """Return forbidden answer-key JSON field paths.

    This inspects object field names only. Natural-language string values may
    contain words such as "reference", "references", "oracle", or "gold"
    without being treated as answer-key leakage.
    """

    found: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if isinstance(key, str) else f"{path}.<non_string_key>"
            if isinstance(key, str) and key in FORBIDDEN_ANSWER_KEY_FIELDS:
                found.append(child_path)
            found.extend(forbidden_answer_key_field_paths(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(forbidden_answer_key_field_paths(child, f"{path}[{index}]"))
    return found


def validate_answer_key_free_tasks(tasks: list[dict[str, Any]]) -> None:
    for task in tasks:
        found = forbidden_answer_key_field_paths(task)
        if found:
            raise ValueError(f"model_input_contains_forbidden_answer_key_fields:{task.get('task_id')}:{','.join(found)}")


def _repo_path(repo_root: Path, path: Path) -> Path:
    return path if path.is_absolute() else repo_root / path


def _canonical_model_input_paths(repo_root: Path) -> dict[str, tuple[Path, Path]]:
    return {
        "heldout_eval": (
            (repo_root / "data/empirical/v0_1/heldout_eval/model_inputs/tasks.jsonl").resolve(),
            (repo_root / "data/empirical/v0_1/heldout_eval/model_inputs/manifest.json").resolve(),
        ),
        "public_dev": (
            (repo_root / "data/empirical/v0_1/public_dev/model_inputs/tasks.jsonl").resolve(),
            (repo_root / "data/empirical/v0_1/public_dev/model_inputs/manifest.json").resolve(),
        ),
    }


def canonical_model_input_split(*, repo_root: Path, model_inputs: Path, model_input_manifest: Path) -> str | None:
    actual_tasks = _repo_path(repo_root, model_inputs).resolve()
    actual_manifest = _repo_path(repo_root, model_input_manifest).resolve()
    for split_name, (canonical_tasks, canonical_manifest) in _canonical_model_input_paths(repo_root).items():
        if actual_tasks == canonical_tasks and actual_manifest == canonical_manifest:
            return split_name
    return None


def validate_model_input_paths(
    *,
    model_inputs: Path,
    model_input_manifest: Path,
    repo_root: Path,
    allow_public_dev_smoke: bool = False,
) -> None:
    """Reject obvious reference/oracle paths before execution."""

    for path in (model_inputs, model_input_manifest):
        parts = set(path.parts)
        forbidden = {"trusted_verifier_package", "trusted", "oracle_results.jsonl", "task_metadata.jsonl"}
        overlap = parts & forbidden
        if overlap:
            raise ValueError(f"forbidden_model_execution_path:{path}:{','.join(sorted(overlap))}")
    if model_inputs.name != "tasks.jsonl":
        raise ValueError("model_inputs_must_be_tasks_jsonl")
    if model_input_manifest.name != "manifest.json":
        raise ValueError("model_input_manifest_must_be_manifest_json")
    actual_tasks = _repo_path(repo_root, model_inputs).resolve()
    actual_manifest = _repo_path(repo_root, model_input_manifest).resolve()
    if actual_tasks.parent != actual_manifest.parent:
        raise ValueError("model_inputs_and_manifest_must_share_directory")
    split_name = canonical_model_input_split(
        repo_root=repo_root,
        model_inputs=model_inputs,
        model_input_manifest=model_input_manifest,
    )
    if split_name == "heldout_eval":
        return
    if allow_public_dev_smoke and split_name == "public_dev":
        return
    canonical_public_tasks, canonical_public_manifest = _canonical_model_input_paths(repo_root)["public_dev"]
    if actual_tasks == canonical_public_tasks or actual_manifest == canonical_public_manifest:
        raise ValueError("model_execution_requires_heldout_eval_model_inputs")
    raise ValueError("model_execution_requires_canonical_model_inputs")


def validate_smoke_task_limit_usage(
    *,
    repo_root: Path,
    model_inputs: Path,
    model_input_manifest: Path,
    allow_public_dev_smoke: bool,
    smoke_task_limit: int | None,
) -> None:
    if smoke_task_limit is None:
        return
    if isinstance(smoke_task_limit, bool) or not isinstance(smoke_task_limit, int) or smoke_task_limit <= 0:
        raise ValueError("smoke_task_limit_must_be_positive_integer")
    if not allow_public_dev_smoke:
        raise ValueError("smoke_task_limit_requires_allow_public_dev_smoke")
    split_name = canonical_model_input_split(
        repo_root=repo_root,
        model_inputs=model_inputs,
        model_input_manifest=model_input_manifest,
    )
    if split_name != "public_dev":
        raise ValueError("smoke_task_limit_only_allowed_for_public_dev_smoke")


def _repo_relative_posix(repo_root: Path, path: Path) -> str:
    resolved_root = repo_root.resolve()
    resolved_path = path.resolve()
    try:
        return resolved_path.relative_to(resolved_root).as_posix()
    except ValueError:
        return resolved_path.as_posix()


def validate_model_input_task_schemas(tasks: list[dict[str, Any]]) -> None:
    errors: list[str] = []
    required = {
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
    }
    allowed_keys = set(required)
    seen_task_ids: set[str] = set()
    for index, task in enumerate(tasks):
        task_id = task.get("task_id", f"<index:{index}>")
        extra = sorted(set(task) - allowed_keys)
        if extra:
            errors.append(f"{task_id}:unexpected_model_input_task_keys:{','.join(extra)}")
        missing = sorted(required - set(task))
        if missing:
            errors.append(f"{task_id}:missing_model_input_task_keys:{','.join(missing)}")
            continue
        if task["schema_version"] != "boundarybench.model_input_task.v1":
            errors.append(f"{task_id}:invalid_model_input_schema_version")
        if not isinstance(task["task_id"], str) or not task["task_id"]:
            errors.append(f"{task_id}:invalid_task_id")
        elif task["task_id"] in seen_task_ids:
            errors.append(f"{task_id}:duplicate_task_id")
        else:
            seen_task_ids.add(task["task_id"])
        if task["split"] not in {"public_dev", "sealed_test"}:
            errors.append(f"{task_id}:invalid_split")
        if task["family"] not in TASK_FAMILIES:
            errors.append(f"{task_id}:invalid_family")
        if not isinstance(task["prompt"], str) or not task["prompt"]:
            errors.append(f"{task_id}:invalid_prompt")
        if not isinstance(task["input"], dict):
            errors.append(f"{task_id}:input_must_be_object")
        actions = task["allowed_actions"]
        if (
            not isinstance(actions, list)
            or not actions
            or any(action not in ALLOWED_ACTIONS for action in actions)
            or len(actions) != len(set(actions))
        ):
            errors.append(f"{task_id}:invalid_allowed_actions")
            actions = []
        semantics = task["action_semantics"]
        if not isinstance(semantics, dict) or any(action not in semantics for action in actions):
            errors.append(f"{task_id}:invalid_action_semantics")
        abstention = task["abstention"]
        if not isinstance(abstention, dict) or not isinstance(abstention.get("allowed"), bool):
            errors.append(f"{task_id}:invalid_abstention")
        evidence_refs = task["evidence_refs"]
        if not isinstance(evidence_refs, list) or not evidence_refs or not all(isinstance(ref, dict) for ref in evidence_refs):
            errors.append(f"{task_id}:invalid_evidence_refs")
        elif any(not isinstance(ref.get("ref_id"), str) or not ref.get("ref_id") for ref in evidence_refs):
            errors.append(f"{task_id}:evidence_refs_require_ref_id")
        if not isinstance(task["failure_slices"], list) or not task["failure_slices"]:
            errors.append(f"{task_id}:invalid_failure_slices")
    if errors:
        raise ValueError("model_input_task_schema_validation_failed:" + ";".join(errors))


def _counts_by_key(tasks: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for task in tasks:
        value = task.get(key)
        if isinstance(value, str):
            counts[value] = counts.get(value, 0) + 1
    return counts


def validate_model_input_package(
    *,
    repo_root: Path,
    model_inputs: Path,
    model_input_manifest: Path,
    freeze_manifest: Path,
    split_name: str,
    tasks: list[dict[str, Any]],
    freeze_validation_mode: str = FREEZE_VALIDATION_FULL,
    expected_freeze_manifest_sha256: str | None = None,
) -> None:
    errors: list[str] = []
    freeze_errors = validate_freeze_manifest(
        repo_root=repo_root,
        freeze_manifest_path=freeze_manifest,
        validation_mode=freeze_validation_mode,
        expected_freeze_manifest_sha256=expected_freeze_manifest_sha256,
    )
    errors.extend(f"freeze:{error}" for error in freeze_errors)
    actual_tasks = _repo_path(repo_root, model_inputs).resolve()
    actual_manifest = _repo_path(repo_root, model_input_manifest).resolve()
    try:
        manifest = json.loads(actual_manifest.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        manifest = {}
        errors.append(f"model_input_manifest_json_parse_error:{exc.msg}")
    if manifest.get("schema_version") != MODEL_INPUT_SPLIT_MANIFEST_SCHEMA_VERSION:
        errors.append(f"invalid_model_input_manifest_schema_version:{manifest.get('schema_version')}")
    if manifest.get("answer_key_free") is not True:
        errors.append("model_input_manifest_not_marked_answer_key_free")
    expected_stage10_name = split_name
    expected_split = "sealed_test" if split_name == "heldout_eval" else "public_dev"
    if manifest.get("stage10_split_name") != expected_stage10_name:
        errors.append(f"model_input_manifest_stage10_split_mismatch:{manifest.get('stage10_split_name')}")
    if manifest.get("split") != expected_split:
        errors.append(f"model_input_manifest_split_mismatch:{manifest.get('split')}")
    if manifest.get("tasks_path") != _repo_relative_posix(repo_root, actual_tasks):
        errors.append("model_input_manifest_tasks_path_mismatch")
    if manifest.get("tasks_sha256") != sha256_file(actual_tasks):
        errors.append("model_input_manifest_tasks_sha256_mismatch")
    if manifest.get("task_count") != len(tasks):
        errors.append("model_input_manifest_task_count_mismatch")
    if manifest.get("families") != sorted(_counts_by_key(tasks, "family")):
        errors.append("model_input_manifest_families_mismatch")
    if manifest.get("family_counts") != _counts_by_key(tasks, "family"):
        errors.append("model_input_manifest_family_counts_mismatch")

    try:
        freeze_payload = json.loads(freeze_manifest.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        freeze_payload = {}
        errors.append(f"freeze_manifest_json_parse_error:{exc.msg}")
    if split_name == "heldout_eval":
        frozen_hashes = freeze_payload.get("heldout_model_input_hashes")
        if not isinstance(frozen_hashes, dict):
            errors.append("freeze_manifest_missing_heldout_model_input_hashes")
        else:
            for path in (actual_tasks, actual_manifest):
                rel_path = _repo_relative_posix(repo_root, path)
                expected_hash = frozen_hashes.get(rel_path)
                if expected_hash != sha256_file(path):
                    errors.append(f"freeze_manifest_heldout_model_input_hash_mismatch:{rel_path}")
    else:
        summaries = freeze_payload.get("split_summaries")
        summary = None
        if isinstance(summaries, list):
            for candidate in summaries:
                if isinstance(candidate, dict) and candidate.get("model_input_manifest_path") == "public_dev/model_inputs/manifest.json":
                    summary = candidate
                    break
        if summary is None:
            errors.append("freeze_manifest_missing_public_dev_split_summary")
        else:
            if summary.get("family_counts") != manifest.get("family_counts"):
                errors.append("freeze_manifest_public_dev_family_counts_mismatch")
            if sum(summary.get("family_counts", {}).values()) != len(tasks):
                errors.append("freeze_manifest_public_dev_task_count_mismatch")

    if errors:
        raise ValueError("model_input_package_validation_failed:" + ";".join(errors))


def git_commitish(repo_root: Path, *args: str) -> str:
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=repo_root,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "UNKNOWN"
    return completed.stdout.strip() or "UNKNOWN"


def benchmark_contract_commit(repo_root: Path, tag: str) -> str:
    return git_commitish(repo_root, "rev-list", "-n", "1", tag)


def normalize_commit_sha(value: str | None, *, field_name: str) -> str | None:
    if value is None:
        return None
    if not COMMIT_SHA_RE.fullmatch(value):
        raise ValueError(f"invalid_{field_name}_commit:must_be_40_hex")
    return value.lower()


def validate_explicit_commit_provenance(
    *,
    execution_isolated_validation: bool,
    runner_commit: str | None,
    benchmark_contract_commit_value: str | None,
) -> tuple[str | None, str | None]:
    normalized_runner = normalize_commit_sha(runner_commit, field_name="runner")
    normalized_contract = normalize_commit_sha(
        benchmark_contract_commit_value,
        field_name="benchmark_contract",
    )
    if execution_isolated_validation:
        if normalized_runner is None:
            raise ValueError("execution_isolated_validation_requires_runner_commit")
        if normalized_contract is None:
            raise ValueError("execution_isolated_validation_requires_benchmark_contract_commit")
    return normalized_runner, normalized_contract


def resolve_commit_provenance(
    *,
    repo_root: Path,
    benchmark_contract_tag: str,
    execution_isolated_validation: bool,
    runner_commit: str | None,
    benchmark_contract_commit_value: str | None,
) -> tuple[str, str]:
    explicit_runner, explicit_contract = validate_explicit_commit_provenance(
        execution_isolated_validation=execution_isolated_validation,
        runner_commit=runner_commit,
        benchmark_contract_commit_value=benchmark_contract_commit_value,
    )
    resolved_runner = explicit_runner or git_commitish(repo_root, "rev-parse", "HEAD")
    resolved_contract = explicit_contract or benchmark_contract_commit(repo_root, benchmark_contract_tag)
    if execution_isolated_validation and resolved_runner == "UNKNOWN":
        raise ValueError("execution_isolated_validation_requires_known_runner_commit")
    if execution_isolated_validation and resolved_contract == "UNKNOWN":
        raise ValueError("execution_isolated_validation_requires_known_benchmark_contract_commit")
    return resolved_runner, resolved_contract


def load_freeze_policy_hash(freeze_manifest: Path) -> str | None:
    try:
        payload = json.loads(freeze_manifest.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    value = payload.get("policy_sha256")
    return value if isinstance(value, str) else None


def extract_json_object(text: str) -> str:
    """Extract the first JSON object if a provider wraps the result in prose."""

    stripped = text.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        return stripped
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return stripped
    return stripped[start : end + 1]


def parse_model_result(*, task: dict[str, Any], text: str) -> tuple[dict[str, Any] | None, str, list[str]]:
    parsed, errors = safe_parse_result(extract_json_object(text))
    if parsed is None:
        return None, "safe_parse_reject", errors
    schema_errors = validate_result(parsed, task)
    if schema_errors:
        return None, "safe_schema_reject", schema_errors
    return parsed, "valid_result", []


def validate_runtime_evidence(*, task: dict[str, Any], evidence_mode: str, evidence: dict[str, Any] | None) -> None:
    """Validate evidence-mode payloads before persistence."""

    if evidence_mode == "output_only":
        return
    if not isinstance(evidence, dict):
        raise ValueError(f"missing_runtime_evidence:{evidence_mode}:{task['task_id']}")
    if evidence_mode == "full_category_evidence":
        if evidence.get("kind") != "full_category_evidence":
            raise ValueError(f"invalid_full_category_evidence_kind:{task['task_id']}")
        if evidence.get("score_type") != "logprob":
            raise ValueError(f"full_category_evidence_requires_logprob:{task['task_id']}")
        if evidence.get("single_next_token_logit_used") is not False:
            raise ValueError(f"full_category_evidence_must_not_use_single_next_token_logit:{task['task_id']}")
        rows = evidence.get("category_scores")
        if not isinstance(rows, list):
            raise ValueError(f"full_category_evidence_missing_category_scores:{task['task_id']}")
        observed = {row.get("action") for row in rows if isinstance(row, dict)}
        expected = set(task["allowed_actions"])
        if observed != expected:
            raise ValueError(f"full_category_evidence_action_set_mismatch:{task['task_id']}")
        for row in rows:
            if not isinstance(row, dict) or row.get("score_type") != "logprob" or not isinstance(row.get("score"), int | float):
                raise ValueError(f"full_category_evidence_invalid_score_row:{task['task_id']}")
        return
    if evidence_mode == "token_top_k":
        if evidence.get("kind") != "token_top_k":
            raise ValueError(f"invalid_token_top_k_evidence_kind:{task['task_id']}")
        rows = evidence.get("tokens")
        if not isinstance(rows, list):
            raise ValueError(f"token_top_k_missing_tokens:{task['task_id']}")
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError(f"token_top_k_invalid_token_row:{task['task_id']}")
            if row.get("renormalized_visible_top_k") is not False:
                raise ValueError(f"token_top_k_must_not_renormalize_visible_set:{task['task_id']}")
            if not isinstance(row.get("missing_tail_mass"), int | float):
                raise ValueError(f"token_top_k_missing_tail_mass:{task['task_id']}")
            top_k = row.get("top_k")
            if not isinstance(top_k, list):
                raise ValueError(f"token_top_k_missing_top_k:{task['task_id']}")
            for token in top_k:
                if not isinstance(token, dict) or not isinstance(token.get("probability"), int | float):
                    raise ValueError(f"token_top_k_invalid_probability:{task['task_id']}")
        return
    raise ValueError(f"unsupported_evidence_mode:{evidence_mode}")


def write_raw_response(path: Path, payload: dict[str, Any]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return sha256_file(path)


def prompt_token_count_for_runner(runner: TaskRunner, prompt: str) -> int | None:
    counter = getattr(runner, "prompt_token_count", None)
    if not callable(counter):
        return None
    try:
        value = counter(prompt)
    except (AttributeError, KeyError, RuntimeError, TypeError, ValueError):
        return None
    return int(value) if isinstance(value, int | float) and value >= 0 else None


def runtime_metadata_for_runner(runner: TaskRunner) -> dict[str, Any]:
    metadata = getattr(runner, "runtime_metadata", None)
    return metadata if isinstance(metadata, dict) else {}


def generated_token_count_from_response(response: RuntimeResponse) -> int | None:
    if response.generated_token_count is not None:
        return response.generated_token_count
    for source in (response.raw_response, response.usage or {}):
        for key in (
            "_boundarybench_generated_token_count",
            "generated_token_count",
            "output_tokens",
            "completion_tokens",
            "output_token_count",
        ):
            value = source.get(key) if isinstance(source, dict) else None
            if isinstance(value, int) and value >= 0:
                return value
    return None


def _format_optional_int(value: int | None) -> str:
    return str(value) if value is not None else "NOT_AVAILABLE"


def _format_optional_str(value: Any) -> str:
    return str(value) if value is not None else "NOT_AVAILABLE"


def print_smoke_generation_start(
    *,
    stream: TextIO,
    index: int,
    total: int,
    task_id: str,
    prompt: str,
    tokenizer_input_tokens: int | None,
    runtime_metadata: dict[str, Any],
) -> None:
    print(
        f"[smoke {index}/{total}] task_id={task_id} generation_start "
        f"prompt_chars={len(prompt)} tokenizer_input_tokens={_format_optional_int(tokenizer_input_tokens)} "
        f"execution_device={_format_optional_str(runtime_metadata.get('execution_device'))} "
        f"execution_dtype={_format_optional_str(runtime_metadata.get('execution_dtype'))}",
        file=stream,
        flush=True,
    )


def print_smoke_generation_complete(
    *,
    stream: TextIO,
    index: int,
    total: int,
    task_id: str,
    latency_seconds: float,
    generated_tokens: int | None,
) -> None:
    suffix = f" generated_tokens={generated_tokens}" if generated_tokens is not None else ""
    print(
        f"[smoke {index}/{total}] task_id={task_id} generation_complete "
        f"latency_seconds={latency_seconds:.3f}{suffix}",
        file=stream,
        flush=True,
    )


def _http_json(
    *,
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any],
    timeout_seconds: float,
) -> tuple[dict[str, Any], dict[str, str], float]:
    body = json.dumps(payload, sort_keys=True).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={**headers, "Content-Type": "application/json"},
        method="POST",
    )
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            response_body = response.read().decode("utf-8")
            elapsed_ms = (time.perf_counter() - start) * 1000
            decoded = json.loads(response_body)
            return decoded, {key.lower(): value for key, value in response.headers.items()}, elapsed_ms
    except urllib.error.HTTPError as exc:
        response_body = exc.read().decode("utf-8", errors="replace")
        elapsed_ms = (time.perf_counter() - start) * 1000
        try:
            decoded = json.loads(response_body)
        except json.JSONDecodeError:
            decoded = {"error": response_body}
        decoded.setdefault("http_status", exc.code)
        return decoded, {key.lower(): value for key, value in exc.headers.items()}, elapsed_ms


def _extract_openai_text(payload: dict[str, Any]) -> str:
    if isinstance(payload.get("output_text"), str):
        return payload["output_text"]
    chunks: list[str] = []
    for output in payload.get("output", []) if isinstance(payload.get("output"), list) else []:
        if not isinstance(output, dict):
            continue
        for content in output.get("content", []) if isinstance(output.get("content"), list) else []:
            if isinstance(content, dict) and isinstance(content.get("text"), str):
                chunks.append(content["text"])
    return "\n".join(chunks)


def _extract_anthropic_text(payload: dict[str, Any]) -> str:
    chunks: list[str] = []
    for content in payload.get("content", []) if isinstance(payload.get("content"), list) else []:
        if isinstance(content, dict) and content.get("type") == "text" and isinstance(content.get("text"), str):
            chunks.append(content["text"])
    return "\n".join(chunks)


class OpenAIResponsesRunner:
    """OpenAI Responses API runner without tools/retrieval/browsing."""

    def __init__(self, *, model_id: str, api_key: str, base_url: str | None = None) -> None:
        self.model_id = model_id
        self.api_key = api_key
        self.base_url = (base_url or "https://api.openai.com/v1/responses").rstrip("/")

    def execute(self, *, task: dict[str, Any], prompt: str, config: GenerationConfig) -> RuntimeResponse:
        payload: dict[str, Any] = {
            "model": self.model_id,
            "input": prompt,
            "temperature": config.temperature,
            "max_output_tokens": config.max_output_tokens,
        }
        decoded, headers, latency_ms = _http_json(
            url=self.base_url,
            headers={"Authorization": f"Bearer {self.api_key}"},
            payload=payload,
            timeout_seconds=config.timeout_seconds,
        )
        decoded["_boundarybench_latency_ms"] = latency_ms
        return RuntimeResponse(
            text=_extract_openai_text(decoded),
            raw_response=decoded,
            provider_request_id=headers.get("x-request-id") or decoded.get("id"),
            usage=decoded.get("usage") if isinstance(decoded.get("usage"), dict) else None,
            model_revision_or_digest=decoded.get("model") if isinstance(decoded.get("model"), str) else None,
            runtime_metadata={
                "execution_device": None,
                "execution_dtype": None,
                "torch_version": None,
                "transformers_version": None,
                "accelerator_available": {},
            },
        )


class AnthropicMessagesRunner:
    """Anthropic Messages API runner without tools/retrieval/browsing."""

    def __init__(self, *, model_id: str, api_key: str, base_url: str | None = None) -> None:
        self.model_id = model_id
        self.api_key = api_key
        self.base_url = (base_url or "https://api.anthropic.com/v1/messages").rstrip("/")

    def execute(self, *, task: dict[str, Any], prompt: str, config: GenerationConfig) -> RuntimeResponse:
        payload: dict[str, Any] = {
            "model": self.model_id,
            "max_tokens": config.max_output_tokens,
            "temperature": config.temperature,
            "messages": [{"role": "user", "content": prompt}],
        }
        decoded, headers, latency_ms = _http_json(
            url=self.base_url,
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": os.environ.get("BOUNDARYBENCH_ANTHROPIC_VERSION", "2023-06-01"),
            },
            payload=payload,
            timeout_seconds=config.timeout_seconds,
        )
        decoded["_boundarybench_latency_ms"] = latency_ms
        return RuntimeResponse(
            text=_extract_anthropic_text(decoded),
            raw_response=decoded,
            provider_request_id=headers.get("request-id") or decoded.get("id"),
            usage=decoded.get("usage") if isinstance(decoded.get("usage"), dict) else None,
            model_revision_or_digest=decoded.get("model") if isinstance(decoded.get("model"), str) else None,
            runtime_metadata={
                "execution_device": None,
                "execution_dtype": None,
                "torch_version": None,
                "transformers_version": None,
                "accelerator_available": {},
            },
        )


class MockResponseRunner:
    """Mock-only runner used by tests and offline command dry-runs."""

    def __init__(self, response_dir: Path) -> None:
        self.response_dir = response_dir

    def execute(self, *, task: dict[str, Any], prompt: str, config: GenerationConfig) -> RuntimeResponse:
        path = self.response_dir / f"{task['task_id']}.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        raw_response = payload.get("raw_response")
        if not isinstance(raw_response, dict):
            raw_response = {"mock_response": payload}
        return RuntimeResponse(
            text=str(payload.get("text", "")),
            raw_response=raw_response,
            provider_request_id=payload.get("provider_request_id"),
            usage=payload.get("usage") if isinstance(payload.get("usage"), dict) else None,
            provider_reported_cost_usd=payload.get("provider_reported_cost_usd"),
            model_revision_or_digest=payload.get("model_revision_or_digest"),
            evidence=payload.get("evidence") if isinstance(payload.get("evidence"), dict) else None,
            runtime_metadata=payload.get("runtime_metadata") if isinstance(payload.get("runtime_metadata"), dict) else None,
        )


class PythonBackendOpenWeightRunner:
    """Open-weight runner backed by a user-supplied local Python module.

    The backend spec is ``module:function``. The callable receives keyword
    arguments ``task``, ``prompt``, ``config``, and ``evidence_mode`` and returns
    a dictionary compatible with ``RuntimeResponse`` fields.
    """

    def __init__(self, *, backend_spec: str, evidence_mode: str) -> None:
        module_name, _, function_name = backend_spec.partition(":")
        if not module_name or not function_name:
            raise ValueError("open_weight_backend_must_be_module_colon_function")
        module = importlib.import_module(module_name)
        self.callable = getattr(module, function_name)
        self.evidence_mode = evidence_mode

    def execute(self, *, task: dict[str, Any], prompt: str, config: GenerationConfig) -> RuntimeResponse:
        payload = self.callable(task=task, prompt=prompt, config=config.as_dict(), evidence_mode=self.evidence_mode)
        if not isinstance(payload, dict):
            raise ValueError("open_weight_backend_returned_non_object")
        return RuntimeResponse(
            text=str(payload.get("text", "")),
            raw_response=payload.get("raw_response") if isinstance(payload.get("raw_response"), dict) else payload,
            provider_request_id=payload.get("provider_request_id"),
            usage=payload.get("usage") if isinstance(payload.get("usage"), dict) else None,
            provider_reported_cost_usd=payload.get("provider_reported_cost_usd"),
            model_revision_or_digest=payload.get("model_revision_or_digest"),
            evidence=payload.get("evidence") if isinstance(payload.get("evidence"), dict) else None,
            runtime_metadata=payload.get("runtime_metadata") if isinstance(payload.get("runtime_metadata"), dict) else None,
        )


def dtype_name(dtype: Any) -> str | None:
    """Return a stable dtype name for provenance."""

    if dtype is None:
        return None
    text = str(dtype)
    return text.removeprefix("torch.")


def _bool_call(value: Any) -> bool:
    if callable(value):
        try:
            return bool(value())
        except (RuntimeError, AttributeError, TypeError):
            return False
    return bool(value)


def select_transformers_runtime(torch_module: Any, *, transformers_version: str | None) -> dict[str, Any]:
    """Select deterministic device/dtype/load settings for Transformers inference."""

    cuda_available = _bool_call(getattr(getattr(torch_module, "cuda", None), "is_available", None))
    mps_backend = getattr(getattr(torch_module, "backends", None), "mps", None)
    mps_available = _bool_call(getattr(mps_backend, "is_available", None))
    if cuda_available:
        device = "cuda"
        bf16_supported = _bool_call(getattr(getattr(torch_module, "cuda", None), "is_bf16_supported", None))
        dtype = getattr(torch_module, "bfloat16", None) if bf16_supported else getattr(torch_module, "float16", None)
    elif mps_available:
        device = "mps"
        dtype = getattr(torch_module, "float16", None)
    else:
        device = "cpu"
        dtype = getattr(torch_module, "bfloat16", None) or getattr(torch_module, "float16", None)
    load_kwargs: dict[str, Any] = {"low_cpu_mem_usage": True}
    if dtype is not None:
        load_kwargs["dtype"] = dtype
    return {
        "execution_device": device,
        "dtype": dtype,
        "execution_dtype": dtype_name(dtype),
        "torch_version": getattr(torch_module, "__version__", None),
        "transformers_version": transformers_version,
        "accelerator_available": {
            "cuda": cuda_available,
            "mps": mps_available,
        },
        "model_load_kwargs": load_kwargs,
    }


def load_transformers_model(model_cls: Any, model_dir: str, load_kwargs: dict[str, Any]) -> Any:
    """Load a model with dtype, falling back to torch_dtype for older Transformers."""

    try:
        return model_cls.from_pretrained(model_dir, **load_kwargs)
    except TypeError:
        if "dtype" not in load_kwargs:
            raise
        fallback_kwargs = dict(load_kwargs)
        fallback_kwargs["torch_dtype"] = fallback_kwargs.pop("dtype")
        return model_cls.from_pretrained(model_dir, **fallback_kwargs)


def move_tensors_to_device(value: Any, device: str) -> Any:
    """Recursively move tokenizer/model tensors to the selected execution device."""

    if isinstance(value, dict):
        return {key: move_tensors_to_device(child, device) for key, child in value.items()}
    if isinstance(value, list):
        return [move_tensors_to_device(child, device) for child in value]
    if isinstance(value, tuple):
        return tuple(move_tensors_to_device(child, device) for child in value)
    if hasattr(value, "to") and callable(value.to):
        return value.to(device)
    return value


class TransformersOpenWeightRunner:
    """Optional Hugging Face Transformers causal-LM runner.

    This is imported lazily so the core package remains dependency-free. For
    ``full_category_evidence`` it computes conditional sequence log-likelihood
    for every complete allowed action label.
    """

    def __init__(
        self,
        *,
        model_dir: str,
        evidence_mode: str,
        token_top_k: int,
        torch_module: Any | None = None,
        tokenizer_cls: Any | None = None,
        model_cls: Any | None = None,
        transformers_version: str | None = None,
    ) -> None:
        if torch_module is None or tokenizer_cls is None or model_cls is None:
            try:
                import torch  # type: ignore
                import transformers  # type: ignore
                from transformers import AutoModelForCausalLM, AutoTokenizer  # type: ignore
            except ImportError as exc:  # pragma: no cover - exercised only when optional deps missing
                raise RuntimeError("transformers_and_torch_required_for_open_weight_transformers_runner") from exc
            torch_module = torch
            tokenizer_cls = AutoTokenizer
            model_cls = AutoModelForCausalLM
            transformers_version = getattr(transformers, "__version__", None)
        self.torch = torch_module
        runtime = select_transformers_runtime(self.torch, transformers_version=transformers_version)
        self.execution_device = runtime["execution_device"]
        self.execution_dtype = runtime["dtype"]
        self.execution_dtype_name = runtime["execution_dtype"]
        self.runtime_metadata = {
            "execution_device": self.execution_device,
            "execution_dtype": self.execution_dtype_name,
            "torch_version": runtime["torch_version"],
            "transformers_version": runtime["transformers_version"],
            "accelerator_available": runtime["accelerator_available"],
        }
        self.tokenizer = tokenizer_cls.from_pretrained(model_dir)
        self.model = load_transformers_model(model_cls, model_dir, runtime["model_load_kwargs"])
        self.model = self.model.to(self.execution_device)
        self.model.eval()
        self.model_dir = model_dir
        self.evidence_mode = evidence_mode
        self.token_top_k = token_top_k

    def prompt_token_count(self, prompt: str) -> int:
        encoded = self.tokenizer(prompt, return_tensors="pt")
        input_ids = encoded["input_ids"] if isinstance(encoded, dict) else encoded.input_ids
        return int(input_ids.shape[-1])

    def _generate(self, prompt: str, config: GenerationConfig) -> tuple[str, dict[str, Any], int]:
        encoded = move_tensors_to_device(self.tokenizer(prompt, return_tensors="pt"), self.execution_device)
        kwargs: dict[str, Any] = {
            "max_new_tokens": config.max_output_tokens,
            "do_sample": config.temperature > 0,
            "temperature": config.temperature if config.temperature > 0 else None,
            "return_dict_in_generate": self.evidence_mode == "token_top_k",
            "output_scores": self.evidence_mode == "token_top_k",
        }
        kwargs = {key: value for key, value in kwargs.items() if value is not None}
        if config.seed is not None:
            self.torch.manual_seed(config.seed)
        with self.torch.no_grad():
            generated = self.model.generate(**encoded, **kwargs)
        if self.evidence_mode == "token_top_k":
            sequences = generated.sequences
            scores = generated.scores
        else:
            sequences = generated
            scores = []
        prompt_len = encoded["input_ids"].shape[-1]
        new_tokens = sequences[0][prompt_len:]
        generated_token_count = int(new_tokens.shape[-1])
        text = self.tokenizer.decode(new_tokens, skip_special_tokens=True)
        evidence: dict[str, Any] = {}
        if self.evidence_mode == "token_top_k":
            token_rows = []
            for token_id, logits in zip(new_tokens.tolist(), scores, strict=False):
                probs = self.torch.softmax(logits[0], dim=-1)
                top_probs, top_ids = self.torch.topk(probs, k=min(self.token_top_k, probs.shape[-1]))
                visible = [
                    {
                        "token_id": int(idx),
                        "token": self.tokenizer.decode([int(idx)]),
                        "probability": float(prob),
                    }
                    for idx, prob in zip(top_ids.tolist(), top_probs.tolist(), strict=True)
                ]
                token_rows.append(
                    {
                        "sampled_token_id": int(token_id),
                        "sampled_token": self.tokenizer.decode([int(token_id)]),
                        "top_k": visible,
                        "missing_tail_mass": float(max(0.0, 1.0 - sum(row["probability"] for row in visible))),
                        "renormalized_visible_top_k": False,
                    }
                )
            evidence = {"kind": "token_top_k", "tokens": token_rows}
        return text, evidence, generated_token_count

    def _sequence_logprob(self, prompt: str, label: str) -> float:
        context = prompt + "\nAction label:"
        context_ids = move_tensors_to_device(self.tokenizer(context, return_tensors="pt")["input_ids"], self.execution_device)
        label_ids = move_tensors_to_device(
            self.tokenizer(label, add_special_tokens=False, return_tensors="pt")["input_ids"],
            self.execution_device,
        )
        input_ids = self.torch.cat([context_ids, label_ids], dim=-1)
        with self.torch.no_grad():
            logits = self.model(input_ids).logits
        log_probs = self.torch.log_softmax(logits, dim=-1)
        start = context_ids.shape[-1]
        total = 0.0
        for offset, token_id in enumerate(label_ids[0].tolist()):
            position = start + offset - 1
            total += float(log_probs[0, position, token_id])
        return total

    def execute(self, *, task: dict[str, Any], prompt: str, config: GenerationConfig) -> RuntimeResponse:
        text, evidence, generated_token_count = self._generate(prompt, config)
        if self.evidence_mode == "full_category_evidence":
            scores = [
                {
                    "action": action,
                    "score": self._sequence_logprob(prompt, action),
                    "score_type": "logprob",
                    "complete_action_label": action,
                }
                for action in task["allowed_actions"]
            ]
            evidence = {
                "kind": "full_category_evidence",
                "score_type": "logprob",
                "category_scores": scores,
                "bounded_action_set": list(task["allowed_actions"]),
                "single_next_token_logit_used": False,
            }
        return RuntimeResponse(
            text=text,
            raw_response={
                "runtime": "transformers",
                "evidence": evidence,
                "model_dir": self.model_dir,
                "runtime_metadata": self.runtime_metadata,
            },
            model_revision_or_digest=os.environ.get("BOUNDARYBENCH_OPEN_WEIGHT_MODEL_DIGEST"),
            evidence=evidence,
            runtime_metadata=self.runtime_metadata,
            generated_token_count=generated_token_count,
        )


def runner_for_family(
    *,
    family: str,
    evidence_mode: str,
    config: GenerationConfig,
    mock_response_dir: Path | None = None,
) -> tuple[TaskRunner, str, str, str | None]:
    """Create a runner and return ``(runner, provider, model_id, digest)``."""

    if mock_response_dir is not None:
        return MockResponseRunner(mock_response_dir), family, os.environ.get(f"BOUNDARYBENCH_{family.upper()}_MODEL_ID", "MOCK_MODEL"), "mock"

    if family == "closed_provider_a":
        if evidence_mode != "output_only":
            raise ValueError(f"unsupported_evidence_mode_for_closed_provider_a:{evidence_mode}")
        model_id = os.environ["BOUNDARYBENCH_CLOSED_PROVIDER_A_MODEL_ID"]
        runner = OpenAIResponsesRunner(
            model_id=model_id,
            api_key=os.environ["BOUNDARYBENCH_CLOSED_PROVIDER_A_API_KEY"],
            base_url=os.environ.get("BOUNDARYBENCH_OPENAI_RESPONSES_URL"),
        )
        return runner, "openai_responses_api", model_id, None
    if family == "closed_provider_b":
        if evidence_mode != "output_only":
            raise ValueError(f"unsupported_evidence_mode_for_closed_provider_b:{evidence_mode}")
        model_id = os.environ["BOUNDARYBENCH_CLOSED_PROVIDER_B_MODEL_ID"]
        runner = AnthropicMessagesRunner(
            model_id=model_id,
            api_key=os.environ["BOUNDARYBENCH_CLOSED_PROVIDER_B_API_KEY"],
            base_url=os.environ.get("BOUNDARYBENCH_ANTHROPIC_MESSAGES_URL"),
        )
        return runner, "anthropic_messages_api", model_id, None
    if family in OPEN_WEIGHT_FAMILIES:
        if evidence_mode not in ALLOWED_EVIDENCE_MODES:
            raise ValueError(f"unsupported_open_weight_evidence_mode:{evidence_mode}")
        prefix = "BOUNDARYBENCH_OPEN_WEIGHT_A" if family == "open_weight_family_a" else "BOUNDARYBENCH_OPEN_WEIGHT_B"
        model_id = os.environ[f"{prefix}_MODEL_ID"]
        digest = os.environ.get(f"{prefix}_MODEL_DIGEST")
        backend = os.environ.get(f"{prefix}_BACKEND")
        if backend:
            return PythonBackendOpenWeightRunner(backend_spec=backend, evidence_mode=evidence_mode), family, model_id, digest
        model_dir = os.environ[f"{prefix}_MODEL_DIR"]
        return TransformersOpenWeightRunner(model_dir=model_dir, evidence_mode=evidence_mode, token_top_k=config.token_top_k), family, model_id, digest
    raise ValueError(f"unknown_family:{family}")


def _required_env_for_family(family: str, mock_response_dir: Path | None) -> tuple[str, ...]:
    if mock_response_dir is not None:
        return ()
    if family == "closed_provider_a":
        return ("BOUNDARYBENCH_CLOSED_PROVIDER_A_MODEL_ID", "BOUNDARYBENCH_CLOSED_PROVIDER_A_API_KEY")
    if family == "closed_provider_b":
        return ("BOUNDARYBENCH_CLOSED_PROVIDER_B_MODEL_ID", "BOUNDARYBENCH_CLOSED_PROVIDER_B_API_KEY")
    if family == "open_weight_family_a":
        if os.environ.get("BOUNDARYBENCH_OPEN_WEIGHT_A_BACKEND"):
            return ("BOUNDARYBENCH_OPEN_WEIGHT_A_MODEL_ID", "BOUNDARYBENCH_OPEN_WEIGHT_A_BACKEND")
        return ("BOUNDARYBENCH_OPEN_WEIGHT_A_MODEL_ID", "BOUNDARYBENCH_OPEN_WEIGHT_A_MODEL_DIR")
    if family == "open_weight_family_b":
        if os.environ.get("BOUNDARYBENCH_OPEN_WEIGHT_B_BACKEND"):
            return ("BOUNDARYBENCH_OPEN_WEIGHT_B_MODEL_ID", "BOUNDARYBENCH_OPEN_WEIGHT_B_BACKEND")
        return ("BOUNDARYBENCH_OPEN_WEIGHT_B_MODEL_ID", "BOUNDARYBENCH_OPEN_WEIGHT_B_MODEL_DIR")
    return ()


def missing_requirements(*, family: str, evidence_mode: str, mock_response_dir: Path | None = None) -> list[str]:
    missing = [name for name in _required_env_for_family(family, mock_response_dir) if not os.environ.get(name)]
    if family in CLOSED_PROVIDER_FAMILIES and evidence_mode != "output_only":
        missing.append(f"unsupported_evidence_mode:{evidence_mode}")
    if family in OPEN_WEIGHT_FAMILIES and evidence_mode not in ALLOWED_EVIDENCE_MODES:
        missing.append(f"unsupported_evidence_mode:{evidence_mode}")
    return missing


def empirical_result_record(
    *,
    task: dict[str, Any],
    run_id: str,
    family: str,
    provider: str,
    model_id: str,
    model_revision_or_digest: str | None,
    evidence_mode: str,
    prompt_hash: str,
    input_manifest_hash: str,
    freeze_manifest_hash: str,
    freeze_validation_mode: str,
    trusted_artifacts_present: bool | None,
    policy_hash: str | None,
    benchmark_contract_tag: str,
    benchmark_contract_commit_value: str,
    runner_commit: str,
    generation_config: GenerationConfig,
    access_time_utc: str,
    latency_ms: float,
    raw_response_path: Path,
    raw_output_hash: str,
    provider_request_id: str | None,
    usage: dict[str, Any] | None,
    cost_usd: float | None,
    parse_status: str,
    parse_errors: list[str],
    result_included: bool,
    runtime_metadata: dict[str, Any] | None,
    unsupported_reason: str | None = None,
) -> dict[str, Any]:
    runtime_metadata = runtime_metadata or {}
    return {
        "schema_version": EMPIRICAL_RESULT_SCHEMA_VERSION,
        "task_id": task["task_id"],
        "run_id": run_id,
        "run_status": "COMPLETED",
        "model": {
            "exact_model_id": model_id,
            "provider": provider,
            "artifact_version_digest": model_revision_or_digest,
            "access_date": access_time_utc,
            "family": family,
        },
        "prompt_hash": prompt_hash,
        "policy_hash": policy_hash,
        "decoding_configuration": generation_config.as_dict(),
        "seed": generation_config.seed,
        "evidence_mode": evidence_mode,
        "raw_output_path": raw_response_path.as_posix(),
        "raw_output_hash": raw_output_hash,
        "latency_ms": latency_ms,
        "token_usage": usage,
        "reported_provider_cost_usd": cost_usd,
        "provider_request_id": provider_request_id,
        "parse_status": parse_status,
        "parse_errors": parse_errors,
        "result_included": result_included,
        "execution_device": runtime_metadata.get("execution_device"),
        "execution_dtype": runtime_metadata.get("execution_dtype"),
        "torch_version": runtime_metadata.get("torch_version"),
        "transformers_version": runtime_metadata.get("transformers_version"),
        "accelerator_available": runtime_metadata.get("accelerator_available", {}),
        "runner_commit": runner_commit,
        "code_commit": runner_commit,
        "benchmark_contract": {
            "tag": benchmark_contract_tag,
            "commit": benchmark_contract_commit_value,
        },
        "input_manifest_hash": input_manifest_hash,
        "data_manifest_hash": input_manifest_hash,
        "freeze_manifest_hash": freeze_manifest_hash,
        "freeze_manifest_sha256": freeze_manifest_hash,
        "freeze_validation_mode": freeze_validation_mode,
        "trusted_artifacts_present": trusted_artifacts_present,
        "unsupported_reason": unsupported_reason,
    }


def run_model_family(
    *,
    repo_root: Path,
    family: str,
    evidence_mode: str,
    model_inputs: Path,
    model_input_manifest: Path,
    freeze_manifest: Path,
    out_dir: Path,
    run_id: str,
    generation_config: GenerationConfig,
    benchmark_contract_tag: str = "benchmark-contract-v0.1",
    mock_response_dir: Path | None = None,
    allow_public_dev_smoke: bool = False,
    smoke_task_limit: int | None = None,
    execution_isolated_validation: bool = False,
    expected_freeze_manifest_sha256: str | None = None,
    runner_commit: str | None = None,
    benchmark_contract_commit_value: str | None = None,
    progress_stream: TextIO | None = None,
) -> dict[str, Any]:
    resolved_runner_commit, resolved_contract_commit = resolve_commit_provenance(
        repo_root=repo_root,
        benchmark_contract_tag=benchmark_contract_tag,
        execution_isolated_validation=execution_isolated_validation,
        runner_commit=runner_commit,
        benchmark_contract_commit_value=benchmark_contract_commit_value,
    )
    validate_model_input_paths(
        model_inputs=model_inputs,
        model_input_manifest=model_input_manifest,
        repo_root=repo_root,
        allow_public_dev_smoke=allow_public_dev_smoke,
    )
    validate_smoke_task_limit_usage(
        repo_root=repo_root,
        model_inputs=model_inputs,
        model_input_manifest=model_input_manifest,
        allow_public_dev_smoke=allow_public_dev_smoke,
        smoke_task_limit=smoke_task_limit,
    )
    split_name = canonical_model_input_split(
        repo_root=repo_root,
        model_inputs=model_inputs,
        model_input_manifest=model_input_manifest,
    )
    if split_name is None:
        raise ValueError("model_execution_requires_canonical_model_inputs")
    all_tasks = read_jsonl(model_inputs)
    freeze_validation_mode = (
        FREEZE_VALIDATION_EXECUTION_ISOLATED if execution_isolated_validation else FREEZE_VALIDATION_FULL
    )
    validate_model_input_package(
        repo_root=repo_root,
        model_inputs=model_inputs,
        model_input_manifest=model_input_manifest,
        freeze_manifest=freeze_manifest,
        split_name=split_name,
        tasks=all_tasks,
        freeze_validation_mode=freeze_validation_mode,
        expected_freeze_manifest_sha256=expected_freeze_manifest_sha256,
    )
    validate_answer_key_free_tasks(all_tasks)
    validate_model_input_task_schemas(all_tasks)
    tasks = all_tasks[:smoke_task_limit] if smoke_task_limit is not None else all_tasks
    missing = missing_requirements(family=family, evidence_mode=evidence_mode, mock_response_dir=mock_response_dir)
    if missing:
        raise RuntimeError("model_execution_prerequisites_missing:" + ",".join(missing))

    runner, provider, model_id, digest = runner_for_family(
        family=family,
        evidence_mode=evidence_mode,
        config=generation_config,
        mock_response_dir=mock_response_dir,
    )
    run_root = out_dir / run_id
    if run_root.exists():
        raise FileExistsError(f"run_id_already_exists:{run_root}")
    raw_dir = run_root / "raw_responses"
    results_path = run_root / "results.jsonl"
    provenance_path = run_root / "empirical_results.jsonl"
    manifest_path = run_root / "run_manifest.json"
    input_manifest_hash = sha256_file(model_input_manifest)
    freeze_hash = sha256_file(freeze_manifest)
    policy_hash = load_freeze_policy_hash(freeze_manifest)
    results: list[dict[str, Any]] = []
    provenance: list[dict[str, Any]] = []
    trusted_artifacts_present = False if execution_isolated_validation else None
    smoke_progress_stream = progress_stream if allow_public_dev_smoke and split_name == "public_dev" else None

    for task_index, task in enumerate(tasks, start=1):
        prompt = build_prompt(task)
        if smoke_progress_stream is not None:
            print_smoke_generation_start(
                stream=smoke_progress_stream,
                index=task_index,
                total=len(tasks),
                task_id=task["task_id"],
                prompt=prompt,
                tokenizer_input_tokens=prompt_token_count_for_runner(runner, prompt),
                runtime_metadata=runtime_metadata_for_runner(runner),
            )
        access_time = utc_now()
        started = time.perf_counter()
        response = runner.execute(task=task, prompt=prompt, config=generation_config)
        elapsed_seconds = time.perf_counter() - started
        if smoke_progress_stream is not None:
            print_smoke_generation_complete(
                stream=smoke_progress_stream,
                index=task_index,
                total=len(tasks),
                task_id=task["task_id"],
                latency_seconds=elapsed_seconds,
                generated_tokens=generated_token_count_from_response(response),
            )
        validate_runtime_evidence(task=task, evidence_mode=evidence_mode, evidence=response.evidence)
        latency_ms = float(response.raw_response.get("_boundarybench_latency_ms", elapsed_seconds * 1000))
        raw_payload = {
            "schema_version": "boundarybench.raw_model_response.v1",
            "task_id": task["task_id"],
            "run_id": run_id,
            "provider": provider,
            "model_id": model_id,
            "evidence_mode": evidence_mode,
            "access_time_utc": access_time,
            "raw_response": response.raw_response,
            "normalized_text": response.text,
            "evidence": response.evidence,
            "runtime_metadata": response.runtime_metadata,
        }
        raw_path = raw_dir / f"{task['task_id']}.json"
        raw_hash = write_raw_response(raw_path, raw_payload)
        parsed, parse_status, parse_errors = parse_model_result(task=task, text=response.text)
        result_included = parsed is not None
        if parsed is not None:
            results.append(parsed)
        provenance.append(
            empirical_result_record(
                task=task,
                run_id=run_id,
                family=family,
                provider=provider,
                model_id=model_id,
                model_revision_or_digest=response.model_revision_or_digest or digest,
                evidence_mode=evidence_mode,
                prompt_hash=sha256_text(prompt),
                input_manifest_hash=input_manifest_hash,
                freeze_manifest_hash=freeze_hash,
                freeze_validation_mode=freeze_validation_mode,
                trusted_artifacts_present=trusted_artifacts_present,
                policy_hash=policy_hash,
                benchmark_contract_tag=benchmark_contract_tag,
                benchmark_contract_commit_value=resolved_contract_commit,
                runner_commit=resolved_runner_commit,
                generation_config=generation_config,
                access_time_utc=access_time,
                latency_ms=latency_ms,
                raw_response_path=raw_path,
                raw_output_hash=raw_hash,
                provider_request_id=response.provider_request_id,
                usage=response.usage,
                cost_usd=response.provider_reported_cost_usd,
                parse_status=parse_status,
                parse_errors=parse_errors,
                result_included=result_included,
                runtime_metadata=response.runtime_metadata,
            )
        )

    write_jsonl(results_path, results)
    write_jsonl(provenance_path, provenance)
    manifest = {
        "schema_version": MODEL_RUN_MANIFEST_SCHEMA_VERSION,
        "run_id": run_id,
        "family": family,
        "provider": provider,
        "exact_model_id": model_id,
        "evidence_mode": evidence_mode,
        "task_count": len(tasks),
        "source_model_input_task_count": len(all_tasks),
        "smoke_task_limit": smoke_task_limit,
        "result_count": len(results),
        "results_path": results_path.as_posix(),
        "results_sha256": sha256_file(results_path),
        "provenance_path": provenance_path.as_posix(),
        "provenance_sha256": sha256_file(provenance_path),
        "raw_responses_dir": raw_dir.as_posix(),
        "model_inputs_path": model_inputs.as_posix(),
        "model_input_manifest_path": model_input_manifest.as_posix(),
        "input_manifest_hash": input_manifest_hash,
        "freeze_manifest_path": freeze_manifest.as_posix(),
        "freeze_manifest_hash": freeze_hash,
        "freeze_manifest_sha256": freeze_hash,
        "freeze_validation_mode": freeze_validation_mode,
        "trusted_artifacts_present": trusted_artifacts_present,
        "benchmark_contract_tag": benchmark_contract_tag,
        "benchmark_contract_commit": resolved_contract_commit,
        "runner_commit": resolved_runner_commit,
        "trusted_verifier_package_present": False,
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest
