#!/usr/bin/env bash
# Reproduce every result from the data on disk and compare it with what is committed.
#
# A result that cannot be regenerated is not a result. A result that regenerates to a
# different number is a finding, not a pass, so this script fails and prints both.
set -euo pipefail

cd "$(dirname "$0")/.."
PY=".venv/bin/python"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

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

compare() {
  local fresh="$1" committed="$2" label="$3"
  if [ ! -f "$committed" ]; then
    echo "  $label: no committed result to compare against"
    return 0
  fi
  if diff -q "$fresh" "$committed" >/dev/null; then
    echo "  $label: identical to the committed result"
  else
    echo "  $label: DIFFERS from the committed result" >&2
    diff -u "$committed" "$fresh" | head -40 >&2
    return 1
  fi
}

step "tests" "$PY" -m pytest -q

step "cube tiles" "$PY" scripts/verify_tiles.py

DATA_ROOT="${DATA_ROOT:-../data/level2}"
export DATA_ROOT
TILE="${TILE:-../data/cube/Npix4010_cube.fits}"
if [ -f "$TILE" ]; then
  step "spectrum at the ecliptic pole" "$PY" scripts/read_spectrum.py --tile "$TILE"
else
  echo
  echo "== spectrum at the ecliptic pole: skipped, no local tile at $TILE"
fi

step "detection limit, C2" "$PY" -m src.limit \
  --field "ecliptic pole" \
  --mef ../ecluna/data/level2/2026W28_2A_0586_1.fits \
  --visits 19 \
  --out "$TMP/limit_c2.json"
compare "$TMP/limit_c2.json" results/limit_ecliptic_pole.json "limit_c2"

step "diagnosis, six fields" "$PY" -m src.limit --diagnose --out "$TMP/diagnosis_fields.json"
compare "$TMP/diagnosis_fields.json" results/diagnosis_fields.json "diagnosis_fields"

echo
echo "reproduction finished: every result regenerated and compared"
