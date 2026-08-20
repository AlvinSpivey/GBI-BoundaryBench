"""The external-validity predicate EV, and the versioned policy contract P.

Section 12.1.3 of the manuscript defines the operational admission gate as

    EV : B x W -> {0, 1}

a *terminating Boolean procedure over authoritative evidence, not an LLM
judgment*, and Section 12.6 makes admissibility existential over witnesses:

    Admissible(b) = 1  <=>  there exists an admissible witness w with EV(b, w) = 1

Section 9.2 decomposes the policy object into

    P = ( A, G, T, D, H, Q, R, Lambda, E, F_b )

with A the allowed action set, G hard gating predicates, T thresholds and
validity windows, D dependency rules, H human-authority requirements, Q
quarantine scope, R recovery and escalation, Lambda liveness constraints, E
signed exception rules, and F_b failover behavior. This module implements that
tuple as executable code and evaluates it against witness bundles.

Why this module is the substantive v2 change
--------------------------------------------
BoundaryBench v0.1 scored a proposal by exact agreement with a held-out reference
action. That is answer-key agreement. It is a legitimate benchmark property, but
it is *not* the property the manuscript claims, and it is not available at
deployment time, where there is no answer key. Consequently v0.1 could not
measure either of the two clinical targets in Table 3, and its zero-coverage
result could not distinguish a safe substrate from one that refuses everything.

EV closes that gap: it decides admissibility from witnesses alone. The reference
action is then used only as an independent yardstick to score EV itself, never as
an input to it.

Falsifiability
--------------
``POLICY_INCOMPLETE`` is a deliberately deficient policy that omits two gating
predicates. It is evaluated alongside the complete policy in every scorecard run.
If a 100% severe-contradiction sensitivity were an artifact of the measurement
rather than a property of the policy, the incomplete policy would score 100% too.
It does not, which is what gives the reported number meaning.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence

from boundarybench.betal.witness import WitnessBundle

EV_VERSION = "gbi-v2-external-validity-v1"

ADMITTING_ACTIONS: frozenset[str] = frozenset({"admit", "admit_historical_only"})
REFUSING_ACTIONS: frozenset[str] = frozenset(
    {"quarantine_slice", "abstain", "expert_review", "reject"}
)

# Declared fail-closed precedence over gating predicates. Earlier entries
# dominate. The two Boundary rules from Appendix B.3 sit at the top by
# construction, not by tuning.
GATE_PRECEDENCE: tuple[tuple[str, str, str], ...] = (
    # (gate name, action, rationale)
    ("boundary_1_identity_unresolvable", "reject",
     "Boundary 1: identity resolution failed; halt and deny write permissions."),
    ("boundary_1_identity_ambiguous", "quarantine_slice",
     "Boundary 1: ambiguous identity match; halt and deny write regardless of "
     "demographic similarity score."),
    ("boundary_2_bundle_unsigned", "reject",
     "Boundary 2: terminology bundle is unsigned; administrative freeze."),
    ("boundary_2_bundle_unpinned", "reject",
     "Boundary 2: terminology bundle version is unpinned; administrative freeze."),
    ("terminology_unresolvable", "reject",
     "Code does not resolve under any version in the signed bundle."),
    ("structured_field_fully_contaminated", "reject",
     "Structured column holds only narrative text; value unsupported."),
    ("validity_window_invalid", "reject",
     "Temporal evidence is not a valid interval."),
    ("validity_window_expired", "quarantine_slice",
     "Validity window has expired against the evaluation instant."),
    ("provenance_signature_absent", "quarantine_slice",
     "No provenance witness; localize the slice rather than admit it."),
    ("required_evidence_absent", "abstain",
     "A fact required by the asserted answer is absent; do not fill by inference."),
    ("policy_predicate_refusal", "reject",
     "A firing policy predicate mandates refusal under declared precedence."),
    ("policy_predicate_identity_confidence", "quarantine_slice",
     "Policy predicate: identity confidence below threshold."),
    ("structured_field_partially_contaminated", "expert_review",
     "Recoverable numeric prefix with narrative bleed; silent coercion not permitted."),
    ("identity_mismatch_over_tolerance", "expert_review",
     "Identity field mismatches exceed the declared tolerance."),
    ("evidence_completeness_below_floor", "expert_review",
     "Evidence completeness below the declared floor."),
    ("identity_score_below_floor", "expert_review",
     "Demographic similarity below the declared review floor."),
)

# Gates the incomplete policy fails to implement. Chosen as two genuinely severe
# classes so the deficiency shows up in sensitivity rather than in noise.
INCOMPLETE_POLICY_OMISSIONS: frozenset[str] = frozenset(
    {"boundary_2_bundle_unsigned", "provenance_signature_absent"}
)


@dataclass(frozen=True)
class PolicyContract:
    """A versioned instance of P = (A, G, T, D, H, Q, R, Lambda, E, F_b)."""

    policy_id: str
    version: str
    effective_time: str
    strictness: float = 0.5
    # A
    allowed_actions: tuple[str, ...] = (
        "admit", "admit_historical_only", "quarantine_slice", "abstain",
        "expert_review", "reject",
    )
    # G
    implemented_gates: frozenset[str] = field(
        default_factory=lambda: frozenset(name for name, _, _ in GATE_PRECEDENCE)
    )
    # D
    dependency_closure_enabled: bool = True
    # H
    human_authority_required_for: tuple[str, ...] = ("expert_review",)
    # Q
    quarantine_scope: str = "slice"
    # Lambda
    liveness_permits_independent_work: bool = True
    # E
    signed_exceptions_enabled: bool = False
    # F_b
    failover_action: str = "reject"

    # T, derived from strictness so the sensitivity / false-conflict trade-off is
    # a single declared dial rather than a set of hand-picked constants.
    @property
    def identity_mismatch_tolerance(self) -> int:
        return int(round(2 * (1.0 - self.strictness)))

    @property
    def evidence_completeness_floor(self) -> float:
        return 0.20 + 0.80 * self.strictness

    @property
    def identity_score_floor(self) -> float:
        return 0.90 * self.strictness

    def thresholds(self) -> dict[str, Any]:
        return {
            "identity_mismatch_tolerance": self.identity_mismatch_tolerance,
            "evidence_completeness_floor": round(self.evidence_completeness_floor, 4),
            "identity_score_floor": round(self.identity_score_floor, 4),
        }

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "boundarybench.gbi_v2_policy_contract.v1",
            "ev_version": EV_VERSION,
            "policy_id": self.policy_id,
            "version": self.version,
            "effective_time": self.effective_time,
            "strictness": self.strictness,
            "allowed_actions": list(self.allowed_actions),
            "implemented_gate_count": len(self.implemented_gates),
            "total_declared_gate_count": len(GATE_PRECEDENCE),
            "omitted_gates": sorted(
                {name for name, _, _ in GATE_PRECEDENCE} - self.implemented_gates
            ),
            "thresholds": self.thresholds(),
            "dependency_closure_enabled": self.dependency_closure_enabled,
            "quarantine_scope": self.quarantine_scope,
            "liveness_permits_independent_work": self.liveness_permits_independent_work,
            "signed_exceptions_enabled": self.signed_exceptions_enabled,
            "failover_action": self.failover_action,
        }


def complete_policy(strictness: float = 0.5) -> PolicyContract:
    return PolicyContract(
        policy_id="gbi-v2-policy-complete",
        version="2.0",
        effective_time="2026-01-01T00:00:00Z",
        strictness=strictness,
    )


def incomplete_policy(strictness: float = 0.5) -> PolicyContract:
    """A policy missing two gating predicates. Used to falsify the scorecard."""

    return PolicyContract(
        policy_id="gbi-v2-policy-incomplete",
        version="0.9",
        effective_time="2026-01-01T00:00:00Z",
        strictness=strictness,
        implemented_gates=frozenset(
            name for name, _, _ in GATE_PRECEDENCE if name not in INCOMPLETE_POLICY_OMISSIONS
        ),
    )


# Boundary 1 forbids resolving identity ambiguity with a demographic similarity
# score. A policy that tried to do so anyway is the natural ablation: it keeps the
# advisory score gate but drops the two hard identity gates.
SCORE_ONLY_POLICY_OMISSIONS: frozenset[str] = frozenset(
    {"boundary_1_identity_unresolvable", "boundary_1_identity_ambiguous"}
)


def score_only_policy(strictness: float = 0.5) -> PolicyContract:
    """Ablation: identity handled by demographic similarity instead of a hard gate.

    Appendix B.3 Boundary 1 requires an ambiguous identity match to halt "regardless
    of demographic similarity scores". This policy violates that requirement on
    purpose, so the scorecard can show what the requirement buys.
    """

    return PolicyContract(
        policy_id="gbi-v2-policy-score-only-identity",
        version="0.5",
        effective_time="2026-01-01T00:00:00Z",
        strictness=strictness,
        implemented_gates=frozenset(
            name for name, _, _ in GATE_PRECEDENCE if name not in SCORE_ONLY_POLICY_OMISSIONS
        ),
    )


@dataclass
class Verdict:
    """The result of evaluating EV for one proposal against one witness."""

    task_id: str
    required_action: str
    fired_gate: str | None
    rationale: str
    admissible: bool
    refusal_reasons: tuple[str, ...]
    witness_severe_classes: tuple[str, ...]
    proposal_action: str | None
    proposal_consistent_with_witness: bool
    quarantine_keys: tuple[str, ...]
    administrative_freeze: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "required_action": self.required_action,
            "fired_gate": self.fired_gate,
            "rationale": self.rationale,
            "admissible": self.admissible,
            "refusal_reasons": list(self.refusal_reasons),
            "witness_severe_classes": list(self.witness_severe_classes),
            "proposal_action": self.proposal_action,
            "proposal_consistent_with_witness": self.proposal_consistent_with_witness,
            "quarantine_keys": list(self.quarantine_keys),
            "administrative_freeze": self.administrative_freeze,
        }


def _gate_conditions(witness: WitnessBundle, policy: PolicyContract) -> dict[str, bool]:
    """Evaluate every declared gating predicate against the witness."""

    firing = set(witness.firing_predicates)
    return {
        "boundary_1_identity_unresolvable": witness.identity_status == "unresolvable",
        "boundary_1_identity_ambiguous": witness.identity_status == "ambiguous",
        "boundary_2_bundle_unsigned": not witness.bundle_signed,
        "boundary_2_bundle_unpinned": not witness.bundle_pinned,
        "terminology_unresolvable": not witness.code_resolvable,
        "structured_field_fully_contaminated": witness.field_contamination == "full",
        "validity_window_invalid": not witness.validity_window_valid,
        "validity_window_expired": witness.validity_window_expired,
        "provenance_signature_absent": not witness.provenance_signature_present,
        "required_evidence_absent": witness.absent_fact_count > 0,
        "policy_predicate_refusal": bool(
            firing & {"provenance_signature_absent", "terminology_version_unsupported"}
        ),
        "policy_predicate_identity_confidence": "identity_confidence_below_threshold" in firing,
        "structured_field_partially_contaminated": witness.field_contamination == "partial",
        "identity_mismatch_over_tolerance": (
            witness.identity_mismatched_field_count > policy.identity_mismatch_tolerance
        ),
        "evidence_completeness_below_floor": (
            witness.evidence_completeness < policy.evidence_completeness_floor
        ),
        # Boundary 1 forbids the similarity score from overriding an ambiguity
        # finding. It may only ever *add* a review requirement, never remove one,
        # which is why it sits at the bottom of the precedence order.
        "identity_score_below_floor": witness.identity_match_score < policy.identity_score_floor,
    }


def required_action_from_witness(
    witness: WitnessBundle, policy: PolicyContract
) -> tuple[str, str | None, str, tuple[str, ...]]:
    """Compute the action the witness alone entails, under declared precedence.

    Returns ``(action, fired_gate, rationale, all_fired_gate_names)``. No
    reference action is consulted anywhere in this function.
    """

    conditions = _gate_conditions(witness, policy)
    fired = tuple(
        name
        for name, _, _ in GATE_PRECEDENCE
        if conditions.get(name) and name in policy.implemented_gates
    )
    for name, action, rationale in GATE_PRECEDENCE:
        if name not in policy.implemented_gates:
            continue
        if conditions.get(name):
            return action, name, rationale, fired

    # No gate fired. Qualified admission where the witness says historical-only.
    if witness.code_superseded:
        return (
            "admit_historical_only",
            None,
            "Code resolves only under a superseded bundle version; historical-only.",
            fired,
        )
    if not witness.validity_window_open:
        return (
            "admit_historical_only",
            None,
            "Validity window is closed; admissible as historical evidence only.",
            fired,
        )
    return "admit", None, "All declared gates pass over authoritative evidence.", fired


def evaluate_ev(
    *,
    witness: WitnessBundle,
    policy: PolicyContract,
    proposal: dict[str, Any] | None = None,
    format_boundary_passed: bool = True,
) -> Verdict:
    """Evaluate EV(b, w) for a candidate proposal against a witness bundle.

    A proposal is admissible only if all of the following hold:

    0. the emission cleared the format boundary (safe parse and schema validation);
    1. the witness itself entails an admitting action;
    2. the proposal's action agrees with the action the witness entails;
    3. every evidence reference the proposal cites exists in the witness;
    4. any source-record claim the proposal makes matches the witness.

    Conditions 3 and 4 are what catch a fabricated-witness proposal whose action
    happens to be right. They are checked independently of the witness severity
    path, so a gap in one cannot be hidden by the other.

    Condition 0 is separate from ``proposal is None``. Evaluating the gate with no
    proposal at all is the substrate-only configuration, which measures a property
    of the policy. A proposal that *existed* but failed to parse is a different
    thing: there is nothing to admit, and treating it as substrate-only would
    silently credit the model with the substrate's verdict.
    """

    action, gate, rationale, fired = required_action_from_witness(witness, policy)
    severe = witness.severe_classes()
    reasons: list[str] = []
    if gate is not None:
        reasons.append(f"gate:{gate}")

    consistent = True
    proposal_action: str | None = None
    if proposal is not None:
        proposal_action = proposal.get("action")
        cited = set(proposal.get("evidence_refs") or ())
        unknown = cited - set(witness.available_evidence_ref_ids)
        if unknown:
            consistent = False
            reasons.append(f"fabricated_evidence:{','.join(sorted(unknown))}")
        answer = proposal.get("answer")
        if isinstance(answer, dict):
            claimed_source = answer.get("source_record_id")
            if (
                claimed_source is not None
                and witness.provenance_source_record_id is not None
                and claimed_source != witness.provenance_source_record_id
            ):
                consistent = False
                reasons.append("source_record_id_not_witnessed")
        if proposal_action != action:
            reasons.append(f"action_disagrees_with_witness:{proposal_action}!={action}")

    if not format_boundary_passed:
        reasons.append("format_boundary_reject")
        consistent = False

    admissible = (
        format_boundary_passed
        and action in ADMITTING_ACTIONS
        and consistent
        and (proposal is None or proposal_action == action)
    )

    # Surgical quarantine scope. Subject-scoped keys always close. Shared reference
    # objects close only when the refusal implicates the shared object itself,
    # which is exactly Boundary 2's administrative freeze.
    if admissible:
        quarantine_keys: tuple[str, ...] = ()
        froze_shared = False
    else:
        quarantine_keys = witness.dependency_keys
        froze_shared = gate in ("boundary_2_bundle_unsigned", "boundary_2_bundle_unpinned")
        if froze_shared:
            quarantine_keys = quarantine_keys + witness.shared_reference_keys
    return Verdict(
        task_id=witness.task_id,
        required_action=action,
        fired_gate=gate,
        rationale=rationale,
        admissible=admissible,
        refusal_reasons=tuple(reasons),
        witness_severe_classes=severe,
        proposal_action=proposal_action,
        proposal_consistent_with_witness=consistent,
        quarantine_keys=quarantine_keys,
        administrative_freeze=froze_shared,
    )


def boundary_conformance_probes(policy: PolicyContract) -> list[dict[str, Any]]:
    """Direct conformance probes for Appendix B.3 Boundary 1 and Boundary 2.

    These are not statistical. Each probe is a single constructed witness whose
    required outcome the manuscript states in prose, checked literally.
    """

    probes: list[dict[str, Any]] = []

    # Boundary 1: ambiguous identity must halt and deny the write "regardless of
    # demographic similarity scores". Probe it at the maximum similarity score.
    ambiguous_high_score = WitnessBundle(
        task_id="probe-boundary-1-high-similarity",
        family="patient_identity_normalization",
        identity_status="ambiguous",
        identity_mismatched_field_count=1,
        identity_match_score=1.0,
    )
    verdict = evaluate_ev(witness=ambiguous_high_score, policy=policy)
    probes.append(
        {
            "probe": "boundary_1_ambiguous_identity_at_similarity_1.0",
            "requirement": "must not admit; similarity score must not override ambiguity",
            "required_action": verdict.required_action,
            "admissible": verdict.admissible,
            "passed": not verdict.admissible and verdict.required_action in REFUSING_ACTIONS,
        }
    )

    unresolvable_high_score = WitnessBundle(
        task_id="probe-boundary-1-unresolvable",
        family="patient_identity_normalization",
        identity_status="unresolvable",
        identity_mismatched_field_count=3,
        identity_match_score=1.0,
    )
    verdict = evaluate_ev(witness=unresolvable_high_score, policy=policy)
    probes.append(
        {
            "probe": "boundary_1_unresolvable_identity_at_similarity_1.0",
            "requirement": "must halt and deny write permissions",
            "required_action": verdict.required_action,
            "admissible": verdict.admissible,
            "passed": verdict.required_action == "reject",
        }
    )

    # Boundary 2: unsigned or unpinned terminology must trigger an administrative
    # freeze, even when every other gate passes.
    for label, kwargs in (
        ("unsigned", {"bundle_signed": False}),
        ("unpinned", {"bundle_pinned": False}),
    ):
        witness = WitnessBundle(
            task_id=f"probe-boundary-2-{label}",
            family="code_system_version_validation",
            **kwargs,
        )
        verdict = evaluate_ev(witness=witness, policy=policy)
        probes.append(
            {
                "probe": f"boundary_2_terminology_bundle_{label}",
                "requirement": "must trigger administrative freeze; no clinical lookup admitted",
                "required_action": verdict.required_action,
                "admissible": verdict.admissible,
                "passed": verdict.required_action == "reject",
            }
        )

    # A fully clean witness must be admitted. Without this probe the boundary
    # tests above would be satisfiable by a policy that refuses everything.
    clean = WitnessBundle(task_id="probe-clean-baseline", family="rpms_to_fhir_mapping")
    verdict = evaluate_ev(witness=clean, policy=policy)
    probes.append(
        {
            "probe": "non_vacuity_clean_witness_is_admitted",
            "requirement": "a witness with no contradiction must be admitted",
            "required_action": verdict.required_action,
            "admissible": verdict.admissible,
            "passed": verdict.required_action == "admit" and verdict.admissible,
        }
    )
    return probes
