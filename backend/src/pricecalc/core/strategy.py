"""Multi-leg strategy analytics: net risk, payoff, breakevens, extremes.

**When every leg shares one expiry, payoff is piecewise linear in the terminal
spot**, with kinks only at the strikes. That fact drives the module:

* Breakevens are the roots of a piecewise-linear function, so linear
  interpolation between adjacent kinks is *exact* — not an approximation that
  gets better with more points.
* Its extremes occur at a kink or at infinity, so max profit and max loss come
  from evaluating the kinks and inspecting the asymptotic slope. A grid search
  would approximate the same answers and miss an unbounded wing entirely.

**Multiple expiries break that.** The payoff is taken at the *nearest* expiry,
where longer-dated legs have not settled — they still carry time value and are
marked with Black-Scholes over their remaining life. That makes the curve smooth
rather than kinked, so roots are bracketed on a grid and bisected, and the
turning point can sit between strikes. `StrategyAnalysis.exact` says which
regime produced the numbers.

Ignoring this is the classic calendar-spread error: settle both legs at once and
the two calls cancel exactly, flattening the diagram into a horizontal line at
minus the debit and erasing the tent shape that is the whole structure.

Terminal spot is bounded below by zero, so only the upper wing can run away.
That asymmetry is why `max_loss` is finite for a long straddle but `max_profit`
is not.

Quantities are signed and expressed in units of the underlying: a contract
multiplier is a presentation concern and is deliberately not modelled here.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum
from itertools import pairwise

from pricecalc.core.black_scholes import Greeks, OptionType, greeks, price

# Kinks closer together than this are treated as one, so a duplicated strike
# does not produce a zero-length segment for the root finder.
STRIKE_EPS = 1e-9


class LegKind(StrEnum):
    CALL = "call"
    PUT = "put"
    UNDERLYING = "underlying"


@dataclass(frozen=True, slots=True)
class StrategyLeg:
    """One position. ``quantity`` is signed: positive long, negative short.

    ``entry_price`` is what was actually paid or received per unit, which is
    what makes the P&L a P&L rather than a valuation. ``strike``, ``tau`` and
    ``vol`` are required for option legs and ignored for the underlying.
    """

    kind: LegKind
    quantity: float
    entry_price: float
    strike: float | None = None
    tau: float | None = None
    vol: float | None = None

    def __post_init__(self) -> None:
        if self.kind is LegKind.UNDERLYING:
            return
        if self.strike is None or self.strike <= 0.0:
            raise ValueError(f"{self.kind.value} leg needs a positive strike, got {self.strike}")
        if self.tau is None or self.tau < 0.0:
            raise ValueError(f"{self.kind.value} leg needs a non-negative tau, got {self.tau}")
        if self.vol is None or self.vol <= 0.0:
            raise ValueError(f"{self.kind.value} leg needs a positive vol, got {self.vol}")

    @property
    def option_type(self) -> OptionType | None:
        if self.kind is LegKind.CALL:
            return OptionType.CALL
        if self.kind is LegKind.PUT:
            return OptionType.PUT
        return None

    def terminal_value(self, spot: float) -> float:
        """Value of one unit at expiry — intrinsic for options, spot for stock."""
        if self.kind is LegKind.UNDERLYING:
            return spot
        assert self.strike is not None  # noqa: S101 - guaranteed by __post_init__
        if self.kind is LegKind.CALL:
            return max(spot - self.strike, 0.0)
        return max(self.strike - spot, 0.0)

    @property
    def label(self) -> str:
        if self.kind is LegKind.UNDERLYING:
            return "underlying"
        assert self.strike is not None and self.tau is not None  # noqa: S101
        return f"{self.tau:.4g}y {self.strike:g} {self.kind.value}"


@dataclass(frozen=True, slots=True)
class Extreme:
    """A best or worst case. ``spot`` is None when the extreme is at infinity."""

    value: float
    spot: float | None
    unbounded: bool


@dataclass(frozen=True, slots=True)
class PayoffPoint:
    spot: float
    payoff: float
    value: float


@dataclass(frozen=True, slots=True)
class StrategyAnalysis:
    net_cost: float
    net_greeks: Greeks
    breakevens: tuple[float, ...]
    max_profit: Extreme
    max_loss: Extreme
    payoff_slope_up: float
    payoff_slope_down: float
    kinks: tuple[float, ...]
    curve: tuple[PayoffPoint, ...]
    horizon_tau: float
    """The nearest expiry. Legs living beyond it are marked, not settled."""
    exact: bool
    """True when one expiry makes the payoff piecewise linear, so breakevens
    and extremes are solved in closed form rather than searched on a grid."""


def net_cost(legs: tuple[StrategyLeg, ...]) -> float:
    """Cash paid to open, per unit. Positive is a debit, negative a credit."""
    return sum(leg.quantity * leg.entry_price for leg in legs)


def horizon_tau(legs: tuple[StrategyLeg, ...]) -> float:
    """The nearest option expiry — the natural horizon for a payoff diagram."""
    taus = [leg.tau for leg in legs if leg.tau is not None]
    return min(taus) if taus else 0.0


def is_single_expiry(legs: tuple[StrategyLeg, ...]) -> bool:
    """True when every option leg shares one expiry, which is what makes the
    payoff piecewise linear and the exact analysis below valid."""
    return len({leg.tau for leg in legs if leg.tau is not None}) <= 1


def payoff(
    legs: tuple[StrategyLeg, ...],
    terminal_spot: float,
    rate: float = 0.0,
    div_yield: float = 0.0,
) -> float:
    """P&L at the nearest expiry.

    Legs expiring at that horizon settle to intrinsic. **Longer-dated legs do
    not** — they still carry time value, so they are marked with Black-Scholes
    over their remaining life. Treating every leg as expiring at once is the
    classic error in a calendar spread: the two legs cancel exactly and the
    diagram flattens into a straight line at minus the debit, hiding the tent
    shape that is the entire point of the structure.

    A surviving leg makes the curve smooth rather than kinked, which is why
    `analyse` reports multi-expiry results as approximate.
    """
    h = horizon_tau(legs)
    gross = 0.0

    for leg in legs:
        if leg.kind is LegKind.UNDERLYING:
            gross += leg.quantity * terminal_spot
            continue

        assert leg.tau is not None and leg.strike is not None  # noqa: S101
        assert leg.vol is not None  # noqa: S101
        remaining = leg.tau - h

        if remaining <= STRIKE_EPS:
            gross += leg.quantity * leg.terminal_value(terminal_spot)
            continue

        opt = leg.option_type
        assert opt is not None  # noqa: S101

        if terminal_spot <= 0.0:
            # Black-Scholes is undefined at zero spot, but the limit is not:
            # a call is worthless and a put is worth the discounted strike,
            # since the underlying can never recover from zero.
            survivor = 0.0 if opt is OptionType.CALL else leg.strike * math.exp(-rate * remaining)
        else:
            survivor = price(terminal_spot, leg.strike, rate, div_yield, leg.vol, remaining, opt)
        gross += leg.quantity * survivor

    return gross - net_cost(legs)


def net_greeks(legs: tuple[StrategyLeg, ...], spot: float, rate: float, div_yield: float) -> Greeks:
    """Portfolio risk: the quantity-weighted sum of each leg's Greeks.

    Legs may sit on different expiries — a calendar spread is still one
    portfolio, and its risks add. The underlying contributes delta 1 per unit
    and nothing else.
    """
    totals = dict.fromkeys(("delta", "gamma", "vega", "theta", "rho", "vanna", "volga"), 0.0)

    for leg in legs:
        if leg.kind is LegKind.UNDERLYING:
            totals["delta"] += leg.quantity
            continue
        opt = leg.option_type
        assert opt is not None and leg.tau is not None  # noqa: S101
        assert leg.strike is not None and leg.vol is not None  # noqa: S101
        g = greeks(spot, leg.strike, rate, div_yield, leg.vol, leg.tau, opt)
        for name in totals:
            totals[name] += leg.quantity * getattr(g, name)

    return Greeks(**totals)


def asymptotic_slopes(legs: tuple[StrategyLeg, ...]) -> tuple[float, float]:
    """Payoff slope as spot runs to infinity, and as it falls to zero.

    Deep in the money a call moves one-for-one with spot and a put is dead;
    deep out the reverse. Summing those limits gives the wing slopes, and the
    sign of the upper one decides whether profit or loss is unbounded.
    """
    up = 0.0
    down = 0.0
    for leg in legs:
        if leg.kind is LegKind.CALL:
            up += leg.quantity
        elif leg.kind is LegKind.PUT:
            down -= leg.quantity
        else:
            up += leg.quantity
            down += leg.quantity
    return up, down


def kink_points(legs: tuple[StrategyLeg, ...]) -> list[float]:
    """Strikes where the payoff changes slope, deduplicated and sorted."""
    strikes = sorted({leg.strike for leg in legs if leg.strike is not None})
    out: list[float] = []
    for k in strikes:
        if not out or k - out[-1] > STRIKE_EPS:
            out.append(k)
    return out


def breakevens(
    legs: tuple[StrategyLeg, ...], rate: float = 0.0, div_yield: float = 0.0
) -> list[float]:
    """Terminal spots where P&L crosses zero, at the nearest expiry.

    Single expiry: exact, not sampled. Between adjacent kinks the payoff is a
    straight line, so a sign change there is solved by linear interpolation
    with no error, and the segment beyond the last kink is solved from its
    known asymptotic slope.

    Multiple expiries: a surviving leg makes the curve smooth, so the roots are
    bracketed on a dense grid and refined by bisection instead.
    """
    if not is_single_expiry(legs):
        return _numeric_breakevens(legs, rate, div_yield)

    kinks = kink_points(legs)
    nodes = [0.0, *kinks]
    found: list[float] = []

    for node in nodes:
        if abs(payoff(legs, node, rate, div_yield)) <= STRIKE_EPS:
            found.append(node)

    for left, right in pairwise(nodes):
        p_left = payoff(legs, left, rate, div_yield)
        p_right = payoff(legs, right, rate, div_yield)
        if p_left * p_right < 0.0:
            found.append(left + (right - left) * (-p_left) / (p_right - p_left))

    # The unbounded segment to the right of the final kink.
    slope_up, _ = asymptotic_slopes(legs)
    if kinks and abs(slope_up) > STRIKE_EPS:
        last = kinks[-1]
        p_last = payoff(legs, last, rate, div_yield)
        if p_last * slope_up < 0.0:
            root = last - p_last / slope_up
            if root > last + STRIKE_EPS:
                found.append(root)

    # Deduplicate by proximity rather than by rounding: a kink that is also a
    # root gets found twice, but rounding the values to merge them would throw
    # away the exactness the interpolation just bought.
    found.sort()
    unique: list[float] = []
    for b in found:
        if not unique or b - unique[-1] > STRIKE_EPS:
            unique.append(b)
    return unique


def _grid(legs: tuple[StrategyLeg, ...], points: int = 2001) -> list[float]:
    """A dense spot grid spanning the strikes, for the smooth multi-expiry case."""
    kinks = kink_points(legs) or [1.0]
    hi = max(kinks) * 2.5
    return [hi * i / (points - 1) for i in range(points)] + kinks


def _numeric_breakevens(
    legs: tuple[StrategyLeg, ...], rate: float, div_yield: float
) -> list[float]:
    """Bracket sign changes on a grid, then bisect. Used when a leg survives
    the horizon and the payoff is therefore curved rather than kinked."""
    xs = sorted(set(_grid(legs)))
    found: list[float] = []

    for left, right in pairwise(xs):
        p_left = payoff(legs, left, rate, div_yield)
        p_right = payoff(legs, right, rate, div_yield)
        if p_left == 0.0:
            found.append(left)
        elif p_left * p_right < 0.0:
            lo, hi = left, right
            for _ in range(60):
                mid = 0.5 * (lo + hi)
                if payoff(legs, lo, rate, div_yield) * payoff(legs, mid, rate, div_yield) <= 0.0:
                    hi = mid
                else:
                    lo = mid
            found.append(0.5 * (lo + hi))

    found.sort()
    unique: list[float] = []
    for b in found:
        if not unique or b - unique[-1] > 1e-6:
            unique.append(b)
    return unique


def extremes(
    legs: tuple[StrategyLeg, ...], rate: float = 0.0, div_yield: float = 0.0
) -> tuple[Extreme, Extreme]:
    """Best and worst case at the nearest expiry.

    A piecewise-linear function attains its extremes at a kink or at infinity,
    so for a single-expiry structure evaluating the kinks plus zero is
    exhaustive. When a leg survives the horizon the curve is smooth and the
    turning point can sit between strikes — a calendar's peak does exactly
    that — so the search falls back to a dense grid.

    Spot cannot go below zero, which is why only the upper wing runs away.
    """
    candidate_spots = kink_points(legs) if is_single_expiry(legs) else _grid(legs)
    return _extremes_over(legs, candidate_spots, rate, div_yield)


def _extremes_over(
    legs: tuple[StrategyLeg, ...],
    candidate_spots: list[float],
    rate: float,
    div_yield: float,
) -> tuple[Extreme, Extreme]:
    candidates = [0.0, *candidate_spots]
    values = [(payoff(legs, s, rate, div_yield), s) for s in candidates]

    slope_up, _ = asymptotic_slopes(legs)
    best_value, best_spot = max(values)
    worst_value, worst_spot = min(values)

    if slope_up > STRIKE_EPS:
        max_profit = Extreme(value=math.inf, spot=None, unbounded=True)
    else:
        max_profit = Extreme(value=best_value, spot=best_spot, unbounded=False)

    if slope_up < -STRIKE_EPS:
        max_loss = Extreme(value=-math.inf, spot=None, unbounded=True)
    else:
        max_loss = Extreme(value=worst_value, spot=worst_spot, unbounded=False)

    return max_profit, max_loss


def payoff_curve(
    legs: tuple[StrategyLeg, ...],
    spot: float,
    rate: float,
    div_yield: float,
    lo: float,
    hi: float,
    steps: int = 121,
) -> list[PayoffPoint]:
    """Payoff at expiry alongside mark-to-market value today.

    Every kink is forced into the grid: sampling a kinked function on an evenly
    spaced grid rounds off the corners, which is exactly where a strategy's
    interesting behaviour lives.
    """
    grid = {lo + (hi - lo) * i / (steps - 1) for i in range(steps)}
    grid.update(k for k in kink_points(legs) if lo <= k <= hi)

    cost = net_cost(legs)
    points: list[PayoffPoint] = []
    for s in sorted(grid):
        mark = 0.0
        for leg in legs:
            if leg.kind is LegKind.UNDERLYING:
                mark += leg.quantity * s
                continue
            opt = leg.option_type
            assert opt is not None and leg.strike is not None  # noqa: S101
            assert leg.tau is not None and leg.vol is not None  # noqa: S101
            mark += leg.quantity * price(s, leg.strike, rate, div_yield, leg.vol, leg.tau, opt)
        points.append(
            PayoffPoint(spot=s, payoff=payoff(legs, s, rate, div_yield), value=mark - cost)
        )

    _ = spot  # reserved: the caller marks the current spot on the chart
    return points


def analyse(
    legs: tuple[StrategyLeg, ...],
    spot: float,
    rate: float,
    div_yield: float,
    span: float = 0.5,
    steps: int = 121,
) -> StrategyAnalysis:
    """Full analysis of a position — what the Strategy tab renders."""
    if not legs:
        raise ValueError("a strategy needs at least one leg")

    slope_up, slope_down = asymptotic_slopes(legs)
    max_profit, max_loss = extremes(legs, rate, div_yield)

    anchors = [spot, *kink_points(legs)]
    lo = max(0.0, min(anchors) * (1.0 - span))
    hi = max(anchors) * (1.0 + span)

    return StrategyAnalysis(
        net_cost=net_cost(legs),
        net_greeks=net_greeks(legs, spot, rate, div_yield),
        breakevens=tuple(breakevens(legs, rate, div_yield)),
        max_profit=max_profit,
        max_loss=max_loss,
        payoff_slope_up=slope_up,
        payoff_slope_down=slope_down,
        kinks=tuple(kink_points(legs)),
        curve=tuple(payoff_curve(legs, spot, rate, div_yield, lo, hi, steps)),
        horizon_tau=horizon_tau(legs),
        exact=is_single_expiry(legs),
    )
