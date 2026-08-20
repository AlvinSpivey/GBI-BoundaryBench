#!/usr/bin/env python3
"""Generate the GBI-DCSE v3 claim-coverage figure.

Reads only ``artifacts/public_results/gbi_dcse_v3/claim_register.json``.

Run from the repository root:

    python3 docs/betal/figure_sources/make_gbi_dcse_v3_figures.py
"""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[3]
METRICS = ROOT / "artifacts/public_results/gbi_dcse_v3"
FIGURES = ROOT / "docs/betal/figures"

FONT = "Inter, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif"
INK = "#172033"
INK_SECONDARY = "#475569"
INK_MUTED = "#64748B"
SURFACE = "#FFFFFF"
SURFACE_ALT = "#F8FAFC"
GRID = "#E2E8F0"
HAIRLINE = "#CBD5E1"

# Outcome palette, validated with the dataviz validator against surface #FFFFFF:
# lightness band PASS, all-pairs CVD separation PASS (worst deutan dE 20.7,
# tritan 15.6), normal-vision floor PASS (worst 24.4), contrast PASS.
#
# The validator reports one FAIL: the chroma floor on #94A3B8. That is deliberate
# and not a defect here. The chroma floor exists so a categorical series does not
# accidentally read as gray; in this figure "out of scope" is *meant* to read as a
# neutral, because it is the absence of a verdict rather than a third outcome
# competing for attention. Every segment also carries a direct count label, so
# identity never depends on colour alone.
OUTCOME = {
    "met": {"color": "#2563EB", "label": "Met"},
    "erratum": {"color": "#C2410C", "label": "Erratum (manuscript defect, corrected)"},
    "out_of_scope": {"color": "#94A3B8", "label": "Out of scope (never reported as met)"},
}

SECTION_ORDER = (
    ("1", "1  organizing picture"),
    ("2", "2  logit topology"),
    ("3", "3  boundary semantics"),
    ("4", "4  condensed probes"),
    ("5", "5  neuro-symbolic split"),
    ("6", "6  Dirichlet evidence"),
    ("7", "7  sheaves and cones"),
    ("8", "8  audit geometry"),
    ("9", "9  DCSE protocol"),
    ("10", "10  EHR application"),
    ("11", "11  BoundaryBench v0.1"),
    ("12", "12  containment"),
    ("A", "A  reference implementation"),
    ("B", "B  validation and targets"),
)


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


def _swatch(x: float, y: float, color: str) -> str:
    return (
        f'<rect x="{x:.1f}" y="{y:.1f}" width="14" height="14" rx="3" fill="{color}"/>'
    )


def _segment(x: float, y: float, width: float, height: float, color: str, *, first: bool, last: bool) -> str:
    """Stacked segment with 4px rounded outer ends and a 2px surface gap."""

    radius = 4.0
    if width <= 0.6:
        return ""
    left_r = radius if first else 0.0
    right_r = radius if last else 0.0
    return (
        f'<path d="M {x + left_r:.1f} {y:.1f} '
        f'L {x + width - right_r:.1f} {y:.1f} '
        f'{f"Q {x + width:.1f} {y:.1f} {x + width:.1f} {y + right_r:.1f}" if right_r else ""} '
        f'L {x + width:.1f} {y + height - right_r:.1f} '
        f'{f"Q {x + width:.1f} {y + height:.1f} {x + width - right_r:.1f} {y + height:.1f}" if right_r else ""} '
        f'L {x + left_r:.1f} {y + height:.1f} '
        f'{f"Q {x:.1f} {y + height:.1f} {x:.1f} {y + height - left_r:.1f}" if left_r else ""} '
        f'L {x:.1f} {y + left_r:.1f} '
        f'{f"Q {x:.1f} {y:.1f} {x + left_r:.1f} {y:.1f}" if left_r else ""} Z" fill="{color}"/>'
    )


def _load() -> dict[str, Any]:
    register = json.loads((METRICS / "claim_register.json").read_text(encoding="utf-8"))
    summary = register["summary"]
    if summary["total_claims"] != len(register["claims"]):
        raise ValueError("summary total does not match the claim list")
    if summary["met"] + summary["unmet"] + summary["out_of_scope"] != summary["total_claims"]:
        raise ValueError("register counts do not reconcile")
    # Fail loudly rather than draw a figure implying an out-of-scope claim was met.
    for claim in register["claims"]:
        if claim["class"] == "OUT_OF_SCOPE" and claim["met"] is not None:
            raise ValueError(f"{claim['id']}: out-of-scope claim reports a verdict")
    return register


def write_coverage(register: dict[str, Any]) -> Path:
    claims = register["claims"]
    summary = register["summary"]

    buckets: dict[str, dict[str, int]] = {
        key: {"met": 0, "erratum": 0, "out_of_scope": 0} for key, _ in SECTION_ORDER
    }
    for claim in claims:
        top = claim["section"].split(".")[0].split(" ")[0]
        if top not in buckets:
            raise ValueError(f"{claim['id']}: unmapped section {claim['section']!r}")
        if claim["met"] is None:
            buckets[top]["out_of_scope"] += 1
        elif claim["met"] is True:
            buckets[top]["met"] += 1
        else:
            buckets[top]["erratum"] += 1

    max_total = max(sum(bucket.values()) for bucket in buckets.values())
    width, height = 1180, 892
    label_x = 44
    plot_x = 300
    plot_w = 660
    row_h = 30.0
    row_gap = 8.0
    plot_y = 218

    def x_of(count: float) -> float:
        return plot_x + (count / max_total) * plot_w

    parts: list[str] = [
        f'<rect width="{width}" height="{height}" fill="{SURFACE}"/>',
        _text(label_x, 52, "Every main.pdf claim, enumerated and scored", size=25, weight="600"),
        _text(
            label_x,
            80,
            f"{summary['total_claims']} claims across sections 1-12 and appendices A-B. "
            f"{summary['met']} of {summary['testable_in_this_environment']} testable claims met.",
            size=15,
            fill=INK_SECONDARY,
        ),
        _text(
            label_x,
            102,
            "No language model, TEE, BFT cluster, FHIR server or zero-knowledge prover is present. Synthetic data only.",
            size=13,
            fill=INK_MUTED,
        ),
    ]

    # Legend, above the plot so it cannot collide with the bars.
    cursor = label_x
    for key in ("met", "erratum", "out_of_scope"):
        spec = OUTCOME[key]
        parts.append(_swatch(cursor, 132, spec["color"]))
        parts.append(_text(cursor + 21, 144, spec["label"], size=14, fill=INK_SECONDARY))
        cursor += 30 + 7.4 * len(spec["label"])

    # Count gridlines.
    plot_bottom = plot_y + len(SECTION_ORDER) * (row_h + row_gap)
    for tick in range(0, max_total + 1, 4):
        x = x_of(tick)
        parts.append(
            f'<line x1="{x:.1f}" y1="{plot_y - 10:.1f}" x2="{x:.1f}" y2="{plot_bottom:.1f}" '
            f'stroke="{GRID}" stroke-width="1"/>'
        )
        parts.append(_text(x, plot_y - 18, str(tick), size=12, fill=INK_MUTED, anchor="middle"))
    parts.append(_text(plot_x, plot_y - 40, "claims", size=13, weight="600", fill=INK_SECONDARY))

    for index, (key, label) in enumerate(SECTION_ORDER):
        row_y = plot_y + index * (row_h + row_gap)
        bucket = buckets[key]
        parts.append(
            _text(plot_x - 16, row_y + row_h / 2 + 5, label, size=14, fill=INK, anchor="end")
        )
        order = [name for name in ("met", "erratum", "out_of_scope") if bucket[name] > 0]
        offset = 0.0
        for position, name in enumerate(order):
            count = bucket[name]
            seg_x = x_of(offset) + (2.0 if position else 0.0)
            seg_w = x_of(offset + count) - x_of(offset) - (2.0 if position else 0.0)
            parts.append(
                _segment(
                    seg_x,
                    row_y,
                    seg_w,
                    row_h,
                    OUTCOME[name]["color"],
                    first=position == 0,
                    last=position == len(order) - 1,
                )
            )
            if seg_w >= 18:
                parts.append(
                    _text(
                        seg_x + seg_w / 2,
                        row_y + row_h / 2 + 5,
                        str(count),
                        size=13,
                        weight="600",
                        fill=SURFACE,
                        anchor="middle",
                    )
                )
            offset += count
        total = sum(bucket.values())
        parts.append(
            _text(
                x_of(total) + 12,
                row_y + row_h / 2 + 5,
                f"{bucket['met']}/{total}",
                size=13,
                fill=INK_MUTED,
            )
        )

    # Footer: name the exceptions rather than leaving them as a colour.
    strip_y = plot_bottom + 24
    parts.append(
        f'<rect x="{label_x}" y="{strip_y}" width="{width - 2 * label_x}" height="82" rx="10" '
        f'fill="{SURFACE_ALT}" stroke="{HAIRLINE}" stroke-width="1"/>'
    )
    parts.append(_text(label_x + 20, strip_y + 28, "The four exceptions, named", size=14, weight="600"))
    exceptions = [claim for claim in claims if claim["met"] is not True]
    detail = "   ".join(
        f"{claim['id']} ({claim['class'].replace('_', ' ').lower()})" for claim in exceptions
    )
    parts.append(_text(label_x + 20, strip_y + 52, detail, size=13, fill=INK_SECONDARY))
    parts.append(
        _text(
            label_x + 20,
            strip_y + 72,
            "C-6.6: the Sec. 6.3 evidence-box bound holds only on the swept slice, not over the box.   "
            "C-9.16 / C-B1.7 / C-B2.4: need a ZK prover, a clinical cohort, and a TEE.",
            size=12,
            fill=INK_MUTED,
        )
    )

    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="Stacked bar chart of main.pdf claims met, errata and out-of-scope, by manuscript section">'
        + "".join(parts)
        + "</svg>"
    )
    FIGURES.mkdir(parents=True, exist_ok=True)
    path = FIGURES / "gbi_dcse_v3_claim_coverage.svg"
    path.write_text(svg + "\n", encoding="utf-8")
    return path


def main() -> int:
    register = _load()
    path = write_coverage(register)
    print(f"wrote {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
