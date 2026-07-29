"""Property-based tests: relations that must hold for *every* input.

The example-based suite pins six market regimes chosen by hand. Those catch a
wrong formula, but they cannot catch a formula that is right in the regimes
someone thought to write down. Hypothesis generates thousands of inputs and,
when one fails, shrinks it to the smallest reproducing case — which is usually
the boundary nobody considered.

**Scope of the generated envelope.** Inputs are drawn from a wide but
*realistic* market envelope (see `market()` below). Genuinely pathological
corners — zero time, zero vol, expiry-day intrinsic — are deliberately excluded
here because they are already pinned by exact-value tests in
`test_black_scholes.py`, and mixing them in only produces failures about
floating-point limits rather than about the maths.

**Tolerances scale with the inputs.** An absolute tolerance that is sane for a
$100 stock is meaningless for a $50,000 one, so comparisons are expressed
relative to the largest term in the identity being checked.
"""

from __future__ import annotations

import math

import pytest
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

from pricecalc.core import arbitrage as arb
from pricecalc.core.black_scholes import (
    NoImpliedVolError,
    OptionType,
    d1_d2,
    greeks,
    implied_vol,
    price,
    price_bounds,
)
from pricecalc.core.chain import Chain, Quote
from pricecalc.core.marketdata.simulated import SmileParams, generate_chain

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

finite = {"allow_nan": False, "allow_infinity": False}

option_types = st.sampled_from([OptionType.CALL, OptionType.PUT])


@st.composite
def market(draw: st.DrawFn) -> dict[str, float]:
    """A realistic market state.

    Strike is drawn as a multiple of spot rather than independently: an
    unconstrained pair can differ by many orders of magnitude, which says
    nothing about the model and everything about `log()` losing precision.
    """
    spot = draw(st.floats(min_value=1.0, max_value=10_000.0, **finite))
    moneyness = draw(st.floats(min_value=0.25, max_value=4.0, **finite))
    return {
        "spot": spot,
        "strike": spot * moneyness,
        "rate": draw(st.floats(min_value=-0.02, max_value=0.20, **finite)),
        "div_yield": draw(st.floats(min_value=0.0, max_value=0.15, **finite)),
        "vol": draw(st.floats(min_value=0.01, max_value=2.0, **finite)),
        "tau": draw(st.floats(min_value=1.0 / 365.0, max_value=5.0, **finite)),
    }


def scale_tol(m: dict[str, float]) -> float:
    """Absolute tolerance proportional to the largest quantity in play."""
    return 1e-8 * max(m["spot"], m["strike"])


# ---------------------------------------------------------------------------
# Pricing
# ---------------------------------------------------------------------------


class TestPricingProperties:
    @given(m=market())
    def test_put_call_parity_holds_everywhere(self, m):
        """C - P = S·e^(-q·tau) - K·e^(-r·tau), for every input in the envelope."""
        call = price(**m, option_type=OptionType.CALL)
        put = price(**m, option_type=OptionType.PUT)
        expected = m["spot"] * math.exp(-m["div_yield"] * m["tau"]) - m["strike"] * math.exp(
            -m["rate"] * m["tau"]
        )
        assert call - put == pytest.approx(expected, abs=scale_tol(m))

    @given(m=market(), opt=option_types)
    def test_price_stays_inside_its_no_arbitrage_band(self, m, opt):
        px = price(**m, option_type=opt)
        lower, upper = price_bounds(
            m["spot"], m["strike"], m["rate"], m["div_yield"], m["tau"], opt
        )
        tol = scale_tol(m)
        assert lower - tol <= px <= upper + tol

    @given(m=market(), opt=option_types, bump=st.floats(0.001, 1.0, **finite))
    def test_price_is_increasing_in_volatility(self, m, opt, bump):
        """Strictly positive vega is what makes implied vol well-defined."""
        base = price(**m, option_type=opt)
        higher = price(**{**m, "vol": m["vol"] + bump}, option_type=opt)
        assert higher >= base - scale_tol(m)

    @given(m=market(), opt=option_types)
    def test_price_moves_the_right_way_with_spot(self, m, opt):
        step = m["spot"] * 0.01
        up = price(**{**m, "spot": m["spot"] + step}, option_type=opt)
        down = price(**{**m, "spot": m["spot"] - step}, option_type=opt)
        tol = scale_tol(m)
        if opt is OptionType.CALL:
            assert up >= down - tol
        else:
            assert up <= down + tol

    @given(m=market(), opt=option_types)
    def test_price_moves_the_right_way_with_strike(self, m, opt):
        step = m["strike"] * 0.01
        up = price(**{**m, "strike": m["strike"] + step}, option_type=opt)
        down = price(**{**m, "strike": m["strike"] - step}, option_type=opt)
        tol = scale_tol(m)
        if opt is OptionType.CALL:
            assert up <= down + tol
        else:
            assert up >= down - tol

    @given(m=market(), opt=option_types)
    def test_price_is_convex_in_strike(self, m, opt):
        """Convexity in strike is exactly what the butterfly scanner enforces."""
        gap = m["strike"] * 0.05
        lo = price(**{**m, "strike": m["strike"] - gap}, option_type=opt)
        mid = price(**m, option_type=opt)
        hi = price(**{**m, "strike": m["strike"] + gap}, option_type=opt)
        assert lo - 2.0 * mid + hi >= -scale_tol(m)

    @given(m=market(), opt=option_types, factor=st.floats(0.01, 100.0, **finite))
    def test_price_is_homogeneous_of_degree_one(self, m, opt, factor):
        """Scaling spot and strike together scales the price by the same factor.

        A currency redenomination cannot change value. This catches an absolute
        constant leaking into a formula that should be scale-free — the kind of
        bug that hides completely in a suite priced around S = 100.
        """
        base = price(**m, option_type=opt)
        scaled = price(
            **{**m, "spot": m["spot"] * factor, "strike": m["strike"] * factor},
            option_type=opt,
        )
        assert scaled == pytest.approx(base * factor, rel=1e-9, abs=1e-9 * factor)

    @given(m=market())
    def test_d1_and_d2_differ_by_total_volatility(self, m):
        d1, d2 = d1_d2(m["spot"], m["strike"], m["rate"], m["div_yield"], m["vol"], m["tau"])
        assert d1 - d2 == pytest.approx(m["vol"] * math.sqrt(m["tau"]), rel=1e-12)


# ---------------------------------------------------------------------------
# Greeks
# ---------------------------------------------------------------------------


class TestGreekProperties:
    @given(m=market())
    def test_second_order_greeks_do_not_depend_on_the_right(self, m):
        """Parity is linear in S and K, so its curvature terms cancel."""
        c = greeks(**m, option_type=OptionType.CALL)
        p = greeks(**m, option_type=OptionType.PUT)
        assert c.gamma == pytest.approx(p.gamma, rel=1e-9)
        assert c.vega == pytest.approx(p.vega, rel=1e-9)
        assert c.vanna == pytest.approx(p.vanna, rel=1e-9)
        assert c.volga == pytest.approx(p.volga, rel=1e-9)

    @given(m=market())
    def test_delta_parity(self, m):
        c = greeks(**m, option_type=OptionType.CALL).delta
        p = greeks(**m, option_type=OptionType.PUT).delta
        assert c - p == pytest.approx(math.exp(-m["div_yield"] * m["tau"]), abs=1e-9)

    @given(m=market(), opt=option_types)
    def test_long_premium_has_positive_convexity(self, m, opt):
        g = greeks(**m, option_type=opt)
        assert g.gamma >= 0.0
        assert g.vega >= 0.0

    @given(m=market(), opt=option_types)
    def test_delta_respects_its_bounds(self, m, opt):
        """A call delta lives in [0, e^(-q·tau)]; a put's in [-e^(-q·tau), 0]."""
        cap = math.exp(-m["div_yield"] * m["tau"])
        delta = greeks(**m, option_type=opt).delta
        if opt is OptionType.CALL:
            assert -1e-12 <= delta <= cap + 1e-12
        else:
            assert -cap - 1e-12 <= delta <= 1e-12

    @given(m=market(), opt=option_types)
    def test_gamma_and_vega_scale_correctly(self, m, opt):
        """Gamma is per $1 of a scale-free quantity, so it scales as 1/S."""
        factor = 10.0
        base = greeks(**m, option_type=opt)
        scaled = greeks(
            **{**m, "spot": m["spot"] * factor, "strike": m["strike"] * factor},
            option_type=opt,
        )
        assert scaled.gamma == pytest.approx(base.gamma / factor, rel=1e-8)
        assert scaled.vega == pytest.approx(base.vega * factor, rel=1e-8)
        assert scaled.delta == pytest.approx(base.delta, rel=1e-9)


# ---------------------------------------------------------------------------
# Implied volatility
# ---------------------------------------------------------------------------


class TestImpliedVolProperties:
    @given(m=market(), opt=option_types)
    @settings(suppress_health_check=[HealthCheck.filter_too_much])
    def test_round_trip_recovers_the_input_volatility(self, m, opt):
        """price -> implied_vol -> the same vol, wherever the inversion is well posed.

        Deep out-of-the-money options are excluded: their price is flat in vol,
        so recovering sigma from a price is ill-conditioned as a matter of
        arithmetic, not of implementation. Vega is the conditioning number, so
        that is what we filter on.
        """
        g = greeks(**m, option_type=opt)
        assume(g.vega * 100.0 > 1e-4 * m["spot"])

        px = price(**m, option_type=opt)
        recovered = implied_vol(
            target_price=px,
            spot=m["spot"],
            strike=m["strike"],
            rate=m["rate"],
            div_yield=m["div_yield"],
            tau=m["tau"],
            option_type=opt,
        )
        assert recovered == pytest.approx(m["vol"], rel=1e-6)

    @given(m=market(), opt=option_types, over=st.floats(1.001, 5.0, **finite))
    def test_a_price_above_the_band_never_yields_a_volatility(self, m, opt, over):
        _, upper = price_bounds(m["spot"], m["strike"], m["rate"], m["div_yield"], m["tau"], opt)
        with pytest.raises(NoImpliedVolError):
            implied_vol(
                target_price=upper * over,
                spot=m["spot"],
                strike=m["strike"],
                rate=m["rate"],
                div_yield=m["div_yield"],
                tau=m["tau"],
                option_type=opt,
            )

    @given(m=market(), opt=option_types, under=st.floats(0.0, 0.999, **finite))
    def test_a_price_below_the_band_never_yields_a_volatility(self, m, opt, under):
        lower, _ = price_bounds(m["spot"], m["strike"], m["rate"], m["div_yield"], m["tau"], opt)
        assume(lower > 1e-6 * m["spot"])
        with pytest.raises(NoImpliedVolError):
            implied_vol(
                target_price=lower * under,
                spot=m["spot"],
                strike=m["strike"],
                rate=m["rate"],
                div_yield=m["div_yield"],
                tau=m["tau"],
                option_type=opt,
            )


# ---------------------------------------------------------------------------
# Chain input validation — the guards a live feed will exercise first
# ---------------------------------------------------------------------------


class TestQuoteValidation:
    @given(
        bid=st.floats(0.0, 1000.0, **finite),
        spread=st.floats(0.0, 100.0, **finite),
    )
    def test_accepts_any_uncrossed_market(self, bid, spread):
        q = Quote(tau=1.0, strike=100.0, option_type=OptionType.CALL, bid=bid, ask=bid + spread)
        assert q.mid == pytest.approx(bid + spread / 2.0)
        assert q.spread == pytest.approx(spread)

    @given(bid=st.floats(0.01, 1000.0, **finite), gap=st.floats(0.001, 100.0, **finite))
    def test_rejects_a_crossed_market(self, bid, gap):
        """Bid above ask is bad data, not a free lunch — reject at the boundary."""
        with pytest.raises(ValueError, match="crossed market"):
            Quote(tau=1.0, strike=100.0, option_type=OptionType.CALL, bid=bid, ask=bid - gap)

    @given(bid=st.floats(-1000.0, -0.001, **finite))
    def test_rejects_a_negative_bid(self, bid):
        with pytest.raises(ValueError, match="bid must be non-negative"):
            Quote(tau=1.0, strike=100.0, option_type=OptionType.CALL, bid=bid, ask=100.0)

    @given(strike=st.floats(-1000.0, 0.0, **finite))
    def test_rejects_a_non_positive_strike(self, strike):
        with pytest.raises(ValueError, match="strike must be positive"):
            Quote(tau=1.0, strike=strike, option_type=OptionType.CALL, bid=1.0, ask=2.0)

    @given(spot=st.floats(-1000.0, 0.0, **finite))
    def test_chain_rejects_a_non_positive_spot(self, spot):
        with pytest.raises(ValueError, match="spot must be positive"):
            Chain(spot=spot, rate=0.0, div_yield=0.0, quotes=())

    def test_chain_rejects_a_crossed_underlying(self):
        with pytest.raises(ValueError, match="crossed market"):
            Chain(
                spot=100.0,
                rate=0.0,
                div_yield=0.0,
                quotes=(),
                underlying_bid=101.0,
                underlying_ask=99.0,
            )


# ---------------------------------------------------------------------------
# Scanner
# ---------------------------------------------------------------------------

# Chain generation plus an O(strikes^3) butterfly sweep is far heavier than a
# scalar price, so these run fewer examples and waive the per-example deadline.
scanner_settings = settings(
    max_examples=30,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)


@st.composite
def chain_params(draw: st.DrawFn) -> dict[str, object]:
    n_expiries = draw(st.integers(1, 3))
    return {
        "spot": draw(st.floats(10.0, 5_000.0, **finite)),
        "rate": draw(st.floats(-0.01, 0.15, **finite)),
        "div_yield": draw(st.floats(0.0, 0.08, **finite)),
        "expiries": tuple(
            sorted(
                draw(
                    st.lists(
                        st.floats(0.02, 3.0, **finite),
                        min_size=n_expiries,
                        max_size=n_expiries,
                        unique=True,
                    )
                )
            )
        ),
        "strike_count": draw(st.integers(3, 9)),
        "strike_span": draw(st.floats(0.05, 0.6, **finite)),
        "smile": SmileParams(
            atm_vol=draw(st.floats(0.05, 1.2, **finite)),
            skew=draw(st.floats(-0.6, 0.4, **finite)),
            curvature=draw(st.floats(0.0, 1.5, **finite)),
        ),
        "spread_bps": draw(st.floats(0.0, 500.0, **finite)),
        "seed": draw(st.integers(0, 10_000)),
    }


class TestScannerProperties:
    @given(params=chain_params())
    @scanner_settings
    def test_a_consistently_priced_chain_never_shows_arbitrage(self, params):
        """The central claim: one smile in, zero findings out, for any parameters.

        This is the false-positive guarantee. The example-based suite checks a
        handful of parameter sets; this checks the shape of the claim.
        """
        sim = generate_chain(**params, n_violations=0)
        assert arb.scan(sim.chain) == []

    @given(params=chain_params(), n=st.integers(1, 3))
    @scanner_settings
    def test_every_finding_is_financed_by_its_own_legs(self, params, n):
        """Reported profit must equal the net cash flow of the published trade."""
        sim = generate_chain(**params, n_violations=n)
        for v in arb.scan(sim.chain):
            net = sum(leg.cash_flow for leg in v.legs)
            assert net == pytest.approx(v.profit, abs=1e-6 * float(params["spot"]))

    @given(params=chain_params(), n=st.integers(1, 3))
    @scanner_settings
    def test_findings_are_strictly_profitable_and_ranked(self, params, n):
        sim = generate_chain(**params, n_violations=n)
        found = arb.scan(sim.chain)
        profits = [v.profit for v in found]
        assert all(p > 0 for p in profits)
        assert profits == sorted(profits, reverse=True)

    @given(params=chain_params(), n=st.integers(1, 3), floor=st.floats(0.0, 5.0, **finite))
    @scanner_settings
    def test_raising_the_edge_filter_only_removes_findings(self, params, n, floor):
        """Filtering is monotone: a stricter floor yields a subset, never new items."""
        sim = generate_chain(**params, n_violations=n)
        loose = arb.scan(sim.chain, min_edge=0.0)
        strict = arb.scan(sim.chain, min_edge=floor)
        loose_ids = {(v.kind, v.tau, v.strikes, round(v.profit, 9)) for v in loose}
        for v in strict:
            assert (v.kind, v.tau, v.strikes, round(v.profit, 9)) in loose_ids
            assert v.profit > floor

    @given(params=chain_params(), n=st.integers(0, 3))
    @scanner_settings
    def test_generation_is_reproducible_from_the_seed(self, params, n):
        """Determinism is load-bearing: the simulator is the scanner's oracle."""
        first = generate_chain(**params, n_violations=n)
        second = generate_chain(**params, n_violations=n)
        assert first.chain.quotes == second.chain.quotes
        assert [p.description for p in first.planted] == [p.description for p in second.planted]

    @given(params=chain_params())
    @scanner_settings
    def test_generated_markets_are_never_crossed(self, params):
        sim = generate_chain(**params, n_violations=2)
        for q in sim.chain.quotes:
            assert 0.0 <= q.bid <= q.ask
