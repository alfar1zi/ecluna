"""Print the 102-channel spectrum at a sky position.

Reads a local cube tile when one is given, otherwise opens the tile over HTTP
range requests. Local is the normal path: a tile is 320 MB and is downloaded
once, then reused.

Usage:
  python scripts/read_spectrum.py --tile data/cube/Npix4010_cube.fits
  python scripts/read_spectrum.py 270.3415 66.6023
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import argparse
import sys

import numpy as np

from src.cube import CubeTile, open_local, spectrum_from_hdul, tile_index


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("ra", type=float, nargs="?")
    ap.add_argument("dec", type=float, nargs="?")
    ap.add_argument("--tile", help="local cube tile path")
    ap.add_argument("--pixel", nargs=2, type=int, default=None,
                    help="pixel to read; default is the best covered pixel")
    args = ap.parse_args()

    if args.tile:
        hdul = open_local(args.tile)
        try:
            print("HDUs:", [h.name for h in hdul])
            if args.pixel is None:
                import numpy as np
                coverage = np.isfinite(hdul["IMAGE"].data).sum(axis=0)
                y, x = np.unravel_index(int(np.argmax(coverage)), coverage.shape)
                print(f"best covered pixel: {x}, {y} "
                      f"({int(coverage[y, x])} of 102 channels)")
            else:
                x, y = args.pixel
            values = spectrum_from_hdul(hdul, int(x), int(y))
        finally:
            hdul.close()
    else:
        if args.ra is None or args.dec is None:
            ap.error("give RA and Dec, or --tile")
        index = tile_index(args.ra, args.dec)
        print(f"position {args.ra:.6f} {args.dec:.6f} -> tile {index}")
        with CubeTile(index) as tile:
            print("HDUs:", tile.hdus)
            x, y = args.pixel if args.pixel else (256, 256)
            values = tile.spectrum(x, y)

    finite = values[np.isfinite(values)]
    print(f"channels {len(values)}, finite {len(finite)}")
    print(f"min {finite.min():.4g}  median {np.median(finite):.4g}  "
          f"max {finite.max():.4g} MJy/sr")
    print("channels 49-54:", np.round(values[48:54], 3))
    return 0


if __name__ == "__main__":
    sys.exit(main())
