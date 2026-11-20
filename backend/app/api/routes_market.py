import asyncio
import logging
from fastapi import APIRouter, Query, HTTPException
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone, timedelta

logger = logging.getLogger("nextrade.market_routes")

from backend.app.coordinator import coordinator
from backend.app.database import AsyncSessionLocal
from backend.app.models import BacktestRun
from backend.app.market.history_service import HistoricalMarketDataService
from backend.app.strategy.indicators import (
    calculate_ema,
    calculate_rsi,
    calculate_vwap,
    calculate_atr,
    calculate_heikin_ashi,
    aggregate_candles
)

router = APIRouter(prefix="/api/market", tags=["Market"])

IST = timezone(timedelta(hours=5, minutes=30))


@router.get("/status")
async def get_market_status():
    """
    Return comprehensive market feed status, separate WebSocket connection,
    market data freshness, market open/closed state, and active contract.
    """
    nifty_price = 24500.0
    if coordinator.latest_nifty_tick:
        nifty_price = coordinator.latest_nifty_tick.last_price

    opt_premium = 145.0
    if coordinator.latest_option_tick:
        opt_premium = coordinator.latest_option_tick.last_price

    contract = coordinator.current_contract

    # Determine market session status (IST)
    now_utc = datetime.now(timezone.utc)
    ist_now = now_utc.astimezone(IST)
    is_weekday = ist_now.weekday() < 5
    time_str = ist_now.strftime("%H:%M")
    is_market_open = bool(is_weekday and ("09:15" <= time_str <= "15:30"))
    market_session_status = "OPEN" if is_market_open else "CLOSED"

    # Data freshness
    if not coordinator.active_adapter.is_connected:
        freshness = "DISCONNECTED"
    elif coordinator.is_stale:
        freshness = "STALE"
    else:
        freshness = "FRESH"

    return {
        "is_connected": coordinator.active_adapter.is_connected,
        "is_demo": coordinator.active_adapter.is_demo,
        "broker_name": "kotak_neo" if not coordinator.active_adapter.is_demo else "Kotak Neo (Simulated Demo)",
        "feed_status": "ONLINE" if coordinator.active_adapter.is_connected and not coordinator.is_stale else "STALE/OFFLINE",
        "data_freshness": freshness,
        "is_stale": coordinator.is_stale,
        "is_market_open": is_market_open,
        "market_session_status": market_session_status,
        "active_strategy_id": coordinator.strategy_engine.active_strategy_id,
        "last_tick_time": coordinator.last_tick_received_at.isoformat() if coordinator.last_tick_received_at else None,
        "nifty_price": nifty_price,
        "option_symbol": contract.get("symbol", "NIFTY ATM CE"),
        "option_premium": opt_premium,
        "atm_strike": contract.get("strike", 24500.0),
        "expiry": contract.get("expiry", "WEEKLY"),
        "lot_size": contract.get("lot_size", 65),
        "instrument_token": contract.get("instrument_token", ""),
        "timestamp": now_utc.isoformat()
    }


@router.get("/candles")
async def get_candles(
    symbol: str = Query("NIFTY 50", description="Symbol to fetch candles for"),
    timeframe: str = Query("1m", description="Timeframe: 1m, 2m, 3m, 5m, 15m, 30m, 1h, 4h, 1D"),
    chart_type: str = Query("candlestick", description="candlestick, bar, line, area, heikin_ashi"),
    mode: str = Query("LIVE", description="LIVE, BACKTEST, HISTORICAL"),
    data_source: str = Query("REAL_MARKET", description="REAL_MARKET, SYNTHETIC_TEST"),
    range_preset: str = Query("5D", description="TODAY, 1D, 5D, 1M, 3M, 6M, 1Y, CUSTOM"),
    start_date: Optional[str] = Query(None, description="Start date YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="End date YYYY-MM-DD"),
    before_timestamp: Optional[int] = Query(None, description="Timestamp for pagination/scrolling backwards"),
    limit: int = Query(300, ge=10, le=2000),
    run_id: Optional[int] = Query(None, description="Backtest Run ID to synchronize")
):
    """
    Get candles with multi-timeframe aggregation, complete history (days/weeks/months/years),
    backward pagination, chart type support (including Heikin Ashi),
    and full technical indicators: EMA 9, EMA 21, EMA 50, VWAP, RSI 14, ATR, and UT Bot trailing stop.
    """
    try:
        res = await HistoricalMarketDataService.get_candles(
            symbol=symbol,
            timeframe=timeframe,
            chart_type=chart_type,
            mode=mode,
            data_source=data_source,
            range_preset=range_preset,
            start_date=start_date,
            end_date=end_date,
            before_timestamp=before_timestamp,
            limit=limit,
            run_id=run_id
        )
        return res
    except Exception as e:
        logger.error(f"Error fetching candles for {symbol} ({timeframe}): {e}", exc_info=True)
        # Fallback to local in-memory history if any unexpected error
        history = coordinator.candle_builder.get_history(symbol)
        raw_dicts = [
            {
                "timestamp": int(c.timestamp.timestamp()),
                "time_iso": c.timestamp.isoformat(),
                "open": c.open,
                "high": c.high,
                "low": c.low,
                "close": c.close,
                "volume": float(c.volume),
                "symbol": symbol
            }
            for c in history[-limit:]
        ]
        return {
            "status": "FALLBACK",
            "symbol": symbol,
            "timeframe": timeframe,
            "chart_type": chart_type,
            "candles": raw_dicts
        }


@router.get("/chart/trade-markers")
async def get_chart_trade_markers(
    mode: str = Query("LIVE", description="LIVE or BACKTEST"),
    run_id: Optional[int] = Query(None, description="Backtest run ID"),
    symbol: Optional[str] = Query(None, description="Filter by instrument"),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None)
):
    """
    Return synchronized trade execution markers from stored ledger.
    Includes exact executed fill price, timestamp, SL trigger, target trigger,
    gross/net P&L, charges, slippage, and exit reason.
    """
    try:
        markers = await HistoricalMarketDataService.get_trade_markers(
            mode=mode,
            run_id=run_id,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date
        )
        return {"status": "SUCCESS", "mode": mode, "markers": markers}
    except Exception as e:
        logger.error(f"Error retrieving trade markers: {e}", exc_info=True)
        return {"status": "ERROR", "message": str(e), "markers": []}


@router.get("/chart/instruments")
async def get_chart_instruments(
    query: str = Query("", description="Search term for symbol or strike")
):
    """
    Return list of searchable instruments (NIFTY 50 Index, ATM CE/PE, and surrounding strikes).
    """
    instruments = HistoricalMarketDataService.search_instruments(query)
    return {"status": "SUCCESS", "instruments": instruments}


@router.get("/chart/backtest-runs")
async def get_chart_backtest_runs():
    """
    Return list of completed backtest runs available for chart synchronization.
    """
    from sqlalchemy import select, desc
    async with AsyncSessionLocal() as session:
        stmt = select(BacktestRun).order_by(BacktestRun.id.desc()).limit(20)
        res = await session.execute(stmt)
        runs = res.scalars().all()
        return {
            "status": "SUCCESS",
            "runs": [
                {
                    "run_id": r.id,
                    "strategy_id": r.strategy_id,
                    "strategy_name": r.strategy_name,
                    "instrument_symbol": r.instrument_symbol,
                    "start_date": r.start_date,
                    "end_date": r.end_date,
                    "total_trades": r.total_trades,
                    "win_rate": r.win_rate,
                    "net_profit": r.net_profit,
                    "data_source": r.data_source,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in runs
            ]
        }



@router.get("/option-chain")
async def get_option_chain():
    """Return option chain strikes around current ATM strike."""
    nifty_price = 24500.0
    if coordinator.latest_nifty_tick:
        nifty_price = coordinator.latest_nifty_tick.last_price

    # Check if live Kotak option chain is available
    if coordinator.kotak_adapter and coordinator.kotak_adapter.latest_option_chain_data:
        oc = coordinator.kotak_adapter.latest_option_chain_data
        common = oc.get("common_data", {})
        calls = oc.get("call", [])
        puts = oc.get("put", [])
        atm = coordinator.option_selector.calculate_atm_strike(nifty_price)

        # Build put lookup by strike
        put_map = {}
        for p in puts:
            s_val = float(p.get("inst", {}).get("strkPrc", 0))
            put_map[s_val] = p

        strikes = []
        for c in calls:
            inst_c = c.get("inst", {})
            quote_c = c.get("quote", {})
            oi_c = c.get("oi", {})
            s = float(inst_c.get("strkPrc", 0))

            p_data = put_map.get(s, {})
            inst_p = p_data.get("inst", {})
            quote_p = p_data.get("quote", {})
            oi_p = p_data.get("oi", {})

            strikes.append({
                "strike": s,
                "is_atm": bool(abs(s - atm) < 25),
                "ce_symbol": inst_c.get("symbol", f"NIFTY {int(s)} CE"),
                "ce_token": inst_c.get("neoSymbol", "").replace("nse_fo|", ""),
                "ce_ltp": float(quote_c.get("ltp", 0.0)),
                "ce_oi": int(oi_c.get("cur", 0) or 0),
                "ce_volume": int(quote_c.get("vol", 0) or 0),
                "pe_symbol": inst_p.get("symbol", f"NIFTY {int(s)} PE"),
                "pe_token": inst_p.get("neoSymbol", "").replace("nse_fo|", ""),
                "pe_ltp": float(quote_p.get("ltp", 0.0)),
                "pe_oi": int(oi_p.get("cur", 0) or 0),
                "pe_volume": int(quote_p.get("vol", 0) or 0),
            })

        if strikes:
            return {
                "underlying": "NIFTY",
                "spot_price": nifty_price,
                "atm_strike": atm,
                "expiry": common.get("expiryDt", "2026-11-23"),
                "strikes": strikes
            }

    strikes = coordinator.option_selector.get_option_chain_strikes(nifty_price, count=12)
    return {
        "underlying": "NIFTY",
        "spot_price": nifty_price,
        "atm_strike": coordinator.option_selector.calculate_atm_strike(nifty_price),
        "expiry": coordinator.current_contract.get("expiry", "WEEKLY"),
        "strikes": strikes
    }


@router.get("/expiries")
async def get_expiries():
    """Return list of upcoming Thursday expiry dates."""
    if coordinator.kotak_adapter and coordinator.kotak_adapter.client:
        try:
            loop = asyncio.get_running_loop()
            res = await loop.run_in_executor(
                None,
                lambda: coordinator.kotak_adapter.client.expiries("nse_fo", "NIFTY")
            )
            if res and "expiries" in res:
                return {"expiries": res["expiries"]}
        except Exception:
            pass

    expiries = coordinator.option_selector.get_upcoming_expiries()
    return {"expiries": expiries}


@router.post("/select-contract")
async def select_contract(payload: Dict[str, Any]):
    """Manually select option contract / expiry override."""
    strike = payload.get("strike")
    expiry = payload.get("expiry")
    spot_price = coordinator.latest_nifty_tick.last_price if coordinator.latest_nifty_tick else 24500.0

    if coordinator.paper_broker.active_position:
        raise HTTPException(
            status_code=400,
            detail="Cannot change contract while a paper trading position is open!"
        )

    contract = coordinator.option_selector.select_atm_ce(
        spot_price=spot_price,
        expiry=expiry,
        manual_strike=float(strike) if strike else None
    )
    coordinator.current_contract = contract

    if isinstance(coordinator.active_adapter, SyntheticMarketFeed):
        coordinator.active_adapter.update_atm_strike(
            contract["strike"],
            contract["symbol"],
            contract["instrument_token"]
        )

    return {"status": "SUCCESS", "contract": contract}
