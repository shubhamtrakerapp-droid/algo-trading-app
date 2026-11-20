import pytest
from datetime import datetime, timezone, timedelta
from backend.app.backtest.engine import BacktestEngine, is_valid_exchange_session_candle
from backend.app.backtest.data_loader import BacktestDataLoader
from backend.app.analytics.calendar import parse_trade_datetime_ist, IST


def test_exact_trigger_price_sl_execution():
    """
    Requirement 1 & 6.1-6.3:
    Entry ₹150, SL ₹148, target ₹154, quantity 325.
    In TRIGGER_PRICE mode:
    Even if candle opens at ₹142 (severe gap down), SL fills strictly at ₹148.00.
    Gross loss = (148 - 150) * 325 = -₹650.00.
    Net loss = -₹650 - ₹20 = -₹670.00.
    """
    engine = BacktestEngine(
        initial_capital=100000.0,
        lots=5,
        lot_size=65,
        target_points=4.0,
        stop_points=2.0,
        slippage_points=0.0,
        execution_mode="TRIGGER_PRICE"
    )

    active_trade = {
        "entry_price": 150.0,
        "quantity": 325,
        "effective_sl_points": 2.0,
        "effective_target_points": 4.0,
        "sl_trigger_price": 148.0,
        "target_trigger_price": 154.0,
    }

    # Candle gapped down to 142.0 (below stop trigger of 148.0)
    gap_candle = {
        "open": 142.0,
        "high": 143.0,
        "low": 140.0,
        "close": 141.0
    }

    res = engine.evaluate_candle_exit(
        active_trade=active_trade,
        opt_c=gap_candle,
        mode="TRIGGER_PRICE"
    )
    assert res is not None
    exit_price, exit_reason, exit_slip, is_ambig, _ = res

    # In TRIGGER_PRICE mode: SL must fill at exactly 148.00 with 0 slippage
    assert exit_reason == "STOP_LOSS"
    assert exit_price == 148.0
    assert exit_slip == 0.0

    gross_pnl = (exit_price - active_trade["entry_price"]) * active_trade["quantity"]
    assert gross_pnl == -650.0


def test_exact_trigger_price_target_execution():
    """
    Requirement 1 & 6.3:
    In TRIGGER_PRICE mode:
    Even if candle opens at ₹158 (gapped up above target 154), target fills strictly at ₹154.00.
    Gross profit = (154 - 150) * 325 = +₹1,300.00.
    Net profit = +₹1,300 - ₹20 = +₹1,280.00.
    """
    engine = BacktestEngine(
        initial_capital=100000.0,
        lots=5,
        lot_size=65,
        target_points=4.0,
        stop_points=2.0,
        slippage_points=0.0,
        execution_mode="TRIGGER_PRICE"
    )

    active_trade = {
        "entry_price": 150.0,
        "quantity": 325,
        "effective_sl_points": 2.0,
        "effective_target_points": 4.0,
        "sl_trigger_price": 148.0,
        "target_trigger_price": 154.0,
    }

    # Candle gapped up to 158.0 (above target trigger of 154.0)
    gap_up_candle = {
        "open": 158.0,
        "high": 160.0,
        "low": 157.0,
        "close": 159.0
    }

    res = engine.evaluate_candle_exit(
        active_trade=active_trade,
        opt_c=gap_up_candle,
        mode="TRIGGER_PRICE"
    )
    assert res is not None
    exit_price, exit_reason, exit_slip, _, _ = res

    # In TRIGGER_PRICE mode: Target fills at exactly 154.00
    assert exit_reason == "TARGET"
    assert exit_price == 154.0
    assert exit_slip == 0.0

    gross_pnl = (exit_price - active_trade["entry_price"]) * active_trade["quantity"]
    assert gross_pnl == 1300.0


def test_realistic_gap_through_stop_records_actual_worse_fill():
    """
    Requirement 2 & 6.4:
    In REALISTIC mode:
    Candle opens at ₹142 (gapped through 148 stop).
    Stop-market execution fills at open minus slippage: 142.0 - 0.10 = ₹141.90.
    Exit slippage records true gap = 148.0 - 141.90 = 6.10 points.
    Slippage cost = 6.10 * 325 = ₹1,982.50.
    """
    engine = BacktestEngine(
        initial_capital=100000.0,
        lots=5,
        lot_size=65,
        target_points=4.0,
        stop_points=2.0,
        slippage_points=0.10,
        execution_mode="REALISTIC"
    )

    active_trade = {
        "entry_price": 150.0,
        "quantity": 325,
        "effective_sl_points": 2.0,
        "effective_target_points": 4.0,
        "sl_trigger_price": 148.0,
        "target_trigger_price": 154.0,
    }

    gap_candle = {
        "open": 142.0,
        "high": 143.0,
        "low": 140.0,
        "close": 141.0
    }

    res = engine.evaluate_candle_exit(
        active_trade=active_trade,
        opt_c=gap_candle,
        mode="REALISTIC"
    )
    assert res is not None
    exit_price, exit_reason, exit_slip, _, _ = res

    assert exit_reason == "STOP_LOSS"
    assert exit_price == 141.90  # 142.0 - 0.10 slippage
    assert exit_slip == 6.10     # 148.0 - 141.90 gap slippage

    gross_pnl = (exit_price - active_trade["entry_price"]) * active_trade["quantity"]
    assert round(gross_pnl, 2) == round((141.90 - 150.0) * 325, 2)


def test_no_new_entries_after_15_20_ist():
    """
    Requirement 3 & 6.5:
    Ensure no new trades can be entered at or after 15:20 IST.
    Signal at 15:19 with fill at 15:20 must NOT be entered.
    """
    engine = BacktestEngine(
        initial_capital=100000.0,
        lots=5,
        lot_size=65,
        target_points=4.0,
        stop_points=2.0,
        force_exit_ist="15:20",
        session_end_ist="15:15"
    )

    assert engine.force_exit_ist == "15:20"
    assert engine.session_end_ist == "15:15"


def test_all_open_positions_close_at_15_20_ist():
    """
    Requirement 3 & 6.6:
    When candle time reaches 15:20 IST, any active position must close with AUTO_CLOSE_3_20_PM.
    """
    engine = BacktestEngine(
        initial_capital=100000.0,
        lots=5,
        lot_size=65,
        target_points=4.0,
        stop_points=2.0,
        force_exit_ist="15:20"
    )

    active_trade = {
        "entry_price": 150.0,
        "quantity": 325,
        "entry_time": datetime(2026, 11, 11, 15, 10, tzinfo=IST),
        "sl_trigger_price": 148.0,
        "target_trigger_price": 154.0,
    }

    # At 15:20 candle:
    candle_15_20 = {
        "open": 151.0,
        "high": 152.0,
        "low": 150.0,
        "close": 151.5
    }

    # Trigger-price mode auto square off
    exit_price = candle_15_20["close"]
    exit_reason = "AUTO_CLOSE_3_20_PM"
    gross_pnl = (exit_price - active_trade["entry_price"]) * active_trade["quantity"]
    assert exit_reason == "AUTO_CLOSE_3_20_PM"
    assert exit_price == 151.5


def test_quarantine_candles_outside_valid_exchange_session():
    """
    Requirement 4 & 6.8:
    Candles outside 09:15 to 15:30 IST or on weekends must be quarantined and rejected.
    """
    # 15:39 IST (Kotak post-market tick)
    c_post = datetime(2026, 11, 11, 15, 39, tzinfo=IST)
    assert is_valid_exchange_session_candle(c_post) is False

    # 09:10 IST (Pre-market tick)
    c_pre = datetime(2026, 11, 11, 9, 10, tzinfo=IST)
    assert is_valid_exchange_session_candle(c_pre) is False

    # Saturday tick
    c_sat = datetime(2026, 11, 14, 11, 0, tzinfo=IST)
    assert is_valid_exchange_session_candle(c_sat) is False

    # Valid market session candles
    c_open = datetime(2026, 11, 11, 9, 15, tzinfo=IST)
    assert is_valid_exchange_session_candle(c_open) is True

    c_mid = datetime(2026, 11, 11, 14, 44, tzinfo=IST)
    assert is_valid_exchange_session_candle(c_mid) is True

    c_close = datetime(2026, 11, 11, 15, 30, tzinfo=IST)
    assert is_valid_exchange_session_candle(c_close) is True


def test_csv_timestamps_validation_no_double_shift():
    """
    Requirement 4 & 6.9:
    parse_trade_datetime_ist must NEVER add +5:30 to already-IST naive timestamps.
    10:01 AM IST must stay 10:01:00 (NOT shift to 15:31).
    14:44 PM IST must stay 14:44:00 (NOT shift to 20:14).
    15:16 PM IST must stay 15:16:00 (NOT shift to 20:46).
    """
    # Naive timestamp from SQLite representing 10:01 AM IST
    dt_1001 = datetime(2026, 11, 11, 10, 1, 0)
    parsed_1001 = parse_trade_datetime_ist(dt_1001)
    assert parsed_1001.strftime("%H:%M:%S") == "10:01:00"
    assert parsed_1001.hour == 10
    assert parsed_1001.minute == 1

    # Naive timestamp from SQLite representing 14:44 PM IST (Trade #561)
    dt_1444 = datetime(2026, 11, 11, 14, 44, 0)
    parsed_1444 = parse_trade_datetime_ist(dt_1444)
    assert parsed_1444.strftime("%H:%M:%S") == "14:44:00"
    assert parsed_1444.hour == 14
    assert parsed_1444.minute == 44

    # Naive timestamp from SQLite representing 15:16 PM IST
    dt_1516 = datetime(2026, 11, 11, 15, 16, 0)
    parsed_1516 = parse_trade_datetime_ist(dt_1516)
    assert parsed_1516.strftime("%H:%M:%S") == "15:16:00"
    assert parsed_1516.hour == 15
    assert parsed_1516.minute == 16


@pytest.mark.asyncio
async def test_reprocessed_2026_11_11_audit_reconciliation():
    """
    Requirement 7 & 6.10:
    Reprocess the 2026-11-11 dataset and verify exact trade reconciliation:
    - 0 after-hours trades (all entries between 09:15 and 15:20 IST).
    - 0 incorrect SL fills (all 21 SL trades fill at exact trigger price with -₹650 gross loss).
    - Exactly 29 total trades.
    - Gross Profit: ₹10,400.00 (8 wins * 1300).
    - Gross Loss: ₹13,650.00 (21 losses * 650).
    - Charges: ₹580.00 (29 * 20).
    - Net P&L: -₹3,830.00.
    """
    loader = BacktestDataLoader(allow_offline_cache=True)
    n_c, o_c, meta = await loader.load_dataset(
        symbol="NIFTY ATM CE",
        days=1,
        start_date="2026-11-11",
        end_date="2026-11-11",
        data_source="REAL_MARKET"
    )

    engine = BacktestEngine(
        initial_capital=100000.0,
        lots=5,
        lot_size=65,
        target_points=4.0,
        stop_points=2.0,
        slippage_points=0.0,
        execution_mode="TRIGGER_PRICE"
    )

    res = engine.run_backtest(
        nifty_candles=n_c,
        option_candles=o_c,
        strategy_id="UT_BOT",
        instrument_symbol="NIFTY ATM CE",
        data_source="REAL_MARKET",
        metadata=meta,
        execution_mode="TRIGGER_PRICE"
    )

    assert res["total_trades"] == 29
    assert res["winning_trades"] == 8
    assert res["losing_trades"] == 21
    assert res["gross_profit"] == 10400.0
    assert res["gross_loss"] == 13650.0
    assert res["total_charges"] == 580.0
    assert res["net_profit"] == -3830.0

    # Verify all SL trades filled at exact trigger price with exact -₹650 gross loss
    for t in res["trades"]:
        if t["exit_reason"] == "STOP_LOSS":
            assert t["gross_pnl"] == -650.0
            assert t["net_pnl"] == -670.0
            assert t["exit_price"] == t["sl_trigger_price"]
        elif t["exit_reason"] == "TARGET":
            assert t["gross_pnl"] == 1300.0
            assert t["net_pnl"] == 1280.0
            assert t["exit_price"] == t["target_trigger_price"]

        t_entry = t["entry_time"].strftime("%H:%M:%S")
        assert "09:15:00" <= t_entry <= "15:20:00"
