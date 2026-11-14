# Ecluna

A tool for looking at the same patch of sky across many SPHEREx visits, and for
measuring what such a search can and cannot see.

Most tools show the sky. This one also says what is blocking the view: for any patch,
it reports the faintest moving object SPHEREx could still detect there, and names the
reason that number is what it is.

## What it does

1. **Blink.** Enter a position, get the visits to that patch in order, and flip through
   them to spot anything that moved.
2. **Spectrum.** Click a pixel and read its 102-channel spectrum from the all-sky cube.
3. **Limit.** Get the faintest moving object that would have been detected, with a
   confidence interval and a sample count.
4. **Diagnosis.** Get the reason: too few visits, a crowded field, or a bright
   background, each with the remedy that follows from it.

## What it does not claim

No mass, no orbit, no position for any unknown object. No statement that a planet does
not exist. The output is a limit on depth, with the range of separations and
brightnesses that were actually tested.

## Layout

```
src/            measurement code: cube reader, detection limit, diagnosis
scripts/        acquisition, verification, reproduction
tests/          unit and invariant tests
results/        measured values, each with its source file and hash
docs/           environment and method reference
web/            static site, no runtime network calls
```

## Install

```
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## Run

```
.venv/bin/python -m pytest -q          # tests
./scripts/reproduce.sh                 # every result, from the data on disk
```

`scripts/reproduce.sh` prints the command it runs for each result and fails if a
number changes without the source changing.

## Data

| Source | What it provides |
|---|---|
| SPHEREx DR1 all-sky cube (NASA IPAC IRSA) | 102-channel spectra, zodiacal light subtracted, 12.9 arcsec per pixel |
| SPHEREx DR1 Level 2 spectral images (NASA IPAC IRSA) | IMAGE, FLAGS, VARIANCE, ZODI, ePSF, WCS-WAVE |
| SPHEREx spectral channel table (NASA IPAC IRSA) | 102 channel wavelengths, bandwidths, resolving power |
| 2MASS (NASA IPAC IRSA) | star positions for registration and masking |
| AllWISE (NASA IPAC IRSA) | long baseline positions for the proper motion overlay |
| Gaia DR3 (ESA) | proper motions and parallax |
| JPL Horizons | predicted positions of known objects |

Every figure in the product points to a file with a recorded sha256. The manifest is
`results/foundation.json`.

## Team

| Name | Role |
|---|---|
| Alfarizi | data, backend, product |
| Alezuna Nadhif | logic, backend |
| Regon Schefendi | UI, frontend |

## License

Apache-2.0. See `LICENSE`.
