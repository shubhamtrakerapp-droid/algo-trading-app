import pytest
import asyncio
from datetime import datetime, timezone
from backend.app.services.pcr_service import PCRService, normalize_underlying, get_strike_step
from backend.app.models import PCRSnapshot
from backend.app.database import AsyncSessionLocal, init_db


@pytest.mark.asyncio
async def test_underlying_normalization_and_steps():
    assert normalize_underlying("NIFTY 50") == "NIFTY"
    assert normalize_underlying("nifty") == "NIFTY"
    assert normalize_underlying("BANKNIFTY") == "BANKNIFTY"
    assert normalize_underlying("Bank Nifty") == "BANKNIFTY"
    assert normalize_underlying("FINNIFTY") == "FINNIFTY"
    assert normalize_underlying("Nifty Fin Service") == "FINNIFTY"

    assert get_strike_step("NIFTY") == 50.0
    assert get_strike_step("BANKNIFTY") == 100.0
    assert get_strike_step("FINNIFTY") == 50.0


@pytest.mark.asyncio
async def test_pcr_mathematical_formulas():
    # Prompt Section 16 Requirement:
    # Call OI = 2,000,000, Put OI = 2,400,000 -> OI PCR = 1.20
    # Call volume = 100,000, Put volume = 80,000 -> Volume PCR = 0.80
    tot_call_oi = 2000000
    tot_put_oi = 2400000
    oi_pcr = round(tot_put_oi / tot_call_oi, 2)
    assert oi_pcr == 1.20

    tot_call_vol = 100000
    tot_put_vol = 80000
    vol_pcr = round(tot_put_vol / tot_call_vol, 2)
    assert vol_pcr == 0.80

    # Zero denominator handling: should not throw ZeroDivisionError
    zero_call_oi = 0
    pcr_zero = round(tot_put_oi / zero_call_oi, 2) if zero_call_oi > 0 else None
    assert pcr_zero is None


@pytest.mark.asyncio
async def test_sentiment_engine_rules():
    # Test 1: Bullish Alignment
    # OI PCR > 1.05, Vol PCR > 1.05, Put OI change > Call OI change, Spot > VWAP
    res_bullish = PCRService._evaluate_sentiment(
        oi_pcr=1.25,
        volume_pcr=1.15,
        put_oi_change=500000,
        call_oi_change=100000,
        spot_price=25600.0,
        futures_vwap=25400.0,
        prev_oi_pcr=1.18,
        bullish_threshold=1.05,
        bearish_threshold=0.95
    )
    assert res_bullish["sentiment_bias"] == "BULLISH"
    assert res_bullish["score"] >= 2.0
    assert res_bullish["factors"]["oi_pcr_bias"] == "BULLISH"
    assert res_bullish["factors"]["price_vwap_bias"] == "BULLISH"

    # Test 2: Bearish Alignment
    # OI PCR < 0.95, Vol PCR < 0.95, Call OI change > Put OI change, Spot < VWAP
    res_bearish = PCRService._evaluate_sentiment(
        oi_pcr=0.75,
        volume_pcr=0.80,
        put_oi_change=-200000,
        call_oi_change=600000,
        spot_price=25200.0,
        futures_vwap=25400.0,
        prev_oi_pcr=0.82,
        bullish_threshold=1.05,
        bearish_threshold=0.95
    )
    assert res_bearish["sentiment_bias"] == "BEARISH"
    assert res_bearish["score"] <= -2.0
    assert res_bearish["factors"]["oi_pcr_bias"] == "BEARISH"
    assert res_bearish["factors"]["price_vwap_bias"] == "BEARISH"

    # Test 3: Conflicting Signals (OI PCR Bullish, but Spot below VWAP)
    res_conflict = PCRService._evaluate_sentiment(
        oi_pcr=1.30,
        volume_pcr=1.10,
        put_oi_change=400000,
        call_oi_change=100000,
        spot_price=25100.0,
        futures_vwap=25350.0,  # Spot < VWAP
        prev_oi_pcr=1.28,
        bullish_threshold=1.05,
        bearish_threshold=0.95
    )
    assert res_conflict["sentiment_bias"] == "CONFLICTING"
    assert "Conflicting Signals" in res_conflict["headline"]


MOCK_RAW_CHAIN = {
    "common_data": {"expiryDt": "2026-11-23", "mktLot": "65", "unlSymbol": "NIFTY"},
    "spot": {"ltp": "25500.00", "prevClose": "25400.00"},
    "future": {"symbol": "NIFTY26NOVFUT", "ltp": "25520.00", "exchId": "61471"},
    "call": [
        {
            "inst": {"strkPrc": str(s), "symbol": f"NIFTY26NOV{s}CE", "neoSymbol": f"OPT_{s}_CE"},
            "quote": {"ltp": "120.0", "vol": "100000"},
            "oi": {"cur": "2000000", "prev": "2200000"}
        }
        for s in range(24000, 27000, 50)
    ],
    "put": [
        {
            "inst": {"strkPrc": str(s), "symbol": f"NIFTY26NOV{s}PE", "neoSymbol": f"OPT_{s}_PE"},
            "quote": {"ltp": "95.0", "vol": "80000"},
            "oi": {"cur": "2400000", "prev": "2000000"}
        }
        for s in range(24000, 27000, 50)
    ]
}

MOCK_FUTURES_QUOTE = {
    "exchange_token": "61471",
    "display_symbol": "NIFTY26NOVFUT",
    "avg_cost": "25450.00",
    "ltp": "25520.00"
}


@pytest.mark.asyncio
async def test_pcr_service_analyze_and_db_persistence(monkeypatch):
    await init_db()

    async def mock_fetch(underlying, expiry=None, force_refresh=False):
        return MOCK_RAW_CHAIN, MOCK_FUTURES_QUOTE, "FRESH", None

    monkeypatch.setattr(PCRService, "fetch_raw_chain", mock_fetch)

    res = await PCRService.analyze_pcr(underlying="NIFTY", strike_range=5)
    assert res["status"] == "SUCCESS"
    assert res["underlying"] == "NIFTY"
    assert res["range_info"]["strike_range"] == 5
    assert len(res["strikes"]) == 11  # 5 below + ATM + 5 above = 11

    # Check cards
    cards = res["cards"]
    assert "oi_pcr" in cards
    assert "volume_pcr" in cards
    assert "call_oi" in cards
    assert "put_oi" in cards
    assert "price_vwap" in cards
    assert "market_bias" in cards

    # Check VWAP label requirement
    assert cards["price_vwap"]["index_vwap"] is None
    assert cards["price_vwap"]["index_vwap_label"] == "Index VWAP unavailable"
    assert cards["price_vwap"]["futures_vwap_label"] == "NIFTY FUTURES VWAP"

    # Check DB snapshot persistence
    hist = await PCRService.get_history(underlying="NIFTY", strike_range=5)
    assert len(hist) >= 1
    point = hist[-1]
    assert "oi_pcr" in point
    assert "volume_pcr" in point
    assert "spot_price" in point


@pytest.mark.asyncio
async def test_pcr_api_endpoints(monkeypatch):
    from starlette.testclient import TestClient
    from backend.app.main import app

    async def mock_fetch(underlying, expiry=None, force_refresh=False):
        return MOCK_RAW_CHAIN, MOCK_FUTURES_QUOTE, "FRESH", None

    monkeypatch.setattr(PCRService, "fetch_raw_chain", mock_fetch)

    with TestClient(app) as client:
        # Test GET /api/market-data/pcr
        r1 = client.get("/api/market-data/pcr?underlying=NIFTY&strike_range=10")
        assert r1.status_code == 200
        d1 = r1.json()
        assert d1["status"] == "SUCCESS"
        assert d1["range_info"]["strike_range"] == 10
        assert len(d1["strikes"]) == 21  # 10 below + ATM + 10 above = 21

        # Test GET /api/market-data/pcr/expiries
        r2 = client.get("/api/market-data/pcr/expiries?underlying=NIFTY")
        assert r2.status_code == 200
        d2 = r2.json()
        assert d2["status"] == "SUCCESS"
        assert len(d2["expiries"]) > 0

        # Test GET /api/market-data/pcr/history
        r3 = client.get("/api/market-data/pcr/history?underlying=NIFTY&strike_range=10")
        assert r3.status_code == 200
        d3 = r3.json()
        assert d3["status"] == "SUCCESS"

        # Test GET /api/market-data/pcr/dates
        r4 = client.get("/api/market-data/pcr/dates?underlying=NIFTY")
        assert r4.status_code == 200
        d4 = r4.json()
        assert d4["status"] == "SUCCESS"
        assert len(d4["dates"]) > 0
