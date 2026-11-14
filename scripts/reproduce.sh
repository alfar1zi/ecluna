#!/usr/bin/env bash
# Reproduce every result from the data on disk.
#
# Each step prints the command it runs. A step that fails stops the run, because a
# partial reproduction is worse than none: it looks like a pass.
set -euo pipefail

cd "$(dirname "$0")/.."
PY=".venv/bin/python"

if [ ! -x "$PY" ]; then
  echo "no virtual environment at .venv; see docs/ENV.md" >&2
  exit 1
fi

step() {
  echo
  echo "== $1"
  shift
  echo "\$ $*"
  "$@"
}

step "tests" "$PY" -m pytest -q

step "cube tiles" "$PY" scripts/verify_tiles.py

TILE="../ecluna/data/cube/Npix4010_cube.fits"
if [ -f "$TILE" ]; then
  step "spectrum at the C2 field" "$PY" scripts/read_spectrum.py --tile "$TILE"
else
  echo
  echo "== spectrum at the C2 field: skipped, no local tile at $TILE"
fi

echo
echo "== results on disk"
for f in results/*.json; do
  printf '  %-34s %s bytes\n' "$f" "$(wc -c < "$f")"
done

echo
echo "reproduction finished"
