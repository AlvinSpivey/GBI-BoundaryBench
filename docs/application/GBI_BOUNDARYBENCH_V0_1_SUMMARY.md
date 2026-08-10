# GBI BoundaryBench v0.1 application summary

## Problem

Generative models can produce plausible legacy-EHR transformations, but enterprise systems need a separate criterion for whether those proposals are admissible. A patient match, diagnosis mapping, FHIR resource, temporal classification, or policy action may look reasonable in text while still lacking identity support, provenance, terminology/version validity, temporal consistency, evidence sufficiency, or safe dependency handling.

BoundaryBench treats that distinction as the benchmark target. The model proposes; the Programmatic Verification Engine decides whether the proposal can become an admissible action, must be quarantined, requires expert review, should be rejected, or should abstain.

## Approach

GBI BoundaryBench v0.1 is a synthetic, non-clinical benchmark for legacy-EHR boundary validation. It evaluates eight task families:

- patient identity normalization;
- orphan/duplicate detection;
- field anomaly/free-text bleed;
- code-system version validation;
- RPMS-to-FHIR mapping;
- temporal status classification;
- evidence sufficiency;
- policy action selection.

Each task has typed inputs, allowed outputs, deterministic reference behavior, evidence references, failure slices, and explicit action semantics. Candidate outputs are scored by a deterministic verifier that checks parse/schema validity, exact answer/action compatibility, graph and provenance constraints, temporal status, terminology/version behavior, evidence sufficiency, dependency-aware quarantine, and policy.

The allowed policy actions are `ADMIT`, `ADMIT_HISTORICAL_ONLY`, `QUARANTINE_SLICE`, `ABSTAIN`, `EXPERT_REVIEW`, and `REJECT`.

## Engineering rigor

The v0.1 empirical package was designed to separate model execution from trusted scoring:

- held-out model inputs were answer-key-free;
- benchmark inputs and verifier artifacts were cryptographically pinned;
- the execution harness was frozen before held-out execution;
- every model execution recorded explicit provenance;
- raw outputs were frozen before scoring;
- trusted scoring occurred only after the raw freeze;
- invalid outputs were preserved as empirical outcomes rather than repaired or dropped;
- fail-closed behavior converted missing or invalid admissibility into quarantine;
- an interrupted token-top-k attempt was preserved as an audit event instead of hidden or mixed into the canonical result.

The frozen governance chain is:

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

## Empirical result

The frozen v0.1 run evaluated `Qwen/Qwen3-4B-Instruct-2507` at pinned revision `cdbee75f17c01a7cc42f958dc650907174af0554`.

The run covered 256 held-out tasks across three evidence modes:

- `output_only`;
- `token_top_k`;
- `full_category_evidence`.

The frozen scored result is:

| Metric | Value |
|---|---:|
| Canonical executions | 768 |
| Completed executions | 768 |
| Accepted result records | 0 |
| Safe parse rejects | 369 |
| Safe schema rejects | 399 |
| Verified completions | 0 |
| Coverage | 0.0 |
| Invalid-output rate | 1.0 |
| Quarantined executions | 768 |

Per evidence mode, all three runs had 256 tasks, 123 safe parse rejects, 133 safe schema rejects, zero accepted outputs, zero verified completions, zero coverage, invalid-output rate 1.0, and quarantine frequency 1.0.

The key interpretation is narrow: the dominant v0.1 limitation was not whether inference could execute; all 768 executions completed. The limitation was whether generated proposals crossed the structured admissibility boundary. Additional model-side evidence access did not improve verified completion in this run because outputs failed earlier at the parse/schema boundary.

Zero false accepts should not be presented as evidence of strong safety performance. Coverage was zero, so the verifier had no accepted model actions over which selective risk could be estimated.

## Limitations

BoundaryBench v0.1 evaluates one 4B open-weight model family. Cross-model generalization remains future work.

Current limitations include:

- synthetic-only data;
- no clinical validation;
- no certified terminology crosswalk;
- no completed independent human-review statistics;
- no confidence intervals;
- no repeat-run stability analysis;
- no provider-cost comparison;
- zero coverage, which prevents selective-risk estimation;
- no isolation of every possible cause of parse/schema failure in v0.1.

The benchmark result should not be used to claim that all frontier models fail, that all LLMs fail EHR transformation, that Qwen is unsafe, or that evidence modes are generally useless.

## Next work

Immediate next experiments should preserve v0.1 held-out semantics and avoid tuning on held-out answers. Useful next steps are:

- diagnose parse/schema failures on public-development cases;
- evaluate a second open-weight family such as Mistral;
- compare closed-provider output-only behavior such as OpenAI;
- test structured-output and interface constraints;
- add repeat-run stability where meaningful;
- add confidence intervals once there is nonzero accepted coverage;
- expand human review with actual independent reviewer decisions.

The long-term research question is not whether a model can emit plausible healthcare text. It is whether model proposals can be made auditable enough for deterministic enterprise admission, quarantine, review, rejection, or abstention.
