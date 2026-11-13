"""Print the 102-channel spectrum at a sky position.

Reads a local cube tile when one is given, otherwise opens the tile over HTTP
range requests. Local is the normal path: a tile is 320 MB and is downloaded
once, then reused.

Usage:
  python scripts/read_spectrum.py --tile data/cube/Npix4010_cube.fits
  python scripts/read_spectrum.py 270.3415 66.6023
"""

import argparse
import sys

import numpy as np

from src.cube import CubeTile, open_local, spectrum_from_hdul, tile_index


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("ra", type=float, nargs="?")
    ap.add_argument("dec", type=float, nargs="?")
    ap.add_argument("--tile", help="local cube tile path")
    ap.add_argument("--pixel", nargs=2, type=int, default=[256, 256])
    args = ap.parse_args()

    if args.tile:
        hdul = open_local(args.tile)
        try:
            print("HDUs:", [h.name for h in hdul])
            values = spectrum_from_hdul(hdul, args.pixel[0], args.pixel[1])
        finally:
            hdul.close()
    else:
        if args.ra is None or args.dec is None:
            ap.error("give RA and Dec, or --tile")
        index = tile_index(args.ra, args.dec)
        print(f"position {args.ra:.6f} {args.dec:.6f} -> tile {index}")
        with CubeTile(index) as tile:
            print("HDUs:", tile.hdus)
            values = tile.spectrum(args.pixel[0], args.pixel[1])

    finite = values[np.isfinite(values)]
    print(f"channels {len(values)}, finite {len(finite)}")
    print(f"min {finite.min():.4g}  median {np.median(finite):.4g}  "
          f"max {finite.max():.4g} MJy/sr")
    print("channels 49-54:", np.round(values[48:54], 3))
    return 0


if __name__ == "__main__":
    sys.exit(main())
