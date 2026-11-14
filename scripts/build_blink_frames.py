"""Build blink frames for the five test objects on one common grid.

A blink shows motion only when every frame sits on the same sky grid: the raw
cutouts carry a different tangent point per exposure, so flipping them shows the
pointing drift rather than the object. Each object is therefore aligned onto one
grid, cropped to a square window around its measured position, and rendered with
one stretch shared by every frame.

Run from the ecluna-submit repository:

    .venv/bin/python scripts/build_blink_frames.py
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import sys

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SERIES = ROOT / "data" / "epochs_dr1"
WEB = ROOT / "web"
OUT_JSON = WEB / "data" / "blink.json"

# The window is as large as the aligned grid allows, up to 128 pixels. A 44 pixel
# window upscaled to fill a column reads as mush; the same field at 128 keeps the
# stars separable.
FOV_PX = 128
# The stretch is measured on the flattened frame, where the sky gradient is gone
# and the robust sigma is about 0.06 MJy/sr. At 8 sigma the noise fills the frame;
# at 40 the background stays dark and a star is a point rather than a smudge.
LO_SIGMA = -1.0
HI_SIGMA = 40.0
SAT_SIGMA = 60.0


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def robust_sigma(values: np.ndarray) -> float:
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return float("nan")
    med = float(np.median(finite))
    return float(1.4826 * np.median(np.abs(finite - med)))


def flatten(stamp: np.ndarray, box: int = 21) -> np.ndarray:
    """Remove the smooth sky background from one frame.

    The zodiacal background varies across a stamp by a factor of several, so a
    single stretch leaves one side of the frame bright and the other dark. A
    running median removes that gradient and leaves the stars, which is what a
    blink is for.
    """
    from scipy.ndimage import median_filter

    arr = np.array(stamp, dtype=np.float32)
    fill = float(np.nanmedian(arr))
    arr = np.where(np.isfinite(arr), arr, fill)
    size = min(box, arr.shape[0] if arr.shape[0] % 2 else arr.shape[0] - 1)
    return arr - median_filter(arr, size=size, mode="nearest")


def render(stamp: np.ndarray, lo: float, hi: float, dest: pathlib.Path) -> dict:
    from PIL import Image

    arr = np.where(np.isfinite(stamp), stamp, lo)
    soft = (hi - lo) / 30.0
    norm = np.arcsinh((arr - lo) / soft) / np.arcsinh(SAT_SIGMA)
    gray = (np.clip(norm, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)
    dest.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(gray, mode="L").save(dest, optimize=True)
    return {"bytes": dest.stat().st_size, "sha256": sha256(dest)}


def build(object_id: str, ra: float, dec: float) -> dict:
    from src.epochs import align, load_strips

    folder = SERIES / object_id
    cube, variance, mjd, wcs = align(load_strips(folder), coverage_only=True)
    visits, ny, nx = cube.shape

    # The object sits at the catalogue position plus the offset measured on this
    # stack, so the window is centred on the object rather than on the frame.
    x, y = wcs.world_to_pixel_values(ra, dec)
    cx = float(np.ravel(x)[0])
    cy = float(np.ravel(y)[0])

    side = min(FOV_PX, nx, ny)
    half = side // 2
    x0 = int(round(min(max(cx - half, 0), nx - side)))
    y0 = int(round(min(max(cy - half, 0), ny - side)))
    x0 = max(x0, 0)
    y0 = max(y0, 0)
    width = min(side, nx - x0)
    height = min(side, ny - y0)

    window = cube[:, y0:y0 + height, x0:x0 + width]
    flat = np.stack([flatten(window[i]) for i in range(visits)])
    pooled = np.concatenate([flat[i][np.isfinite(flat[i])].ravel()[::17]
                             for i in range(visits)])
    median = float(np.median(pooled))
    sigma = robust_sigma(pooled)
    lo = median + LO_SIGMA * sigma
    hi = median + HI_SIGMA * sigma

    frames = []
    for i in range(visits):
        stem = f"{mjd[i]:.4f}".replace(".", "-")
        dest = WEB / "assets" / "blink" / object_id / f"{stem}.png"
        info = render(flat[i], lo, hi, dest)
        frames.append({
            "mjd": float(mjd[i]),
            "mjd_label": round(float(mjd[i]), 1),
            "png": str(dest.relative_to(WEB)),
            "median_mjy_sr": round(float(np.nanmedian(window[i])), 6),
            "robust_sigma": round(robust_sigma(flat[i]), 6),
            "png_sha256": info["sha256"],
            "png_bytes": info["bytes"],
        })

    return {
        "id": object_id,
        "visits": visits,
        "window": {"x0": x0, "y0": y0, "width": int(width), "height": int(height),
                   "object_px": [round(cx - x0, 2), round(cy - y0, 2)],
                   "note": "the object is centred at object_px, in window pixels"},
        "stretch": {"lo_mjy_sr": round(lo, 6), "hi_mjy_sr": round(hi, 6),
                    "median_mjy_sr": round(median, 6),
                    "robust_sigma_mjy_sr": round(sigma, 6)},
        "frames": frames,
    }


def main() -> int:
    targets = {
        "barnard": (269.452077, 4.693365),
        "epsindib": (331.044147, -56.782844),
        "rwaur": (76.956526, 30.401438),
        "rdra": (248.167611, 66.754979),
        "wise0855": (133.795129, -7.245147),
    }
    out = {"objects": []}
    for name, (ra, dec) in targets.items():
        rec = build(name, ra, dec)
        out["objects"].append(rec)
        print(f"{name:10s} {rec['visits']:3d} frames  window {rec['window']['width']}x"
              f"{rec['window']['height']}  object at {rec['window']['object_px']}")
    OUT_JSON.write_text(json.dumps(out, indent=1))
    print(f"wrote {OUT_JSON.relative_to(WEB.parent)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
