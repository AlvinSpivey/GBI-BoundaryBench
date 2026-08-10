# BoundaryBench v0.1 application blurbs

## ~50-word resume/project blurb

Built GBI BoundaryBench v0.1, a synthetic legacy-EHR benchmark that separates model proposals from admissible enterprise actions using deterministic programmatic verification. Froze answer-key-free held-out execution, raw outputs, and trusted scoring for Qwen3-4B; 768 completed executions produced zero admissible outputs and deterministic quarantine.

## ~150-word application project description

GBI BoundaryBench v0.1 is a research benchmark for legacy-EHR transformation boundaries. I built it around a separation between model proposals and programmatically verified admissible actions: models generate structured mappings, classifications, repairs, traces, or abstentions, while a deterministic verifier checks identity, provenance, terminology/version, temporal validity, evidence sufficiency, dependencies, and policy.

The empirical package uses answer-key-free held-out model inputs, frozen manifests, explicit model-run provenance, a blind raw-output freeze, and trusted scoring only after the raw freeze. In the first frozen run, Qwen/Qwen3-4B-Instruct-2507 completed 768 held-out executions across output-only, token-top-k, and full-category-evidence modes. Zero outputs satisfied the admissibility contract: 369 failed safe parsing, 399 failed schema validation, and all 768 were quarantined. The result is intentionally narrow: v0.1 shows an engineered failure boundary for one 4B open-weight model, not a general claim about all LLMs or all EHR transformation.

## ~300-word technical project description

GBI BoundaryBench v0.1 is a synthetic, reproducible benchmark for evaluating whether model-generated legacy-EHR transformations can cross a deterministic admissibility boundary. The project is built around a research thesis: model output should be treated as evidence, not authority. A model proposes a mapping, classification, repair, trace, or abstention; a separate Programmatic Verification Engine decides whether the proposal can be admitted, admitted as historical-only, quarantined at a slice level, sent to expert review, rejected, or abstained.

The benchmark covers eight task families: patient identity normalization, orphan/duplicate detection, field anomaly/free-text bleed, code-system version validation, RPMS-to-FHIR mapping, temporal status classification, evidence sufficiency, and policy action selection. Each task has typed inputs, allowed outputs, deterministic references, evidence requirements, failure slices, and explicit action semantics. The verifier checks safe parse/schema validity, exact reference compatibility, identity and provenance constraints, terminology/version behavior, temporal validity, evidence sufficiency, dependency-aware quarantine, and policy.

I implemented the empirical governance chain as an engineering artifact: answer-key-free held-out model inputs, a separate trusted verifier package, cryptographic freeze manifests, immutable execution-harness tags, model-run provenance, a raw-output freeze before scoring, and scored artifacts generated only from frozen raw outputs. Infrastructure interruptions are preserved as audit metadata instead of being hidden or mixed with canonical runs.

The first frozen held-out run evaluated Qwen/Qwen3-4B-Instruct-2507 at a pinned revision across 256 tasks and three evidence modes: output-only, token-top-k, and full-category evidence. All 768 executions completed, but no output satisfied the benchmark's admissibility contract. The runner recorded 369 safe parse rejects and 399 safe schema rejects; trusted scoring retained all 768 executions in the denominator and quarantined all of them. The result is narrow and deliberately conservative: it does not claim general LLM incapability or Qwen unsafety. It shows that, for this v0.1 run, inference completion was not enough; generated outputs failed before they became enterprise-admissible actions.
