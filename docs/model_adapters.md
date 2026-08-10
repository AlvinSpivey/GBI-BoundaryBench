# Model adapter API

The adapter layer defines provider-neutral request/response contracts for model access. It does not grade model outputs and does not assume that logits or token log probabilities exist.

Implemented package:

- `src/boundarybench/adapters/`

Machine-readable schemas:

- `schemas/model_request.schema.json`
- `schemas/model_provenance.schema.json`
- `schemas/model_response.schema.json`

## Access modes

| Mode | Implementation | Evidence policy |
|---|---|---|
| `open_weight_full_category` | `CallableOpenWeightFullCategoryAdapter`, `OfflineOpenWeightFullCategoryAdapter` | Records full action/category evidence only when the runtime callable supplies a score for every allowed action. |
| `token_top_k` | `CallableTokenTopKAdapter`, `OfflineTokenTopKAdapter` | Records visible top-k token mass and missing tail mass. It does not renormalize visible top-k tokens as though the tail were zero. |
| `output_only` | `CallableOutputOnlyAdapter`, `OfflineOutputOnlyAdapter` | Records output text only and explicitly marks category/logprob evidence as unobserved. |
| `local_surrogate_probe` | `LocalSurrogateProbeAdapter` | Trains only on supplied observable feature/label examples and reports held-out fidelity, calibration, coverage, and invalidation rules. It is not hidden-state reconstruction. |

The callable adapters are the integration seam for real local models, SDK calls, or HTTP clients. They do not read credentials directly. Provider-specific code should pass non-secret configuration into `AdapterConfig.extra` and keep credential values in the environment.

## Provenance

Every `ModelResponse` records:

- provider and exact model ID supplied to the adapter;
- access mode;
- adapter class and adapter API version;
- UTC access time;
- prompt SHA-256;
- request/config SHA-256;
- seed;
- current code commit when available;
- runtime metadata;
- retry policy and attempt count;
- latency in milliseconds;
- usage, cost, and external request ID when actually returned by a runtime;
- whether the response is a mock;
- observed evidence flags for full-category, token-top-k, and output text.

No credential values are recorded.

## Environment configuration

`.env.example` contains placeholders only. Copy it to `.env` for local experiments and keep `.env` untracked.

Real provider runs must not be reported unless raw outputs and provenance artifacts exist. Any unavailable provider/model/cost/latency result must remain `NOT_RUN`.

## Retry policy

`RetryPolicy` supports bounded retries for transient adapter failures. Non-transient validation failures should be returned as structured adapter errors, not silently retried into success.

## Offline mocks

Offline mocks are available for tests and smoke checks:

```bash
PYTHONPATH=src python3 scripts/run_adapter_offline_smoke.py
```

These responses are marked `is_mock: true` and `execution_status: mock_completed`. They are not benchmark model runs and should not be included in model result tables.

## Local surrogate probe

`LocalSurrogateProbeAdapter.fit(...)` requires explicit train and validation examples. Its report includes:

- train count;
- validation count;
- held-out fidelity when validation examples are covered;
- Brier score when validation examples are covered;
- expected calibration error when validation examples are covered;
- coverage;
- invalidation rules.

Out-of-domain surrogate requests return an abstain action when available and include a `surrogate_out_of_domain:*` error.
