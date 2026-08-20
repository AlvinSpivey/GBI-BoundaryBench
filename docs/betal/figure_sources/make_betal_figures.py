#!/usr/bin/env python3
"""Generate the BeTaL-GBI v0.2 SVG figures.

Reads only the public-safe aggregate artifacts under
``artifacts/public_results/v0_2``. Reads no held-out reference material and
no raw model output.

Run from the repository root:

    python3 docs/betal/figure_sources/make_betal_figures.py
"""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[3]
METRICS = ROOT / "artifacts/public_results/v0_2"
FIGURES = ROOT / "docs/betal/figures"

FONT = "Inter, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif"

# Ink tokens, matching the existing v0.1 application figures.
INK = "#172033"
INK_SECONDARY = "#475569"
INK_MUTED = "#64748B"
SURFACE = "#FFFFFF"
SURFACE_ALT = "#F8FAFC"
GRID = "#E2E8F0"
HAIRLINE = "#CBD5E1"

# Categorical series palette. Validated with the dataviz palette validator
# against surface #FFFFFF: lightness band PASS, chroma floor PASS, adjacent CVD
# separation PASS (worst deutan dE 13.7), normal-vision floor PASS (worst 22.6),
# contrast PASS. The all-pairs tritan separation for teal/orange sits at dE 6.4,
# which is why every series here also carries a legend entry, a distinct marker
# shape, and a direct label: identity is never color-alone.
SERIES = {
    "feedback_coordinate": {"color": "#2563EB", "label": "Feedback (BeTaL-style)", "marker": "circle"},
    "random_sampling_ppr": {"color": "#C2410C", "label": "RS+PPR baseline", "marker": "square"},
    "best_of_n": {"color": "#0D9488", "label": "Best-of-N baseline", "marker": "triangle"},
}
TIER_SERIES = {
    "tier_low": {"color": "#C2410C", "label": "tier_low (c=0.35)", "marker": "square"},
    "tier_mid": {"color": "#2563EB", "label": "tier_mid (c=0.55)", "marker": "circle"},
    "tier_high": {"color": "#0D9488", "label": "tier_high (c=0.75)", "marker": "triangle"},
}

LEVELS = ("hard", "medium", "easy", "trivial")
LEVEL_RHO = {"hard": 0.25, "medium": 0.50, "easy": 0.75, "trivial": 0.90}


def _text(
    x: float,
    y: float,
    value: str,
    *,
    size: int = 15,
    weight: str = "400",
    fill: str = INK,
    anchor: str = "start",
    family: str = FONT,
) -> str:
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" font-family="{family}" font-size="{size}" '
        f'font-weight="{weight}" fill="{fill}" text-anchor="{anchor}">{html.escape(value)}</text>'
    )


def _marker(shape: str, x: float, y: float, color: str, size: float = 5.0) -> str:
    """Markers carry a ring in the surface color so overlaps stay readable."""

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
    """entries: (color, marker_shape, label). A legend is always present for >= 2 series."""

    parts: list[str] = []
    cursor = x
    for color, shape, label in entries:
        parts.append(_marker(shape, cursor + 6, y - 4, color))
        parts.append(_text(cursor + 18, y, label, size=14, fill=INK_SECONDARY))
        cursor += 20 + 8.0 * len(label) + 26
    return parts


def _rounded_bar(x: float, y: float, width: float, height: float, color: str) -> str:
    """Bar with 4px rounded data-end, square base, anchored to the baseline."""

    if height <= 0.5:
        return f'<rect x="{x:.1f}" y="{y - 1:.1f}" width="{width:.1f}" height="1.5" fill="{color}"/>'
    radius = min(4.0, width / 2, height)
    bottom = y + height
    return (
        f'<path d="M {x:.1f} {bottom:.1f} L {x:.1f} {y + radius:.1f} '
        f'Q {x:.1f} {y:.1f} {x + radius:.1f} {y:.1f} '
        f'L {x + width - radius:.1f} {y:.1f} '
        f'Q {x + width:.1f} {y:.1f} {x + width:.1f} {y + radius:.1f} '
        f'L {x + width:.1f} {bottom:.1f} Z" fill="{color}"/>'
    )


def _load() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    aggregate = json.loads((METRICS / "aggregate_metrics.json").read_text(encoding="utf-8"))
    monotonicity = json.loads(
        (METRICS / "monotonicity_and_reachability.json").read_text(encoding="utf-8")
    )
    degenerate = json.loads((METRICS / "degenerate_gap_report.json").read_text(encoding="utf-8"))
    # Fail loudly rather than draw a figure that disagrees with the artifacts.
    if aggregate["iterations_per_run"] != 10:
        raise ValueError("unexpected iterations_per_run")
    if aggregate["llm_designer_executed"] is not False:
        raise ValueError("figure captions assume no designer LLM was executed")
    if not degenerate["probe_summary"]["rho_hat_adm_invariant_across_V"]:
        raise ValueError("degenerate-gap figure assumes an invariant admissibility rate")
    return aggregate, monotonicity, degenerate


def write_gap_comparison(aggregate: dict[str, Any]) -> Path:
    per_level = {
        (row["designer"], row["difficulty_level"]): row for row in aggregate["per_level"]
    }
    width, height = 1080, 724
    plot_x, plot_y = 96, 176
    plot_w, plot_h = width - plot_x - 150, 296
    y_max = 40.0  # percent

    def y_of(percent: float) -> float:
        return plot_y + plot_h - (percent / y_max) * plot_h

    parts: list[str] = [
        f'<rect width="{width}" height="{height}" fill="{SURFACE}"/>',
        _text(plot_x, 52, "Held-out gap by target level and search strategy", size=25, weight="600"),
        _text(
            plot_x,
            80,
            "|rho_hat_task - rho| on a held-out instantiation of each strategy's selected configuration",
            size=15,
            fill=INK_SECONDARY,
        ),
        _text(
            plot_x,
            102,
            "Declared target surrogate tier_mid (c=0.55) - 256 tasks per instantiation - 10 iterations per run - no language model executed",
            size=13,
            fill=INK_MUTED,
        ),
    ]

    # Recessive gridlines and a single y axis.
    for tick in range(0, int(y_max) + 1, 10):
        y = y_of(tick)
        parts.append(
            f'<line x1="{plot_x}" y1="{y:.1f}" x2="{plot_x + plot_w}" y2="{y:.1f}" '
            f'stroke="{GRID}" stroke-width="1"/>'
        )
        parts.append(_text(plot_x - 12, y + 5, f"{tick}%", size=13, fill=INK_MUTED, anchor="end"))
    parts.append(
        f'<line x1="{plot_x}" y1="{plot_y + plot_h}" x2="{plot_x + plot_w}" '
        f'y2="{plot_y + plot_h}" stroke="{HAIRLINE}" stroke-width="1.5"/>'
    )

    group_w = plot_w / len(LEVELS)
    bar_w = 46.0
    gap = 2.0  # 2px surface gap between adjacent bars
    cluster_w = 3 * bar_w + 2 * gap
    for level_index, level in enumerate(LEVELS):
        cluster_x = plot_x + level_index * group_w + (group_w - cluster_w) / 2
        for series_index, (key, spec) in enumerate(SERIES.items()):
            row = per_level[(key, level)]
            value = 100.0 * float(row["holdout_gap"])
            bar_x = cluster_x + series_index * (bar_w + gap)
            bar_top = y_of(value)
            parts.append(
                _rounded_bar(bar_x, bar_top, bar_w, plot_y + plot_h - bar_top, spec["color"])
            )
            parts.append(
                _text(
                    bar_x + bar_w / 2,
                    bar_top - 9,
                    f"{value:.1f}",
                    size=13,
                    weight="600",
                    fill=INK,
                    anchor="middle",
                )
            )
        parts.append(
            _text(
                plot_x + level_index * group_w + group_w / 2,
                plot_y + plot_h + 28,
                level,
                size=16,
                weight="600",
                anchor="middle",
            )
        )
        parts.append(
            _text(
                plot_x + level_index * group_w + group_w / 2,
                plot_y + plot_h + 48,
                f"rho = {LEVEL_RHO[level]:.2f}",
                size=13,
                fill=INK_MUTED,
                anchor="middle",
            )
        )

    parts.extend(
        _legend(
            plot_x,
            140,
            [(spec["color"], spec["marker"], spec["label"]) for spec in SERIES.values()],
        )
    )

    # Mean summary strip: three fixed columns, so no label can overflow the panel.
    strip_y = plot_y + plot_h + 76
    strip_h = 104
    parts.append(
        f'<rect x="{plot_x}" y="{strip_y}" width="{plot_w}" height="{strip_h}" rx="10" '
        f'fill="{SURFACE_ALT}" stroke="{HAIRLINE}" stroke-width="1"/>'
    )
    parts.append(
        _text(
            plot_x + 20,
            strip_y + 28,
            "Mean gap across the four levels",
            size=14,
            weight="600",
        )
    )
    column_w = (plot_w - 40) / 3
    for column, row in enumerate(aggregate["designer_comparison"]):
        spec = SERIES[row["designer"]]
        column_x = plot_x + 20 + column * column_w
        parts.append(_marker(spec["marker"], column_x + 6, strip_y + 52, spec["color"]))
        parts.append(
            _text(column_x + 20, strip_y + 57, spec["label"], size=13, weight="600", fill=INK)
        )
        parts.append(
            _text(
                column_x + 20,
                strip_y + 80,
                f"search {row['mean_search_gap_pct']:.2f}%   "
                f"held-out {row['mean_holdout_gap_pct']:.2f}%",
                size=13,
                fill=INK_SECONDARY,
            )
        )

    parts.append(
        _text(
            plot_x,
            height - 22,
            "Lower is better. Values are exact and reproducible from per_level_metrics.csv; no confidence intervals were run.",
            size=13,
            fill=INK_MUTED,
        )
    )
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="Grouped bar chart of held-out gap by target level for three search strategies">'
        + "".join(parts)
        + "</svg>"
    )
    FIGURES.mkdir(parents=True, exist_ok=True)
    path = FIGURES / "betal_designer_gap_comparison.svg"
    path.write_text(svg + "\n", encoding="utf-8")
    return path


def write_difficulty_response(monotonicity: dict[str, Any]) -> Path:
    width, height = 1080, 684
    plot_x, plot_y = 96, 176
    plot_w, plot_h = width - plot_x - 230, 344

    def x_of(dial: float) -> float:
        return plot_x + dial * plot_w

    def y_of(rate: float) -> float:
        return plot_y + plot_h - rate * plot_h

    parts: list[str] = [
        f'<rect width="{width}" height="{height}" fill="{SURFACE}"/>',
        _text(plot_x, 52, "Difficulty response of the declared parameter space", size=25, weight="600"),
        _text(
            plot_x,
            80,
            "Observed rho_hat_task against the declared monotone dial through V, for three surrogate competence tiers",
            size=15,
            fill=INK_SECONDARY,
        ),
        _text(
            plot_x,
            102,
            "Dashed lines mark the four BeTaL target levels. A level is reachable for a tier only where that tier's curve crosses it.",
            size=13,
            fill=INK_MUTED,
        ),
    ]

    for tick in range(0, 11, 2):
        rate = tick / 10
        y = y_of(rate)
        parts.append(
            f'<line x1="{plot_x}" y1="{y:.1f}" x2="{plot_x + plot_w}" y2="{y:.1f}" '
            f'stroke="{GRID}" stroke-width="1"/>'
        )
        parts.append(_text(plot_x - 12, y + 5, f"{rate:.1f}", size=13, fill=INK_MUTED, anchor="end"))
    for level, rho in LEVEL_RHO.items():
        y = y_of(rho)
        parts.append(
            f'<line x1="{plot_x}" y1="{y:.1f}" x2="{plot_x + plot_w}" y2="{y:.1f}" '
            f'stroke="{INK_MUTED}" stroke-width="1.2" stroke-dasharray="6 5"/>'
        )
        parts.append(
            _text(plot_x + plot_w + 10, y + 5, f"{level} ({rho:.2f})", size=13, fill=INK_MUTED)
        )
    parts.append(
        f'<line x1="{plot_x}" y1="{plot_y + plot_h}" x2="{plot_x + plot_w}" '
        f'y2="{plot_y + plot_h}" stroke="{HAIRLINE}" stroke-width="1.5"/>'
    )
    for tick in range(0, 11, 2):
        dial = tick / 10
        parts.append(
            _text(
                x_of(dial),
                plot_y + plot_h + 26,
                f"{dial:.1f}",
                size=13,
                fill=INK_MUTED,
                anchor="middle",
            )
        )
    parts.append(
        _text(
            plot_x + plot_w / 2,
            plot_y + plot_h + 52,
            "declared difficulty dial through V  (0 = easy end of every dimension, 1 = hard end)",
            size=14,
            fill=INK_SECONDARY,
            anchor="middle",
        )
    )
    parts.append(
        _text(plot_x - 62, plot_y - 10, "rho_hat_task", size=14, weight="600", fill=INK_SECONDARY)
    )

    for check in monotonicity["checks"]:
        name = check["target_name"]
        spec = TIER_SERIES[name]
        points = [
            (x_of(row["dial"]), y_of(row["rho_hat_task"]))
            for row in check["rows"]
            if row["rho_hat_task"] is not None
        ]
        path_data = " ".join(
            ("M" if index == 0 else "L") + f" {x:.1f} {y:.1f}" for index, (x, y) in enumerate(points)
        )
        parts.append(
            f'<path d="{path_data}" fill="none" stroke="{spec["color"]}" stroke-width="2" '
            f'stroke-linejoin="round"/>'
        )
        for x, y in points:
            parts.append(_marker(spec["marker"], x, y, spec["color"], size=4.5))
        # Direct label placed where the three curves are well separated, so identity
        # never depends on color alone and the labels cannot collide.
        anchor_index = min(2, len(points) - 1)
        anchor_x, anchor_y = points[anchor_index]
        parts.append(
            _text(
                anchor_x + 12,
                anchor_y - 12,
                spec["label"],
                size=13,
                weight="600",
                fill=spec["color"],
            )
        )

    parts.extend(
        _legend(
            plot_x,
            140,
            [(spec["color"], spec["marker"], spec["label"]) for spec in TIER_SERIES.values()],
        )
    )

    violations = sum(check["strict_violations"] for check in monotonicity["checks"])
    comparisons = sum(max(0, len(check["rows"]) - 1) for check in monotonicity["checks"])
    parts.append(
        _text(
            plot_x,
            height - 40,
            f"{violations} local non-monotonicities in {comparisons} consecutive dial steps, "
            "consistent with binomial sampling noise at 256 tasks per instantiation.",
            size=13,
            fill=INK_MUTED,
        )
    )
    parts.append(
        _text(
            plot_x,
            height - 20,
            "Competence values are declared simulator constants, not measurements of any model.",
            size=13,
            fill=INK_MUTED,
        )
    )
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="Line chart of observed task rate against the declared difficulty dial for three surrogate tiers">'
        + "".join(parts)
        + "</svg>"
    )
    FIGURES.mkdir(parents=True, exist_ok=True)
    path = FIGURES / "betal_difficulty_response.svg"
    path.write_text(svg + "\n", encoding="utf-8")
    return path


def write_loop_diagram(degenerate: dict[str, Any]) -> Path:
    width, height = 1180, 800
    parts: list[str] = [
        '<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" '
        f'markerHeight="7" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" '
        f'fill="{INK_SECONDARY}"/></marker></defs>',
        f'<rect width="{width}" height="{height}" fill="{SURFACE}"/>',
        _text(60, 52, "BeTaL-GBI: parameter search with an admissibility gate", size=25, weight="600"),
        _text(
            60,
            80,
            "BeTaL Algorithm 1 over the GBI BoundaryBench admission boundary. The gate is the addition.",
            size=15,
            fill=INK_SECONDARY,
        ),
    ]

    def box(
        x: float,
        y: float,
        w: float,
        h: float,
        title: str,
        lines: Sequence[str],
        *,
        fill: str = SURFACE_ALT,
        stroke: str = HAIRLINE,
        title_fill: str = INK,
    ) -> None:
        parts.append(
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="14" fill="{fill}" '
            f'stroke="{stroke}" stroke-width="2"/>'
        )
        parts.append(_text(x + 18, y + 30, title, size=16, weight="600", fill=title_fill))
        for index, line in enumerate(lines):
            parts.append(_text(x + 18, y + 54 + index * 20, line, size=13, fill=INK_SECONDARY))

    def arrow(x1: float, y1: float, x2: float, y2: float, label: str | None = None) -> None:
        parts.append(
            f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{INK_SECONDARY}" '
            f'stroke-width="2.5" marker-end="url(#arrow)"/>'
        )
        if label:
            parts.append(
                _text(
                    (x1 + x2) / 2 + 8,
                    (y1 + y2) / 2 - 8,
                    label,
                    size=12,
                    weight="600",
                    fill=INK_MUTED,
                )
            )

    box(
        60,
        118,
        320,
        128,
        "1-2  Designer",
        [
            "Reads V, rho, and the iteration summary.",
            "Returns a JSON configuration proposal.",
            "LLM seam present; NOT_RUN in v0.2.",
        ],
        fill="#F0F9FF",
        stroke="#BAE0FD",
    )
    box(
        430,
        118,
        320,
        128,
        "3  Domain projection",
        [
            "Clamp, snap to the declared grid, coerce type.",
            "Unknown keys dropped and recorded.",
            "Every projection note is kept in the run record.",
        ],
    )
    box(
        800,
        118,
        320,
        128,
        "4  Simulator",
        [
            "Instantiates 256 synthetic legacy-EHR tasks",
            "across eight families, references derived",
            "from an explicit corruption manifest.",
        ],
    )
    box(
        800,
        290,
        320,
        128,
        "5  Target surrogate",
        [
            "Emits raw text per task.",
            "Boundary-floor or repaired-emitter surrogate.",
            "No language model is executed.",
        ],
    )
    box(
        430,
        290,
        320,
        128,
        "v0.1 Programmatic Verification Engine",
        [
            "Unmodified. Safe parse, schema, exact, graph,",
            "temporal, version, evidence, quarantine.",
            "The BeTaL layer never re-implements a criterion.",
        ],
        fill="#F0FDF4",
        stroke="#BBF7D0",
    )

    # The gate.
    box(
        430,
        462,
        690,
        112,
        "ADMISSIBILITY GATE     rho_hat_adm = admitted / task_count",
        [
            "rho_hat_adm >= 0.05  ->  the observed rate is a difficulty signal; continue the search.",
            "rho_hat_adm <  0.05  ->  the gap is UNDEFINED, not large. Stop, probe the dial, report the floor.",
        ],
        fill="#FEFCE8",
        stroke="#FDE68A",
    )

    box(
        60,
        618,
        500,
        140,
        "6-8  Gap, feedback, selection",
        [
            "g_i = |rho_hat_task - rho|  with rho_hat_task = verified / admitted.",
            "Append (v_i, rho_hat_i) to the summary for the next prompt.",
            "Keep the configuration with the smallest gap, then evaluate it",
            "on a held-out instantiation under a different split seed.",
        ],
        fill="#F0F9FF",
        stroke="#BAE0FD",
    )
    box(
        620,
        618,
        500,
        140,
        "Degenerate outcome (frozen v0.1 shape)",
        [
            "rho_hat_adm = 0.0 at every probed dial value, all three evidence modes.",
            "369 safe_parse_reject / 399 safe_schema_reject across 768 executions.",
            "No point in V raises the rate, so no parameter search is well posed.",
            "Correct action: repair the output-format boundary first.",
        ],
        fill="#FEF2F2",
        stroke="#FECACA",
    )

    # Arrow routing is explicit and non-crossing: each connector occupies its own
    # lane so no arrow passes through a box or collides with body text.
    arrow(380, 182, 428, 182)
    arrow(750, 182, 798, 182)
    arrow(960, 246, 960, 288)
    arrow(798, 354, 752, 354)
    arrow(775, 418, 775, 460)
    arrow(480, 576, 480, 614)
    parts.append(_text(492, 600, "gate open", size=12, weight="600", fill=INK_MUTED))
    arrow(870, 576, 870, 614)
    parts.append(_text(882, 600, "gate shut", size=12, weight="600", fill=INK_MUTED))
    arrow(140, 616, 140, 250)
    parts.append(_text(152, 440, "next iteration", size=12, weight="600", fill=INK_MUTED))

    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="Flow diagram of the BeTaL-GBI search loop with an admissibility gate">'
        + "".join(parts)
        + "</svg>"
    )
    FIGURES.mkdir(parents=True, exist_ok=True)
    path = FIGURES / "betal_gbi_loop.svg"
    path.write_text(svg + "\n", encoding="utf-8")
    return path


def main() -> int:
    aggregate, monotonicity, degenerate = _load()
    for path in (
        write_loop_diagram(degenerate),
        write_gap_comparison(aggregate),
        write_difficulty_response(monotonicity),
    ):
        print(f"wrote {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
