from __future__ import annotations

import math

from pydantic import BaseModel, Field, model_validator

from pricecalc.api.schemas import GreeksOut
from pricecalc.core.presets import PRESET_SUMMARY, Preset
from pricecalc.core.strategy import (
    Extreme,
    LegKind,
    PayoffPoint,
    StrategyAnalysis,
    StrategyLeg,
)


class LegIn(BaseModel):
    kind: LegKind
    quantity: float = Field(..., description="Signed: positive long, negative short")
    entry_price: float = Field(..., ge=0, description="Paid or received per unit")
    strike: float | None = Field(None, gt=0)
    tau: float | None = Field(None, ge=0, le=50)
    vol: float | None = Field(None, gt=0, le=10)

    @model_validator(mode="after")
    def _option_legs_need_their_contract_terms(self) -> LegIn:
        if self.kind is not LegKind.UNDERLYING and (
            self.strike is None or self.tau is None or self.vol is None
        ):
            raise ValueError(f"a {self.kind.value} leg requires strike, tau and vol")
        if self.quantity == 0.0:
            raise ValueError("a leg with zero quantity has no effect; remove it instead")
        return self

    def to_core(self) -> StrategyLeg:
        return StrategyLeg(
            kind=self.kind,
            quantity=self.quantity,
            entry_price=self.entry_price,
            strike=self.strike,
            tau=self.tau,
            vol=self.vol,
        )


class AnalyseRequest(BaseModel):
    spot: float = Field(100.0, gt=0)
    rate: float = Field(0.04, ge=-0.5, le=1.0)
    div_yield: float = Field(0.0, ge=0.0, le=1.0)
    legs: list[LegIn] = Field(..., min_length=1, max_length=24)
    span: float = Field(0.5, gt=0.01, le=3.0, description="Chart half-width vs spot")
    steps: int = Field(121, ge=11, le=801)


class PresetRequest(BaseModel):
    """Build a canonical structure at fair value, then analyse it."""

    preset: Preset
    spot: float = Field(100.0, gt=0)
    rate: float = Field(0.04, ge=-0.5, le=1.0)
    div_yield: float = Field(0.0, ge=0.0, le=1.0)
    vol: float = Field(0.20, gt=0.001, le=5.0)
    tau: float = Field(0.25, gt=0.0, le=10.0)
    width: float = Field(0.05, gt=0.001, le=0.5, description="Strike offset vs spot")
    span: float = Field(0.5, gt=0.01, le=3.0)
    steps: int = Field(121, ge=11, le=801)


class LegOut(BaseModel):
    kind: LegKind
    label: str
    quantity: float
    entry_price: float
    strike: float | None
    tau: float | None
    vol: float | None

    @classmethod
    def from_core(cls, leg: StrategyLeg) -> LegOut:
        return cls(
            kind=leg.kind,
            label=leg.label,
            quantity=leg.quantity,
            entry_price=leg.entry_price,
            strike=leg.strike,
            tau=leg.tau,
            vol=leg.vol,
        )


class ExtremeOut(BaseModel):
    value: float | None = Field(..., description="None when unbounded — JSON has no infinity")
    spot: float | None
    unbounded: bool

    @classmethod
    def from_core(cls, e: Extreme) -> ExtremeOut:
        return cls(
            value=None if not math.isfinite(e.value) else e.value,
            spot=e.spot,
            unbounded=e.unbounded,
        )


class PayoffPointOut(BaseModel):
    spot: float
    payoff: float
    value: float

    @classmethod
    def from_core(cls, p: PayoffPoint) -> PayoffPointOut:
        return cls(spot=p.spot, payoff=p.payoff, value=p.value)


class AnalyseResponse(BaseModel):
    legs: list[LegOut]
    net_cost: float = Field(..., description="Positive is a debit, negative a credit")
    net_greeks: GreeksOut
    breakevens: list[float]
    max_profit: ExtremeOut
    max_loss: ExtremeOut
    payoff_slope_up: float = Field(..., description="Payoff slope as spot runs to infinity")
    payoff_slope_down: float
    kinks: list[float]
    curve: list[PayoffPointOut]
    horizon_tau: float = Field(
        ..., description="Nearest expiry; later legs are marked, not settled"
    )
    exact: bool = Field(
        ..., description="False when a leg outlives the horizon and the curve is searched"
    )
    preset: Preset | None = None
    summary: str | None = None

    @classmethod
    def from_core(
        cls,
        legs: tuple[StrategyLeg, ...],
        analysis: StrategyAnalysis,
        preset: Preset | None = None,
    ) -> AnalyseResponse:
        return cls(
            legs=[LegOut.from_core(leg) for leg in legs],
            net_cost=analysis.net_cost,
            net_greeks=GreeksOut.from_core(analysis.net_greeks),
            breakevens=list(analysis.breakevens),
            max_profit=ExtremeOut.from_core(analysis.max_profit),
            max_loss=ExtremeOut.from_core(analysis.max_loss),
            payoff_slope_up=analysis.payoff_slope_up,
            payoff_slope_down=analysis.payoff_slope_down,
            kinks=list(analysis.kinks),
            horizon_tau=analysis.horizon_tau,
            exact=analysis.exact,
            curve=[PayoffPointOut.from_core(p) for p in analysis.curve],
            preset=preset,
            summary=PRESET_SUMMARY.get(preset) if preset else None,
        )


class PresetInfo(BaseModel):
    id: Preset
    label: str
    summary: str


def preset_catalogue() -> list[PresetInfo]:
    return [
        PresetInfo(
            id=p,
            label=p.value.replace("_", " ").title(),
            summary=PRESET_SUMMARY[p],
        )
        for p in Preset
    ]
