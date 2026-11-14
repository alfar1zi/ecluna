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
