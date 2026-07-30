from __future__ import annotations

from dataclasses import replace

from fastapi import APIRouter, Query

from pricecalc.api.schemas_mm import (
    SimulateRequest,
    SimulateResponse,
    SweepPoint,
    SweepResponse,
)
from pricecalc.core.mm import simulator

router = APIRouter(prefix="/marketmaking", tags=["market making"])


@router.post("/simulate", response_model=SimulateResponse)
def simulate(req: SimulateRequest) -> SimulateResponse:
    """Run one market-making session and attribute the P&L.

    Every quantity is seeded, so the same request replays the same session —
    including the order flow, not just the price path.
    """
    result = simulator.run(req.to_sim_params(), req.to_quote_params(), req.to_surface())
    return SimulateResponse.from_core(result)


@router.post("/sweep", response_model=SweepResponse)
def sweep(
    req: SimulateRequest,
    paths: int = Query(16, ge=2, le=64, description="Seeds averaged per setting"),
) -> SweepResponse:
    """Average outcomes across seeds for a range of risk-aversion settings.

    This is where the model earns its keep. A single session tells you almost
    nothing: the naive maker often finishes ahead by being accidentally long a
    market that rose. Averaged over paths, the tradeoff appears — quoting wider
    captures more per fill but wins fewer of them, and there is an interior
    optimum rather than a monotone "more caution is better".
    """
    sim_params = req.to_sim_params()
    quote_params = req.to_quote_params()
    surface = req.to_surface()

    levels = [0.0, 0.05, 0.1, 0.2, 0.4, 0.8, 1.6]
    points: list[SweepPoint] = []

    for gamma in levels:
        runs = [
            simulator.run(
                replace(sim_params, seed=req.seed + offset),
                replace(quote_params, risk_aversion=gamma),
                surface,
            )
            for offset in range(paths)
        ]
        n = float(len(runs))
        points.append(
            SweepPoint(
                risk_aversion=gamma,
                fills=sum(r.fills for r in runs) / n,
                spread_pnl=sum(r.spread_pnl for r in runs) / n,
                inventory_pnl=sum(r.inventory_pnl for r in runs) / n,
                hedge_pnl=sum(r.hedge_pnl for r in runs) / n,
                total_pnl=sum(r.total_pnl for r in runs) / n,
                max_abs_inventory=sum(r.max_abs_inventory for r in runs) / n,
                ending_inventory=sum(abs(r.ending_inventory) for r in runs) / n,
            )
        )

    return SweepResponse(points=points, paths_per_point=paths)
