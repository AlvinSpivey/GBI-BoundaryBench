#!/usr/bin/env python3
"""Execute the full GBI-DCSE v3 evaluation and write public-safe artifacts.

v0.2 asked whether the benchmark could be tuned. v2 scored the GBI admission
boundary. v3 adds the DCSE protocol layer and closes the remaining main.pdf
claims, then records the result as an auditable claim register.

Run from the repository root:

    PYTHONPATH=src python3 scripts/run_gbi_dcse_v3_scorecard.py

Prerequisite: the v2 artifacts must exist, because v3 reuses their measurements
for the GBI half rather than recomputing them.

No language model is executed. No provider is contacted. No TEE, BFT cluster or
FHIR server is present. All data is synthetic and non-clinical.
"""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

from boundarybench.dcse.attestation import run_attestation_suite
from boundarybench.dcse.cone_certificate import run_cone_certificate_suite
from boundarybench.dcse.consensus import run_consensus_suite
from boundarybench.dcse.enclave import run_enclave_suite
from boundarybench.dcse.infrastructure import run_infrastructure_domain_suite
from boundarybench.dcse.ledger import run_ledger_suite
from boundarybench.dcse.protocol import run_protocol_inventory
from boundarybench.dcse.receipts import run_receipt_suite
from boundarybench.dcse.transaction import run_rollback_conformance_suite
from boundarybench.gbi.appendix_a import run_report, run_self_check
from boundarybench.gbi.claims import run_all_section_claims
from boundarybench.gbi.register import REGISTER_VERSION, build_register, summarise

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts/public_results/gbi_dcse_v3"
V2 = ROOT / "artifacts/public_results/gbi_v2"

RUN_PLAN = "gbi-dcse-v3-evaluation-plan-v3.0.0"
CONTRACT = "benchmark-contract-v0.1"


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    print(f"  wrote {path.relative_to(ROOT)}")


def main() -> int:
    print("GBI-DCSE v3 evaluation")
    if not (V2 / "table3_scorecard.json").exists():
        print("  ERROR: v2 artifacts missing. Run scripts/run_gbi_v2_scorecard.py first.")
        return 1
    OUT.mkdir(parents=True, exist_ok=True)

    results: dict[str, Any] = {}

    print("[1/8] Appendix A reference implementation")
    results["appendix_a_self_check"] = run_self_check()
    results["appendix_a_report"] = run_report()
    check, report = results["appendix_a_self_check"], results["appendix_a_report"]
    print(f"  self-check {check['assertions_passed']}/{check['assertions_run']} assertions passed")
    print(f"  published values {report['comparisons_agreeing']}/{report['comparisons_run']} reproduced")
    _write_json(OUT / "appendix_a.json", {"self_check": check, "report": report})

    print("[2/8] GBI Sections 2, 3, 4, 6.2, 8")
    results["gbi_sections"] = run_all_section_claims()
    print(f"  {results['gbi_sections']['claims_met']}/{results['gbi_sections']['claims_tested']} section claims met")
    _write_json(OUT / "gbi_section_claims.json", results["gbi_sections"])

    print("[3/8] DCSE protocol inventory (Sections 5, 9.1, 9.2, 10, 12)")
    results["protocol"] = run_protocol_inventory()
    print(f"  all structural claims met: {results['protocol']['all_structural_claims_met']}")
    _write_json(OUT / "protocol_inventory.json", results["protocol"])

    print("[4/8] DCSE ledger L, with fault injection (Sections 9.1, 9.4)")
    results["ledger_suite"] = run_ledger_suite()
    ledger = results["ledger_suite"]
    print(
        f"  {ledger['faults_injected']} fault classes injected; all detected: {ledger['all_faults_detected']}; "
        f"all correctly classified: {ledger['all_faults_correctly_classified']}"
    )
    print(f"  every fallback trigger halts authoritative writes: {ledger['every_fallback_trigger_halts_writes']}")
    _write_json(OUT / "ledger_suite.json", ledger)

    print("[5/8] Appendix B.1 systems validation")
    results["attestation"] = run_attestation_suite()
    results["consensus"] = run_consensus_suite()
    results["transaction"] = run_rollback_conformance_suite()
    attest, consensus, txn = results["attestation"], results["consensus"], results["transaction"]
    print(f"  attestation: {attest['injection_cases_run']} injections, all fail closed: {attest['all_injections_fail_closed']}")
    print(f"  consensus: {consensus['configurations_analysed']} configurations, all invariants hold: {consensus['all_invariants_hold']}")
    print(f"  rollback conformance holds: {txn['rollback_conformance_holds']}; atomicity+liveness: {txn['atomicity_and_liveness_both_hold']}")
    _write_json(
        OUT / "systems_validation.json",
        {"attestation": attest, "consensus": consensus, "rollback_conformance": txn},
    )

    print("[6/8] enclave sparse certification and the cone certificate (Sections 9.3, 9.5)")
    results["enclave"] = run_enclave_suite()
    results["cone_certificate"] = run_cone_certificate_suite()
    enclave, cert = results["enclave"], results["cone_certificate"]
    print(
        f"  enclave: n={enclave['matrix_size']}, {enclave['forgeries_run']} forgeries all rejected: "
        f"{enclave['all_forgeries_rejected']}; flop ratio dense/sparse "
        f"{enclave['resource_comparison']['flop_ratio_dense_over_sparse']:.0f}x"
    )
    print(f"  Section 9.5 precondition met: {cert['precondition_of_section_9_5_met']}; ZK implemented: {cert['zero_knowledge_implemented']}")
    _write_json(OUT / "enclave_and_certificate.json", {"enclave": enclave, "cone_certificate": cert})

    print("[7/8] receipts and domain portability (Sections 9.2, 12; Table 1)")
    results["receipts"] = run_receipt_suite()
    results["infrastructure"] = run_infrastructure_domain_suite()
    receipts, infra = results["receipts"], results["infrastructure"]
    print(f"  receipt coherence holds: {receipts['receipt_coherence_holds']} ({receipts['receipts_emitted']} receipts)")
    print(
        f"  infrastructure domain: sensitivity {infra['severe_contradiction_sensitivity']}, "
        f"false conflict {infra['false_conflict_adjudication_rate']}, "
        f"portability supported: {infra['table_1_portability_claim_supported']}"
    )
    _write_json(OUT / "receipts.json", receipts)
    _write_json(OUT / "infrastructure_domain.json", infra)

    print("[8/8] claim register")
    for name, filename in (
        ("v2_scorecard", "table3_scorecard.json"),
        ("v2_targets", "target_runs.json"),
        ("v2_assertions", "appendix_b1_assertions.json"),
        ("v2_conformance", "boundary_conformance.json"),
    ):
        results[name] = json.loads((V2 / filename).read_text(encoding="utf-8"))

    register = build_register(results)
    summary = summarise(register)
    print(
        f"  {summary['total_claims']} claims enumerated; {summary['met']}/{summary['testable_in_this_environment']} "
        f"testable claims met; {summary['out_of_scope']} out of scope; {summary['errata']} errata"
    )
    if summary["unmet_ids"]:
        print(f"  UNMET: {summary['unmet_ids']}")
    if summary["out_of_scope_ids"]:
        print(f"  OUT OF SCOPE: {summary['out_of_scope_ids']}")

    _write_json(
        OUT / "claim_register.json",
        {
            "schema_version": "boundarybench.gbi_dcse_claim_register.v1",
            "register_version": REGISTER_VERSION,
            "run_plan": RUN_PLAN,
            "benchmark_contract": CONTRACT,
            "summary": summary,
            "claims": register,
        },
    )

    with (OUT / "claim_register.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["id", "section", "class", "met", "claim", "note"])
        for claim in register:
            writer.writerow(
                [
                    claim["id"],
                    claim["section"],
                    claim["class"],
                    "" if claim["met"] is None else claim["met"],
                    claim["claim"],
                    claim["note"] or "",
                ]
            )
    print(f"  wrote {(OUT / 'claim_register.csv').relative_to(ROOT)}")

    provenance = {
        "schema_version": "boundarybench.gbi_dcse_v3_provenance.v1",
        "run_plan": RUN_PLAN,
        "benchmark_contract": CONTRACT,
        "builds_on": {
            "v0_2_search": "artifacts/public_results/v0_2",
            "v2_scorecard": "artifacts/public_results/gbi_v2",
        },
        "component_versions": {
            "claim_register": REGISTER_VERSION,
            "appendix_a_port": results["appendix_a_report"]["appendix_a_version"],
            "gbi_section_claims": results["gbi_sections"]["claims_version"],
            "dcse_ledger": ledger["ledger_version"],
            "dcse_attestation": attest["attestation_version"],
            "dcse_consensus": consensus["consensus_version"],
            "dcse_enclave": enclave["enclave_version"],
            "dcse_transaction": txn["transaction_version"],
            "dcse_receipts": receipts["receipts_version"],
            "dcse_cone_certificate": cert["cone_certificate_version"],
            "dcse_infrastructure_domain": infra["infrastructure_version"],
            "dcse_protocol_inventory": results["protocol"]["protocol_version"],
        },
        "execution_scope": {
            "language_models_executed": 0,
            "provider_calls": 0,
            "held_out_references_read": 0,
            "tee_present": False,
            "bft_cluster_present": False,
            "fhir_server_present": False,
            "hardware_root_of_trust_present": False,
            "zero_knowledge_proof_system_present": False,
            "real_clinical_data_used": False,
            "real_infrastructure_data_used": False,
            "synthetic_data_only": True,
        },
        "cryptography": {
            "signature_scheme": "Ed25519 via the cryptography package",
            "digest": "SHA-256",
            "note": "Real signatures, so equivocation evidence is publicly verifiable.",
        },
        "verifier": {
            "source": "boundarybench.verification (v0.1 Programmatic Verification Engine)",
            "modified_for_v3": False,
        },
        "reproduce": [
            "PYTHONPATH=src python3 scripts/run_betal_v0_2_search.py",
            "PYTHONPATH=src python3 scripts/run_gbi_v2_scorecard.py",
            "PYTHONPATH=src python3 scripts/run_gbi_dcse_v3_scorecard.py",
            "PYTHONPATH=src python3 scripts/verify_gbi_dcse_v3_scorecard.py",
        ],
    }
    _write_json(OUT / "PROVENANCE.json", provenance)

    lines = []
    for path in sorted(OUT.glob("*")):
        if path.name == "SHA256SUMS":
            continue
        lines.append(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}")
    (OUT / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"  wrote {(OUT / 'SHA256SUMS').relative_to(ROOT)}")
    print("done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
