"""Static arbitrage scanner tests.

The scanner's value depends entirely on its false-positive rate: a screen that
cries wolf on a healthy chain is worse than no screen. So the central test is
negative — a chain built from Black-Scholes on a smile satisfies every static
bound by construction, and the scanner must return *nothing* on it, across a
wide sweep of rates, dividends, skews and spreads.

The positive tests then plant violations by hand and assert the scanner reports
both the right kind and the exact locked-in profit.

Every finding is also checked against a portfolio invariant: the reported
profit must equal the sum of the legs' cash flows. That catches a whole class
of bug where the arithmetic is right but the published trade doesn't finance
it — a violation you could not actually put on.
"""

from __future__ import annotations

import math

import pytest

from pricecalc.core import arbitrage as arb
from pricecalc.core.arbitrage import ViolationKind
from pricecalc.core.black_scholes import OptionType
from pricecalc.core.chain import Chain, Quote
from pricecalc.core.marketdata.simulated import SmileParams, generate_chain


def cash_flow_sum(violation) -> float:
    return sum(leg.cash_flow for leg in violation.legs)


def quote(tau, strike, opt, bid, ask) -> Quote:
    return Quote(tau=tau, strike=strike, option_type=opt, bid=bid, ask=ask)


class TestCleanChainIsSilent:
    """A chain generated from a consistent smile must yield no findings."""

    @pytest.mark.parametrize("seed", [1, 7, 42, 1234, 99999])
    def test_default_parameters(self, seed):
        sim = generate_chain(seed=seed)
        assert arb.scan(sim.chain) == []

    @pytest.mark.parametrize("rate", [0.0, 0.02, 0.08])
    @pytest.mark.parametrize("div_yield", [0.0, 0.03])
    def test_across_carry_regimes(self, rate, div_yield):
        sim = generate_chain(rate=rate, div_yield=div_yield, seed=5)
        assert arb.scan(sim.chain) == []

    @pytest.mark.parametrize("skew", [-0.4, -0.12, 0.0, 0.25])
    @pytest.mark.parametrize("curvature", [0.0, 0.45, 1.2])
    def test_across_smile_shapes(self, skew, curvature):
        """Even a steep, convex smile is arbitrage-free — smiles are not arbitrage."""
        sim = generate_chain(smile=SmileParams(skew=skew, curvature=curvature), seed=11)
        assert arb.scan(sim.chain) == []

    @pytest.mark.parametrize("spread_bps", [1.0, 80.0, 400.0])
    def test_across_spread_widths(self, spread_bps):
        sim = generate_chain(spread_bps=spread_bps, seed=3)
        assert arb.scan(sim.chain) == []

    def test_dense_strike_ladder(self):
        """More strikes means far more butterfly triples — all must stay clean."""
        sim = generate_chain(strike_count=21, strike_span=0.5, seed=8)
        assert arb.scan(sim.chain) == []


class TestPlantedViolationsAreFound:
    """Ground truth: every planted bound must come back from the scanner."""

    @pytest.mark.parametrize("seed", [2, 13, 77, 404, 8888])
    def test_each_planted_bound_is_recovered(self, seed):
        sim = generate_chain(n_violations=3, seed=seed)
        assert sim.planted
        found = arb.scan(sim.chain)

        for plant in sim.planted:
            match = [
                v
                for v in found
                if v.kind.value == plant.kind
                and plant.strike in v.strikes
                and v.tau == pytest.approx(plant.tau)
            ]
            assert match, f"planted {plant.kind} at {plant.strike:g}/{plant.tau:.4g}y was missed"

    @pytest.mark.parametrize("seed", [2, 13, 77])
    def test_planted_violations_clear_the_intended_margin(self, seed):
        """Plants are solved to breach by ~0.4% of spot, so they survive filtering."""
        sim = generate_chain(n_violations=3, seed=seed)
        assert arb.scan(sim.chain, min_edge=0.2)

    def test_more_plants_yield_more_findings(self):
        few = arb.scan(generate_chain(n_violations=1, seed=21).chain)
        many = arb.scan(generate_chain(n_violations=6, seed=21).chain)
        assert len(many) > len(few)


class TestPutCallParity:
    """C - P = S·e^(-q·tau) - K·e^(-r·tau)."""

    def _chain(self, call_bid, call_ask, put_bid, put_ask, rate=0.05, div_yield=0.0) -> Chain:
        return Chain(
            spot=100.0,
            rate=rate,
            div_yield=div_yield,
            quotes=(
                quote(1.0, 100.0, OptionType.CALL, call_bid, call_ask),
                quote(1.0, 100.0, OptionType.PUT, put_bid, put_ask),
            ),
        )

    def test_fair_parity_is_silent(self):
        # C - P must equal 100 - 100·e^(-0.05) = 4.8771.
        chain = self._chain(10.30, 10.40, 5.45, 5.55)
        assert arb.check_put_call_parity(chain) == []

    def test_cheap_synthetic_is_a_reversal(self):
        """Long call, short put, short stock is a *reversal* by convention.

        The labels were originally the wrong way round: a conversion is long
        stock plus a long put against a short call, and this is its mirror.
        The cash flows were always right; only the name on the screen was not.
        """
        chain = self._chain(6.00, 6.10, 5.45, 5.55)
        found = arb.check_put_call_parity(chain)
        assert len(found) == 1
        v = found[0]
        assert v.kind is ViolationKind.PUT_CALL_PARITY
        assert "Reversal" in v.summary
        expected = 5.45 + 100.0 - 6.10 - 100.0 * math.exp(-0.05)
        assert v.profit == pytest.approx(expected, abs=1e-12)

    def test_rich_synthetic_is_a_conversion(self):
        """Long stock, long put, short call — the textbook conversion."""
        chain = self._chain(14.00, 14.10, 5.45, 5.55)
        found = arb.check_put_call_parity(chain)
        assert len(found) == 1
        assert "Conversion" in found[0].summary
        expected = 14.00 + 100.0 * math.exp(-0.05) - 5.55 - 100.0
        assert found[0].profit == pytest.approx(expected, abs=1e-12)

    def test_conversion_and_reversal_are_mutually_exclusive(self):
        """Non-negative spreads make it impossible for both sides to be free money."""
        for call_mid in [4.0, 6.0, 8.0, 10.0, 12.0, 14.0]:
            chain = self._chain(call_mid - 0.05, call_mid + 0.05, 5.45, 5.55)
            kinds = [v.summary.split()[0] for v in arb.check_put_call_parity(chain)]
            assert not ("Conversion" in kinds and "Reversal" in kinds)

    def test_dividends_shift_the_parity_line(self):
        """A chain that is fair at q=0 becomes an arbitrage at q=4%, and vice versa."""
        fair_no_div = self._chain(10.30, 10.40, 5.45, 5.55, div_yield=0.0)
        assert arb.check_put_call_parity(fair_no_div) == []
        with_div = self._chain(10.30, 10.40, 5.45, 5.55, div_yield=0.04)
        assert arb.check_put_call_parity(with_div) != []


class TestVerticals:
    def _calls(self, lo_bid, lo_ask, hi_bid, hi_ask, rate=0.0) -> Chain:
        return Chain(
            spot=100.0,
            rate=rate,
            div_yield=0.0,
            quotes=(
                quote(1.0, 95.0, OptionType.CALL, lo_bid, lo_ask),
                quote(1.0, 105.0, OptionType.CALL, hi_bid, hi_ask),
            ),
        )

    def test_ordered_calls_are_silent(self):
        assert arb.check_verticals(self._calls(12.0, 12.2, 6.0, 6.2)) == []

    def test_higher_strike_bidding_above_lower_offer(self):
        found = arb.check_verticals(self._calls(6.0, 6.2, 8.0, 8.2))
        monotonic = [v for v in found if v.kind is ViolationKind.VERTICAL_MONOTONICITY]
        assert len(monotonic) == 1
        assert monotonic[0].profit == pytest.approx(8.0 - 6.2, abs=1e-12)

    def test_spread_priced_above_its_cap(self):
        # Strike gap is 10 and r=0, so the spread cannot be worth more than 10.
        found = arb.check_verticals(self._calls(30.0, 30.2, 5.0, 5.2))
        capped = [v for v in found if v.kind is ViolationKind.VERTICAL_CAP]
        assert len(capped) == 1
        assert capped[0].profit == pytest.approx(30.0 - 5.2 - 10.0, abs=1e-12)

    def test_cap_accounts_for_discounting(self):
        """At a positive rate the cap is the discounted gap, so it binds sooner."""
        chain = self._calls(30.0, 30.2, 5.0, 5.2, rate=0.10)
        capped = [v for v in arb.check_verticals(chain) if v.kind is ViolationKind.VERTICAL_CAP]
        assert capped[0].profit == pytest.approx(30.0 - 5.2 - 10.0 * math.exp(-0.10), abs=1e-12)

    def test_put_monotonicity_runs_the_other_way(self):
        chain = Chain(
            spot=100.0,
            rate=0.0,
            div_yield=0.0,
            quotes=(
                quote(1.0, 95.0, OptionType.PUT, 8.0, 8.2),
                quote(1.0, 105.0, OptionType.PUT, 6.0, 6.2),
            ),
        )
        found = [
            v for v in arb.check_verticals(chain) if v.kind is ViolationKind.VERTICAL_MONOTONICITY
        ]
        assert len(found) == 1
        assert found[0].profit == pytest.approx(8.0 - 6.2, abs=1e-12)


class TestButterflyConvexity:
    def _chain(self, mid_bid, mid_ask) -> Chain:
        return Chain(
            spot=100.0,
            rate=0.0,
            div_yield=0.0,
            quotes=(
                quote(1.0, 90.0, OptionType.CALL, 14.0, 14.2),
                quote(1.0, 100.0, OptionType.CALL, mid_bid, mid_ask),
                quote(1.0, 110.0, OptionType.CALL, 4.0, 4.2),
            ),
        )

    def test_convex_prices_are_silent(self):
        # Midpoint of the wings is 9.1; a mid strike below that is convex.
        assert arb.check_butterflies(self._chain(8.5, 8.7)) == []

    def test_concave_middle_strike_is_an_arbitrage(self):
        found = arb.check_butterflies(self._chain(11.0, 11.2))
        assert len(found) == 1
        v = found[0]
        assert v.kind is ViolationKind.BUTTERFLY_CONVEXITY
        assert v.profit == pytest.approx(11.0 - 0.5 * 14.2 - 0.5 * 4.2, abs=1e-12)
        assert v.strikes == (90.0, 100.0, 110.0)

    def test_uneven_strikes_use_interpolation_weights(self):
        """K2 sits 1/4 of the way from K1 to K3, so the wings weight 3/4 and 1/4."""
        chain = Chain(
            spot=100.0,
            rate=0.0,
            div_yield=0.0,
            quotes=(
                quote(1.0, 90.0, OptionType.CALL, 14.0, 14.2),
                quote(1.0, 95.0, OptionType.CALL, 13.0, 13.2),
                quote(1.0, 110.0, OptionType.CALL, 4.0, 4.2),
            ),
        )
        found = arb.check_butterflies(chain)
        assert len(found) == 1
        assert found[0].profit == pytest.approx(13.0 - 0.75 * 14.2 - 0.25 * 4.2, abs=1e-12)


class TestCalendars:
    def _chain(self, div_yield: float) -> Chain:
        return Chain(
            spot=100.0,
            rate=0.0,
            div_yield=div_yield,
            quotes=(
                quote(0.25, 100.0, OptionType.CALL, 9.0, 9.2),
                quote(1.00, 100.0, OptionType.CALL, 5.0, 5.2),
            ),
        )

    def test_near_dated_bidding_above_far_dated_offer(self):
        found = arb.check_calendars(self._chain(div_yield=0.0))
        assert len(found) == 1
        assert found[0].kind is ViolationKind.CALENDAR_MONOTONICITY
        assert found[0].profit == pytest.approx(9.0 - 5.2, abs=1e-12)

    def test_skipped_entirely_when_dividends_are_present(self):
        """With a dividend yield the ordering legitimately fails, so we stay quiet."""
        assert arb.check_calendars(self._chain(div_yield=0.03)) == []

    def test_ordered_calendar_is_silent(self):
        chain = Chain(
            spot=100.0,
            rate=0.0,
            div_yield=0.0,
            quotes=(
                quote(0.25, 100.0, OptionType.CALL, 5.0, 5.2),
                quote(1.00, 100.0, OptionType.CALL, 9.0, 9.2),
            ),
        )
        assert arb.check_calendars(chain) == []


class TestAbsoluteBounds:
    def test_call_bid_above_the_stock(self):
        chain = Chain(
            spot=100.0,
            rate=0.0,
            div_yield=0.0,
            quotes=(quote(1.0, 90.0, OptionType.CALL, 105.0, 105.2),),
        )
        found = arb.check_absolute_bounds(chain)
        assert any(v.kind is ViolationKind.ABSOLUTE_BOUND for v in found)
        assert found[0].profit == pytest.approx(105.0 - 100.0, abs=1e-12)

    def test_call_offered_below_forward_intrinsic(self):
        chain = Chain(
            spot=100.0,
            rate=0.0,
            div_yield=0.0,
            quotes=(quote(1.0, 90.0, OptionType.CALL, 8.0, 8.2),),
        )
        found = arb.check_absolute_bounds(chain)
        assert len(found) == 1
        assert found[0].profit == pytest.approx(10.0 - 8.2, abs=1e-12)

    def test_put_bid_above_discounted_strike(self):
        chain = Chain(
            spot=100.0,
            rate=0.05,
            div_yield=0.0,
            quotes=(quote(1.0, 100.0, OptionType.PUT, 99.0, 99.2),),
        )
        found = arb.check_absolute_bounds(chain)
        assert found[0].profit == pytest.approx(99.0 - 100.0 * math.exp(-0.05), abs=1e-12)


class TestPortfolioInvariant:
    """The published trade must actually finance the reported profit."""

    @pytest.mark.parametrize("seed", [2, 13, 77, 404, 8888])
    def test_profit_equals_net_cash_flow_of_the_legs(self, seed):
        sim = generate_chain(n_violations=4, seed=seed)
        found = arb.scan(sim.chain)
        assert found
        for v in found:
            assert cash_flow_sum(v) == pytest.approx(v.profit, abs=1e-9), v.summary

    def test_every_finding_is_strictly_profitable(self):
        sim = generate_chain(n_violations=6, seed=31)
        assert all(v.profit > 0 for v in arb.scan(sim.chain))

    def test_results_are_ranked_richest_first(self):
        sim = generate_chain(n_violations=6, seed=31)
        profits = [v.profit for v in arb.scan(sim.chain)]
        assert profits == sorted(profits, reverse=True)

    def test_min_edge_filters_the_tail(self):
        sim = generate_chain(n_violations=6, seed=31)
        everything = arb.scan(sim.chain, min_edge=1e-9)
        filtered = arb.scan(sim.chain, min_edge=1.0)
        assert len(filtered) < len(everything)
        assert all(v.profit > 1.0 for v in filtered)
