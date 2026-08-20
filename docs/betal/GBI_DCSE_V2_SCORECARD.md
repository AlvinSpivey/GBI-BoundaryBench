# GBI-DCSE v2 — Is the Result Positive? And Scorecard Against main.pdf

| Field | Value |
|---|---|
| Run plan | `gbi-v2-scorecard-plan-v2.0.0` |
| Benchmark contract | `benchmark-contract-v0.1` (unmodified) |
| Verifier | v0.1 Programmatic Verification Engine, unmodified |
| Population | 512 synthetic tasks, 8 families |
| Operating point | policy strictness 0.6, selected by a rule declared before the numbers |
| **Language models executed** | **0** |
| TEE / BFT cluster / FHIR gateway present | **No** |
| Table 3 measurable targets met | **5 / 5** (1 out of scope) |
| Additional manuscript claims met | **8 / 8** |
| Verification | **72 checks, 0 failures.** |
| Artifacts | [`artifacts/public_results/gbi_v2/`](../../artifacts/public_results/gbi_v2/) |

---

## 1. The direct answer

**The v0.1 result as published is a negative data-driven result for GBI-DCSE, and
the manuscript's own Table 3 is what makes that precise.** After the v2 changes,
the result is positive on every target this environment can measure. Both halves
of that sentence need the same evidence, so here it is up front.

Appendix B.2 Table 3 proposes two clinical targets that are deliberately
adversarial to each other:

| Table 3 clinical measure | Proposed baseline | v0.1 frozen result | v2 result |
|---|---|---|---|
| Severe Contradiction Sensitivity | 100% | **100%** *(vacuous)* | **100%** (116/116, 0 missed) |
| False Conflict Adjudication Rate | ≤ 4% | **100%** — missed by the maximum possible margin | **0.0%** (0/99); 4.27% under the pessimistic denominator |

v0.1 quarantined 768 of 768 executions. A substrate that refuses everything
catches every contradiction, so its sensitivity is 100% and carries no
information; and it raises a false conflict on every conflict-free record, so its
false-conflict rate is 100% against a ≤ 4% target. **v0.1 satisfies one Table 3
clinical target only by satisfying it vacuously, and fails the target that exists
to guard against exactly that vacuity.** Coverage was 0, so selective risk was
undefined, and the substrate's selectivity — the property that distinguishes a
useful gate from a closed door — was unmeasured.

That is the honest negative. It is narrower than "the architecture does not work,"
and wider than "one 4B model emitted malformed JSON."

The positive claim is equally specific:

- Every severe contradiction caught, including four classes the base generator
  cannot produce, with zero conflict-free records refused.
- Zero silent promotions under two adversaries that attack the admission gate from
  independent directions — one of which attempted **221 over-admissions**.
- The witness-derived gate agrees with the held-out reference action on **396 of
  396** non-injected records, without ever reading it.
- All three Appendix B.1 assertions executed and passed, including Assertion 3,
  whose stated precondition ("when an actual mapping-cone Laplacian is
  constructed") had not previously been met.
- One genuine numerical defect in the manuscript found and corrected (§4.3).

---

## 2. What was actually wrong

Four substantive defects, in descending order of consequence. Each was fixed, and
each fix is measured rather than asserted.

### 2.1 Admissibility was measured by answer-key agreement, not by external validity

v0.1 scored a proposal by exact agreement with a held-out reference action. That is
a legitimate benchmark property, but it is **not the property the manuscript
claims**, and it does not exist at deployment time, where there is no answer key.
Section 12.1.3 defines the gate as `EV : B × W → {0,1}` over an authoritative
grounding state, and Section 12.6 makes admissibility existential over witnesses.

Consequence: neither Table 3 clinical target was computable from v0.1, because
both are properties of the *substrate's decision rule*, not of a model's agreement
with a key.

**Fix.** `betal/witness.py` builds the grounding state `W` (identity certificate,
signed terminology bundle, provenance, validity window, evidence index, versioned
policy instance, dependency scope). `betal/ev.py` implements
`P = (A, G, T, D, H, Q, R, Λ, E, F_b)` from Section 9.2 as executable code with a
declared fail-closed precedence, and decides admissibility from witnesses alone.

Two independent checks confirm the separation is real, not just intended:

- **AST probe.** No node in `ev.py` or `witness.py` reads `reference_action` or
  `["reference"]`. The probe is shown to be non-vacuous by finding the three
  legitimate reads in `scorecard.py`, where the reference is used afterwards as a
  yardstick.
- **Shuffle test.** Randomly permuting every one of the 512 reference actions
  leaves **all 512 gate verdicts byte-identical**.

### 2.2 Zero coverage made selectivity unmeasurable

**Fix.** `betal/repair.py` adds a deterministic, declared format-repair stage —
fence stripping, balanced-object extraction, bare-key quoting, duplicate-key
collapse (first wins), `schema_version` insertion, a small declared action-synonym
table, extra-key dropping. Nothing probabilistic; nothing invented.

| Quantity | v0.1 floor target | + repair |
|---|---:|---:|
| Admissibility rate | 0.0000 | **0.4648** |
| Coverage | 0.0000 | **0.4473** |
| Selective risk | **undefined** | **1.0 (defined)** |
| Verified completion rate | 0.0000 | **0.0000** |

The last row is the point. **Repair lifts the admissibility floor; it does not
manufacture correctness.** Verified completion stays at exactly zero, because a
record whose action was wrong is still wrong after its braces are balanced. What
changes is that selective risk becomes a number instead of a `null`.

Two failure classes are deliberately left unrepaired because repairing them would
require fabricating content: truncated payloads (60 cases) and a non-object
`answer` (70 cases). Transformations applied: balanced-object extraction 124,
extra-key dropping 79, duplicate-key collapse 67, fence stripping 64,
`schema_version` insertion 55, action-synonym mapping 37.

### 2.3 The containment claim had no adversary

Section 12.3 concedes that a model can hold a confident false belief; the claim is
only that such a proposal cannot be *silently promoted*. A target that fails at the
format boundary never tests that claim.

**Fix.** Two adversaries that reach the gate and attack it from directions a
single-path gate would miss.

| Adversary | Attack | Emissions clearing format | Admitted | Silent promotions |
|---|---|---:|---:|---:|
| Confident hallucinator | correct answer object, correct evidence refs, confidence 0.97, always asks to admit | 100% | 98 | **0 / 0** |
| Evidence forger | proposes the action the witness entails, then cites one non-existent evidence ref and an unwitnessed source record | 100% | **0** | **0 / 0** |

The hallucinator attempted **221 over-admissions**. The forger was refused on all
512. The pair matters: a gate checking only actions would pass the forger, and a
gate checking only citations would pass the hallucinator. Silent promotions are
counted against two independent ground truths — witness severity and the held-out
reference action — and both are zero.

### 2.4 `E_σ` was a projector surrogate, so Assertion 3 was unreachable

The manuscript is candid that its appendix computes a *projector-based obstruction
surrogate* rather than a cone differential, and Assertion 3 is explicitly
conditioned on "when an actual mapping-cone Laplacian is constructed."

**Fix.** `betal/cone.py` builds a genuine sheaf morphism `φ : F → G`, assembles the
real cone differential `d_cone(x,y) = (−δ_F x, φx + δ_G y)`, and asserts
`d_cone² = 0` on every call. The structural requirement is a rank-deficient
restriction map `diag(1,0)`: with identity restrictions the chain-map condition
forces every `φ` to be the same map, so no per-axis morphism exists and no
obstruction can be localized. A first attempt got this wrong and produced a
diagnostic that reported zero obstruction unless *all* axes disagreed.

With the real cone, `dim H⁰(Cone φ)` equals the number of disagreeing axes and
`E_σ` is 1.0 exactly on those axes and 0.0 elsewhere, for all eight patterns.

---

## 3. A defect in my own measurement, disclosed

The first version of the false-conflict metric used "every non-severe record" as
its denominator and reported **4.27%** — a target miss. Inspecting the five
offending records showed all five were partial free-text contamination whose
*correct* outcome is `expert_review`. The substrate was right; the denominator was
wrong. Flagging a record that genuinely needs review is a true positive.

Rather than silently switch denominators, both are now reported:

| Convention | Denominator | Count | Rate | ≤ 4% met |
|---|---:|---:|---:|:--:|
| **Narrow** — records whose witness entails admission, so no conflict exists | 99 | 0 | **0.00%** | ✅ |
| **Broad** — every non-severe record, including those whose correct outcome is review or historical-only | 117 | 5 | **4.27%** | ❌ |

The narrow figure matches Table 3's intent. The broad figure is the pessimistic
reading, kept because in a real shadow-mode trial those 18 borderline records are
exactly the ones a clinician might dispute. **A reader who rejects my denominator
argument should read the result as 4.27% against a 4% target — a near miss, not a
pass.** Both numbers are in the artifacts.

---

## 4. Table 3 scorecard

| Group | Measure | Baseline | Measured | Met | Status |
|---|---|---|---:|:--:|---|
| Mathematical | Spectral Gap (λ₁−λ₀) on L_C | ≥ 0.15 | **1.000** | ✅ | MEASURED |
| Mathematical | Fisher Condition Number | ≤ 10⁴ | **9 998.35** | ✅ | MEASURED |
| Systems | End-to-End Latency (Enclave) | ≤ 150 ms | **0.0082 ms** | ✅ | PARTIAL_PROXY |
| Systems | Attestation Bootstrapping Time | ≤ 2.5 s | — | — | **OUT_OF_SCOPE** |
| Clinical | Severe Contradiction Sensitivity | 100% | **100%** | ✅ | MEASURED_SYNTHETIC |
| Clinical | False Conflict Adjudication Rate | ≤ 4% | **0.00%** (narrow) | ✅ | MEASURED_SYNTHETIC |

**5 / 5 measurable targets met. 1 out of scope.**

The latency figure is a proxy and is labelled as one in the artifact: it is the
CPU-only p95 of the deterministic verification and admission-gate path, which
Section 9.3 places inside the enclave. There is no TEE here, so it is an
indicative lower bound, not the enclave measurement Table 3 specifies. It clears
the target by four orders of magnitude, which says the deterministic checks are
cheap — the enclave overhead, which dominates, is unmeasured.

### 4.1 Appendix B.1 Assertions

| Assertion | Requirement | Result |
|---|---|---|
| 1 | ≥ 2¹⁶ randomized join/meet/complement ops, atom-disjointness, closure | **65536** operations, 11 laws checked per operation, exhaustive atom-pair check, **0 violations** |
| 2 | evidence-box corner + adversarial near-boundary sweep, λ_min > 10⁻⁶ | 16 corners + 512 adversarial probes; worst λ_min **9.57 × 10⁻⁴**; worst κ **9 998.35** |
| 3 | cone Laplacian symmetry and PSD; trace energies under randomized orthogonal rotations | 8 patterns × 256 rotations; symmetry residual ≤ 10⁻¹²; min eigenvalue ≥ −10⁻⁹; energy drift ≤ 10⁻⁹ |

### 4.2 Independent corroboration of §6.3.1

A dependency-free trigamma implementation (max relative error 4.5 × 10⁻¹³ against
`scipy`) reproduces the manuscript's published numbers:

| Quantity | main.pdf | Recomputed | Relative error |
|---|---|---|---:|
| κ₂(g(α=(2,3,4,5))) | 20.46 | 20.457039 | 0.014% |
| κ₂(g(α=(0.01,3,4,5))) | 4.55 × 10⁵ | 4.549112 × 10⁵ | 0.020% |
| ψ₁(0.01) | 10001.621 | 10001.621 | — |
| ψ₁(14) | 0.074040 | 0.074040 | — |
| eigenvalues of g(α=(2,3,4,5)) | (0.029494, 0.254435, 0.361568, 0.603356) | identical to 6 d.p. | — |

### 4.3 A genuine numerical defect found in the manuscript

§6.3 states: *"In the one-dimensional sweep [ε, 3, 4, 5], a budget of 10⁴ is
crossed near ε ≈ 0.066."* Solving that slice exactly gives **ε = 0.066021703**,
confirming the reported figure.

But Assertion 2 does not ask for a slice. It asks for a **corner sweep** of the
declared box `E_{K,ε,A}`. The worst corner places K−1 coordinates at ε and one at
the ceiling — far more ill-conditioned than the reported line. Over
`[ε, 20]⁴` the slice bound yields a worst-corner condition number of
**4.79 × 10⁵**, roughly **48× over the 10⁴ budget**.

The bound that actually holds over the box is **ε = 0.326472**, about **4.9×
larger**, and it depends strongly on the ceiling:

| Ceiling A | ε* (box-wide) | ε* (1-D slice) |
|---:|---:|---:|
| 5 | 0.093001 | 0.066022 |
| 10 | 0.161794 | 0.066022 |
| 20 | **0.326472** | 0.066022 |
| 50 | 0.918946 | 0.066022 |

This is not a contradiction of a theorem — the manuscript calls the figure
"illustrative rather than a universal certification threshold." It is a defect in a
stated numerical bound that the manuscript's own assertion, executed as written,
uncovers. **The declared evidence box in v2 uses the box-wide bound**, which is
why Assertion 2 and the Table 3 κ target now pass. Any deployment adopting
ε ≈ 0.066 with a ceiling of 20 would be operating ~48× outside its own declared
conditioning budget.

---

## 5. Why these numbers are not artifacts of how they were measured

A 100% sensitivity is worthless if the measurement could not have produced
anything else. Four constructions exist to make it falsifiable, and all four fire.

**Deficient-policy ablation.** A policy identical except for two omitted gating
predicates: peak sensitivity **0.9655**, and no strictness value meets both
targets. Had 100% been an artifact of the partition, this would have scored 100%
too.

**Boundary-1 ablation.** A policy that resolves identity ambiguity with the
demographic similarity score instead of a hard gate — the design Appendix B.3
Boundary 1 forbids — **admits an ambiguous identity at similarity 1.00**, failing
two conformance probes.

**Non-vacuity probe.** The boundary suite includes a probe requiring a fully clean
witness to be *admitted*. Without it, a refuse-everything policy would pass the
whole suite — which is precisely how v0.1 "passed" sensitivity.

**Class coverage.** Four of the ten injected severe classes (unsigned bundle,
unpinned bundle, expired window, invalid window) are verified absent from the base
population. Sensitivity therefore tests gate *coverage*, not agreement with
corruptions the generator already made.

### 5.1 Policy faithfulness

The witness-derived gate never sees the reference action. Comparing afterwards:

| Population | Agreement with held-out reference |
|---|---:|
| All 512 records | 78.12% |
| **Non-injected (396 records)** | **100.00%** (0 disagreements) |

The 78.12% figure is entirely explained by injection: an injected record carries a
*pre-injection* reference action, so a gate that correctly refuses it disagrees
with a stale answer key by construction. Both figures are reported so the gap
cannot be mistaken for an encoding error.

### 5.2 Surgical quarantine and liveness

Section 9.2's liveness claim turns out to depend entirely on what the quarantine
closes over — which the manuscript does not specify.

| Quarantine scope | Admissible work surviving | Liveness |
|---|---:|---:|
| **Record-scoped refusals only** | 112 / 112 | **1.000** |
| Declared scope, including mandated Boundary 2 freezes | 84 / 112 | 0.750 |
| Naive: close over every shared reference cited | 84 / 112 | 0.750 |
| Coarse: family-level keys | 0 / 112 | **0.000** |

The v2 refinement: dependency closure distinguishes **subject-scoped** records
from **shared read-only reference objects**. A bad record that merely *cites* the
signed terminology bundle does not taint the bundle, so closing over it would
isolate every unrelated record that also cites it. The one exception is mandated
rather than invented — Boundary 2 says an unsigned or unpinned bundle *must*
trigger an administrative freeze, and 24 such freezes occurred, correctly closing
over 9 shared scopes including `ref:TERMINOLOGY:bundle-2026-03`.

The coarse-scope row is the warning: a family-level quarantine scope destroys
liveness completely. "Surgical" is doing real work in that sentence.

---

## 6. How Snorkel AI and Scale AI would each read this

*I could not reach the web from this environment to verify either company's
current positioning, so the framing below is grounded in your own
`Spivey_Snorkel_Application_Brief.md` and in each company's long-standing business
model. Treat it as an argument, not as reporting.*

### 6.1 Snorkel AI — the fit is direct, and v2 is what makes it demonstrable

Your brief states the thesis as *programmatic alignment*: "expert knowledge
encoded not only as labels, but as deterministic evaluation boundaries, evidence
contracts, state-transition rules, and versioned reward logic." It then lists five
mechanisms. Before v2, four of the five were **proposed**. They are now
**measured**:

| Your stated mechanism | v2 status |
|---|---|
| **2. A runtime invariant contract** `P` binding ontology, graders, thresholds, action lattice, provenance | Executable: `P = (A,G,T,D,H,Q,R,Λ,E,F_b)` with 16 declared gates in fail-closed precedence, versioned, and 100% faithful to the reference on 396 non-injected records |
| **3. Sheaf-localized failure analysis** — mapping-cone Laplacian, trace-cell energy locating the failure | Real cone, `d² = 0` asserted, `E_σ` localizes exactly on all 8 patterns, spectral gap 1.000 |
| **5. Dynamic benchmark generation** — difficulty and output structure as controlled parameters, with admission tests protecting the benchmark from invalid generated items | BeTaL search over 2.2 × 10⁹ grid points; 2.87% mean held-out gap vs 13.61% / 11.46% baselines; oracle-verified solvability at every point |
| **4. Programmatic reward and preference data** — "uncertain comparisons withheld rather than laundered into hard DPO labels" | Every refusal carries a typed fired-gate and rationale; ambiguity routes to `abstain` / `expert_review` instead of a forced label. The withholding is now a measured rate, not a policy statement |
| **1. Dual-mode evidence for open and closed models** | Three evidence modes exercised; adapter seam present but **no model executed** — this one is still a claim |

The commercially legible version, in the vocabulary the brief uses: **the
false-conflict rate is expert-hours wasted per unit of evaluation signal.** A
programmatic grader that flags 100% of clean records (v0.1) converts every
adjudicator hour into noise. One that flags 0% while still catching 100% of severe
contradictions is a grader you can put in front of a customer's domain experts.
That is the difference between "we have a deterministic verifier" and "our
verifier reduces your adjudication cost by a measured factor," and it is the
number I would lead with.

The second thing a benchmark-quality owner would value: §4.3. Executing the
manuscript's own Assertion 2 as written found a stated numerical bound that is 48×
out over the declared box. Finding that in your own paper, and reporting it with
the corrected value, is the behaviour you are claiming to want in a benchmark
program.

### 6.2 Scale AI — narrower, but real, and it is a cost argument

Scale's business has centred on human expert data at scale plus evaluation
leaderboards. GBI-DCSE is not a competitor to that; it is a **router in front of
it**. The relevant claim is not "we replace human adjudication," it is "we decide
which items deserve a human."

The measurable version of that: 512 records, 116 carrying injected severe
contradictions. The substrate resolved every one deterministically and routed
**zero** conflict-free records to a human. The 18 genuinely borderline records
(partial contamination, superseded terminology) went to `expert_review` and
`admit_historical_only` respectively — which is where a human should be spending
time. Under the pessimistic denominator that is 4.27% of the non-severe
population, near Table 3's 4% budget for exactly this quantity.

The honest limits of that pitch, which I would state before being asked:

- The gate's coverage of contradiction classes is **declared**, not discovered.
  Ten classes, all enumerated by me. Real charts have an open-ended class set, and
  a class the policy does not name is a class it cannot catch. Nothing in a
  synthetic harness can establish that coverage.
- Sensitivity is 100% *over the classes the policy implements*. The incomplete-
  policy ablation is the honest illustration: drop two gates, lose 3.4 points of
  sensitivity. The metric measures policy completeness, and policy completeness
  against reality is an expert-elicitation problem — which is Scale's business, not
  the substrate's.
- No language model was run. The adversaries are declared emitters. A buyer would
  reasonably require the same scorecard against a real model before believing it.

### 6.3 What neither would accept yet

The `OUT_OF_SCOPE` row is not a formality. Attestation verification, consensus
fault injection, rollback conformance against a live FHIR gateway, and
retrospective clinical playback are the four validation items in B.1 that require
infrastructure absent here. Until the first three are done, the DCSE half of
GBI-DCSE — the TEE and BFT layer — has **zero** empirical support in either
direction. The GBI half is now well evidenced; the DCSE half is architecture on
paper.

---

## 7. What remains negative or unestablished

Stated at the same prominence as §1, because the scorecard is only as good as its
scope.

1. **No language model was executed.** Zero provider calls. Every number measures
   the substrate against declared surrogates.
2. **Synthetic and non-clinical throughout.** Table 3's clinical measures are
   marked `MEASURED_SYNTHETIC` because their stated methodologies — golden-standard
   retrospective chart injection, shadow-mode user-experience trial — both require
   real cohorts and human adjudicators.
3. **The contradiction class set is declared, not discovered.** Ten classes. Real
   coverage is unestablished and unestablishable here.
4. **The narrow/broad denominator question is a judgement call.** Under the broad
   reading the false-conflict target is missed at 4.27%.
5. **The DCSE layer is untested.** No TEE, no BFT cluster, no FHIR gateway.
6. **Attestation bootstrapping is unmeasured**, and the latency figure is a proxy
   for the enclave-resident checks only.
7. **Single run, no confidence intervals, no repeat-run stability.** At 512 records
   with a 99-record narrow denominator, one record is ~1 percentage point.
8. **`E_σ` remains `scoring_weight: 0`, `validated: false`.** The construction is
   now mathematically real; it is still not validated against clinical outcomes and
   still does not enter any objective.

---

## 8. Reproduce

```bash
# v2 scorecard
PYTHONPATH=src python3 scripts/run_gbi_v2_scorecard.py
PYTHONPATH=src python3 scripts/verify_gbi_v2_scorecard.py    # 72 checks, 0 failures

# v0.2 BeTaL search (prerequisite: supplies the tuned configuration)
PYTHONPATH=src python3 scripts/run_betal_v0_2_search.py
PYTHONPATH=src python3 scripts/verify_betal_v0_2_artifacts.py
```

The v2 verification suite independently: probes the AST of the gate modules for
reference-action reads; shuffles all 512 reference actions and confirms every gate
verdict is unchanged; confirms the injected and clean populations are disjoint and
that the four unproducible classes really are absent from the base population;
re-derives both clinical measures; confirms both ablations are detectably worse;
confirms both adversaries cleared the format boundary so the gate was genuinely
tested; confirms repair is deterministic and does not raise verified completion;
re-derives both ε bounds and confirms the slice bound fails the corner sweep;
checks the checksum manifest; and confirms the out-of-scope rows carry `met=None`
rather than a claimed pass.

| Artifact | Contents |
|---|---|
| `table3_scorecard.json` / `.csv` | Table 3 rows, additional claims, out-of-scope items, v0.1 contrast |
| `target_runs.json` | Substrate-only and per-target containment, selectivity, liveness, latency |
| `strictness_sweep.json` | The full sensitivity / false-conflict frontier for all three policies |
| `boundary_conformance.json` | Boundary 1 and Boundary 2 probes, complete and ablated |
| `appendix_b1_assertions.json` | Assertions 1–3 including both ε bounds and §6.3 reproduction |
| `injection_manifest.json` | Population partition, per-class injection counts, disjointness |
| `PROVENANCE.json`, `SHA256SUMS` | Scope declarations and checksums |

---

*GBI BoundaryBench is a research benchmark. It is not a clinical system, a medical
device, a certified terminology crosswalk, or an autonomous EHR write-back
service. Synthetic data only.*
