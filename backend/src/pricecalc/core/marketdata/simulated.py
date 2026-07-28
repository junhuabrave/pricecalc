"""A synthetic option chain, arbitrage-free by construction unless told otherwise.

Prices come from Black-Scholes on a skewed smile, so the resulting chain
satisfies every static bound the scanner tests. That is the point: a clean
chain must produce **zero** findings, which makes the scanner falsifiable. Any
violation it reports on a clean chain is a bug in the scanner, not a signal.

Mispricings are then injected deliberately, one per requested violation, with a
recorded ground truth. Tests assert the scanner finds exactly what was planted.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from pricecalc.core.black_scholes import OptionType, price
from pricecalc.core.chain import Chain, Quote


@dataclass(frozen=True, slots=True)
class SmileParams:
    """A skewed, convex smile in log-moneyness k = ln(K/F).

    ``skew`` is negative for equities — downside strikes trade at higher vol
    because the demand for crash protection is one-sided. ``curvature`` lifts
    both wings relative to the at-the-money level.
    """

    atm_vol: float = 0.20
    skew: float = -0.12
    curvature: float = 0.45
    # Long-dated smiles flatten as the distribution of returns tends to normal.
    term_flattening: float = 0.35
    min_vol: float = 0.02

    def vol(self, log_moneyness: float, tau: float) -> float:
        damp = 1.0 / (1.0 + self.term_flattening * math.sqrt(max(tau, 1e-9)))
        k = log_moneyness
        v = self.atm_vol + damp * (self.skew * k + self.curvature * k * k)
        return max(v, self.min_vol)


@dataclass(frozen=True, slots=True)
class PlantedViolation:
    """Ground truth for an injected mispricing — what a test should expect back."""

    kind: str
    tau: float
    strike: float
    option_type: OptionType
    description: str


@dataclass(frozen=True, slots=True)
class SimulatedChain:
    """A generated chain plus the record of anything deliberately broken."""

    chain: Chain
    planted: tuple[PlantedViolation, ...]

    @property
    def name(self) -> str:
        return "simulated"

    def snapshot(self) -> Chain:
        return self.chain


def _half_spread(mid: float, vega: float, spread_bps: float, min_tick: float) -> float:
    """Spread widens with vega and with the option's own price.

    Real markets are wider where the market maker's risk is larger, so a
    proportional term (price) plus a risk term (vega) beats a flat tick — and
    it keeps deep-OTM options from showing an implausibly tight two-sided market.
    """
    return max(min_tick, 0.5 * (spread_bps / 10_000.0) * mid + 0.02 * vega)


def generate_chain(
    spot: float = 100.0,
    rate: float = 0.04,
    div_yield: float = 0.0,
    expiries: tuple[float, ...] = (0.08, 0.25, 0.5, 1.0),
    strike_count: int = 11,
    strike_span: float = 0.30,
    smile: SmileParams | None = None,
    spread_bps: float = 80.0,
    min_tick: float = 0.01,
    n_violations: int = 0,
    seed: int = 42,
) -> SimulatedChain:
    """Build a chain, optionally planting `n_violations` mispricings.

    Args:
        spot: Underlying price.
        rate: Continuously-compounded risk-free rate.
        div_yield: Continuous dividend yield. Non-zero disables calendar checks.
        expiries: Times to expiry in years.
        strike_count: Strikes per expiry (forced odd so one lands at-the-money).
        strike_span: Half-width of the strike ladder, as a fraction of spot.
        smile: Volatility smile; a skewed equity default is used when omitted.
        spread_bps: Proportional component of the bid/ask, in basis points.
        min_tick: Floor on the half-spread.
        n_violations: How many mispricings to plant. Capped at one per expiry,
            since two plants on the same expiry can cancel each other out.
        seed: Fixes both the strike jitter and the planted violations.
    """
    rng = np.random.default_rng(seed)
    smile = smile or SmileParams()
    if strike_count % 2 == 0:
        strike_count += 1  # keep a strike exactly at the money

    quotes: list[Quote] = []
    for tau in expiries:
        forward = spot * math.exp((rate - div_yield) * tau)
        strikes = np.linspace(spot * (1.0 - strike_span), spot * (1.0 + strike_span), strike_count)

        for raw_strike in strikes:
            strike = round(float(raw_strike), 2)
            k = math.log(strike / forward)
            vol = smile.vol(k, tau)

            for opt in (OptionType.CALL, OptionType.PUT):
                mid = price(spot, strike, rate, div_yield, vol, tau, opt)
                # Vega drives the risk component of the spread.
                vega = (
                    spot
                    * math.exp(-div_yield * tau)
                    * math.sqrt(tau)
                    * math.exp(-0.5 * k * k)
                    / 2.5
                )
                half = _half_spread(mid, vega, spread_bps, min_tick)
                bid = max(0.0, round(mid - half, 4))
                ask = round(mid + half, 4)
                quotes.append(Quote(tau=tau, strike=strike, option_type=opt, bid=bid, ask=ask))

    planted: list[PlantedViolation] = []
    if n_violations > 0:
        # Edge must clear the spreads it has to breach, so scale it to the underlying
        # rather than to the (possibly tiny) price of a deep-OTM option.
        edge = max(0.05, 0.004 * spot)
        quotes, planted = _plant(quotes, rng, n_violations, spot, rate, div_yield, edge)

    return SimulatedChain(
        chain=Chain(spot=spot, rate=rate, div_yield=div_yield, quotes=tuple(quotes)),
        planted=tuple(planted),
    )


def _plant(
    quotes: list[Quote],
    rng: np.random.Generator,
    count: int,
    spot: float,
    rate: float,
    div_yield: float,
    edge: float,
) -> tuple[list[Quote], list[PlantedViolation]]:
    """Construct each mispricing to breach one named bound by a known margin.

    An earlier version just marked a random quote up by a percentage and hoped
    something broke. It usually didn't: 30% of a deep-OTM option is a few cents,
    which the bid/ask absorbs. Each plant here is *solved* against the bound it
    targets — set the bid to exactly what the check compares against, plus
    ``edge`` — so the violation is guaranteed and its size is known in advance.

    A plant often trips neighbouring checks too (a call bid lifted above the
    next strike's offer also distorts the local butterfly). That is faithful to
    how one stale quote looks on a real screen; ``PlantedViolation`` records the
    bound that was deliberately targeted.
    """
    out = list(quotes)
    where = {(q.tau, q.strike, q.option_type): i for i, q in enumerate(out)}
    taus = sorted({q.tau for q in out if q.tau > 0.05})
    planted: list[PlantedViolation] = []
    used: set[tuple[float, float, OptionType]] = set()

    if not taus:
        return out, planted

    def rewrite(key: tuple[float, float, OptionType], new_bid: float) -> Quote:
        q = out[where[key]]
        bid = round(max(0.0, new_bid), 4)
        ask = round(max(q.ask, bid + max(q.spread, 0.01)), 4)
        replacement = Quote(tau=q.tau, strike=q.strike, option_type=q.option_type, bid=bid, ask=ask)
        out[where[key]] = replacement
        return replacement

    kinds = ["vertical_monotonicity", "butterfly_convexity", "put_call_parity"]

    # One plant per expiry. Two plants on the same expiry interfere: lifting a
    # quote also widens its ask, which can un-break the bound an earlier plant
    # was solved against. Isolating them keeps every ground truth valid.
    order = list(taus)
    rng.shuffle(order)

    for n, tau_value in enumerate(order[:count]):
        tau = float(tau_value)
        strikes = sorted({q.strike for q in out if q.tau == tau})
        if len(strikes) < 3:
            continue
        kind = kinds[n % len(kinds)]

        if kind == "vertical_monotonicity":
            # Lift a higher strike's call bid above the next lower strike's offer.
            i = int(rng.integers(len(strikes) - 1))
            lo, hi = strikes[i], strikes[i + 1]
            key = (tau, hi, OptionType.CALL)
            if key in used:
                continue
            target = out[where[(tau, lo, OptionType.CALL)]].ask + edge
            new = rewrite(key, target)
            used.add(key)
            planted.append(
                PlantedViolation(
                    kind=kind,
                    tau=tau,
                    strike=hi,
                    option_type=OptionType.CALL,
                    description=(
                        f"call {hi:g} bid lifted to {new.bid:.4f}, above the {lo:g} offer"
                    ),
                )
            )

        elif kind == "butterfly_convexity":
            # Make the middle strike concave against its two wings.
            i = int(rng.integers(len(strikes) - 2))
            lo, mid, hi = strikes[i], strikes[i + 1], strikes[i + 2]
            key = (tau, mid, OptionType.CALL)
            if key in used:
                continue
            span = hi - lo
            w_lo, w_hi = (hi - mid) / span, (mid - lo) / span
            target = (
                w_lo * out[where[(tau, lo, OptionType.CALL)]].ask
                + w_hi * out[where[(tau, hi, OptionType.CALL)]].ask
                + edge
            )
            new = rewrite(key, target)
            used.add(key)
            planted.append(
                PlantedViolation(
                    kind=kind,
                    tau=tau,
                    strike=mid,
                    option_type=OptionType.CALL,
                    description=(
                        f"call {mid:g} bid lifted to {new.bid:.4f}, breaking convexity "
                        f"against {lo:g}/{hi:g}"
                    ),
                )
            )

        else:  # put_call_parity — richen the call until a reversal is free money.
            strike = float(strikes[int(rng.integers(len(strikes)))])
            key = (tau, strike, OptionType.CALL)
            if key in used or (tau, strike, OptionType.PUT) not in where:
                continue
            put = out[where[(tau, strike, OptionType.PUT)]]
            target = (
                put.ask + spot * math.exp(-div_yield * tau) - strike * math.exp(-rate * tau) + edge
            )
            new = rewrite(key, target)
            used.add(key)
            planted.append(
                PlantedViolation(
                    kind=kind,
                    tau=tau,
                    strike=strike,
                    option_type=OptionType.CALL,
                    description=(
                        f"call {strike:g} bid lifted to {new.bid:.4f}, breaking parity "
                        f"against the {strike:g} put"
                    ),
                )
            )

    return out, planted
