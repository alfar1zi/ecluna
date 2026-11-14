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
    tracks_requested: int
    pixels_used: int
    max_speed_px_per_visit: float
    mask_radius_px: int
    s_median: float
    s_sigma: float
    s_p95: float
    s_p99: float
    s_p999: float
    gaussian_p95: float
    gaussian_p99: float
    threshold_5sigma: float
    expected_false_alarms_per_1e6: float
    p95_ci: tuple[float, float]
    status: str

    def as_dict(self) -> dict:
        d = asdict(self)
        d["p95_ci"] = list(self.p95_ci)
        return d



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

def psf_kernel(fwhm_px: float) -> np.ndarray:
    """Normalised Gaussian kernel, summing to one."""
    sigma = fwhm_px / 2.3548
    size = int(np.ceil(fwhm_px * 3)) | 1
    half = size // 2
    y, x = np.mgrid[-half:half + 1, -half:half + 1]
    kernel = np.exp(-(x ** 2 + y ** 2) / (2 * sigma ** 2))
    return kernel / kernel.sum()


def track_statistic(cube: np.ndarray, variance: np.ndarray, x0: float, y0: float,
                    vx: float, vy: float, fwhm_px: float = 2.0) -> float:
    """Matched filter value along one track, weighted by the PSF.

    cube and variance are shaped (visits, ny, nx). The track position in visit k
    is (x0 + vx * k, y0 + vy * k). The filter sums the PSF-weighted flux around
    that position, which is what the limit formula in src/limit.py assumes: a
    single-pixel sample would be less sensitive by the square root of the number
    of pixels under the PSF, and the two numbers would not be comparable.
    """
    kernel = psf_kernel(fwhm_px)
    half = kernel.shape[0] // 2
    n_visits, ny, nx = cube.shape
    total = 0.0
    weight_norm = 0.0
    for k in range(n_visits):
        cx = int(round(x0 + vx * k))
        cy = int(round(y0 + vy * k))
        if not (half <= cx < nx - half and half <= cy < ny - half):
            return np.nan
        patch_f = cube[k, cy - half:cy + half + 1, cx - half:cx + half + 1]
        patch_v = variance[k, cy - half:cy + half + 1, cx - half:cx + half + 1]
        if not np.isfinite(patch_f).all() or not np.isfinite(patch_v).all():
            return np.nan
        if (patch_v <= 0).any():
            return np.nan
        # Inverse-variance weighting inside the aperture, then the PSF shape.
        w = kernel / patch_v
        total += float(np.sum(w * patch_f))
        weight_norm += float(np.sum(w * w * patch_v))
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


def mask_centre(cube: np.ndarray, radius: int) -> np.ndarray:
    """Blank a square around the centre of the grid.

    The acquisition cuts a stamp centred on the target, so the target itself sits
    in the middle. A null measured across the whole stamp is then dominated by
    tracks that cross the bright object: on Epsilon Indi B that gave a threshold
    of 108.98 where the surrounding field gives about 10. The centre is excluded
    and the null describes the background, which is what it is for.
    """
    if radius <= 0:
        return cube
    out = cube.copy()
    ny, nx = out.shape[1], out.shape[2]
    cy, cx = ny // 2, nx // 2
    out[:, max(0, cy - radius):cy + radius, max(0, cx - radius):cx + radius] = np.nan
    return out


def valid_pixels(cube: np.ndarray, margin: int) -> tuple[np.ndarray, np.ndarray]:
    """Every pixel whose whole track neighbourhood is usable.

    The track sweeps margin pixels, so the position needs a margin-sized square of
    finite pixels around it. Relaxing that square to fit the frame would return
    positions that cannot carry the track, and the sample would then be empty for a
    different reason. The caller reduces the speed or the mask instead.
    """
    from scipy.ndimage import binary_erosion

    good = np.isfinite(cube).all(axis=0)
    if margin > 0:
        size = 2 * margin + 1
        good = binary_erosion(good, structure=np.ones((size, size), bool),
                              border_value=0)
    ys, xs = np.nonzero(good)
    if xs.size == 0:
        raise ValueError("no pixel is finite in every visit")
    return xs, ys


def null_distribution(cube: np.ndarray, variance: np.ndarray, tracks: int = 20000,
                      max_speed: float = 1.0, seed: int = 20261114,
                      mask_radius_px: int = 0) -> np.ndarray:
    """S for random tracks on real data with nothing injected."""
    if mask_radius_px:
        cube = mask_centre(cube, mask_radius_px)
        variance = mask_centre(variance, mask_radius_px)
    rng = np.random.default_rng(seed)
    n_visits, ny, nx = cube.shape
    margin = int(np.ceil(max_speed * n_visits)) + 2
    xs, ys = valid_pixels(cube, margin)
    values = np.empty(tracks, dtype=float)
    for i in range(tracks):
        pick = rng.integers(0, xs.size)
        x0 = float(xs[pick])
        y0 = float(ys[pick])
        vx = rng.uniform(-max_speed, max_speed)
        vy = rng.uniform(-max_speed, max_speed)
        values[i] = track_statistic(cube, variance, x0, y0, vx, vy)
    return values[np.isfinite(values)]


def quantile_interval(values: np.ndarray, q: float, level: float = 0.95
                      ) -> tuple[float, float]:
    """Distribution-free interval for a quantile, from the binomial order statistics.

    Deterministic: the same sample always gives the same interval, which a
    resampling interval does not.
    """
    from scipy.stats import binom

    n = values.size
    if n < 20:
        return float(np.min(values)), float(np.max(values))
    ordered = np.sort(values)
    alpha = (1.0 - level) / 2.0
    lo_rank = int(binom.ppf(alpha, n, q))
    hi_rank = int(binom.ppf(1.0 - alpha, n, q))
    lo_rank = max(0, min(lo_rank, n - 1))
    hi_rank = max(0, min(hi_rank, n - 1))
    return float(ordered[lo_rank]), float(ordered[hi_rank])


def calibrate(cube: np.ndarray, variance: np.ndarray, field: str,
              tracks: int = 20000, max_speed: float = 1.0,
              seed: int = 20261114, mask_radius_px: int = 0) -> NullResult:
    """Measure the null distribution and the threshold that follows from it."""
    from scipy.stats import norm

    flat = subtract_background(cube)
    # A track at s pixels per visit sweeps s * visits pixels, and the sample has to
    # sit that far from the edge. With a mask in the middle and many visits the
    # usable area can vanish, so the speed is reduced until it does not, and the
    # speed actually used is part of the result.
    speed = max_speed
    mask = mask_radius_px
    values = None
    # Two things can starve the sample: a track that sweeps too far for the frame,
    # and a mask that takes the middle. Both are reduced in turn, and whatever is
    # used is reported, because it changes what was searched.
    for _ in range(12):
        try:
            values = null_distribution(flat, variance, tracks=tracks,
                                       max_speed=speed, seed=seed,
                                       mask_radius_px=mask)
            break
        except ValueError:
            # The mask usually eats more area than the track does, so it gives way
            # first. Speed only comes down once the mask is small.
            if mask > 6:
                mask = int(mask * 0.7)
            elif speed > 0.05:
                speed /= 2.0
            else:
                raise
    max_speed = speed
    mask_radius_px = mask
    if values.size < 100:
        raise ValueError("too few finite tracks to calibrate")
    median = float(np.median(values))
    sigma = float(np.std(values))
    p95 = float(np.quantile(values, 0.95))
    # The threshold is a quantile of a finite sample, so it has a sampling error.
    # Reporting it without one would make a 1.4 and a 1.9 look like a real
    # difference between fields when it can be the number of tracks.
    #
    # The interval comes from the binomial order statistics, not from resampling:
    # a bootstrap gave a different interval on two runs of the same data, which
    # makes the result unreproducible. This depends only on the sample size.
    p95_ci = quantile_interval(values, 0.95)
    p99 = float(np.quantile(values, 0.99))
    p999 = float(np.quantile(values, 0.999))
    # The Gaussian value is what a 5 sigma cut would be if the noise were normal.
    gaussian_5 = float(norm.ppf(1 - 2.87e-7))
    return NullResult(
        field=field,
        visits=int(cube.shape[0]),
        tracks=int(values.size),
        # The number asked for, kept apart from the number that survived: a
        # reproduction that feeds the survivor count back in asks for fewer tracks
        # and lands on a different sample.
        tracks_requested=int(tracks),
        pixels_used=int(np.isfinite(cube).all(axis=0).sum()),
        s_median=median,
        s_sigma=sigma,
        s_p95=p95,
        s_p99=p99,
        s_p999=p999,
        gaussian_p95=float(norm.ppf(0.95)),
        gaussian_p99=float(norm.ppf(0.99)),
        max_speed_px_per_visit=float(max_speed),
        mask_radius_px=int(mask_radius_px),
        threshold_5sigma=gaussian_5,
        expected_false_alarms_per_1e6=float((values > gaussian_5).mean() * 1e6),
        p95_ci=p95_ci,
        status="measured",
    )


def stack_averaging(cube: np.ndarray, box: int = 31) -> dict:
    """How much the stack actually averages down, compared with independent visits.

    If the visits were independent, the scatter of the mean stack would be the
    per-visit scatter divided by the square root of the number of visits. A fixed
    pattern that is the same in every visit does not average down, so the ratio of
    the measured scatter to that prediction says how much of the noise is fixed.

    A ratio near one means the visits are independent and more visits help. A ratio
    well above one means a fixed pattern dominates, and more visits will not reach
    fainter flux.
    """
    flat = subtract_background(cube, box=box)
    n = flat.shape[0]
    per_visit = float(np.nanmedian([np.nanstd(flat[k]) for k in range(n)]))
    stack = np.nanmean(flat, axis=0)
    measured = float(np.nanstd(stack))
    predicted = per_visit / np.sqrt(n) if n > 0 else float("nan")
    ratio = measured / predicted if predicted and np.isfinite(predicted) else float("nan")
    return {
        "visits": int(n),
        "per_visit_scatter": per_visit,
        "stack_scatter": measured,
        "predicted_if_independent": predicted,
        "ratio": float(ratio),
        "method": "scatter of the mean stack over the per-visit scatter divided by sqrt(visits)",
    }


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
    ap.add_argument("--visits", type=int, default=0,
                    help="cap the visit count; 0 uses every strip covering the centre")
    ap.add_argument("--tracks", type=int, default=3000)
    ap.add_argument("--max-speed", type=float, default=None,
                    help="pixels per visit; default keeps a track inside a third "
                         "of the frame for the given visit count")
    ap.add_argument("--mask-radius", type=int, default=0,
                    help="blank this half-width around the grid centre before "
                         "measuring the null")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    strips = load_strips(pathlib.Path(args.strips))
    cube, variance, mjd, _ = align(strips,
                                   max_strips=args.visits if args.visits else None,
                                   coverage_only=True)
    scale = noise_scale(cube, variance)
    # A track at one pixel per visit sweeps n_visits pixels. On a 155 pixel frame
    # with 48 visits that is a third of the frame, and no pixel is far enough from
    # the edge to hold such a track. The default keeps the sweep inside a third.
    max_speed = args.max_speed
    if max_speed is None:
        shortest = min(cube.shape[1], cube.shape[2])
        max_speed = min(1.0, shortest / (3.0 * cube.shape[0]))
        print(f"  max speed {max_speed:.3f} px per visit "
              f"(frame {shortest} px, {cube.shape[0]} visits)")
    result = calibrate(cube, variance, args.field, tracks=args.tracks,
                       max_speed=max_speed, mask_radius_px=args.mask_radius)
    payload = {
        "field": args.field,
        "visits": int(cube.shape[0]),
        "mjd_first": float(mjd[0]),
        "mjd_last": float(mjd[-1]),
        "noise_scale": scale,
        "null": result.as_dict(),
        "source": {"strips": recorded_path(args.strips), "visits_used": int(cube.shape[0])},
    }
    pathlib.Path(args.out).write_text(json.dumps(payload, indent=1))
    print(f"wrote {args.out}: sigma {result.s_sigma:.2f}, p95 {result.s_p95:.2f}, "
          f"noise scale {scale['scale']:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())


def noise_scale_from_frame(image: np.ndarray, variance: np.ndarray,
                           box: int = 31) -> dict:
    """Noise scale from a single frame, when no visit series exists.

    The same measurement as noise_scale(), applied to one image instead of a
    stack: the standard deviation of (image - running median) / sqrt(variance).
    A single frame cannot separate correlated noise from structure as well as a
    stack can, so the value is reported with the frame count it came from.
    """
    from scipy.ndimage import median_filter

    ok = np.isfinite(image) & np.isfinite(variance) & (variance > 0)
    if ok.sum() < 10000:
        raise ValueError("too few usable pixels to measure the noise scale")
    filled = np.where(ok, image, np.nanmedian(image))
    background = median_filter(filled, size=box, mode="nearest")
    z = (image - background)[ok] / np.sqrt(variance[ok])
    return {
        "scale": float(np.std(z)),
        "frames": 1,
        "pixels": int(ok.sum()),
        "method": "standard deviation of (image - running median) / sqrt(variance)",
    }
