"""Provenance capture for model adapter responses."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import platform
import subprocess
import sys
from typing import Any

from boundarybench.adapters.hashing import config_sha256, prompt_sha256
from boundarybench.adapters.types import AdapterConfig, ExecutionStatus, ModelRequest, RetryPolicy

ADAPTER_API_VERSION = "boundarybench.adapters.v1"


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def git_commit(repo_root: Path | None = None) -> str | None:
    """Return the current git commit if available, without mutating the repo."""

    root = repo_root or Path.cwd()
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    commit = completed.stdout.strip()
    return commit or None


def runtime_metadata() -> dict[str, Any]:
    return {
        "python_version": sys.version.split()[0],
        "platform": platform.platform(),
        "implementation": platform.python_implementation(),
    }


def capture_provenance(
    *,
    request: ModelRequest,
    config: AdapterConfig,
    adapter_class: str,
    retry_policy: RetryPolicy,
    attempt_count: int,
    latency_ms: float,
    is_mock: bool,
    execution_status: ExecutionStatus,
    full_category_evidence_observed: bool,
    token_top_k_evidence_observed: bool,
    output_text_observed: bool,
    external_request_id: str | None = None,
    usage: dict[str, Any] | None = None,
    cost_usd: float | None = None,
    data_manifest_sha256: str | None = None,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    """Build a shareable provenance record.

    Credential values are never read or recorded here. Real provider adapters
    should record only non-secret environment variable names or credential
    availability state in ``config.extra``.
    """

    return {
        "schema_version": "boundarybench.model_provenance.v1",
        "adapter_api_version": ADAPTER_API_VERSION,
        "provider": config.provider,
        "model_id": config.model_id,
        "access_mode": config.access_mode,
        "adapter_class": adapter_class,
        "access_time_utc": utc_now_iso(),
        "prompt_sha256": prompt_sha256(request.prompt),
        "request_config_sha256": config_sha256(
            {
                "request": {
                    "task_id": request.task_id,
                    "allowed_actions": list(request.allowed_actions),
                    "seed": request.seed,
                    "temperature": request.temperature,
                    "max_output_tokens": request.max_output_tokens,
                    "metadata": request.metadata,
                },
                "adapter_config": config.as_dict(),
            }
        ),
        "seed": request.seed,
        "code_commit": git_commit(repo_root),
        "data_manifest_sha256": data_manifest_sha256,
        "runtime": runtime_metadata(),
        "retry_policy": retry_policy.as_dict(),
        "attempt_count": attempt_count,
        "latency_ms": round(latency_ms, 3),
        "usage": usage,
        "cost_usd": cost_usd,
        "external_request_id": external_request_id,
        "is_mock": is_mock,
        "execution_status": execution_status,
        "observed_evidence": {
            "full_category": full_category_evidence_observed,
            "token_top_k": token_top_k_evidence_observed,
            "output_text": output_text_observed,
        },
    }

