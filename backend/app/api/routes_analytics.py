import io
import csv
import logging
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, HTTPException, Query, Response
from sqlalchemy import select, desc
from typing import Dict, Any, List, Optional

from backend.app.coordinator import coordinator
from backend.app.database import AsyncSessionLocal
from backend.app.models import PaperTrade, BacktestTrade, BacktestRun, SystemEvent
from backend.app.analytics.metrics import compute_trading_metrics
from backend.app.analytics.calendar import (
    PerformanceCalendarEngine,
    parse_trade_datetime_ist,
    get_current_ist_datetime,
    IST
)

logger = logging.getLogger("nextrade.analytics")
router = APIRouter(prefix="/api/analytics", tags=["Analytics"])


async def fetch_unified_trades(
    session,
    source: str = "PAPER",
    strategy_id: Optional[str] = None,
    execution_mode: Optional[str] = None,
    run_id: Optional[int] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    instrument_symbol: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Retrieve trades from PaperTrade or BacktestTrade according to filters,
    normalizing into a unified trade dictionary structure.
    Strictly isolates sources so paper trades and backtest runs never mix.
    """
    results: List[Dict[str, Any]] = []
    norm_source = (source or "PAPER").upper()

    # 1. Paper Trades (Only when source is PAPER or ALL)
    if norm_source in ("PAPER", "ALL") and run_id is None:
        stmt = select(PaperTrade).order_by(PaperTrade.exit_time.asc())
        if strategy_id and strategy_id != "ALL":
            stmt = stmt.where(PaperTrade.strategy_id == strategy_id)
        if execution_mode and execution_mode != "ALL":
            stmt = stmt.where(PaperTrade.execution_mode == execution_mode)

        res = await session.execute(stmt)
        p_trades = res.scalars().all()

        for t in p_trades:
            exit_dt = parse_trade_datetime_ist(t.exit_time)
            entry_dt = parse_trade_datetime_ist(t.entry_time)
            date_str = exit_dt.strftime("%Y-%m-%d") if exit_dt else ""

            if start_date and date_str and date_str < start_date:
                continue
            if end_date and date_str and date_str > end_date:
                continue
            if instrument_symbol and instrument_symbol != "ALL":
                if instrument_symbol.lower() not in t.option_symbol.lower():
                    continue

            results.append({
                "id": t.id,
                "trade_source": "PAPER_TRADING",
                "strategy_id": getattr(t, "strategy_id", "EMA_RSI"),
                "position_id": t.position_id,
                "underlying_symbol": t.underlying_symbol,
                "option_symbol": t.option_symbol,
                "strike": t.strike,
                "expiry": t.expiry,
                "entry_time": entry_dt.isoformat() if entry_dt else str(t.entry_time),
                "exit_time": exit_dt.isoformat() if exit_dt else str(t.exit_time),
                "entry_price": t.entry_price,
                "exit_price": t.exit_price,
                "quantity": t.quantity,
                "target_price": t.target_price,
                "stop_price": t.stop_price,
                "configured_sl_points": getattr(t, "configured_sl_points", None) or 2.0,
                "configured_target_points": getattr(t, "configured_target_points", None) or 4.0,
                "effective_sl_points": getattr(t, "effective_sl_points", None) or 2.0,
                "effective_target_points": getattr(t, "effective_target_points", None) or 4.0,
                "sl_trigger_price": getattr(t, "sl_trigger_price", t.stop_price),
                "target_trigger_price": getattr(t, "target_trigger_price", t.target_price),
                "slippage_cost": getattr(t, "slippage_cost", 0.0) or 0.0,
                "execution_mode": getattr(t, "execution_mode", "REALISTIC"),
                "is_ambiguous": getattr(t, "is_ambiguous", False) or False,
                "ambiguity_flag": getattr(t, "ambiguity_flag", None),
                "holding_time_minutes": getattr(t, "holding_time_minutes", 1) or 1,
                "exit_reason": t.exit_reason,
                "gross_pnl": t.gross_pnl,
                "entry_charge": getattr(t, "entry_charge", 10.0),
                "exit_charge": getattr(t, "exit_charge", 10.0),
                "charges": t.total_charges,
                "total_charges": t.total_charges,
                "net_pnl": t.net_pnl,
                "is_win": t.is_win
            })

    # 2. Backtest Trades (Only when source is BACKTEST or ALL, or when a specific run_id is requested)
    if norm_source in ("BACKTEST", "ALL") or (norm_source != "PAPER" and run_id is not None):
        stmt = select(BacktestTrade).order_by(BacktestTrade.exit_time.asc())
        if run_id is not None:
            stmt = stmt.where(BacktestTrade.run_id == run_id)
        if strategy_id and strategy_id != "ALL":
            stmt = stmt.where(BacktestTrade.strategy_id == strategy_id)
        if execution_mode and execution_mode != "ALL":
            stmt = stmt.where(BacktestTrade.execution_mode == execution_mode)

        res = await session.execute(stmt)
        b_trades = res.scalars().all()

        for t in b_trades:
            exit_dt = parse_trade_datetime_ist(t.exit_time)
            entry_dt = parse_trade_datetime_ist(t.entry_time)
            date_str = exit_dt.strftime("%Y-%m-%d") if exit_dt else ""

            if start_date and date_str and date_str < start_date:
                continue
            if end_date and date_str and date_str > end_date:
                continue
            if instrument_symbol and instrument_symbol != "ALL":
                if instrument_symbol.lower() not in t.option_symbol.lower():
                    continue

            results.append({
                "id": t.id,
                "run_id": t.run_id,
                "trade_source": "BACKTEST",
                "strategy_id": getattr(t, "strategy_id", "UT_BOT"),
                "position_id": t.id,
                "underlying_symbol": getattr(t, "underlying_symbol", "NIFTY"),
                "option_symbol": t.option_symbol,
                "strike": t.strike,
                "expiry": t.expiry,
                "entry_time": entry_dt.isoformat() if entry_dt else str(t.entry_time),
                "exit_time": exit_dt.isoformat() if exit_dt else str(t.exit_time),
                "entry_price": t.entry_price,
                "exit_price": t.exit_price,
                "quantity": t.quantity,
                "target_price": t.target,
                "stop_price": t.stop,
                "configured_sl_points": getattr(t, "configured_sl_points", None) or 2.0,
                "configured_target_points": getattr(t, "configured_target_points", None) or 4.0,
                "effective_sl_points": getattr(t, "effective_sl_points", None) or 2.0,
                "effective_target_points": getattr(t, "effective_target_points", None) or 4.0,
                "sl_trigger_price": getattr(t, "sl_trigger_price", t.stop),
                "target_trigger_price": getattr(t, "target_trigger_price", t.target),
                "slippage_cost": getattr(t, "slippage_cost", 0.0) or 0.0,
                "execution_mode": getattr(t, "execution_mode", "TRIGGER_PRICE"),
                "is_ambiguous": getattr(t, "is_ambiguous", False) or False,
                "ambiguity_flag": getattr(t, "ambiguity_flag", None),
                "holding_time_minutes": getattr(t, "holding_time_minutes", 1) or 1,
                "exit_reason": t.exit_reason,
                "gross_pnl": t.gross_pnl,
                "entry_charge": getattr(t, "entry_charge", 10.0),
                "exit_charge": getattr(t, "exit_charge", 10.0),
                "charges": getattr(t, "charges", 20.0),
                "total_charges": getattr(t, "charges", 20.0),
                "net_pnl": t.net_pnl,
                "is_win": t.is_win
            })

    # Sort chronological by exit time
    results.sort(key=lambda x: x["exit_time"])
    return results


@router.get("/summary")
async def get_analytics_summary(
    source: str = Query(default="PAPER"),
    run_id: Optional[int] = Query(default=None),
    strategy_id: Optional[str] = Query(default=None),
    execution_mode: Optional[str] = Query(default=None),
    instrument_symbol: Optional[str] = Query(default=None),
    start_date: Optional[str] = Query(default=None),
    end_date: Optional[str] = Query(default=None)
):
    """
    Compute and return comprehensive analytics across paper trades or historical backtest runs.
    Derived directly from the verified underlying trade ledger without cross-contamination.
    """
    norm_source = (source or "PAPER").upper()
    async with AsyncSessionLocal() as session:
        initial_capital = 100000.0
        run_info = None

        if norm_source == "BACKTEST":
            if run_id is not None:
                run_res = await session.execute(select(BacktestRun).where(BacktestRun.id == run_id))
                run = run_res.scalar_one_or_none()
                if not run:
                    raise HTTPException(status_code=404, detail=f"Backtest run #{run_id} not found.")
                initial_capital = run.initial_capital
                run_info = {
                    "id": run.id,
                    "strategy_id": getattr(run, "strategy_id", "UT_BOT"),
                    "strategy_name": run.strategy_name,
                    "instrument_symbol": getattr(run, "instrument_symbol", "NIFTY ATM CE"),
                    "timeframe": getattr(run, "timeframe", "1m"),
                    "start_date": run.start_date,
                    "end_date": run.end_date,
                    "data_source": run.data_source,
                    "created_at": run.created_at.isoformat()
                }
            else:
                # Find latest completed backtest run
                latest_res = await session.execute(select(BacktestRun).order_by(desc(BacktestRun.id)).limit(1))
                run = latest_res.scalar_one_or_none()
                if run:
                    run_id = run.id
                    initial_capital = run.initial_capital
                    run_info = {
                        "id": run.id,
                        "strategy_id": getattr(run, "strategy_id", "UT_BOT"),
                        "strategy_name": run.strategy_name,
                        "instrument_symbol": getattr(run, "instrument_symbol", "NIFTY ATM CE"),
                        "timeframe": getattr(run, "timeframe", "1m"),
                        "start_date": run.start_date,
                        "end_date": run.end_date,
                        "data_source": run.data_source,
                        "created_at": run.created_at.isoformat()
                    }
                else:
                    empty_res = compute_trading_metrics([], initial_capital=initial_capital)
                    empty_res["data_source"] = "BACKTEST"
                    empty_res["run_id"] = None
                    empty_res["run_info"] = None
                    return empty_res
        elif norm_source == "PAPER":
            initial_capital = coordinator.paper_broker.initial_capital

        trades = await fetch_unified_trades(
            session=session,
            source=norm_source,
            strategy_id=strategy_id,
            execution_mode=execution_mode,
            run_id=run_id,
            start_date=start_date,
            end_date=end_date,
            instrument_symbol=instrument_symbol
        )

        metrics = compute_trading_metrics(trades, initial_capital=initial_capital)
        metrics["data_source"] = norm_source
        metrics["run_id"] = run_id
        metrics["run_info"] = run_info
        return metrics


@router.get("/backtest-runs")
async def get_analytics_backtest_runs(limit: int = 50):
    """List available backtest runs for the Analytics selector dropdown."""
    async with AsyncSessionLocal() as session:
        stmt = select(BacktestRun).order_by(desc(BacktestRun.id)).limit(limit)
        res = await session.execute(stmt)
        runs = res.scalars().all()
        return [
            {
                "id": r.id,
                "strategy_id": getattr(r, "strategy_id", "UT_BOT"),
                "strategy_name": r.strategy_name,
                "timeframe": getattr(r, "timeframe", "1m"),
                "instrument_symbol": getattr(r, "instrument_symbol", "NIFTY ATM CE"),
                "start_date": r.start_date,
                "end_date": r.end_date,
                "data_source": r.data_source,
                "initial_capital": r.initial_capital,
                "final_capital": r.final_capital,
                "total_trades": r.total_trades,
                "win_rate": r.win_rate,
                "net_profit": r.net_profit,
                "profit_factor": r.profit_factor,
                "max_drawdown": r.max_drawdown,
                "created_at": r.created_at.isoformat()
            }
            for r in runs
        ]


async def validate_and_resolve_run_id(session, source: str, run_id: Optional[int]) -> Optional[int]:
    """Validate that run_id exists or resolve to the latest backtest run."""
    norm_source = (source or "PAPER").upper()
    if norm_source == "BACKTEST":
        if run_id is not None:
            res = await session.execute(select(BacktestRun).where(BacktestRun.id == run_id))
            if not res.scalar_one_or_none():
                raise HTTPException(status_code=404, detail=f"Backtest run #{run_id} not found.")
            return run_id
        else:
            res = await session.execute(select(BacktestRun).order_by(desc(BacktestRun.id)).limit(1))
            latest = res.scalar_one_or_none()
            return latest.id if latest else None
    return None


@router.get("/calendar/monthly")
async def get_monthly_calendar(
    year: int = Query(default=2026),
    month: int = Query(default=11, ge=1, le=12),
    source: str = Query(default="PAPER"),  # PAPER, BACKTEST, ALL
    strategy_id: Optional[str] = Query(default=None),
    execution_mode: Optional[str] = Query(default=None),
    run_id: Optional[int] = Query(default=None)
):
    """
    Return full-month calendar grid (Monday-Sunday columns),
    daily performance metrics, streaks, and monthly summary.
    """
    norm_source = (source or "PAPER").upper()
    async with AsyncSessionLocal() as session:
        resolved_run_id = await validate_and_resolve_run_id(session, norm_source, run_id)
        trades = await fetch_unified_trades(
            session=session,
            source=norm_source,
            strategy_id=strategy_id,
            execution_mode=execution_mode,
            run_id=resolved_run_id
        )

        tested_start = None
        tested_end = None
        if norm_source == "BACKTEST" and resolved_run_id:
            b_run = await session.get(BacktestRun, resolved_run_id)
            if b_run:
                tested_start = b_run.start_date
                tested_end = b_run.end_date

    res = PerformanceCalendarEngine.get_monthly_calendar(
        trades=trades,
        year=year,
        month=month,
        tested_start_date=tested_start,
        tested_end_date=tested_end
    )
    return {
        "status": "SUCCESS",
        "data_source": norm_source,
        "run_id": resolved_run_id,
        "strategy_filter": strategy_id or "ALL",
        "execution_mode_filter": execution_mode or "ALL",
        **res
    }


@router.get("/calendar/yearly")
async def get_yearly_overview(
    year: int = Query(default=2026),
    source: str = Query(default="PAPER"),
    strategy_id: Optional[str] = Query(default=None),
    execution_mode: Optional[str] = Query(default=None),
    run_id: Optional[int] = Query(default=None)
):
    """
    Return 12-month yearly performance overview with annual summary and streak analysis.
    """
    norm_source = (source or "PAPER").upper()
    async with AsyncSessionLocal() as session:
        resolved_run_id = await validate_and_resolve_run_id(session, norm_source, run_id)
        trades = await fetch_unified_trades(
            session=session,
            source=norm_source,
            strategy_id=strategy_id,
            execution_mode=execution_mode,
            run_id=resolved_run_id
        )

    res = PerformanceCalendarEngine.get_yearly_overview(trades=trades, year=year)
    return {
        "status": "SUCCESS",
        "data_source": norm_source,
        "run_id": resolved_run_id,
        "strategy_filter": strategy_id or "ALL",
        "execution_mode_filter": execution_mode or "ALL",
        **res
    }


@router.get("/calendar/day")
async def get_daily_details(
    date: str = Query(description="Target date in YYYY-MM-DD format"),
    source: str = Query(default="PAPER"),
    strategy_id: Optional[str] = Query(default=None),
    run_id: Optional[int] = Query(default=None)
):
    """
    Return complete trade ledger and detailed daily metrics for a single trading date.
    """
    norm_source = (source or "PAPER").upper()
    async with AsyncSessionLocal() as session:
        resolved_run_id = await validate_and_resolve_run_id(session, norm_source, run_id)
        trades = await fetch_unified_trades(
            session=session,
            source=norm_source,
            strategy_id=strategy_id,
            run_id=resolved_run_id,
            start_date=date,
            end_date=date
        )
        b_run = None
        if norm_source == "BACKTEST" and resolved_run_id:
            b_run = await session.get(BacktestRun, resolved_run_id)

    daily_map = PerformanceCalendarEngine.aggregate_trades_by_date(trades)
    day_stats = daily_map.get(date)

    sym = b_run.instrument_symbol if b_run and b_run.instrument_symbol else "NIFTY ATM CE"

    if not day_stats:
        from backend.app.analytics.nse_holidays import is_weekend, get_nse_holiday_name
        d_obj = datetime.strptime(date, "%Y-%m-%d").date()
        is_wknd = is_weekend(d_obj)
        holiday = get_nse_holiday_name(d_obj)

        if is_wknd:
            status = "WEEKEND"
            desc = "Exchange closed (Weekend)"
        elif holiday:
            status = "HOLIDAY"
            desc = f"Exchange Holiday ({holiday})"
        else:
            status = "NO_TRADE"
            desc = "No strategy entries generated on this trading day."

        return {
            "date": date,
            "has_trades": False,
            "status": status,
            "status_description": desc,
            "trades_count": 0,
            "net_pnl": 0.0,
            "gross_profit": 0.0,
            "gross_loss": 0.0,
            "total_charges": 0.0,
            "slippage_cost": 0.0,
            "wins": 0,
            "losses": 0,
            "win_rate": 0.0,
            "avg_holding_time": 0.0,
            "trades": [],
            "run_id": resolved_run_id,
            "symbol": sym
        }

    # Additional day metrics
    wins_list = [t for t in day_stats["trades"] if float(t.get("net_pnl") or 0.0) > 0]
    losses_list = [t for t in day_stats["trades"] if float(t.get("net_pnl") or 0.0) <= 0]
    avg_win = round(sum(float(t.get("net_pnl") or 0.0) for t in wins_list) / len(wins_list), 2) if wins_list else 0.0
    avg_loss = round(sum(float(t.get("net_pnl") or 0.0) for t in losses_list) / len(losses_list), 2) if losses_list else 0.0
    largest_win = round(max([float(t.get("net_pnl") or 0.0) for t in wins_list], default=0.0), 2)
    largest_loss = round(min([float(t.get("net_pnl") or 0.0) for t in losses_list], default=0.0), 2)

    return {
        "date": date,
        "has_trades": True,
        "status": "TRADED",
        "status_description": f"{day_stats['trades_count']} strategy trades executed",
        "trades_count": day_stats["trades_count"],
        "net_pnl": day_stats["net_pnl"],
        "gross_pnl": day_stats["gross_pnl"],
        "gross_profit": day_stats["gross_profit"],
        "gross_loss": day_stats["gross_loss"],
        "total_charges": day_stats["total_charges"],
        "slippage_cost": day_stats["slippage_cost"],
        "wins": day_stats["wins"],
        "losses": day_stats["losses"],
        "win_rate": day_stats["win_rate"],
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "largest_win": largest_win,
        "largest_loss": largest_loss,
        "avg_holding_time": day_stats["avg_holding_time"],
        "max_holding_time": day_stats["max_holding_time"],
        "min_holding_time": day_stats["min_holding_time"],
        "trades": day_stats["trades"],
        "run_id": resolved_run_id,
        "symbol": sym
    }


@router.get("/calendar/custom-range")
async def get_custom_range_analysis(
    start_date: str = Query(description="Start date YYYY-MM-DD"),
    end_date: str = Query(description="End date YYYY-MM-DD"),
    source: str = Query(default="PAPER"),
    strategy_id: Optional[str] = Query(default=None),
    execution_mode: Optional[str] = Query(default=None),
    instrument_symbol: Optional[str] = Query(default=None),
    run_id: Optional[int] = Query(default=None)
):
    """
    Return performance analytics across a custom date range with active filters.
    """
    norm_source = (source or "PAPER").upper()
    async with AsyncSessionLocal() as session:
        resolved_run_id = await validate_and_resolve_run_id(session, norm_source, run_id)
        trades = await fetch_unified_trades(
            session=session,
            source=norm_source,
            strategy_id=strategy_id,
            execution_mode=execution_mode,
            run_id=resolved_run_id,
            start_date=start_date,
            end_date=end_date,
            instrument_symbol=instrument_symbol
        )

    res = PerformanceCalendarEngine.get_custom_range_analysis(
        trades=trades,
        start_date=start_date,
        end_date=end_date
    )
    return {
        "status": "SUCCESS",
        "data_source": norm_source,
        "run_id": resolved_run_id,
        "strategy_filter": strategy_id or "ALL",
        "execution_mode_filter": execution_mode or "ALL",
        **res
    }


@router.get("/export/daily-trades-csv")
async def export_daily_trades_csv(
    date: str = Query(...),
    source: str = Query(default="PAPER"),
    strategy_id: Optional[str] = Query(default=None),
    run_id: Optional[int] = Query(default=None)
):
    """Export trade records for a specific day as CSV."""
    norm_source = (source or "PAPER").upper()
    async with AsyncSessionLocal() as session:
        resolved_run_id = await validate_and_resolve_run_id(session, norm_source, run_id)
        trades = await fetch_unified_trades(
            session=session,
            source=norm_source,
            strategy_id=strategy_id,
            run_id=resolved_run_id,
            start_date=date,
            end_date=date
        )

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Trade ID", "Source", "Strategy", "Entry Time (IST)", "Exit Time (IST)", "Hold (mins)",
        "Option Symbol", "Strike", "Expiry", "Execution Mode",
        "Entry Premium (₹)", "Configured SL (pts)", "Effective SL (pts)", "SL Trigger (₹)",
        "Configured Target (pts)", "Target Trigger (₹)", "Exit Premium (₹)", "Quantity",
        "Exit Reason", "Gross P&L (₹)", "Entry Charge (₹)", "Exit Charge (₹)", "Total Charges (₹)",
        "Slippage Cost (₹)", "Net P&L (₹)", "Ambiguity Flag", "Result"
    ])

    for t in trades:
        ent_dt = parse_trade_datetime_ist(t.get("entry_time"))
        ex_dt = parse_trade_datetime_ist(t.get("exit_time"))
        ent_str = ent_dt.strftime("%Y-%m-%d %H:%M:%S") if ent_dt else str(t.get("entry_time", ""))
        ex_str = ex_dt.strftime("%Y-%m-%d %H:%M:%S") if ex_dt else str(t.get("exit_time", ""))
        writer.writerow([
            t["id"],
            t["trade_source"],
            t["strategy_id"],
            ent_str,
            ex_str,
            t["holding_time_minutes"],
            t["option_symbol"],
            t["strike"],
            t["expiry"],
            t["execution_mode"],
            t["entry_price"],
            t["configured_sl_points"],
            t["effective_sl_points"],
            t["sl_trigger_price"],
            t["configured_target_points"],
            t["target_trigger_price"],
            t["exit_price"],
            t["quantity"],
            t["exit_reason"],
            t["gross_pnl"],
            t["entry_charge"],
            t["exit_charge"],
            t["total_charges"],
            t["slippage_cost"],
            t["net_pnl"],
            t["ambiguity_flag"] or "NO",
            "WIN" if t["is_win"] else "LOSS"
        ])

    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=nextrade_daily_trades_{date}.csv"}
    )


@router.get("/export/monthly-csv")
async def export_monthly_csv(
    year: int = Query(...),
    month: int = Query(...),
    source: str = Query(default="PAPER"),
    strategy_id: Optional[str] = Query(default=None),
    run_id: Optional[int] = Query(default=None)
):
    """Export monthly performance breakdown as CSV."""
    norm_source = (source or "PAPER").upper()
    async with AsyncSessionLocal() as session:
        resolved_run_id = await validate_and_resolve_run_id(session, norm_source, run_id)
        trades = await fetch_unified_trades(
            session=session,
            source=norm_source,
            strategy_id=strategy_id,
            run_id=resolved_run_id
        )

    res = PerformanceCalendarEngine.get_monthly_calendar(trades=trades, year=year, month=month)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Trading Date", "Weekday", "Trades Count", "Wins", "Losses", "Win Rate (%)",
        "Gross Profit (₹)", "Gross Loss (₹)", "Total Charges (₹)", "Slippage Cost (₹)",
        "Net P&L (₹)", "Status"
    ])

    for d in res["days"]:
        writer.writerow([
            d["date"],
            d["weekday_name"],
            d["trades_count"],
            d["wins"],
            d["losses"],
            d["win_rate"],
            d["gross_profit"],
            d["gross_loss"],
            d["total_charges"],
            d["slippage_cost"],
            d["net_pnl"],
            d["status"]
        ])

    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=nextrade_monthly_summary_{year}_{month:02d}.csv"}
    )


@router.get("/export/yearly-csv")
async def export_yearly_csv(
    year: int = Query(...),
    source: str = Query(default="PAPER"),
    strategy_id: Optional[str] = Query(default=None),
    run_id: Optional[int] = Query(default=None)
):
    """Export yearly performance summary as CSV."""
    norm_source = (source or "PAPER").upper()
    async with AsyncSessionLocal() as session:
        resolved_run_id = await validate_and_resolve_run_id(session, norm_source, run_id)
        trades = await fetch_unified_trades(
            session=session,
            source=norm_source,
            strategy_id=strategy_id,
            run_id=resolved_run_id
        )

    res = PerformanceCalendarEngine.get_yearly_overview(trades=trades, year=year)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Month #", "Month Name", "Trades Count", "Winning Days", "Losing Days",
        "Win Rate (%)", "Gross Profit (₹)", "Gross Loss (₹)", "Charges (₹)",
        "Slippage (₹)", "Net P&L (₹)", "Status"
    ])

    for m in res["months"]:
        writer.writerow([
            m["month"],
            m["month_name"],
            m["trades_count"],
            m["winning_days"],
            m["losing_days"],
            m["win_rate"],
            m["gross_profit"],
            m["gross_loss"],
            m["charges"],
            m["slippage"],
            m["net_pnl"],
            m["status"]
        ])

    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=nextrade_yearly_summary_{year}.csv"}
    )


@router.get("/export/custom-csv")
async def export_custom_range_csv(
    start_date: str = Query(...),
    end_date: str = Query(...),
    source: str = Query(default="PAPER"),
    strategy_id: Optional[str] = Query(default=None),
    run_id: Optional[int] = Query(default=None)
):
    """Export custom date range performance and trade ledger as CSV."""
    norm_source = (source or "PAPER").upper()
    async with AsyncSessionLocal() as session:
        resolved_run_id = await validate_and_resolve_run_id(session, norm_source, run_id)
        trades = await fetch_unified_trades(
            session=session,
            source=norm_source,
            strategy_id=strategy_id,
            run_id=resolved_run_id,
            start_date=start_date,
            end_date=end_date
        )

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Trade ID", "Source", "Strategy", "Entry Time (IST)", "Exit Time (IST)", "Hold (mins)",
        "Option Symbol", "Strike", "Expiry", "Execution Mode",
        "Entry Premium (₹)", "Configured SL (pts)", "Effective SL (pts)", "SL Trigger (₹)",
        "Configured Target (pts)", "Target Trigger (₹)", "Exit Premium (₹)", "Quantity",
        "Exit Reason", "Gross P&L (₹)", "Entry Charge (₹)", "Exit Charge (₹)", "Total Charges (₹)",
        "Slippage Cost (₹)", "Net P&L (₹)", "Ambiguity Flag", "Result"
    ])

    for t in trades:
        ent_dt = parse_trade_datetime_ist(t.get("entry_time"))
        ex_dt = parse_trade_datetime_ist(t.get("exit_time"))
        ent_str = ent_dt.strftime("%Y-%m-%d %H:%M:%S") if ent_dt else str(t.get("entry_time", ""))
        ex_str = ex_dt.strftime("%Y-%m-%d %H:%M:%S") if ex_dt else str(t.get("exit_time", ""))
        writer.writerow([
            t["id"],
            t["trade_source"],
            t["strategy_id"],
            ent_str,
            ex_str,
            t["holding_time_minutes"],
            t["option_symbol"],
            t["strike"],
            t["expiry"],
            t["execution_mode"],
            t["entry_price"],
            t["configured_sl_points"],
            t["effective_sl_points"],
            t["sl_trigger_price"],
            t["configured_target_points"],
            t["target_trigger_price"],
            t["exit_price"],
            t["quantity"],
            t["exit_reason"],
            t["gross_pnl"],
            t["entry_charge"],
            t["exit_charge"],
            t["total_charges"],
            t["slippage_cost"],
            t["net_pnl"],
            t["ambiguity_flag"] or "NO",
            "WIN" if t["is_win"] else "LOSS"
        ])

    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=nextrade_custom_trades_{start_date}_to_{end_date}.csv"}
    )


@router.get("/events")
async def get_system_events(limit: int = 50):
    """Retrieve system event logs (disconnects, reconnects, stale warnings, recovery)."""
    async with AsyncSessionLocal() as session:
        stmt = select(SystemEvent).order_by(desc(SystemEvent.id)).limit(limit)
        res = await session.execute(stmt)
        events = res.scalars().all()
        return [
            {
                "id": e.id,
                "event_type": e.event_type,
                "title": e.title,
                "message": e.message,
                "details": e.details_json,
                "created_at": e.created_at.isoformat()
            }
            for e in events
        ]
