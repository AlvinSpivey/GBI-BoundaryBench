"""Section 9.5: the consistency certificate, and what it can and cannot claim.

Section 9.5 states a schematic goal and, importantly, a *precondition*:

    "exists w : VerifyConeCertificate(c, w) = 1  and  Policy(w) = pass"
    "If vanishing of a particular cohomology group is part of the certificate, that
    property must be encoded by a concrete finite computation or residual check;
    the expression H^1(Cone phi) = 0 is not itself a witness predicate."

The precondition is the testable part and it is what this module implements:
``VerifyConeCertificate`` is a concrete, finite, terminating predicate over an
explicit witness, and the cohomology claim is encoded as a rank-plus-residual check
rather than as an abstract statement.

**On zero knowledge: it is not implemented, and it is not claimed.** The manuscript
itself frames the ZK layer as a future extension ("A future deployment may attach a
zero-knowledge proof"). What is here is a hiding, binding commitment plus a finite
verification predicate — an honest building block, and a strictly weaker object
than a zero-knowledge proof. Calling this ZK would be the single easiest way to
overstate the whole framework, so the module reports
``zero_knowledge_implemented: False`` and the scorecard treats §9.5 as
precondition-met with the proof system out of scope.

The public input ``c`` binds the transaction digest, the policy version and the
verification parameters, exactly as the manuscript specifies, so a certificate
cannot be replayed against a different transaction or a different policy.
"""

from __future__ import annotations

from dataclasses import dataclass
import secrets
from typing import Any, Sequence

import numpy as np

from boundarybench.dcse.crypto import digest, digest_bytes

CONE_CERTIFICATE_VERSION = "dcse-cone-certificate-v3.0"

RESIDUAL_TOLERANCE = 1e-8


@dataclass(frozen=True)
class PublicInput:
    """The public input c of Section 9.5."""

    transaction_digest: str
    policy_version: str
    laplacian_digest: str
    tolerance: float
    claimed_h1_vanishes: bool
    claimed_obstruction_dimension: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "transaction_digest": self.transaction_digest,
            "policy_version": self.policy_version,
            "laplacian_digest": self.laplacian_digest,
            "tolerance": self.tolerance,
            "claimed_h1_vanishes": self.claimed_h1_vanishes,
            "claimed_obstruction_dimension": self.claimed_obstruction_dimension,
        }

    def digest(self) -> str:
        return digest(self.as_dict())


@dataclass(frozen=True)
class Witness:
    """The private witness w: an explicit basis plus the full spectrum."""

    basis: np.ndarray
    spectrum: np.ndarray
    blinding_hex: str

    def commitment(self) -> str:
        payload = (
            np.ascontiguousarray(self.basis, dtype=float).tobytes()
            + np.ascontiguousarray(self.spectrum, dtype=float).tobytes()
            + bytes.fromhex(self.blinding_hex)
        )
        return digest_bytes(payload)


def make_witness(basis: np.ndarray, spectrum: np.ndarray) -> Witness:
    return Witness(
        basis=np.asarray(basis, dtype=float),
        spectrum=np.asarray(spectrum, dtype=float),
        blinding_hex=secrets.token_bytes(32).hex(),
    )


def laplacian_public_digest(laplacian: np.ndarray) -> str:
    """A public, sparse-computable fingerprint of the operator.

    Trace, Frobenius norm and size are all O(nnz) to compute and are exactly the
    quantities the enclave's moment identities use, so publishing them does not
    hand a verifier any dense work.
    """

    return digest(
        {
            "size": int(laplacian.shape[0]),
            "trace": round(float(np.trace(laplacian)), 12),
            "frobenius_squared": round(float(np.sum(laplacian * laplacian)), 12),
        }
    )


def verify_cone_certificate(
    public_input: PublicInput,
    witness: Witness,
    laplacian: np.ndarray,
) -> dict[str, Any]:
    """``VerifyConeCertificate(c, w)``: a concrete, finite, terminating predicate.

    Every clause is a finite numerical check. In particular the cohomology claim is
    encoded as:

    * ``H^1(Cone phi) = 0``  <=>  the count of eigenvalues within tolerance of zero
      equals the claimed obstruction dimension, and that dimension is zero;
    * the claimed basis genuinely spans a near-null space (residual check);
    * the claimed spectrum genuinely belongs to this operator (moment identities).

    No clause requires evaluating an abstract predicate about a cohomology group.
    """

    clauses: dict[str, bool] = {}

    clauses["operator_binding"] = (
        laplacian_public_digest(laplacian) == public_input.laplacian_digest
    )

    spectrum = witness.spectrum
    size = int(laplacian.shape[0])
    clauses["spectrum_length_matches_operator"] = spectrum.size == size

    trace = float(np.trace(laplacian))
    frobenius_squared = float(np.sum(laplacian * laplacian))
    clauses["first_moment_identity"] = (
        abs(float(spectrum.sum()) - trace) <= 1e-9 * max(1.0, abs(trace))
    )
    clauses["second_moment_identity"] = (
        abs(float(np.sum(spectrum**2)) - frobenius_squared)
        <= 1e-9 * max(1.0, abs(frobenius_squared))
    )

    counted = int(np.sum(np.abs(spectrum) <= public_input.tolerance))
    clauses["dimension_count_matches_claim"] = counted == public_input.claimed_obstruction_dimension

    basis = witness.basis
    if basis.size:
        residuals = [
            float(np.linalg.norm(laplacian @ basis[:, column]))
            for column in range(basis.shape[1])
        ]
        clauses["basis_residuals_within_tolerance"] = max(residuals) <= public_input.tolerance
        gram = basis.T @ basis
        clauses["basis_orthonormal"] = bool(
            np.allclose(gram, np.eye(basis.shape[1]), atol=1e-9)
        )
        clauses["basis_width_matches_claim"] = (
            basis.shape[1] == public_input.claimed_obstruction_dimension
        )
    else:
        clauses["basis_residuals_within_tolerance"] = True
        clauses["basis_orthonormal"] = True
        clauses["basis_width_matches_claim"] = public_input.claimed_obstruction_dimension == 0

    # The cohomology claim, encoded finitely.
    h1_vanishes_in_fact = counted == 0
    clauses["h1_claim_matches_finite_computation"] = (
        public_input.claimed_h1_vanishes == h1_vanishes_in_fact
    )

    accepted = all(clauses.values())
    return {
        "public_input_digest": public_input.digest(),
        "witness_commitment": witness.commitment(),
        "clauses": clauses,
        "failed_clauses": [name for name, ok in clauses.items() if not ok],
        "accepted": accepted,
        "h1_vanishes_in_fact": h1_vanishes_in_fact,
        "encoded_as": "finite_rank_and_residual_check_not_an_abstract_predicate",
        "clause_count": len(clauses),
    }


def run_cone_certificate_suite() -> dict[str, Any]:
    """Honest certificates accepted; every false cohomology claim rejected."""

    from boundarybench.dcse.enclave import external_dense_solve, scalable_cone_laplacian

    # Case A: a complex with genuine obstruction, so H^1 does not vanish.
    obstructed = scalable_cone_laplacian(24, (2, 11))
    obstructed_solution = external_dense_solve(obstructed)
    # Case B: a fully consistent complex, so the obstruction space is trivial.
    consistent = scalable_cone_laplacian(24, ())
    consistent_solution = external_dense_solve(consistent)

    def certificate_for(
        laplacian: np.ndarray,
        solution: dict[str, Any],
        *,
        transaction: str,
        policy_version: str = "1.1",
        claim_vanishes: bool | None = None,
        claim_dimension: int | None = None,
    ) -> tuple[PublicInput, Witness]:
        dimension = solution["claimed_dimension"] if claim_dimension is None else claim_dimension
        vanishes = (dimension == 0) if claim_vanishes is None else claim_vanishes
        public_input = PublicInput(
            transaction_digest=digest({"transaction": transaction}),
            policy_version=policy_version,
            laplacian_digest=laplacian_public_digest(laplacian),
            tolerance=RESIDUAL_TOLERANCE,
            claimed_h1_vanishes=vanishes,
            claimed_obstruction_dimension=dimension,
        )
        witness = make_witness(solution["claimed_basis"], solution["claimed_spectrum"])
        return public_input, witness

    results: dict[str, Any] = {}

    ci, wi = certificate_for(consistent, consistent_solution, transaction="tx-clean")
    results["honest_consistent_h1_vanishes"] = verify_cone_certificate(ci, wi, consistent)

    co, wo = certificate_for(obstructed, obstructed_solution, transaction="tx-obstructed")
    results["honest_obstructed_h1_does_not_vanish"] = verify_cone_certificate(co, wo, obstructed)

    # Forgery 1: claim H^1 = 0 when it does not.
    false_claim = PublicInput(
        transaction_digest=co.transaction_digest,
        policy_version=co.policy_version,
        laplacian_digest=co.laplacian_digest,
        tolerance=co.tolerance,
        claimed_h1_vanishes=True,
        claimed_obstruction_dimension=0,
    )
    results["false_h1_vanishing_claim"] = verify_cone_certificate(false_claim, wo, obstructed)

    # Forgery 2: replay a valid certificate against a different operator.
    results["operator_substitution"] = verify_cone_certificate(ci, wi, obstructed)

    # Forgery 3: replay against a different policy version. The public input digest
    # changes, so a signature over c would not verify; the binding is shown here by
    # the digest differing rather than by a clause failing.
    other_policy = PublicInput(
        transaction_digest=ci.transaction_digest,
        policy_version="9.9",
        laplacian_digest=ci.laplacian_digest,
        tolerance=ci.tolerance,
        claimed_h1_vanishes=ci.claimed_h1_vanishes,
        claimed_obstruction_dimension=ci.claimed_obstruction_dimension,
    )
    policy_binding_differs = other_policy.digest() != ci.digest()

    # Forgery 4: fabricate a spectrum with no near-zero eigenvalues.
    fabricated = make_witness(
        np.zeros((obstructed.shape[0], 0)), np.abs(obstructed_solution["claimed_spectrum"]) + 1.0
    )
    results["fabricated_spectrum"] = verify_cone_certificate(false_claim, fabricated, obstructed)

    # Commitment properties: binding (different witness -> different commitment)
    # and hiding (the commitment reveals nothing about the basis by construction,
    # demonstrated here only as blinding freshness, which is all a hash commitment
    # gives).
    again = make_witness(obstructed_solution["claimed_basis"], obstructed_solution["claimed_spectrum"])
    commitment_binding = wo.commitment() != fabricated.commitment()
    commitment_blinding_fresh = wo.commitment() != again.commitment()

    honest_ok = (
        results["honest_consistent_h1_vanishes"]["accepted"]
        and results["honest_obstructed_h1_does_not_vanish"]["accepted"]
    )
    forgeries_rejected = all(
        not results[name]["accepted"]
        for name in ("false_h1_vanishing_claim", "operator_substitution", "fabricated_spectrum")
    )

    return {
        "schema_version": "boundarybench.dcse_cone_certificate_suite.v1",
        "cone_certificate_version": CONE_CERTIFICATE_VERSION,
        "consistent_complex_obstruction_dimension": consistent_solution["claimed_dimension"],
        "obstructed_complex_obstruction_dimension": obstructed_solution["claimed_dimension"],
        "results": {
            name: {
                "accepted": verdict["accepted"],
                "failed_clauses": verdict["failed_clauses"],
                "h1_vanishes_in_fact": verdict["h1_vanishes_in_fact"],
            }
            for name, verdict in results.items()
        },
        "clause_count": results["honest_consistent_h1_vanishes"]["clause_count"],
        "honest_certificates_accepted": honest_ok,
        "all_forgeries_rejected": forgeries_rejected,
        "policy_version_binding_changes_public_input": policy_binding_differs,
        "commitment_is_binding": commitment_binding,
        "commitment_is_blinded": commitment_blinding_fresh,
        "cohomology_claim_encoded_finitely": True,
        "verify_predicate_is_total_and_terminating": True,
        "precondition_of_section_9_5_met": bool(
            honest_ok and forgeries_rejected and policy_binding_differs
        ),
        "zero_knowledge_implemented": False,
        "zero_knowledge_claimed": False,
        "scope": (
            "A binding, blinded commitment plus a finite verification predicate. This is "
            "strictly weaker than a zero-knowledge proof: a verifier who is given the "
            "witness learns it. The manuscript frames the ZK layer as a future "
            "extension, and it remains future work here."
        ),
    }
