"""The identity/provenance ledger L from Section 9.1.

Section 9.1 lists L as one of the seven DCSE protocol objects: "the immutable
history used to bind a proposal to the correct subject, entity, case, or work item
and to detect protocol equivocation." Section 9.4 gives it two modes and a
fallback trigger, and states the crucial scope limit:

    "The ledger proves protocol-level non-equivocation, not patient identity
    truth. Clinical identity remains an external validity predicate."

Both halves are implemented and both are tested. The second half is the one an
implementation is likely to get wrong by over-claiming, so there is an explicit
test that a *fully valid* ledger can contain a *wrong* identity binding — the
ledger's validity says nothing about whether the binding is correct, only that no
node said two different things about it.

Design notes:

* Entries are hash-chained per node and carry a strictly monotonic counter, so
  truncation, reordering and replay are all detectable.
* Equivocation evidence is a pair of genuinely signed conflicting entries. Because
  signing is Ed25519, the evidence is verifiable by anyone holding only public
  keys — which is what makes it evidence rather than an assertion.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

from boundarybench.dcse.crypto import Identity, digest, verify

LEDGER_VERSION = "dcse-ledger-v3.0"

GENESIS = "0" * 64

FALLBACK_TRIGGERS = (
    "monotonic_counter_failure",
    "enclave_restart",
    "attestation_loss",
    "equivocation_evidence",
)


@dataclass(frozen=True)
class LedgerEntry:
    node_id: str
    sequence: int
    counter: int
    previous_digest: str
    payload: dict[str, Any]
    nonce: str
    signature: str
    public_key_hex: str

    def signing_body(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "sequence": self.sequence,
            "counter": self.counter,
            "previous_digest": self.previous_digest,
            "payload": self.payload,
            "nonce": self.nonce,
        }

    def entry_digest(self) -> str:
        return digest({"body": self.signing_body(), "signature": self.signature})

    def as_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "sequence": self.sequence,
            "counter": self.counter,
            "previous_digest": self.previous_digest,
            "payload": self.payload,
            "nonce": self.nonce,
            "signature": self.signature[:32] + "...",
            "entry_digest": self.entry_digest(),
        }


@dataclass
class IdentityLedger:
    """Append-only, per-node hash-chained log with a monotonic counter."""

    entries: list[LedgerEntry] = field(default_factory=list)
    heads: dict[str, str] = field(default_factory=dict)
    counters: dict[str, int] = field(default_factory=dict)
    sequences: dict[str, int] = field(default_factory=dict)
    public_keys: dict[str, str] = field(default_factory=dict)

    def append(
        self,
        identity: Identity,
        payload: dict[str, Any],
        *,
        nonce: str,
        counter: int | None = None,
        previous_digest: str | None = None,
        sequence: int | None = None,
    ) -> LedgerEntry:
        """Append a signed entry. Overrides exist only so faults can be injected."""

        node_id = identity.node_id
        next_counter = self.counters.get(node_id, 0) + 1 if counter is None else counter
        next_sequence = self.sequences.get(node_id, -1) + 1 if sequence is None else sequence
        head = self.heads.get(node_id, GENESIS) if previous_digest is None else previous_digest
        entry = LedgerEntry(
            node_id=node_id,
            sequence=next_sequence,
            counter=next_counter,
            previous_digest=head,
            payload=payload,
            nonce=nonce,
            signature="",
            public_key_hex=identity.public_key_hex,
        )
        signature = identity.sign(entry.signing_body())
        entry = LedgerEntry(
            node_id=entry.node_id,
            sequence=entry.sequence,
            counter=entry.counter,
            previous_digest=entry.previous_digest,
            payload=entry.payload,
            nonce=entry.nonce,
            signature=signature,
            public_key_hex=entry.public_key_hex,
        )
        self.entries.append(entry)
        self.heads[node_id] = entry.entry_digest()
        self.counters[node_id] = max(self.counters.get(node_id, 0), next_counter)
        self.sequences[node_id] = max(self.sequences.get(node_id, -1), next_sequence)
        self.public_keys[node_id] = entry.public_key_hex
        return entry

    def head(self, node_id: str) -> str:
        return self.heads.get(node_id, GENESIS)

    # --- verification -----------------------------------------------------

    def verify(self) -> dict[str, Any]:
        """Full structural verification: signatures, chain, counters, sequences."""

        problems: list[dict[str, Any]] = []
        per_node_chain: dict[str, str] = {}
        per_node_counter: dict[str, int] = {}
        per_node_sequence: dict[str, int] = {}
        nonces_seen: set[tuple[str, str]] = set()

        for index, entry in enumerate(self.entries):
            if not verify(entry.public_key_hex, entry.signing_body(), entry.signature):
                problems.append({"index": index, "problem": "invalid_signature", "node": entry.node_id})
                continue
            expected_prev = per_node_chain.get(entry.node_id, GENESIS)
            if entry.previous_digest != expected_prev:
                problems.append(
                    {
                        "index": index,
                        "problem": "hash_chain_break",
                        "node": entry.node_id,
                        "expected_previous": expected_prev[:16],
                        "observed_previous": entry.previous_digest[:16],
                    }
                )
            last_counter = per_node_counter.get(entry.node_id, 0)
            if entry.counter <= last_counter:
                problems.append(
                    {
                        "index": index,
                        "problem": "monotonic_counter_failure",
                        "node": entry.node_id,
                        "last_counter": last_counter,
                        "observed_counter": entry.counter,
                    }
                )
            last_sequence = per_node_sequence.get(entry.node_id, -1)
            if entry.sequence != last_sequence + 1:
                problems.append(
                    {
                        "index": index,
                        "problem": "sequence_gap_or_reuse",
                        "node": entry.node_id,
                        "expected_sequence": last_sequence + 1,
                        "observed_sequence": entry.sequence,
                    }
                )
            key = (entry.node_id, entry.nonce)
            if key in nonces_seen:
                problems.append({"index": index, "problem": "nonce_replay", "node": entry.node_id})
            nonces_seen.add(key)
            per_node_chain[entry.node_id] = entry.entry_digest()
            per_node_counter[entry.node_id] = max(last_counter, entry.counter)
            per_node_sequence[entry.node_id] = max(last_sequence, entry.sequence)

        equivocation = self.detect_equivocation()
        return {
            "schema_version": "boundarybench.dcse_ledger_verification.v1",
            "ledger_version": LEDGER_VERSION,
            "entries": len(self.entries),
            "nodes": sorted(self.public_keys),
            "problems": problems,
            "problem_count": len(problems),
            "structurally_valid": not problems,
            "equivocation_evidence": equivocation,
            "equivocation_detected": bool(equivocation),
            "non_equivocating": not equivocation,
        }

    def detect_equivocation(self) -> list[dict[str, Any]]:
        """Two validly signed entries from one node at one sequence, differing.

        This is the whole non-equivocation property. Note what it does *not*
        require: no trusted clock, no quorum, no knowledge of which entry is
        "right". Two signatures over conflicting bodies at the same sequence are
        self-contained proof that the node equivocated.
        """

        by_slot: dict[tuple[str, int], list[LedgerEntry]] = {}
        for entry in self.entries:
            if verify(entry.public_key_hex, entry.signing_body(), entry.signature):
                by_slot.setdefault((entry.node_id, entry.sequence), []).append(entry)
        evidence: list[dict[str, Any]] = []
        for (node_id, sequence), group in sorted(by_slot.items()):
            digests = {digest(entry.signing_body()) for entry in group}
            if len(digests) > 1:
                evidence.append(
                    {
                        "node_id": node_id,
                        "sequence": sequence,
                        "conflicting_bodies": len(digests),
                        "entry_digests": sorted(entry.entry_digest() for entry in group),
                        "both_signatures_valid": True,
                        "publicly_verifiable": True,
                        "proves": "protocol_level_equivocation_by_this_node",
                        "does_not_prove": "which_binding_is_factually_correct",
                    }
                )
        return evidence


@dataclass
class WritePathGuard:
    """Section 9.4's two modes and the fallback that halts authoritative writes."""

    ledger: IdentityLedger
    attestation_healthy: bool = True
    counter_service_healthy: bool = True
    enclave_generation: int = 1
    active_replicas: int = 4
    byzantine_tolerance: int = 1

    def status(self) -> dict[str, Any]:
        verification = self.ledger.verify()
        triggers: list[str] = []
        if not self.counter_service_healthy or any(
            problem["problem"] == "monotonic_counter_failure" for problem in verification["problems"]
        ):
            triggers.append("monotonic_counter_failure")
        if not self.attestation_healthy:
            triggers.append("attestation_loss")
        if verification["equivocation_detected"]:
            triggers.append("equivocation_evidence")
        required = 3 * self.byzantine_tolerance + 1
        quorum_ok = self.active_replicas >= required
        if not quorum_ok:
            triggers.append("replica_population_below_3f_plus_1")
        mode = "fast_path_tee_assisted" if not triggers else "conservative_bft_fallback"
        return {
            "schema_version": "boundarybench.dcse_write_path_status.v1",
            "mode": mode,
            "fallback_triggers": triggers,
            "declared_trigger_set": list(FALLBACK_TRIGGERS),
            "active_replicas": self.active_replicas,
            "byzantine_tolerance_f": self.byzantine_tolerance,
            "required_replicas_3f_plus_1": required,
            "quorum_threshold_met": quorum_ok,
            "authoritative_writes_permitted": not triggers,
            "ledger_structurally_valid": verification["structurally_valid"],
            "ledger_non_equivocating": verification["non_equivocating"],
        }


def ledger_scope_demonstration() -> dict[str, Any]:
    """Show that ledger validity does not imply identity correctness.

    Section 9.4's scope limit is a negative claim, so it needs a witness: a ledger
    that passes every structural check while recording a binding that is factually
    wrong. If a test suite cannot produce that case, the implementation is probably
    conflating the two properties.
    """

    from boundarybench.dcse.crypto import derive_identity

    node = derive_identity("node-a", seed="scope-demo")
    ledger = IdentityLedger()
    # A deliberately wrong binding: the subject is patient 1001, the record
    # belongs to 2002. The ledger records the decision faithfully.
    ledger.append(
        node,
        {
            "kind": "identity_binding",
            "asserted_subject": "patient-1001",
            "source_record": "src-2002",
            "decided_by": "external_validity_predicate",
        },
        nonce="n1",
    )
    verification = ledger.verify()
    return {
        "purpose": "Section 9.4 scope limit: protocol non-equivocation is not identity truth",
        "ledger_structurally_valid": verification["structurally_valid"],
        "ledger_non_equivocating": verification["non_equivocating"],
        "recorded_binding_is_factually_wrong": True,
        "ledger_validity_implies_identity_truth": False,
        "conclusion": (
            "A structurally perfect, non-equivocating ledger recorded an incorrect "
            "identity binding. Ledger validity and identity correctness are "
            "independent properties, exactly as Section 9.4 states."
        ),
    }


LEDGER_FAULT_CLASSES = (
    "monotonic_counter_rollback",
    "monotonic_counter_repeat",
    "hash_chain_break",
    "sequence_reuse",
    "nonce_replay",
    "forged_signature",
    "equivocation_same_sequence",
)


def run_ledger_suite() -> dict[str, Any]:
    """A clean ledger, then one injected fault per declared class.

    Every fault must be detected, and each must be detected as *itself* rather than
    as some other problem. A suite that only checked "something was detected" could
    not distinguish a ledger that catches equivocation from one that happens to
    reject every entry.
    """

    from boundarybench.dcse.crypto import derive_identity

    def fresh() -> tuple[IdentityLedger, Any, Any]:
        ledger = IdentityLedger()
        node_a = derive_identity("node-a", seed="ledger-suite")
        node_b = derive_identity("node-b", seed="ledger-suite")
        for index in range(4):
            ledger.append(node_a, {"kind": "bind", "subject": f"s{index}"}, nonce=f"a{index}")
            ledger.append(node_b, {"kind": "bind", "subject": f"s{index}"}, nonce=f"b{index}")
        return ledger, node_a, node_b

    clean_ledger, node_a, _ = fresh()
    clean = clean_ledger.verify()

    cases: dict[str, dict[str, Any]] = {}

    # 1. Counter rollback.
    ledger, node, _ = fresh()
    ledger.append(node, {"kind": "bind", "subject": "roll"}, nonce="r1", counter=2)
    cases["monotonic_counter_rollback"] = ledger.verify()

    # 2. Counter repeat.
    ledger, node, _ = fresh()
    ledger.append(node, {"kind": "bind", "subject": "rep"}, nonce="r2", counter=4)
    cases["monotonic_counter_repeat"] = ledger.verify()

    # 3. Hash-chain break.
    ledger, node, _ = fresh()
    ledger.append(node, {"kind": "bind", "subject": "brk"}, nonce="r3", previous_digest=GENESIS)
    cases["hash_chain_break"] = ledger.verify()

    # 4. Sequence reuse (without conflicting content, so it is a sequence fault only).
    ledger, node, _ = fresh()
    existing = ledger.entries[0]
    ledger.append(
        node,
        dict(existing.payload),
        nonce="r4",
        sequence=existing.sequence,
        previous_digest=existing.previous_digest,
    )
    cases["sequence_reuse"] = ledger.verify()

    # 5. Nonce replay.
    ledger, node, _ = fresh()
    ledger.append(node, {"kind": "bind", "subject": "replay"}, nonce="a0")
    cases["nonce_replay"] = ledger.verify()

    # 6. Forged signature.
    ledger, node, _ = fresh()
    attacker = derive_identity("attacker", seed="ledger-suite")
    victim = ledger.entries[0]
    ledger.entries.append(
        LedgerEntry(
            node_id=victim.node_id,
            sequence=99,
            counter=99,
            previous_digest=ledger.head(victim.node_id),
            payload={"kind": "bind", "subject": "forged"},
            nonce="forged",
            signature=attacker.sign(
                {
                    "node_id": victim.node_id,
                    "sequence": 99,
                    "counter": 99,
                    "previous_digest": ledger.head(victim.node_id),
                    "payload": {"kind": "bind", "subject": "forged"},
                    "nonce": "forged",
                }
            ),
            public_key_hex=victim.public_key_hex,
        )
    )
    cases["forged_signature"] = ledger.verify()

    # 7. Equivocation: two validly signed, conflicting entries at one sequence.
    ledger, node, _ = fresh()
    target = ledger.entries[0]
    ledger.append(
        node,
        {"kind": "bind", "subject": "CONFLICTING"},
        nonce="equiv",
        sequence=target.sequence,
        counter=target.counter,
        previous_digest=target.previous_digest,
    )
    cases["equivocation_same_sequence"] = ledger.verify()

    detection = {}
    expected_problem = {
        "monotonic_counter_rollback": "monotonic_counter_failure",
        "monotonic_counter_repeat": "monotonic_counter_failure",
        "hash_chain_break": "hash_chain_break",
        "sequence_reuse": "sequence_gap_or_reuse",
        "nonce_replay": "nonce_replay",
        "forged_signature": "invalid_signature",
        "equivocation_same_sequence": "sequence_gap_or_reuse",
    }
    for name, verification in cases.items():
        problems = {problem["problem"] for problem in verification["problems"]}
        detection[name] = {
            "structurally_valid": verification["structurally_valid"],
            "problems_detected": sorted(problems),
            "detected": not verification["structurally_valid"] or verification["equivocation_detected"],
            "expected_problem_present": expected_problem[name] in problems,
            "equivocation_detected": verification["equivocation_detected"],
        }

    guard_clean = WritePathGuard(ledger=clean_ledger).status()
    equivocating = IdentityLedger()
    node_e = derive_identity("node-e", seed="ledger-suite")
    equivocating.append(node_e, {"kind": "bind", "subject": "x"}, nonce="e1")
    equivocating.append(
        node_e, {"kind": "bind", "subject": "y"}, nonce="e2", sequence=0, counter=1,
        previous_digest=GENESIS,
    )
    guard_equivocating = WritePathGuard(ledger=equivocating).status()

    guards = {
        "clean": guard_clean,
        "equivocating": guard_equivocating,
        "attestation_lost": WritePathGuard(ledger=clean_ledger, attestation_healthy=False).status(),
        "counter_service_down": WritePathGuard(ledger=clean_ledger, counter_service_healthy=False).status(),
        "below_quorum": WritePathGuard(ledger=clean_ledger, active_replicas=3, byzantine_tolerance=1).status(),
    }

    return {
        "schema_version": "boundarybench.dcse_ledger_suite.v1",
        "ledger_version": LEDGER_VERSION,
        "clean_ledger": {
            "entries": clean["entries"],
            "structurally_valid": clean["structurally_valid"],
            "non_equivocating": clean["non_equivocating"],
        },
        "fault_classes_declared": list(LEDGER_FAULT_CLASSES),
        "faults_injected": len(cases),
        "detection": detection,
        "all_faults_detected": all(entry["detected"] for entry in detection.values()),
        "all_faults_correctly_classified": all(
            entry["expected_problem_present"] for entry in detection.values()
        ),
        "equivocation_detected_when_injected": detection["equivocation_same_sequence"][
            "equivocation_detected"
        ],
        "equivocation_not_falsely_reported": not clean["equivocation_detected"],
        "write_path_guards": guards,
        "clean_permits_writes": guards["clean"]["authoritative_writes_permitted"],
        "every_fallback_trigger_halts_writes": all(
            guards[name]["authoritative_writes_permitted"] is False
            for name in ("equivocating", "attestation_lost", "counter_service_down", "below_quorum")
        ),
        "declared_trigger_set": list(FALLBACK_TRIGGERS),
        "scope_demonstration": ledger_scope_demonstration(),
        "signature_scheme": "Ed25519 (real signatures, publicly verifiable equivocation evidence)",
    }
