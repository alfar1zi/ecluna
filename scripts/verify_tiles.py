"""Verify every acquired cube tile by reading a real spectrum from it.

A tile that cannot produce a spectrum is not data, it is a file. This checks the
HDU layout, the channel count, and the documented dichroic gap at channels 51
and 52, then writes the result next to the manifest.
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import json

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = ROOT.parent / "ecluna" / "data"
MANIFEST = ROOT / "results" / "foundation.json"
OUT = ROOT / "results" / "tiles_verified.json"


def main() -> int:
    from astropy.io import fits

    manifest = json.loads(MANIFEST.read_text())
    tiles = manifest.get("tiles", {})
    if not tiles:
        print("no tiles in the manifest", file=sys.stderr)
        return 1

    report = {"tiles": {}, "status": "pass"}
    for name, entry in tiles.items():
        path = DATA / "cube" / f"Npix{entry['tile_index']}_cube.fits"
        if not path.exists():
            report["tiles"][name] = {"status": "missing"}
            report["status"] = "fail"
            print(f"{name}: MISSING {path.name}")
            continue
        with fits.open(path, memmap=True) as hdul:
            names = [h.name for h in hdul]
            image = hdul["IMAGE"].data
            nz, ny, nx = image.shape
            # pick the pixel with the most finite channels
            coverage = np.isfinite(image).sum(axis=0)
            y, x = np.unravel_index(int(np.argmax(coverage)), coverage.shape)
            spectrum = np.asarray(image[:, y, x], dtype=float)
        finite = int(np.isfinite(spectrum).sum())
        gap = [int(not np.isfinite(spectrum[50])), int(not np.isfinite(spectrum[51]))]
        ok = (nz == 102 and finite >= 90 and gap == [1, 1])
        report["tiles"][name] = {
            "file": path.name, "hdus": names, "shape": [nz, ny, nx],
            "pixel": [int(x), int(y)], "finite_channels": finite,
            "dichroic_gap_empty": gap,
            "median_mjy_sr": float(np.nanmedian(spectrum)),
            "status": "pass" if ok else "fail",
        }
        if not ok:
            report["status"] = "fail"
        print(f"{name}: {nz}x{ny}x{nx} finite={finite} gap={gap} "
              f"median={np.nanmedian(spectrum):.4g} -> {'pass' if ok else 'fail'}")

    OUT.write_text(json.dumps(report, indent=1))
    print(f"wrote {OUT.relative_to(ROOT)}")
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
