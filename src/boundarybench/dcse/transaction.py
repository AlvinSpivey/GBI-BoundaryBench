"""Atomicity and rollback conformance, Appendix B.1 Systems Validation item 3.

    "Inject a corrupted medication order nested within a multi-resource FHIR
    transaction bundle. Verify that the target FHIR gateway rejects the transaction
    atomically and returns an appropriate OperationOutcome; capture the failed
    attempt in the deployment's audit/provenance path according to policy.
    Unrelated resources outside the submitted transaction should remain unchanged."

Section 7.3 and Section 9.2 add the constraint that makes this non-trivial:

    "Stalk-level quarantine is applied before constructing that atomic transaction,
    or across independently scoped transactions."
    "Localized quarantine is a pre-commit work-item mechanism, not permission to
    partially commit an operation whose underlying system requires atomicity."

So there are two claims in tension, and both are tested:

* **Atomicity.** A transaction bundle with one bad entry commits *nothing*.
* **Liveness.** Independent verified work still progresses, via a separately
  scoped transaction — not by partially committing the failed one.

The failure mode a naive implementation falls into is satisfying liveness by
partially committing. The store is snapshotted and diffed to rule that out
directly rather than trusting a return code.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

from boundarybench.dcse.crypto import digest

TRANSACTION_VERSION = "dcse-transaction-v3.0"

BUNDLE_TRANSACTION = "transaction"
BUNDLE_BATCH = "batch"


@dataclass(frozen=True)
class ResourceEntry:
    resource_type: str
    resource_id: str
    content: dict[str, Any]
    subject: str
    admissible: bool
    refusal_reason: str | None = None

    def key(self) -> str:
        return f"{self.resource_type}/{self.resource_id}"


@dataclass
class ResourceStore:
    """A minimal versioned resource store standing in for the FHIR server."""

    resources: dict[str, dict[str, Any]] = field(default_factory=dict)

    def snapshot(self) -> str:
        return digest(
            {key: value for key, value in sorted(self.resources.items())}
        )

    def state(self) -> dict[str, Any]:
        return {key: dict(value) for key, value in sorted(self.resources.items())}

    def apply(self, entries: Sequence[ResourceEntry]) -> None:
        for entry in entries:
            existing = self.resources.get(entry.key())
            version = 1 if existing is None else int(existing["version"]) + 1
            self.resources[entry.key()] = {"version": version, "content": dict(entry.content)}


@dataclass
class Bundle:
    bundle_type: str
    entries: list[ResourceEntry]

    def as_dict(self) -> dict[str, Any]:
        return {
            "type": self.bundle_type,
            "entry_count": len(self.entries),
            "entries": [entry.key() for entry in self.entries],
        }


def operation_outcome(severity: str, code: str, diagnostics: str, expression: Sequence[str] = ()) -> dict[str, Any]:
    """A FHIR-shaped OperationOutcome."""

    return {
        "resourceType": "OperationOutcome",
        "issue": [
            {
                "severity": severity,
                "code": code,
                "diagnostics": diagnostics,
                "expression": list(expression),
            }
        ],
    }


@dataclass
class TransactionAssembler:
    """Applies quarantine before constructing the atomic bundle."""

    allow_separately_scoped: bool = True

    def assemble(self, candidates: Sequence[ResourceEntry]) -> dict[str, Any]:
        admissible = [entry for entry in candidates if entry.admissible]
        quarantined = [entry for entry in candidates if not entry.admissible]

        # Dependency scoping: a subject with any refused entry has its whole
        # subject scope held back, because an atomic bundle spanning that subject
        # cannot be partially committed.
        refused_subjects = {entry.subject for entry in quarantined}
        held_back = [entry for entry in admissible if entry.subject in refused_subjects]
        clean = [entry for entry in admissible if entry.subject not in refused_subjects]

        primary = Bundle(BUNDLE_TRANSACTION, clean) if clean else None
        separate = None
        if self.allow_separately_scoped and held_back:
            # Held-back work is routed to its own scope, not merged into the
            # primary transaction and not partially committed.
            separate = Bundle(BUNDLE_TRANSACTION, held_back)
        return {
            "primary_transaction": primary,
            "separately_scoped_transaction": separate,
            "quarantined_entries": quarantined,
            "quarantine_applied_before_construction": True,
            "quarantined_keys": [entry.key() for entry in quarantined],
            "held_back_keys": [entry.key() for entry in held_back],
        }


@dataclass
class FhirGateway:
    """Rejects a transaction bundle atomically if any entry fails validation."""

    store: ResourceStore
    audit: list[dict[str, Any]] = field(default_factory=list)

    def validate(self, entry: ResourceEntry) -> str | None:
        if not entry.admissible:
            return entry.refusal_reason or "entry_inadmissible"
        if entry.resource_type == "MedicationRequest":
            if entry.content.get("status") not in {"active", "completed", "on-hold"}:
                return "medication_request_status_invalid"
            if not entry.content.get("subject"):
                return "medication_request_missing_subject"
        if not isinstance(entry.content, dict) or not entry.content:
            return "empty_resource_body"
        return None

    def submit(self, bundle: Bundle) -> dict[str, Any]:
        before = self.store.snapshot()
        before_state = self.store.state()
        problems = [
            {"entry": entry.key(), "reason": reason}
            for entry in bundle.entries
            if (reason := self.validate(entry)) is not None
        ]

        if bundle.bundle_type == BUNDLE_TRANSACTION and problems:
            outcome = operation_outcome(
                "error",
                "business-rule",
                "Transaction rejected atomically; no resource was created or updated.",
                [problem["entry"] for problem in problems],
            )
            record = {
                "kind": "AuditEvent",
                "action": "transaction_rejected",
                "bundle": bundle.as_dict(),
                "problems": problems,
                "outcome": "4",  # FHIR AuditEvent minor failure
                "store_digest_before": before,
                "store_digest_after": self.store.snapshot(),
            }
            self.audit.append(record)
            return {
                "committed": False,
                "atomic": True,
                "operation_outcome": outcome,
                "problems": problems,
                "store_unchanged": self.store.snapshot() == before,
                "store_state_identical": self.store.state() == before_state,
                "audit_event_recorded": True,
            }

        if bundle.bundle_type == BUNDLE_TRANSACTION:
            self.store.apply(bundle.entries)
            self.audit.append(
                {
                    "kind": "AuditEvent",
                    "action": "transaction_committed",
                    "bundle": bundle.as_dict(),
                    "outcome": "0",
                    "store_digest_before": before,
                    "store_digest_after": self.store.snapshot(),
                }
            )
            return {
                "committed": True,
                "atomic": True,
                "operation_outcome": operation_outcome(
                    "information", "informational", "Transaction committed."
                ),
                "problems": [],
                "committed_keys": [entry.key() for entry in bundle.entries],
                "audit_event_recorded": True,
            }

        # Batch semantics: entries are independent.
        good = [entry for entry in bundle.entries if self.validate(entry) is None]
        self.store.apply(good)
        self.audit.append(
            {
                "kind": "AuditEvent",
                "action": "batch_processed",
                "bundle": bundle.as_dict(),
                "outcome": "0" if not problems else "4",
                "store_digest_before": before,
                "store_digest_after": self.store.snapshot(),
            }
        )
        return {
            "committed": bool(good),
            "atomic": False,
            "operation_outcome": operation_outcome(
                "warning" if problems else "information",
                "processing" if problems else "informational",
                "Batch processed; entries are independent.",
            ),
            "problems": problems,
            "committed_keys": [entry.key() for entry in good],
            "audit_event_recorded": True,
        }


def run_rollback_conformance_suite() -> dict[str, Any]:
    """The B.1 rollback-conformance protocol, executed."""

    store = ResourceStore()
    # Pre-existing, unrelated resources that must not be touched.
    unrelated = [
        ResourceEntry("Patient", "9001", {"name": "unrelated-a"}, "patient-9001", True),
        ResourceEntry("Observation", "7001", {"value": 5.2}, "patient-9001", True),
    ]
    store.apply(unrelated)
    baseline_state = store.state()
    baseline_digest = store.snapshot()

    gateway = FhirGateway(store=store)
    assembler = TransactionAssembler()

    # A multi-resource bundle for one subject with a corrupted medication order
    # nested inside it, plus verified work for a different subject.
    candidates = [
        ResourceEntry("Patient", "1001", {"name": "subject-a"}, "patient-1001", True),
        ResourceEntry("Condition", "2001", {"code": "E11.9"}, "patient-1001", True),
        ResourceEntry(
            "MedicationRequest",
            "3001",
            {"status": "CORRUPTED", "subject": None},
            "patient-1001",
            False,
            "medication_request_status_invalid",
        ),
        ResourceEntry("Observation", "4001", {"value": 7.1}, "patient-1001", True),
        # Independent, fully verified work for another subject.
        ResourceEntry("Patient", "1002", {"name": "subject-b"}, "patient-1002", True),
        ResourceEntry("Condition", "2002", {"code": "I10"}, "patient-1002", True),
    ]

    assembled = assembler.assemble(candidates)
    primary_result = (
        gateway.submit(assembled["primary_transaction"])
        if assembled["primary_transaction"]
        else None
    )
    separate_result = (
        gateway.submit(assembled["separately_scoped_transaction"])
        if assembled["separately_scoped_transaction"]
        else None
    )

    # Now the direct B.1 protocol: submit the corrupted order *inside* an atomic
    # bundle, bypassing pre-construction quarantine, and require atomic rejection.
    forced_bundle = Bundle(
        BUNDLE_TRANSACTION,
        [
            ResourceEntry("Patient", "1003", {"name": "subject-c"}, "patient-1003", True),
            ResourceEntry("Condition", "2003", {"code": "J45.909"}, "patient-1003", True),
            ResourceEntry(
                "MedicationRequest",
                "3003",
                {"status": "CORRUPTED", "subject": None},
                "patient-1003",
                True,  # asserted admissible by an upstream that got it wrong
            ),
            ResourceEntry("Observation", "4003", {"value": 3.3}, "patient-1003", True),
        ],
    )
    pre_forced_state = store.state()
    forced_result = gateway.submit(forced_bundle)
    post_forced_state = store.state()

    unrelated_keys = {entry.key() for entry in unrelated}
    unrelated_unchanged = all(
        baseline_state[key] == post_forced_state.get(key) for key in unrelated_keys
    )
    no_partial_commit = all(
        entry.key() not in post_forced_state for entry in forced_bundle.entries
    )

    return {
        "schema_version": "boundarybench.dcse_rollback_conformance.v1",
        "transaction_version": TRANSACTION_VERSION,
        "baseline_store_digest": baseline_digest,
        "pre_construction_quarantine": {
            "quarantined_keys": assembled["quarantined_keys"],
            "held_back_keys": assembled["held_back_keys"],
            "quarantine_applied_before_construction": assembled[
                "quarantine_applied_before_construction"
            ],
            "primary_transaction": assembled["primary_transaction"].as_dict()
            if assembled["primary_transaction"]
            else None,
            "separately_scoped_transaction": assembled["separately_scoped_transaction"].as_dict()
            if assembled["separately_scoped_transaction"]
            else None,
        },
        "primary_transaction_result": primary_result,
        "separately_scoped_result": separate_result,
        "independent_work_progressed": bool(primary_result and primary_result["committed"]),
        "held_back_work_not_silently_dropped": assembled["separately_scoped_transaction"] is not None,
        "forced_atomic_submission": {
            "committed": forced_result["committed"],
            "atomic": forced_result["atomic"],
            "operation_outcome": forced_result["operation_outcome"],
            "problems": forced_result["problems"],
            "store_unchanged": forced_result["store_unchanged"],
            "store_state_identical": forced_result["store_state_identical"],
            "audit_event_recorded": forced_result["audit_event_recorded"],
        },
        "no_partial_commit_from_rejected_bundle": no_partial_commit,
        "unrelated_resources_unchanged": unrelated_unchanged,
        "operation_outcome_severity_is_error": (
            forced_result["operation_outcome"]["issue"][0]["severity"] == "error"
        ),
        "operation_outcome_code_is_business_rule": (
            forced_result["operation_outcome"]["issue"][0]["code"] == "business-rule"
        ),
        "audit_trail_entries": len(gateway.audit),
        "audit_trail": gateway.audit,
        "rollback_conformance_holds": bool(
            not forced_result["committed"]
            and forced_result["store_state_identical"]
            and no_partial_commit
            and unrelated_unchanged
            and forced_result["audit_event_recorded"]
            and forced_result["operation_outcome"]["issue"][0]["severity"] == "error"
        ),
        "atomicity_and_liveness_both_hold": bool(
            not forced_result["committed"]
            and no_partial_commit
            and primary_result
            and primary_result["committed"]
        ),
        "scope": (
            "A conforming in-process gateway model, not a production FHIR server. "
            "It exercises the atomicity contract and the pre-construction quarantine "
            "rule; it does not certify any vendor's server."
        ),
    }
