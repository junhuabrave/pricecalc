"""Black-Scholes-Merton pricing, Greeks and implied volatility.

The model prices European options on an asset paying a continuous dividend
yield ``q``. Every function here is pure and scalar; vectorised sweeps are
built on top in :mod:`pricecalc.core.strategy` and the market-data layer.

Greek unit conventions
----------------------
Greeks are returned in the units a trader reads off a risk screen, *not* raw
partial derivatives. The conversion is applied once, at the boundary:

===========  ==========================================  ================
Greek        Meaning                                     Unit
===========  ==========================================  ================
``delta``    dV/dS                                       per $1 of spot
``gamma``    d2V/dS2                                     per $1 of spot
``vega``     dV/dsigma / 100                             per 1 vol point
``theta``    dV/dt / 365                                 per calendar day
``rho``      dV/dr / 100                                 per 1% of rate
``vanna``    d2V/dS dsigma / 100                         delta per vol pt
``volga``    d2V/dsigma2 / 10000                         vega per vol pt
===========  ==========================================  ================

``theta`` is negative for long premium. ``vega``/``volga`` scale by 100 and
10000 respectively because a "vol point" is 0.01 in decimal terms.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from scipy.optimize import brentq

SQRT_2PI: Final = math.sqrt(2.0 * math.pi)
SQRT_2: Final = math.sqrt(2.0)

# Below these thresholds an input is treated as exactly zero. Guards the
# division by sigma*sqrt(T) in d1 and keeps expiry-day pricing finite.
MIN_TIME: Final = 1e-12
MIN_VOL: Final = 1e-12

# Search bracket for the implied-vol root finder (decimal vol, so 0.0001% to 1000%).
IV_LOWER: Final = 1e-6
IV_UPPER: Final = 10.0


class OptionType(StrEnum):
    CALL = "call"
    PUT = "put"

    @property
    def sign(self) -> int:
        """+1 for a call, -1 for a put — lets one formula serve both."""
        return 1 if self is OptionType.CALL else -1


class NoImpliedVolError(ValueError):
    """Raised when a price admits no Black-Scholes implied volatility.

    This is not a numerical failure: it means the quote sits outside the
    model's attainable range (below intrinsic or above the discounted
    underlying), which is itself a static-arbitrage signal.
    """


@dataclass(frozen=True, slots=True)
class Greeks:
    """First- and second-order risk, in trader units (see module docstring)."""

    delta: float
    gamma: float
    vega: float
    theta: float
    rho: float
    vanna: float
    volga: float


@dataclass(frozen=True, slots=True)
class PricingResult:
    price: float
    greeks: Greeks
    d1: float
    d2: float
    forward: float
    intrinsic: float
    time_value: float


def norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / SQRT_2PI


def norm_cdf(x: float) -> float:
    """Standard normal CDF via erfc — accurate in both tails, unlike 1-N(-x)."""
    return 0.5 * math.erfc(-x / SQRT_2)


def forward_price(spot: float, rate: float, div_yield: float, tau: float) -> float:
    """Forward F = S * exp((r - q) * tau)."""
    return spot * math.exp((rate - div_yield) * tau)


def d1_d2(
    spot: float, strike: float, rate: float, div_yield: float, vol: float, tau: float
) -> tuple[float, float]:
    """The two Black-Scholes moneyness terms.

    Degenerate inputs (tau or vol at zero) push d1/d2 to +/-inf, which makes the
    normal CDFs collapse to the correct deterministic 0/1 payoff indicator.
    """
    if tau <= MIN_TIME or vol <= MIN_VOL:
        fwd = forward_price(spot, rate, div_yield, max(tau, 0.0))
        limit = math.inf if fwd > strike else (-math.inf if fwd < strike else 0.0)
        return limit, limit

    vol_sqrt_t = vol * math.sqrt(tau)
    d1 = (math.log(spot / strike) + (rate - div_yield + 0.5 * vol * vol) * tau) / vol_sqrt_t
    return d1, d1 - vol_sqrt_t


def price(
    spot: float,
    strike: float,
    rate: float,
    div_yield: float,
    vol: float,
    tau: float,
    option_type: OptionType,
) -> float:
    """Black-Scholes-Merton price of a European option.

    Args:
        spot: Current underlying price S.
        strike: Strike K.
        rate: Continuously-compounded risk-free rate r (decimal, 0.05 = 5%).
        div_yield: Continuous dividend yield q (decimal).
        vol: Volatility sigma (decimal, 0.20 = 20%).
        tau: Time to expiry in years.
        option_type: Call or put.
    """
    _validate(spot, strike, tau)
    phi = option_type.sign

    if tau <= MIN_TIME:
        return max(phi * (spot - strike), 0.0)

    disc_r = math.exp(-rate * tau)
    disc_q = math.exp(-div_yield * tau)

    if vol <= MIN_VOL:
        # Deterministic underlying: discounted intrinsic on the forward.
        return disc_r * max(phi * (forward_price(spot, rate, div_yield, tau) - strike), 0.0)

    d1, d2 = d1_d2(spot, strike, rate, div_yield, vol, tau)
    return phi * (spot * disc_q * norm_cdf(phi * d1) - strike * disc_r * norm_cdf(phi * d2))


def greeks(
    spot: float,
    strike: float,
    rate: float,
    div_yield: float,
    vol: float,
    tau: float,
    option_type: OptionType,
) -> Greeks:
    """Analytic Greeks, returned in trader units (see module docstring)."""
    _validate(spot, strike, tau)
    phi = option_type.sign

    # At expiry every sensitivity vanishes except a step-function delta.
    if tau <= MIN_TIME:
        itm = phi * (spot - strike) > 0
        return Greeks(
            delta=float(phi) if itm else 0.0,
            gamma=0.0,
            vega=0.0,
            theta=0.0,
            rho=0.0,
            vanna=0.0,
            volga=0.0,
        )

    # Zero volatility with time left is a *different* limit, and collapsing the
    # two was a bug: the payoff is certain, but it is not immediate. An
    # in-the-money option is then a forward contract on the difference, and a
    # forward has delta, rho and theta — only the volatility-driven sensitivities
    # disappear. Reported values are the limits as vol -> 0+, so `greeks()`
    # agrees with `price()`, which already handles this case.
    if vol <= MIN_VOL:
        disc_r = math.exp(-rate * tau)
        disc_q = math.exp(-div_yield * tau)
        if phi * (forward_price(spot, rate, div_yield, tau) - strike) <= 0:
            return Greeks(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
        return Greeks(
            delta=phi * disc_q,
            gamma=0.0,
            vega=0.0,
            theta=phi * (div_yield * spot * disc_q - rate * strike * disc_r) / 365.0,
            rho=phi * strike * tau * disc_r / 100.0,
            vanna=0.0,
            volga=0.0,
        )

    d1, d2 = d1_d2(spot, strike, rate, div_yield, vol, tau)
    sqrt_t = math.sqrt(tau)
    disc_r = math.exp(-rate * tau)
    disc_q = math.exp(-div_yield * tau)
    pdf_d1 = norm_pdf(d1)

    # Raw partial derivatives, per unit of the underlying variable and per year.
    delta = phi * disc_q * norm_cdf(phi * d1)
    gamma = disc_q * pdf_d1 / (spot * vol * sqrt_t)
    vega_raw = spot * disc_q * pdf_d1 * sqrt_t
    theta_raw = (
        -spot * disc_q * pdf_d1 * vol / (2.0 * sqrt_t)
        + phi * div_yield * spot * disc_q * norm_cdf(phi * d1)
        - phi * rate * strike * disc_r * norm_cdf(phi * d2)
    )
    rho_raw = phi * strike * tau * disc_r * norm_cdf(phi * d2)
    vanna_raw = -disc_q * pdf_d1 * d2 / vol
    volga_raw = vega_raw * d1 * d2 / vol

    return Greeks(
        delta=delta,
        gamma=gamma,
        vega=vega_raw / 100.0,
        theta=theta_raw / 365.0,
        rho=rho_raw / 100.0,
        vanna=vanna_raw / 100.0,
        volga=volga_raw / 10_000.0,
    )


def evaluate(
    spot: float,
    strike: float,
    rate: float,
    div_yield: float,
    vol: float,
    tau: float,
    option_type: OptionType,
) -> PricingResult:
    """Price + Greeks + diagnostics in one pass — what the API layer returns."""
    px = price(spot, strike, rate, div_yield, vol, tau, option_type)
    grk = greeks(spot, strike, rate, div_yield, vol, tau, option_type)
    d1, d2 = d1_d2(spot, strike, rate, div_yield, vol, tau)
    intrinsic = max(option_type.sign * (spot - strike), 0.0)
    return PricingResult(
        price=px,
        greeks=grk,
        d1=d1,
        d2=d2,
        forward=forward_price(spot, rate, div_yield, tau),
        intrinsic=intrinsic,
        time_value=px - intrinsic,
    )


def price_bounds(
    spot: float, strike: float, rate: float, div_yield: float, tau: float, option_type: OptionType
) -> tuple[float, float]:
    """No-arbitrage (lower, upper) bounds on a European option price.

    Lower bound is the discounted intrinsic on the forward; upper bound is the
    discounted underlying for a call, or the discounted strike for a put. Any
    quote outside this band is a static arbitrage regardless of volatility.
    """
    disc_r = math.exp(-rate * tau)
    disc_q = math.exp(-div_yield * tau)
    if option_type is OptionType.CALL:
        return max(spot * disc_q - strike * disc_r, 0.0), spot * disc_q
    return max(strike * disc_r - spot * disc_q, 0.0), strike * disc_r


def implied_vol(
    target_price: float,
    spot: float,
    strike: float,
    rate: float,
    div_yield: float,
    tau: float,
    option_type: OptionType,
) -> float:
    """Invert Black-Scholes for volatility using Brent's method.

    Price is strictly increasing in vol, so the root is unique and bracketing
    is safe. We check the no-arbitrage band first: a quote outside it has no
    implied vol at all, and saying so is more useful than returning a clamped
    number that silently hides an arbitrage.

    Raises:
        NoImpliedVolError: The price is at or outside the attainable range.
    """
    _validate(spot, strike, tau)
    if tau <= MIN_TIME:
        raise NoImpliedVolError("Cannot imply volatility at expiry (tau = 0)")

    lower, upper = price_bounds(spot, strike, rate, div_yield, tau, option_type)
    # Tolerance scaled to the quote so it behaves on both penny and index options.
    tol = max(1e-10, 1e-10 * spot)
    if target_price <= lower + tol:
        raise NoImpliedVolError(
            f"Price {target_price:.6f} is at or below the no-arbitrage lower bound "
            f"{lower:.6f}; no positive implied volatility exists."
        )
    if target_price >= upper - tol:
        raise NoImpliedVolError(
            f"Price {target_price:.6f} is at or above the no-arbitrage upper bound "
            f"{upper:.6f}; no finite implied volatility exists."
        )

    def objective(vol: float) -> float:
        return price(spot, strike, rate, div_yield, vol, tau, option_type) - target_price

    hi = IV_UPPER
    # The bracket is guaranteed by the bound checks above, but a deep-ITM long-dated
    # quote can need vol > IV_UPPER before the price crosses. Widen a few times.
    while objective(hi) < 0.0 and hi < 1_000.0:
        hi *= 4.0
    if objective(hi) < 0.0:  # pragma: no cover - unreachable given the bound checks
        raise NoImpliedVolError("Failed to bracket the implied volatility root")

    return float(brentq(objective, IV_LOWER, hi, xtol=1e-12, rtol=1e-12, maxiter=200))


def _validate(spot: float, strike: float, tau: float) -> None:
    if spot <= 0.0:
        raise ValueError(f"spot must be positive, got {spot}")
    if strike <= 0.0:
        raise ValueError(f"strike must be positive, got {strike}")
    if tau < 0.0:
        raise ValueError(f"tau must be non-negative, got {tau}")
