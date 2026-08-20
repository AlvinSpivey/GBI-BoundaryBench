"""Designers for the BeTaL-GBI parameter search.

BeTaL's step 1 and 2 are a *model call*: the designer LLM reads the environment
description, the parameter set, the target performance level, and a natural
language summary of previous iterations, and returns a new configuration.

This module provides that interface (``render_designer_prompt``,
``LLMDesigner``, ``TranscriptDesigner``) together with three model-free
designers that can be executed offline and reproducibly:

``FeedbackCoordinateDesigner``
    The reference feedback designer. Phase one brackets the declared monotone
    dial through V; phase two refines individual coordinates using per-family
    observed rates. Plays the role BeTaL assigns to the designer LLM and is the
    strategy the headline results use.

``RandomSamplingPPRDesigner``
    BeTaL's RS+PPR baseline: uniform sampling on the declared grid with
    prioritized replay around the best configuration found so far.

``BestOfNDesigner``
    BeTaL's BoN baseline: N independent samples with no feedback between them.

The model-free designers exist so the harness has a reproducible, auditable
control. They are *not* stand-ins for a frontier designer's reasoning, and no
result obtained from them should be reported as an LLM designer result.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import random
from typing import Any, Protocol, Sequence

from boundarybench.betal.space import (
    Configuration,
    FAMILY_PARAMETER,
    PARAMETERS,
    PARAMETER_SPECS,
    configuration_from_dial,
    dial_of_configuration,
    project_to_domain,
    space_manifest,
)

DESIGNER_VERSION = "betal-gbi-designer-v0.2"


@dataclass(frozen=True)
class Observation:
    """One completed iteration, as the designer sees it."""

    index: int
    config: Configuration
    rho_hat_adm: float
    rho_hat_task: float | None
    gap: float | None
    per_family_rho_task: dict[str, float | None]

    @property
    def dial(self) -> float:
        return dial_of_configuration(self.config)


class Designer(Protocol):
    name: str
    kind: str

    def propose(self, *, rho: float, history: Sequence[Observation], iteration: int) -> Configuration:
        ...


# --- Prompt contract for a real designer LLM --------------------------------

DESIGNER_SYSTEM_PROMPT = """\
ROLE

You are the Benchmark Tuner for GBI BoundaryBench. You parameterize synthetic
legacy-EHR transformation tasks so that a named target model reaches a specified
verified-completion rate. You are designing an evaluation environment, not
solving its tasks and not making clinical judgments. All records are synthetic
and non-clinical.

WHAT YOU CONTROL

You control exactly the parameters listed in PARAMETER_SPACE. Nothing else. You
may not change the boundary algebra, the action set, the reference rules, the
verifier, or the admissibility policy. Those are frozen by contract; a benchmark
whose verifier moves between iterations measures nothing.

THE QUANTITY YOU ARE TUNING

Observed performance is reported to you as two separate rates.

  rho_hat_adm  = admitted / task_count
                 the fraction of target emissions that cleared safe parsing and
                 schema validation and therefore entered the judgment substrate.

  rho_hat_task = verified_completion / admitted
                 the fraction of ADMITTED emissions that satisfied every
                 deterministic criterion.

You are tuning rho_hat_task toward the target rate rho. rho is a target
PERFORMANCE rate, so a LOWER rho means a HARDER benchmark.

You are NOT tuning rho_hat_adm. If rho_hat_adm is at or near zero, the target is
failing at the output-format boundary, upstream of anything your parameters
control. Do not attempt to compensate by changing difficulty; report that the
admissibility floor must be repaired first and stop. Difficulty parameters
cannot move a rate that is pinned by malformed output.

DECLARED MONOTONICITY

Every parameter has a declared harder_direction. Moving a parameter in that
direction is intended to lower rho_hat_task and never to raise it. If an
observation contradicts this, say so explicitly in your rationale rather than
silently working around it: a broken monotonicity claim is a finding about the
parameter space, not noise to be smoothed over.

HOW TO USE THE HISTORY

ITERATION_HISTORY gives you, for each previous iteration, the configuration, the
two observed rates, the resulting gap |rho_hat_task - rho|, and per-family
rates. Use it to bracket. Once you have one configuration above rho and one
below it, interpolate between them rather than restarting your search. Use the
per-family rates to find which single parameter is carrying the deviation
instead of moving everything at once.

OUTPUT FORMAT

Return exactly one JSON object and no other text:

{
  "parameters": { "<parameter_name>": <number>, ... },
  "rationale": "<two or three sentences: what you changed, and what you expect>",
  "expected_rho_hat_task": <number between 0 and 1>,
  "admissibility_blocked": <true or false>
}

Include every parameter name from PARAMETER_SPACE. Values outside a declared
domain are projected onto it and the projection is recorded against you, so
propose in-domain values. Set "admissibility_blocked" to true if and only if you
are stopping because rho_hat_adm is pinned near zero.
"""


def render_history_summary(history: Sequence[Observation]) -> str:
    """Natural-language iteration summary, BeTaL Algorithm 1 step 7."""

    if not history:
        return "ITERATION_HISTORY: none. This is the first iteration."
    lines = ["ITERATION_HISTORY:"]
    for observation in history:
        rho_task = (
            "undefined (no admitted emissions)"
            if observation.rho_hat_task is None
            else f"{observation.rho_hat_task:.4f}"
        )
        gap = "undefined" if observation.gap is None else f"{observation.gap:.4f}"
        family_bits = ", ".join(
            f"{family}={'n/a' if value is None else f'{value:.2f}'}"
            for family, value in sorted(observation.per_family_rho_task.items())
        )
        lines.append(
            f"  iteration {observation.index}: "
            f"parameters={json.dumps(observation.config.values, sort_keys=True)} "
            f"rho_hat_adm={observation.rho_hat_adm:.4f} "
            f"rho_hat_task={rho_task} gap={gap}"
        )
        lines.append(f"    per-family rho_hat_task: {family_bits}")
    return "\n".join(lines)


def render_designer_prompt(
    *, rho: float, level_name: str, history: Sequence[Observation], task_count: int
) -> str:
    """Assemble the full user-turn prompt for a designer LLM."""

    manifest = space_manifest()
    parameter_lines = [
        f"  - {entry['name']}: {entry['kind']} in [{entry['low']}, {entry['high']}] "
        f"step {entry['step']} ({entry['grid_points']} grid points), "
        f"family={entry['family']}, harder_direction={entry['harder_direction']}\n"
        f"      {entry['description']}"
        for entry in manifest["parameters"]
    ]
    return "\n".join(
        [
            "ENVIRONMENT",
            "  GBI BoundaryBench synthetic legacy-EHR transformation tasks across eight",
            "  families. Each task presents synthetic RPMS-shaped records and requires the",
            "  target to select exactly one action from a typed action set and to cite the",
            "  evidence supporting it. A deterministic verifier decides admissibility.",
            "",
            f"  Tasks per instantiation: {task_count}",
            "  Difficulty level name: " + level_name,
            f"  Target performance rate rho (verified completion given admission): {rho}",
            "",
            "PARAMETER_SPACE",
            *parameter_lines,
            "",
            render_history_summary(history),
            "",
            "Propose the next configuration now.",
        ]
    )


class LLMDesigner:
    """Adapter seam for a real designer LLM.

    The BeTaL paper uses GPT-5, Claude Opus 4.1, and Grok 4 as designers with
    temperature 0.5 and a 4096-token reasoning budget. Supplying such a designer
    to this harness requires only a callable that maps a prompt string to a
    response string; the parsing, projection, and recording are handled here.

    This class is intentionally unbound. No designer LLM was executed for the
    v0.2 search results in this repository, and the reported numbers must not be
    read as a designer-LLM result.
    """

    kind = "llm_designer"

    def __init__(
        self,
        *,
        completion_fn,
        model_id: str,
        temperature: float = 0.5,
        reasoning_budget_tokens: int = 4096,
        task_count: int = 256,
        level_name: str = "unspecified",
    ) -> None:
        self.completion_fn = completion_fn
        self.model_id = model_id
        self.temperature = temperature
        self.reasoning_budget_tokens = reasoning_budget_tokens
        self.task_count = task_count
        self.level_name = level_name
        self.name = f"llm_designer:{model_id}"
        self.transcript: list[dict[str, Any]] = []

    def propose(self, *, rho: float, history: Sequence[Observation], iteration: int) -> Configuration:
        prompt = render_designer_prompt(
            rho=rho, level_name=self.level_name, history=history, task_count=self.task_count
        )
        raw = self.completion_fn(
            system=DESIGNER_SYSTEM_PROMPT,
            user=prompt,
            temperature=self.temperature,
            reasoning_budget_tokens=self.reasoning_budget_tokens,
        )
        payload = _extract_json_object(raw)
        parameters = payload.get("parameters", {}) if isinstance(payload, dict) else {}
        self.transcript.append(
            {
                "iteration": iteration,
                "model_id": self.model_id,
                "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
                "raw_response": raw,
                "parsed_parameters": parameters,
                "rationale": payload.get("rationale") if isinstance(payload, dict) else None,
                "admissibility_blocked": (
                    payload.get("admissibility_blocked") if isinstance(payload, dict) else None
                ),
            }
        )
        return project_to_domain(parameters, origin=self.name)


def _extract_json_object(raw: str) -> dict[str, Any]:
    """Best-effort extraction of the first JSON object in a designer response."""

    text = raw.strip()
    if text.startswith("```"):
        lines = [line for line in text.splitlines() if not line.strip().startswith("```")]
        text = "\n".join(lines)
    start = text.find("{")
    if start < 0:
        return {}
    depth = 0
    for position in range(start, len(text)):
        if text[position] == "{":
            depth += 1
        elif text[position] == "}":
            depth -= 1
            if depth == 0:
                try:
                    decoded = json.loads(text[start : position + 1])
                except json.JSONDecodeError:
                    return {}
                return decoded if isinstance(decoded, dict) else {}
    return {}


class TranscriptDesigner:
    """Replay a recorded designer transcript so an LLM run becomes reproducible."""

    kind = "transcript_replay"

    def __init__(self, *, transcript: list[dict[str, Any]], name: str = "transcript_designer") -> None:
        self.transcript = transcript
        self.name = name

    def propose(self, *, rho: float, history: Sequence[Observation], iteration: int) -> Configuration:
        for entry in self.transcript:
            if int(entry.get("iteration", -1)) == iteration:
                return project_to_domain(entry.get("parsed_parameters", {}), origin=self.name)
        raise KeyError(f"transcript has no entry for iteration {iteration}")


# --- Model-free reference designers -----------------------------------------


class FeedbackCoordinateDesigner:
    """Reference feedback designer: dial bracketing, then coordinate refinement.

    Phase 1 (iterations 1..ceil(I/2)) searches the declared monotone dial. Once a
    configuration above rho and one below it exist, subsequent proposals
    interpolate by secant; before that, they extrapolate outward.

    Phase 2 (remaining iterations) holds the best dial and nudges the single
    coordinate whose family rate deviates most from rho, one declared grid step
    at a time. This is what makes the search multi-dimensional rather than a
    one-parameter sweep.
    """

    kind = "feedback_coordinate"
    name = "feedback_coordinate_designer"

    def __init__(self, *, iterations: int = 10, seed: str = "betal") -> None:
        self.iterations = iterations
        self.phase_one_end = max(2, (iterations + 1) // 2)
        self.seed = seed
        self.notes: list[str] = []

    def _rng(self, iteration: int) -> random.Random:
        digest = hashlib.sha256(f"{self.seed}|{self.name}|{iteration}".encode("utf-8")).digest()
        return random.Random(int.from_bytes(digest[:8], "big"))

    def propose(self, *, rho: float, history: Sequence[Observation], iteration: int) -> Configuration:
        usable = [obs for obs in history if obs.rho_hat_task is not None]
        if iteration <= self.phase_one_end or not usable:
            return self._phase_one(rho=rho, usable=usable, iteration=iteration)
        return self._phase_two(rho=rho, usable=usable, iteration=iteration)

    def _phase_one(
        self, *, rho: float, usable: Sequence[Observation], iteration: int
    ) -> Configuration:
        if not usable:
            # Declared monotonicity: higher dial lowers the rate, so open at 1 - rho.
            dial = 1.0 - rho
            self.notes.append(f"iter{iteration}: phase1 open at dial={dial:.3f} from 1-rho prior")
            return configuration_from_dial(dial, origin=self.name)

        points = sorted((obs.dial, float(obs.rho_hat_task)) for obs in usable)  # type: ignore[arg-type]
        above = [(t, r) for t, r in points if r > rho]
        below = [(t, r) for t, r in points if r <= rho]
        if above and below:
            t_lo, r_lo = max(above, key=lambda pair: pair[0])
            t_hi, r_hi = min(below, key=lambda pair: pair[0])
            if abs(r_hi - r_lo) < 1e-9:
                dial = 0.5 * (t_lo + t_hi)
                self.notes.append(f"iter{iteration}: phase1 bisect flat bracket -> {dial:.3f}")
            else:
                dial = t_lo + (r_lo - rho) * (t_hi - t_lo) / (r_lo - r_hi)
                self.notes.append(
                    f"iter{iteration}: phase1 secant in bracket "
                    f"[{t_lo:.3f},{t_hi:.3f}] -> {dial:.3f}"
                )
        elif above:
            # Every observation is still too easy; push harder.
            t_max = max(t for t, _ in points)
            dial = min(1.0, t_max + max(0.1, 0.5 * (1.0 - t_max)))
            self.notes.append(f"iter{iteration}: phase1 extrapolate harder -> {dial:.3f}")
        else:
            t_min = min(t for t, _ in points)
            dial = max(0.0, t_min - max(0.1, 0.5 * t_min))
            self.notes.append(f"iter{iteration}: phase1 extrapolate easier -> {dial:.3f}")

        tried = {round(obs.dial, 4) for obs in usable}
        attempt = 0
        while round(dial, 4) in tried and attempt < 6:
            nudge = (0.03 / (attempt + 1)) * (1 if self._rng(iteration).random() < 0.5 else -1)
            dial = min(max(dial + nudge, 0.0), 1.0)
            attempt += 1
        if attempt:
            self.notes.append(f"iter{iteration}: phase1 diversified off repeat -> {dial:.3f}")
        return configuration_from_dial(dial, origin=self.name)

    def _phase_two(
        self, *, rho: float, usable: Sequence[Observation], iteration: int
    ) -> Configuration:
        best = min(usable, key=lambda obs: abs(float(obs.rho_hat_task) - rho))  # type: ignore[arg-type]
        values = dict(best.config.values)
        deviations: list[tuple[float, str]] = []
        for family, parameter in FAMILY_PARAMETER.items():
            observed = best.per_family_rho_task.get(family)
            if observed is None:
                continue
            deviations.append((observed - rho, parameter))
        if not deviations:
            self.notes.append(f"iter{iteration}: phase2 no per-family signal; reusing best")
            return Configuration(values=values, origin=self.name)
        deviations.sort(key=lambda pair: abs(pair[0]), reverse=True)
        # Move the two most deviant coordinates one declared grid step each.
        moved: list[str] = []
        for deviation, parameter in deviations[:2]:
            spec = PARAMETERS[parameter]
            direction = 1.0 if spec.harder_direction == "up" else -1.0
            # Positive deviation means the family is too easy, so move harder.
            sign = direction if deviation > 0 else -direction
            step = spec.step * (1 if abs(deviation) < 0.20 else 2)
            values[parameter] = float(values[parameter]) + sign * step
            moved.append(f"{parameter}{'+' if sign > 0 else '-'}{step:g}")
        self.notes.append(
            f"iter{iteration}: phase2 refine from iter{best.index} "
            f"(gap={abs(float(best.rho_hat_task) - rho):.4f}) moving {', '.join(moved)}"
        )
        return project_to_domain(values, origin=self.name)


class RandomSamplingPPRDesigner:
    """RS+PPR baseline: uniform grid sampling with prioritized replay."""

    kind = "random_sampling_ppr"
    name = "random_sampling_ppr_designer"

    def __init__(self, *, seed: str = "betal", replay_probability: float = 0.5) -> None:
        self.seed = seed
        self.replay_probability = replay_probability
        self.notes: list[str] = []

    def _rng(self, iteration: int) -> random.Random:
        digest = hashlib.sha256(f"{self.seed}|{self.name}|{iteration}".encode("utf-8")).digest()
        return random.Random(int.from_bytes(digest[:8], "big"))

    def propose(self, *, rho: float, history: Sequence[Observation], iteration: int) -> Configuration:
        rng = self._rng(iteration)
        usable = [obs for obs in history if obs.rho_hat_task is not None]
        if usable and rng.random() < self.replay_probability:
            best = min(usable, key=lambda obs: abs(float(obs.rho_hat_task) - rho))  # type: ignore[arg-type]
            values = dict(best.config.values)
            for spec in rng.sample(list(PARAMETER_SPECS), k=3):
                values[spec.name] = float(values[spec.name]) + rng.choice((-1, 1)) * spec.step
            self.notes.append(f"iter{iteration}: replay around iter{best.index}")
            return project_to_domain(values, origin=self.name)
        values = {
            spec.name: spec.low
            + rng.randint(0, int(round((spec.high - spec.low) / spec.step))) * spec.step
            for spec in PARAMETER_SPECS
        }
        self.notes.append(f"iter{iteration}: uniform grid sample")
        return project_to_domain(values, origin=self.name)


class BestOfNDesigner:
    """BoN baseline: independent samples, no feedback between iterations."""

    kind = "best_of_n"
    name = "best_of_n_designer"

    def __init__(self, *, seed: str = "betal") -> None:
        self.seed = seed
        self.notes: list[str] = []

    def propose(self, *, rho: float, history: Sequence[Observation], iteration: int) -> Configuration:
        digest = hashlib.sha256(f"{self.seed}|{self.name}|{iteration}".encode("utf-8")).digest()
        rng = random.Random(int.from_bytes(digest[:8], "big"))
        values = {
            spec.name: spec.low
            + rng.randint(0, int(round((spec.high - spec.low) / spec.step))) * spec.step
            for spec in PARAMETER_SPECS
        }
        self.notes.append(f"iter{iteration}: independent sample, history ignored")
        return project_to_domain(values, origin=self.name)


DESIGNER_REGISTRY = {
    "feedback_coordinate": FeedbackCoordinateDesigner,
    "random_sampling_ppr": RandomSamplingPPRDesigner,
    "best_of_n": BestOfNDesigner,
}
