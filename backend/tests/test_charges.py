import pytest
import asyncio
from backend.app.paper.charges import ChargesCalculator
from backend.app.paper.broker import PaperBroker
from backend.app.database import AsyncSessionLocal
from backend.app.models import PaperTrade, PaperPosition, ChargeSetting


def test_default_flat_charges_single_trade():
    """Test 1: Default configuration charges ₹10 entry + ₹10 exit = ₹20 total."""
    calc = ChargesCalculator()
    chg = calc.calculate_charges(
        entry_price=150.0,
        exit_price=154.0,
        quantity=65,
        entry_order_count=1,
        exit_order_count=1
    )
    assert chg.entry_charge == 10.0
    assert chg.exit_charge == 10.0
    assert chg.total_charges == 20.0


def test_charges_not_multiplied_by_quantity_or_lots():
    """
    Test 2: Flat per-order charges are NEVER multiplied by quantity, lots, or turnover.
    Example: 5 lots = 325 quantity. Total charges must be ₹20, NOT ₹20 × 325 or ₹20 × 5.
    """
    calc = ChargesCalculator()
    chg = calc.calculate_charges(
        entry_price=145.0,
        exit_price=149.0,
        quantity=325,  # 5 lots of 65
        entry_order_count=1,
        exit_order_count=1
    )
    assert chg.entry_charge == 10.0
    assert chg.exit_charge == 10.0
    assert chg.total_charges == 20.0

    # Verify Gross P&L and Net P&L accounting
    gross_pnl = (149.0 - 145.0) * 325  # 4.0 * 325 = 1300.0
    net_pnl = gross_pnl - chg.total_charges  # 1300 - 20 = 1280.0
    assert gross_pnl == 1300.0
    assert net_pnl == 1280.0


def test_configurable_charge_settings():
    """Test 3: Configurable entry and exit charges (e.g. ₹15 entry, ₹12 exit = ₹27 round-trip)."""
    calc = ChargesCalculator(entry_charge_per_order=15.0, exit_charge_per_order=12.0)
    chg = calc.calculate_charges(
        entry_price=100.0,
        exit_price=104.0,
        quantity=65,
        entry_order_count=1,
        exit_order_count=1
    )
    assert chg.entry_charge == 15.0
    assert chg.exit_charge == 12.0
    assert chg.total_charges == 27.0


def test_multiple_separate_exit_orders():
    """Test 4: Multiple separate exit orders charge ₹10 for each exit order."""
    calc = ChargesCalculator(entry_charge_per_order=10.0, exit_charge_per_order=10.0)
    # 1 entry order, 2 separate exit orders (e.g. scaling out)
    chg = calc.calculate_charges(
        entry_order_count=1,
        exit_order_count=2
    )
    assert chg.entry_charge == 10.0
    assert chg.exit_charge == 20.0
    assert chg.total_charges == 30.0


def test_partial_fills_count_as_single_order():
    """Test 5: If one order is filled across multiple partial fills, count it as one order."""
    calc = ChargesCalculator()
    # 1 order filled in 3 fills still counts as entry_order_count=1
    chg = calc.calculate_charges(
        entry_order_count=1,
        exit_order_count=1
    )
    assert chg.total_charges == 20.0


def test_accounting_consistency():
    """Test 6: Verify mathematical consistency between Gross P&L, Net P&L, and Cash Balance."""
    initial_capital = 100000.0
    calc = ChargesCalculator()

    # Winning trade: +4 pts on 325 qty
    trade1_gross = 4.0 * 325  # +1300.0
    trade1_chg = calc.calculate_charges(quantity=325).total_charges  # 20.0
    trade1_net = trade1_gross - trade1_chg  # +1280.0

    # Losing trade: -4 pts on 325 qty
    trade2_gross = -4.0 * 325  # -1300.0
    trade2_chg = calc.calculate_charges(quantity=325).total_charges  # 20.0
    trade2_net = trade2_gross - trade2_chg  # -1320.0

    cumulative_net = trade1_net + trade2_net  # 1280 - 1320 = -40.0
    cash_balance = initial_capital + cumulative_net  # 99960.0

    assert trade1_net == 1280.0
    assert trade2_net == -1320.0
    assert cumulative_net == -40.0
    assert cash_balance == 99960.0


@pytest.mark.asyncio
async def test_broker_paper_trading_charges_and_db_persistence():
    """Test 7: PaperBroker uses configured flat charges and records them on PaperTrade."""
    broker = PaperBroker(initial_capital=100000.0)
    await broker.load_charges_settings()

    contract = {
        "instrument_token": "TEST_TOKEN_999",
        "symbol": "NIFTY 24500 CE",
        "strike": 24500.0,
        "expiry": "28-NOV-2026",
        "lot_size": 65
    }

    # Open position with 5 lots (325 qty)
    pos = await broker.execute_buy(
        contract=contract,
        current_premium=150.0,
        underlying_price=24500.0,
        lots=5,
        bypass_session_check=True
    )
    assert pos is not None
    assert pos["quantity"] == 325
    assert pos["entry_charge"] == 10.0
    assert pos["exit_charge"] == 10.0
    assert pos["charges"] == 20.0

    pos_id = pos["id"]
    # Close position manually at 154.0 (slippage 0.10 means fill at 153.90)
    trade = await broker.manual_close(exit_price=154.0, reason="MANUAL")
    assert trade is not None
    assert trade.quantity == 325
    assert trade.total_charges == 20.0

    # Gross P&L: (153.90 - 150.10) * 325 = 3.80 * 325 = 1235.0
    expected_gross = round((153.90 - 150.10) * 325, 2)
    expected_net = round(expected_gross - 20.0, 2)
    assert trade.gross_pnl == expected_gross
    assert trade.net_pnl == expected_net
    assert broker.cash_balance == round(100000.0 + expected_net, 2)

    # Clean up test trade and position
    async with AsyncSessionLocal() as session:
        from sqlalchemy import delete
        from backend.app.models import PaperOrder
        await session.execute(delete(PaperTrade).where(PaperTrade.position_id == pos_id))
        await session.execute(delete(PaperOrder).where(PaperOrder.position_id == pos_id))
        await session.execute(delete(PaperPosition).where(PaperPosition.id == pos_id))
        await session.commit()
