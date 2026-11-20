import pytest
from datetime import datetime, timezone, timedelta
from backend.app.paper.broker import PaperBroker
from backend.app.database import AsyncSessionLocal
from backend.app.models import PaperPosition, PaperTrade, AutoExitSetting

IST = timezone(timedelta(hours=5, minutes=30))

SAMPLE_CONTRACT = {
    "instrument_token": "OPT_AUTO_TEST_1",
    "symbol": "NIFTY 24500 CE",
    "strike": 24500.0,
    "expiry": "28-NOV-2026",
    "lot_size": 65
}


@pytest.mark.asyncio
async def test_position_with_profit_at_320():
    """Test 1: Position in profit at 03:20 PM IST is closed with AUTO_CLOSE_3_20_PM."""
    broker = PaperBroker(initial_capital=100000.0, slippage_points=0.10)
    broker.auto_close_time_ist = "15:20"

    # Buy at 150.0 (executed at 150.10 with slippage)
    pos = await broker.execute_buy(SAMPLE_CONTRACT, current_premium=150.0, underlying_price=24500.0, lots=1, bypass_session_check=True)
    assert pos is not None

    # At 15:20 IST, price is 152.0 (profit)
    now_1520 = datetime(2026, 11, 18, 15, 20, 0, tzinfo=IST)
    trade = await broker.check_and_run_auto_close(
        now=now_1520,
        latest_option_price=152.0,
        is_feed_stale=False,
        is_feed_connected=True
    )

    assert trade is not None
    assert trade.exit_reason == "AUTO_CLOSE_3_20_PM"
    assert broker.active_position is None
    # Executed exit price = 152.0 - 0.10 = 151.90
    assert trade.exit_price == 151.90
    # Gross P&L: (151.90 - 150.10) * 65 = 1.80 * 65 = 117.0
    assert trade.gross_pnl == 117.0
    # Charges: ₹20 (10 entry + 10 exit)
    assert trade.total_charges == 20.0
    # Net P&L: 117.0 - 20.0 = 97.0
    assert trade.net_pnl == 97.0
    assert broker.cash_balance == 100097.0
    assert broker.session_cutoff_active is True

    # Clean up test records
    async with AsyncSessionLocal() as session:
        from sqlalchemy import delete
        from backend.app.models import PaperOrder, PaperPosition, PaperTrade
        await session.execute(delete(PaperTrade).where(PaperTrade.position_id == pos["id"]))
        await session.execute(delete(PaperOrder).where(PaperOrder.position_id == pos["id"]))
        await session.execute(delete(PaperPosition).where(PaperPosition.id == pos["id"]))
        await session.commit()


@pytest.mark.asyncio
async def test_position_with_loss_at_320():
    """Test 2: Position in loss at 03:20 PM IST is closed with AUTO_CLOSE_3_20_PM."""
    broker = PaperBroker(initial_capital=100000.0, slippage_points=0.10)
    broker.auto_close_time_ist = "15:20"

    pos = await broker.execute_buy(SAMPLE_CONTRACT, current_premium=150.0, underlying_price=24500.0, lots=1, bypass_session_check=True)
    assert pos is not None

    # At 15:20 IST, price is 148.0 (loss)
    now_1520 = datetime(2026, 11, 18, 15, 20, 0, tzinfo=IST)
    trade = await broker.check_and_run_auto_close(
        now=now_1520,
        latest_option_price=148.0,
        is_feed_stale=False,
        is_feed_connected=True
    )

    assert trade is not None
    assert trade.exit_reason == "AUTO_CLOSE_3_20_PM"
    assert broker.active_position is None
    # Executed exit price = 148.0 - 0.10 = 147.90
    assert trade.exit_price == 147.90
    # Gross P&L: (147.90 - 150.10) * 65 = -2.20 * 65 = -143.0
    assert trade.gross_pnl == -143.0
    assert trade.total_charges == 20.0
    assert trade.net_pnl == -163.0
    assert broker.cash_balance == 99837.0

    # Clean up test records
    async with AsyncSessionLocal() as session:
        from sqlalchemy import delete
        from backend.app.models import PaperOrder, PaperPosition, PaperTrade
        await session.execute(delete(PaperTrade).where(PaperTrade.position_id == pos["id"]))
        await session.execute(delete(PaperOrder).where(PaperOrder.position_id == pos["id"]))
        await session.execute(delete(PaperPosition).where(PaperPosition.id == pos["id"]))
        await session.commit()


@pytest.mark.asyncio
async def test_multi_strategy_and_toggle_filters():
    """Test 3: Apply to all strategies toggle & profitable/losing position toggles."""
    broker = PaperBroker(initial_capital=100000.0, slippage_points=0.0)
    broker.auto_close_time_ist = "15:20"
    broker.auto_exit_apply_all = False

    # Open with UT_BOT
    pos = await broker.execute_buy(SAMPLE_CONTRACT, current_premium=150.0, underlying_price=24500.0, lots=1, strategy_id="UT_BOT", bypass_session_check=True)
    assert pos is not None

    now_1520 = datetime(2026, 11, 18, 15, 20, 0, tzinfo=IST)
    # Check with different strategy_id (e.g. EMA_RSI) -> should skip
    res = await broker.check_and_run_auto_close(
        now=now_1520,
        latest_option_price=151.0,
        is_feed_stale=False,
        is_feed_connected=True,
        strategy_id="EMA_RSI"
    )
    assert res is None
    assert broker.active_position is not None

    # Check with matching strategy_id UT_BOT -> should close
    res2 = await broker.check_and_run_auto_close(
        now=now_1520,
        latest_option_price=151.0,
        is_feed_stale=False,
        is_feed_connected=True,
        strategy_id="UT_BOT"
    )
    assert res2 is not None
    assert broker.active_position is None


@pytest.mark.asyncio
async def test_position_already_closed_by_target():
    """Test 4: Position already closed by target at 15:15 is not re-closed at 15:20."""
    broker = PaperBroker(initial_capital=100000.0, slippage_points=0.0)
    broker.auto_close_time_ist = "15:20"

    await broker.execute_buy(SAMPLE_CONTRACT, current_premium=150.0, underlying_price=24500.0, lots=1, bypass_session_check=True)

    # Target hit at 15:15 (+4 pts = 154.0)
    now_1515 = datetime(2026, 11, 18, 15, 15, 0, tzinfo=IST)
    target_trade = await broker.update_tick(SAMPLE_CONTRACT["instrument_token"], current_price=154.0, timestamp=now_1515)
    assert target_trade is not None
    assert target_trade.exit_reason == "TARGET"
    assert broker.active_position is None

    # Scheduler fires at 15:20 IST
    now_1520 = datetime(2026, 11, 18, 15, 20, 0, tzinfo=IST)
    auto_trade = await broker.check_and_run_auto_close(
        now=now_1520,
        latest_option_price=153.0,
        is_feed_stale=False,
        is_feed_connected=True
    )
    assert auto_trade is None
    assert len(broker.closed_trades) == 1  # Exactly 1 trade (target exit), no duplicate trade added


@pytest.mark.asyncio
async def test_position_already_closed_by_stop_loss():
    """Test 5: Position already closed by stop loss at 15:10 is not re-closed at 15:20."""
    broker = PaperBroker(initial_capital=100000.0, slippage_points=0.0)
    broker.auto_close_time_ist = "15:20"

    await broker.execute_buy(SAMPLE_CONTRACT, current_premium=150.0, underlying_price=24500.0, lots=1, bypass_session_check=True)

    # Stop hit at 15:10 (-4 pts = 146.0)
    now_1510 = datetime(2026, 11, 18, 15, 10, 0, tzinfo=IST)
    stop_trade = await broker.update_tick(SAMPLE_CONTRACT["instrument_token"], current_price=146.0, timestamp=now_1510)
    assert stop_trade is not None
    assert stop_trade.exit_reason in ("STOP_LOSS", "GAP_STOP")
    assert broker.active_position is None

    # Scheduler fires at 15:20 IST
    now_1520 = datetime(2026, 11, 18, 15, 20, 0, tzinfo=IST)
    auto_trade = await broker.check_and_run_auto_close(
        now=now_1520,
        latest_option_price=145.0,
        is_feed_stale=False,
        is_feed_connected=True
    )
    assert auto_trade is None


@pytest.mark.asyncio
async def test_duplicate_scheduler_events():
    """Test 6: Duplicate scheduler calls at 15:20:00, 15:20:01, 15:20:02 trigger exit only ONCE."""
    broker = PaperBroker(initial_capital=100000.0, slippage_points=0.0)
    broker.auto_close_time_ist = "15:20"

    await broker.execute_buy(SAMPLE_CONTRACT, current_premium=150.0, underlying_price=24500.0, lots=1, bypass_session_check=True)

    # Call 1: 15:20:00
    t1 = datetime(2026, 11, 18, 15, 20, 0, tzinfo=IST)
    res1 = await broker.check_and_run_auto_close(t1, latest_option_price=151.0, is_feed_stale=False, is_feed_connected=True)
    assert res1 is not None
    assert res1.exit_reason == "AUTO_CLOSE_3_20_PM"

    # Call 2: 15:20:01 (duplicate event)
    t2 = datetime(2026, 11, 18, 15, 20, 1, tzinfo=IST)
    res2 = await broker.check_and_run_auto_close(t2, latest_option_price=151.0, is_feed_stale=False, is_feed_connected=True)
    assert res2 is None

    # Call 3: 15:20:02 (duplicate event)
    t3 = datetime(2026, 11, 18, 15, 20, 2, tzinfo=IST)
    res3 = await broker.check_and_run_auto_close(t3, latest_option_price=151.0, is_feed_stale=False, is_feed_connected=True)
    assert res3 is None


@pytest.mark.asyncio
async def test_market_data_disconnected_or_stale():
    """Test 7: If market data is stale or disconnected, do NOT invent prices. Flag warning and wait for fresh tick."""
    broker = PaperBroker(initial_capital=100000.0, slippage_points=0.0)
    broker.auto_close_time_ist = "15:20"

    await broker.execute_buy(SAMPLE_CONTRACT, current_premium=150.0, underlying_price=24500.0, lots=1, bypass_session_check=True)

    # At 15:20 IST, feed is DISCONNECTED or STALE
    now_1520 = datetime(2026, 11, 18, 15, 20, 0, tzinfo=IST)
    trade = await broker.check_and_run_auto_close(
        now=now_1520,
        latest_option_price=150.0,
        is_feed_stale=True,  # Feed is stale
        is_feed_connected=False  # Feed is disconnected
    )

    # Position must NOT be closed with an invented price!
    assert trade is None
    assert broker.active_position is not None
    assert broker.auto_exit_awaiting_valid_data is True
    assert "awaiting valid" in broker.auto_exit_warning.lower()

    # When valid live tick arrives at 15:21 with reconnected feed
    now_1521 = datetime(2026, 11, 18, 15, 21, 0, tzinfo=IST)
    trade_resumed = await broker.check_and_run_auto_close(
        now=now_1521,
        latest_option_price=152.5,
        is_feed_stale=False,
        is_feed_connected=True
    )
    assert trade_resumed is not None
    assert trade_resumed.exit_reason == "AUTO_CLOSE_3_20_PM"
    assert trade_resumed.exit_price == 152.5
    assert broker.active_position is None
    assert broker.auto_exit_awaiting_valid_data is False
    assert broker.auto_exit_warning is None


@pytest.mark.asyncio
async def test_session_cutoff_prevents_new_entries():
    """Test 8: Prevent new entries for the remainder of the session after 03:20 PM IST."""
    broker = PaperBroker(initial_capital=100000.0)
    broker.auto_close_time_ist = "15:20"
    broker.session_cutoff_active = True

    # Attempt BUY at 15:25 IST
    now_1525 = datetime(2026, 11, 18, 15, 25, 0, tzinfo=IST)
    pos = await broker.execute_buy(SAMPLE_CONTRACT, current_premium=150.0, underlying_price=24500.0, timestamp=now_1525, bypass_session_check=False)
    assert pos is None


@pytest.mark.asyncio
async def test_backend_restart_near_scheduled_exit():
    """Test 9: Backend restart near scheduled exit restores position and auto-closes properly."""
    broker1 = PaperBroker(initial_capital=100000.0, slippage_points=0.0)
    broker1.auto_close_time_ist = "15:20"

    # Buy at 15:18 IST
    t_1518 = datetime(2026, 11, 18, 15, 18, 0, tzinfo=IST)
    pos = await broker1.execute_buy(SAMPLE_CONTRACT, current_premium=150.0, underlying_price=24500.0, timestamp=t_1518, bypass_session_check=True)
    assert pos is not None
    pos_id = pos["id"]

    # Backend restarts at 15:20:15 IST
    broker2 = PaperBroker(initial_capital=100000.0, slippage_points=0.0)
    await broker2.restore_from_db()
    assert broker2.active_position is not None
    assert broker2.active_position["id"] == pos_id

    # Auto exit scheduler runs at 15:20:16 IST
    t_1520 = datetime(2026, 11, 18, 15, 20, 16, tzinfo=IST)
    trade = await broker2.check_and_run_auto_close(
        now=t_1520,
        latest_option_price=152.0,
        is_feed_stale=False,
        is_feed_connected=True
    )
    assert trade is not None
    assert trade.exit_reason == "AUTO_CLOSE_3_20_PM"
    assert broker2.active_position is None
