"""Authoritative grounding state W, as witness bundles.

The GBI/DCSE manuscript defines admissibility against an external-validity
predicate over an *authoritative grounding state*, not against an answer key
(Section 12.1.3, Section 12.6):

    W = ( patient identity log, FHIR resources, signed terminology bundle,
          Provenance, AuditEvent, policy rules, human adjudications )

    Admissible(b) = 1  <=>  there exists an admissible witness w with EV(b, w) = 1

This module builds that `w`. It is the object that makes the substrate's safety
claim measurable, because a deployed system has witnesses and does *not* have a
reference action. BoundaryBench v0.1 scored proposals by exact agreement with a
held-out reference; that measures answer-key agreement, which is a different
property from admissibility and is not available at deployment time.

The witness is derived from the simulator's corruption manifest, but it exposes
only what a deployed grounding state would expose. It never carries the reference
action. That separation is asserted in the verification suite: if the reference
leaked into the witness, every downstream containment number would be circular.

Graded fields are deliberate. `identity_match_score` and `evidence_completeness`
exist so that clean records sometimes *look* borderline, which is what makes the
sensitivity / false-conflict trade-off in Table 3 a real trade-off rather than a
formality.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
from typing import Any

WITNESS_VERSION = "gbi-v2-witness-bundle-v2"

# Tables holding shared, read-only reference objects rather than subject-scoped
# records. The distinction matters for surgical quarantine: a bad record that
# *cites* the signed terminology bundle does not taint the bundle, so closing the
# quarantine over the bundle would isolate every unrelated record that also cites
# it. Only a refusal that implicates the shared object itself -- Boundary 2's
# unsigned or unpinned bundle, which the manuscript says triggers an
# administrative freeze -- may close over it.
SHARED_REFERENCE_TABLES: frozenset[str] = frozenset(
    {"TERMINOLOGY", "POLICY", "MAPPING", "EVIDENCE_INDEX"}
)

# Severity classes. A "severe contradiction" is one of the conditions the
# manuscript's Boundary 1 / Boundary 2 and Section 12.2 containment table say must
# never reach an authoritative write. Superseded-but-resolvable terminology is
# deliberately NOT severe: Section 10.2 admits it as historical-only evidence.
SEVERE_CLASSES: tuple[str, ...] = (
    "identity_ambiguous",
    "identity_unresolvable",
    "terminology_bundle_unsigned",
    "terminology_bundle_unpinned",
    "terminology_unresolvable",
    "provenance_signature_absent",
    "validity_window_expired",
    "validity_window_invalid",
    "structured_field_fully_contaminated",
    "required_evidence_absent",
    "policy_predicate_mandates_refusal",
)


def _unit(*parts: str) -> float:
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).digest()
    return int.from_bytes(digest[:7], "big") / float(1 << 56)


@dataclass
class WitnessBundle:
    """One authoritative grounding state, as exposed to the admission gate."""

    task_id: str
    family: str

    # Identity certificate.
    identity_status: str = "accepted"          # accepted | ambiguous | unresolvable
    identity_mismatched_field_count: int = 0
    identity_match_score: float = 1.0          # demographic similarity, advisory only
    identity_candidate_count: int = 1

    # Signed terminology bundle.
    bundle_signed: bool = True
    bundle_pinned: bool = True
    declared_code_version: str = "current"
    code_resolvable: bool = True
    code_superseded: bool = False

    # Provenance.
    provenance_signature_present: bool = True
    provenance_source_record_id: str | None = None

    # Temporal validity.
    validity_window_open: bool = True
    validity_window_expired: bool = False
    validity_window_valid: bool = True

    # Structured-field integrity.
    field_contamination: str = "clean"         # clean | partial | full

    # Evidence sufficiency.
    required_fact_count: int = 0
    absent_fact_count: int = 0
    evidence_completeness: float = 1.0
    available_evidence_ref_ids: tuple[str, ...] = ()

    # Versioned policy instance.
    policy_id: str = "gbi-v2-policy"
    policy_version: str = "1.0"
    policy_effective_time: str = "2026-01-01T00:00:00Z"
    firing_predicates: tuple[str, ...] = ()

    # Dependency scope for surgical quarantine. Two granularities are carried so
    # that the liveness claim in Section 9.2 can be tested against the declared
    # quarantine scope rather than assumed: record-level keys support surgical
    # isolation, family-level keys model a coarse scope that would close over
    # unrelated work.
    dependency_keys: tuple[str, ...] = ()
    shared_reference_keys: tuple[str, ...] = ()
    coarse_dependency_keys: tuple[str, ...] = ()

    # Provenance of any injected contradiction (Table 3 chart-injection method).
    injected_classes: tuple[str, ...] = ()

    def severe_classes(self) -> tuple[str, ...]:
        """Enumerate the severe-contradiction classes present in this witness."""

        found: list[str] = []
        if self.identity_status == "ambiguous":
            found.append("identity_ambiguous")
        if self.identity_status == "unresolvable":
            found.append("identity_unresolvable")
        if not self.bundle_signed:
            found.append("terminology_bundle_unsigned")
        if not self.bundle_pinned:
            found.append("terminology_bundle_unpinned")
        if not self.code_resolvable:
            found.append("terminology_unresolvable")
        if not self.provenance_signature_present:
            found.append("provenance_signature_absent")
        if self.validity_window_expired:
            found.append("validity_window_expired")
        if not self.validity_window_valid:
            found.append("validity_window_invalid")
        if self.field_contamination == "full":
            found.append("structured_field_fully_contaminated")
        if self.absent_fact_count > 0:
            found.append("required_evidence_absent")
        if any(
            predicate
            in (
                "provenance_signature_absent",
                "terminology_version_unsupported",
                "identity_confidence_below_threshold",
            )
            for predicate in self.firing_predicates
        ):
            found.append("policy_predicate_mandates_refusal")
        return tuple(sorted(set(found)))

    @property
    def is_severe(self) -> bool:
        return bool(self.severe_classes())

    @property
    def is_clean(self) -> bool:
        """No severe contradiction and no historical-only qualification."""

        return not self.is_severe and not self.code_superseded and self.field_contamination == "clean"

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "boundarybench.gbi_v2_witness.v1",
            "witness_version": WITNESS_VERSION,
            "task_id": self.task_id,
            "family": self.family,
            "identity": {
                "status": self.identity_status,
                "mismatched_field_count": self.identity_mismatched_field_count,
                "match_score": round(self.identity_match_score, 4),
                "candidate_count": self.identity_candidate_count,
            },
            "terminology": {
                "bundle_signed": self.bundle_signed,
                "bundle_pinned": self.bundle_pinned,
                "declared_code_version": self.declared_code_version,
                "resolvable": self.code_resolvable,
                "superseded": self.code_superseded,
            },
            "provenance": {
                "signature_present": self.provenance_signature_present,
                "source_record_id": self.provenance_source_record_id,
            },
            "temporal": {
                "window_open": self.validity_window_open,
                "expired": self.validity_window_expired,
                "valid": self.validity_window_valid,
            },
            "field_integrity": {"contamination": self.field_contamination},
            "evidence": {
                "required_fact_count": self.required_fact_count,
                "absent_fact_count": self.absent_fact_count,
                "completeness": round(self.evidence_completeness, 4),
            },
            "policy": {
                "policy_id": self.policy_id,
                "version": self.policy_version,
                "effective_time": self.policy_effective_time,
                "firing_predicates": list(self.firing_predicates),
            },
            "dependency": {
                "subject_scoped_keys": list(self.dependency_keys),
                "shared_reference_keys": list(self.shared_reference_keys),
                "coarse_keys": list(self.coarse_dependency_keys),
            },
            "severe_classes": list(self.severe_classes()),
            "injected_classes": list(self.injected_classes),
        }


def derive_witness(task: dict[str, Any], manifest: dict[str, Any]) -> WitnessBundle:
    """Build the grounding state for one task from its corruption manifest.

    The reference action in ``manifest["reference_action"]`` is deliberately not
    read. Only the corruption record is consulted, which is the information a
    deployed grounding state would hold about the record's provenance and
    integrity.
    """

    family = manifest["family"]
    corruption = manifest.get("corruption", {})
    task_id = manifest["task_id"]
    evidence_ids = tuple(ref["ref_id"] for ref in task["evidence_refs"])
    source_ids = {ref.get("source_record_id") for ref in task["evidence_refs"]}
    witness = WitnessBundle(
        task_id=task_id,
        family=family,
        available_evidence_ref_ids=evidence_ids,
        provenance_source_record_id=next(iter(sorted(i for i in source_ids if i)), None),
        dependency_keys=tuple(
            sorted(
                {
                    f"source:{ref['source_record_id']}"
                    for ref in task["evidence_refs"]
                    if ref["table"] not in SHARED_REFERENCE_TABLES
                }
                | {
                    f"row:{ref['table']}:{ref['row_id']}"
                    for ref in task["evidence_refs"]
                    if ref["table"] not in SHARED_REFERENCE_TABLES
                }
            )
        ),
        shared_reference_keys=tuple(
            sorted(
                f"ref:{ref['table']}:{ref['row_id']}"
                for ref in task["evidence_refs"]
                if ref["table"] in SHARED_REFERENCE_TABLES
            )
        ),
        coarse_dependency_keys=(f"family:{family}",)
        + tuple(sorted({f"slice:{s}" for s in task["failure_slices"]})),
    )

    # Graded, advisory demographic similarity. Present on every record, and per
    # Boundary 1 it must never be allowed to override an ambiguity finding.
    witness.identity_match_score = 0.55 + 0.45 * _unit(task_id, "similarity")

    if family == "patient_identity_normalization":
        mismatched = list(corruption.get("corrupted_identity_fields", []))
        witness.identity_mismatched_field_count = len(mismatched)
        if not mismatched:
            witness.identity_status = "accepted"
        elif len(mismatched) == 1 and "SSN" not in mismatched:
            witness.identity_status = "ambiguous"
        else:
            witness.identity_status = "unresolvable"
    elif family == "orphan_duplicate_detection":
        condition = corruption.get("resolution_condition")
        if condition == "unique":
            witness.identity_status = "accepted"
            witness.identity_candidate_count = 1
        elif condition == "duplicate":
            witness.identity_status = "ambiguous"
            witness.identity_candidate_count = 2
        else:
            witness.identity_status = "unresolvable"
            witness.identity_candidate_count = 0
    elif family == "field_anomaly_bleed":
        condition = corruption.get("bleed_condition", "clean")
        witness.field_contamination = {
            "clean": "clean",
            "partial_bleed": "partial",
            "full_bleed": "full",
        }[condition]
    elif family == "code_system_version_validation":
        condition = corruption.get("version_condition")
        witness.declared_code_version = str(corruption.get("code_version", "current"))
        if condition == "supported_icd10":
            witness.code_resolvable = True
            witness.code_superseded = False
        elif condition == "superseded_icd9":
            witness.code_resolvable = True
            witness.code_superseded = True
        else:
            witness.code_resolvable = False
            witness.code_superseded = True
    elif family == "rpms_to_fhir_mapping":
        witness.provenance_signature_present = (
            corruption.get("mapping_condition") == "mapped_with_provenance"
        )
    elif family == "temporal_status_classification":
        # The authoritative status field determines the window; conflicting cues
        # do not expire it. An INACTIVE/RESOLVED record has a closed window and is
        # historical-only, which is admissible, not severe.
        status = str(corruption.get("status", "ACTIVE")).upper()
        witness.validity_window_open = status == "ACTIVE"
        witness.validity_window_expired = False
        witness.validity_window_valid = True
    elif family == "evidence_sufficiency":
        absent = int(corruption.get("withheld_fact_count", 0))
        witness.required_fact_count = 5
        witness.absent_fact_count = absent
        witness.evidence_completeness = max(0.0, 1.0 - absent / 5.0)
    elif family == "policy_action_selection":
        witness.firing_predicates = tuple(corruption.get("firing_predicates", []))

    return witness


def derive_witnesses(
    tasks: list[dict[str, Any]], manifests: list[dict[str, Any]]
) -> list[WitnessBundle]:
    return [derive_witness(task, manifest) for task, manifest in zip(tasks, manifests)]
