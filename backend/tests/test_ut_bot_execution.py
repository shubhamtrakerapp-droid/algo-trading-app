import pytest
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any
from backend.app.strategy.ut_bot import UTBotStrategy
from backend.app.backtest.engine import BacktestEngine


IST = timezone(timedelta(hours=5, minutes=30))


def generate_oscillating_candles(num_candles: int = 55) -> List[Dict[str, Any]]:
    """
    Generate candles with 2 complete up-down oscillations:
    - Bar 0-10: declining (150 -> 130)
    - Bar 11-20: rally (130 -> 170) -> BUY signal at bar 11
    - Bar 21-30: drop (170 -> 130) -> SELL signal at bar 22
    - Bar 31-40: rally (130 -> 170) -> second BUY signal at bar 32
    - Bar 41-50: drop (170 -> 130) -> second SELL signal at bar 42
    """
    base_dt = datetime(2026, 11, 18, 9, 20, tzinfo=IST)
    candles = []
    for i in range(num_candles):
        if i <= 10:
            price = 150.0 - i * 2.0
        elif 11 <= i <= 20:
            price = 130.0 + (i - 10) * 4.0
        elif 21 <= i <= 30:
            price = 170.0 - (i - 20) * 4.0
        elif 31 <= i <= 40:
            price = 130.0 + (i - 30) * 4.0
        else:
            price = 170.0 - (i - 40) * 4.0

        c_time = base_dt + timedelta(minutes=i)
        candles.append({
            "timestamp": c_time.isoformat(),
            "open": round(price - 0.2, 2),
            "high": round(price + 1.0, 2),
            "low": round(price - 1.0, 2),
            "close": round(price, 2),
            "volume": 5000,
            "symbol": "NIFTY ATM CE",
            "strike": 24500.0,
            "expiry": "WEEKLY"
        })
    return candles


def generate_sell_first_candles(num_candles: int = 25) -> List[Dict[str, Any]]:
    """
    Generate candles where bar 0-8 are flat (warmup), then bar 9 plunges,
    triggering a SELL signal at bar 9 with no prior BUY or open position.
    """
    base_dt = datetime(2026, 11, 18, 9, 20, tzinfo=IST)
    candles = []
    for i in range(num_candles):
        if i <= 8:
            price = 150.0 + (i % 2) * 0.5
        else:
            price = 150.0 - (i - 8) * 3.0

        c_time = base_dt + timedelta(minutes=i)
        candles.append({
            "timestamp": c_time.isoformat(),
            "open": round(price - 0.2, 2),
            "high": round(price + 1.0, 2),
            "low": round(price - 1.0, 2),
            "close": round(price, 2),
            "volume": 5000,
            "symbol": "NIFTY ATM CE",
            "strike": 24500.0,
            "expiry": "WEEKLY"
        })
    return candles


def generate_target_exit_candles(num_candles: int = 25) -> List[Dict[str, Any]]:
    """
    Generate candles where a BUY signal triggers at bar 11, and bar 12 touches +4.0 Target.
    """
    base_dt = datetime(2026, 11, 18, 9, 20, tzinfo=IST)
    candles = []
    for i in range(num_candles):
        if i <= 10:
            price = 150.0 - i * 2.0
        elif 11 <= i <= 13:
            price = 130.0 + (i - 10) * 4.0
        else:
            price = 142.0 + (i - 13) * 3.0

        c_time = base_dt + timedelta(minutes=i)
        high_val = price + (10.0 if i == 12 else 1.0)
        candles.append({
            "timestamp": c_time.isoformat(),
            "open": round(price - 0.2, 2),
            "high": round(high_val, 2),
            "low": round(price - 1.0, 2),
            "close": round(price, 2),
            "volume": 5000,
            "symbol": "NIFTY ATM CE",
            "strike": 24500.0,
            "expiry": "WEEKLY"
        })
    return candles


def test_ut_bot_buy_opens_position():
    """Requirement 1: BUY signal with no open position opens BUY position."""
    candles = generate_oscillating_candles(num_candles=25)
    engine = BacktestEngine(
        initial_capital=100000.0,
        lots=5,
        lot_size=65,
        target_points=50.0,
        stop_points=50.0,
        execution_mode="TRIGGER_PRICE",
        exit_on_ut_sell_signal=True
    )

    results = engine.run_backtest(
        nifty_candles=candles,
        option_candles=candles,
        strategy_id="UT_BOT",
        ut_bot_params={
            "key_value": 1.0,
            "atr_period": 5,
            "target_points": 50.0,
            "stop_points": 50.0,
            "signal_source": "CHART_INSTRUMENT"
        },
        timeframe_minutes=1,
        instrument_symbol="NIFTY ATM CE",
        data_source="SYNTHETIC_TEST"
    )

    assert results["total_trades"] >= 1
    assert results["buy_entries_count"] >= 1
    first_trade = results["trades"][0]
    assert first_trade["entry_price"] > 0
    assert first_trade["quantity"] == 325


def test_ut_bot_sell_closes_position_with_correct_exit_reason():
    """Requirement 1 & 4: SELL signal with an open BUY position closes position with exit_reason='UT_SELL_SIGNAL'."""
    candles = generate_oscillating_candles(num_candles=30)
    engine = BacktestEngine(
        initial_capital=100000.0,
        lots=5,
        lot_size=65,
        target_points=50.0,  # Wide target to ensure UT Sell causes the exit
        stop_points=50.0,    # Wide stop to ensure UT Sell causes the exit
        execution_mode="TRIGGER_PRICE",
        exit_on_ut_sell_signal=True
    )

    results = engine.run_backtest(
        nifty_candles=candles,
        option_candles=candles,
        strategy_id="UT_BOT",
        ut_bot_params={
            "key_value": 1.0,
            "atr_period": 5,
            "target_points": 50.0,
            "stop_points": 50.0,
            "signal_source": "CHART_INSTRUMENT"
        },
        timeframe_minutes=1,
        instrument_symbol="NIFTY ATM CE",
        data_source="SYNTHETIC_TEST"
    )

    ut_sell_trades = [t for t in results["trades"] if t["exit_reason"] == "UT_SELL_SIGNAL"]
    assert len(ut_sell_trades) >= 1
    assert results["sell_exits_count"] >= 1

    first_ut_exit = ut_sell_trades[0]
    assert first_ut_exit["exit_reason"] == "UT_SELL_SIGNAL"
    assert first_ut_exit["exit_price"] > 0
    assert first_ut_exit["gross_pnl"] != 0.0
    assert first_ut_exit["net_pnl"] != 0.0


def test_ut_bot_sell_without_position_is_ignored():
    """Requirement 1: SELL signal with no open position does NOT create a trade (short selling disabled)."""
    candles = generate_sell_first_candles(num_candles=15)
    engine = BacktestEngine(
        initial_capital=100000.0,
        lots=5,
        lot_size=65,
        target_points=10.0,
        stop_points=5.0,
        execution_mode="TRIGGER_PRICE",
        exit_on_ut_sell_signal=True
    )

    results = engine.run_backtest(
        nifty_candles=candles,
        option_candles=candles,
        strategy_id="UT_BOT",
        ut_bot_params={
            "key_value": 1.0,
            "atr_period": 5,
            "signal_source": "CHART_INSTRUMENT"
        },
        timeframe_minutes=1,
        instrument_symbol="NIFTY ATM CE",
        data_source="SYNTHETIC_TEST"
    )

    # Zero trades executed because SELL signals without position must be ignored
    assert results["total_trades"] == 0
    # Diagnostics must record the ignored SELL signal
    diagnostics = results.get("execution_diagnostics", [])
    ignored_sells = [d for d in diagnostics if d["signal_type"] == "SELL" and d["action_taken"] == "IGNORED"]
    assert len(ignored_sells) >= 1
    assert "Short selling disabled" in ignored_sells[0]["action_reason"]


def test_repeated_buy_signals_do_not_create_duplicates():
    """Requirement 1: Repeated BUY signals while already in position are suppressed (no duplicate entries)."""
    candles = generate_oscillating_candles(num_candles=55)
    engine = BacktestEngine(
        initial_capital=100000.0,
        lots=5,
        lot_size=65,
        target_points=100.0,
        stop_points=50.0,
        execution_mode="TRIGGER_PRICE",
        exit_on_ut_sell_signal=True
    )

    results = engine.run_backtest(
        nifty_candles=candles,
        option_candles=candles,
        strategy_id="UT_BOT",
        ut_bot_params={
            "key_value": 1.0,
            "atr_period": 5,
            "signal_source": "CHART_INSTRUMENT"
        },
        timeframe_minutes=1,
        instrument_symbol="NIFTY ATM CE",
        data_source="SYNTHETIC_TEST"
    )

    trades = results["trades"]
    # Check that there are never overlapping positions
    for idx in range(len(trades) - 1):
        assert trades[idx]["exit_time"] <= trades[idx + 1]["entry_time"]


def test_multiple_buy_sell_cycles():
    """Requirement 1 & 6: Multiple complete BUY -> SELL cycles execute correctly."""
    candles = generate_oscillating_candles(num_candles=55)
    engine = BacktestEngine(
        initial_capital=100000.0,
        lots=5,
        lot_size=65,
        target_points=50.0,
        stop_points=50.0,
        execution_mode="TRIGGER_PRICE",
        exit_on_ut_sell_signal=True
    )

    results = engine.run_backtest(
        nifty_candles=candles,
        option_candles=candles,
        strategy_id="UT_BOT",
        ut_bot_params={
            "key_value": 1.0,
            "atr_period": 5,
            "target_points": 50.0,
            "stop_points": 50.0,
            "signal_source": "CHART_INSTRUMENT"
        },
        timeframe_minutes=1,
        instrument_symbol="NIFTY ATM CE",
        data_source="SYNTHETIC_TEST"
    )

    # 2 complete cycles executed
    assert results["total_trades"] >= 2
    assert results["buy_entries_count"] >= 2
    assert results["sell_exits_count"] >= 2

    trades = results["trades"]
    for i in range(len(trades) - 1):
        assert trades[i]["entry_time"] < trades[i]["exit_time"]
        assert trades[i]["exit_time"] <= trades[i + 1]["entry_time"]


def test_pe_option_trading_behavior():
    """Requirement 2: NIFTY ATM PE trading executes BUY PE and exits on SELL."""
    candles = generate_oscillating_candles(num_candles=30)
    for c in candles:
        c["symbol"] = "NIFTY 24500 PE"

    engine = BacktestEngine(
        initial_capital=100000.0,
        lots=5,
        lot_size=65,
        target_points=50.0,
        stop_points=50.0,
        execution_mode="TRIGGER_PRICE",
        exit_on_ut_sell_signal=True
    )

    results = engine.run_backtest(
        nifty_candles=candles,
        option_candles=candles,
        strategy_id="UT_BOT",
        ut_bot_params={
            "key_value": 1.0,
            "atr_period": 5,
            "target_points": 50.0,
            "stop_points": 50.0,
            "signal_source": "CHART_INSTRUMENT"
        },
        timeframe_minutes=1,
        instrument_symbol="NIFTY ATM PE",
        data_source="SYNTHETIC_TEST"
    )

    assert results["total_trades"] >= 1
    first_trade = results["trades"][0]
    assert first_trade["contract_type"] == "PE"


def test_direct_nifty_index_trading():
    """Requirement 3: NIFTY 50 direct index executes directly on index candles."""
    candles = generate_oscillating_candles(num_candles=30)
    for c in candles:
        c["symbol"] = "NIFTY 50"

    engine = BacktestEngine(
        initial_capital=100000.0,
        lots=5,
        lot_size=65,
        target_points=50.0,
        stop_points=50.0,
        execution_mode="TRIGGER_PRICE",
        exit_on_ut_sell_signal=True
    )

    results = engine.run_backtest(
        nifty_candles=candles,
        option_candles=candles,
        strategy_id="UT_BOT",
        ut_bot_params={
            "key_value": 1.0,
            "atr_period": 5,
            "target_points": 50.0,
            "stop_points": 50.0,
            "signal_source": "NIFTY_INDEX"
        },
        timeframe_minutes=1,
        instrument_symbol="NIFTY 50",
        data_source="SYNTHETIC_TEST"
    )

    assert results["signal_instrument"] == "NIFTY 50 Index"
    assert "Direct" in results["execution_instrument"]
    assert results["total_trades"] >= 1
    assert results["trades"][0]["contract_type"] == "INDEX"


def test_sl_and_target_still_work_when_sell_signal_not_triggered():
    """Requirement 4 & 6: Stop Loss and Target exits still work when SELL signal has not triggered."""
    candles = generate_target_exit_candles(num_candles=25)
    engine = BacktestEngine(
        initial_capital=100000.0,
        lots=5,
        lot_size=65,
        target_points=4.0,   # Tight target of 4.0 points
        stop_points=2.0,    # Tight stop of 2.0 points
        execution_mode="TRIGGER_PRICE",
        exit_on_ut_sell_signal=True
    )

    results = engine.run_backtest(
        nifty_candles=candles,
        option_candles=candles,
        strategy_id="UT_BOT",
        ut_bot_params={
            "key_value": 1.0,
            "atr_period": 5,
            "target_points": 4.0,
            "stop_points": 2.0,
            "signal_source": "CHART_INSTRUMENT"
        },
        timeframe_minutes=1,
        instrument_symbol="NIFTY ATM CE",
        data_source="SYNTHETIC_TEST"
    )

    assert results["total_trades"] >= 1
    first_trade = results["trades"][0]
    # Trade exited via TARGET
    assert first_trade["exit_reason"] in ("TARGET", "TARGET_LIMIT")
    assert results["target_exits_count"] >= 1
    assert first_trade["exit_price"] == round(first_trade["entry_price"] + 4.0, 2)


def test_execution_diagnostics_logging():
    """Requirement 5: Execution diagnostics log contains every signal with action, prices, P&L."""
    candles = generate_oscillating_candles(num_candles=35)
    engine = BacktestEngine(
        initial_capital=100000.0,
        lots=5,
        lot_size=65,
        target_points=50.0,
        stop_points=50.0,
        execution_mode="TRIGGER_PRICE",
        exit_on_ut_sell_signal=True
    )

    results = engine.run_backtest(
        nifty_candles=candles,
        option_candles=candles,
        strategy_id="UT_BOT",
        ut_bot_params={
            "key_value": 1.0,
            "atr_period": 5,
            "target_points": 50.0,
            "stop_points": 50.0,
            "signal_source": "CHART_INSTRUMENT"
        },
        timeframe_minutes=1,
        instrument_symbol="NIFTY ATM CE",
        data_source="SYNTHETIC_TEST"
    )

    diagnostics = results.get("execution_diagnostics", [])
    assert len(diagnostics) > 0

    # Verify diagnostic schema
    for diag in diagnostics:
        assert "timestamp" in diag
        assert "signal_type" in diag
        assert "signal_instrument" in diag
        assert "execution_instrument" in diag
        assert "position_before_signal" in diag
        assert "action_taken" in diag
        assert diag["action_taken"] in ("ENTRY", "EXIT", "IGNORED")
        assert "action_reason" in diag
        assert "gross_pnl" in diag
        assert "net_pnl" in diag


@pytest.mark.asyncio
async def test_backtest_save_and_csv_export():
    """Requirement 6: Trade history, analytics, and CSV export match the new execution results."""
    candles = generate_oscillating_candles(num_candles=55)
    engine = BacktestEngine(
        initial_capital=100000.0,
        lots=5,
        lot_size=65,
        target_points=50.0,
        stop_points=50.0,
        execution_mode="TRIGGER_PRICE",
        exit_on_ut_sell_signal=True
    )

    results = engine.run_backtest(
        nifty_candles=candles,
        option_candles=candles,
        strategy_id="UT_BOT",
        ut_bot_params={
            "key_value": 1.0,
            "atr_period": 5,
            "target_points": 50.0,
            "stop_points": 50.0,
            "signal_source": "CHART_INSTRUMENT"
        },
        timeframe_minutes=1,
        instrument_symbol="NIFTY ATM CE",
        data_source="SYNTHETIC_TEST"
    )

    run_id = await engine.save_backtest_run(results)
    assert run_id > 0

    from backend.app.api.routes_backtest import get_backtest_run_details, export_backtest_csv
    details = await get_backtest_run_details(run_id)
    assert details["run"]["id"] == run_id
    assert len(details["trades"]) == results["total_trades"]

    csv_resp = await export_backtest_csv(run_id)
    assert csv_resp.status_code == 200
    csv_text = csv_resp.body.decode("utf-8")
    assert "UT_SELL_SIGNAL" in csv_text
    assert "Trade ID" in csv_text

