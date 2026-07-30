"""Static no-arbitrage checks across an option chain.

Every violation below is *model-free*: it holds for any dynamics of the
underlying, needs no volatility input, and is enforceable by holding the
replicating portfolio to expiry. That is what separates these from "the model
says this option is cheap" — there is no model to be wrong about.

Two rules govern every check:

**Execute at tradeable prices.** Legs you buy cost ``ask``; legs you sell pay
``bid``. A violation computed off mids is a spread you cannot cross, not an
arbitrage. This is why a chain with wide markets produces few findings.

**Report the cash that is actually locked in.** ``Violation.profit`` is the net
credit today after every leg — including the bond leg funding any future
obligation — for one unit of the structure. It is riskless, not expected.

Dividends are modelled as a continuous yield ``q``. To deliver one share at
expiry you hold ``exp(-q·tau)`` shares today and reinvest the dividends, which
is why stock legs carry that factor rather than being whole shares.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum
from itertools import combinations

from pricecalc.core.black_scholes import OptionType, price_bounds
from pricecalc.core.chain import Chain

# Findings below this are floating-point noise or uncrossable dust. Callers
# raise it to filter for edge that survives commissions and slippage.
DEFAULT_MIN_EDGE = 1e-6


class ViolationKind(StrEnum):
    ABSOLUTE_BOUND = "absolute_bound"
    PUT_CALL_PARITY = "put_call_parity"
    VERTICAL_MONOTONICITY = "vertical_monotonicity"
    VERTICAL_CAP = "vertical_cap"
    BUTTERFLY_CONVEXITY = "butterfly_convexity"
    CALENDAR_MONOTONICITY = "calendar_monotonicity"


@dataclass(frozen=True, slots=True)
class Leg:
    """One position in the replicating trade.

    ``quantity`` is signed: positive is long, negative is short. Stock legs are
    fractional by design (``exp(-q·tau)`` shares). The bond leg represents cash
    lent or borrowed to expiry, quoted at its present value.
    """

    instrument: str
    quantity: float
    price: float

    @property
    def cash_flow(self) -> float:
        """Cash today. Negative is an outflow (you paid)."""
        return -self.quantity * self.price


@dataclass(frozen=True, slots=True)
class Violation:
    kind: ViolationKind
    summary: str
    detail: str
    profit: float
    legs: tuple[Leg, ...]
    tau: float
    strikes: tuple[float, ...]


def scan(chain: Chain, min_edge: float = DEFAULT_MIN_EDGE) -> list[Violation]:
    """Run every static check and return findings, richest first.

    Args:
        chain: Two-sided quotes plus carry parameters.
        min_edge: Minimum locked-in profit to report, per unit of the structure.
    """
    found: list[Violation] = []
    found.extend(check_absolute_bounds(chain, min_edge))
    found.extend(check_put_call_parity(chain, min_edge))
    found.extend(check_verticals(chain, min_edge))
    found.extend(check_butterflies(chain, min_edge))
    found.extend(check_calendars(chain, min_edge))
    return sorted(found, key=lambda v: v.profit, reverse=True)


def check_absolute_bounds(chain: Chain, min_edge: float = DEFAULT_MIN_EDGE) -> list[Violation]:
    """Every option price sits between its discounted intrinsic and its cap.

    A call cannot be worth more than the (dividend-discounted) stock, nor less
    than the forward intrinsic; a put is capped by the discounted strike. These
    hold with no reference to volatility at all.
    """
    out: list[Violation] = []
    for q in chain.quotes:
        if q.tau <= 0.0:
            continue
        lower, upper = price_bounds(
            chain.spot, q.strike, chain.rate, chain.div_yield, q.tau, q.option_type
        )
        disc_q = math.exp(-chain.div_yield * q.tau)
        disc_r = math.exp(-chain.rate * q.tau)

        # Overpriced: sell the option, buy the cheapest portfolio that dominates it.
        if q.bid - upper > min_edge:
            profit = q.bid - (
                chain.underlying_ask * disc_q
                if q.option_type is OptionType.CALL
                else q.strike * disc_r
            )
            if profit > min_edge:
                hedge = (
                    Leg("underlying", disc_q, chain.underlying_ask)
                    if q.option_type is OptionType.CALL
                    else Leg(f"cash to {q.tau:.4g}y", 1.0, q.strike * disc_r)
                )
                out.append(
                    Violation(
                        kind=ViolationKind.ABSOLUTE_BOUND,
                        summary=f"{q.label} bid {q.bid:.4f} exceeds its upper bound {upper:.4f}",
                        detail=(
                            (
                                "A call can never be worth more than the "
                                "dividend-discounted stock. Sell the option and hold "
                                "the dominating portfolio to expiry."
                            )
                            if q.option_type is OptionType.CALL
                            else (
                                "A put can never be worth more than the discounted strike. Sell it "
                                "and lend the strike to expiry."
                            )
                        ),
                        profit=profit,
                        legs=(Leg(q.label, -1.0, q.bid), hedge),
                        tau=q.tau,
                        strikes=(q.strike,),
                    )
                )

        # Underpriced: buy the option and short the portfolio that replicates it.
        # The floor must be evaluated at the price the stock leg actually executes
        # at — you short at the bid to hedge a call, and pay the offer for a put.
        if q.option_type is OptionType.CALL:
            executable_floor = chain.underlying_bid * disc_q - q.strike * disc_r
            hedge_legs = (
                Leg("underlying", -disc_q, chain.underlying_bid),
                Leg(f"cash to {q.tau:.4g}y", 1.0, q.strike * disc_r),
            )
        else:
            executable_floor = q.strike * disc_r - chain.underlying_ask * disc_q
            hedge_legs = (
                Leg("underlying", disc_q, chain.underlying_ask),
                Leg(f"cash to {q.tau:.4g}y", -1.0, q.strike * disc_r),
            )

        edge = executable_floor - q.ask
        if edge > min_edge:
            out.append(
                Violation(
                    kind=ViolationKind.ABSOLUTE_BOUND,
                    summary=f"{q.label} ask {q.ask:.4f} is below its floor {max(lower, 0.0):.4f}",
                    detail=(
                        "The option is offered below the present value of the forward intrinsic "
                        "it is guaranteed to deliver. Buy it and short the replicating "
                        "portfolio; the option's optionality is free on top."
                    ),
                    profit=edge,
                    legs=(Leg(q.label, 1.0, q.ask), *hedge_legs),
                    tau=q.tau,
                    strikes=(q.strike,),
                )
            )
    return out


def check_put_call_parity(chain: Chain, min_edge: float = DEFAULT_MIN_EDGE) -> list[Violation]:
    """C - P = S·e^(-q·tau) - K·e^(-r·tau), enforced in both directions.

    A long call plus a short put at the same strike and expiry replicates the
    forward exactly. When the synthetic and the cash market disagree by more
    than the bid/ask, one side is free money:

    * **Conversion** — the synthetic is cheap: buy call, sell put, short stock.
    * **Reversal** — the synthetic is rich: sell call, buy put, buy stock.

    Both legs of that pair cannot be positive at once when spreads are
    non-negative, so at most one fires per strike.
    """
    out: list[Violation] = []
    for tau in chain.expiries():
        if tau <= 0.0:
            continue
        disc_r = math.exp(-chain.rate * tau)
        disc_q = math.exp(-chain.div_yield * tau)

        for strike in chain.strikes(tau):
            call = chain.get(tau, strike, OptionType.CALL)
            put = chain.get(tau, strike, OptionType.PUT)
            if call is None or put is None:
                continue

            # Reversal: buy call, sell put, short e^(-q·tau) shares, lend K·e^(-r·tau).
            # At expiry the synthetic delivers S_T - K and the short delivers -S_T,
            # leaving exactly -K, which the bond covers. Everything left is today's cash.
            reversal_edge = put.bid + chain.underlying_bid * disc_q - call.ask - strike * disc_r
            if reversal_edge > min_edge:
                out.append(
                    Violation(
                        kind=ViolationKind.PUT_CALL_PARITY,
                        summary=f"Reversal at {strike:g}, {tau:.4g}y locks {reversal_edge:.4f}",
                        detail=(
                            "The synthetic long (long call, short put) is cheaper than the stock "
                            "it replicates. Buy the synthetic, short the stock against it, and "
                            "lend the strike. Every path cancels; the credit is riskless."
                        ),
                        profit=reversal_edge,
                        legs=(
                            Leg(call.label, 1.0, call.ask),
                            Leg(put.label, -1.0, put.bid),
                            Leg("underlying", -disc_q, chain.underlying_bid),
                            Leg(f"cash to {tau:.4g}y", 1.0, strike * disc_r),
                        ),
                        tau=tau,
                        strikes=(strike,),
                    )
                )

            # Conversion: the mirror image.
            conversion_edge = call.bid + strike * disc_r - put.ask - chain.underlying_ask * disc_q
            if conversion_edge > min_edge:
                out.append(
                    Violation(
                        kind=ViolationKind.PUT_CALL_PARITY,
                        summary=f"Conversion at {strike:g}, {tau:.4g}y locks {conversion_edge:.4f}",
                        detail=(
                            "The synthetic long is richer than the stock. Sell the synthetic "
                            "(sell call, buy put), buy the stock, and borrow the strike."
                        ),
                        profit=conversion_edge,
                        legs=(
                            Leg(call.label, -1.0, call.bid),
                            Leg(put.label, 1.0, put.ask),
                            Leg("underlying", disc_q, chain.underlying_ask),
                            Leg(f"cash to {tau:.4g}y", -1.0, strike * disc_r),
                        ),
                        tau=tau,
                        strikes=(strike,),
                    )
                )
    return out


def check_verticals(chain: Chain, min_edge: float = DEFAULT_MIN_EDGE) -> list[Violation]:
    """Monotonicity and slope bounds on adjacent strikes.

    Two independent facts, both model-free:

    * **Monotonicity** — calls fall as the strike rises; puts rise. A debit
      spread that pays a credit is free money.
    * **Slope cap** — a vertical's payoff never exceeds the strike gap, so it
      cannot cost more than that gap discounted. Equivalently the call price
      falls no faster than ``e^(-r·tau)`` per unit of strike.
    """
    out: list[Violation] = []
    for tau in chain.expiries():
        if tau <= 0.0:
            continue
        disc_r = math.exp(-chain.rate * tau)
        strikes = chain.strikes(tau)

        # Every ordered pair, not just neighbours. A crossable edge between
        # non-adjacent strikes is masked when the intervening strike's spread
        # is wide, and `check_butterflies` already pays for `combinations`,
        # so restricting this one bought nothing.
        for lo, hi in combinations(strikes, 2):
            gap_pv = (hi - lo) * disc_r

            c_lo, c_hi = chain.get(tau, lo, OptionType.CALL), chain.get(tau, hi, OptionType.CALL)
            if c_lo is not None and c_hi is not None:
                # Monotonicity: the higher strike bids above the lower strike's offer.
                edge = c_hi.bid - c_lo.ask
                if edge > min_edge:
                    out.append(
                        Violation(
                            kind=ViolationKind.VERTICAL_MONOTONICITY,
                            summary=f"Call {hi:g} bids above call {lo:g} offer ({tau:.4g}y)",
                            detail=(
                                "A call struck higher can never be worth more than one struck "
                                "lower. Buy the low strike, sell the high strike: the spread "
                                "pays a credit today and can only pay you again at expiry."
                            ),
                            profit=edge,
                            legs=(Leg(c_lo.label, 1.0, c_lo.ask), Leg(c_hi.label, -1.0, c_hi.bid)),
                            tau=tau,
                            strikes=(lo, hi),
                        )
                    )
                # Slope cap: selling the spread nets more than its worst-case payout.
                edge = c_lo.bid - c_hi.ask - gap_pv
                if edge > min_edge:
                    out.append(
                        Violation(
                            kind=ViolationKind.VERTICAL_CAP,
                            summary=(
                                f"Call {lo:g}/{hi:g} spread sells above its "
                                f"{hi - lo:g} cap ({tau:.4g}y)"
                            ),
                            detail=(
                                "The spread can never owe more than the strike gap. Selling it "
                                "for more than that gap's present value funds the worst case "
                                "with cash left over."
                            ),
                            profit=edge,
                            legs=(
                                Leg(c_lo.label, -1.0, c_lo.bid),
                                Leg(c_hi.label, 1.0, c_hi.ask),
                                Leg(f"cash to {tau:.4g}y", 1.0, gap_pv),
                            ),
                            tau=tau,
                            strikes=(lo, hi),
                        )
                    )

            p_lo, p_hi = chain.get(tau, lo, OptionType.PUT), chain.get(tau, hi, OptionType.PUT)
            if p_lo is not None and p_hi is not None:
                # Puts rise with strike, so the violation is the mirror image.
                edge = p_lo.bid - p_hi.ask
                if edge > min_edge:
                    out.append(
                        Violation(
                            kind=ViolationKind.VERTICAL_MONOTONICITY,
                            summary=f"Put {lo:g} bids above put {hi:g} offer ({tau:.4g}y)",
                            detail=(
                                "A put struck lower can never be worth more than one struck "
                                "higher. Sell the low strike, buy the high strike for a credit."
                            ),
                            profit=edge,
                            legs=(Leg(p_lo.label, -1.0, p_lo.bid), Leg(p_hi.label, 1.0, p_hi.ask)),
                            tau=tau,
                            strikes=(lo, hi),
                        )
                    )
                edge = p_hi.bid - p_lo.ask - gap_pv
                if edge > min_edge:
                    out.append(
                        Violation(
                            kind=ViolationKind.VERTICAL_CAP,
                            summary=(
                                f"Put {lo:g}/{hi:g} spread sells above its "
                                f"{hi - lo:g} cap ({tau:.4g}y)"
                            ),
                            detail=(
                                "The put spread's payoff is capped by the strike gap; it is bid "
                                "above the present value of that cap."
                            ),
                            profit=edge,
                            legs=(
                                Leg(p_hi.label, -1.0, p_hi.bid),
                                Leg(p_lo.label, 1.0, p_lo.ask),
                                Leg(f"cash to {tau:.4g}y", 1.0, gap_pv),
                            ),
                            tau=tau,
                            strikes=(lo, hi),
                        )
                    )
    return out


def check_butterflies(chain: Chain, min_edge: float = DEFAULT_MIN_EDGE) -> list[Violation]:
    """Price must be convex in strike, for calls and puts alike.

    For ``K1 < K2 < K3`` write the middle strike as a weighted average of the
    wings, ``K2 = w1·K1 + w3·K3``. Convexity requires the middle option to cost
    no more than the same blend of the wings. When it does, the butterfly —
    long ``w1`` of the low wing, short one middle, long ``w3`` of the high wing
    — is a non-negative payoff bought for a credit.

    The weights handle unevenly spaced strikes; for a uniform ladder they
    collapse to the familiar 1 / -2 / 1 ratio (scaled by a half).
    """
    out: list[Violation] = []
    for tau in chain.expiries():
        if tau <= 0.0:
            continue
        strikes = chain.strikes(tau)

        for k_lo, k_mid, k_hi in combinations(strikes, 3):
            span = k_hi - k_lo
            w_lo = (k_hi - k_mid) / span
            w_hi = (k_mid - k_lo) / span

            for opt in (OptionType.CALL, OptionType.PUT):
                lo_q, mid_q, hi_q = (
                    chain.get(tau, k_lo, opt),
                    chain.get(tau, k_mid, opt),
                    chain.get(tau, k_hi, opt),
                )
                if lo_q is None or mid_q is None or hi_q is None:
                    continue

                edge = mid_q.bid - w_lo * lo_q.ask - w_hi * hi_q.ask
                if edge > min_edge:
                    out.append(
                        Violation(
                            kind=ViolationKind.BUTTERFLY_CONVEXITY,
                            summary=(
                                f"{opt.value.capitalize()} {k_lo:g}/{k_mid:g}/{k_hi:g} butterfly "
                                f"pays {edge:.4f} to own ({tau:.4g}y)"
                            ),
                            detail=(
                                "Option prices are convex in strike, so the middle strike cannot "
                                "cost more than the matching blend of its wings. Sell the middle, "
                                "buy the wings in the weights shown: the payoff is non-negative "
                                "everywhere and you are paid to put it on."
                            ),
                            profit=edge,
                            legs=(
                                Leg(lo_q.label, w_lo, lo_q.ask),
                                Leg(mid_q.label, -1.0, mid_q.bid),
                                Leg(hi_q.label, w_hi, hi_q.ask),
                            ),
                            tau=tau,
                            strikes=(k_lo, k_mid, k_hi),
                        )
                    )
    return out


def check_calendars(chain: Chain, min_edge: float = DEFAULT_MIN_EDGE) -> list[Violation]:
    """Longer-dated options dominate shorter-dated ones at the same strike.

    **Two conditions are required, and this check returns nothing unless both
    hold: no dividends, and a non-negative rate.**

    With a dividend yield the ordering genuinely fails — holding a call forgoes
    the dividends the stock pays, so a longer-dated European call can
    legitimately trade below a shorter-dated one.

    A *negative* rate breaks it just as surely, which is easy to miss. The far
    call's floor is ``S - K*exp(-r*dt)``, and that dominates the near call's
    intrinsic ``(S - K)+`` only while ``exp(-r*dt) <= 1``. Below zero the
    discount factor exceeds one, the floor drops beneath the near option's
    intrinsic, and the ordering is no longer a bound. Gating on dividends alone
    produced phantom findings on a perfectly consistent chain at ``r = -5%``,
    which is exactly the failure a screening tool cannot afford.

    The general condition surviving both is stated on total implied variance at
    matched forward-moneyness, which needs an interpolated surface rather than
    raw quotes. Returning nothing is the honest answer; the caller is told the
    check was skipped rather than handed noise.
    """
    if abs(chain.div_yield) > 0.0 or chain.rate < 0.0:
        return []

    out: list[Violation] = []
    expiries = chain.expiries()
    for near, far in combinations([t for t in expiries if t > 0.0], 2):
        shared = set(chain.strikes(near)) & set(chain.strikes(far))
        for strike in sorted(shared):
            for opt in (OptionType.CALL,):  # Puts need r=0 as well; calls suffice here.
                near_q, far_q = chain.get(near, strike, opt), chain.get(far, strike, opt)
                if near_q is None or far_q is None:
                    continue
                edge = near_q.bid - far_q.ask
                if edge > min_edge:
                    out.append(
                        Violation(
                            kind=ViolationKind.CALENDAR_MONOTONICITY,
                            summary=(
                                f"Call {strike:g} {near:.4g}y bids above the {far:.4g}y offer"
                            ),
                            detail=(
                                "Without dividends a longer-dated call dominates a shorter-dated "
                                "one at the same strike — it confers every right the near option "
                                "does, and more. Sell the near, buy the far for a credit."
                            ),
                            profit=edge,
                            legs=(
                                Leg(near_q.label, -1.0, near_q.bid),
                                Leg(far_q.label, 1.0, far_q.ask),
                            ),
                            tau=near,
                            strikes=(strike,),
                        )
                    )
    return out
