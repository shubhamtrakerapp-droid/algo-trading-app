import pytest
import asyncio
from datetime import datetime, timezone, timedelta
from backend.app.paper.broker import PaperBroker
from backend.app.database import init_db

IST = timezone(timedelta(hours=5, minutes=30))
T_1030_IST = datetime(2026, 11, 18, 10, 30, 0, tzinfo=IST)


@pytest.fixture(autouse=True)
def run_around_tests():
    # Setup test DB tables
    asyncio.run(init_db())
    yield


def test_risk_and_quantity_calculation():
    broker = PaperBroker(
        initial_capital=100000.0,
        default_lots=1,
        target_points=4.0,
        stop_points=4.0,
        max_loss_per_trade=1000.0
    )

    # 1. 1 lot with lot size 65:
    # Quantity = 65
    # Max loss pts = 1000 / 65 = 15.38 pts
    # Effective stop = min(4.0, 15.38) = 4.0 pts
    risk_65 = broker.calculate_risk_parameters(lots=1, lot_size=65, entry_price=150.0)
    assert risk_65["quantity"] == 65
    assert risk_65["max_loss_points"] == 15.38
    assert risk_65["effective_stop_distance"] == 4.0
    assert risk_65["target_price"] == 154.0
    assert risk_65["stop_price"] == 146.0

    # 2. Large quantity case (e.g., 5 lots of 65 = 325 quantity):
    # Quantity = 325
    # Max loss pts = 1000 / 325 = 3.08 pts
    # Since 3.08 < 4.0, effective stop distance MUST tighten to 3.08 pts!
    risk_325 = broker.calculate_risk_parameters(lots=5, lot_size=65, entry_price=150.0)
    assert risk_325["quantity"] == 325
    assert risk_325["max_loss_points"] == 3.08
    assert risk_325["effective_stop_distance"] == 3.08
    assert risk_325["target_price"] == 154.0
    assert risk_325["stop_price"] == round(150.0 - 3.08, 2)


@pytest.mark.asyncio
async def test_target_execution():
    broker = PaperBroker(initial_capital=100000.0, target_points=4.0, stop_points=4.0, slippage_points=0.0)
    contract = {
        "instrument_token": "OPT_24500_CE",
        "symbol": "NIFTY26NOV24500CE",
        "strike": 24500.0,
        "expiry": "2026-11-26",
        "lot_size": 65
    }

    # Open position at premium 150.0
    pos = await broker.execute_buy(contract, current_premium=150.0, underlying_price=24500.0, lots=1, bypass_session_check=True)
    assert pos is not None
    assert pos["status"] == "OPEN"
    assert pos["entry_price"] == 150.0
    assert pos["target_price"] == 154.0
    assert pos["stop_price"] == 146.0

    # Price ticks to 152.0 (no exit)
    res = await broker.update_tick(token="OPT_24500_CE", current_price=152.0, timestamp=T_1030_IST)
    assert res is None
    assert broker.active_position is not None

    # Price hits target 154.0
    res_target = await broker.update_tick(token="OPT_24500_CE", current_price=154.0, timestamp=T_1030_IST)
    assert res_target is not None
    assert res_target.exit_reason == "TARGET"
    assert res_target.gross_pnl == round(4.0 * 65, 2)  # +260.0
    assert broker.active_position is None


@pytest.mark.asyncio
async def test_stop_loss_execution():
    broker = PaperBroker(initial_capital=100000.0, target_points=4.0, stop_points=4.0, slippage_points=0.0)
    contract = {
        "instrument_token": "OPT_24500_CE",
        "symbol": "NIFTY26NOV24500CE",
        "strike": 24500.0,
        "expiry": "2026-11-26",
        "lot_size": 65
    }

    pos = await broker.execute_buy(contract, current_premium=150.0, underlying_price=24500.0, lots=1, bypass_session_check=True)
    assert pos is not None

    # Price hits exact stop 146.0
    res_stop = await broker.update_tick(token="OPT_24500_CE", current_price=146.0, timestamp=T_1030_IST)
    assert res_stop is not None
    assert res_stop.exit_reason == "STOP_LOSS"
    assert res_stop.gross_pnl == round(-4.0 * 65, 2)  # -260.0
    assert broker.active_position is None


@pytest.mark.asyncio
async def test_gap_down_through_stop():
    broker = PaperBroker(initial_capital=100000.0, target_points=4.0, stop_points=4.0, slippage_points=0.0)
    contract = {
        "instrument_token": "OPT_24500_CE",
        "symbol": "NIFTY26NOV24500CE",
        "strike": 24500.0,
        "expiry": "2026-11-26",
        "lot_size": 65
    }

    pos = await broker.execute_buy(contract, current_premium=150.0, underlying_price=24500.0, lots=1, bypass_session_check=True)
    assert pos is not None

    # Sudden gap down to 142.0 (below stop of 146.0)
    res_gap = await broker.update_tick(token="OPT_24500_CE", current_price=142.0, timestamp=T_1030_IST)
    assert res_gap is not None
    assert res_gap.exit_reason == "GAP_STOP"
    assert res_gap.exit_price == 142.0
    assert res_gap.gross_pnl == round((142.0 - 150.0) * 65, 2)  # -520.0
    assert broker.active_position is None


@pytest.mark.asyncio
async def test_duplicate_order_prevention():
    broker = PaperBroker(initial_capital=100000.0)
    contract = {
        "instrument_token": "OPT_24500_CE",
        "symbol": "NIFTY26NOV24500CE",
        "strike": 24500.0,
        "expiry": "2026-11-26",
        "lot_size": 65
    }

    # First order succeeds
    pos1 = await broker.execute_buy(contract, current_premium=150.0, underlying_price=24500.0, bypass_session_check=True)
    assert pos1 is not None

    # Second order while first is open MUST be rejected
    pos2 = await broker.execute_buy(contract, current_premium=150.0, underlying_price=24500.0, bypass_session_check=True)
    assert pos2 is None

    # Cleanly close pos1 so no unclosed test position leaks into DB
    await broker.manual_close(150.0)
    assert broker.active_position is None


@pytest.mark.asyncio
async def test_force_exit_at_1520():
    broker = PaperBroker(initial_capital=100000.0, force_exit_time_ist="15:20", slippage_points=0.0)
    contract = {
        "instrument_token": "OPT_24500_CE",
        "symbol": "NIFTY26NOV24500CE",
        "strike": 24500.0,
        "expiry": "2026-11-26",
        "lot_size": 65
    }

    # Enter before 15:20
    pos = await broker.execute_buy(contract, current_premium=150.0, underlying_price=24500.0, bypass_session_check=True)
    assert pos is not None

    # Ticks arrive at 15:20 IST
    t_1520 = datetime(2026, 11, 18, 15, 20, 0, tzinfo=IST)
    res = await broker.update_tick(token="OPT_24500_CE", current_price=151.0, timestamp=t_1520)

    assert res is not None
    assert res.exit_reason in ["AUTO_CLOSE_3_20_PM", "FORCE_EXIT_1520"]
    assert broker.active_position is None
