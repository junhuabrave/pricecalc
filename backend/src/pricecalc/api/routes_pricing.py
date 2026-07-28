from __future__ import annotations

import numpy as np
from fastapi import APIRouter, HTTPException, status

from pricecalc.api.schemas import (
    EvaluateRequest,
    EvaluateResponse,
    GreeksOut,
    ImpliedVolRequest,
    ImpliedVolResponse,
    SweepPoint,
    SweepRequest,
    SweepResponse,
)
from pricecalc.core import black_scholes as bs

router = APIRouter(prefix="/pricing", tags=["pricing"])


@router.post("/evaluate", response_model=EvaluateResponse)
def evaluate(req: EvaluateRequest) -> EvaluateResponse:
    """Price a single European option and return its full risk profile."""
    result = bs.evaluate(
        spot=req.spot,
        strike=req.strike,
        rate=req.rate,
        div_yield=req.div_yield,
        vol=req.vol,
        tau=req.tau_years,
        option_type=req.option_type,
    )
    return EvaluateResponse.from_core(result, req.strike)


@router.post("/implied-vol", response_model=ImpliedVolResponse)
def implied_vol(req: ImpliedVolRequest) -> ImpliedVolResponse:
    """Back out the volatility that reproduces an observed premium.

    A quote outside the no-arbitrage band has no implied vol; we surface that
    as a 422 with the band attached rather than clamping to a fake number.
    """
    lower, upper = bs.price_bounds(
        req.spot, req.strike, req.rate, req.div_yield, req.tau_years, req.option_type
    )
    try:
        vol = bs.implied_vol(
            target_price=req.price,
            spot=req.spot,
            strike=req.strike,
            rate=req.rate,
            div_yield=req.div_yield,
            tau=req.tau_years,
            option_type=req.option_type,
        )
    except bs.NoImpliedVolError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "message": str(exc),
                "lower_bound": lower,
                "upper_bound": upper,
            },
        ) from exc

    grk = bs.greeks(
        req.spot, req.strike, req.rate, req.div_yield, vol, req.tau_years, req.option_type
    )
    return ImpliedVolResponse(
        implied_vol=vol,
        lower_bound=lower,
        upper_bound=upper,
        greeks=GreeksOut.from_core(grk),
    )


@router.post("/sweep", response_model=SweepResponse)
def sweep(req: SweepRequest) -> SweepResponse:
    """Evaluate price and Greeks across a spot grid for charting."""
    # spot_min/spot_max are filled in by the request validator.
    assert req.spot_min is not None and req.spot_max is not None  # noqa: S101
    grid = np.linspace(req.spot_min, req.spot_max, req.steps)

    points: list[SweepPoint] = []
    for s in grid:
        spot = float(s)
        px = bs.price(
            spot, req.strike, req.rate, req.div_yield, req.vol, req.tau_years, req.option_type
        )
        g = bs.greeks(
            spot, req.strike, req.rate, req.div_yield, req.vol, req.tau_years, req.option_type
        )
        points.append(
            SweepPoint(
                spot=spot,
                price=px,
                intrinsic=max(req.option_type.sign * (spot - req.strike), 0.0),
                delta=g.delta,
                gamma=g.gamma,
                vega=g.vega,
                theta=g.theta,
            )
        )
    return SweepResponse(points=points)
