"""Recover a known object at its predicted position.

Before the pipeline can be trusted with an unknown object, it has to find an object
whose position is already known. This measures the recovered flux at the predicted
position and compares it with the noise there, so the answer is a signal-to-noise
ratio and a flux, not a yes.

Three outcomes are possible and they mean different things:

  recovered     a source is present at the predicted position, above the threshold
  below limit   the position is correct but the object is fainter than we can see
  not in field  the prediction falls outside the frames we have

The middle case is a result, not a failure: it says the object is too faint for
this visit set, which is exactly the kind of statement the product makes.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict

import numpy as np


@dataclass
class Recovery:
    name: str
    ra_deg: float
    dec_deg: float
    in_field: bool
    visits_used: int
    offset_px: tuple[float, float] | None
    peak_mjy_sr: float | None
    noise_mjy_sr: float | None
    snr: float | None
    verdict: str
    reason: str

    def as_dict(self) -> dict:
        d = asdict(self)
        if self.offset_px:
            d["offset_px"] = list(self.offset_px)
        return d


def local_noise(variance_plane: np.ndarray, x: int, y: int, box: int = 15) -> float | None:
    """Median per-pixel noise in a box around a position."""
    ny, nx = variance_plane.shape
    half = box // 2
    x0, x1 = max(0, x - half), min(nx, x + half + 1)
    y0, y1 = max(0, y - half), min(ny, y + half + 1)
    patch = variance_plane[y0:y1, x0:x1]
    good = patch[np.isfinite(patch) & (patch > 0)]
    if good.size < 20:
        return None
    return float(np.sqrt(np.median(good)))


def peak_near(cube: np.ndarray, x: int, y: int, radius: int = 3) -> tuple[float, int, int]:
    """Stack the visits and take the brightest pixel within a radius.

    The stack is the mean over visits, because the object is at the same place in
    every visit here: a known object is fixed on the sky for the purpose of this
    check, and any motion is handled by the caller's prediction.
    """
    stack = np.nanmean(cube, axis=0)
    ny, nx = stack.shape
    x0, x1 = max(0, x - radius), min(nx, x + radius + 1)
    y0, y1 = max(0, y - radius), min(ny, y + radius + 1)
    patch = stack[y0:y1, x0:x1]
    if not np.isfinite(patch).any():
        return float("nan"), x, y
    iy, ix = np.unravel_index(np.nanargmax(patch), patch.shape)
    return float(patch[iy, ix]), x0 + ix, y0 + iy


def recover(cube: np.ndarray, variance: np.ndarray, wcs, name: str,
            ra_deg: float, dec_deg: float, threshold: float,
            search_radius_px: int = 3) -> Recovery:
    """Look for a known object at its predicted position."""
    from astropy.wcs import WCS

    ny, nx = cube.shape[1], cube.shape[2]
    x, y = wcs.world_to_pixel_values(ra_deg, dec_deg)
    x, y = float(x[0] if np.ndim(x) else x), float(y[0] if np.ndim(y) else y)
    margin = search_radius_px + 2
    if not (margin <= x < nx - margin and margin <= y < ny - margin):
        return Recovery(name=name, ra_deg=ra_deg, dec_deg=dec_deg, in_field=False,
                        visits_used=0, offset_px=None, peak_mjy_sr=None,
                        noise_mjy_sr=None, snr=None, verdict="not in field",
                        reason=f"predicted position ({x:.0f}, {y:.0f}) is outside "
                               f"the {nx} x {ny} grid")

    flat = cube - np.nanmedian(cube, axis=(1, 2))[:, None, None]
    peak, px, py = peak_near(flat, int(round(x)), int(round(y)),
                             radius=search_radius_px)
    noise = local_noise(np.nanmedian(variance, axis=0), px, py)
    if noise is None or not np.isfinite(peak):
        return Recovery(name=name, ra_deg=ra_deg, dec_deg=dec_deg, in_field=True,
                        visits_used=int(cube.shape[0]), offset_px=(px - x, py - y),
                        peak_mjy_sr=None, noise_mjy_sr=None, snr=None,
                        verdict="not measurable", reason="no usable variance there")

    # The stack averages n visits, so the noise on the stack is the per-pixel noise
    # divided by the square root of the number of visits.
    noise_stack = noise / np.sqrt(cube.shape[0])
    snr = float(peak / noise_stack)
    offset = (float(px - x), float(py - y))
    if snr >= threshold:
        verdict = "recovered"
        reason = f"peak {peak:.4f} MJy/sr is {snr:.1f} sigma above the local noise"
    else:
        verdict = "below limit"
        reason = (f"peak {peak:.4f} MJy/sr is only {snr:.1f} sigma, below the "
                  f"{threshold:.1f} sigma threshold for this visit set")
    return Recovery(name=name, ra_deg=ra_deg, dec_deg=dec_deg, in_field=True,
                    visits_used=int(cube.shape[0]), offset_px=offset,
                    peak_mjy_sr=float(peak), noise_mjy_sr=float(noise_stack),
                    snr=snr, verdict=verdict, reason=reason)


def _cli() -> int:
    import argparse
    import json
    import pathlib

    from src.epochs import align, load_strips
    from src.null import calibrate

    ap = argparse.ArgumentParser(description="recover known objects in one field")
    ap.add_argument("--strips", required=True)
    ap.add_argument("--visits", type=int, default=0,
                    help="cap the visit count; 0 uses every strip covering the centre")
    ap.add_argument("--objects", required=True,
                    help="JSON with name, ra_deg, dec_deg entries")
    ap.add_argument("--radius", type=int, default=3)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    strips = load_strips(pathlib.Path(args.strips))
    cube, variance, mjd, wcs = align(strips,
                                     max_strips=args.visits if args.visits else None,
                                     coverage_only=True)
    null = calibrate(cube, variance, "control", tracks=1500)
    threshold = null.s_p95

    catalog = json.loads(pathlib.Path(args.objects).read_text())
    results = []
    for entry in catalog["objects"]:
        rec = recover(cube, variance, wcs, entry["name"], entry["ra_deg"],
                      entry["dec_deg"], threshold, search_radius_px=args.radius)
        results.append(rec.as_dict())
        print(f"  {entry['name']}: {rec.verdict} - {rec.reason}")

    payload = {
        "threshold": threshold,
        "threshold_source": "95th percentile of the measured null distribution",
        "visits": int(cube.shape[0]),
        "mjd_first": float(mjd[0]),
        "mjd_last": float(mjd[-1]),
        "field_centre_deg": [float(wcs.wcs.crval[0]), float(wcs.wcs.crval[1])],
        "results": results,
        "source": {"strips": args.strips, "objects": args.objects},
    }
    pathlib.Path(args.out).write_text(json.dumps(payload, indent=1))
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
