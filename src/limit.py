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

# Flag bits that make a pixel unusable for a limit: any non-zero flag is treated
# as unusable here, which is conservative. The archive defines the bits in
# Table 16 of the Explanatory Supplement.
USABLE_FLAG = 0


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
                      max_pixels: int = 400_000) -> Limit:
    """Compute the limit from a variance map and a flag map."""
    usable = (flags == USABLE_FLAG) & np.isfinite(variance) & (variance > 0)
    usable_fraction = float(usable.mean())
    values = variance[usable]
    if values.size == 0:
        raise ValueError("no usable pixels in this field")
    if values.size > max_pixels:
        step = values.size // max_pixels + 1
        values = values[::step]

    sigma_pix = float(np.sqrt(np.median(values)))
    lo, hi = bootstrap_median(np.sqrt(values))
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
