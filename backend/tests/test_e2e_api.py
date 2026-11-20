import pytest
from httpx import AsyncClient, ASGITransport
from backend.app.main import app
from backend.app.database import init_db


@pytest.mark.asyncio
async def test_full_system_e2e_flow():
    await init_db()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Health check
        res = await client.get("/api/health")
        assert res.status_code == 200
        health_data = res.json()
        assert health_data["status"] == "HEALTHY"
        assert health_data["mode"] == "PAPER_TRADING_ONLY"

        # 2. Market Status
        res = await client.get("/api/market/status")
        assert res.status_code == 200
        m_status = res.json()
        assert "nifty_price" in m_status
        assert "atm_strike" in m_status
        assert "option_symbol" in m_status

        # 3. Market Candles
        res = await client.get("/api/market/candles?symbol=NIFTY 50&limit=50")
        assert res.status_code == 200
        candles_res = res.json()
        assert "candles" in candles_res

        # 4. Option Chain
        res = await client.get("/api/market/option-chain")
        assert res.status_code == 200
        chain_res = res.json()
        assert len(chain_res["strikes"]) > 0

        # 5. Expiries
        res = await client.get("/api/market/expiries")
        assert res.status_code == 200
        exp_res = res.json()
        assert len(exp_res["expiries"]) > 0

        # 6. Strategy Settings & Status
        res = await client.get("/api/strategy/settings")
        assert res.status_code == 200
        strat_settings = res.json()
        assert strat_settings["ema_fast"] == 9
        assert strat_settings["ema_slow"] == 50

        res = await client.get("/api/strategy/status")
        assert res.status_code == 200

        # 7. Paper Trading Status
        res = await client.get("/api/paper/status")
        assert res.status_code == 200
        p_status = res.json()
        assert p_status["initial_capital"] == 100000.0

        # 8. Backtesting
        res = await client.post("/api/backtest/run", json={
            "start_date": "2026-11-01",
            "end_date": "2026-11-15",
            "lots": 1,
            "lot_size": 65,
            "target_points": 4.0,
            "stop_points": 4.0,
            "max_loss_per_trade": 1000.0,
            "slippage_points": 0.10,
            "use_synthetic_data": True
        })
        assert res.status_code == 200
        bt_res = res.json()
        assert "total_trades" in bt_res
        assert "net_profit" in bt_res
        assert "win_rate" in bt_res

        # 9. Analytics Summary
        res = await client.get("/api/analytics/summary")
        assert res.status_code == 200
        an_res = res.json()
        assert "total_trades" in an_res
        assert "equity_curve" in an_res
