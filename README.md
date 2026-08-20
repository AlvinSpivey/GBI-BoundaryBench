

# GBI BoundaryBench / GBI-DCSE Research Program

I realize applications of Topological Discovery have historically been hard to grasp. Hopefully this repository, explanations, and the following audio overview will be helpful as you review my work.

https://github.com/user-attachments/assets/d90b58ab-b51a-4248-b95d-17342ef45f3a

<p align="center">
  <a href="https://github.com/AlvinSpivey/GBI-BoundaryBench/blob/1f34ed2d2ea685d5e5f5451fb09e0412d6aacd48/paper/audio/audio_overview_small.mp4">
    <img src="https://img.shields.io/badge/▶%20Listen-Audio%20Overview%20(.mp4)-blue?style=for-the-badge" alt="Download Uncompressed Audio" width="300">
  </a>
</p>

---


## A Paradigm Shift in Healthcare Interoperability: The GBI-DCSE Substrate for Full-Stack AI Verification

The Geometric Belief Interface and Decentralized Cryptographic Sheaf-Enclave (GBI-DCSE) architecture establishes a rigorous formal substrate for clinical artificial intelligence, reclassifying interoperability as a "boundary problem". This framework necessitates a neuro-symbolic partition where the generative model functions as the *ars inveniendi* (discovery) and the substrate acts as the *ars iudicandi* (judgment). 

By treating model outputs as evidence rather than authority, the architecture enables a verifiable transition from the "fail-closed" zero-coverage baseline of BoundaryBench v0.1 to the full-stack architectural claims of GBI-DCSE v3. The GBI-DCSE protocol enforces a selective, policy-versioned routing substrate that utilizes homological algebra to isolate clinical contradictions through "Surgical Quarantine" without compromising the atomicity of enterprise workflows.

### 1. The Crisis of Unverified Model Autonomy in Clinical Systems

Strategic healthcare informatics is currently threatened by "silent promotion"—the precarious phenomenon where unverified Large Language Model (LLM) outputs are elevated to authoritative clinical actions without passing through a deterministic judgment layer. Current "accuracy" metrics are fundamentally insufficient for enterprise safety; they provide a surface-level measure of linguistic fluency while ignoring the structural admissibility required for clinical state updates. A model may exhibit high confidence yet propose actions entirely unsupported by the authoritative witness record.

The necessity of a formal verification layer was demonstrated by the BoundaryBench v0.1 results. In a frozen evaluation of the Qwen3-4B-Instruct-2507 model, 768 model executions were completed, yet zero results crossed the admission contract. These failures were precisely factored: 369 safe parse rejects and 399 schema validation rejects. 

This "zero-coverage" result serves as a critical baseline, proving that successful inference is not synonymous with an enterprise-admissible action. Furthermore, the v0.2 "Benchmark Tuning" phase confirmed that without repairing this interface floor, any attempt to tune task difficulty remains "degenerate," as the semantic layer is never reached.

The zero-coverage baseline raises three core scientific questions for the field of medical informatics:

*   **Benchmark Difficulty:** Can difficulty be meaningfully parameterized if model outputs consistently fail the "fail-closed" requirements of structured clinical contracts?
*   **Gate Selectivity:** Can a verification substrate move beyond vacuous refusal to a state of high selectivity, permitting eligible work while quarantining contradictions?
*   **Architectural Scrutiny:** Do the broader systems-level claims—such as ledger non-equivocation, TEE-assisted attestation, and sparse certificate verification—survive executable scrutiny?

The mathematical resolution to these questions is found in the Logit-Boundary Geometric Belief Interface (GBI).

### 2. The GBI Paradigm: From Language Generation to Boundary Semantics

The GBI paradigm shifts clinical AI integration from the interpretation of natural language to the enforcement of a finite "Boundary Algebra". In this framework, the logit layer is treated as a numerical proposal over a finite set of categorical decisions (e.g., $\{\text{exact}, \text{conflict}, \text{unmapped}\}$). This "Logit Boundary" transforms a non-deterministic linguistic problem into a manageable interface for deterministic judgment, ensuring that no free-form clinical assertion can directly become a database update.

To ensure clinical safety, the GBI factors system failure across four discrete layers:

#### The GBI Factorization of Failure

| Verification Layer | Operational Objective |
| :--- | :--- |
| **Interface/Format Admission** | Ensures outputs are safely parsable and satisfy schema contracts before semantic evaluation. |
| **Task-Semantic Correctness** | Measures the accuracy of the proposed clinical action among successfully admitted outputs. |
| **Evidence/Policy Admissibility** | Evaluates whether the proposal is authorized by versioned institutional policy and authoritative witnesses. |
| **Systems Integrity** | Verifies the control plane, including identity, provenance, and TEE-assisted cryptographic signatures. |

Central to this interface is the Dirichlet Evidence registry. By enforcing a fixed "Evidence Box" where:

$$\alpha_i \in [\epsilon, A]$$

(with $A=20$ as the ceiling in v3 testing), the system prevents boundary singularities that lead to numerical instability. This ensures the Dirichlet Fisher metric remains well-conditioned, preventing "stiff" optimization where nearly excluded categories cause singular behavior. These local categorical decisions are synthesized into a global structure via the Distributed Cryptographic Sheaf-Enclave (DCSE) protocol.

### 3. DCSE: The Distributed Trust Substrate

Clinical safety mandates a decentralized approach to verification, moving away from centralized gating toward a non-equivocation profile assisted by Trusted Execution Environments (TEEs). The DCSE protocol ensures that actions are tied to a verifiable history, preventing the system from providing conflicting accounts of the same clinical event.

The Identity/Provenance Ledger is the load-bearing foundation of this architecture. While it does not prove "clinical truth" in a medical sense, it provides a non-equivocation guarantee by proving the provenance of the decision process. 

To maintain efficiency, the DCSE utilizes Sparse Enclave Certificates. By offloading dense linear algebra (e.g., SVD) to the host while keeping small deterministic checks inside the enclave, the system achieves a $14,741\times$ efficiency gain. Crucially, the enclave utilizes spectral moments to detect forged certificates; residual checks alone would accept a forged kernel, whereas spectral moments catch the forgery, making them empirically load-bearing rather than ornamental.

The attestation model handles seven distinct fault classes to maintain a "fail-closed" posture:

1. Invalid signatures
2. Expired quotes
3. Modified measurements
4. Unlisted measurements
5. Replayed nonces
6. Revoked platform keys
7. Downgraded TCB (Trusted Computing Base) versions

By halting authoritative writes when these faults are detected, the system prevents unverified platforms from updating the clinical state.

### 4. Clinical Impact: Solving the "Allergy-Medication" and "Renal-Context" Obstructions

High-value healthcare requires "Surgical Quarantine"—the ability to isolate specific clinical "stalks" (e.g., a single `MedicationRequest`) without halting the entire transaction. This isolation occurs at the stalk-level before the construction of a FHIR Transaction Bundle, thereby preserving the atomicity of the final commit.

#### Scenario Evaluations

*   **Penicillin/Amoxicillin Conflict:** When a model proposes an amoxicillin order for a patient with a confirmed penicillin allergy, the GBI gate identifies a "confirmed-conflict" status. By validating against version-pinned terminology, the system triggers a business-rule `OperationOutcome(severity=error, code=business-rule)`, effectively blocking the clinical write-back.
*   **Metformin/Renal Context:** If policy requires eGFR lab results for a metformin order, the GBI treats the "absence of evidence" as a hard gate. The system refuses to authorize the write, converting a hallucinated appropriateness into a documented abstention.

This localization is enabled by Sheaf-based localization and the calculation of Mapping-Cone Trace Energy ($E_\sigma$). Per Proposition 7.1, $E_\sigma$ is the metric of choice due to its basis-invariance; the diagnostic remains valid regardless of the orthogonal rotation of the obstruction subspace. This provides a physically meaningful localization of inconsistency, transforming the benchmark into a diagnostic loop for institutional policy.

### 5. The Claim-Register Methodology: A New Standard for Research Integrity

The GBI-DCSE v3 evaluation establishes a new standard for research integrity via a machine-readable Claim Register, enumerating explicit claims, auditable "nonclaims," and "out-of-scope" declarations. A load-bearing result of v3 is the portability test to the "sensitive-infrastructure" domain, where eight modules (including crypto, ledger, and transaction modules) were reused verbatim, proving the architecture's "Full-Stack" applicability across divergent domains.

The methodology also facilitated the discovery of the Fisher-bound Erratum. The evaluation revealed that the previously stated numerical bound ($\epsilon \approx 0.066$) was only correct for a specific one-dimensional slice and did not satisfy the $\kappa_2 \leq 10^4$ budget over the entire evidence box; the corrected box-wide bound was found to be:

$$\epsilon_{\text{box}} \approx 0.326472$$

This ability of the substrate to expose its own mathematical defects marks a paradigm shift in scientific transparency.

The v3 results are summarized as follows:
* **95 of 96** testable claims were met in the 99-row register.
* **3 claims** were declared out of scope (requiring hardware not present in synthetic tests).
* **1 claim** was corrected as an erratum.

The progression from the zero-coverage failures of v0.1, through the benchmark tuning of v0.2, to the architectural verification of v3, establishes GBI-DCSE as a reproducible and selective routing substrate. The core finding is that model output is evidence, not authority. While the substrate does not eliminate internal model hallucinations, it successfully contains them, providing a certificate-producing check at the model-to-system boundary that is ready for the next phase of frontier-model evaluation.

## Programmatic verification of model-to-enterprise boundaries

GBI BoundaryBench is a public research showcase for testing the boundary between a plausible model or agent proposal and an enterprise-admissible action. The core design principle is simple: a model output is evidence, not authority.

```text
MODEL / AGENT PROPOSAL
      ↓
TYPED EVIDENCE
      ↓
PROGRAMMATIC VERIFICATION
      ↓
VERSIONED ENTERPRISE POLICY
      ↓
ADMIT / QUARANTINE / REVIEW / REJECT
```

The repository is anchored in synthetic legacy-EHR transformation, then extends into admission-aware benchmark tuning, reference-independent runtime verification, and claim-level systems verification. Across all stages, the question is not whether a model output looks plausible; it is whether a typed proposal can cross a governed boundary under explicit evidence, provenance, version, dependency, and policy constraints.

This repository is an application-facing public showcase. It is not a clinical system, a medical device, a certified terminology crosswalk, or an autonomous EHR write-back service. Expected answers in the private research record are benchmark references derived from synthetic generator truth and explicit corruption manifests, not clinical truth.

## Research progression

| Stage | Research question | Evidence |
|---|---|---|
| BoundaryBench v0.1 | Can malformed/model-generated output be prevented from silently crossing the structured boundary? | Frozen Qwen3-4B held-out execution; 768/768 executions completed, zero accepted, deterministic quarantine. |
| BoundaryBench v0.2 / BeTaL-inspired tuning | Can benchmark difficulty be tuned without confusing interface admission failure with task competence? | 9-dimensional finite design space with 2,218,750,380 grid configurations; feedback-coordinate search mean held-out gap 2.87% versus 13.61% and 11.46% for non-feedback baselines. |
| GBI v2 runtime admissibility | Can a reference-independent runtime policy gate remain selective under repaired inputs, contradictions, and synthetic adversaries? | 512 synthetic tasks; selected strictness 0.6; 116/116 injected severe contradictions detected; zero silent promotions under evaluated synthetic adversaries. |
| GBI-DCSE v3 claim verification | Can the broader systems manuscript be converted into explicit, executable claim-to-evidence checks? | 99 registered manuscript claims, 96 testable, 95 met/supported plus one erratum; standalone scorecard verifier reports 148 checks and 0 failures. |

Important distinctions:

- `admission rate` is not the same as conditional task performance.
- benchmark reference answers are not runtime authority.
- deterministic format repair is not substantive answer repair.
- synthetic adversaries are not frontier-model executions.
- synthetic systems verification is not production clinical validation.

## Historical v0.1 empirical result

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

- Research program summary: [`docs/RESEARCH_PROGRAM.md`](docs/RESEARCH_PROGRAM.md)
- v0.2/v2/v3 summary: [`docs/application/GBI_V0_2_V2_V3_SUMMARY.md`](docs/application/GBI_V0_2_V2_V3_SUMMARY.md)
- Architecture figure: [`docs/application/figures/boundarybench_architecture.svg`](docs/application/figures/boundarybench_architecture.svg)
- Empirical failure-flow figure: [`docs/application/figures/qwen_v0_1_failure_flow.svg`](docs/application/figures/qwen_v0_1_failure_flow.svg)
- Application summary: [`docs/application/GBI_BOUNDARYBENCH_V0_1_SUMMARY.md`](docs/application/GBI_BOUNDARYBENCH_V0_1_SUMMARY.md)
- Enterprise portability: [`docs/application/ENTERPRISE_PORTABILITY.md`](docs/application/ENTERPRISE_PORTABILITY.md)
- Reproducibility summary: [`docs/application/REPRODUCIBILITY.md`](docs/application/REPRODUCIBILITY.md)
- Benchmark card: [`docs/benchmark_card.md`](docs/benchmark_card.md)
- Public aggregate results: [`artifacts/public_results/v0_1/`](artifacts/public_results/v0_1/)
- New result artifacts: [`artifacts/public_results/v0_2/`](artifacts/public_results/v0_2/), [`artifacts/public_results/gbi_v2/`](artifacts/public_results/gbi_v2/), [`artifacts/public_results/gbi_dcse_v3/`](artifacts/public_results/gbi_dcse_v3/)
- Papers: [`paper/README.md`](paper/README.md)

### Research manuscript

**Logit-Boundary Geometric Belief Interfaces and Sparse Sheaf-Enclave Protocols** — Alvin Spivey & Yu Huang

Research manuscript underlying the GBI/DCSE verification architecture and BoundaryBench evaluation framework.

**Status: public on arXiv as [arXiv:2608.10300v2](https://arxiv.org/abs/2608.10300).**

[Read the canonical arXiv paper](https://arxiv.org/abs/2608.10300) or the repository PDF copy: [`paper/GBI_DCSE_manuscript.pdf`](paper/GBI_DCSE_manuscript.pdf).

The original manuscript covers:

- typed model-to-system evidence boundaries;
- the versioned runtime admissibility policy `P`;
- healthcare / financial / government domain portability;
- pre-commit surgical quarantine and liveness;
- deterministic human-review surfaces;
- GBI BoundaryBench v0.1 empirical evaluation.

The companion manuscript, [`paper/GBI_DCSE_BeTaL_Companion.pdf`](paper/GBI_DCSE_BeTaL_Companion.pdf), adds benchmark-design and systems-verification evidence for BoundaryBench v0.2, GBI v2, and GBI-DCSE v3. It is prepared for arXiv submission and does not yet have an arXiv identifier.

## Why the newer work matters

The v0.2/v2/v3 stages make the research program more diagnostic:

- benchmark design can fail if admission degenerates, because zero admission makes conditional task competence unidentified;
- customer-specific failure surfaces require separating interface failure from capability failure;
- a runtime enterprise gate should be reproducible from versioned policy and evidence rather than benchmark answer keys;
- verification infrastructure should be capable of falsifying its own claims;
- the v3 claim registry converts research prose into evidence classes and executable assertions;
- cross-domain portability is demonstrated only for the evaluated synthetic domains and should not be generalized beyond them.

The practical claim remains narrow: the framework contains unsupported or inadmissible model outputs before governed downstream action under the tested policy. It does not solve hallucination generally, establish clinical safety, or validate a production deployment.

## Research relevance

For researchers and enterprise AI teams, the useful pattern is a separable evaluation control plane:

- evaluation quality: distinguish formatting/admission failure from actual task competence;
- dynamic benchmark design: tune benchmark environments only where the intended metric is identifiable and reachable;
- data development: convert verified failure slices into concrete targets for expert data, synthetic/counterfactual examples, evaluator design, retrieval changes, or post-training;
- runtime governance: evaluate proposed actions under versioned enterprise evidence and policy rather than model confidence alone;
- research assurance: map manuscript claims to evidence categories and executable assertions;
- portability: preserve a stable verification control plane while changing domain-specific policy and evidence objects.

The newer artifacts make the model/system boundary more measurable; they do not predetermine any particular vendor, product, or training intervention.

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
artifacts/public_results/v0_2/
artifacts/public_results/gbi_v2/
artifacts/public_results/gbi_dcse_v3/
```

The public result files contain aggregate and slice metrics, status distributions, claim registers, scorecards, and provenance identifiers. They intentionally do not contain trusted held-out answer content or raw held-out model responses.

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
src/boundarybench/betal/         v0.2 benchmark-tuning simulator and deterministic verification helpers
src/boundarybench/gbi/           GBI v2/v3 claim and appendix verification helpers
src/boundarybench/dcse/          synthetic DCSE protocol/ledger/receipt/certificate verification helpers
artifacts/public_results/v0_1/   public-safe aggregate scored metrics and provenance
artifacts/public_results/v0_2/   admission-aware benchmark tuning artifacts
artifacts/public_results/gbi_v2/ reference-independent runtime admissibility artifacts
artifacts/public_results/gbi_dcse_v3/ claim-level systems verification artifacts
docs/betal/                      v0.2/v2/v3 reports, figure sources, and generated figures
paper/                           public manuscript PDFs and companion source
```

## Limitations and next experiments

BoundaryBench v0.1 is synthetic-only and non-clinical. The frozen empirical result evaluates one 4B open-weight model family, not the frontier-model ecosystem. There are no confidence intervals, repeat-run stability estimates, provider-cost comparisons, or completed human-review statistics for this run. Zero coverage prevents selective-risk estimation, and v0.1 does not isolate every possible cause of parse/schema failure.

Next work should diagnose parse/schema failures on public-development cases without modifying v0.1 held-out semantics, add a second open-weight family such as Mistral, compare closed providers such as OpenAI under output-only constraints, test structured-output interfaces, and add confidence intervals and repeat-run stability when meaningful.

## Licensing boundary

Original software in this repository is offered under Apache-2.0 as stated in `LICENSE`. Synthetic benchmark data, documentation, notices, and third-party material have separate boundaries in `DATA_LICENSE.md`, `DOCUMENTATION_LICENSE.md`, `NOTICE`, and `THIRD_PARTY_NOTICES.md`.

No license is granted for private credentials, confidential business materials, private endpoints, real PHI/PII, hidden held-out answer content, trusted verifier packages, raw held-out responses, or third-party source material not expressly cleared for redistribution.
