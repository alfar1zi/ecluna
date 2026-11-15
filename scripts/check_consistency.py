"""Compare the analytic limit with the measured one, and report the ratio.

The analytic limit comes from the archive variance and a Gaussian threshold. The
measured limit comes from injecting sources and counting what comes back. They
are built from different assumptions, so they will not agree exactly. This prints
the ratio so a disagreement is visible instead of being averaged away.
"""

from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]


def main() -> int:
    diagnosis = json.loads((ROOT / "results" / "diagnosis_fields.json").read_text())
    rows = []
    for name, entry in diagnosis["fields"].items():
        # The measurement writes the field name as it is, hyphens included. The
        # underscore form is only a fallback for results written before the names
        # were unified, and it is tried second so a stale file cannot win.
        curve_path = ROOT / "results" / f"completeness_{name}.json"
        if not curve_path.exists():
            curve_path = ROOT / "results" / f"completeness_{name.replace('-', '_')}.json"
        if not curve_path.exists():
            rows.append({"field": name, "measured": None,
                         "analytic": entry["limit"]["flux_limit_mjy_sr_px"],
                         "analytic_visits": entry["limit"]["visits"],
                         "ratio": None, "status": "not measured"})
            continue
        curve = json.loads(curve_path.read_text())["curve"]
        measured = curve["f50"]
        analytic = entry["limit"]["flux_limit_mjy_sr_px"]
        ratio = analytic / measured if measured else None
        rows.append({"field": name, "measured": measured, "analytic": analytic,
                     "analytic_visits": entry["limit"]["visits"],
                     "ratio": ratio,
                     "status": "measured" if measured else "no crossing"})

    # The analytic limit is computed for the number of visits the archive lists;
    # the measurement uses the frames that were actually acquired. Those are not
    # the same number, and the limit falls as 1/sqrt(visits), so comparing them
    # without correcting is comparing two different experiments. The analytic value
    # is rescaled to the measured visit count before the ratio is taken.
    detail = []
    for row in rows:
        if row["measured"] is None:
            continue
        null_path = ROOT / "results" / f"null_{row['field']}.json"
        curve_path = ROOT / "results" / f"completeness_{row['field']}.json"
        if not null_path.exists() or not curve_path.exists():
            continue
        null = json.loads(null_path.read_text())["null"]
        curve = json.loads(curve_path.read_text())["curve"]
        visits_analytic = row["analytic_visits"]
        visits_measured = curve["visits"]
        factor = (visits_analytic / visits_measured) ** 0.5
        rescaled = row["analytic"] * factor
        row["analytic_at_measured_visits"] = rescaled
        row["ratio_at_measured_visits"] = (
            rescaled / row["measured"] if row["measured"] else None)
        # The two numbers sit at different false-positive rates, and that is the
        # whole difference. The analytic value cuts at 5 sigma, which admits about
        # 3e-7 of the noise; the measurement cuts at the p95 of the null, which
        # admits 5 percent. A looser cut reaches fainter flux, so the measured
        # limit is the lower of the two by construction. The rates are recorded so
        # the comparison is read as two operating points, not as a disagreement.
        row["analytic_false_positive_rate"] = 2.87e-7
        row["measured_false_positive_rate"] = 0.05
        detail.append({
            "field": row["field"],
            "visits_analytic": visits_analytic,
            "visits_measured": visits_measured,
            "rescale_factor": round(factor, 3),
            "analytic_threshold_sigma": 5.0,
            "measured_threshold_sigma": round(null["s_p95"] / null["s_sigma"], 2),
            "noise_scale": round(
                json.loads(null_path.read_text())["noise_scale"]["scale"], 2),
        })

    out = {"rows": rows, "detail": detail, "note": (
        "The analytic limit is rescaled to the measured visit count before the "
        "ratio is taken, because the limit falls as 1/sqrt(visits) and the archive "
        "lists more visits than were acquired. What remains is the difference "
        "between a 5 sigma Gaussian cut on the archive variance and the empirical "
        "p95 of the null on the measured scatter. The measured value is the one to "
        "quote; the analytic value is a cross-check, not a second measurement. The "
        "two also sit at different false-positive rates: the analytic cut at 5 sigma "
        "admits about 3e-7 of the noise, the measured cut at the p95 admits 5 "
        "percent. A looser cut reaches fainter flux, so the measured limit is lower "
        "by construction, and the ratio is the price of the looser cut rather than a "
        "disagreement between two estimates of one number.")}
    (ROOT / "results" / "consistency.json").write_text(json.dumps(out, indent=1))

    print(f"{'field':16s} {'analytic':>9s} {'at N':>9s} {'measured':>9s} "
          f"{'ratio':>6s}  {'fpr':>9s}")
    for row in rows:
        a = f"{row['analytic']:.4f}" if row["analytic"] else "-"
        b = (f"{row['analytic_at_measured_visits']:.4f}"
             if row.get("analytic_at_measured_visits") else "-")
        m = f"{row['measured']:.4f}" if row["measured"] else "-"
        r = (f"{row['ratio_at_measured_visits']:.2f}"
             if row.get("ratio_at_measured_visits") else "-")
        print(f"{row['field']:16s} {a:>9s} {b:>9s} {m:>9s} {r:>6s}  "
              f"{'5e-2/3e-7':>9s}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
