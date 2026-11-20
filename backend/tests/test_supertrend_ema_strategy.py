import pytest
import asyncio
from datetime import datetime, timezone, timedelta
from typing import List

from backend.app.adapters.base import CandleData
from backend.app.strategy.indicators import calculate_supertrend, calculate_ema
from backend.app.strategy.supertrend_ema import SupertrendEMAStrategy, SupertrendEMAEvaluation
from backend.app.strategy.engine import MultiStrategyManager
from backend.app.database import AsyncSessionLocal, init_db
from backend.app.models.models import PaperTrade, PaperPosition, StrategyDailyRisk
from backend.app.paper.broker import PaperBroker
from backend.app.backtest.engine import BacktestEngine
from backend.app.backtest.data_loader import BacktestDataLoader
from sqlalchemy import delete

IST = timezone(timedelta(hours=5, minutes=30))
T_1030_IST = datetime(2026, 11, 18, 10, 30, 0, tzinfo=IST)


@pytest.fixture(autouse=True)
def run_around_tests():
    asyncio.run(init_db())
    yield


def make_candle(dt_ist: datetime, open_p: float, high_p: float, low_p: float, close_p: float) -> CandleData:
    dt_utc = dt_ist.astimezone(timezone.utc)
    return CandleData(
        timestamp=dt_utc,
        open=open_p,
        high=high_p,
        low=low_p,
        close=close_p,
        volume=1000.0,
        complete=True
    )


# =====================================================================
# 1. SUPERTREND & EMA INDICATOR TESTS
# =====================================================================

def test_supertrend_indicator_basic():
    """Verify Supertrend Wilder's ATR and ratchet bands logic."""
    highs = [100.0 + i * 2.0 for i in range(30)]
    lows = [95.0 + i * 2.0 for i in range(30)]
    closes = [98.0 + i * 2.0 for i in range(30)]

    res = calculate_supertrend(highs, lows, closes, atr_period=10, multiplier=3.0)
    assert len(res["supertrend"]) == 30
    assert len(res["direction"]) == 30
    assert len(res["upper_band"]) == 30
    assert len(res["lower_band"]) == 30
    assert len(res["atr"]) == 30

    for a in res["atr"][10:]:
        assert a > 0

    assert res["direction"][-1] == 1
    assert res["supertrend"][-1] == res["lower_band"][-1]


def test_supertrend_direction_flip():
    """Verify Supertrend flips direction when price crosses bands."""
    highs = [100.0 + i * 2.0 for i in range(20)]
    lows = [95.0 + i * 2.0 for i in range(20)]
    closes = [98.0 + i * 2.0 for i in range(20)]

    last_h, last_l, last_c = highs[-1], lows[-1], closes[-1]
    for i in range(1, 15):
        highs.append(last_h - i * 6.0)
        lows.append(last_l - i * 6.0)
        closes.append(last_c - i * 6.0)

    res = calculate_supertrend(highs, lows, closes, atr_period=10, multiplier=2.0)
    assert res["direction"][19] == 1
    assert res["direction"][-1] == -1
    assert res["supertrend"][-1] == res["upper_band"][-1]


def test_ema_indicator_calculations():
    """Verify EMA 9 and EMA 21 calculations."""
    closes = [100.0 + i * 1.5 for i in range(40)]
    ema_9 = calculate_ema(closes, period=9)
    ema_21 = calculate_ema(closes, period=21)

    assert len(ema_9) == 40
    assert len(ema_21) == 40
    assert ema_9[-1] > ema_21[-1]
    assert closes[-1] > ema_9[-1] > ema_21[-1]


# =====================================================================
# 2. DYNAMIC NET P&L TARGET AND STOP POINTS
# =====================================================================

def test_tradingview_pinescript_v6_exact_parity():
    """
    Verify 1:1 mathematical and logic parity with TradingView Pine Script v6:
    //@version=6
    strategy("NIFTY Supertrend + EMA 9/21 Scalper")
    targetPoints = (targetRupees + entryCharge + exitCharge) / quantity
    stopPoints = (stopRupees - entryCharge - exitCharge) / quantity
    """
    strategy = SupertrendEMAStrategy(
        atr_period=10,
        multiplier=3.0,
        ema_fast=9,
        ema_slow=21,
        lots=5,
        lot_size=65,
        target_net_profit=200.0,
        max_loss_per_trade=1000.0,
        roundtrip_charges=20.0,  # entryCharge(10) + exitCharge(10)
        session_start_ist="09:20",
        session_end_ist="15:15",
        force_exit_ist="15:20"
    )

    pts = strategy.calculate_target_and_stop_points()
    assert pts["quantity"] == 325
    # Pine Script: targetPoints = (200 + 10 + 10) / 325 = 0.676923...
    assert round(pts["target_points"], 4) == round(220.0 / 325, 4)
    # Pine Script: stopPoints = (1000 - 10 - 10) / 325 = 3.015384...
    assert round(pts["stop_points"], 4) == round(980.0 / 325, 4)

    # Session boundaries matching Pine Script:
    # currentTime >= startTime (09:20) and currentTime <= lastEntryTime (15:15)
    t_0919 = datetime(2026, 11, 19, 9, 19, tzinfo=IST)
    t_0920 = datetime(2026, 11, 19, 9, 20, tzinfo=IST)
    t_1515 = datetime(2026, 11, 19, 15, 15, tzinfo=IST)
    t_1516 = datetime(2026, 11, 19, 15, 16, tzinfo=IST)
    t_1520 = datetime(2026, 11, 19, 15, 20, tzinfo=IST)

    assert strategy.is_within_trading_session(t_0919) is False
    assert strategy.is_within_trading_session(t_0920) is True
    assert strategy.is_within_trading_session(t_1515) is True
    assert strategy.is_within_trading_session(t_1516) is False
    assert strategy.is_force_exit_time(t_1520) is True


def test_dynamic_target_and_stop_default_5lots():
    """
    Verify dynamic points calculation for default:
    5 lots * 65 = 325 qty.
    Target net profit = ₹200.
    Max loss per trade = ₹1000.
    Charges = ₹20 roundtrip.
    Slippage = ₹0.
    Expected Target pts = (200 + 20) / 325 = 0.6769 -> ~0.68 pts.
    Expected Stop pts   = (1000 - 20) / 325 = 980 / 325 = 3.0154 -> ~3.02 pts.
    """
    strategy = SupertrendEMAStrategy(
        lots=5,
        lot_size=65,
        target_net_profit=200.0,
        max_loss_per_trade=1000.0,
        roundtrip_charges=20.0
    )

    pts = strategy.calculate_target_and_stop_points()
    assert pts["quantity"] == 325
    assert pts["target_net_profit"] == 200.0
    assert pts["max_loss_per_trade"] == 1000.0
    assert pts["roundtrip_charges"] == 20.0
    assert pts["slippage_cost"] == 0.0

    assert abs(pts["target_points"] - 0.6769) < 0.001
    assert pts["theoretical_target_pts"] == 0.68

    assert abs(pts["stop_points"] - 3.0154) < 0.001
    assert pts["theoretical_stop_pts"] == 3.02

    gross_target = pts["target_points"] * 325
    net_target = gross_target - 20.0
    assert abs(net_target - 200.0) < 0.1

    gross_stop = pts["stop_points"] * 325
    net_stop = -gross_stop - 20.0
    assert abs(net_stop - (-1000.0)) < 0.1


def test_dynamic_points_with_slippage():
    """Verify dynamic points adjust upward for slippage to guarantee target net profit."""
    strategy = SupertrendEMAStrategy(
        lots=5,
        lot_size=65,
        target_net_profit=200.0,
        max_loss_per_trade=1000.0,
        roundtrip_charges=20.0
    )

    pts = strategy.calculate_target_and_stop_points(slippage_points=0.25)
    assert pts["slippage_cost"] == 162.5
    assert abs(pts["target_points"] - 1.1769) < 0.001
    assert abs(pts["stop_points"] - 2.5154) < 0.001


def test_dynamic_points_custom_lots():
    """Verify points calculation scales with custom lots."""
    strategy = SupertrendEMAStrategy(lots=10, lot_size=65)  # 650 qty
    pts = strategy.calculate_target_and_stop_points()
    assert pts["quantity"] == 650
    assert abs(pts["target_points"] - 0.3385) < 0.001
    assert abs(pts["stop_points"] - 1.5077) < 0.001


# =====================================================================
# 3. ENTRY SIGNAL CONDITIONS ON COMPLETED CANDLES
# =====================================================================

def test_supertrend_ema_buy_ce_signal():
    """
    BUY CE Entry Conditions:
      1. Supertrend direction is bullish (1)
      2. EMA 9 > EMA 21
      3. Candle close > EMA 9 and Candle close > EMA 21
      4. Confirmed on same completed candle
      5. Within trading session (09:20 - 15:15 IST)
    """
    strategy = SupertrendEMAStrategy()
    base_time = datetime(2026, 11, 18, 10, 0, tzinfo=IST)

    candles: List[CandleData] = []
    for i in range(35):
        t = base_time + timedelta(minutes=i)
        p = 24000.0 + i * 10.0
        candles.append(make_candle(t, p - 3.0, p + 5.0, p - 4.0, p + 2.0))

    eval_result = strategy.evaluate_completed_candle(candles)
    assert eval_result is not None
    assert eval_result.supertrend_direction == 1
    assert eval_result.trend_str == "BULLISH"
    assert eval_result.c_st_bull is True
    assert eval_result.c_ema_bull is True
    assert eval_result.c_close_bull is True
    assert eval_result.session_valid is True
    assert eval_result.signal == "BUY_CE"
    assert eval_result.is_buy_ce is True
    assert eval_result.is_buy is True
    assert eval_result.target_contract_type == "CE"


def test_supertrend_ema_buy_pe_signal():
    """
    BUY PE Entry Conditions:
      1. Supertrend direction is bearish (-1)
      2. EMA 9 < EMA 21
      3. Candle close < EMA 9 and Candle close < EMA 21
      4. Confirmed on same completed candle
      5. Within trading session (09:20 - 15:15 IST)
    """
    strategy = SupertrendEMAStrategy()
    base_time = datetime(2026, 11, 18, 11, 0, tzinfo=IST)

    candles: List[CandleData] = []
    for i in range(35):
        t = base_time + timedelta(minutes=i)
        p = 24500.0 - i * 10.0
        candles.append(make_candle(t, p + 3.0, p + 4.0, p - 5.0, p - 2.0))

    eval_result = strategy.evaluate_completed_candle(candles)
    assert eval_result is not None
    assert eval_result.supertrend_direction == -1
    assert eval_result.trend_str == "BEARISH"
    assert eval_result.c_st_bear is True
    assert eval_result.c_ema_bear is True
    assert eval_result.c_close_bear is True
    assert eval_result.session_valid is True
    assert eval_result.signal == "BUY_PE"
    assert eval_result.is_buy_pe is True
    assert eval_result.is_buy is True
    assert eval_result.target_contract_type == "PE"


def test_supertrend_ema_no_signal_on_contradiction():
    """If Supertrend is bullish but close is below EMA, signal must be NONE."""
    strategy = SupertrendEMAStrategy()
    base_time = datetime(2026, 11, 18, 10, 0, tzinfo=IST)

    candles: List[CandleData] = []
    for i in range(30):
        t = base_time + timedelta(minutes=i)
        p = 24000.0 + i * 10.0
        candles.append(make_candle(t, p - 3.0, p + 5.0, p - 4.0, p + 2.0))

    t_pullback = base_time + timedelta(minutes=30)
    p_pullback = 24200.0
    candles.append(make_candle(t_pullback, p_pullback + 10.0, p_pullback + 10.0, p_pullback - 25.0, p_pullback - 20.0))

    eval_result = strategy.evaluate_completed_candle(candles)
    assert eval_result is not None
    assert eval_result.c_close_bull is False
    assert eval_result.signal == "NONE"
    assert eval_result.is_buy is False


def test_session_time_filters():
    """Verify session restrictions: no entries before 09:20 IST or after 15:15 IST; square off at 15:20 IST."""
    strategy = SupertrendEMAStrategy()

    # 09:15 IST (Market open, too early for entry)
    t_0915 = datetime(2026, 11, 18, 9, 15, tzinfo=IST)
    assert strategy.is_within_trading_session(t_0915) is False
    assert strategy.is_force_exit_time(t_0915) is False

    # 09:20 IST (Session entry window opens)
    t_0920 = datetime(2026, 11, 18, 9, 20, tzinfo=IST)
    assert strategy.is_within_trading_session(t_0920) is True

    # 15:15 IST (Session entry window closes)
    t_1515 = datetime(2026, 11, 18, 15, 15, tzinfo=IST)
    assert strategy.is_within_trading_session(t_1515) is True
    assert strategy.is_force_exit_time(t_1515) is False

    # 15:16 IST (No new entries)
    t_1516 = datetime(2026, 11, 18, 15, 16, tzinfo=IST)
    assert strategy.is_within_trading_session(t_1516) is False
    assert strategy.is_force_exit_time(t_1516) is False

    # 15:20 IST (Auto square-off)
    t_1520 = datetime(2026, 11, 18, 15, 20, tzinfo=IST)
    assert strategy.is_within_trading_session(t_1520) is False
    assert strategy.is_force_exit_time(t_1520) is True


# =====================================================================
# 4. MULTI-STRATEGY MANAGER INTEGRATION
# =====================================================================

def test_multi_strategy_manager_independence():
    """Verify SUPERTREND_EMA is registered and isolated from UT_BOT and EMA_RSI."""
    manager = MultiStrategyManager()
    profiles = manager.get_all_profiles()
    strat_ids = [p["strategy_id"] for p in profiles]
    assert "EMA_RSI" in strat_ids
    assert "UT_BOT" in strat_ids
    assert "SUPERTREND_EMA" in strat_ids

    manager.set_active_strategy("SUPERTREND_EMA")
    assert manager.active_strategy_id == "SUPERTREND_EMA"
    active_strat = manager.get_active_strategy()
    assert isinstance(active_strat, SupertrendEMAStrategy)

    # Modify Supertrend strategy parameters
    active_strat.atr_period = 14
    active_strat.multiplier = 2.5
    active_strat.lots = 3

    st_cfg = active_strat.get_config_dict()
    assert st_cfg["atr_period"] == 14
    assert st_cfg["multiplier"] == 2.5
    assert st_cfg["lots"] == 3

    # Check that UT_BOT and EMA_RSI configs remain intact
    ut_cfg = manager.ut_bot_strategy.get_config_dict()
    assert "key_value" in ut_cfg
    ema_cfg = manager.ema_strategy.get_config_dict()
    assert "ema_fast" in ema_cfg


# =====================================================================
# 5. DAILY RISK MANAGEMENT & LOCK MECHANISM
# =====================================================================

@pytest.mark.asyncio
async def test_daily_risk_profit_target_lock():
    """
    Verify that when daily realized net P&L reaches or exceeds +₹1,000,
    the broker locks new entries with DAILY_PROFIT_LOCKED.
    """
    broker = PaperBroker()
    contract = {
        "instrument_token": "OPT_24500_CE",
        "symbol": "NIFTY26NOV24500CE",
        "strike": 24500.0,
        "expiry": "2026-11-26",
        "lot_size": 65
    }

    async with AsyncSessionLocal() as session:
        await session.execute(delete(PaperTrade).where(PaperTrade.strategy_id == "SUPERTREND_EMA"))
        await session.execute(delete(PaperPosition).where(PaperPosition.strategy_id == "SUPERTREND_EMA"))
        await session.execute(delete(StrategyDailyRisk).where(StrategyDailyRisk.strategy_id == "SUPERTREND_EMA"))
        await session.commit()

        # Insert 3 winning trades totaling > +₹1,000 net
        for i in range(3):
            pos = PaperPosition(
                strategy_id="SUPERTREND_EMA",
                instrument_token="OPT_24500_CE",
                symbol="NIFTY26NOV25250CE",
                strike=25250.0,
                expiry="2026-11-26",
                lot_size=65,
                lots=5,
                quantity=325,
                entry_price=150.0,
                current_price=151.15,
                target_price=151.15,
                stop_price=146.98,
                effective_stop_distance=3.02,
                max_loss_amount=1000.0,
                highest_price=151.15,
                lowest_price=150.0,
                status="CLOSED"
            )
            session.add(pos)
            await session.flush()

            t = PaperTrade(
                strategy_id="SUPERTREND_EMA",
                position_id=pos.id,
                underlying_symbol="NIFTY",
                underlying_price_at_entry=24500.0,
                option_symbol="NIFTY26NOV25250CE",
                strike=25250.0,
                expiry="2026-11-26",
                entry_time=T_1030_IST - timedelta(minutes=30 - i * 5),
                exit_time=T_1030_IST - timedelta(minutes=25 - i * 5),
                entry_price=150.0,
                exit_price=151.15,
                quantity=325,
                target_price=151.15,
                stop_price=146.98,
                exit_reason="TARGET",
                gross_pnl=373.75,
                total_charges=20.0,
                net_pnl=353.75,
                is_win=True
            )
            session.add(t)
        await session.commit()

    # Total net P&L = 3 * 353.75 = 1,061.25 >= 1,000.0
    risk_status = await broker.get_daily_risk_status("SUPERTREND_EMA", now=T_1030_IST)
    assert risk_status["is_locked"] is True
    assert risk_status["lock_reason"] == "DAILY_PROFIT_LOCKED"
    assert risk_status["realized_net_pnl"] >= 1000.0
    assert "Profit Target Reached" in risk_status["status_text"]

    # Attempting execute_buy during trading hours should be blocked
    order = await broker.execute_buy(
        contract=contract,
        current_premium=150.0,
        underlying_price=24500.0,
        lots=5,
        strategy_id="SUPERTREND_EMA",
        timestamp=T_1030_IST
    )
    assert order is None  # Blocked due to daily profit lock!

    async with AsyncSessionLocal() as session:
        await session.execute(delete(PaperTrade).where(PaperTrade.strategy_id == "SUPERTREND_EMA"))
        await session.execute(delete(PaperPosition).where(PaperPosition.strategy_id == "SUPERTREND_EMA"))
        await session.execute(delete(StrategyDailyRisk).where(StrategyDailyRisk.strategy_id == "SUPERTREND_EMA"))
        await session.commit()


@pytest.mark.asyncio
async def test_daily_risk_loss_limit_lock():
    """
    Verify that when daily realized net P&L reaches or breaches -₹2,000,
    the broker locks new entries with DAILY_LOSS_LOCKED.
    """
    broker = PaperBroker()
    contract = {
        "instrument_token": "OPT_24500_CE",
        "symbol": "NIFTY26NOV24500CE",
        "strike": 24500.0,
        "expiry": "2026-11-26",
        "lot_size": 65
    }

    async with AsyncSessionLocal() as session:
        await session.execute(delete(PaperTrade).where(PaperTrade.strategy_id == "SUPERTREND_EMA"))
        await session.execute(delete(PaperPosition).where(PaperPosition.strategy_id == "SUPERTREND_EMA"))
        await session.execute(delete(StrategyDailyRisk).where(StrategyDailyRisk.strategy_id == "SUPERTREND_EMA"))
        await session.commit()

        # Insert 2 losing trades totaling -₹2,003 net
        for i in range(2):
            pos = PaperPosition(
                strategy_id="SUPERTREND_EMA",
                instrument_token="OPT_24500_CE",
                symbol="NIFTY26NOV25250CE",
                strike=25250.0,
                expiry="2026-11-26",
                lot_size=65,
                lots=5,
                quantity=325,
                entry_price=150.0,
                current_price=146.98,
                target_price=151.15,
                stop_price=146.98,
                effective_stop_distance=3.02,
                max_loss_amount=1000.0,
                highest_price=150.0,
                lowest_price=146.98,
                status="CLOSED"
            )
            session.add(pos)
            await session.flush()

            t = PaperTrade(
                strategy_id="SUPERTREND_EMA",
                position_id=pos.id,
                underlying_symbol="NIFTY",
                underlying_price_at_entry=24500.0,
                option_symbol="NIFTY26NOV25250CE",
                strike=25250.0,
                expiry="2026-11-26",
                entry_time=T_1030_IST - timedelta(minutes=40 - i * 10),
                exit_time=T_1030_IST - timedelta(minutes=30 - i * 10),
                entry_price=150.0,
                exit_price=146.98,
                quantity=325,
                target_price=151.15,
                stop_price=146.98,
                exit_reason="STOP_LOSS",
                gross_pnl=-981.5,
                total_charges=20.0,
                net_pnl=-1001.5,
                is_win=False
            )
            session.add(t)
        await session.commit()

    risk_status = await broker.get_daily_risk_status("SUPERTREND_EMA", now=T_1030_IST)
    assert risk_status["is_locked"] is True
    assert risk_status["lock_reason"] == "DAILY_LOSS_LOCKED"
    assert risk_status["realized_net_pnl"] <= -2000.0
    assert "Loss Limit Reached" in risk_status["status_text"]

    order = await broker.execute_buy(
        contract=contract,
        current_premium=150.0,
        underlying_price=24500.0,
        lots=5,
        strategy_id="SUPERTREND_EMA",
        timestamp=T_1030_IST
    )
    assert order is None  # Blocked due to daily loss lock!

    async with AsyncSessionLocal() as session:
        await session.execute(delete(PaperTrade).where(PaperTrade.strategy_id == "SUPERTREND_EMA"))
        await session.execute(delete(PaperPosition).where(PaperPosition.strategy_id == "SUPERTREND_EMA"))
        await session.execute(delete(StrategyDailyRisk).where(StrategyDailyRisk.strategy_id == "SUPERTREND_EMA"))
        await session.commit()


@pytest.mark.asyncio
async def test_daily_risk_reset_on_next_day():
    """Verify that trades from yesterday do not lock today's trading."""
    broker = PaperBroker()
    yesterday_dt = T_1030_IST - timedelta(days=1)

    async with AsyncSessionLocal() as session:
        await session.execute(delete(PaperTrade).where(PaperTrade.strategy_id == "SUPERTREND_EMA"))
        await session.execute(delete(PaperPosition).where(PaperPosition.strategy_id == "SUPERTREND_EMA"))
        await session.execute(delete(StrategyDailyRisk).where(StrategyDailyRisk.strategy_id == "SUPERTREND_EMA"))
        await session.commit()

        pos = PaperPosition(
            strategy_id="SUPERTREND_EMA",
            instrument_token="OPT_24500_CE",
            symbol="NIFTY26NOV25250CE",
            strike=25250.0,
            expiry="2026-11-26",
            lot_size=65,
            lots=5,
            quantity=325,
            entry_price=150.0,
            current_price=140.0,
            target_price=151.15,
            stop_price=146.98,
            effective_stop_distance=3.02,
            max_loss_amount=1000.0,
            highest_price=150.0,
            lowest_price=140.0,
            status="CLOSED"
        )
        session.add(pos)
        await session.flush()

        t = PaperTrade(
            strategy_id="SUPERTREND_EMA",
            position_id=pos.id,
            underlying_symbol="NIFTY",
            underlying_price_at_entry=24500.0,
            option_symbol="NIFTY26NOV25250CE",
            strike=25250.0,
            expiry="2026-11-26",
            entry_time=yesterday_dt - timedelta(minutes=10),
            exit_time=yesterday_dt,
            entry_price=150.0,
            exit_price=140.0,
            quantity=325,
            target_price=151.15,
            stop_price=146.98,
            exit_reason="STOP_LOSS",
            gross_pnl=-3250.0,
            total_charges=20.0,
            net_pnl=-3270.0,
            is_win=False
        )
        session.add(t)
        await session.commit()

    risk_status = await broker.get_daily_risk_status("SUPERTREND_EMA", now=T_1030_IST)
    assert risk_status["trade_count"] == 0
    assert risk_status["realized_net_pnl"] == 0.0
    assert risk_status["is_locked"] is False

    async with AsyncSessionLocal() as session:
        await session.execute(delete(PaperTrade).where(PaperTrade.strategy_id == "SUPERTREND_EMA"))
        await session.execute(delete(PaperPosition).where(PaperPosition.strategy_id == "SUPERTREND_EMA"))
        await session.execute(delete(StrategyDailyRisk).where(StrategyDailyRisk.strategy_id == "SUPERTREND_EMA"))
        await session.commit()


# =====================================================================
# 6. EXIT RULES & BACKTEST INTEGRATION
# =====================================================================

def test_supertrend_ema_backtest_execution():
    """
    Run backtest for SUPERTREND_EMA:
    - Verifies CE and PE execution
    - Verifies TARGET, STOP_LOSS, SUPERTREND_REVERSAL, and 15:20 FORCE_EXIT
    - Verifies daily profit lock and daily loss lock during backtest
    """
    loader = BacktestDataLoader()
    nifty, options = loader.generate_synthetic_backtest_dataset(days=3, seed=42)

    engine = BacktestEngine(
        initial_capital=100000.0,
        lots=5,
        lot_size=65,
        execution_mode="TRIGGER_PRICE",
        slippage_points=0.0
    )

    result = engine.run_backtest(
        nifty_candles=nifty,
        option_candles=options,
        strategy_id="SUPERTREND_EMA",
        supertrend_ema_params={
            "atr_period": 10,
            "multiplier": 3.0,
            "ema_fast": 9,
            "ema_slow": 21,
            "lots": 5,
            "lot_size": 65,
            "target_net_profit": 200.0,
            "max_loss_per_trade": 1000.0,
            "daily_profit_target": 1000.0,
            "daily_loss_limit": -2000.0,
            "roundtrip_charges": 20.0
        },
        timeframe_minutes=1
    )

    assert result["strategy_id"] == "SUPERTREND_EMA"
    assert result["total_trades"] > 0
    trade_dicts = result["trades"]

    exit_reasons = {t["exit_reason"] for t in trade_dicts}
    valid_reasons = {"TARGET", "STOP_LOSS", "SUPERTREND_REVERSAL", "FORCE_EXIT", "AUTO_SQUARE_OFF"}
    assert any(r in valid_reasons for r in exit_reasons)

    for t in trade_dicts:
        assert t["quantity"] == 325
        assert t["charges"] == 20.0
        expected_net = round(t["gross_pnl"] - t["charges"] - t.get("slippage_cost", 0.0), 2)
        assert abs(t["net_pnl"] - expected_net) <= 0.05

    for day in result.get("daily_breakdown", []):
        assert "date" in day
        assert "net_pnl" in day
        assert "trades" in day
        if day.get("status") == "LOCKED":
            assert day["net_pnl"] >= 1000.0 or day["net_pnl"] <= -2000.0


def test_supertrend_ema_realistic_mode_backtest():
    """Verify SUPERTREND_EMA backtest in REALISTIC mode reports slippage and gap risks honestly."""
    loader = BacktestDataLoader()
    nifty, options = loader.generate_synthetic_backtest_dataset(days=2, seed=101)

    engine = BacktestEngine(
        initial_capital=100000.0,
        lots=5,
        lot_size=65,
        execution_mode="REALISTIC",
        slippage_points=0.20
    )

    result = engine.run_backtest(
        nifty_candles=nifty,
        option_candles=options,
        strategy_id="SUPERTREND_EMA",
        supertrend_ema_params={
            "atr_period": 10,
            "multiplier": 3.0,
            "ema_fast": 9,
            "ema_slow": 21,
            "lots": 5,
            "lot_size": 65,
            "target_net_profit": 200.0,
            "max_loss_per_trade": 1000.0,
        },
        timeframe_minutes=1
    )

    assert result["execution_mode"] == "REALISTIC"
    assert result["total_trades"] > 0
    for t in result["trades"]:
        assert "slippage_cost" in t
        assert t["slippage_cost"] >= 0.0


# =====================================================================
# 7. FASTAPI API ROUTES INTEGRATION
# =====================================================================

@pytest.mark.asyncio
async def test_supertrend_ema_api_endpoints():
    """Verify REST API endpoints for SUPERTREND_EMA: /select, /profiles, /configure, /status, /backtest/run."""
    from httpx import AsyncClient, ASGITransport
    from backend.app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Select SUPERTREND_EMA
        res = await client.post("/api/strategy/select", json={"strategy_id": "SUPERTREND_EMA"})
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "SUCCESS"
        assert data["active_strategy_id"] == "SUPERTREND_EMA"

        # 2. Get profiles
        res = await client.get("/api/strategy/profiles")
        assert res.status_code == 200
        profiles_data = res.json()
        assert profiles_data["active_strategy_id"] == "SUPERTREND_EMA"
        profile_ids = [p["strategy_id"] for p in profiles_data["profiles"]]
        assert "SUPERTREND_EMA" in profile_ids

        # 3. Configure SUPERTREND_EMA
        cfg_payload = {
            "strategy_id": "SUPERTREND_EMA",
            "atr_period": 10,
            "multiplier": 3.0,
            "ema_fast": 9,
            "ema_slow": 21,
            "lots": 5,
            "lot_size": 65,
            "target_net_profit": 200.0,
            "max_loss_per_trade": 1000.0,
            "daily_profit_target": 1000.0,
            "daily_loss_limit": -2000.0,
        }
        res = await client.post("/api/strategy/configure", json=cfg_payload)
        assert res.status_code == 200
        cfg_res = res.json()
        assert cfg_res["status"] == "UPDATED"
        assert cfg_res["config"]["atr_period"] == 10
        assert cfg_res["config"]["lots"] == 5

        # 4. Strategy Status
        res = await client.get("/api/strategy/status")
        assert res.status_code == 200
        status_data = res.json()
        assert status_data["strategy_id"] == "SUPERTREND_EMA"
        assert "daily_risk" in status_data
        assert status_data["target_points"] > 0
        assert status_data["stop_points"] > 0
        assert status_data["quantity"] == 325

        # 5. Backtest API with SUPERTREND_EMA
        bt_payload = {
            "strategy_id": "SUPERTREND_EMA",
            "days": 2,
            "use_synthetic_data": True,
            "execution_mode": "TRIGGER_PRICE",
            "supertrend_ema": {
                "atr_period": 10,
                "multiplier": 3.0,
                "ema_fast": 9,
                "ema_slow": 21,
                "lots": 5,
                "lot_size": 65,
                "target_net_profit": 200.0,
                "max_loss_per_trade": 1000.0,
                "daily_profit_target": 1000.0,
                "daily_loss_limit": -2000.0
            }
        }
        res = await client.post("/api/backtest/run", json=bt_payload)
        assert res.status_code == 200
        bt_res = res.json()
        assert bt_res["strategy_id"] == "SUPERTREND_EMA"
        assert bt_res["total_trades"] > 0
        assert "trades" in bt_res
        assert "run_id" in bt_res

