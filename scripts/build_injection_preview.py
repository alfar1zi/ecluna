"""Render what a source at the detection limit looks like in our own frames.

The completeness curve says the pipeline recovers 15 to 60 percent of sources at
0.2 MJy/sr and all of them at 0.4. A reader cannot feel what that means from a
number, so this script injects a point source of a known flux into a real frame,
renders it with the same stretch the blink uses, and writes the difference beside
it. The point is that at the low end the source is there and cannot be seen.

The stretch is copied from build_blink_frames.py on purpose: a different stretch
would make the comparison a lie.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
from astropy.io import fits
from PIL import Image
from scipy.ndimage import median_filter

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "web" / "assets" / "injection"
DATA = ROOT / "web" / "data" / "injection.json"

FRAME = ROOT / "data" / "epochs_dr1" / "barnard" / "barnard_2025W34_2B_0090_4.fits"
FOV_PX = 128
LO_SIGMA = -1.0
HI_SIGMA = 40.0
SAT_SIGMA = 60.0
PSF_FWHM_PX = 2.0

# The two levels the completeness curve turns on.
LEVELS = [0.2, 0.4]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def robust_sigma(values: np.ndarray) -> float:
    finite = values[np.isfinite(values)]
    med = float(np.median(finite))
    return float(1.4826 * np.median(np.abs(finite - med)))


def flatten(stamp: np.ndarray, box: int = 21) -> np.ndarray:
    arr = np.array(stamp, dtype=np.float32)
    fill = float(np.nanmedian(arr))
    arr = np.where(np.isfinite(arr), arr, fill)
    size = min(box, arr.shape[0] if arr.shape[0] % 2 else arr.shape[0] - 1)
    return arr - median_filter(arr, size=size, mode="nearest")


def render_linear(stamp: np.ndarray, lo: float, hi: float, dest: Path) -> dict:
    """A difference image: zero is black, so a change is the only thing that shows."""
    arr = np.where(np.isfinite(stamp), stamp, lo)
    norm = (arr - lo) / (hi - lo)
    gray = (np.clip(norm, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)
    dest.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(gray, mode="L").save(dest, optimize=True)
    return {"bytes": dest.stat().st_size, "sha256": sha256(dest)}


def render(stamp: np.ndarray, lo: float, hi: float, dest: Path) -> dict:
    arr = np.where(np.isfinite(stamp), stamp, lo)
    soft = (hi - lo) / 30.0
    norm = np.arcsinh((arr - lo) / soft) / np.arcsinh(SAT_SIGMA)
    gray = (np.clip(norm, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)
    dest.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(gray, mode="L").save(dest, optimize=True)
    return {"bytes": dest.stat().st_size, "sha256": sha256(dest)}


def gaussian(shape: tuple[int, int], cx: float, cy: float, sigma: float, peak: float) -> np.ndarray:
    yy, xx = np.mgrid[0 : shape[0], 0 : shape[1]]
    return peak * np.exp(-(((xx - cx) ** 2 + (yy - cy) ** 2) / (2.0 * sigma * sigma)))


def main() -> None:
    with fits.open(FRAME) as hdus:
        raw = np.array(hdus[0].data, dtype=np.float32)

    # The stretch and the window come from the blink data, not from this frame:
    # a different stretch would make the comparison a lie.
    blink = json.loads((ROOT / "web" / "data" / "blink.json").read_text())
    entry = next(o for o in blink["objects"] if o["id"] == "barnard")
    stretch = entry["stretch"]
    window = entry["window"]
    lo = stretch["lo_mjy_sr"]
    hi = stretch["hi_mjy_sr"]
    sigma = stretch["robust_sigma_mjy_sr"]

    flat = flatten(raw)
    x0, y0 = window["x0"], window["y0"]
    w, h = window["width"], window["height"]
    flat = flat[y0 : y0 + h, x0 : x0 + w]

    # Off centre, so the source is not confused with the object the frame is
    # centred on.
    cx = w * 0.36
    cy = h * 0.62
    psf_sigma = PSF_FWHM_PX / 2.3548

    OUT.mkdir(parents=True, exist_ok=True)
    panels = []

    base = render(flat, lo, hi, OUT / "original.png")
    panels.append({"id": "original", "label": "The frame as it is", "flux": None, **base})

    for flux in LEVELS:
        injected = flat + gaussian(flat.shape, cx, cy, psf_sigma, flux)
        name = f"injected_{int(round(flux * 100)):03d}.png"
        info = render(injected, lo, hi, OUT / name)
        # The peak of the injection in units of the frame noise, which is the
        # number the completeness curve is indexed by.
        peak_snr = flux / sigma
        panels.append(
            {
                "id": f"injected_{int(round(flux * 100)):03d}",
                "label": f"A source of {flux:.1f} MJy/sr",
                "flux": flux,
                "peak_snr": round(peak_snr, 2),
                **info,
            }
        )

    # The difference, so the reader can see where the source is even when the
    # stretched frame hides it.
    diff = gaussian(flat.shape, cx, cy, psf_sigma, LEVELS[0])
    diff_lo = -0.5 * LEVELS[0]
    diff_hi = 1.2 * LEVELS[0]
    diff_info = render_linear(diff, 0.0, diff_hi, OUT / "difference.png")
    panels.append(
        {
            "id": "difference",
            "label": "The same source, subtracted",
            "flux": LEVELS[0],
            **diff_info,
        }
    )

    payload = {
        "schema_version": "injection-preview-1",
        "frame": str(FRAME.relative_to(ROOT)),
        "frame_sha256": sha256(FRAME),
        "fov_px": [w, h],
        "psf_fwhm_px": PSF_FWHM_PX,
        "robust_sigma_mjy_sr": round(sigma, 6),
        "stretch": {"lo_mjy_sr": round(lo, 6), "hi_mjy_sr": round(hi, 6)},
        "position_px": [round(cx, 1), round(cy, 1)],
        "levels_mjy_sr": LEVELS,
        "panels": panels,
        "note": (
            "A point source of a known flux was added to a real frame and rendered with "
            "the same stretch the blink uses. At 0.2 MJy/sr the source is in the pixels "
            "and cannot be seen, which is what a completeness of 15 to 60 percent means."
        ),
    }
    DATA.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"wrote {DATA.relative_to(ROOT)} and {len(panels)} panels in {OUT.relative_to(ROOT)}")
    for panel in panels:
        print(f"  {panel['id']:16s} {panel['label']}")


if __name__ == "__main__":
    main()
