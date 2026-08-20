#!/usr/bin/env python3
"""Independent verification of the GBI-DCSE v3 evaluation.

Does not trust the runner. Re-derives the reported numbers, re-runs the adversarial
suites, and attacks the three claims most likely to be circular or overstated:

1. that the enclave's *spectral-moment* half of the certificate is load-bearing
   rather than decorative — checked by running the residual half alone against the
   forgery only the moment half catches;
2. that equivocation evidence is genuinely publicly verifiable — checked by
   verifying both conflicting signatures with nothing but the public key;
3. that the claim register does not launder a broken resolver into an
   "out of scope" verdict — checked by asserting the register's own integrity
   invariants and its section coverage against main.pdf.

Run from the repository root:

    PYTHONPATH=src python3 scripts/verify_gbi_dcse_v3_scorecard.py
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import sys
from typing import Any

import numpy as np

from boundarybench.dcse.attestation import (
    AttestationPolicy,
    issue_quote,
    run_attestation_suite,
    verify_quote,
)
from boundarybench.dcse.cone_certificate import run_cone_certificate_suite
from boundarybench.dcse.consensus import RoundConfig, analyse_round, quorum_size, required_replicas
from boundarybench.dcse.crypto import derive_identity, digest, verify
from boundarybench.dcse.enclave import (
    RESIDUAL_TOLERANCE,
    external_dense_solve,
    run_enclave_suite,
    scalable_cone_laplacian,
)
from boundarybench.dcse.infrastructure import (
    SEVERE_CLASSES,
    generate_population,
    required_action,
    ADMITTING_ACTIONS,
)
from boundarybench.dcse.ledger import GENESIS, IdentityLedger, run_ledger_suite
from boundarybench.dcse.receipts import run_receipt_suite
from boundarybench.dcse.transaction import run_rollback_conformance_suite
from boundarybench.gbi.appendix_a import (
    _independent_trigamma,
    approx_trigamma,
    fisher_dirichlet,
    hyperellipsoid_certificate,
    run_report,
    run_self_check,
)
from boundarybench.gbi.claims import run_all_section_claims

ROOT = Path(__file__).resolve().parents[1]
V3 = ROOT / "artifacts/public_results/gbi_dcse_v3"

FAILURES: list[str] = []
CHECKS = 0


def check(condition: Any, label: str, detail: str = "") -> None:
    global CHECKS
    CHECKS += 1
    ok = bool(condition)
    if ok:
        print(f"  PASS  {label}")
    else:
        print(f"  FAIL  {label} {detail}")
        FAILURES.append(f"{label} {detail}".strip())


def approx(left: float, right: float, tolerance: float = 1e-9) -> bool:
    return abs(left - right) <= tolerance


def section(title: str) -> None:
    print(f"\n[{title}]")


def main() -> int:
    register_doc = json.loads((V3 / "claim_register.json").read_text(encoding="utf-8"))
    appendix = json.loads((V3 / "appendix_a.json").read_text(encoding="utf-8"))
    sections_doc = json.loads((V3 / "gbi_section_claims.json").read_text(encoding="utf-8"))
    systems = json.loads((V3 / "systems_validation.json").read_text(encoding="utf-8"))
    enclave_doc = json.loads((V3 / "enclave_and_certificate.json").read_text(encoding="utf-8"))
    ledger_doc = json.loads((V3 / "ledger_suite.json").read_text(encoding="utf-8"))
    receipts_doc = json.loads((V3 / "receipts.json").read_text(encoding="utf-8"))
    infra_doc = json.loads((V3 / "infrastructure_domain.json").read_text(encoding="utf-8"))
    protocol_doc = json.loads((V3 / "protocol_inventory.json").read_text(encoding="utf-8"))
    provenance = json.loads((V3 / "PROVENANCE.json").read_text(encoding="utf-8"))

    # ---------------------------------------------------------------- 1
    section("1. Appendix A reproduced independently")
    fresh_check = run_self_check()
    fresh_report = run_report()
    check(fresh_check["all_passed"], f"all {fresh_check['assertions_run']} Appendix A self-check assertions pass")
    check(
        fresh_check["assertions_run"] == appendix["self_check"]["assertions_run"],
        "self-check assertion count matches the artifact",
    )
    check(fresh_report["all_agree"], f"all {fresh_report['comparisons_run']} published values reproduce")
    # Hand-check the three most load-bearing numbers rather than trusting the loop.
    cert = hyperellipsoid_certificate(
        np.array([[1.20, 0.10, 0.0], [0.20, 0.80, 0.05], [0.0, 0.10, 1.10]])
    )
    check(approx(cert.axis_eccentricity, 1.701632, 5e-6), f"H = {cert.axis_eccentricity:.6f} matches 1.701632")
    check(approx(cert.jacobian, 1.028, 5e-6), f"J = {cert.jacobian:.6f} matches 1.028")
    check(approx(cert.outer_distortion, 1.922661, 5e-6), f"K_O = {cert.outer_distortion:.6f} matches 1.922661")
    interior = np.linalg.eigvalsh(fisher_dirichlet([2.0, 3.0, 4.0, 5.0]))
    check(
        approx(float(np.max(interior) / np.min(interior)), 20.46, 0.01),
        f"Fisher condition {float(np.max(interior) / np.min(interior)):.4f} matches 20.46",
    )
    # The ported trigamma must agree with an independent implementation.
    worst = max(
        abs(approx_trigamma(x) - _independent_trigamma(x)) / abs(_independent_trigamma(x))
        for x in (0.01, 0.5, 1.0, 2.0, 7.999, 8.0, 14.0, 100.0)
    )
    check(worst < 1e-8, f"ported trigamma agrees with an independent route to {worst:.2e}")
    check(
        fresh_report["condensed_probe"]["eventually_constant"] is False
        and fresh_report["condensed_probe"]["witnesses_nonzero_cokernel"],
        "1/n converges but is not eventually constant, witnessing the nonzero cokernel",
    )

    # ---------------------------------------------------------------- 2
    section("2. GBI section claims re-run")
    fresh_sections = run_all_section_claims()
    check(fresh_sections["all_met"], f"all {fresh_sections['claims_tested']} section claims met on re-run")
    check(
        fresh_sections["verdicts"] == sections_doc["verdicts"],
        "section verdicts are identical to the artifact (deterministic)",
    )
    # Hand-verify the Section 2.5 table instead of trusting the module's own compare.
    logits = np.array([4.0, 2.7, 1.4, 0.7, -0.2, -1.0])
    expo = np.exp(logits - logits.max())
    p = expo / expo.sum()
    hand_entropy = float(-sum(v * math.log(v) for v in p if v > 0))
    check(approx(hand_entropy, 0.885219, 5e-6), f"hand-computed entropy at tau=1 is {hand_entropy:.6f}")
    check(approx(float(p.max()), 0.711530, 5e-6), f"hand-computed max probability is {float(p.max()):.6f}")
    order = np.argsort(p)[::-1]
    hand_tail = float(1.0 - p[order[:3]].sum())
    check(approx(hand_tail, 0.0417, 5e-4), f"hand-computed top-3 tail mass is {hand_tail:.6f}")
    boolean = fresh_sections["results"]["section_3_boolean_homomorphism"]
    check(
        boolean["pair_checks"] == 4096 and boolean["violation_count"] == 0 and boolean["exhaustive"],
        f"Boolean homomorphism checked exhaustively over {boolean['pair_checks']} pairs with 0 violations",
    )
    switch = fresh_sections["results"]["section_2_dynamical_category_switch"]
    check(
        switch["category_switches"] >= 1 and switch["min_entropy_nats_after_settling"] >= 0.60,
        f"Section 2.7 category switch at entropy >= {switch['min_entropy_nats_after_settling']:.4f} nats "
        f"(two-category maximum is {math.log(2):.4f})",
    )
    safety = fresh_sections["results"]["section_8_safety_checks"]
    check(
        safety["checks_added_beyond_appendix_a"] == 3 and safety["all_four_checks_passed"],
        "all four Section 8.1 safety checks pass, three of them absent from Appendix A",
    )
    b3 = fresh_sections["results"]["section_8_boundary_3"]
    check(
        b3["high_k_did_not_force_quarantine"] and b3["policy_violation_quarantined_despite_low_k"],
        "Boundary 3 holds in both directions (high K does not quarantine; policy violation does)",
    )

    # ---------------------------------------------------------------- 3
    section("3. Ledger: real signatures and publicly verifiable equivocation")
    fresh_ledger = run_ledger_suite()
    check(fresh_ledger["all_faults_detected"], f"all {fresh_ledger['faults_injected']} ledger fault classes detected")
    check(fresh_ledger["all_faults_correctly_classified"], "each fault is classified as itself, not merely detected")
    check(fresh_ledger["equivocation_not_falsely_reported"], "a clean ledger reports no equivocation")
    check(fresh_ledger["every_fallback_trigger_halts_writes"], "every declared fallback trigger halts authoritative writes")
    check(fresh_ledger["clean_permits_writes"], "a clean ledger on the fast path permits writes (non-vacuous)")

    # Build equivocation and verify the evidence with public keys only.
    node = derive_identity("verify-node", seed="v3-verify")
    ledger = IdentityLedger()
    first = ledger.append(node, {"binding": "A"}, nonce="n1")
    second = ledger.append(
        node, {"binding": "B"}, nonce="n2", sequence=first.sequence, counter=first.counter,
        previous_digest=first.previous_digest,
    )
    evidence = ledger.detect_equivocation()
    check(len(evidence) == 1, "equivocation detected exactly once for one conflicting pair")
    public_key = node.public_key_hex
    both_verify = verify(public_key, first.signing_body(), first.signature) and verify(
        public_key, second.signing_body(), second.signature
    )
    check(both_verify, "both conflicting entries verify against the public key alone")
    check(
        digest(first.signing_body()) != digest(second.signing_body()),
        "the two signed bodies genuinely differ, so this is equivocation and not a duplicate",
    )
    # A tampered signature must not verify.
    tampered = second.signature[:-2] + ("00" if second.signature[-2:] != "00" else "11")
    check(
        not verify(public_key, second.signing_body(), tampered),
        "a tampered signature fails verification (signatures are real, not decorative)",
    )
    check(
        provenance["cryptography"]["signature_scheme"].startswith("Ed25519"),
        "provenance records the signature scheme as Ed25519",
    )
    check(
        fresh_ledger["scope_demonstration"]["ledger_validity_implies_identity_truth"] is False,
        "a valid non-equivocating ledger can still record a wrong identity binding",
    )

    # ---------------------------------------------------------------- 4
    section("4. Attestation: every injection caught by its intended check")
    fresh_attest = run_attestation_suite()
    check(fresh_attest["baseline_accepted"], "a valid quote is accepted (non-vacuous)")
    check(fresh_attest["all_injections_fail_closed"], f"all {fresh_attest['injection_cases_run']} injections fail closed")
    expected_check = {
        "invalid_signature": "signature_valid",
        "expired_quote": "quote_not_expired",
        "modified_measurement": "signature_valid",
        "unlisted_measurement_correctly_signed": "measurement_in_allowlist",
        "replayed_nonce": "nonce_matches_challenge",
        "revoked_platform_key": "signer_not_revoked",
        "downgraded_tcb_version": "tcb_version_at_or_above_minimum",
    }
    for name, expected in expected_check.items():
        failed = fresh_attest["injection_cases"][name]["failed_checks"]
        check(expected in failed, f"{name} caught by {expected}", f"(got {failed})")
    check(
        systems["attestation"]["hardware_root_of_trust_present"] is False,
        "no hardware root of trust is claimed",
    )
    check(
        systems["attestation"]["attestation_bound_database_keys_claimed"] is False,
        "the manuscript's conditional on attestation-bound database keys is honoured",
    )

    # ---------------------------------------------------------------- 5
    section("5. Consensus: 3f+1 arithmetic re-derived by hand")
    for f in range(1, 6):
        n = required_replicas(f)
        check(n == 3 * f + 1 and quorum_size(f) == 2 * f + 1, f"f={f}: n={n}, quorum={quorum_size(f)}")
        # Two quorums of 2f+1 in n=3f+1 intersect in at least f+1 replicas, so with
        # at most f Byzantine at least one correct replica is in both. Safety holds.
        intersection = 2 * quorum_size(f) - n
        check(intersection == f + 1, f"f={f}: quorum intersection is f+1 = {intersection}")
        within = analyse_round(RoundConfig(n=n, f_declared=f, byzantine=f))
        check(within["safety_holds"], f"f={f}: safety holds at exactly f Byzantine faults")
        beyond = analyse_round(RoundConfig(n=n, f_declared=f, byzantine=f + 1))
        check(not beyond["safety_holds"], f"f={f}: safety is violable at f+1, so the bound is tight")
        check(
            beyond["authoritative_writes_permitted"] is False,
            f"f={f}: no authoritative write is permitted when safety is at risk",
        )
        short = analyse_round(RoundConfig(n=n - 1, f_declared=f, byzantine=0))
        check(
            short["halt_reason"] == "replica_population_below_3f_plus_1",
            f"f={f}: n={n - 1} halts with the below-threshold reason",
        )
    check(
        systems["consensus"]["analysis_method"].startswith("exhaustive"),
        "the consensus analysis is exhaustive over the model, not sampled",
    )

    # ---------------------------------------------------------------- 6
    section("6. Enclave: is the spectral-moment half of the certificate load-bearing?")
    fresh_enclave = run_enclave_suite()
    check(fresh_enclave["honest_solver_accepted"], "an honest dense solver is accepted")
    check(fresh_enclave["all_forgeries_rejected"], f"all {fresh_enclave['forgeries_run']} forgery classes rejected")
    under = fresh_enclave["forgery_results"].get("under_claimed_dimension_hiding_obstruction")
    check(under is not None, "the obstruction-hiding forgery was exercised")
    if under is not None:
        check(
            under["failed_checks"] == ["spectral_moment_upper_bound"],
            "the obstruction-hiding forgery is caught ONLY by the spectral-moment check",
            f"(failed: {under['failed_checks']})",
        )
    # Prove the residual half alone would pass it: drop a true kernel column and
    # check the residual and orthogonality conditions directly.
    laplacian = scalable_cone_laplacian(60, (3, 17, 41))
    solution = external_dense_solve(laplacian)
    trimmed = solution["claimed_basis"][:, :-1]
    residuals = [float(np.linalg.norm(laplacian @ trimmed[:, c])) for c in range(trimmed.shape[1])]
    gram_error = float(np.linalg.norm(trimmed.T @ trimmed - np.eye(trimmed.shape[1])))
    check(
        max(residuals) <= RESIDUAL_TOLERANCE and gram_error <= 1e-9,
        f"the residual half alone accepts the hidden-obstruction basis "
        f"(worst residual {max(residuals):.2e}) — so the moment half is not decorative",
    )
    check(
        fresh_enclave["resource_comparison"]["enclave_fits_budget"]
        and fresh_enclave["resource_comparison"]["dense_exceeds_budget"],
        "the sparse path fits the declared budget and the dense path does not",
    )
    ratio = fresh_enclave["resource_comparison"]["flop_ratio_dense_over_sparse"]
    check(ratio > 1000, f"dense/sparse flop ratio is {ratio:.0f}x")
    check(
        fresh_enclave["scope"].startswith("No TEE"),
        "the enclave module states plainly that there is no TEE",
    )

    # ---------------------------------------------------------------- 7
    section("7. Rollback conformance verified by store diff")
    fresh_txn = run_rollback_conformance_suite()
    forced = fresh_txn["forced_atomic_submission"]
    check(forced["committed"] is False, "the bundle containing a corrupted order commits nothing")
    check(forced["store_state_identical"], "the store state is byte-identical after the rejection")
    check(fresh_txn["no_partial_commit_from_rejected_bundle"], "no entry of the rejected bundle appears in the store")
    check(fresh_txn["unrelated_resources_unchanged"], "resources outside the bundle are unchanged")
    check(forced["operation_outcome"]["issue"][0]["severity"] == "error", "an error-severity OperationOutcome is returned")
    check(
        forced["operation_outcome"]["issue"][0]["code"] == "business-rule",
        "the OperationOutcome code is business-rule",
    )
    check(forced["audit_event_recorded"], "the failed attempt is captured in the audit path")
    check(
        fresh_txn["independent_work_progressed"] and fresh_txn["held_back_work_not_silently_dropped"],
        "independent work progressed and held-back work was rerouted rather than dropped",
    )
    check(
        fresh_txn["atomicity_and_liveness_both_hold"],
        "atomicity and liveness hold simultaneously, which is the hard part",
    )

    # ---------------------------------------------------------------- 8
    section("8. Receipt coherence and replay")
    fresh_receipts = run_receipt_suite()
    check(fresh_receipts["receipt_coherence_holds"], "receipt coherence holds")
    check(fresh_receipts["chain_verification"]["chain_valid"], "the receipt chain verifies")
    check(fresh_receipts["every_decision_fully_receipted"], "every decision has its required receipt set")
    check(fresh_receipts["replay_reproduces_every_decision"], "replay from receipts reproduces every decision")
    check(fresh_receipts["tamper_detection"]["tampering_detected"], "a tampered receipt is detected")
    check(
        fresh_receipts["review_surface_omits_model_confidence"],
        "no receipt carries a model confidence number in its review surface",
    )
    check(fresh_receipts["all_receipts_version_pinned"], "every receipt pins policy and terminology versions")
    check(
        len(fresh_receipts["review_surface_forbidden_fields"]) == 0,
        "no forbidden review-surface field is present",
    )

    # ---------------------------------------------------------------- 9
    section("9. Cone certificate and the zero-knowledge boundary")
    fresh_cert = run_cone_certificate_suite()
    check(fresh_cert["honest_certificates_accepted"], "honest certificates accepted for both vanishing and non-vanishing H^1")
    check(fresh_cert["all_forgeries_rejected"], "every false cohomology claim rejected")
    check(
        fresh_cert["results"]["false_h1_vanishing_claim"]["failed_clauses"],
        "the false H^1 = 0 claim fails named clauses rather than being silently accepted",
    )
    check(fresh_cert["zero_knowledge_implemented"] is False, "zero knowledge is not implemented")
    check(fresh_cert["zero_knowledge_claimed"] is False, "zero knowledge is not claimed")
    check(fresh_cert["commitment_is_binding"] and fresh_cert["commitment_is_blinded"], "the commitment is binding and blinded")
    check(
        fresh_cert["policy_version_binding_changes_public_input"],
        "changing the policy version changes the public input digest, so certificates cannot be replayed across policies",
    )

    # ---------------------------------------------------------------- 10
    section("10. Infrastructure domain: denominators re-derived")
    population = generate_population(512)
    severe = [w for w in population["witnesses"] if w.is_severe]
    clean = [w for w in population["witnesses"] if w.is_clean]
    caught = sum(1 for w in severe if required_action(w)[0] not in ADMITTING_ACTIONS)
    false_conflicts = sum(1 for w in clean if required_action(w)[0] not in ADMITTING_ACTIONS)
    check(
        len(severe) == infra_doc["severe_population"],
        f"severe population re-derived as {len(severe)}",
    )
    check(caught == len(severe), f"all {len(severe)} severe contradictions caught independently")
    check(
        approx(caught / len(severe), infra_doc["severe_contradiction_sensitivity"]),
        "sensitivity matches the artifact",
    )
    check(false_conflicts == 0, f"zero false conflicts over {len(clean)} conflict-free records")
    check(
        set(population["injected_classes"]) == set(SEVERE_CLASSES),
        f"all {len(SEVERE_CLASSES)} severe classes are represented in the population",
    )
    check(
        infra_doc["portability"]["architecture_changed_for_new_domain"] is False
        and infra_doc["portability"]["domain_neutral_module_count"] == 8,
        "8 domain-neutral modules reused with no architectural change",
    )
    check(
        infra_doc["scope"].startswith("Synthetic"),
        "the infrastructure result is scoped to synthetic records",
    )

    # ---------------------------------------------------------------- 11
    section("11. Claim register integrity and coverage")
    claims = register_doc["claims"]
    summary = register_doc["summary"]
    ids = [claim["id"] for claim in claims]
    check(len(ids) == len(set(ids)), "claim ids are unique")
    check(
        all(claim["met"] in (True, False, None) for claim in claims),
        "every met value is exactly True, False or None",
    )
    check(
        all(claim["met"] is not None for claim in claims if claim["class"] != "OUT_OF_SCOPE"),
        "no testable claim is left unresolved (a broken resolver cannot masquerade as out-of-scope)",
    )
    check(
        all(claim["met"] is None for claim in claims if claim["class"] == "OUT_OF_SCOPE"),
        "no out-of-scope claim is reported as met",
    )
    unmet = [claim for claim in claims if claim["met"] is False]
    check(
        all(claim["class"] == "ERRATUM" for claim in unmet),
        "the only unmet claims are errata against the manuscript",
        f"({[claim['id'] for claim in unmet]})",
    )
    # Section coverage: every main.pdf section and appendix must appear.
    covered = {claim["section"].split(".")[0].split(" ")[0] for claim in claims}
    required_sections = {str(index) for index in range(1, 13)} | {"A", "B"}
    missing = sorted(required_sections - covered)
    check(not missing, "every main.pdf section 1-12 plus appendices A and B is represented", f"(missing {missing})")
    check(
        summary["met"] + summary["unmet"] + summary["out_of_scope"] == summary["total_claims"],
        "register counts reconcile",
    )
    check(
        summary["testable_in_this_environment"] == summary["met"] + summary["unmet"],
        "testable count reconciles with met plus unmet",
    )
    check(summary["out_of_scope"] == 3, f"exactly 3 claims are out of scope ({summary['out_of_scope_ids']})")
    check(summary["errata"] == 1, f"exactly 1 erratum ({summary['erratum_ids']})")

    # ---------------------------------------------------------------- 12
    section("12. Scope declarations and checksums")
    scope = provenance["execution_scope"]
    for key in (
        "language_models_executed",
        "provider_calls",
        "held_out_references_read",
    ):
        check(scope[key] == 0, f"{key} == 0")
    for key in (
        "tee_present",
        "bft_cluster_present",
        "fhir_server_present",
        "hardware_root_of_trust_present",
        "zero_knowledge_proof_system_present",
        "real_clinical_data_used",
        "real_infrastructure_data_used",
    ):
        check(scope[key] is False, f"{key} is False")
    check(scope["synthetic_data_only"] is True, "synthetic_data_only is True")
    check(provenance["verifier"]["modified_for_v3"] is False, "the v0.1 verifier was not modified")
    manifest_lines = (V3 / "SHA256SUMS").read_text(encoding="utf-8").strip().splitlines()
    recorded = {name: value for value, name in (line.split("  ", 1) for line in manifest_lines)}
    on_disk = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in V3.glob("*")
        if path.name != "SHA256SUMS"
    }
    check(set(recorded) == set(on_disk), "the checksum manifest covers exactly the artifacts present")
    check(all(recorded[name] == value for name, value in on_disk.items()), "every artifact digest matches")

    # ---------------------------------------------------------------- 13
    section("13. Numbers quoted in the v3 report")
    report_path = ROOT / "docs/betal/GBI_DCSE_V3_FULL_EVALUATION.md"
    if not report_path.exists():
        check(False, "v3 report present", f"({report_path} missing)")
    else:
        report = report_path.read_text(encoding="utf-8")
        compact = "".join(report.split())
        for needle, label, haystack in (
            (str(summary["total_claims"]), "total claim count", report),
            (f"{summary['met']}/{summary['testable_in_this_environment']}", "met over testable", compact),
            (str(fresh_enclave["matrix_size"]), "enclave matrix size", report),
            (f"{ratio:,.0f}", "flop ratio", report),
            (str(fresh_attest["injection_cases_run"]), "attestation injection count", report),
            (str(systems["consensus"]["configurations_analysed"]), "consensus configuration count", report),
            (str(fresh_ledger["faults_injected"]), "ledger fault class count", report),
            (str(fresh_enclave["forgeries_run"]), "enclave forgery class count", report),
            ("0.326472", "box-wide epsilon", report),
            ("1.922661", "K_O", report),
            ("1.627658", "appendix entropy in bits", report),
            (f"{len(severe)}", "infrastructure severe population", report),
            (str(len(clean)), "infrastructure clean population", report),
        ):
            check(needle in haystack, f"report quotes {label}: '{needle}'")
        check(
            f"**{CHECKS + 1} checks, 0 failures.**" in report,
            f"report documents the current total check count ({CHECKS + 1})",
        )

    print(f"\n{'=' * 72}")
    print(f"checks run: {CHECKS}    failures: {len(FAILURES)}")
    if FAILURES:
        for failure in FAILURES:
            print(f"  - {failure}")
        return 1
    print("ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
