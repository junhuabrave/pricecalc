"""Inventory-aware quoting, after Avellaneda and Stoikov (2008).

A naive market maker quotes symmetrically around fair value and accumulates
whatever the market wants to give it. That is profitable until it is not: the
position drifts, and the mark-to-market loss on inventory swamps the spread
captured earning it.

The fix has two parts, and they are separate ideas that are easy to conflate:

**Skew — where to centre the quotes.** The mid is shifted away from fair value
against the inventory, to a *reservation price*: the price at which the maker
is indifferent to holding what it holds. Long inventory pushes both quotes
down, which makes the bid less attractive and the offer more attractive, so
flow arrives that flattens the book. This is not a forecast of direction — it
is a statement about the maker's own risk, and it works even if the underlying
is a pure martingale.

**Width — how far apart to put them.** Half-spread grows with inventory risk
and with how patient the flow is. The ``ln(1 + gamma/kappa)`` term is the
compensation for adverse selection: quote tighter than that and the fills you
get are the ones you did not want.

Both scale with ``horizon``, the time left over which risk must be carried.
Risk that must be held overnight deserves a wider market than risk that can be
unwound in a minute.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

MIN_HALF_SPREAD = 1e-6


@dataclass(frozen=True, slots=True)
class QuoteParams:
    """Maker configuration.

    Attributes:
        risk_aversion: ``gamma``. Zero quotes symmetrically around fair with a
            minimal spread — the naive maker, useful as a control. Larger
            values skew harder and quote wider.
        order_flow_intensity: ``A`` in ``lambda = A*exp(-kappa*delta)``, in
            arrivals **per year** at zero distance from fair — the same clock
            as every other time quantity in the codebase. The default is about
            6000, or roughly 24 marketable orders per trading day in this one
            contract. Quoting time in years makes this number look strange; the
            alternative is a second time unit and the bugs that come with it.
        order_flow_decay: ``kappa``, per unit of *price* distance. Large kappa
            means impatient flow that only trades tight markets. It also sets
            the floor on the adverse-selection premium, which tends to
            ``1/kappa`` as risk aversion goes to zero.
        min_half_spread: A floor, standing in for the tick and for fees.
        max_position: Inventory beyond which the maker stops adding, quoting
            one side only. A real desk has a limit; a model without one will
            happily accumulate an unbounded position.
    """

    risk_aversion: float = 0.10
    order_flow_intensity: float = 6000.0
    order_flow_decay: float = 8.0
    min_half_spread: float = 0.01
    max_position: float = 25.0


@dataclass(frozen=True, slots=True)
class Quote:
    fair_value: float
    reservation_price: float
    bid: float
    ask: float
    half_spread: float
    skew: float
    """Reservation price less fair value. Negative when long — the maker marks
    its own quotes down to attract the flow that would flatten it."""

    @property
    def spread(self) -> float:
        return self.ask - self.bid


def price_variance(delta: float, spot: float, vol: float) -> float:
    """Instantaneous variance of the *option's* price, per year.

    The maker's risk is not the underlying's variance but the option's, and to
    first order the option moves ``delta`` for every unit the underlying moves.
    Squaring that gives price variance in currency-squared per year, which is
    the unit Avellaneda-Stoikov needs.
    """
    return (delta * spot * vol) ** 2


def make_quote(
    fair_value: float,
    inventory: float,
    delta: float,
    spot: float,
    vol: float,
    horizon: float,
    params: QuoteParams,
) -> Quote:
    """Two-sided market in one option, skewed and widened for inventory.

    Args:
        fair_value: Model value of the option.
        inventory: Signed position in this option, positive long.
        delta: The option's delta, used to size inventory risk.
        spot: Underlying price.
        vol: Underlying volatility.
        horizon: Years of risk still to carry. Drives both skew and width.
        params: Maker configuration.
    """
    variance = price_variance(delta, spot, vol)
    gamma = params.risk_aversion

    # Reservation price: fair value adjusted for the risk already on the book.
    skew = -inventory * gamma * variance * horizon
    reservation = fair_value + skew

    # Inventory term plus the adverse-selection premium. With no risk aversion
    # the second term is undefined in the limit, so the maker falls back to the
    # floor: a risk-neutral maker has no reason to charge for inventory at all.
    inventory_width = 0.5 * gamma * variance * horizon
    if gamma > 0.0 and params.order_flow_decay > 0.0:
        adverse_selection = math.log1p(gamma / params.order_flow_decay) / gamma
    else:
        adverse_selection = 0.0

    half = max(params.min_half_spread, inventory_width + 0.5 * adverse_selection)

    bid = reservation - half
    ask = reservation + half

    # Position limit: stop bidding when maximally long, stop offering when
    # maximally short. Pulling the quote entirely is cleaner than widening it
    # to a level nobody would ever hit.
    if inventory >= params.max_position:
        bid = 0.0
    if inventory <= -params.max_position:
        ask = math.inf

    return Quote(
        fair_value=fair_value,
        reservation_price=reservation,
        bid=max(0.0, bid),
        ask=ask,
        half_spread=half,
        skew=skew,
    )


def fill_probability(distance: float, dt: float, params: QuoteParams) -> float:
    """Chance of a resting quote trading within ``dt``.

    Arrivals are Poisson with intensity falling exponentially in the quote's
    distance from fair, ``lambda = A*exp(-kappa*delta)``. Over a short interval
    the probability of at least one arrival is ``1 - exp(-lambda*dt)``.

    A quote *through* fair value (negative distance) is strictly better than
    the market and fills essentially on contact, so intensity is capped rather
    than allowed to grow without bound.
    """
    if distance < 0.0:
        distance = 0.0
    intensity = params.order_flow_intensity * math.exp(-params.order_flow_decay * distance)
    return 1.0 - math.exp(-intensity * dt)
