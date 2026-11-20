import pytest
import asyncio
from backend.app.paper.broker import PaperBroker
from backend.app.database import init_db, AsyncSessionLocal
from backend.app.models import PaperPosition


@pytest.mark.asyncio
async def test_restart_recovery_of_open_position():
    await init_db()

    # Instance 1: Opens a position
    broker1 = PaperBroker(initial_capital=100000.0)
    contract = {
        "instrument_token": "OPT_24500_CE",
        "symbol": "NIFTY26NOV24500CE",
        "strike": 24500.0,
        "expiry": "2026-11-26",
        "lot_size": 65
    }

    pos1 = await broker1.execute_buy(contract, current_premium=150.0, underlying_price=24500.0, bypass_session_check=True)
    assert pos1 is not None
    pos_id = pos1["id"]

    # Simulate backend crash/restart: Instantiate a fresh broker2
    broker2 = PaperBroker(initial_capital=100000.0)
    assert broker2.active_position is None

    # Call restore_from_db()
    await broker2.restore_from_db()

    # broker2 must have recovered the exact open position!
    assert broker2.active_position is not None
    assert broker2.active_position["id"] == pos_id
    assert broker2.active_position["symbol"] == "NIFTY26NOV24500CE"
    assert broker2.active_position["entry_price"] == pos1["entry_price"]

    # Now verify broker2 can complete the trade on target hit
    res = await broker2.update_tick("OPT_24500_CE", current_price=160.0)
    assert res is not None
    assert res.exit_reason == "TARGET"
    assert broker2.active_position is None
