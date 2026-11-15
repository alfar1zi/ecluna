"""Strip absolute local paths from a transcript before it is committed.

Run logs are evidence and belong in the repository, but they must not carry the
absolute path of the machine that produced them: it is noise at best and a leak at
worst. CI rejects any tracked file matching /home/<user>/, so the scrub happens
before the commit rather than after a failed build.

    .venv/bin/python scripts/scrub_log.py results/logs/*.log

Each file is rewritten in place. The command prints what it changed and exits 0
even when nothing matched, so it can be chained unconditionally.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# Any absolute path under a home directory, which is what CI looks for, plus the
# resolved repository root even when it lives somewhere else.
PATTERNS = [
    (re.compile(re.escape(str(ROOT)) + r"/?"), "./"),
    (re.compile(r"/(?:home|Users)/[^/\s]+/[^\s:]*?(?=/)"), "."),
]


def scrub(text: str) -> tuple[str, int]:
    changed = 0
    for pattern, replacement in PATTERNS:
        text, count = pattern.subn(replacement, text)
        changed += count
    return text, changed


def main(argv: list[str]) -> int:
    paths = [Path(p) for p in argv[1:]]
    if not paths:
        print("usage: scrub_log.py <file> [file ...]", file=sys.stderr)
        return 2
    for path in paths:
        original = path.read_text()
        cleaned, changed = scrub(original)
        if not changed:
            print(f"{path}: clean")
            continue
        path.write_text(cleaned)
        print(f"{path}: replaced {changed} absolute path(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
