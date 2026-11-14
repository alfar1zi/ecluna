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


def common_bounds(strips: list[Strip]) -> tuple[float, float, float, float]:
    """Intersection of every strip footprint.

    The intersection is the only region where a time series exists for every
    visit. Taking a quantile instead produces a large box that most visits only
    partly cover, which looks like more data and is not.
    """
    boxes = [footprint(s) for s in strips]
    ra_min = max(b[0] for b in boxes)
    ra_max = min(b[1] for b in boxes)
    dec_min = max(b[2] for b in boxes)
    dec_max = min(b[3] for b in boxes)
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


def align(strips: list[Strip], max_strips: int | None = None,
          coverage_only: bool = False):
    """Reproject the strips onto a common grid.

    Returns (cube, variance_cube, mjd, wcs) with cube shaped (visits, ny, nx).
    With coverage_only the strips that do not cover the set centre are dropped,
    so every visit in the cube has data across the whole grid.
    """
    from astropy.wcs import WCS
    from reproject import reproject_interp

    if coverage_only:
        strips, _, _ = covering_centre(strips)
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


def covering_centre(strips: list[Strip]) -> tuple[list[Strip], float, float]:
    """Strips that cover the median centre of the set.

    Using every strip forces the grid onto the intersection of all of them, which
    can be empty when a few visits are offset by a degree. Using a fixed small
    number throws away data for no reason. This takes the centre of the set and
    keeps every strip that actually covers it, so the choice is a measurement.
    """
    boxes = [footprint(s) for s in strips]
    ra0 = float(np.median([(b[0] + b[1]) / 2 for b in boxes]))
    dec0 = float(np.median([(b[2] + b[3]) / 2 for b in boxes]))
    kept = [s for s, b in zip(strips, boxes)
            if b[0] <= ra0 <= b[1] and b[2] <= dec0 <= b[3]]
    if len(kept) < 2:
        raise ValueError("fewer than two strips cover the centre")
    return kept, ra0, dec0
