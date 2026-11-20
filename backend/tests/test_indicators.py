import pytest
from backend.app.strategy.indicators import calculate_ema, calculate_rsi, calculate_vwap


def test_ema_calculation():
    # Constant prices should yield constant EMA
    prices = [100.0] * 30
    ema_9 = calculate_ema(prices, 9)
    assert len(ema_9) == 30
    assert abs(ema_9[-1] - 100.0) < 1e-4

    # Monotonically increasing prices
    prices_up = list(range(1, 31))
    ema_fast = calculate_ema(prices_up, 9)
    ema_slow = calculate_ema(prices_up, 21)
    # Fast EMA should lead slow EMA in an uptrend
    assert ema_fast[-1] > ema_slow[-1]


def test_rsi_calculation():
    # Flat prices -> RSI 50
    prices = [100.0] * 30
    rsi = calculate_rsi(prices, 14)
    assert len(rsi) == 30
    assert abs(rsi[-1] - 50.0) < 1e-4

    # Pure uptrend -> RSI close to 100
    prices_up = [100.0 + (i * 2.0) for i in range(30)]
    rsi_up = calculate_rsi(prices_up, 14)
    assert rsi_up[-1] > 80.0

    # Pure downtrend -> RSI close to 0
    prices_down = [100.0 - (i * 2.0) for i in range(30)]
    rsi_down = calculate_rsi(prices_down, 14)
    assert rsi_down[-1] < 20.0


def test_vwap_calculation():
    candles = [
        {"high": 102.0, "low": 98.0, "close": 100.0, "volume": 1000.0},
        {"high": 104.0, "low": 100.0, "close": 103.0, "volume": 2000.0},
    ]
    vwap = calculate_vwap(candles)
    assert len(vwap) == 2
    # Typical prices: c1 = 100.0, c2 = (104+100+103)/3 = 102.333
    # VWAP = ((100 * 1000) + (102.333 * 2000)) / 3000 = (100000 + 204666.67) / 3000 = 101.56
    assert abs(vwap[-1] - 101.56) < 0.1
