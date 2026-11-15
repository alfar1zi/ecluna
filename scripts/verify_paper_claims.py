"""Check that numbers typed into paper/paper.tex still match their source JSON.

The paper quotes values that were copied by hand from artefacts. This script
re-derives each one from the artefact and fails when the text disagrees, so a
later change to the data cannot silently leave the paper stale.

Run from the repository root:

    .venv/bin/python scripts/verify_paper_claims.py

Exit code 0 means every checked string is present with the expected value.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEX = ROOT / "paper" / "paper.tex"
WEB = ROOT / "web" / "data"


def load(name: str) -> dict:
    return json.loads((WEB / name).read_text())


def main() -> int:
    text = TEX.read_text()
    failures: list[str] = []
    checked = 0

    def expect(label: str, needle: str, source: str) -> None:
        nonlocal checked
        checked += 1
        if needle not in text:
            failures.append(f"{label}: missing {needle!r} (source {source})")

    comp = load("completeness.json")
    for field in comp["fields"]:
        f50 = f"{field['f50']:.3f}"
        expect(f"{field['id']} f50", f50, "web/data/completeness.json")

    expected_at_02 = {"field-a": "60\\%", "field-b": "15\\%", "ecliptic-pole": "37.5\\%"}
    for field in comp["fields"]:
        for level in field["levels"]:
            if abs(level["flux_mjy_sr"] - 0.2) < 1e-9:
                got = f"{100 * level['completeness']:.4g}"
                want = expected_at_02[field["id"]].replace("\\%", "")
                if abs(float(got) - float(want)) > 0.05:
                    failures.append(
                        f"{field['id']} completeness at 0.2: paper says {want}%, "
                        f"source says {got}%"
                    )
                checked += 1

    parallax = load("parallax.json")
    geom_400 = next(g for g in parallax["geometry_full_baseline"] if g["dist_au"] == 400.0)
    expect("shift at 400 AU", f"{geom_400['peak_shift_arcsec']:.2f}", "web/data/parallax.json")
    half_field = parallax["half_field_arcsec"]
    horizon = geom_400["dist_au"] * geom_400["peak_shift_arcsec"] / half_field
    if abs(horizon - 2219.0) > 1.0:
        failures.append(f"horizon from geometry is {horizon:.1f} AU, paper says 2219")
    expect("horizon", "2{,}219", "derived from web/data/parallax.json")

    stack = load("shift_stack.json")
    null = stack["null"]
    best = stack["best_hypothesis"]
    verdict = stack["threshold_verdict"]
    for key, value, digits in [
        ("null median", null["median"], 1),
        ("null p95", null["p95"], 1),
        ("null p99", null["p99"], 1),
        ("null p999", null["p999"], 1),
        ("best T", best["T"], 1),
    ]:
        expect(key, f"{value:.{digits}f}", "web/data/shift_stack.json")
    expect("best T truncated", "1843.8", "web/data/shift_stack.json")
    expect("p999 truncated", "1892.1", "web/data/shift_stack.json")
    expect("p value", f"{verdict['empirical_p_value_of_best'] * 1e3:.2f}", "web/data/shift_stack.json")
    expect("n evaluable", f"{null['n_evaluable']:,}".replace(",", "{,}"), "web/data/shift_stack.json")
    expect("n draws", "5{,}000", "web/data/shift_stack.json")
    expect("seed", str(null["seed"]), "web/data/shift_stack.json")
    grid = stack["requested_grid_feasibility"]
    expect("n hypotheses", f"{grid['grid']['n_hypotheses']:,}".replace(",", "{,}"), "web/data/shift_stack.json")
    expect("max rate", f"{grid['max_rate_keeping_full_overlap_arcsec_per_h']:.4f}", "web/data/shift_stack.json")

    summary = stack["sensitivity_region_size"]
    expect("sensitivity T", f"{summary['best_T']:.1f}", "web/data/shift_stack.json")

    recovery = load("named_recovery_summary.json")
    expect("n recovered", f"{recovery['summary']['n_recovered']}", "web/data/named_recovery_summary.json")
    for obj in recovery["objects"]:
        expect(f"{obj['id']} peak snr", f"{obj['peak_snr']:.2f}", "web/data/named_recovery_summary.json")
        expect(f"{obj['id']} scatter", f"{obj['registration_scatter_px']:.3f}", "web/data/named_recovery_summary.json")

    views = load("views.json")
    moving_key = "candidate: not in the catalogue, and it moves"
    total_candidates = sum(
        (o.get("candidates") or {}).get("counts", {}).get(moving_key, 0)
        for o in views["objects"]
    )
    if total_candidates != 16:
        failures.append(f"candidate total is {total_candidates}, paper says 16")
    expect("candidate total", "returns $16$ candidate", "web/data/views.json")
    total_epochs = sum(o["n_epochs"] for o in views["objects"])
    if total_epochs != 258:
        failures.append(f"frame total is {total_epochs}, paper says 258")
    expect("frame total", "$258$", "web/data/views.json")

    injection = load("injection.json")
    expect("noise", f"{injection['robust_sigma_mjy_sr']:.3f}", "web/data/injection.json")
    expect("psf", f"{injection['psf_fwhm_px']:.1f}", "web/data/injection.json")

    print(f"checked {checked} strings against source artefacts")
    if failures:
        print("FAIL")
        for line in failures:
            print("  " + line)
        return 1
    print("PASS: every quoted value matches its source")
    return 0


if __name__ == "__main__":
    sys.exit(main())
