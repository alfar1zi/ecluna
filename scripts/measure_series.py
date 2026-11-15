"""Measure the visit series of one target: null calibration and completeness.

Two commands per target, in order, so every series is measured the same way:

  python scripts/measure_series.py --target wise0855

The null is calibrated first and the completeness curve reads its threshold, so
one field never ends up with two thresholds from two different sample sizes.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


def run(command: list[str]) -> int:
    print(f"$ {' '.join(command)}", flush=True)
    return subprocess.run(command, cwd=ROOT).returncode


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", required=True)
    ap.add_argument("--strips", default=None,
                    help="series directory; defaults to the DR1 cutouts")
    ap.add_argument("--tracks", type=int, default=1500)
    ap.add_argument("--per-level", type=int, default=40)
    ap.add_argument("--fluxes", default="0.02,0.05,0.10,0.20,0.40,0.80")
    ap.add_argument("--max-speed", type=float, default=None,
                    help="largest motion in pixels per visit; the default fits the "
                         "frame, which is too generous for a fragmented footprint")
    ap.add_argument("--mask-radius", type=int, default=0,
                    help="blank this half-width around the grid centre; needed for "
                         "a stamp cut on a bright star")
    args = ap.parse_args()

    strips = pathlib.Path(args.strips) if args.strips else (
        DATA / "epochs_dr1" / args.target)
    if not strips.is_dir():
        print(f"no series at {strips}", file=sys.stderr)
        return 1

    python = str(ROOT / ".venv" / "bin" / "python")
    null_out = f"results/null_{args.target}.json"
    curve_out = f"results/completeness_{args.target}.json"

    speed = [] if args.max_speed is None else ["--max-speed", str(args.max_speed)]
    if run([python, "-m", "src.null", "--field", args.target,
            "--strips", str(strips), "--tracks", str(args.tracks),
            "--mask-radius", str(args.mask_radius), *speed,
            "--out", null_out]) != 0:
        return 1

    if run([python, "-m", "src.inject", "--field", args.target,
            "--strips", str(strips), "--per-level", str(args.per_level),
            "--fluxes", args.fluxes, "--null", null_out, *speed,
            "--out", curve_out]) != 0:
        return 1

    curve = json.loads((ROOT / curve_out).read_text())
    null = json.loads((ROOT / null_out).read_text())
    print(f"{args.target}: {curve['curve']['visits']} visits, "
          f"threshold {curve['threshold']:.2f}, f50 {curve['curve']['f50']}, "
          f"noise scale {null['noise_scale']['scale']:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
