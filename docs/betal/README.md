# BeTaL-GBI — autonomous benchmark design over the admission boundary

This directory applies [BeTaL](https://arxiv.org/html/2510.25039v1) (Benchmark
Tuning with LLM-in-the-loop) to GBI BoundaryBench: it makes the legacy-EHR task
environment **parameterized**, so a designer can tune it toward a target
verified-completion rate instead of shipping a fixed task set.

**Language models executed: 0.** The v0.2 artifacts measure the search harness
against declared, transparent target surrogates. No provider was contacted, no
held-out reference was read, and the v0.1 verifier was not modified.

## Start here

| Document | What it is |
|---|---|
| [`GBI_DCSE_V3_FULL_EVALUATION.md`](GBI_DCSE_V3_FULL_EVALUATION.md) | **Every main.pdf claim, scored.** Includes the DCSE half and the sensitive-infrastructure assessment |
| [`GBI_DCSE_V2_SCORECARD.md`](GBI_DCSE_V2_SCORECARD.md) | Is the result positive? Scorecard against main.pdf Table 3 and Appendix B.1 |
| [`BETAL_V0_2_SEARCH_REPORT.md`](BETAL_V0_2_SEARCH_REPORT.md) | Performance report: results, limitations, reproduction |
| [`BETAL_GBI_DESIGN_SPEC.md`](BETAL_GBI_DESIGN_SPEC.md) | Full specification: designer prompt, parameter space, algorithm, errata |
| [`figures/betal_gbi_loop.svg`](figures/betal_gbi_loop.svg) | The loop and the admissibility gate |
| [`figures/betal_designer_gap_comparison.svg`](figures/betal_designer_gap_comparison.svg) | Held-out gap by level and search strategy |
| [`figures/betal_difficulty_response.svg`](figures/betal_difficulty_response.svg) | Difficulty response of the declared parameter space |
| [`figures/gbi_dcse_v3_claim_coverage.svg`](figures/gbi_dcse_v3_claim_coverage.svg) | All 99 main.pdf claims by section: met, errata, out of scope |
| [`figures/gbi_v2_clinical_frontier.svg`](figures/gbi_v2_clinical_frontier.svg) | Table 3 clinical frontier, with ablations and the v0.1 baseline |
| [`../../artifacts/public_results/gbi_dcse_v3/`](../../artifacts/public_results/gbi_dcse_v3/) | v3 claim register and DCSE artifacts |
| [`../../artifacts/public_results/gbi_v2/`](../../artifacts/public_results/gbi_v2/) | v2 scorecard artifacts |
| [`../../artifacts/public_results/v0_2/`](../../artifacts/public_results/v0_2/) | Machine-readable artifacts and checksums |

## The two findings

**1. The frozen v0.1 baseline makes BeTaL's objective undefined.** Every one of the
768 v0.1 executions failed at the parse or schema gate, so `rho_hat = 0` for every
configuration and the gap `|rho_hat - rho| = rho` is constant across the whole
parameter space — zero search signal. Demonstrated mechanically: across five probe
configurations and all three evidence modes, the admissibility rate takes exactly
one value, `0.0`.

The fix is to decompose the rate and gate the search:

```
rho_hat_adm  = admitted / task_count            # did emissions enter the substrate?
rho_hat_task = verified_completion / admitted    # the quantity BeTaL tunes
```

When `rho_hat_adm` is pinned near zero the gap is reported as **undefined**, not
large, and the run halts with `degenerate_gap_admissibility_floor` having selected
nothing. The admissibility floor is a prerequisite to repair, not a difficulty dial
to tune.

**2. With a schema-compliant target, the search works and feedback is what makes it
work.** Mean held-out gap **2.87%** for the feedback designer against **13.61%**
(RS+PPR) and **11.46%** (Best-of-N); a **4.00×** and **4.54×** advantage on mean
search gap. BeTaL reports 5.3%–13.2% eval gaps and a 2–4× baseline advantage on its
own environments, so this environment behaves like a BeTaL environment.

## v2: scoring the substrate against the manuscript

v0.2 answered "can the benchmark be tuned?". v2 answers "does the substrate meet
what main.pdf claims?" — and the manuscript's own Appendix B.2 Table 3 is what
makes the v0.1 answer precise:

| Table 3 clinical measure | Baseline | v0.1 frozen | v2 |
|---|---|---|---|
| Severe Contradiction Sensitivity | 100% | 100% *(vacuous — everything was refused)* | **100%** (116/116) |
| False Conflict Adjudication Rate | ≤ 4% | **100%** — maximum possible miss | **0.0%** (0/99) |

v0.1 satisfies one clinical target only vacuously and fails the target that guards
against that vacuity. v2 meets **5/5** measurable Table 3 targets (1 needs a TEE
and is marked out of scope) and **8/8** additional manuscript claims, including all
three Appendix B.1 assertions.

Four substantive changes made that possible, and one defect was found in the
manuscript along the way:

- **A reference-free admission gate.** `EV(b, w)` over witness bundles, with
  `P = (A,G,T,D,H,Q,R,Λ,E,F_b)` executable. Verified never to read the reference
  action: shuffling all 512 reference actions leaves every gate verdict unchanged.
- **Format repair.** Admissibility 0 → 0.4648, so selective risk is finally
  defined. Verified completion stays at 0: repair does not manufacture correctness.
- **Two adversaries.** A confident hallucinator (221 attempted over-admissions) and
  an evidence forger. Zero silent promotions against both, by two ground truths.
- **A real mapping cone.** `d² = 0` asserted, `E_σ` localizes exactly, which finally
  satisfies Assertion 3's stated precondition.
- **Errata.** §6.3's evidence-box bound ε ≈ 0.066 holds only along the 1-D slice it
  swept. Over the declared box the worst corner is 48× over the κ ≤ 10⁴ budget; the
  bound that actually holds is **ε = 0.326472**, and it depends on the ceiling.

## v3: the DCSE half, and every remaining claim

At the end of v2 the DCSE half of GBI-DCSE had **zero empirical support in either
direction** — the GBI half was well evidenced, the DCSE half was architecture on
paper. v3 closes that, and enumerates every claim in main.pdf so "nothing left
unmet" is auditable rather than asserted.

**99 claims. 95 of 96 testable claims met. 3 out of scope. 1 erratum.**

| DCSE claim | Result |
|---|---|
| Seven §9.1 protocol objects (B, V, Θ, F, W, L, P) | all implemented and exercised |
| Ten §9.2 policy components (A, G, T, D, H, Q, R, Λ, E, F_b) | all present |
| Ledger L: 7 fault classes injected | all detected, each classified as itself |
| Equivocation evidence | verifiable with the **public key alone** (real Ed25519) |
| Attestation: 7 injection classes | all fail closed, each caught by its intended check |
| Consensus: 62 configurations, exhaustive | safety holds at ≤ f; **violable at f+1, so the bound is tight** |
| Below 3f+1 replicas | halts authoritative writes |
| Enclave sparse certificate: 9 forgery classes | all rejected; **14,741× fewer flops** than the dense path |
| Rollback conformance | nothing commits; store byte-identical; unrelated records untouched |
| Atomicity **and** liveness | both hold simultaneously |
| Receipts | 14/14 replay to the original verdict; tampering detected |
| §9.5 zero-knowledge prover | **out of scope** — precondition met, proof system is future work |

The load-bearing finding: the enclave certificate's **spectral-moment half is not
decorative**. An adversary who drops a genuine kernel direction hides real
inconsistency, and the residual check alone accepts it with a worst residual of
2.28 × 10⁻¹⁵. Only the moment identities catch it.

**Sensitive infrastructure (Table 1 portability).** A second domain instantiation
reused **8 domain-neutral modules verbatim** and required **4** domain-specific
objects and **zero** architectural changes: 265/265 severe contradictions caught,
0/175 false conflicts.

**The erratum.** §6.3's evidence-box bound ε ≈ 0.066 holds only on the
one-dimensional slice it swept. Over the declared box the worst corner is ~48× over
the κ ≤ 10⁴ budget; the bound that holds is **ε = 0.326472**, ceiling-dependent.

## Reproduce

```bash
# v0.2 BeTaL search
PYTHONPATH=src python3 scripts/run_betal_v0_2_search.py          # ~11s, CPU only, no network
PYTHONPATH=src python3 scripts/verify_betal_v0_2_artifacts.py    # 319 checks, 0 failures

# v2 scorecard against main.pdf
PYTHONPATH=src python3 scripts/run_gbi_v2_scorecard.py
PYTHONPATH=src python3 scripts/verify_gbi_v2_scorecard.py        # 72 checks, 0 failures

# v3 full evaluation: DCSE layer plus every remaining claim
PYTHONPATH=src python3 scripts/run_gbi_dcse_v3_scorecard.py
PYTHONPATH=src python3 scripts/verify_gbi_dcse_v3_scorecard.py   # 148 checks, 0 failures

# figures
python3 docs/betal/figure_sources/make_betal_figures.py
python3 docs/betal/figure_sources/make_gbi_v2_figures.py
python3 docs/betal/figure_sources/make_gbi_dcse_v3_figures.py
```

The verification script does not trust the run script: it re-validates every
generated task against the repository schema, re-derives every reported number from
the raw per-iteration records, re-checks the mapping-cone construction across all
agreement patterns, fuzzes domain projection, confirms the checksum manifest, and
asserts that the documents quote the artifacts correctly.

## What is new in code

```text
src/boundarybench/betal/space.py       declared parameter space V, total domain projection
src/boundarybench/betal/simulator.py   deterministic instantiation across the 8 task families
src/boundarybench/betal/targets.py     declared target surrogates (boundary floor, emitter, oracle)
src/boundarybench/betal/metrics.py     rho decomposition, delegates grading to the v0.1 PVE
src/boundarybench/betal/designer.py    designer prompt contract, LLM seam, model-free controls
src/boundarybench/betal/loop.py        BeTaL Algorithm 1 + admissibility gate, transfer, monotonicity
src/boundarybench/betal/cone.py        genuine mapping-cone E_sigma (zero scoring weight)

src/boundarybench/betal/witness.py     authoritative grounding state W (witness bundles)
src/boundarybench/betal/ev.py          EV(b,w) + executable policy contract P, with ablations
src/boundarybench/betal/injection.py   severe-contradiction chart injection (Table 3 methodology)
src/boundarybench/betal/repair.py      deterministic format repair, lifts the admissibility floor
src/boundarybench/betal/adversaries.py confident hallucinator, evidence forger
src/boundarybench/betal/assertions.py  Appendix B.1 Assertions 1-3 as an executable suite
src/boundarybench/betal/scorecard.py   Table 3 measures, liveness, selectivity, latency

src/boundarybench/gbi/appendix_a.py    Python port of the Appendix A Julia reference
src/boundarybench/gbi/claims.py        Sections 2, 3, 4, 6.2, 8 executable claim tests
src/boundarybench/gbi/register.py      the main.pdf claim register with integrity guards
src/boundarybench/dcse/crypto.py       Ed25519 signing and digests
src/boundarybench/dcse/ledger.py       protocol object L, non-equivocation, write-path guard
src/boundarybench/dcse/attestation.py  quote verifier and injection suite
src/boundarybench/dcse/consensus.py    exhaustive 3f+1 quorum analysis
src/boundarybench/dcse/enclave.py      sparse certificate, forgery suite, resource budgets
src/boundarybench/dcse/transaction.py  atomic bundle assembler and gateway
src/boundarybench/dcse/receipts.py     receipt chain, coherence and replay
src/boundarybench/dcse/cone_certificate.py  VerifyConeCertificate as a finite predicate
src/boundarybench/dcse/infrastructure.py    Table 1 second domain instantiation
src/boundarybench/dcse/protocol.py     protocol-object and structural-claim inventories
```

The BeTaL layer never re-implements a verification criterion. All grading is
delegated to the unmodified v0.1 Programmatic Verification Engine.

---

## Suggested addition to the repository README

Paste after the *Headline empirical result* section:

```markdown
### v0.2: autonomous benchmark design (BeTaL-GBI)

The v0.1 result says the admission boundary was never crossed. It does not say how
hard the tasks were, because nothing reached the judgment substrate. `docs/betal/`
makes the environment parameterized so difficulty becomes a tunable quantity, and
records why the v0.1 baseline cannot be tuned:

- The BeTaL gap `|rho_hat - rho|` is **constant across the entire parameter space**
  when every emission fails at parse or schema. An admissibility gate reports it as
  undefined rather than large, and selects nothing.
- With a schema-compliant target surrogate the search reaches a **2.87%** mean
  held-out gap against **13.61%** and **11.46%** for BeTaL's published baselines.
- No language model was executed for these artifacts.

See [`README.md`](README.md).
```
