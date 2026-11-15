# Environment

Versions used for every result in `results/`.

| Component | Version |
|---|---|
| Python | 3.12.3 |
| numpy | 2.5.4 |
| scipy | 1.18.1 |
| astropy | 8.0.2 |
| reproject | 0.21.0 |
| astroquery | 0.4.11 |
| pillow | 13.0.0 |
| pytest | 9.2.0 |

Install:

```
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Versions are pinned in `requirements.txt`. A run is only comparable to another run
made with the same pins; the event logs record the interpreter version alongside
each result.

## Run logs

A transcript under `results/logs/` is evidence and is committed with the result it
explains. It must not carry the absolute path of the machine that produced it, so
scrub it before staging:

```
.venv/bin/python scripts/scrub_log.py results/logs/*.log
```

CI rejects any tracked file that matches `/home/<user>/`, which is what a Python
warning prints on its own line. Suppressing the warning would hide a real finding
(an empty slice in the stack), so the path is removed and the warning stays.
