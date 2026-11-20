import pytest
from datetime import datetime, timezone, timedelta
from backend.app.strategy.indicators import calculate_atr, calculate_heikin_ashi, aggregate_candles
from backend.app.strategy.ut_bot import UTBotStrategy


def test_atr_calculation():
    """Verify ATR computes properly with Wilder's smoothing."""
    highs = [100 + i * 2 for i in range(20)]
    lows = [95 + i * 2 for i in range(20)]
    closes = [98 + i * 2 for i in range(20)]

    atr = calculate_atr(highs, lows, closes, period=10)
    assert len(atr) == 20
    assert all(a > 0 for a in atr)
    # True range for each candle is 5 (high - low = 5, gap is 4), so ATR should hover around 5
    assert 4.0 <= atr[-1] <= 6.0


def test_heikin_ashi_calculation():
    """Verify Heikin Ashi values compute properly."""
    opens = [100.0, 102.0, 104.0]
    highs = [105.0, 107.0, 108.0]
    lows = [98.0, 100.0, 103.0]
    closes = [103.0, 105.0, 107.0]

    ha = calculate_heikin_ashi(opens, highs, lows, closes)
    assert len(ha["close"]) == 3
    # ha_close[0] = (100 + 105 + 98 + 103) / 4 = 101.5
    assert ha["close"][0] == 101.5
    # ha_open[0] = (100 + 103) / 2 = 101.5
    assert ha["open"][0] == 101.5


def test_ut_bot_trailing_stop_recursion():
    """Verify UT Bot trailing stop adjusts upward with rising price and downward with falling price."""
    strategy = UTBotStrategy(key_value=1.0, atr_period=5, lots=5, lot_size=65)

    base_time = datetime(2026, 11, 18, 9, 30, tzinfo=timezone.utc)
    # Rising price series
    candles = []
    for i in range(15):
        price = 100.0 + i * 3.0
        candles.append({
            "timestamp": base_time + timedelta(minutes=i),
            "open": price - 1.0,
            "high": price + 2.0,
            "low": price - 2.0,
            "close": price,
            "volume": 1000,
            "symbol": "NIFTY26NOV25250CE"
        })

    evals = strategy.calculate_series(candles)
    assert len(evals) == 15

    # With monotonically rising prices, the trailing stop should move upward
    trailing_stops = [e.trailing_stop for e in evals]
    assert trailing_stops[-1] > trailing_stops[0]


def test_ut_bot_buy_crossover_only_once():
    """
    CRITICAL: Verify BUY signal generates ONLY on the crossover candle,
    and NOT on every subsequent candle while price stays above trailing stop (Solves ISSUE C).
    """
    strategy = UTBotStrategy(key_value=1.0, atr_period=5, lots=5, lot_size=65)

    base_time = datetime(2026, 11, 18, 9, 30, tzinfo=timezone.utc)
    # Start in downtrend (stops above price), then jump up (crossover), then stay high
    candles = []
    # 8 declining candles
    for i in range(8):
        price = 200.0 - i * 5.0
        candles.append({
            "timestamp": base_time + timedelta(minutes=i),
            "open": price + 2.0,
            "high": price + 3.0,
            "low": price - 3.0,
            "close": price,
            "volume": 1000,
            "symbol": "TEST"
        })

    # Sudden surge upward on candle 8: crossover!
    for i in range(8, 14):
        price = 220.0 + (i - 8) * 2.0
        candles.append({
            "timestamp": base_time + timedelta(minutes=i),
            "open": price - 1.0,
            "high": price + 2.0,
            "low": price - 1.0,
            "close": price,
            "volume": 1000,
            "symbol": "TEST"
        })

    evals = strategy.calculate_series(candles)
    buy_signals = [i for i, e in enumerate(evals) if e.is_buy]

    # Must produce exactly ONE buy signal on the crossover candle, NOT repeated
    assert len(buy_signals) == 1
    assert buy_signals[0] == 8
    # Subsequent candles 9, 10, 11, 12, 13 must NOT have is_buy = True!
    for idx in range(9, 14):
        assert not evals[idx].is_buy


def test_ut_bot_effective_stop_points():
    """Verify UT Bot risk overlay: baseline 4 points vs ₹1,000 risk cap."""
    # 5 lots * 65 = 325 qty
    strat_baseline = UTBotStrategy(lots=5, lot_size=65, stop_points=4.0, max_loss_per_trade=None)
    assert strat_baseline.calculate_effective_stop_points() == 4.0

    strat_capped = UTBotStrategy(lots=5, lot_size=65, stop_points=4.0, max_loss_per_trade=1000.0)
    # 1000 / 325 = 3.0769
    assert strat_capped.calculate_effective_stop_points() == round(1000.0 / 325, 4)
