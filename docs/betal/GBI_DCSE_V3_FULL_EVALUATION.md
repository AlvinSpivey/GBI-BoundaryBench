# GBI-DCSE v3 — Full Evaluation Against Every main.pdf Claim

**Including the DCSE half, and an assessment as a triage substrate for sensitive
infrastructure data with coherent provenance and receipts**

| Field | Value |
|---|---|
| Run plan | `gbi-dcse-v3-evaluation-plan-v3.0.0` |
| Benchmark contract | `benchmark-contract-v0.1` (unmodified) |
| Verifier | v0.1 Programmatic Verification Engine, unmodified |
| **Claims enumerated from main.pdf** | **99** |
| **Testable claims met** | **95/96** |
| Out of scope (never reported as met) | 3 |
| Errata against the manuscript | 1 |
| Language models executed | **0** |
| TEE / BFT cluster / FHIR server / ZK prover | **None** |
| Signatures | Real Ed25519 |
| Verification | **148 checks, 0 failures.** |
| Artifacts | [`artifacts/public_results/gbi_dcse_v3/`](../../artifacts/public_results/gbi_dcse_v3/) |

---

## 1. The direct answer

At the end of v2 I wrote that the DCSE half of GBI-DCSE had **zero empirical
support in either direction** — that the GBI half was well evidenced and the DCSE
half was "architecture on paper." That was the correct assessment then. It is no
longer correct.

**DCSE, evaluated on its own terms: positive.** All seven Section 9.1 protocol
objects are implemented and exercised. All ten Section 9.2 policy components are
present. The three Appendix B.1 systems-validation protocols — attestation
verification, consensus fault injection, rollback conformance — now execute and
pass. The one load-bearing engineering claim in Section 9.3, that a small sparse
check inside the enclave can certify a dense computation performed outside it
*against a solver that lies*, holds against nine forgery classes.

**GBI, re-checked completely: positive.** Sections 2, 3, 4, 6.2 and 8 had no test
at all before v3. All ten of their claims now hold, including the Section 2.7
dynamical example the manuscript explicitly declines to implement, and the three
Section 8.1 safety checks that Appendix A omits.

**The combination: positive, with three honest holes and one erratum.** Of 99
enumerated claims, 95 of the 96 testable ones are met. The single unmet claim is an
**erratum** — a numerical bound in §6.3 that does not hold over the box it is
stated for. Three claims are **out of scope** and are never reported as met: the
zero-knowledge prover, the clinical retrospective playback, and the attestation
bootstrapping time. Each needs infrastructure or a cohort that does not exist here.

### Coverage by manuscript section

| Section | Claims met | Section | Claims met |
|---|---|---|---|
| §1 organizing picture | 3/3 | §8 audit geometry | 8/8 |
| §2 logit topology | 11/11 | §9 DCSE protocol | 15/16 |
| §3 boundary semantics | 4/4 | §10 EHR application | 4/4 |
| §4 condensed probes | 3/3 | §11 BoundaryBench v0.1 | 3/3 |
| §5 neuro-symbolic split | 3/3 | §12 containment | 9/9 |
| §6 Dirichlet evidence | 7/8 | Appendix A | 3/3 |
| §7 sheaves and cones | 7/7 | Appendix B | 15/17 |

By evidence class: 16 `REPRODUCED`, 51 `MEASURED`, 5 `MEASURED_SYNTHETIC`,
22 `STRUCTURAL`, 1 `PARTIAL_PROXY`, 3 `OUT_OF_SCOPE`, 1 `ERRATUM`.

---

## 2. The DCSE layer, which did not exist before v3

### 2.1 The ledger L, and its scope limit

Section 9.1 lists L among the seven protocol objects; Section 9.4 gives it two
modes and four fallback triggers. It is now a hash-chained, per-node append-only
log with a strictly monotonic counter and **real Ed25519 signatures**.

Seven fault classes injected. All seven detected, and each classified *as itself*
rather than merely flagged:

| Injected fault | Detected as |
|---|---|
| monotonic counter rollback | `monotonic_counter_failure` |
| monotonic counter repeat | `monotonic_counter_failure` |
| hash-chain break | `hash_chain_break` |
| sequence reuse | `sequence_gap_or_reuse` |
| nonce replay | `nonce_replay` |
| forged signature | `invalid_signature` |
| equivocation at one sequence | equivocation evidence emitted |

The signature choice is not incidental. Section 9.4's non-equivocation property is
only useful if a third party holding **no secret** can verify that a node signed
two conflicting statements. The verification suite does exactly that: it builds an
equivocating pair and verifies both signatures against the public key alone, then
confirms the two signed bodies genuinely differ. A shared-key MAC could not support
that, so Ed25519 is load-bearing rather than decorative.

All five write-path guards behave correctly: a clean ledger on the fast path
permits writes (so the test is not vacuous), and equivocation, attestation loss,
counter-service failure and a below-quorum replica population each halt
authoritative writes.

**The scope limit is tested as its own claim.** Section 9.4 says the ledger "proves
protocol-level non-equivocation, not patient identity truth." That is a negative
claim, so it needs a witness: a structurally perfect, non-equivocating ledger that
records a *factually wrong* identity binding. The suite produces one. Ledger
validity and identity correctness are demonstrably independent, which is what the
manuscript claims and what an over-claiming implementation would get wrong.

### 2.2 Attestation verification (Appendix B.1)

Seven injection classes, each caught by its **intended** check rather than by
whichever check happened to fire first:

| Injection | Caught by |
|---|---|
| invalid signature | `signature_valid` |
| expired quote | `quote_not_expired` |
| modified measurement | `signature_valid` |
| unlisted measurement, correctly signed | `measurement_in_allowlist` |
| replayed nonce | `nonce_matches_challenge` |
| revoked platform key | `signer_not_revoked` |
| downgraded TCB version | `tcb_version_at_or_above_minimum` |

Every one denies the governed write path. A valid quote is accepted, so the suite
distinguishes a working verifier from one that refuses everything.

The fourth row matters: a *correctly signed* quote for an unapproved build must
still be rejected. A verifier that only checked signatures would pass it.

**What this is not.** There is no hardware root of trust, no real MRENCLAVE, and no
IAS/DCAP round trip. The manuscript's own conditional on key revocation — test it
"only in deployments whose key-management design actually uses attestation-bound
database keys" — is honoured: revocation is tested as verifier behaviour and no
claim is made about attestation-bound keys.

### 2.3 Consensus fault injection (Appendix B.1)

62 configurations analysed **exhaustively over the model**, not sampled. For each
(n, f, Byzantine, crashed, partitioned) the analysis enumerates every split of
correct replicas between two conflicting values and reports whether both can reach
a 2f+1 quorum.

| Property | Result |
|---|---|
| Safety at ≤ f Byzantine faults | holds in every configuration |
| Safety at f+1 Byzantine faults | **violable — the bound is tight** |
| Replica population below 3f+1 | halts with `replica_population_below_3f_plus_1` |
| Crash faults ≤ f | progress; > f halts |
| Partition ≤ f | progress; > f halts |
| Authoritative write while halted | never |

The second row is what makes the first meaningful. A model that reported safety at
f+1 faults would be wrong, and a suite that never tested f+1 could not tell the
difference. The verification suite re-derives the arithmetic by hand for f = 1…5:
two quorums of 2f+1 in a population of 3f+1 intersect in exactly f+1 replicas, so
with at most f Byzantine at least one *correct* replica sits in both — and a correct
replica votes once.

### 2.4 The enclave sparse certificate (Section 9.3)

This is the DCSE claim with real engineering content, and it is the one worth
testing hardest:

> "Dense SVD, QR, and large eigensolvers are performed outside the enclave or
> replaced with sparse certified residual checks."

If that fails, the partitioning collapses: either the dense work moves inside and
blows the resource budget, or the enclave trusts an untrusted solver.

Setup: a cone Laplacian on a 60-vertex cycle complex, **n = 240**, 477 nonzeros,
true obstruction dimension 3. The dense eigendecomposition runs outside. The
enclave verifies a two-part certificate.

| Half | Check | Certifies |
|---|---|---|
| Residual | `‖B ᵀB − I‖ ≈ 0` and `max_i ‖L b_i‖ ≤ tol` | dim ker **≥** k |
| Spectral moments | `Σλ_i = tr(L)` and `Σλ_i² = ‖L‖_F²` | dim ker **≤** k |

Nine forgery classes, all rejected:

| Forgery | Rejected by |
|---|---|
| random basis | residual |
| basis from a different matrix | residual + moments |
| over-claimed dimension | residual + moments |
| **under-claimed dimension, hiding obstruction** | **moments only** |
| unnormalized basis | residual |
| fabricated spectrum | moments |
| stale ledger head | hash chain |
| wrong policy version | policy evaluation |
| forged signature | signature/nonce |

**The fourth row is the finding.** A residual check alone cannot rule out *more*
obstruction than claimed — an adversary who drops a genuine kernel direction hides
a real inconsistency and every residual still passes. The verification suite proves
this directly: it runs the residual half alone against the trimmed basis and
observes a worst residual of **2.28 × 10⁻¹⁵**, comfortably inside tolerance. So the
spectral-moment half is not decorative; without it the certificate would accept a
solver that under-reports the failure. A suite that checked only residuals would
have shipped that hole.

Resource accounting against a declared WASM/WAMR-style budget:

| | Sparse enclave path | External dense path | Budget |
|---|---:|---:|---:|
| Flops | 8,440 | 124,416,000 | 5,000,000 |
| Peak heap (bytes) | 13,440 | 921,600 | 262,144 |
| Syscalls | 2 | — | 64 |
| Within budget | **yes** | **no** | — |

A **14,741×** flop ratio and a 68.6× heap ratio. The dense path exceeds the declared
budget on both axes; the sparse path uses 0.17% of the flop budget and 5% of the
heap budget. That is the quantitative version of the manuscript's design rationale.

### 2.5 Rollback conformance and the atomicity/liveness tension

Appendix B.1 asks for a corrupted medication order nested inside a multi-resource
transaction bundle. Sections 7.3 and 9.2 add the harder constraint: quarantine must
happen *before* bundle construction, and localized quarantine is "not permission to
partially commit an operation whose underlying system requires atomicity."

Two claims in tension, both tested by **diffing the store**, not by reading a
return code:

| Property | Result |
|---|---|
| Bundle with a corrupted order commits | nothing |
| Store state after rejection | byte-identical |
| Entries of the rejected bundle present in store | none |
| Unrelated resources | unchanged |
| OperationOutcome | `severity: error`, `code: business-rule` |
| Failed attempt captured in audit path | yes (3 audit entries) |
| Independent verified work | **progressed** |
| Held-back work | rerouted to a separately scoped transaction, not dropped |

The failure mode a naive implementation falls into is satisfying liveness by
partially committing. The store diff rules that out directly.

### 2.6 Receipt coherence and replay (the "coherent provenance" requirement)

Five decisions produced **14 receipts** across all three kinds — `AuditEvent`,
`OperationOutcome`, `Provenance` — hash-linked to each other and bound to the
identity ledger.

| Coherence property | Result |
|---|---|
| Receipt chain verifies | yes |
| Ledger binding verifies | yes |
| Every decision has its required receipt set | yes |
| Every refusal carries an OperationOutcome with severity and code | yes |
| Every receipt pins policy **and** terminology version | yes |
| Review surface carries all 7 deterministic reason fields | yes |
| Review surface carries a model confidence number | **no** |
| Tampering with one receipt body | detected (`invalid_receipt_signature`, `receipt_chain_break`) |
| **Replay from the receipt reproduces the original decision** | **14/14** |

Replay is the property that makes provenance an audit trail rather than a log.
Given only a receipt — its recorded witness digest, policy version and terminology
version — re-deriving the decision reproduces the original verdict exactly, for
every receipt. That is also the mechanism half of Appendix B.1's retrospective
playback item; the clinical half is out of scope (§4).

The confidence-number row implements Section 9.2's automation-bias requirement as a
prohibition rather than a preference: three forbidden fields (`model_confidence`,
`logit_margin`, `softmax_probability`) are checked absent from every review surface.

### 2.7 The consistency certificate, and the zero-knowledge boundary

Section 9.5's precondition is the testable part:

> "If vanishing of a particular cohomology group is part of the certificate, that
> property must be encoded by a concrete finite computation or residual check; the
> expression H¹(Cone φ) = 0 is not itself a witness predicate."

`VerifyConeCertificate(c, w)` is now a total, terminating predicate with **9 finite
clauses**. Honest certificates are accepted for both a consistent complex
(H¹ vanishes, dim 0) and an obstructed one (dim 2). Three forgeries rejected: a
false H¹ = 0 claim, an operator substitution, and a fabricated spectrum. The public
input binds the transaction digest and the policy version, so changing the policy
version changes the digest and a certificate cannot be replayed across policies.

**Zero knowledge is not implemented and not claimed.** What exists is a binding,
blinded hash commitment plus a finite predicate — strictly weaker, because a
verifier given the witness learns it. The manuscript frames the ZK layer as future
work and it remains future work. Claiming otherwise would be the single easiest way
to overstate this framework, so the artifact records
`zero_knowledge_implemented: false` and the register marks §9.5's proof system
`OUT_OF_SCOPE`.

---

## 3. The GBI sections that had never been tested

### 3.1 Appendix A ported and reproduced independently

The manuscript ships a complete Julia reference implementation. It is now ported to
Python — different language, different linear-algebra library, no access to the
original runtime — and **all 11 `run_self_check` assertions pass** with **all 21
published values reproduced**:

| Quantity | main.pdf | Recomputed |
|---|---|---|
| Singular values of A | 1.254966, 1.110695, 0.737507 | identical to 6 d.p. |
| Axis eccentricity H | 1.701632 | 1.701632 |
| Jacobian J | 1.028 | 1.028000 |
| Outer distortion K_O | **1.922661** | 1.922661 |
| Stalk energies | 0.019778 / 1.977750 / 0.002472 | agree to < 0.01% |
| Fisher eigenvalues (interior) | 0.029494, 0.254435, 0.361568, 0.603356 | identical to 6 d.p. |
| Fisher condition (interior / boundary) | 20.46 / 4.55 × 10⁵ | 20.457 / 4.549 × 10⁵ |
| trigamma(0.01) / trigamma(14) | 10001.621 / 0.074040 | identical |
| Local mapping-status entropy | — | **1.627658** bits |

The ported `approx_trigamma` is validated in both directions: it reproduces the
manuscript's numbers *and* agrees with an independent series/asymptotic
implementation to 2.5 × 10⁻⁹. Agreement across two independent implementations means
these are properties of the mathematics, not of one runtime.

The port deliberately keeps the projector surrogate **as a surrogate**, labelled
`projector_surrogate_not_a_mapping_cone`. Silently upgrading it to the real cone
built in `betal/cone.py` would erase a distinction the manuscript is careful to draw.

### 3.2 Sections 2, 3, 4, 6.2, 8

| Claim | Result |
|---|---|
| §2.1 Def 2.1 / Thm 2.1 affine reconstruction | holds; worst residual 2.2 × 10⁻¹⁵ |
| §2.2 probe-visible quotient | kernel dim 4; kernel perturbations up to 1000× produce drift < 10⁻¹²; a control direction produces drift 0.85 |
| §2.5 entropy table at τ ∈ {1, 0.5, 0.2, 0.05} | all four rows reproduce to 6 d.p. |
| §2.5 top-3 tail mass | 0.041708 vs published 0.0417 |
| §2.5 D_KL under hard truncation | infinite, as claimed |
| §2.6 component-logit decomposition | exact (25 attributable components) |
| **§2.7 category switch under high entropy** | **2 switches with entropy never below 0.665 nats — 96% of the two-category maximum** |
| §3 Boolean homomorphism | exhaustive over 64 elements and **4096 pairs**, zero violations |
| §4 operational probes | positive probe passes; each of 4 invariants has a negative probe that fails on that invariant *only* |
| §6.2 dynamic atom registry | 9 categories after growth, min Fisher eigenvalue 0.124, α = 0 rejected |
| **§8.1 all four safety checks** | **all pass; 3 of the 4 absent from Appendix A** |
| §8.2 / B.3 Boundary 3 | holds in both directions |

Two are worth pulling out.

**§2.7 was explicitly unimplemented.** The manuscript says "the present appendix
does not implement that dynamical example" for a category switch under sustained
high entropy. It is implemented: a driven two-state system crosses the decision
boundary twice while entropy never drops below 0.665 nats against a two-category
maximum of ln 2 = 0.693. That is the regime where a smooth logit trajectory crosses
a discrete boundary with no confidence signal marking the crossing — precisely the
situation the manuscript says deterministic judgment exists to handle.

**Boundary 3 is a negative claim, so both directions are tested.** A badly
conditioned but policy-clean chart (K = 20.0) is flagged for review and **not**
quarantined; a well-conditioned chart (K = 1.07) with a real policy violation **is**
quarantined. A system letting K drive decisions fails the first; one ignoring policy
fails the second.

---

## 4. What remains negative: one erratum, three holes

Stated at the same prominence as the results.

### 4.1 The erratum (C-6.6) — a numerical bound that does not hold

§6.3 states the 10⁴ condition-number budget is crossed near ε ≈ 0.066. Solving the
one-dimensional sweep `[ε,3,4,5]` exactly gives **ε = 0.066021703**, confirming the
figure *for that slice*.

But Appendix B.1 Assertion 2 requires a **corner sweep of the declared box**. The
worst corner puts K−1 coordinates at ε and one at the ceiling. Over `[ε,20]⁴` the
slice bound yields a worst-corner condition number of **4.79 × 10⁵ — about 48× over
budget**. The bound that actually holds is **ε = 0.326472**, ~4.9× larger, and it
depends strongly on the ceiling (0.093 at A = 5; 0.919 at A = 50).

This is not a contradicted theorem — the manuscript calls the figure "illustrative."
It is a stated numerical bound that the manuscript's own assertion, executed as
written, refutes. Any deployment adopting ε ≈ 0.066 with a ceiling of 20 operates
~48× outside its own declared conditioning budget. v3 uses the box-wide bound.

### 4.2 Three out-of-scope claims, never reported as met

| Claim | Why | What *is* established |
|---|---|---|
| **C-9.16** zero-knowledge proof of the consistency result | no proof system; the manuscript itself frames this as future work | the finite-encoding precondition, plus a binding blinded commitment |
| **C-B1.7** retrospective clinical playback over a powered cohort | requires a real preregistered cohort and expert adjudicators | the reproducibility mechanism: receipt-driven replay reproduces 14/14 decisions |
| **C-B2.4** attestation bootstrapping time ≤ 2.5 s | requires a TEE/IAS handshake | software verification-path p95 of 0.168 ms, reported as a proxy only |

The register's own integrity is machine-checked: a claim marked `OUT_OF_SCOPE` must
resolve to `None`, and any claim in *any other* class that resolves to `None` raises
an error rather than being silently counted as out of scope. That guard exists
because a broken resolver quietly downgrading a testable claim is the most dangerous
failure mode for a register whose job is honesty about what was established.

### 4.3 Standing limits, unchanged from v2

1. **No language model executed.** Zero provider calls.
2. **Synthetic and non-clinical throughout.** No real EHR, asset, operator,
   location or telemetry value.
3. **No TEE, BFT cluster, FHIR server or ZK prover.** The consensus result is an
   exhaustive analysis of a model, not a running cluster. The enclave budget is
   enforced in accounting, not by hardware.
4. **Contradiction classes are declared, not discovered.** Ten clinical, ten
   infrastructure. Real coverage is unestablishable here.
5. **`E_σ` remains `scoring_weight: 0`, `validated: false`.**
6. **The false-conflict denominator remains a judgement call** (narrow 0.0%, broad
   4.27% against a 4% target).

---

## 5. As a triage substrate for sensitive infrastructure data

This was the specific question, so here is the specific answer.

### 5.1 Portability, measured rather than asserted

Table 1 claims the architecture is shared while semantics are domain-specific. v3
instantiates the Government/mission-systems column for sensitive infrastructure
asset and telemetry records, and reports **what had to change**:

| | Count | Detail |
|---|---:|---|
| Domain-neutral modules reused **verbatim** | **8** | crypto, ledger, attestation, consensus, enclave, transaction, receipts, cone_certificate |
| Domain-specific objects written fresh | **4** | witness type, policy function, gate precedence, severe-class list |
| Architectural changes required | **0** | — |

The systems layer ran unchanged: attestation injections all fail closed, all
consensus invariants hold, the enclave certificate holds.

### 5.2 Triage performance on the infrastructure population

512 synthetic records. **265** carry an injected severe contradiction; **175** are
fully clean; the remainder legitimately require review or historical-only release.
All ten severe classes are represented.

| Measure | Result |
|---|---|
| Severe contradiction sensitivity | **1.000** (265/265, 0 missed) |
| False conflict adjudication rate | **0.000** (0/175) |
| Receipt chain valid | yes |
| Ledger valid and non-equivocating | yes |
| Atomicity under a forced bad entry | held; unrelated records unchanged |

Action distribution: 175 release-verified, 54 release-historical-only, 157 reject,
78 quarantine-record, 44 analyst-review, 4 abstain.

The 15 infrastructure gates cover the concerns that distinguish this domain from
healthcare: **classification handling caveats, need-to-know, jurisdiction, source
reliability rating, directive version pinning** — alongside the shared concerns of
entity resolution, catalog signature, provenance and validity windows.

### 5.3 What this supports, and what it does not

**Supports.** The substrate is a defensible *router* in front of human adjudication
for sensitive infrastructure data quality. It resolves every severe contradiction
deterministically, sends zero clean records to a human, emits a hash-linked
receipt for every decision that replays to the same verdict, halts authoritative
writes on attestation loss or equivocation or below-quorum, and never partially
commits an atomic bundle. For a domain where "who decided this, on what evidence,
under which directive version, and can you prove it later" is the operative
question, that is the right shape of answer.

**Does not support.** Any claim about operational readiness. There is no accredited
TEE, no real BFT deployment, no integration with an authoritative registry, no
handling-caveat model reviewed by anyone with actual classification authority, and
no real data of any kind. The gate set is mine, not an operator's. In a real
programme the ten severe classes would be elicited from the people who own the
directives, and the false-conflict rate would be measured against *their* judgement
of what counts as a conflict — which is the part no synthetic harness can supply.

---

## 6. Reproduce and verify

```bash
PYTHONPATH=src python3 scripts/run_betal_v0_2_search.py
PYTHONPATH=src python3 scripts/run_gbi_v2_scorecard.py
PYTHONPATH=src python3 scripts/run_gbi_dcse_v3_scorecard.py
PYTHONPATH=src python3 scripts/verify_gbi_dcse_v3_scorecard.py   # 148 checks, 0 failures
```

The v3 verification suite does not trust the runner. It re-runs every adversarial
suite; hand-computes the §2.5 entropy table, the hyperellipsoid certificate and the
Fisher condition numbers; cross-validates the ported trigamma against an
independent implementation; re-derives the 3f+1 quorum-intersection arithmetic for
f = 1…5; builds an equivocating ledger pair and verifies both signatures with the
public key alone; **runs the enclave's residual check in isolation to prove the
spectral-moment half is load-bearing**; verifies rollback conformance by diffing the
store; and asserts the claim register's own integrity and section coverage.

| Artifact | Contents |
|---|---|
| `claim_register.json` / `.csv` | 99 claims with section, class, verdict and evidence |
| `appendix_a.json` | Self-check assertions and all 21 reproduced values |
| `gbi_section_claims.json` | Sections 2, 3, 4, 6.2, 8 |
| `protocol_inventory.json` | Seven protocol objects, ten policy components, pipeline, Table 2 |
| `ledger_suite.json` | Ledger faults, equivocation evidence, write-path guards |
| `systems_validation.json` | Attestation, consensus, rollback conformance |
| `enclave_and_certificate.json` | Sparse certificate, forgeries, resource budgets, §9.5 |
| `receipts.json` | Receipt coherence and replay |
| `infrastructure_domain.json` | Table 1 portability for sensitive infrastructure |
| `PROVENANCE.json`, `SHA256SUMS` | Scope declarations and checksums |

---

*GBI BoundaryBench is a research benchmark. It is not a clinical system, a medical
device, a certified terminology crosswalk, an autonomous EHR write-back service, or
an accredited system for handling sensitive infrastructure data. Synthetic data
only.*
