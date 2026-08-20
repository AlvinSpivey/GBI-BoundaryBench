"""Mapping-cone trace cell energy on a declared toy complex.

The GBI/DCSE manuscript defines the trace cell energy of a stalk as

    E_sigma = tr( Pi_Lambda Pi_sigma )

where ``Pi_Lambda`` is the orthogonal projector onto the obstruction null space of
a cone Laplacian and ``Pi_sigma`` is the projector onto a stalk subspace
(Definition 7.1), and it gates surgical quarantine on ``E_sigma > theta``
(Section 7.3). The manuscript is explicit that its executable appendix computes a
*projector-based obstruction surrogate* rather than a real mapping-cone
differential, and that the resulting table is therefore not evidence of a
validated diagnostic.

This module closes that specific gap for the BeTaL environment: it builds an
actual sheaf morphism ``phi : F -> G`` over a finite cell complex, assembles the
genuine cone differential

    d_cone(x, y) = ( -delta_F x , phi(x) + delta_G y ),

forms the degree-0 cone Hodge Laplacian

    Delta = d^{-1} (d^{-1})^*  +  (d^0)^* d^0,

and reads ``Pi_Lambda`` off its kernel. So ``E_sigma`` here is computed from a
cone Laplacian, not from a standalone projector.

That is a mathematical improvement and nothing more. It is still a *declared toy
complex* with declared stalk dimensions, and it is still not validated against
clinical outcomes. Consistent with the repository's existing policy in
``verification/diagnostics.py``, every value produced here carries
``scoring_weight = 0`` and ``validated = false``, and none of it enters the BeTaL
objective. E_sigma is reported as a covariate alongside the search, never as a
score.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

CONE_VERSION = "betal-gbi-mapping-cone-v0.2"

# Declared clinical stalk axes for the toy complex, following the manuscript's
# three-coordinate example (Allergy, MedicationRequest, RenalLab) but renamed to
# the admission axes BoundaryBench actually checks.
STALKS: tuple[str, ...] = ("identity", "terminology", "provenance_temporal")

# Triangle complex: every pair of axes shares an incidence.
EDGES: tuple[tuple[int, int], ...] = ((0, 1), (1, 2), (0, 2))

STALK_DIM = 2
QUARANTINE_THRESHOLD = 0.5


# Restriction map every vertex stalk uses to reach an incident edge stalk.
#
# It is deliberately *not* the identity. With identity restrictions on a
# connected complex, the chain-map condition
#
#     phi_e . F_{v->e}  =  G_{v->e} . phi_v
#
# forces every phi to be the same map, so no per-stalk morphism exists and no
# obstruction can be localized. Projecting onto the first coordinate leaves the
# second coordinate of each vertex stalk unconstrained by the chain-map
# condition, which is exactly the degree of freedom a per-axis grounding
# morphism needs. This is the structural reason the toy complex must carry a
# rank-deficient restriction.
RESTRICTION = np.diag([1.0, 0.0])


def _coboundary(vertex_count: int, edges: tuple[tuple[int, int], ...], dim: int) -> np.ndarray:
    """Assemble delta : C^0 -> C^1 from the declared restriction map and signed incidence."""

    rows = len(edges) * dim
    cols = vertex_count * dim
    delta = np.zeros((rows, cols))
    restriction = RESTRICTION
    for edge_index, (tail, head) in enumerate(edges):
        row = slice(edge_index * dim, (edge_index + 1) * dim)
        delta[row, head * dim : (head + 1) * dim] += restriction
        delta[row, tail * dim : (tail + 1) * dim] -= restriction
    return delta


def _null_space_projector(matrix: np.ndarray, tolerance: float = 1e-9) -> np.ndarray:
    """Orthogonal projector onto the kernel of a symmetric positive-semidefinite matrix."""

    eigenvalues, eigenvectors = np.linalg.eigh(matrix)
    scale = max(1.0, float(np.max(np.abs(eigenvalues))) if eigenvalues.size else 1.0)
    mask = eigenvalues <= tolerance * scale
    basis = eigenvectors[:, mask]
    if basis.size == 0:
        return np.zeros_like(matrix)
    return basis @ basis.T


@dataclass(frozen=True)
class ConeDiagnostic:
    stalk_energies: dict[str, float]
    obstruction_dimension: int
    quarantined_stalks: tuple[str, ...]
    agreement: dict[str, bool]

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "boundarybench.betal_cone_diagnostic.v1",
            "cone_version": CONE_VERSION,
            "status": "DIAGNOSTIC_ONLY_NOT_VALIDATED",
            "scoring_weight": 0,
            "validated": False,
            "construction": "genuine_cone_laplacian_on_declared_toy_complex",
            "quarantine_threshold": QUARANTINE_THRESHOLD,
            "obstruction_dimension": self.obstruction_dimension,
            "stalk_energies": {name: round(value, 6) for name, value in self.stalk_energies.items()},
            "quarantined_stalks": list(self.quarantined_stalks),
            "axis_agreement": dict(self.agreement),
        }


def cone_diagnostic(agreement: dict[str, bool]) -> ConeDiagnostic:
    """Compute E_sigma for each declared axis given candidate/reference agreement.

    ``agreement[axis] = True`` means the candidate assertion on that axis matches
    the authoritative reference, so ``phi`` is the identity there.
    ``False`` means the axis component of ``phi`` annihilates its stalk, which
    breaks commutativity with the restriction maps on every incident edge and
    produces a relative obstruction localized near that axis.
    """

    vertex_count = len(STALKS)
    dim = STALK_DIM
    delta_f = _coboundary(vertex_count, EDGES, dim)
    delta_g = delta_f.copy()

    # phi on vertices: diag(1, b) where b = 1 if the axis agrees with the
    # authoritative reference and 0 if it does not. The first coordinate is fixed
    # to 1 by the chain-map condition; the second is the free per-axis degree of
    # freedom that carries the agreement signal.
    phi_0 = np.zeros((vertex_count * dim, vertex_count * dim))
    for index, name in enumerate(STALKS):
        block = slice(index * dim, (index + 1) * dim)
        agrees = bool(agreement.get(name, True))
        phi_0[block, block] = np.diag([1.0, 1.0 if agrees else 0.0])

    # phi on edges: identity. Combined with the rank-deficient restriction this
    # satisfies phi_1 . delta_F == delta_G . phi_0 exactly, so d_cone^2 = 0.
    phi_1 = np.eye(len(EDGES) * dim)

    # d^{-1} : C^0(F) -> C^1(F) (+) C^0(G),  z |-> (-delta_F z, phi_0 z)
    d_minus_1 = np.vstack([-delta_f, phi_0])

    # d^0 : C^1(F) (+) C^0(G) -> C^1(G),  (x, y) |-> phi_1 x + delta_G y
    d_0 = np.hstack([phi_1, delta_g])

    # Cone condition. Asserted rather than assumed: an invalid cone would make
    # every downstream energy meaningless.
    composite = d_0 @ d_minus_1
    if not np.allclose(composite, 0.0, atol=1e-12):
        raise AssertionError(
            "cone differential does not square to zero; phi is not a chain map"
        )

    laplacian = d_minus_1 @ d_minus_1.T + d_0.T @ d_0
    projector = _null_space_projector(laplacian)
    obstruction_dimension = int(round(float(np.trace(projector))))

    # Pi_sigma: the G-stalk coordinates of axis sigma inside C^0(Cone).
    f_edge_dim = len(EDGES) * dim
    energies: dict[str, float] = {}
    for index, name in enumerate(STALKS):
        stalk_projector = np.zeros_like(laplacian)
        offset = f_edge_dim + index * dim
        for coordinate in range(offset, offset + dim):
            stalk_projector[coordinate, coordinate] = 1.0
        energies[name] = float(np.trace(projector @ stalk_projector))

    quarantined = tuple(
        name for name, value in energies.items() if value > QUARANTINE_THRESHOLD
    )
    return ConeDiagnostic(
        stalk_energies=energies,
        obstruction_dimension=obstruction_dimension,
        quarantined_stalks=quarantined,
        agreement=dict(agreement),
    )


_AXIS_BY_FAMILY: dict[str, str] = {
    "patient_identity_normalization": "identity",
    "orphan_duplicate_detection": "identity",
    "field_anomaly_bleed": "provenance_temporal",
    "code_system_version_validation": "terminology",
    "rpms_to_fhir_mapping": "provenance_temporal",
    "temporal_status_classification": "provenance_temporal",
    "evidence_sufficiency": "provenance_temporal",
    "policy_action_selection": "terminology",
}


def axis_for_family(family: str) -> str:
    return _AXIS_BY_FAMILY[family]


def energy_profile_for_failure_families(failing_families: set[str]) -> ConeDiagnostic:
    """Map a set of failing task families onto axis disagreement, then compute E_sigma."""

    failing_axes = {axis_for_family(family) for family in failing_families}
    agreement = {axis: axis not in failing_axes for axis in STALKS}
    return cone_diagnostic(agreement)


def reference_table() -> dict[str, Any]:
    """Enumerate E_sigma for every agreement pattern.

    Useful as a smoke test and as the audit table a reviewer can check by hand.
    """

    rows = []
    for mask in range(1 << len(STALKS)):
        agreement = {
            name: not bool(mask & (1 << index)) for index, name in enumerate(STALKS)
        }
        diagnostic = cone_diagnostic(agreement)
        rows.append(
            {
                "disagreeing_axes": sorted(name for name, ok in agreement.items() if not ok),
                "obstruction_dimension": diagnostic.obstruction_dimension,
                "stalk_energies": {
                    name: round(value, 6) for name, value in diagnostic.stalk_energies.items()
                },
                "quarantined_stalks": list(diagnostic.quarantined_stalks),
            }
        )
    return {
        "schema_version": "boundarybench.betal_cone_reference_table.v1",
        "cone_version": CONE_VERSION,
        "status": "DIAGNOSTIC_ONLY_NOT_VALIDATED",
        "scoring_weight": 0,
        "validated": False,
        "stalk_dimension": STALK_DIM,
        "complex": {"vertices": list(STALKS), "edges": [list(edge) for edge in EDGES]},
        "quarantine_threshold": QUARANTINE_THRESHOLD,
        "rows": rows,
    }
