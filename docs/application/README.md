# BoundaryBench v0.1 application package

This directory contains the application-facing summary for GBI BoundaryBench v0.1.

Start here:

- Project summary: [`GBI_BOUNDARYBENCH_V0_1_SUMMARY.md`](GBI_BOUNDARYBENCH_V0_1_SUMMARY.md)
- v0.2/v2/v3 summary: [`GBI_V0_2_V2_V3_SUMMARY.md`](GBI_V0_2_V2_V3_SUMMARY.md)
- Enterprise portability: [`ENTERPRISE_PORTABILITY.md`](ENTERPRISE_PORTABILITY.md)
- Application blurbs: [`APPLICATION_BLURBS.md`](APPLICATION_BLURBS.md)
- Reproducibility summary: [`REPRODUCIBILITY.md`](REPRODUCIBILITY.md)

Figures:

- Architecture: [`figures/boundarybench_architecture.svg`](figures/boundarybench_architecture.svg)
- Empirical failure flow: [`figures/qwen_v0_1_failure_flow.svg`](figures/qwen_v0_1_failure_flow.svg)

Sources:

- Deterministic figure generator: [`figure_sources/make_application_figures.py`](figure_sources/make_application_figures.py)
- Public aggregate scored artifacts: [`../../artifacts/public_results/v0_1/`](../../artifacts/public_results/v0_1/)
- Benchmark card: [`../benchmark_card.md`](../benchmark_card.md)
- Programmatic verifier: [`../programmatic_verification_engine.md`](../programmatic_verification_engine.md)

The application interpretation is narrow: v0.1 evaluates one 4B open-weight model family under a frozen held-out protocol. Later v0.2/v2/v3 artifacts add deterministic benchmark-design and systems-verification evidence. None of these stages claim clinical validation, production readiness, general frontier-model failure, or general ineffectiveness of evidence access.
