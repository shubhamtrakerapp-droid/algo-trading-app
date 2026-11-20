import pytest
from datetime import datetime, timezone
from httpx import AsyncClient, ASGITransport
from backend.app.main import app
from backend.app.database import init_db, AsyncSessionLocal
from backend.app.models.models import PaperPosition, PaperTrade, BacktestRun, BacktestTrade
from backend.app.analytics.calendar import PerformanceCalendarEngine


# =========================================================================
# 1. UNIT TESTS: CALENDAR ENGINE DATES & MONTH STRUCTURES
# =========================================================================

def test_month_lengths_and_leap_year():
    """Verify calendar engine handles 28, 29, 30, and 31 day months with correct leap year handling."""
    engine = PerformanceCalendarEngine()

    # February 2024 (Leap year -> 29 days)
    res_2024_feb = engine.get_monthly_calendar([], 2024, 2)
    assert res_2024_feb["num_days"] == 29
    assert len(res_2024_feb["days"]) == 29
    assert res_2024_feb["days"][-1]["day_number"] == 29
    assert res_2024_feb["days"][-1]["date"] == "2024-02-29"

    # February 2025 (Non-leap year -> 28 days)
    res_2025_feb = engine.get_monthly_calendar([], 2025, 2)
    assert res_2025_feb["num_days"] == 28
    assert len(res_2025_feb["days"]) == 28
    assert res_2025_feb["days"][-1]["day_number"] == 28
    assert res_2025_feb["days"][-1]["date"] == "2025-02-28"

    # April 2026 (30 days)
    res_2026_apr = engine.get_monthly_calendar([], 2026, 4)
    assert res_2026_apr["num_days"] == 30
    assert len(res_2026_apr["days"]) == 30
    assert res_2026_apr["days"][-1]["day_number"] == 30

    # October 2026 (31 days)
    res_2026_oct = engine.get_monthly_calendar([], 2026, 10)
    assert res_2026_oct["num_days"] == 31
    assert len(res_2026_oct["days"]) == 31
    assert res_2026_oct["days"][-1]["day_number"] == 31


def test_first_weekday_alignment():
    """Verify first_weekday accurately places Monday through Sunday in a 0..6 grid."""
    engine = PerformanceCalendarEngine()

    # Nov 2026: 2026-11-01 is a Sunday -> first_weekday must be 6
    res_nov_2026 = engine.get_monthly_calendar([], 2026, 11)
    assert res_nov_2026["first_weekday"] == 6  # 6 = Sunday

    # June 2026: 2026-06-01 is a Monday -> first_weekday must be 0
    res_jun_2026 = engine.get_monthly_calendar([], 2026, 6)
    assert res_jun_2026["first_weekday"] == 0  # 0 = Monday

    # Sept 2026: 2026-09-01 is a Tuesday -> first_weekday must be 1
    res_sep_2026 = engine.get_monthly_calendar([], 2026, 9)
    assert res_sep_2026["first_weekday"] == 1


# =========================================================================
# 2. UNIT TESTS: STREAKS & NO-TRADE GAP CALCULATION
# =========================================================================

def test_streaks_calculation_chronological():
    """Test consecutive winning/losing day streaks, zero P&L neutrality, and non-trading days."""
    engine = PerformanceCalendarEngine()

    trades = [
        {"exit_time": "2026-11-02T10:00:00", "gross_pnl": 120.0, "charges": 20.0, "slippage_cost": 0.0, "net_pnl": 100.0, "holding_time_minutes": 5},
        {"exit_time": "2026-11-03T11:00:00", "gross_pnl": 220.0, "charges": 20.0, "slippage_cost": 0.0, "net_pnl": 200.0, "holding_time_minutes": 8},
        {"exit_time": "2026-11-04T12:00:00", "gross_pnl": 170.0, "charges": 20.0, "slippage_cost": 0.0, "net_pnl": 150.0, "holding_time_minutes": 3},
        {"exit_time": "2026-11-05T13:00:00", "gross_pnl": -30.0, "charges": 20.0, "slippage_cost": 0.0, "net_pnl": -50.0, "holding_time_minutes": 4},
        {"exit_time": "2026-11-06T14:00:00", "gross_pnl": -60.0, "charges": 20.0, "slippage_cost": 0.0, "net_pnl": -80.0, "holding_time_minutes": 6},
        {"exit_time": "2026-11-09T15:00:00", "gross_pnl": 20.0, "charges": 20.0, "slippage_cost": 0.0, "net_pnl": 0.0, "holding_time_minutes": 2},
        {"exit_time": "2026-11-10T10:30:00", "gross_pnl": 320.0, "charges": 20.0, "slippage_cost": 0.0, "net_pnl": 300.0, "holding_time_minutes": 10},
    ]

    daily_dict = engine.aggregate_trades_by_date(trades)
    streaks = engine.calculate_streaks(daily_dict)

    assert streaks["total_winning_days"] == 4
    assert streaks["total_losing_days"] == 2
    assert streaks["total_neutral_days"] == 1
    assert streaks["max_consecutive_wins"] == 3
    assert streaks["max_consecutive_losses"] == 2
    assert streaks["current_streak_type"] == "WIN"
    assert streaks["current_streak_count"] == 1


def test_longest_no_trade_gap():
    """Verify calculation of longest gap between consecutive active trading days."""
    engine = PerformanceCalendarEngine()

    # Traded on Day 2, Day 12 (gap = 9 calendar days), Day 15 (gap = 2 calendar days)
    trades = [
        {"exit_time": "2026-11-02T10:00:00", "gross_pnl": 100.0, "charges": 20.0, "slippage_cost": 0.0, "net_pnl": 80.0, "holding_time_minutes": 5},
        {"exit_time": "2026-11-12T10:00:00", "gross_pnl": 150.0, "charges": 20.0, "slippage_cost": 0.0, "net_pnl": 130.0, "holding_time_minutes": 5},
        {"exit_time": "2026-11-15T10:00:00", "gross_pnl": -50.0, "charges": 20.0, "slippage_cost": 0.0, "net_pnl": -70.0, "holding_time_minutes": 5},
    ]

    daily_dict = engine.aggregate_trades_by_date(trades)
    streaks = engine.calculate_streaks(daily_dict)

    # From 2026-11-02 to 2026-11-12 is 10 days difference -> 9 intervening calendar days
    assert streaks["longest_no_trade_period_days"] == 9


# =========================================================================
# 3. UNIT TESTS: P&L RECONCILIATION & ACCOUNTING INTEGRITY
# =========================================================================

def test_pnl_mathematical_reconciliation():
    """Verify Net P&L = Gross Profit - Gross Loss - Charges - Slippage across daily, monthly and yearly."""
    engine = PerformanceCalendarEngine()

    trades = [
        {"exit_time": "2026-11-05T10:00:00", "gross_pnl": 500.0, "charges": 20.0, "slippage_cost": 6.5, "net_pnl": 473.5, "holding_time_minutes": 10},
        {"exit_time": "2026-11-05T14:00:00", "gross_pnl": -250.0, "charges": 20.0, "slippage_cost": 6.5, "net_pnl": -276.5, "holding_time_minutes": 5},
        {"exit_time": "2026-11-12T11:00:00", "gross_pnl": 300.0, "charges": 20.0, "slippage_cost": 0.0, "net_pnl": 280.0, "holding_time_minutes": 12},
    ]

    # Monthly check
    m_res = engine.get_monthly_calendar(trades, 2026, 11)
    summary = m_res["summary"]
    expected_gross_profit = 800.0
    expected_gross_loss = 250.0
    expected_charges = 60.0
    expected_slippage = 13.0
    expected_net = expected_gross_profit - expected_gross_loss - expected_charges - expected_slippage  # 477.0

    assert round(summary["gross_profit"], 2) == round(expected_gross_profit, 2)
    assert round(summary["gross_loss"], 2) == round(expected_gross_loss, 2)
    assert round(summary["total_charges"], 2) == round(expected_charges, 2)
    assert round(summary["total_slippage"], 2) == round(expected_slippage, 2)
    assert round(summary["net_pnl"], 2) == round(expected_net, 2)

    # Yearly check
    y_res = engine.get_yearly_overview(trades, 2026)
    y_sum = y_res["annual_summary"]
    assert round(y_sum["annual_gross_profit"], 2) == round(expected_gross_profit, 2)
    assert round(y_sum["annual_gross_loss"], 2) == round(expected_gross_loss, 2)
    assert round(y_sum["annual_charges"], 2) == round(expected_charges, 2)
    assert round(y_sum["annual_slippage"], 2) == round(expected_slippage, 2)
    assert round(y_sum["annual_net_pnl"], 2) == round(expected_net, 2)


# =========================================================================
# 4. INTEGRATION TESTS: FASTAPI CALENDAR & CSV ENDPOINTS
# =========================================================================

@pytest.mark.asyncio
async def test_calendar_api_endpoints():
    """Test monthly, yearly, daily detail, and custom range API endpoints."""
    await init_db()

    # Insert a sample paper position & trade
    async with AsyncSessionLocal() as session:
        pos = PaperPosition(
            strategy_id="UT_BOT",
            instrument_token="OPT_24500_CE",
            symbol="NIFTY26NOV24500CE",
            strike=24500.0,
            expiry="2026-11-26",
            lot_size=65,
            lots=5,
            quantity=325,
            entry_price=150.0,
            current_price=154.0,
            target_price=154.0,
            stop_price=148.0,
            effective_stop_distance=2.0,
            max_loss_amount=1000.0,
            configured_sl_points=2.0,
            configured_target_points=4.0,
            effective_sl_points=2.0,
            effective_target_points=4.0,
            sl_trigger_price=148.0,
            target_trigger_price=154.0,
            highest_price=154.0,
            lowest_price=149.0,
            status="CLOSED",
            exit_reason="TARGET",
            gross_pnl=1300.0,
            entry_charge=10.0,
            exit_charge=10.0,
            charges=20.0,
            net_pnl=1280.0,
        )
        session.add(pos)
        await session.flush()

        trade = PaperTrade(
            strategy_id="UT_BOT",
            position_id=pos.id,
            underlying_symbol="NIFTY",
            underlying_price_at_entry=24500.0,
            option_symbol="NIFTY26NOV24500CE",
            strike=24500.0,
            expiry="2026-11-26",
            quantity=325,
            entry_price=150.0,
            exit_price=154.0,
            target_price=154.0,
            stop_price=148.0,
            configured_sl_points=2.0,
            configured_target_points=4.0,
            effective_sl_points=2.0,
            effective_target_points=4.0,
            sl_trigger_price=148.0,
            target_trigger_price=154.0,
            slippage_cost=0.0,
            execution_mode="TRIGGER_PRICE",
            holding_time_minutes=15,
            exit_reason="TARGET",
            gross_pnl=1300.0,
            entry_charge=10.0,
            exit_charge=10.0,
            charges_brokerage=20.0,
            total_charges=20.0,
            net_pnl=1280.0,
            is_win=True,
            entry_time=datetime(2026, 11, 12, 10, 0, 0, tzinfo=timezone.utc),
            exit_time=datetime(2026, 11, 12, 10, 15, 0, tzinfo=timezone.utc),
        )
        session.add(trade)
        await session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Monthly Calendar
        res = await client.get("/api/analytics/calendar/monthly?year=2026&month=11&source=PAPER")
        assert res.status_code == 200
        m_json = res.json()
        assert m_json["status"] == "SUCCESS"
        assert m_json["year"] == 2026
        assert m_json["month"] == 11
        assert len(m_json["days"]) == 30
        assert m_json["summary"]["total_trades"] >= 1
        assert m_json["summary"]["net_pnl"] >= 1280.0

        # Verify Day 12 has trade data
        day_12 = next((d for d in m_json["days"] if d["day_number"] == 12), None)
        assert day_12 is not None
        assert day_12["has_trades"] is True
        assert day_12["status"] == "WIN"
        assert day_12["net_pnl"] >= 1280.0

        # 2. Daily Detail Endpoint
        res_day = await client.get("/api/analytics/calendar/day?date=2026-11-12&source=PAPER")
        assert res_day.status_code == 200
        d_json = res_day.json()
        assert d_json["date"] == "2026-11-12"
        assert d_json["has_trades"] is True
        assert len(d_json["trades"]) >= 1
        t0 = d_json["trades"][0]
        assert t0["option_symbol"] == "NIFTY26NOV24500CE"
        assert t0["exit_reason"] == "TARGET"
        assert t0["charges"] == 20.0

        # 3. Yearly Calendar
        res_year = await client.get("/api/analytics/calendar/yearly?year=2026&source=PAPER")
        assert res_year.status_code == 200
        y_json = res_year.json()
        assert y_json["year"] == 2026
        assert len(y_json["months"]) == 12
        assert y_json["annual_summary"]["total_trades"] >= 1

        # 4. Custom Range
        res_custom = await client.get("/api/analytics/calendar/custom-range?start_date=2026-11-01&end_date=2026-11-30&source=PAPER")
        assert res_custom.status_code == 200
        c_json = res_custom.json()
        assert c_json["total_trades"] >= 1
        assert c_json["net_pnl"] >= 1280.0

        # 5. CSV Exports
        res_csv_day = await client.get("/api/analytics/export/daily-trades-csv?date=2026-11-12&source=PAPER")
        assert res_csv_day.status_code == 200
        assert "text/csv" in res_csv_day.headers["content-type"]
        assert "Trade ID" in res_csv_day.text
        assert "NIFTY26NOV24500CE" in res_csv_day.text

        res_csv_m = await client.get("/api/analytics/export/monthly-csv?year=2026&month=11&source=PAPER")
        assert res_csv_m.status_code == 200
        assert "text/csv" in res_csv_m.headers["content-type"]
        assert "Trading Date" in res_csv_m.text

        res_csv_y = await client.get("/api/analytics/export/yearly-csv?year=2026&source=PAPER")
        assert res_csv_y.status_code == 200
        assert "text/csv" in res_csv_y.headers["content-type"]
        assert "Month Name" in res_csv_y.text

        res_csv_c = await client.get("/api/analytics/export/custom-csv?start_date=2026-11-01&end_date=2026-11-30&source=PAPER")
        assert res_csv_c.status_code == 200
        assert "text/csv" in res_csv_c.headers["content-type"]
