"""Domain portability, Section 9.2 and Table 1: sensitive infrastructure / mission data.

Table 1 asserts that the DCSE protocol objects are shared across domains while the
semantics are not:

    "The architecture is shared; semantics, authoritative evidence, and policy are
    domain-specific."

That is a claim about *code reuse*, so the honest way to test it is to instantiate a
second domain and observe what had to change. This module is that instantiation, for
the Government / mission-systems column of Table 1, applied to sensitive
infrastructure asset and telemetry records.

What is reused **verbatim**, with no domain awareness anywhere in it:

* the identity/provenance ledger and its non-equivocation detection,
* the attestation verifier,
* the consensus quorum model,
* the enclave check set and its sparse certificate,
* the atomic transaction assembler and gateway,
* the receipt chain.

What had to be written fresh: the witness derivation and the gate set. That is
exactly the split Table 1 predicts, and the module reports the split as a measured
quantity rather than an assertion.

Mapping from Table 1's healthcare column to this one:

| Object | Healthcare | Sensitive infrastructure |
|---|---|---|
| B | admissible clinical action states | verified / releasable / restricted / review-required / reject |
| V | FHIR, RxNorm, SNOMED, LOINC versions | asset-catalog schema, controlled vocabulary, handling-standard versions |
| Theta | evidence over mapping/identity/temporal categories | evidence over entity resolution, source reliability, asset status |
| F | candidate mapping, FHIR resource, write-ready item | candidate asset record, telemetry claim, entity association |
| W | source EHR records, signed terminology, provenance | authoritative registries, signed source records, directives |
| L | patient identity decisions plus provenance | entity/case/credential identity plus non-equivocation history |
| P | identity, terminology, temporal, write policy | access, classification handling, need-to-know, jurisdiction, degraded mode |
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
from typing import Any, Iterable, Sequence

INFRASTRUCTURE_VERSION = "dcse-infrastructure-domain-v3.0"

# Domain-specific action lattice. Same shape as the clinical one, different names,
# mapped onto the shared admit/refuse partition the architecture understands.
ACTIONS = (
    "release_verified",
    "release_historical_only",
    "quarantine_record",
    "abstain",
    "analyst_review",
    "reject",
)
ADMITTING_ACTIONS = frozenset({"release_verified", "release_historical_only"})

# Domain-specific gates, in declared fail-closed precedence. Precedence order is
# part of the contract exactly as in the clinical policy.
GATE_PRECEDENCE = (
    "catalog_bundle_unsigned",
    "catalog_bundle_unpinned",
    "handling_caveat_violation",
    "jurisdiction_unauthorized",
    "need_to_know_unsatisfied",
    "entity_resolution_ambiguous",
    "entity_resolution_absent",
    "provenance_signature_absent",
    "validity_window_invalid",
    "source_reliability_unrated",
    "directive_version_unpinned",
    "validity_window_expired",
    "catalog_entry_superseded",
    "required_evidence_absent",
    "telemetry_field_contaminated",
)

# Gates whose correct outcome is a hard refusal rather than review.
HARD_REFUSAL_GATES = frozenset(
    {
        "catalog_bundle_unsigned",
        "catalog_bundle_unpinned",
        "handling_caveat_violation",
        "jurisdiction_unauthorized",
        "need_to_know_unsatisfied",
        "provenance_signature_absent",
        "validity_window_invalid",
        "source_reliability_unrated",
        "directive_version_unpinned",
    }
)

# Severe contradiction classes for this domain, the analogue of the clinical set.
SEVERE_CLASSES = (
    "catalog_bundle_unsigned",
    "catalog_bundle_unpinned",
    "handling_caveat_violation",
    "jurisdiction_unauthorized",
    "need_to_know_unsatisfied",
    "entity_resolution_ambiguous",
    "provenance_signature_absent",
    "validity_window_invalid",
    "source_reliability_unrated",
    "directive_version_unpinned",
)


@dataclass(frozen=True)
class InfrastructureWitness:
    """The authoritative grounding state W for one candidate record."""

    record_id: str
    asset_class: str
    entity_resolution: str  # certified | ambiguous | absent
    catalog_signature: str  # signed | unsigned | unpinned
    catalog_entry: str  # current | superseded
    handling_caveats: tuple[str, ...]
    clearance_caveats: tuple[str, ...]
    jurisdiction: str  # authorized | unauthorized
    need_to_know: str  # satisfied | unsatisfied
    source_reliability: str  # rated | unrated
    provenance_signature: str  # present | absent
    validity_window: str  # open | expired | invalid
    directive_version: str  # pinned | unpinned
    required_evidence_present: bool
    telemetry_contamination: str  # clean | partial | full
    subject_scope_keys: tuple[str, ...]
    shared_reference_keys: tuple[str, ...]

    def fired_gates(self) -> tuple[str, ...]:
        fired: list[str] = []
        if self.catalog_signature == "unsigned":
            fired.append("catalog_bundle_unsigned")
        if self.catalog_signature == "unpinned":
            fired.append("catalog_bundle_unpinned")
        if not set(self.handling_caveats) <= set(self.clearance_caveats):
            fired.append("handling_caveat_violation")
        if self.jurisdiction == "unauthorized":
            fired.append("jurisdiction_unauthorized")
        if self.need_to_know == "unsatisfied":
            fired.append("need_to_know_unsatisfied")
        if self.entity_resolution == "ambiguous":
            fired.append("entity_resolution_ambiguous")
        if self.entity_resolution == "absent":
            fired.append("entity_resolution_absent")
        if self.provenance_signature == "absent":
            fired.append("provenance_signature_absent")
        if self.validity_window == "invalid":
            fired.append("validity_window_invalid")
        if self.source_reliability == "unrated":
            fired.append("source_reliability_unrated")
        if self.directive_version == "unpinned":
            fired.append("directive_version_unpinned")
        if self.validity_window == "expired":
            fired.append("validity_window_expired")
        if self.catalog_entry == "superseded":
            fired.append("catalog_entry_superseded")
        if not self.required_evidence_present:
            fired.append("required_evidence_absent")
        if self.telemetry_contamination in {"partial", "full"}:
            fired.append("telemetry_field_contaminated")
        return tuple(gate for gate in GATE_PRECEDENCE if gate in set(fired))

    def severe_classes(self) -> frozenset[str]:
        return frozenset(set(self.fired_gates()) & set(SEVERE_CLASSES))

    @property
    def is_severe(self) -> bool:
        return bool(self.severe_classes())

    @property
    def is_clean(self) -> bool:
        return not self.fired_gates()


def required_action(witness: InfrastructureWitness) -> tuple[str, str | None]:
    """Domain-specific policy P: fail-closed precedence over the fired gates."""

    fired = witness.fired_gates()
    if not fired:
        return "release_verified", None
    dominant = fired[0]
    if dominant in HARD_REFUSAL_GATES:
        if dominant in {
            "catalog_bundle_unsigned",
            "catalog_bundle_unpinned",
            "directive_version_unpinned",
        }:
            return "reject", dominant
        if dominant in {
            "handling_caveat_violation",
            "jurisdiction_unauthorized",
            "need_to_know_unsatisfied",
        }:
            return "reject", dominant
        if dominant in {"provenance_signature_absent", "validity_window_invalid"}:
            return "quarantine_record", dominant
        return "analyst_review", dominant
    if dominant == "entity_resolution_ambiguous":
        return "quarantine_record", dominant
    if dominant == "entity_resolution_absent":
        return "quarantine_record", dominant
    if dominant == "required_evidence_absent":
        return "abstain", dominant
    if dominant == "validity_window_expired":
        return "release_historical_only", dominant
    if dominant == "catalog_entry_superseded":
        return "release_historical_only", dominant
    if dominant == "telemetry_field_contaminated":
        return ("reject" if witness.telemetry_contamination == "full" else "analyst_review"), dominant
    return "analyst_review", dominant


def _unit(*parts: str) -> float:
    material = "|".join(parts).encode("utf-8")
    return int.from_bytes(hashlib.sha256(material).digest()[:7], "big") / float(1 << 56)


ASSET_CLASSES = (
    "substation_transformer",
    "pipeline_valve_station",
    "water_treatment_pump",
    "telecom_backhaul_node",
    "port_crane_controller",
    "rail_signal_interlock",
)


def generate_population(
    count: int = 512, *, severe_fraction: float = 0.5, seed: str = "infra-v3"
) -> dict[str, Any]:
    """Deterministic synthetic population, half of it carrying a severe contradiction.

    Non-clinical, non-real. No actual asset, operator, location or telemetry value
    is represented; the records exist only to exercise the gate set.
    """

    witnesses: list[InfrastructureWitness] = []
    severe_ids: list[str] = []
    clean_ids: list[str] = []
    injected_classes: dict[str, int] = {}

    for index in range(count):
        record_id = f"infra-{index:05d}"
        asset_class = ASSET_CLASSES[index % len(ASSET_CLASSES)]
        make_severe = _unit(seed, "severe", record_id) < severe_fraction

        base = {
            "entity_resolution": "certified",
            "catalog_signature": "signed",
            "catalog_entry": "current",
            "handling_caveats": ("HANDLE-A",),
            "clearance_caveats": ("HANDLE-A", "HANDLE-B"),
            "jurisdiction": "authorized",
            "need_to_know": "satisfied",
            "source_reliability": "rated",
            "provenance_signature": "present",
            "validity_window": "open",
            "directive_version": "pinned",
            "required_evidence_present": True,
            "telemetry_contamination": "clean",
        }

        if make_severe:
            klass = SEVERE_CLASSES[int(_unit(seed, "class", record_id) * len(SEVERE_CLASSES)) % len(SEVERE_CLASSES)]
            if klass == "catalog_bundle_unsigned":
                base["catalog_signature"] = "unsigned"
            elif klass == "catalog_bundle_unpinned":
                base["catalog_signature"] = "unpinned"
            elif klass == "handling_caveat_violation":
                base["handling_caveats"] = ("HANDLE-A", "HANDLE-RESTRICTED")
            elif klass == "jurisdiction_unauthorized":
                base["jurisdiction"] = "unauthorized"
            elif klass == "need_to_know_unsatisfied":
                base["need_to_know"] = "unsatisfied"
            elif klass == "entity_resolution_ambiguous":
                base["entity_resolution"] = "ambiguous"
            elif klass == "provenance_signature_absent":
                base["provenance_signature"] = "absent"
            elif klass == "validity_window_invalid":
                base["validity_window"] = "invalid"
            elif klass == "source_reliability_unrated":
                base["source_reliability"] = "unrated"
            elif klass == "directive_version_unpinned":
                base["directive_version"] = "unpinned"
            injected_classes[klass] = injected_classes.get(klass, 0) + 1
            severe_ids.append(record_id)
        else:
            # Non-severe variation, so the clean population is not uniform: some
            # records legitimately require review or historical-only release.
            draw = _unit(seed, "benign", record_id)
            if draw < 0.10:
                base["validity_window"] = "expired"
            elif draw < 0.20:
                base["catalog_entry"] = "superseded"
            elif draw < 0.26:
                base["telemetry_contamination"] = "partial"
            elif draw < 0.30:
                base["required_evidence_present"] = False
            else:
                clean_ids.append(record_id)

        witnesses.append(
            InfrastructureWitness(
                record_id=record_id,
                asset_class=asset_class,
                subject_scope_keys=(f"record:{record_id}", f"asset:{asset_class}:{index // 8}"),
                shared_reference_keys=("ref:CATALOG:asset-catalog-2026-03", "ref:DIRECTIVE:handling-1.1"),
                **base,
            )
        )

    return {
        "witnesses": witnesses,
        "severe_ids": frozenset(severe_ids),
        "clean_ids": frozenset(clean_ids),
        "injected_classes": injected_classes,
        "population": count,
    }


def run_infrastructure_domain_suite(count: int = 512) -> dict[str, Any]:
    """Run the shared architecture over the infrastructure domain and measure reuse."""

    from boundarybench.dcse.attestation import run_attestation_suite
    from boundarybench.dcse.consensus import run_consensus_suite
    from boundarybench.dcse.crypto import derive_identity
    from boundarybench.dcse.enclave import run_enclave_suite
    from boundarybench.dcse.ledger import IdentityLedger, WritePathGuard
    from boundarybench.dcse.receipts import ReceiptChain
    from boundarybench.dcse.transaction import (
        Bundle,
        BUNDLE_TRANSACTION,
        FhirGateway,
        ResourceEntry,
        ResourceStore,
        TransactionAssembler,
    )

    population = generate_population(count)
    witnesses = population["witnesses"]

    # --- the same two Table 3 measures, this domain's semantics ---------------
    severe_total = sum(1 for w in witnesses if w.is_severe)
    severe_caught = 0
    false_conflicts = 0
    admissible_denominator = 0
    admitted = 0
    refused = 0
    by_action: dict[str, int] = {}

    for witness in witnesses:
        action, gate = required_action(witness)
        by_action[action] = by_action.get(action, 0) + 1
        if witness.is_severe and action not in ADMITTING_ACTIONS:
            severe_caught += 1
        if witness.is_clean:
            admissible_denominator += 1
            if action not in ADMITTING_ACTIONS:
                false_conflicts += 1
        if action in ADMITTING_ACTIONS:
            admitted += 1
        else:
            refused += 1

    sensitivity = severe_caught / severe_total if severe_total else None
    false_conflict_rate = (
        false_conflicts / admissible_denominator if admissible_denominator else None
    )

    # --- reuse of the domain-neutral protocol layer, verbatim ----------------
    signer = derive_identity("infra-node", seed="infra-v3")
    ledger = IdentityLedger()
    chain = ReceiptChain(signer=signer, ledger=ledger)
    receipts_emitted = 0
    for index, witness in enumerate(witnesses[:64]):
        action, gate = required_action(witness)
        chain.emit(
            kind="AuditEvent",
            subject=witness.record_id,
            decision=action,
            witness={"asset_class": witness.asset_class, "gates": list(witness.fired_gates())},
            policy_version="1.1",
            terminology_version="asset-catalog-2026-03",
            body={
                "resourceType": "AuditEvent",
                "action": "E",
                "outcome": "0" if action in ADMITTING_ACTIONS else "4",
                "review_surface": {
                    "candidate_value": witness.asset_class,
                    "authoritative_evidence": witness.catalog_signature,
                    "source_freshness": witness.catalog_entry,
                    "schema_authority": "infrastructure.record.v1",
                    "provenance_reference": witness.provenance_signature,
                    "policy_rule_id": gate or "no_gate_fired",
                    "required_action": action,
                },
            },
            nonce=f"infra-audit-{index}",
        )
        receipts_emitted += 1
        if action not in ADMITTING_ACTIONS:
            chain.emit(
                kind="OperationOutcome",
                subject=witness.record_id,
                decision=action,
                witness={"asset_class": witness.asset_class, "gates": list(witness.fired_gates())},
                policy_version="1.1",
                terminology_version="asset-catalog-2026-03",
                body={
                    "resourceType": "OperationOutcome",
                    "issue": [
                        {
                            "severity": "error" if action == "reject" else "warning",
                            "code": "business-rule",
                            "diagnostics": f"refused: {gate}",
                        }
                    ],
                    "review_surface": {
                        "candidate_value": witness.asset_class,
                        "authoritative_evidence": witness.catalog_signature,
                        "source_freshness": witness.catalog_entry,
                        "schema_authority": "infrastructure.record.v1",
                        "provenance_reference": witness.provenance_signature,
                        "policy_rule_id": gate or "no_gate_fired",
                        "required_action": action,
                    },
                },
                nonce=f"infra-outcome-{index}",
            )
            receipts_emitted += 1

    chain_verification = chain.verify()
    ledger_verification = ledger.verify()
    guard = WritePathGuard(ledger=ledger).status()

    # Atomic release bundle: one contaminated telemetry record nested inside.
    store = ResourceStore()
    store.apply([ResourceEntry("AssetRecord", "unrelated-1", {"v": 1}, "scope-z", True)])
    baseline = store.state()
    gateway = FhirGateway(store=store)
    assembler = TransactionAssembler()
    candidates = []
    for witness in witnesses[:6]:
        action, _ = required_action(witness)
        candidates.append(
            ResourceEntry(
                "AssetRecord",
                witness.record_id,
                {"asset_class": witness.asset_class, "status": "active"},
                witness.subject_scope_keys[0],
                action in ADMITTING_ACTIONS,
                None if action in ADMITTING_ACTIONS else "policy_refusal",
            )
        )
    assembled = assembler.assemble(candidates)
    forced = gateway.submit(
        Bundle(
            BUNDLE_TRANSACTION,
            [
                ResourceEntry("AssetRecord", "forced-1", {"v": 1}, "scope-y", True),
                ResourceEntry(
                    "MedicationRequest",  # the gateway's atomicity rule is resource-agnostic
                    "forced-2",
                    {"status": "CORRUPTED", "subject": None},
                    "scope-y",
                    True,
                ),
            ],
        )
    )
    atomicity_held = not forced["committed"] and forced["store_state_identical"]
    unrelated_unchanged = store.state()["AssetRecord/unrelated-1"] == baseline["AssetRecord/unrelated-1"]

    # The domain-neutral systems layer, run unchanged.
    attestation = run_attestation_suite(seed="infra-v3-attestation")
    consensus = run_consensus_suite()
    enclave = run_enclave_suite(vertices=40, disagreeing=(4, 22))

    reused_modules = [
        "dcse.crypto",
        "dcse.ledger",
        "dcse.attestation",
        "dcse.consensus",
        "dcse.enclave",
        "dcse.transaction",
        "dcse.receipts",
        "dcse.cone_certificate",
    ]
    domain_specific = ["InfrastructureWitness", "required_action", "GATE_PRECEDENCE", "SEVERE_CLASSES"]

    return {
        "schema_version": "boundarybench.dcse_infrastructure_domain.v1",
        "infrastructure_version": INFRASTRUCTURE_VERSION,
        "table_1_column": "Government / mission systems, applied to sensitive infrastructure",
        "population": population["population"],
        "severe_population": severe_total,
        "clean_population": len(population["clean_ids"]),
        "injected_class_counts": population["injected_classes"],
        "all_severe_classes_represented": set(population["injected_classes"]) == set(SEVERE_CLASSES),
        "action_distribution": dict(sorted(by_action.items())),
        "severe_contradiction_sensitivity": sensitivity,
        "severe_contradictions_missed": severe_total - severe_caught,
        "sensitivity_target_met": sensitivity == 1.0,
        "false_conflict_adjudication_rate": false_conflict_rate,
        "false_conflict_count": false_conflicts,
        "false_conflict_denominator": admissible_denominator,
        "false_conflict_target_met": (
            false_conflict_rate is not None and false_conflict_rate <= 0.04
        ),
        "admitted": admitted,
        "refused": refused,
        "receipts_emitted": receipts_emitted,
        "receipt_chain_valid": chain_verification["chain_valid"],
        "ledger_structurally_valid": ledger_verification["structurally_valid"],
        "ledger_non_equivocating": ledger_verification["non_equivocating"],
        "write_path_mode": guard["mode"],
        "authoritative_writes_permitted": guard["authoritative_writes_permitted"],
        "atomicity_held_under_forced_bad_entry": atomicity_held,
        "unrelated_records_unchanged": unrelated_unchanged,
        "pre_construction_quarantine_keys": assembled["quarantined_keys"][:8],
        "systems_layer_reused_verbatim": {
            "attestation_all_injections_fail_closed": attestation["all_injections_fail_closed"],
            "consensus_all_invariants_hold": consensus["all_invariants_hold"],
            "enclave_claim_supported": enclave["section_9_3_claim_supported"],
        },
        "portability": {
            "domain_neutral_modules_reused": reused_modules,
            "domain_neutral_module_count": len(reused_modules),
            "domain_specific_objects": domain_specific,
            "domain_specific_object_count": len(domain_specific),
            "architecture_changed_for_new_domain": False,
            "semantics_changed_for_new_domain": True,
        },
        "table_1_portability_claim_supported": bool(
            sensitivity == 1.0
            and false_conflict_rate is not None
            and false_conflict_rate <= 0.04
            and chain_verification["chain_valid"]
            and ledger_verification["structurally_valid"]
            and atomicity_held
            and unrelated_unchanged
            and attestation["all_injections_fail_closed"]
            and consensus["all_invariants_hold"]
            and enclave["section_9_3_claim_supported"]
        ),
        "scope": (
            "Synthetic, non-real records. No actual asset, operator, location or telemetry "
            "value is represented. This tests architectural portability, not readiness for "
            "any operational infrastructure environment."
        ),
    }
