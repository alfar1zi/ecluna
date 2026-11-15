"""Measure every target that has a visit series, and report what is missing.

One command so the whole set stays consistent: the same null, the same mask rule,
the same threshold reuse. Targets without a series are listed rather than skipped
silently.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = ROOT.parent / "ecluna" / "data"
# The named objects are recovered at a catalogue position; the survey fields are
# measured for a limit. They are different questions and different commands.
NAMED = ["wise0855", "barnard", "epsindib", "rwaur", "rdra"]
FIELDS = ["ecliptic-pole", "field-a", "field-b"]
TARGETS = NAMED + FIELDS


def run(command: list[str]) -> int:
    print(f"$ {' '.join(command)}", flush=True)
    return subprocess.run(command, cwd=ROOT).returncode


def series_for(target: str) -> pathlib.Path | None:
    for candidate in (DATA / "epochs_dr1" / target, DATA / "raw" / f"epochs_{target.replace('-', '_')}"):
        if candidate.is_dir() and list(candidate.glob("*.fits")):
            return candidate
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--targets", nargs="*", default=None)
    ap.add_argument("--mask-radius", type=int, default=30)
    ap.add_argument("--tracks", type=int, default=1200)
    ap.add_argument("--minimum-visits", type=int, default=6)
    args = ap.parse_args()

    python = str(ROOT / ".venv" / "bin" / "python")
    # The report accumulates: measuring one target must not erase the others, or
    # the table depends on which command was run last.
    path = ROOT / "results" / "measured_targets.json"
    report = {"measured": [], "skipped": []}
    if path.exists():
        try:
            report = json.loads(path.read_text())
        except json.JSONDecodeError:
            pass
    report.setdefault("measured", [])
    report.setdefault("skipped", [])
    touched = set(args.targets or TARGETS)
    report["measured"] = [r for r in report["measured"] if r["target"] not in touched]
    report["skipped"] = [r for r in report["skipped"] if r["target"] not in touched]
    for target in (args.targets or TARGETS):
        series = series_for(target)
        if series is None:
            report["skipped"].append({"target": target, "reason": "no series"})
            print(f"{target}: skipped, no series")
            continue
        count = len(list(series.glob("*.fits")))
        if count < args.minimum_visits:
            report["skipped"].append({"target": target,
                                      "reason": f"only {count} visits"})
            print(f"{target}: skipped, {count} visits")
            continue

        if target in NAMED:
            if run([python, "scripts/measure_recovery.py", "--target", target,
                    "--mask-radius", str(args.mask_radius),
                    "--tracks", str(args.tracks)]) != 0:
                report["skipped"].append({"target": target, "reason": "recovery failed"})
                continue
            entry = json.loads((ROOT / f"results/recovery_{target}.json").read_text())
            report["measured"].append({
                "target": target, "kind": "named",
                "visits": entry["visits"],
                "threshold": round(entry["threshold"], 2),
                "verdict": entry["recovery"]["verdict"],
                "snr": (round(entry["recovery"]["snr"], 1)
                        if entry["recovery"]["snr"] else None),
            })
        else:
            if run([python, "scripts/measure_series.py", "--target", target,
                    "--strips", str(series),
                    "--mask-radius", str(args.mask_radius),
                    "--tracks", str(args.tracks)]) != 0:
                report["skipped"].append({"target": target, "reason": "series failed"})
                continue
            entry = json.loads((ROOT / f"results/null_{target}.json").read_text())
            curve = json.loads((ROOT / f"results/completeness_{target}.json").read_text())
            report["measured"].append({
                "target": target, "kind": "field",
                "visits": entry["visits"],
                "threshold": round(entry["threshold"] if "threshold" in entry
                                   else entry["null"]["s_p95"], 2),
                "verdict": f"f50 {curve['curve']['f50']}",
                "snr": None,
            })

    report["measured"].sort(key=lambda r: r["target"])
    report["skipped"].sort(key=lambda r: r["target"])
    path.write_text(json.dumps(report, indent=1))
    print()
    print(f"{'target':14s} {'visits':>6s} {'threshold':>10s} {'sigma':>9s} verdict")
    for row in report["measured"]:
        snr = f"{row['snr']:.1f}" if row["snr"] else "-"
        print(f"{row['target']:14s} {row['visits']:6d} {row['threshold']:10.2f} "
              f"{snr:>9s} {row['verdict']}")
    for row in report["skipped"]:
        print(f"{row['target']:14s} skipped: {row['reason']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
