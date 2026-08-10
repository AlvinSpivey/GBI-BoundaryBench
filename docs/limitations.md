# Limitations

GBI BoundaryBench v0.1 is an engineering research artifact with narrow scope.

## Non-clinical status

The benchmark is not clinically validated. It is not a medical device, clinical decision support tool, certified terminology crosswalk, production integration, or autonomous write-back workflow.

## Synthetic-only data

The data is synthetic and derived from Synthea sample data plus project-authored transformations. Synthetic data can expose boundary-handling failures, but it does not prove performance on real EHR data, real patient populations, or site-specific workflows.

## Small public-dev split

The public-dev split contains one task per v0.1 task family. It is suitable for development, regression testing, and demonstration. It is not sufficient for statistically stable model ranking.

Stage 10 adds a larger empirical package, and Stage 11 freezes one scored held-out run for a single 4B open-weight model family. The package remains synthetic and should not be cited as a general frontier-model result.

## Historical source gap

The exact 310-patient source population for the older sibling RPMS files audited in Stage 0 was not recovered. Those legacy files are not benchmark gold truth.

## Terminology limits

The benchmark checks deterministic code-system/version behavior needed by its tasks. It does not provide or certify a comprehensive ICD, SNOMED, LOINC, or GEM crosswalk.

## Verification limits

The verifier is deterministic and process-isolated through `python -I`. Stage 10 adds a verifier container recipe and read-only trusted-package checks, but exact container runtime and mount behavior must be verified by the operator before external model execution. A hostile local process with workspace write access remains outside the current isolation guarantee.

The sheaf/mapping-cone layer is diagnostic-only and has zero scoring weight unless independently validated in a future release.

## Model-result limits

The frozen v0.1 empirical result covers `Qwen/Qwen3-4B-Instruct-2507` only. It does not establish cross-model generalization, closed-provider performance, real-world EHR performance, or general model incapability. Unsupported cells remain `NOT_RUN`. Offline mocks are adapter-health checks and must not be cited as model performance.

The scored Qwen run had zero coverage and no accepted result records. Therefore selective risk is undefined, and zero false accepts must not be interpreted as evidence of strong safety performance.

Confidence intervals, repeat-run stability, and provider-cost comparisons are `NOT_RUN`.

## Human-review limits

Human-review protocols and synthetic tests exist, but completed real review, adjudication, and agreement-analysis values remain `NOT_RUN`.

## Release-rights limits

This repository records provenance, notices, and license boundaries, but it is not legal advice. Any public redistribution should be reviewed by the repository owner or counsel, especially if future releases add third-party materials, provider traces, manuscript content, or non-public evaluation splits.
