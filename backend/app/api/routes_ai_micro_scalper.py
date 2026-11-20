import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy import select, desc

from backend.app.coordinator import coordinator
from backend.app.schemas.schemas import (
    AIMicroScalperConfigUpdateRequest,
    AIMicroScalperBacktestRequest,
)
from backend.app.strategy.ai_micro_scalper.strategy import AIMicroScalperStrategy
from backend.app.strategy.ai_micro_scalper.backtest import AIMicroScalperBacktestEngine
from backend.app.backtest.data_loader import BacktestDataLoader
from backend.app.database import AsyncSessionLocal
from backend.app.models import PaperTrade, StrategyDailyRisk, StrategyConfigVersion

logger = logging.getLogger("nextrade.api.ai_micro_scalper")

router = APIRouter(prefix="/api/ai-micro-scalper", tags=["AI Micro-Scalper"])


async def _record_config_version(strategy_id: str, config: dict, summary: str = "Configuration updated"):
    try:
        async with AsyncSessionLocal() as session:
            stmt = select(StrategyConfigVersion.version).where(
                StrategyConfigVersion.strategy_id == strategy_id
            ).order_by(desc(StrategyConfigVersion.version)).limit(1)
            res = await session.execute(stmt)
            latest_v = res.scalar_one_or_none() or 0
            ver = StrategyConfigVersion(
                strategy_id=strategy_id,
                version=latest_v + 1,
                config_json=json.dumps(config, default=str),
                change_summary=summary,
                changed_by="user"
            )
            session.add(ver)
            await session.commit()
    except Exception as e:
        logger.error(f"Error persisting strategy config version: {e}")


@router.get("/status")
async def get_ai_micro_scalper_status():
    """
    Get live status of AI MICRO-SCALPER V1.
    STRICTLY PAPER TRADING ONLY.
    Returns:
      - Active status
      - Operating mode (PAPER_TRADING_ONLY)
      - Current virtual capital
      - Daily risk status and limits
      - Latest evaluation & agent voting breakdown
      - Current active position (if any)
      - Today's closed trades
    """
    is_active = (coordinator.strategy_engine.active_strategy_id == "AI_MICRO_SCALPER_V1")
    ai_strat = coordinator.strategy_engine.ai_micro_scalper_strategy

    daily_risk = await coordinator.paper_broker.get_daily_risk_status(
        strategy_id="AI_MICRO_SCALPER_V1",
        daily_profit_target=ai_strat.daily_profit_target,
        daily_loss_limit=ai_strat.daily_loss_limit,
    )

    last_eval = ai_strat.last_evaluation
    last_eval_dict = None
    if last_eval:
        last_eval_dict = {
            "candle_time": last_eval.candle_time.isoformat(),
            "symbol": last_eval.symbol,
            "underlying_price": last_eval.underlying_price,
            "time_ist": last_eval.time_ist,
            "signal": last_eval.signal,
            "is_buy_ce": last_eval.is_buy_ce,
            "is_buy_pe": last_eval.is_buy_pe,
            "is_buy": last_eval.is_buy,
            "target_contract_type": last_eval.target_contract_type,
            "contract_symbol": last_eval.contract_symbol,
            "contract_strike": last_eval.contract_strike,
            "contract_premium": last_eval.contract_premium,
            "is_itm": last_eval.is_itm,
            "spread": last_eval.spread,
            "lots": last_eval.lots,
            "lot_size": last_eval.lot_size,
            "quantity": last_eval.quantity,
            "target_points": last_eval.target_points,
            "stop_points": last_eval.stop_points,
            "capital_required": last_eval.capital_required,
            "capital_ratio": last_eval.capital_ratio,
            "agent_votes": last_eval.agent_votes,
            "action_reason": last_eval.action_reason,
            "session_valid": last_eval.session_valid,
            "ema_5m_20": last_eval.ema_5m_20,
            "ema_5m_50": last_eval.ema_5m_50,
            "vwap_5m": last_eval.vwap_5m,
            "adx_5m": last_eval.adx_5m,
            "ema_1m_9": last_eval.ema_1m_9,
            "ema_1m_20": last_eval.ema_1m_20,
            "vwap_1m": last_eval.vwap_1m,
            "rsi_1m": last_eval.rsi_1m,
            "atr_1m": last_eval.atr_1m,
        }

    # Fetch today's paper trades for this strategy
    today_trades: List[Dict[str, Any]] = []
    try:
        async with AsyncSessionLocal() as session:
            stmt = (
                select(PaperTrade)
                .where(PaperTrade.strategy_id == "AI_MICRO_SCALPER_V1")
                .order_by(PaperTrade.exit_time.desc())
                .limit(20)
            )
            res = await session.execute(stmt)
            trades_db = res.scalars().all()
            for t in trades_db:
                today_trades.append({
                    "id": t.id,
                    "symbol": t.symbol,
                    "entry_time": t.entry_time.isoformat(),
                    "exit_time": t.exit_time.isoformat(),
                    "entry_price": t.entry_price,
                    "exit_price": t.exit_price,
                    "quantity": t.quantity,
                    "gross_pnl": t.gross_pnl,
                    "total_charges": t.total_charges,
                    "net_pnl": t.net_pnl,
                    "exit_reason": t.exit_reason,
                    "is_win": t.is_win,
                })
    except Exception as e:
        logger.error(f"Error reading paper trades: {e}")

    active_pos = None
    if coordinator.paper_broker.active_position:
        pos = coordinator.paper_broker.active_position
        if pos.get("strategy_id") == "AI_MICRO_SCALPER_V1":
            active_pos = pos

    return {
        "strategy_id": "AI_MICRO_SCALPER_V1",
        "strategy_name": "NEXTRADE AI MICRO-SCALPER V1",
        "is_active": is_active,
        "operating_mode": "PAPER_TRADING_ONLY",
        "current_capital": coordinator.paper_broker.get_strategy_cash("AI_MICRO_SCALPER_V1"),
        "initial_capital": ai_strat.initial_capital,
        "daily_risk": daily_risk,
        "last_evaluation": last_eval_dict,
        "active_position": active_pos,
        "today_trades": today_trades,
    }


@router.get("/config")
async def get_ai_micro_scalper_config():
    """Get current configuration of AI MICRO-SCALPER V1."""
    ai_strat = coordinator.strategy_engine.ai_micro_scalper_strategy
    return ai_strat.get_config_dict()


@router.post("/config")
async def update_ai_micro_scalper_config(
    req: AIMicroScalperConfigUpdateRequest,
):
    """Update editable settings for AI MICRO-SCALPER V1."""
    ai_strat = coordinator.strategy_engine.ai_micro_scalper_strategy

    if req.initial_capital is not None:
        ai_strat.initial_capital = float(req.initial_capital)
    if req.lots is not None:
        ai_strat.lots = int(req.lots)
        ai_strat.quantity = ai_strat.lots * ai_strat.lot_size
    if req.lot_size is not None:
        ai_strat.lot_size = int(req.lot_size)
        ai_strat.quantity = ai_strat.lots * ai_strat.lot_size
    if req.preferred_premium_min is not None:
        ai_strat.preferred_premium_min = float(req.preferred_premium_min)
        ai_strat.option_selector.preferred_premium_min = ai_strat.preferred_premium_min
    if req.preferred_premium_max is not None:
        ai_strat.preferred_premium_max = float(req.preferred_premium_max)
        ai_strat.option_selector.preferred_premium_max = ai_strat.preferred_premium_max
    if req.target_net_profit is not None:
        ai_strat.target_net_profit = float(req.target_net_profit)
    if req.max_loss_per_trade is not None:
        ai_strat.max_loss_per_trade = float(req.max_loss_per_trade)
    if req.daily_profit_target is not None:
        ai_strat.daily_profit_target = float(req.daily_profit_target)
    if req.daily_loss_limit is not None:
        ai_strat.daily_loss_limit = float(req.daily_loss_limit)
    if req.max_trades_per_day is not None:
        ai_strat.max_trades_per_day = int(req.max_trades_per_day)
    if req.max_consecutive_losses is not None:
        ai_strat.max_consecutive_losses = int(req.max_consecutive_losses)
    if req.max_holding_time_minutes is not None:
        ai_strat.max_holding_time_minutes = int(req.max_holding_time_minutes)
    if req.roundtrip_charges is not None:
        ai_strat.roundtrip_charges = float(req.roundtrip_charges)
    if req.max_spread is not None:
        ai_strat.max_spread = float(req.max_spread)
        ai_strat.option_selector.max_bid_ask_spread = ai_strat.max_spread
    if req.slippage_points is not None:
        ai_strat.slippage_points = float(req.slippage_points)

    logger.info("AI MICRO-SCALPER V1 configuration updated.")
    await _record_config_version("AI_MICRO_SCALPER_V1", ai_strat.get_config_dict())
    return {
        "status": "SUCCESS",
        "message": "Configuration updated successfully.",
        "config": ai_strat.get_config_dict(),
    }


@router.post("/control")
async def control_ai_micro_scalper(
    action: str,  # "START", "PAUSE", "SWITCH"
):
    """Control strategy execution state (Strictly PAPER TRADING ONLY)."""
    action_upper = action.upper()
    if action_upper in ("START", "SWITCH", "ACTIVATE"):
        coordinator.strategy_engine.set_active_strategy("AI_MICRO_SCALPER_V1")
        return {"status": "SUCCESS", "active_strategy": "AI_MICRO_SCALPER_V1"}
    elif action_upper in ("PAUSE", "STOP", "DEACTIVATE"):
        coordinator.strategy_engine.set_active_strategy("UT_BOT")
        return {"status": "SUCCESS", "active_strategy": "UT_BOT"}
    else:
        raise HTTPException(status_code=400, detail=f"Unknown control action: {action}")


@router.post("/emergency-close")
async def emergency_close_ai_micro_scalper():
    """
    Emergency Close any active paper position for AI Micro-Scalper.
    STRICTLY PAPER TRADING ONLY.
    """
    pos = coordinator.paper_broker.active_position
    if not pos:
        return {"status": "NO_ACTIVE_POSITION", "message": "No open paper position to close."}

    exit_price = pos["current_price"]
    if coordinator.latest_option_tick:
        exit_price = coordinator.latest_option_tick.last_price

    res = await coordinator.paper_broker.manual_close(
        exit_price=exit_price,
        reason="EMERGENCY_MANUAL_CLOSE",
    )
    coordinator.option_selector.set_position_open_state(False)
    return {
        "status": "CLOSED",
        "message": "Position closed successfully in paper trading.",
        "trade": res,
    }


@router.post("/backtest")
async def run_ai_micro_scalper_backtest(
    req: AIMicroScalperBacktestRequest,
):
    """
    Execute dedicated historical backtest of AI MICRO-SCALPER V1.
    """
    kotak_ad = coordinator.kotak_adapter if hasattr(coordinator, "kotak_adapter") else None
    loader = BacktestDataLoader(kotak_adapter=kotak_ad, allow_offline_cache=True)

    requested_source = "REAL_MARKET" if req.data_source in ("REAL_MARKET", "KOTAK_NEO_HISTORICAL") else "SYNTHETIC_TEST"
    effective_days = req.duration_days or 5

    try:
        nifty_candles, option_candles, metadata = await loader.load_dataset(
            symbol="NIFTY ATM CE",
            timeframe_minutes=1,
            days=effective_days,
            start_date=req.start_date,
            end_date=req.end_date,
            data_source=requested_source,
        )
    except Exception as e:
        logger.error(f"Failed to load candles for AI Micro-Scalper backtest: {e}")
        raise HTTPException(status_code=400, detail=f"Data loading error: {str(e)}")

    engine = AIMicroScalperBacktestEngine(
        initial_capital=req.initial_capital,
        lots=req.lots,
        lot_size=req.lot_size,
        target_net_profit=req.target_net_profit,
        max_loss_per_trade=req.max_loss_per_trade,
        daily_profit_target=req.daily_profit_target,
        daily_loss_limit=req.daily_loss_limit,
        max_trades_per_day=req.max_trades_per_day,
        max_consecutive_losses=req.max_consecutive_losses,
        max_holding_time_minutes=req.max_holding_time_minutes,
        roundtrip_charges=req.roundtrip_charges,
        slippage_points=req.slippage_points,
        execution_mode=req.execution_mode,
    )

    results = await engine.run_backtest(
        nifty_candles=nifty_candles,
        option_candles_ce=option_candles,
        option_candles_pe=option_candles,
        data_source=req.data_source,
        execution_mode=req.execution_mode,
        split_type=req.split_type,
        save_to_db=True,
    )

    if "error" in results:
        raise HTTPException(status_code=400, detail=results["error"])

    return results


@router.post("/ablation")
async def run_ai_micro_scalper_ablation(
    req: AIMicroScalperBacktestRequest,
):
    """
    Run Agent Performance Comparison / Ablation (A through G) on AI MICRO-SCALPER V1.
    """
    kotak_ad = coordinator.kotak_adapter if hasattr(coordinator, "kotak_adapter") else None
    loader = BacktestDataLoader(kotak_adapter=kotak_ad, allow_offline_cache=True)

    requested_source = "REAL_MARKET" if req.data_source in ("REAL_MARKET", "KOTAK_NEO_HISTORICAL") else "SYNTHETIC_TEST"
    effective_days = req.duration_days or 5

    try:
        nifty_candles, option_candles, metadata = await loader.load_dataset(
            symbol="NIFTY ATM CE",
            timeframe_minutes=1,
            days=effective_days,
            start_date=req.start_date,
            end_date=req.end_date,
            data_source=requested_source,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Data loading error: {str(e)}")

    engine = AIMicroScalperBacktestEngine(
        initial_capital=req.initial_capital,
        lots=req.lots,
        lot_size=req.lot_size,
        target_net_profit=req.target_net_profit,
        max_loss_per_trade=req.max_loss_per_trade,
        daily_profit_target=req.daily_profit_target,
        daily_loss_limit=req.daily_loss_limit,
        max_trades_per_day=req.max_trades_per_day,
        max_consecutive_losses=req.max_consecutive_losses,
        max_holding_time_minutes=req.max_holding_time_minutes,
        roundtrip_charges=req.roundtrip_charges,
        slippage_points=req.slippage_points,
        execution_mode=req.execution_mode,
    )

    ablation_results = await engine.run_ablation_comparison(
        nifty_candles=nifty_candles,
        option_candles_ce=option_candles,
        option_candles_pe=option_candles,
        data_source=req.data_source,
        execution_mode=req.execution_mode,
    )

    return ablation_results
