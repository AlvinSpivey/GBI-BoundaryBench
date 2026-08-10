"""Prompt construction helpers for task-suite model requests."""

from __future__ import annotations

from typing import Any

from boundarybench.adapters.types import ModelRequest


def build_task_prompt(task: dict[str, Any]) -> str:
    """Build a compact, deterministic prompt for a BoundaryBench task."""

    evidence_ids = [ref["ref_id"] for ref in task["evidence_refs"]]
    return "\n".join(
        [
            "You are solving a GBI BoundaryBench task.",
            "Return only JSON matching boundarybench.result.v1.",
            f"Task ID: {task['task_id']}",
            f"Family: {task['family']}",
            f"Allowed actions: {', '.join(task['allowed_actions'])}",
            f"Prompt: {task['prompt']}",
            f"Input: {task['input']}",
            f"Evidence reference IDs available: {', '.join(evidence_ids)}",
            "Do not invent evidence. Abstain or reject when required evidence is absent or unsafe.",
        ]
    )


def request_from_task(task: dict[str, Any], *, seed: int | None = None) -> ModelRequest:
    """Create a provider-neutral adapter request from a task artifact."""

    return ModelRequest(
        task_id=task["task_id"],
        prompt=build_task_prompt(task),
        allowed_actions=tuple(task["allowed_actions"]),
        seed=seed,
        metadata={
            "split": task["split"],
            "family": task["family"],
            "failure_slices": task["failure_slices"],
            "evidence_ref_ids": [ref["ref_id"] for ref in task["evidence_refs"]],
            "surrogate_features": {"family": task["family"]},
        },
    )

