"""Read spectra from the SPHEREx all-sky cube without downloading a tile.

A DR1 cube tile is 512 x 512 x 102 float32, about 320 MB. This module gives
astropy a file-like object that fetches only the bytes it asks for, so a
spectrum costs a few hundred kilobytes instead of a full download.

Layout facts, from the SPHEREx archive documentation:
  * tiles are HEALPix order 5, NESTED, 12,288 of them, about 1.8 deg across,
  * path: dr1/hips5_cube/hips_20261026/Norder5/Dir<d>/Npix<n>_cube.fits,
    where d is the tile index rounded down to a multiple of 10,000,
  * HDUs: IMAGE, NHITS, FLAGS, SPECTRAL_CHANNELS, WCS-WAVE,
  * the cube is zodiacal-light subtracted, 12.9 arcsec per pixel.
"""

from __future__ import annotations

import http.client
import ssl

import numpy as np

HOST = "nasa-irsa-spherex.s3.amazonaws.com"
PREFIX = "/dr1/hips5_cube/hips_20261026/Norder5"
NSIDE = 32
ORDER = 5
TILE_COUNT = 12288


def tile_index(ra_deg: float, dec_deg: float) -> int:
    """HEALPix NESTED index at nside 32 for a sky position."""
    import astropy.units as u
    from astropy_healpix import HEALPix

    hp = HEALPix(nside=NSIDE, order="nested")
    return int(hp.lonlat_to_healpix(ra_deg * u.deg, dec_deg * u.deg))


def tile_path(index: int) -> str:
    """S3 key of the cube tile that holds a HEALPix index."""
    if not 0 <= index < TILE_COUNT:
        raise ValueError(f"tile index {index} outside 0..{TILE_COUNT - 1}")
    directory = (index // 10000) * 10000
    return f"{PREFIX}/Dir{directory}/Npix{index}_cube.fits"


class RangeFile:
    """Minimal seekable file over HTTP range requests, for astropy."""

    def __init__(self, path: str, timeout: float = 60.0):
        self.path = path
        self._conn = http.client.HTTPSConnection(
            HOST, timeout=timeout, context=ssl.create_default_context())
        self._pos = 0
        self._size = self._content_length()

    def _content_length(self) -> int:
        self._conn.request("HEAD", self.path)
        response = self._conn.getresponse()
        response.read()
        if response.status != 200:
            raise FileNotFoundError(f"{self.path}: HTTP {response.status}")
        return int(response.getheader("Content-Length", 0))

    def seek(self, offset: int, whence: int = 0) -> int:
        if whence == 0:
            self._pos = offset
        elif whence == 1:
            self._pos += offset
        else:
            self._pos = self._size + offset
        return self._pos

    def tell(self) -> int:
        return self._pos

    def read(self, size: int = -1) -> bytes:
        if size is None or size < 0:
            size = self._size - self._pos
        if size == 0:
            return b""
        end = min(self._pos + size, self._size) - 1
        self._conn.request("GET", self.path,
                           headers={"Range": f"bytes={self._pos}-{end}"})
        response = self._conn.getresponse()
        body = response.read()
        if response.status not in (200, 206):
            raise IOError(f"{self.path}: HTTP {response.status} at {self._pos}")
        self._pos += len(body)
        return body

    def close(self) -> None:
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


class CubeTile:
    """One all-sky cube tile, opened lazily."""

    def __init__(self, index: int, timeout: float = 60.0):
        from astropy.io import fits

        self.index = index
        self.path = tile_path(index)
        self._file = RangeFile(self.path, timeout=timeout)
        self._hdul = fits.open(self._file, memmap=False)

    @property
    def hdus(self) -> list[str]:
        return [h.name for h in self._hdul]

    def _image_geometry(self) -> tuple[int, int, int, int]:
        """(channels, ny, nx, byte offset of the first pixel)."""
        hdu = self._hdul["IMAGE"]
        nz, ny, nx = hdu.header["NAXIS3"], hdu.header["NAXIS2"], hdu.header["NAXIS1"]
        return nz, ny, nx, int(hdu._data_offset)

    def spectrum(self, x: int, y: int) -> np.ndarray:
        """102 channel values at one pixel, in MJy/sr.

        Reads four bytes per channel. The plane stride is nx * ny * 4, so the
        values are not contiguous and each one is a separate range request.
        """
        nz, ny, nx, base = self._image_geometry()
        if not (0 <= x < nx and 0 <= y < ny):
            raise ValueError(f"pixel ({x}, {y}) outside {nx}x{ny}")
        plane = nx * ny * 4
        out = np.empty(nz, dtype=float)
        for k in range(nz):
            offset = base + k * plane + (y * nx + x) * 4
            self._file.seek(offset)
            out[k] = np.frombuffer(self._file.read(4), dtype=">f4")[0]
        return out

    def stamp(self, size: int = 32) -> np.ndarray:
        """Cube cutout of shape (channels, size, size) at the tile centre.

        One contiguous read per channel: size rows of the full width, then the
        left size columns are kept.
        """
        nz, ny, nx, base = self._image_geometry()
        half = size // 2
        x0, y0 = nx // 2 - half, ny // 2 - half
        out = np.empty((nz, size, size), dtype=np.float32)
        for k in range(nz):
            offset = base + k * nx * ny * 4 + (y0 * nx + x0) * 4
            self._file.seek(offset)
            raw = self._file.read(size * nx * 4)
            block = np.frombuffer(raw, dtype=">f4").reshape(size, nx)
            out[k] = block[:, :size]
        return out

    def close(self) -> None:
        self._hdul.close()
        self._file.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def open_local(path: str):
    """Open a cube tile that is already on disk."""
    from astropy.io import fits

    return fits.open(path, memmap=True)


def spectrum_from_hdul(hdul, x: int, y: int) -> np.ndarray:
    """102 channel values at one pixel of an open cube tile, in MJy/sr."""
    image = hdul["IMAGE"].data
    nz, ny, nx = image.shape
    if not (0 <= x < nx and 0 <= y < ny):
        raise ValueError(f"pixel ({x}, {y}) outside {nx}x{ny}")
    return np.asarray(image[:, y, x], dtype=float)


def stamp_from_hdul(hdul, size: int = 32) -> np.ndarray:
    """Cube cutout of shape (channels, size, size) at the tile centre."""
    image = hdul["IMAGE"].data
    nz, ny, nx = image.shape
    half = size // 2
    x0, y0 = nx // 2 - half, ny // 2 - half
    return np.asarray(image[:, y0:y0 + size, x0:x0 + size], dtype=np.float32)
