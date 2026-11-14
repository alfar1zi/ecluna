"""Detection limit for a moving point source in a SPHEREx field.

The limit is computed from the archive VARIANCE extension, not estimated from the
image, so it carries the instrument's own uncertainty model.

For a mean stack of N visits the per-pixel noise falls as sigma / sqrt(N). A point
source spread over an effective number of pixels N_eff is detected at

    F_lim = k * sigma_pix / sqrt(N) * sqrt(N_eff)

where F_lim is the total flux in MJy/sr times pixel, and k is the detection
threshold in sigma. The peak surface brightness of the same source is

    peak = F_lim / (2 * pi * sigma_psf^2)

Every returned number carries a 95 percent interval from a bootstrap over the
unmasked pixels, and the sample count used.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict

import numpy as np

# Flag bits, from Table 16 of the SPHEREx Explanatory Supplement (SSDC-DP-017
# v2.1, 2026-11-10). Two groups matter and they are not the same.
#
# Bits that make a pixel unusable in any exposure. The supplement says so in
# words: NONFUNC "is unusable for any purpose", HOT and COLD are "not usable for
# science", NONLINEAR "should be excluded from most scientific analyses".
DEAD_BITS = (1 << 1) | (1 << 2) | (1 << 6) | (1 << 7) | (1 << 9) | (1 << 10) \
    | (1 << 11) | (1 << 14) | (1 << 15)

# Bits that spoil one exposure but not the pixel. A cosmic ray, a ghost, a
# streak or a satellite halo is a per-exposure event.
TRANSIENT_BITS = (1 << 0) | (1 << 19) | (1 << 20) | (1 << 22) | (1 << 24) \
    | (1 << 25) | (1 << 26) | (1 << 27) | (1 << 28) | (1 << 29)

# Bit 21 SOURCE is deliberately absent from both groups. It marks a pixel mapped
# to a known source, which is a position, not a defect: the variance already
# carries the extra noise there, and a moving object is elsewhere in the next
# visit. Masking it would delete most of a crowded field for no reason.
SOURCE_BIT = 1 << 21
FULLSAMPLE_BIT = 1 << 12


@dataclass
class Limit:
    field: str
    visits: int
    threshold_sigma: float
    psf_fwhm_px: float
    usable_fraction: float
    sigma_pix_mjy_sr: float
    sigma_pix_ci95: tuple[float, float]
    n_eff_px: float
    flux_limit_mjy_sr_px: float
    flux_limit_ci95: tuple[float, float]
    peak_limit_mjy_sr: float
    peak_limit_ci95: tuple[float, float]
    n_samples: int
    status: str

    def as_dict(self) -> dict:
        d = asdict(self)
        d["sigma_pix_ci95"] = list(self.sigma_pix_ci95)
        d["flux_limit_ci95"] = list(self.flux_limit_ci95)
        d["peak_limit_ci95"] = list(self.peak_limit_ci95)
        return d


def effective_pixels(fwhm_px: float) -> float:
    """Matched-filter effective area of a Gaussian PSF."""
    sigma = fwhm_px / 2.3548
    return float(4.0 * np.pi * sigma * sigma)


def bootstrap_median(values: np.ndarray, draws: int = 200, seed: int = 20261114):
    """95 percent interval of the median by resampling."""
    rng = np.random.default_rng(seed)
    n = values.size
    medians = np.empty(draws)
    for i in range(draws):
        medians[i] = np.median(values[rng.integers(0, n, n)])
    return float(np.percentile(medians, 2.5)), float(np.percentile(medians, 97.5))


def limit_from_arrays(variance: np.ndarray, flags: np.ndarray, visits: int,
                      fwhm_px: float, field: str, threshold_sigma: float = 5.0,
                      max_pixels: int = 400_000,
                      noise_scale: float = 1.0) -> Limit:
    """Compute the limit from a variance map and a flag map."""
    usable = ((flags & DEAD_BITS) == 0) & np.isfinite(variance) & (variance > 0)
    usable_fraction = float(usable.mean())
    values = variance[usable]
    if values.size == 0:
        raise ValueError("no usable pixels in this field")
    if values.size > max_pixels:
        step = values.size // max_pixels + 1
        values = values[::step]

    # noise_scale corrects the archive variance to the scatter measured in the
    # data; see src/null.py noise_scale(). It is 1.0 when the archive variance is
    # taken at face value.
    sigma_pix = float(np.sqrt(np.median(values))) * noise_scale
    lo, hi = bootstrap_median(np.sqrt(values))
    lo, hi = lo * noise_scale, hi * noise_scale
    n_eff = effective_pixels(fwhm_px)
    scale = threshold_sigma / np.sqrt(visits) * np.sqrt(n_eff)
    flux = sigma_pix * scale
    peak = flux / (2.0 * np.pi * (fwhm_px / 2.3548) ** 2)

    return Limit(
        field=field,
        visits=visits,
        threshold_sigma=threshold_sigma,
        psf_fwhm_px=fwhm_px,
        usable_fraction=usable_fraction,
        sigma_pix_mjy_sr=sigma_pix,
        sigma_pix_ci95=(lo, hi),
        n_eff_px=n_eff,
        flux_limit_mjy_sr_px=flux,
        flux_limit_ci95=(lo * scale, hi * scale),
        peak_limit_mjy_sr=peak,
        peak_limit_ci95=(lo * scale / (2.0 * np.pi * (fwhm_px / 2.3548) ** 2),
                         hi * scale / (2.0 * np.pi * (fwhm_px / 2.3548) ** 2)),
        n_samples=int(values.size),
        status="projected",
    )


def limit_from_mef(path: str, visits: int, fwhm_px: float, field: str,
                   threshold_sigma: float = 5.0) -> Limit:
    """Compute the limit from a Level 2 MEF on disk."""
    from astropy.io import fits

    with fits.open(path, memmap=True) as hdul:
        variance = np.asarray(hdul["VARIANCE"].data, dtype=np.float64)
        flags = np.asarray(hdul["FLAGS"].data)
    return limit_from_arrays(variance, flags, visits, fwhm_px, field,
                             threshold_sigma=threshold_sigma)


def systematic_budget(variance: np.ndarray, flags: np.ndarray, visits: int,
                      fwhm_px: float, field: str, threshold_sigma: float = 5.0,
                      fwhm_uncertainty: float = 0.2) -> dict:
    """Spread of the limit under the choices that are not measured.

    The bootstrap interval covers only the sampling error of the median variance.
    The dominant uncertainty is systematic: the PSF width and the flag mask. This
    recomputes the limit across those choices and reports the range, so the two
    kinds of uncertainty are never mixed into one number.
    """
    variants = []
    for fwhm in (fwhm_px - fwhm_uncertainty, fwhm_px, fwhm_px + fwhm_uncertainty):
        variants.append(limit_from_arrays(variance, flags, visits, fwhm, field,
                                          threshold_sigma=threshold_sigma))
    # stricter mask: only pixels with no flag at all, already the default; looser
    # mask: ignore flags that only mark edges, approximated by keeping all finite
    loose = limit_from_arrays(variance, np.zeros_like(flags), visits, fwhm_px, field,
                              threshold_sigma=threshold_sigma)
    peaks = [v.peak_limit_mjy_sr for v in variants] + [loose.peak_limit_mjy_sr]
    fluxes = [v.flux_limit_mjy_sr_px for v in variants] + [loose.flux_limit_mjy_sr_px]
    return {
        "peak_min": float(min(peaks)),
        "peak_max": float(max(peaks)),
        "flux_min": float(min(fluxes)),
        "flux_max": float(max(fluxes)),
        "fwhm_variants_px": [fwhm_px - fwhm_uncertainty, fwhm_px, fwhm_px + fwhm_uncertainty],
        "mask_variants": ["any non-zero flag", "no mask"],
        "usable_fraction_strict": variants[1].usable_fraction,
        "usable_fraction_loose": loose.usable_fraction,
    }


def variance_budget(variance: np.ndarray, zodi: np.ndarray, flags: np.ndarray,
                    bins: int = 12) -> dict:
    """Split the variance into a background term, a read-noise floor, and crowding.

    Photon noise from the zodiacal background scales with the background level, so
    the variance is binned in ZODI and a straight line is fitted through the bin
    medians. The slope times the median background is the background share; the
    intercept is the read-noise floor. Crowding is the fraction of pixels the flag
    map removes, which is area, not variance, and is reported separately.
    """
    usable = ((flags & DEAD_BITS) == 0) & np.isfinite(variance) & (variance > 0) \
        & np.isfinite(zodi) & (zodi > 0)
    if usable.sum() < 1000:
        raise ValueError("too few usable pixels for a variance budget")

    v = variance[usable]
    z = zodi[usable]
    edges = np.quantile(z, np.linspace(0, 1, bins + 1))
    xs, ys = [], []
    for i in range(bins):
        lo, hi = edges[i], edges[i + 1]
        sel = (z >= lo) & (z <= hi)
        if sel.sum() > 50:
            xs.append(float(np.median(z[sel])))
            ys.append(float(np.median(v[sel])))
    xs = np.asarray(xs)
    ys = np.asarray(ys)
    slope, intercept = np.polyfit(xs, ys, 1)
    intercept = max(intercept, 0.0)
    median_v = float(np.median(v))
    median_z = float(np.median(z))
    background = max(slope, 0.0) * median_z
    read = intercept
    total = background + read
    if total <= 0:
        raise ValueError("degenerate variance budget")
    return {
        "background_share": float(background / total),
        "read_share": float(read / total),
        "crowding_share": float(1.0 - usable.mean()),
        "median_variance": median_v,
        "median_zodi": median_z,
        "slope": float(slope),
        "intercept": float(intercept),
        "bins_used": len(xs),
    }


def confusion_share(variance: np.ndarray, flags: np.ndarray) -> dict:
    """How much of the variance comes from pixels that sit on a known source.

    Bit 21 SOURCE marks a pixel mapped to a known source. Those pixels are not
    defective, but they are noisier, and that extra noise does not average down
    with more visits because the sources are fixed. This measures the excess
    directly instead of assuming it.
    """
    flags = flags.astype(np.int64)
    ok = np.isfinite(variance) & (variance > 0)
    on_source = ok & (((flags >> 21) & 1) == 1)
    off_source = ok & (((flags >> 21) & 1) == 0)
    if on_source.sum() < 100 or off_source.sum() < 100:
        return {"confusion_share": 0.0, "source_fraction": float(on_source.mean()),
                "var_on_source": None, "var_off_source": None, "measurable": False}
    v_on = float(np.median(variance[on_source]))
    v_off = float(np.median(variance[off_source]))
    v_all = float(np.median(variance[ok]))
    fraction = float(on_source.sum() / ok.sum())
    excess = max(0.0, v_on - v_off)
    return {
        "confusion_share": float(min(1.0, excess * fraction / v_all)) if v_all > 0 else 0.0,
        "source_fraction": fraction,
        "var_on_source": v_on,
        "var_off_source": v_off,
        "measurable": True,
    }


def diagnose(budget: dict, confusion: dict) -> dict:
    """Name the dominant limiter with a stated decision rule.

    The three quantities are not comparable: area loss is a fraction of the field,
    confusion and background are fractions of the variance. Taking the largest of
    them would be meaningless, so the rule is ordered and each threshold is stated.

    1. area loss above 0.5  -> the field has no usable data, nothing helps
    2. confusion above 0.5  -> a fixed pattern dominates, more visits do not help
    3. otherwise            -> background photon noise, which averages down as 1/sqrt(N)
    """
    area = budget["crowding_share"]
    conf = confusion["confusion_share"]
    if area > 0.5:
        cause, remedy = "area loss", "a different patch: this area has no usable data"
    elif conf > 0.5:
        cause, remedy = "confusion", "a longer wavelength band, or a field with fewer bright stars"
    else:
        cause, remedy = "background", "more visits to the same patch"
    return {
        "cause": cause,
        "remedy": remedy,
        "area_loss": area,
        "confusion_share": conf,
        "background_share": budget["background_share"],
        "averages_down_with_visits": cause == "background",
        "rule": "area>0.5 then confusion>0.5 then background",
    }


def _cli() -> int:
    """Command line: regenerate a result file from the data on disk."""
    import argparse
    import json
    import pathlib

    from astropy.io import fits

    ap = argparse.ArgumentParser(description="detection limit and diagnosis")
    ap.add_argument("--field", help="field name, e.g. C2")
    ap.add_argument("--mef", help="Level 2 MEF path")
    ap.add_argument("--visits", type=int, help="number of visits")
    ap.add_argument("--fwhm", type=float, default=2.0, help="PSF FWHM in pixels")
    ap.add_argument("--diagnose", action="store_true",
                    help="write the diagnosis for every field in the manifest")
    ap.add_argument("--fields", default="results/fields.json")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    if args.diagnose:
        import os
        root = pathlib.Path(os.environ.get("DATA_ROOT", "../data/level2"))
        fields = json.loads(pathlib.Path(args.fields).read_text()).get("fields", {})
        if not fields:
            print("no fields in the manifest", file=__import__("sys").stderr)
            return 1
        out = {"generated": "reproduce.sh", "fields": {}}
        for name, entry in fields.items():
            path = str(root / entry["file"])
            visits = entry["visits"]
            with fits.open(path, memmap=True) as hdul:
                variance = np.asarray(hdul["VARIANCE"].data, dtype=np.float64)
                flags = np.asarray(hdul["FLAGS"].data).astype(np.int64)
                zodi = np.asarray(hdul["ZODI"].data, dtype=np.float64)
            limit = limit_from_arrays(variance, flags, visits, args.fwhm, name)
            budget = variance_budget(variance, zodi, flags)
            confusion = confusion_share(variance, flags)
            out["fields"][name] = {
                "visits": visits, "file": entry["file"],
                "limit": limit.as_dict(), "budget": budget,
                "confusion": confusion, "diagnosis": diagnose(budget, confusion),
            }
            print(f"  {name}: {out['fields'][name]['diagnosis']['cause']}")
        pathlib.Path(args.out).write_text(json.dumps(out, indent=1))
        print(f"wrote {args.out}")
        return 0

    if not (args.field and args.mef and args.visits):
        ap.error("give --field, --mef and --visits, or --diagnose")
    limit = limit_from_mef(args.mef, visits=args.visits, fwhm_px=args.fwhm,
                           field=args.field)
    with fits.open(args.mef, memmap=True) as hdul:
        variance = np.asarray(hdul["VARIANCE"].data, dtype=np.float64)
        flags = np.asarray(hdul["FLAGS"].data)
    budget = systematic_budget(variance, flags, args.visits, args.fwhm, args.field)
    payload = {"limit": limit.as_dict(), "systematic": budget,
               "source": {"file": args.mef, "variance_hdu": "VARIANCE",
                          "flags_hdu": "FLAGS",
                          "flag_policy": "SSDC-DP-017 v2.1 Table 16, DEAD_BITS only"}}
    pathlib.Path(args.out).write_text(json.dumps(payload, indent=1))
    print(f"wrote {args.out}: peak {limit.peak_limit_mjy_sr:.5f} MJy/sr")
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
