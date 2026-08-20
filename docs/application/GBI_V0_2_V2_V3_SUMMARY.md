# BoundaryBench v0.2, GBI v2, and GBI-DCSE v3 summary

This document summarizes the public-safe deterministic verification artifacts added after the frozen BoundaryBench v0.1 release. These stages do not rewrite the historical v0.1 experiment.

## BoundaryBench v0.2 / BeTaL-inspired benchmark tuning

The v0.2 work asks whether benchmark difficulty can be tuned without confusing interface-admission failure with conditional task competence.

Source artifacts:

- [`../../artifacts/public_results/v0_2/`](../../artifacts/public_results/v0_2/)
- [`../betal/BETAL_V0_2_SEARCH_REPORT.md`](../betal/BETAL_V0_2_SEARCH_REPORT.md)
- [`../betal/BETAL_GBI_DESIGN_SPEC.md`](../betal/BETAL_GBI_DESIGN_SPEC.md)

Verified headline values from the public artifacts:

- parameter dimensions: `9`;
- finite grid configurations: `2,218,750,380`;
- feedback-coordinate search: mean search gap `5.23%`, mean held-out gap `2.87%`, mean best gap `1.23%`;
- random/PPR baseline: mean search gap `20.90%`, mean held-out gap `13.61%`, mean best gap `11.37%`;
- Best-of-N baseline: mean search gap `23.72%`, mean held-out gap `11.46%`, mean best gap `10.59%`;
- feedback held-out target results:
  - hard target `0.25` -> `0.2578125`;
  - medium target `0.50` -> `0.51171875`;
  - easy target `0.75` -> `0.7890625`;
  - trivial target `0.90` -> `0.84375`.

The core methodological change is to treat admission and conditional task performance as distinct quantities. Task difficulty is undefined below the declared admission floor. A degenerate or unreachable admission state should be reported as such, not treated as zero task competence.

No new language model designer or model execution was used in the v0.2 benchmark-design experiments.

## GBI v2 runtime admissibility

GBI v2 asks whether a runtime gate can use authoritative witness state and policy rather than benchmark reference answers.

Source artifacts:

- [`../../artifacts/public_results/gbi_v2/`](../../artifacts/public_results/gbi_v2/)
- [`../betal/GBI_DCSE_V2_SCORECARD.md`](../betal/GBI_DCSE_V2_SCORECARD.md)

Verified headline values:

- synthetic tasks: `512`;
- selected strictness: `0.6`;
- runtime admissibility based on authoritative state and policy, not benchmark reference answers;
- shuffled-reference test leaves runtime verdicts unchanged;
- deterministic format repair:
  - admission `0.46484375`;
  - coverage `0.447265625`;
  - verified completion remains `0`;
- injected severe contradictions: `116`;
- detected at selected strictness: `116 / 116`;
- narrow preregistered clean-admissible false-conflict result: `0 / 99`;
- broader reasonable denominator: `5 / 117 = 4.2735%`;
- confident-hallucinator synthetic adversary: zero silent promotions under the evaluated policy;
- evidence-forger synthetic adversary: zero admitted and zero silent promotions.

Both false-conflict denominators are retained. The broader `5 / 117` result is not hidden.

These are deterministic synthetic adversaries, not frontier-model executions.

## GBI-DCSE v3 claim-level systems verification

GBI-DCSE v3 asks whether the broader systems manuscript can be converted into explicit claim-to-evidence checks.

Source artifacts:

- [`../../artifacts/public_results/gbi_dcse_v3/`](../../artifacts/public_results/gbi_dcse_v3/)
- [`../betal/GBI_DCSE_V3_FULL_EVALUATION.md`](../betal/GBI_DCSE_V3_FULL_EVALUATION.md)

Verified headline values:

- registered manuscript claims: `99`;
- testable in this environment: `96`;
- supported/met by supplied evidence: `95`;
- evidence classes:
  - `16` reproduced;
  - `51` measured;
  - `5` measured synthetic;
  - `22` structural;
  - `1` partial proxy;
  - `3` out of scope;
  - `1` erratum;
- standalone scorecard verifier: `148` checks, `0` failures;
- corrected Dirichlet-Fisher full-box epsilon: approximately `0.326472` for `A=20` and the declared condition-number budget;
- the earlier `~0.066` value applies only to a restricted slice, not the full declared box;
- sparse certificate workload: approximately `14,741x` fewer arithmetic operations and `68.6x` smaller heap proxy under the paper’s accounting;
- residual-only kernel verification is insufficient against the constructed underclaimed-kernel attack;
- spectral-moment checks detect that case.

Second synthetic domain evidence:

- `8` domain-neutral systems modules reused unchanged;
- `4` domain-specific policy/witness objects;
- `265 / 265` injected severe cases caught;
- `0 / 175` false conflicts on the declared clean synthetic population;
- `0` architecture changes.

Out-of-scope items are preserved as out of scope:

- real zero-knowledge proof implementation;
- real retrospective clinical validation;
- real TEE/IAS attestation bootstrapping.

Proxy and synthetic measurements are not production claims.

## Interpretation

The newer work shows how a benchmark/evaluation pipeline can separate:

- format admission from conditional task performance;
- benchmark answer-key agreement from runtime admissibility;
- deterministic format repair from substantive answer repair;
- synthetic adversary containment from frontier-model safety claims;
- research-prose claims from executable evidence checks.

The repository remains a synthetic, non-clinical research artifact.
