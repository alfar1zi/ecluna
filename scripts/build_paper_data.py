"""Emit the CSV files and position tables the LaTeX paper reads.

Every number here is copied from the JSON artefacts that the web page already
uses; nothing is recomputed. Run from the repository root:

    .venv/bin/python scripts/build_paper_data.py
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web" / "data"
OUT = ROOT / "paper" / "data"


def read(name: str) -> dict:
    return json.loads((WEB / name).read_text())


def write_csv(path: Path, header: list[str], rows: list[list[object]]) -> None:
    lines = [",".join(header)]
    lines += [",".join(str(c) for c in row) for row in rows]
    path.write_text("\n".join(lines) + "\n")


def completeness() -> None:
    data = read("completeness.json")
    rows = []
    for field in data["fields"]:
        for level in field["levels"]:
            rows.append(
                [
                    field["id"],
                    level["flux_mjy_sr"],
                    round(level["completeness"], 6),
                    round(level["wilson95"][0], 6),
                    round(level["wilson95"][1], 6),
                    level["injected"],
                    level["recovered"],
                ]
            )
    header = ["field", "flux", "completeness", "wilson_low", "wilson_high", "injected", "recovered"]
    write_csv(OUT / "completeness.csv", header, rows)
    for field in data["fields"]:
        per_field = [
            [level["flux_mjy_sr"], round(level["completeness"], 6),
             round(level["wilson95"][0], 6), round(level["wilson95"][1], 6)]
            for level in field["levels"]
        ]
        write_csv(
            OUT / f"completeness_{field['id']}.csv",
            ["flux", "completeness", "wilson_low", "wilson_high"],
            per_field,
        )

    summary = []
    for field in data["fields"]:
        summary.append(
            [
                field["id"],
                field["label"],
                field["visits"],
                field["tracks"],
                round(field["f50"], 4),
                round(field["f50_ci"][0], 4),
                round(field["f50_ci"][1], 4),
                round(field["threshold"], 4),
            ]
        )
    write_csv(
        OUT / "completeness_summary.csv",
        ["id", "label", "visits", "tracks", "f50", "f50_ci_hi", "f50_ci_lo", "threshold"],
        summary,
    )


def shift_stack() -> None:
    data = read("shift_stack.json")
    null = data["null"]
    rows = [
        ["median", 0.5, round(null["median"], 3)],
        ["p95", 0.05, round(null["p95"], 3)],
        ["p99", 0.01, round(null["p99"], 3)],
        ["p999", 0.001, round(null["p999"], 3)],
        ["max", 1.0 / null["n_draws"], round(null["max"], 3)],
    ]
    write_csv(OUT / "null_tail.csv", ["label", "tail_probability", "T"], rows)

    best = data["best_hypothesis"]
    verdict = data["threshold_verdict"]
    write_csv(
        OUT / "shift_stack_summary.csv",
        ["key", "value"],
        [
            ["n_draws", null["n_draws"]],
            ["n_evaluable", null["n_evaluable"]],
            ["seed", null["seed"]],
            ["p999", round(null["p999"], 3)],
            ["best_T", round(best["T"], 3)],
            ["best_rate_ra", round(best["rate_ra_arcsec_per_h"], 5)],
            ["best_rate_dec", round(best["rate_dec_arcsec_per_h"], 5)],
            ["p_value", round(verdict["empirical_p_value_of_best"], 6)],
            ["detection", str(verdict["detection"]).lower()],
        ],
    )


def parallax() -> None:
    data = read("parallax.json")
    rows = [[g["dist_au"], round(g["peak_shift_arcsec"], 2)] for g in data["geometry_full_baseline"]]
    write_csv(OUT / "parallax.csv", ["dist_au", "peak_shift_arcsec"], rows)

    horizon = data["half_field_arcsec"] * 400.0 / 997.21
    write_csv(
        OUT / "parallax_summary.csv",
        ["key", "value"],
        [
            ["baseline_days", data["baseline_days"]],
            ["pixel_scale_arcsec", data["pixel_scale_arcsec"]],
            ["half_field_arcsec", data["half_field_arcsec"]],
            ["horizon_au", round(horizon, 1)],
        ],
    )


def sky() -> None:
    patches = read("patches.json")
    views = read("views.json")
    rows = []
    for patch in patches["patches"]:
        rows.append(
            [
                "patch",
                patch["id"],
                patch["ra_deg"],
                patch["dec_deg"],
                round(patch["ecl_lat_deg"], 2),
                patch["n_dates"],
            ]
        )
    for obj in views["objects"]:
        rows.append(["object", obj["id"], obj["ra_deg"], obj["dec_deg"], "", obj["n_epochs"]])
    write_csv(OUT / "sky.csv", ["kind", "id", "ra_deg", "dec_deg", "ecl_lat_deg", "n"], rows)


def recovery() -> None:
    data = read("named_recovery_summary.json")
    rows = []
    for obj in data["objects"]:
        rows.append(
            [
                obj["id"],
                obj["evaluated_frame"],
                obj["verdict"].split(" (")[0],
                "" if obj["snr_3x3"] is None else round(obj["snr_3x3"], 3),
                round(obj["peak_snr"], 2),
                round(obj["peak_offset_px"], 2),
                round(obj["registration_scatter_px"], 3),
                str(obj["criteria"]["R1_pass"]).lower(),
                str(obj["criteria"]["R2_pass"]).lower(),
                str(obj["criteria"]["R3_pass"]).lower(),
                str(obj["criteria"]["R4_pass"]).lower(),
            ]
        )
    write_csv(
        OUT / "recovery.csv",
        ["id", "frame", "verdict", "snr_3x3", "peak_snr", "offset_px", "scatter_px", "R1", "R2", "R3", "R4"],
        rows,
    )


def candidates() -> None:
    views = read("views.json")
    rows = []
    for obj in views["objects"]:
        cands = obj.get("candidates") or []
        rows.append([obj["id"], obj["n_epochs"], len(cands)])
    write_csv(OUT / "candidates.csv", ["id", "n_epochs", "n_candidates"], rows)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    completeness()
    shift_stack()
    parallax()
    sky()
    recovery()
    candidates()
    for path in sorted(OUT.glob("*.csv")):
        print(path.relative_to(ROOT), path.stat().st_size)


if __name__ == "__main__":
    main()
