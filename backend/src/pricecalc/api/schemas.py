"""Request/response models for the HTTP layer.

These are deliberately separate from the dataclasses in ``core``: the core
stays framework-free and easy to unit test, and the wire format can evolve
(field renames, extra diagnostics) without touching the maths.
"""

from __future__ import annotations

import math

from pydantic import BaseModel, Field, model_validator

from pricecalc.core.black_scholes import Greeks, OptionType, PricingResult


class MarketInputs(BaseModel):
    """The Black-Scholes state vector, shared by every pricing endpoint."""

    spot: float = Field(..., gt=0, description="Underlying price S")
    strike: float = Field(..., gt=0, description="Strike K")
    rate: float = Field(0.05, ge=-0.5, le=1.0, description="Risk-free rate r, decimal")
    div_yield: float = Field(0.0, ge=-0.5, le=1.0, description="Dividend yield q, decimal")
    tau_years: float = Field(..., ge=0, le=50, description="Time to expiry in years")
    option_type: OptionType = OptionType.CALL


class EvaluateRequest(MarketInputs):
    vol: float = Field(..., gt=0, le=10, description="Volatility sigma, decimal (0.2 = 20%)")


class GreeksOut(BaseModel):
    delta: float
    gamma: float
    vega: float
    theta: float
    rho: float
    vanna: float
    volga: float

    @classmethod
    def from_core(cls, g: Greeks) -> GreeksOut:
        return cls(
            delta=g.delta,
            gamma=g.gamma,
            vega=g.vega,
            theta=g.theta,
            rho=g.rho,
            vanna=g.vanna,
            volga=g.volga,
        )


class EvaluateResponse(BaseModel):
    price: float
    greeks: GreeksOut
    d1: float
    d2: float
    forward: float
    intrinsic: float
    time_value: float
    moneyness: float = Field(..., description="log(F/K); 0 is at-the-money-forward")

    @classmethod
    def from_core(cls, r: PricingResult, strike: float) -> EvaluateResponse:
        return cls(
            price=r.price,
            greeks=GreeksOut.from_core(r.greeks),
            d1=r.d1,
            d2=r.d2,
            forward=r.forward,
            intrinsic=r.intrinsic,
            time_value=r.time_value,
            moneyness=math.log(r.forward / strike),
        )


class ImpliedVolRequest(MarketInputs):
    price: float = Field(..., gt=0, description="Observed option premium")


class ImpliedVolResponse(BaseModel):
    implied_vol: float
    lower_bound: float = Field(..., description="No-arbitrage minimum premium")
    upper_bound: float = Field(..., description="No-arbitrage maximum premium")
    greeks: GreeksOut


class SweepRequest(EvaluateRequest):
    """Price/Greeks across a spot grid — drives the charts on the pricer tab."""

    spot_min: float | None = Field(None, gt=0)
    spot_max: float | None = Field(None, gt=0)
    steps: int = Field(101, ge=3, le=1001)

    @model_validator(mode="after")
    def _default_and_check_range(self) -> SweepRequest:
        # Default to +/-40% around spot, which comfortably covers the gamma peak.
        if self.spot_min is None:
            self.spot_min = self.spot * 0.6
        if self.spot_max is None:
            self.spot_max = self.spot * 1.4
        if self.spot_min >= self.spot_max:
            raise ValueError("spot_min must be strictly less than spot_max")
        return self


class SweepPoint(BaseModel):
    spot: float
    price: float
    intrinsic: float
    delta: float
    gamma: float
    vega: float
    theta: float


class SweepResponse(BaseModel):
    points: list[SweepPoint]
