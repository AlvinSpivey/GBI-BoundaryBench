# Public reproducibility guide

This public showcase is not the full private benchmark checkout. It is designed for architecture review, application review, and inspection of public aggregate results without exposing held-out answer keys.

## Publicly checkable artifacts

The public aggregate result files are under:

```text
artifacts/public_results/v0_1/
```

Validate the published result files with:

```bash
(cd artifacts/public_results/v0_1 && shasum -a 256 -c PUBLIC_ARTIFACT_SHA256SUMS)
```

The public result files contain aggregate metrics, per-mode metrics, status distributions, task-family/slice metrics, risk-coverage plot data, and public provenance. They do not contain raw held-out model responses or trusted held-out references.

## Private research-chain identifiers

The frozen v0.1 empirical result is governed by:

```text
benchmark-contract-v0.1
        ↓
empirical-run-plan-v0.1.8
        ↓
empirical-raw-v0.1
        ↓
empirical-scored-v0.1
```

Key identifiers:

- benchmark contract commit: `4e66210c1feb3bfff0f3e7e1fe3c4a3f899d77a3`;
- runner commit: `5b717c9fff00c816946adf095a271cf05cc5b5f1`;
- raw-freeze commit: `7ed87ba68b715f60bdf88a8015aa2659313b5876`;
- scored commit: `3bcb9dad9af04c1cfedb5b6f74aa40e36d9a0e13`;
- frozen benchmark SHA256: `ae0f875ed40316a99b8fbddd1ee248296ace94431f0b3f1f05437ea906967c78`;
- raw archive SHA256: `155c28cb104bc0c0923c16e3f2098a59707aadebc31596304afe073b1250eaf0`;
- scored checksum-manifest SHA256: `4b04383b9874410ce7353623f697a10c7b46fbdcecfa7271f2b849c78720182b`.

## Withheld materials

The full benchmark execution/scoring package includes hidden held-out references, oracle outputs, trusted verifier packages, raw held-out model responses, private audit logs, and private Git history. Those materials are intentionally not published here so future blind held-out evaluation remains meaningful.

## Result summary

The public aggregate files record one frozen v0.1 run of `Qwen/Qwen3-4B-Instruct-2507` at revision `cdbee75f17c01a7cc42f958dc650907174af0554`: 768 completed canonical held-out executions, zero accepted outputs, 369 safe parse rejects, 399 safe schema rejects, 768 quarantines, coverage 0.0, invalid-output rate 1.0, and selective risk undefined at zero coverage.
