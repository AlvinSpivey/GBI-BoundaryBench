"""Severe-contradiction injection, following Table 3's stated methodology.

Appendix B.2 specifies that Severe Contradiction Sensitivity is to be measured by
*"golden-standard retrospective chart injection"*: contradictions are introduced
deliberately into otherwise clean records, and the substrate is scored on whether
it catches every one.

This module implements the synthetic analogue. It takes a population of witness
bundles, partitions it, and injects severe contradictions into a declared subset,
recording exactly what was injected where.

Three properties matter for the measurement to mean anything.

* **Disjointness.** The injected population and the clean population never
  overlap. Sensitivity is measured only on injected records; the false-conflict
  rate is measured only on records that were clean before injection and left
  alone. If these overlapped, one target could be met by borrowing from the other.
* **Class coverage.** Injection round-robins over every severe class, including
  four classes the base simulator never produces (unsigned bundle, unpinned
  bundle, expired window, invalid window). Sensitivity therefore tests policy
  *coverage*, not just agreement with corruptions the generator already made.
* **Injection is recorded, not inferred.** Every injected class is stamped onto
  the witness in ``injected_classes`` and returned in a manifest, so the scorer
  never has to guess which records were tampered with.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
from typing import Any, Callable

from boundarybench.betal.witness import WitnessBundle

INJECTION_VERSION = "gbi-v2-contradiction-injection-v1"

# Injectable severe classes. The first four are *not* producible by the base
# simulator, so they test gate coverage rather than manifest agreement.
INJECTABLE_CLASSES: tuple[str, ...] = (
    "terminology_bundle_unsigned",
    "terminology_bundle_unpinned",
    "validity_window_expired",
    "validity_window_invalid",
    "identity_ambiguous",
    "identity_unresolvable",
    "provenance_signature_absent",
    "terminology_unresolvable",
    "structured_field_fully_contaminated",
    "required_evidence_absent",
)

BASE_SIMULATOR_CANNOT_PRODUCE: frozenset[str] = frozenset(
    {
        "terminology_bundle_unsigned",
        "terminology_bundle_unpinned",
        "validity_window_expired",
        "validity_window_invalid",
    }
)

_MUTATIONS: dict[str, Callable[[WitnessBundle], WitnessBundle]] = {
    "terminology_bundle_unsigned": lambda w: replace(w, bundle_signed=False),
    "terminology_bundle_unpinned": lambda w: replace(w, bundle_pinned=False),
    "validity_window_expired": lambda w: replace(w, validity_window_expired=True),
    "validity_window_invalid": lambda w: replace(w, validity_window_valid=False),
    # Injected ambiguity keeps a deliberately high similarity score: Boundary 1
    # says the score must not override the ambiguity finding, so the injected
    # population directly stresses that rule.
    "identity_ambiguous": lambda w: replace(
        w, identity_status="ambiguous", identity_mismatched_field_count=1,
        identity_match_score=max(w.identity_match_score, 0.97),
    ),
    "identity_unresolvable": lambda w: replace(
        w, identity_status="unresolvable", identity_mismatched_field_count=3,
        identity_match_score=max(w.identity_match_score, 0.95),
    ),
    "provenance_signature_absent": lambda w: replace(w, provenance_signature_present=False),
    "terminology_unresolvable": lambda w: replace(
        w, code_resolvable=False, code_superseded=True, declared_code_version="unknown"
    ),
    "structured_field_fully_contaminated": lambda w: replace(w, field_contamination="full"),
    "required_evidence_absent": lambda w: replace(
        w, required_fact_count=5, absent_fact_count=2, evidence_completeness=0.6
    ),
}


def _rank(*parts: str) -> int:
    return int.from_bytes(hashlib.sha256("|".join(parts).encode("utf-8")).digest()[:8], "big")


@dataclass
class InjectionResult:
    witnesses: list[WitnessBundle]
    injected_task_ids: tuple[str, ...]
    clean_task_ids: tuple[str, ...]
    base_severe_task_ids: tuple[str, ...]
    manifest: dict[str, Any]


def inject_severe_contradictions(
    witnesses: list[WitnessBundle],
    *,
    injection_rate: float = 0.5,
    seed: str = "injection",
) -> InjectionResult:
    """Inject severe contradictions into a disjoint subset of the clean population.

    Records that already carry a severe contradiction from the base simulator are
    left untouched and reported separately: they belong to neither the injected
    population nor the clean population, because for them neither target's
    denominator is well defined by Table 3's methodology.
    """

    if not 0.0 <= injection_rate <= 1.0:
        raise ValueError("injection_rate must lie in [0,1]")

    base_severe = [w for w in witnesses if w.is_severe]
    eligible = [w for w in witnesses if not w.is_severe]
    ordered = sorted(eligible, key=lambda w: _rank(seed, w.task_id))
    injected_count = int(round(len(ordered) * injection_rate))
    to_inject = ordered[:injected_count]
    to_leave = ordered[injected_count:]

    injected_ids = {w.task_id for w in to_inject}
    class_assignment: dict[str, str] = {}
    for position, witness in enumerate(to_inject):
        class_assignment[witness.task_id] = INJECTABLE_CLASSES[position % len(INJECTABLE_CLASSES)]

    result: list[WitnessBundle] = []
    per_class: dict[str, int] = {}
    for witness in witnesses:
        if witness.task_id in injected_ids:
            injected_class = class_assignment[witness.task_id]
            mutated = _MUTATIONS[injected_class](witness)
            mutated = replace(mutated, injected_classes=(injected_class,))
            per_class[injected_class] = per_class.get(injected_class, 0) + 1
            result.append(mutated)
        else:
            result.append(witness)

    # Post-condition: every injected record must actually be severe now, and every
    # left-alone record must still be non-severe. A silent failure here would
    # corrupt both denominators.
    by_id = {w.task_id: w for w in result}
    injected_not_severe = sorted(i for i in injected_ids if not by_id[i].is_severe)
    left_alone_severe = sorted(w.task_id for w in to_leave if by_id[w.task_id].is_severe)
    if injected_not_severe or left_alone_severe:
        raise AssertionError(
            "injection post-condition violated: "
            f"injected_not_severe={injected_not_severe} left_alone_severe={left_alone_severe}"
        )

    manifest = {
        "schema_version": "boundarybench.gbi_v2_injection_manifest.v1",
        "injection_version": INJECTION_VERSION,
        "seed": seed,
        "injection_rate": injection_rate,
        "population": {
            "total": len(witnesses),
            "base_severe": len(base_severe),
            "injected_severe": len(to_inject),
            "clean_left_alone": len(to_leave),
        },
        "injected_per_class": dict(sorted(per_class.items())),
        "classes_not_producible_by_base_simulator": sorted(BASE_SIMULATOR_CANNOT_PRODUCE),
        "disjointness_verified": True,
        "methodology_note": (
            "Synthetic analogue of Appendix B.2's golden-standard retrospective chart "
            "injection. No clinical chart, cohort, or adjudication is involved."
        ),
    }
    return InjectionResult(
        witnesses=result,
        injected_task_ids=tuple(sorted(injected_ids)),
        clean_task_ids=tuple(sorted(w.task_id for w in to_leave)),
        base_severe_task_ids=tuple(sorted(w.task_id for w in base_severe)),
        manifest=manifest,
    )
