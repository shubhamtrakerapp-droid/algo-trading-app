import asyncio
import io
import csv
import json
from fastapi import APIRouter, HTTPException, Response
from sqlalchemy import select, desc, delete
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from backend.app.coordinator import coordinator
from backend.app.database import AsyncSessionLocal
from backend.app.models import (
    PaperPosition,
    PaperTrade,
    PaperOrder,
    StrategySignal,
    SystemEvent,
    BacktestRun,
    BacktestTrade,
    ChargeSetting,
    AutoExitSetting,
    StrategyVirtualAccount,
    StrategyDailyRisk
)
from backend.app.schemas.schemas import (
    ManualTradeRequest,
    ChargeSettingsRequest,
    ChargeSettingsResponse,
    AutoExitSettingsSchema,
    AutoExitSettingsUpdateRequest
)

router = APIRouter(prefix="/api/paper", tags=["Paper Trading"])


@router.get("/status")
async def get_paper_status():
    """Return virtual capital, realized/unrealized P&L, and open position state."""
    async with AsyncSessionLocal() as session:
        # Fetch closed trades to compute daily P&L
        stmt = select(PaperTrade).order_by(desc(PaperTrade.id))
        res = await session.execute(stmt)
        trades = res.scalars().all()

        realized_pnl = round(sum(t.net_pnl for t in trades), 2)
        total_trades = len(trades)
        wins = sum(1 for t in trades if t.is_win)
        win_rate = round((wins / total_trades) * 100, 2) if total_trades > 0 else 0.0

    pos = coordinator.paper_broker.active_position
    unrealized_pnl = pos["net_pnl"] if pos else 0.0

    active_strat = coordinator.strategy_engine.get_active_strategy()
    strat_cfg = active_strat.get_config_dict()

    return {
        "initial_capital": coordinator.paper_broker.initial_capital,
        "cash_balance": coordinator.paper_broker.cash_balance,
        "portfolio_value": round(coordinator.paper_broker.cash_balance + unrealized_pnl, 2),
        "realized_pnl": realized_pnl,
        "unrealized_pnl": unrealized_pnl,
        "daily_pnl": round(realized_pnl + unrealized_pnl, 2),
        "total_trades": total_trades,
        "win_rate": win_rate,
        "active_position": pos,
        "active_strategy_id": coordinator.strategy_engine.active_strategy_id,
        "active_strategy_config": strat_cfg,
        "default_lots": getattr(active_strat, "lots", coordinator.paper_broker.default_lots),
        "max_loss_per_trade": getattr(active_strat, "max_loss_per_trade", coordinator.paper_broker.max_loss_per_trade),
        "target_points": getattr(active_strat, "target_points", coordinator.paper_broker.target_points),
        "stop_points": getattr(active_strat, "stop_points", coordinator.paper_broker.stop_points),
        "force_exit_time_ist": coordinator.paper_broker.auto_close_time_ist,
        "auto_exit_settings": coordinator.paper_broker.get_auto_exit_status_dict()
    }


@router.get("/ledgers")
async def get_strategy_ledgers():
    """Return all strategy-isolated virtual accounts and live ledger balances."""
    broker = coordinator.paper_broker
    ledgers_data = {}
    for sid, ledger in broker.ledgers.items():
        ledgers_data[sid] = {
            "strategy_id": ledger.strategy_id,
            "strategy_name": ledger.strategy_name,
            "initial_capital": ledger.initial_capital,
            "available_cash": ledger.available_cash,
            "reserved_capital": ledger.reserved_capital,
            "total_equity": ledger.total_equity,
            "realized_gross_pnl": ledger.realized_gross_pnl,
            "realized_net_pnl": ledger.realized_net_pnl,
            "total_charges": ledger.total_charges,
            "slippage_cost": ledger.slippage_cost,
            "capital_deployment_cap_pct": ledger.capital_deployment_cap_pct,
            "max_deployable_capital": round(ledger.available_cash * (ledger.capital_deployment_cap_pct / 100.0), 2),
            "daily_profit_target": ledger.daily_profit_target,
            "daily_loss_limit": ledger.daily_loss_limit,
            "max_trades_per_day": ledger.max_trades_per_day,
            "max_consecutive_losses": ledger.max_consecutive_losses,
            "risk_limits_enabled": ledger.risk_limits_enabled,
            "has_open_position": ledger.active_position is not None,
        }
    return {"ledgers": ledgers_data}


@router.get("/ledgers/{strategy_id}")
async def get_strategy_ledger_detail(strategy_id: str):
    """Return specific strategy virtual ledger and today's risk status."""
    broker = coordinator.paper_broker
    ledger = broker.get_strategy_ledger(strategy_id)
    daily_risk = await broker.get_daily_risk_status(strategy_id=strategy_id)
    return {
        "strategy_id": ledger.strategy_id,
        "strategy_name": ledger.strategy_name,
        "initial_capital": ledger.initial_capital,
        "available_cash": ledger.available_cash,
        "reserved_capital": ledger.reserved_capital,
        "total_equity": ledger.total_equity,
        "realized_gross_pnl": ledger.realized_gross_pnl,
        "realized_net_pnl": ledger.realized_net_pnl,
        "total_charges": ledger.total_charges,
        "slippage_cost": ledger.slippage_cost,
        "capital_deployment_cap_pct": ledger.capital_deployment_cap_pct,
        "max_deployable_capital": round(ledger.available_cash * (ledger.capital_deployment_cap_pct / 100.0), 2),
        "risk_limits_enabled": ledger.risk_limits_enabled,
        "active_position": ledger.active_position,
        "daily_risk": daily_risk
    }


@router.get("/position")
async def get_open_position():
    """Return current open position or null."""
    return {"position": coordinator.paper_broker.active_position}


@router.post("/order")
async def place_manual_paper_order(req: ManualTradeRequest):
    """
    Manually place a simulated paper trade order (for testing or manual control).
    Enforces same risk and position rules.
    """
    if coordinator.paper_broker.active_position:
        raise HTTPException(status_code=400, detail="An open paper position already exists.")

    spot = coordinator.latest_nifty_tick.last_price if coordinator.latest_nifty_tick else 24500.0
    contract = coordinator.current_contract

    premium = 145.0
    if coordinator.latest_option_tick:
        premium = coordinator.latest_option_tick.last_price

    active_strat = coordinator.strategy_engine.get_active_strategy()
    res = await coordinator.paper_broker.execute_buy(
        contract=contract,
        current_premium=premium,
        underlying_price=spot,
        lots=req.lots,
        strategy_id=coordinator.strategy_engine.active_strategy_id,
        strategy_config=json.dumps(active_strat.get_config_dict()),
        target_points=getattr(active_strat, "target_points", None),
        stop_points=getattr(active_strat, "stop_points", None),
        max_loss_per_trade=getattr(active_strat, "max_loss_per_trade", None)
    )
    if not res:
        raise HTTPException(status_code=400, detail="Order could not be executed (check session cutoff time).")

    coordinator.option_selector.set_position_open_state(True)
    return {"status": "FILLED", "position": res}


@router.post("/close")
async def close_position():
    """Manually square off active paper position."""
    if not coordinator.paper_broker.active_position:
        raise HTTPException(status_code=400, detail="No active position to close.")

    curr_premium = coordinator.latest_option_tick.last_price if coordinator.latest_option_tick else coordinator.paper_broker.active_position["current_price"]
    res = await coordinator.paper_broker.manual_close(curr_premium)
    coordinator.option_selector.set_position_open_state(False)

    return {"status": "CLOSED", "trade": res}


@router.post("/reset")
async def reset_paper_data():
    """Clear all paper trading positions, orders, trades, signals, and backtest records."""
    async with AsyncSessionLocal() as session:
        await session.execute(delete(PaperTrade))
        await session.execute(delete(PaperOrder))
        await session.execute(delete(PaperPosition))
        await session.execute(delete(StrategySignal))
        await session.execute(delete(SystemEvent))
        await session.execute(delete(BacktestTrade))
        await session.execute(delete(BacktestRun))
        await session.commit()

    coordinator.paper_broker.reset()
    coordinator.option_selector.set_position_open_state(False)

    # Broadcast reset to WebSocket clients
    asyncio.create_task(coordinator.broadcast({
        "type": "PAPER_UPDATE",
        "data": {
            "cash_balance": coordinator.paper_broker.cash_balance,
            "realized_pnl": 0.0,
            "unrealized_pnl": 0.0,
            "daily_pnl": 0.0,
            "total_trades": 0,
            "win_rate": 0.0,
            "active_position": None
        }
    }))

    return {
        "status": "RESET_SUCCESS",
        "message": "All demo paper trades, orders, positions, signals, and backtest data have been removed.",
        "initial_capital": coordinator.paper_broker.initial_capital,
        "cash_balance": coordinator.paper_broker.cash_balance
    }


@router.get("/trades")
async def get_paper_trades(
    strategy_id: Optional[str] = None,
    limit: int = 100
):
    """Return historical closed paper trades, optionally filtered by strategy_id."""
    async with AsyncSessionLocal() as session:
        stmt = select(PaperTrade).order_by(desc(PaperTrade.id))
        if strategy_id:
            stmt = stmt.where(PaperTrade.strategy_id == strategy_id)
        stmt = stmt.limit(limit)

        res = await session.execute(stmt)
        trades = res.scalars().all()
        return [
            {
                "id": t.id,
                "strategy_id": getattr(t, "strategy_id", "EMA_RSI"),
                "strategy_config": getattr(t, "strategy_config", None),
                "position_id": t.position_id,
                "underlying_symbol": t.underlying_symbol,
                "underlying_price_at_entry": t.underlying_price_at_entry,
                "option_symbol": t.option_symbol,
                "strike": t.strike,
                "expiry": t.expiry,
                "entry_time": t.entry_time.isoformat(),
                "exit_time": t.exit_time.isoformat(),
                "entry_price": t.entry_price,
                "exit_price": t.exit_price,
                "quantity": t.quantity,
                "target_price": t.target_price,
                "stop_price": t.stop_price,
                "configured_sl_points": getattr(t, "configured_sl_points", None),
                "configured_target_points": getattr(t, "configured_target_points", None),
                "effective_sl_points": getattr(t, "effective_sl_points", None),
                "effective_target_points": getattr(t, "effective_target_points", None),
                "sl_trigger_price": getattr(t, "sl_trigger_price", None),
                "target_trigger_price": getattr(t, "target_trigger_price", None),
                "slippage_cost": getattr(t, "slippage_cost", 0.0),
                "execution_mode": getattr(t, "execution_mode", "TRIGGER_PRICE"),
                "is_ambiguous": getattr(t, "is_ambiguous", False),
                "ambiguity_flag": getattr(t, "ambiguity_flag", None),
                "holding_time_minutes": getattr(t, "holding_time_minutes", 0),
                "exit_reason": t.exit_reason,
                "gross_pnl": t.gross_pnl,
                "entry_charge": getattr(t, "entry_charge", 10.0),
                "exit_charge": getattr(t, "exit_charge", 10.0),
                "charges_brokerage": t.charges_brokerage,
                "charges_stt": t.charges_stt,
                "charges_exchange": t.charges_exchange,
                "charges_gst": t.charges_gst,
                "charges_sebi": t.charges_sebi,
                "charges_stamp": t.charges_stamp,
                "total_charges": t.total_charges,
                "net_pnl": t.net_pnl,
                "is_win": t.is_win
            }
            for t in trades
        ]


@router.get("/charges-settings", response_model=ChargeSettingsResponse)
async def get_charges_settings():
    """Retrieve current configured paper trading charges."""
    entry_chg = coordinator.paper_broker.charges_calc.entry_charge_per_order
    exit_chg = coordinator.paper_broker.charges_calc.exit_charge_per_order
    return {
        "entry_charge_per_order": entry_chg,
        "exit_charge_per_order": exit_chg,
        "total_roundtrip_charge": round(entry_chg + exit_chg, 2),
        "status": "SUCCESS"
    }


@router.post("/charges-settings", response_model=ChargeSettingsResponse)
async def update_charges_settings(req: ChargeSettingsRequest):
    """
    Update paper trading charges settings and persist in database.
    Applies to all new simulated orders without silently altering historical trades.
    """
    res = await coordinator.paper_broker.update_charges_settings(
        entry_charge=req.entry_charge_per_order,
        exit_charge=req.exit_charge_per_order
    )
    return {
        **res,
        "status": "SUCCESS",
        "message": f"Paper charges updated: Entry ₹{req.entry_charge_per_order}, Exit ₹{req.exit_charge_per_order} (Total: ₹{res['total_roundtrip_charge']})"
    }


@router.get("/auto-exit-settings", response_model=AutoExitSettingsSchema)
async def get_auto_exit_settings():
    """Retrieve current Auto Exit configuration, countdown timer, and execution status."""
    return coordinator.paper_broker.get_auto_exit_status_dict()


@router.post("/auto-exit-settings", response_model=AutoExitSettingsSchema)
async def update_auto_exit_settings(req: AutoExitSettingsUpdateRequest):
    """Update Auto Exit configuration and persist to database."""
    res = await coordinator.paper_broker.update_auto_exit_settings(
        enabled=req.enabled,
        auto_close_time=req.auto_close_time,
        apply_to_all_strategies=req.apply_to_all_strategies,
        close_profitable=req.close_profitable,
        close_losing=req.close_losing
    )
    return res


@router.post("/auto-exit-trigger")
async def trigger_auto_exit(force_now: bool = True):
    """
    Manually trigger or test Auto Exit on all active open paper positions.
    Useful for testing execution flow and verifying position square-off.
    """
    latest_price = coordinator.latest_option_tick.last_price if coordinator.latest_option_tick else None
    trade = await coordinator.paper_broker.check_and_run_auto_close(
        now=datetime.now(timezone.utc),
        latest_option_price=latest_price,
        is_feed_stale=coordinator.is_stale,
        is_feed_connected=bool(coordinator.active_adapter.is_connected),
        strategy_id=coordinator.strategy_engine.active_strategy_id,
        force_now=force_now
    )
    if trade:
        coordinator.option_selector.set_position_open_state(False)
        return {
            "status": "CLOSED",
            "trade": {
                "position_id": trade.position_id,
                "symbol": trade.symbol,
                "exit_price": trade.exit_price,
                "gross_pnl": trade.gross_pnl,
                "total_charges": trade.total_charges,
                "net_pnl": trade.net_pnl,
                "exit_reason": trade.exit_reason
            },
            "broker_status": coordinator.paper_broker.auto_exit_last_status
        }
    else:
        return {
            "status": "NO_ACTION",
            "message": coordinator.paper_broker.auto_exit_last_status,
            "awaiting_valid_data": coordinator.paper_broker.auto_exit_awaiting_valid_data,
            "warning": coordinator.paper_broker.auto_exit_warning
        }


@router.get("/trades/csv")
async def export_paper_trades_csv():
    """Export all closed paper trades to CSV."""
    async with AsyncSessionLocal() as session:
        stmt = select(PaperTrade).order_by(PaperTrade.id.asc())
        res = await session.execute(stmt)
        trades = res.scalars().all()

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "Trade ID", "Strategy", "Entry Time (IST)", "Exit Time (IST)", "Holding Time (mins)",
            "Option Symbol", "Strike", "Expiry", "Execution Mode",
            "Entry Premium (₹)", "Configured SL (pts)", "Effective SL (pts)", "SL Trigger Price (₹)",
            "Configured Target (pts)", "Target Trigger Price (₹)", "Exit Premium (₹)", "Quantity",
            "Exit Reason", "Gross P&L (₹)", "Entry Charge (₹)", "Exit Charge (₹)",
            "Total Charges (₹)", "Slippage Cost (₹)", "Net P&L (₹)", "Ambiguity Flag", "Result"
        ])

        for t in trades:
            hold_mins = getattr(t, "holding_time_minutes", None)
            if hold_mins is None or hold_mins <= 0:
                hold_mins = max(1, int((t.exit_time - t.entry_time).total_seconds() // 60))
            writer.writerow([
                t.id,
                getattr(t, "strategy_id", "EMA_RSI"),
                t.entry_time.isoformat(),
                t.exit_time.isoformat(),
                hold_mins,
                t.option_symbol,
                t.strike,
                t.expiry,
                getattr(t, "execution_mode", "TRIGGER_PRICE"),
                t.entry_price,
                getattr(t, "configured_sl_points", ""),
                getattr(t, "effective_sl_points", ""),
                getattr(t, "sl_trigger_price", t.stop_price),
                getattr(t, "configured_target_points", ""),
                getattr(t, "target_trigger_price", t.target_price),
                t.exit_price,
                t.quantity,
                t.exit_reason,
                t.gross_pnl,
                getattr(t, "entry_charge", 10.0),
                getattr(t, "exit_charge", 10.0),
                t.total_charges,
                getattr(t, "slippage_cost", 0.0),
                t.net_pnl,
                getattr(t, "ambiguity_flag", "") or ("YES" if getattr(t, "is_ambiguous", False) else "NO"),
                "WIN" if t.is_win else "LOSS"
            ])

        csv_content = output.getvalue()
        return Response(
            content=csv_content,
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=nextrade_paper_trades.csv"}
        )


@router.post("/charges/recalculate")
async def recalculate_historical_charges(apply: bool = False):
    """
    Controlled recalculation of historical trade charges according to current settings.
    If apply=False, returns preview only.
    If apply=True, recalculates and updates database trades and cash balance.
    """
    entry_rate = coordinator.paper_broker.charges_calc.entry_charge_per_order
    exit_rate = coordinator.paper_broker.charges_calc.exit_charge_per_order
    roundtrip = round(entry_rate + exit_rate, 2)

    async with AsyncSessionLocal() as session:
        stmt = select(PaperTrade).order_by(PaperTrade.id.asc())
        res = await session.execute(stmt)
        trades = res.scalars().all()

        preview = []
        total_pnl_diff = 0.0

        for t in trades:
            old_charges = t.total_charges
            new_charges = roundtrip
            new_net = round(t.gross_pnl - new_charges, 2)
            pnl_diff = round(new_net - t.net_pnl, 2)
            total_pnl_diff += pnl_diff

            preview.append({
                "trade_id": t.id,
                "gross_pnl": t.gross_pnl,
                "old_charges": old_charges,
                "new_charges": new_charges,
                "old_net_pnl": t.net_pnl,
                "new_net_pnl": new_net,
                "diff": pnl_diff
            })

            if apply:
                t.entry_charge = entry_rate
                t.exit_charge = exit_rate
                t.charges_brokerage = new_charges
                t.total_charges = new_charges
                t.net_pnl = new_net
                t.is_win = bool(new_net > 0)

        if apply:
            await session.commit()
            # Reconcile cash balance
            await coordinator.paper_broker.restore_from_db()

    return {
        "status": "APPLIED" if apply else "PREVIEW",
        "trades_count": len(preview),
        "total_pnl_diff": round(total_pnl_diff, 2),
        "entry_charge_per_order": entry_rate,
        "exit_charge_per_order": exit_rate,
        "preview": preview
    }


@router.get("/orders")
async def get_paper_orders(limit: int = 100):
    """Return historical paper orders audit trail."""
    async with AsyncSessionLocal() as session:
        stmt = select(PaperOrder).order_by(desc(PaperOrder.id)).limit(limit)
        res = await session.execute(stmt)
        orders = res.scalars().all()
        return [
            {
                "id": o.id,
                "position_id": o.position_id,
                "order_type": o.order_type,
                "transaction_type": o.transaction_type,
                "symbol": o.symbol,
                "strike": o.strike,
                "expiry": o.expiry,
                "quantity": o.quantity,
                "requested_price": o.requested_price,
                "executed_price": o.executed_price,
                "slippage": o.slippage,
                "status": o.status,
                "created_at": o.created_at.isoformat(),
                "filled_at": o.filled_at.isoformat() if o.filled_at else None
            }
            for o in orders
        ]
