"""Acquire a visit series for one target from SPHEREx DR1.

The blink strips on disk carry only IMAGE and VARIANCE. This downloads the full
Level 2 files, cuts a square around the target, and keeps IMAGE, VARIANCE and
FLAGS in the cutout, so the later steps can mask a cosmic ray or a ghost instead
of hoping it is not there.

Full files are about 70 MB each, so each one is cut and deleted rather than
stored.

Usage:
  python scripts/acquire_epochs.py --target wise0855 --band SPHEREx-D2 --visits 12
"""

from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys
import tempfile

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = ROOT.parent / "ecluna" / "data"

TARGETS = {
    "wise0855": (133.795129, -7.245147),
    "barnard": (269.452077, 4.693365),
    "epsindib": (331.044147, -56.782844),
    "rwaur": (76.956526, 30.401438),
    "rdra": (248.167611, 66.754979),
    "ecliptic-pole": (270.3415, 66.6023),
    "field-a": (7.6, -18.12),
    "field-b": (187.2, 18.39),
    "high-latitude": (45.0, 80.0),
    "galactic-plane": (0.0, 0.0),
}


def select_visits(available: int, wanted: int) -> list[int]:
    """Indices spread across the series, not the first N.

    Taking the first N visits would cover a few weeks and miss the baseline; the
    player is supposed to show the whole series, so the picks are evenly spaced.
    """
    if available <= 0 or wanted <= 0:
        return []
    count = min(wanted, available)
    picks = np.linspace(0, available - 1, count).round().astype(int)
    return sorted({int(p) for p in picks})


def query(ra: float, dec: float, band: str, radius_deg: float = 0.12):
    """DR1 rows overlapping a position in one band, oldest first."""
    from astroquery.ipac.irsa import Irsa
    from astropy.coordinates import SkyCoord
    import astropy.units as u

    table = Irsa.query_sia(pos=(SkyCoord(ra, dec, unit="deg"), radius_deg * u.deg),
                           collection="spherex_dr1")
    if len(table) == 0:
        return table
    keep = table[table["energy_bandpassname"] == band]
    return keep[np.argsort(np.asarray(keep["t_min"]))]


def s3_url(cloud_access: str) -> str | None:
    """HTTPS form of the S3 key, which is about ten times faster than IRSA."""
    if not cloud_access:
        return None
    try:
        info = json.loads(cloud_access)["aws"]
    except (ValueError, KeyError):
        return None
    return f"https://{info['bucket_name']}.s3.amazonaws.com/{info['key']}"


def cutout(url: str, ra: float, dec: float, size: int, out: pathlib.Path,
           obs_id: str = "", mjd: float = float("nan")) -> dict:
    """Download one Level 2 file, cut a square, keep IMAGE, VARIANCE and FLAGS."""
    from astropy.io import fits
    from astropy.nddata import Cutout2D
    from astropy.wcs import WCS

    with tempfile.TemporaryDirectory() as tmp:
        full = pathlib.Path(tmp) / "full.fits"
        # The archive occasionally drops a connection; three tries with a short
        # backoff is enough and does not hide a real failure.
        downloaded = False
        for attempt in range(3):
            result = subprocess.run(
                ["curl", "-sS", "--retry", "2", "--retry-delay", "2",
                 "--max-time", "300", "-o", str(full), url],
                capture_output=True, text=True)
            if result.returncode == 0 and full.exists() and full.stat().st_size > 1_000_000:
                downloaded = True
                break
        if not downloaded:
            return {"ok": False, "error": "download failed after three tries"}

        with fits.open(full, memmap=False) as hdul:
            image = hdul["IMAGE"].data
            variance = hdul["VARIANCE"].data
            flags = hdul["FLAGS"].data
            header = hdul["IMAGE"].header.copy()
            wcs = WCS(header, naxis=2)
            x, y = wcs.world_to_pixel_values(ra, dec)
            position = (float(np.ravel(x)[0]), float(np.ravel(y)[0]))
            cut_image = Cutout2D(image, position, size, wcs=wcs)
            cut_variance = Cutout2D(variance, position, size, wcs=wcs)
            cut_flags = Cutout2D(flags, position, size, wcs=wcs)

        out.parent.mkdir(parents=True, exist_ok=True)
        # relax=True keeps the SIP distortion; without it the cutout header loses
        # A_ORDER and B_ORDER and the alignment is wrong by an arcsecond.
        primary = fits.PrimaryHDU(cut_image.data.astype(np.float32),
                                  header=cut_image.wcs.to_header(relax=True))
        primary.header["BUNIT"] = ("MJy/sr", "surface brightness")
        # The DR1 header does not carry OBS_ID or MJD under those names, so the
        # values come from the catalogue row that selected the file.
        primary.header["OBS_ID"] = (obs_id, "observation id from the SIA row")
        primary.header["MJD"] = (mjd, "start time from the SIA row")
        hdus = fits.HDUList([
            primary,
            fits.ImageHDU(cut_variance.data.astype(np.float32), name="VARIANCE"),
            fits.ImageHDU(cut_flags.data.astype(np.int32), name="FLAGS"),
        ])
        hdus.writeto(out, overwrite=True)

    return {"ok": True, "bytes": out.stat().st_size,
            "pixel": [round(position[0], 1), round(position[1], 1)]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", required=True, choices=sorted(TARGETS))
    ap.add_argument("--band", default="SPHEREx-D2")
    ap.add_argument("--visits", type=int, default=12)
    ap.add_argument("--size", type=int, default=128)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    ra, dec = TARGETS[args.target]
    table = query(ra, dec, args.band)
    if len(table) == 0:
        print(f"{args.target}: no rows in {args.band}", file=sys.stderr)
        return 1
    # Spread the picks across the series so the baseline is covered, not the first
    # few visits.
    picks = select_visits(len(table), args.visits)

    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    manifest = {"target": args.target, "band": args.band, "ra_deg": ra,
                "dec_deg": dec, "available": len(table), "frames": []}

    for n, i in enumerate(picks, 1):
        row = table[i]
        # The S3 copy is the same file; measured at 2.3 MB/s against roughly
        # 0.6 MB/s through the IRSA endpoint.
        url = s3_url(str(row["cloud_access"])) or str(row["access_url"])
        mjd = float(row["t_min"])
        obs_id = str(row["obs_id"]).strip()
        name = f"{args.target}_{n:02d}_{mjd:.0f}.fits"
        info = cutout_by_range(url, ra, dec, args.size, out / name,
                               obs_id=obs_id, mjd=mjd)
        if not info["ok"]:
            print(f"  {n}/{len(picks)} {obs_id}: failed")
            continue
        manifest["frames"].append({
            "file": name, "obs_id": obs_id, "mjd": mjd,
            "bytes": info["bytes"], "pixel": info["pixel"],
        })
        print(f"  {n}/{len(picks)} {obs_id} MJD {mjd:.3f} {info['bytes'] // 1024} KB")

    (out / "manifest.json").write_text(json.dumps(manifest, indent=1))
    print(f"{args.target}: {len(manifest['frames'])} frames from {len(table)} available")
    return 0




def _range(url: str, a: int, b: int) -> bytes:
    out = subprocess.run(["curl", "-sS", "--max-time", "120", "-r", f"{a}-{b}", url],
                         capture_output=True)
    if out.returncode != 0:
        raise RuntimeError("range request failed")
    return out.stdout


def _header_cards(raw: bytes) -> dict:
    cards = {}
    for i in range(0, len(raw), 80):
        card = raw[i:i + 80].decode("ascii", "replace")
        key = card[:8].strip()
        if key:
            cards[key] = card
    return cards


def _card_value(cards: dict, key: str, default=None):
    card = cards.get(key)
    if card is None:
        return default
    raw = card[10:].split("/")[0].strip()
    if raw.startswith("'"):
        return raw.strip("' ").strip()
    if raw in ("T", "F"):
        return raw == "T"
    try:
        return int(raw)
    except ValueError:
        try:
            return float(raw.replace("D", "E"))
        except ValueError:
            return raw


def cutout_by_range(url: str, ra: float, dec: float, size: int,
                    out: pathlib.Path, obs_id: str = "",
                    mjd: float = float("nan")) -> dict:
    """Cut a square by reading only the rows it needs.

    A full Level 2 file is 65 MB and the link runs at 0.15 to 0.4 MB/s, so a 128
    pixel stamp costs several minutes if the whole file is fetched. The IMAGE
    extension header spans nine 2880-byte blocks, so the first 16 blocks are read
    once, the data offset is computed from the END card, and only the rows under
    the stamp are fetched after that.
    """
    from astropy.io import fits
    from astropy.wcs import WCS

    block = 2880
    head = _range(url, 0, 16 * block - 1)
    if len(head) < 16 * block:
        return {"ok": False, "error": "could not read the header region"}

    def card_at(index: int) -> str:
        return head[index:index + 80].decode("ascii", "replace")

    def end_card_after(start: int) -> int:
        """Byte offset of the first card whose keyword is END, at or after start."""
        index = start - (start % 80)
        while index + 80 <= len(head):
            if card_at(index)[:8].strip() == "END":
                return index
            index += 80
        return -1

    # A raw byte search for "END" can hit the word inside a comment; the card
    # keyword is what marks the end of a header.
    end_primary = end_card_after(0)
    if end_primary < 0:
        return {"ok": False, "error": "no END card in the primary header"}
    image_header_at = ((end_primary // block) + 1) * block

    end_image = end_card_after(image_header_at)
    if end_image < 0:
        return {"ok": False, "error": "no END card in the IMAGE header"}
    data_at = ((end_image // block) + 1) * block

    header_text = head[image_header_at:data_at].decode("ascii", "replace")
    # Cards must stay exactly 80 characters; stripping them shifts every value
    # and the WCS then puts the target outside the frame.
    cards = [header_text[i:i + 80].ljust(80)
             for i in range(0, len(header_text) - 79, 80)]
    header = fits.Header.fromstring("\n".join(cards), sep="\n")
    nx = int(header["NAXIS1"])
    ny = int(header["NAXIS2"])
    wcs = WCS(header, naxis=2)
    xf, yf = wcs.world_to_pixel_values(ra, dec)
    cx = int(round(float(np.ravel(xf)[0])))
    cy = int(round(float(np.ravel(yf)[0])))
    if not (0 <= cx < nx and 0 <= cy < ny):
        return {"ok": False, "error": f"target at ({cx}, {cy}) is outside the frame"}

    half = size // 2
    x0 = max(0, min(cx - half, nx - size))
    y0 = max(0, min(cy - half, ny - size))
    row_bytes = nx * 4
    start_byte = data_at + y0 * row_bytes
    raw = _range(url, start_byte, start_byte + size * row_bytes - 1)
    block_data = np.frombuffer(raw, dtype=">f4").reshape(size, nx)[:, x0:x0 + size]

    header["CRPIX1"] = float(header["CRPIX1"]) - x0
    header["CRPIX2"] = float(header["CRPIX2"]) - y0
    header["NAXIS1"] = size
    header["NAXIS2"] = size
    header["OBS_ID"] = (obs_id, "observation id from the SIA row")
    header["MJD"] = (mjd, "start time from the SIA row")
    header["BUNIT"] = ("MJy/sr", "surface brightness")
    header["STAMPX0"] = (x0, "column offset of this stamp in the full frame")
    header["STAMPY0"] = (y0, "row offset of this stamp in the full frame")

    # Walk the remaining extensions by jumping over the data of the previous one.
    extras: dict[str, np.ndarray] = {}
    position = data_at + ((nx * ny * 4 + block - 1) // block) * block
    for _ in range(6):
        chunk = _range(url, position, position + 16 * block - 1)
        if len(chunk) < block:
            break
        local_end = -1
        index = 0
        while index + 80 <= len(chunk):
            if chunk[index:index + 80].decode("ascii", "replace")[:8].strip() == "END":
                local_end = index
                break
            index += 80
        if local_end < 0:
            break
        header_len = ((local_end // block) + 1) * block
        text = chunk[:header_len].decode("ascii", "replace")
        cards = [text[i:i + 80].ljust(80) for i in range(0, len(text) - 79, 80)]
        ext = fits.Header.fromstring("\n".join(cards), sep="\n")
        name = str(ext.get("EXTNAME", "")).strip()
        enx = int(ext.get("NAXIS1", 0))
        eny = int(ext.get("NAXIS2", 0))
        ebytes = enx * eny * abs(int(ext.get("BITPIX", 32))) // 8 + int(ext.get("PCOUNT", 0))
        ext_data_at = position + header_len
        if name in ("VARIANCE", "FLAGS") and enx == nx and eny == ny:
            row = enx * abs(int(ext.get("BITPIX", 32))) // 8
            raw = _range(url, ext_data_at + y0 * row,
                         ext_data_at + y0 * row + size * row - 1)
            dtype = ">f4" if abs(int(ext.get("BITPIX", 32))) == 32 else ">i4"
            extras[name] = np.frombuffer(raw, dtype=dtype).reshape(size, nx)[:, x0:x0 + size]
        position = ext_data_at + ((ebytes + block - 1) // block) * block
        if len(extras) == 2:
            break

    out.parent.mkdir(parents=True, exist_ok=True)
    hdus = [fits.PrimaryHDU(block_data.astype(np.float32), header=header)]
    if "VARIANCE" in extras:
        hdus.append(fits.ImageHDU(extras["VARIANCE"].astype(np.float32), name="VARIANCE"))
    if "FLAGS" in extras:
        hdus.append(fits.ImageHDU(extras["FLAGS"].astype(np.int32), name="FLAGS"))
    fits.HDUList(hdus).writeto(out, overwrite=True)
    return {"ok": True, "bytes": out.stat().st_size, "pixel": [x0, y0],
            "centre": [cx, cy], "extensions": list(extras)}


if __name__ == "__main__":
    raise SystemExit(main())
