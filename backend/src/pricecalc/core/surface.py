"""A volatility surface: implied vol as a function of strike and expiry.

The arbitrage scanner works on a chain of quotes; a market maker needs
something continuous, because it must price a strike nobody has quoted yet.
This module supplies that.

Parameterisation is in **total variance** ``w = sigma^2 * tau`` against
log-moneyness ``k = ln(K/F)``, not in vol against strike. Two reasons:

* Total variance is the quantity that must be non-decreasing in maturity for
  the surface to be free of calendar arbitrage, so stating the model in those
  terms makes that condition checkable rather than hopeful.
* The smile flattens with maturity roughly as ``1/sqrt(tau)`` in vol terms,
  which is awkward to write directly but falls out naturally here.

The surface is *not* guaranteed arbitrage-free for every parameter set — an
arbitrary smile never is. `is_butterfly_arbitrage_free` checks the condition
that matters (Durrleman's, in its g-function form) so a caller can tell rather
than assume.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from itertools import pairwise

MIN_VOL = 0.005
MIN_TAU = 1e-9


@dataclass(frozen=True, slots=True)
class VolSurface:
    """Skewed, convex smile with a term structure.

    Attributes:
        atm_vol: At-the-money-forward volatility at ``ref_tau``.
        skew: Slope in log-moneyness. Negative for equities, where one-sided
            demand for crash protection bids up downside strikes.
        curvature: Convexity; lifts both wings relative to the money.
        term_slope: Drift in ATM vol per year. Positive means an upward-sloping
            term structure, the usual shape in a calm market.
        smile_decay: How fast skew and curvature flatten with maturity. Longer
            horizons aggregate more independent returns, so the distribution
            tends toward normal and the smile washes out.
        ref_tau: Maturity at which ``atm_vol`` is quoted.
    """

    atm_vol: float = 0.20
    skew: float = -0.12
    curvature: float = 0.40
    term_slope: float = 0.02
    smile_decay: float = 0.35
    ref_tau: float = 0.25

    def atm(self, tau: float) -> float:
        """At-the-money-forward vol at a given maturity."""
        return max(MIN_VOL, self.atm_vol + self.term_slope * (tau - self.ref_tau))

    def vol(self, log_moneyness: float, tau: float) -> float:
        """Implied vol at log-moneyness ``k = ln(K/F)`` and maturity ``tau``."""
        damp = 1.0 / (1.0 + self.smile_decay * math.sqrt(max(tau, MIN_TAU)))
        k = log_moneyness
        return max(MIN_VOL, self.atm(tau) + damp * (self.skew * k + self.curvature * k * k))

    def vol_for_strike(self, strike: float, forward: float, tau: float) -> float:
        if strike <= 0.0 or forward <= 0.0:
            raise ValueError("strike and forward must be positive")
        return self.vol(math.log(strike / forward), tau)

    def total_variance(self, log_moneyness: float, tau: float) -> float:
        """w = sigma^2 * tau — the quantity calendar arbitrage is stated in."""
        v = self.vol(log_moneyness, tau)
        return v * v * tau

    def is_calendar_arbitrage_free(self, log_moneyness: float, taus: tuple[float, ...]) -> bool:
        """Total variance must not decrease with maturity at fixed moneyness.

        Buying more time cannot buy less uncertainty. Violate this and a
        calendar spread is free money.
        """
        variances = [self.total_variance(log_moneyness, t) for t in sorted(taus)]
        return all(b >= a - 1e-12 for a, b in pairwise(variances))

    def is_butterfly_arbitrage_free(
        self, tau: float, k_lo: float = -1.5, k_hi: float = 1.5
    ) -> bool:
        """Durrleman's condition: the risk-neutral density stays non-negative.

        Convexity of price in strike is equivalent to a non-negative implied
        density, and for a smile written in total variance that is the
        ``g(k) >= 0`` condition below. A steep enough wing violates it, which is
        the analytic statement of the bug property-testing found in the chain
        generator: an arbitrary smile is not arbitrage-free.

        Evaluated on a grid rather than solved, since the smile has no closed
        form for the roots of g.
        """
        steps = 200
        for i in range(steps + 1):
            k = k_lo + (k_hi - k_lo) * i / steps
            if self._durrleman_g(k, tau) < -1e-9:
                return False
        return True

    def _durrleman_g(self, k: float, tau: float) -> float:
        h = 1e-4
        w = self.total_variance(k, tau)
        if w <= 0.0:
            return 1.0
        w_up = self.total_variance(k + h, tau)
        w_dn = self.total_variance(k - h, tau)
        dw = (w_up - w_dn) / (2.0 * h)
        d2w = (w_up - 2.0 * w + w_dn) / (h * h)

        term = 1.0 - k * dw / (2.0 * w)
        return term * term - 0.25 * dw * dw * (0.25 + 1.0 / w) + 0.5 * d2w
