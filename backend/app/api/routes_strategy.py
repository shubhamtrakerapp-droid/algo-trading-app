import json
import logging
from fastapi import APIRouter, HTTPException, Query, Body
from sqlalchemy import select, desc
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from backend.app.coordinator import coordinator
from backend.app.database import AsyncSessionLocal
from backend.app.models import StrategySignal
from backend.app.strategy.engine import StrategyEvaluationResult
from backend.app.strategy.ut_bot import UTBotEvaluation
from backend.app.strategy.supertrend_ema import SupertrendEMAEvaluation

logger = logging.getLogger("nextrade.api.strategy")
router = APIRouter(prefix="/api/strategy", tags=["Strategy"])


@router.get("/settings")
async def get_strategy_settings():
    """Retrieve active strategy rules and parameters (backward compatible)."""
    strat = coordinator.strategy_engine.get_active_strategy()
    cfg = dict(strat.get_config_dict())
    if "ema_fast" not in cfg:
        cfg["ema_fast"] = 9
        cfg["ema_medium"] = 21
        cfg["ema_slow"] = 50
        cfg["rsi_period"] = 14
        cfg["rsi_threshold"] = 50.0
    return cfg


@router.get("/profiles")
async def get_strategy_profiles():
    """Retrieve all available strategies and active status."""
    return {
        "active_strategy_id": coordinator.strategy_engine.active_strategy_id,
        "profiles": coordinator.strategy_engine.get_all_profiles()
    }


@router.post("/select")
async def select_active_strategy(payload: Dict[str, str] = Body(...)):
    """Switch active live paper trading strategy."""
    strat_id = payload.get("strategy_id")
    if not strat_id or strat_id not in ("EMA_RSI", "UT_BOT", "SUPERTREND_EMA", "SUPERTREND_EMA_SCALPER"):
        raise HTTPException(status_code=400, detail="Invalid strategy_id. Must be 'EMA_RSI', 'UT_BOT', or 'SUPERTREND_EMA'.")

    normalized = "SUPERTREND_EMA" if strat_id == "SUPERTREND_EMA_SCALPER" else strat_id
    coordinator.strategy_engine.set_active_strategy(normalized)
    return {
        "status": "SUCCESS",
        "active_strategy_id": coordinator.strategy_engine.active_strategy_id,
        "config": coordinator.strategy_engine.get_active_strategy().get_config_dict()
    }


@router.post("/configure")
async def configure_strategy(payload: Dict[str, Any] = Body(...)):
    """
    Configure strategy parameters.
    """
    strat_id = payload.get("strategy_id", coordinator.strategy_engine.active_strategy_id)
    if strat_id == "UT_BOT":
        ut = coordinator.strategy_engine.ut_bot_strategy
        if "key_value" in payload:
            ut.key_value = float(payload["key_value"])
        if "atr_period" in payload:
            ut.atr_period = int(payload["atr_period"])
        if "use_heikin_ashi" in payload:
            ut.use_heikin_ashi = bool(payload["use_heikin_ashi"])
        if "lots" in payload:
            ut.lots = int(payload["lots"])
            ut.quantity = ut.lots * ut.lot_size
        if "lot_size" in payload:
            ut.lot_size = int(payload["lot_size"])
            ut.quantity = ut.lots * ut.lot_size
        if "target_points" in payload:
            ut.target_points = float(payload["target_points"])
        if "stop_points" in payload:
            ut.stop_points = float(payload["stop_points"])
        if "max_loss_per_trade" in payload:
            val = payload["max_loss_per_trade"]
            ut.max_loss_per_trade = float(val) if val is not None and float(val) > 0 else None
        if "signal_source" in payload:
            ut.signal_source = str(payload["signal_source"])

        return {"status": "UPDATED", "strategy_id": "UT_BOT", "config": ut.get_config_dict()}

    elif strat_id in ("SUPERTREND_EMA", "SUPERTREND_EMA_SCALPER"):
        st = coordinator.strategy_engine.supertrend_ema_strategy
        if "atr_period" in payload:
            st.atr_period = int(payload["atr_period"])
        if "multiplier" in payload:
            st.multiplier = float(payload["multiplier"])
        if "ema_fast" in payload:
            st.ema_fast = int(payload["ema_fast"])
        if "ema_slow" in payload:
            st.ema_slow = int(payload["ema_slow"])
        if "lots" in payload:
            st.lots = int(payload["lots"])
            st.quantity = st.lots * st.lot_size
        if "lot_size" in payload:
            st.lot_size = int(payload["lot_size"])
            st.quantity = st.lots * st.lot_size
        if "target_net_profit" in payload:
            st.target_net_profit = float(payload["target_net_profit"])
        if "max_loss_per_trade" in payload:
            st.max_loss_per_trade = float(payload["max_loss_per_trade"])
        if "daily_profit_target" in payload:
            st.daily_profit_target = float(payload["daily_profit_target"])
        if "daily_loss_limit" in payload:
            st.daily_loss_limit = float(payload["daily_loss_limit"])
        return {"status": "UPDATED", "strategy_id": "SUPERTREND_EMA", "config": st.get_config_dict()}

    elif strat_id == "EMA_RSI":
        ema = coordinator.strategy_engine.ema_strategy
        if "lots" in payload:
            ema.lots = int(payload["lots"])
            ema.quantity = ema.lots * ema.lot_size
        if "target_points" in payload:
            ema.target_points = float(payload["target_points"])
        if "stop_points" in payload:
            ema.stop_points = float(payload["stop_points"])
        return {"status": "UPDATED", "strategy_id": "EMA_RSI", "config": ema.get_config_dict()}

    raise HTTPException(status_code=400, detail="Unknown strategy_id")


@router.get("/status")
async def get_strategy_status(strategy_id: Optional[str] = Query(None)):
    """
    Return live evaluation telemetry for the active strategy (or requested strategy).
    Provides actual evaluated values: ATR, Trailing Stop, Crossover, IST time, and action reasons.
    """
    strat_id = strategy_id or coordinator.strategy_engine.active_strategy_id

    if strat_id == "UT_BOT":
        ut = coordinator.strategy_engine.ut_bot_strategy
        last_eval: Optional[UTBotEvaluation] = ut.last_evaluation

        if not last_eval:
            return {
                "strategy_id": "UT_BOT",
                "strategy_name": "UT Bot ATM Option Strategy",
                "status": "INITIALIZING",
                "message": "Collecting completed bars for ATR & trailing stop warm-up...",
                "key_value": ut.key_value,
                "atr_period": ut.atr_period,
                "use_heikin_ashi": ut.use_heikin_ashi,
                "lots": ut.lots,
                "lot_size": ut.lot_size,
                "quantity": ut.quantity,
                "target_points": ut.target_points,
                "stop_points": ut.stop_points,
                "effective_stop_points": ut.calculate_effective_stop_points(),
                "max_loss_per_trade": ut.max_loss_per_trade,
                "signal_source": ut.signal_source,
                "signal": "NONE",
                "is_buy": False,
                "is_sell": False
            }

        return {
            "strategy_id": "UT_BOT",
            "strategy_name": "UT Bot ATM Option Strategy",
            "status": "ACTIVE",
            "timestamp": last_eval.timestamp.isoformat(),
            "candle_time": last_eval.candle_time.isoformat(),
            "time_ist": last_eval.time_ist,
            "symbol": last_eval.symbol,
            "src_price": last_eval.src_price,
            "atr": last_eval.atr,
            "n_loss": last_eval.n_loss,
            "trailing_stop": last_eval.trailing_stop,
            "prev_trailing_stop": last_eval.prev_trailing_stop,
            "pos": last_eval.pos,
            "prev_pos": last_eval.prev_pos,
            "above": last_eval.above,
            "below": last_eval.below,
            "signal": last_eval.signal,
            "is_buy": last_eval.is_buy,
            "is_sell": last_eval.is_sell,
            "session_valid": last_eval.session_valid,
            "action_reason": last_eval.action_reason,
            "lots": ut.lots,
            "lot_size": ut.lot_size,
            "quantity": ut.quantity,
            "target_points": ut.target_points,
            "stop_points": ut.stop_points,
            "effective_stop_points": ut.calculate_effective_stop_points(),
            "max_loss_per_trade": ut.max_loss_per_trade,
            "signal_source": ut.signal_source
        }

    elif strat_id in ("SUPERTREND_EMA", "SUPERTREND_EMA_SCALPER"):
        st = coordinator.strategy_engine.supertrend_ema_strategy
        last_eval_st: Optional[SupertrendEMAEvaluation] = st.last_evaluation
        daily_risk = await coordinator.paper_broker.get_daily_risk_status(
            strategy_id="SUPERTREND_EMA",
            daily_profit_target=st.daily_profit_target,
            daily_loss_limit=st.daily_loss_limit
        )
        pts = st.calculate_target_and_stop_points(
            quantity=st.quantity,
            roundtrip_charges=coordinator.paper_broker.charges_calc.entry_charge_per_order + coordinator.paper_broker.charges_calc.exit_charge_per_order,
            slippage_points=coordinator.paper_broker.slippage_points if coordinator.paper_broker.execution_mode == "REALISTIC" else 0.0
        )

        contract = coordinator.current_contract or {}
        active_pos = coordinator.paper_broker.active_position
        curr_premium = 0.0
        if coordinator.latest_option_tick:
            curr_premium = coordinator.latest_option_tick.last_price
        elif active_pos:
            curr_premium = active_pos["current_price"]

        base_res = {
            "strategy_id": "SUPERTREND_EMA",
            "strategy_name": "SUPERTREND EMA SCALPER",
            "atr_period": st.atr_period,
            "multiplier": st.multiplier,
            "ema_fast": st.ema_fast,
            "ema_slow": st.ema_slow,
            "lots": st.lots,
            "lot_size": st.lot_size,
            "quantity": st.quantity,
            "target_net_profit": st.target_net_profit,
            "max_loss_per_trade": st.max_loss_per_trade,
            "daily_profit_target": st.daily_profit_target,
            "daily_loss_limit": st.daily_loss_limit,
            "roundtrip_charges": st.roundtrip_charges,
            "target_points": pts["target_points"],
            "stop_points": pts["stop_points"],
            "theoretical_target_pts": pts["theoretical_target_pts"],
            "theoretical_stop_pts": pts["theoretical_stop_pts"],
            "contract_symbol": contract.get("symbol", "NIFTY ATM CE"),
            "current_premium": curr_premium,
            "daily_risk": daily_risk,
            "active_position": active_pos
        }

        if not last_eval_st:
            return {
                **base_res,
                "status": "INITIALIZING",
                "message": "Collecting 1-minute completed bars for Supertrend & EMA warm-up...",
                "trend": "NEUTRAL",
                "supertrend": 0.0,
                "supertrend_direction": 1,
                "supertrend_upper": 0.0,
                "supertrend_lower": 0.0,
                "supertrend_atr": 0.0,
                "ema_9": 0.0,
                "ema_21": 0.0,
                "signal": "NONE",
                "is_buy_ce": False,
                "is_buy_pe": False,
                "is_buy": False,
                "target_contract_type": "NONE",
                "action_reason": "Waiting for completed bars"
            }

        return {
            **base_res,
            "status": "ACTIVE",
            "timestamp": last_eval_st.timestamp.isoformat(),
            "candle_time": last_eval_st.candle_time.isoformat(),
            "time_ist": last_eval_st.time_ist,
            "underlying_price": last_eval_st.underlying_price,
            "supertrend": last_eval_st.supertrend,
            "supertrend_direction": last_eval_st.supertrend_direction,
            "supertrend_upper": last_eval_st.supertrend_upper,
            "supertrend_lower": last_eval_st.supertrend_lower,
            "supertrend_atr": last_eval_st.supertrend_atr,
            "trend": last_eval_st.trend_str,
            "ema_9": last_eval_st.ema_9,
            "ema_21": last_eval_st.ema_21,
            "c_st_bull": last_eval_st.c_st_bull,
            "c_ema_bull": last_eval_st.c_ema_bull,
            "c_close_bull": last_eval_st.c_close_bull,
            "c_st_bear": last_eval_st.c_st_bear,
            "c_ema_bear": last_eval_st.c_ema_bear,
            "c_close_bear": last_eval_st.c_close_bear,
            "signal": last_eval_st.signal,
            "is_buy_ce": last_eval_st.is_buy_ce,
            "is_buy_pe": last_eval_st.is_buy_pe,
            "is_buy": last_eval_st.is_buy,
            "target_contract_type": last_eval_st.target_contract_type,
            "action_reason": last_eval_st.action_reason
        }

    else:
        ema = coordinator.strategy_engine.ema_strategy
        last_eval_ema: Optional[StrategyEvaluationResult] = ema.last_evaluation
        if not last_eval_ema:
            return {
                "strategy_id": "EMA_RSI",
                "strategy_name": "NIFTY 1M EMA+RSI ATM CE",
                "status": "INITIALIZING",
                "message": "Collecting 1-minute completed bars for indicator warm-up...",
                "condition_1": False,
                "condition_2": False,
                "condition_3": False,
                "condition_4": False,
                "signal": "NONE",
                "is_buy": False
            }

        return {
            "strategy_id": "EMA_RSI",
            "strategy_name": "NIFTY 1M EMA+RSI ATM CE",
            "status": "ACTIVE",
            "timestamp": last_eval_ema.timestamp.isoformat(),
            "candle_time": last_eval_ema.candle_time.isoformat(),
            "time_ist": last_eval_ema.time_ist,
            "underlying_price": last_eval_ema.underlying_price,
            "ema_9": last_eval_ema.ema_9,
            "ema_21": last_eval_ema.ema_21,
            "ema_50": last_eval_ema.ema_50,
            "rsi_14": last_eval_ema.rsi_14,
            "condition_1": last_eval_ema.condition_1,
            "condition_2": last_eval_ema.condition_2,
            "condition_3": last_eval_ema.condition_3,
            "condition_4": last_eval_ema.condition_4,
            "signal": last_eval_ema.signal,
            "is_buy": last_eval_ema.is_buy
        }


@router.get("/signals")
async def get_signals(
    strategy_id: Optional[str] = Query(None, description="Filter signals by strategy_id"),
    limit: int = 50
):
    """Retrieve historical signals generated by strategies."""
    async with AsyncSessionLocal() as session:
        stmt = select(StrategySignal).order_by(desc(StrategySignal.id))
        if strategy_id:
            stmt = stmt.where(StrategySignal.strategy_id == strategy_id)
        stmt = stmt.limit(limit)

        res = await session.execute(stmt)
        signals = res.scalars().all()
        return [
            {
                "id": s.id,
                "strategy_id": s.strategy_id,
                "timestamp": s.timestamp.isoformat(),
                "candle_time": s.candle_time.isoformat(),
                "underlying_price": s.underlying_price,
                "atr": s.atr,
                "trailing_stop": s.trailing_stop,
                "ema_9": s.ema_9,
                "ema_21": s.ema_21,
                "ema_50": s.ema_50,
                "rsi_14": s.rsi_14,
                "condition_1": s.condition_1,
                "condition_2": s.condition_2,
                "condition_3": s.condition_3,
                "condition_4": s.condition_4,
                "signal_type": s.signal_type,
                "executed": s.executed,
                "notes": s.notes
            }
            for s in signals
        ]
