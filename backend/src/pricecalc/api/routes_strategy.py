from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from pricecalc.api.schemas_strategy import (
    AnalyseRequest,
    AnalyseResponse,
    PresetInfo,
    PresetRequest,
    preset_catalogue,
)
from pricecalc.core import presets, strategy

router = APIRouter(prefix="/strategy", tags=["strategy"])


@router.get("/presets", response_model=list[PresetInfo])
def list_presets() -> list[PresetInfo]:
    """Catalogue of canonical structures the UI can offer."""
    return preset_catalogue()


@router.post("/analyse", response_model=AnalyseResponse)
def analyse(req: AnalyseRequest) -> AnalyseResponse:
    """Net risk, payoff, breakevens and extremes for an arbitrary position.

    Breakevens and extremes are solved exactly rather than sampled: the payoff
    is piecewise linear in terminal spot, so its roots and turning points are
    determined by the strikes and the wing slopes alone.
    """
    legs = tuple(leg.to_core() for leg in req.legs)
    try:
        result = strategy.analyse(
            legs, req.spot, req.rate, req.div_yield, span=req.span, steps=req.steps
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    return AnalyseResponse.from_core(legs, result)


@router.post("/preset", response_model=AnalyseResponse)
def build_preset(req: PresetRequest) -> AnalyseResponse:
    """Build a named structure at fair value and analyse it in one call."""
    legs = presets.build(
        req.preset,
        spot=req.spot,
        rate=req.rate,
        div_yield=req.div_yield,
        vol=req.vol,
        tau=req.tau,
        width=req.width,
    )
    result = strategy.analyse(
        legs, req.spot, req.rate, req.div_yield, span=req.span, steps=req.steps
    )
    return AnalyseResponse.from_core(legs, result, preset=req.preset)
