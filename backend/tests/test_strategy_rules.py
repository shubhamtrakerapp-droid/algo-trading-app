import pytest
from datetime import datetime, timezone, timedelta
from backend.app.strategy.engine import StrategyEngine
from backend.app.adapters.base import CandleData

IST = timezone(timedelta(hours=5, minutes=30))


def create_candle(dt_utc: datetime, close: float) -> CandleData:
    return CandleData(
        timestamp=dt_utc,
        open=close - 1.0,
        high=close + 1.0,
        low=close - 1.0,
        close=close,
        volume=1000.0,
        complete=True
    )


def test_session_filter_boundaries():
    engine = StrategyEngine(session_start_ist="09:20", session_end_ist="15:15", force_exit_ist="15:20")

    # 09:19 IST -> False
    t_0919 = datetime(2026, 11, 18, 9, 19, tzinfo=IST)
    assert engine.is_within_trading_session(t_0919) is False

    # 09:20 IST -> True
    t_0920 = datetime(2026, 11, 18, 9, 20, tzinfo=IST)
    assert engine.is_within_trading_session(t_0920) is True

    # 15:15 IST -> True
    t_1515 = datetime(2026, 11, 18, 15, 15, tzinfo=IST)
    assert engine.is_within_trading_session(t_1515) is True

    # 15:16 IST -> False
    t_1516 = datetime(2026, 11, 18, 15, 16, tzinfo=IST)
    assert engine.is_within_trading_session(t_1516) is False

    # 15:20 IST -> Force Exit
    t_1520 = datetime(2026, 11, 18, 15, 20, tzinfo=IST)
    assert engine.is_force_exit_time(t_1520) is True


def test_strategy_buy_signal_confirmed():
    engine = StrategyEngine(session_start_ist="09:20", session_end_ist="15:15")

    # Build 60 candles in a strong uptrend during market session (e.g. 10:00 IST onwards)
    base_time = datetime(2026, 11, 18, 10, 0, tzinfo=IST).astimezone(timezone.utc)
    candles = []
    price = 24000.0
    for i in range(60):
        t = base_time + timedelta(minutes=i)
        price += 10.0  # Steady uptrend
        candles.append(create_candle(t, price))

    eval_res = engine.evaluate_completed_candle(candles)
    assert eval_res is not None

    # In a 60-bar steady uptrend:
    # Condition 1: EMA 9 > EMA 21
    assert eval_res.condition_1 is True
    # Condition 2: Close > EMA 50
    assert eval_res.condition_2 is True
    # Condition 3: RSI 14 > 50
    assert eval_res.condition_3 is True
    # Condition 4: Session filter (10:00 to 11:00 IST is within 09:20 - 15:15)
    assert eval_res.condition_4 is True

    # All 4 conditions satisfied -> BUY_ATM_CE
    assert eval_res.signal == "BUY_ATM_CE"
    assert eval_res.is_buy is True


def test_strategy_outside_session_no_signal():
    engine = StrategyEngine(session_start_ist="09:20", session_end_ist="15:15")

    # Build candles outside trading session (e.g. 08:30 IST)
    base_time = datetime(2026, 11, 18, 7, 0, tzinfo=IST).astimezone(timezone.utc)
    candles = []
    price = 24000.0
    for i in range(60):
        t = base_time + timedelta(minutes=i)
        price += 10.0
        candles.append(create_candle(t, price))

    eval_res = engine.evaluate_completed_candle(candles)
    assert eval_res is not None
    # Condition 4 must be False outside 09:20 - 15:15 IST
    assert eval_res.condition_4 is False
    assert eval_res.is_buy is False
    assert eval_res.signal == "NONE"


def test_strategy_requires_at_least_50_candles():
    engine = StrategyEngine()
    base_time = datetime(2026, 11, 18, 10, 0, tzinfo=IST).astimezone(timezone.utc)
    # Only 30 candles provided
    candles = [create_candle(base_time + timedelta(minutes=i), 24000.0 + i) for i in range(30)]
    eval_res = engine.evaluate_completed_candle(candles)
    assert eval_res is None  # Must return None to prevent premature unreliable evaluation
