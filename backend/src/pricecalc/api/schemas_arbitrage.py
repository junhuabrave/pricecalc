from __future__ import annotations

from pydantic import BaseModel, Field

from pricecalc.core.arbitrage import Leg, Violation, ViolationKind
from pricecalc.core.chain import Chain, Quote


class ScanRequest(BaseModel):
    """Generate a simulated chain and scan it in one call.

    There is no live feed yet, so the chain is produced on demand. Every field
    is seeded or deterministic, which makes a finding reproducible from the
    request alone — paste the same body, get the same arbitrage.
    """

    spot: float = Field(100.0, gt=0)
    rate: float = Field(0.04, ge=-0.5, le=1.0)
    div_yield: float = Field(0.0, ge=0.0, le=1.0, description="Non-zero disables calendar checks")

    expiries: list[float] = Field(default=[0.08, 0.25, 0.5, 1.0], min_length=1, max_length=12)
    strike_count: int = Field(11, ge=3, le=41)
    strike_span: float = Field(0.30, gt=0.01, le=0.9, description="Ladder half-width vs spot")

    atm_vol: float = Field(0.20, gt=0.001, le=5.0)
    skew: float = Field(-0.12, ge=-2.0, le=2.0, description="Negative for equity skew")
    curvature: float = Field(0.45, ge=0.0, le=5.0)

    spread_bps: float = Field(80.0, ge=0.0, le=5000.0)
    n_violations: int = Field(0, ge=0, le=12, description="Mispricings to plant; one per expiry")
    seed: int = Field(42, ge=0)
    min_edge: float = Field(0.01, ge=0.0, description="Minimum locked-in profit to report")


class QuoteOut(BaseModel):
    tau: float
    strike: float
    option_type: str
    bid: float
    ask: float
    mid: float

    @classmethod
    def from_core(cls, q: Quote) -> QuoteOut:
        return cls(
            tau=q.tau,
            strike=q.strike,
            option_type=q.option_type.value,
            bid=q.bid,
            ask=q.ask,
            mid=q.mid,
        )


class ChainOut(BaseModel):
    spot: float
    rate: float
    div_yield: float
    quotes: list[QuoteOut]

    @classmethod
    def from_core(cls, c: Chain) -> ChainOut:
        return cls(
            spot=c.spot,
            rate=c.rate,
            div_yield=c.div_yield,
            quotes=[QuoteOut.from_core(q) for q in c.quotes],
        )


class LegOut(BaseModel):
    instrument: str
    quantity: float
    price: float
    cash_flow: float

    @classmethod
    def from_core(cls, leg: Leg) -> LegOut:
        return cls(
            instrument=leg.instrument,
            quantity=leg.quantity,
            price=leg.price,
            cash_flow=leg.cash_flow,
        )


class ViolationOut(BaseModel):
    kind: ViolationKind
    summary: str
    detail: str
    profit: float
    tau: float
    strikes: list[float]
    legs: list[LegOut]

    @classmethod
    def from_core(cls, v: Violation) -> ViolationOut:
        return cls(
            kind=v.kind,
            summary=v.summary,
            detail=v.detail,
            profit=v.profit,
            tau=v.tau,
            strikes=list(v.strikes),
            legs=[LegOut.from_core(leg) for leg in v.legs],
        )


class ScanSummary(BaseModel):
    quotes_scanned: int
    violations_found: int
    total_edge: float = Field(..., description="Sum of locked-in profit across findings")
    by_kind: dict[str, int]
    calendar_checks_skipped: bool = Field(
        ..., description="True when a dividend yield makes calendar ordering invalid"
    )


class ScanResponse(BaseModel):
    chain: ChainOut
    violations: list[ViolationOut]
    summary: ScanSummary
    planted: list[str] = Field(
        default_factory=list, description="Mispricings deliberately injected, for verification"
    )
