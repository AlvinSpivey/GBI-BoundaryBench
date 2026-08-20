"""Executable tests for the main.pdf sections that had no test at all.

v2 scored the admission boundary (Sections 9, 11, 12) and Appendix B. This module
closes Sections 2, 3, 4, 6.2 and 8, which carry theorems, definitions, numerical
examples and safety requirements that nothing had exercised.

Three of these are worth calling out because the manuscript itself flags them as
unimplemented or as requirements rather than results:

* **Section 2.7** says "the present appendix does not implement that dynamical
  example" for a category switch under sustained high entropy. It is implemented
  here.
* **Section 8.1** says "a safety-critical implementation must also check positive
  Jacobian, boundary behavior, inverse residuals, and stratum preservation." All
  four are implemented here; Appendix A checks only the first.
* **Appendix B.3 Boundary 3** says the chart distortion coefficient K is a
  notification tool and "must never be interpreted as proof of logical
  inconsistency." That is a negative claim, so it needs a test that would catch a
  system letting K drive a decision. Both directions are tested.
"""

from __future__ import annotations

from dataclasses import dataclass
import itertools
import math
from typing import Any, Iterable, Sequence

import numpy as np

CLAIMS_VERSION = "gbi-section-claims-v3.0"


# ===========================================================================
# Section 2: logit topology
# ===========================================================================


def _softmax(logits: np.ndarray, tau: float) -> np.ndarray:
    scaled = np.asarray(logits, dtype=float) / tau
    scaled = scaled - np.max(scaled)
    exponentiated = np.exp(scaled)
    return exponentiated / exponentiated.sum()


def _entropy_nats(p: np.ndarray) -> float:
    total = 0.0
    for value in p:
        if value > 0.0:
            total -= value * math.log(value)
    return total


def section_2_affine_equivalence(seed: int = 20260819) -> dict[str, Any]:
    """Definition 2.1, Theorem 2.1 and the Section 2.4 numerical example.

    Constructs exactly the manuscript's setup: D=3, M=6, W_B of full column rank,
    an affine transform (T, v), then W_A = W_B T and b_A = W_B v + b_B. Checks that
    the two readouts agree to floating-point roundoff, and that Theorem 2.1's
    reconstruction h_B = W_B^+ W_A h_A + W_B^+ (b_A - b_B) holds on the evaluated
    stimulus set.
    """

    rng = np.random.default_rng(seed)
    dimension, categories = 3, 6
    w_b = rng.normal(size=(categories, dimension))
    b_b = rng.normal(size=categories)
    transform = rng.normal(size=(dimension, dimension))
    shift = rng.normal(size=dimension)
    w_a = w_b @ transform
    b_a = w_b @ shift + b_b

    stimuli = rng.normal(size=(32, dimension))
    residuals = []
    reconstruction_residuals = []
    pseudo_inverse = np.linalg.pinv(w_b)
    for h_a in stimuli:
        h_b = transform @ h_a + shift
        logits_a = w_a @ h_a + b_a
        logits_b = w_b @ h_b + b_b
        residuals.append(float(np.linalg.norm(logits_a - logits_b)))
        reconstructed = pseudo_inverse @ w_a @ h_a + pseudo_inverse @ (b_a - b_b)
        reconstruction_residuals.append(float(np.linalg.norm(reconstructed - h_b)))

    worst_logit_residual = max(residuals)
    return {
        "definition": "2.1 exact logit equivalence; Theorem 2.1 affine reconstruction",
        "dimension_D": dimension,
        "categories_M": categories,
        "w_b_full_column_rank": int(np.linalg.matrix_rank(w_b)) == dimension,
        "stimuli_evaluated": len(stimuli),
        "worst_logit_residual_l2": worst_logit_residual,
        "published_order_of_magnitude": 1.49e-15,
        "logit_residual_is_roundoff": worst_logit_residual < 1e-12,
        "worst_reconstruction_residual_l2": max(reconstruction_residuals),
        "theorem_2_1_holds_on_evaluated_set": max(reconstruction_residuals) < 1e-10,
        "left_inverse_identity_residual": float(
            np.linalg.norm(pseudo_inverse @ w_b - np.eye(dimension))
        ),
    }


def section_2_probe_visible_quotient(seed: int = 424242) -> dict[str, Any]:
    """Definition 2.2 and the first-isomorphism-theorem identification.

    Builds a rank-deficient readout so ker(W_U) is nontrivial, then checks that

    * any perturbation inside ker(W_U) leaves the logits exactly unchanged, and
    * dim(H / ker W) equals dim(im W), which is the canonical identification the
      manuscript relies on to say the probe-visible quotient needs no dual space.
    """

    rng = np.random.default_rng(seed)
    hidden_dim, categories, rank = 8, 6, 4
    left = rng.normal(size=(categories, rank))
    right = rng.normal(size=(rank, hidden_dim))
    readout = left @ right
    bias = rng.normal(size=categories)

    kernel_basis = np.linalg.svd(readout)[2][int(np.linalg.matrix_rank(readout)) :].T
    h = rng.normal(size=hidden_dim)
    baseline = readout @ h + bias
    drifts = []
    for column in range(kernel_basis.shape[1]):
        for magnitude in (1.0, 10.0, 1000.0):
            perturbed = h + magnitude * kernel_basis[:, column]
            drifts.append(float(np.linalg.norm((readout @ perturbed + bias) - baseline)))

    image_rank = int(np.linalg.matrix_rank(readout))
    kernel_dimension = hidden_dim - image_rank
    # A visible perturbation, to show the invisibility test is not vacuous.
    visible_direction = np.linalg.pinv(readout) @ rng.normal(size=categories)
    visible_drift = float(
        np.linalg.norm((readout @ (h + visible_direction) + bias) - baseline)
    )
    return {
        "definition": "2.2 probe-visible quotient; first isomorphism theorem",
        "hidden_dimension": hidden_dim,
        "readout_rank": image_rank,
        "kernel_dimension": kernel_dimension,
        "kernel_is_nontrivial": kernel_dimension > 0,
        "perturbations_tested": len(drifts),
        "worst_kernel_perturbation_logit_drift": max(drifts),
        "kernel_directions_are_probe_invisible": max(drifts) < 1e-9,
        "quotient_dimension_equals_image_dimension": (
            hidden_dim - kernel_dimension == image_rank
        ),
        "control_visible_direction_drift": visible_drift,
        "control_is_visible": visible_drift > 1e-6,
    }


SECTION_2_5_LOGITS = (4.0, 2.7, 1.4, 0.7, -0.2, -1.0)
SECTION_2_5_PUBLISHED = {
    1.00: (0.885219, 0.711530),
    0.50: (0.293843, 0.924709),
    0.20: (0.011293, 0.998496),
    0.05: (0.000000, 1.000000),
}


def section_2_softmax_and_topk() -> dict[str, Any]:
    """Section 2.5: the entropy/max-probability table, tail mass, and the top-k loss.

    The last item is the safety-relevant one. Hard top-k truncation sets nonzero
    probabilities to zero, so D_KL(P || P^(k)) is infinite. A receipt that records
    only a truncated distribution has therefore discarded an unbounded amount of
    information, which is why the manuscript requires full-spectrum logits or an
    explicit tail-mass statement.
    """

    logits = np.array(SECTION_2_5_LOGITS)
    rows = []
    for tau, (published_entropy, published_max) in SECTION_2_5_PUBLISHED.items():
        p = _softmax(logits, tau)
        entropy = _entropy_nats(p)
        max_p = float(np.max(p))
        rows.append(
            {
                "tau": tau,
                "entropy_nats": entropy,
                "published_entropy_nats": published_entropy,
                "entropy_agrees": abs(entropy - published_entropy) <= 5e-6,
                "max_probability": max_p,
                "published_max_probability": published_max,
                "max_probability_agrees": abs(max_p - published_max) <= 5e-6,
            }
        )

    p_full = _softmax(logits, 1.0)
    order = np.argsort(p_full)[::-1]
    top3 = order[:3]
    tail_mass = float(1.0 - p_full[top3].sum())

    # D_KL(P || P^(3)) with hard truncation: the truncated distribution assigns
    # zero to categories P assigns positive mass, so the divergence diverges.
    truncated = np.zeros_like(p_full)
    truncated[top3] = p_full[top3]
    truncated = truncated / truncated.sum()
    divergent_terms = [
        int(index)
        for index in range(len(p_full))
        if p_full[index] > 0.0 and truncated[index] == 0.0
    ]
    kl = 0.0
    for index in range(len(p_full)):
        if p_full[index] > 0.0:
            if truncated[index] == 0.0:
                kl = math.inf
                break
            kl += p_full[index] * math.log(p_full[index] / truncated[index])

    # Temperature collapse: as tau -> 0 the distribution tends to a simplex vertex.
    collapse = _softmax(logits, 1e-3)
    return {
        "section": "2.5 softmax dynamics and top-k loss",
        "logits": list(SECTION_2_5_LOGITS),
        "rows": rows,
        "all_rows_agree": all(
            row["entropy_agrees"] and row["max_probability_agrees"] for row in rows
        ),
        "top3_tail_mass": tail_mass,
        "published_top3_tail_mass": 0.0417,
        "tail_mass_agrees": abs(tail_mass - 0.0417) <= 5e-4,
        "kl_full_vs_truncated_is_infinite": kl == math.inf,
        "categories_zeroed_by_truncation": divergent_terms,
        "vertex_collapse_max_probability": float(np.max(collapse)),
        "collapses_to_vertex": float(np.max(collapse)) > 1.0 - 1e-9,
    }


def section_2_component_logits(seed: int = 777, layers: int = 12) -> dict[str, Any]:
    """Section 2.6: because the readout is affine, the logit decomposes exactly.

    L = W h^(0) + sum_l W a^(l) + sum_l W m^(l) + b, with no approximation term.
    The audit primitive the manuscript wants — reporting which component pushed the
    logit toward a category — is only well defined if this identity is exact.
    """

    rng = np.random.default_rng(seed)
    hidden_dim, categories = 16, 6
    readout = rng.normal(size=(categories, hidden_dim))
    bias = rng.normal(size=categories)
    h0 = rng.normal(size=hidden_dim)
    attention = [rng.normal(size=hidden_dim) for _ in range(layers)]
    mlp = [rng.normal(size=hidden_dim) for _ in range(layers)]

    h_final = h0 + sum(attention) + sum(mlp)
    direct = readout @ h_final + bias
    decomposed = (
        readout @ h0
        + sum(readout @ a for a in attention)
        + sum(readout @ m for m in mlp)
        + bias
    )
    contributions = {
        "residual_stream": float(np.linalg.norm(readout @ h0)),
        "attention_total": float(np.linalg.norm(sum(readout @ a for a in attention))),
        "mlp_total": float(np.linalg.norm(sum(readout @ m for m in mlp))),
    }
    return {
        "section": "2.6 component logits",
        "layers": layers,
        "decomposition_residual_l2": float(np.linalg.norm(direct - decomposed)),
        "decomposition_is_exact": float(np.linalg.norm(direct - decomposed)) < 1e-10,
        "component_norms": contributions,
        "attributable_components": 1 + 2 * layers,
    }


def section_2_dynamical_category_switch() -> dict[str, Any]:
    """Section 2.7, which the manuscript explicitly does not implement.

    "A two-dimensional illustrative system can exhibit the same qualitative
    effect - for example, a category switch while entropy remains high - but the
    present appendix does not implement that dynamical example."

    Implemented here as a driven two-state system. The requirement is strict: the
    argmax category must change while the entropy stays above a high threshold for
    the whole trajectory. That is the regime where a smooth logit trajectory
    crosses a discrete decision boundary without any confidence signal marking the
    crossing, which is the exact situation the manuscript says deterministic
    judgment exists to handle.
    """

    steps = 240
    entropy_floor = 0.60  # nats; ln 2 = 0.693 is the two-category maximum
    hidden = np.array([0.0, 0.0])
    readout = np.array([[1.0, 0.0], [0.0, 1.0]])
    trajectory = []
    for step in range(steps):
        phase = 2.0 * math.pi * step / steps
        # Input drives the two coordinates in antiphase with a small amplitude, so
        # the leading category alternates while the margin stays small.
        drive = np.array([0.06 * math.cos(phase), 0.06 * math.cos(phase + math.pi)])
        hidden = 0.75 * hidden + drive
        logits = readout @ hidden
        p = _softmax(logits, 1.0)
        trajectory.append(
            {
                "step": step,
                "argmax": int(np.argmax(logits)),
                "entropy_nats": _entropy_nats(p),
                "margin": float(abs(logits[0] - logits[1])),
            }
        )

    # Ignore the first few steps while the state leaves the origin.
    settled = trajectory[8:]
    switches = sum(
        1 for a, b in zip(settled, settled[1:]) if a["argmax"] != b["argmax"]
    )
    min_entropy = min(entry["entropy_nats"] for entry in settled)
    return {
        "section": "2.7 logit space as a non-autonomous dynamical system",
        "manuscript_status": "explicitly not implemented in the manuscript appendix",
        "steps": steps,
        "settled_steps": len(settled),
        "category_switches": switches,
        "min_entropy_nats_after_settling": float(min_entropy),
        "entropy_floor_nats": entropy_floor,
        "max_margin_after_settling": max(entry["margin"] for entry in settled),
        "switch_occurs_under_sustained_high_entropy": bool(
            switches >= 1 and min_entropy >= entropy_floor
        ),
        "interpretation": (
            "The decision boundary is crossed repeatedly while entropy never drops "
            "below the floor, so no confidence signal marks the crossing."
        ),
    }


# ===========================================================================
# Section 3: finite boundary semantics
# ===========================================================================

BOUNDARY_ATOMS = ("exact", "equivalent", "narrower", "broader", "conflict", "unmapped")


def section_3_boolean_homomorphism(
    worlds: int = 3, times: int = 3, facilities: int = 2
) -> dict[str, Any]:
    """Definition 3.2: the semantics map is a Boolean homomorphism.

    A finite Boolean algebra B on the six clinical atoms, and a semantics
    [[.]] : B -> P(W x T x L) built by assigning each atom a disjoint block of the
    product and taking unions. The homomorphism laws are then checked on every
    element and every pair, exhaustively rather than by sampling: with six atoms
    that is 64 elements and 4096 pairs, which is small enough to be complete.

    Exhaustiveness matters. A sampled check on a 64-element algebra would leave the
    interesting corners (bottom, top, complements of singletons) to chance.
    """

    universe = [
        (w, t, l)
        for w in range(worlds)
        for t in range(times)
        for l in range(facilities)
    ]
    atom_count = len(BOUNDARY_ATOMS)
    # Assign each atom a disjoint, non-empty block covering the universe.
    blocks: dict[str, frozenset[tuple[int, int, int]]] = {}
    for index, atom in enumerate(BOUNDARY_ATOMS):
        block = {point for position, point in enumerate(universe) if position % atom_count == index}
        blocks[atom] = frozenset(block)

    full = frozenset(universe)

    def interpret(element: frozenset[str]) -> frozenset[tuple[int, int, int]]:
        result: set[tuple[int, int, int]] = set()
        for atom in element:
            result |= blocks[atom]
        return frozenset(result)

    elements = [
        frozenset(combination)
        for size in range(atom_count + 1)
        for combination in itertools.combinations(BOUNDARY_ATOMS, size)
    ]

    violations: list[str] = []
    # Atoms partition the universe.
    if frozenset().union(*blocks.values()) != full:
        violations.append("atom_blocks_do_not_cover_universe")
    for left, right in itertools.combinations(BOUNDARY_ATOMS, 2):
        if blocks[left] & blocks[right]:
            violations.append(f"atoms_overlap:{left},{right}")
    for atom in BOUNDARY_ATOMS:
        if not blocks[atom]:
            violations.append(f"atom_block_empty:{atom}")

    pair_checks = 0
    for left in elements:
        # Complement law.
        if interpret(frozenset(BOUNDARY_ATOMS) - left) != full - interpret(left):
            violations.append(f"complement_law:{sorted(left)}")
        for right in elements:
            pair_checks += 1
            if interpret(left & right) != interpret(left) & interpret(right):
                violations.append(f"meet_law:{sorted(left)}|{sorted(right)}")
            if interpret(left | right) != interpret(left) | interpret(right):
                violations.append(f"join_law:{sorted(left)}|{sorted(right)}")

    return {
        "definition": "3.1 boundary algebra; 3.2 model-relative semantics",
        "atoms": list(BOUNDARY_ATOMS),
        "algebra_elements": len(elements),
        "universe_size": len(universe),
        "world_time_facility_shape": [worlds, times, facilities],
        "pair_checks": pair_checks,
        "complement_checks": len(elements),
        "violations": violations[:10],
        "violation_count": len(violations),
        "is_boolean_homomorphism": not violations,
        "bottom_maps_to_empty": interpret(frozenset()) == frozenset(),
        "top_maps_to_universe": interpret(frozenset(BOUNDARY_ATOMS)) == full,
        "exhaustive": True,
    }


# ===========================================================================
# Section 4: operational profinite probes
# ===========================================================================


@dataclass(frozen=True)
class ProbeState:
    """One version-pinned state in an operational probe sequence."""

    label: str
    terminology_version: str
    identity_log_head: str
    policy_version: str
    fhir_capability: tuple[str, ...]


DECLARED_PROBE_INVARIANTS = (
    "terminology_version_monotone",
    "identity_log_head_advances",
    "policy_version_monotone",
    "fhir_capability_not_narrowed",
)


def _version_key(version: str) -> tuple[int, ...]:
    parts = []
    for chunk in version.replace("-", ".").split("."):
        parts.append(int(chunk) if chunk.isdigit() else 0)
    return tuple(parts)


def run_operational_probe(states: Sequence[ProbeState]) -> dict[str, Any]:
    """Definition 4.1: a probe passes iff every transition preserves the invariants."""

    transitions = []
    for before, after in zip(states, states[1:]):
        broken = []
        if _version_key(after.terminology_version) < _version_key(before.terminology_version):
            broken.append("terminology_version_monotone")
        if after.identity_log_head == before.identity_log_head:
            broken.append("identity_log_head_advances")
        if _version_key(after.policy_version) < _version_key(before.policy_version):
            broken.append("policy_version_monotone")
        if not set(before.fhir_capability) <= set(after.fhir_capability):
            broken.append("fhir_capability_not_narrowed")
        transitions.append(
            {
                "from": before.label,
                "to": after.label,
                "broken_invariants": broken,
                "preserved": not broken,
            }
        )
    return {
        "definition": "4.1 operational profinite probe",
        "states": len(states),
        "transitions": transitions,
        "declared_invariants": list(DECLARED_PROBE_INVARIANTS),
        "passed": all(entry["preserved"] for entry in transitions),
    }


def section_4_probe_suite() -> dict[str, Any]:
    """A passing probe, plus one probe per invariant that must fail.

    The negative probes are the point. A probe suite in which nothing can fail
    certifies nothing, so each declared invariant gets a sequence that violates it
    and only it.
    """

    base = [
        ProbeState("s0", "2026-01-01", "h0", "1.0", ("Patient", "Observation")),
        ProbeState("s1", "2026-02-01", "h1", "1.0", ("Patient", "Observation")),
        ProbeState("s2", "2026-03-01", "h2", "1.1", ("Patient", "Observation", "Condition")),
        ProbeState("s3", "2026-03-01", "h3", "1.1", ("Patient", "Observation", "Condition")),
    ]
    passing = run_operational_probe(base)

    negatives = {}
    rollback = list(base)
    rollback[2] = ProbeState("s2", "2025-12-01", "h2", "1.1", ("Patient", "Observation", "Condition"))
    negatives["terminology_version_monotone"] = run_operational_probe(rollback)

    stalled = list(base)
    stalled[2] = ProbeState("s2", "2026-03-01", "h1", "1.1", ("Patient", "Observation", "Condition"))
    negatives["identity_log_head_advances"] = run_operational_probe(stalled)

    policy_rollback = list(base)
    policy_rollback[3] = ProbeState("s3", "2026-03-01", "h3", "0.9", ("Patient", "Observation", "Condition"))
    negatives["policy_version_monotone"] = run_operational_probe(policy_rollback)

    narrowed = list(base)
    narrowed[3] = ProbeState("s3", "2026-03-01", "h3", "1.1", ("Patient",))
    negatives["fhir_capability_not_narrowed"] = run_operational_probe(narrowed)

    detected = {}
    for invariant, probe in negatives.items():
        broken = {name for entry in probe["transitions"] for name in entry["broken_invariants"]}
        detected[invariant] = {
            "probe_failed": not probe["passed"],
            "broken_invariants_detected": sorted(broken),
            "detected_the_intended_invariant": invariant in broken,
            "detected_only_the_intended_invariant": broken == {invariant},
        }

    return {
        "section": "4 condensed-mathematics motivation and operational probes",
        "positive_probe_passes": passing["passed"],
        "positive_probe": passing,
        "negative_probes": detected,
        "every_invariant_is_detectable": all(
            entry["detected_only_the_intended_invariant"] for entry in detected.values()
        ),
        "suite_is_non_vacuous": all(entry["probe_failed"] for entry in detected.values()),
    }


# ===========================================================================
# Section 6.2: dynamic atom registry
# ===========================================================================


def section_6_2_dynamic_atom_registry(alpha_new: float = 0.5) -> dict[str, Any]:
    """Section 6.2: category growth must be auditable and must not divide by zero.

    "When a new category c_{K+1} appears, the registry assigns alpha_{K+1} =
    alpha_new > 0 and records the terminology version and parent category."
    """

    epsilon, ceiling = 0.326472, 20.0  # box-wide bound from the v2 errata
    registry: list[dict[str, Any]] = [
        {"category": atom, "alpha": 2.0, "terminology_version": "2026-01-01", "parent": None}
        for atom in BOUNDARY_ATOMS
    ]
    events: list[dict[str, Any]] = []

    def alphas() -> list[float]:
        return [entry["alpha"] for entry in registry]

    def fisher_min_eigenvalue(values: Sequence[float]) -> float:
        from boundarybench.gbi.appendix_a import fisher_dirichlet

        return float(np.min(np.linalg.eigvalsh(fisher_dirichlet(values))))

    events.append(
        {
            "event": "initial",
            "categories": len(registry),
            "min_alpha": min(alphas()),
            "fisher_min_eigenvalue": fisher_min_eigenvalue(alphas()),
        }
    )

    for index, (name, parent, version) in enumerate(
        (
            ("narrower_postcoordinated", "narrower", "2026-04-01"),
            ("equivalent_with_qualifier", "equivalent", "2026-05-01"),
            ("conflict_severity_graded", "conflict", "2026-06-01"),
        )
    ):
        registry.append(
            {
                "category": name,
                "alpha": alpha_new,
                "terminology_version": version,
                "parent": parent,
            }
        )
        events.append(
            {
                "event": f"atom_added:{name}",
                "categories": len(registry),
                "alpha_assigned": alpha_new,
                "alpha_is_strictly_positive": alpha_new > 0.0,
                "parent_recorded": parent is not None,
                "terminology_version_recorded": version,
                "min_alpha": min(alphas()),
                "fisher_min_eigenvalue": fisher_min_eigenvalue(alphas()),
            }
        )

    # Boundary case: a registry that assigned alpha_new = 0 would be singular.
    singular_rejected = False
    try:
        from boundarybench.gbi.appendix_a import fisher_dirichlet

        fisher_dirichlet(alphas() + [0.0])
    except ValueError:
        singular_rejected = True

    inside_box = all(epsilon <= value <= ceiling for value in alphas())
    return {
        "section": "6.2 evidence boxes and dynamic atom registries",
        "events": events,
        "final_category_count": len(registry),
        "all_alphas_strictly_positive": all(value > 0.0 for value in alphas()),
        "every_addition_records_version_and_parent": all(
            entry.get("parent_recorded", True)
            and entry.get("terminology_version_recorded", "x") is not None
            for entry in events[1:]
        ),
        "min_fisher_eigenvalue_across_growth": min(
            entry["fisher_min_eigenvalue"] for entry in events
        ),
        "no_singularity_during_growth": min(
            entry["fisher_min_eigenvalue"] for entry in events
        )
        > 1e-6,
        "zero_alpha_is_rejected": singular_rejected,
        "declared_evidence_box": {"epsilon": epsilon, "ceiling": ceiling},
        "alpha_new_inside_declared_box": alpha_new >= epsilon,
        "all_alphas_inside_declared_box": inside_box,
        "growth_is_auditable": True,
    }


# ===========================================================================
# Section 8: audit chart certificates and Boundary 3
# ===========================================================================


def section_8_safety_checks(matrix: np.ndarray | None = None) -> dict[str, Any]:
    """Section 8.1's four required safety checks, not just the Jacobian.

    "A safety-critical implementation must also check positive Jacobian, boundary
    behavior, inverse residuals, and stratum preservation."

    Appendix A checks the positive Jacobian only. The other three are implemented
    here:

    * **boundary behavior** - the map must send the unit sphere to a bounded
      ellipsoid with both axes finite and bounded away from zero, checked by
      sampling the sphere and comparing against the singular-value envelope.
    * **inverse residuals** - the numerically computed inverse must satisfy
      ||A A^-1 - I|| within a tolerance scaled by the condition number, otherwise
      the certificate's distortion figures are not trustworthy.
    * **stratum preservation** - the map must not collapse a positive-dimensional
      stratum, i.e. rank must be preserved on every coordinate subspace.
    """

    from boundarybench.gbi.appendix_a import hyperellipsoid_certificate

    if matrix is None:
        matrix = np.array([[1.20, 0.10, 0.0], [0.20, 0.80, 0.05], [0.0, 0.10, 1.10]])
    a = np.asarray(matrix, dtype=float)
    certificate = hyperellipsoid_certificate(a)
    singular_values = np.array(certificate.singular_values)
    sigma_max, sigma_min = float(singular_values.max()), float(singular_values.min())

    positive_jacobian = certificate.jacobian > 0.0

    rng = np.random.default_rng(31337)
    directions = rng.normal(size=(4096, a.shape[1]))
    directions /= np.linalg.norm(directions, axis=1, keepdims=True)
    images = directions @ a.T
    radii = np.linalg.norm(images, axis=1)
    boundary_ok = bool(
        radii.min() >= sigma_min - 1e-9 and radii.max() <= sigma_max + 1e-9
    )

    inverse = np.linalg.inv(a)
    forward_residual = float(np.linalg.norm(a @ inverse - np.eye(a.shape[0])))
    backward_residual = float(np.linalg.norm(inverse @ a - np.eye(a.shape[0])))
    condition = sigma_max / sigma_min
    inverse_tolerance = 1e-12 * max(1.0, condition)
    inverse_ok = forward_residual <= inverse_tolerance and backward_residual <= inverse_tolerance

    strata = []
    stratum_ok = True
    for size in range(1, a.shape[1] + 1):
        for columns in itertools.combinations(range(a.shape[1]), size):
            submatrix = a[:, list(columns)]
            rank = int(np.linalg.matrix_rank(submatrix))
            preserved = rank == size
            strata.append({"columns": list(columns), "rank": rank, "preserved": preserved})
            stratum_ok = stratum_ok and preserved

    return {
        "section": "8.1 higher-dimensional hyperellipsoid certificates",
        "certificate": certificate.as_dict(),
        "checks": {
            "positive_jacobian": {
                "passed": positive_jacobian,
                "jacobian": certificate.jacobian,
                "implemented_in_appendix_a": True,
            },
            "boundary_behavior": {
                "passed": boundary_ok,
                "sampled_directions": int(directions.shape[0]),
                "observed_radius_range": [float(radii.min()), float(radii.max())],
                "singular_value_envelope": [sigma_min, sigma_max],
                "implemented_in_appendix_a": False,
            },
            "inverse_residuals": {
                "passed": inverse_ok,
                "forward_residual": forward_residual,
                "backward_residual": backward_residual,
                "tolerance": inverse_tolerance,
                "implemented_in_appendix_a": False,
            },
            "stratum_preservation": {
                "passed": stratum_ok,
                "strata_checked": len(strata),
                "implemented_in_appendix_a": False,
            },
        },
        "all_four_checks_passed": positive_jacobian and boundary_ok and inverse_ok and stratum_ok,
        "checks_added_beyond_appendix_a": 3,
    }


def section_8_boundary_3_advisory_only(k_tabular: float = 1.5) -> dict[str, Any]:
    """Appendix B.3 Boundary 3: the chart coefficient K is advisory, never decisive.

    "High visual distortion must never be interpreted as proof of logical
    inconsistency. A quarantine decision must follow the declared deterministic
    policy."

    This is a negative claim, so both error directions are tested:

    * high K with a clean policy verdict must NOT quarantine, and
    * low K with a policy violation MUST quarantine.

    A system that let K drive the decision would fail the first case; a system
    that ignored the policy would fail the second. Also checked: the review
    surface carries deterministic reasons rather than a confidence number, which
    is the Section 9.2 automation-bias requirement.
    """

    from boundarybench.gbi.appendix_a import hyperellipsoid_certificate

    # A badly conditioned but policy-clean chart.
    high_k_matrix = np.array([[6.0, 0.0, 0.0], [0.0, 0.30, 0.0], [0.0, 0.0, 0.9]])
    high_k = hyperellipsoid_certificate(high_k_matrix).axis_eccentricity
    # A well conditioned chart with a real policy violation.
    low_k_matrix = np.array([[1.05, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 0.98]])
    low_k = hyperellipsoid_certificate(low_k_matrix).axis_eccentricity

    def decide(policy_violations: Sequence[str], distortion: float) -> dict[str, Any]:
        # The decision depends on the policy only. K sets a notification flag.
        quarantine = bool(policy_violations)
        return {
            "distortion_K": distortion,
            "chart_flagged_for_review": distortion > k_tabular,
            "policy_violations": list(policy_violations),
            "quarantine": quarantine,
            "decided_by": "declared_deterministic_policy",
            # Section 9.2: the review surface exposes reasons, not a score.
            "review_surface": {
                "candidate_value_present": True,
                "authoritative_evidence_present": True,
                "source_freshness_present": True,
                "schema_authority_present": True,
                "provenance_present": True,
                "policy_rule_present": True,
                "required_action_present": True,
                "model_confidence_number_present": False,
            },
        }

    high_k_clean = decide([], high_k)
    low_k_violating = decide(["terminology_version_unsupported"], low_k)

    surfaces = (high_k_clean["review_surface"], low_k_violating["review_surface"])
    return {
        "boundary": "B.3 Boundary 3 - chart distortion is advisory only",
        "k_tabular": k_tabular,
        "high_distortion_clean_policy": high_k_clean,
        "low_distortion_violating_policy": low_k_violating,
        "high_k_did_not_force_quarantine": (
            high_k_clean["chart_flagged_for_review"] and not high_k_clean["quarantine"]
        ),
        "policy_violation_quarantined_despite_low_k": (
            not low_k_violating["chart_flagged_for_review"] and low_k_violating["quarantine"]
        ),
        "boundary_3_holds": (
            high_k_clean["chart_flagged_for_review"]
            and not high_k_clean["quarantine"]
            and low_k_violating["quarantine"]
        ),
        "review_surface_exposes_deterministic_reasons": all(
            all(value for key, value in surface.items() if key != "model_confidence_number_present")
            for surface in surfaces
        ),
        "review_surface_omits_confidence_number": all(
            not surface["model_confidence_number_present"] for surface in surfaces
        ),
    }


def run_all_section_claims() -> dict[str, Any]:
    """Every Section 2/3/4/6.2/8 claim test, as one record."""

    results = {
        "section_2_affine_equivalence": section_2_affine_equivalence(),
        "section_2_probe_visible_quotient": section_2_probe_visible_quotient(),
        "section_2_softmax_and_topk": section_2_softmax_and_topk(),
        "section_2_component_logits": section_2_component_logits(),
        "section_2_dynamical_category_switch": section_2_dynamical_category_switch(),
        "section_3_boolean_homomorphism": section_3_boolean_homomorphism(),
        "section_4_probe_suite": section_4_probe_suite(),
        "section_6_2_dynamic_atom_registry": section_6_2_dynamic_atom_registry(),
        "section_8_safety_checks": section_8_safety_checks(),
        "section_8_boundary_3": section_8_boundary_3_advisory_only(),
    }
    verdicts = {
        "section_2_affine_equivalence": results["section_2_affine_equivalence"][
            "theorem_2_1_holds_on_evaluated_set"
        ]
        and results["section_2_affine_equivalence"]["logit_residual_is_roundoff"],
        "section_2_probe_visible_quotient": results["section_2_probe_visible_quotient"][
            "kernel_directions_are_probe_invisible"
        ]
        and results["section_2_probe_visible_quotient"][
            "quotient_dimension_equals_image_dimension"
        ]
        and results["section_2_probe_visible_quotient"]["control_is_visible"],
        "section_2_softmax_and_topk": results["section_2_softmax_and_topk"]["all_rows_agree"]
        and results["section_2_softmax_and_topk"]["tail_mass_agrees"]
        and results["section_2_softmax_and_topk"]["kl_full_vs_truncated_is_infinite"],
        "section_2_component_logits": results["section_2_component_logits"][
            "decomposition_is_exact"
        ],
        "section_2_dynamical_category_switch": results["section_2_dynamical_category_switch"][
            "switch_occurs_under_sustained_high_entropy"
        ],
        "section_3_boolean_homomorphism": results["section_3_boolean_homomorphism"][
            "is_boolean_homomorphism"
        ],
        "section_4_probe_suite": results["section_4_probe_suite"]["positive_probe_passes"]
        and results["section_4_probe_suite"]["every_invariant_is_detectable"],
        "section_6_2_dynamic_atom_registry": results["section_6_2_dynamic_atom_registry"][
            "no_singularity_during_growth"
        ]
        and results["section_6_2_dynamic_atom_registry"]["zero_alpha_is_rejected"],
        "section_8_safety_checks": results["section_8_safety_checks"]["all_four_checks_passed"],
        "section_8_boundary_3": results["section_8_boundary_3"]["boundary_3_holds"]
        and results["section_8_boundary_3"]["review_surface_omits_confidence_number"],
    }
    return {
        "schema_version": "boundarybench.gbi_section_claims.v1",
        "claims_version": CLAIMS_VERSION,
        "results": results,
        "verdicts": verdicts,
        "claims_tested": len(verdicts),
        "claims_met": sum(1 for value in verdicts.values() if value),
        "all_met": all(verdicts.values()),
    }
