import pytest
import json
import asyncio
from datetime import datetime, timezone, timedelta
from sqlalchemy import select, delete

from backend.app.database import AsyncSessionLocal, init_db
from backend.app.models import (
    PaperOrder,
    PaperPosition,
    PaperTrade,
    PaperAccount,
    PaperAccountBalance,
    PaperTradeEvent,
    PaperExecutionLog,
    PaperCharge,
    PaperRiskEvent,
    BacktestRun,
    BacktestTrade,
    BacktestDailyResult,
    BacktestMetric,
    BacktestDataCoverage,
    BacktestExecutionLog,
    StrategySignal,
    StrategySignalEvaluation,
    AgentDecision,
    StrategyExecutionEvent,
    StrategyConfigVersion,
    StrategyDailyRisk,
    StrategyVirtualAccount,
)
from backend.app.paper.broker import PaperBroker
from backend.app.backtest.engine import BacktestEngine


@pytest.fixture(autouse=True)
async def setup_db():
    await init_db()
    async with AsyncSessionLocal() as session:
        await session.execute(
            delete(PaperPosition).where(PaperPosition.status == "OPEN")
        )
        await session.commit()
    yield
    # Clean up any test artifacts to keep historical trades pristine
    async with AsyncSessionLocal() as session:
        await session.execute(delete(PaperTradeEvent).where(PaperTradeEvent.trade_id > 32))
        await session.execute(delete(PaperCharge).where(PaperCharge.trade_id > 32))
        await session.execute(delete(PaperAccountBalance).where(PaperAccountBalance.related_trade_id > 32))
        await session.execute(delete(PaperTrade).where(PaperTrade.id > 32))
        await session.execute(
            delete(PaperOrder).where(
                (PaperOrder.symbol.like("%TEST%")) | 
                (PaperOrder.symbol.like("%REC%")) | 
                (PaperOrder.symbol.like("%CLOSE%"))
            )
        )
        await session.execute(
            delete(PaperPosition).where(
                (PaperPosition.symbol.like("%TEST%")) | 
                (PaperPosition.symbol.like("%REC%")) | 
                (PaperPosition.symbol.like("%CLOSE%"))
            )
        )
        await session.commit()
    b = PaperBroker()
    await b.restore_from_db()


@pytest.mark.asyncio
async def test_01_create_paper_order_persist_and_reload():
    """1. Create paper order -> persist -> reload."""
    now = datetime.now(timezone.utc)
    order_data = PaperOrder(
        position_id=99991,
        order_type="MARKET",
        transaction_type="BUY",
        instrument_token="OPT_NIFTY_24500_CE",
        symbol="NIFTY26NOV24500CE",
        strike=24500.0,
        expiry="2026-11-26",
        quantity=65,
        requested_price=120.0,
        executed_price=120.5,
        slippage=0.5,
        status="FILLED",
        created_at=now,
        filled_at=now
    )
    async with AsyncSessionLocal() as session:
        session.add(order_data)
        await session.commit()
        order_id = order_data.id

    # Reload in a brand new session
    async with AsyncSessionLocal() as session:
        res = await session.execute(select(PaperOrder).where(PaperOrder.id == order_id))
        loaded = res.scalar_one_or_none()
        assert loaded is not None
        assert loaded.symbol == "NIFTY26NOV24500CE"
        assert loaded.quantity == 65
        assert loaded.executed_price == 120.5
        assert loaded.status == "FILLED"

        # Cleanup
        await session.delete(loaded)
        await session.commit()


@pytest.mark.asyncio
async def test_02_open_position_restart_backend_recover_position():
    """2. Open position -> restart backend -> recover position."""
    now = datetime.now(timezone.utc)
    contract = {
        "instrument_token": "TEST_RECOVER_TOKEN",
        "symbol": "NIFTY26NOV24500CE_REC",
        "strike": 24500.0,
        "expiry": "2026-11-26",
        "lot_size": 65
    }

    broker1 = PaperBroker()
    await broker1.restore_from_db()
    strat_id = "AI_MICRO_SCALPER_V1"

    # Make sure no active position exists prior to test
    async with AsyncSessionLocal() as session:
        await session.execute(
            delete(PaperPosition).where(PaperPosition.symbol == "NIFTY26NOV24500CE_REC")
        )
        await session.commit()

    pos = await broker1.execute_buy(
        contract=contract,
        current_premium=100.0,
        underlying_price=24500.0,
        lots=1,
        timestamp=now,
        bypass_session_check=True,
        strategy_id=strat_id,
        target_points=4.0,
        stop_points=2.0
    )
    assert pos is not None
    pos_id = pos["id"]

    # Simulate full backend restart: instantiate a new PaperBroker and restore
    broker2 = PaperBroker()
    await broker2.restore_from_db()

    assert broker2.active_position is not None
    assert broker2.active_position["id"] == pos_id
    assert broker2.active_position["symbol"] == "NIFTY26NOV24500CE_REC"
    assert broker2.active_position["status"] == "OPEN"

    # Clean up position
    await broker2._close_position(
        exit_price=104.0,
        exit_reason="TEST_RECOVERY_CLEANUP",
        exit_time=now + timedelta(minutes=2)
    )


@pytest.mark.asyncio
async def test_03_close_position_verify_pnl_and_charges():
    """3. Close position -> verify P&L, charges, trade events, and account ledger."""
    now = datetime.now(timezone.utc)
    # Clear any lingering test position
    async with AsyncSessionLocal() as session:
        await session.execute(
            delete(PaperPosition).where(PaperPosition.status == "OPEN")
        )
        await session.commit()

    broker = PaperBroker()
    await broker.restore_from_db()
    strat_id = "AI_MICRO_SCALPER_V1"

    contract = {
        "instrument_token": "TEST_CLOSE_TOKEN",
        "symbol": "NIFTY26NOV24500CE_CLOSE",
        "strike": 24500.0,
        "expiry": "2026-11-26",
        "lot_size": 65
    }

    pos = await broker.execute_buy(
        contract=contract,
        current_premium=100.0,
        underlying_price=24500.0,
        lots=1,
        timestamp=now,
        bypass_session_check=True,
        strategy_id=strat_id,
        target_points=4.0,
        stop_points=2.0,
        execution_mode="TRIGGER_PRICE"
    )
    assert pos is not None
    pos_id = pos["id"]

    # Close at target +4 points (exit price 104.0)
    exit_now = now + timedelta(minutes=3)
    res = await broker._close_position(
        exit_price=104.0,
        exit_reason="TARGET_HIT",
        exit_time=exit_now
    )
    assert res is not None

    # Gross PnL: (104.0 - 100.0) * 65 = 260.0
    expected_gross = round((104.0 - pos["entry_price"]) * 65, 2)
    expected_charges = 20.0
    expected_net = expected_gross - expected_charges

    assert round(res.gross_pnl, 2) == expected_gross
    assert round(res.total_charges, 2) == expected_charges
    assert round(res.net_pnl, 2) == expected_net

    # Verify granular persistence tables: PaperTrade, PaperTradeEvent, PaperCharge, PaperAccountBalance
    async with AsyncSessionLocal() as session:
        t_res = await session.execute(select(PaperTrade).where(PaperTrade.position_id == pos_id))
        trade = t_res.scalar_one_or_none()
        assert trade is not None
        assert trade.exit_reason == "TARGET_HIT"
        assert trade.net_pnl == expected_net

        evt_res = await session.execute(select(PaperTradeEvent).where(PaperTradeEvent.trade_id == trade.id))
        evts = evt_res.scalars().all()
        assert len(evts) >= 1
        assert any(e.event_type == "TARGET_HIT" for e in evts)

        chg_res = await session.execute(select(PaperCharge).where(PaperCharge.trade_id == trade.id))
        chg = chg_res.scalar_one_or_none()
        assert chg is not None
        assert chg.total_charges == 20.0

        bal_res = await session.execute(
            select(PaperAccountBalance).where(PaperAccountBalance.related_trade_id == trade.id)
        )
        bal = bal_res.scalar_one_or_none()
        assert bal is not None
        assert bal.change_reason == "TRADE_EXIT_SETTLEMENT"
        assert bal.change_amount == expected_net


@pytest.mark.asyncio
async def test_04_05_backtest_save_reload_and_exact_trade_ledger():
    """4 & 5. Start backtest -> save run -> restart -> load previous run and verify exact trades."""
    engine = BacktestEngine()
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    trades_data = [
        {
            "signal_time": datetime.now(timezone.utc),
            "entry_time": datetime.now(timezone.utc),
            "exit_time": datetime.now(timezone.utc) + timedelta(minutes=5),
            "underlying_price": 24500.0,
            "option_symbol": "NIFTY26NOV24500CE_BT1",
            "strike": 24500.0,
            "expiry": "2026-11-26",
            "entry_price": 100.0,
            "exit_price": 104.0,
            "quantity": 65,
            "target": 104.0,
            "stop": 98.0,
            "configured_sl_points": 2.0,
            "configured_target_points": 4.0,
            "exit_reason": "TARGET",
            "gross_pnl": 260.0,
            "entry_charge": 10.0,
            "exit_charge": 10.0,
            "charges": 20.0,
            "net_pnl": 240.0,
            "is_win": True
        },
        {
            "signal_time": datetime.now(timezone.utc),
            "entry_time": datetime.now(timezone.utc),
            "exit_time": datetime.now(timezone.utc) + timedelta(minutes=2),
            "underlying_price": 24510.0,
            "option_symbol": "NIFTY26NOV24500CE_BT2",
            "strike": 24500.0,
            "expiry": "2026-11-26",
            "entry_price": 105.0,
            "exit_price": 103.0,
            "quantity": 65,
            "target": 109.0,
            "stop": 103.0,
            "configured_sl_points": 2.0,
            "configured_target_points": 4.0,
            "exit_reason": "STOP_LOSS",
            "gross_pnl": -130.0,
            "entry_charge": 10.0,
            "exit_charge": 10.0,
            "charges": 20.0,
            "net_pnl": -150.0,
            "is_win": False
        }
    ]

    mock_results = {
        "strategy_id": "AI_MICRO_SCALPER_V1",
        "strategy_name": "NEXTRADE AI MICRO-SCALPER V1",
        "config_snapshot": {"lots": 1, "target": 4.0, "stop": 2.0},
        "timeframe": "1m",
        "contract_symbol": "NIFTY ATM CE",
        "start_date": "2026-11-01",
        "end_date": "2026-11-20",
        "initial_capital": 20000.0,
        "final_capital": 20090.0,
        "total_trades": 2,
        "winning_trades": 1,
        "losing_trades": 1,
        "win_rate": 50.0,
        "gross_profit": 260.0,
        "gross_loss": 130.0,
        "net_profit": 90.0,
        "max_drawdown": 150.0,
        "profit_factor": 2.0,
        "avg_profit": 260.0,
        "avg_loss": 130.0,
        "largest_win": 260.0,
        "largest_loss": -130.0,
        "total_charges": 40.0,
        "data_source": "HISTORICAL_DATA",
        "execution_mode": "TRIGGER_PRICE",
        "trades": trades_data
    }

    run_id = await engine.save_backtest_run(mock_results)
    assert run_id > 0

    # Verify backtest run, trade ledger, metrics, and daily results persist
    async with AsyncSessionLocal() as session:
        run_res = await session.execute(select(BacktestRun).where(BacktestRun.id == run_id))
        loaded_run = run_res.scalar_one_or_none()
        assert loaded_run is not None
        assert loaded_run.net_profit == 90.0
        assert loaded_run.total_trades == 2

        trades_res = await session.execute(
            select(BacktestTrade).where(BacktestTrade.run_id == run_id).order_by(BacktestTrade.id.asc())
        )
        loaded_trades = trades_res.scalars().all()
        assert len(loaded_trades) == 2
        assert loaded_trades[0].net_pnl == 240.0
        assert loaded_trades[1].net_pnl == -150.0

        daily_res = await session.execute(
            select(BacktestDailyResult).where(BacktestDailyResult.run_id == run_id)
        )
        daily_rows = daily_res.scalars().all()
        assert len(daily_rows) >= 1

        met_res = await session.execute(
            select(BacktestMetric).where(BacktestMetric.run_id == run_id)
        )
        metrics = {m.metric_key: m.metric_value for m in met_res.scalars().all()}
        assert metrics.get("win_rate") == 50.0
        assert metrics.get("profit_factor") == 2.0


@pytest.mark.asyncio
async def test_06_07_signals_generate_and_reject_persistence():
    """6 & 7. Generate signal -> persist; Reject signal -> persist rejection reason."""
    now = datetime.now(timezone.utc)
    sig_accepted = StrategySignal(
        strategy_id="AI_MICRO_SCALPER_V1",
        timestamp=now,
        candle_time=now,
        underlying_symbol="NIFTY",
        underlying_price=24500.0,
        ema_9=24510.0,
        ema_21=24490.0,
        rsi_14=62.0,
        signal_type="BUY_ATM_CE",
        executed=True,
        notes="All 4 agents approved: Trend, Momentum, Volatility, Microstructure"
    )

    sig_rejected = StrategySignal(
        strategy_id="AI_MICRO_SCALPER_V1",
        timestamp=now,
        candle_time=now,
        underlying_symbol="NIFTY",
        underlying_price=24500.0,
        ema_9=24490.0,
        ema_21=24510.0,
        rsi_14=42.0,
        signal_type="NONE",
        executed=False,
        notes="REJECTED: Momentum agent vetoed (RSI 42.0 < 55.0 threshold)"
    )

    async with AsyncSessionLocal() as session:
        session.add(sig_accepted)
        session.add(sig_rejected)
        await session.commit()
        id_acc = sig_accepted.id
        id_rej = sig_rejected.id

    async with AsyncSessionLocal() as session:
        res1 = await session.execute(select(StrategySignal).where(StrategySignal.id == id_acc))
        loaded1 = res1.scalar_one_or_none()
        assert loaded1.executed is True
        assert loaded1.signal_type == "BUY_ATM_CE"

        res2 = await session.execute(select(StrategySignal).where(StrategySignal.id == id_rej))
        loaded2 = res2.scalar_one_or_none()
        assert loaded2.executed is False
        assert "REJECTED" in loaded2.notes


@pytest.mark.asyncio
async def test_08_09_strategy_config_versions_and_invariance():
    """8 & 9. Change strategy settings -> persist new version; Historical configuration remains unchanged."""
    strat_id = "AI_MICRO_SCALPER_V1"
    async with AsyncSessionLocal() as session:
        v1 = StrategyConfigVersion(
            strategy_id=strat_id,
            version=101,
            config_json=json.dumps({"target_points": 4.0, "stop_points": 2.0, "lots": 2}),
            change_summary="Initial parameters",
            changed_by="tester"
        )
        session.add(v1)
        await session.commit()

        v2 = StrategyConfigVersion(
            strategy_id=strat_id,
            version=102,
            config_json=json.dumps({"target_points": 5.0, "stop_points": 2.5, "lots": 3}),
            change_summary="Updated target & lots",
            changed_by="tester"
        )
        session.add(v2)
        await session.commit()

    # Verify both versions exist independently
    async with AsyncSessionLocal() as session:
        res1 = await session.execute(
            select(StrategyConfigVersion).where(
                StrategyConfigVersion.strategy_id == strat_id,
                StrategyConfigVersion.version == 101
            )
        )
        loaded_v1 = res1.scalar_one_or_none()
        assert json.loads(loaded_v1.config_json)["target_points"] == 4.0

        res2 = await session.execute(
            select(StrategyConfigVersion).where(
                StrategyConfigVersion.strategy_id == strat_id,
                StrategyConfigVersion.version == 102
            )
        )
        loaded_v2 = res2.scalar_one_or_none()
        assert json.loads(loaded_v2.config_json)["target_points"] == 5.0

        # Clean up test versions
        await session.delete(loaded_v1)
        await session.delete(loaded_v2)
        await session.commit()


@pytest.mark.asyncio
async def test_10_daily_risk_lock_persists_across_restart():
    """10. Apply daily risk lock -> restart -> lock remains."""
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    strat_id = "AI_MICRO_SCALPER_V1"

    async with AsyncSessionLocal() as session:
        res = await session.execute(
            select(StrategyDailyRisk).where(
                StrategyDailyRisk.strategy_id == strat_id,
                StrategyDailyRisk.trading_date == today_str
            )
        )
        rec = res.scalar_one_or_none()
        if not rec:
            rec = StrategyDailyRisk(
                strategy_id=strat_id,
                trading_date=today_str,
                realized_net_pnl=-550.0,
                trade_count=3,
                is_locked=True,
                lock_reason="DAILY_LOSS_LOCKED"
            )
            session.add(rec)
        else:
            rec.is_locked = True
            rec.lock_reason = "DAILY_LOSS_LOCKED"
        await session.commit()

    # Simulate fresh PaperBroker restart
    broker = PaperBroker()
    status = await broker.get_daily_risk_status(strategy_id=strat_id)
    assert status["is_locked"] is True
    assert "LOCKED" in status["lock_reason"]


@pytest.mark.asyncio
async def test_11_account_balances_reconcile_with_trade_ledger():
    """11. Check account balances against ledger."""
    broker = PaperBroker()
    await broker.restore_from_db()

    for sid in ["UT_BOT", "AI_MICRO_SCALPER_V1"]:
        ledger = broker.get_strategy_ledger(sid)
        async with AsyncSessionLocal() as session:
            trades_res = await session.execute(
                select(PaperTrade).where(PaperTrade.strategy_id == sid)
            )
            trades = trades_res.scalars().all()
            sum_net = sum(float(t.net_pnl) for t in trades)
            sum_charges = sum(float(t.total_charges) for t in trades)

            assert round(ledger.realized_net_pnl, 2) == round(sum_net, 2)
            assert round(ledger.total_charges, 2) == round(sum_charges, 2)
            expected_cash = round(ledger.initial_capital + sum_net - ledger.reserved_capital, 2)
            assert round(ledger.available_cash, 2) == expected_cash


@pytest.mark.asyncio
async def test_12_virtual_accounts_isolation():
    """12 & 14. Strategy virtual accounts remain independent with zero bleed."""
    broker = PaperBroker()
    await broker.restore_from_db()

    ut_cash_before = broker.get_strategy_cash("UT_BOT")
    ai_cash_before = broker.get_strategy_cash("AI_MICRO_SCALPER_V1")

    assert ut_cash_before > 100000.0  # UT BOT historical profits
    assert ai_cash_before > 0.0
    assert ut_cash_before != ai_cash_before

    # Verify they don't share balance
    assert broker.get_strategy_ledger("UT_BOT").initial_capital == 100000.0
    assert broker.get_strategy_ledger("AI_MICRO_SCALPER_V1").initial_capital == 20000.0
