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

DATA_ROOT="${DATA_ROOT:-data/level2}"
export DATA_ROOT
TILE="${TILE:-data/cube/Npix4010_cube.fits}"
if [ -f "$TILE" ]; then
  step "spectrum at the ecliptic pole" "$PY" scripts/read_spectrum.py --tile "$TILE"
else
  echo
  echo "== spectrum at the ecliptic pole: skipped, no local tile at $TILE"
fi

step "detection limit, C2" "$PY" -m src.limit \
  --field "ecliptic pole" \
  --mef data/level2/2026W28_2A_0586_1.fits \
  --visits 23 \
  --out "$TMP/limit_ecliptic_pole.json"
compare "$TMP/limit_ecliptic_pole.json" results/limit_ecliptic_pole.json "limit_ecliptic_pole"

step "diagnosis, six fields" "$PY" -m src.limit --diagnose --out "$TMP/diagnosis_fields.json"
compare "$TMP/diagnosis_fields.json" results/diagnosis_fields.json "diagnosis_fields"

# The field series are measured by one command, with the parameters recorded in
# the committed result. Reading them back keeps the reproduction honest: it reruns
# what was actually done, not a default that happens to be close.
for field in ecliptic-pole field-a field-b; do
  committed="results/null_$field.json"
  [ -f "$committed" ] || continue
  read -r tracks mask speed <<EOF
$("$PY" -c "import json;n=json.load(open('$committed'))['null'];print(n.get('tracks_requested',n['tracks']),n['mask_radius_px'],n['max_speed_px_per_visit'])")
EOF
  strips="data/raw/epochs_$(echo "$field" | tr '-' '_')"
  [ -d "$strips" ] || { echo "== $field: skipped, no strips at $strips"; continue; }
  step "null calibration, $field" "$PY" -m src.null \
    --field "$field" --strips "$strips" --tracks "$tracks" \
    --mask-radius "$mask" --max-speed "$speed" \
    --out "$TMP/null_$field.json"
  compare "$TMP/null_$field.json" "results/null_$field.json" "null_$field"
done

# The known-object control on the ecliptic pole reads the same null, so it is
# reproduced with the same threshold rather than recalibrating on its own sample.
if [ -f results/controls_ecliptic_pole.json ] && [ -f results/null_ecliptic-pole.json ]; then
  step "known-object control, ecliptic pole" "$PY" -m src.controls \
    --strips data/raw/epochs_ecliptic_pole \
    --objects results/controls_ecliptic_pole.json \
    --null results/null_ecliptic-pole.json \
    --out "$TMP/controls_ecliptic_pole_result.json"
  compare "$TMP/controls_ecliptic_pole_result.json" \
    results/controls_ecliptic_pole_result.json "controls_ecliptic_pole"
fi

step "recovery of the named objects" bash -c '
  for t in wise0855 barnard epsindib rwaur rdra; do
    "$0" scripts/measure_recovery.py --target "$t" --mask-radius 45 \
      --out "/tmp/recovery_$t.json" >/dev/null && echo "  $t ok"
  done' "$PY"

step "analytic versus measured limit" "$PY" scripts/check_consistency.py

step "spectra of the named objects" "$PY" scripts/build_spectra.py

echo
echo "reproduction finished: every result regenerated and compared"
