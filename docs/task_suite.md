# v0.1 task suite

The v0.1 public-dev split is a small deterministic development split generated from the Stage 1 paired data-truth artifacts under `data/stage1/official_synthea_sample_310/`.

It is a benchmark engineering fixture, not a clinical validation set. The expected answers are benchmark references derived from synthetic generator truth and explicit corruption/event provenance.


## Public showcase note

This public repository includes task-family documentation, schemas, and safe source interfaces. It does not include the private held-out task package, trusted references, oracle outputs, or hidden labels. Mentions of generated oracle files describe the private benchmark workflow; the files themselves are not published here.

## Task families

The current split contains one task for each v0.1 family:

| Family | Required behavior |
|---|---|
| `patient_identity_normalization` | Normalize a noisy RPMS patient identifier and admit only if it links to DEM evidence. |
| `orphan_duplicate_detection` | Detect orphan or duplicate patient references and localize quarantine/review. |
| `field_anomaly_bleed` | Detect free-text bleed in structured fields and route to review. |
| `code_system_version_validation` | Distinguish current ICD-10-CM from legacy ICD-9-CM evidence. |
| `rpms_to_fhir_mapping` | Map RPMS table/row evidence to expected FHIR resource type and provenance. |
| `temporal_status_classification` | Admit active evidence separately from historical-only evidence. |
| `evidence_sufficiency` | Abstain when required evidence for an asserted diagnosis is absent. |
| `policy_action_selection` | Apply deterministic fail-closed policy actions for unsafe inputs. |

## Contracts

Machine-readable contracts are in:

- `schemas/task.schema.json`
- `schemas/result.schema.json`

Python typed contracts and dependency-free validators are in `src/boundarybench/tasks/schemas.py`.

Every task records:

- typed inputs;
- allowed actions;
- explicit action semantics;
- abstention policy;
- evidence references;
- failure slices;
- deterministic reference action and answer.

Candidate results are parsed through `safe_parse_result`. Malformed JSON, non-object JSON, schema-invalid outputs, unknown actions, missing evidence, and task-ID mismatches fail closed.

## Public-dev artifacts

Generated artifacts:

- `data/tasks/public_dev/tasks.jsonl`
- `data/tasks/public_dev/oracle_results.jsonl`
- `data/tasks/public_dev/manifest.json`

Regenerate with:

```bash
PYTHONPATH=src python3 scripts/generate_public_dev_tasks.py
```

The oracle output for every task must pass deterministic grading. A no-op abstain-with-empty-answer output must fail every public-dev task, including the evidence-sufficiency task, because required answer/evidence fields are still checked.

## Five-minute rules baseline

The deterministic rules baseline is intentionally simple and local. It uses task inputs only and does not call a model.

Run:

```bash
PYTHONPATH=src python3 scripts/run_rules_baseline.py
```

Outputs:

- `artifacts/baselines/rules_public_dev/results.jsonl`
- `artifacts/baselines/rules_public_dev/grades.jsonl`
- `artifacts/baselines/rules_public_dev/report.json`

The current recorded public-dev baseline report has 8 tasks, 8 passes, score 8, and no result-file parse errors. This is a local deterministic rules-baseline result only; no model/provider latency, cost, or clinical validation claim is implied.
