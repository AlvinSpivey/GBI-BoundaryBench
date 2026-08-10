# Contribution rubric

GBI BoundaryBench accepts contributions that improve reproducibility, task quality, verifier rigor, release hygiene, or documentation without weakening the benchmark boundary.

## Non-negotiable contribution rules

- Do not use real PHI/PII.
- Do not fabricate baseline scores, labels, citations, licenses, model IDs, costs, latency, API capabilities, or validation results.
- Do not call synthetic labels clinical truth.
- Do not add credentials, private endpoints, account/customer strategy, or confidential business material.
- Keep model execution and grading separate.
- Keep unsupported run cells as `NOT_RUN`.
- Preserve explicit license boundaries for software, data, documentation, and third-party material.

## Task contributions

A new task family or split must include:

- typed inputs and allowed outputs;
- deterministic oracle behavior;
- no-op and malformed-output tests;
- evidence references;
- failure slices;
- explicit abstention/action semantics;
- provenance and seed metadata;
- deterministic grader coverage.

## Data contributions

Data must be synthetic or explicitly licensed for redistribution. Include source URL or generator version, seed/configuration, transformation manifest, hashes, license/notice review, and confidentiality review.

Do not infer gold labels by diffing independently generated clean and messy files.

## Model-run contributions

Real model runs must include raw outputs, immutable metadata, exact model ID, provider/access mode, prompt/config hashes, seed, code/data commit, cost/latency when returned, and evidence availability. Output-only APIs must remain output-only.

## Review checklist

Before submitting:

```bash
python3 -m unittest discover -s tests -v
PYTHONPATH=src python3 scripts/validate_release.py
```

If you changed release contents:

```bash
PYTHONPATH=src python3 scripts/generate_checksums.py --out SHA256SUMS
PYTHONPATH=src python3 scripts/build_release.py --rc rc1
PYTHONPATH=src python3 scripts/validate_release.py --archive dist/gbi-boundarybench-0.1.0-rc1.tar.gz
```

## Review outcomes

Maintainers should reject or request changes for contributions that weaken fail-closed behavior, mix model and grader responsibilities, add uncleared material, hide `NOT_RUN` status, or make unsupported clinical or provider claims.
