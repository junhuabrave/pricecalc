from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from pricecalc.api.routes_arbitrage import router as arbitrage_router
from pricecalc.api.routes_pricing import router as pricing_router
from pricecalc.config import settings

app = FastAPI(
    title="pricecalc",
    description="Options pricing, no-arbitrage detection and market-making simulation",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Every router mounts under /api so the Vite dev proxy has a single prefix to forward.
app.include_router(pricing_router, prefix="/api")
app.include_router(arbitrage_router, prefix="/api")


@app.get("/api/health", tags=["meta"])
def health() -> dict[str, str]:
    return {"status": "ok", "app": settings.app_name, "version": "0.1.0"}


def run() -> None:
    """Entrypoint for `poetry run pricecalc-api`."""
    import uvicorn

    uvicorn.run(
        "pricecalc.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.debug,
    )
