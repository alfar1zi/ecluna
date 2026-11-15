"""Build the two-panel figure the README shows, as SVG, from the JSON artefacts.

The figure is generated rather than drawn by hand so that it cannot drift from
the data: every coordinate comes from web/data/completeness.json and
web/data/shift_stack.json.

    .venv/bin/python scripts/build_readme_figure.py
"""

from __future__ import annotations

import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web" / "data"
OUT = ROOT / "docs" / "img" / "result.svg"

W, H = 1200, 520
BG = "#121212"
INK = "#e7e2d5"
MUTED = "#8f8f8f"
GRID = "#2a2a2a"
AMBER = "#e8a33d"
SLATE = "#8fb0c9"
GREY = "#9aa0a6"

FIELDS = [
    ("field-a", "Field A, 16 visits", SLATE),
    ("field-b", "Field B, 45 visits", AMBER),
    ("ecliptic-pole", "Ecliptic pole, 23 visits", GREY),
]


def log_scale(vmin: float, vmax: float, p0: float, p1: float):
    a, b = math.log10(vmin), math.log10(vmax)
    return lambda v: p0 + (math.log10(v) - a) / (b - a) * (p1 - p0)


def lin_scale(vmin: float, vmax: float, p0: float, p1: float):
    return lambda v: p0 + (v - vmin) / (vmax - vmin) * (p1 - p0)


def esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def text(x: float, y: float, body: str, size: int = 13, fill: str = INK,
         anchor: str = "start", weight: str = "400", spacing: str = "0") -> str:
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" font-family="Helvetica, Arial, sans-serif" '
        f'font-size="{size}" fill="{fill}" text-anchor="{anchor}" '
        f'font-weight="{weight}" letter-spacing="{spacing}">{esc(body)}</text>'
    )


def completeness_panel(comp: dict) -> list[str]:
    x0, x1, y0, y1 = 78, 560, 430, 96
    sx = log_scale(0.04, 1.0, x0, x1)
    sy = lin_scale(0.0, 1.0, y0, y1)
    out = [text(x0, 62, "COMPLETENESS", 12, MUTED, spacing="1.6")]

    for frac in (0.0, 0.25, 0.5, 0.75, 1.0):
        y = sy(frac)
        out.append(f'<line x1="{x0}" y1="{y:.1f}" x2="{x1}" y2="{y:.1f}" stroke="{GRID}" stroke-width="1"/>')
        out.append(text(x0 - 10, y + 4, f"{int(frac * 100)}%", 12, MUTED, "end"))

    for tick in (0.05, 0.1, 0.2, 0.4, 0.8):
        x = sx(tick)
        out.append(f'<line x1="{x:.1f}" y1="{y0}" x2="{x:.1f}" y2="{y1}" stroke="{GRID}" stroke-width="1"/>')
        out.append(text(x, y0 + 20, f"{tick:g}", 12, MUTED, "middle"))

    out.append(f'<line x1="{x0}" y1="{y0}" x2="{x1}" y2="{y0}" stroke="{MUTED}" stroke-width="1"/>')
    out.append(text((x0 + x1) / 2, y0 + 44, "injected flux, MJy per steradian", 12, MUTED, "middle"))

    for field_id, label, colour in FIELDS:
        field = next(f for f in comp["fields"] if f["id"] == field_id)
        levels = field["levels"]
        upper = " ".join(f"{sx(l['flux_mjy_sr']):.1f},{sy(l['wilson95'][1]):.1f}" for l in levels)
        lower = " ".join(f"{sx(l['flux_mjy_sr']):.1f},{sy(l['wilson95'][0]):.1f}" for l in reversed(levels))
        out.append(f'<polygon points="{upper} {lower}" fill="{colour}" fill-opacity="0.13" stroke="none"/>')
        pts = " ".join(f"{sx(l['flux_mjy_sr']):.1f},{sy(l['completeness']):.1f}" for l in levels)
        out.append(f'<polyline points="{pts}" fill="none" stroke="{colour}" stroke-width="2.2"/>')
        for l in levels:
            out.append(
                f'<circle cx="{sx(l["flux_mjy_sr"]):.1f}" cy="{sy(l["completeness"]):.1f}" '
                f'r="3.4" fill="{colour}"/>'
            )

    out.append(
        f'<line x1="{x0}" y1="{sy(0.5):.1f}" x2="{x1}" y2="{sy(0.5):.1f}" '
        f'stroke="{MUTED}" stroke-width="1" stroke-dasharray="5 4"/>'
    )

    legend_x = x0
    for _, label, colour in FIELDS:
        out.append(f'<line x1="{legend_x}" y1="82" x2="{legend_x + 16}" y2="82" stroke="{colour}" stroke-width="2.4"/>')
        out.append(text(legend_x + 22, 86, label, 12, INK))
        legend_x += 168
    return out


def null_panel(stack: dict) -> list[str]:
    x0, x1, y0, y1 = 700, 1140, 430, 96
    null = stack["null"]
    best = stack["threshold_verdict"]["best_T"]
    p999 = null["p999"]
    xmax = 2200.0
    sx = lin_scale(0.0, xmax, x0, x1)
    sy = log_scale(2e-4, 1.0, y0, y1)
    out = [text(x0, 62, "NULL TAIL", 12, MUTED, spacing="1.6")]

    for prob in (1.0, 0.1, 0.01, 0.001):
        y = sy(prob)
        out.append(f'<line x1="{x0}" y1="{y:.1f}" x2="{x1}" y2="{y:.1f}" stroke="{GRID}" stroke-width="1"/>')
        label = {1.0: "1", 0.1: "0.1", 0.01: "0.01", 0.001: "0.001"}[prob]
        out.append(text(x0 - 10, y + 4, label, 12, MUTED, "end"))

    for tick in (0, 500, 1000, 1500, 2000):
        x = sx(tick)
        out.append(f'<line x1="{x:.1f}" y1="{y0}" x2="{x:.1f}" y2="{y1}" stroke="{GRID}" stroke-width="1"/>')
        out.append(text(x, y0 + 20, f"{tick}", 12, MUTED, "middle"))

    out.append(f'<line x1="{x0}" y1="{y0}" x2="{x1}" y2="{y0}" stroke="{MUTED}" stroke-width="1"/>')
    out.append(text((x0 + x1) / 2, y0 + 44, "stack statistic T", 12, MUTED, "middle"))

    points = [
        (null["median"], 0.5),
        (null["p95"], 0.05),
        (null["p99"], 0.01),
        (null["p999"], 0.001),
        (null["max"], 1.0 / null["n_draws"]),
    ]
    pts = " ".join(f"{sx(t):.1f},{sy(p):.1f}" for t, p in points)
    out.append(f'<polyline points="{pts}" fill="none" stroke="{SLATE}" stroke-width="2.2"/>')
    for t, p in points:
        out.append(f'<circle cx="{sx(t):.1f}" cy="{sy(p):.1f}" r="3.4" fill="{SLATE}"/>')

    out.append(
        f'<line x1="{sx(best):.1f}" y1="{y1}" x2="{sx(best):.1f}" y2="{y0}" '
        f'stroke="{AMBER}" stroke-width="1.6" stroke-dasharray="6 4"/>'
    )
    out.append(text(sx(best) - 8, y1 + 16, f"best T {best:,.1f}", 12, AMBER, "end"))
    out.append(
        f'<line x1="{sx(p999):.1f}" y1="{y1}" x2="{sx(p999):.1f}" y2="{y0}" '
        f'stroke="{MUTED}" stroke-width="1.4" stroke-dasharray="3 4"/>'
    )
    out.append(text(sx(p999) + 8, y1 + 16, f"p99.9 {p999:,.1f}", 12, MUTED))

    out.append(text(x0, y0 + 62, "5,000 draws, 3,406 evaluable, seed 20261031", 12, MUTED))
    out.append(text(x0, y0 + 80, "the best stack sits below the threshold: no detection", 12, INK))
    return out


def main() -> None:
    comp = json.loads((WEB / "completeness.json").read_text())
    stack = json.loads((WEB / "shift_stack.json").read_text())

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
        f'viewBox="0 0 {W} {H}" role="img" '
        f'aria-label="Completeness per field and the empirical null tail with the best stack statistic">',
        f'<rect x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" rx="10" fill="{BG}" stroke="{GRID}"/>',
        text(78, 34, "Two measurements that bound the search", 17, INK, weight="600"),
    ]
    parts += completeness_panel(comp)
    parts += null_panel(stack)
    parts.append(
        text(78, H - 18, "source: web/data/completeness.json, web/data/shift_stack.json", 11, MUTED)
    )
    parts.append("</svg>")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(parts) + "\n")
    print(f"wrote {OUT.relative_to(ROOT)} ({OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
