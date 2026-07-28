# pricecalc

An options market-making sandbox — price European options, invert quotes back to
implied volatility, and (as the remaining tabs land) hunt static arbitrage across a
chain, build multi-leg strategies, and simulate quoting a book.

Python quantitative core behind FastAPI, React SPA on top. Market data is simulated;
no vendor feed or API key is required to run anything.

## Status

| Scenario | State | What it does |
|---|---|---|
| **Pricer** | ✅ Implemented | Black-Scholes-Merton price, seven Greeks, implied vol with no-arbitrage band checking, spot sweeps |
| **Arbitrage** | 🚧 Scaffolded | Put-call parity, vertical/butterfly/calendar bounds, each violation with its replicating trade |
| **Strategy** | 🚧 Scaffolded | Multi-leg net Greeks, payoff diagram, breakevens, max P&L |
| **Market making** | 🚧 Scaffolded | Surface-driven quoting, inventory skew, simulated flow, P&L attribution |

The scaffolded tabs render their own specs in-app, so the intended scope is visible
without reading the source.

## Quick start

Two processes. Backend first:

```bash
cd backend
poetry env use python3.12
poetry install
poetry run pricecalc-api          # http://127.0.0.1:8000  ·  docs at /docs
```

Then the frontend:

```bash
cd frontend
pnpm install
pnpm dev                          # http://localhost:5173
```

Vite proxies `/api` to the backend, so there is no base URL to configure and CORS
never fires in development.

## Layout

```
backend/
  src/pricecalc/
    core/black_scholes.py    pricing, Greeks, implied vol — no framework imports
    api/                     pydantic schemas + routers
    main.py                  app, CORS, /api mount
  tests/{unit,integration}
frontend/
  src/
    components/features/     one directory per scenario tab
    components/charts/       Recharts wrappers + shared theme
    lib/pricing.ts           TanStack Query hooks
    stores/useMarketStore.ts global market state vector
```

## What the Pricer gives you

Price, intrinsic, time value, forward and log-moneyness, plus **delta, gamma, vega,
theta, rho, vanna and volga** — all in trader units (vega per vol point, theta per
calendar day, rho per 1% of rate), labelled as such in the UI because that is the
usual source of confusion.

The implied-vol solver checks the no-arbitrage band *before* root-finding. A premium
below discounted intrinsic or above the discounted underlying has no implied vol at
all, and the API returns a 422 with the band attached rather than a clamped number.
That rejection is the first arbitrage signal in the app, and the foundation the
Arbitrage tab builds on.

## Testing

The maths is verified three independent ways: a textbook closed-form value, put-call
parity across six market regimes, and central finite differences against every
analytic Greek (which is what catches unit-scaling mistakes).

```bash
cd backend  && poetry run pytest        # 158 tests
cd frontend && pnpm test:run            # 14 tests
```

## Development

See [CLAUDE.md](./CLAUDE.md) for architecture notes, conventions and gotchas.
