"""An independent oracle for the pricer: Monte Carlo under geometric Brownian motion.

Every other test in this suite is written against the same closed-form
implementation it is testing. Put-call parity, finite differences and the
textbook value all pin *relationships* between numbers the module produced
itself, so a formula that is subtly wrong in a way that respects those
relationships — a misplaced discount factor that cancels between the call and
the put, say — would satisfy all of them.

Simulating the risk-neutral terminal distribution shares no algebra with
Black-Scholes. Under the martingale measure ``S_T = S*exp((r - q - sigma^2/2)*tau
+ sigma*sqrt(tau)*Z)``, and the option is worth the discounted expected payoff.
If the analytic price lands inside the simulation's confidence interval, the two
independent derivations agree.

Estimators are seeded, so a failure here is a real disagreement, not a run of
bad luck. Antithetic sampling plus the discounted terminal spot as a control
variate (its expectation ``S*exp(-q*tau)`` is known exactly) buys roughly an
order of magnitude in accuracy for the same paths.
"""

from __future__ import annotations

import math
from typing import ClassVar

import numpy as np
import pytest

from pricecalc.core import black_scholes as bs
from pricecalc.core.black_scholes import OptionType

PATHS = 1_000_000
SEED = 20240101
# Five standard errors: with a fixed seed this is deterministic, and it leaves
# room for the estimator's own tiny bias without letting a real error through.
SIGMAS = 5.0

# Regimes chosen to exercise the parts of the formula that carry units: a
# dividend yield (the e^-q factor on the spot term), a negative rate (the sign
# of the discount), a very short expiry and a very long one.
REGIMES = [
    pytest.param(100.0, 100.0, 0.05, 0.00, 0.20, 1.00, id="atm-1y"),
    pytest.param(100.0, 130.0, 0.05, 0.00, 0.20, 0.50, id="otm-call"),
    pytest.param(100.0, 70.0, 0.03, 0.02, 0.35, 2.00, id="itm-call-with-dividend"),
    pytest.param(50.0, 52.5, 0.01, 0.00, 0.60, 0.05, id="short-dated-high-vol"),
    pytest.param(4200.0, 4000.0, 0.045, 0.015, 0.15, 0.25, id="index-scale"),
    pytest.param(100.0, 100.0, -0.02, 0.03, 0.30, 1.50, id="negative-rate"),
    pytest.param(100.0, 100.0, 0.04, 0.00, 0.20, 5.00, id="long-dated"),
]


def _terminal_spots(
    spot: float, rate: float, div_yield: float, vol: float, tau: float, seed: int
) -> np.ndarray:
    """Risk-neutral terminal spot under GBM, antithetically paired."""
    rng = np.random.default_rng(seed)
    z = rng.standard_normal(PATHS // 2)
    z = np.concatenate([z, -z])
    drift = (rate - div_yield - 0.5 * vol * vol) * tau
    return spot * np.exp(drift + vol * math.sqrt(tau) * z)


def mc_price(
    spot: float,
    strike: float,
    rate: float,
    div_yield: float,
    vol: float,
    tau: float,
    option_type: OptionType,
    seed: int = SEED,
) -> tuple[float, float]:
    """Discounted expected payoff and its standard error."""
    st = _terminal_spots(spot, rate, div_yield, vol, tau, seed)
    disc = math.exp(-rate * tau)
    phi = float(option_type.sign)
    payoff = disc * np.maximum(phi * (st - strike), 0.0)

    # Control variate: the discounted terminal spot must average to S*e^(-q*tau)
    # under the risk-neutral measure — that is the no-arbitrage forward, known
    # without reference to the option formula.
    control = disc * st
    beta = float(np.cov(payoff, control)[0, 1] / np.var(control))
    adjusted = payoff - beta * (control - spot * math.exp(-div_yield * tau))
    return float(adjusted.mean()), float(adjusted.std(ddof=1) / math.sqrt(len(adjusted)))


class TestPriceAgainstSimulation:
    @pytest.mark.parametrize(("spot", "strike", "rate", "div_yield", "vol", "tau"), REGIMES)
    @pytest.mark.parametrize("option_type", [OptionType.CALL, OptionType.PUT])
    def test_analytic_price_lands_inside_the_simulated_confidence_interval(
        self, spot, strike, rate, div_yield, vol, tau, option_type
    ):
        """Black-Scholes is the discounted risk-neutral expectation of the payoff.

        Simulating that expectation directly shares no algebra with the closed
        form, so agreement is evidence the formula itself is right rather than
        evidence that it is self-consistent.
        """
        analytic = bs.price(spot, strike, rate, div_yield, vol, tau, option_type)
        simulated, stderr = mc_price(spot, strike, rate, div_yield, vol, tau, option_type)
        assert abs(analytic - simulated) <= SIGMAS * stderr, (
            f"{option_type.value}: analytic {analytic:.6f} vs simulated "
            f"{simulated:.6f} +/- {stderr:.6f}"
        )

    def test_the_oracle_would_reject_a_wrong_price(self):
        """Guard the guard: the interval must be tight enough to catch a real error.

        A pricer that discounted the strike at the dividend yield instead of the
        rate is the classic transposed-argument bug. It must fall outside the
        band, otherwise passing the test above means nothing.
        """
        spot, strike, rate, div_yield, vol, tau = 100.0, 100.0, 0.05, 0.03, 0.20, 1.0
        simulated, stderr = mc_price(spot, strike, rate, div_yield, vol, tau, OptionType.CALL)

        d1, d2 = bs.d1_d2(spot, strike, rate, div_yield, vol, tau)
        wrong = spot * math.exp(-div_yield * tau) * bs.norm_cdf(d1) - strike * math.exp(
            -div_yield * tau
        ) * bs.norm_cdf(d2)
        assert abs(wrong - simulated) > SIGMAS * stderr


class TestGreeksAgainstSimulation:
    """Pathwise derivative estimators — an oracle for the *units*, not just the value.

    Differentiating the discounted payoff inside the expectation gives an
    unbiased estimator of the Greek that never touches the analytic formula.
    ``d(S_T)/dS = S_T/S`` and ``d(S_T)/dsigma = S_T*(sqrt(tau)*Z - sigma*tau)``,
    so delta and vega fall out of the same paths. Vega is the one worth
    simulating: it is the Greek whose reported value is rescaled, and a wrong
    scale factor is invisible to any test that compares two rescaled numbers.
    """

    CASES: ClassVar[list] = [
        pytest.param(100.0, 100.0, 0.05, 0.00, 0.20, 1.00, id="atm-1y"),
        pytest.param(100.0, 70.0, 0.03, 0.02, 0.35, 2.00, id="itm-with-dividend"),
        pytest.param(4200.0, 4000.0, 0.045, 0.015, 0.15, 0.25, id="index-scale"),
    ]

    @staticmethod
    def _pathwise(spot, strike, rate, div_yield, vol, tau, option_type, seed=4242):
        rng = np.random.default_rng(seed)
        z = rng.standard_normal(PATHS // 2)
        z = np.concatenate([z, -z])
        sqrt_t = math.sqrt(tau)
        st = spot * np.exp((rate - div_yield - 0.5 * vol * vol) * tau + vol * sqrt_t * z)
        disc = math.exp(-rate * tau)
        phi = float(option_type.sign)
        # The payoff is differentiable except on a null set, so the indicator is
        # all that survives of max(phi*(S_T - K), 0).
        exercised = (st > strike) if option_type is OptionType.CALL else (st < strike)
        d_spot = disc * phi * exercised * st / spot
        d_vol = disc * phi * exercised * st * (sqrt_t * z - vol * tau)
        n = len(st)
        return (
            float(d_spot.mean()),
            float(d_spot.std(ddof=1) / math.sqrt(n)),
            float(d_vol.mean()),
            float(d_vol.std(ddof=1) / math.sqrt(n)),
        )

    @pytest.mark.parametrize(("spot", "strike", "rate", "div_yield", "vol", "tau"), CASES)
    @pytest.mark.parametrize("option_type", [OptionType.CALL, OptionType.PUT])
    def test_delta_matches_the_pathwise_estimator(
        self, spot, strike, rate, div_yield, vol, tau, option_type
    ):
        """Delta is reported raw, per $1 of spot, so the simulated value is directly
        comparable with no rescaling in between."""
        analytic = bs.greeks(spot, strike, rate, div_yield, vol, tau, option_type).delta
        mean, stderr, _, _ = self._pathwise(spot, strike, rate, div_yield, vol, tau, option_type)
        assert abs(analytic - mean) <= SIGMAS * stderr

    @pytest.mark.parametrize(("spot", "strike", "rate", "div_yield", "vol", "tau"), CASES)
    @pytest.mark.parametrize("option_type", [OptionType.CALL, OptionType.PUT])
    def test_vega_is_reported_per_vol_point(
        self, spot, strike, rate, div_yield, vol, tau, option_type
    ):
        """A vol point is 0.01 of decimal volatility, so the reported number is
        the raw derivative divided by 100.

        The simulation produces dV/dsigma in decimal terms with no knowledge of
        the reporting convention, which is what makes it a real check on the
        scale factor rather than on the derivative alone.
        """
        analytic = bs.greeks(spot, strike, rate, div_yield, vol, tau, option_type).vega
        _, _, mean, stderr = self._pathwise(spot, strike, rate, div_yield, vol, tau, option_type)
        assert abs(analytic - mean / 100.0) <= SIGMAS * stderr / 100.0
