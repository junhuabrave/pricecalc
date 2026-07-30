"""Greek unit scaling, verified against finite differences of ``price()`` alone.

The existing finite-difference suite derives ``vanna`` from the analytic
``delta`` and ``volga`` from the analytic ``vega``. That makes each of those a
check on one derivative given another, not on the pair: a scale factor applied
consistently to both would cancel and the test would still pass.

Everything below is differenced from ``price()`` and nothing else, so the whole
chain — derivative, cross derivative, and the factor converting each to trader
units — is independent of what ``greeks()`` believes.

Bump sizes are chosen so truncation error (which grows with the bump) and
floating-point cancellation (which grows as it shrinks) both sit well under the
tolerance; second and mixed differences need a larger bump for that reason.
"""

from __future__ import annotations

import math
from typing import ClassVar

import pytest

from pricecalc.core import black_scholes as bs
from pricecalc.core.black_scholes import OptionType

CASES = [
    pytest.param(
        {"spot": 100.0, "strike": 100.0, "rate": 0.05, "div_yield": 0.0, "vol": 0.20, "tau": 1.0},
        id="atm-1y",
    ),
    pytest.param(
        {"spot": 100.0, "strike": 130.0, "rate": 0.05, "div_yield": 0.0, "vol": 0.20, "tau": 0.5},
        id="otm",
    ),
    pytest.param(
        {"spot": 100.0, "strike": 70.0, "rate": 0.03, "div_yield": 0.02, "vol": 0.35, "tau": 2.0},
        id="itm-with-dividend",
    ),
    pytest.param(
        {
            "spot": 4200.0,
            "strike": 4000.0,
            "rate": 0.045,
            "div_yield": 0.015,
            "vol": 0.15,
            "tau": 0.25,
        },
        id="index-scale",
    ),
    pytest.param(
        {"spot": 100.0, "strike": 100.0, "rate": -0.02, "div_yield": 0.03, "vol": 0.30, "tau": 1.5},
        id="negative-rate",
    ),
]
TYPES = [OptionType.CALL, OptionType.PUT]


def px(case: dict[str, float], option_type: OptionType, **bumps: float) -> float:
    return bs.price(**{**case, **bumps}, option_type=option_type)


class TestUnitConversion:
    """Each Greek's reported value equals the raw derivative times one factor.

    The factor is the whole point: a trader reads vega per vol point and theta
    per calendar day, and getting the factor wrong produces numbers that look
    plausible on a risk screen and are wrong by two orders of magnitude.
    """

    @pytest.mark.parametrize("case", CASES)
    @pytest.mark.parametrize("opt", TYPES)
    def test_vega_is_the_price_move_for_one_vol_point(self, case, opt):
        """Vega should predict the actual repricing for a 1-point vol move.

        Rather than compare derivatives, reprice at sigma +/- 0.005 and check
        that the difference — a genuine one-vol-point move — is what vega says.
        Second-order effects cancel in the central difference.
        """
        h = 0.005  # half a vol point either side
        reprice = px(case, opt, vol=case["vol"] + h) - px(case, opt, vol=case["vol"] - h)
        assert bs.greeks(**case, option_type=opt).vega == pytest.approx(reprice, rel=1e-3)

    @pytest.mark.parametrize("case", CASES)
    @pytest.mark.parametrize("opt", TYPES)
    def test_theta_is_the_price_move_over_one_calendar_day(self, case, opt):
        """Theta should predict one day of decay: tau shrinks by 1/365 of a year.

        The sign convention matters as much as the size — long premium decays,
        so theta must be the *negative* of the derivative with respect to tau.
        """
        day = 1.0 / 365.0
        reprice = px(case, opt, tau=case["tau"] - 0.5 * day) - px(
            case, opt, tau=case["tau"] + 0.5 * day
        )
        assert bs.greeks(**case, option_type=opt).theta == pytest.approx(reprice, rel=2e-3)

    @pytest.mark.parametrize("case", CASES)
    @pytest.mark.parametrize("opt", TYPES)
    def test_rho_is_the_price_move_for_one_percent_of_rate(self, case, opt):
        h = 0.005  # half a percent either side
        reprice = px(case, opt, rate=case["rate"] + h) - px(case, opt, rate=case["rate"] - h)
        assert bs.greeks(**case, option_type=opt).rho == pytest.approx(reprice, rel=1e-3)

    @pytest.mark.parametrize("case", CASES)
    @pytest.mark.parametrize("opt", TYPES)
    def test_vanna_is_the_mixed_second_derivative_per_vol_point(self, case, opt):
        """d2V/dS dsigma, from a four-point mixed difference of the price surface.

        This is the check the existing suite cannot make: differencing the
        analytic delta in vol tests vanna *given* delta, so a scale error shared
        by both survives. Here nothing but ``price()`` is consulted.
        """
        hs = case["spot"] * 1e-3
        hv = 1e-3
        mixed = (
            px(case, opt, spot=case["spot"] + hs, vol=case["vol"] + hv)
            - px(case, opt, spot=case["spot"] + hs, vol=case["vol"] - hv)
            - px(case, opt, spot=case["spot"] - hs, vol=case["vol"] + hv)
            + px(case, opt, spot=case["spot"] - hs, vol=case["vol"] - hv)
        ) / (4.0 * hs * hv)
        assert bs.greeks(**case, option_type=opt).vanna == pytest.approx(mixed / 100.0, rel=1e-4)

    @pytest.mark.parametrize("case", CASES)
    @pytest.mark.parametrize("opt", TYPES)
    def test_volga_is_the_second_vol_derivative_per_vol_point_squared(self, case, opt):
        """d2V/dsigma2, from a second difference of the price in vol alone.

        Volga is reported as the change in (already rescaled) vega per vol
        point, so the raw second derivative is divided by 100 twice. Deriving it
        from ``price()`` is the only way to see both factors.
        """
        hv = 1e-3
        second = (
            px(case, opt, vol=case["vol"] + hv)
            - 2.0 * px(case, opt)
            + px(case, opt, vol=case["vol"] - hv)
        ) / (hv * hv)
        assert bs.greeks(**case, option_type=opt).volga == pytest.approx(
            second / 10_000.0, rel=1e-4
        )


class TestDegenerateVolatility:
    """The zero-volatility limit, where the option becomes a forward contract.

    With sigma = 0 the underlying is deterministic: it arrives at
    ``S*exp((r-q)*tau)`` with certainty, and an in-the-money option is a
    guaranteed claim on ``F - K``. ``price()`` implements exactly that. The
    Greeks of that deterministic claim are *not* all zero — it is a forward, and
    a forward has delta, rho and theta.
    """

    ITM_CALL: ClassVar[dict[str, float]] = {
        "spot": 120.0,
        "strike": 100.0,
        "rate": 0.05,
        "div_yield": 0.03,
        "vol": 0.0,
        "tau": 1.0,
    }

    def test_zero_vol_price_is_the_discounted_forward_intrinsic(self):
        expected = math.exp(-0.05) * (120.0 * math.exp(0.05 - 0.03) - 100.0)
        assert bs.price(**self.ITM_CALL, option_type=OptionType.CALL) == pytest.approx(
            expected, rel=1e-12
        )

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "greeks() collapses every sensitivity to zero whenever vol <= MIN_VOL, but that "
            "limit only holds at tau = 0. With tau > 0 and zero vol the option is a forward: "
            "delta is exp(-q*tau), not 1, and rho and theta are non-zero. price() gets this "
            "right, so greeks() contradicts the pricer it accompanies."
        ),
    )
    def test_zero_vol_greeks_are_those_of_a_forward(self):
        """A certain in-the-money call is ``e^(-q*tau)`` shares less a bond.

        Its delta is therefore ``e^(-q*tau)`` (the shares you must hold to
        deliver one at expiry), and its rho is the sensitivity of the borrowed
        strike, ``K*tau*e^(-r*tau)``, reported per 1% of rate. Both follow from
        the deterministic payoff with no volatility anywhere in sight.
        """
        tau, rate, div_yield, strike = 1.0, 0.05, 0.03, 100.0
        g = bs.greeks(**self.ITM_CALL, option_type=OptionType.CALL)

        assert g.delta == pytest.approx(math.exp(-div_yield * tau), rel=1e-9)
        assert g.rho == pytest.approx(strike * tau * math.exp(-rate * tau) / 100.0, rel=1e-9)
        assert g.theta != 0.0

    def test_the_limit_from_above_disagrees_with_the_value_at_zero(self):
        """The discontinuity, stated without reference to what is correct.

        Approaching zero vol the Greeks tend to the forward's; at exactly zero
        they jump to the expiry-day collapse. One of the two is wrong, and it
        is not the limit.
        """
        near = bs.greeks(**{**self.ITM_CALL, "vol": 1e-8}, option_type=OptionType.CALL)
        at_zero = bs.greeks(**self.ITM_CALL, option_type=OptionType.CALL)

        assert near.delta == pytest.approx(math.exp(-0.03), rel=1e-9)
        assert near.rho == pytest.approx(100.0 * math.exp(-0.05) / 100.0, rel=1e-9)
        assert at_zero.delta != pytest.approx(near.delta, rel=1e-6)
        assert at_zero.rho != pytest.approx(near.rho, rel=1e-6)

    @pytest.mark.parametrize("opt", TYPES)
    def test_expiry_day_collapse_is_correct(self, opt):
        """At tau = 0 the collapse *is* right: nothing is left to be sensitive to."""
        g = bs.greeks(
            spot=120.0, strike=100.0, rate=0.05, div_yield=0.03, vol=0.2, tau=0.0, option_type=opt
        )
        assert (g.gamma, g.vega, g.theta, g.rho, g.vanna, g.volga) == (0.0,) * 6
        assert g.delta == (1.0 if opt is OptionType.CALL else 0.0)
