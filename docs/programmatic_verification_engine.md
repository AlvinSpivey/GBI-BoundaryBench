# Programmatic Verification Engine

The Programmatic Verification Engine (PVE) is the deterministic grading boundary for BoundaryBench. It consumes immutable task artifacts and candidate result files. It does not call a model and does not trust model-authored files.

Implementation:

- package: `src/boundarybench/verification/`
- direct CLI: `PYTHONPATH=src python3 scripts/run_verifier.py ...`
- isolated CLI: `PYTHONPATH=src python3 scripts/run_verifier_isolated.py ...`
- isolated worker: `scripts/verification_worker.py`

## Isolation

The isolated runner launches a separate Python process with:

- `python -I`;
- a minimal environment containing only `PATH`, `LANG`, and `LC_ALL`;
- no inherited provider/API credential variables;
- repo-local `src` inserted by the worker script, not inherited through `PYTHONPATH`.

Every verifier summary records an isolation report:

- `python_isolated_flag`;
- `safe_path_flag`;
- `forbidden_env_visible`;
- `environment_inherited`;
- `process_boundary`.

This is process isolation, not a container sandbox. Containerized grader isolation remains a release hardening item.

## Deterministic graders

Each parsed result is checked by independent criteria:

| Criterion | Purpose |
|---|---|
| `schema` | Validate immutable task contract, safe JSON parse behavior, result schema, task ID, allowed action, and extra-key rejection. |
| `exact` | Require exact action and exact answer match against the benchmark reference. |
| `graph` | Check source-record, row, and RPMS-to-FHIR resource-type provenance consistency for graph-like claims. |
| `temporal` | Check active vs historical-only action/answer semantics for temporal-status tasks. |
| `version` | Check ICD version behavior without treating the hand-built mapping as a certified terminology crosswalk. |
| `evidence` | Require all reference evidence IDs and reject unknown/spoofed evidence IDs. |

Malformed JSON, non-object JSON, missing results, duplicate task IDs, orphan result task IDs, unexpected model-authored keys, and unknown evidence references all fail closed.

Verifier input integrity is checked before scoring when a task split manifest is present beside the task file. The manifest records task/oracle SHA-256 hashes, and the verifier also checks root `SHA256SUMS` when available. Any manifest/checksum mismatch fails before scored metrics are produced.

## Dependency-aware quarantine

The PVE computes dependency keys from immutable task metadata:

- task ID;
- task family;
- source record IDs;
- RPMS table/row IDs;
- corruption event IDs;
- failure slices.

When a candidate fails, or when the selected policy action is `quarantine_slice` or `reject`, the verifier emits a quarantine record with local slices and the dependency-closure task IDs.

## Selective-risk metrics

Verifier summaries record:

- task count;
- parsed count;
- passed count;
- score;
- coverage, defined as parsed non-abstain decisions divided by all tasks;
- selective risk, defined as failed covered decisions divided by covered decisions;
- false accept count;
- false reject count;
- abstention count;
- quarantine count;
- result-file errors.

These metrics are deterministic summaries of submitted candidate outputs. They are not model benchmark results unless the candidate result file has separate model-run provenance.

If the result file contains any parse, duplicate-task, missing-task, or orphan-result error, the summary sets `result_file_valid: false`, `metrics_valid: false`, `invalid_reason: "result_file_errors"`, and aggregate `score`/`passed_count` to zero. Per-task grades remain diagnostic, but the aggregate is not reportable.

## Oracle, no-op, malformed, and adversarial trials

Trial inputs are generated with:

```bash
PYTHONPATH=src python3 scripts/generate_verifier_trials.py --tasks data/tasks/public_dev/tasks.jsonl --out-dir artifacts/verification/trials/public_dev
```

Committed verifier artifacts include isolated outputs for:

- oracle results;
- no-op abstain-with-empty-answer results;
- malformed output;
- answer-key injection;
- evidence spoofing;
- task-ID mismatch.

## Optional sheaf/mapping-cone diagnostic

The sheaf/mapping-cone layer is diagnostic-only. It has zero scoring weight and reports `DIAGNOSTIC_ONLY_NOT_VALIDATED` when explicitly enabled. It must not affect pass/fail decisions until independent validation artifacts exist.
