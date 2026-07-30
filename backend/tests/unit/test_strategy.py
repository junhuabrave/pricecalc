"""Multi-leg strategy analytics.

Structures are chosen so the answer is known from first principles rather than
from running the code: a bull call spread's maximum profit is the strike gap
less the debit, a butterfly's is the wing width less the debit, and a covered
call cannot make more than the strike it sold. Each test asserts the closed-form
figure, so a regression shows up as a wrong number rather than a changed one.
"""

from __future__ import annotations

import math

import pytest

from pricecalc.core import presets, strategy
from pricecalc.core.presets import Preset
from pricecalc.core.strategy import LegKind, StrategyLeg

SPOT, RATE, DIV, VOL, TAU = 100.0, 0.0, 0.0, 0.20, 0.25


def call(qty: float, strike: float, entry: float, tau: float = TAU) -> StrategyLeg:
    return StrategyLeg(
        kind=LegKind.CALL, quantity=qty, entry_price=entry, strike=strike, tau=tau, vol=VOL
    )


def put(qty: float, strike: float, entry: float, tau: float = TAU) -> StrategyLeg:
    return StrategyLeg(
        kind=LegKind.PUT, quantity=qty, entry_price=entry, strike=strike, tau=tau, vol=VOL
    )


def stock(qty: float, entry: float = SPOT) -> StrategyLeg:
    return StrategyLeg(kind=LegKind.UNDERLYING, quantity=qty, entry_price=entry)


class TestLegValidation:
    def test_option_leg_requires_a_strike(self):
        with pytest.raises(ValueError, match="positive strike"):
            StrategyLeg(kind=LegKind.CALL, quantity=1.0, entry_price=1.0, tau=1.0, vol=0.2)

    def test_option_leg_requires_a_volatility(self):
        with pytest.raises(ValueError, match="positive vol"):
            StrategyLeg(kind=LegKind.CALL, quantity=1.0, entry_price=1.0, strike=100.0, tau=1.0)

    def test_underlying_needs_no_option_fields(self):
        leg = stock(1.0)
        assert leg.terminal_value(137.0) == 137.0
        assert leg.option_type is None


class TestPayoff:
    def test_long_call_is_intrinsic_less_premium(self):
        legs = (call(1.0, 100.0, 4.0),)
        assert strategy.payoff(legs, 90.0) == pytest.approx(-4.0)
        assert strategy.payoff(legs, 100.0) == pytest.approx(-4.0)
        assert strategy.payoff(legs, 110.0) == pytest.approx(6.0)

    def test_short_put_mirrors_the_long(self):
        long_leg = (put(1.0, 100.0, 3.0),)
        short_leg = (put(-1.0, 100.0, 3.0),)
        for spot in (70.0, 100.0, 130.0):
            assert strategy.payoff(long_leg, spot) == pytest.approx(
                -strategy.payoff(short_leg, spot)
            )

    def test_net_cost_signs_debits_and_credits(self):
        assert strategy.net_cost((call(1.0, 100.0, 4.0),)) == pytest.approx(4.0)
        assert strategy.net_cost((call(-1.0, 100.0, 4.0),)) == pytest.approx(-4.0)


class TestAsymptoticSlopes:
    def test_long_call_rises_one_for_one(self):
        assert strategy.asymptotic_slopes((call(1.0, 100.0, 4.0),)) == (1.0, 0.0)

    def test_long_put_falls_one_for_one(self):
        assert strategy.asymptotic_slopes((put(1.0, 100.0, 4.0),)) == (0.0, -1.0)

    def test_a_capped_spread_is_flat_in_both_wings(self):
        legs = (call(1.0, 100.0, 4.0), call(-1.0, 110.0, 1.0))
        assert strategy.asymptotic_slopes(legs) == (0.0, 0.0)

    def test_stock_moves_with_spot_on_both_sides(self):
        assert strategy.asymptotic_slopes((stock(1.0),)) == (1.0, 1.0)


class TestBreakevens:
    def test_long_call_breaks_even_at_strike_plus_premium(self):
        found = strategy.breakevens((call(1.0, 100.0, 4.0),))
        assert found == pytest.approx([104.0])

    def test_long_put_breaks_even_at_strike_less_premium(self):
        found = strategy.breakevens((put(1.0, 100.0, 4.0),))
        assert found == pytest.approx([96.0])

    def test_straddle_has_a_breakeven_on_each_side(self):
        legs = (call(1.0, 100.0, 4.0), put(1.0, 100.0, 4.0))
        assert strategy.breakevens(legs) == pytest.approx([92.0, 108.0])

    def test_bull_call_spread_breaks_even_inside_the_strikes(self):
        legs = (call(1.0, 100.0, 6.0), call(-1.0, 110.0, 2.0))
        assert strategy.breakevens(legs) == pytest.approx([104.0])

    def test_breakevens_are_exact_not_sampled(self):
        """An irrational-looking breakeven must come back to full precision."""
        legs = (call(1.0, 100.0, 1.0 / 3.0),)
        assert strategy.breakevens(legs)[0] == pytest.approx(100.0 + 1.0 / 3.0, abs=1e-12)

    def test_a_tangential_zero_still_counts(self):
        """A free straddle touches zero at the strike without crossing it.

        P&L is |S - K|, which never goes negative but is exactly zero at the
        strike. That is a real breakeven — you make nothing there — so it is
        reported even though the payoff does not change sign.
        """
        legs = (call(1.0, 100.0, 0.0), put(1.0, 100.0, 0.0))
        assert strategy.breakevens(legs) == pytest.approx([100.0])

    def test_a_structure_that_never_reaches_zero_has_no_breakeven(self):
        """A spread taken in for a credit whose payoff is never negative.

        The vertical pays between 0 and 10 and was opened for a 2 credit, so
        P&L lives in [2, 12] and never touches zero. (This is an arbitrage —
        which is the only way to have no breakeven at all.)
        """
        legs = (call(1.0, 100.0, 0.0), call(-1.0, 110.0, 2.0))
        assert strategy.net_cost(legs) < 0
        assert strategy.breakevens(legs) == []


class TestExtremes:
    def test_long_call_profit_is_unbounded_and_loss_is_the_premium(self):
        profit, loss = strategy.extremes((call(1.0, 100.0, 4.0),))
        assert profit.unbounded and profit.value == math.inf and profit.spot is None
        assert not loss.unbounded
        assert loss.value == pytest.approx(-4.0)

    def test_short_call_loss_is_unbounded(self):
        profit, loss = strategy.extremes((call(-1.0, 100.0, 4.0),))
        assert not profit.unbounded
        assert profit.value == pytest.approx(4.0)
        assert loss.unbounded and loss.value == -math.inf

    def test_long_put_is_bounded_on_both_sides(self):
        """Spot cannot go below zero, so even the downside is finite."""
        profit, loss = strategy.extremes((put(1.0, 100.0, 4.0),))
        assert not profit.unbounded
        assert profit.value == pytest.approx(96.0)
        assert profit.spot == pytest.approx(0.0)
        assert loss.value == pytest.approx(-4.0)

    def test_bull_call_spread_is_capped_at_the_strike_gap_less_debit(self):
        legs = (call(1.0, 100.0, 6.0), call(-1.0, 110.0, 2.0))
        profit, loss = strategy.extremes(legs)
        assert profit.value == pytest.approx(10.0 - 4.0)
        assert loss.value == pytest.approx(-4.0)
        assert not profit.unbounded and not loss.unbounded

    def test_butterfly_peaks_at_the_body(self):
        legs = (call(1.0, 90.0, 12.0), call(-2.0, 100.0, 5.0), call(1.0, 110.0, 1.0))
        profit, loss = strategy.extremes(legs)
        debit = 12.0 - 10.0 + 1.0
        assert profit.value == pytest.approx(10.0 - debit)
        assert profit.spot == pytest.approx(100.0)
        assert loss.value == pytest.approx(-debit)

    def test_covered_call_caps_upside_at_the_short_strike(self):
        legs = (stock(1.0, entry=100.0), call(-1.0, 110.0, 3.0))
        profit, loss = strategy.extremes(legs)
        assert not profit.unbounded
        assert profit.value == pytest.approx(13.0)
        assert loss.value == pytest.approx(-97.0)  # stock to zero, keep the premium


class TestNetGreeks:
    def test_legs_aggregate(self):
        legs = (call(1.0, 100.0, 4.0), call(-1.0, 110.0, 1.0))
        net = strategy.net_greeks(legs, SPOT, RATE, DIV)
        from pricecalc.core.black_scholes import OptionType, greeks

        a = greeks(SPOT, 100.0, RATE, DIV, VOL, TAU, OptionType.CALL)
        b = greeks(SPOT, 110.0, RATE, DIV, VOL, TAU, OptionType.CALL)
        assert net.delta == pytest.approx(a.delta - b.delta)
        assert net.vega == pytest.approx(a.vega - b.vega)

    def test_underlying_contributes_pure_delta(self):
        net = strategy.net_greeks((stock(3.0),), SPOT, RATE, DIV)
        assert net.delta == pytest.approx(3.0)
        assert net.gamma == 0.0 and net.vega == 0.0 and net.theta == 0.0

    def test_a_struck_at_the_money_straddle_is_not_delta_neutral(self):
        """A common misconception: strike = spot does not mean zero delta.

        Straddle delta is 2N(d1) - 1, and at K = S with r = q = 0 the drift term
        leaves d1 = sigma*sqrt(tau)/2, which is strictly positive. The straddle
        is quietly long.
        """
        legs = (call(1.0, SPOT, 4.0), put(1.0, SPOT, 4.0))
        net = strategy.net_greeks(legs, SPOT, 0.0, 0.0)
        d1 = VOL * math.sqrt(TAU) / 2.0
        from pricecalc.core.black_scholes import norm_cdf

        assert net.delta == pytest.approx(2.0 * norm_cdf(d1) - 1.0, abs=1e-12)
        assert net.delta > 0.0

    def test_the_delta_neutral_straddle_strike_sits_above_the_forward(self):
        """d1 = 0 requires K = S*exp((r - q + sigma^2/2)*tau), not K = forward."""
        neutral_strike = SPOT * math.exp((RATE - DIV + 0.5 * VOL**2) * TAU)
        forward = SPOT * math.exp((RATE - DIV) * TAU)
        assert neutral_strike > forward

        legs = (call(1.0, neutral_strike, 4.0), put(1.0, neutral_strike, 4.0))
        net = strategy.net_greeks(legs, SPOT, RATE, DIV)
        assert net.delta == pytest.approx(0.0, abs=1e-12)
        assert net.gamma > 0 and net.vega > 0

    def test_a_delta_hedged_call_has_no_delta(self):
        from pricecalc.core.black_scholes import OptionType, greeks

        d = greeks(SPOT, 100.0, RATE, DIV, VOL, TAU, OptionType.CALL).delta
        legs = (call(1.0, 100.0, 4.0), stock(-d))
        assert strategy.net_greeks(legs, SPOT, RATE, DIV).delta == pytest.approx(0.0, abs=1e-12)


class TestPayoffCurve:
    def test_every_kink_appears_in_the_grid(self):
        """An even grid rounds the corners off exactly where they matter."""
        legs = (call(1.0, 97.3, 4.0), call(-1.0, 113.7, 1.0))
        curve = strategy.payoff_curve(legs, SPOT, RATE, DIV, 50.0, 150.0, steps=11)
        spots = [p.spot for p in curve]
        assert any(s == pytest.approx(97.3) for s in spots)
        assert any(s == pytest.approx(113.7) for s in spots)

    def test_value_exceeds_payoff_for_long_premium(self):
        """Before expiry a long option still carries time value."""
        legs = (call(1.0, 100.0, 4.0),)
        for point in strategy.payoff_curve(legs, SPOT, RATE, DIV, 80.0, 120.0, steps=21):
            assert point.value >= point.payoff - 1e-9


class TestAnalyse:
    def test_rejects_an_empty_strategy(self):
        with pytest.raises(ValueError, match="at least one leg"):
            strategy.analyse((), SPOT, RATE, DIV)

    def test_returns_a_complete_analysis(self):
        legs = presets.build(Preset.BULL_CALL_SPREAD, spot=SPOT, rate=RATE, vol=VOL, tau=TAU)
        result = strategy.analyse(legs, SPOT, RATE, DIV)
        assert result.net_cost > 0  # a debit spread
        assert len(result.breakevens) == 1
        assert not result.max_profit.unbounded
        assert not result.max_loss.unbounded
        assert result.curve


class TestPresets:
    @pytest.mark.parametrize("preset", list(Preset))
    def test_every_preset_builds_and_analyses(self, preset):
        legs = presets.build(preset, spot=SPOT, rate=RATE, div_yield=DIV, vol=VOL, tau=TAU)
        assert legs
        result = strategy.analyse(legs, SPOT, RATE, DIV)
        assert math.isfinite(result.net_cost)

    @pytest.mark.parametrize(
        ("preset", "unbounded_profit", "unbounded_loss"),
        [
            (Preset.LONG_CALL, True, False),
            (Preset.LONG_PUT, False, False),
            (Preset.BULL_CALL_SPREAD, False, False),
            (Preset.STRADDLE, True, False),
            (Preset.BUTTERFLY, False, False),
            (Preset.IRON_CONDOR, False, False),
            (Preset.COVERED_CALL, False, False),
            (Preset.COLLAR, False, False),
        ],
    )
    def test_boundedness_matches_the_structure(self, preset, unbounded_profit, unbounded_loss):
        legs = presets.build(preset, spot=SPOT, rate=RATE, div_yield=DIV, vol=VOL, tau=TAU)
        profit, loss = strategy.extremes(legs)
        assert profit.unbounded is unbounded_profit
        assert loss.unbounded is unbounded_loss

    def test_debit_structures_cost_money_and_credit_ones_pay(self):
        debit = presets.build(Preset.BULL_CALL_SPREAD, spot=SPOT, rate=RATE, vol=VOL, tau=TAU)
        credit = presets.build(Preset.IRON_CONDOR, spot=SPOT, rate=RATE, vol=VOL, tau=TAU)
        assert strategy.net_cost(debit) > 0
        assert strategy.net_cost(credit) < 0

    def test_straddle_is_long_volatility(self):
        legs = presets.build(Preset.STRADDLE, spot=SPOT, rate=RATE, vol=VOL, tau=TAU)
        net = strategy.net_greeks(legs, SPOT, RATE, DIV)
        assert net.vega > 0
        assert net.gamma > 0
        assert net.theta < 0  # you pay for that convexity every day

    def test_butterfly_is_short_volatility_at_the_body(self):
        legs = presets.build(Preset.BUTTERFLY, spot=SPOT, rate=RATE, vol=VOL, tau=TAU)
        net = strategy.net_greeks(legs, SPOT, RATE, DIV)
        assert net.gamma < 0
        assert net.theta > 0  # short gamma collects decay

    def test_calendar_spans_two_expiries(self):
        legs = presets.build(Preset.CALENDAR, spot=SPOT, rate=RATE, vol=VOL, tau=TAU)
        assert len({leg.tau for leg in legs}) == 2
        assert strategy.net_greeks(legs, SPOT, RATE, DIV).vega > 0  # long the back month

    def test_presets_open_at_fair_value(self):
        """Every leg is priced at theoretical value, so nothing starts with edge."""
        legs = presets.build(Preset.IRON_CONDOR, spot=SPOT, rate=RATE, vol=VOL, tau=TAU)
        from pricecalc.core.black_scholes import price

        for leg in legs:
            if leg.option_type is None:
                continue
            assert leg.strike is not None and leg.tau is not None and leg.vol is not None
            fair = price(SPOT, leg.strike, RATE, DIV, leg.vol, leg.tau, leg.option_type)
            assert leg.entry_price == pytest.approx(fair)


class TestMultiExpiryHorizon:
    """A calendar spread only makes sense if the back month is still alive.

    Settling every leg at once makes the two calls cancel exactly, leaving a
    flat line at minus the debit. These tests pin the correct behaviour: the
    near leg settles to intrinsic while the far leg is marked over its
    remaining life, producing the characteristic tent.
    """

    def _calendar(self):
        return presets.build(Preset.CALENDAR, spot=SPOT, rate=RATE, div_yield=DIV, vol=VOL, tau=TAU)

    def test_horizon_is_the_nearest_expiry(self):
        legs = self._calendar()
        assert strategy.horizon_tau(legs) == pytest.approx(TAU)
        assert not strategy.is_single_expiry(legs)

    def test_single_expiry_structures_are_flagged_exact(self):
        legs = presets.build(Preset.BUTTERFLY, spot=SPOT, rate=RATE, vol=VOL, tau=TAU)
        assert strategy.is_single_expiry(legs)
        assert strategy.analyse(legs, SPOT, RATE, DIV).exact is True

    def test_calendar_is_flagged_inexact(self):
        assert strategy.analyse(self._calendar(), SPOT, RATE, DIV).exact is False

    def test_calendar_payoff_is_not_flat(self):
        """The regression this class exists for."""
        legs = self._calendar()
        sampled = [strategy.payoff(legs, s, RATE, DIV) for s in (60.0, 100.0, 140.0)]
        assert max(sampled) - min(sampled) > 1.0

    def test_calendar_peaks_near_the_strike(self):
        """Short gamma at the body: the near leg decays fastest at the strike."""
        legs = self._calendar()
        profit, _ = strategy.extremes(legs, RATE, DIV)
        assert not profit.unbounded
        assert profit.spot is not None
        assert profit.spot == pytest.approx(SPOT, rel=0.12)
        assert profit.value > 0.0

    def test_calendar_has_two_breakevens(self):
        """A tent crosses zero on the way up and again on the way down."""
        found = strategy.breakevens(self._calendar(), RATE, DIV)
        assert len(found) == 2
        lo, hi = found
        assert lo < SPOT < hi

    def test_a_surviving_leg_is_worth_more_than_its_intrinsic(self):
        """At the horizon the far leg is marked, not settled.

        At spot = strike both legs are exactly at the money, so every intrinsic
        is zero. Settling both would leave a gross value of zero; because the
        back month still has half a year to run, the true gross is its
        remaining time value.
        """
        legs = self._calendar()
        gross_at_strike = strategy.payoff(legs, SPOT, RATE, DIV) + strategy.net_cost(legs)
        assert gross_at_strike > 0.0

        far = max(legs, key=lambda leg: leg.tau or 0.0)
        from pricecalc.core.black_scholes import OptionType, price

        assert far.strike is not None and far.tau is not None and far.vol is not None
        remaining = far.tau - strategy.horizon_tau(legs)
        expected = price(SPOT, far.strike, RATE, DIV, far.vol, remaining, OptionType.CALL)
        assert gross_at_strike == pytest.approx(expected)
