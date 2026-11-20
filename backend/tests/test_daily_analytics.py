import pytest
from datetime import datetime, timezone
from backend.app.analytics.metrics import compute_trading_metrics
from backend.app.schemas.schemas import DailyAnalyticsSchema, AnalyticsSummaryResponse


def test_empty_trading_history():
    """Test analytics computation with an empty trades list."""
    metrics = compute_trading_metrics([], initial_capital=100000.0)
    assert metrics["total_trades"] == 0
    assert metrics["daily_summary"] == []
    assert metrics["net_profit"] == 0.0
    assert metrics["total_brokerage_charges"] == 0.0

    # Validate against Pydantic schema
    validated = AnalyticsSummaryResponse(**metrics)
    assert len(validated.daily_summary) == 0


def test_day_with_charges():
    """Test a single day with standard charges."""
    trades = [
        {
            "id": 1,
            "exit_time": "2026-11-18T10:00:00",
            "gross_pnl": 500.0,
            "charges": 45.50,
            "net_pnl": 454.50,
            "is_win": True,
        },
        {
            "id": 2,
            "exit_time": "2026-11-18T11:00:00",
            "gross_pnl": -300.0,
            "charges": 40.00,
            "net_pnl": -340.00,
            "is_win": False,
        },
    ]

    metrics = compute_trading_metrics(trades, initial_capital=100000.0)
    assert len(metrics["daily_summary"]) == 1

    day = metrics["daily_summary"][0]
    assert day["date"] == "2026-11-18"
    assert day["trades"] == 2
    assert day["wins"] == 1
    assert day["losses"] == 1
    assert day["grossProfit"] == 500.0
    assert day["grossLoss"] == 300.0
    assert day["charges"] == 85.50
    assert isinstance(day["charges"], float)
    assert day["pnl"] == 114.50  # 454.50 - 340.00 = 114.50
    assert day["win_rate"] == 50.0

    # Validate against Pydantic schema
    validated_day = DailyAnalyticsSchema(**day)
    assert validated_day.charges == 85.50
    assert validated_day.pnl == 114.50


def test_day_with_missing_charges():
    """Test a day where charges property is completely missing in trade dict."""
    trades = [
        {
            "id": 1,
            "exit_time": "2026-11-18T10:00:00",
            "gross_pnl": 260.0,
            # charges key missing
            "net_pnl": 260.0,
            "is_win": True,
        }
    ]

    metrics = compute_trading_metrics(trades, initial_capital=100000.0)
    assert len(metrics["daily_summary"]) == 1
    day = metrics["daily_summary"][0]

    assert "charges" in day
    assert day["charges"] == 0.0
    assert isinstance(day["charges"], float)
    assert day["trades"] == 1
    assert day["wins"] == 1
    assert day["losses"] == 0
    assert day["grossProfit"] == 260.0
    assert day["grossLoss"] == 0.0
    assert day["pnl"] == 260.0

    # Validate against Pydantic schema
    validated_day = DailyAnalyticsSchema(**day)
    assert validated_day.charges == 0.0


def test_day_with_null_charges():
    """Test a day where charges is explicitly None."""
    trades = [
        {
            "id": 1,
            "exit_time": "2026-11-18T10:00:00",
            "gross_pnl": 400.0,
            "charges": None,  # explicitly None
            "net_pnl": 400.0,
            "is_win": True,
        }
    ]

    metrics = compute_trading_metrics(trades, initial_capital=100000.0)
    assert len(metrics["daily_summary"]) == 1
    day = metrics["daily_summary"][0]

    assert "charges" in day
    assert day["charges"] == 0.0
    assert isinstance(day["charges"], float)
    assert day["pnl"] == 400.0

    # Validate against Pydantic schema
    validated_day = DailyAnalyticsSchema(**day)
    assert validated_day.charges == 0.0


def test_multiple_trading_days_and_consistency():
    """
    Test across multiple trading days and verify mathematical consistency:
    - Daily PnL equals grossProfit - grossLoss - charges
    - Sum of Daily PnL equals Net Profit (Realized PnL)
    - Sum of Daily Charges equals Total Brokerage Charges
    """
    trades = [
        # Day 1: 2026-11-17
        {
            "id": 1,
            "exit_time": "2026-11-17T09:30:00",
            "gross_pnl": 650.0,
            "charges": 50.0,
            "net_pnl": 600.0,
            "is_win": True,
        },
        {
            "id": 2,
            "exit_time": "2026-11-17T11:45:00",
            "gross_pnl": -400.0,
            "charges": 45.0,
            "net_pnl": -445.0,
            "is_win": False,
        },
        # Day 2: 2026-11-18 (one trade has missing charges, one has null charges)
        {
            "id": 3,
            "exit_time": "2026-11-18T10:15:00",
            "gross_pnl": 1300.0,
            "charges": 55.25,
            "net_pnl": 1244.75,
            "is_win": True,
        },
        {
            "id": 4,
            "exit_time": "2026-11-18T14:30:00",
            "gross_pnl": -650.0,
            "charges": None,  # null charges
            "net_pnl": -650.0,
            "is_win": False,
        },
    ]

    metrics = compute_trading_metrics(trades, initial_capital=100000.0)
    assert len(metrics["daily_summary"]) == 2

    # Verify Day 1
    d1 = metrics["daily_summary"][0]
    assert d1["date"] == "2026-11-17"
    assert d1["trades"] == 2
    assert d1["wins"] == 1
    assert d1["losses"] == 1
    assert d1["grossProfit"] == 650.0
    assert d1["grossLoss"] == 400.0
    assert d1["charges"] == 95.0
    assert d1["pnl"] == 155.0  # 650 - 400 - 95 = 155.0
    assert round(d1["grossProfit"] - d1["grossLoss"] - d1["charges"], 2) == d1["pnl"]

    # Verify Day 2
    d2 = metrics["daily_summary"][1]
    assert d2["date"] == "2026-11-18"
    assert d2["trades"] == 2
    assert d2["wins"] == 1
    assert d2["losses"] == 1
    assert d2["grossProfit"] == 1300.0
    assert d2["grossLoss"] == 650.0
    assert d2["charges"] == 55.25
    assert d2["pnl"] == 594.75  # 1300 - 650 - 55.25 = 594.75
    assert round(d2["grossProfit"] - d2["grossLoss"] - d2["charges"], 2) == d2["pnl"]

    # Global consistency checks
    sum_daily_pnl = round(sum(d["pnl"] for d in metrics["daily_summary"]), 2)
    assert sum_daily_pnl == metrics["net_profit"]
    assert metrics["net_profit"] == 749.75  # 155.0 + 594.75

    sum_daily_charges = round(sum(d["charges"] for d in metrics["daily_summary"]), 2)
    assert sum_daily_charges == metrics["total_brokerage_charges"]
    assert metrics["total_brokerage_charges"] == 150.25  # 95.0 + 55.25

    # Check cash balance consistency
    cash_balance = round(100000.0 + metrics["net_profit"], 2)
    assert cash_balance == 100749.75

    # Full Pydantic validation
    validated_summary = AnalyticsSummaryResponse(**metrics)
    assert len(validated_summary.daily_summary) == 2
    for day_model in validated_summary.daily_summary:
        assert isinstance(day_model.charges, float)
        assert day_model.charges >= 0.0
