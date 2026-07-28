# pricecalc — backend

FastAPI service wrapping a framework-free quantitative core.

```
src/pricecalc/
├── core/               pure maths, no FastAPI imports — unit-testable in isolation
│   └── black_scholes.py
├── api/                HTTP boundary: pydantic schemas + routers
└── main.py             app factory, CORS, router mounting
```

## Setup

```bash
poetry env use python3.12
poetry install
```

## Run

```bash
poetry run pricecalc-api          # http://127.0.0.1:8000, docs at /docs
```

## Checks

```bash
poetry run pytest                             # all tests
poetry run pytest tests/unit -v               # unit only
poetry run pytest -k test_put_call_parity     # single test by name
poetry run ruff check --fix . && poetry run black .
poetry run mypy src/
```
