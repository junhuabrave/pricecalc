"""Breakevens and extremes, checked against the payoff function rather than the derivation.

``strategy.py`` claims exactness for a single expiry because the payoff is
piecewise linear. The tests here do not re-derive that argument; they take the
claimed answers and confront them with ``payoff()`` itself. A breakeven that is
really a breakeven prices at zero; a maximum that is really a maximum is not
beaten anywhere on a dense sweep; an extreme reported as unbounded really does
run away when you push spot far enough.

That separation matters because the interesting failures are structural — a
root or a wing the search never looks at — and those are invisible to any test
that only checks the cases the search was written for.
"""

from __future__ import annotations

import math
from itertools import pairwise

import pytest

from pricecalc.core import strategy
from pricecalc.core.strategy import LegKind, StrategyLeg

VOL, TAU = 0.20, 0.25


def call(qty: float, strike: float, entry: float, tau: float = TAU) -> StrategyLeg:
    return StrategyLeg(
        kind=LegKind.CALL, quantity=qty, entry_price=entry, strike=strike, tau=tau, vol=VOL
    )


def put(qty: float, strike: float, entry: float, tau: float = TAU) -> StrategyLeg:
    return StrategyLeg(
        kind=LegKind.PUT, quantity=qty, entry_price=entry, strike=strike, tau=tau, vol=VOL
    )


def stock(qty: float, entry: float) -> StrategyLeg:
    return StrategyLeg(kind=LegKind.UNDERLYING, quantity=qty, entry_price=entry)


STRUCTURES = {
    "long-call": (call(1.0, 100.0, 4.0),),
    "short-call": (call(-1.0, 100.0, 4.0),),
    "long-put": (put(1.0, 100.0, 4.0),),
    "straddle": (call(1.0, 100.0, 4.0), put(1.0, 100.0, 4.0)),
    "short-strangle": (put(-1.0, 90.0, 2.0), call(-1.0, 110.0, 2.0)),
    "bull-call-spread": (call(1.0, 100.0, 6.0), call(-1.0, 110.0, 2.0)),
    "butterfly": (call(1.0, 90.0, 12.0), call(-2.0, 100.0, 5.0), call(1.0, 110.0, 1.0)),
    "ratio-spread": (call(1.0, 95.0, 8.0), call(-2.0, 110.0, 2.0)),
    "unevenly-spaced": (call(1.0, 87.5, 14.0), call(-3.0, 103.25, 4.0), call(2.0, 118.75, 1.5)),
    "covered-call": (stock(1.0, 100.0), call(-1.0, 110.0, 3.0)),
    "collar": (stock(1.0, 100.0), put(1.0, 90.0, 2.0), call(-1.0, 110.0, 1.5)),
    "synthetic-short": (call(-1.0, 100.0, 5.0), put(1.0, 100.0, 5.0)),
}


def dense_sweep(legs: tuple[StrategyLeg, ...], hi: float = 400.0, points: int = 4001):
    return [hi * i / (points - 1) for i in range(points)]


class TestBreakevensAreReallyRoots:
    """Every reported breakeven must price to zero, and no root may be missed.

    The first half is soundness, the second completeness. Sweeping the payoff on
    a grid finer than any structure's kinks and looking for sign changes finds
    the roots independently of how ``breakevens()`` looks for them.
    """

    @pytest.mark.parametrize("name", list(STRUCTURES))
    def test_every_reported_breakeven_has_zero_payoff(self, name):
        legs = STRUCTURES[name]
        for spot in strategy.breakevens(legs):
            assert strategy.payoff(legs, spot) == pytest.approx(0.0, abs=1e-9)

    @pytest.mark.parametrize("name", list(STRUCTURES))
    def test_no_sign_change_is_left_unreported(self, name):
        """A sign change on a fine grid is a root; it must appear in the answer."""
        legs = STRUCTURES[name]
        reported = strategy.breakevens(legs)
        grid = dense_sweep(legs)

        for left, right in pairwise(grid):
            if strategy.payoff(legs, left) * strategy.payoff(legs, right) < 0.0:
                assert any(
                    left - 1e-9 <= b <= right + 1e-9 for b in reported
                ), f"{name}: unreported root bracketed by [{left}, {right}]"

    def test_a_long_stock_position_breaks_even_at_its_entry_price(self):
        """Bought at 100, you are flat at 100 — the most elementary breakeven there is."""
        assert strategy.payoff((stock(1.0, 100.0),), 100.0) == pytest.approx(0.0)

    @pytest.mark.parametrize("quantity", [1.0, -1.0, 2.5])
    def test_a_stock_only_position_reports_its_breakeven(self, quantity):
        legs = (stock(quantity, 100.0),)
        assert strategy.breakevens(legs) == pytest.approx([100.0])


class TestExtremesBoundThePayoff:
    """A maximum that something beats is not a maximum.

    ``extremes()`` evaluates only the kinks and reads the wings off the
    asymptotic slope. Sweeping the payoff on a dense grid is a completely
    different procedure, so agreement is evidence the shortcut is sound.
    """

    @pytest.mark.parametrize("name", list(STRUCTURES))
    def test_nothing_on_a_dense_sweep_beats_the_reported_extremes(self, name):
        legs = STRUCTURES[name]
        max_profit, max_loss = strategy.extremes(legs)
        for spot in dense_sweep(legs):
            value = strategy.payoff(legs, spot)
            assert value <= max_profit.value + 1e-9
            assert value >= max_loss.value - 1e-9

    @pytest.mark.parametrize("name", list(STRUCTURES))
    def test_a_bounded_extreme_is_actually_attained(self, name):
        """If it is finite, some terminal spot must reach it — otherwise the
        number is an artefact of where the search happened to look."""
        legs = STRUCTURES[name]
        max_profit, max_loss = strategy.extremes(legs)
        for extreme in (max_profit, max_loss):
            if extreme.unbounded:
                continue
            assert extreme.spot is not None
            assert strategy.payoff(legs, extreme.spot) == pytest.approx(extreme.value, abs=1e-9)

    @pytest.mark.parametrize("name", list(STRUCTURES))
    def test_unboundedness_is_confirmed_by_pushing_spot_out(self, name):
        """Claiming an infinite wing is a claim about the limit, so test the limit.

        Terminal spot is bounded below by zero, so only the upside can run away
        — a structure reported unbounded must keep moving as spot grows, and one
        reported bounded must not.
        """
        legs = STRUCTURES[name]
        max_profit, max_loss = strategy.extremes(legs)
        far, further = 10_000.0, 100_000.0
        drift = strategy.payoff(legs, further) - strategy.payoff(legs, far)

        if max_profit.unbounded:
            assert drift > 1.0
        if max_loss.unbounded:
            assert drift < -1.0
        if not max_profit.unbounded and not max_loss.unbounded:
            assert abs(drift) < 1e-6


class TestMultiExpiryWings:
    """A surviving leg does not settle, so its wing slope is not its payoff slope.

    Past the horizon a long call is *marked*, and as spot runs away that mark
    tends to ``S*exp(-q*dt) - K*exp(-r*dt)``. Its slope is ``exp(-q*dt)``, which
    is strictly below the 1.0 a settled call contributes whenever there is a
    dividend yield. In a calendar the two no longer cancel, and the short near
    leg wins the race.
    """

    CALENDAR = (
        call(-1.0, 100.0, 4.0, tau=0.25),
        call(1.0, 100.0, 7.0, tau=1.0),
    )
    RATE, DIV = 0.03, 0.06

    def test_the_upper_wing_falls_away_without_limit(self):
        """The mark on the back month grows more slowly than the assignment it
        must cover, by exactly the dividends forgone over the remaining life."""
        remaining = 1.0 - 0.25
        expected_slope = math.exp(-self.DIV * remaining) - 1.0
        assert expected_slope < 0.0

        near = strategy.payoff(self.CALENDAR, 5_000.0, self.RATE, self.DIV)
        far = strategy.payoff(self.CALENDAR, 10_000.0, self.RATE, self.DIV)
        assert (far - near) / 5_000.0 == pytest.approx(expected_slope, rel=1e-3)
        assert far < near - 100.0

    def test_without_a_dividend_yield_the_wing_is_genuinely_flat(self):
        """With q = 0 the mark keeps pace one-for-one and the loss really is capped."""
        near = strategy.payoff(self.CALENDAR, 5_000.0, self.RATE, 0.0)
        far = strategy.payoff(self.CALENDAR, 10_000.0, self.RATE, 0.0)
        assert far == pytest.approx(near, abs=1e-6)

    def test_the_loss_is_reported_as_unbounded(self):
        _, max_loss = strategy.extremes(self.CALENDAR, self.RATE, self.DIV)
        assert max_loss.unbounded
        assert max_loss.value == -math.inf

    def test_the_loss_really_does_keep_deepening_with_spot(self):
        """Unboundedness stated without reference to infinity.

        Regression: `extremes` once reported this loss capped at a finite
        number that a spot of 1,000 already beat, because the wing slope summed
        terminal-payoff slopes for a leg that is marked rather than settled.
        The dividend yield makes the far call's mark grow at `e^(-q*dt)` per
        unit of spot, strictly slower than the short near leg it is meant to
        offset, so the position bleeds without limit as spot rises.
        """
        losses = [
            strategy.payoff(self.CALENDAR, s, self.RATE, self.DIV)
            for s in (500.0, 1_000.0, 5_000.0, 20_000.0)
        ]
        assert all(b < a for a, b in pairwise(losses))
        assert losses[-1] < losses[0] - 100.0


class TestAsymptoticSlopeAlgebra:
    """Wing slopes, read off the payoff rather than off the leg quantities."""

    @pytest.mark.parametrize("name", list(STRUCTURES))
    def test_the_slopes_match_the_payoff_far_from_every_strike(self, name):
        legs = STRUCTURES[name]
        up, down = strategy.asymptotic_slopes(legs)

        high, higher = 10_000.0, 20_000.0
        measured_up = (strategy.payoff(legs, higher) - strategy.payoff(legs, high)) / 10_000.0
        assert measured_up == pytest.approx(up, abs=1e-9)

        low, lower = 1e-4, 1e-5
        measured_down = (strategy.payoff(legs, low) - strategy.payoff(legs, lower)) / (low - lower)
        assert measured_down == pytest.approx(down, abs=1e-6)
