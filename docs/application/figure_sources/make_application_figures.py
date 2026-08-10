#!/usr/bin/env python3
"""Generate application-facing BoundaryBench v0.1 SVG figures.

The script reads only compact scored metrics under artifacts/public_results/v0_1.
It does not read trusted references, raw model response text, or benchmark answer
content.
"""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
SCORED = ROOT / "artifacts/public_results/v0_1"
FIGURES = ROOT / "docs/application/figures"


def _load_metrics() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    aggregate = json.loads((SCORED / "aggregate_metrics.json").read_text(encoding="utf-8"))
    per_mode = json.loads((SCORED / "per_mode_metrics.json").read_text(encoding="utf-8"))["rows"]
    expected_distribution = {"safe_parse_reject": 123, "safe_schema_reject": 133}
    if aggregate["canonical_execution_count"] != 768:
        raise ValueError("unexpected canonical_execution_count")
    if aggregate["canonical_result_count"] != 0:
        raise ValueError("unexpected canonical_result_count")
    if aggregate["invalid_output_rate"] != 1.0:
        raise ValueError("unexpected invalid_output_rate")
    if aggregate["coverage"] != 0.0:
        raise ValueError("unexpected coverage")
    if aggregate["selective_risk"] is not None:
        raise ValueError("selective_risk should be null at zero coverage")
    for row in per_mode:
        if row["task_count"] != 256:
            raise ValueError(f"unexpected task_count for {row['evidence_mode']}")
        if row["accepted_result_count"] != 0:
            raise ValueError(f"unexpected accepted_result_count for {row['evidence_mode']}")
        if row["parse_schema_status_distribution"] != expected_distribution:
            raise ValueError(f"unexpected parse/schema distribution for {row['evidence_mode']}")
    return aggregate, per_mode


def _text(x: int, y: int, text: str, *, size: int = 18, weight: str = "400", fill: str = "#172033", anchor: str = "start") -> str:
    escaped = html.escape(text)
    return (
        f'<text x="{x}" y="{y}" font-family="Inter, -apple-system, BlinkMacSystemFont, '
        f'Segoe UI, sans-serif" font-size="{size}" font-weight="{weight}" '
        f'fill="{fill}" text-anchor="{anchor}">{escaped}</text>'
    )


def _rect(x: int, y: int, w: int, h: int, *, fill: str, stroke: str = "#CBD5E1", rx: int = 18) -> str:
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}" stroke="{stroke}" stroke-width="2"/>'


def _arrow(x1: int, y1: int, x2: int, y2: int, *, color: str = "#475569") -> str:
    return (
        f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" '
        f'stroke-width="3" marker-end="url(#arrow)"/>'
    )


def write_architecture() -> Path:
    width, height = 1200, 760
    dims = ["Identity", "Provenance", "Terminology / version", "Temporal validity", "Evidence sufficiency", "Dependencies", "Policy"]
    actions = ["ADMIT", "ADMIT_HISTORICAL_ONLY", "QUARANTINE_SLICE", "ABSTAIN", "EXPERT_REVIEW", "REJECT"]
    dim_boxes = []
    for i, label in enumerate(dims):
        col = i % 4
        row = i // 4
        x = 388 + col * 186
        y = 300 + row * 76
        dim_boxes.append(_rect(x, y, 160, 48, fill="#EEF6FF", stroke="#7AB7E8", rx=12))
        dim_boxes.append(_text(x + 80, y + 30, label, size=14, weight="650", fill="#0F3A5D", anchor="middle"))
    action_boxes = []
    for i, label in enumerate(actions):
        x = 86 + i * 173
        y = 620
        fill = "#F0FDF4" if label.startswith("ADMIT") else "#FFF7ED" if label in {"QUARANTINE_SLICE", "EXPERT_REVIEW"} else "#F8FAFC"
        stroke = "#22C55E" if label.startswith("ADMIT") else "#FB923C" if label in {"QUARANTINE_SLICE", "EXPERT_REVIEW"} else "#94A3B8"
        action_boxes.append(_rect(x, y, 150, 56, fill=fill, stroke=stroke, rx=14))
        display = label.replace("_", " ")
        action_boxes.append(_text(x + 75, y + 34, display, size=12, weight="750", fill="#172033", anchor="middle"))
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">
  <title id="title">GBI BoundaryBench verification architecture</title>
  <desc id="desc">A model proposes a legacy-EHR transformation; a deterministic verifier controls whether the output becomes an admissible action, quarantine, review, abstention, or rejection.</desc>
  <defs>
    <marker id="arrow" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto" markerUnits="strokeWidth">
      <path d="M0,0 L0,6 L9,3 z" fill="#475569"/>
    </marker>
    <filter id="shadow" x="-20%" y="-20%" width="140%" height="140%">
      <feDropShadow dx="0" dy="6" stdDeviation="8" flood-color="#0F172A" flood-opacity="0.12"/>
    </filter>
  </defs>
  <rect width="1200" height="760" fill="#FFFFFF"/>
  {_text(600, 54, "GBI BoundaryBench v0.1", size=30, weight="800", anchor="middle")}
  {_text(600, 88, "Model proposal is evidence; programmatic verification controls admissibility.", size=18, fill="#475569", anchor="middle")}

  <g filter="url(#shadow)">
    {_rect(70, 150, 260, 108, fill="#F8FAFC", stroke="#CBD5E1")}
    {_text(200, 188, "Legacy EHR boundary", size=20, weight="750", anchor="middle")}
    {_text(200, 218, "Synthetic RPMS-shaped rows", size=15, fill="#475569", anchor="middle")}
    {_text(200, 242, "messy enterprise records", size=15, fill="#475569", anchor="middle")}

    {_rect(470, 150, 260, 108, fill="#FEFCE8", stroke="#FACC15")}
    {_text(600, 188, "Model proposal", size=20, weight="750", anchor="middle")}
    {_text(600, 218, "mapping / repair / trace", size=15, fill="#475569", anchor="middle")}
    {_text(600, 242, "classification / abstention", size=15, fill="#475569", anchor="middle")}

    {_rect(870, 150, 260, 108, fill="#F0F9FF", stroke="#38BDF8")}
    {_text(1000, 188, "Programmatic verifier", size=20, weight="750", anchor="middle")}
    {_text(1000, 218, "deterministic checks", size=15, fill="#475569", anchor="middle")}
    {_text(1000, 242, "fail-closed policy", size=15, fill="#475569", anchor="middle")}
  </g>
  {_arrow(330, 204, 470, 204)}
  {_arrow(730, 204, 870, 204)}

  {_text(600, 292, "Verification dimensions", size=18, weight="800", fill="#0F3A5D", anchor="middle")}
  {"".join(dim_boxes)}

  {_arrow(1000, 258, 1000, 380)}
  {_arrow(1000, 458, 1000, 565)}
  {_text(600, 585, "Admissible actions and fail-closed outcomes", size=18, weight="800", fill="#172033", anchor="middle")}
  {"".join(action_boxes)}
  {_text(600, 720, "The verifier, not the model, decides whether a proposal becomes action, quarantine, review, abstention, or rejection.", size=15, fill="#475569", anchor="middle")}
</svg>
"""
    path = FIGURES / "boundarybench_architecture.svg"
    path.write_text(svg, encoding="utf-8")
    return path


def write_failure_flow(aggregate: dict[str, Any], per_mode: list[dict[str, Any]]) -> Path:
    width, height = 1200, 780
    parse_rejects = sum(row["parse_schema_status_distribution"]["safe_parse_reject"] for row in per_mode)
    schema_rejects = sum(row["parse_schema_status_distribution"]["safe_schema_reject"] for row in per_mode)
    accepted = aggregate["canonical_result_count"]
    quarantined = aggregate["quarantine_count"]
    rows_svg = []
    mode_order = ["output_only", "token_top_k", "full_category_evidence"]
    by_mode = {row["evidence_mode"]: row for row in per_mode}
    for i, mode in enumerate(mode_order):
        row = by_mode[mode]
        y = 538 + i * 54
        label = mode.replace("_", " ")
        rows_svg.append(_text(112, y + 31, label, size=16, weight="700"))
        rows_svg.append(_text(410, y + 31, str(row["parse_schema_status_distribution"]["safe_parse_reject"]), size=16, weight="700", anchor="middle"))
        rows_svg.append(_text(595, y + 31, str(row["parse_schema_status_distribution"]["safe_schema_reject"]), size=16, weight="700", anchor="middle"))
        rows_svg.append(_text(778, y + 31, str(row["accepted_result_count"]), size=16, weight="700", anchor="middle"))
        rows_svg.append(_text(970, y + 31, "0.0 / 1.0", size=16, weight="700", anchor="middle"))
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">
  <title id="title">Qwen3-4B BoundaryBench v0.1 failure flow</title>
  <desc id="desc">Across 768 canonical held-out executions, 369 outputs were safe parse rejects, 399 were safe schema rejects, zero were accepted, and all 768 were quarantined.</desc>
  <defs>
    <marker id="arrow" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto" markerUnits="strokeWidth">
      <path d="M0,0 L0,6 L9,3 z" fill="#475569"/>
    </marker>
    <filter id="shadow" x="-20%" y="-20%" width="140%" height="140%">
      <feDropShadow dx="0" dy="6" stdDeviation="8" flood-color="#0F172A" flood-opacity="0.12"/>
    </filter>
  </defs>
  <rect width="1200" height="780" fill="#FFFFFF"/>
  {_text(600, 52, "Qwen3-4B-Instruct-2507 on BoundaryBench v0.1", size=28, weight="800", anchor="middle")}
  {_text(600, 86, "256 held-out tasks × 3 evidence modes = 768 frozen canonical executions", size=18, fill="#475569", anchor="middle")}

  <g filter="url(#shadow)">
    {_rect(120, 130, 960, 82, fill="#F8FAFC", stroke="#CBD5E1")}
    {_text(600, 166, "768 completed held-out executions", size=24, weight="800", anchor="middle")}
    {_text(600, 194, "all retained in the evaluation denominator", size=15, fill="#475569", anchor="middle")}
  </g>
  {_arrow(600, 212, 600, 250)}

  <g filter="url(#shadow)">
    {_rect(150, 250, 410, 92, fill="#FFF7ED", stroke="#FB923C")}
    {_text(355, 288, f"{parse_rejects} safe_parse_reject", size=23, weight="800", anchor="middle")}
    {_text(355, 318, "mutually exclusive runner outcome", size=15, fill="#9A3412", anchor="middle")}
    {_rect(640, 250, 410, 92, fill="#FEF2F2", stroke="#F87171")}
    {_text(845, 288, f"{schema_rejects} safe_schema_reject", size=23, weight="800", anchor="middle")}
    {_text(845, 318, "mutually exclusive runner outcome", size=15, fill="#991B1B", anchor="middle")}
  </g>
  {_arrow(600, 342, 600, 380)}

  <g filter="url(#shadow)">
    {_rect(210, 380, 340, 78, fill="#F8FAFC", stroke="#94A3B8")}
    {_text(380, 414, f"{accepted} accepted outputs", size=22, weight="800", anchor="middle")}
    {_text(380, 440, "0 boundarybench.result.v1 records", size=14, fill="#475569", anchor="middle")}
    {_rect(650, 380, 340, 78, fill="#F0F9FF", stroke="#38BDF8")}
    {_text(820, 414, f"{quarantined} quarantined", size=22, weight="800", anchor="middle")}
    {_text(820, 440, "deterministic fail-closed outcome", size=14, fill="#475569", anchor="middle")}
  </g>
  {_arrow(600, 458, 600, 490)}
  {_text(600, 501, "Coverage = 0.0   •   Invalid-output rate = 1.0   •   Selective risk = undefined at zero coverage", size=17, weight="700", fill="#172033", anchor="middle")}

  <rect x="82" y="526" width="1036" height="204" rx="16" fill="#FFFFFF" stroke="#CBD5E1" stroke-width="2"/>
  {_text(112, 558, "Evidence mode", size=14, weight="800", fill="#475569")}
  {_text(410, 558, "Parse reject", size=14, weight="800", fill="#475569", anchor="middle")}
  {_text(595, 558, "Schema reject", size=14, weight="800", fill="#475569", anchor="middle")}
  {_text(778, 558, "Accepted", size=14, weight="800", fill="#475569", anchor="middle")}
  {_text(970, 558, "Coverage / invalid", size=14, weight="800", fill="#475569", anchor="middle")}
  <line x1="100" y1="574" x2="1100" y2="574" stroke="#E2E8F0" stroke-width="2"/>
  <line x1="100" y1="628" x2="1100" y2="628" stroke="#F1F5F9" stroke-width="2"/>
  <line x1="100" y1="682" x2="1100" y2="682" stroke="#F1F5F9" stroke-width="2"/>
  {"".join(rows_svg)}
  {_text(600, 756, "The parse/schema categories are parallel outcomes, not sequential pipeline stages.", size=14, fill="#64748B", anchor="middle")}
</svg>
"""
    path = FIGURES / "qwen_v0_1_failure_flow.svg"
    path.write_text(svg, encoding="utf-8")
    return path


def main() -> int:
    FIGURES.mkdir(parents=True, exist_ok=True)
    aggregate, per_mode = _load_metrics()
    for path in (write_architecture(), write_failure_flow(aggregate, per_mode)):
        print(path.relative_to(ROOT).as_posix())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
