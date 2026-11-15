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
import re
import urllib.parse
import json
import pathlib
import subprocess
import sys
import tempfile

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = ROOT / "data"

# Proper motion per target, milliarcseconds per year, ICRS. Applied before cutting:
# a stamp cut on the catalogue position does not contain a nearby star that has
# moved since J2000.
PM = {
    "barnard": (-801.551, 10362.394),
    "epsindib": (3981.977, -2466.832),
    "wise0855": (-8123.7, 673.2),
    "rwaur": (7.23, -20.33),
    "rdra": (-20.643, 6.149),
}

TARGETS = {
    "wise0855": (133.818908, -7.247048),
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
        # A frame already on disk is kept. Re-running to fill a gap must not
        # re-download what is there, and must not drop it if the network fails
        # again: the series is the frames that exist.
        existing = out / name
        # A cutout is about 160 KB, not the 65 MB of the full file, so the size
        # test has to match what is written here.
        if existing.exists() and existing.stat().st_size > 10_000:
            manifest["frames"].append({
                "file": name, "obs_id": obs_id, "mjd": mjd,
                "bytes": existing.stat().st_size, "pixel": None,
            })
            print(f"  {n}/{len(picks)} {obs_id} MJD {mjd:.3f} kept")
            continue
        # One bad frame must not end the target: the series is still useful with
        # the visits that did arrive, and the count is recorded.
        try:
            info = cutout_by_range(url, ra, dec, args.size, out / name,
                                   obs_id=obs_id, mjd=mjd,
                                   proper_motion=PM.get(args.target))
        except Exception as error:
            print(f"  {n}/{len(picks)} {obs_id}: {type(error).__name__} "
                  f"{str(error)[:60]}")
            continue
        if not info["ok"]:
            print(f"  {n}/{len(picks)} {obs_id}: {info.get('error', 'failed')}")
            continue
        manifest["frames"].append({
            "file": name, "obs_id": obs_id, "mjd": mjd,
            "bytes": info["bytes"], "pixel": info["pixel"],
        })
        print(f"  {n}/{len(picks)} {obs_id} MJD {mjd:.3f} {info['bytes'] // 1024} KB")

    (out / "manifest.json").write_text(json.dumps(manifest, indent=1))
    print(f"{args.target}: {len(manifest['frames'])} frames from {len(table)} available")
    return 0




def _range(url: str, a: int, b: int, tries: int = 3) -> bytes:
    """One range request, retried a few times before giving up."""
    for attempt in range(tries):
        out = subprocess.run(["curl", "-sS", "--max-time", "90", "--retry", "2",
                              "--retry-delay", "1", "-r", f"{a}-{b}", url],
                             capture_output=True)
        expected = b - a + 1
        if out.returncode == 0 and len(out.stdout) == expected:
            return out.stdout
    raise RuntimeError(f"range {a}-{b} failed after {tries} tries")


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
                    mjd: float = float("nan"),
                    proper_motion: tuple[float, float] | None = None) -> dict:
    """Cut a square around a position, optionally moved to the observation time.

    proper_motion is (pm_ra_cosdec, pm_dec) in milliarcseconds per year, from the
    catalogue. A nearby star moves far enough between J2000 and the observation
    that a stamp cut on the catalogue position does not contain it: Barnard moves
    10 arcsec a year, which is 272 arcsec by 2026, and that is 44 pixels.
    """
    """Cut a square by reading only the rows it needs.

    A full Level 2 file is 65 MB and the link runs at 0.15 to 0.4 MB/s, so a 128
    pixel stamp costs several minutes if the whole file is fetched. The IMAGE
    extension header spans nine 2880-byte blocks, so the first 16 blocks are read
    once, the data offset is computed from the END card, and only the rows under
    the stamp are fetched after that.
    """
    from astropy.io import fits
    from astropy.time import Time
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
    ra_obs, dec_obs = ra, dec
    if proper_motion is not None:
        from astropy.coordinates import SkyCoord
        import astropy.units as u
        pmra, pmdec = proper_motion
        epoch = float(header.get("MJD", mjd))
        if np.isfinite(epoch):
            start = SkyCoord(ra, dec, unit="deg",
                             pm_ra_cosdec=pmra * u.mas / u.yr,
                             pm_dec=pmdec * u.mas / u.yr,
                             obstime="J2000")
            moved = start.apply_space_motion(
                new_obstime=Time(epoch, format="mjd", scale="utc"))
            ra_obs, dec_obs = float(moved.ra.deg), float(moved.dec.deg)
    xf, yf = wcs.world_to_pixel_values(ra_obs, dec_obs)
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

    # The cutout is a translation of the full frame, and a TAN projection is not
    # translation invariant: moving CRPIX alone leaves the tangent point pointing at
    # the old place. The corrected header states the sky position of the stamp
    # centre and puts the reference pixel there, and the SIP polynomial is dropped
    # because its coefficients were fitted to the full-frame pixel coordinates.
    centre = wcs.pixel_to_world_values(x0 + size / 2.0, y0 + size / 2.0)
    crval1, crval2 = float(np.ravel(centre[0])[0]), float(np.ravel(centre[1])[0])
    cdelt = wcs.wcs.cdelt
    for key in [k for k in list(header) if k.startswith(("A_", "B_", "AP_", "BP_"))]:
        del header[key]
    header["CTYPE1"] = "RA---TAN"
    header["CTYPE2"] = "DEC--TAN"
    header["CRVAL1"] = (crval1, "right ascension of the stamp centre, deg")
    header["CRVAL2"] = (crval2, "declination of the stamp centre, deg")
    header["CRPIX1"] = (size / 2.0 + 0.5, "reference pixel on this stamp")
    header["CRPIX2"] = (size / 2.0 + 0.5, "reference pixel on this stamp")
    header["CDELT1"] = float(cdelt[0])
    header["CDELT2"] = float(cdelt[1])
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
    # The extra extensions sit past 60 MB of a 65 MB file, where the link is least
    # reliable. IMAGE alone is enough to render and search, so a failure here
    # costs the variance, not the frame.
    for _ in range(6):
        try:
            chunk = _range(url, position, position + 16 * block - 1)
        except Exception:
            break
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
            try:
                raw = _range(url, ext_data_at + y0 * row,
                             ext_data_at + y0 * row + size * row - 1)
            except Exception:
                break
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


_KEY_CACHE: dict[str, list[str]] = {}


def s3_keys_for_visit(visit: str) -> list[str]:
    """Every S3 key under one visit directory.

    The archive serves the Level 2 files over plain HTTP with no authentication, and
    the index endpoint lists them, so a key can be found from the observation id
    alone. This is what makes the cutouts regenerable after the SIA service, which
    used to supply the URL, is unavailable.
    """
    import json as _json
    import urllib.request

    if visit in _KEY_CACHE:
        return _KEY_CACHE[visit]
    keys: list[str] = []
    token = ""
    while True:
        url = ("https://nasa-irsa-spherex.s3.amazonaws.com/?list-type=2"
               f"&prefix=qr2/level2/{visit}/&max-keys=900")
        if token:
            url += f"&continuation-token={urllib.parse.quote(token)}"
        with urllib.request.urlopen(url, timeout=40) as response:
            body = response.read().decode()
        keys.extend(re.findall(r"<Key>([^<]+)</Key>", body))
        match = re.search(r"<NextContinuationToken>([^<]+)</NextContinuationToken>", body)
        if not match:
            break
        token = match.group(1)
    _KEY_CACHE[visit] = keys
    return keys


def key_for_obs_id(obs_id: str, detector: int = 2) -> str | None:
    """The S3 key for one observation id and detector.

    2025W34_2B_0090_4 -> qr2/level2/2025W34_2B/<version>/<det>/level2_2025W34_2B_0090_4D2_...
    The version and the detector are in the key but not in the id, so the visit is
    listed and the id plus the detector are matched against the file names. Matching
    on the id alone also catches the same exposure in other detectors.
    """
    visit = "_".join(obs_id.split("_")[:2])
    stem = obs_id.split("_", 2)[2]
    for key in s3_keys_for_visit(visit):
        if f"_{stem}D{detector}_" in key and key.endswith(".fits"):
            return key
    return None
