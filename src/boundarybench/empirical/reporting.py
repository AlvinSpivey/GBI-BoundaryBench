"""Stage 10 empirical reporting from immutable run records."""

from __future__ import annotations

from collections import defaultdict
import csv
import json
from pathlib import Path
from typing import Any

from boundarybench.tasks.io import read_jsonl


REPORT_SCHEMA_VERSION = "boundarybench.empirical_report.v1"
EMPIRICAL_RESULT_SCHEMA_VERSION = "boundarybench.empirical_result.v1"
VERIFICATION_SUMMARY_SCHEMA_VERSION = "boundarybench.verification_summary.v1"
METRIC_FIELDS = (
    "verified_completion",
    "false_acceptance",
    "false_rejection",
    "abstention",
    "coverage",
    "selective_risk",
    "invalid_output_rate",
    "quarantine_frequency",
    "latency_ms",
    "reported_provider_cost_usd",
    "repeat_run_stability",
)


def _is_empirical_result(record: Any) -> bool:
    return isinstance(record, dict) and record.get("schema_version") == EMPIRICAL_RESULT_SCHEMA_VERSION


def _read_records(runs_dir: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if not runs_dir.exists():
        return records
    for path in sorted(runs_dir.rglob("*.jsonl")):
        records.extend(record for record in read_jsonl(path) if _is_empirical_result(record))
    for path in sorted(runs_dir.rglob("*.json")):
        if path.name.endswith(".schema.json"):
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if _is_empirical_result(payload):
            records.append(payload)
    return records


def _read_verification_summaries(runs_dir: Path) -> dict[str, dict[str, Any]]:
    summaries: dict[str, dict[str, Any]] = {}
    if not runs_dir.exists():
        return summaries
    for path in sorted(runs_dir.rglob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict) or payload.get("schema_version") != VERIFICATION_SUMMARY_SCHEMA_VERSION:
            continue
        run_id = _run_id_from_summary_path(path)
        if run_id:
            summaries[run_id] = payload
    return summaries


def _run_id_from_summary_path(path: Path) -> str | None:
    for part in path.parts:
        if part.startswith("run_"):
            return part
    return None


def _not_run_row(model_key: str = "NOT_RUN") -> dict[str, Any]:
    return {"model": model_key, **{field: "NOT_RUN" for field in METRIC_FIELDS}}


def _summarize_group(records: list[dict[str, Any]], verification_summaries: dict[str, dict[str, Any]]) -> dict[str, Any]:
    if not records:
        return _not_run_row()
    completed = [record for record in records if record.get("run_status") == "COMPLETED"]
    if not completed:
        model_key = str(records[0].get("model", {}).get("exact_model_id", "NOT_RUN"))
        return _not_run_row(model_key)
    summaries = [
        verification_summaries[record["run_id"]]
        for record in completed
        if isinstance(record.get("run_id"), str) and record["run_id"] in verification_summaries
    ]
    if not summaries:
        model_key = str(completed[0].get("model", {}).get("exact_model_id", "UNKNOWN"))
        return _not_run_row(model_key)
    total = len(summaries)
    model_key = str(completed[0].get("model", {}).get("exact_model_id", "UNKNOWN"))
    latency_values = [record.get("latency_ms") for record in completed if isinstance(record.get("latency_ms"), (int, float))]
    cost_values = [
        record.get("reported_provider_cost_usd")
        for record in completed
        if isinstance(record.get("reported_provider_cost_usd"), (int, float))
    ]
    coverage = sum(float(summary.get("coverage", 0.0)) for summary in summaries) / total
    selective_values = [summary.get("selective_risk") for summary in summaries if isinstance(summary.get("selective_risk"), (int, float))]
    selective_risk = sum(float(value) for value in selective_values) / len(selective_values) if selective_values else "NOT_RUN"
    invalid = sum(
        1.0 - (float(summary.get("parsed_count", 0)) / float(summary.get("task_count", 1) or 1))
        for summary in summaries
    ) / total
    quarantine = sum(
        float(summary.get("quarantine_count", 0)) / float(summary.get("task_count", 1) or 1)
        for summary in summaries
    ) / total
    scores = [summary.get("score") for summary in summaries if isinstance(summary.get("score"), int)]
    repeat_stability: float | str = "NOT_RUN"
    if len(scores) >= 2:
        repeat_stability = 1.0 if len(set(scores)) == 1 else 0.0
    return {
        "model": model_key,
        "verified_completion": sum(int(summary.get("passed_count", 0)) for summary in summaries),
        "false_acceptance": sum(int(summary.get("false_accept_count", 0)) for summary in summaries),
        "false_rejection": sum(int(summary.get("false_reject_count", 0)) for summary in summaries),
        "abstention": sum(int(summary.get("abstention_count", 0)) for summary in summaries),
        "coverage": coverage,
        "selective_risk": selective_risk,
        "invalid_output_rate": invalid,
        "quarantine_frequency": quarantine,
        "latency_ms": sum(latency_values) / len(latency_values) if latency_values else "NOT_RUN",
        "reported_provider_cost_usd": sum(cost_values) if cost_values else "NOT_RUN",
        "repeat_run_stability": repeat_stability,
    }


def build_report(*, runs_dir: Path, out_dir: Path) -> dict[str, Any]:
    records = _read_records(runs_dir)
    summaries = _read_verification_summaries(runs_dir)
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        model = record.get("model", {})
        provider = str(model.get("provider", "UNKNOWN"))
        evidence_mode = str(record.get("evidence_mode", "UNKNOWN"))
        exact_model = str(model.get("exact_model_id", "UNKNOWN"))
        grouped[(provider, evidence_mode, exact_model)].append(record)
    rows = []
    if grouped:
        for (provider, evidence_mode, exact_model), group in sorted(grouped.items()):
            row = _summarize_group(group, summaries)
            row.update({"provider": provider, "evidence_mode": evidence_mode})
            row["model"] = exact_model
            rows.append(row)
    else:
        row = _not_run_row()
        row.update({"provider": "NOT_RUN", "evidence_mode": "NOT_RUN"})
        rows.append(row)
    out_dir.mkdir(parents=True, exist_ok=True)
    table_path = out_dir / "empirical_results_table.csv"
    with table_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["provider", "evidence_mode", "model", *METRIC_FIELDS],
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)
    report = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "runs_dir": runs_dir.as_posix(),
        "run_record_count": len(records),
        "verification_summary_count": len(summaries),
        "tables": {"empirical_results_table": table_path.as_posix()},
        "rows": rows,
        "hand_authored_results": False,
    }
    (out_dir / "empirical_report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def write_risk_coverage_plot_data(*, report_path: Path, out_path: Path) -> dict[str, Any]:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    points = []
    for row in report.get("rows", []):
        if isinstance(row.get("coverage"), (int, float)) and isinstance(row.get("selective_risk"), (int, float)):
            points.append(
                {
                    "provider": row.get("provider"),
                    "evidence_mode": row.get("evidence_mode"),
                    "coverage": row["coverage"],
                    "selective_risk": row["selective_risk"],
                }
            )
    payload = {
        "schema_version": "boundarybench.risk_coverage_plot_data.v1",
        "source_report": report_path.as_posix(),
        "points": points,
        "status": "NOT_RUN" if not points else "READY",
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs-dir", type=Path, default=Path("artifacts/empirical/model_runs"))
    parser.add_argument("--out-dir", type=Path, default=Path("artifacts/empirical/stage10/reporting"))
    args = parser.parse_args(argv)
    report = build_report(runs_dir=args.runs_dir, out_dir=args.out_dir)
    write_risk_coverage_plot_data(
        report_path=args.out_dir / "empirical_report.json",
        out_path=args.out_dir / "risk_coverage_plot_data.json",
    )
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
