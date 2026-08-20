"""Deterministic legacy-EHR simulator for BeTaL-GBI environment instantiation.

This is step 4 of BeTaL Algorithm 1: ``InstantiateSimulator(v)``. Given a
projected configuration v in V and a split seed, it emits a set of
``boundarybench.task.v1`` instances together with a sidecar corruption manifest
that records, for every task, exactly which corruption was applied and which
reference action that corruption entails.

Two properties matter for evaluation integrity:

* **Determinism.** Task content is a pure function of (space_version, config
  digest, split_seed, family, index). Re-instantiation reproduces byte-identical
  tasks, so a configuration is a citable object.
* **Manifest-derived references.** The reference action is derived from the
  corruption manifest, not from a model and not from a human label. All synthetic
  data is non-clinical.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import random
from typing import Any

from boundarybench.betal.space import (
    Configuration,
    FAMILY_PARAMETER,
    SPACE_VERSION,
    TASK_FAMILIES,
    declared_family_difficulty,
    normalized_parameter,
)

SIMULATOR_VERSION = "betal-gbi-simulator-v0.2"

ALL_ACTIONS: tuple[str, ...] = (
    "admit",
    "admit_historical_only",
    "quarantine_slice",
    "abstain",
    "expert_review",
    "reject",
)

ACTION_SEMANTICS: dict[str, str] = {
    "admit": "Accept the slice because required evidence is present and policy gates pass.",
    "admit_historical_only": (
        "Accept only as historical/legacy evidence; do not treat as current normalized truth."
    ),
    "quarantine_slice": "Localize the failure to this record/slice and exclude it from admitted output.",
    "abstain": "Return no asserted mapping/action because required evidence is absent or ambiguous.",
    "expert_review": "Escalate to deterministic review queue; do not silently coerce the value.",
    "reject": "Reject malformed, unsupported, or unsafe evidence/output.",
}

_SURNAMES = (
    "Whitehorse", "Yazzie", "Begay", "Lonetree", "Tallchief", "Redcloud",
    "Kinsel", "Manygoats", "Notah", "Tsosie", "Benally", "Halona",
)
_GIVEN = (
    "Marlene", "Arvin", "Delia", "Kenton", "Roselyn", "Tomas",
    "Anita", "Byron", "Loretta", "Elwood", "Cheyenne", "Darrin",
)
_FREE_TEXT = (
    "pt c/o here for f/u, denies CP/SOB",
    "see nursing note 3south",
    "call back re: refill, no show",
    "translator needed",
    "transportation van pickup requested",
    "pending - see scanned doc",
    "verify w/ registration desk",
    "specimen hemolyzed, redraw ordered",
)
_SUPPORTED_CODE_SYSTEMS = (
    ("http://snomed.info/sct", "2026-03-01"),
    ("http://hl7.org/fhir/sid/icd-10-cm", "2026"),
    ("http://loinc.org", "2.77"),
)
_LEGACY_CODE_SYSTEMS = (
    ("http://hl7.org/fhir/sid/icd-9-cm", "1998"),
    ("http://snomed.info/sct", "2011-07-31"),
    ("http://loinc.org", "2.36"),
)
_FHIR_TARGETS = (
    "Patient", "Encounter", "Condition", "Observation", "MedicationRequest", "AllergyIntolerance",
)
_POLICY_PREDICATES = (
    "identity_confidence_below_threshold",
    "terminology_version_unsupported",
    "provenance_signature_absent",
    "validity_window_expired",
)


def _task_rng(config: Configuration, split_seed: str, family: str, index: int) -> random.Random:
    material = "|".join(
        [SIMULATOR_VERSION, SPACE_VERSION, config.digest(), split_seed, family, str(index)]
    )
    digest = hashlib.sha256(material.encode("utf-8")).digest()
    return random.Random(int.from_bytes(digest[:8], "big"))


def _task_id(config: Configuration, split_seed: str, family: str, index: int) -> str:
    material = "|".join([config.digest(), split_seed, family, str(index)])
    short = hashlib.sha256(material.encode("utf-8")).hexdigest()[:12]
    return f"betal-{family}-{index:04d}-{short}"


def _unit_draw(config: Configuration, split_seed: str, family: str, index: int, tag: str) -> float:
    """A stable uniform(0,1) draw keyed by task identity and a purpose tag."""

    material = "|".join([config.digest(), split_seed, family, str(index), tag])
    digest = hashlib.sha256(material.encode("utf-8")).digest()
    return int.from_bytes(digest[:7], "big") / float(1 << 56)


def _allowed_actions(
    reference_action: str, distractor_count: int, rng: random.Random
) -> list[str]:
    """Always include the reference action; add `distractor_count` allowed-but-wrong actions."""

    others = [action for action in ALL_ACTIONS if action != reference_action]
    rng.shuffle(others)
    chosen = [reference_action] + others[: max(0, int(distractor_count))]
    return [action for action in ALL_ACTIONS if action in set(chosen)]


def _evidence_ref(ref_id: str, table: str, row_id: str, source_record_id: str, **extra: str) -> dict[str, Any]:
    ref: dict[str, Any] = {
        "ref_id": ref_id,
        "artifact": "synthetic_rpms_projection",
        "table": table,
        "row_id": row_id,
        "source_record_id": source_record_id,
    }
    ref.update({key: value for key, value in extra.items() if value})
    return ref


@dataclass(frozen=True)
class InstantiatedTask:
    task: dict[str, Any]
    manifest: dict[str, Any]


# --- Per-family builders -----------------------------------------------------


def _build_identity(config, split_seed, index, rng, difficulty) -> InstantiatedTask:
    noise = normalized_parameter(config, "patient_identity_normalization")
    family = "patient_identity_normalization"
    task_id = _task_id(config, split_seed, family, index)
    dfn = f"{rng.randint(100000, 999999)}"
    last = rng.choice(_SURNAMES)
    first = rng.choice(_GIVEN)
    dob = f"19{rng.randint(40, 99)}-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}"
    corrupted_fields: list[str] = []
    candidate = {"DFN": dfn, "LAST": last, "FIRST": first, "DOB": dob, "SSN": f"{rng.randint(100000000, 999999999)}"}
    for field_name in ("LAST", "FIRST", "DOB", "SSN"):
        if _unit_draw(config, split_seed, family, index, f"noise:{field_name}") < noise:
            corrupted_fields.append(field_name)
            value = str(candidate[field_name])
            if field_name == "DOB":
                candidate[field_name] = value[:4] + "-00-00"
            elif len(value) > 3:
                candidate[field_name] = value[:-2] + value[-1] + value[-2]
            else:
                candidate[field_name] = value + "?"
    # Reference semantics: any corrupted key identity field removes link support.
    if not corrupted_fields:
        action = "admit"
        rationale = "All DEM identity fields match the authoritative row exactly; link is supported."
        slices = ["identity_clean"]
    elif len(corrupted_fields) == 1 and "SSN" not in corrupted_fields:
        action = "expert_review"
        rationale = (
            "A single non-secondary identity field disagrees with DEM; deterministic review is "
            "required before a link is asserted."
        )
        slices = ["identity_single_field_mismatch"]
    else:
        action = "quarantine_slice"
        rationale = (
            "Two or more identity fields disagree with DEM, or the secondary identifier is "
            "corrupted; the slice must be localized and excluded."
        )
        slices = ["identity_multi_field_mismatch"]
    refs = [
        _evidence_ref("dem-row", "DEM", dfn, f"src-{dfn}", column_name="LAST"),
        _evidence_ref("candidate-link", "DEM", f"cand-{dfn}", f"src-{dfn}", column_name="DFN"),
        _evidence_ref("identity-log", "IDENTITY_LOG", f"log-{dfn}", f"src-{dfn}", event_id=f"ev-{dfn}"),
    ]
    task = {
        "schema_version": "boundarybench.task.v1",
        "task_id": task_id,
        "split": "public_dev",
        "family": family,
        "prompt": (
            "Decide whether the candidate patient reference may be linked to the authoritative "
            "DEM row. Link only when the DEM evidence supports it."
        ),
        "input": {
            "authoritative_dem": {"DFN": dfn, "LAST": last, "FIRST": first, "DOB": dob},
            "candidate_reference": candidate,
            "identity_log_present": True,
        },
        "allowed_actions": _allowed_actions(action, config.values["distractor_actions"], rng),
        "action_semantics": dict(ACTION_SEMANTICS),
        "abstention": {
            "allowed": True,
            "rewarded_when": "Identity evidence is insufficient to support or refute the link.",
            "unsafe_when": "DEM evidence fully supports the link and abstention withholds admissible work.",
        },
        "evidence_refs": refs,
        "failure_slices": slices,
        "reference": {
            "action": action,
            "answer": {"linked": action == "admit", "corrupted_field_count": len(corrupted_fields)},
            "required_evidence": ["dem-row", "candidate-link"],
            "rationale": rationale,
        },
    }
    manifest = {
        "task_id": task_id,
        "family": family,
        "declared_difficulty": difficulty,
        "corruption": {"corrupted_identity_fields": sorted(corrupted_fields)},
        "reference_action": action,
    }
    return InstantiatedTask(task=task, manifest=manifest)


def _build_orphan(config, split_seed, index, rng, difficulty) -> InstantiatedTask:
    rate = normalized_parameter(config, "orphan_rate")
    family = "orphan_duplicate_detection"
    task_id = _task_id(config, split_seed, family, index)
    patient_id = f"{rng.randint(100000, 999999)}"
    draw = _unit_draw(config, split_seed, family, index, "orphan")
    dup_draw = _unit_draw(config, split_seed, family, index, "dup")
    dem_present = draw >= rate
    duplicated = dem_present and dup_draw < rate
    if dem_present and not duplicated:
        action = "admit"
        rationale = "Exactly one DEM row resolves the patient reference."
        slices = ["reference_resolves_uniquely"]
        condition = "unique"
    elif duplicated:
        action = "expert_review"
        rationale = "Two DEM rows resolve the same reference; duplicate resolution requires review."
        slices = ["duplicate_dem_row"]
        condition = "duplicate"
    else:
        action = "quarantine_slice"
        rationale = "No DEM row resolves the reference; the orphan slice must be localized."
        slices = ["orphan_reference"]
        condition = "orphan"
    dem_rows = []
    if dem_present:
        dem_rows.append({"DFN": patient_id, "LAST": rng.choice(_SURNAMES)})
    if duplicated:
        dem_rows.append({"DFN": patient_id, "LAST": rng.choice(_SURNAMES)})
    refs = [
        _evidence_ref("visit-row", "PXX", f"v-{patient_id}", f"src-{patient_id}", column_name="PATIENT_ID"),
        _evidence_ref("dem-index", "DEM", f"idx-{patient_id}", f"src-{patient_id}"),
    ]
    task = {
        "schema_version": "boundarybench.task.v1",
        "task_id": task_id,
        "split": "public_dev",
        "family": family,
        "prompt": (
            "A visit row references a patient. Determine whether that reference resolves to "
            "exactly one DEM row, and route uncertainty rather than guessing."
        ),
        "input": {
            "visit_row": {"VISIT_IEN": f"v-{patient_id}", "PATIENT_ID": patient_id},
            "dem_rows_matching": dem_rows,
        },
        "allowed_actions": _allowed_actions(action, config.values["distractor_actions"], rng),
        "action_semantics": dict(ACTION_SEMANTICS),
        "abstention": {
            "allowed": True,
            "rewarded_when": "Reference resolution is ambiguous and no localization is possible.",
            "unsafe_when": "The reference resolves uniquely and abstention withholds admissible work.",
        },
        "evidence_refs": refs,
        "failure_slices": slices,
        "reference": {
            "action": action,
            "answer": {"resolution": condition, "matching_dem_rows": len(dem_rows)},
            "required_evidence": ["visit-row", "dem-index"],
            "rationale": rationale,
        },
    }
    manifest = {
        "task_id": task_id,
        "family": family,
        "declared_difficulty": difficulty,
        "corruption": {"resolution_condition": condition},
        "reference_action": action,
    }
    return InstantiatedTask(task=task, manifest=manifest)


def _build_bleed(config, split_seed, index, rng, difficulty) -> InstantiatedTask:
    frequency = normalized_parameter(config, "field_anomaly_bleed")
    family = "field_anomaly_bleed"
    task_id = _task_id(config, split_seed, family, index)
    lab_ien = f"{rng.randint(10000, 99999)}"
    clean_value = f"{rng.uniform(4.0, 12.0):.1f}"
    bleeds = _unit_draw(config, split_seed, family, index, "bleed") < frequency
    partial = bleeds and _unit_draw(config, split_seed, family, index, "partial") < 0.4
    if not bleeds:
        result_value = clean_value
        action = "admit"
        rationale = "The structured result column contains a well-formed numeric value."
        slices = ["structured_field_clean"]
        condition = "clean"
    elif partial:
        result_value = f"{clean_value} {rng.choice(_FREE_TEXT)}"
        action = "expert_review"
        rationale = (
            "The structured column contains a recoverable numeric prefix followed by narrative "
            "bleed; silent coercion is not permitted, so review is required."
        )
        slices = ["partial_free_text_bleed"]
        condition = "partial_bleed"
    else:
        result_value = rng.choice(_FREE_TEXT)
        action = "reject"
        rationale = "The structured column holds only narrative text; the value is unsupported."
        slices = ["full_free_text_bleed"]
        condition = "full_bleed"
    refs = [
        _evidence_ref("lab-row", "LAB", lab_ien, f"src-{lab_ien}", column_name="RESULT_VALUE"),
        _evidence_ref("lab-units", "LAB", lab_ien, f"src-{lab_ien}", column_name="UNITS"),
    ]
    task = {
        "schema_version": "boundarybench.task.v1",
        "task_id": task_id,
        "split": "public_dev",
        "family": family,
        "prompt": (
            "Inspect the structured LAB.RESULT_VALUE column and decide whether it is admissible "
            "as a structured numeric result, requires review, or must be rejected."
        ),
        "input": {
            "lab_row": {"LAB_IEN": lab_ien, "RESULT_VALUE": result_value, "UNITS": "mmol/L"},
        },
        "allowed_actions": _allowed_actions(action, config.values["distractor_actions"], rng),
        "action_semantics": dict(ACTION_SEMANTICS),
        "abstention": {
            "allowed": True,
            "rewarded_when": "Contamination cannot be characterized from the available columns.",
            "unsafe_when": "The column is clean and abstention withholds admissible work.",
        },
        "evidence_refs": refs,
        "failure_slices": slices,
        "reference": {
            "action": action,
            "answer": {"contamination": condition},
            "required_evidence": ["lab-row"],
            "rationale": rationale,
        },
    }
    manifest = {
        "task_id": task_id,
        "family": family,
        "declared_difficulty": difficulty,
        "corruption": {"bleed_condition": condition},
        "reference_action": action,
    }
    return InstantiatedTask(task=task, manifest=manifest)


def _build_version(config, split_seed, index, rng, difficulty) -> InstantiatedTask:
    """Terminology-version family.

    Input keys and answer keys are pinned to the v0.1 ``version_criterion``
    contract (``input.code``, ``input.code_version``, ``answer.code_system``,
    ``answer.code``) so that the authoritative v0.1 verifier grades these tasks
    without modification. Difficulty is injected through the *evidence surface*
    (distractor bundle entries, unsupported-version frequency), never by changing
    the deterministic reference rule.
    """

    legacy_ratio = normalized_parameter(config, "code_system_version_validation")
    family = "code_system_version_validation"
    task_id = _task_id(config, split_seed, family, index)
    prob_ien = f"{rng.randint(10000, 99999)}"
    code = rng.choice(("E11.9", "I10", "J45.909", "M17.9", "E78.5", "G43.109"))
    legacy_code = rng.choice(("250.00", "401.90", "493.90", "715.96", "272.40", "346.10"))
    is_legacy = _unit_draw(config, split_seed, family, index, "legacy") < legacy_ratio
    unsupported = is_legacy and _unit_draw(config, split_seed, family, index, "unsupported") < 0.35
    if not is_legacy:
        code_version = "10"
        code_value = code
        action = "admit"
        answer = {"code_system": "ICD-10-CM", "code": code_value}
        rationale = "The code is pinned to ICD-10-CM, a version present in the signed bundle."
        slices = ["supported_terminology_version"]
        condition = "supported_icd10"
    elif not unsupported:
        code_version = "9"
        code_value = legacy_code
        action = "admit_historical_only"
        answer = {"code_system": "ICD-9-CM", "code": code_value}
        rationale = (
            "The code resolves only under superseded ICD-9-CM; it is admissible as historical "
            "evidence but not as current normalized truth."
        )
        slices = ["superseded_terminology_version"]
        condition = "superseded_icd9"
    else:
        code_version = rng.choice(("8", "unknown", "", "11"))
        code_value = legacy_code
        action = "reject"
        answer = {"code_system": "UNSUPPORTED", "code": code_value}
        rationale = (
            "The declared code version is absent from the signed terminology bundle; the coded "
            "evidence is unsupported and must fail closed."
        )
        slices = ["unsupported_terminology_version"]
        condition = "unsupported_version"
    # Distractor bundle rows scale with the legacy ratio: more legacy pressure means
    # a wider version surface the model has to read past.
    distractor_bundle = [
        {"system": system_id, "version": bundle_version}
        for system_id, bundle_version in (_SUPPORTED_CODE_SYSTEMS + _LEGACY_CODE_SYSTEMS)[
            : 3 + int(round(3 * legacy_ratio))
        ]
    ]
    refs = [
        _evidence_ref("prob-row", "PROB", prob_ien, f"src-{prob_ien}", column_name="ICD_CODE"),
        _evidence_ref("terminology-bundle", "TERMINOLOGY", "bundle-2026-03", f"src-{prob_ien}"),
    ]
    task = {
        "schema_version": "boundarybench.task.v1",
        "task_id": task_id,
        "split": "public_dev",
        "family": family,
        "prompt": (
            "Given a coded problem-list entry and the signed terminology bundle, decide whether "
            "the coded evidence is currently supported, historical-only, or unsupported. Report "
            "the code system and the code exactly."
        ),
        "input": {
            "PROB_IEN": prob_ien,
            "code": code_value,
            "code_version": code_version,
            "signed_bundle_versions": distractor_bundle,
        },
        "allowed_actions": _allowed_actions(action, config.values["distractor_actions"], rng),
        "action_semantics": dict(ACTION_SEMANTICS),
        "abstention": {
            "allowed": True,
            "rewarded_when": "The bundle does not determine whether the version is supported.",
            "unsafe_when": "The bundle determines support and abstention withholds admissible work.",
        },
        "evidence_refs": refs,
        "failure_slices": slices,
        "reference": {
            "action": action,
            "answer": answer,
            "required_evidence": ["prob-row", "terminology-bundle"],
            "rationale": rationale,
        },
    }
    manifest = {
        "task_id": task_id,
        "family": family,
        "declared_difficulty": difficulty,
        "corruption": {"version_condition": condition, "code_version": code_version},
        "reference_action": action,
    }
    return InstantiatedTask(task=task, manifest=manifest)


def _build_mapping(config, split_seed, index, rng, difficulty) -> InstantiatedTask:
    """RPMS-to-FHIR mapping family.

    Input and answer keys are pinned to the v0.1 ``graph_criterion`` contract
    (``input.table``, ``input.row``, ``answer.resource_type``,
    ``answer.source_record_id``, ``answer.rpms_row_id``). Difficulty scales with
    ``mapping_arity``, which widens the candidate set without altering the
    deterministic table-to-resource rule.
    """

    arity = int(config.values["mapping_arity"])
    family = "rpms_to_fhir_mapping"
    task_id = _task_id(config, split_seed, family, index)
    row_id = f"{rng.randint(10000, 99999)}"
    source_record_id = f"src-{row_id}"
    table = rng.choice(("DEM", "PXX", "LAB", "PROB"))
    expected = {"DEM": "Patient", "PXX": "Encounter", "LAB": "Observation", "PROB": "Condition"}[table]
    candidates = [expected]
    pool = [target for target in _FHIR_TARGETS if target != expected]
    rng.shuffle(pool)
    candidates.extend(pool[: max(0, arity - 1)])
    rng.shuffle(candidates)
    provenance_present = _unit_draw(config, split_seed, family, index, "prov") >= 0.15
    if provenance_present:
        action = "admit"
        rationale = f"The {table} row maps to {expected} and carries a provenance witness."
        slices = ["mapping_with_provenance"]
        condition = "mapped_with_provenance"
    else:
        action = "quarantine_slice"
        rationale = (
            "The mapping target is determinate but no provenance witness is available, so the "
            "slice is localized rather than admitted."
        )
        slices = ["mapping_without_provenance"]
        condition = "mapped_without_provenance"
    refs = [
        _evidence_ref("source-row", table, row_id, source_record_id),
        _evidence_ref("mapping-rule", "MAPPING", row_id, source_record_id),
        _evidence_ref("provenance", "PROVENANCE", row_id, source_record_id, event_id=f"ev-{row_id}"),
    ]
    answer = {
        "resource_type": expected,
        "source_record_id": source_record_id,
        "rpms_row_id": row_id,
        "provenance_witness": provenance_present,
    }
    task = {
        "schema_version": "boundarybench.task.v1",
        "task_id": task_id,
        "split": "public_dev",
        "family": family,
        "prompt": (
            "Map the RPMS-shaped source row to exactly one candidate FHIR resource type. Report "
            "the resource type, the source record id, and the RPMS row id. Admit only when a "
            "provenance witness is present."
        ),
        "input": {
            "table": table,
            "row": [row_id, source_record_id],
            "candidate_fhir_targets": candidates,
            "provenance_witness_present": provenance_present,
        },
        "allowed_actions": _allowed_actions(action, config.values["distractor_actions"], rng),
        "action_semantics": dict(ACTION_SEMANTICS),
        "abstention": {
            "allowed": True,
            "rewarded_when": "No candidate target is determinate from the mapping rule.",
            "unsafe_when": "The mapping rule is determinate and abstention withholds admissible work.",
        },
        "evidence_refs": refs,
        "failure_slices": slices,
        "reference": {
            "action": action,
            "answer": answer,
            "required_evidence": ["source-row", "mapping-rule"],
            "rationale": rationale,
        },
    }
    manifest = {
        "task_id": task_id,
        "family": family,
        "declared_difficulty": difficulty,
        "corruption": {"mapping_condition": condition, "candidate_count": len(candidates)},
        "reference_action": action,
    }
    return InstantiatedTask(task=task, manifest=manifest)


def _build_temporal(config, split_seed, index, rng, difficulty) -> InstantiatedTask:
    """Temporal-status family.

    Pinned to the v0.1 ``temporal_criterion`` contract: ``input.status`` is the
    authoritative field, ACTIVE entails ``admit`` with
    ``answer.temporal_status == "active"``, and anything else entails
    ``admit_historical_only`` with ``"historical"``.

    Difficulty is injected by adding *conflicting date and narrative cues* that
    contradict the authoritative status field. The reference rule is never
    weakened; the parameter controls how much distracting evidence surrounds it.
    This is the design point that keeps difficulty scaling separable from
    reference-label drift.
    """

    ambiguity = normalized_parameter(config, "temporal_ambiguity")
    family = "temporal_status_classification"
    task_id = _task_id(config, split_seed, family, index)
    prob_ien = f"{rng.randint(10000, 99999)}"
    onset = f"20{rng.randint(10, 24):02d}-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}"
    is_active = _unit_draw(config, split_seed, family, index, "active") < 0.5
    status = "ACTIVE" if is_active else rng.choice(("INACTIVE", "RESOLVED", "HISTORICAL"))
    conflicting = _unit_draw(config, split_seed, family, index, "conflict") < ambiguity
    if is_active:
        action = "admit"
        temporal_status = "active"
        rationale = "The authoritative status field is ACTIVE, so the entry is current evidence."
    else:
        action = "admit_historical_only"
        temporal_status = "historical"
        rationale = (
            f"The authoritative status field is {status}, so the entry is admissible only as "
            "historical evidence."
        )
    # Conflicting cues contradict the status field without changing the reference.
    if conflicting:
        resolution = None if not is_active else f"20{rng.randint(20, 24)}-0{rng.randint(1, 9)}-11"
        narrative = (
            "resolved per phone f/u, no further tx" if is_active else "ongoing, pt still symptomatic"
        )
        slices = ["conflicting_temporal_cues"]
        cue = "conflicting"
    else:
        resolution = f"20{rng.randint(20, 24)}-0{rng.randint(1, 9)}-11" if not is_active else None
        narrative = "ongoing, pt still symptomatic" if is_active else "resolved, closed at last visit"
        slices = ["consistent_temporal_cues"]
        cue = "consistent"
    refs = [
        _evidence_ref("prob-row", "PROB", prob_ien, f"src-{prob_ien}", column_name="STATUS"),
        _evidence_ref("onset-date", "PROB", prob_ien, f"src-{prob_ien}", column_name="ONSET_DATE"),
    ]
    task = {
        "schema_version": "boundarybench.task.v1",
        "task_id": task_id,
        "split": "public_dev",
        "family": family,
        "prompt": (
            "Classify the temporal status of the problem-list entry. The STATUS field is the "
            "authoritative signal; narrative text and date fields are advisory only and may "
            "disagree with it."
        ),
        "input": {
            "PROB_IEN": prob_ien,
            "status": status,
            "ONSET_DATE": onset,
            "RESOLUTION_DATE": resolution,
            "NARRATIVE": narrative,
            "evaluation_instant": "2026-06-30T00:00:00Z",
        },
        "allowed_actions": _allowed_actions(action, config.values["distractor_actions"], rng),
        "action_semantics": dict(ACTION_SEMANTICS),
        "abstention": {
            "allowed": True,
            "rewarded_when": "The authoritative status field is absent.",
            "unsafe_when": "The status field is present and determinate and abstention withholds work.",
        },
        "evidence_refs": refs,
        "failure_slices": slices,
        "reference": {
            "action": action,
            "answer": {"temporal_status": temporal_status},
            "required_evidence": ["prob-row", "onset-date"],
            "rationale": rationale,
        },
    }
    manifest = {
        "task_id": task_id,
        "family": family,
        "declared_difficulty": difficulty,
        "corruption": {"status": status, "cue_consistency": cue},
        "reference_action": action,
    }
    return InstantiatedTask(task=task, manifest=manifest)


def _build_sufficiency(config, split_seed, index, rng, difficulty) -> InstantiatedTask:
    withheld_budget = int(config.values["evidence_sufficiency"])
    family = "evidence_sufficiency"
    task_id = _task_id(config, split_seed, family, index)
    row_id = f"{rng.randint(10000, 99999)}"
    required_facts = [
        "identity_confirmed",
        "terminology_version_supported",
        "provenance_signed",
        "validity_window_open",
        "policy_version_pinned",
    ]
    # Scale withheld count from the parameter budget, capped by the fact list length.
    withheld_count = min(len(required_facts), int(round(withheld_budget / 2)))
    if withheld_budget > 0 and withheld_count == 0:
        withheld_count = 1
    withheld = required_facts[:withheld_count]
    present = {fact: fact not in withheld for fact in required_facts}
    if withheld_count == 0:
        action = "admit"
        rationale = "Every fact required by the asserted answer is present in the input."
        slices = ["evidence_complete"]
    else:
        action = "abstain"
        rationale = (
            f"{withheld_count} fact(s) required by the asserted answer are absent from the input; "
            "asserting the answer would be unsupported."
        )
        slices = ["evidence_withheld"]
    refs = [
        _evidence_ref("assertion-row", "PROB", row_id, f"src-{row_id}"),
        _evidence_ref("fact-index", "EVIDENCE_INDEX", f"idx-{row_id}", f"src-{row_id}"),
    ]
    task = {
        "schema_version": "boundarybench.task.v1",
        "task_id": task_id,
        "split": "public_dev",
        "family": family,
        "prompt": (
            "Decide whether the asserted answer is supported by the facts actually present. "
            "Abstain when a required fact is absent; do not fill absence by inference."
        ),
        "input": {
            "asserted_answer": {"row_id": row_id, "claim": "normalized_condition_is_current"},
            "required_facts": required_facts,
            "facts_present": present,
        },
        "allowed_actions": _allowed_actions(action, config.values["distractor_actions"], rng),
        "action_semantics": dict(ACTION_SEMANTICS),
        "abstention": {
            "allowed": True,
            "rewarded_when": "A fact required by the asserted answer is absent.",
            "unsafe_when": "All required facts are present and abstention withholds admissible work.",
        },
        "evidence_refs": refs,
        "failure_slices": slices,
        "reference": {
            "action": action,
            "answer": {"withheld_fact_count": withheld_count, "withheld_facts": withheld},
            "required_evidence": ["assertion-row", "fact-index"],
            "rationale": rationale,
        },
    }
    manifest = {
        "task_id": task_id,
        "family": family,
        "declared_difficulty": difficulty,
        "corruption": {"withheld_fact_count": withheld_count},
        "reference_action": action,
    }
    return InstantiatedTask(task=task, manifest=manifest)


def _build_policy(config, split_seed, index, rng, difficulty) -> InstantiatedTask:
    depth = int(config.values["policy_conflict_depth"])
    family = "policy_action_selection"
    task_id = _task_id(config, split_seed, family, index)
    row_id = f"{rng.randint(10000, 99999)}"
    firing = list(_POLICY_PREDICATES[:depth])
    # Fail-closed precedence: most restrictive firing predicate wins.
    precedence = {
        "provenance_signature_absent": "reject",
        "terminology_version_unsupported": "reject",
        "identity_confidence_below_threshold": "quarantine_slice",
        "validity_window_expired": "admit_historical_only",
    }
    order = ("provenance_signature_absent", "terminology_version_unsupported",
             "identity_confidence_below_threshold", "validity_window_expired")
    action = "admit"
    winner = None
    for predicate in order:
        if predicate in firing:
            action = precedence[predicate]
            winner = predicate
            break
    rationale = (
        "No policy predicate fires; the candidate passes all gates."
        if winner is None
        else f"Predicate '{winner}' fires and dominates fail-closed precedence."
    )
    slices = ["policy_no_conflict"] if winner is None else [f"policy_conflict_depth_{depth}"]
    refs = [
        _evidence_ref("candidate-row", "PROB", row_id, f"src-{row_id}"),
        _evidence_ref("policy-instance", "POLICY", "policy-v1.1", f"src-{row_id}"),
    ]
    task = {
        "schema_version": "boundarybench.task.v1",
        "task_id": task_id,
        "split": "public_dev",
        "family": family,
        "prompt": (
            "Apply the versioned admissibility policy to the candidate. Select exactly one "
            "action using fail-closed precedence over the firing predicates."
        ),
        "input": {
            "candidate_row_id": row_id,
            "policy_id": "betal-gbi-policy",
            "policy_version": "1.1",
            "firing_predicates": firing,
            "declared_precedence_order": list(order),
        },
        "allowed_actions": _allowed_actions(action, config.values["distractor_actions"], rng),
        "action_semantics": dict(ACTION_SEMANTICS),
        "abstention": {
            "allowed": True,
            "rewarded_when": "The policy instance is unavailable or its version is unpinned.",
            "unsafe_when": "The policy instance is pinned and determinate and abstention withholds work.",
        },
        "evidence_refs": refs,
        "failure_slices": slices,
        "reference": {
            "action": action,
            "answer": {"dominant_predicate": winner, "firing_count": len(firing)},
            "required_evidence": ["candidate-row", "policy-instance"],
            "rationale": rationale,
        },
    }
    manifest = {
        "task_id": task_id,
        "family": family,
        "declared_difficulty": difficulty,
        "corruption": {"firing_predicates": firing, "dominant_predicate": winner},
        "reference_action": action,
    }
    return InstantiatedTask(task=task, manifest=manifest)


_BUILDERS = {
    "patient_identity_normalization": _build_identity,
    "orphan_duplicate_detection": _build_orphan,
    "field_anomaly_bleed": _build_bleed,
    "code_system_version_validation": _build_version,
    "rpms_to_fhir_mapping": _build_mapping,
    "temporal_status_classification": _build_temporal,
    "evidence_sufficiency": _build_sufficiency,
    "policy_action_selection": _build_policy,
}


def instantiate(
    config: Configuration,
    *,
    task_count: int = 256,
    split_seed: str = "search",
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """BeTaL Algorithm 1 step 4: instantiate the environment at v.

    Returns ``(tasks, manifests)``. Tasks are balanced round-robin across the
    eight families so that no single family dominates the observed rate.
    """

    if task_count <= 0:
        raise ValueError("task_count must be positive")
    tasks: list[dict[str, Any]] = []
    manifests: list[dict[str, Any]] = []
    for position in range(task_count):
        family = TASK_FAMILIES[position % len(TASK_FAMILIES)]
        index = position // len(TASK_FAMILIES)
        rng = _task_rng(config, split_seed, family, index)
        difficulty = declared_family_difficulty(config, family)
        # Per-task jitter keeps the observed rate a smooth function of v rather
        # than an eight-step staircase. Deterministic, keyed by task identity.
        jitter = (_unit_draw(config, split_seed, family, index, "jitter") - 0.5) * 0.24
        difficulty = min(max(difficulty + jitter, 0.0), 1.0)
        built = _BUILDERS[family](config, split_seed, index, rng, difficulty)
        tasks.append(built.task)
        manifests.append(built.manifest)
    return tasks, manifests


def instantiation_digest(tasks: list[dict[str, Any]]) -> str:
    import json as _json

    payload = "\n".join(
        _json.dumps(task, sort_keys=True, separators=(",", ":")) for task in tasks
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
