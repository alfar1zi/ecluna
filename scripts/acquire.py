"""Acquire the foundation data set, one step at a time.

Every step writes what it got, with a sha256, so the measurement code never
depends on a file whose origin is unknown.

Steps:
  tiles  download and hash the all-sky cube tile for each target
  gaia   cone search around each target, proper motions included
  wise   cone search around each target for the long baseline overlay
  epochs build the blink series for one field from the strips on disk
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import subprocess
import sys

TARGETS = {
    "wise0855": (133.795129, -7.245147),
    "barnard": (269.454, 4.693),
    "epsindib": (330.800, -56.800),
    "rwaur": (73.500, 30.300),
    "rdra": (245.600, 66.000),
    "c2": (270.3415, 66.6023),
}

S3 = "https://nasa-irsa-spherex.s3.amazonaws.com"
CUBE = "dr1/hips5_cube/hips_20261026/Norder5"
ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = ROOT.parent / "ecluna" / "data"


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def tile_index(ra: float, dec: float) -> int:
    import astropy.units as u
    from astropy_healpix import HEALPix

    return int(HEALPix(nside=32, order="nested").lonlat_to_healpix(
        ra * u.deg, dec * u.deg))


def step_tiles(manifest: dict) -> None:
    out = DATA / "cube"
    out.mkdir(parents=True, exist_ok=True)
    manifest["tiles"] = {}
    for name, (ra, dec) in TARGETS.items():
        index = tile_index(ra, dec)
        directory = (index // 10000) * 10000
        key = f"{CUBE}/Dir{directory}/Npix{index}_cube.fits"
        path = out / f"Npix{index}_cube.fits"
        if not path.exists() or path.stat().st_size == 0:
            print(f"  {name}: fetching {key}", flush=True)
            subprocess.run(["curl", "-sS", "-o", str(path), f"{S3}/{key}"], check=True)
        size = path.stat().st_size
        digest = sha256(path)
        manifest["tiles"][name] = {"tile_index": index, "key": key,
                                   "bytes": size, "sha256": digest,
                                   "ra_deg": ra, "dec_deg": dec}
        print(f"  {name}: tile {index}, {size / 2**20:.0f} MiB, {digest[:12]}", flush=True)


def step_gaia(manifest: dict, radius_arcmin: float = 15.0) -> None:
    from astroquery.gaia import Gaia

    out = DATA / "catalog"
    out.mkdir(parents=True, exist_ok=True)
    manifest["gaia"] = {}
    for name, (ra, dec) in TARGETS.items():
        query = (
            "SELECT source_id, ra, dec, pmra, pmdec, parallax, phot_g_mean_mag "
            f"FROM gaiadr3.gaia_source WHERE 1=CONTAINS(POINT('ICRS', ra, dec), "
            f"CIRCLE('ICRS', {ra}, {dec}, {radius_arcmin / 60.0}))"
        )
        path = out / f"gaia_{name}.csv"
        if not path.exists():
            # An async job has no 2000-row cap; the synchronous endpoint silently
            # truncates at 2000, which looks like a real count.
            job = Gaia.launch_job_async(query)
            table = job.get_results()
            table.write(path, format="csv", overwrite=True)
        rows = sum(1 for _ in open(path)) - 1
        manifest["gaia"][name] = {"radius_arcmin": radius_arcmin, "rows": rows,
                                  "file": str(path.relative_to(DATA)),
                                  "sha256": sha256(path)}
        print(f"  {name}: {rows} Gaia sources", flush=True)


def step_wise(manifest: dict, radius_arcmin: float = 15.0) -> None:
    from astroquery.ipac.irsa import Irsa
    from astropy.coordinates import SkyCoord
    import astropy.units as u

    out = DATA / "catalog"
    out.mkdir(parents=True, exist_ok=True)
    manifest["wise"] = {}
    for name, (ra, dec) in TARGETS.items():
        path = out / f"wise_{name}.csv"
        if not path.exists():
            table = Irsa.query_region(SkyCoord(ra, dec, unit="deg"),
                                      catalog="allwise_p3as_psd",
                                      spatial="Cone",
                                      radius=radius_arcmin * u.arcmin)
            table.write(path, format="csv", overwrite=True)
        rows = sum(1 for _ in open(path)) - 1
        manifest["wise"][name] = {"radius_arcmin": radius_arcmin, "rows": rows,
                                  "file": str(path.relative_to(DATA)),
                                  "sha256": sha256(path)}
        print(f"  {name}: {rows} WISE sources", flush=True)


STRIP_FIELDS = {
    "c2": "epochs_C2",
    "p1": "epochs_P1",
    "p2": "epochs_P2_big",
    "wise0855": "epochs_W0855",
}


def step_epochs(manifest: dict) -> None:
    """Index the blink strips already on disk: MJD, observation id, hash."""
    import re

    from astropy.io import fits

    manifest["epochs"] = {}
    for field, folder in STRIP_FIELDS.items():
        directory = DATA / "raw" / folder
        if not directory.is_dir():
            print(f"  {field}: no folder {folder}", flush=True)
            continue
        rows = []
        for path in sorted(directory.glob("*.fits")):
            with fits.open(path, memmap=True) as hdul:
                header = hdul[0].header
                shape = list(hdul[0].data.shape)
                crval = [float(header.get("CRVAL1", 0)), float(header.get("CRVAL2", 0))]
                date_obs = header.get("DATE-OBS")
            # MJD comes from the header when present, otherwise from DATE-OBS, so a
            # filename without the number is not a data loss.
            if header.get("MJD") is not None:
                mjd = float(header["MJD"])
            elif date_obs:
                from astropy.time import Time
                mjd = float(Time(date_obs, scale="utc").mjd)
            else:
                # Third fallback: the observation id in the filename starts with the
                # integer MJD, e.g. c2_61241_2026W30_1B_0175_4.fits.
                name_mjd = re.match(r"[a-z0-9]+_(\d{5})_", path.name)
                mjd = float(name_mjd.group(1)) if name_mjd else None
            match = re.search(r"(\d{4}W\d{2}_[0-9A-Z]{2}_\d{4}_\d)", path.name)
            obs_id = match.group(1) if match else None
            rows.append({"file": path.name, "mjd": mjd, "obs_id": obs_id,
                         "shape": shape, "crval_deg": crval, "date_obs": date_obs,
                         "bytes": path.stat().st_size, "sha256": sha256(path)})
        rows.sort(key=lambda r: (r["mjd"] is None, r["mjd"] if r["mjd"] else 0.0))
        manifest["epochs"][field] = {"folder": folder, "count": len(rows),
                                     "mjd_min": rows[0]["mjd"] if rows else None,
                                     "mjd_max": rows[-1]["mjd"] if rows else None,
                                     "strips": rows}
        print(f"  {field}: {len(rows)} strips, MJD {rows[0]['mjd']} to {rows[-1]['mjd']}",
              flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("steps", nargs="+", choices=["tiles", "gaia", "wise", "epochs"])
    ap.add_argument("--manifest", default=str(ROOT / "results" / "foundation.json"))
    args = ap.parse_args()

    path = pathlib.Path(args.manifest)
    path.parent.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(path.read_text()) if path.exists() else {}

    for step in args.steps:
        print(f"[{step}]", flush=True)
        # Re-read before writing: two runs of this script at the same time would
        # otherwise clobber each other's sections, which already cost the tile
        # entries once.
        current = json.loads(path.read_text()) if path.exists() else {}
        if step == "tiles":
            step_tiles(current)
        elif step == "gaia":
            step_gaia(current)
        elif step == "wise":
            step_wise(current)
        elif step == "epochs":
            step_epochs(current)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(current, indent=1))
        tmp.replace(path)
        manifest = current
        print(f"  manifest written: {path}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
