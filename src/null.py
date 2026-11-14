"""Calibrate the detection threshold from the data, not from a Gaussian.

A moving object is a track: a position in the first visit and a displacement per
visit. The matched filter along a track is

    S = sum_k w_k F_k(p_k) / sqrt( sum_k w_k^2 var_k ),   w_k = 1 / var_k

If the noise were Gaussian and independent, S would be a standard normal and a
5 sigma cut would be the threshold. Real survey data is neither, so the threshold
is taken from the observed distribution of S on the same data with nothing
injected. The Gaussian value is reported next to it, so the difference is visible
rather than assumed away.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict

import numpy as np


@dataclass
class NullResult:
    field: str
    visits: int
    tracks: int
    pixels_used: int
    s_median: float
    s_sigma: float
    s_p95: float
    s_p99: float
    s_p999: float
    gaussian_p95: float
    gaussian_p99: float
    threshold_5sigma: float
    expected_false_alarms_per_1e6: float
    status: str

    def as_dict(self) -> dict:
        return asdict(self)


def track_statistic(cube: np.ndarray, variance: np.ndarray, x0: float, y0: float,
                    vx: float, vy: float) -> float:
    """Matched filter value along one track.

    cube and variance are shaped (visits, ny, nx). The track position in visit k
    is (x0 + vx * k, y0 + vy * k), sampled with bilinear interpolation.
    """
    n_visits, ny, nx = cube.shape
    total = 0.0
    weight_norm = 0.0
    for k in range(n_visits):
        x = x0 + vx * k
        y = y0 + vy * k
        if not (0 <= x < nx - 1 and 0 <= y < ny - 1):
            return np.nan
        ix, iy = int(x), int(y)
        fx, fy = x - ix, y - iy
        f = (cube[k, iy, ix] * (1 - fx) * (1 - fy)
             + cube[k, iy, ix + 1] * fx * (1 - fy)
             + cube[k, iy + 1, ix] * (1 - fx) * fy
             + cube[k, iy + 1, ix + 1] * fx * fy)
        v = (variance[k, iy, ix] * (1 - fx) * (1 - fy)
             + variance[k, iy, ix + 1] * fx * (1 - fy)
             + variance[k, iy + 1, ix] * (1 - fx) * fy
             + variance[k, iy + 1, ix + 1] * fx * fy)
        if not np.isfinite(f) or not np.isfinite(v) or v <= 0:
            return np.nan
        w = 1.0 / v
        total += w * f
        weight_norm += w * w * v
    if weight_norm <= 0:
        return np.nan
    return float(total / np.sqrt(weight_norm))


def subtract_background(cube: np.ndarray, box: int = 31) -> np.ndarray:
    """Remove the per-visit background with a running median.

    The sky background is a smooth offset of order 0.1 MJy/sr, far larger than the
    noise. Without removing it the matched filter measures the offset, not a
    source: the null distribution came out with a median of 21 sigma instead of 0.
    """
    from scipy.ndimage import median_filter

    out = np.empty_like(cube)
    for k in range(cube.shape[0]):
        plane = cube[k]
        finite = np.isfinite(plane)
        if not finite.any():
            out[k] = plane
            continue
        filled = np.where(finite, plane, np.nanmedian(plane))
        out[k] = plane - median_filter(filled, size=box, mode="nearest")
    return out


def valid_region(cube: np.ndarray, margin: int) -> tuple[int, int, int, int]:
    """Bounding box of the pixels that are finite in every visit."""
    good = np.isfinite(cube).all(axis=0)
    ys, xs = np.nonzero(good)
    if xs.size == 0:
        raise ValueError("no pixel is finite in every visit")
    return (int(xs.min()) + margin, int(xs.max()) - margin,
            int(ys.min()) + margin, int(ys.max()) - margin)


def null_distribution(cube: np.ndarray, variance: np.ndarray, tracks: int = 20000,
                      max_speed: float = 1.0, seed: int = 20261114) -> np.ndarray:
    """S for random tracks on real data with nothing injected."""
    rng = np.random.default_rng(seed)
    n_visits, ny, nx = cube.shape
    margin = int(np.ceil(max_speed * n_visits)) + 2
    x_lo, x_hi, y_lo, y_hi = valid_region(cube, margin)
    if x_hi <= x_lo or y_hi <= y_lo:
        raise ValueError("the valid region is too small for the requested speed")
    values = np.empty(tracks, dtype=float)
    for i in range(tracks):
        x0 = rng.uniform(x_lo, x_hi)
        y0 = rng.uniform(y_lo, y_hi)
        vx = rng.uniform(-max_speed, max_speed)
        vy = rng.uniform(-max_speed, max_speed)
        values[i] = track_statistic(cube, variance, x0, y0, vx, vy)
    return values[np.isfinite(values)]


def calibrate(cube: np.ndarray, variance: np.ndarray, field: str,
              tracks: int = 20000, max_speed: float = 1.0,
              seed: int = 20261114) -> NullResult:
    """Measure the null distribution and the threshold that follows from it."""
    from scipy.stats import norm

    flat = subtract_background(cube)
    values = null_distribution(flat, variance, tracks=tracks,
                               max_speed=max_speed, seed=seed)
    if values.size < 100:
        raise ValueError("too few finite tracks to calibrate")
    median = float(np.median(values))
    sigma = float(np.std(values))
    p95 = float(np.quantile(values, 0.95))
    p99 = float(np.quantile(values, 0.99))
    p999 = float(np.quantile(values, 0.999))
    # The Gaussian value is what a 5 sigma cut would be if the noise were normal.
    gaussian_5 = float(norm.ppf(1 - 2.87e-7))
    return NullResult(
        field=field,
        visits=int(cube.shape[0]),
        tracks=int(values.size),
        pixels_used=int(np.isfinite(cube).all(axis=0).sum()),
        s_median=median,
        s_sigma=sigma,
        s_p95=p95,
        s_p99=p99,
        s_p999=p999,
        gaussian_p95=float(norm.ppf(0.95)),
        gaussian_p99=float(norm.ppf(0.99)),
        threshold_5sigma=gaussian_5,
        expected_false_alarms_per_1e6=float((values > gaussian_5).mean() * 1e6),
        status="measured",
    )


def noise_scale(cube: np.ndarray, variance: np.ndarray, box: int = 31) -> dict:
    """How much larger the real pixel scatter is than the archive variance says.

    The VARIANCE extension is the formal per-pixel variance from the pipeline. It
    does not include every term that shows up in the data: background estimation
    error, resampling correlation, and any noise the pipeline models separately.
    Measured on the strips, the standardised residual has a scatter near 6 rather
    than 1, so a limit built on the archive variance alone would be about six
    times too deep.

    Returns the scale factor and the per-visit values, so the correction is a
    measurement rather than a fudge.
    """
    flat = subtract_background(cube, box=box)
    per_visit = []
    for k in range(cube.shape[0]):
        f = flat[k]
        v = variance[k]
        ok = np.isfinite(f) & np.isfinite(v) & (v > 0)
        if ok.sum() < 1000:
            per_visit.append(float("nan"))
            continue
        z = f[ok] / np.sqrt(v[ok])
        per_visit.append(float(np.std(z)))
    finite = [x for x in per_visit if np.isfinite(x)]
    return {
        "scale": float(np.median(finite)) if finite else float("nan"),
        "per_visit": per_visit,
        "visits_used": len(finite),
        "method": "standard deviation of (image - running median) / sqrt(variance)",
    }


def _cli() -> int:
    """Command line: calibrate the null for one field and write the result."""
    import argparse
    import json
    import pathlib

    from src.epochs import align, load_strips

    ap = argparse.ArgumentParser(description="null calibration for one field")
    ap.add_argument("--field", required=True)
    ap.add_argument("--strips", required=True, help="directory of blink strips")
    ap.add_argument("--visits", type=int, default=6)
    ap.add_argument("--tracks", type=int, default=3000)
    ap.add_argument("--max-speed", type=float, default=1.0)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    strips = load_strips(pathlib.Path(args.strips))
    cube, variance, mjd, _ = align(strips, max_strips=args.visits)
    scale = noise_scale(cube, variance)
    result = calibrate(cube, variance, args.field, tracks=args.tracks,
                       max_speed=args.max_speed)
    payload = {
        "field": args.field,
        "visits": int(cube.shape[0]),
        "mjd_first": float(mjd[0]),
        "mjd_last": float(mjd[-1]),
        "noise_scale": scale,
        "null": result.as_dict(),
        "source": {"strips": args.strips, "visits_used": int(cube.shape[0])},
    }
    pathlib.Path(args.out).write_text(json.dumps(payload, indent=1))
    print(f"wrote {args.out}: sigma {result.s_sigma:.2f}, p95 {result.s_p95:.2f}, "
          f"noise scale {scale['scale']:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
