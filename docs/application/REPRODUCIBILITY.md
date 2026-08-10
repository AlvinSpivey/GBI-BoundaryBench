# BoundaryBench v0.1 public reproducibility summary

This public repository is an application-facing showcase for GBI BoundaryBench v0.1. It intentionally separates three categories of material:

1. public artifacts released here;
2. immutable identifiers and hashes from the private research record;
3. trusted held-out references, oracles, verifier packages, raw held-out responses, and private audit logs that remain withheld to preserve blind-evaluation integrity.

## Immutable private research chain

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

## Identifiers

| Artifact | Identifier |
|---|---|
| Benchmark contract | `benchmark-contract-v0.1` |
| Benchmark contract commit | `4e66210c1feb3bfff0f3e7e1fe3c4a3f899d77a3` |
| Final execution harness | `empirical-run-plan-v0.1.8` |
| Runner commit | `5b717c9fff00c816946adf095a271cf05cc5b5f1` |
| Raw freeze | `empirical-raw-v0.1` |
| Raw freeze commit | `7ed87ba68b715f60bdf88a8015aa2659313b5876` |
| Scored freeze | `empirical-scored-v0.1` |
| Scored commit | `3bcb9dad9af04c1cfedb5b6f74aa40e36d9a0e13` |
| Frozen benchmark SHA256 | `ae0f875ed40316a99b8fbddd1ee248296ace94431f0b3f1f05437ea906967c78` |
| Raw archive SHA256 | `155c28cb104bc0c0923c16e3f2098a59707aadebc31596304afe073b1250eaf0` |
| Scored artifact checksum-manifest SHA256 | `4b04383b9874410ce7353623f697a10c7b46fbdcecfa7271f2b849c78720182b` |

The same identifiers are available as machine-readable public provenance in [`../../artifacts/public_results/v0_1/PROVENANCE.json`](../../artifacts/public_results/v0_1/PROVENANCE.json).

## What is public here

This showcase includes:

- polished project documentation and application figures;
- benchmark cards and design documentation;
- safe task/result/provenance schema descriptions;
- source code sufficient to inspect the task contracts, provider-neutral adapter boundary, and deterministic verification architecture;
- public aggregate scored artifacts under [`../../artifacts/public_results/v0_1/`](../../artifacts/public_results/v0_1/);
- a public-only checksum manifest for the published result files.

## What is intentionally withheld

The public repository does not include:

- held-out trusted references or answer keys;
- oracle outputs or hidden labels;
- trusted verifier packages containing benchmark references;
- raw held-out model responses;
- private audit/run logs;
- private Git history or private governance tags.

The reason is evaluation integrity, not secrecy about the method. Publishing hidden references would contaminate future blind held-out model evaluation.

## Execution and scoring governance

The held-out model execution host received answer-key-free model inputs. It did not receive reference actions, reference answers, reference rationales, oracle results, hidden generation seeds, or the trusted verifier package.

Raw outputs were frozen under `empirical-raw-v0.1` before trusted scoring began. Scoring occurred only after that raw freeze and used the deterministic Programmatic Verification Engine. No model execution occurred during scoring.

All 768 canonical executions remained in the evaluation denominator. The interrupted `heldout_token_top_k_run_001` attempt was preserved as audit-only metadata in the private record and was not mixed into scoring; the canonical retry was `heldout_token_top_k_run_002`.

No benchmark data, prompts, task semantics, verifier rules, scoring rules, or result schemas were changed in response to held-out model behavior.

## Public scored result summary

The frozen scored package records:

- 768 canonical held-out executions;
- 256 tasks per evidence mode;
- zero accepted result records;
- 369 safe parse rejects;
- 399 safe schema rejects;
- zero verified completions;
- coverage 0.0;
- invalid-output rate 1.0;
- quarantine frequency 1.0;
- selective risk `null` because coverage was zero.

These claims can be checked against the public aggregate files in [`../../artifacts/public_results/v0_1/`](../../artifacts/public_results/v0_1/).
