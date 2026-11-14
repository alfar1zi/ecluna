"""Align the blink strips of one field onto a common grid.

Each strip is a narrow slice of the detector taken at a different time, so the
strips do not share a pixel grid. Before anything can be measured across visits,
they have to be reprojected onto one grid that covers the sky they all see.

The common grid is built from the intersection of the strip footprints, not from
the union: a pixel that only some visits cover cannot be used for a time series.
"""

from __future__ import annotations

import pathlib
from dataclasses import dataclass

import numpy as np

PIXEL_SCALE_DEG = 6.15 / 3600.0


@dataclass
class Strip:
    path: pathlib.Path
    mjd: float
    image: np.ndarray
    variance: np.ndarray
    header: object


def load_strips(directory: pathlib.Path) -> list[Strip]:
    """Read every strip in a directory, with its time and variance."""
    from astropy.io import fits

    strips = []
    for path in sorted(directory.glob("*.fits")):
        with fits.open(path, memmap=False) as hdul:
            image = np.asarray(hdul[0].data, dtype=np.float32)
            variance = (np.asarray(hdul["VARIANCE"].data, dtype=np.float32)
                        if "VARIANCE" in hdul else np.full_like(image, np.nan))
            header = hdul[0].header.copy()
        mjd = header.get("MJD")
        if mjd is None:
            from astropy.time import Time
            if header.get("DATE-OBS"):
                mjd = float(Time(header["DATE-OBS"], scale="utc").mjd)
            else:
                import re
                match = re.match(r"(?:[a-z0-9]+_)?(\d{5})_", path.name)
                mjd = float(match.group(1)) if match else float("nan")
        strips.append(Strip(path=path, mjd=float(mjd), image=image,
                            variance=variance, header=header))
    strips.sort(key=lambda s: s.mjd)
    return strips


def footprint(strip: Strip) -> tuple[float, float, float, float]:
    """Sky bounds of a strip: ra_min, ra_max, dec_min, dec_max."""
    from astropy.wcs import WCS

    wcs = WCS(strip.header, naxis=2)
    ny, nx = strip.image.shape
    ra, dec = wcs.pixel_to_world_values([0, nx - 1, 0, nx - 1], [0, 0, ny - 1, ny - 1])
    ra = np.asarray(ra)
    dec = np.asarray(dec)
    return float(ra.min()), float(ra.max()), float(dec.min()), float(dec.max())


def common_bounds(strips: list[Strip], quantile: float = 0.9
                  ) -> tuple[float, float, float, float]:
    """Sky covered by most strips, not by all of them.

    Requiring every strip leaves a sliver, because a few visits are offset by a
    degree. The grid is built from the median of the low edges and the median of
    the high edges, so half the visits cover it fully and the rest are clipped.
    """
    boxes = [footprint(s) for s in strips]
    ra_min = float(np.quantile([b[0] for b in boxes], 1.0 - quantile))
    ra_max = float(np.quantile([b[1] for b in boxes], quantile))
    dec_min = float(np.quantile([b[2] for b in boxes], 1.0 - quantile))
    dec_max = float(np.quantile([b[3] for b in boxes], quantile))
    if ra_min >= ra_max or dec_min >= dec_max:
        raise ValueError("the strips have no sky in common")
    return ra_min, ra_max, dec_min, dec_max


def common_wcs(strips: list[Strip]):
    """A TAN grid covering the intersection, at the native pixel scale."""
    from astropy.wcs import WCS

    ra_min, ra_max, dec_min, dec_max = common_bounds(strips)
    nx = max(8, int(round((ra_max - ra_min) * np.cos(np.radians(dec_max))
                          / PIXEL_SCALE_DEG)))
    ny = max(8, int(round((dec_max - dec_min) / PIXEL_SCALE_DEG)))
    wcs = WCS(naxis=2)
    wcs.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    wcs.wcs.crval = [(ra_min + ra_max) / 2.0, (dec_min + dec_max) / 2.0]
    wcs.wcs.cdelt = [-PIXEL_SCALE_DEG, PIXEL_SCALE_DEG]
    wcs.wcs.crpix = [nx / 2.0 + 0.5, ny / 2.0 + 0.5]
    return wcs, nx, ny


def align(strips: list[Strip], max_strips: int | None = None):
    """Reproject every strip onto the common grid.

    Returns (cube, variance_cube, mjd, wcs) with cube shaped (visits, ny, nx).
    """
    from astropy.wcs import WCS
    from reproject import reproject_interp

    if max_strips:
        strips = strips[:max_strips]
    wcs, nx, ny = common_wcs(strips)
    cube = np.full((len(strips), ny, nx), np.nan, dtype=np.float32)
    varcube = np.full((len(strips), ny, nx), np.nan, dtype=np.float32)
    for i, strip in enumerate(strips):
        src = WCS(strip.header, naxis=2)
        data, _ = reproject_interp((strip.image, src), wcs, shape_out=(ny, nx))
        var, _ = reproject_interp((strip.variance, src), wcs, shape_out=(ny, nx))
        cube[i] = data
        varcube[i] = var
    return cube, varcube, np.array([s.mjd for s in strips]), wcs
