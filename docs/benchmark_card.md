# Benchmark card

## Name

GBI BoundaryBench v0.1 release candidate.


## Public showcase scope

This repository publishes the application-facing documentation, public schemas/interfaces, verifier architecture code, and aggregate scored artifacts. Hidden held-out references, oracle outputs, trusted verifier packages, raw held-out responses, private audit logs, and private Git history are intentionally withheld to preserve blind-evaluation integrity.

## Intended use

GBI BoundaryBench is a non-clinical research benchmark for testing whether model outputs at a legacy-EHR boundary can be made auditable by deterministic verification. It is designed for benchmark engineering, model-adapter testing, abstention behavior, provenance checks, and fail-closed policy evaluation.

The benchmark is not intended for clinical decision support, production EHR integration, certified terminology mapping, patient care, revenue-cycle operations, or autonomous write-back.

## Research hypothesis

Frontier models remain weak at converting messy, partially observed enterprise records into auditable, policy-compliant actions, especially when the correct action is abstention or localized quarantine rather than confident completion.

The benchmark treats model output as evidence, not authority. Scoring is performed by the Programmatic Verification Engine, not by the model under test.

## Data basis

The v0.1 public-dev split is derived from Stage 1 synthetic benchmark records under `data/stage1/official_synthea_sample_310/`. Those artifacts were generated from an official Synthea sample-data alternative documented in `data/external/synthea_sample_data/PROVENANCE.md`, then converted into canonical records, RPMS-shaped views, and deterministic corruption manifests.

The historical sibling RPMS clean/noisy files audited during Stage 0 are not used as gold truth because they were not true paired corruption views and their exact original 310-patient source population was not recovered.

## Task families

The public-dev split contains one deterministic task for each v0.1 family:

- patient identity normalization;
- orphan/duplicate detection;
- field anomaly/free-text bleed;
- code-system version validation;
- RPMS-to-FHIR mapping;
- temporal status classification;
- evidence sufficiency;
- policy action selection.

Each task has typed inputs, allowed outputs, deterministic reference behavior, evidence requirements, failure slices, and explicit abstention/action semantics.

## Scoring

Scoring is deterministic and fail-closed. The verifier checks:

- safe parse and schema validity;
- exact action/answer match against benchmark references;
- graph/resource provenance consistency;
- temporal status;
- code-system version handling;
- evidence sufficiency and evidence-ID validity;
- dependency-aware quarantine closure;
- selective-risk metrics.

Malformed outputs, unknown actions, task-ID mismatches, unsupported evidence, missing required evidence, ambiguous identity, unsupported terminology/version, and invalid dates fail closed.

## Current results

The frozen v0.1 held-out empirical result is tagged as `empirical-scored-v0.1`. It evaluates one open-weight model family, `Qwen/Qwen3-4B-Instruct-2507`, at pinned revision `cdbee75f17c01a7cc42f958dc650907174af0554`.

Across 256 held-out tasks and three evidence modes (`output_only`, `token_top_k`, and `full_category_evidence`), all 768 canonical executions completed. Zero outputs satisfied the benchmark's admissibility contract. The runner provenance records 369 safe parse rejects and 399 safe schema rejects; the verifier retained all 768 executions in the denominator and quarantined all 768.

This result is narrow. It does not show that all frontier models fail, that Qwen is unsafe, or that zero false accepts demonstrate strong safety performance. Coverage was zero, so selective risk is undefined. Additional model-side evidence access did not improve verified completion in this v0.1 run because outputs failed earlier at the parse/schema admissibility boundary.

The current public-dev table also includes deterministic rules runs, offline adapter mocks, and a local surrogate diagnostic. Offline adapter mocks are adapter-health checks and are not model results. Open-weight or closed-provider cells other than the frozen Qwen v0.1 run remain `NOT_RUN` unless exact model identity, terms review, runtime/provenance, raw outputs, cost/latency when returned, and code/data commit are recorded.

Synthetic unit-test reviewer decisions are not human-review results.

## Human review status

Human-review materials exist, including reviewer guide, roles, calibration set, double-review form, adjudication form, disagreement taxonomy, provenance schema, and agreement-analysis script. Completed human-review values remain `NOT_RUN`.

## Stage 10 pre-model empirical package

Stage 10 adds a pre-registered empirical-evaluation package anchored to frozen release-candidate commit `a09066cc35917a3ecfb1ac2bd9dcfbfdc06e1a4a`. It expands deterministic cases from Stage 1 canonical truth and corruption manifests while preserving v0.1 task semantics, grader criteria, reference meanings, and action definitions.

The package separates:

- public development inputs and trusted references;
- held-out answer-key-free model inputs;
- held-out trusted verifier references and task-manifest hashes;
- surrogate-probe calibration interactions that do not overlap held-out patients/source records/seeds;
- frozen reference, grader, task-manifest, policy, and data-manifest hashes.

The held-out model-input package excludes reference action, reference answer, reference rationale, grader oracle, and hidden generation seed. Stage 10 itself did not include scored model results; Stage 11 froze the raw Qwen outputs under `empirical-raw-v0.1` and scored them under `empirical-scored-v0.1`. Unsupported or unavailable model cells remain `NOT_RUN` or `NOT_AVAILABLE`.

## Contamination controls

The public-dev split is intentionally small and public. It is suitable for development and smoke testing, not for sealed leaderboard claims. Future non-public evaluation splits must be generated from immutable source records and corruption manifests, keep answer keys separate from model execution, and record seed/commit provenance.

## Known limitations

See `docs/limitations.md`. Major limitations include synthetic-only data, no clinical validation, no certified terminology crosswalk, no completed real human review, only one frozen open-weight model-family run, no confidence intervals, no repeat-run stability analysis, no provider-cost comparison, and zero coverage preventing selective-risk estimation.

## Release gates

Before any public scored release beyond this release candidate:

- release artifacts must pass `scripts/validate_release.py`;
- checksum/SBOM files must match committed sources;
- unsupported result cells must remain `NOT_RUN`;
- any real model run must include raw outputs and immutable provenance;
- any real human review must include reviewer provenance and agreement analysis;
- hidden evaluation splits must not expose answer keys to model execution;
- containerized scorer isolation should be added or explicitly documented as not yet available.
