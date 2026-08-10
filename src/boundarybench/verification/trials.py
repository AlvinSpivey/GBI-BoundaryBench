"""Generate deterministic verifier trial result files."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from boundarybench.tasks.grade import noop_result, oracle_result
from boundarybench.tasks.io import read_jsonl, write_jsonl


def _oracle_by_task(tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [oracle_result(task) for task in tasks]


def generate_verifier_trials(tasks_path: Path, out_dir: Path) -> dict[str, Any]:
    tasks = read_jsonl(tasks_path)
    out_dir.mkdir(parents=True, exist_ok=True)

    noop_path = out_dir / "noop_results.jsonl"
    malformed_path = out_dir / "malformed_results.jsonl"
    answer_key_path = out_dir / "answer_key_injection_results.jsonl"
    evidence_spoof_path = out_dir / "evidence_spoof_results.jsonl"
    task_id_mismatch_path = out_dir / "task_id_mismatch_results.jsonl"

    write_jsonl(noop_path, [noop_result(task) for task in tasks])
    malformed_path.write_text("{not-json\n[]\n", encoding="utf-8")

    answer_key_rows = []
    for task in tasks:
        row = oracle_result(task)
        row["reference"] = task["reference"]
        row["untrusted_hint"] = "attempt to pass by embedding the answer key"
        answer_key_rows.append(row)
    write_jsonl(answer_key_path, answer_key_rows)

    evidence_spoof_rows = []
    for task in tasks:
        row = oracle_result(task)
        row["evidence_refs"] = list(row["evidence_refs"]) + ["../../data/tasks/public_dev/oracle_results.jsonl"]
        evidence_spoof_rows.append(row)
    write_jsonl(evidence_spoof_path, evidence_spoof_rows)

    mismatch_rows = _oracle_by_task(tasks)
    for row in mismatch_rows:
        row["task_id"] = "mismatched-" + row["task_id"]
    write_jsonl(task_id_mismatch_path, mismatch_rows)

    manifest = {
        "schema_version": "boundarybench.verifier_trials_manifest.v1",
        "tasks_path": str(tasks_path),
        "trial_count": 5,
        "trials": [
            {
                "name": "noop",
                "path": str(noop_path),
                "expected": "all_tasks_fail",
            },
            {
                "name": "malformed",
                "path": str(malformed_path),
                "expected": "safe_parse_reject_and_no_success",
            },
            {
                "name": "answer_key_injection",
                "path": str(answer_key_path),
                "expected": "schema_reject_extra_model_authored_keys",
            },
            {
                "name": "evidence_spoof",
                "path": str(evidence_spoof_path),
                "expected": "evidence_reject_unknown_refs",
            },
            {
                "name": "task_id_mismatch",
                "path": str(task_id_mismatch_path),
                "expected": "reject_orphan_results_and_missing_expected_results",
            },
        ],
    }
    manifest_path = out_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def main(argv: list[str] | None = None) -> None:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tasks", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    args = parser.parse_args(argv)
    print(json.dumps(generate_verifier_trials(args.tasks, args.out_dir), sort_keys=True))


if __name__ == "__main__":
    main()

