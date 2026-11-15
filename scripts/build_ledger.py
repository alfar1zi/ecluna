"""Build the provenance ledger the page shows behind the Numbers button.

Every claim the page makes is listed with the file it is read from, that file's
hash, and the result file the web copy was built from. Where the source is not in
the repository the ledger says so rather than leaving the row blank: a claim whose
source cannot be produced is a weaker claim, and the page should not hide that.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web" / "data"
OUT = WEB / "ledger.json"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def row(claim: str, data: str, source: str | None, uncertainty: str, status: str) -> dict:
    data_path = WEB / data
    source_path = ROOT / source if source else None
    return {
        "claim": claim,
        "data_file": f"web/data/{data}",
        "data_sha256": digest(data_path) if data_path.exists() else None,
        "source_file": source,
        "source_present": bool(source_path and source_path.exists()),
        "source_sha256": digest(source_path) if source_path and source_path.exists() else None,
        "uncertainty": uncertainty,
        "status": status,
    }


def main() -> None:
    rows = [
        row(
            "Three of the five named objects are recovered",
            "named_recovery_summary.json",
            "results/cache/named_object_recovery_20261102.json",
            "criteria v3, frozen before the run, sha256 ff65d657",
            "measured",
        ),
        row(
            "Across three fields the pipeline recovers 15 to 60% at 0.2 MJy/sr and all of them at 0.4",
            "completeness.json",
            "results/completeness_field-a.json",
            "Wilson 95% interval, 40 injections per point, 200 tracks per field",
            "measured",
        ),
        row(
            "The three fields disagree, and the spread is the result",
            "completeness.json",
            "results/completeness_field-b.json",
            "half recovery 0.176 MJy/sr in field A against 0.282 in field B",
            "measured",
        ),
        row(
            "A cutout this size can only track objects beyond 2,219 AU",
            "parallax.json",
            None,
            "half field 179.8 arcsec over a 213.3 day baseline",
            "measured, source not in the repository",
        ),
        row(
            "Sixteen sources are absent from the catalogue and move",
            "views.json",
            "results/classified_barnard.json",
            "speed floor 0.037 px per visit, threshold from the null",
            "measured",
        ),
        row(
            "The survey covers five patches over 258 visits",
            "blink.json",
            None,
            "36 to 70 visits per object, 182 to 373 day baselines",
            "measured",
        ),
        row(
            "No Planet X is detected",
            "parallax.json",
            None,
            "a negative result, bounded by the reach and the completeness above",
            "measured negative",
        ),
    ]

    payload = {
        "schema_version": "ledger-1",
        "note": (
            "Each row names the file the page reads and the result file that file was "
            "built from. Where the source is not in the repository the row says so: the "
            "web copy is still hashed, but the chain stops there."
        ),
        "rows": rows,
    }
    OUT.write_text(json.dumps(payload, indent=2) + "\n")
    missing = sum(1 for r in rows if not r["source_present"])
    print(f"wrote {OUT.relative_to(ROOT)}: {len(rows)} rows, {missing} without a source in the repository")


if __name__ == "__main__":
    main()
