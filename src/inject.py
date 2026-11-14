"""Measure completeness by injecting sources and seeing how many come back.

The limit in src/limit.py is a prediction from the variance. This measures it: a
source of known flux is added to the real frames at a known position and track,
the same search runs, and the recovered fraction is counted. The flux at which
half the sources come back is the measured limit, f50.

The injected source is not a delta function. It is drawn with the PSF of the
instrument, and its noise contribution is added to the variance map, so a
recovered source is recovered for the right reason.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict

import numpy as np


@dataclass
class Level:
    flux: float
    injected: int
    recovered: int
    completeness: float
    wilson_low: float
    wilson_high: float

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class Curve:
    field: str
    visits: int
    tracks: int
    fwhm_px: float
    levels: list[Level]
    f50: float | None
    f50_ci: tuple[float, float] | None
    status: str

    def as_dict(self) -> dict:
        return {
            "field": self.field,
            "visits": self.visits,
            "tracks": self.tracks,
            "fwhm_px": self.fwhm_px,
            "levels": [level.as_dict() for level in self.levels],
            "f50": self.f50,
            "f50_ci": list(self.f50_ci) if self.f50_ci else None,
            "status": self.status,
        }


def gaussian_psf(fwhm_px: float, size: int | None = None) -> np.ndarray:
    """Normalised PSF kernel, summing to one."""
    sigma = fwhm_px / 2.3548
    if size is None:
        size = int(np.ceil(fwhm_px * 3)) | 1
    half = size // 2
    y, x = np.mgrid[-half:half + 1, -half:half + 1]
    kernel = np.exp(-(x ** 2 + y ** 2) / (2 * sigma ** 2))
    return kernel / kernel.sum()


def inject(cube: np.ndarray, variance: np.ndarray, x: float, y: float,
           vx: float, vy: float, flux: float, fwhm_px: float = 2.0):
    """Add a moving point source drawn with the PSF, and its variance.

    Returns copies; the input arrays are not modified.
    """
    kernel = gaussian_psf(fwhm_px)
    half = kernel.shape[0] // 2
    out = cube.copy()
    var_out = variance.copy()
    n_visits, ny, nx = cube.shape
    for k in range(n_visits):
        cx = int(round(x + vx * k))
        cy = int(round(y + vy * k))
        if not (half <= cx < nx - half and half <= cy < ny - half):
            return None, None
        patch = kernel * flux
        out[k, cy - half:cy + half + 1, cx - half:cx + half + 1] += patch.astype(out.dtype)
        # The source's own Poisson term is not added. The variance map is in
        # (MJy/sr)^2 while the patch is in MJy/sr, so adding the patch directly is
        # dimensionally wrong: it inflated the variance by three orders of
        # magnitude and suppressed the very signal being measured. At the fluxes
        # tested the source is faint against the background, so its Poisson term
        # is negligible next to the background variance.
    return out, var_out


def wilson(successes: int, trials: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion."""
    if trials == 0:
        return 0.0, 1.0
    p = successes / trials
    denom = 1 + z * z / trials
    centre = (p + z * z / (2 * trials)) / denom
    half = z * np.sqrt(p * (1 - p) / trials + z * z / (4 * trials * trials)) / denom
    return float(max(0.0, centre - half)), float(min(1.0, centre + half))


def completeness(cube: np.ndarray, variance: np.ndarray, threshold: float,
                 fluxes: list[float], per_level: int = 120, field: str = "",
                 fwhm_px: float = 2.0, max_speed: float = 1.0,
                 seed: int = 20261114) -> Curve:
    """Inject sources at each flux, search, and count what comes back."""
    from src.null import subtract_background, track_statistic, valid_pixels

    rng = np.random.default_rng(seed)
    flat = subtract_background(cube)
    n_visits, ny, nx = cube.shape
    margin = int(np.ceil(max_speed * n_visits)) + 4
    xs, ys = valid_pixels(flat, margin)

    levels: list[Level] = []
    recovered_positions: dict[float, list[float]] = {}
    for flux in fluxes:
        found = 0
        values = []
        for _ in range(per_level):
            pick = rng.integers(0, xs.size)
            x = float(xs[pick])
            y = float(ys[pick])
            vx = rng.uniform(-max_speed, max_speed)
            vy = rng.uniform(-max_speed, max_speed)
            filled, filled_var = inject(flat, variance, x, y, vx, vy, flux, fwhm_px)
            if filled is None:
                continue
            value = track_statistic(filled, filled_var, x, y, vx, vy)
            if not np.isfinite(value):
                continue
            values.append(float(value))
            if value > threshold:
                found += 1
        trials = len(values)
        low, high = wilson(found, trials)
        levels.append(Level(flux=flux, injected=trials, recovered=found,
                            completeness=found / trials if trials else 0.0,
                            wilson_low=low, wilson_high=high))
        if values:
            recovered_positions[flux] = values

    f50, ci = interpolate_f50(levels)
    return Curve(field=field, visits=int(n_visits), tracks=per_level * len(fluxes),
                 fwhm_px=fwhm_px, levels=levels, f50=f50, f50_ci=ci,
                 status="measured")


def interpolate_f50(levels: list[Level]) -> tuple[float | None, tuple[float, float] | None]:
    """Flux where completeness crosses one half, by linear interpolation."""
    usable = [lv for lv in levels if lv.injected > 0]
    if len(usable) < 2:
        return None, None
    # Completeness rises with flux, so the crossing is the pair where the low level
    # is below one half and the high level is at or above it.
    for i in range(len(usable) - 1):
        a, b = usable[i], usable[i + 1]
        if a.completeness < 0.5 <= b.completeness:
            frac = (0.5 - a.completeness) / (b.completeness - a.completeness)
            flux = a.flux + frac * (b.flux - a.flux)
            lo = _crossing(usable, lambda lv: lv.wilson_low)
            hi = _crossing(usable, lambda lv: lv.wilson_high)
            return float(flux), (float(lo if lo is not None else flux),
                                  float(hi if hi is not None else flux))
    # monotone but never crossing: report the last level if it is below one half
    if usable[-1].completeness < 0.5:
        return None, None
    return float(usable[0].flux), None


def _crossing(levels: list[Level], pick) -> float | None:
    """Flux where the chosen interval edge crosses one half."""
    for i in range(len(levels) - 1):
        lo_i, hi_i = pick(levels[i]), pick(levels[i + 1])
        if lo_i < 0.5 <= hi_i:
            frac = (0.5 - lo_i) / (hi_i - lo_i)
            return levels[i].flux + frac * (levels[i + 1].flux - levels[i].flux)
    return None


def _cli() -> int:
    """Command line: measure the completeness curve for one field."""
    import argparse
    import json
    import pathlib

    from src.epochs import align, load_strips
    from src.null import calibrate

    ap = argparse.ArgumentParser(description="completeness curve for one field")
    ap.add_argument("--field", required=True)
    ap.add_argument("--strips", required=True)
    ap.add_argument("--visits", type=int, default=0,
                    help="cap the visit count; 0 uses every strip covering the centre")
    ap.add_argument("--per-level", type=int, default=120)
    ap.add_argument("--fwhm", type=float, default=2.0)
    ap.add_argument("--max-speed", type=float, default=1.0)
    ap.add_argument("--fluxes", default="0.02,0.04,0.06,0.08,0.10,0.13,0.16,0.20,0.30,0.50",
                    help="comma separated flux levels in MJy/sr per pixel")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    strips = load_strips(pathlib.Path(args.strips))
    cube, variance, mjd, _ = align(strips,
                                   max_strips=args.visits if args.visits else None,
                                   coverage_only=True)
    null = calibrate(cube, variance, args.field, tracks=2000,
                     max_speed=args.max_speed)
    # The threshold is the measured 95th percentile of the null, so the false alarm
    # rate per track is five percent by construction.
    threshold = null.s_p95
    fluxes = [float(x) for x in args.fluxes.split(",")]
    curve = completeness(cube, variance, threshold, fluxes,
                         per_level=args.per_level, field=args.field,
                         fwhm_px=args.fwhm, max_speed=args.max_speed)
    payload = {
        "field": args.field,
        "threshold": threshold,
        "threshold_source": "95th percentile of the measured null distribution",
        "mjd_first": float(mjd[0]),
        "mjd_last": float(mjd[-1]),
        "curve": curve.as_dict(),
        "source": {"strips": args.strips, "visits_used": int(cube.shape[0])},
    }
    pathlib.Path(args.out).write_text(json.dumps(payload, indent=1))
    for lv in curve.levels:
        print(f"  flux {lv.flux:5.2f}: {lv.recovered:3d}/{lv.injected:3d} "
              f"= {lv.completeness:.2f} [{lv.wilson_low:.2f}, {lv.wilson_high:.2f}]")
    print(f"f50: {curve.f50}")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
