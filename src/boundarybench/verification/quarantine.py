"""Dependency-aware quarantine logic for PVE outputs."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from boundarybench.verification.types import QuarantineRecord

QUARANTINE_ACTIONS = {"quarantine_slice", "reject"}


def dependency_keys(task: dict[str, Any]) -> tuple[str, ...]:
    keys = {f"task:{task['task_id']}", f"family:{task['family']}"}
    for ref in task["evidence_refs"]:
        source_record_id = ref.get("source_record_id")
        table = ref.get("table")
        row_id = ref.get("row_id")
        if source_record_id:
            keys.add(f"source:{source_record_id}")
        if table and row_id:
            keys.add(f"row:{table}:{row_id}")
        if ref.get("event_id"):
            keys.add(f"event:{ref['event_id']}")
    for failure_slice in task["failure_slices"]:
        keys.add(f"slice:{failure_slice}")
    return tuple(sorted(keys))


def dependency_index(tasks: list[dict[str, Any]]) -> dict[str, tuple[str, ...]]:
    by_key: dict[str, list[str]] = defaultdict(list)
    for task in tasks:
        for key in dependency_keys(task):
            by_key[key].append(task["task_id"])
    return {key: tuple(sorted(values)) for key, values in by_key.items()}


def quarantine_record(
    *,
    task: dict[str, Any],
    result: dict[str, Any] | None,
    passed: bool,
    dependency_lookup: dict[str, tuple[str, ...]],
) -> QuarantineRecord:
    keys = dependency_keys(task)
    closure = sorted({task_id for key in keys for task_id in dependency_lookup.get(key, ())})
    observed_action = result.get("action") if isinstance(result, dict) else None
    should_quarantine = (not passed) or observed_action in QUARANTINE_ACTIONS
    if not should_quarantine:
        return QuarantineRecord(
            quarantined=False,
            local_slices=tuple(task["failure_slices"]),
            dependency_keys=keys,
            closure_task_ids=(),
            reason="not_required",
        )
    reason = "candidate_failed" if not passed else f"policy_action:{observed_action}"
    return QuarantineRecord(
        quarantined=True,
        local_slices=tuple(task["failure_slices"]),
        dependency_keys=keys,
        closure_task_ids=tuple(closure),
        reason=reason,
    )

