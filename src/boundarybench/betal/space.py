"""Declared parameter space V for BeTaL-GBI benchmark tuning.

The parameter space is the object the Designer searches. It is deliberately
finite, typed, and version-pinned: every dimension has an explicit domain, an
explicit projection rule, and an explicit declared monotone direction with
respect to task difficulty.

Nothing in this module is a claim about clinical difficulty. The declared
difficulty map is a property of the *simulator*, not of medicine and not of any
model. It exists so that difficulty scaling is auditable rather than emergent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import math
from typing import Any, Literal

SPACE_VERSION = "betal-gbi-parameter-space-v0.2"

Kind = Literal["continuous", "integer"]


@dataclass(frozen=True)
class ParamSpec:
    """One controllable dimension of the design space V."""

    name: str
    kind: Kind
    low: float
    high: float
    step: float
    family: str
    harder_direction: Literal["up", "down"]
    description: str

    def project(self, value: Any) -> tuple[float | int, tuple[str, ...]]:
        """Project an arbitrary proposal onto this dimension's domain.

        Mirrors BeTaL's ``ProjectToDomain``. Returns the projected value and a
        tuple of non-fatal projection notes so that designer drift is visible in
        the run record instead of being silently absorbed.
        """

        notes: list[str] = []
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            try:
                value = float(value)  # type: ignore[arg-type]
                notes.append(f"{self.name}:coerced_to_number")
            except (TypeError, ValueError):
                notes.append(f"{self.name}:uninterpretable_replaced_with_low")
                value = self.low
        if math.isnan(float(value)) or math.isinf(float(value)):
            notes.append(f"{self.name}:non_finite_replaced_with_low")
            value = self.low
        numeric = float(value)
        if numeric < self.low:
            notes.append(f"{self.name}:clamped_low")
            numeric = self.low
        if numeric > self.high:
            notes.append(f"{self.name}:clamped_high")
            numeric = self.high
        snapped = self.low + round((numeric - self.low) / self.step) * self.step
        snapped = min(max(snapped, self.low), self.high)
        if abs(snapped - numeric) > 1e-12:
            notes.append(f"{self.name}:snapped_to_step")
        if self.kind == "integer":
            return int(round(snapped)), tuple(notes)
        # Guard against float accumulation on the declared grid.
        return round(snapped, 10), tuple(notes)

    def easy_end(self) -> float | int:
        return self.low if self.harder_direction == "up" else self.high

    def hard_end(self) -> float | int:
        return self.high if self.harder_direction == "up" else self.low


PARAMETER_SPECS: tuple[ParamSpec, ...] = (
    ParamSpec(
        name="patient_identity_normalization",
        kind="continuous",
        low=0.0,
        high=1.0,
        step=0.05,
        family="patient_identity_normalization",
        harder_direction="up",
        description=(
            "Fraction of DEM identity fields carrying transcription, truncation, or "
            "transposition noise. Higher values shrink the separation between a "
            "supportable identity link and a required quarantine."
        ),
    ),
    ParamSpec(
        name="orphan_rate",
        kind="continuous",
        low=0.0,
        high=0.5,
        step=0.05,
        family="orphan_duplicate_detection",
        harder_direction="up",
        description=(
            "Fraction of patient references pointing at absent or duplicated DEM rows. "
            "Higher values increase the number of records whose correct action is "
            "quarantine_slice or expert_review rather than admit."
        ),
    ),
    ParamSpec(
        name="field_anomaly_bleed",
        kind="continuous",
        low=0.0,
        high=0.5,
        step=0.05,
        family="field_anomaly_bleed",
        harder_direction="up",
        description=(
            "Frequency at which free-text narrative bleeds into a structured column. "
            "Targets the failure mode responsible for the v0.1 safe_parse_reject slice."
        ),
    ),
    ParamSpec(
        name="code_system_version_validation",
        kind="continuous",
        low=0.0,
        high=1.0,
        step=0.05,
        family="code_system_version_validation",
        harder_direction="up",
        description=(
            "Fraction of coded evidence pinned to an unsupported or superseded "
            "terminology version. Higher values raise the count of tasks whose only "
            "admissible outcome is admit_historical_only or reject."
        ),
    ),
    ParamSpec(
        name="mapping_arity",
        kind="integer",
        low=1,
        high=6,
        step=1,
        family="rpms_to_fhir_mapping",
        harder_direction="up",
        description=(
            "Number of candidate FHIR target resources offered for one RPMS-shaped row. "
            "Higher arity widens the local categorical decision the model must resolve."
        ),
    ),
    ParamSpec(
        name="temporal_ambiguity",
        kind="continuous",
        low=0.0,
        high=1.0,
        step=0.05,
        family="temporal_status_classification",
        harder_direction="up",
        description=(
            "Fraction of records whose validity interval is open, stale, or overlapping, "
            "so that active and historical-only evidence are not separable by date alone."
        ),
    ),
    ParamSpec(
        name="evidence_sufficiency",
        kind="integer",
        low=0,
        high=10,
        step=1,
        family="evidence_sufficiency",
        harder_direction="up",
        description=(
            "Count of facts required by the reference answer that are withheld from the "
            "model input. Higher values reward abstention and punish confident assertion."
        ),
    ),
    ParamSpec(
        name="policy_conflict_depth",
        kind="integer",
        low=0,
        high=4,
        step=1,
        family="policy_action_selection",
        harder_direction="up",
        description=(
            "Number of simultaneously firing policy predicates whose fail-closed "
            "precedence order must be applied to select a single action."
        ),
    ),
    ParamSpec(
        name="distractor_actions",
        kind="integer",
        low=0,
        high=5,
        step=1,
        family="*",
        harder_direction="up",
        description=(
            "Count of allowed-but-incorrect actions retained in the task's allowed_actions "
            "list. Applies to every family; widens the categorical decision uniformly."
        ),
    ),
)

PARAMETERS: dict[str, ParamSpec] = {spec.name: spec for spec in PARAMETER_SPECS}

FAMILY_PARAMETER: dict[str, str] = {
    spec.family: spec.name for spec in PARAMETER_SPECS if spec.family != "*"
}

TASK_FAMILIES: tuple[str, ...] = tuple(FAMILY_PARAMETER)


@dataclass(frozen=True)
class Configuration:
    """A projected point v in V, with its provenance."""

    values: dict[str, float | int]
    projection_notes: tuple[str, ...] = ()
    origin: str = "unspecified"

    def digest(self) -> str:
        payload = json.dumps(self.values, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def as_dict(self) -> dict[str, Any]:
        return {
            "space_version": SPACE_VERSION,
            "origin": self.origin,
            "values": dict(sorted(self.values.items())),
            "projection_notes": list(self.projection_notes),
            "config_sha256": self.digest(),
        }


def project_to_domain(proposal: dict[str, Any], *, origin: str = "designer") -> Configuration:
    """Project an arbitrary designer proposal into V.

    Unknown keys are dropped and recorded. Missing keys fall back to the easy end
    of their dimension, which is the conservative choice: a designer that fails to
    name a dimension does not silently get a hard benchmark.
    """

    values: dict[str, float | int] = {}
    notes: list[str] = []
    for key in sorted(set(proposal) - set(PARAMETERS)):
        notes.append(f"{key}:unknown_parameter_dropped")
    for name, spec in PARAMETERS.items():
        if name not in proposal:
            values[name] = spec.easy_end()
            notes.append(f"{name}:missing_defaulted_to_easy_end")
            continue
        projected, param_notes = spec.project(proposal[name])
        values[name] = projected
        notes.extend(param_notes)
    return Configuration(values=values, projection_notes=tuple(notes), origin=origin)


def configuration_from_dial(t: float, *, origin: str = "dial") -> Configuration:
    """Map a scalar dial t in [0,1] onto a monotone path through V.

    The dial exists for two reasons. First, it gives the offline reference
    designer a one-dimensional, declared-monotone handle so that its search is
    reproducible without a model call. Second, it defines the ordered reference
    path against which a real LLM designer's multi-dimensional proposals can be
    compared. It is a convenience path, not a claim that V is one-dimensional.
    """

    t = min(max(float(t), 0.0), 1.0)
    proposal: dict[str, Any] = {}
    for name, spec in PARAMETERS.items():
        easy = float(spec.easy_end())
        hard = float(spec.hard_end())
        proposal[name] = easy + t * (hard - easy)
    config = project_to_domain(proposal, origin=origin)
    return Configuration(
        values=config.values,
        projection_notes=tuple(
            note for note in config.projection_notes if not note.endswith(":snapped_to_step")
        ),
        origin=origin,
    )


def dial_of_configuration(config: Configuration) -> float:
    """Invert ``configuration_from_dial`` approximately, by averaging normalized position."""

    positions: list[float] = []
    for name, spec in PARAMETERS.items():
        easy = float(spec.easy_end())
        hard = float(spec.hard_end())
        if hard == easy:
            continue
        positions.append((float(config.values[name]) - easy) / (hard - easy))
    return sum(positions) / len(positions) if positions else 0.0


# --- Declared difficulty map -------------------------------------------------
#
# base + slope * normalized_parameter, per family. These constants are declared
# simulator parameters. They are not fitted to any model and are not clinical
# severity weights.

_DIFFICULTY_MAP: dict[str, tuple[float, float]] = {
    "patient_identity_normalization": (0.15, 0.85),
    "orphan_duplicate_detection": (0.15, 0.85),
    "field_anomaly_bleed": (0.15, 0.85),
    "code_system_version_validation": (0.15, 0.85),
    "rpms_to_fhir_mapping": (0.10, 0.80),
    "temporal_status_classification": (0.15, 0.85),
    "evidence_sufficiency": (0.10, 0.85),
    "policy_action_selection": (0.10, 0.75),
}

_DISTRACTOR_WEIGHT = 0.05


def normalized_parameter(config: Configuration, name: str) -> float:
    spec = PARAMETERS[name]
    easy = float(spec.easy_end())
    hard = float(spec.hard_end())
    if hard == easy:
        return 0.0
    return (float(config.values[name]) - easy) / (hard - easy)


def declared_family_difficulty(config: Configuration, family: str) -> float:
    """Declared latent difficulty in [0,1] for a family under configuration v."""

    base, slope = _DIFFICULTY_MAP[family]
    primary = normalized_parameter(config, FAMILY_PARAMETER[family])
    distractor = normalized_parameter(config, "distractor_actions")
    value = base + slope * primary + _DISTRACTOR_WEIGHT * distractor
    return min(max(value, 0.0), 1.0)


def declared_difficulty_profile(config: Configuration) -> dict[str, float]:
    return {family: declared_family_difficulty(config, family) for family in TASK_FAMILIES}


def space_manifest() -> dict[str, Any]:
    """Machine-readable description of V, for the run record and the designer prompt."""

    return {
        "schema_version": "boundarybench.betal_parameter_space.v1",
        "space_version": SPACE_VERSION,
        "dimension_count": len(PARAMETER_SPECS),
        "cardinality_note": (
            "Continuous dimensions are snapped to a declared step grid, so V is finite. "
            "The grid, not the interval, is the searched object."
        ),
        "parameters": [
            {
                "name": spec.name,
                "kind": spec.kind,
                "low": spec.low,
                "high": spec.high,
                "step": spec.step,
                "grid_points": int(round((spec.high - spec.low) / spec.step)) + 1,
                "family": spec.family,
                "harder_direction": spec.harder_direction,
                "description": spec.description,
            }
            for spec in PARAMETER_SPECS
        ],
        "declared_difficulty_map": {
            family: {"base": base, "slope": slope} for family, (base, slope) in _DIFFICULTY_MAP.items()
        },
        "declared_difficulty_disclaimer": (
            "The difficulty map is a simulator property used to make difficulty scaling "
            "auditable. It is not a clinical severity model and is not fitted to any "
            "model's observed behavior."
        ),
    }


def grid_cardinality() -> int:
    total = 1
    for spec in PARAMETER_SPECS:
        total *= int(round((spec.high - spec.low) / spec.step)) + 1
    return total
