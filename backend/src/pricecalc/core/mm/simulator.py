"""A time-stepped market-making simulation with P&L attribution.

The maker quotes one option, takes whatever flow arrives, and carries the
resulting inventory. Each step: the underlying moves, the option is revalued,
quotes are refreshed against current inventory, arrivals are drawn, and the
book is marked.

**P&L is decomposed rather than reported as one number**, because the single
number hides the only question worth asking: was the money made by capturing
spread, or by being accidentally long a market that went up? Those look
identical on a P&L line and could not be more different — the first is a
business, the second is luck that will reverse.

Three components, and they sum to the total by construction:

* **Spread capture** — the edge earned at the moment of each fill, measured as
  the distance from fair value. Always non-negative; this is the business.
* **Inventory P&L** — mark-to-market on the position between fills. This is the
  cost of doing the business, and it is what the skew exists to control.
* **Hedge P&L** — what the delta hedge made or lost, when hedging is on.

Everything is seeded, so a run is reproducible from its parameters.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from pricecalc.core.black_scholes import OptionType, greeks, price
from pricecalc.core.mm.quoting import QuoteParams, fill_probability, make_quote
from pricecalc.core.surface import VolSurface


@dataclass(frozen=True, slots=True)
class SimulationParams:
    """One market-making session.

    Attributes:
        spot: Starting underlying price.
        drift: Real-world drift of the underlying. Left at zero by default: a
            non-zero drift makes a directionally-biased maker look skilled, and
            the point of the simulation is to separate skill from direction.
        rate: Risk-free rate used for discounting.
        div_yield: Continuous dividend yield.
        strike: The option being made.
        expiry: Its time to expiry at the start, in years.
        option_type: Call or put.
        horizon: Length of the session in years.
        steps: Number of time steps.
        hedge_delta: Whether to hedge the delta of accumulated inventory.
        hedge_threshold: Delta drift tolerated before re-hedging. Hedging every
            step is optimal only if trading is free; a band trades a little
            slippage for far fewer hedges.
        hedge_cost_bps: Cost per hedge trade, in basis points of notional.
        seed: Fixes both the price path and the order flow.
    """

    spot: float = 100.0
    drift: float = 0.0
    rate: float = 0.04
    div_yield: float = 0.0
    strike: float = 100.0
    expiry: float = 0.25
    option_type: OptionType = OptionType.CALL
    horizon: float = 1.0 / 52.0
    steps: int = 200
    hedge_delta: bool = True
    hedge_threshold: float = 0.5
    hedge_cost_bps: float = 1.0
    seed: int = 42


@dataclass(frozen=True, slots=True)
class Step:
    t: float
    spot: float
    fair_value: float
    bid: float
    ask: float
    reservation: float
    skew: float
    inventory: float
    delta_exposure: float
    hedge_position: float
    spread_pnl: float
    inventory_pnl: float
    hedge_pnl: float
    total_pnl: float
    buys: int
    sells: int


@dataclass(frozen=True, slots=True)
class SimulationResult:
    steps: tuple[Step, ...]
    spread_pnl: float
    inventory_pnl: float
    hedge_pnl: float
    total_pnl: float
    fills: int
    buys: int
    sells: int
    hedge_trades: int
    max_abs_inventory: float
    ending_inventory: float
    realised_vol: float
    metadata: dict[str, float] = field(default_factory=dict)


def run(
    params: SimulationParams,
    quote_params: QuoteParams,
    surface: VolSurface | None = None,
) -> SimulationResult:
    """Run one session and return the path plus attributed P&L."""
    if params.steps < 2:
        raise ValueError("a simulation needs at least two steps")
    if params.horizon >= params.expiry:
        raise ValueError("the session must end before the option expires")

    surface = surface or VolSurface()
    rng = np.random.default_rng(params.seed)
    dt = params.horizon / params.steps

    spot = params.spot
    inventory = 0.0
    hedge_position = 0.0
    spread_pnl = 0.0
    inventory_pnl = 0.0
    hedge_pnl = 0.0
    fills = buys = sells = hedge_trades = 0
    max_abs_inventory = 0.0

    forward = spot * math.exp((params.rate - params.div_yield) * params.expiry)
    vol = surface.vol_for_strike(params.strike, forward, params.expiry)
    prev_value = price(
        spot, params.strike, params.rate, params.div_yield, vol, params.expiry, params.option_type
    )
    prev_spot = spot
    log_returns: list[float] = []

    steps: list[Step] = []

    for i in range(params.steps):
        t = i * dt
        tau = params.expiry - t
        remaining = params.horizon - t

        forward = spot * math.exp((params.rate - params.div_yield) * tau)
        vol = surface.vol_for_strike(params.strike, forward, tau)
        fair = price(
            spot, params.strike, params.rate, params.div_yield, vol, tau, params.option_type
        )
        g = greeks(spot, params.strike, params.rate, params.div_yield, vol, tau, params.option_type)

        # Mark the book before trading, so spread capture and inventory P&L
        # never double-count the same price move.
        if i > 0:
            inventory_pnl += inventory * (fair - prev_value)
            hedge_pnl += hedge_position * (spot - prev_spot)

        quote = make_quote(
            fair_value=fair,
            inventory=inventory,
            delta=g.delta,
            spot=spot,
            vol=vol,
            horizon=max(remaining, dt),
            params=quote_params,
        )

        step_buys = step_sells = 0

        # A customer selling to us lifts our bid; the edge is fair less the bid.
        if quote.bid > 0.0:
            distance = fair - quote.bid
            if rng.random() < fill_probability(distance, dt, quote_params):
                inventory += 1.0
                spread_pnl += distance
                fills += 1
                buys += 1
                step_buys = 1

        if math.isfinite(quote.ask):
            distance = quote.ask - fair
            if rng.random() < fill_probability(distance, dt, quote_params):
                inventory -= 1.0
                spread_pnl += distance
                fills += 1
                sells += 1
                step_sells = 1

        delta_exposure = inventory * g.delta
        if params.hedge_delta:
            drift_from_flat = delta_exposure + hedge_position
            if abs(drift_from_flat) > params.hedge_threshold:
                trade = -drift_from_flat
                hedge_position += trade
                hedge_pnl -= abs(trade) * spot * params.hedge_cost_bps / 10_000.0
                hedge_trades += 1

        max_abs_inventory = max(max_abs_inventory, abs(inventory))
        steps.append(
            Step(
                t=t,
                spot=spot,
                fair_value=fair,
                bid=quote.bid,
                ask=quote.ask if math.isfinite(quote.ask) else fair * 4.0,
                reservation=quote.reservation_price,
                skew=quote.skew,
                inventory=inventory,
                delta_exposure=delta_exposure,
                hedge_position=hedge_position,
                spread_pnl=spread_pnl,
                inventory_pnl=inventory_pnl,
                hedge_pnl=hedge_pnl,
                total_pnl=spread_pnl + inventory_pnl + hedge_pnl,
                buys=step_buys,
                sells=step_sells,
            )
        )

        prev_value = fair
        prev_spot = spot

        # Evolve the underlying. Log-Euler is exact for geometric Brownian
        # motion, so step size affects only path resolution, not correctness.
        shock = float(rng.normal())
        increment = (params.drift - 0.5 * vol * vol) * dt + vol * math.sqrt(dt) * shock
        spot *= math.exp(increment)
        log_returns.append(increment)

    realised = float(np.std(log_returns, ddof=1) / math.sqrt(dt)) if len(log_returns) > 1 else 0.0

    return SimulationResult(
        steps=tuple(steps),
        spread_pnl=spread_pnl,
        inventory_pnl=inventory_pnl,
        hedge_pnl=hedge_pnl,
        total_pnl=spread_pnl + inventory_pnl + hedge_pnl,
        fills=fills,
        buys=buys,
        sells=sells,
        hedge_trades=hedge_trades,
        max_abs_inventory=max_abs_inventory,
        ending_inventory=inventory,
        realised_vol=realised,
        metadata={"implied_vol_at_open": vol, "dt": dt},
    )
