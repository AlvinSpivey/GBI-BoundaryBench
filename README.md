# GBI BoundaryBench v0.1

## Programmatic Verification of Legacy-EHR Transformations

GBI BoundaryBench is a research benchmark for testing the boundary between a plausible model proposal and an enterprise-admissible action. The core design principle is simple: a model output is evidence, not authority.

```text
MODEL PROPOSAL
      ↓
PROGRAMMATIC VERIFICATION
      ↓
ADMISSIBLE ACTION / QUARANTINE / REVIEW / REJECTION
```

The benchmark uses synthetic legacy-EHR-style records and deterministic verifier rules to evaluate whether proposed mappings, repairs, classifications, traces, and abstentions satisfy explicit identity, provenance, terminology/version, temporal-validity, evidence, dependency, and policy constraints.

This repository is an application-facing public showcase. It is not a clinical system, a medical device, a certified terminology crosswalk, or an autonomous EHR write-back service. Expected answers in the private research record are benchmark references derived from synthetic generator truth and explicit corruption manifests, not clinical truth.

## Headline empirical result

Across 768 frozen held-out executions of `Qwen/Qwen3-4B-Instruct-2507` spanning three evidence modes, all model executions completed, but zero outputs satisfied the benchmark's admissibility contract: 369 were rejected during safe parsing and 399 during schema validation. All 768 were deterministically quarantined.

This v0.1 result evaluates one 4B open-weight model and is not a general claim about LLM capability in EHR transformation. It also should not be read as evidence that Qwen is unsafe or that zero false accepts demonstrate strong safety performance. Coverage was zero, so selective risk is undefined.

| Metric | Frozen value |
|---|---:|
| Held-out tasks | 256 |
| Evidence modes | 3 |
| Canonical executions | 768 |
| Completed executions | 768 |
| Accepted `boundarybench.result.v1` records | 0 |
| Safe parse rejects | 369 |
| Safe schema rejects | 399 |
| Coverage | 0.0 |
| Invalid-output rate | 1.0 |
| Quarantined executions | 768 |
| Selective risk | undefined at zero coverage |

Start with:

- Architecture figure: [`docs/application/figures/boundarybench_architecture.svg`](docs/application/figures/boundarybench_architecture.svg)
- Empirical failure-flow figure: [`docs/application/figures/qwen_v0_1_failure_flow.svg`](docs/application/figures/qwen_v0_1_failure_flow.svg)
- Application summary: [`docs/application/GBI_BOUNDARYBENCH_V0_1_SUMMARY.md`](docs/application/GBI_BOUNDARYBENCH_V0_1_SUMMARY.md)
- Enterprise portability: [`docs/application/ENTERPRISE_PORTABILITY.md`](docs/application/ENTERPRISE_PORTABILITY.md)
- Reproducibility summary: [`docs/application/REPRODUCIBILITY.md`](docs/application/REPRODUCIBILITY.md)
- Benchmark card: [`docs/benchmark_card.md`](docs/benchmark_card.md)
- Public aggregate results: [`artifacts/public_results/v0_1/`](artifacts/public_results/v0_1/)
- Submitted research manuscript: [`paper/GBI_DCSE_manuscript.pdf`](paper/GBI_DCSE_manuscript.pdf)

### Research manuscript

**Logit-Boundary Geometric Belief Interfaces and Sparse Sheaf-Enclave Protocols** — Alvin Spivey & Yu Huang

Companion research manuscript underlying the GBI/DCSE verification architecture and BoundaryBench evaluation framework.

**Status: submitted to arXiv: [processing / identifier](https://arxiv.org/abs/2608.10300).**

[Read the submitted manuscript](paper/GBI_DCSE_manuscript.pdf)

The manuscript covers:

- typed model-to-system evidence boundaries;
- the versioned runtime admissibility policy `P`;
- healthcare / financial / government domain portability;
- pre-commit surgical quarantine and liveness;
- deterministic human-review surfaces;
- GBI BoundaryBench v0.1 empirical evaluation.

## Why this benchmark exists

Legacy EHR transformation is not just a text-generation problem. A system may need to decide whether a proposed patient match, diagnosis mapping, FHIR resource, temporal classification, or policy action is admissible under operational constraints. BoundaryBench makes that boundary explicit:

- models propose structured outputs;
- the verifier controls admissibility;
- malformed or unsupported outputs fail closed;
- correct abstention and localized quarantine are first-class outcomes;
- every scored result is tied to immutable task, model, raw-output, and verifier provenance.

## From healthcare benchmark to enterprise diagnostic evaluation

BoundaryBench v0.1 is instantiated in legacy-EHR transformation, but the verification interface is intended to be domain-portable:

```text
MODEL / AGENT PROPOSAL
      ↓
TYPED EVIDENCE RECEIPT
      ↓
PROGRAMMATIC VERIFICATION
      ↓
VERSIONED ENTERPRISE POLICY
      ↓
ADMIT / QUARANTINE / REVIEW / REJECT
```

The verification architecture is portable; the task semantics, authoritative evidence, dependencies, and policy contract are domain-specific. An enterprise version of this pattern would run a versioned evaluation package locally against the customer’s actual model, agent, retrieval, data-interface, and policy stack. The point is customer-specific, in-situ empirical evaluation rather than relying only on generic leaderboard performance or proxy estimates.

Operationally, the loop is:

```text
customer stack
      ↓
local diagnostic evaluation
      ↓
empirical failure surface
      ↓
failure slices
      ↓
expert data / graders / synthetic examples / retrieval changes /
post-training environments
      ↓
re-evaluation
```

This can turn observed failures into a data-development roadmap without predetermining that any specific vendor, product, or training approach is the answer. Enterprise portability details are in [`docs/application/ENTERPRISE_PORTABILITY.md`](docs/application/ENTERPRISE_PORTABILITY.md).

## What BoundaryBench evaluates

The v0.1 task suite covers eight task families:

| Family | Required behavior |
|---|---|
| `patient_identity_normalization` | Link noisy patient identity evidence only when DEM evidence supports it. |
| `orphan_duplicate_detection` | Detect orphan or duplicate patient references and route uncertainty to quarantine/review. |
| `field_anomaly_bleed` | Detect free-text bleed or structured-field contamination. |
| `code_system_version_validation` | Distinguish supported and legacy terminology/version evidence. |
| `rpms_to_fhir_mapping` | Map RPMS-shaped rows to expected FHIR resource types with provenance. |
| `temporal_status_classification` | Separate active evidence from historical-only evidence. |
| `evidence_sufficiency` | Abstain when required evidence for an asserted answer is absent. |
| `policy_action_selection` | Apply fail-closed policy actions for unsafe or incomplete inputs. |

Allowed policy actions are `ADMIT`, `ADMIT_HISTORICAL_ONLY`, `QUARANTINE_SLICE`, `ABSTAIN`, `EXPERT_REVIEW`, and `REJECT`.

## Verification architecture

The Programmatic Verification Engine is deterministic and separate from model execution. It checks safe parsing, schema validity, exact action/answer compatibility with benchmark references, identity and source-record consistency, provenance and evidence references, terminology/version constraints, temporal validity, dependency-aware quarantine closure, and policy-action semantics.

Malformed JSON, schema-invalid outputs, task-ID mismatches, unknown actions, unsupported evidence, ambiguous identity, unsupported terminology/version, invalid dates, and missing required evidence fail closed.

## Public results included here

This repository includes compact aggregate scored artifacts only:

```text
artifacts/public_results/v0_1/
```

The public result files contain aggregate and slice metrics, status distributions, and provenance identifiers. They intentionally do not contain trusted held-out answer content or raw held-out model responses.

## Why the full held-out benchmark is not public

The full private research repository contains hidden held-out references, oracle outputs, and trusted verifier packages. Those materials are withheld to preserve evaluation integrity for future blind model runs. Publishing the hidden references would make later held-out evaluations contaminated by construction.

The public showcase therefore releases the architecture, documentation, safe schemas/interfaces, source code needed to understand the verifier boundary, aggregate scored results, figures, and immutable governance identifiers. It excludes hidden answers, held-out trusted references, oracle files, raw held-out responses, private audit logs, and private Git history.

## Frozen evaluation protocol

The v0.1 empirical chain in the private research record is immutable:

```text
benchmark-contract-v0.1
        ↓
empirical-run-plan-v0.1.8
        ↓
blind held-out execution
        ↓
empirical-raw-v0.1
        ↓
trusted scoring
        ↓
empirical-scored-v0.1
```

Important identifiers are recorded in [`artifacts/public_results/v0_1/PROVENANCE.json`](artifacts/public_results/v0_1/PROVENANCE.json), including the benchmark contract commit, runner commit, raw-freeze commit, scored-freeze commit, frozen benchmark SHA256, raw archive SHA256, and scored checksum-manifest SHA256.

## Repository navigation

```text
docs/application/               application-facing summary, figures, blurbs, governance notes
docs/                           benchmark card, data card, verifier design, threat model, limitations
schemas/                        machine-readable public task/result/provenance interfaces
src/boundarybench/tasks/         typed task/result contracts and task-family logic
src/boundarybench/verification/  deterministic verification engine and fail-closed checks
src/boundarybench/adapters/      provider-neutral adapter interfaces and offline adapter scaffolding
src/boundarybench/empirical/     execution/reporting interfaces included where public-safe
artifacts/public_results/v0_1/   public-safe aggregate scored metrics and provenance
```

## Limitations and next experiments

BoundaryBench v0.1 is synthetic-only and non-clinical. The frozen empirical result evaluates one 4B open-weight model family, not the frontier-model ecosystem. There are no confidence intervals, repeat-run stability estimates, provider-cost comparisons, or completed human-review statistics for this run. Zero coverage prevents selective-risk estimation, and v0.1 does not isolate every possible cause of parse/schema failure.

Next work should diagnose parse/schema failures on public-development cases without modifying v0.1 held-out semantics, add a second open-weight family such as Mistral, compare closed providers such as OpenAI under output-only constraints, test structured-output interfaces, and add confidence intervals and repeat-run stability when meaningful.

## Licensing boundary

Original software in this repository is offered under Apache-2.0 as stated in `LICENSE`. Synthetic benchmark data, documentation, notices, and third-party material have separate boundaries in `DATA_LICENSE.md`, `DOCUMENTATION_LICENSE.md`, `NOTICE`, and `THIRD_PARTY_NOTICES.md`.

No license is granted for private credentials, confidential business materials, private endpoints, real PHI/PII, hidden held-out answer content, trusted verifier packages, raw held-out responses, or third-party source material not expressly cleared for redistribution.
