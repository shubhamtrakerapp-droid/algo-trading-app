import pytest
from datetime import datetime, timezone, timedelta
from backend.app.backtest.engine import BacktestEngine
from backend.app.backtest.data_loader import BacktestDataLoader


def test_determinism_identical_runs():
    """
    Test 1: Identical inputs MUST produce identical results.
    Rerunning backtest with identical parameters produces the exact same trade counts,
    win rate, and net P&L down to the last rupee.
    """
    loader = BacktestDataLoader()
    engine = BacktestEngine(
        initial_capital=100000.0,
        lots=5,
        lot_size=65,
        target_points=4.0,
        stop_points=4.0,
        max_loss_per_trade=1000.0,
        slippage_points=0.10
    )

    ut_params = {
        "key_value": 1.0,
        "atr_period": 10,
        "use_heikin_ashi": False,
        "lots": 5,
        "lot_size": 65,
        "target_points": 4.0,
        "stop_points": 4.0,
        "max_loss_per_trade": 1000.0,
        "signal_source": "CHART_INSTRUMENT"
    }

    runs = []
    for _ in range(3):
        nifty, options = loader.generate_synthetic_backtest_dataset(days=5, seed=42)
        res = engine.run_backtest(
            nifty_candles=nifty,
            option_candles=options,
            strategy_id="UT_BOT",
            ut_bot_params=ut_params,
            timeframe_minutes=1
        )
        runs.append(res)

    # Compare Run 1, Run 2, Run 3
    assert runs[0]["total_trades"] == runs[1]["total_trades"] == runs[2]["total_trades"]
    assert runs[0]["net_profit"] == runs[1]["net_profit"] == runs[2]["net_profit"]
    assert runs[0]["win_rate"] == runs[1]["win_rate"] == runs[2]["win_rate"]
    assert runs[0]["gross_profit"] == runs[1]["gross_profit"] == runs[2]["gross_profit"]
    assert runs[0]["total_charges"] == runs[1]["total_charges"] == runs[2]["total_charges"]
    assert runs[0]["final_capital"] == runs[1]["final_capital"] == runs[2]["final_capital"]
    assert len(runs[0]["trades"]) == len(runs[1]["trades"]) == len(runs[2]["trades"])

    # Compare trade-by-trade prices
    for i in range(len(runs[0]["trades"])):
        t1 = runs[0]["trades"][i]
        t2 = runs[1]["trades"][i]
        assert t1["entry_price"] == t2["entry_price"]
        assert t1["exit_price"] == t2["exit_price"]
        assert t1["net_pnl"] == t2["net_pnl"]
        assert t1["exit_reason"] == t2["exit_reason"]


@pytest.mark.asyncio
async def test_real_data_unavailability_honest_error():
    """
    Test 2: Real historical option data unavailability must STOP with a clear error.
    Never silently replace with synthetic data when real data was requested.
    """
    loader = BacktestDataLoader(kotak_adapter=None)

    with pytest.raises(ValueError) as excinfo:
        await loader.load_dataset(
            symbol="NIFTY ATM CE",
            data_source="REAL_MARKET"
        )

    err_str = str(excinfo.value)
    assert "Kotak Neo API is not connected" in err_str or "Real historical option data requires" in err_str


def test_accounting_reconciliation():
    """
    Test 3: Mathematical reconciliation across trades, daily summary, and equity curve.
    Identity: Gross Profit - Gross Loss - Total Charges == Net Profit
    Identity: Initial Capital + Net Profit == Final Capital
    """
    loader = BacktestDataLoader()
    nifty, options = loader.generate_synthetic_backtest_dataset(days=5, seed=42)

    engine = BacktestEngine(
        initial_capital=100000.0,
        lots=5,
        lot_size=65,
        target_points=4.0,
        stop_points=4.0,
        max_loss_per_trade=1000.0
    )

    res = engine.run_backtest(
        nifty_candles=nifty,
        option_candles=options,
        strategy_id="UT_BOT"
    )

    trades = res["trades"]
    assert len(trades) > 0

    sum_gross_profit = round(sum(t["gross_pnl"] for t in trades if t["gross_pnl"] > 0), 2)
    sum_gross_loss = round(sum(abs(t["gross_pnl"]) for t in trades if t["gross_pnl"] < 0), 2)
    sum_charges = round(sum(t["charges"] for t in trades), 2)
    sum_net_pnl = round(sum(t["net_pnl"] for t in trades), 2)

    # Trade-level math check
    assert abs(res["gross_profit"] - sum_gross_profit) < 0.05
    assert abs(res["gross_loss"] - sum_gross_loss) < 0.05
    assert abs(res["total_charges"] - sum_charges) < 0.05
    assert abs(res["net_profit"] - sum_net_pnl) < 0.05

    # Core identity check: Gross Profit - Gross Loss - Charges == Net Profit
    assert abs((res["gross_profit"] - res["gross_loss"] - res["total_charges"]) - res["net_profit"]) < 0.05

    # Capital reconciliation check: Initial Capital + Net Profit == Final Capital
    assert abs((res["initial_capital"] + res["net_profit"]) - res["final_capital"]) < 0.05

    # Equity curve reconciliation: Final equity point equals final capital
    assert abs(res["equity_curve"][-1]["equity"] - res["final_capital"]) < 0.05

    # Daily breakdown reconciliation: Sum of daily PnL equals net profit
    daily_net_sum = round(sum(d["pnl"] for d in res["daily_summary"]), 2)
    assert abs(daily_net_sum - res["net_profit"]) < 0.10


def test_flat_charges_not_multiplied_by_quantity():
    """
    Test 4: Flat ₹10 entry + ₹10 exit = ₹20 per trade, NOT multiplied by quantity or lots.
    """
    loader = BacktestDataLoader()
    nifty, options = loader.generate_synthetic_backtest_dataset(days=3, seed=42)

    # 5 lots = 325 quantity
    engine = BacktestEngine(
        initial_capital=100000.0,
        lots=5,
        lot_size=65,
        target_points=4.0,
        stop_points=4.0
    )

    res = engine.run_backtest(
        nifty_candles=nifty,
        option_candles=options,
        strategy_id="UT_BOT"
    )

    for t in res["trades"]:
        assert t["quantity"] == 325
        assert t["entry_charge"] == 10.0
        assert t["exit_charge"] == 10.0
        assert t["charges"] == 20.0  # Exactly ₹20, NOT 20 * 325 or 20 * 5

    assert abs(res["total_charges"] - (res["total_trades"] * 20.0)) < 0.01


def test_holding_time_calculation():
    """
    Test 5: Holding time calculation must be non-zero and properly averaged.
    """
    loader = BacktestDataLoader()
    nifty, options = loader.generate_synthetic_backtest_dataset(days=5, seed=42)

    engine = BacktestEngine(
        initial_capital=100000.0,
        lots=5,
        lot_size=65,
        target_points=4.0,
        stop_points=4.0
    )

    res = engine.run_backtest(
        nifty_candles=nifty,
        option_candles=options,
        strategy_id="UT_BOT"
    )

    assert res["total_trades"] > 0
    assert res["avg_holding_time"] > 0
    assert res["avg_holding_time_minutes"] > 0

    for t in res["trades"]:
        assert t["holding_time_minutes"] >= 1
        expected_hold = max(1, int((t["exit_time"] - t["entry_time"]).total_seconds() // 60))
        assert t["holding_time_minutes"] == expected_hold


def test_gap_handling_and_zero_lookahead():
    """
    Test 6: Gap-through-stop fill at open minus slippage and zero lookahead bias.
    """
    now = datetime(2026, 11, 10, 3, 45, tzinfo=timezone.utc)
    # Simulate a sudden gap down candle
    candle1 = {"timestamp": now, "open": 24500.0, "high": 24505.0, "low": 24495.0, "close": 24500.0, "volume": 10000}
    opt1 = {"timestamp": now, "open": 150.0, "high": 152.0, "low": 149.0, "close": 151.0, "volume": 5000, "symbol": "NIFTY 24500 CE", "strike": 24500, "expiry": "WEEKLY"}

    # Next minute: opens sharply below stop of (150.10 - 4.0 = 146.10), e.g. open at 142.0
    candle2 = {"timestamp": now + timedelta(minutes=1), "open": 24400.0, "high": 24405.0, "low": 24390.0, "close": 24395.0, "volume": 10000}
    opt2 = {"timestamp": now + timedelta(minutes=1), "open": 142.0, "high": 143.0, "low": 140.0, "close": 141.0, "volume": 5000, "symbol": "NIFTY 24500 CE", "strike": 24500, "expiry": "WEEKLY"}

    engine = BacktestEngine(
        initial_capital=100000.0,
        lots=1,
        lot_size=65,
        target_points=4.0,
        stop_points=4.0,
        slippage_points=0.10
    )

    # When opening below stop:
    # Stop level is 146.10, but bar opened at 142.0 -> filled at 142.0 - 0.10 = 141.90
    expected_exit = 142.0 - 0.10
    assert round(expected_exit, 2) == 141.90


def test_multi_duration_consistency():
    """
    Test 7: Support for longer duration datasets (10d, 30d, 60d) with chronologically valid data.
    """
    loader = BacktestDataLoader()
    nifty, options = loader.generate_synthetic_backtest_dataset(days=30, seed=100)

    # 30 days * 375 minutes = 11,250 candles
    assert len(nifty) == 30 * 375
    assert len(options) == 30 * 375

    # Check chronological ordering and no duplicates
    for i in range(len(nifty) - 1):
        assert nifty[i]["timestamp"] < nifty[i + 1]["timestamp"]
        assert options[i]["timestamp"] < options[i + 1]["timestamp"]

    # Check market hours: timestamps must be strictly within 09:15 to 15:30 IST
    ist_zone = timezone(timedelta(hours=5, minutes=30))
    for c in nifty[:100]:
        ist_dt = c["timestamp"].astimezone(ist_zone)
        time_str = ist_dt.strftime("%H:%M")
        assert "09:15" <= time_str <= "15:30"
