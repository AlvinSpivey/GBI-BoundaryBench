"""Python port of the Appendix A Julia reference implementation.

Appendix A of main.pdf ships a complete executable reference
(``anc/gbi_dcse_arxiv_revised.jl``) with a ``run_self_check`` suite and a
``run_report`` that prints specific numbers quoted in Sections 6.3, 7.3 and 8.1.

This module is a faithful port. Its purpose is narrow and worth stating: the
manuscript's numbers should be reproducible by an *independent* implementation in
a different language, using a different linear-algebra library, without the
original author's code. Agreement then means the numbers are properties of the
mathematics rather than of one runtime.

Two deliberate fidelity choices:

* ``approx_trigamma`` is ported recurrence-for-recurrence rather than replaced
  with a library call, because the manuscript's numbers were produced by *that*
  approximation. A separate check compares it against an independent
  series/asymptotic implementation so the port is validated in both directions.
* The projector-based obstruction surrogate is kept exactly as Appendix A defines
  it, including its explicit 6x2 matrix. It is *not* silently upgraded to the real
  mapping cone built in ``betal/cone.py``. The manuscript is explicit that these
  are different objects, and conflating them would erase the distinction the
  manuscript is careful to draw.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Sequence

import numpy as np

APPENDIX_A_VERSION = "gbi-appendix-a-port-v3.0"

# Constants transcribed from Appendix A.
MAPPING_STATUS_LABELS = ("exact", "equivalent", "narrower", "broader", "conflict", "unmapped")
FISHER_MIN_EIGENVALUE = 1e-6
QUARANTINE_THRESHOLD = 0.80
KTABULAR = 1.5
PSD_TOL = 1e-10


# --- Section 4: condensed / operational probe -------------------------------


def condensed_probe_demo() -> dict[str, Any]:
    """Appendix A ``condensed_probe_demo``.

    The sequence 1/n converges but is not eventually constant, so it fails the
    operational compatibility check. This is the finite, executable stand-in for
    the Section 4 statement that ``Cok(f)(N_inf)`` is nonzero: a convergent
    sequence that is not eventually constant is exactly a nonzero element of
    {convergent}/{eventually constant}.
    """

    seq = [1.0 / index for index in range(1, 21)]
    tail = seq[-5:]
    tail_variation = max(abs(value - seq[-1]) for value in tail)
    return {
        "sequence_length": len(seq),
        "final_term": seq[-1],
        "tail_variation": tail_variation,
        "eventually_constant": tail_variation < 1e-12,
        "converges": abs(seq[-1] - 0.0) < 1.0,
        "witnesses_nonzero_cokernel": tail_variation >= 1e-12,
    }


def entropy_bits(p: Sequence[float]) -> float:
    """Appendix A ``entropy_bits``: Shannon entropy in bits, skipping zeros."""

    total = 0.0
    for value in p:
        x = float(value)
        if x > 0.0:
            total -= x * math.log2(x)
    return total


# --- Section 6: trigamma and the Dirichlet Fisher metric --------------------


def approx_trigamma(x: float) -> float:
    """Appendix A ``approx_trigamma``, ported recurrence-for-recurrence.

    Upward recurrence psi_1(y) = psi_1(y+1) + 1/y^2 until y >= 8, then the
    asymptotic expansion.
    """

    if not x > 0.0:
        raise ValueError("trigamma approximation requires x > 0")
    y = float(x)
    acc = 0.0
    while y < 8.0:
        acc += 1.0 / (y * y)
        y += 1.0
    inv_y = 1.0 / y
    inv2 = inv_y * inv_y
    inv3 = inv2 * inv_y
    inv5 = inv2 * inv3
    inv7 = inv2 * inv5
    inv9 = inv2 * inv7
    return acc + inv_y + 0.5 * inv2 + inv3 / 6.0 - inv5 / 30.0 + inv7 / 42.0 - inv9 / 30.0


def _independent_trigamma(x: float, terms: int = 200_000) -> float:
    """Independent trigamma, for cross-validating the ported approximation.

    Uses the same mathematical function reached by a different route: direct
    series summation after enough upward recurrence steps that the tail is
    dominated by the integral bound.
    """

    y = float(x)
    acc = 0.0
    while y < 40.0:
        acc += 1.0 / (y * y)
        y += 1.0
    # sum_{k>=0} 1/(y+k)^2, summed directly with an Euler-Maclaurin tail.
    total = 0.0
    for k in range(terms):
        total += 1.0 / ((y + k) ** 2)
    tail_start = y + terms
    total += 1.0 / tail_start - 0.5 / (tail_start**2)
    return acc + total


def fisher_dirichlet(alpha: Sequence[float]) -> np.ndarray:
    """Appendix A ``fisher_dirichlet``: g_ij = psi_1(a_i) delta_ij - psi_1(sum a)."""

    values = [float(a) for a in alpha]
    if not values:
        raise ValueError("alpha must be non-empty")
    for value in values:
        if not value > 0.0:
            raise ValueError("Dirichlet alpha values must be > 0")
    alpha_sum = sum(values)
    base = -approx_trigamma(alpha_sum)
    size = len(values)
    metric = np.full((size, size), base, dtype=float)
    for index, value in enumerate(values):
        metric[index, index] += approx_trigamma(value)
    return metric


# --- Section 8: Wirtinger derivatives and the hyperellipsoid certificate ----


def f_map(z: complex, theta: float) -> complex:
    return z * z + theta * z.conjugate()


def wirtinger_exact(z: complex, theta: float) -> tuple[complex, complex]:
    """Exact Wirtinger derivatives of f(z;theta) = z^2 + theta*conj(z)."""

    return 2.0 * z, complex(theta, 0.0)


def wirtinger_fd(z: complex, theta: float, h: float) -> tuple[complex, complex]:
    """Central finite differences, retained by Appendix A as a validation fallback."""

    fx = (f_map(z + h, theta) - f_map(z - h, theta)) / (2.0 * h)
    fy = (f_map(z + 1j * h, theta) - f_map(z - 1j * h, theta)) / (2.0 * h)
    return 0.5 * (fx - 1j * fy), 0.5 * (fx + 1j * fy)


@dataclass(frozen=True)
class HyperellipsoidCertificate:
    singular_values: tuple[float, ...]
    axis_eccentricity: float
    jacobian: float
    outer_distortion: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "singular_values": [round(v, 6) for v in self.singular_values],
            "axis_eccentricity_H": self.axis_eccentricity,
            "jacobian_J": self.jacobian,
            "outer_distortion_K_O": self.outer_distortion,
        }


def hyperellipsoid_certificate(matrix: np.ndarray) -> HyperellipsoidCertificate:
    """Appendix A ``hyperellipsoid_certificate``: Section 8.1 audit certificate."""

    a = np.asarray(matrix, dtype=float)
    singular_values = np.linalg.svd(a, compute_uv=False)
    sigma_min = float(np.min(singular_values))
    sigma_max = float(np.max(singular_values))
    jacobian = float(np.linalg.det(a))
    if not sigma_min > 0.0:
        raise ValueError("matrix must be full rank")
    if not jacobian > 0.0:
        raise ValueError("matrix must have positive Jacobian")
    return HyperellipsoidCertificate(
        singular_values=tuple(float(v) for v in singular_values),
        axis_eccentricity=sigma_max / sigma_min,
        jacobian=jacobian,
        outer_distortion=sigma_max ** a.shape[0] / jacobian,
    )


# --- Section 7.3: projector-based obstruction surrogate --------------------


def orthonormal_columns(matrix: np.ndarray) -> np.ndarray:
    """Appendix A ``orthonormal_columns``: thin QR, first `cols` columns of Q."""

    m = np.asarray(matrix, dtype=float)
    rows, cols = m.shape
    if cols > rows:
        raise ValueError("matrix must have at least as many rows as columns")
    q, _ = np.linalg.qr(m)
    return q[:, :cols]


def appendix_raw_obstructions() -> np.ndarray:
    """Appendix A's explicit 6x2 obstruction matrix.

    Row pairs model the Allergy, MedicationRequest and RenalLab stalks.
    """

    return np.array(
        [
            [0.10, 0.10],
            [0.10, -0.10],
            [1.00, 1.00],
            [1.00, -1.00],
            [0.05, 0.00],
            [0.00, 0.05],
        ],
        dtype=float,
    )


APPENDIX_STALK_RANGES: tuple[tuple[str, tuple[int, int]], ...] = (
    ("Allergy", (0, 2)),
    ("MedicationRequest", (2, 4)),
    ("RenalLab", (4, 6)),
)


def mapping_cone_certificate(
    raw_obstructions: np.ndarray, threshold: float = QUARANTINE_THRESHOLD
) -> dict[str, Any]:
    """Appendix A ``mapping_cone_certificate``.

    Named as in the source. It is a *projector surrogate*: the projector is built
    directly from the supplied obstruction vectors, and the "Laplacian" is
    ``I - projector``. There is no sheaf morphism and no cone differential here.
    The manuscript says so, and the port preserves the distinction.
    """

    basis = orthonormal_columns(raw_obstructions)
    projector = basis @ basis.T
    laplacian = np.eye(projector.shape[0]) - projector
    energies = []
    for name, (start, stop) in APPENDIX_STALK_RANGES:
        energy = float(sum(projector[index, index] for index in range(start, stop)))
        energies.append(
            {
                "name": name,
                "energy": energy,
                "decision": "QUARANTINE" if energy > threshold else "COMMIT",
            }
        )
    return {
        "basis": basis,
        "projector": projector,
        "laplacian": laplacian,
        "eigenvalues": tuple(float(v) for v in np.linalg.eigvalsh(laplacian)),
        "energies": energies,
        "construction": "projector_surrogate_not_a_mapping_cone",
    }


# --- run_self_check, ported assertion for assertion ------------------------


def run_self_check() -> dict[str, Any]:
    """Every ``@assert`` in Appendix A's ``run_self_check``, as a checked record."""

    results: list[dict[str, Any]] = []

    def record(name: str, passed: bool, detail: Any = None) -> None:
        results.append({"assertion": name, "passed": bool(passed), "detail": detail})

    alpha = [2.0, 3.0, 4.0, 5.0]
    metric = fisher_dirichlet(alpha)
    record("fisher_metric_symmetric", bool(np.allclose(metric, metric.T, atol=1e-15)))
    eigenvalues = np.linalg.eigvalsh(metric)
    record(
        "fisher_min_eigenvalue_above_tolerance",
        float(np.min(eigenvalues)) > FISHER_MIN_EIGENVALUE,
        float(np.min(eigenvalues)),
    )

    boundary_alpha = [0.01, 3.0, 4.0, 5.0]
    boundary_metric = fisher_dirichlet(boundary_alpha)
    boundary_eigenvalues = np.linalg.eigvalsh(boundary_metric)
    record(
        "boundary_fisher_min_eigenvalue_above_tolerance",
        float(np.min(boundary_eigenvalues)) > FISHER_MIN_EIGENVALUE,
        float(np.min(boundary_eigenvalues)),
    )

    z = complex(1.0, 1.0)
    theta = 0.35
    fz_exact, fzb_exact = wirtinger_exact(z, theta)
    fz_fd, fzb_fd = wirtinger_fd(z, theta, 1e-5)
    record(
        "wirtinger_dz_exact_matches_finite_difference",
        abs(fz_exact - fz_fd) <= 1e-10 * max(1.0, abs(fz_exact)) + 1e-10,
        abs(fz_exact - fz_fd),
    )
    record(
        "wirtinger_dzbar_exact_matches_finite_difference",
        abs(fzb_exact - fzb_fd) <= 1e-10 * max(1.0, abs(fzb_exact)) + 1e-10,
        abs(fzb_exact - fzb_fd),
    )

    a = np.array([[1.20, 0.10, 0.0], [0.20, 0.80, 0.05], [0.0, 0.10, 1.10]])
    certificate = hyperellipsoid_certificate(a)
    record("axis_eccentricity_at_least_one", certificate.axis_eccentricity >= 1.0,
           certificate.axis_eccentricity)
    record("outer_distortion_at_least_one", certificate.outer_distortion >= 1.0,
           certificate.outer_distortion)

    raw = appendix_raw_obstructions()
    cone = mapping_cone_certificate(raw)
    basis = cone["basis"]
    record(
        "surrogate_basis_orthonormal",
        bool(np.allclose(basis.T @ basis, np.eye(basis.shape[1]), atol=1e-12)),
        float(np.max(np.abs(basis.T @ basis - np.eye(basis.shape[1])))),
    )
    laplacian = cone["laplacian"]
    record(
        "surrogate_laplacian_symmetric",
        bool(np.allclose(laplacian, laplacian.T, atol=1e-15)),
        float(np.max(np.abs(laplacian - laplacian.T))),
    )
    record(
        "surrogate_laplacian_eigenvalues_above_negative_tolerance",
        float(min(cone["eigenvalues"])) >= -PSD_TOL,
        float(min(cone["eigenvalues"])),
    )

    angle = 0.73
    rotation = np.array(
        [[math.cos(angle), -math.sin(angle)], [math.sin(angle), math.cos(angle)]]
    )
    rotated_basis = basis @ rotation
    rotated_projector = rotated_basis @ rotated_basis.T
    drift = float(np.linalg.norm(cone["projector"] - rotated_projector))
    record("surrogate_projector_rotation_invariant", drift <= 1e-12, drift)

    return {
        "schema_version": "boundarybench.appendix_a_self_check.v1",
        "appendix_a_version": APPENDIX_A_VERSION,
        "assertions": results,
        "assertions_run": len(results),
        "assertions_passed": sum(1 for entry in results if entry["passed"]),
        "all_passed": all(entry["passed"] for entry in results),
    }


# --- run_report reproduction with the manuscript's printed values ----------

# Values printed by Appendix A's run_report / quoted in Sections 6.3, 7.3, 8.1.
MANUSCRIPT_VALUES: dict[str, Any] = {
    "hyperellipsoid_singular_values": (1.254966, 1.110695, 0.737507),
    "hyperellipsoid_H": 1.701632,
    "hyperellipsoid_J": 1.028000,
    "hyperellipsoid_K_O": 1.922661,
    "stalk_energies": {
        "Allergy": 0.019778,
        "MedicationRequest": 1.977750,
        "RenalLab": 0.002472,
    },
    "fisher_eigenvalues_interior": (0.029494, 0.254435, 0.361568, 0.603356),
    "fisher_condition_interior": 20.46,
    "fisher_eigenvalues_boundary": (0.021986, 0.254705, 0.362908, 10001.5344),
    "fisher_condition_boundary": 4.55e5,
    "trigamma_at_0_01": 10001.621,
    "trigamma_at_14": 0.074040,
}


def run_report() -> dict[str, Any]:
    """Reproduce Appendix A's printed report and compare against the manuscript."""

    comparisons: list[dict[str, Any]] = []

    def compare(name: str, computed: float, published: float, tolerance_pct: float = 1.0) -> None:
        error_pct = (
            0.0 if published == 0 else abs(computed - published) / abs(published) * 100.0
        )
        comparisons.append(
            {
                "quantity": name,
                "computed": computed,
                "published": published,
                "relative_error_pct": error_pct,
                "agrees": error_pct <= tolerance_pct,
            }
        )

    probe = condensed_probe_demo()

    status_alpha = [1.0, 14.0, 1.0, 1.0, 3.0, 1.0]
    total = sum(status_alpha)
    status_p = [value / total for value in status_alpha]
    status_entropy = entropy_bits(status_p)

    a = np.array([[1.20, 0.10, 0.0], [0.20, 0.80, 0.05], [0.0, 0.10, 1.10]])
    certificate = hyperellipsoid_certificate(a)
    for index, published in enumerate(MANUSCRIPT_VALUES["hyperellipsoid_singular_values"]):
        compare(f"singular_value_{index + 1}", certificate.singular_values[index], published)
    compare("axis_eccentricity_H", certificate.axis_eccentricity, MANUSCRIPT_VALUES["hyperellipsoid_H"])
    compare("jacobian_J", certificate.jacobian, MANUSCRIPT_VALUES["hyperellipsoid_J"])
    compare("outer_distortion_K_O", certificate.outer_distortion, MANUSCRIPT_VALUES["hyperellipsoid_K_O"])

    cone = mapping_cone_certificate(appendix_raw_obstructions())
    for entry in cone["energies"]:
        compare(
            f"stalk_energy_{entry['name']}",
            entry["energy"],
            MANUSCRIPT_VALUES["stalk_energies"][entry["name"]],
            tolerance_pct=1.0,
        )

    interior = np.linalg.eigvalsh(fisher_dirichlet([2.0, 3.0, 4.0, 5.0]))
    for index, published in enumerate(MANUSCRIPT_VALUES["fisher_eigenvalues_interior"]):
        compare(f"fisher_eigenvalue_interior_{index + 1}", float(interior[index]), published)
    compare(
        "fisher_condition_interior",
        float(np.max(interior) / np.min(interior)),
        MANUSCRIPT_VALUES["fisher_condition_interior"],
    )
    boundary = np.linalg.eigvalsh(fisher_dirichlet([0.01, 3.0, 4.0, 5.0]))
    for index, published in enumerate(MANUSCRIPT_VALUES["fisher_eigenvalues_boundary"]):
        compare(f"fisher_eigenvalue_boundary_{index + 1}", float(boundary[index]), published)
    compare(
        "fisher_condition_boundary",
        float(np.max(boundary) / np.min(boundary)),
        MANUSCRIPT_VALUES["fisher_condition_boundary"],
    )
    compare("trigamma_0_01", approx_trigamma(0.01), MANUSCRIPT_VALUES["trigamma_at_0_01"])
    compare("trigamma_14", approx_trigamma(14.0), MANUSCRIPT_VALUES["trigamma_at_14"])

    # Cross-validate the ported approximation against an independent route.
    trigamma_cross = []
    for x in (0.01, 0.5, 1.0, 2.0, 7.999, 8.0, 14.0, 100.0):
        ported = approx_trigamma(x)
        independent = _independent_trigamma(x)
        trigamma_cross.append(
            {
                "x": x,
                "ported": ported,
                "independent": independent,
                "relative_error": abs(ported - independent) / abs(independent),
            }
        )

    return {
        "schema_version": "boundarybench.appendix_a_report.v1",
        "appendix_a_version": APPENDIX_A_VERSION,
        "condensed_probe": probe,
        "mapping_status_labels": list(MAPPING_STATUS_LABELS),
        "local_status_posterior_mean": [round(value, 4) for value in status_p],
        "local_status_entropy_bits": status_entropy,
        "hyperellipsoid_certificate": certificate.as_dict(),
        "surrogate_stalk_energies": [
            {"name": entry["name"], "energy": entry["energy"], "decision": entry["decision"]}
            for entry in cone["energies"]
        ],
        "surrogate_energy_sum_equals_rank": {
            "sum": sum(entry["energy"] for entry in cone["energies"]),
            "rank": int(np.linalg.matrix_rank(appendix_raw_obstructions())),
        },
        "surrogate_laplacian_eigenvalues": [round(v, 4) for v in cone["eigenvalues"]],
        "manuscript_comparisons": comparisons,
        "comparisons_run": len(comparisons),
        "comparisons_agreeing": sum(1 for entry in comparisons if entry["agrees"]),
        "all_agree": all(entry["agrees"] for entry in comparisons),
        "trigamma_cross_validation": trigamma_cross,
        "trigamma_cross_validation_max_relative_error": max(
            entry["relative_error"] for entry in trigamma_cross
        ),
        "ktabular": KTABULAR,
        "quarantine_threshold": QUARANTINE_THRESHOLD,
    }
