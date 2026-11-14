"""Recover a named object from its own visit series.

For a field centred on a bright star, a detection limit measured in that field is
dominated by the star's wings and says little. The question the challenge asks is
different and sharper: given the visits we have, does the pipeline find the object
at the position its own catalogue gives? That is a recovery test, and it is the
same check the known-object control runs on Gaia stars.

Usage:
  python scripts/measure_recovery.py --target wise0855 --mask-radius 45
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = ROOT / "data"

TARGETS = {
    "wise0855": (133.795129, -7.245147),
    "barnard": (269.452077, 4.693365),
    "epsindib": (331.044147, -56.782844),
    "rwaur": (76.956526, 30.401438),
    "rdra": (248.167611, 66.754979),
}



def recorded_path(path: str) -> str:
    """The path as it should appear in a result.

    A result is published, so it must not carry the operator's home directory. The
    path is recorded relative to the data root when it sits under it, and by its
    last two components otherwise, which is enough to say which series was read.
    """
    import os
    import pathlib as _pathlib

    root = os.environ.get("DATA_ROOT")
    resolved = _pathlib.Path(path).resolve()
    if root:
        try:
            return str(resolved.relative_to(_pathlib.Path(root).resolve().parent))
        except ValueError:
            pass
    parts = resolved.parts
    return "/".join(parts[-2:]) if len(parts) >= 2 else str(resolved)

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", required=True, choices=sorted(TARGETS))
    ap.add_argument("--mask-radius", type=int, default=0)
    ap.add_argument("--radius", type=int, default=3)
    ap.add_argument("--tracks", type=int, default=1000)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    from src.controls import recover
    from src.controls import check_criteria
    from src.epochs import align, load_strips
    from src.null import calibrate

    ra, dec = TARGETS[args.target]
    strips = DATA / "epochs_dr1" / args.target
    series = load_strips(strips)
    cube, variance, mjd, wcs = align(series, coverage_only=True, centre=(ra, dec))
    # The mask cannot be wider than a third of the frame, or it blanks the frame
    # instead of the target: 45 pixels on an 88 x 108 cube removed everything.
    mask = args.mask_radius
    if mask:
        mask = min(mask, min(cube.shape[1], cube.shape[2]) // 3)
    null = calibrate(cube, variance, args.target, tracks=args.tracks,
                     mask_radius_px=mask)

    result = recover(cube, variance, wcs, args.target, ra, dec, null.s_p95,
                     search_radius_px=args.radius)

    payload = {
        "target": args.target,
        "ra_deg": ra,
        "dec_deg": dec,
        "visits": int(cube.shape[0]),
        "mjd_first": float(mjd[0]),
        "mjd_last": float(mjd[-1]),
        "threshold": float(null.s_p95),
        "threshold_ci": list(null.p95_ci),
        "noise_scale": float(null.noise_scale["scale"]) if hasattr(null, "noise_scale") else None,
        "mask_radius": mask,
        "recovery": result.as_dict(),
        "criteria_sha256": check_criteria(),
        "source": {"strips": recorded_path(str(strips)), "visits_used": int(cube.shape[0])},
    }
    out = args.out or f"results/recovery_{args.target}.json"
    pathlib.Path(ROOT / out).write_text(json.dumps(payload, indent=1))
    print(f"{args.target}: {result.verdict} | {result.reason}")
    print(f"  visits {cube.shape[0]}, threshold {null.s_p95:.2f}, "
          f"written {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
