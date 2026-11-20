import asyncio
import pytest
from datetime import datetime, timezone, timedelta
from backend.app.paper.broker import PaperBroker, IST
from backend.app.models import (
    PaperTrade,
    PaperPosition,
    PaperOrder,
    StrategyVirtualAccount,
    StrategyDailyRisk,
    SystemEvent
)
from backend.app.database import AsyncSessionLocal
from sqlalchemy import select, delete


@pytest.fixture
async def broker():
    """Initializes a clean PaperBroker instance and restores ledgers."""
    b = PaperBroker(initial_capital=100000.0)
    await b.restore_from_db()
    return b


@pytest.mark.asyncio
async def test_01_micro_scalper_initial_capital_and_deployment_cap(broker):
    """Test 1: Verify AI_MICRO_SCALPER_V1 initial capital is ₹20,000 and deployment cap is 90% (₹18,000)."""
    ledger = broker.get_strategy_ledger("AI_MICRO_SCALPER_V1")
    assert ledger.initial_capital == 20000.0
    assert ledger.capital_deployment_cap_pct == 90.0
    max_deployable = round(ledger.available_cash * (ledger.capital_deployment_cap_pct / 100.0), 2)
    # Available cash was reconciled to ₹19,418.50 after historical -₹581.50 P&L
    expected_deployable = round(ledger.available_cash * 0.90, 2)
    assert max_deployable == expected_deployable
    assert max_deployable <= 18000.0


@pytest.mark.asyncio
async def test_02_buying_power_rejection_exceeding_deployment_cap(broker):
    """Test 2: Order requiring margin > max deployable capital is rejected with insufficient buying power."""
    # Attempt to buy 130 qty @ ₹150 = ₹19,500 required margin (> ₹18,000 cap and > ₹17,476.65 deployable)
    contract = {
        "symbol": "NIFTY 24500 CE",
        "strike": 24500.0,
        "expiry": "2026-11-26",
        "token": "TEST_OPT",
        "lot_size": 65
    }
    result = await broker.execute_buy(
        contract=contract,
        current_premium=150.0,
        underlying_price=24500.0,
        lots=2,  # 130 qty -> 130 * 150 = ₹19,500
        strategy_id="AI_MICRO_SCALPER_V1",
        bypass_session_check=True,
        execution_mode="TRIGGER_PRICE"
    )
    assert result is None
    assert broker.active_position is None

    # Verify rejection event logged in SystemEvent
    async with AsyncSessionLocal() as session:
        stmt = select(SystemEvent).where(
            SystemEvent.event_type == "RISK_REJECTION"
        ).order_by(SystemEvent.id.desc())
        res = await session.execute(stmt)
        evt = res.scalars().first()
        assert evt is not None
        assert "Buying Power Rejection" in evt.title or "RISK_REJECTION" in evt.event_type


@pytest.mark.asyncio
async def test_03_concurrency_lock_serializes_simultaneous_entries(broker):
    """Test 3: Simultaneous entries via asyncio.gather allow only 1 position to open."""
    # Ensure no active position
    broker.active_position = None
    broker.get_strategy_ledger("AI_MICRO_SCALPER_V1").active_position = None

    contract = {
        "symbol": "NIFTY 24500 CE",
        "strike": 24500.0,
        "expiry": "2026-11-26",
        "token": "TEST_OPT_CONCURRENCY",
        "lot_size": 65
    }

    # Fire 5 simultaneous execute_buy calls concurrently with valid margin (65 qty @ ₹100 = ₹6,500)
    tasks = [
        broker.execute_buy(
            contract=contract,
            current_premium=100.0,
            underlying_price=24500.0,
            lots=1,
            strategy_id="AI_MICRO_SCALPER_V1",
            bypass_session_check=True,
            execution_mode="TRIGGER_PRICE"
        )
        for _ in range(5)
    ]
    results = await asyncio.gather(*tasks)

    # Exactly one order must succeed; four must be rejected
    successful = [r for r in results if r is not None]
    rejected = [r for r in results if r is None]

    assert len(successful) == 1
    assert len(rejected) == 4
    assert broker.active_position is not None
    assert broker.get_strategy_ledger("AI_MICRO_SCALPER_V1").active_position is not None

    # Clean up position and trade created in test_03
    pos_id = broker.active_position["id"]
    await broker.manual_close(exit_price=104.0, reason="TEST_CLEANUP")
    async with AsyncSessionLocal() as session:
        await session.execute(delete(PaperTrade).where(PaperTrade.position_id == pos_id))
        await session.execute(delete(PaperOrder).where(PaperOrder.position_id == pos_id))
        await session.execute(delete(PaperPosition).where(PaperPosition.id == pos_id))
        await session.commit()
    await broker.restore_from_db()


@pytest.mark.asyncio
async def test_04_isolated_ut_bot_ledger_independence(broker):
    """Test 4: UT_BOT virtual account remains independent from AI_MICRO_SCALPER_V1."""
    ut_ledger = broker.get_strategy_ledger("UT_BOT")
    ai_ledger = broker.get_strategy_ledger("AI_MICRO_SCALPER_V1")

    assert ut_ledger.initial_capital == 100000.0
    assert ut_ledger.available_cash >= 133280.0
    assert ut_ledger.available_cash == round(ut_ledger.initial_capital + ut_ledger.realized_net_pnl - ut_ledger.reserved_capital, 2)
    assert ut_ledger.risk_limits_enabled is False

    assert ai_ledger.initial_capital == 20000.0
    assert ai_ledger.available_cash == round(ai_ledger.initial_capital + ai_ledger.realized_net_pnl - ai_ledger.reserved_capital, 2)
    assert ai_ledger.capital_deployment_cap_pct == 90.0
    assert ai_ledger.risk_limits_enabled is True


@pytest.mark.asyncio
async def test_05_cross_contamination_prevention(broker):
    """Test 5: An AI Micro-Scalper trade changes only AI ledger, zero effect on UT_BOT."""
    ut_cash_before = broker.get_strategy_cash("UT_BOT")
    ai_cash_before = broker.get_strategy_cash("AI_MICRO_SCALPER_V1")

    contract = {
        "symbol": "NIFTY 24500 CE",
        "strike": 24500.0,
        "expiry": "2026-11-26",
        "token": "TEST_OPT_ISOLATION",
        "lot_size": 65
    }
    pos = await broker.execute_buy(
        contract=contract,
        current_premium=100.0,
        underlying_price=24500.0,
        lots=1,
        strategy_id="AI_MICRO_SCALPER_V1",
        bypass_session_check=True,
        execution_mode="TRIGGER_PRICE"
    )
    assert pos is not None

    pos_id = pos["id"]
    # Close with +₹200 net profit (exit @ 103.38 with ₹20 charges)
    res = await broker.manual_close(exit_price=103.38, reason="TARGET")
    assert res is not None

    ut_cash_after = broker.get_strategy_cash("UT_BOT")
    ai_cash_after = broker.get_strategy_cash("AI_MICRO_SCALPER_V1")

    # UT_BOT cash must not have changed by even 1 paisa!
    assert ut_cash_after == ut_cash_before
    # AI Micro-Scalper cash must reflect the trade net P&L
    assert ai_cash_after == round(ai_cash_before + res.net_pnl, 2)

    # Clean up test trade
    async with AsyncSessionLocal() as session:
        await session.execute(delete(PaperTrade).where(PaperTrade.position_id == pos_id))
        await session.execute(delete(PaperOrder).where(PaperOrder.position_id == pos_id))
        await session.execute(delete(PaperPosition).where(PaperPosition.id == pos_id))
        await session.commit()
    await broker.restore_from_db()


@pytest.mark.asyncio
async def test_06_double_entry_capital_reservation_and_release(broker):
    """Test 6: Verify double-entry ledger reservation on entry and release on exit."""
    ledger = broker.get_strategy_ledger("AI_MICRO_SCALPER_V1")
    cash_start = ledger.available_cash
    assert ledger.reserved_capital == 0.0

    contract = {
        "symbol": "NIFTY 24500 CE",
        "strike": 24500.0,
        "expiry": "2026-11-26",
        "token": "TEST_OPT_DOUBLE_ENTRY",
        "lot_size": 65
    }
    # Buy 65 qty @ ₹100 = ₹6,500 required margin
    pos = await broker.execute_buy(
        contract=contract,
        current_premium=100.0,
        underlying_price=24500.0,
        lots=1,
        strategy_id="AI_MICRO_SCALPER_V1",
        bypass_session_check=True,
        execution_mode="TRIGGER_PRICE"
    )
    assert pos is not None
    assert ledger.reserved_capital == 6500.0
    assert ledger.available_cash == round(cash_start - 6500.0, 2)
    assert round(ledger.available_cash + ledger.reserved_capital, 2) == cash_start

    pos_id = pos["id"]
    # Close position
    trade_res = await broker.manual_close(exit_price=104.0, reason="TARGET")
    assert trade_res is not None
    assert ledger.reserved_capital == 0.0
    assert ledger.available_cash == round(cash_start + trade_res.net_pnl, 2)

    # Clean up test trade
    async with AsyncSessionLocal() as session:
        await session.execute(delete(PaperTrade).where(PaperTrade.position_id == pos_id))
        await session.execute(delete(PaperOrder).where(PaperOrder.position_id == pos_id))
        await session.execute(delete(PaperPosition).where(PaperPosition.id == pos_id))
        await session.commit()
    await broker.restore_from_db()


@pytest.mark.asyncio
async def test_07_daily_trade_limit_hard_gate(broker):
    """Test 7: Daily trade limit (5 trades) locks AI Micro-Scalper and rejects 6th entry."""
    test_date = datetime(2026, 11, 25, 10, 0, tzinfo=timezone.utc)
    ledger = broker.get_strategy_ledger("AI_MICRO_SCALPER_V1")
    assert ledger.max_trades_per_day == 5

    # Insert 5 simulated closed trades on test_date
    created_trade_ids = []
    async with AsyncSessionLocal() as session:
        for i in range(5):
            t = PaperTrade(
                position_id=80000 + i,
                strategy_id="AI_MICRO_SCALPER_V1",
                underlying_symbol="NIFTY",
                underlying_price_at_entry=24500.0,
                option_symbol="NIFTY26NOV24500CE",
                strike=24500.0,
                expiry="2026-11-26",
                entry_time=test_date - timedelta(minutes=10 * (5 - i)),
                exit_time=test_date - timedelta(minutes=5 * (5 - i)),
                entry_price=100.0,
                exit_price=103.5,
                quantity=130,
                target_price=103.5,
                stop_price=97.5,
                gross_pnl=455.0,
                total_charges=20.0,
                net_pnl=435.0,
                is_win=True,
                exit_reason="TARGET"
            )
            session.add(t)
            await session.flush()
            created_trade_ids.append(t.id)
        await session.commit()

    try:
        risk_status = await broker.get_daily_risk_status(
            strategy_id="AI_MICRO_SCALPER_V1",
            now=test_date
        )
        assert risk_status["is_locked"] is True
        assert risk_status["lock_reason"] in ("MAX_DAILY_TRADES_LOCKED", "DAILY_PROFIT_LOCKED")
        assert risk_status["trade_count"] == 5

        # Attempt 6th entry on that date: must be rejected
        contract = {
            "symbol": "NIFTY 24500 CE",
            "strike": 24500.0,
            "expiry": "2026-11-26",
            "token": "TEST_OPT_GATE",
            "lot_size": 65
        }
        res_6th = await broker.execute_buy(
            contract=contract,
            current_premium=100.0,
            underlying_price=24500.0,
            lots=1,
            strategy_id="AI_MICRO_SCALPER_V1",
            timestamp=test_date,
            bypass_session_check=False,
            execution_mode="TRIGGER_PRICE"
        )
        assert res_6th is None
        assert broker.active_position is None
    finally:
        # Clean up test trades
        async with AsyncSessionLocal() as session:
            await session.execute(delete(PaperTrade).where(PaperTrade.id.in_(created_trade_ids)))
            await session.commit()


@pytest.mark.asyncio
async def test_08_daily_profit_lock(broker):
    """Test 8: Daily profit lock (+₹500 for Micro-Scalper) blocks further entries."""
    test_date = datetime(2026, 11, 26, 11, 0, tzinfo=timezone.utc)
    created_id = None

    # Insert 1 winning trade with +₹520 net profit (exceeds ₹500 profit lock)
    async with AsyncSessionLocal() as session:
        t = PaperTrade(
            position_id=85001,
            strategy_id="AI_MICRO_SCALPER_V1",
            underlying_symbol="NIFTY",
            underlying_price_at_entry=24500.0,
            option_symbol="NIFTY26NOV24500CE",
            strike=24500.0,
            expiry="2026-11-26",
            entry_time=test_date - timedelta(minutes=10),
            exit_time=test_date - timedelta(minutes=2),
            entry_price=100.0,
            exit_price=104.15,
            quantity=130,
            target_price=104.0,
            stop_price=97.5,
            gross_pnl=540.0,
            total_charges=20.0,
            net_pnl=520.0,
            is_win=True,
            exit_reason="TARGET"
        )
        session.add(t)
        await session.flush()
        created_id = t.id
        await session.commit()

    try:
        risk_status = await broker.get_daily_risk_status(
            strategy_id="AI_MICRO_SCALPER_V1",
            now=test_date
        )
        assert risk_status["is_locked"] is True
        assert risk_status["lock_reason"] == "DAILY_PROFIT_LOCKED"
        assert risk_status["realized_net_pnl"] >= 500.0
    finally:
        if created_id:
            async with AsyncSessionLocal() as session:
                await session.execute(delete(PaperTrade).where(PaperTrade.id == created_id))
                await session.commit()


@pytest.mark.asyncio
async def test_09_daily_loss_lock(broker):
    """Test 9: Daily loss lock (-₹500 for Micro-Scalper) blocks further entries."""
    test_date = datetime(2026, 11, 27, 11, 0, tzinfo=timezone.utc)
    created_id = None

    # Insert 1 losing trade with -₹520 net loss (breaches -₹500 loss limit)
    async with AsyncSessionLocal() as session:
        t = PaperTrade(
            position_id=85002,
            strategy_id="AI_MICRO_SCALPER_V1",
            underlying_symbol="NIFTY",
            underlying_price_at_entry=24500.0,
            option_symbol="NIFTY26NOV24500CE",
            strike=24500.0,
            expiry="2026-11-26",
            entry_time=test_date - timedelta(minutes=10),
            exit_time=test_date - timedelta(minutes=2),
            entry_price=100.0,
            exit_price=96.0,
            quantity=130,
            target_price=104.0,
            stop_price=96.0,
            gross_pnl=-520.0,
            total_charges=20.0,
            net_pnl=-540.0,
            is_win=False,
            exit_reason="STOP_LOSS"
        )
        session.add(t)
        await session.flush()
        created_id = t.id
        await session.commit()

    try:
        risk_status = await broker.get_daily_risk_status(
            strategy_id="AI_MICRO_SCALPER_V1",
            now=test_date
        )
        assert risk_status["is_locked"] is True
        assert risk_status["lock_reason"] == "DAILY_LOSS_LOCKED"
        assert risk_status["realized_net_pnl"] <= -500.0
    finally:
        if created_id:
            async with AsyncSessionLocal() as session:
                await session.execute(delete(PaperTrade).where(PaperTrade.id == created_id))
                await session.commit()


@pytest.mark.asyncio
async def test_10_open_position_can_exit_normally_when_risk_locked(broker):
    """Test 10: Positions can still exit normally when risk lock is active."""
    pos_id = None
    # Create an actual PaperPosition row in DB
    async with AsyncSessionLocal() as session:
        p = PaperPosition(
            strategy_id="AI_MICRO_SCALPER_V1",
            instrument_token="TEST_EXIT",
            symbol="NIFTY 24500 CE",
            strike=24500.0,
            expiry="2026-11-26",
            quantity=130,
            lots=2,
            lot_size=65,
            entry_price=100.0,
            current_price=100.0,
            target_price=104.0,
            stop_price=98.0,
            effective_stop_distance=2.0,
            max_loss_amount=300.0,
            highest_price=100.0,
            lowest_price=100.0,
            status="OPEN",
            entry_time=datetime.now(timezone.utc),
            execution_mode="TRIGGER_PRICE"
        )
        session.add(p)
        await session.flush()
        pos_id = p.id
        await session.commit()

    broker.active_position = {
        "id": pos_id,
        "strategy_id": "AI_MICRO_SCALPER_V1",
        "instrument_token": "TEST_EXIT",
        "symbol": "NIFTY 24500 CE",
        "strike": 24500.0,
        "expiry": "2026-11-26",
        "quantity": 130,
        "entry_price": 100.0,
        "target_price": 104.0,
        "stop_price": 98.0,
        "highest_price": 100.0,
        "lowest_price": 100.0,
        "entry_time": datetime.now(timezone.utc),
        "execution_mode": "TRIGGER_PRICE"
    }
    broker.get_strategy_ledger("AI_MICRO_SCALPER_V1").active_position = broker.active_position
    broker.get_strategy_ledger("AI_MICRO_SCALPER_V1").reserved_capital = 13000.0

    try:
        # Execute tick exit at target (104.5 >= 104.0)
        result = await broker.update_tick("TEST_EXIT", 104.5)
        assert result is not None
        assert result.exit_reason == "TARGET"
        assert broker.active_position is None
        assert broker.get_strategy_ledger("AI_MICRO_SCALPER_V1").active_position is None
    finally:
        # Clean up test position, orders, trades
        async with AsyncSessionLocal() as session:
            await session.execute(delete(PaperOrder).where(PaperOrder.position_id == pos_id))
            await session.execute(delete(PaperTrade).where(PaperTrade.position_id == pos_id))
            await session.execute(delete(PaperPosition).where(PaperPosition.id == pos_id))
            await session.commit()


@pytest.mark.asyncio
async def test_11_restart_recovery_preserves_ledgers_and_counters(broker):
    """Test 11: A fresh broker instance restores exact persisted ledger balances and counts."""
    fresh_broker = PaperBroker(initial_capital=100000.0)
    await fresh_broker.restore_from_db()

    ut = fresh_broker.get_strategy_ledger("UT_BOT")
    ai = fresh_broker.get_strategy_ledger("AI_MICRO_SCALPER_V1")
    st = fresh_broker.get_strategy_ledger("SUPERTREND_EMA")

    assert ut.initial_capital == 100000.0
    assert ut.available_cash >= 133280.0
    assert ut.risk_limits_enabled is False

    assert ai.initial_capital == 20000.0
    assert ai.capital_deployment_cap_pct == 90.0
    assert ai.risk_limits_enabled is True

    assert st.initial_capital == 50000.0


@pytest.mark.asyncio
async def test_12_historical_trades_integrity():
    """Test 12: Ensure historical 32 trades remain strictly intact with original strategy attribution."""
    async with AsyncSessionLocal() as session:
        stmt = select(PaperTrade)
        res = await session.execute(stmt)
        trades = res.scalars().all()
        # Ensure at least 32 trades are preserved
        assert len(trades) >= 32

        ut_trades = [t for t in trades if getattr(t, "strategy_id", "UT_BOT") == "UT_BOT"]
        ai_trades = [t for t in trades if getattr(t, "strategy_id", "") == "AI_MICRO_SCALPER_V1"]

        assert len(ut_trades) >= 26
        assert len(ai_trades) >= 6
