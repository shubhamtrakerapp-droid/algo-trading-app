import pytest
import asyncio
from datetime import datetime, timezone, timedelta, date
from unittest.mock import MagicMock, patch

from backend.app.adapters.kotak_neo import KotakNeoAdapter, KotakNeoHistoricalDataError
from backend.app.backtest.data_loader import BacktestDataLoader
from backend.app.backtest.engine import BacktestEngine
from backend.app.coordinator import coordinator
from backend.app.database import init_db, AsyncSessionLocal
from backend.app.models import HistoricalCandle
from backend.app.market.history_service import HistoricalMarketDataService
from sqlalchemy import select, delete

IST = timezone(timedelta(hours=5, minutes=30))


@pytest.fixture(autouse=True)
async def setup_db():
    await init_db()


# =========================================================================
# 1. NIFTY 50 HISTORICAL CANDLES (SINGLE DAY & 5-DAY REQUESTED PERIOD)
# =========================================================================

@pytest.mark.asyncio
async def test_nifty_single_day_historical_candles():
    """Verify 1-minute historical candles for a completed trading day."""
    adapter = KotakNeoAdapter()
    adapter.initialize_client()
    assert adapter.client is not None

    candles = await adapter.get_historical_candles(
        symbol="NIFTY 50",
        token="Nifty 50",
        exchange_segment="nse_cm",
        interval="1min",
        from_date="2026-11-17",
        to_date="2026-11-17"
    )

    assert len(candles) >= 300
    first_c = candles[0]
    assert first_c.open > 20000.0
    assert first_c.high >= max(first_c.open, first_c.close)
    assert first_c.low <= min(first_c.open, first_c.close)
    assert first_c.low > 0.0


@pytest.mark.asyncio
async def test_nifty_requested_period_2026_11_09_to_2026_11_13():
    """Verify authentic NIFTY 50 candles for the exact period 2026-11-09 to 2026-11-13."""
    adapter = KotakNeoAdapter()
    adapter.initialize_client()

    candles = await adapter.get_historical_candles(
        symbol="NIFTY 50",
        token="Nifty 50",
        exchange_segment="nse_cm",
        interval="1min",
        from_date="2026-11-09",
        to_date="2026-11-13"
    )

    assert len(candles) >= 1400  # Returns ~1447 real candles
    first_c = candles[0]
    last_c = candles[-1]

    # Verify session start on Monday Nov 09
    assert first_c.open > 24000.0
    # Verify session end on Friday Nov 13
    assert last_c.close > 24000.0
    assert first_c.timestamp < last_c.timestamp


# =========================================================================
# 2. TIME INTERVALS (1MIN AND 5MIN) & NEOSYMBOL RESOLUTION
# =========================================================================

@pytest.mark.asyncio
async def test_timeframe_interval_mapping_1m_and_5m():
    """Verify mapping of intervals (1m -> 1min, 5m -> 5min) and neosymbol resolution."""
    adapter = KotakNeoAdapter()
    adapter.initialize_client()

    # Verify neosymbol resolution
    assert adapter.resolve_neosymbol("NIFTY 50", "26000", "nse_cm") == "nse_cm|Nifty 50"
    assert adapter.resolve_neosymbol("NIFTY", "Nifty 50", "nse_cm") == "nse_cm|Nifty 50"
    assert adapter.resolve_neosymbol("BANK NIFTY", "26009", "nse_cm") == "nse_cm|Nifty Bank"

    # 1min fetch
    c_1m = await adapter.get_historical_candles(
        symbol="NIFTY 50",
        token="Nifty 50",
        exchange_segment="nse_cm",
        interval="1m",
        from_date="2026-11-17",
        to_date="2026-11-17"
    )
    # 5min fetch
    c_5m = await adapter.get_historical_candles(
        symbol="NIFTY 50",
        token="Nifty 50",
        exchange_segment="nse_cm",
        interval="5m",
        from_date="2026-11-17",
        to_date="2026-11-17"
    )

    assert len(c_1m) > len(c_5m)
    assert len(c_5m) >= 60  # ~75 bars in 375 minutes


# =========================================================================
# 3. OHLCV INTEGRITY AND IST TIMESTAMP PARSING
# =========================================================================

@pytest.mark.asyncio
async def test_ohlcv_mathematical_integrity_and_parsing():
    """Ensure high is always >= max(open, close) and low <= min(open, close)."""
    adapter = KotakNeoAdapter()
    adapter.initialize_client()

    candles = await adapter.get_historical_candles(
        symbol="NIFTY 50",
        token="Nifty 50",
        exchange_segment="nse_cm",
        interval="1min",
        from_date="2026-11-13",
        to_date="2026-11-13"
    )

    assert len(candles) > 0
    for c in candles:
        assert c.high >= max(c.open, c.close)
        assert c.low <= min(c.open, c.close)
        assert c.low > 0.0
        assert c.open > 0.0
        assert c.close > 0.0


@pytest.mark.asyncio
async def test_ist_timestamp_handling():
    """Verify timestamps reflect IST market hours (09:15 to 15:30 IST)."""
    adapter = KotakNeoAdapter()
    adapter.initialize_client()

    candles = await adapter.get_historical_candles(
        symbol="NIFTY 50",
        token="Nifty 50",
        exchange_segment="nse_cm",
        interval="1min",
        from_date="2026-11-13",
        to_date="2026-11-13"
    )

    first_ts = candles[0].timestamp
    if first_ts.tzinfo is None:
        first_ts = first_ts.replace(tzinfo=timezone.utc)
    ist_ts = first_ts.astimezone(IST)

    assert ist_ts.hour == 9
    assert ist_ts.minute == 15


# =========================================================================
# 4. DATE BATCHING & DUPLICATE PREVENTION
# =========================================================================

def test_chunk_date_range_limits():
    """Verify date ranges > 25 days are sliced into <= 25-day batches."""
    chunks = KotakNeoAdapter.chunk_date_range("2026-09-01", "2026-11-18", max_days=25)
    assert len(chunks) >= 3
    for c_start, c_end in chunks:
        d1 = datetime.strptime(c_start, "%Y-%m-%d").date()
        d2 = datetime.strptime(c_end, "%Y-%m-%d").date()
        assert (d2 - d1).days < 25


@pytest.mark.asyncio
async def test_database_caching_and_subsequent_retrieval():
    """Verify real candles are stored in historical_candles and loaded from DB on repeat."""
    adapter = KotakNeoAdapter()
    adapter.initialize_client()
    loader = BacktestDataLoader(kotak_adapter=adapter)

    # First load: fetches from broker and persists to cache
    n1, o1, meta1 = await loader.load_dataset(
        symbol="NIFTY ATM CE",
        start_date="2026-11-09",
        end_date="2026-11-13",
        data_source="REAL_MARKET"
    )
    assert len(n1) > 0
    assert len(o1) > 0
    contract_sym = meta1["contract_symbol"]

    # Verify candles exist in DB
    async with AsyncSessionLocal() as session:
        stmt = select(HistoricalCandle).where(HistoricalCandle.symbol == contract_sym)
        res = await session.execute(stmt)
        rows = res.scalars().all()
        assert len(rows) > 0

    # Second load: retrieves from database cache
    n2, o2, meta2 = await loader.load_dataset(
        symbol="NIFTY ATM CE",
        start_date="2026-11-09",
        end_date="2026-11-13",
        data_source="REAL_MARKET"
    )
    assert len(n2) == len(n1)
    assert len(o2) == len(o1)


# =========================================================================
# 5. BACKTEST ENGINE & ERROR HANDLING (NO SYNTHETIC FALLBACK)
# =========================================================================

@pytest.mark.asyncio
async def test_backtest_with_verified_historical_candles():
    """Run full UT Bot backtest with authentic Kotak Neo historical data."""
    adapter = KotakNeoAdapter()
    adapter.initialize_client()
    loader = BacktestDataLoader(kotak_adapter=adapter)

    n_candles, o_candles, meta = await loader.load_dataset(
        symbol="NIFTY ATM CE",
        start_date="2026-11-09",
        end_date="2026-11-13",
        data_source="REAL_MARKET"
    )

    engine = BacktestEngine(
        initial_capital=100000.0,
        lots=1,
        lot_size=65,
        target_points=4.0,
        stop_points=2.0
    )
    results = engine.run_backtest(
        nifty_candles=n_candles,
        option_candles=o_candles,
        strategy_id="UT_BOT",
        instrument_symbol="NIFTY ATM CE",
        data_source="REAL_MARKET",
        metadata=meta
    )

    assert results["total_trades"] > 0
    assert "net_profit" in results
    assert results["data_source"] == "REAL_MARKET"
    assert results["data_quality_status"] == "AUTHENTIC_MARKET_DATA"
    assert meta["data_quality_status"] == "AUTHENTIC_MARKET_DATA"


@pytest.mark.asyncio
async def test_no_automatic_synthetic_fallback_when_broker_unavailable():
    """Verify REAL_MARKET mode fails with clear error and NEVER switches to synthetic silently."""
    loader = BacktestDataLoader(kotak_adapter=None)

    with pytest.raises(ValueError) as exc_info:
        await loader.load_dataset(
            symbol="NIFTY ATM CE",
            start_date="2026-11-09",
            end_date="2026-11-13",
            data_source="REAL_MARKET"
        )

    assert "Kotak Neo API is not connected" in str(exc_info.value)


@pytest.mark.asyncio
async def test_api_failure_and_error_propagation():
    """Verify explicit broker error codes and messages are propagated transparently."""
    adapter = KotakNeoAdapter()
    adapter.initialize_client()

    # Pass an invalid neosymbol to trigger a broker 422 error
    with pytest.raises(KotakNeoHistoricalDataError) as exc_info:
        await adapter.get_historical_candles(
            symbol="INVALID_SYM",
            token="99999999",
            exchange_segment="nse_cm",
            interval="1min",
            from_date="2026-11-13",
            to_date="2026-11-13"
        )

    assert exc_info.value.status_code in (400, 422)
    assert "Kotak Neo API Error" in str(exc_info.value)
