"""Build the completeness data the page draws, from the three measured curves.

The previous web copy carried nine levels and 600 injections per level, and no
result file in the repository produces those numbers: the run that made them is
not here. The three field curves below are measured, carry their own Wilson
intervals, and name the null file their threshold came from, so the page is built
from those instead. The numbers change; the chain of evidence does not break.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "web" / "data" / "completeness.json"

FIELDS = [
    ("field-a", "Field A"),
    ("field-b", "Field B"),
    ("ecliptic-pole", "Ecliptic pole"),
]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    series = []
    sources = []
    for key, label in FIELDS:
        path = ROOT / "results" / f"completeness_{key}.json"
        data = json.loads(path.read_text())
        curve = data["curve"]
        series.append(
            {
                "id": key,
                "label": label,
                "visits": curve["visits"],
                "tracks": curve["tracks"],
                "fwhm_px": curve["fwhm_px"],
                "f50": curve["f50"],
                "f50_ci": curve["f50_ci"],
                "threshold": data["threshold"],
                "threshold_source": data["threshold_source"],
                "mjd_first": data["mjd_first"],
                "mjd_last": data["mjd_last"],
                "levels": [
                    {
                        "flux_mjy_sr": level["flux"],
                        "injected": level["injected"],
                        "recovered": level["recovered"],
                        "completeness": level["completeness"],
                        "wilson95": [level["wilson_low"], level["wilson_high"]],
                    }
                    for level in curve["levels"]
                ],
            }
        )
        sources.append(
            {
                "path": f"results/completeness_{key}.json",
                "sha256": digest(path),
            }
        )

    payload = {
        "schema_version": "completeness-fields-1",
        "axis": "injected flux in MJy per steradian, the same unit the frames carry",
        "method": (
            "Tracks of a known flux were injected into the real frames and the pipeline "
            "was run on them. The curve is the fraction recovered at each flux, with a "
            "Wilson 95% interval, for each of the three fields that were measured."
        ),
        "not_claimed": [
            "absolute magnitude completeness, which needs a trustworthy zeropoint",
            "completeness for moving objects",
            "a stacking gain curve",
        ],
        "sources": sources,
        "fields": series,
    }
    OUT.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"wrote {OUT.relative_to(ROOT)}: {len(series)} fields, "
          f"{sum(len(s['levels']) for s in series)} points")


if __name__ == "__main__":
    main()
