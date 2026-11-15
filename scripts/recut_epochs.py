"""Re-cut every visit of the five test objects at the position the object occupies.

The stored stamps were cut at the catalogue position without proper motion, so a
nearby star sat tens of pixels from the stamp centre: Barnard moves 10 arcsec a
year, which is 272 arcsec by 2026 and 44 pixels. This cuts each visit at the
position the object has at that observation time, and writes a header whose
reference pixel is the stamp centre.

The archive index (SIA) is not needed: the Level 2 files are listed over plain
HTTP, so the key is found from the observation id.

Run from the ecluna-submit repository:

    .venv/bin/python scripts/recut_epochs.py
"""

from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.acquire_epochs import PM, cutout_by_range, key_for_obs_id  # noqa: E402

SERIES = ROOT / "web" / "data" / "named_series.json"
FOLDER = {"epsindb": "epsindib"}
POSITION = {
    "barnard": (269.452077, 4.693365),
    "epsindb": (331.044147, -56.782844),
    "wise0855": (133.818908, -7.247048),
    "rwaur": (76.956526, 30.401438),
    "rdra": (248.167611, 66.754979),
}
SIZE = 128


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default=None,
                    help="one object id, so several can run at once")
    args = ap.parse_args()

    series = json.loads(SERIES.read_text())
    total_ok = total_fail = 0
    for obj in series["objects"]:
        oid = obj["id"]
        if args.only and oid != args.only:
            continue
        folder = ROOT / "data" / "epochs_dr1" / FOLDER.get(oid, oid)
        folder.mkdir(parents=True, exist_ok=True)
        ra, dec = POSITION[oid]
        pm = PM[FOLDER.get(oid, oid)]
        ok = fail = 0
        frames = []
        for e in obj["epochs"]:
            name = f"{FOLDER.get(oid, oid)}_{e['obs_id']}.fits"
            out = folder / name
            if out.exists():
                ok += 1
                frames.append({"file": name, "obs_id": e["obs_id"],
                               "mjd": e["mjd_start"], "bytes": out.stat().st_size})
                continue
            try:
                key = key_for_obs_id(e["obs_id"], 2)
                if not key:
                    fail += 1
                    print(f"  {oid} {e['obs_id']}: no key")
                    continue
                url = "https://nasa-irsa-spherex.s3.amazonaws.com/" + key
                info = cutout_by_range(url, ra, dec, SIZE, out,
                                       obs_id=e["obs_id"], mjd=e["mjd_start"],
                                       proper_motion=pm)
                if info.get("ok"):
                    ok += 1
                    frames.append({"file": name, "obs_id": e["obs_id"],
                                   "mjd": e["mjd_start"], "bytes": info["bytes"],
                                   "s3_key": key})
                else:
                    fail += 1
                    print(f"  {oid} {e['obs_id']}: {info.get('error')}")
            except Exception as error:
                fail += 1
                print(f"  {oid} {e['obs_id']}: {type(error).__name__}")
        manifest = {"target": oid, "size": SIZE,
                    "position_j2000": [ra, dec],
                    "proper_motion_mas_yr": list(pm),
                    "frames": frames}
        (folder / "manifest.json").write_text(json.dumps(manifest, indent=1))
        print(f"{oid}: {ok} ok, {fail} gagal")
        total_ok += ok
        total_fail += fail
    print(f"total: {total_ok} ok, {total_fail} gagal")
    return 0


if __name__ == "__main__":
    sys.exit(main())
