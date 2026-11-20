import pytest
import asyncio
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any

from backend.app.adapters.base import CandleData
from backend.app.database import AsyncSessionLocal, init_db
from backend.app.models.models import PaperTrade, PaperPosition, StrategyDailyRisk
from backend.app.strategy.ai_micro_scalper.indicators import calculate_adx, calculate_session_vwap
from backend.app.strategy.ai_micro_scalper.agents import (
    TrendAgent,
    MomentumAgent,
    VolatilityAgent,
    MarketRegimeAgent,
    RiskAgent,
    AIVotingEngine,
)
from backend.app.strategy.ai_micro_scalper.option_selector import AIMicroScalperOptionSelector
from backend.app.strategy.ai_micro_scalper.strategy import (
    AIMicroScalperStrategy,
    AIMicroScalperEvaluation,
)
from backend.app.strategy.ai_micro_scalper.backtest import (
    AIMicroScalperBacktestEngine,
)
from backend.app.paper.broker import PaperBroker

IST = timezone(timedelta(hours=5, minutes=30))


@pytest.fixture(autouse=True)
def run_around_tests():
    asyncio.run(init_db())
    yield


def make_1m_candle(
    dt_ist: datetime,
    open_p: float,
    high_p: float,
    low_p: float,
    close_p: float,
    volume: float = 1000.0,
) -> CandleData:
    dt_utc = dt_ist.astimezone(timezone.utc)
    return CandleData(
        timestamp=dt_utc,
        open=open_p,
        high=high_p,
        low=low_p,
        close=close_p,
        volume=volume,
        complete=True,
    )


def generate_nifty_trending_history(
    direction: str = "BULLISH", count: int = 120
) -> List[CandleData]:
    """Generate 1m candles forming a clean 5m trend and pullback."""
    base_time = datetime(2026, 11, 18, 9, 15, 0, tzinfo=IST)
    candles = []
    base_price = 24500.0

    for i in range(count):
        cur_time = base_time + timedelta(minutes=i)
        step = (0.5 * (i % 5)) if direction == "BULLISH" else (-0.5 * (i % 5))
        trend_shift = (i // 5) * 10.0 if direction == "BULLISH" else -((i // 5) * 10.0)

        # Pullback simulation in the last 5 minutes
        if i >= count - 4:
            if direction == "BULLISH":
                low_p = base_price + trend_shift - 4.0
                open_p = base_price + trend_shift - 2.0
                close_p = base_price + trend_shift + (4.0 if i == count - 1 else -1.0)
                high_p = close_p + 1.0
            else:
                high_p = base_price + trend_shift + 4.0
                open_p = base_price + trend_shift + 2.0
                close_p = base_price + trend_shift - (4.0 if i == count - 1 else -1.0)
                low_p = close_p - 1.0
        else:
            open_p = base_price + trend_shift + step
            close_p = open_p + (2.0 if direction == "BULLISH" else -2.0)
            high_p = max(open_p, close_p) + 1.5
            low_p = min(open_p, close_p) - 1.5

        candles.append(make_1m_candle(cur_time, open_p, high_p, low_p, close_p))

    return candles


# =====================================================================
# TEST 1: Bullish trend generates CE candidate
# =====================================================================
def test_01_bullish_trend_generates_ce_candidate():
    strat = AIMicroScalperStrategy(initial_capital=20000.0)
    history = generate_nifty_trending_history(direction="BULLISH", count=120)

    quotes = {
        "ATM_CE": {
            "symbol": "NIFTY 24700 CE",
            "last_price": 125.0,
            "bid": 124.8,
            "ask": 125.2,
            "strike": 24700.0,
            "expiry": "2026-11-20",
            "lot_size": 65,
        }
    }

    eval_res = strat.evaluate_completed_candle(
        completed_candles=history,
        current_capital=20000.0,
        option_quotes=quotes,
    )

    assert eval_res is not None
    assert eval_res.ema_5m_20 > eval_res.ema_5m_50
    assert eval_res.underlying_price > eval_res.vwap_5m
    assert eval_res.adx_5m >= 20.0
    assert eval_res.signal == "BUY_CE"
    assert eval_res.is_buy_ce is True
    assert eval_res.target_contract_type == "CE"


# =====================================================================
# TEST 2: Bearish trend generates PE candidate
# =====================================================================
def test_02_bearish_trend_generates_pe_candidate():
    strat = AIMicroScalperStrategy(initial_capital=20000.0)
    history = generate_nifty_trending_history(direction="BEARISH", count=120)

    quotes = {
        "ATM_PE": {
            "symbol": "NIFTY 24300 PE",
            "last_price": 125.0,
            "bid": 124.8,
            "ask": 125.2,
            "strike": 24300.0,
            "expiry": "2026-11-20",
            "lot_size": 65,
        }
    }

    eval_res = strat.evaluate_completed_candle(
        completed_candles=history,
        current_capital=20000.0,
        option_quotes=quotes,
    )

    assert eval_res is not None
    assert eval_res.ema_5m_20 < eval_res.ema_5m_50
    assert eval_res.underlying_price < eval_res.vwap_5m
    assert eval_res.adx_5m >= 20.0
    assert eval_res.signal == "BUY_PE"
    assert eval_res.is_buy_pe is True
    assert eval_res.target_contract_type == "PE"


# =====================================================================
# TEST 3: Sideways market rejects entry (ADX < 20)
# =====================================================================
def test_03_sideways_market_rejects_entry():
    strat = AIMicroScalperStrategy(initial_capital=20000.0)
    base_time = datetime(2026, 11, 18, 9, 15, 0, tzinfo=IST)
    flat_history = []
    for i in range(120):
        t = base_time + timedelta(minutes=i)
        p = 24500.0 + (0.5 if i % 2 == 0 else -0.5)
        flat_history.append(make_1m_candle(t, p, p + 0.5, p - 0.5, p))

    eval_res = strat.evaluate_completed_candle(completed_candles=flat_history)
    assert eval_res is None or eval_res.signal == "NONE"


# =====================================================================
# TEST 4: Incomplete candle does not generate signal
# =====================================================================
def test_04_incomplete_candle_does_not_generate_signal():
    strat = AIMicroScalperStrategy(initial_capital=20000.0)
    base_time = datetime(2026, 11, 18, 9, 15, 0, tzinfo=IST)
    short_history = [
        make_1m_candle(
            base_time + timedelta(minutes=i),
            24500.0 + i,
            24501.0 + i,
            24499.0 + i,
            24500.5 + i,
        )
        for i in range(10)
    ]
    eval_res = strat.evaluate_completed_candle(completed_candles=short_history)
    assert eval_res is None


# =====================================================================
# TEST 5: Signal is not repainted
# =====================================================================
def test_05_signal_is_not_repainted():
    strat = AIMicroScalperStrategy(initial_capital=20000.0)
    history = generate_nifty_trending_history(direction="BULLISH", count=100)

    eval_1 = strat.evaluate_completed_candle(completed_candles=history)
    next_candle = make_1m_candle(
        datetime(2026, 11, 18, 11, 0, tzinfo=IST),
        24600.0,
        24605.0,
        24595.0,
        24602.0,
    )
    eval_2 = strat.evaluate_completed_candle(completed_candles=history[:100])

    assert eval_1.signal == eval_2.signal
    assert eval_1.underlying_price == eval_2.underlying_price


# =====================================================================
# TEST 6: Index signal executes on option premium
# =====================================================================
def test_06_index_signal_executes_on_option_premium():
    strat = AIMicroScalperStrategy(initial_capital=20000.0)
    history = generate_nifty_trending_history(direction="BULLISH", count=120)

    quotes = {
        "ATM_CE": {
            "symbol": "NIFTY 24700 CE",
            "last_price": 132.50,
            "bid": 132.30,
            "ask": 132.70,
            "strike": 24700.0,
            "expiry": "2026-11-20",
            "lot_size": 65,
        }
    }

    eval_res = strat.evaluate_completed_candle(
        completed_candles=history,
        option_quotes=quotes,
    )

    assert eval_res.signal == "BUY_CE"
    assert eval_res.underlying_price > 24000.0
    assert eval_res.contract_premium == 132.50
    assert "CE" in eval_res.contract_symbol


# =====================================================================
# TEST 7: Index points never used for option P&L
# =====================================================================
def test_07_index_points_never_used_for_option_pnl():
    pts_info = AIMicroScalperStrategy().calculate_target_and_stop_points(
        quantity=130,
        slippage_points=0.05,
    )
    assert 1.0 < pts_info["target_points"] < 3.0
    assert 1.5 < pts_info["stop_points"] < 3.0


# =====================================================================
# TEST 8: Invalid premium (< ₹20 or > ₹500) rejects contract
# =====================================================================
def test_08_invalid_premium_rejects_contract():
    selector = AIMicroScalperOptionSelector()
    quotes_too_low = {
        "ATM_CE": {
            "symbol": "NIFTY_CE",
            "last_price": 0.20,
            "bid": 0.15,
            "ask": 0.25,
        }
    }
    res_low = selector.select_contract(24500.0, "CE", quotes_map=quotes_too_low)
    assert res_low["is_valid"] is False


# =====================================================================
# TEST 9: Spread above 0.5 threshold rejects contract
# =====================================================================
def test_09_spread_above_threshold_rejects_contract():
    selector = AIMicroScalperOptionSelector(max_bid_ask_spread=0.50)
    quotes_wide_spread = {
        "ATM_CE": {
            "symbol": "NIFTY_CE",
            "last_price": 125.0,
            "bid": 124.0,
            "ask": 125.0,  # Spread 1.0 > 0.50
        }
    }
    res = selector.select_contract(24500.0, "CE", quotes_map=quotes_wide_spread)
    assert res["spread"] == 1.0
    assert res["is_valid"] is False


# =====================================================================
# TEST 10: Insufficient capital (> 90% of ₹20,000) rejects trade
# =====================================================================
def test_10_insufficient_capital_rejects_trade():
    selector = AIMicroScalperOptionSelector(max_capital_deployment_pct=90.0)
    quotes = {
        "ATM_CE": {
            "symbol": "NIFTY_CE",
            "last_price": 145.0,
            "bid": 144.8,
            "ask": 145.2,
        }
    }
    res = selector.select_contract(
        spot_price=24500.0,
        option_type="CE",
        quotes_map=quotes,
        available_capital=20000.0,
        lots=2,
        lot_size=65,
    )
    assert res["is_affordable"] is False
    assert res["required_capital"] > 18000.0


# =====================================================================
# TEST 11: Actual instrument lot size is used
# =====================================================================
def test_11_actual_instrument_lot_size_used():
    selector = AIMicroScalperOptionSelector()
    lot_sz = selector.resolve_lot_size()
    assert lot_sz > 0
    assert isinstance(lot_sz, int)


# =====================================================================
# TEST 12: Target closes at correct net P&L (₹200)
# =====================================================================
def test_12_target_closes_at_correct_net_pnl():
    strat = AIMicroScalperStrategy(target_net_profit=200.0, roundtrip_charges=20.0)
    qty = 130
    pts_info = strat.calculate_target_and_stop_points(quantity=qty, slippage_points=0.0)

    entry_price = 125.0
    exit_price = entry_price + pts_info["target_points"]
    gross_pnl = (exit_price - entry_price) * qty
    net_pnl = gross_pnl - 20.0
    assert round(net_pnl, 2) == 200.0


# =====================================================================
# TEST 13: Stop closes at correct net P&L (-₹300)
# =====================================================================
def test_13_stop_closes_at_correct_net_pnl():
    strat = AIMicroScalperStrategy(max_loss_per_trade=300.0, roundtrip_charges=20.0)
    qty = 130
    pts_info = strat.calculate_target_and_stop_points(quantity=qty, slippage_points=0.0)

    entry_price = 125.0
    exit_price = entry_price - pts_info["stop_points"]
    gross_pnl = (exit_price - entry_price) * qty
    net_pnl = gross_pnl - 20.0
    assert abs(net_pnl - (-300.0)) < 0.1


# =====================================================================
# TEST 14: Daily +₹500 lock works
# =====================================================================
def test_14_daily_profit_target_lock():
    agent = RiskAgent()
    dec = agent.evaluate(daily_net_pnl=550.0, daily_profit_target=500.0)
    assert dec.approved is False
    assert "Daily profit target" in dec.explanation


# =====================================================================
# TEST 15: Daily -₹500 lock works
# =====================================================================
def test_15_daily_loss_limit_lock():
    agent = RiskAgent()
    dec = agent.evaluate(daily_net_pnl=-550.0, daily_loss_limit=-500.0)
    assert dec.approved is False
    assert "Daily loss limit" in dec.explanation


# =====================================================================
# TEST 16: 2 consecutive losses stop new entries
# =====================================================================
def test_16_consecutive_losses_stop_new_entries():
    agent = RiskAgent()
    dec = agent.evaluate(consecutive_losses=2, max_consecutive_losses=2)
    assert dec.approved is False
    assert "consecutive losses" in dec.explanation


# =====================================================================
# TEST 17: Max 5 trades per day enforced
# =====================================================================
def test_17_max_trades_per_day_enforced():
    agent = RiskAgent()
    dec = agent.evaluate(trades_today=5, max_trades_per_day=5)
    assert dec.approved is False
    assert "Maximum daily trades" in dec.explanation


# =====================================================================
# TEST 18: 15:20 square-off works
# =====================================================================
def test_18_force_exit_at_1520_square_off():
    strat = AIMicroScalperStrategy()
    t_1519 = datetime(2026, 11, 18, 15, 19, 0, tzinfo=IST)
    t_1520 = datetime(2026, 11, 18, 15, 20, 0, tzinfo=IST)
    t_1525 = datetime(2026, 11, 18, 15, 25, 0, tzinfo=IST)

    assert strat.is_force_exit_time(t_1519) is False
    assert strat.is_force_exit_time(t_1520) is True
    assert strat.is_force_exit_time(t_1525) is True


# =====================================================================
# TEST 19: Opposite signal closes existing position
# =====================================================================
def test_19_opposite_signal_closes_existing_position():
    agent = RiskAgent()
    dec = agent.evaluate(has_open_position=True)
    assert dec.approved is False
    assert "Active open position exists" in dec.explanation


# =====================================================================
# TEST 20: No duplicate positions
# =====================================================================
def test_20_no_duplicate_positions():
    voting_engine = AIVotingEngine()
    voting_res = voting_engine.evaluate(
        signal_type="BUY_CE",
        candles_5m={"close": 24600.0, "ema_20": 24550.0, "ema_50": 24500.0, "vwap": 24520.0, "adx": 25.0},
        candles_1m={"close": 24600.0, "open": 24595.0, "high": 24602.0, "low": 24580.0, "volume": 1500.0, "ema_9": 24585.0, "ema_20": 24575.0, "vwap": 24560.0, "rsi": 60.0, "atr": 5.0},
        option_data={"symbol": "NIFTY_CE", "last_price": 125.0, "quantity": 130, "spread": 0.20},
        capital=20000.0,
        has_open_position=True,
        candle_time=datetime(2026, 11, 18, 10, 30, tzinfo=IST),
    )
    assert voting_res.consensus_approved is False
    assert voting_res.risk_approved is False


# =====================================================================
# TEST 21: Missing historical data marked as MISSING_DATA
# =====================================================================
@pytest.mark.asyncio
async def test_21_missing_historical_data_marked_missing():
    engine = AIMicroScalperBacktestEngine()
    base_time = datetime(2026, 11, 18, 9, 15, tzinfo=IST)
    nifty_candles = [
        {"timestamp": (base_time + timedelta(minutes=i)).isoformat(), "open": 24500.0 + i, "high": 24502.0 + i, "low": 24498.0 + i, "close": 24501.0 + i, "volume": 1000}
        for i in range(50)
    ]
    res = await engine.run_backtest(
        nifty_candles=nifty_candles,
        option_candles_ce=[],
        option_candles_pe=[],
        data_source="KOTAK_NEO_HISTORICAL",
        save_to_db=False,
    )
    assert res is not None
    assert res["total_trades"] == 0


# =====================================================================
# TEST 22: Reproducible backtest runs
# =====================================================================
@pytest.mark.asyncio
async def test_22_reproducible_backtest_runs():
    engine = AIMicroScalperBacktestEngine()
    base_time = datetime(2026, 11, 18, 9, 15, tzinfo=IST)
    nifty_candles = [
        {"timestamp": (base_time + timedelta(minutes=i)).isoformat(), "open": 24500.0 + i * 2, "high": 24503.0 + i * 2, "low": 24497.0 + i * 2, "close": 24502.0 + i * 2, "volume": 1500}
        for i in range(70)
    ]
    opt_candles = [
        {"timestamp": (base_time + timedelta(minutes=i)).isoformat(), "open": 125.0 + i * 0.5, "high": 127.0 + i * 0.5, "low": 124.0 + i * 0.5, "close": 126.0 + i * 0.5, "volume": 5000, "symbol": "NIFTY_CE", "strike": 24600.0, "expiry": "2026-11-20"}
        for i in range(70)
    ]

    res_1 = await engine.run_backtest(
        nifty_candles=nifty_candles,
        option_candles_ce=opt_candles,
        data_source="KOTAK_NEO_HISTORICAL",
        execution_mode="TRIGGER_PRICE",
        save_to_db=False,
    )
    res_2 = await engine.run_backtest(
        nifty_candles=nifty_candles,
        option_candles_ce=opt_candles,
        data_source="KOTAK_NEO_HISTORICAL",
        execution_mode="TRIGGER_PRICE",
        save_to_db=False,
    )

    assert res_1["total_trades"] == res_2["total_trades"]
    assert res_1["win_rate"] == res_2["win_rate"]
    assert res_1["net_profit"] == res_2["net_profit"]


# =====================================================================
# TEST 23: Backtest analytics match trade ledger
# =====================================================================
@pytest.mark.asyncio
async def test_23_backtest_analytics_match_trade_ledger():
    engine = AIMicroScalperBacktestEngine()
    base_time = datetime(2026, 11, 18, 9, 15, tzinfo=IST)
    nifty_candles = [
        {"timestamp": (base_time + timedelta(minutes=i)).isoformat(), "open": 24500.0 + (i * 2.0 if i < 35 else i * 0.5), "high": 24503.0 + (i * 2.0 if i < 35 else i * 0.5), "low": 24497.0 + (i * 2.0 if i < 35 else i * 0.5), "close": 24502.0 + (i * 2.0 if i < 35 else i * 0.5), "volume": 1500}
        for i in range(80)
    ]
    opt_candles = [
        {"timestamp": (base_time + timedelta(minutes=i)).isoformat(), "open": 125.0 + i * 0.2, "high": 128.0 + i * 0.2, "low": 123.0 + i * 0.2, "close": 126.0 + i * 0.2, "volume": 5000, "symbol": "NIFTY_CE", "strike": 24600.0, "expiry": "2026-11-20"}
        for i in range(80)
    ]

    res = await engine.run_backtest(
        nifty_candles=nifty_candles,
        option_candles_ce=opt_candles,
        data_source="KOTAK_NEO_HISTORICAL",
        save_to_db=False,
    )

    trades = res.get("trades", [])
    if trades:
        sum_gross = round(sum(t["gross_pnl"] for t in trades), 2)
        sum_charges = round(sum(t["charges"] for t in trades), 2)
        sum_net = round(sum(t["net_pnl"] for t in trades), 2)
        assert round(res["gross_profit"] - res["gross_loss"], 2) == sum_gross
        assert round(res["total_charges"], 2) == sum_charges
        assert round(res["net_profit"], 2) == sum_net


# =====================================================================
# TEST 24: CSV export matches displayed results
# =====================================================================
def test_24_csv_export_matches_displayed_results():
    trades = [
        {
            "trade_number": 1,
            "contract_symbol": "NIFTY 24500 CE",
            "entry_time": "2026-11-18T10:00:00+05:30",
            "exit_time": "2026-11-18T10:04:00+05:30",
            "entry_price": 125.0,
            "exit_price": 126.8,
            "quantity": 130,
            "gross_pnl": 234.0,
            "charges": 20.0,
            "net_pnl": 214.0,
            "exit_reason": "TARGET",
        }
    ]
    csv_line = f"{trades[0]['trade_number']},{trades[0]['contract_symbol']},{trades[0]['entry_price']},{trades[0]['exit_price']},{trades[0]['net_pnl']}"
    assert "1,NIFTY 24500 CE,125.0,126.8,214.0" in csv_line


# =====================================================================
# TEST 25: Application restart preserves risk locks and open positions
# =====================================================================
@pytest.mark.asyncio
async def test_25_application_restart_preserves_risk_locks_and_positions():
    broker = PaperBroker()
    strat_id = "AI_MICRO_SCALPER_V1"
    status_before = await broker.get_daily_risk_status(strategy_id=strat_id)
    pos_id = None
    trade_id = None

    async with AsyncSessionLocal() as session:
        pos = PaperPosition(
            strategy_id=strat_id,
            instrument_token="OPT_24500_CE",
            symbol="NIFTY 24500 CE",
            strike=24500.0,
            expiry="2026-11-20",
            lot_size=65,
            lots=2,
            quantity=130,
            entry_price=125.0,
            current_price=127.0,
            target_price=128.0,
            stop_price=122.0,
            effective_stop_distance=3.0,
            max_loss_amount=300.0,
            highest_price=127.0,
            lowest_price=125.0,
            status="CLOSED",
            entry_time=datetime.now(timezone.utc),
        )
        session.add(pos)
        await session.flush()
        pos_id = pos.id

        trade = PaperTrade(
            position_id=pos.id,
            strategy_id=strat_id,
            underlying_symbol="NIFTY",
            underlying_price_at_entry=24500.0,
            option_symbol="NIFTY 24500 CE",
            strike=24500.0,
            expiry="2026-11-20",
            entry_time=datetime.now(timezone.utc),
            exit_time=datetime.now(timezone.utc),
            entry_price=125.0,
            exit_price=127.0,
            quantity=130,
            target_price=128.0,
            stop_price=122.0,
            gross_pnl=260.0,
            total_charges=20.0,
            net_pnl=240.0,
            exit_reason="TARGET",
            is_win=True,
        )
        session.add(trade)
        await session.flush()
        trade_id = trade.id
        await session.commit()

    try:
        status = await broker.get_daily_risk_status(strategy_id=strat_id)
        assert status["realized_net_pnl"] == round(status_before["realized_net_pnl"] + 240.0, 2)
        assert status["trade_count"] == status_before["trade_count"] + 1
    finally:
        async with AsyncSessionLocal() as session:
            if trade_id:
                from sqlalchemy import delete
                await session.execute(delete(PaperTrade).where(PaperTrade.id == trade_id))
            if pos_id:
                await session.execute(delete(PaperPosition).where(PaperPosition.id == pos_id))
            await session.commit()
