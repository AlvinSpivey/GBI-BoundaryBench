#!/usr/bin/env python3
"""Generate the GBI-DCSE v2 scorecard figures.

Reads only the public-safe artifacts under ``artifacts/public_results/gbi_v2``.

Run from the repository root:

    python3 docs/betal/figure_sources/make_gbi_v2_figures.py
"""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[3]
METRICS = ROOT / "artifacts/public_results/gbi_v2"
FIGURES = ROOT / "docs/betal/figures"

FONT = "Inter, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif"
INK = "#172033"
INK_SECONDARY = "#475569"
INK_MUTED = "#64748B"
SURFACE = "#FFFFFF"
SURFACE_ALT = "#F8FAFC"
GRID = "#E2E8F0"
HAIRLINE = "#CBD5E1"

# Same validated categorical palette as the v0.2 figures: lightness band PASS,
# chroma floor PASS, adjacent CVD separation PASS (worst deutan dE 13.7),
# normal-vision floor PASS, contrast PASS. Every series also carries a legend
# entry, a distinct marker shape, and a direct label, so identity is never
# color-alone.
POLICY_SERIES = {
    "complete": {
        "color": "#2563EB",
        "label": "Complete policy",
        "marker": "circle",
    },
    "incomplete_ablation": {
        "color": "#C2410C",
        "label": "Ablation: 2 gates omitted",
        "marker": "square",
    },
    "score_only_identity_ablation": {
        "color": "#0D9488",
        "label": "Ablation: score-based identity",
        "marker": "triangle",
    },
}
# Reserved status ink for the frozen baseline, which is a state and not a series.
BASELINE_INK = "#991B1B"


def _text(
    x: float,
    y: float,
    value: str,
    *,
    size: int = 15,
    weight: str = "400",
    fill: str = INK,
    anchor: str = "start",
) -> str:
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" font-family="{FONT}" font-size="{size}" '
        f'font-weight="{weight}" fill="{fill}" text-anchor="{anchor}">{html.escape(value)}</text>'
    )


def _marker(shape: str, x: float, y: float, color: str, size: float = 5.5) -> str:
    if shape == "circle":
        return (
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{size:.1f}" fill="{color}" '
            f'stroke="{SURFACE}" stroke-width="2"/>'
        )
    if shape == "square":
        side = size * 1.8
        return (
            f'<rect x="{x - side / 2:.1f}" y="{y - side / 2:.1f}" width="{side:.1f}" '
            f'height="{side:.1f}" rx="1.5" fill="{color}" stroke="{SURFACE}" stroke-width="2"/>'
        )
    if shape == "diamond":
        points = " ".join(
            f"{px:.1f},{py:.1f}"
            for px, py in (
                (x, y - size * 1.3),
                (x + size * 1.3, y),
                (x, y + size * 1.3),
                (x - size * 1.3, y),
            )
        )
        return f'<polygon points="{points}" fill="{color}" stroke="{SURFACE}" stroke-width="2"/>'
    points = " ".join(
        f"{px:.1f},{py:.1f}"
        for px, py in (
            (x, y - size * 1.15),
            (x + size * 1.05, y + size * 0.75),
            (x - size * 1.05, y + size * 0.75),
        )
    )
    return f'<polygon points="{points}" fill="{color}" stroke="{SURFACE}" stroke-width="2"/>'


def _legend(x: float, y: float, entries: Sequence[tuple[str, str, str]]) -> list[str]:
    parts: list[str] = []
    cursor = x
    for color, shape, label in entries:
        parts.append(_marker(shape, cursor + 6, y - 4, color))
        parts.append(_text(cursor + 18, y, label, size=14, fill=INK_SECONDARY))
        cursor += 20 + 7.6 * len(label) + 26
    return parts


def _load() -> tuple[dict[str, Any], dict[str, Any]]:
    scorecard = json.loads((METRICS / "table3_scorecard.json").read_text(encoding="utf-8"))
    sweep = json.loads((METRICS / "strictness_sweep.json").read_text(encoding="utf-8"))
    if scorecard["language_model_executed"] is not False:
        raise ValueError("figure captions assume no language model was executed")
    contrast = scorecard["v01_baseline_contrast"]
    if contrast["false_conflict_adjudication_rate"] != 1.0:
        raise ValueError("v0.1 contrast is not the expected refuse-everything point")
    return scorecard, sweep


def write_clinical_frontier(scorecard: dict[str, Any], sweep: dict[str, Any]) -> Path:
    width, height = 1160, 790
    plot_x, plot_y = 130, 214
    plot_w, plot_h = 700, 360
    x_max = 1.0
    # y_max deliberately above 1.0 so the 100% line is not flush with the plot
    # ceiling: the callouts for the target band and the frozen baseline live in
    # that headroom instead of on top of the data.
    y_min, y_max = 0.78, 1.035

    def x_of(rate: float) -> float:
        return plot_x + min(rate, x_max) / x_max * plot_w

    def y_of(rate: float) -> float:
        return plot_y + plot_h - (min(max(rate, y_min), y_max) - y_min) / (y_max - y_min) * plot_h

    target_fc = 0.04
    parts: list[str] = [
        f'<rect width="{width}" height="{height}" fill="{SURFACE}"/>',
        _text(plot_x, 54, "Table 3 clinical frontier: sensitivity against false conflict", size=25, weight="600"),
        _text(
            plot_x,
            82,
            "Both targets must hold at once. Refusing everything satisfies the first and maximally violates the second.",
            size=15,
            fill=INK_SECONDARY,
        ),
        _text(
            plot_x,
            104,
            "512 synthetic tasks - 116 injected severe contradictions - 99 conflict-free records - no language model executed",
            size=13,
            fill=INK_MUTED,
        ),
    ]

    # Target region: sensitivity == 1.0 and false conflict <= 4%.
    parts.append(
        f'<rect x="{plot_x}" y="{y_of(1.004):.1f}" width="{x_of(target_fc) - plot_x:.1f}" '
        f'height="{y_of(0.996) - y_of(1.004):.1f}" rx="4" fill="#F0FDF4" stroke="#86EFAC" '
        f'stroke-width="2"/>'
    )

    # Axes.
    for tick in range(0, 11, 2):
        rate = tick / 10
        x = x_of(rate)
        parts.append(
            f'<line x1="{x:.1f}" y1="{plot_y}" x2="{x:.1f}" y2="{plot_y + plot_h}" '
            f'stroke="{GRID}" stroke-width="1"/>'
        )
        parts.append(
            _text(x, plot_y + plot_h + 26, f"{rate:.0%}", size=13, fill=INK_MUTED, anchor="middle")
        )
    for value in (0.80, 0.85, 0.90, 0.95, 1.00):
        y = y_of(value)
        parts.append(
            f'<line x1="{plot_x}" y1="{y:.1f}" x2="{plot_x + plot_w}" y2="{y:.1f}" '
            f'stroke="{GRID}" stroke-width="1"/>'
        )
        parts.append(_text(plot_x - 12, y + 5, f"{value:.0%}", size=13, fill=INK_MUTED, anchor="end"))
    parts.append(
        f'<line x1="{plot_x}" y1="{plot_y + plot_h}" x2="{plot_x + plot_w}" '
        f'y2="{plot_y + plot_h}" stroke="{HAIRLINE}" stroke-width="1.5"/>'
    )
    parts.append(
        _text(
            plot_x + plot_w / 2,
            plot_y + plot_h + 54,
            "False Conflict Adjudication Rate  (lower is better)",
            size=14,
            fill=INK_SECONDARY,
            anchor="middle",
        )
    )
    parts.append(
        f'<text transform="translate({plot_x - 74:.1f},{plot_y + plot_h / 2:.1f}) rotate(-90)" '
        f'font-family="{FONT}" font-size="14" font-weight="600" fill="{INK_SECONDARY}" '
        f'text-anchor="middle">Severe Contradiction Sensitivity</text>'
    )

    # Policy frontiers across the strictness sweep.
    for key, spec in POLICY_SERIES.items():
        rows = sweep["policies"][key]["rows"]
        points = [
            (x_of(row["false_conflict_adjudication_rate"]), y_of(row["severe_contradiction_sensitivity"]))
            for row in rows
            if row["false_conflict_adjudication_rate"] is not None
            and row["severe_contradiction_sensitivity"] is not None
        ]
        ordered = sorted(set(points))
        path_data = " ".join(
            ("M" if index == 0 else "L") + f" {x:.1f} {y:.1f}"
            for index, (x, y) in enumerate(ordered)
        )
        parts.append(
            f'<path d="{path_data}" fill="none" stroke="{spec["color"]}" stroke-width="2" '
            f'stroke-linejoin="round" opacity="0.85"/>'
        )
        for x, y in ordered:
            parts.append(_marker(spec["marker"], x, y, spec["color"], size=4.5))

    # The frozen v0.1 baseline: the refuse-everything corner.
    contrast = scorecard["v01_baseline_contrast"]
    bx, by = x_of(contrast["false_conflict_adjudication_rate"]), y_of(
        contrast["severe_contradiction_sensitivity"]
    )
    parts.append(_marker("diamond", bx, by, BASELINE_INK, size=7))
    parts.append(
        _text(bx + 4, by - 44, "v0.1 frozen: 768/768 refused", size=13, weight="600",
              fill=BASELINE_INK, anchor="end")
    )
    parts.append(
        _text(bx + 4, by - 26, "sensitivity 100% (vacuous), false conflict 100%", size=12,
              fill=BASELINE_INK, anchor="end")
    )

    # The selected v2 operating point.
    complete_rows = sweep["policies"]["complete"]["rows"]
    selected = next(
        row
        for row in complete_rows
        if row["strictness"] == scorecard["operating_strictness"]
    )
    sx, sy = x_of(selected["false_conflict_adjudication_rate"]), y_of(
        selected["severe_contradiction_sensitivity"]
    )
    parts.append(
        f'<circle cx="{sx:.1f}" cy="{sy:.1f}" r="13" fill="none" stroke="#166534" '
        f'stroke-width="2.5"/>'
    )
    parts.append(
        _text(sx + 26, sy + 30, "v2 selected operating point", size=13, weight="600", fill="#166534")
    )
    parts.append(
        _text(
            sx + 26,
            sy + 48,
            f"strictness {selected['strictness']}: sensitivity 100%, false conflict 0.0%",
            size=12,
            fill="#166534",
        )
    )

    parts.extend(
        _legend(
            plot_x,
            150,
            [(spec["color"], spec["marker"], spec["label"]) for spec in POLICY_SERIES.values()]
            + [(BASELINE_INK, "diamond", "v0.1 frozen baseline")],
        )
    )
    parts.append(
        f'<rect x="{plot_x}" y="{168}" width="26" height="14" rx="3" fill="#F0FDF4" '
        f'stroke="#86EFAC" stroke-width="2"/>'
    )
    parts.append(
        _text(
            plot_x + 34,
            180,
            "Table 3 target region: sensitivity 100% and false conflict <= 4%",
            size=14,
            fill=INK_SECONDARY,
        )
    )

    # Scorecard strip.
    strip_y = plot_y + plot_h + 86
    parts.append(
        f'<rect x="{plot_x}" y="{strip_y}" width="{plot_w + 200}" height="72" rx="10" '
        f'fill="{SURFACE_ALT}" stroke="{HAIRLINE}" stroke-width="1"/>'
    )
    summary = scorecard["table_3_summary"]
    claims = scorecard["additional_claims_summary"]
    parts.append(
        _text(plot_x + 20, strip_y + 30, "Scorecard against main.pdf Appendix B", size=14, weight="600")
    )
    parts.append(
        _text(
            plot_x + 20,
            strip_y + 54,
            f"Table 3: {summary['targets_met']}/{summary['measurable_in_this_environment']} measurable targets met, "
            f"{summary['out_of_scope']} out of scope (needs a TEE).   "
            f"Additional manuscript claims: {claims['met']}/{claims['evaluated']} met.   "
            "Appendix B.1 Assertions 1-3: all passed.",
            size=13,
            fill=INK_SECONDARY,
        )
    )
    parts.append(
        _text(
            plot_x,
            height - 20,
            "Ablation curves are deliberately deficient policies. That they fail is what makes the complete policy's result informative.",
            size=13,
            fill=INK_MUTED,
        )
    )

    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="Scatter of severe-contradiction sensitivity against false-conflict rate for '
        f'three policies, with the Table 3 target region and the frozen v0.1 baseline">'
        + "".join(parts)
        + "</svg>"
    )
    FIGURES.mkdir(parents=True, exist_ok=True)
    path = FIGURES / "gbi_v2_clinical_frontier.svg"
    path.write_text(svg + "\n", encoding="utf-8")
    return path


def main() -> int:
    scorecard, sweep = _load()
    path = write_clinical_frontier(scorecard, sweep)
    print(f"wrote {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
