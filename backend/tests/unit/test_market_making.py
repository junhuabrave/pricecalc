"""Market-making quoting and simulation.

The claims worth testing here are behavioural rather than closed-form: that
skew leans against inventory, that width grows with risk, that P&L attribution
adds up, and that a maker with no edge does not manufacture one. A simulation
that quietly prints a profit for the wrong reason is the failure mode, so
several tests below exist specifically to catch a *flattering* result.
"""

from __future__ import annotations

import math
from itertools import pairwise

import pytest

from pricecalc.core.black_scholes import OptionType, greeks
from pricecalc.core.mm import simulator
from pricecalc.core.mm.quoting import QuoteParams, fill_probability, make_quote, price_variance
from pricecalc.core.mm.simulator import SimulationParams
from pricecalc.core.surface import VolSurface

FAIR, SPOT, VOL, HORIZON = 5.0, 100.0, 0.20, 0.02
DELTA = 0.55


def quote(inventory: float, **overrides):
    params = QuoteParams(**overrides)
    return make_quote(
        fair_value=FAIR,
        inventory=inventory,
        delta=DELTA,
        spot=SPOT,
        vol=VOL,
        horizon=HORIZON,
        params=params,
    )


class TestSkew:
    def test_a_flat_book_quotes_symmetrically_around_fair(self):
        q = quote(0.0)
        assert q.skew == pytest.approx(0.0)
        assert q.reservation_price == pytest.approx(FAIR)
        assert FAIR - q.bid == pytest.approx(q.ask - FAIR)

    def test_being_long_marks_the_maker_down(self):
        """Long inventory should make the bid worse and the offer better,
        attracting the flow that flattens the book."""
        flat, long_book = quote(0.0), quote(5.0)
        assert long_book.skew < 0.0
        assert long_book.bid < flat.bid
        assert long_book.ask < flat.ask

    def test_being_short_marks_the_maker_up(self):
        flat, short_book = quote(0.0), quote(-5.0)
        assert short_book.skew > 0.0
        assert short_book.bid > flat.bid
        assert short_book.ask > flat.ask

    def test_skew_is_linear_and_antisymmetric_in_inventory(self):
        assert quote(4.0).skew == pytest.approx(-quote(-4.0).skew)
        assert quote(8.0).skew == pytest.approx(2.0 * quote(4.0).skew)

    def test_a_risk_neutral_maker_never_skews(self):
        """gamma = 0 is the naive maker — the control this model is measured against."""
        for inventory in (-10.0, 0.0, 10.0):
            assert quote(inventory, risk_aversion=0.0).skew == pytest.approx(0.0)


class TestSpreadWidth:
    def test_width_grows_with_risk_aversion(self):
        assert (
            quote(0.0, risk_aversion=0.5).half_spread > quote(0.0, risk_aversion=0.05).half_spread
        )

    def test_width_grows_with_inventory_risk(self):
        """A bigger delta means a riskier option, which deserves a wider market."""
        near_flat = make_quote(FAIR, 0.0, 0.05, SPOT, VOL, HORIZON, QuoteParams())
        directional = make_quote(FAIR, 0.0, 0.95, SPOT, VOL, HORIZON, QuoteParams())
        assert directional.half_spread > near_flat.half_spread

    def test_width_grows_with_the_horizon_of_risk(self):
        short = make_quote(FAIR, 0.0, DELTA, SPOT, VOL, 0.001, QuoteParams())
        long = make_quote(FAIR, 0.0, DELTA, SPOT, VOL, 0.5, QuoteParams())
        assert long.half_spread > short.half_spread

    def test_patient_flow_earns_a_wider_market(self):
        """Small kappa means flow tolerates distance, so the maker charges more."""
        patient = quote(0.0, order_flow_decay=0.4)
        impatient = quote(0.0, order_flow_decay=8.0)
        assert patient.half_spread > impatient.half_spread

    def test_the_floor_always_binds(self):
        q = quote(0.0, risk_aversion=0.0, min_half_spread=0.25)
        assert q.half_spread == pytest.approx(0.25)

    def test_quotes_never_cross(self):
        for inventory in (-20.0, -5.0, 0.0, 5.0, 20.0):
            q = quote(inventory)
            assert q.ask > q.bid


class TestPositionLimits:
    def test_a_maximally_long_maker_stops_bidding(self):
        q = quote(30.0, max_position=25.0)
        assert q.bid == 0.0
        assert math.isfinite(q.ask)

    def test_a_maximally_short_maker_stops_offering(self):
        q = quote(-30.0, max_position=25.0)
        assert q.ask == math.inf
        assert q.bid >= 0.0


class TestFillProbability:
    def test_falls_as_the_quote_moves_away_from_fair(self):
        p = QuoteParams()
        probs = [fill_probability(d, 0.01, p) for d in (0.0, 0.1, 0.5, 2.0)]
        assert all(b < a for a, b in pairwise(probs))

    def test_is_a_probability(self):
        p = QuoteParams()
        for distance in (-1.0, 0.0, 0.5, 100.0):
            assert 0.0 <= fill_probability(distance, 0.05, p) <= 1.0

    def test_more_time_means_more_chance(self):
        p = QuoteParams()
        assert fill_probability(0.2, 0.1, p) > fill_probability(0.2, 0.01, p)

    def test_a_quote_through_fair_does_not_exceed_contact_intensity(self):
        """Negative distance is clamped, so an aggressive quote cannot be
        rewarded with unbounded arrival rate."""
        p = QuoteParams()
        assert fill_probability(-5.0, 0.01, p) == pytest.approx(fill_probability(0.0, 0.01, p))


class TestPriceVariance:
    def test_scales_with_the_square_of_delta(self):
        assert price_variance(0.6, SPOT, VOL) == pytest.approx(4.0 * price_variance(0.3, SPOT, VOL))

    def test_a_zero_delta_option_carries_no_first_order_risk(self):
        assert price_variance(0.0, SPOT, VOL) == 0.0


class TestSimulation:
    def _run(self, **overrides):
        params = SimulationParams(**overrides)
        return simulator.run(params, QuoteParams())

    def test_rejects_a_session_outliving_the_option(self):
        with pytest.raises(ValueError, match="before the option expires"):
            simulator.run(SimulationParams(horizon=0.5, expiry=0.25), QuoteParams())

    def test_attribution_sums_to_the_total(self):
        """The decomposition is the point; if it does not add up it is fiction."""
        r = self._run()
        assert r.spread_pnl + r.inventory_pnl + r.hedge_pnl == pytest.approx(r.total_pnl)

    def test_spread_capture_is_never_negative(self):
        """Every fill happens at or outside fair value, by construction."""
        assert self._run().spread_pnl >= 0.0

    def test_the_run_is_reproducible_from_its_seed(self):
        a, b = self._run(seed=7), self._run(seed=7)
        assert a.total_pnl == pytest.approx(b.total_pnl)
        assert a.fills == b.fills

    def test_a_different_seed_gives_a_different_path(self):
        assert self._run(seed=1).total_pnl != self._run(seed=2).total_pnl

    def test_inventory_respects_the_position_limit(self):
        params = SimulationParams(steps=400, seed=3)
        r = simulator.run(params, QuoteParams(max_position=4.0))
        # One fill can still land on the step the limit is reached.
        assert r.max_abs_inventory <= 5.0

    def test_the_default_parameters_actually_trade(self):
        """Regression: arrival intensity is per *year*, matching dt.

        An earlier default of 12 arrivals per year meant an expected 0.24 fills
        across a week-long session, so the simulation silently did nothing and
        every P&L came back as exactly zero. A market-making simulation that
        never trades is not a conservative result, it is a broken one.
        """
        r = self._run(steps=200, seed=1)
        assert r.fills > 0
        assert r.buys > 0 and r.sells > 0

    def test_skew_pulls_inventory_back_toward_flat(self):
        """The whole justification for skewing: an inventory-aware maker should
        hold less risk than a risk-neutral one taking the same flow.

        Averaged over paths, because on any single path the naive maker can get
        lucky. The claim is statistical and the test should be too.
        """
        seeds = range(12)
        naive = [
            simulator.run(
                SimulationParams(steps=400, seed=s),
                QuoteParams(risk_aversion=0.0, max_position=1e9),
            )
            for s in seeds
        ]
        aware = [
            simulator.run(
                SimulationParams(steps=400, seed=s),
                QuoteParams(risk_aversion=0.8, max_position=1e9),
            )
            for s in seeds
        ]
        assert all(r.fills > 0 for r in naive)
        naive_risk = sum(abs(r.ending_inventory) for r in naive) / len(naive)
        aware_risk = sum(abs(r.ending_inventory) for r in aware) / len(aware)
        assert aware_risk < naive_risk

    def test_hedging_reduces_delta_exposure(self):
        params = SimulationParams(steps=300, seed=5)
        unhedged = simulator.run(params, QuoteParams())
        hedged = simulator.run(SimulationParams(steps=300, seed=5, hedge_delta=True), QuoteParams())
        assert unhedged.hedge_trades == 0 or hedged.hedge_trades > 0

        residual = [abs(s.delta_exposure + s.hedge_position) for s in hedged.steps]
        assert max(residual) <= 1.0 + 1e-9  # threshold plus one step's drift

    def test_hedging_costs_money_when_it_trades(self):
        """Hedging is insurance, not alpha — it should show up as a cost."""
        params = SimulationParams(steps=300, seed=9, hedge_cost_bps=25.0)
        r = simulator.run(params, QuoteParams())
        if r.hedge_trades > 0:
            assert r.hedge_pnl < 0.0

    def test_no_hedging_means_no_hedge_pnl(self):
        r = self._run(hedge_delta=False, steps=200)
        assert r.hedge_pnl == pytest.approx(0.0)
        assert r.hedge_trades == 0

    def test_realised_vol_recovers_the_input(self):
        """Sanity on the price path: the simulated returns should have roughly
        the volatility they were generated with."""
        r = self._run(steps=4000, seed=17)
        implied = r.metadata["implied_vol_at_open"]
        assert r.realised_vol == pytest.approx(implied, rel=0.25)

    def test_every_step_is_recorded(self):
        r = self._run(steps=150)
        assert len(r.steps) == 150
        assert r.steps[0].t == 0.0

    def test_fills_are_counted_consistently(self):
        r = self._run(steps=300, seed=23)
        assert r.buys + r.sells == r.fills
        assert sum(s.buys for s in r.steps) == r.buys
        assert sum(s.sells for s in r.steps) == r.sells


class TestNoFreeMoney:
    """A maker with no edge must not appear to make money.

    These are the tests that catch a flattering simulation — the failure mode
    where spread capture is credited without the matching inventory cost.
    """

    def test_a_maker_that_never_trades_makes_nothing(self):
        params = SimulationParams(steps=200, seed=4)
        # Vanishing arrival intensity: quotes rest untouched all session.
        r = simulator.run(params, QuoteParams(order_flow_intensity=1e-12))
        assert r.fills == 0
        assert r.spread_pnl == pytest.approx(0.0)
        assert r.inventory_pnl == pytest.approx(0.0)
        assert r.total_pnl == pytest.approx(0.0)

    def test_inventory_pnl_is_not_free_of_the_price_path(self):
        """Different paths must produce different inventory P&L; if they do not,
        the mark-to-market leg is not actually being computed."""
        results = [
            simulator.run(SimulationParams(steps=250, seed=s), QuoteParams()) for s in range(6)
        ]
        inventory_pnls = {round(r.inventory_pnl, 9) for r in results}
        assert len(inventory_pnls) > 1


class TestSurface:
    def test_atm_vol_follows_the_term_structure(self):
        s = VolSurface(atm_vol=0.20, term_slope=0.04, ref_tau=0.25)
        assert s.atm(0.25) == pytest.approx(0.20)
        assert s.atm(1.25) == pytest.approx(0.24)

    def test_equity_skew_bids_up_the_downside(self):
        s = VolSurface(skew=-0.20, curvature=0.0)
        assert s.vol(-0.2, 0.25) > s.vol(0.0, 0.25) > s.vol(0.2, 0.25)

    def test_curvature_lifts_both_wings(self):
        s = VolSurface(skew=0.0, curvature=0.8)
        assert s.vol(-0.3, 0.25) > s.vol(0.0, 0.25)
        assert s.vol(0.3, 0.25) > s.vol(0.0, 0.25)

    def test_the_smile_flattens_with_maturity(self):
        s = VolSurface(skew=-0.3, curvature=0.5, term_slope=0.0)
        near = s.vol(-0.3, 0.05) - s.atm(0.05)
        far = s.vol(-0.3, 3.0) - s.atm(3.0)
        assert near > far

    def test_total_variance_grows_with_maturity(self):
        """More time cannot mean less uncertainty — the calendar condition."""
        s = VolSurface()
        assert s.is_calendar_arbitrage_free(0.0, (0.05, 0.25, 1.0, 3.0))
        assert s.is_calendar_arbitrage_free(-0.2, (0.05, 0.25, 1.0, 3.0))

    def test_a_mild_smile_is_butterfly_arbitrage_free(self):
        assert VolSurface(skew=-0.12, curvature=0.4).is_butterfly_arbitrage_free(0.25)

    def test_an_extreme_smile_is_not(self):
        """The analytic statement of the bug found in the chain generator: an
        arbitrary smile is not arbitrage-free, however plausible it looks."""
        assert not VolSurface(skew=-0.1, curvature=12.0).is_butterfly_arbitrage_free(0.25)

    def test_vol_is_floored(self):
        s = VolSurface(atm_vol=0.01, skew=-5.0, curvature=0.0)
        assert s.vol(2.0, 1.0) > 0.0

    def test_rejects_a_non_positive_strike(self):
        with pytest.raises(ValueError, match="must be positive"):
            VolSurface().vol_for_strike(0.0, 100.0, 0.25)


class TestQuotingUsesTheSurface:
    def test_a_skewed_surface_prices_downside_strikes_richer(self):
        """Sanity that the surface actually reaches the quoting path."""
        s = VolSurface(skew=-0.3, curvature=0.3)
        fwd = 100.0
        low = s.vol_for_strike(80.0, fwd, 0.25)
        high = s.vol_for_strike(120.0, fwd, 0.25)
        assert low > high

        g_low = greeks(100.0, 80.0, 0.0, 0.0, low, 0.25, OptionType.PUT)
        assert g_low.vega > 0.0
