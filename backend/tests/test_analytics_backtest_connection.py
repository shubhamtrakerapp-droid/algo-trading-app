import pytest
from httpx import AsyncClient, ASGITransport
from datetime import datetime, timezone, timedelta
from backend.app.main import app
from backend.app.database import AsyncSessionLocal
from backend.app.models import BacktestRun, BacktestTrade, PaperTrade


@pytest.mark.asyncio
async def test_analytics_summary_paper_vs_backtest_isolation():
    """Verify that paper trades and backtest runs do not cross-contaminate."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Query Paper summary
        resp_paper = await client.get("/api/analytics/summary?source=PAPER")
        assert resp_paper.status_code == 200
        data_paper = resp_paper.json()
        assert data_paper["data_source"] == "PAPER"

        # 2. Query Backtest summary with invalid run
        resp_invalid = await client.get("/api/analytics/summary?source=BACKTEST&run_id=999999")
        assert resp_invalid.status_code == 404
        assert "not found" in resp_invalid.json()["detail"]

        # 3. Create a test backtest run with 2 trades
        async with AsyncSessionLocal() as session:
            test_run = BacktestRun(
                strategy_id="UT_BOT",
                strategy_name="UT Bot Test Run",
                timeframe="1m",
                instrument_symbol="NIFTY ATM CE",
                start_date="2026-11-10",
                end_date="2026-11-11",
                initial_capital=100000.0,
                final_capital=100500.0,
                total_trades=2,
                winning_trades=1,
                losing_trades=1,
                win_rate=50.0,
                gross_profit=700.0,
                gross_loss=160.0,
                net_profit=500.0,
                profit_factor=4.38,
                max_drawdown=160.0,
                total_charges=40.0,
                data_source="TEST_MARKET"
            )
            session.add(test_run)
            await session.commit()
            await session.refresh(test_run)
            run_id = test_run.id

            t1 = BacktestTrade(
                run_id=run_id,
                signal_time=datetime(2026, 11, 10, 9, 30, tzinfo=timezone.utc),
                entry_time=datetime(2026, 11, 10, 9, 31, tzinfo=timezone.utc),
                exit_time=datetime(2026, 11, 10, 9, 45, tzinfo=timezone.utc),
                underlying_price=24500.0,
                option_symbol="NIFTY26NOV24500CE",
                strike=24500.0,
                expiry="2026-11-26",
                entry_price=100.0,
                exit_price=104.0,
                quantity=175,
                target=104.0,
                stop=98.0,
                configured_sl_points=2.0,
                configured_target_points=4.0,
                effective_sl_points=2.0,
                effective_target_points=4.0,
                sl_trigger_price=98.0,
                target_trigger_price=104.0,
                slippage_cost=0.0,
                execution_mode="TRIGGER_PRICE",
                holding_time_minutes=14,
                exit_reason="TARGET_REACHED",
                gross_pnl=700.0,
                entry_charge=10.0,
                exit_charge=10.0,
                charges=20.0,
                net_pnl=680.0,
                is_win=True
            )
            t2 = BacktestTrade(
                run_id=run_id,
                signal_time=datetime(2026, 11, 11, 10, 0, tzinfo=timezone.utc),
                entry_time=datetime(2026, 11, 11, 10, 1, tzinfo=timezone.utc),
                exit_time=datetime(2026, 11, 11, 10, 15, tzinfo=timezone.utc),
                underlying_price=24520.0,
                option_symbol="NIFTY26NOV24500CE",
                strike=24500.0,
                expiry="2026-11-26",
                entry_price=102.0,
                exit_price=100.0,
                quantity=175,
                target=106.0,
                stop=100.0,
                configured_sl_points=2.0,
                configured_target_points=4.0,
                effective_sl_points=2.0,
                effective_target_points=4.0,
                sl_trigger_price=100.0,
                target_trigger_price=106.0,
                slippage_cost=0.0,
                execution_mode="TRIGGER_PRICE",
                holding_time_minutes=14,
                exit_reason="STOP_LOSS",
                gross_pnl=-350.0,
                entry_charge=10.0,
                exit_charge=10.0,
                charges=20.0,
                net_pnl=-370.0,
                is_win=False
            )
            session.add_all([t1, t2])
            await session.commit()

        # 4. Fetch backtest summary for this exact run
        resp_run = await client.get(f"/api/analytics/summary?source=BACKTEST&run_id={run_id}")
        assert resp_run.status_code == 200
        data_run = resp_run.json()
        assert data_run["data_source"] == "BACKTEST"
        assert data_run["run_id"] == run_id
        assert data_run["total_trades"] == 2
        assert data_run["winning_trades"] == 1
        assert data_run["losing_trades"] == 1
        assert data_run["win_rate"] == 50.0
        assert data_run["net_profit"] == 310.0  # 680 - 370
        assert data_run["total_brokerage_charges"] == 40.0

        # 5. Fetch monthly calendar for this exact run
        resp_cal = await client.get(f"/api/analytics/calendar/monthly?year=2026&month=11&source=BACKTEST&run_id={run_id}")
        assert resp_cal.status_code == 200
        cal_data = resp_cal.json()
        assert cal_data["run_id"] == run_id
        assert cal_data["summary"]["total_trades"] == 2
        assert cal_data["summary"]["net_pnl"] == 310.0

        # 6. Fetch daily details for 2026-11-10
        resp_day = await client.get(f"/api/analytics/calendar/day?date=2026-11-10&source=BACKTEST&run_id={run_id}")
        assert resp_day.status_code == 200
        day_data = resp_day.json()
        assert day_data["has_trades"] is True
        assert day_data["trades_count"] == 1
        assert day_data["net_pnl"] == 680.0

        # 7. Fetch custom range
        resp_rng = await client.get(f"/api/analytics/calendar/custom-range?start_date=2026-11-01&end_date=2026-11-30&source=BACKTEST&run_id={run_id}")
        assert resp_rng.status_code == 200
        rng_data = resp_rng.json()
        assert rng_data["total_trades"] == 2
        assert rng_data["net_pnl"] == 310.0

        # 8. Verify backtest runs list
        resp_runs = await client.get("/api/analytics/backtest-runs")
        assert resp_runs.status_code == 200
        runs_list = resp_runs.json()
        assert any(r["id"] == run_id for r in runs_list)
