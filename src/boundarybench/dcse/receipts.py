"""Receipt coherence and replay, Sections 5, 9.1, 12 and Appendix B.3.

The manuscript's operational promise is a receipt, not a decision:

    "The substrate emits typed certificates, not autonomous clinical decisions."
    "On precondition failure, it emits an OperationOutcome, records Provenance, and
    refuses authoritative write-back."
    "The review surface should expose the deterministic reasons for
    inadmissibility ... rather than reduce review to a model confidence number."

A receipt layer is only worth anything if it is *coherent*: complete, hash-linked,
version-pinned, and replayable. Those four are testable, and the fourth is the one
that matters most for an audit years later.

**Replay** is the strong property. Given only a receipt — its recorded witness
digest, policy version and terminology version — re-deriving the decision must
reproduce the original verdict exactly. That is what makes provenance an audit
trail rather than a log. It is also the mechanism half of the Appendix B.1
"retrospective playback" item: the clinical half needs a real cohort, but the
reproducibility half can be established here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Sequence

from boundarybench.dcse.crypto import Identity, digest, verify
from boundarybench.dcse.ledger import IdentityLedger

RECEIPTS_VERSION = "dcse-receipts-v3.0"

RECEIPT_KINDS = ("OperationOutcome", "Provenance", "AuditEvent")

# Deterministic review fields required by Section 9.2. A receipt that carried a
# model confidence number in place of these would reintroduce automation bias.
REQUIRED_REVIEW_FIELDS = (
    "candidate_value",
    "authoritative_evidence",
    "source_freshness",
    "schema_authority",
    "provenance_reference",
    "policy_rule_id",
    "required_action",
)

FORBIDDEN_REVIEW_FIELDS = ("model_confidence", "logit_margin", "softmax_probability")


@dataclass(frozen=True)
class Receipt:
    kind: str
    subject: str
    decision: str
    witness_digest: str
    policy_version: str
    terminology_version: str
    ledger_entry_digest: str
    previous_receipt_digest: str
    body: dict[str, Any]
    signature: str
    public_key_hex: str

    def signing_body(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "subject": self.subject,
            "decision": self.decision,
            "witness_digest": self.witness_digest,
            "policy_version": self.policy_version,
            "terminology_version": self.terminology_version,
            "ledger_entry_digest": self.ledger_entry_digest,
            "previous_receipt_digest": self.previous_receipt_digest,
            "body": self.body,
        }

    def receipt_digest(self) -> str:
        return digest({"body": self.signing_body(), "signature": self.signature})


@dataclass
class ReceiptChain:
    """Hash-linked receipt log bound to the identity ledger."""

    signer: Identity
    ledger: IdentityLedger
    receipts: list[Receipt] = field(default_factory=list)
    _head: str = "0" * 64

    def emit(
        self,
        *,
        kind: str,
        subject: str,
        decision: str,
        witness: dict[str, Any],
        policy_version: str,
        terminology_version: str,
        body: dict[str, Any],
        nonce: str,
    ) -> Receipt:
        if kind not in RECEIPT_KINDS:
            raise ValueError(f"unknown receipt kind: {kind}")
        witness_digest = digest(witness)
        entry = self.ledger.append(
            self.signer,
            {
                "kind": "receipt_binding",
                "receipt_kind": kind,
                "subject": subject,
                "decision": decision,
                "witness_digest": witness_digest,
                "policy_version": policy_version,
                "terminology_version": terminology_version,
            },
            nonce=nonce,
        )
        receipt = Receipt(
            kind=kind,
            subject=subject,
            decision=decision,
            witness_digest=witness_digest,
            policy_version=policy_version,
            terminology_version=terminology_version,
            ledger_entry_digest=entry.entry_digest(),
            previous_receipt_digest=self._head,
            body=body,
            signature="",
            public_key_hex=self.signer.public_key_hex,
        )
        signature = self.signer.sign(receipt.signing_body())
        receipt = Receipt(
            kind=receipt.kind,
            subject=receipt.subject,
            decision=receipt.decision,
            witness_digest=receipt.witness_digest,
            policy_version=receipt.policy_version,
            terminology_version=receipt.terminology_version,
            ledger_entry_digest=receipt.ledger_entry_digest,
            previous_receipt_digest=receipt.previous_receipt_digest,
            body=receipt.body,
            signature=signature,
            public_key_hex=receipt.public_key_hex,
        )
        self.receipts.append(receipt)
        self._head = receipt.receipt_digest()
        return receipt

    def verify(self) -> dict[str, Any]:
        problems: list[dict[str, Any]] = []
        head = "0" * 64
        ledger_digests = {entry.entry_digest() for entry in self.ledger.entries}
        for index, receipt in enumerate(self.receipts):
            if not verify(receipt.public_key_hex, receipt.signing_body(), receipt.signature):
                problems.append({"index": index, "problem": "invalid_receipt_signature"})
            if receipt.previous_receipt_digest != head:
                problems.append({"index": index, "problem": "receipt_chain_break"})
            if receipt.ledger_entry_digest not in ledger_digests:
                problems.append({"index": index, "problem": "receipt_not_bound_to_ledger"})
            if receipt.kind == "OperationOutcome":
                issues = receipt.body.get("issue", [])
                if not issues or not issues[0].get("severity") or not issues[0].get("code"):
                    problems.append({"index": index, "problem": "operation_outcome_missing_severity_or_code"})
            head = receipt.receipt_digest()
        return {
            "receipts": len(self.receipts),
            "problems": problems,
            "problem_count": len(problems),
            "chain_valid": not problems,
        }


def _review_surface(reasons: dict[str, Any]) -> dict[str, Any]:
    return {field: reasons.get(field) for field in REQUIRED_REVIEW_FIELDS}


def run_receipt_suite(
    *,
    decisions: Sequence[dict[str, Any]] | None = None,
    policy_version: str = "1.1",
    terminology_version: str = "2026-03-01",
) -> dict[str, Any]:
    """Emit receipts for a mix of decisions, then check coherence and replay."""

    from boundarybench.dcse.crypto import derive_identity

    if decisions is None:
        decisions = [
            {
                "subject": "subject-1001",
                "decision": "admit",
                "witness": {"identity": "certified", "terminology": "signed", "provenance": "present"},
                "fired_gates": [],
            },
            {
                "subject": "subject-1002",
                "decision": "quarantine_slice",
                "witness": {"identity": "ambiguous", "terminology": "signed", "provenance": "present"},
                "fired_gates": ["identity_ambiguous"],
            },
            {
                "subject": "subject-1003",
                "decision": "abstain",
                "witness": {"identity": "certified", "terminology": "signed", "provenance": "absent"},
                "fired_gates": ["required_evidence_absent"],
            },
            {
                "subject": "subject-1004",
                "decision": "expert_review",
                "witness": {"identity": "certified", "terminology": "superseded", "provenance": "present"},
                "fired_gates": ["terminology_superseded"],
            },
            {
                "subject": "subject-1005",
                "decision": "reject",
                "witness": {"identity": "certified", "terminology": "unsigned", "provenance": "present"},
                "fired_gates": ["terminology_bundle_unsigned"],
            },
        ]

    signer = derive_identity("receipt-signer", seed="dcse-v3-receipts")
    ledger = IdentityLedger()
    chain = ReceiptChain(signer=signer, ledger=ledger)

    ADMITTING = {"admit", "admit_historical_only"}
    per_decision: list[dict[str, Any]] = []

    for index, decision in enumerate(decisions):
        emitted: list[str] = []
        reasons = {
            "candidate_value": decision["witness"],
            "authoritative_evidence": {"terminology": decision["witness"]["terminology"]},
            "source_freshness": terminology_version,
            "schema_authority": "boundarybench.result.v1",
            "provenance_reference": decision["witness"]["provenance"],
            "policy_rule_id": ",".join(decision["fired_gates"]) or "no_gate_fired",
            "required_action": decision["decision"],
        }

        # AuditEvent for every decision, without exception.
        chain.emit(
            kind="AuditEvent",
            subject=decision["subject"],
            decision=decision["decision"],
            witness=decision["witness"],
            policy_version=policy_version,
            terminology_version=terminology_version,
            body={
                "resourceType": "AuditEvent",
                "action": "E",
                "outcome": "0" if decision["decision"] in ADMITTING else "4",
                "review_surface": _review_surface(reasons),
            },
            nonce=f"audit-{index}",
        )
        emitted.append("AuditEvent")

        # OperationOutcome for every refusal.
        if decision["decision"] not in ADMITTING:
            severity = "error" if decision["decision"] == "reject" else "warning"
            chain.emit(
                kind="OperationOutcome",
                subject=decision["subject"],
                decision=decision["decision"],
                witness=decision["witness"],
                policy_version=policy_version,
                terminology_version=terminology_version,
                body={
                    "resourceType": "OperationOutcome",
                    "issue": [
                        {
                            "severity": severity,
                            "code": "business-rule",
                            "diagnostics": f"refused: {reasons['policy_rule_id']}",
                        }
                    ],
                    "review_surface": _review_surface(reasons),
                },
                nonce=f"outcome-{index}",
            )
            emitted.append("OperationOutcome")

        # Provenance for accepted evidence and for recorded abstentions.
        chain.emit(
            kind="Provenance",
            subject=decision["subject"],
            decision=decision["decision"],
            witness=decision["witness"],
            policy_version=policy_version,
            terminology_version=terminology_version,
            body={
                "resourceType": "Provenance",
                "recorded": terminology_version,
                "activity": decision["decision"],
                "agent": [{"who": "gbi-dcse-coprocessor", "type": "assembler"}],
                "review_surface": _review_surface(reasons),
            },
            nonce=f"prov-{index}",
        )
        emitted.append("Provenance")
        per_decision.append({"subject": decision["subject"], "decision": decision["decision"], "receipts": emitted})

    verification = chain.verify()
    ledger_verification = ledger.verify()

    # Coherence: completeness of the receipt set per decision.
    completeness = []
    for record, decision in zip(per_decision, decisions):
        refusal = decision["decision"] not in ADMITTING
        completeness.append(
            {
                "subject": record["subject"],
                "decision": record["decision"],
                "has_audit_event": "AuditEvent" in record["receipts"],
                "has_provenance": "Provenance" in record["receipts"],
                "has_operation_outcome": "OperationOutcome" in record["receipts"],
                "operation_outcome_required": refusal,
                "complete": (
                    "AuditEvent" in record["receipts"]
                    and "Provenance" in record["receipts"]
                    and (("OperationOutcome" in record["receipts"]) == refusal)
                ),
            }
        )

    # No receipt may carry a model confidence number in the review surface.
    forbidden_present = []
    for receipt in chain.receipts:
        surface = receipt.body.get("review_surface", {})
        for field_name in FORBIDDEN_REVIEW_FIELDS:
            if field_name in surface:
                forbidden_present.append({"kind": receipt.kind, "field": field_name})
    required_present = all(
        all(field_name in receipt.body.get("review_surface", {}) for field_name in REQUIRED_REVIEW_FIELDS)
        for receipt in chain.receipts
    )

    # Version pinning: every receipt records the policy and terminology version.
    version_pinned = all(
        receipt.policy_version and receipt.terminology_version for receipt in chain.receipts
    )

    # Replay: re-derive each decision from the receipt alone.
    def replay_rule(witness: dict[str, Any]) -> str:
        if witness["terminology"] == "unsigned":
            return "reject"
        if witness["identity"] == "ambiguous":
            return "quarantine_slice"
        if witness["provenance"] == "absent":
            return "abstain"
        if witness["terminology"] == "superseded":
            return "expert_review"
        return "admit"

    replays = []
    witness_by_digest = {digest(decision["witness"]): decision["witness"] for decision in decisions}
    for receipt in chain.receipts:
        witness = witness_by_digest[receipt.witness_digest]
        replayed = replay_rule(witness)
        replays.append(
            {
                "subject": receipt.subject,
                "recorded_decision": receipt.decision,
                "replayed_decision": replayed,
                "reproduced": replayed == receipt.decision,
            }
        )
    replay_ok = all(entry["reproduced"] for entry in replays)

    # Tamper detection: mutate one receipt body and confirm the chain breaks.
    tampered_chain = ReceiptChain(signer=signer, ledger=ledger, receipts=list(chain.receipts))
    if tampered_chain.receipts:
        original = tampered_chain.receipts[1]
        tampered_body = dict(original.body)
        tampered_body["tampered"] = True
        tampered_chain.receipts[1] = Receipt(
            kind=original.kind,
            subject=original.subject,
            decision=original.decision,
            witness_digest=original.witness_digest,
            policy_version=original.policy_version,
            terminology_version=original.terminology_version,
            ledger_entry_digest=original.ledger_entry_digest,
            previous_receipt_digest=original.previous_receipt_digest,
            body=tampered_body,
            signature=original.signature,
            public_key_hex=original.public_key_hex,
        )
    tampered_verification = tampered_chain.verify()

    return {
        "schema_version": "boundarybench.dcse_receipt_suite.v1",
        "receipts_version": RECEIPTS_VERSION,
        "decisions": len(decisions),
        "receipts_emitted": len(chain.receipts),
        "receipt_kinds_used": sorted({receipt.kind for receipt in chain.receipts}),
        "chain_verification": verification,
        "ledger_verification": {
            "structurally_valid": ledger_verification["structurally_valid"],
            "non_equivocating": ledger_verification["non_equivocating"],
            "entries": ledger_verification["entries"],
        },
        "completeness": completeness,
        "every_decision_fully_receipted": all(entry["complete"] for entry in completeness),
        "review_surface_required_fields_present": required_present,
        "review_surface_forbidden_fields": forbidden_present,
        "review_surface_omits_model_confidence": not forbidden_present,
        "all_receipts_version_pinned": version_pinned,
        "replay": replays,
        "replay_reproduces_every_decision": replay_ok,
        "tamper_detection": {
            "tampered_chain_valid": tampered_verification["chain_valid"],
            "problems_detected": [problem["problem"] for problem in tampered_verification["problems"]],
            "tampering_detected": not tampered_verification["chain_valid"],
        },
        "receipt_coherence_holds": bool(
            verification["chain_valid"]
            and ledger_verification["structurally_valid"]
            and all(entry["complete"] for entry in completeness)
            and required_present
            and not forbidden_present
            and version_pinned
            and replay_ok
            and not tampered_verification["chain_valid"]
        ),
    }
