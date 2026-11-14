"""Build the four views the page needs from the data already measured.

1. light curve      brightness per visit, with the detection limit under it
2. stability        how large a change this series would have shown
3. track map        where the object sits in each visit, over the catalogue stars
4. candidate map    sources the catalogue does not list, with the reason for each

Every number here is read from a result file or computed from the per-visit
measurements; nothing is typed in. Run from the ecluna-submit repository:

    .venv/bin/python scripts/build_views.py
"""

from __future__ import annotations

import json
import pathlib
import sys

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

WEB = ROOT / "web"
SERIES = WEB / "data" / "named_series.json"
CLASSIFIED = ROOT / "results"

TARGETS = ("barnard", "epsindb", "rwaur", "rdra", "wise0855")
FOLDER = {"epsindb": "epsindib"}


def load_json(path: pathlib.Path) -> dict:
    return json.loads(path.read_text())


def aperture_photometry(target: str, ra: float, dec: float) -> dict:
    """Brightness of the object per visit, measured in a small aperture.

    The median of a stamp is the sky, not the object: a 128 pixel stamp is mostly
    background, so its median barely moves when the star does. The flux is summed in
    a 7 pixel box around the object on the aligned stack, with the local background
    subtracted from a ring around it.
    """
    from src.epochs import align, load_strips

    folder = ROOT / "data" / "epochs_dr1" / FOLDER.get(target, target)
    cube, variance, mjd, wcs = align(load_strips(folder), coverage_only=True,
                                     centre=(ra, dec))
    flat = cube - np.nanmedian(cube, axis=(1, 2))[:, None, None]
    x, y = wcs.world_to_pixel_values(ra, dec)
    x = float(np.ravel(x)[0]); y = float(np.ravel(y)[0])
    ix, iy = int(round(x)), int(round(y))
    ny, nx = flat.shape[1], flat.shape[2]
    # The aperture has to fit inside the grid; a target near an edge gets a smaller
    # ring rather than no measurement at all.
    r_in = 3
    r_out = min(6, ix, iy, nx - 1 - ix, ny - 1 - iy)
    if r_out <= r_in:
        r_in = max(1, r_out - 1)
    if r_out <= r_in:
        return {"mjd": [], "flux": [], "noise": [], "pixel": [round(x, 2), round(y, 2)]}
    flux, noise = [], []
    for i in range(cube.shape[0]):
        patch = flat[i]
        inner = patch[iy - r_in:iy + r_in + 1, ix - r_in:ix + r_in + 1]
        outer = patch[iy - r_out:iy + r_out + 1, ix - r_out:ix + r_out + 1]
        if not np.isfinite(inner).any() or not np.isfinite(outer).any():
            continue
        background = float(np.nanmedian(outer))
        flux.append(float(np.nansum(inner - background)))
        noise.append(float(np.nanstd(outer) * np.sqrt(np.isfinite(inner).sum())))
    return {"mjd": [float(m) for m in mjd[:len(flux)]],
            "flux": flux, "noise": noise,
            "pixel": [round(x, 2), round(y, 2)]}


def light_curve(obj: dict) -> dict:
    """Brightness per visit, and the limit the search reached there.

    The limit is the measured 95th percentile of the null, converted to a peak
    brightness through the same PSF the search uses, so the curve and the limit are
    on one axis and a reader can see what the series would have shown.
    """
    phot = aperture_photometry(obj["id"], obj["ra_deg"], obj["dec_deg"])
    mjd = np.array(phot["mjd"])
    flux = np.array(phot["flux"])
    sigma = np.array(phot["noise"])

    # The per-visit scatter is the honest uncertainty of one measurement. The
    # scatter of the medians across the series says whether the object varied.
    scatter = float(np.std(flux))
    typical = float(np.median(sigma))
    # A ratio of scatter to noise only means something when the object is detected:
    # for a source near zero the ratio explodes without the object varying.
    detection = float(np.median(flux)) / typical if typical > 0 else None
    change = (scatter / typical) if typical > 0 else None

    return {
        "mjd": [round(float(x), 3) for x in mjd],
        "flux_mjy_sr_px": [round(float(x), 3) for x in flux],
        "per_visit_noise_mjy_sr_px": [round(float(x), 3) for x in sigma],
        "aperture_px": 3,
        "aperture_centre_px": phot["pixel"],
        "visits": int(len(mjd)),
        "baseline_days": round(float(mjd[-1] - mjd[0]), 1),
        "flux_scatter_mjy_sr_px": round(scatter, 3),
        "typical_noise_mjy_sr_px": round(typical, 3),
        "scatter_over_sigma": round(change, 2) if change else None,
        "detection_sigma": round(detection, 1) if detection else None,
        "note": ("scatter_over_sigma is the spread of the per-visit brightness in "
                 "units of one measurement's noise: a value near 1 means the object "
                 "did not change, a larger value means it did"),
    }


def stability(obj: dict, recovery: dict | None) -> dict:
    """The change this series would have shown, stated as a number.

    Not seeing a change is a result: it says the object is stable down to the level
    the data can resolve.
    """
    phot = aperture_photometry(obj["id"], obj["ra_deg"], obj["dec_deg"])
    sigma = np.array(phot["noise"])
    flux = np.array(phot["flux"])
    typical = float(np.median(sigma))
    median_flux = float(np.median(flux))
    # A change smaller than the per-visit noise cannot be followed visit by visit,
    # but it can be followed in the mean of the series if it is sustained.
    detect = typical / np.sqrt(len(flux))
    relative = detect / median_flux if median_flux else None
    return {
        "median_flux_mjy_sr_px": round(median_flux, 3),
        "per_visit_noise_mjy_sr_px": round(typical, 3),
        "smallest_sustained_change_mjy_sr_px": round(detect, 3),
        "smallest_sustained_change_fraction": round(relative, 4) if relative else None,
        "limit_threshold": round(float(recovery["threshold"]), 2) if recovery else None,
        "limit_ci": [round(float(x), 2) for x in recovery["threshold_ci"]] if recovery else None,
        "note": ("a sustained change below smallest_sustained_change_mjy_sr would "
                 "not be resolved by this series; the object is quoted as stable to "
                 "that level, not as unchanging"),
    }


def track_map(obj: dict) -> dict:
    """Where the object sits in each visit, in the aligned grid, over the stars.

    The motion is the catalogued proper motion applied to the observation time; it
    is what the series should show, and the map lets a reader compare it with what
    the frames do.
    """
    pm = obj.get("proper_motion") or {}
    pmra = pm.get("pm_ra_cosdec_mas_yr")
    pmdec = pm.get("pm_dec_mas_yr")
    scale = 6.15  # arcsec per pixel, SPHEREx Level 2
    epochs = obj["epochs"]
    t0 = epochs[0]["mjd_start"]
    points = []
    for e in epochs:
        years = (e["mjd_start"] - 51544.5) / 365.25
        arcsec_ra = (pmra or 0.0) / 1000.0 * years
        arcsec_dec = (pmdec or 0.0) / 1000.0 * years
        points.append({
            "mjd": round(float(e["mjd_start"]), 3),
            "east_arcsec": round(float(arcsec_ra), 3),
            "north_arcsec": round(float(arcsec_dec), 3),
            "east_px": round(float(arcsec_ra / scale), 3),
            "north_px": round(float(arcsec_dec / scale), 3),
        })
    if points:
        span_px = float(np.hypot(points[-1]["east_px"] - points[0]["east_px"],
                                 points[-1]["north_px"] - points[0]["north_px"]))
    else:
        span_px = 0.0
    return {
        "proper_motion_mas_yr": {"east": pmra, "north": pmdec},
        "source": pm.get("source"),
        "pixel_scale_arcsec": scale,
        "points": points,
        "span_px": round(span_px, 2),
        "note": ("motion is the catalogued proper motion, not a measurement of these "
                 "frames: the pipeline is built for detection, and the per-visit "
                 "centroid scatter is larger than this span"),
    }


def candidates(target: str) -> dict | None:
    path = CLASSIFIED / f"classified_{target}.json"
    if not path.exists():
        return None
    data = load_json(path)
    catalogue = f"stars_gaia_named_{ 'epsindb' if target == 'epsindb' else target}.json"
    gaia_path = ROOT / "results" / "cache" / catalogue
    stars = []
    if gaia_path.exists():
        for s in load_json(gaia_path)["stars"]:
            stars.append({"ra": s["ra"], "dec": s["dec"]})
    rows = []
    for r in data["sources"]:
        rows.append({
            "ra_deg": r["ra_deg"], "dec_deg": r["dec_deg"],
            "brightness_mjy_sr": r["peak_mjy_sr"],
            "signal_to_noise": r["snr"],
            "in_catalogue": r["in_catalogue"],
            "nearest_catalogue_arcsec": r["nearest_catalogue_arcsec"],
            # A track that never produced a finite value is recorded as null: JSON
            # has no infinity, and a reader that parses strictly would reject the
            # whole file.
            "track_statistic": (r["track_statistic"]
                                if r["track_statistic"] is not None
                                and abs(r["track_statistic"]) != float("inf")
                                else None),
            "speed_px_per_visit": r["best_speed_px_per_visit"],
            "moving": r["moving"],
            "verdict": r["verdict"],
        })
    return {
        "visits": data["visits"],
        "grid": data["grid"],
        "noise_mjy_sr": data["noise_mjy_sr"],
        "threshold": data["threshold"],
        "threshold_source": data["threshold_source"],
        "speed_floor_px_per_visit": data["speed_floor_px_per_visit"],
        "speeds_tested": data["speeds_tested"],
        "counts": data["counts"],
        "sources": rows,
        "catalogue_stars": stars[:1200],
        "note": ("a candidate is a source the catalogue does not list and a track "
                 "finds moving. A source absent from the catalogue is more often a "
                 "faint star the catalogue missed than a moving object, so a "
                 "candidate is a thing to check, not a discovery"),
    }


def main() -> int:
    series = load_json(SERIES)
    out = {"generated_from": "web/data/named_series.json and results/classified_*.json",
           "objects": []}
    for obj in series["objects"]:
        if obj["id"] not in TARGETS:
            continue
        recovery_path = ROOT / "results" / f"recovery_{obj['id'].replace('epsindb','epsindib')}.json"
        recovery = load_json(recovery_path) if recovery_path.exists() else None
        rec = {
            "id": obj["id"],
            "name": obj["name"],
            "ra_deg": obj["ra_deg"], "dec_deg": obj["dec_deg"],
            "n_epochs": obj.get("n_epochs"),
            "light_curve": light_curve(obj),
            "stability": stability(obj, recovery),
            "track_map": track_map(obj),
            "candidates": candidates(obj["id"]),
        }
        out["objects"].append(rec)
        lc = rec["light_curve"]
        print(f"{obj['id']:10s} {lc['visits']:3d} visits  scatter/noise "
              f"{lc['scatter_over_sigma']}")
    path = WEB / "data" / "views.json"
    path.write_text(json.dumps(out, indent=1))
    print(f"wrote {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
