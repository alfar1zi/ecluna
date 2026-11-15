"""Build the practice frames for the second rung of the curiosity ladder.

A reader is shown a real frame with a source added, and asked to find it. The
source is injected at a brightness the pipeline recovers reliably, so a miss means
the reader did not find it rather than that the data could not show it. The answer
is stored beside the image, never in it.

The stretch and the window come from blink.json, so the practice frame looks
exactly like the frames in the flip view.
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
OUT = ROOT / "web" / "assets" / "practice"
DATA = ROOT / "web" / "data" / "practice.json"

FRAME = ROOT / "data" / "epochs_dr1" / "barnard" / "barnard_2025W34_2B_0090_4.fits"
PSF_FWHM_PX = 2.0
# At 0.4 MJy/sr the pipeline recovers every injected source, so a miss is the
# reader's rather than the data's.
INJECT_FLUX = 0.4
N_FRAMES = 5
SEED = 20261115


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def flatten(stamp: np.ndarray, box: int = 21) -> np.ndarray:
    arr = np.array(stamp, dtype=np.float32)
    fill = float(np.nanmedian(arr))
    arr = np.where(np.isfinite(arr), arr, fill)
    size = min(box, arr.shape[0] if arr.shape[0] % 2 else arr.shape[0] - 1)
    return arr - median_filter(arr, size=size, mode="nearest")


def render(stamp: np.ndarray, lo: float, hi: float, dest: Path, sat: float = 60.0) -> dict:
    arr = np.where(np.isfinite(stamp), stamp, lo)
    soft = (hi - lo) / 30.0
    norm = np.arcsinh((arr - lo) / soft) / np.arcsinh(sat)
    gray = (np.clip(norm, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)
    dest.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(gray, mode="L").save(dest, optimize=True)
    return {"bytes": dest.stat().st_size, "sha256": sha256(dest)}


def gaussian(shape: tuple[int, int], cx: float, cy: float, sigma: float, peak: float) -> np.ndarray:
    yy, xx = np.mgrid[0 : shape[0], 0 : shape[1]]
    return peak * np.exp(-(((xx - cx) ** 2 + (yy - cy) ** 2) / (2.0 * sigma * sigma)))


def main() -> None:
    blink = json.loads((ROOT / "web" / "data" / "blink.json").read_text())
    entry = next(o for o in blink["objects"] if o["id"] == "barnard")
    stretch = entry["stretch"]
    window = entry["window"]
    lo = stretch["lo_mjy_sr"]
    hi = stretch["hi_mjy_sr"]

    with fits.open(FRAME) as hdus:
        raw = np.array(hdus[0].data, dtype=np.float32)

    flat = flatten(raw)
    x0, y0 = window["x0"], window["y0"]
    w, h = window["width"], window["height"]
    flat = flat[y0 : y0 + h, x0 : x0 + w]

    rng = np.random.default_rng(SEED)
    sigma = PSF_FWHM_PX / 2.3548

    OUT.mkdir(parents=True, exist_ok=True)
    rounds = []
    for index in range(N_FRAMES):
        # Keep the source away from the edges, where the frame is noisier.
        cx = float(rng.uniform(0.18, 0.82) * w)
        cy = float(rng.uniform(0.18, 0.82) * h)
        injected = flat + gaussian(flat.shape, cx, cy, sigma, INJECT_FLUX)
        name = f"round_{index + 1:02d}.png"
        info = render(injected, lo, hi, OUT / name)
        rounds.append(
            {
                "id": f"round_{index + 1:02d}",
                "png": f"assets/practice/{name}",
                "answer_px": [round(cx, 1), round(cy, 1)],
                "answer_fraction": [round(cx / w, 4), round(cy / h, 4)],
                "flux_mjy_sr": INJECT_FLUX,
                **info,
            }
        )

    payload = {
        "schema_version": "practice-1",
        "frame": str(FRAME.relative_to(ROOT)),
        "frame_sha256": sha256(FRAME),
        "seed": SEED,
        "width": w,
        "height": h,
        "psf_fwhm_px": PSF_FWHM_PX,
        "inject_flux_mjy_sr": INJECT_FLUX,
        "note": (
            "A source of 0.4 MJy/sr was added to a real frame. The pipeline recovers "
            "every source at this brightness, so a miss means it was not found by eye."
        ),
        "rounds": rounds,
    }
    DATA.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"wrote {DATA.relative_to(ROOT)} and {len(rounds)} frames in {OUT.relative_to(ROOT)}")
    for r in rounds:
        print(f"  {r['id']}  answer at {r['answer_px']}")


if __name__ == "__main__":
    main()
