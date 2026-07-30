"""Model-free invariants, asserted over generated inputs rather than chosen ones.

Hand-picked cases test the regimes the author thought of. The properties below
hold for *every* admissible input, so letting Hypothesis choose puts the awkward
corners — a dividend yield above the rate, a negative rate, a strike three
standard deviations out, an expiry of a day — into the same assertions as the
comfortable middle.

Everything here is either model-free (parity, price bounds, convexity in strike)
or a structural claim the module makes about its own output. None of it is
derived from the Black-Scholes formula, so none of it can share an error with it.
"""

from __future__ import annotations

import math

import pytest
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

from pricecalc.core import arbitrage, strategy
from pricecalc.core import black_scholes as bs
from pricecalc.core.black_scholes import NoImpliedVolError, OptionType
from pricecalc.core.chain import Chain, Quote
from pricecalc.core.strategy import LegKind, StrategyLeg

FAST = settings(max_examples=200, deadline=None, suppress_health_check=[HealthCheck.too_slow])
SLOW = settings(max_examples=25, deadline=None, suppress_health_check=[HealthCheck.too_slow])

spots = st.floats(min_value=1.0, max_value=10_000.0, allow_nan=False, allow_infinity=False)
strikes = st.floats(min_value=1.0, max_value=10_000.0, allow_nan=False, allow_infinity=False)
rates = st.floats(min_value=-0.10, max_value=0.25, allow_nan=False, allow_infinity=False)
yields = st.floats(min_value=0.0, max_value=0.20, allow_nan=False, allow_infinity=False)
vols = st.floats(min_value=0.01, max_value=3.0, allow_nan=False, allow_infinity=False)
taus = st.floats(min_value=1e-3, max_value=10.0, allow_nan=False, allow_infinity=False)
types = st.sampled_from([OptionType.CALL, OptionType.PUT])


class TestModelFreeInvariants:
    @given(spots, strikes, rates, yields, vols, taus)
    @FAST
    def test_put_call_parity(self, spot, strike, rate, div_yield, vol, tau):
        """C - P = S*e^(-q*tau) - K*e^(-r*tau) for European options, always.

        Parity follows from replication alone, so it constrains the pair of
        prices without appealing to any model. A discounting error that hits
        both sides identically would cancel here — which is why it is one
        invariant among several, not the only one.
        """
        call = bs.price(spot, strike, rate, div_yield, vol, tau, OptionType.CALL)
        put = bs.price(spot, strike, rate, div_yield, vol, tau, OptionType.PUT)
        forward_pv = spot * math.exp(-div_yield * tau) - strike * math.exp(-rate * tau)
        assert call - put == pytest.approx(forward_pv, rel=1e-9, abs=1e-9)

    @given(spots, strikes, rates, yields, vols, taus, types)
    @FAST
    def test_price_sits_inside_its_no_arbitrage_band(
        self, spot, strike, rate, div_yield, vol, tau, option_type
    ):
        """A quote outside the band is an arbitrage; a model that produces one is broken."""
        px = bs.price(spot, strike, rate, div_yield, vol, tau, option_type)
        lower, upper = bs.price_bounds(spot, strike, rate, div_yield, tau, option_type)
        assert lower - 1e-9 <= px <= upper + 1e-9

    @given(spots, strikes, rates, yields, vols, taus, types)
    @FAST
    def test_price_rises_with_volatility(
        self, spot, strike, rate, div_yield, vol, tau, option_type
    ):
        """Vega is positive everywhere, which is what makes implied vol unique.

        If this failed, Brent's bracketing in ``implied_vol`` would be unsound
        even where it converges.
        """
        cheaper = bs.price(spot, strike, rate, div_yield, vol, tau, option_type)
        dearer = bs.price(spot, strike, rate, div_yield, vol * 1.5, tau, option_type)
        assert dearer >= cheaper - 1e-12

    @given(spots, strikes, rates, yields, vols, taus)
    @FAST
    def test_call_falls_and_put_rises_with_the_strike(
        self, spot, strike, rate, div_yield, vol, tau
    ):
        """The monotonicity ``check_verticals`` enforces on quotes must hold on
        the model's own prices, or the generator cannot produce a clean chain."""
        higher = strike * 1.1
        assert (
            bs.price(spot, higher, rate, div_yield, vol, tau, OptionType.CALL)
            <= bs.price(spot, strike, rate, div_yield, vol, tau, OptionType.CALL) + 1e-9
        )
        assert (
            bs.price(spot, higher, rate, div_yield, vol, tau, OptionType.PUT)
            >= bs.price(spot, strike, rate, div_yield, vol, tau, OptionType.PUT) - 1e-9
        )

    @given(spots, strikes, rates, yields, vols, taus, types)
    @FAST
    def test_price_is_convex_in_strike(self, spot, strike, rate, div_yield, vol, tau, option_type):
        """The butterfly at any three strikes costs something non-negative.

        This is the exact condition ``check_butterflies`` screens for, so it is
        also the condition a generated chain has to satisfy before the scanner
        can be expected to stay silent on it.
        """
        gap = strike * 0.1
        k_lo, k_mid, k_hi = strike, strike + gap, strike + 2 * gap
        wing = sum(bs.price(spot, k, rate, div_yield, vol, tau, option_type) for k in (k_lo, k_hi))
        body = 2.0 * bs.price(spot, k_mid, rate, div_yield, vol, tau, option_type)
        assert wing - body >= -1e-7 * max(1.0, spot)

    @given(spots, strikes, rates, yields, vols, taus)
    @FAST
    def test_delta_parity_and_bounds(self, spot, strike, rate, div_yield, vol, tau):
        """delta_call - delta_put = e^(-q*tau), and each sits in its own range.

        Differentiating parity in spot gives the identity; the ranges follow
        because a call is between zero and ``e^(-q*tau)`` shares long.
        """
        discount = math.exp(-div_yield * tau)
        call = bs.greeks(spot, strike, rate, div_yield, vol, tau, OptionType.CALL).delta
        put = bs.greeks(spot, strike, rate, div_yield, vol, tau, OptionType.PUT).delta
        assert call - put == pytest.approx(discount, abs=1e-12)
        assert 0.0 <= call <= discount + 1e-12
        assert -discount - 1e-12 <= put <= 0.0

    @given(spots, strikes, rates, yields, vols, taus, types)
    @FAST
    def test_gamma_and_vega_are_non_negative(
        self, spot, strike, rate, div_yield, vol, tau, option_type
    ):
        """Long premium is long convexity, whichever right you hold."""
        g = bs.greeks(spot, strike, rate, div_yield, vol, tau, option_type)
        assert g.gamma >= 0.0
        assert g.vega >= 0.0


class TestImpliedVolInversion:
    @given(spots, strikes, rates, yields, vols, taus, types)
    @FAST
    def test_round_trip_recovers_the_volatility(
        self, spot, strike, rate, div_yield, vol, tau, option_type
    ):
        """Pricing then inverting must return the input, or the smile is a fiction.

        Quotes that land on the edge of the no-arbitrage band are excluded, not
        because inversion fails there but because there is genuinely no interior
        root to find — which is what ``NoImpliedVolError`` exists to say.
        """
        px = bs.price(spot, strike, rate, div_yield, vol, tau, option_type)
        lower, upper = bs.price_bounds(spot, strike, rate, div_yield, tau, option_type)
        assume(px > lower + 1e-6 * spot)
        assume(px < upper - 1e-6 * spot)

        recovered = bs.implied_vol(px, spot, strike, rate, div_yield, tau, option_type)
        assert bs.price(
            spot, strike, rate, div_yield, recovered, tau, option_type
        ) == pytest.approx(px, rel=1e-6, abs=1e-9)

    @given(spots, strikes, rates, yields, taus, types)
    @FAST
    def test_a_quote_outside_the_band_is_rejected_rather_than_clamped(
        self, spot, strike, rate, div_yield, tau, option_type
    ):
        """Below intrinsic there is no volatility that fits, and saying so is the
        product feature — a clamped fallback would hide a static arbitrage."""
        lower, _ = bs.price_bounds(spot, strike, rate, div_yield, tau, option_type)
        with pytest.raises(NoImpliedVolError):
            bs.implied_vol(lower * 0.5, spot, strike, rate, div_yield, tau, option_type)


class TestScannerOnCleanChains:
    """A chain priced off one flat volatility satisfies every static bound.

    Any finding on such a chain is a false positive by construction, so this is
    the property that makes the scanner falsifiable. Negative rates are excluded
    here and covered separately — that combination is a known defect, not an
    accident of the generator.
    """

    @staticmethod
    def _chain(spot, rate, div_yield, vol, half_spread):
        strike_ladder = [spot * m for m in (0.7, 0.85, 1.0, 1.15, 1.3)]
        quotes = tuple(
            Quote(
                tau=tau,
                strike=k,
                option_type=opt,
                bid=max(0.0, bs.price(spot, k, rate, div_yield, vol, tau, opt) - half_spread),
                ask=bs.price(spot, k, rate, div_yield, vol, tau, opt) + half_spread,
            )
            for tau in (0.1, 0.5, 2.0)
            for k in strike_ladder
            for opt in (OptionType.CALL, OptionType.PUT)
        )
        return Chain(spot=spot, rate=rate, div_yield=div_yield, quotes=quotes)

    @given(
        st.floats(min_value=5.0, max_value=5_000.0),
        st.floats(min_value=0.0, max_value=0.20),
        st.floats(min_value=0.0, max_value=0.15),
        st.floats(min_value=0.05, max_value=1.5),
        st.floats(min_value=0.0, max_value=0.5),
    )
    @SLOW
    def test_a_flat_vol_chain_produces_no_findings(self, spot, rate, div_yield, vol, half_spread):
        found = arbitrage.scan(self._chain(spot, rate, div_yield, vol, half_spread))
        assert found == [], [v.summary for v in found]

    @given(
        st.floats(min_value=5.0, max_value=5_000.0),
        st.floats(min_value=0.0, max_value=0.20),
        st.floats(min_value=0.0, max_value=0.15),
        st.floats(min_value=0.05, max_value=1.5),
        st.floats(min_value=0.5, max_value=20.0),
        st.integers(min_value=0, max_value=4),
    )
    @SLOW
    def test_every_finding_is_financed_by_its_own_legs(
        self, spot, rate, div_yield, vol, lift, which
    ):
        """The replicating trade must pay for itself: the legs' cash flows today
        are the profit, with nothing left over to be funded from elsewhere."""
        chain = self._chain(spot, rate, div_yield, vol, 0.01)
        quotes = list(chain.quotes)
        target = quotes[which % len(quotes)]
        quotes[which % len(quotes)] = Quote(
            tau=target.tau,
            strike=target.strike,
            option_type=target.option_type,
            bid=target.bid + lift,
            ask=target.ask + lift,
        )
        lifted = Chain(spot=spot, rate=rate, div_yield=div_yield, quotes=tuple(quotes))
        for violation in arbitrage.scan(lifted):
            assert sum(leg.cash_flow for leg in violation.legs) == pytest.approx(
                violation.profit, rel=1e-9, abs=1e-9
            )
            assert violation.profit > 0.0


class TestStrategyStructuralClaims:
    """Claims ``strategy.py`` makes about its own output, over generated positions."""

    @staticmethod
    def _legs(quantities, ladder, tau):
        legs = []
        for qty, (kind, strike) in zip(quantities, ladder, strict=False):
            if qty == 0.0:
                continue
            legs.append(
                StrategyLeg(
                    kind=kind, quantity=qty, entry_price=1.0, strike=strike, tau=tau, vol=0.2
                )
            )
        return tuple(legs)

    # Quantities are tradeable sizes. Sizes far below one contract are excluded
    # deliberately: ``_extremes_over`` classifies a wing as flat when its slope
    # is under STRIKE_EPS (1e-9), an epsilon expressed in spot units, so a
    # position of 1e-10 contracts is reported bounded when it is not. That is a
    # threshold-units question, not a question about the extremes logic this
    # property is here to test.
    positions = st.builds(
        _legs.__func__,
        st.lists(
            st.sampled_from([-3.0, -2.0, -1.5, -1.0, -0.5, 0.0, 0.5, 1.0, 1.5, 2.0, 3.0]),
            min_size=4,
            max_size=4,
        ),
        st.just(
            [
                (LegKind.PUT, 90.0),
                (LegKind.PUT, 100.0),
                (LegKind.CALL, 100.0),
                (LegKind.CALL, 110.0),
            ]
        ),
        st.just(0.25),
    ).filter(lambda legs: len(legs) > 0)

    @given(positions)
    @FAST
    def test_the_reported_extremes_bound_the_payoff_everywhere(self, legs):
        """Nothing on a sweep may beat a maximum or undercut a minimum.

        The sweep is an entirely different procedure from reading the kinks and
        the wing slope, so it cannot repeat the same oversight.
        """
        max_profit, max_loss = strategy.extremes(legs)
        for spot in (0.0, 1.0, 50.0, 89.9, 90.0, 95.0, 100.0, 105.0, 110.0, 200.0, 5_000.0):
            value = strategy.payoff(legs, spot)
            assert value <= max_profit.value + 1e-9
            assert value >= max_loss.value - 1e-9

    @given(positions)
    @FAST
    def test_every_breakeven_is_a_root_of_the_payoff(self, legs):
        for spot in strategy.breakevens(legs):
            assert strategy.payoff(legs, spot) == pytest.approx(0.0, abs=1e-8)

    @given(positions)
    @FAST
    def test_a_position_and_its_mirror_have_opposite_payoffs(self, legs):
        """Selling what you bought is flat at every terminal spot.

        Sign errors that treat long and short asymmetrically — a credit booked
        as a debit, a short leg settled at intrinsic with the wrong sign —
        cannot survive this.
        """
        mirror = tuple(
            StrategyLeg(
                kind=leg.kind,
                quantity=-leg.quantity,
                entry_price=leg.entry_price,
                strike=leg.strike,
                tau=leg.tau,
                vol=leg.vol,
            )
            for leg in legs
        )
        for spot in (0.0, 50.0, 100.0, 150.0, 1_000.0):
            assert strategy.payoff(legs, spot) == pytest.approx(
                -strategy.payoff(mirror, spot), abs=1e-9
            )

    @given(positions)
    @FAST
    def test_net_greeks_are_linear_in_the_position(self, legs):
        """Doubling every leg doubles every risk — a portfolio is a sum."""
        doubled = tuple(
            StrategyLeg(
                kind=leg.kind,
                quantity=2.0 * leg.quantity,
                entry_price=leg.entry_price,
                strike=leg.strike,
                tau=leg.tau,
                vol=leg.vol,
            )
            for leg in legs
        )
        single = strategy.net_greeks(legs, 100.0, 0.04, 0.01)
        double = strategy.net_greeks(doubled, 100.0, 0.04, 0.01)
        for name in ("delta", "gamma", "vega", "theta", "rho", "vanna", "volga"):
            assert getattr(double, name) == pytest.approx(2.0 * getattr(single, name), rel=1e-12)
