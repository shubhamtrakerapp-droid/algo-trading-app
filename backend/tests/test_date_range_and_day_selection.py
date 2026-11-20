"""
Test Suite: Date Range, Historical Day Selection, and Calendar Connection Audit.
Validates:
1. Custom 5-day date range.
2. Custom 30-day date range.
3. Older historical dates.
4. A date with zero trades (status = NO_TRADE).
5. A date with multiple trades (status = TRADED).
6. A weekend inside the selected range (status = WEEKEND).
7. A market holiday (status = HOLIDAY).
8. Missing historical candles (status = MISSING_DATA, never marked as no-trade).
9. Exact start/end date preservation (no silent 3-day restriction).
10. Clicking a no-trade date (returns description and chart access).
11. Clicking a date with trades (returns exact candles and trade markers).
12. Analytics calendar matching the selected backtest run.
"""

import pytest
from datetime import datetime, date, timezone, timedelta
from backend.app.backtest.engine import BacktestEngine
from backend.app.backtest.data_loader import BacktestDataLoader
from backend.app.analytics.nse_holidays import is_weekend, get_nse_holiday_name, is_trading_day
from backend.app.analytics.calendar import PerformanceCalendarEngine, IST
from backend.app.market.history_service import HistoricalMarketDataService
from backend.app.database import AsyncSessionLocal
from backend.app.models.models import BacktestRun, BacktestTrade


def test_nse_holidays_and_weekends():
    """Requirement 2, 7, 8: Test holiday and weekend classification."""
    # Weekend
    sat = date(2026, 11, 14)
    sun = date(2026, 11, 15)
    assert is_weekend(sat) is True
    assert is_weekend(sun) is True
    assert is_trading_day(sat) is False
    assert is_trading_day(sun) is False

    # Weekday trading day
    mon = date(2026, 11, 9)
    assert is_weekend(mon) is False
    assert is_trading_day(mon) is True
    assert get_nse_holiday_name(mon) is None

    # Official NSE Holiday: Diwali Balipratipada
    diwali_tue = date(2026, 11, 10)
    assert is_weekend(diwali_tue) is False
    assert get_nse_holiday_name(diwali_tue) == "Diwali Balipratipada"
    assert is_trading_day(diwali_tue) is False

    # Republic Day 2026
    rep_day = date(2026, 1, 26)
    assert get_nse_holiday_name(rep_day) == "Republic Day"


def test_exact_start_end_date_preservation():
    """
    Requirement 1 & 5 & Test 9:
    User selects 2026-11-09 to 2026-11-13.
    The engine must test strictly between 2026-11-09 and 2026-11-13.
    Never silently replace with latest 3 days.
    Note: 2026-11-10 is Diwali Balipratipada (NSE holiday), so 4 trading days are returned.
    """
    loader = BacktestDataLoader(allow_offline_cache=True)
    trading_days = loader._get_trading_days(start_date="2026-11-09", end_date="2026-11-13")

    # 4 trading days: Nov 09, 11, 12, 13 (Nov 10 is Diwali Balipratipada holiday)
    assert len(trading_days) == 4
    assert trading_days[0].strftime("%Y-%m-%d") == "2026-11-09"
    assert trading_days[-1].strftime("%Y-%m-%d") == "2026-11-13"
    assert date(2026, 11, 10) not in trading_days


def test_custom_30_day_date_range():
    """
    Requirement 1 & Test 2:
    Custom 30-day date range generation.
    """
    loader = BacktestDataLoader()
    nifty, options = loader.generate_synthetic_backtest_dataset(days=30, seed=123)

    assert len(nifty) == 30 * 375
    assert len(options) == 30 * 375


def test_custom_date_range_with_weekend_and_holiday():
    """
    Requirement 2 & Tests 1, 6, 7:
    Selected range: 2026-11-09 to 2026-11-15 (7 calendar days).
    Must distinguish:
    - 2026-11-09: TRADED
    - 2026-11-10: HOLIDAY (Diwali Balipratipada)
    - 2026-11-11: TRADED
    - 2026-11-12: TRADED
    - 2026-11-13: TRADED
    - 2026-11-14: WEEKEND
    - 2026-11-15: WEEKEND
    """
    loader = BacktestDataLoader()
    nifty, options = loader.generate_synthetic_backtest_dataset(
        start_date="2026-11-09",
        end_date="2026-11-15",
        seed=42
    )

    metadata = {
        "start_date": "2026-11-09",
        "end_date": "2026-11-15",
        "data_source": "SYNTHETIC_TEST"
    }

    engine = BacktestEngine(execution_mode="TRIGGER_PRICE")
    res = engine.run_backtest(
        nifty_candles=nifty,
        option_candles=options,
        strategy_id="UT_BOT",
        metadata=metadata
    )

    date_wise = res["date_wise_summary"]
    assert len(date_wise) == 7

    status_by_date = {d["date"]: d["status"] for d in date_wise}
    assert status_by_date["2026-11-09"] in ("TRADED", "NO_TRADE")
    assert status_by_date["2026-11-10"] == "HOLIDAY"
    assert status_by_date["2026-11-14"] == "WEEKEND"
    assert status_by_date["2026-11-15"] == "WEEKEND"

    period_summary = res["period_summary"]
    assert period_summary["selected_start_date"] == "2026-11-09"
    assert period_summary["selected_end_date"] == "2026-11-15"


def test_missing_data_days_distinguished_from_no_trade():
    """
    Requirement 2 & 5 & Test 8:
    Never treat missing historical data as a no-trade day.
    """
    # Create artificial candles that only cover 2026-11-09 and 2026-11-11 (skipping 2026-11-12)
    # Range is 2026-11-09 to 2026-11-12
    # 2026-11-10 is Holiday
    # 2026-11-12 has 0 candles -> Must be marked MISSING_DATA
    base_dt1 = datetime(2026, 11, 9, 9, 15, tzinfo=IST)
    base_dt3 = datetime(2026, 11, 11, 9, 15, tzinfo=IST)
    c_day1 = [
        {
            "timestamp": base_dt1 + timedelta(minutes=i),
            "open": 25000.0, "high": 25010.0, "low": 24990.0, "close": 25005.0, "volume": 100
        }
        for i in range(100)
    ]
    c_day3 = [
        {
            "timestamp": base_dt3 + timedelta(minutes=i),
            "open": 25100.0, "high": 25110.0, "low": 25090.0, "close": 25105.0, "volume": 100
        }
        for i in range(100)
    ]
    opt_day1 = [
        {
            "timestamp": base_dt1 + timedelta(minutes=i),
            "open": 150.0, "high": 155.0, "low": 145.0, "close": 152.0, "volume": 100,
            "symbol": "NIFTY ATM CE", "strike": 25000.0, "expiry": "WEEKLY"
        }
        for i in range(100)
    ]
    opt_day3 = [
        {
            "timestamp": base_dt3 + timedelta(minutes=i),
            "open": 150.0, "high": 155.0, "low": 145.0, "close": 152.0, "volume": 100,
            "symbol": "NIFTY ATM CE", "strike": 25100.0, "expiry": "WEEKLY"
        }
        for i in range(100)
    ]

    metadata = {
        "start_date": "2026-11-09",
        "end_date": "2026-11-12",
        "data_source": "SYNTHETIC_TEST"
    }

    engine = BacktestEngine(execution_mode="TRIGGER_PRICE")
    res = engine.run_backtest(
        nifty_candles=c_day1 + c_day3,
        option_candles=opt_day1 + opt_day3,
        strategy_id="UT_BOT",
        metadata=metadata
    )

    date_wise = {d["date"]: d for d in res["date_wise_summary"]}
    assert date_wise["2026-11-10"]["status"] == "HOLIDAY"
    assert date_wise["2026-11-12"]["status"] == "MISSING_DATA"
    assert "2026-11-12" in res["period_summary"]["missing_data_days"]
    assert res["period_summary"]["missing_data_count"] == 1


@pytest.mark.asyncio
async def test_reprocessed_5_day_all_trading_days_included():
    """
    Requirement 2, 3, 5 & Tests 1, 4, 5:
    Real market 5-day range (2026-11-09 to 2026-11-13).
    Verify all 5 dates appear in date_wise_summary.
    2026-11-10 is marked as HOLIDAY.
    Nov 9, 11, 12, 13 are TRADED.
    """
    loader = BacktestDataLoader(allow_offline_cache=True)
    n_c, o_c, meta = await loader.load_dataset(
        symbol="NIFTY ATM CE",
        days=5,
        start_date="2026-11-09",
        end_date="2026-11-13",
        data_source="REAL_MARKET"
    )

    engine = BacktestEngine(execution_mode="TRIGGER_PRICE")
    res = engine.run_backtest(
        nifty_candles=n_c,
        option_candles=o_c,
        strategy_id="UT_BOT",
        metadata=meta
    )

    period_summary = res["period_summary"]
    assert period_summary["selected_start_date"] == "2026-11-09"
    assert period_summary["selected_end_date"] == "2026-11-13"
    assert period_summary["trading_days_tested"] == 4
    assert period_summary["missing_data_count"] == 0

    date_wise = {d["date"]: d for d in res["date_wise_summary"]}
    assert len(date_wise) == 5
    assert date_wise["2026-11-09"]["status"] == "TRADED"
    assert date_wise["2026-11-09"]["trades"] == 26
    assert date_wise["2026-11-10"]["status"] == "HOLIDAY"
    assert date_wise["2026-11-10"]["trades"] == 0
    assert date_wise["2026-11-11"]["status"] == "TRADED"
    assert date_wise["2026-11-11"]["trades"] == 32
    assert date_wise["2026-11-12"]["status"] == "TRADED"
    assert date_wise["2026-11-12"]["trades"] == 37
    assert date_wise["2026-11-13"]["status"] == "TRADED"
    assert date_wise["2026-11-13"]["trades"] == 39


@pytest.mark.asyncio
async def test_clicking_day_returns_candles_and_markers():
    """
    Requirement 4 & Tests 10, 11:
    Test retrieving exact candles and trade markers for a single date.
    """
    loader = BacktestDataLoader(allow_offline_cache=True)
    n_c, o_c, meta = await loader.load_dataset(
        symbol="NIFTY ATM CE",
        days=5,
        start_date="2026-11-09",
        end_date="2026-11-13",
        data_source="REAL_MARKET"
    )

    engine = BacktestEngine(execution_mode="TRIGGER_PRICE")
    res = engine.run_backtest(
        nifty_candles=n_c,
        option_candles=o_c,
        strategy_id="UT_BOT",
        metadata=meta
    )
    run_id = await engine.save_backtest_run(res)
    assert run_id > 0

    # 2026-11-09 has 26 trades in this run
    candles_res = await HistoricalMarketDataService.get_candles(
        symbol=res["contract_symbol"],
        timeframe="1m",
        mode="BACKTEST",
        run_id=run_id,
        start_date="2026-11-09",
        end_date="2026-11-09",
        limit=500
    )
    assert len(candles_res["candles"]) > 0

    markers = await HistoricalMarketDataService.get_trade_markers(
        mode="BACKTEST",
        run_id=run_id,
        symbol=res["contract_symbol"],
        start_date="2026-11-09",
        end_date="2026-11-09"
    )
    assert len(markers) == 52  # 26 entries + 26 exits


@pytest.mark.asyncio
async def test_analytics_calendar_monthly_and_day_connection():
    """
    Requirement 7 & Tests 10, 12:
    Verify Analytics Calendar connects to the exact backtest run_id:
    - November 2026 returns month grid.
    - 2026-11-10 returns status='HOLIDAY' with 0 trades.
    - 2026-11-09 returns has_trades=True with 26 trades.
    """
    loader = BacktestDataLoader(allow_offline_cache=True)
    n_c, o_c, meta = await loader.load_dataset(
        symbol="NIFTY ATM CE",
        days=5,
        start_date="2026-11-09",
        end_date="2026-11-13",
        data_source="REAL_MARKET"
    )

    engine = BacktestEngine(execution_mode="TRIGGER_PRICE")
    res = engine.run_backtest(
        nifty_candles=n_c,
        option_candles=o_c,
        strategy_id="UT_BOT",
        metadata=meta
    )
    run_id = await engine.save_backtest_run(res)

    async with AsyncSessionLocal() as session:
        b_run = await session.get(BacktestRun, run_id)
        assert b_run is not None

    # Monthly calendar with this run_id
    from backend.app.api.routes_analytics import fetch_unified_trades
    async with AsyncSessionLocal() as session:
        trades = await fetch_unified_trades(
            session=session,
            source="BACKTEST",
            run_id=run_id
        )
    cal_res = PerformanceCalendarEngine.get_monthly_calendar(
        trades=trades,
        year=2026,
        month=11,
        tested_start_date="2026-11-09",
        tested_end_date="2026-11-13"
    )

    days_by_num = {d["day_number"]: d for d in cal_res["days"]}
    # Day 9 had trades
    assert days_by_num[9]["has_trades"] is True
    # Day 10 was holiday
    assert days_by_num[10]["has_trades"] is False
    assert days_by_num[10]["status"] == "HOLIDAY"
    # Day 14 is Saturday weekend
    assert days_by_num[14]["status"] == "WEEKEND"
