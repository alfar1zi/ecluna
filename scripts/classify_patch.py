"""Classify every source in a patch: known, unknown, and moving.

The catalog overlay is a subtractor, not a label. A source that Gaia already
lists is known; a source that Gaia does not list is a candidate, and a candidate
that also moves along a track is the only kind worth a second look.

Run from the ecluna-submit repository:

    .venv/bin/python scripts/classify_patch.py --target barnard
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

SERIES = ROOT.parent / "ecluna" / "data" / "epochs_dr1"
GAIA = ROOT.parent / "ecluna" / "results" / "cache"

# A Gaia match is a position, not a claim: the stack scatter is about 2.5 arcsec,
# so a tighter radius would reject real counterparts.
MATCH_ARCSEC = 6.0
DETECT_SIGMA = 8.0
BORDER_PX = 5
# A track only leaves the star when it sweeps more than the PSF. At 2.5 px of
# full width and n visits, a speed below 2.5/n keeps the track inside the same
# source, so a static star scores as high as a mover. The speeds tested start
# above that floor and the floor is written into the result.
PSF_FWHM_PX = 2.5


# The web id and the catalogue file differ for one object.
CATALOGUE = {"epsindib": "epsindb"}


def gaia_near(target: str) -> tuple[np.ndarray, np.ndarray]:
    path = GAIA / f"stars_gaia_named_{CATALOGUE.get(target, target)}.json"
    if not path.exists():
        raise SystemExit(f"no Gaia catalogue at {path}")
    stars = json.loads(path.read_text())["stars"]
    ra = np.array([s["ra"] for s in stars])
    dec = np.array([s["dec"] for s in stars])
    return ra, dec


def offset_arcsec(ra: np.ndarray, dec: np.ndarray,
                  cra: np.ndarray, cdec: np.ndarray) -> np.ndarray:
    dx = (ra - cra) * np.cos(np.radians(dec))
    dy = dec - cdec
    return np.hypot(dx, dy) * 3600.0


def resolve_threshold(target: str) -> tuple[float, str]:
    """The track threshold for one visit series, and where it came from.

    Four speeds are tested per source, so the per-trial false-alarm rate has to be
    a quarter of the quoted one: the 95th percentile used for a single trial would
    give a false candidate somewhere in almost every patch.
    """
    null_path = ROOT / "results" / f"null_{target}.json"
    recovery_path = ROOT / "results" / f"recovery_{target}.json"
    if null_path.exists():
        null = json.loads(null_path.read_text())["null"]
        return float(null["s_p99"]), "99th percentile of the measured null"
    if recovery_path.exists():
        base = float(json.loads(recovery_path.read_text())["threshold"])
        return base * 1.5, "1.5 times the measured 95th percentile"
    raise SystemExit(f"no threshold for {target}: run src.null first")


def classify(target: str, threshold: float, threshold_source: str) -> dict:
    from scipy.ndimage import maximum_filter

    from src.epochs import align, load_strips
    from src.null import track_statistic

    cube, variance, mjd, wcs = align(load_strips(SERIES / target),
                                     coverage_only=True)
    flat = cube - np.nanmedian(cube, axis=(1, 2))[:, None, None]
    stack = np.nanmedian(flat, axis=0)
    noise = float(1.4826 * np.nanmedian(np.abs(stack - np.nanmedian(stack))))

    peaks = ((stack == maximum_filter(np.nan_to_num(stack, nan=-1e9), size=3))
             & (stack > DETECT_SIGMA * noise))
    ys, xs = np.nonzero(peaks)
    ny, nx = stack.shape
    keep = ((xs > BORDER_PX) & (xs < nx - BORDER_PX)
            & (ys > BORDER_PX) & (ys < ny - BORDER_PX))
    xs, ys = xs[keep], ys[keep]

    ra, dec = wcs.pixel_to_world_values(xs.astype(float), ys.astype(float))
    gra, gdec = gaia_near(target)
    nearest = np.array([offset_arcsec(np.array([a]), np.array([b]), gra, gdec).min()
                        for a, b in zip(ra, dec)])
    in_catalog = nearest < MATCH_ARCSEC

    floor = PSF_FWHM_PX / cube.shape[0]
    speeds = tuple(round(floor * k, 4) for k in (2.0, 4.0, 8.0, 16.0))
    rows = []
    for i in range(len(xs)):
        # Speed zero is the stacked peak, not a track, so it cannot be evidence of
        # motion: every detected source scores high there. The comparison is only
        # between the moving speeds.
        best_speed, best_s = 0.0, -np.inf
        for speed in speeds:
            s = track_statistic(flat, variance, float(xs[i]), float(ys[i]),
                                speed, 0.0)
            if np.isfinite(s) and s > best_s:
                best_speed, best_s = speed, float(s)
        moving = best_s >= threshold
        if in_catalog[i]:
            verdict = "known star"
            if moving:
                verdict = "known star, moves as catalogued"
        elif moving:
            verdict = "candidate: not in the catalogue, and it moves"
        else:
            verdict = "not in the catalogue, does not move"
        rows.append({
            "x": int(xs[i]), "y": int(ys[i]),
            "ra_deg": round(float(ra[i]), 6), "dec_deg": round(float(dec[i]), 6),
            "peak_mjy_sr": round(float(stack[ys[i], xs[i]]), 6),
            "snr": round(float(stack[ys[i], xs[i]] / noise), 1),
            "nearest_catalogue_arcsec": round(float(nearest[i]), 2),
            "in_catalogue": bool(in_catalog[i]),
            "best_speed_px_per_visit": best_speed,
            "track_statistic": round(best_s, 2),
            "moving": bool(moving),
            "verdict": verdict,
        })

    counts = {}
    for r in rows:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
    return {
        "target": target,
        "visits": int(cube.shape[0]),
        "grid": [int(ny), int(nx)],
        "noise_mjy_sr": round(noise, 6),
        "detect_sigma": DETECT_SIGMA,
        "match_arcsec": MATCH_ARCSEC,
        "threshold": threshold,
        "threshold_source": threshold_source,
        "speed_floor_px_per_visit": round(float(floor), 4),
        "speeds_tested": [float(x) for x in speeds],
        "counts": counts,
        "sources": rows,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", required=True)
    ap.add_argument("--threshold", type=float, default=None,
                    help="track threshold; defaults to the measured null p95")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    if args.threshold is None:
        threshold, threshold_source = resolve_threshold(args.target)
    else:
        threshold, threshold_source = args.threshold, "given on the command line"

    out = classify(args.target, threshold, threshold_source)
    path = pathlib.Path(args.out or f"results/classified_{args.target}.json")
    path.write_text(json.dumps(out, indent=1))
    print(f"{args.target}: {len(out['sources'])} sources, noise {out['noise_mjy_sr']}")
    for k, v in sorted(out["counts"].items(), key=lambda kv: -kv[1]):
        print(f"  {v:4d}  {k}")
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
