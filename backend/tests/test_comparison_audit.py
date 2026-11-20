import pytest
import csv
import io
from httpx import AsyncClient, ASGITransport
from backend.app.main import app
from backend.app.backtest.engine import BacktestEngine
from backend.app.backtest.data_loader import BacktestDataLoader


@pytest.mark.asyncio
async def test_comparison_audit_api_endpoint():
    """
    Test 1: Verify the /api/backtest/comparison-audit endpoint runs the 4-way matrix
    and returns exact side-by-side reconciliation and root-cause analysis.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/backtest/comparison-audit?start_date=2026-11-09&end_date=2026-11-13")
        assert response.status_code == 200
        data = response.json()

        assert data["status"] == "SUCCESS"
        assert "market_dynamics" in data
        assert "comparison_matrix" in data
        assert "root_causes" in data
        assert "runs" in data

        matrix = data["comparison_matrix"]
        assert len(matrix) == 4

        keys = [item["key"] for item in matrix]
        assert "synthetic_trigger" in keys
        assert "synthetic_realistic" in keys
        assert "real_trigger" in keys
        assert "real_realistic" in keys

        # Verify mathematical identity on all 4 runs:
        # Gross Profit - Gross Loss - Total Charges == Net Profit
        for item in matrix:
            gross_p = item["gross_profit"]
            gross_l = item["gross_loss"]
            chg = item["total_charges"]
            net_p = item["net_profit"]
            assert abs((gross_p - gross_l - chg) - net_p) < 0.15

            # Quality badges
            if item["data_source"] == "SYNTHETIC_TEST":
                assert item["data_quality_status"] == "SIMULATED_TEST"
            else:
                assert item["data_quality_status"] == "AUTHENTIC_MARKET_DATA"

        # Verify market dynamics presence
        syn_dyn = data["market_dynamics"]["synthetic"]
        real_dyn = data["market_dynamics"]["real_market"]

        assert syn_dyn["nifty_drift"] > 0  # Synthetic has bull drift
        assert syn_dyn["option_drift"] > 0
        assert real_dyn["avg_1m_candle_range"] > syn_dyn["avg_1m_candle_range"]  # Real noise is wider


@pytest.mark.asyncio
async def test_comparison_audit_csv_export():
    """
    Test 2: Verify the /api/backtest/comparison-audit/export-csv endpoint produces
    a valid multi-section CSV with matrix, market dynamics, root causes, and trade logs.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/backtest/comparison-audit/export-csv?start_date=2026-11-09&end_date=2026-11-13")
        assert response.status_code == 200
        assert "text/csv" in response.headers["content-type"]
        assert "attachment; filename=" in response.headers.get("content-disposition", "")

        csv_text = response.text
        assert "NEXTRADE — SYNTHETIC VS REAL HISTORICAL BACKTEST COMPARISON AUDIT REPORT" in csv_text
        assert "EMPIRICAL 4-WAY PERFORMANCE MATRIX" in csv_text
        assert "UNDERLYING MARKET DYNAMICS & VOLATILITY NOISE COMPARISON" in csv_text
        assert "ROOT CAUSE SUMMARY" in csv_text
        assert "TRADE LOG: Synthetic (Simulated) — Trigger-Price Mode" in csv_text
        assert "TRADE LOG: Real Market (Kotak Neo) — Realistic Mode" in csv_text

        # Parse CSV to confirm valid syntax
        reader = csv.reader(io.StringIO(csv_text))
        rows = list(reader)
        assert len(rows) > 100


@pytest.mark.asyncio
async def test_strategy_formula_parity_on_both_datasets():
    """
    Test 3: Guarantee that both datasets use the exact same UT Bot strategy code,
    identical ATR formulas, identical SL/Target rules, and identical flat ₹20 charges.
    """
    loader = BacktestDataLoader(allow_offline_cache=True)
    syn_n, syn_o, syn_meta = await loader.load_dataset(
        symbol="NIFTY ATM CE", days=5, start_date="2026-11-09", end_date="2026-11-13", data_source="SYNTHETIC_TEST", seed=42
    )
    real_n, real_o, real_meta = await loader.load_dataset(
        symbol="NIFTY ATM CE", days=5, start_date="2026-11-09", end_date="2026-11-13", data_source="REAL_MARKET"
    )

    engine = BacktestEngine(
        initial_capital=100000.0,
        lots=5,
        lot_size=65,
        target_points=4.0,
        stop_points=2.0,
        slippage_points=0.10,
        execution_mode="TRIGGER_PRICE"
    )

    res_syn = engine.run_backtest(
        nifty_candles=syn_n,
        option_candles=syn_o,
        strategy_id="UT_BOT",
        instrument_symbol="NIFTY ATM CE",
        data_source="SYNTHETIC_TEST",
        metadata=syn_meta
    )

    res_real = engine.run_backtest(
        nifty_candles=real_n,
        option_candles=real_o,
        strategy_id="UT_BOT",
        instrument_symbol="NIFTY ATM CE",
        data_source="REAL_MARKET",
        metadata=real_meta
    )

    # Both must have configured SL 2.0 and Target 4.0
    assert res_syn["configured_sl_points"] == 2.0
    assert res_syn["configured_target_points"] == 4.0
    assert res_real["configured_sl_points"] == 2.0
    assert res_real["configured_target_points"] == 4.0

    # Charges must be flat ₹20 per trade on both
    for t in res_syn["trades"][:10]:
        assert t["charges"] == 20.0
    for t in res_real["trades"][:10]:
        assert t["charges"] == 20.0
