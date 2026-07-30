from __future__ import annotations

import math

from pydantic import BaseModel, Field, model_validator

from pricecalc.core.black_scholes import OptionType
from pricecalc.core.mm.quoting import QuoteParams
from pricecalc.core.mm.simulator import SimulationParams, SimulationResult, Step
from pricecalc.core.surface import VolSurface


class SimulateRequest(BaseModel):
    spot: float = Field(100.0, gt=0)
    drift: float = Field(
        0.0, ge=-1.0, le=1.0, description="Zero by default: direction is not skill"
    )
    rate: float = Field(0.04, ge=-0.5, le=1.0)
    div_yield: float = Field(0.0, ge=0.0, le=1.0)

    strike: float = Field(100.0, gt=0)
    expiry: float = Field(0.25, gt=0, le=10)
    option_type: OptionType = OptionType.CALL

    horizon: float = Field(1.0 / 52.0, gt=0, le=5, description="Session length in years")
    steps: int = Field(200, ge=10, le=2000)

    risk_aversion: float = Field(0.10, ge=0.0, le=10.0, description="0 = naive symmetric maker")
    order_flow_intensity: float = Field(6000.0, gt=0, description="Arrivals per year at fair")
    order_flow_decay: float = Field(8.0, gt=0)
    min_half_spread: float = Field(0.01, ge=0.0)
    max_position: float = Field(25.0, gt=0)

    hedge_delta: bool = True
    hedge_threshold: float = Field(0.5, gt=0)
    hedge_cost_bps: float = Field(1.0, ge=0.0, le=500.0)

    atm_vol: float = Field(0.20, gt=0.001, le=5.0)
    skew: float = Field(-0.12, ge=-2.0, le=2.0)
    curvature: float = Field(0.40, ge=0.0, le=5.0)

    seed: int = Field(42, ge=0)

    @model_validator(mode="after")
    def _session_must_end_before_expiry(self) -> SimulateRequest:
        if self.horizon >= self.expiry:
            raise ValueError("the session must end before the option expires")
        return self

    def to_sim_params(self) -> SimulationParams:
        return SimulationParams(
            spot=self.spot,
            drift=self.drift,
            rate=self.rate,
            div_yield=self.div_yield,
            strike=self.strike,
            expiry=self.expiry,
            option_type=self.option_type,
            horizon=self.horizon,
            steps=self.steps,
            hedge_delta=self.hedge_delta,
            hedge_threshold=self.hedge_threshold,
            hedge_cost_bps=self.hedge_cost_bps,
            seed=self.seed,
        )

    def to_quote_params(self) -> QuoteParams:
        return QuoteParams(
            risk_aversion=self.risk_aversion,
            order_flow_intensity=self.order_flow_intensity,
            order_flow_decay=self.order_flow_decay,
            min_half_spread=self.min_half_spread,
            max_position=self.max_position,
        )

    def to_surface(self) -> VolSurface:
        return VolSurface(atm_vol=self.atm_vol, skew=self.skew, curvature=self.curvature)


class StepOut(BaseModel):
    t: float
    spot: float
    fair_value: float
    bid: float
    ask: float
    reservation: float
    skew: float
    inventory: float
    delta_exposure: float
    hedge_position: float
    spread_pnl: float
    inventory_pnl: float
    hedge_pnl: float
    total_pnl: float

    @classmethod
    def from_core(cls, s: Step) -> StepOut:
        return cls(
            t=s.t,
            spot=s.spot,
            fair_value=s.fair_value,
            bid=s.bid,
            ask=s.ask if math.isfinite(s.ask) else s.fair_value * 4.0,
            reservation=s.reservation,
            skew=s.skew,
            inventory=s.inventory,
            delta_exposure=s.delta_exposure,
            hedge_position=s.hedge_position,
            spread_pnl=s.spread_pnl,
            inventory_pnl=s.inventory_pnl,
            hedge_pnl=s.hedge_pnl,
            total_pnl=s.total_pnl,
        )


class Attribution(BaseModel):
    """P&L split into its sources. The components sum to the total."""

    spread_pnl: float = Field(..., description="Edge captured at each fill — the business")
    inventory_pnl: float = Field(..., description="Mark-to-market on the position — the cost")
    hedge_pnl: float = Field(..., description="What delta hedging made or lost")
    total_pnl: float


class SimulateResponse(BaseModel):
    attribution: Attribution
    steps: list[StepOut]
    fills: int
    buys: int
    sells: int
    hedge_trades: int
    max_abs_inventory: float
    ending_inventory: float
    realised_vol: float
    implied_vol_at_open: float
    capture_per_fill: float = Field(..., description="Average edge earned per fill")

    @classmethod
    def from_core(cls, r: SimulationResult) -> SimulateResponse:
        return cls(
            attribution=Attribution(
                spread_pnl=r.spread_pnl,
                inventory_pnl=r.inventory_pnl,
                hedge_pnl=r.hedge_pnl,
                total_pnl=r.total_pnl,
            ),
            steps=[StepOut.from_core(s) for s in r.steps],
            fills=r.fills,
            buys=r.buys,
            sells=r.sells,
            hedge_trades=r.hedge_trades,
            max_abs_inventory=r.max_abs_inventory,
            ending_inventory=r.ending_inventory,
            realised_vol=r.realised_vol,
            implied_vol_at_open=r.metadata.get("implied_vol_at_open", 0.0),
            capture_per_fill=r.spread_pnl / r.fills if r.fills else 0.0,
        )


class SweepPoint(BaseModel):
    risk_aversion: float
    fills: float
    spread_pnl: float
    inventory_pnl: float
    hedge_pnl: float
    total_pnl: float
    max_abs_inventory: float
    ending_inventory: float


class SweepResponse(BaseModel):
    """Average outcome across seeds, per risk-aversion setting.

    One path says nothing about a strategy — the naive maker gets lucky often
    enough to look fine. Averaging over seeds is what exposes the tradeoff.
    """

    points: list[SweepPoint]
    paths_per_point: int
