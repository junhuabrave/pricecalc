"""Canonical option structures, built at fair value.

Legs are priced with Black-Scholes at the supplied volatility, so a preset opens
at theoretical value with no edge. That is deliberate: it makes the payoff
diagram show the *structure's* shape rather than the shape plus an arbitrary
entry error, and it means a preset's net cost is directly comparable to its
maximum profit.

Strikes are placed relative to spot by ``width`` (a fraction of spot), which
keeps every preset meaningful on a $5 stock and a $5,000 index alike.
"""

from __future__ import annotations

from enum import StrEnum

from pricecalc.core.black_scholes import OptionType, price
from pricecalc.core.strategy import LegKind, StrategyLeg


class Preset(StrEnum):
    LONG_CALL = "long_call"
    LONG_PUT = "long_put"
    BULL_CALL_SPREAD = "bull_call_spread"
    BEAR_PUT_SPREAD = "bear_put_spread"
    STRADDLE = "straddle"
    STRANGLE = "strangle"
    BUTTERFLY = "butterfly"
    IRON_CONDOR = "iron_condor"
    COVERED_CALL = "covered_call"
    COLLAR = "collar"
    CALENDAR = "calendar"


PRESET_SUMMARY: dict[Preset, str] = {
    Preset.LONG_CALL: "Unlimited upside, loss capped at the premium.",
    Preset.LONG_PUT: "Profits as spot falls; loss capped at the premium.",
    Preset.BULL_CALL_SPREAD: "Bullish debit spread — both profit and loss are capped.",
    Preset.BEAR_PUT_SPREAD: "Bearish debit spread — both profit and loss are capped.",
    Preset.STRADDLE: "Long volatility: pays for a large move in either direction.",
    Preset.STRANGLE: "Cheaper long volatility; needs a bigger move than a straddle.",
    Preset.BUTTERFLY: "Pinned-to-strike bet. Cheap, capped, and short volatility.",
    Preset.IRON_CONDOR: "Range-bound credit structure; capped on both wings.",
    Preset.COVERED_CALL: "Long stock with the upside sold off for premium.",
    Preset.COLLAR: "Long stock fenced by a long put and a short call.",
    Preset.CALENDAR: "Sells near-dated decay against a longer-dated hedge.",
}


def build(
    preset: Preset,
    spot: float = 100.0,
    rate: float = 0.04,
    div_yield: float = 0.0,
    vol: float = 0.20,
    tau: float = 0.25,
    width: float = 0.05,
    far_tau: float = 0.75,
) -> tuple[StrategyLeg, ...]:
    """Construct a preset's legs at fair value.

    Args:
        preset: Which structure to build.
        spot: Underlying price; strikes are placed around it.
        rate: Continuously-compounded risk-free rate.
        div_yield: Continuous dividend yield.
        vol: Volatility used to price every leg.
        tau: Near expiry in years.
        width: Strike offset as a fraction of spot.
        far_tau: Back-month expiry, used by the calendar only.
    """
    step = spot * width

    def opt(kind: LegKind, qty: float, strike: float, expiry: float) -> StrategyLeg:
        option_type = OptionType.CALL if kind is LegKind.CALL else OptionType.PUT
        fair = price(spot, strike, rate, div_yield, vol, expiry, option_type)
        return StrategyLeg(
            kind=kind, quantity=qty, entry_price=fair, strike=strike, tau=expiry, vol=vol
        )

    def stock(qty: float) -> StrategyLeg:
        return StrategyLeg(kind=LegKind.UNDERLYING, quantity=qty, entry_price=spot)

    match preset:
        case Preset.LONG_CALL:
            return (opt(LegKind.CALL, 1.0, spot, tau),)
        case Preset.LONG_PUT:
            return (opt(LegKind.PUT, 1.0, spot, tau),)
        case Preset.BULL_CALL_SPREAD:
            return (
                opt(LegKind.CALL, 1.0, spot, tau),
                opt(LegKind.CALL, -1.0, spot + 2 * step, tau),
            )
        case Preset.BEAR_PUT_SPREAD:
            return (
                opt(LegKind.PUT, 1.0, spot, tau),
                opt(LegKind.PUT, -1.0, spot - 2 * step, tau),
            )
        case Preset.STRADDLE:
            return (opt(LegKind.CALL, 1.0, spot, tau), opt(LegKind.PUT, 1.0, spot, tau))
        case Preset.STRANGLE:
            return (
                opt(LegKind.PUT, 1.0, spot - 2 * step, tau),
                opt(LegKind.CALL, 1.0, spot + 2 * step, tau),
            )
        case Preset.BUTTERFLY:
            return (
                opt(LegKind.CALL, 1.0, spot - 2 * step, tau),
                opt(LegKind.CALL, -2.0, spot, tau),
                opt(LegKind.CALL, 1.0, spot + 2 * step, tau),
            )
        case Preset.IRON_CONDOR:
            return (
                opt(LegKind.PUT, 1.0, spot - 4 * step, tau),
                opt(LegKind.PUT, -1.0, spot - 2 * step, tau),
                opt(LegKind.CALL, -1.0, spot + 2 * step, tau),
                opt(LegKind.CALL, 1.0, spot + 4 * step, tau),
            )
        case Preset.COVERED_CALL:
            return (stock(1.0), opt(LegKind.CALL, -1.0, spot + 2 * step, tau))
        case Preset.COLLAR:
            return (
                stock(1.0),
                opt(LegKind.PUT, 1.0, spot - 2 * step, tau),
                opt(LegKind.CALL, -1.0, spot + 2 * step, tau),
            )
        case Preset.CALENDAR:
            return (
                opt(LegKind.CALL, -1.0, spot, tau),
                opt(LegKind.CALL, 1.0, spot, max(far_tau, tau * 2.0)),
            )
