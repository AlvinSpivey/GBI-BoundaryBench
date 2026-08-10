# Enterprise portability of the BoundaryBench verification architecture

GBI BoundaryBench v0.1 is instantiated in legacy-EHR transformation. The public benchmark uses synthetic healthcare-style records because that setting makes identity, provenance, terminology, temporal validity, dependencies, evidence sufficiency, and policy constraints concrete.

The broader architecture is not healthcare-specific:

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

The verification architecture is portable; the task semantics, authoritative evidence, dependencies, and policy contract are domain-specific. A financial, government, industrial, or support-workflow system should not copy the healthcare task suite unchanged. It should instantiate the same boundary pattern with its own admissible actions, evidence sources, controlled vocabularies, dependencies, and policy authority.

## GBI/DCSE enterprise state

An enterprise deployment can be described by the state:

```text
(B, V, Θ, F, W, L, P)
```

where:

| Symbol | Meaning | Enterprise interpretation |
|---|---|---|
| `B` | Boundary algebra | Finite typed universe of assertions/actions the model or agent may propose. |
| `V` | Versioned semantic/terminology bundle | Ontologies, schemas, code systems, mappings, taxonomies, protocol versions, or controlled vocabularies defining meaning at runtime. |
| `Θ` | Evidence registry | Calibrated local categorical evidence state. In the manuscript this includes hierarchical Dirichlet evidence. Model confidence is evidence, not authority. |
| `F` | Candidate/local state | Proposed local assertions, mappings, actions, records, or work items to be evaluated. |
| `W` | Authoritative grounding state | Systems of record, signed source data, approved registries, trusted references, human decisions, or other evidence against which candidate state is judged. |
| `L` | Identity / provenance / non-equivocation ledger | Entity identity decisions and immutable provenance/history needed to bind an action to the correct subject and execution context. Ledger consistency alone does not prove identity truth. |
| `P` | Versioned runtime admissibility policy | Enterprise contract mapping verified facts and failures to allowed actions. |

`P` is the operational center of the system. The verifier does not ask whether the model output is plausible in general; it asks whether a typed proposal is admissible under the current enterprise policy, evidence, version, identity, dependency, and authority constraints.

## Operational decomposition of policy

For implementation and governance, a useful operational decomposition is:

```text
P = (A, G, T, D, H, Q, R, Lambda, E, Fb)
```

This is an enterprise decomposition of the manuscript’s policy object, not a claim that this tuple is already a proven mathematical theorem.

| Component | Meaning |
|---|---|
| `A` | Allowed actions. |
| `G` | Hard gating predicates. |
| `T` | Thresholds and validity windows. |
| `D` | Dependency rules. |
| `H` | Human-authority and dual-control rules. |
| `Q` | Quarantine semantics. |
| `R` | Recovery and escalation rules. |
| `Lambda` | Liveness and degraded-operation constraints. |
| `E` | Exceptions and signed override rules. |
| `Fb` | Failover behavior. |

Every policy instance should be versioned and attributable. At minimum, an evaluation or production policy should record:

- `policy_id`
- `version`
- `effective_time`
- `authority`
- `hash`

This is what lets two evaluations distinguish “the model behaved differently” from “the enterprise policy or evidence contract changed.”

## Domain translation

| State | Healthcare / EHR | Financial services | Government / mission systems |
|---|---|---|---|
| `B` | Mapping/action states such as exact/equivalent/conflict/unmapped and admissible clinical-data actions. | Approve / hold / review / sanctions-review / fraud-review / reject / reconciliation-conflict. | Verified / conflicting / incomplete / releaseable / restricted / review-required / reject. |
| `V` | FHIR versions, RxNorm/SNOMED/LOINC/local dictionaries, policy versions. | Instrument/product taxonomies, legal-entity schemas, message versions, sanctions-list versions, risk-model versions. | Mission schemas, controlled vocabularies, policy directives, handling rules, data-standard versions. |
| `Θ` | Evidence over patient identity, code mapping, temporal status, source freshness, or admissible clinical-data action categories. | Evidence over legitimate/suspicious/blocked/unknown, entity matching, transaction status, or other bounded decisions. | Bounded evidence over entity resolution, source reliability, mission status, releaseability, or action categories. |
| `F` | Candidate mappings, FHIR resources, identity links, temporal status. | Candidate payment, trade, reconciliation update, underwriting result, account change, or agent action. | Candidate claim, case update, entity association, report element, workflow action, or agent tool call. |
| `W` | Source EHR records, authoritative terminology, provenance, human adjudication. | Core ledger, KYC systems, approved market feeds, sanctions sources, risk limits, signed authorizations. | Authoritative registries, signed source records, mission systems, directives, human adjudication. |
| `L` | Patient/provider/resource identity and signed clinical-data provenance. | Customer/account/legal-entity identity and transaction provenance. | Entity/case/credential identity and signed provenance history. |
| `P` | Identity, terminology, temporal, evidence, dependency, and clinical-data write-policy constraints. | Limits, counterparty eligibility, sanctions, freshness, separation of duties, human approval, jurisdiction, permitted automation, override, and failover. | Access, classification/handling, need-to-know, provenance, source requirements, jurisdiction, allowable autonomous actions, human-authority thresholds, continuity-of-operations, and degraded-mode rules. |

The table shows portability of the verification contract, not portability of the healthcare benchmark tasks themselves.

## Liveness and surgical quarantine

Surgical quarantine does not mean partially committing an operation whose underlying system requires atomicity. GBI/DCSE can replace unnecessary pipeline-wide failure with pre-commit, work-item-level quarantine while preserving atomic transaction semantics wherever the underlying system requires them.

Examples:

- Financial services: one disputed payment or legal-entity mapping is excluded from a candidate settlement batch and routed for review; unrelated verified work may continue if institution policy permits.
- Government / mission systems: one ambiguous entity association or unsupported report assertion is quarantined while independent mission work remains live under policy.
- Healthcare / EHR: an inadmissible stalk is excluded or separately routed before an atomic FHIR transaction is constructed.

The verifier should never claim partial success inside a transaction that must be all-or-nothing. The correct boundary is usually before constructing or submitting the atomic transaction.

## Human review surface

Review should not collapse to:

```text
AI confidence = 94%; approve?
```

Model confidence can be part of `Θ`, but it is not authority. Human reviewers need a deterministic contradiction table with fields such as:

| criterion | candidate value | authoritative evidence | status | policy rule | required action |
|---|---|---|---|---|---|
| identity | proposed entity link | system-of-record and provenance ledger evidence | conflict | `P.identity.require_unique_binding` | `QUARANTINE` |
| source freshness | candidate source timestamp | approved feed version and validity window | stale | `P.freshness.max_age` | `REVIEW` |
| terminology/schema version | proposed code or schema | versioned bundle `V` | unsupported | `P.version.allowed_bundle` | `REJECT` |
| authority | proposed autonomous action | dual-control requirement | missing approval | `P.authority.dual_control` | `EXPERT_REVIEW` |
| dependencies | unaffected work item assertion | dependency graph | independent | `P.dependencies.allow_slice_continuation` | `ADMIT` if other criteria pass |
| provenance | cited evidence reference | immutable source history | unverifiable | `P.provenance.require_signed_source` | `QUARANTINE` |

Geometry and visualizations can be useful for diagnosis or operator orientation. For review, the scannable tabular verification record should remain authoritative: it shows the criterion, the candidate value, the authoritative evidence, the policy rule, and the required action.

## Customer-specific diagnostic loop

A customer-deployed diagnostic evaluation can run against the customer’s actual model, agent, retrieval, data-interface, and policy stack:

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

This turns failure slices into a data-development roadmap: expert labeling, synthetic or counterfactual examples, grader/evaluator development, retrieval improvements, benchmark expansion, or post-training environments. Which intervention is appropriate depends on the observed failure surface. The benchmark should identify where specialized data-development work could add value; it should not predetermine that any particular vendor or product must be the answer.

## What transfers and what does not

What transfers:

- typed proposal/result contracts;
- evidence receipts;
- deterministic verification before action;
- versioned policy and provenance;
- fail-closed parsing/schema boundaries;
- quarantine/review/admit/reject action semantics;
- failure-slice reporting for targeted improvement.

What does not transfer automatically:

- healthcare task semantics;
- clinical terminology and FHIR-specific constraints;
- synthetic EHR corruption patterns;
- healthcare reference actions;
- any domain’s authoritative evidence, policy, or legal authority.

The portable claim is therefore narrow and operational: separate model or agent proposals from enterprise-admissible actions, then evaluate the boundary with versioned evidence and policy.
