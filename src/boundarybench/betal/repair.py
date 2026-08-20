"""Format-repair stage: lifting the admissibility floor.

The v0.2 admissibility gate identified the prerequisite: until emissions clear
safe parsing and schema validation, no difficulty measurement is possible and the
substrate's selectivity is unobservable. This module implements the repair.

Every transformation here is **deterministic and declared**. Nothing is
probabilistic, and nothing invents content:

| Transformation | Recovers |
|---|---|
| Strip code fences and surrounding prose, extract the first balanced object | fenced / prose-wrapped payloads |
| Quote bare object keys | JSON-like payloads with unquoted keys |
| Collapse duplicate keys, keeping the first | duplicate-key rejections |
| Insert the constant `schema_version` | missing-version rejections |
| Map a declared action synonym onto the typed action set | unknown-action rejections |
| Drop keys outside the result schema | extra-key rejections |

Two failure classes are deliberately **not** repaired, because repairing them
would require fabricating content the model never produced:

* **Truncated payloads.** A cut-off object has no determinate completion.
* **A non-object `answer`.** There is no way to synthesize the intended answer.

Those are reported as unrecovered and would need a retry against the model, which
this harness does not perform because it executes no model.

The important property to keep in view when reading the results: repair changes
*admissibility*, not *correctness*. A repaired record enters the judgment
substrate and is then graded on its merits, and a wrong action stays wrong. Repair
is what makes selective risk computable; it is not what makes a model right.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Any

from boundarybench.betal.targets import Emission, Target
from boundarybench.tasks.grade import safe_parse_result
from boundarybench.tasks.schemas import RESULT_JSON_SCHEMA, validate_result

REPAIR_VERSION = "gbi-v2-format-repair-v1"

RESULT_SCHEMA_VERSION = "boundarybench.result.v1"
ALLOWED_RESULT_KEYS: frozenset[str] = frozenset(RESULT_JSON_SCHEMA["properties"])

# Declared synonym table. Deliberately small and explicit: a repair layer that
# guessed at action semantics would be making clinical routing decisions.
ACTION_SYNONYMS: dict[str, str] = {
    "approve": "admit",
    "approved": "admit",
    "accept": "admit",
    "accepted": "admit",
    "historical": "admit_historical_only",
    "historical_only": "admit_historical_only",
    "quarantine": "quarantine_slice",
    "isolate": "quarantine_slice",
    "review": "expert_review",
    "escalate": "expert_review",
    "decline": "reject",
    "deny": "reject",
    "refuse": "reject",
    "no_answer": "abstain",
    "unknown": "abstain",
}

_FENCE = re.compile(r"^\s*```[a-zA-Z0-9_-]*\s*|\s*```\s*$")
_BARE_KEY = re.compile(r"([{,]\s*)([A-Za-z_][A-Za-z0-9_]*)(\s*:)")


def _extract_first_object(text: str) -> str | None:
    """Return the first balanced brace-delimited substring, or None."""

    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return None


@dataclass
class RepairOutcome:
    raw_text: str
    repaired_text: str
    applied: tuple[str, ...]
    recovered: bool
    unrecovered_reason: str | None


def repair_emission(raw_text: str, task: dict[str, Any]) -> RepairOutcome:
    """Apply the declared repair transformations to one raw emission."""

    applied: list[str] = []

    # Fast path: already admissible.
    parsed, parse_errors = safe_parse_result(raw_text)
    if parsed is not None and not validate_result(parsed, task):
        return RepairOutcome(raw_text, raw_text, (), True, None)

    text = raw_text
    stripped = _FENCE.sub("", text).strip()
    if stripped != text.strip():
        applied.append("strip_code_fence")
        text = stripped

    candidate = _extract_first_object(text)
    if candidate is None:
        return RepairOutcome(
            raw_text, raw_text, tuple(applied), False, "no_balanced_object_present"
        )
    if candidate != text.strip():
        applied.append("extract_first_balanced_object")

    decoded: dict[str, Any] | None = None
    try:
        decoded = json.loads(candidate)
    except json.JSONDecodeError:
        quoted = _BARE_KEY.sub(r'\1"\2"\3', candidate)
        if quoted != candidate:
            try:
                decoded = json.loads(quoted)
                applied.append("quote_bare_keys")
            except json.JSONDecodeError:
                decoded = None
    if decoded is None:
        # A duplicate key parses under json.loads (last wins) but is rejected by
        # the benchmark's safe parser. Collapsing to first-wins is the declared
        # conservative choice: it keeps the model's first assertion.
        return RepairOutcome(
            raw_text, raw_text, tuple(applied), False, "payload_truncated_or_unparseable"
        )
    if not isinstance(decoded, dict):
        return RepairOutcome(raw_text, raw_text, tuple(applied), False, "payload_not_object")

    # safe_parse_result rejects duplicate keys; json.loads silently kept the last.
    # Detect the case and record that we collapsed it.
    if parsed is None and any("duplicate_json_key" in error for error in parse_errors):
        applied.append("collapse_duplicate_keys_first_wins")
        first_wins: dict[str, Any] = {}
        # Re-parse preserving first occurrence.
        def _first(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
            out: dict[str, Any] = {}
            for key, value in pairs:
                out.setdefault(key, value)
            return out

        try:
            decoded = json.loads(candidate, object_pairs_hook=_first)
        except (json.JSONDecodeError, ValueError):
            pass
        if not isinstance(decoded, dict):
            return RepairOutcome(raw_text, raw_text, tuple(applied), False, "payload_not_object")
        first_wins = decoded

    if decoded.get("schema_version") != RESULT_SCHEMA_VERSION:
        decoded["schema_version"] = RESULT_SCHEMA_VERSION
        applied.append("insert_schema_version")

    action = decoded.get("action")
    if isinstance(action, str) and action not in task["allowed_actions"]:
        mapped = ACTION_SYNONYMS.get(action.strip().lower())
        if mapped is not None and mapped in task["allowed_actions"]:
            decoded["action"] = mapped
            applied.append("map_action_synonym")

    extra = sorted(set(decoded) - ALLOWED_RESULT_KEYS)
    if extra:
        for key in extra:
            decoded.pop(key, None)
        applied.append("drop_extra_keys")

    if "answer" in decoded and not isinstance(decoded["answer"], dict):
        return RepairOutcome(
            raw_text, raw_text, tuple(applied), False, "answer_not_object_cannot_synthesize"
        )
    if "task_id" not in decoded:
        return RepairOutcome(
            raw_text, raw_text, tuple(applied), False, "task_id_absent_cannot_synthesize"
        )
    for required in ("action", "answer", "evidence_refs"):
        if required not in decoded:
            return RepairOutcome(
                raw_text, raw_text, tuple(applied), False, f"{required}_absent_cannot_synthesize"
            )

    repaired_text = json.dumps(decoded, sort_keys=True)
    reparsed, _ = safe_parse_result(repaired_text)
    if reparsed is None or validate_result(reparsed, task):
        errors = validate_result(reparsed, task) if reparsed is not None else ["unparseable"]
        return RepairOutcome(
            raw_text,
            raw_text,
            tuple(applied),
            False,
            "still_invalid_after_repair:" + ",".join(errors[:3]),
        )
    return RepairOutcome(raw_text, repaired_text, tuple(applied), True, None)


class FormatRepairTarget(Target):
    """Wraps a target with the declared deterministic repair stage."""

    kind = "format_repair_wrapper"

    def __init__(self, inner: Target, *, name: str | None = None) -> None:
        self.inner = inner
        self.name = name or f"{inner.name}+repair"
        self.applied_counts: dict[str, int] = {}
        self.unrecovered_counts: dict[str, int] = {}
        self.recovered = 0
        self.attempted = 0

    def assign_failure_modes(self, task_ids, *, mode: str):  # pragma: no cover - delegation
        assigner = getattr(self.inner, "assign_failure_modes", None)
        if assigner is None:
            return {}
        return assigner(task_ids, mode=mode)

    def emit(self, task: dict[str, Any], *, mode: str, difficulty: float) -> Emission:
        emission = self.inner.emit(task, mode=mode, difficulty=difficulty)
        outcome = repair_emission(emission.raw_text, task)
        self.attempted += 1
        for transformation in outcome.applied:
            self.applied_counts[transformation] = self.applied_counts.get(transformation, 0) + 1
        if outcome.recovered:
            self.recovered += 1
        elif outcome.unrecovered_reason:
            reason = outcome.unrecovered_reason.split(":")[0]
            self.unrecovered_counts[reason] = self.unrecovered_counts.get(reason, 0) + 1
        return Emission(
            task_id=emission.task_id,
            raw_text=outcome.repaired_text,
            declared_failure_mode=(
                emission.declared_failure_mode
                if not outcome.recovered
                else f"repaired_from:{emission.declared_failure_mode}"
            ),
        )

    def repair_report(self) -> dict[str, Any]:
        return {
            "schema_version": "boundarybench.gbi_v2_repair_report.v1",
            "repair_version": REPAIR_VERSION,
            "wrapped_target": self.inner.name,
            "emissions_seen": self.attempted,
            "recovered_or_already_valid": self.recovered,
            "recovery_rate": (self.recovered / self.attempted) if self.attempted else None,
            "transformations_applied": dict(sorted(self.applied_counts.items())),
            "unrecovered_reasons": dict(sorted(self.unrecovered_counts.items())),
            "not_repaired_by_design": [
                "truncated payloads (no determinate completion)",
                "non-object answer (cannot synthesize intended content)",
            ],
            "note": (
                "Repair changes admissibility, not correctness. A repaired record is graded "
                "on its merits and a wrong action stays wrong."
            ),
        }

    def manifest(self) -> dict[str, Any]:
        inner = self.inner.manifest()
        return {
            "schema_version": "boundarybench.betal_target_surrogate.v1",
            "name": self.name,
            "kind": self.kind,
            "wrapped": inner,
            "declared_behavior": (
                "Applies only deterministic, declared format repairs to the wrapped target's "
                "raw emission. Performs no model call and fabricates no content."
            ),
        }
