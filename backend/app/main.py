import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime, timezone

from backend.app.config import settings
from backend.app.database import init_db
from backend.app.coordinator import coordinator
from backend.app.api.routes_market import router as market_router
from backend.app.api.routes_strategy import router as strategy_router
from backend.app.api.routes_paper import router as paper_router
from backend.app.api.routes_backtest import router as backtest_router
from backend.app.api.routes_analytics import router as analytics_router
from backend.app.api.routes_ws import router as ws_router
from backend.app.api.routes_ai_micro_scalper import router as ai_micro_scalper_router
from backend.app.api.routes_pcr import router as pcr_router, router_alias as pcr_alias_router
from backend.app.api.routes_auth import router as auth_router

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("nextrade")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown lifecycle manager."""
    logger.info("Starting NEXTRADE Backend...")
    # Initialize DB tables
    await init_db()
    # Initialize System Coordinator and market feed
    await coordinator.initialize()
    logger.info("NEXTRADE Backend is ready and running.")
    yield
    logger.info("Shutting down NEXTRADE Backend...")
    await coordinator.shutdown()
    logger.info("Shutdown complete.")


app = FastAPI(
    title="NEXTRADE — Automated Algorithm & Paper Trading System",
    description="Algorithmic trading engine with Kotak Neo live data, NIFTY 1M strategy, and automated virtual paper execution.",
    version="1.0.0",
    lifespan=lifespan
)

# CORS configuration
allowed_origins = list({x.strip() for x in settings.cors_origin_list if x.strip() and x.strip() != "*"})
if "https://frontend-blush-ten-hatwklroqt.vercel.app" not in allowed_origins:
    allowed_origins.append("https://frontend-blush-ten-hatwklroqt.vercel.app")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_origin_regex=r"^https://.*\.vercel\.app$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def api_prefix_normalizer(request, call_next):
    """
    Normalizes incoming request paths so both /api/... and /... routes resolve cleanly.
    Prevents 404s caused by Vercel serverless function path-stripping or rewrites.
    """
    path = request.scope.get("path", "")
    if (
        path
        and not path.startswith("/api")
        and not path.startswith("/docs")
        and not path.startswith("/openapi")
        and not path.startswith("/redoc")
        and not path.startswith("/ws")
    ):
        request.scope["path"] = f"/api{path}"
    return await call_next(request)


# Include API Routers
app.include_router(market_router)
app.include_router(strategy_router)
app.include_router(paper_router)
app.include_router(backtest_router)
app.include_router(analytics_router)
app.include_router(ws_router)
app.include_router(ai_micro_scalper_router)
app.include_router(pcr_router)
app.include_router(pcr_alias_router)
app.include_router(auth_router)


@app.get("/api/health")
@app.get("/health")
async def health_check():
    """System health check endpoint."""
    return {
        "status": "HEALTHY",
        "app": "NEXTRADE",
        "version": "1.0.0",
        "mode": "PAPER_TRADING_ONLY",
        "feed_mode": "DEMO_SYNTHETIC" if coordinator.active_adapter.is_demo else "KOTAK_NEO_LIVE",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.app.main:app", host=settings.app_host, port=settings.app_port, reload=True)
