"""Extract the 102-channel spectrum of each named object from the all-sky cube.

The cube is the only product that gives a spectrum at an arbitrary position, and
until now it was read but never used for a result. This turns it into one: for
each target, the spectrum at the tile pixel nearest the target position, with the
channel wavelengths and the documented dichroic gap marked.

The pixel is chosen by the tile's own WCS, not by the tile centre, because the
centre of a 1.8 degree tile is rarely where the object is.
"""

from __future__ import annotations

import json
import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
CHANNELS = DATA / "spectral_channels.fits"


def channel_table(path: pathlib.Path) -> dict:
    from astropy.io import fits

    with fits.open(path) as hdul:
        table = hdul[2].data
        return {
            "wavelength_um": [float(v) for v in table["WAVELENGTH"]],
            "bandwidth_um": [float(v) for v in table["BANDWIDTH"]],
            "detector": [int(v) for v in table["DETECTOR"]],
            "resolving_power": [float(v) for v in table["R"]],
        }


def spectrum_at(tile_path: pathlib.Path, ra_deg: float, dec_deg: float) -> dict:
    """Spectrum at the pixel nearest a sky position, from one cube tile."""
    from astropy.io import fits
    from astropy.wcs import WCS

    with fits.open(tile_path, memmap=True) as hdul:
        header = hdul["IMAGE"].header
        nz, ny, nx = hdul["IMAGE"].data.shape
        # The tile carries a real HEALPix celestial WCS, CTYPE RA---HPX and
        # DEC--HPX. A linear approximation from the tile centre put every target
        # tens of thousands of pixels outside the 512 grid, so the WCS is used.
        # The header alone is not enough: the spectral axis is a -TAB lookup, so
        # astropy needs the file object to resolve it. The WCS still has three
        # axes, so the celestial pair is taken from the first two.
        wcs = WCS(hdul["IMAGE"].header, fobj=hdul)
        xf, yf, _ = wcs.world_to_pixel_values(ra_deg, dec_deg, 1.0)
        x = int(round(float(np.ravel(xf)[0])))
        y = int(round(float(np.ravel(yf)[0])))
        inside = 0 <= x < nx and 0 <= y < ny
        if not inside:
            return {"inside": False, "pixel": [x, y], "spectrum": None}
        spectrum = np.asarray(hdul["IMAGE"].data[:, y, x], dtype=float)
    return {"inside": True, "pixel": [int(x), int(y)],
            "spectrum": [None if not np.isfinite(v) else float(v) for v in spectrum]}


def main() -> int:
    manifest = json.loads((ROOT / "results" / "foundation.json").read_text())
    tiles = manifest.get("tiles", {})
    channels = channel_table(CHANNELS)

    out = {"channels": channels, "objects": {}, "source": {
        "cube": "SPHEREx DR1 all-sky cube, hips_20261026",
        "channel_table": "dr1/spectral_channels/cal-sch-v2-2026-229",
        "note": "the cube is zodiacal-light subtracted and 12.9 arcsec per pixel",
    }}
    for name, entry in tiles.items():
        tile = DATA / "cube" / f"Npix{entry['tile_index']}_cube.fits"
        if not tile.exists():
            print(f"  {name}: no tile on disk")
            continue
        result = spectrum_at(tile, entry["ra_deg"], entry["dec_deg"])
        finite = (sum(1 for v in result["spectrum"] if v is not None)
                  if result["spectrum"] else 0)
        out["objects"][name] = {
            "ra_deg": entry["ra_deg"], "dec_deg": entry["dec_deg"],
            "tile_index": entry["tile_index"], "inside": result["inside"],
            "pixel": result["pixel"], "finite_channels": finite,
            "spectrum": result["spectrum"],
        }
        print(f"  {name}: pixel {result['pixel']}, {finite} of 102 channels")

    path = ROOT / "results" / "spectra_named.json"
    path.write_text(json.dumps(out, indent=1))
    print(f"wrote {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
