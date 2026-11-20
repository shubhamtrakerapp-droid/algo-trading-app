import logging
from fastapi import APIRouter, Query, HTTPException
from typing import Optional, List, Dict, Any

from backend.app.services.pcr_service import PCRService, normalize_underlying

logger = logging.getLogger("nextrade.pcr_routes")
router = APIRouter(prefix="/api/market-data/pcr", tags=["PCR & Options Analytics"])
router_alias = APIRouter(prefix="/api/pcr", tags=["PCR & Options Analytics"])


@router.get("")
@router_alias.get("/data")
async def get_pcr_data(
    underlying: str = Query("NIFTY", description="Underlying symbol (NIFTY, BANKNIFTY, FINNIFTY)"),
    expiry: Optional[str] = Query(None, description="Expiry date in YYYY-MM-DD"),
    strike_range: int = Query(10, description="Strike range around ATM (5, 10, 15, 20, 25, or 0 for All)"),
    force_refresh: bool = Query(False, description="Force fresh fetch from Kotak Neo"),
    bullish_threshold: float = Query(1.05, description="OI PCR Bullish Threshold"),
    bearish_threshold: float = Query(0.95, description="OI PCR Bearish Threshold")
):
    """
    Retrieve live Put-Call Ratio (PCR), open interest distribution, strike-wise analytics,
    VWAP context, support/resistance levels, and rules-based market bias.
    """
    try:
        data = await PCRService.analyze_pcr(
            underlying=underlying,
            expiry=expiry,
            strike_range=strike_range,
            force_refresh=force_refresh,
            oi_pcr_bullish_threshold=bullish_threshold,
            oi_pcr_bearish_threshold=bearish_threshold
        )
        return data
    except Exception as e:
        logger.error(f"Error in get_pcr_data({underlying}, {expiry}, range={strike_range}): {e}", exc_info=True)
        return {
            "status": "ERROR",
            "message": str(e),
            "underlying": underlying,
            "data_status": "API ERROR"
        }


@router.get("/expiries")
@router_alias.get("/expiries")
async def get_pcr_expiries(
    underlying: str = Query("NIFTY", description="Underlying symbol")
):
    """Return available expiry dates for the selected underlying."""
    try:
        exps = await PCRService.get_expiries(underlying=underlying)
        return {"status": "SUCCESS", "underlying": normalize_underlying(underlying), "expiries": exps}
    except Exception as e:
        logger.error(f"Error in get_pcr_expiries({underlying}): {e}", exc_info=True)
        return {"status": "ERROR", "message": str(e), "expiries": []}


@router.get("/history")
@router_alias.get("/history")
async def get_pcr_history(
    underlying: str = Query("NIFTY", description="Underlying symbol"),
    trading_date: Optional[str] = Query(None, description="Trading date YYYY-MM-DD"),
    strike_range: int = Query(10, description="Strike range of snapshots")
):
    """Return 1-minute historical intraday PCR time series snapshots for charting."""
    try:
        history = await PCRService.get_history(
            underlying=underlying,
            trading_date=trading_date,
            strike_range=strike_range
        )
        return {
            "status": "SUCCESS",
            "underlying": normalize_underlying(underlying),
            "trading_date": trading_date,
            "strike_range": strike_range,
            "data_points_count": len(history),
            "history": history
        }
    except Exception as e:
        logger.error(f"Error in get_pcr_history({underlying}): {e}", exc_info=True)
        return {"status": "ERROR", "message": str(e), "history": []}


@router.get("/dates")
@router_alias.get("/dates")
async def get_pcr_dates(
    underlying: str = Query("NIFTY", description="Underlying symbol")
):
    """Return list of historical trading dates with recorded PCR snapshots."""
    try:
        dates = await PCRService.get_available_dates(underlying=underlying)
        return {"status": "SUCCESS", "underlying": normalize_underlying(underlying), "dates": dates}
    except Exception as e:
        logger.error(f"Error in get_pcr_dates({underlying}): {e}", exc_info=True)
        return {"status": "ERROR", "message": str(e), "dates": []}
