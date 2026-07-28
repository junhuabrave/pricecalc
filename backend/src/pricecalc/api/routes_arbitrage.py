from __future__ import annotations

from collections import Counter

from fastapi import APIRouter

from pricecalc.api.schemas_arbitrage import (
    ChainOut,
    ScanRequest,
    ScanResponse,
    ScanSummary,
    ViolationOut,
)
from pricecalc.core import arbitrage as arb
from pricecalc.core.marketdata.simulated import SmileParams, generate_chain

router = APIRouter(prefix="/arbitrage", tags=["arbitrage"])


@router.post("/scan", response_model=ScanResponse)
def scan(req: ScanRequest) -> ScanResponse:
    """Generate a chain and report every static arbitrage in it.

    Findings are model-free: each one is enforceable by holding the returned
    legs to expiry, with no view on volatility. With `n_violations = 0` the
    chain is arbitrage-free by construction and the result should be empty —
    that is the scanner's own regression test, exposed to the caller.
    """
    sim = generate_chain(
        spot=req.spot,
        rate=req.rate,
        div_yield=req.div_yield,
        expiries=tuple(sorted(req.expiries)),
        strike_count=req.strike_count,
        strike_span=req.strike_span,
        smile=SmileParams(atm_vol=req.atm_vol, skew=req.skew, curvature=req.curvature),
        spread_bps=req.spread_bps,
        n_violations=req.n_violations,
        seed=req.seed,
    )

    violations = arb.scan(sim.chain, min_edge=req.min_edge)

    return ScanResponse(
        chain=ChainOut.from_core(sim.chain),
        violations=[ViolationOut.from_core(v) for v in violations],
        summary=ScanSummary(
            quotes_scanned=len(sim.chain.quotes),
            violations_found=len(violations),
            total_edge=sum(v.profit for v in violations),
            by_kind=dict(Counter(v.kind.value for v in violations)),
            calendar_checks_skipped=req.div_yield > 0.0,
        ),
        planted=[p.description for p in sim.planted],
    )
