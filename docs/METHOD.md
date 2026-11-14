# Method reference

Every number in `results/` is produced by one command. This page lists the command,
the input it reads, and the output it must produce. If a command produces a different
number, the source changed or the code changed, and the difference has to be explained
before the result is replaced.

## Environment

```
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Versions are pinned in `requirements.txt` and recorded in `docs/ENV.md`.

## Data

The measurement code reads data that is not in the repository, because a single cube
tile is 320 MB and a Level 2 frame is 70 MB. Acquisition is one command per group:

```
.venv/bin/python scripts/acquire.py tiles     # six cube tiles, hashed
.venv/bin/python scripts/acquire.py gaia      # Gaia DR3 around each target
.venv/bin/python scripts/acquire.py wise      # AllWISE around each target
.venv/bin/python scripts/acquire.py epochs    # index the blink strips
```

Each run appends to `results/foundation.json` with the row count, byte size and sha256
of every file. A result that cannot name its input file is not a result.

## Cube tiles

```
.venv/bin/python scripts/verify_tiles.py
```

Reads one spectrum from every acquired tile and checks three things: the cube is
102 x 512 x 512, at least 90 channels are finite at the best pixel, and channels 51
and 52 are empty. The last one is the documented dichroic gap, so a tile that fills
them is wrong.

Output: `results/tiles_verified.json`.

## Spectrum at a position

```
.venv/bin/python scripts/read_spectrum.py 270.3415 66.6023
```

Maps the position to a HEALPix order 5 tile, opens it, and prints the 102 channel
values at the tile centre. With `--tile` it reads a local file instead of the network.

## Detection limit

```
.venv/bin/python -m src.limit
```

Not a command line yet; the limit is produced by `limit_from_mef` in `src/limit.py`.
The C2 result is `results/limit_c2.json`.

The limit is

```
f_lim = k * sigma * sqrt(N_eff) / sqrt(N)
```

with `sigma` the median per-pixel noise from the VARIANCE extension, `N_eff` the
effective pixels under the PSF, `N` the number of visits, and `k` the threshold in
sigma. Two uncertainties are reported and never merged:

- **statistical**, a bootstrap interval on the median variance, usually tiny;
- **systematic**, the spread across the PSF width and the flag mask, usually dominant.

## Flag policy

The flag map is a bitmask defined in Table 16 of the SPHEREx Explanatory Supplement
(SSDC-DP-017 v2.1, 2026-11-10). Three groups matter:

| Group | Bits | Effect |
|---|---|---|
| Dead | NONFUNC 6, MISSING_DATA 9, HOT 10, COLD 11, NONLINEAR 15, DICHROIC 7, PHANMISS 14, OVERFLOW 1, SUR_ERROR 2 | area is lost |
| Per-exposure | TRANSIENT 0, OUTLIER 19, CROSSTALK 20, GHOST 22, GHOST_EXT 24, STREAK 25, BLOOM 26, SNOWBALL 27, HALO 28, SATELLITE_HALO 29 | one visit is spoiled, the pixel is not |
| Position | SOURCE 21 | threshold rises, area is kept |

SOURCE means "pixel mapped to a known source". It is a position, not a defect, and
masking it would delete most of a crowded field for no reason.

## Diagnosis

```
.venv/bin/python -m src.limit
```

`variance_budget` splits the variance into a background photon term and a read-noise
floor by regressing on the zodiacal map in bins. `confusion_share` measures the excess
variance in SOURCE pixels. `diagnose` then applies an ordered rule:

```
if area_loss > 0.5    -> area loss   (nothing helps)
elif confusion > 0.5  -> confusion   (fixed pattern, more visits do not help)
else                  -> background  (stochastic, improves as 1/sqrt(N))
```

Output: `results/diagnosis_fields.json`, six fields.

## Tests

```
.venv/bin/python -m pytest -q
```

The suite covers the tile index arithmetic, the limit scaling, the flag policy, the
variance budget and the diagnosis rule. A test that cannot fail is not a test, so the
flag policy tests assert that SOURCE and TRANSIENT keep the area while NONFUNC removes
it.
