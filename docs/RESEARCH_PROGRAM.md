# GBI BoundaryBench / GBI-DCSE research program

The public repository now covers a staged research program:

```text
GBI/DCSE theory
        ↓
BoundaryBench v0.1
        ↓
BoundaryBench v0.2 / admission-aware benchmark tuning
        ↓
GBI v2 runtime admissibility evaluation
        ↓
GBI-DCSE v3 claim-level systems verification
```

## GBI/DCSE theory

The original paper defines a typed boundary between model proposals and governed system action. The model or agent may emit a receipt or proposal, but a deterministic verification layer evaluates it against evidence, provenance, identity, versioned semantics, dependencies, and policy.

Canonical paper:

- arXiv: [`2608.10300v2`](https://arxiv.org/abs/2608.10300)
- repository PDF copy: [`../paper/GBI_DCSE_manuscript.pdf`](../paper/GBI_DCSE_manuscript.pdf)

## BoundaryBench v0.1

BoundaryBench v0.1 froze one held-out empirical model run:

- model: `Qwen/Qwen3-4B-Instruct-2507`;
- held-out tasks: `256`;
- evidence modes: `3`;
- canonical executions: `768`;
- accepted outputs: `0`;
- safe parse rejects: `369`;
- safe schema rejects: `399`;
- quarantined executions: `768`;
- coverage: `0.0`;
- selective risk: undefined at zero coverage.

This result showed deterministic fail-closed behavior under one 4B open-weight model/configuration. It did not show general LLM failure or general model safety.

## BoundaryBench v0.2

v0.2 addresses a benchmark-design problem exposed by v0.1: when admission is zero, conditional task performance is not identifiable. v0.2 introduces a finite, auditable parameter space and separates admission from task performance.

Public artifacts:

- [`../artifacts/public_results/v0_2/`](../artifacts/public_results/v0_2/)

## GBI v2

GBI v2 moves from benchmark-reference agreement toward runtime admissibility under authoritative witness state `W` and versioned policy `P`. Held-out reference actions are used only after the fact to test faithfulness; they are not runtime authority.

Public artifacts:

- [`../artifacts/public_results/gbi_v2/`](../artifacts/public_results/gbi_v2/)

## GBI-DCSE v3

GBI-DCSE v3 turns manuscript claims into a claim registry, evidence classes, and executable scorecard checks. It explicitly preserves out-of-scope production claims rather than promoting proxies into validation.

Public artifacts:

- [`../artifacts/public_results/gbi_dcse_v3/`](../artifacts/public_results/gbi_dcse_v3/)

## Research relevance

This work is relevant to researchers and enterprise AI teams because it provides a way to:

- distinguish formatting/admission failure from actual task competence;
- tune benchmark environments only when the intended metric is identifiable and reachable;
- convert verified failure slices into concrete targets for expert data, synthetic examples, evaluator design, retrieval changes, or post-training;
- evaluate proposed actions under versioned enterprise evidence and policy rather than model confidence alone;
- map manuscript claims to evidence categories and executable assertions;
- preserve a stable verification control plane while changing domain-specific policy/evidence objects.

The repository is not a clinical validation package, production EHR deployment, TEE deployment, BFT deployment, or proof against arbitrary frontier-model hallucination.
