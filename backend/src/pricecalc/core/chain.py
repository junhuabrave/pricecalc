"""Option chain: two-sided quotes indexed by expiry, strike and right.

The arbitrage scanner works on *tradeable* prices, never mids. You lift the
offer to buy and hit the bid to sell, so every check below is written in terms
of ``ask`` for legs you buy and ``bid`` for legs you sell. A "violation" priced
off mids is not an arbitrage — it is a spread you cannot cross.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from pricecalc.core.black_scholes import OptionType

# Expiries arrive as floats from a single source, so exact grouping is safe;
# rounding guards against a caller assembling a chain from mixed arithmetic.
TAU_PRECISION = 9


@dataclass(frozen=True, slots=True)
class Quote:
    """A two-sided market in one option."""

    tau: float
    strike: float
    option_type: OptionType
    bid: float
    ask: float

    def __post_init__(self) -> None:
        if self.bid < 0.0:
            raise ValueError(f"bid must be non-negative, got {self.bid}")
        if self.ask < self.bid:
            raise ValueError(f"ask {self.ask} is below bid {self.bid} (crossed market)")
        if self.strike <= 0.0:
            raise ValueError(f"strike must be positive, got {self.strike}")
        if self.tau < 0.0:
            raise ValueError(f"tau must be non-negative, got {self.tau}")

    @property
    def mid(self) -> float:
        return 0.5 * (self.bid + self.ask)

    @property
    def spread(self) -> float:
        return self.ask - self.bid

    @property
    def label(self) -> str:
        return f"{self.tau:.4g}y {self.strike:g} {self.option_type.value}"


@dataclass(frozen=True, slots=True)
class Chain:
    """A snapshot of quotes on one underlying, plus the carry parameters.

    ``underlying_bid``/``underlying_ask`` default to ``spot``; set them apart to
    model a wide cash market, which tightens every check involving a stock leg.
    """

    spot: float
    rate: float
    div_yield: float
    quotes: tuple[Quote, ...]
    underlying_bid: float = 0.0
    underlying_ask: float = 0.0
    _index: dict[tuple[float, float, OptionType], Quote] = field(
        default_factory=dict, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        if self.spot <= 0.0:
            raise ValueError(f"spot must be positive, got {self.spot}")
        # Frozen dataclass: fill the defaults and the index through object.__setattr__.
        if self.underlying_bid <= 0.0:
            object.__setattr__(self, "underlying_bid", self.spot)
        if self.underlying_ask <= 0.0:
            object.__setattr__(self, "underlying_ask", self.spot)
        if self.underlying_ask < self.underlying_bid:
            raise ValueError("underlying ask is below its bid (crossed market)")

        index = {(round(q.tau, TAU_PRECISION), q.strike, q.option_type): q for q in self.quotes}
        object.__setattr__(self, "_index", index)

    def get(self, tau: float, strike: float, option_type: OptionType) -> Quote | None:
        return self._index.get((round(tau, TAU_PRECISION), strike, option_type))

    def expiries(self) -> list[float]:
        return sorted({round(q.tau, TAU_PRECISION) for q in self.quotes})

    def strikes(self, tau: float) -> list[float]:
        key = round(tau, TAU_PRECISION)
        return sorted({q.strike for q in self.quotes if round(q.tau, TAU_PRECISION) == key})

    def by_expiry(self) -> dict[float, list[Quote]]:
        grouped: dict[float, list[Quote]] = defaultdict(list)
        for q in self.quotes:
            grouped[round(q.tau, TAU_PRECISION)].append(q)
        return {
            tau: sorted(qs, key=lambda q: (q.strike, q.option_type.value))
            for tau, qs in grouped.items()
        }
