"""Where the static checks hold, and where they are being applied anyway.

A screening tool's false positives cost more than its misses: a miss is edge
someone else takes, a false positive is a trade that loses money. Each test
below either builds a chain that is provably arbitrage-free and demands silence,
or builds a genuine, crossable arbitrage and demands it is seen.

Chains here are priced off a *flat* volatility so that no smile can be blamed
for a finding. With one vol for every strike and expiry the surface is a
textbook Black-Scholes surface, which satisfies every static bound in the module
by construction.
"""

from __future__ import annotations

import math

import pytest

from pricecalc.core import arbitrage
from pricecalc.core.arbitrage import ViolationKind
from pricecalc.core.black_scholes import OptionType, price
from pricecalc.core.chain import Chain, Quote

FLAT_VOL = 0.20
STRIKES = (70.0, 85.0, 100.0, 115.0, 130.0)
EXPIRIES = (0.25, 2.0)


def flat_chain(spot: float, rate: float, div_yield: float, half_spread: float = 0.001) -> Chain:
    """A Black-Scholes chain at one volatility — arbitrage-free by construction."""
    quotes = tuple(
        Quote(
            tau=tau,
            strike=strike,
            option_type=opt,
            bid=max(0.0, price(spot, strike, rate, div_yield, FLAT_VOL, tau, opt) - half_spread),
            ask=price(spot, strike, rate, div_yield, FLAT_VOL, tau, opt) + half_spread,
        )
        for tau in EXPIRIES
        for strike in STRIKES
        for opt in (OptionType.CALL, OptionType.PUT)
    )
    return Chain(spot=spot, rate=rate, div_yield=div_yield, quotes=quotes)


class TestCalendarDomain:
    """``C(T_far) >= C(T_near)`` needs a non-negative rate as well as no dividend.

    The proof is that at the near expiry the far call is still worth at least
    ``S - K*exp(-r*dt)``, which dominates the near call's payoff ``(S - K)+``
    only when ``exp(-r*dt) <= 1``. A negative rate reverses that inequality: the
    strike you will pay later grows rather than shrinks in present value, and a
    longer-dated call can legitimately be worth less.
    """

    def test_positive_rate_chain_is_silent(self):
        assert arbitrage.check_calendars(flat_chain(100.0, 0.05, 0.0)) == []

    def test_zero_rate_chain_is_silent(self):
        assert arbitrage.check_calendars(flat_chain(100.0, 0.0, 0.0)) == []

    def test_a_dividend_yield_skips_the_check(self):
        assert arbitrage.check_calendars(flat_chain(100.0, 0.05, 0.03)) == []

    def test_the_negative_rate_ordering_is_genuinely_reversed(self):
        """Not a quote artefact: the model prices the far call below the near one.

        Both prices sit strictly inside their own no-arbitrage bands, so neither
        is a mispricing — the ordering the calendar check assumes simply does
        not hold at a negative rate.
        """
        near = price(100.0, 70.0, -0.05, 0.0, FLAT_VOL, 0.25, OptionType.CALL)
        far = price(100.0, 70.0, -0.05, 0.0, FLAT_VOL, 2.0, OptionType.CALL)
        assert far < near

        for tau, px in ((0.25, near), (2.0, far)):
            lower, upper = arbitrage.price_bounds(100.0, 70.0, -0.05, 0.0, tau, OptionType.CALL)
            assert lower < px < upper

    def test_the_proposed_calendar_trade_loses_money(self):
        """Sell the near, buy the far: assigned deep in the money, you are short.

        The far call cannot cover the near call's assignment, because the strike
        it lets you pay later is worth *more* in present value at a negative
        rate. The shortfall exceeds the credit taken in.
        """
        credit = price(100.0, 70.0, -0.05, 0.0, FLAT_VOL, 0.25, OptionType.CALL) - price(
            100.0, 70.0, -0.05, 0.0, FLAT_VOL, 2.0, OptionType.CALL
        )
        assert credit > 0.0

        terminal_spot = 400.0
        remaining = 2.0 - 0.25
        assigned = -max(terminal_spot - 70.0, 0.0)
        far_mark = price(terminal_spot, 70.0, -0.05, 0.0, FLAT_VOL, remaining, OptionType.CALL)
        assert assigned + far_mark + credit < 0.0

    def test_negative_rate_chain_is_silent(self):
        assert arbitrage.check_calendars(flat_chain(100.0, -0.05, 0.0)) == []

    def test_a_clean_negative_rate_chain_produces_no_findings_at_all(self):
        assert arbitrage.scan(flat_chain(100.0, -0.05, 0.0)) == []


class TestVerticalCoverage:
    """Monotonicity in strike holds between *any* two strikes, not just neighbours.

    ``check_verticals`` walks adjacent pairs only. Because each comparison has
    to cross a bid/ask spread, a violation can hide in a non-adjacent pair while
    every adjacent pair looks clean — the spreads of the strike in between
    absorb it. The butterfly check already pays for ``combinations``, so the
    asymmetry is not a deliberate cost trade-off.
    """

    WIDE_MIDDLE = (
        Quote(tau=1.0, strike=100.0, option_type=OptionType.CALL, bid=0.5, ask=1.0),
        Quote(tau=1.0, strike=110.0, option_type=OptionType.CALL, bid=1.0, ask=3.0),
        Quote(tau=1.0, strike=120.0, option_type=OptionType.CALL, bid=2.0, ask=2.5),
    )

    def test_the_non_adjacent_pair_is_a_real_crossable_arbitrage(self):
        """Buy the 100 call at 1.00, sell the 120 call at 2.00 for a 1.00 credit.

        The spread's payoff is non-negative for every terminal spot, so the
        credit is locked in. Both fills are at the quoted side, not the mid.
        """
        credit = 2.0 - 1.0
        assert credit > 0.0
        for terminal_spot in (0.0, 100.0, 110.0, 120.0, 500.0):
            payoff = max(terminal_spot - 100.0, 0.0) - max(terminal_spot - 120.0, 0.0)
            assert payoff >= 0.0

    def test_adjacent_pairs_are_individually_clean(self):
        """Nothing is wrong between 100/110 or between 110/120 — the middle
        strike's own spread is what hides the violation."""
        assert 1.0 - 1.0 <= 0.0  # call 110 bid vs call 100 ask
        assert 2.0 - 3.0 <= 0.0  # call 120 bid vs call 110 ask

    def test_the_scanner_finds_it(self):
        chain = Chain(spot=100.0, rate=0.0, div_yield=0.0, quotes=self.WIDE_MIDDLE)
        found = arbitrage.check_verticals(chain)
        assert any(v.kind is ViolationKind.VERTICAL_MONOTONICITY for v in found)


class TestReplicatingTradeDerivations:
    """Each leg must be the position the argument actually requires.

    Checking ``sum(cash_flow) == profit`` only proves the arithmetic closes; it
    would still close if the stock leg were whole shares instead of
    ``exp(-q*tau)``, or if the bond were borrowed when it should be lent. These
    tests settle the trade at expiry and demand a non-negative result on every
    path, which is what makes it an arbitrage rather than a bet.
    """

    SPOT, RATE, DIV, TAU, STRIKE = 100.0, 0.05, 0.04, 1.0, 100.0

    def _settle(self, legs, terminal_spot: float) -> float:
        """Value the replicating trade at expiry, per unit of the structure."""
        total = 0.0
        for leg in legs:
            if leg.instrument == "underlying":
                # exp(-q*tau) shares held with dividends reinvested become
                # exactly one share at expiry.
                total += leg.quantity * math.exp(self.DIV * self.TAU) * terminal_spot
            elif leg.instrument.startswith("cash to"):
                total += leg.quantity * leg.price * math.exp(self.RATE * self.TAU)
            else:
                strike = float(leg.instrument.split()[1])
                sign = 1.0 if leg.instrument.endswith("call") else -1.0
                total += leg.quantity * max(sign * (terminal_spot - strike), 0.0)
        return total

    def _parity_chain(self, call_bid_bump: float) -> Chain:
        call_mid = price(
            self.SPOT, self.STRIKE, self.RATE, self.DIV, 0.2, self.TAU, OptionType.CALL
        )
        put_mid = price(self.SPOT, self.STRIKE, self.RATE, self.DIV, 0.2, self.TAU, OptionType.PUT)
        return Chain(
            spot=self.SPOT,
            rate=self.RATE,
            div_yield=self.DIV,
            quotes=(
                Quote(
                    tau=self.TAU,
                    strike=self.STRIKE,
                    option_type=OptionType.CALL,
                    bid=call_mid + call_bid_bump,
                    ask=call_mid + call_bid_bump + 0.01,
                ),
                Quote(
                    tau=self.TAU,
                    strike=self.STRIKE,
                    option_type=OptionType.PUT,
                    bid=put_mid - 0.01,
                    ask=put_mid,
                ),
            ),
        )

    def test_a_rich_synthetic_is_flat_at_expiry_and_paid_today(self):
        """Sell call, buy put, buy exp(-q*tau) shares, borrow the strike.

        The synthetic short and the long stock cancel exactly, whatever spot
        does, and the borrowed strike is repaid by the exercise. Every terminal
        spot must therefore settle to zero — the entire profit is the credit
        taken at inception.
        """
        found = arbitrage.check_put_call_parity(self._parity_chain(call_bid_bump=1.0))
        assert len(found) == 1
        violation = found[0]
        assert violation.profit > 0.0
        assert sum(leg.cash_flow for leg in violation.legs) == pytest.approx(violation.profit)

        for terminal_spot in (0.0, 50.0, 100.0, 150.0, 1000.0):
            assert self._settle(violation.legs, terminal_spot) == pytest.approx(0.0, abs=1e-9)

    def test_the_stock_leg_is_a_fractional_share(self):
        """``exp(-q*tau)`` shares, not one — dividends reinvested make up the rest.

        Using whole shares would over-hedge by the dividends collected, and the
        'arbitrage' would be short that amount.
        """
        violation = arbitrage.check_put_call_parity(self._parity_chain(call_bid_bump=1.0))[0]
        stock = next(leg for leg in violation.legs if leg.instrument == "underlying")
        assert abs(stock.quantity) == pytest.approx(math.exp(-self.DIV * self.TAU))
        assert abs(stock.quantity) < 1.0

    def test_a_rich_synthetic_buys_stock_at_the_offer(self):
        """You pay the offer for what you buy. Pricing the stock leg off the mid
        would invent edge equal to half the cash spread."""
        chain = Chain(
            spot=self.SPOT,
            rate=self.RATE,
            div_yield=self.DIV,
            underlying_bid=99.0,
            underlying_ask=101.0,
            quotes=self._parity_chain(call_bid_bump=3.0).quotes,
        )
        violation = arbitrage.check_put_call_parity(chain)[0]
        stock = next(leg for leg in violation.legs if leg.instrument == "underlying")
        assert stock.quantity > 0.0
        assert stock.price == 101.0

    def test_a_wide_cash_market_can_extinguish_the_finding(self):
        """The same option quotes stop being an arbitrage once the stock is wide.

        This is the whole reason legs carry a side: an edge of half a point
        vanishes when the stock costs two points to cross.
        """
        tight = self._parity_chain(call_bid_bump=0.5)
        assert arbitrage.check_put_call_parity(tight)

        wide = Chain(
            spot=self.SPOT,
            rate=self.RATE,
            div_yield=self.DIV,
            underlying_bid=98.0,
            underlying_ask=102.0,
            quotes=tight.quotes,
        )
        assert arbitrage.check_put_call_parity(wide) == []

    def test_an_overpriced_call_is_hedged_by_buying_the_stock_at_the_offer(self):
        """A call bid above the discounted stock: sell it, hold the dominating
        portfolio. The hedge must be bought, so it executes at the ask."""
        chain = Chain(
            spot=self.SPOT,
            rate=self.RATE,
            div_yield=self.DIV,
            underlying_bid=99.5,
            underlying_ask=100.5,
            quotes=(
                Quote(
                    tau=self.TAU,
                    strike=self.STRIKE,
                    option_type=OptionType.CALL,
                    bid=99.0,
                    ask=99.5,
                ),
            ),
        )
        found = [
            v
            for v in arbitrage.check_absolute_bounds(chain)
            if v.kind is ViolationKind.ABSOLUTE_BOUND
        ]
        assert found
        stock = next(leg for leg in found[0].legs if leg.instrument == "underlying")
        assert stock.quantity > 0.0
        assert stock.price == 100.5
        assert sum(leg.cash_flow for leg in found[0].legs) == pytest.approx(found[0].profit)

        # Whatever spot does, the portfolio covers the short call.
        for terminal_spot in (0.0, 100.0, 500.0):
            assert self._settle(found[0].legs, terminal_spot) >= -1e-9

    def test_a_cheap_call_is_hedged_by_shorting_the_stock_at_the_bid(self):
        """Buy the call below its floor: the hedge is sold, so it hits the bid,
        and the strike must be *lent* to expiry to fund the exercise."""
        chain = Chain(
            spot=self.SPOT,
            rate=self.RATE,
            div_yield=self.DIV,
            quotes=(
                Quote(tau=self.TAU, strike=50.0, option_type=OptionType.CALL, bid=0.5, ask=1.0),
            ),
        )
        found = arbitrage.check_absolute_bounds(chain)
        assert found
        stock = next(leg for leg in found[0].legs if leg.instrument == "underlying")
        bond = next(leg for leg in found[0].legs if leg.instrument.startswith("cash to"))
        assert stock.quantity < 0.0
        assert stock.price == self.SPOT  # underlying bid defaults to spot
        assert bond.quantity > 0.0  # lent, not borrowed
        assert bond.cash_flow < 0.0

        for terminal_spot in (0.0, 50.0, 500.0):
            assert self._settle(found[0].legs, 0.0) >= -1e-9
            assert self._settle(found[0].legs, terminal_spot) >= -1e-9


class TestButterflyWeights:
    """Unevenly spaced wings need weights that put the middle strike on the chord.

    ``w_lo*K1 + w_hi*K3 = K2`` with ``w_lo + w_hi = 1`` is what makes the
    butterfly's payoff non-negative everywhere; any other pair of weights leaves
    a wing that can go negative, and the 'arbitrage' becomes a directional bet.
    """

    @pytest.mark.parametrize(
        ("k_lo", "k_mid", "k_hi"),
        [(90.0, 100.0, 110.0), (90.0, 95.0, 120.0), (80.0, 115.0, 120.0)],
    )
    def test_the_butterfly_payoff_is_non_negative_at_every_terminal_spot(self, k_lo, k_mid, k_hi):
        chain = Chain(
            spot=100.0,
            rate=0.03,
            div_yield=0.0,
            quotes=tuple(
                Quote(
                    tau=1.0,
                    strike=k,
                    option_type=OptionType.CALL,
                    # Middle strike lifted well above the chord to force a finding.
                    bid=(30.0 if k == k_mid else 0.01),
                    ask=(30.5 if k == k_mid else 0.02),
                )
                for k in (k_lo, k_mid, k_hi)
            ),
        )
        found = arbitrage.check_butterflies(chain)
        assert found, "a concave middle strike must be reported"
        legs = found[0].legs

        quantities = {float(leg.instrument.split()[1]): leg.quantity for leg in legs}
        wings = {k: q for k, q in quantities.items() if k != k_mid}
        assert quantities[k_mid] == -1.0
        assert wings[k_lo] + wings[k_hi] == pytest.approx(1.0)
        assert wings[k_lo] * k_lo + wings[k_hi] * k_hi == pytest.approx(k_mid)

        for terminal_spot in (0.0, k_lo, k_mid, k_hi, 10_000.0):
            settled = sum(qty * max(terminal_spot - k, 0.0) for k, qty in quantities.items())
            assert settled >= -1e-9
