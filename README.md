# Ecluna

A tool for looking at the same patch of sky across many SPHEREx visits, and for
measuring what such a search can and cannot see.

## Status

Early. The repository holds the environment pins and the license. The measurement
code and the web tool are not in the tree yet.

## Layout

```
docs/ENV.md      interpreter and library versions
requirements.txt pinned dependencies
LICENSE          Apache-2.0
CITATION.cff     citation metadata
```

## Environment

```
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## Team

| Name | Role |
|---|---|
| Alfarizi | data, backend, product |
| Alezuna Nadhif | logic, backend |
| Regon Schefendi | UI, frontend |

## License

Apache-2.0. See `LICENSE`.
