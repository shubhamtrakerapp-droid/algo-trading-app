import pytest
from datetime import datetime, timezone, timedelta
from backend.app.backtest.engine import BacktestEngine
from backend.app.backtest.data_loader import BacktestDataLoader

IST = timezone(timedelta(hours=5, minutes=30))


def test_backtest_runs_consistently():
    engine = BacktestEngine(
        initial_capital=100000.0,
        lots=1,
        lot_size=65,
        target_points=4.0,
        stop_points=4.0,
        max_loss_per_trade=1000.0
    )
    loader = BacktestDataLoader()
    nifty_candles, option_candles = loader.generate_synthetic_backtest_dataset(days=3)

    assert len(nifty_candles) > 100
    assert len(option_candles) > 100

    results = engine.run_backtest(nifty_candles, option_candles, data_source="SYNTHETIC_TEST")

    assert "total_trades" in results
    assert "win_rate" in results
    assert "net_profit" in results
    assert results["data_source"] == "SYNTHETIC_TEST"

    # Verify each trade executed against option price, not NIFTY spot price
    for t in results["trades"]:
        # Option premium is ~100-200, while NIFTY spot is ~24000
        assert t["entry_price"] < 500.0
        assert t["underlying_price"] > 20000.0
        assert t["quantity"] == 65
        assert t["exit_reason"] in ["TARGET", "STOP_LOSS", "GAP_STOP", "FORCE_EXIT_1520", "AUTO_CLOSE_3_20_PM", "UT_SELL_SIGNAL"]

    # Also test EMA_RSI strategy explicitly
    ema_results = engine.run_backtest(nifty_candles, option_candles, strategy_id="EMA_RSI", data_source="SYNTHETIC_TEST")
    assert "total_trades" in ema_results
    for t in ema_results["trades"]:
        assert t["entry_price"] < 500.0
        assert t["underlying_price"] > 20000.0
        assert t["exit_reason"] in ["TARGET", "STOP_LOSS", "GAP_STOP", "FORCE_EXIT_1520", "AUTO_CLOSE_3_20_PM"]
