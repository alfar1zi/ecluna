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
        slug = name.replace("-", "_")
        curve_path = ROOT / "results" / f"completeness_{slug}.json"
        if not curve_path.exists():
            rows.append({"field": name, "measured": None,
                         "analytic": entry["limit"]["flux_limit_mjy_sr_px"],
                         "ratio": None, "status": "not measured"})
            continue
        curve = json.loads(curve_path.read_text())["curve"]
        measured = curve["f50"]
        analytic = entry["limit"]["flux_limit_mjy_sr_px"]
        ratio = analytic / measured if measured else None
        rows.append({"field": name, "measured": measured, "analytic": analytic,
                     "ratio": ratio,
                     "status": "measured" if measured else "no crossing"})

    out = {"rows": rows, "note": (
        "The analytic value assumes white noise and a Gaussian threshold. The "
        "measured value does not. A ratio far from one means the noise model is "
        "missing a term, and the measured value is the one to quote.")}
    (ROOT / "results" / "consistency.json").write_text(json.dumps(out, indent=1))

    print(f"{'field':16s} {'analytic':>10s} {'measured':>10s} {'ratio':>7s}")
    for row in rows:
        a = f"{row['analytic']:.4f}" if row["analytic"] else "-"
        m = f"{row['measured']:.4f}" if row["measured"] else "-"
        r = f"{row['ratio']:.2f}" if row["ratio"] else "-"
        print(f"{row['field']:16s} {a:>10s} {m:>10s} {r:>7s}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
