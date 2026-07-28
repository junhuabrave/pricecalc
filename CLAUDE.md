# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

An options market-making sandbox: a Python quantitative core exposed over FastAPI,
driven by a React SPA. Four scenarios are separate tabs — **Pricer** and
**Arbitrage** are implemented; **Strategy** and **Market making** are scaffolded
(see the `ComingSoon` panels for their specs). Market data is simulated; there is
no live feed, but `core/marketdata/base.py` defines the `ChainFeed` protocol a
live adapter would satisfy.

## Commands

All backend commands run from `backend/`, all frontend commands from `frontend/`.

```bash
# Backend — Poetry, Python 3.12, src layout
poetry install
poetry run pricecalc-api                       # uvicorn on :8000, OpenAPI at /docs
poetry run pytest                              # full suite
poetry run pytest tests/unit -v                # unit only
poetry run pytest -k test_put_call_parity      # single test by name
poetry run pytest tests/unit/test_arbitrage.py::TestPutCallParity::test_fair_parity_is_silent
poetry run ruff check --fix . && poetry run black .
poetry run mypy src/                           # strict mode

# Frontend — pnpm, Vite, React 19
pnpm install
pnpm dev                                       # :5173, proxies /api to :8000
pnpm test:run                                  # vitest single run
pnpm test:run src/lib/utils.test.ts            # single file
pnpm lint && pnpm typecheck && pnpm build
```

Both servers must be running for the UI to price anything — the frontend has no
local fallback. After changing a router, restart uvicorn; it runs without
`--reload` unless `DEBUG=true`.

**Run the CI gate, not just the fix commands, before pushing.** CI runs
`black --check .`, which *verifies*; `black .` *reformats* and always passes
locally, so a formatting failure only shows up on the PR:

```bash
cd backend  && poetry run ruff check . && poetry run black --check . \
            && poetry run mypy src/ && poetry run pytest
cd frontend && pnpm lint && pnpm typecheck && pnpm test:run && pnpm build
```

## Architecture

**The core is framework-free.** `backend/src/pricecalc/core/` imports no FastAPI and
no pydantic — it is plain functions over floats and frozen dataclasses. The HTTP
layer in `api/` owns validation and wire format, and converts core dataclasses into
pydantic responses via `from_core` classmethods. Keep new maths in `core/` and unit
test it directly; do not reach for `TestClient` to test a formula.

**Greek units are converted exactly once**, at the bottom of `black_scholes.greeks()`,
and never again. What leaves that function is already in trader units: vega per vol
point, theta per calendar day, rho per 1% of rate. `Greeks` field docs, `GreeksGrid`
notes and the finite-difference tests all assume this. If you add a Greek, scale it
there and add a matching FD test — the scaling is the part that breaks.

**Prices that admit no implied vol are an arbitrage signal, not an error to swallow.**
`implied_vol()` checks the no-arbitrage band before root-finding and raises
`NoImpliedVolError`; the route turns that into a 422 carrying the band. Do not clamp
to a fallback vol — the rejection is a product feature, and the same
bounds (`price_bounds()`) are what `check_absolute_bounds()` scans with.

**Pricing is a pure function of its inputs**, so TanStack Query caches results with
`staleTime: Infinity` (`frontend/src/lib/pricing.ts`). Query keys are the request
objects themselves. There is nothing to invalidate; if a result looks stale, the
inputs differ.

**Arbitrage findings execute at bid/ask, never mids, and must be self-financing.**
Every check in `core/arbitrage.py` buys at `ask` and sells at `bid`; a violation
priced off mids is a spread you cannot cross. Each `Violation` also carries the
`Leg`s of its replicating trade, and `sum(leg.cash_flow) == violation.profit` is
asserted in the tests. If you add a check, add both — a finding without a
financing trade is not a finding.

**A clean chain must produce zero findings.** `generate_chain()` prices off one
smile, so it satisfies every static bound by construction. The false-positive
suite sweeps rates, dividends, skews, spreads and ladder density asserting an
empty result. That negative test is what makes the scanner trustworthy; don't
weaken it to make a new check pass.

**Calendar checks are deliberately skipped when `div_yield > 0`.** With a
dividend yield a longer-dated European call can legitimately trade below a
shorter-dated one, so the ordering is not a bound. The summary reports
`calendar_checks_skipped` rather than emitting false positives. The general
condition needs total implied variance at matched forward-moneyness — an
interpolated surface, not raw quotes.

**The simulator is the test oracle, so its determinism is load-bearing.**
`generate_chain(seed=…)` is fully reproducible — the same request yields the same
chain and therefore the same findings, which is why `/api/arbitrage/scan` takes
generation parameters rather than a chain. Planted mispricings are *solved*
against the bound they target (set the bid to exactly what the check compares
against, plus an edge), not random markups — a percentage bump on a cheap
contract is absorbed by the spread and plants nothing. Plants are limited to one
per expiry: two on the same expiry can cancel, because lifting a quote also
widens its ask, which un-breaks a bound an earlier plant was solved against.

**The market state vector is global.** `useMarketStore` (Zustand) holds spot, strike,
rate, dividend yield, vol, expiry and option type. The Pricer writes it; the other
three tabs are meant to read the same vector rather than keep their own copies.

## Conventions

- Backend: `src/` layout, type hints everywhere, `from __future__ import annotations`
  at the top of each module. Ruff (`E,F,I,N,UP,ANN,S,B,A,C4,RUF`) and mypy strict
  both gate CI.
- Frontend: named exports only, no `export default`. One component per file, props
  interface above the component, `FC<Props>` typed. `cn()` for className merging.
  `@/` maps to `src/`. TypeScript is strict with `noUncheckedIndexedAccess` and
  `exactOptionalPropertyTypes`.
- Tests co-locate with components on the frontend (`Component.test.tsx`); the
  backend mirrors `src/` under `tests/unit` and `tests/integration`.
- `Card` sets `aria-label` from its title, so tests scope with
  `within(screen.getByRole('region', { name: 'Valuation' }))`. Several labels
  (Delta, Gamma…) appear in both the Greeks grid and the chart toggles — unscoped
  queries will match twice.

## Gotchas

- `exactOptionalPropertyTypes` is on, so passing an explicit `undefined` to an
  optional prop is a type error, not a no-op. `valueClassName={cond ? 'x' : undefined}`
  fails; use `''` or omit the prop with a spread.
- `NumberField` holds a draft string while focused. Binding a number straight to the
  input makes `"0."` unrepresentable and the field fights the user mid-keystroke.
- Recharts' tooltip `formatter`/`labelFormatter` are typed loosely; parameters are
  declared `unknown` and coerced.
- jsdom reports zero-size elements, so `src/test/setup.ts` stubs `ResizeObserver` and
  `getBoundingClientRect` — without it Recharts renders nothing and chart tests fail.
- Chart theme constants live in `chartTheme.ts`, not alongside components; mixing
  them trips the Fast Refresh lint rule.

## Git

Trunk-based, Conventional Commits, no direct commits to `main`. Branch as
`<type>/<short-description>`, rebase onto `main`, squash-merge, delete the branch.
Run the full local checks (both suites, lint, typecheck) before opening a PR.
