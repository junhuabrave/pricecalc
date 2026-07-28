# pricecalc

An options market-making sandbox — price European options, invert quotes back to
implied volatility, and scan a chain for static arbitrage. Multi-leg strategy
construction and market-making simulation are the remaining tabs.

Python quantitative core behind FastAPI, React SPA on top. Market data is simulated;
no vendor feed or API key is required to run anything.

## Status

| Scenario | State | What it does |
|---|---|---|
| **Pricer** | ✅ Implemented | Black-Scholes-Merton price, seven Greeks, implied vol with no-arbitrage band checking, spot sweeps |
| **Arbitrage** | ✅ Implemented | Absolute bounds, put-call parity, vertical monotonicity + slope caps, butterfly convexity, calendar ordering — each finding with its replicating trade and locked-in profit |
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
    core/                    pure maths — no framework imports anywhere in here
      black_scholes.py       pricing, Greeks, implied vol
      chain.py               two-sided quotes indexed by expiry/strike/right
      arbitrage.py           six families of static no-arbitrage check
      marketdata/            ChainFeed protocol + seeded simulator
    api/                     pydantic schemas + routers
    main.py                  app, CORS, /api mount
  tests/{unit,integration}
frontend/
  src/
    components/features/     one directory per scenario tab
    components/charts/       Recharts wrappers + shared theme
    lib/                     TanStack Query hooks, one module per domain
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

## What the Arbitrage scanner gives you

Six families of **model-free** static bound — they hold under any dynamics, need
no volatility input, and are enforceable by holding the replicating portfolio to
expiry. There is no model to be wrong about.

Two rules make the findings real rather than cosmetic:

- **Execution prices, never mids.** Legs you buy cost the ask; legs you sell pay
  the bid. A "violation" measured off mids is a spread you cannot cross.
- **The published trade must finance the reported profit.** Every finding ships
  its legs, and the legs' net cash flow equals the stated edge — asserted in the
  tests, so a finding you could not actually put on fails the build.

The generated chain is arbitrage-free by construction, so a clean scan **must**
return nothing. That negative result is the scanner's own regression test, and
it's exposed in the UI: dial planted mispricings to zero and the panel should go
quiet. Anything it reports there is a bug in the scanner, not a signal.

One deliberate silence: **calendar checks are skipped when the dividend yield is
non-zero**, because a longer-dated European call can then legitimately trade
below a shorter-dated one. Reporting those would be false positives, so the API
says the check was skipped rather than handing you noise.

## Testing

The maths is verified three independent ways: a textbook closed-form value, put-call
parity across six market regimes, and central finite differences against every
analytic Greek (which is what catches unit-scaling mistakes).

```bash
cd backend  && poetry run pytest        # 231 tests
cd frontend && pnpm test:run            # 14 tests
```

## Development

See [CLAUDE.md](./CLAUDE.md) for architecture notes, conventions and gotchas.
