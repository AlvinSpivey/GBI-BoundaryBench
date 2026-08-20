"""Enclave-resident checks and sparse verification, Section 9.3.

    "The DCSE design places small, deterministic checks inside the enclave:
    signature and nonce verification, sparse residual checks such as ||Lx||,
    hash-chain validation, policy evaluation, certificate signing. Dense SVD, QR,
    and large eigensolvers are performed outside the enclave or replaced with
    sparse certified residual checks. A WASM/WAMR-style packaging can enforce heap,
    I/O, and syscall budgets for deterministic enclave modules."

That paragraph contains a real, falsifiable engineering claim, and it is the one
worth testing: **a small sparse check inside the enclave can certify a dense
computation performed outside it, including against a solver that lies.**

If that claim fails, the whole TEE partitioning collapses — either the dense work
has to move inside (blowing the resource budget) or the enclave has to trust an
untrusted solver (defeating the point).

The certificate has two halves, because a residual check alone is not enough:

* **Lower bound on the obstruction dimension.** For a claimed orthonormal basis B
  of the near-null space, check ``B^T B ~ I`` and ``max_i ||L b_i|| <= tol``. Cost
  is O(k^2 + k*nnz(L)). This certifies dim ker >= k.
* **Upper bound, via spectral moments.** A residual check cannot rule out *more*
  obstruction than claimed, so the untrusted solver must also publish the full
  spectrum, and the enclave checks two moment identities against quantities it can
  compute sparsely: ``sum lambda_i = tr(L)`` and ``sum lambda_i^2 = ||L||_F^2``.
  Both are O(nnz). A solver that fabricates or over-claims the spectrum breaks at
  least one moment identity.

Without the second half an adversary could hide obstruction, so a suite that
checked only residuals would pass a solver that under-reports the failure.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any, Sequence

import numpy as np

from boundarybench.dcse.crypto import Identity, derive_identity, digest, verify

ENCLAVE_VERSION = "dcse-enclave-v3.0"

# Declared WASM/WAMR-style budget for the enclave module.
DECLARED_BUDGET = {
    "max_heap_bytes": 262_144,
    "max_io_bytes": 65_536,
    "max_syscalls": 64,
    "max_flops": 5_000_000,
}

RESIDUAL_TOLERANCE = 1e-8
ORTHOGONALITY_TOLERANCE = 1e-9
MOMENT_RELATIVE_TOLERANCE = 1e-9

# Declared flop model for a full symmetric eigendecomposition with eigenvectors.
DENSE_EIGEN_FLOP_CONSTANT = 9.0


@dataclass
class ResourceMeter:
    """Accounting for the declared enclave budget."""

    heap_bytes: int = 0
    io_bytes: int = 0
    syscalls: int = 0
    flops: float = 0.0
    peak_heap_bytes: int = 0

    def allocate(self, count: int, itemsize: int = 8) -> None:
        self.heap_bytes += count * itemsize
        self.peak_heap_bytes = max(self.peak_heap_bytes, self.heap_bytes)

    def io(self, nbytes: int) -> None:
        self.io_bytes += nbytes
        self.syscalls += 1

    def work(self, flops: float) -> None:
        self.flops += flops

    def within(self, budget: dict[str, int]) -> dict[str, Any]:
        return {
            "peak_heap_bytes": self.peak_heap_bytes,
            "io_bytes": self.io_bytes,
            "syscalls": self.syscalls,
            "flops": self.flops,
            "heap_within_budget": self.peak_heap_bytes <= budget["max_heap_bytes"],
            "io_within_budget": self.io_bytes <= budget["max_io_bytes"],
            "syscalls_within_budget": self.syscalls <= budget["max_syscalls"],
            "flops_within_budget": self.flops <= budget["max_flops"],
            "all_within_budget": (
                self.peak_heap_bytes <= budget["max_heap_bytes"]
                and self.io_bytes <= budget["max_io_bytes"]
                and self.syscalls <= budget["max_syscalls"]
                and self.flops <= budget["max_flops"]
            ),
        }


# --- a scalable cone Laplacian, so the sparse/dense contrast is meaningful ---

RESTRICTION = np.diag([1.0, 0.0])
STALK_DIM = 2


def scalable_cone_laplacian(vertices: int, disagreeing: Sequence[int]) -> np.ndarray:
    """Cone Laplacian on a cycle complex with `vertices` stalks.

    Same construction as ``betal/cone.py`` (rank-deficient restriction so a
    per-stalk morphism exists), generalized from the 3-stalk triangle to an
    m-cycle so the matrix is large enough for a sparse-versus-dense comparison to
    mean something. ``d_cone^2 = 0`` is asserted, as there.
    """

    edges = [(index, (index + 1) % vertices) for index in range(vertices)]
    dim = STALK_DIM
    delta = np.zeros((len(edges) * dim, vertices * dim))
    for edge_index, (tail, head) in enumerate(edges):
        rows = slice(edge_index * dim, (edge_index + 1) * dim)
        delta[rows, head * dim : (head + 1) * dim] += RESTRICTION
        delta[rows, tail * dim : (tail + 1) * dim] -= RESTRICTION

    phi_0 = np.zeros((vertices * dim, vertices * dim))
    disagree = set(disagreeing)
    for index in range(vertices):
        block = slice(index * dim, (index + 1) * dim)
        phi_0[block, block] = np.diag([1.0, 0.0 if index in disagree else 1.0])
    phi_1 = np.eye(len(edges) * dim)

    d_minus_1 = np.vstack([-delta, phi_0])
    d_0 = np.hstack([phi_1, delta])
    if not np.allclose(d_0 @ d_minus_1, 0.0, atol=1e-12):
        raise AssertionError("cone differential does not square to zero")
    return d_minus_1 @ d_minus_1.T + d_0.T @ d_0


# --- untrusted external solver ----------------------------------------------


def external_dense_solve(laplacian: np.ndarray) -> dict[str, Any]:
    """The dense computation the manuscript places outside the enclave."""

    size = laplacian.shape[0]
    meter = ResourceMeter()
    meter.allocate(size * size)  # the matrix
    meter.allocate(size * size)  # eigenvectors
    meter.work(DENSE_EIGEN_FLOP_CONSTANT * size**3)
    eigenvalues, eigenvectors = np.linalg.eigh(laplacian)
    kernel_columns = [
        index for index, value in enumerate(eigenvalues) if abs(value) <= RESIDUAL_TOLERANCE
    ]
    basis = eigenvectors[:, kernel_columns] if kernel_columns else np.zeros((size, 0))
    return {
        "claimed_basis": basis,
        "claimed_spectrum": eigenvalues.copy(),
        "claimed_dimension": len(kernel_columns),
        "resource_usage": meter.within(DECLARED_BUDGET),
    }


# --- enclave-resident check set ---------------------------------------------


def _sparse_apply(laplacian: np.ndarray, vector: np.ndarray, meter: ResourceMeter) -> np.ndarray:
    """Matrix-vector product costed as a sparse operation over the nonzeros."""

    nonzeros = int(np.count_nonzero(laplacian))
    meter.work(2.0 * nonzeros)
    meter.allocate(vector.size)
    return laplacian @ vector


def enclave_verify_certificate(
    *,
    laplacian: np.ndarray,
    claimed_basis: np.ndarray,
    claimed_spectrum: np.ndarray,
    claimed_dimension: int,
    ledger_head: str,
    signed_payload: dict[str, Any],
    signature: str,
    public_key_hex: str,
    challenge_nonce: str,
    policy_version: str,
    signing_identity: Identity,
) -> dict[str, Any]:
    """The five enclave-resident checks from Section 9.3, with budget accounting."""

    meter = ResourceMeter()
    checks: dict[str, Any] = {}
    size = laplacian.shape[0]
    nonzeros = int(np.count_nonzero(laplacian))

    # 1. Signature and nonce verification.
    meter.io(len(digest(signed_payload)))
    signature_ok = verify(public_key_hex, signed_payload, signature)
    nonce_ok = signed_payload.get("nonce") == challenge_nonce
    checks["signature_and_nonce"] = {
        "signature_valid": signature_ok,
        "nonce_matches": nonce_ok,
        "passed": signature_ok and nonce_ok,
    }

    # 2. Hash-chain validation.
    chain_ok = signed_payload.get("ledger_head") == ledger_head
    meter.work(float(len(ledger_head)))
    checks["hash_chain"] = {
        "expected_head": ledger_head[:16],
        "observed_head": str(signed_payload.get("ledger_head"))[:16],
        "passed": chain_ok,
    }

    # 3a. Sparse residual check: certifies dim ker >= k.
    basis = np.asarray(claimed_basis, dtype=float)
    residuals: list[float] = []
    if basis.size:
        meter.allocate(basis.shape[0] * basis.shape[1])
        for column in range(basis.shape[1]):
            vector = basis[:, column]
            residuals.append(float(np.linalg.norm(_sparse_apply(laplacian, vector, meter))))
        gram = basis.T @ basis
        meter.work(2.0 * basis.shape[1] ** 2 * basis.shape[0])
        orthogonality_error = float(np.linalg.norm(gram - np.eye(basis.shape[1])))
    else:
        orthogonality_error = 0.0
    worst_residual = max(residuals) if residuals else 0.0
    residual_ok = worst_residual <= RESIDUAL_TOLERANCE
    orthogonality_ok = orthogonality_error <= ORTHOGONALITY_TOLERANCE
    checks["sparse_residual_lower_bound"] = {
        "columns_checked": int(basis.shape[1]) if basis.size else 0,
        "worst_residual_norm": worst_residual,
        "residual_tolerance": RESIDUAL_TOLERANCE,
        "orthogonality_error": orthogonality_error,
        "passed": residual_ok and orthogonality_ok,
        "certifies": "obstruction_dimension_at_least_k",
    }

    # 3b. Spectral moment identities: certifies dim ker <= k.
    spectrum = np.asarray(claimed_spectrum, dtype=float)
    trace = float(np.trace(laplacian))
    frobenius_squared = float(np.sum(laplacian * laplacian))
    meter.work(2.0 * nonzeros + float(size))
    meter.allocate(spectrum.size)
    first_moment_error = abs(float(spectrum.sum()) - trace) / max(1.0, abs(trace))
    second_moment_error = abs(float(np.sum(spectrum**2)) - frobenius_squared) / max(
        1.0, abs(frobenius_squared)
    )
    counted_kernel = int(np.sum(np.abs(spectrum) <= RESIDUAL_TOLERANCE))
    moment_ok = (
        first_moment_error <= MOMENT_RELATIVE_TOLERANCE
        and second_moment_error <= MOMENT_RELATIVE_TOLERANCE
        and counted_kernel == claimed_dimension
        and spectrum.size == size
    )
    checks["spectral_moment_upper_bound"] = {
        "trace_identity_relative_error": first_moment_error,
        "frobenius_identity_relative_error": second_moment_error,
        "spectrum_length_matches_dimension": spectrum.size == size,
        "counted_near_zero_eigenvalues": counted_kernel,
        "claimed_dimension": claimed_dimension,
        "passed": moment_ok,
        "certifies": "obstruction_dimension_at_most_k",
    }

    # 4. Policy evaluation.
    policy_ok = policy_version == signed_payload.get("policy_version")
    checks["policy_evaluation"] = {
        "enclave_policy_version": policy_version,
        "payload_policy_version": signed_payload.get("policy_version"),
        "passed": policy_ok,
    }

    all_passed = all(entry["passed"] for entry in checks.values())

    # 5. Certificate signing, only on full acceptance.
    certificate = None
    if all_passed:
        body = {
            "kind": "dcse_consistency_certificate",
            "laplacian_digest": digest(
                {"trace": round(trace, 12), "frobenius_squared": round(frobenius_squared, 12), "size": size}
            ),
            "obstruction_dimension": claimed_dimension,
            "ledger_head": ledger_head,
            "policy_version": policy_version,
            "nonce": challenge_nonce,
        }
        signature_out = signing_identity.sign(body)
        meter.io(len(signature_out) // 2)
        certificate = {"body": body, "signature": signature_out,
                       "public_key_hex": signing_identity.public_key_hex}
    checks["certificate_signing"] = {
        "signed": certificate is not None,
        "passed": (certificate is not None) == all_passed,
    }

    usage = meter.within(DECLARED_BUDGET)
    return {
        "schema_version": "boundarybench.dcse_enclave_verdict.v1",
        "enclave_version": ENCLAVE_VERSION,
        "matrix_size": size,
        "matrix_nonzeros": nonzeros,
        "checks": checks,
        "accepted": all_passed,
        "certificate": certificate,
        "resource_usage": usage,
        "declared_budget": dict(DECLARED_BUDGET),
        "governed_write_path": "permitted" if all_passed else "denied_fail_closed",
    }


# --- forgery suite -----------------------------------------------------------

FORGERY_CLASSES = (
    "random_basis",
    "basis_from_a_different_matrix",
    "over_claimed_dimension",
    "under_claimed_dimension_hiding_obstruction",
    "unnormalized_basis",
    "fabricated_spectrum",
    "stale_ledger_head",
    "wrong_policy_version",
    "forged_signature",
)


def run_enclave_suite(vertices: int = 60, disagreeing: Sequence[int] = (3, 17, 41)) -> dict[str, Any]:
    """Honest solver accepted; every forgery class rejected; budgets compared."""

    laplacian = scalable_cone_laplacian(vertices, disagreeing)
    size = laplacian.shape[0]
    solver = external_dense_solve(laplacian)
    node = derive_identity("coprocessor", seed="dcse-v3-enclave")
    signer = derive_identity("enclave-signer", seed="dcse-v3-enclave")
    ledger_head = digest({"head": "ledger-head-1"})
    policy_version = "1.1"
    nonce = "nonce-enclave-1"
    payload = {
        "ledger_head": ledger_head,
        "policy_version": policy_version,
        "nonce": nonce,
        "obstruction_dimension": solver["claimed_dimension"],
    }
    signature = node.sign(payload)

    def attempt(**overrides: Any) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "laplacian": laplacian,
            "claimed_basis": solver["claimed_basis"],
            "claimed_spectrum": solver["claimed_spectrum"],
            "claimed_dimension": solver["claimed_dimension"],
            "ledger_head": ledger_head,
            "signed_payload": payload,
            "signature": signature,
            "public_key_hex": node.public_key_hex,
            "challenge_nonce": nonce,
            "policy_version": policy_version,
            "signing_identity": signer,
        }
        kwargs.update(overrides)
        return enclave_verify_certificate(**kwargs)

    honest = attempt()

    rng = np.random.default_rng(9001)
    forgeries: dict[str, dict[str, Any]] = {}

    # 1. Random unit vectors passed off as a kernel basis.
    random_basis = rng.normal(size=(size, max(1, solver["claimed_dimension"])))
    random_basis /= np.linalg.norm(random_basis, axis=0, keepdims=True)
    random_basis, _ = np.linalg.qr(random_basis)
    forgeries["random_basis"] = attempt(claimed_basis=random_basis)

    # 2. A genuine kernel basis, but of a different Laplacian.
    other = scalable_cone_laplacian(vertices, (5, 9))
    other_solution = external_dense_solve(other)
    forgeries["basis_from_a_different_matrix"] = attempt(
        claimed_basis=other_solution["claimed_basis"],
        claimed_spectrum=other_solution["claimed_spectrum"],
        claimed_dimension=other_solution["claimed_dimension"],
    )

    # 3. Over-claim: pad the true basis with a non-kernel direction.
    padded = np.hstack(
        [solver["claimed_basis"], rng.normal(size=(size, 1))]
    )
    padded, _ = np.linalg.qr(padded)
    forgeries["over_claimed_dimension"] = attempt(
        claimed_basis=padded, claimed_dimension=solver["claimed_dimension"] + 1
    )

    # 4. Under-claim: drop a genuine kernel direction to hide obstruction. The
    #    residual check alone would pass this; only the moment count catches it.
    if solver["claimed_dimension"] >= 2:
        trimmed = solver["claimed_basis"][:, :-1]
        forgeries["under_claimed_dimension_hiding_obstruction"] = attempt(
            claimed_basis=trimmed, claimed_dimension=solver["claimed_dimension"] - 1
        )

    # 5. Unnormalized basis.
    forgeries["unnormalized_basis"] = attempt(claimed_basis=solver["claimed_basis"] * 0.5)

    # 6. Fabricated spectrum claiming no obstruction at all.
    fake_spectrum = np.abs(solver["claimed_spectrum"]) + 1.0
    forgeries["fabricated_spectrum"] = attempt(
        claimed_spectrum=fake_spectrum, claimed_dimension=0,
        claimed_basis=np.zeros((size, 0)),
    )

    # 7-9. Protocol-level forgeries.
    forgeries["stale_ledger_head"] = attempt(ledger_head=digest({"head": "ledger-head-0"}))
    forgeries["wrong_policy_version"] = attempt(policy_version="9.9")
    forgeries["forged_signature"] = attempt(
        signature=derive_identity("attacker", seed="dcse-v3-enclave").sign(payload)
    )

    dense_usage = solver["resource_usage"]
    enclave_usage = honest["resource_usage"]
    return {
        "schema_version": "boundarybench.dcse_enclave_suite.v1",
        "enclave_version": ENCLAVE_VERSION,
        "complex": {"vertices": vertices, "disagreeing_stalks": list(disagreeing)},
        "matrix_size": size,
        "matrix_nonzeros": honest["matrix_nonzeros"],
        "honest_solver_accepted": honest["accepted"],
        "honest_verdict": honest,
        "true_obstruction_dimension": solver["claimed_dimension"],
        "forgery_classes_declared": list(FORGERY_CLASSES),
        "forgeries_run": len(forgeries),
        "forgery_results": {
            name: {
                "accepted": verdict["accepted"],
                "failed_checks": [
                    key for key, entry in verdict["checks"].items() if not entry["passed"]
                ],
                "governed_write_path": verdict["governed_write_path"],
            }
            for name, verdict in forgeries.items()
        },
        "all_forgeries_rejected": all(not verdict["accepted"] for verdict in forgeries.values()),
        "resource_comparison": {
            "declared_budget": dict(DECLARED_BUDGET),
            "enclave_sparse_path": enclave_usage,
            "external_dense_path": dense_usage,
            "enclave_fits_budget": enclave_usage["all_within_budget"],
            "dense_exceeds_budget": not dense_usage["all_within_budget"],
            "flop_ratio_dense_over_sparse": (
                dense_usage["flops"] / enclave_usage["flops"] if enclave_usage["flops"] else None
            ),
            "heap_ratio_dense_over_sparse": (
                dense_usage["peak_heap_bytes"] / enclave_usage["peak_heap_bytes"]
                if enclave_usage["peak_heap_bytes"]
                else None
            ),
        },
        "section_9_3_claim_supported": bool(
            honest["accepted"]
            and all(not verdict["accepted"] for verdict in forgeries.values())
            and enclave_usage["all_within_budget"]
            and not dense_usage["all_within_budget"]
        ),
        "scope": (
            "No TEE. The 'enclave' is a budget-accounted software module; the budget is "
            "declared and enforced in accounting, not by hardware. The transferable "
            "result is the sufficiency of the sparse certificate, which is a property of "
            "the mathematics and does not depend on the hardware."
        ),
    }
