"""Black-Scholes correctness tests.

Three independent kinds of check, because each catches a different class of bug:

1. A textbook closed-form value (catches a wrong formula outright).
2. Put-call parity (catches sign/discounting errors the textbook case misses).
3. Central finite differences against the analytic Greeks (catches unit-scaling
   and algebra errors in the derivatives).
"""

from __future__ import annotations

import math
from itertools import pairwise

import pytest

from pricecalc.core import black_scholes as bs
from pricecalc.core.black_scholes import NoImpliedVolError, OptionType

# Baseline: S=100, K=100, r=5%, q=0, sigma=20%, 1y. Standard worked example.
BASE = {"spot": 100.0, "strike": 100.0, "rate": 0.05, "div_yield": 0.0, "vol": 0.20, "tau": 1.0}

# A spread of regimes: ATM, deep ITM/OTM, short-dated, high vol, dividend-paying.
CASES = [
    {"spot": 100.0, "strike": 100.0, "rate": 0.05, "div_yield": 0.00, "vol": 0.20, "tau": 1.00},
    {"spot": 100.0, "strike": 130.0, "rate": 0.05, "div_yield": 0.00, "vol": 0.20, "tau": 0.50},
    {"spot": 100.0, "strike": 70.0, "rate": 0.03, "div_yield": 0.02, "vol": 0.35, "tau": 2.00},
    {"spot": 50.0, "strike": 52.5, "rate": 0.01, "div_yield": 0.00, "vol": 0.60, "tau": 0.05},
    {"spot": 4200.0, "strike": 4000.0, "rate": 0.045, "div_yield": 0.015, "vol": 0.15, "tau": 0.25},
    {"spot": 100.0, "strike": 100.0, "rate": 0.00, "div_yield": 0.00, "vol": 0.80, "tau": 3.00},
]
TYPES = [OptionType.CALL, OptionType.PUT]


class TestPrice:
    def test_matches_textbook_value(self):
        call = bs.price(**BASE, option_type=OptionType.CALL)
        assert call == pytest.approx(10.450583572185565, rel=1e-12)

    def test_put_matches_textbook_value(self):
        put = bs.price(**BASE, option_type=OptionType.PUT)
        assert put == pytest.approx(5.573526022256971, rel=1e-12)

    @pytest.mark.parametrize("case", CASES)
    def test_put_call_parity(self, case):
        """C - P = S*exp(-qT) - K*exp(-rT), exactly, for European options."""
        call = bs.price(**case, option_type=OptionType.CALL)
        put = bs.price(**case, option_type=OptionType.PUT)
        expected = case["spot"] * math.exp(-case["div_yield"] * case["tau"]) - case[
            "strike"
        ] * math.exp(-case["rate"] * case["tau"])
        assert call - put == pytest.approx(expected, abs=1e-10)

    @pytest.mark.parametrize("case", CASES)
    @pytest.mark.parametrize("opt", TYPES)
    def test_within_no_arbitrage_bounds(self, case, opt):
        px = bs.price(**case, option_type=opt)
        lower, upper = bs.price_bounds(
            case["spot"], case["strike"], case["rate"], case["div_yield"], case["tau"], opt
        )
        assert lower - 1e-12 <= px <= upper + 1e-12

    @pytest.mark.parametrize("opt", TYPES)
    def test_monotonic_increasing_in_vol(self, opt):
        """Vega > 0 everywhere, which is what makes implied vol well-defined."""
        vols = [0.05, 0.1, 0.2, 0.5, 1.0]
        prices = [bs.price(**{**BASE, "vol": v}, option_type=opt) for v in vols]
        assert all(b > a for a, b in pairwise(prices))

    @pytest.mark.parametrize("opt", TYPES)
    def test_at_expiry_is_intrinsic(self, opt):
        for spot in (80.0, 100.0, 120.0):
            px = bs.price(**{**BASE, "spot": spot, "tau": 0.0}, option_type=opt)
            assert px == pytest.approx(max(opt.sign * (spot - BASE["strike"]), 0.0))

    @pytest.mark.parametrize("opt", TYPES)
    def test_zero_vol_is_discounted_forward_intrinsic(self, opt):
        px = bs.price(**{**BASE, "vol": 0.0}, option_type=opt)
        fwd = 100.0 * math.exp(0.05)
        expected = math.exp(-0.05) * max(opt.sign * (fwd - 100.0), 0.0)
        assert px == pytest.approx(expected, abs=1e-12)

    def test_rejects_non_positive_spot(self):
        with pytest.raises(ValueError, match="spot must be positive"):
            bs.price(**{**BASE, "spot": 0.0}, option_type=OptionType.CALL)


class TestGreeks:
    """Analytic Greeks vs central finite differences.

    The bump sizes and tolerances below are tuned so truncation error (which
    grows with h) and floating-point cancellation (which shrinks with h) are
    both comfortably under the assertion tolerance.
    """

    @pytest.mark.parametrize("case", CASES)
    @pytest.mark.parametrize("opt", TYPES)
    def test_delta(self, case, opt):
        h = case["spot"] * 1e-5
        fd = (
            bs.price(**{**case, "spot": case["spot"] + h}, option_type=opt)
            - bs.price(**{**case, "spot": case["spot"] - h}, option_type=opt)
        ) / (2 * h)
        assert bs.greeks(**case, option_type=opt).delta == pytest.approx(fd, abs=1e-6)

    @pytest.mark.parametrize("case", CASES)
    @pytest.mark.parametrize("opt", TYPES)
    def test_gamma(self, case, opt):
        # Second differences amplify cancellation, so use a larger bump.
        h = case["spot"] * 1e-3
        fd = (
            bs.price(**{**case, "spot": case["spot"] + h}, option_type=opt)
            - 2 * bs.price(**case, option_type=opt)
            + bs.price(**{**case, "spot": case["spot"] - h}, option_type=opt)
        ) / (h * h)
        assert bs.greeks(**case, option_type=opt).gamma == pytest.approx(fd, rel=1e-4, abs=1e-9)

    @pytest.mark.parametrize("case", CASES)
    @pytest.mark.parametrize("opt", TYPES)
    def test_vega_per_vol_point(self, case, opt):
        h = 1e-6
        fd_raw = (
            bs.price(**{**case, "vol": case["vol"] + h}, option_type=opt)
            - bs.price(**{**case, "vol": case["vol"] - h}, option_type=opt)
        ) / (2 * h)
        assert bs.greeks(**case, option_type=opt).vega == pytest.approx(fd_raw / 100.0, rel=1e-5)

    @pytest.mark.parametrize("case", CASES)
    @pytest.mark.parametrize("opt", TYPES)
    def test_theta_per_calendar_day(self, case, opt):
        # theta is dV/dt while tau counts down, hence the sign flip.
        h = 1e-6
        fd_raw = -(
            bs.price(**{**case, "tau": case["tau"] + h}, option_type=opt)
            - bs.price(**{**case, "tau": case["tau"] - h}, option_type=opt)
        ) / (2 * h)
        assert bs.greeks(**case, option_type=opt).theta == pytest.approx(
            fd_raw / 365.0, rel=1e-4, abs=1e-9
        )

    @pytest.mark.parametrize("case", CASES)
    @pytest.mark.parametrize("opt", TYPES)
    def test_rho_per_percent(self, case, opt):
        h = 1e-7
        fd_raw = (
            bs.price(**{**case, "rate": case["rate"] + h}, option_type=opt)
            - bs.price(**{**case, "rate": case["rate"] - h}, option_type=opt)
        ) / (2 * h)
        assert bs.greeks(**case, option_type=opt).rho == pytest.approx(
            fd_raw / 100.0, rel=1e-5, abs=1e-9
        )

    @pytest.mark.parametrize("case", CASES)
    @pytest.mark.parametrize("opt", TYPES)
    def test_vanna(self, case, opt):
        """d(delta)/d(sigma), reported per vol point."""
        h = 1e-6
        fd_raw = (
            bs.greeks(**{**case, "vol": case["vol"] + h}, option_type=opt).delta
            - bs.greeks(**{**case, "vol": case["vol"] - h}, option_type=opt).delta
        ) / (2 * h)
        assert bs.greeks(**case, option_type=opt).vanna == pytest.approx(
            fd_raw / 100.0, rel=1e-4, abs=1e-9
        )

    @pytest.mark.parametrize("case", CASES)
    @pytest.mark.parametrize("opt", TYPES)
    def test_volga(self, case, opt):
        """d(vega)/d(sigma). Both sides are already /100, so scale by 100 once more."""
        h = 1e-5
        fd_raw = (
            bs.greeks(**{**case, "vol": case["vol"] + h}, option_type=opt).vega * 100.0
            - bs.greeks(**{**case, "vol": case["vol"] - h}, option_type=opt).vega * 100.0
        ) / (2 * h)
        assert bs.greeks(**case, option_type=opt).volga == pytest.approx(
            fd_raw / 10_000.0, rel=1e-4, abs=1e-9
        )

    @pytest.mark.parametrize("case", CASES)
    def test_gamma_and_vega_are_type_independent(self, case):
        """Parity is linear in S and K, so its second-order Greeks vanish."""
        c = bs.greeks(**case, option_type=OptionType.CALL)
        p = bs.greeks(**case, option_type=OptionType.PUT)
        assert c.gamma == pytest.approx(p.gamma, rel=1e-12)
        assert c.vega == pytest.approx(p.vega, rel=1e-12)
        assert c.vanna == pytest.approx(p.vanna, rel=1e-12)
        assert c.volga == pytest.approx(p.volga, rel=1e-12)

    @pytest.mark.parametrize("case", CASES)
    def test_delta_parity(self, case):
        """delta_call - delta_put = exp(-qT)."""
        c = bs.greeks(**case, option_type=OptionType.CALL).delta
        p = bs.greeks(**case, option_type=OptionType.PUT).delta
        assert c - p == pytest.approx(math.exp(-case["div_yield"] * case["tau"]), abs=1e-12)

    @pytest.mark.parametrize("opt", TYPES)
    def test_long_option_has_negative_theta_and_positive_gamma(self, opt):
        g = bs.greeks(**BASE, option_type=opt)
        assert g.gamma > 0
        assert g.vega > 0
        assert g.theta < 0

    @pytest.mark.parametrize("opt", TYPES)
    def test_expiry_greeks_collapse(self, opt):
        g = bs.greeks(**{**BASE, "spot": 120.0, "tau": 0.0}, option_type=opt)
        assert g.gamma == 0.0 and g.vega == 0.0 and g.theta == 0.0
        # 120 vs strike 100: the call is ITM, the put is not.
        assert g.delta == (1.0 if opt is OptionType.CALL else 0.0)


class TestImpliedVol:
    @pytest.mark.parametrize("case", CASES)
    @pytest.mark.parametrize("opt", TYPES)
    def test_round_trip(self, case, opt):
        px = bs.price(**case, option_type=opt)
        recovered = bs.implied_vol(
            target_price=px,
            spot=case["spot"],
            strike=case["strike"],
            rate=case["rate"],
            div_yield=case["div_yield"],
            tau=case["tau"],
            option_type=opt,
        )
        assert recovered == pytest.approx(case["vol"], rel=1e-8)

    @pytest.mark.parametrize("vol", [0.01, 0.05, 0.25, 1.5, 4.0])
    def test_round_trip_across_extreme_vols(self, vol):
        px = bs.price(**{**BASE, "vol": vol}, option_type=OptionType.CALL)
        recovered = bs.implied_vol(
            target_price=px,
            **{k: v for k, v in BASE.items() if k != "vol"},
            option_type=OptionType.CALL,
        )
        assert recovered == pytest.approx(vol, rel=1e-6)

    def test_price_below_intrinsic_has_no_solution(self):
        lower, _ = bs.price_bounds(100.0, 100.0, 0.05, 0.0, 1.0, OptionType.CALL)
        with pytest.raises(NoImpliedVolError, match="lower bound"):
            bs.implied_vol(
                target_price=lower * 0.5,
                spot=100.0,
                strike=100.0,
                rate=0.05,
                div_yield=0.0,
                tau=1.0,
                option_type=OptionType.CALL,
            )

    def test_price_above_underlying_has_no_solution(self):
        with pytest.raises(NoImpliedVolError, match="upper bound"):
            bs.implied_vol(
                target_price=105.0,
                spot=100.0,
                strike=100.0,
                rate=0.05,
                div_yield=0.0,
                tau=1.0,
                option_type=OptionType.CALL,
            )

    def test_at_expiry_has_no_solution(self):
        with pytest.raises(NoImpliedVolError, match="at expiry"):
            bs.implied_vol(
                target_price=5.0,
                spot=100.0,
                strike=100.0,
                rate=0.05,
                div_yield=0.0,
                tau=0.0,
                option_type=OptionType.CALL,
            )


class TestEvaluate:
    def test_bundles_price_greeks_and_diagnostics(self):
        r = bs.evaluate(**BASE, option_type=OptionType.CALL)
        assert r.price == pytest.approx(10.450583572185565, rel=1e-12)
        assert r.forward == pytest.approx(100.0 * math.exp(0.05), rel=1e-12)
        assert r.intrinsic == 0.0
        assert r.time_value == pytest.approx(r.price, rel=1e-12)
        assert r.d1 - r.d2 == pytest.approx(BASE["vol"] * math.sqrt(BASE["tau"]), rel=1e-12)
