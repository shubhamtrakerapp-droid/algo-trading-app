import pytest
from datetime import datetime, timezone, timedelta, date
from httpx import AsyncClient, ASGITransport

from backend.app.main import app
from backend.app.database import init_db, AsyncSessionLocal
from backend.app.models import HistoricalCandle, BacktestRun, BacktestTrade, PaperPosition, PaperTrade
from backend.app.market.history_service import HistoricalMarketDataService
from backend.app.strategy.indicators import aggregate_candles, IST


# =========================================================================
# 1. TIMEFRAME AGGREGATION & SESSION BOUNDARY TESTS
# =========================================================================

def test_session_aware_aggregation_15m():
    """Verify 15-minute aggregation anchors to 09:15 IST and computes OHLCV correctly."""
    # 09:15 AM IST on 2026-11-12 is 03:45 AM UTC
    base_utc = datetime(2026, 11, 12, 3, 45, tzinfo=timezone.utc)
    one_min_bars = []

    for i in range(30):
        ts = base_utc + timedelta(minutes=i)
        one_min_bars.append({
            "timestamp": int(ts.timestamp()),
            "open": 100.0 + i,
            "high": 105.0 + i,
            "low": 98.0 + i,
            "close": 102.0 + i,
            "volume": 100.0,
            "symbol": "NIFTY 50"
        })

    agg_15m = aggregate_candles(one_min_bars, 15)
    # 30 1-minute bars should produce exactly 2 15-minute bars (09:15-09:30 and 09:30-09:45)
    assert len(agg_15m) == 2

    # Bar 1 (09:15 to 09:30): minutes 0 to 14
    bar1 = agg_15m[0]
    assert bar1["open"] == 100.0  # first candle open
    assert bar1["close"] == 102.0 + 14  # last candle close (minute 14)
    assert bar1["high"] == max(c["high"] for c in one_min_bars[:15])
    assert bar1["low"] == min(c["low"] for c in one_min_bars[:15])
    assert bar1["volume"] == 1500.0  # 15 * 100

    # Bar 2 (09:30 to 09:45): minutes 15 to 29
    bar2 = agg_15m[1]
    assert bar2["open"] == 100.0 + 15
    assert bar2["close"] == 102.0 + 29
    assert bar2["volume"] == 1500.0


def test_session_date_boundary_never_crosses_overnight():
    """Verify aggregation never merges candles across the overnight 15:30 to 09:15 boundary."""
    # Day 1 close: 15:29 IST (09:59 UTC)
    day1_close_utc = datetime(2026, 11, 12, 9, 59, tzinfo=timezone.utc)
    # Day 2 open: 09:15 IST (03:45 UTC next day)
    day2_open_utc = datetime(2026, 11, 13, 3, 45, tzinfo=timezone.utc)

    candles = [
        {"timestamp": int(day1_close_utc.timestamp()), "open": 200.0, "high": 205.0, "low": 199.0, "close": 202.0, "volume": 500.0},
        {"timestamp": int(day2_open_utc.timestamp()), "open": 210.0, "high": 215.0, "low": 209.0, "close": 212.0, "volume": 600.0},
    ]

    # Even with 4-hour (240m) aggregation, Day 1 and Day 2 must NEVER merge
    agg_240m = aggregate_candles(candles, 240)
    assert len(agg_240m) == 2
    assert agg_240m[0]["open"] == 200.0
    assert agg_240m[1]["open"] == 210.0


def test_daily_timeframe_aggregation():
    """Verify Daily (1D / 1440m) merges all intraday bars of the same IST date into 1 bar."""
    base_day1 = datetime(2026, 11, 12, 3, 45, tzinfo=timezone.utc)
    base_day2 = datetime(2026, 11, 13, 3, 45, tzinfo=timezone.utc)

    candles = []
    # 5 bars on Day 1
    for i in range(5):
        candles.append({
            "timestamp": int((base_day1 + timedelta(minutes=i * 60)).timestamp()),
            "open": 100.0 + i,
            "high": 110.0 + i,
            "low": 95.0,
            "close": 105.0 + i,
            "volume": 1000.0
        })
    # 5 bars on Day 2
    for i in range(5):
        candles.append({
            "timestamp": int((base_day2 + timedelta(minutes=i * 60)).timestamp()),
            "open": 200.0 + i,
            "high": 210.0 + i,
            "low": 195.0,
            "close": 205.0 + i,
            "volume": 2000.0
        })

    daily_bars = aggregate_candles(candles, 1440)
    assert len(daily_bars) == 2
    assert daily_bars[0]["open"] == 100.0
    assert daily_bars[0]["volume"] == 5000.0
    assert daily_bars[1]["open"] == 200.0
    assert daily_bars[1]["volume"] == 10000.0


# =========================================================================
# 2. HISTORICAL MARKET DATA SERVICE QUERY TESTS
# =========================================================================

@pytest.mark.asyncio
async def test_get_candles_all_timeframes():
    """Verify every supported timeframe returns valid OHLCV bars and indicators."""
    await init_db()

    timeframes = ["1m", "2m", "3m", "5m", "15m", "30m", "1h", "4h", "1D"]
    for tf in timeframes:
        res = await HistoricalMarketDataService.get_candles(
            symbol="NIFTY 50",
            timeframe=tf,
            range_preset="5D",
            mode="HISTORICAL",
            data_source="SYNTHETIC_TEST",
            limit=200
        )
        assert res["status"] == "SUCCESS"
        assert res["timeframe"] == tf
        assert len(res["candles"]) > 0

        first_c = res["candles"][0]
        assert "open" in first_c
        assert "high" in first_c
        assert "low" in first_c
        assert "close" in first_c
        assert "volume" in first_c
        assert "ema_9" in first_c
        assert "ema_21" in first_c
        assert "ema_50" in first_c
        assert "rsi_14" in first_c
        assert "trailing_stop" in first_c
        assert first_c["high"] >= first_c["low"]


@pytest.mark.asyncio
async def test_backward_pagination_lazy_loading():
    """Verify scrolling backwards using before_timestamp returns strictly older candles."""
    await init_db()

    # Query initial page
    res_page1 = await HistoricalMarketDataService.get_candles(
        symbol="NIFTY 50",
        timeframe="1m",
        range_preset="5D",
        mode="HISTORICAL",
        limit=50
    )
    assert len(res_page1["candles"]) > 0
    oldest_ts = res_page1["oldest_timestamp"]
    assert oldest_ts is not None

    # Query page 2 before oldest_ts
    res_page2 = await HistoricalMarketDataService.get_candles(
        symbol="NIFTY 50",
        timeframe="1m",
        range_preset="5D",
        mode="HISTORICAL",
        before_timestamp=oldest_ts,
        limit=50
    )

    if res_page2["candles"]:
        # Every candle in page 2 must be strictly before oldest_ts
        for c in res_page2["candles"]:
            assert c["timestamp"] < oldest_ts


@pytest.mark.asyncio
async def test_option_contracts_independent_premium_data():
    """Verify CE and PE contracts return genuine option premiums, distinct from NIFTY index."""
    await init_db()

    res_ce = await HistoricalMarketDataService.get_candles(
        symbol="NIFTY 24500 CE",
        timeframe="1m",
        range_preset="1D",
        mode="HISTORICAL"
    )
    res_pe = await HistoricalMarketDataService.get_candles(
        symbol="NIFTY 24500 PE",
        timeframe="1m",
        range_preset="1D",
        mode="HISTORICAL"
    )
    res_index = await HistoricalMarketDataService.get_candles(
        symbol="NIFTY 50",
        timeframe="1m",
        range_preset="1D",
        mode="HISTORICAL"
    )

    assert len(res_ce["candles"]) > 0
    assert len(res_pe["candles"]) > 0
    assert len(res_index["candles"]) > 0

    # Option premiums are typically ₹20 to ₹500, whereas NIFTY spot is ~24000 to ~26000
    ce_ltp = res_ce["candles"][-1]["close"]
    pe_ltp = res_pe["candles"][-1]["close"]
    spot_ltp = res_index["candles"][-1]["close"]

    assert spot_ltp > 20000.0  # Spot index
    assert ce_ltp < 2000.0     # Option premium
    assert pe_ltp < 2000.0     # Option premium
    assert ce_ltp != spot_ltp  # Never substitute spot for option premium


# =========================================================================
# 3. TRADE MARKERS & AUDIT RECONCILIATION TESTS
# =========================================================================

@pytest.mark.asyncio
async def test_backtest_trade_markers_synchronization():
    """Verify backtest markers accurately reflect executed trades in the stored ledger."""
    await init_db()

    # Create a test backtest run and trade
    async with AsyncSessionLocal() as session:
        b_run = BacktestRun(
            strategy_id="UT_BOT",
            strategy_name="UT Bot ATM Option",
            start_date="2026-11-09",
            end_date="2026-11-13",
            initial_capital=100000.0,
            final_capital=101280.0,
            total_trades=1,
            winning_trades=1,
            losing_trades=0,
            win_rate=100.0,
            gross_profit=1300.0,
            gross_loss=0.0,
            net_profit=1280.0,
            max_drawdown=0.0,
            profit_factor=99.0,
            avg_profit=1280.0,
            avg_loss=0.0,
            largest_win=1280.0,
            largest_loss=0.0,
            total_charges=20.0,
            data_source="HISTORICAL_DATA",
            execution_mode="TRIGGER_PRICE"
        )
        session.add(b_run)
        await session.flush()

        trade = BacktestTrade(
            run_id=b_run.id,
            signal_time=datetime(2026, 11, 10, 10, 0, 0, tzinfo=timezone.utc),
            entry_time=datetime(2026, 11, 10, 10, 1, 0, tzinfo=timezone.utc),
            exit_time=datetime(2026, 11, 10, 10, 15, 0, tzinfo=timezone.utc),
            option_symbol="NIFTY26NOV24500CE",
            underlying_price=24520.0,
            strike=24500.0,
            expiry="2026-11-26",
            entry_price=150.0,
            exit_price=154.0,
            quantity=325,
            stop=148.0,
            target=154.0,
            exit_reason="TARGET",
            gross_pnl=1300.0,
            charges=20.0,
            net_pnl=1280.0,
            is_win=True,
            holding_time_minutes=14,
            execution_mode="TRIGGER_PRICE",
            sl_trigger_price=148.0,
            target_trigger_price=154.0,
            slippage_cost=0.0
        )
        session.add(trade)
        await session.commit()
        saved_run_id = b_run.id

    markers = await HistoricalMarketDataService.get_trade_markers(mode="BACKTEST", run_id=saved_run_id)
    assert len(markers) == 2  # 1 Entry + 1 Exit

    # Entry marker
    m_entry = next(m for m in markers if m["trade_type"] == "ENTRY")
    assert m_entry["price"] == 150.0
    assert m_entry["quantity"] == 325
    assert m_entry["contract"] == "NIFTY26NOV24500CE"
    assert m_entry["sl_trigger"] == 148.0
    assert m_entry["target_trigger"] == 154.0

    # Exit marker
    m_exit = next(m for m in markers if m["trade_type"] == "EXIT")
    assert m_exit["price"] == 154.0
    assert m_exit["exit_reason"] == "TARGET"
    assert m_exit["gross_pnl"] == 1300.0
    assert m_exit["charges"] == 20.0
    assert m_exit["net_pnl"] == 1280.0


# =========================================================================
# 4. API ENDPOINT ROUTE TESTS
# =========================================================================

@pytest.mark.asyncio
async def test_market_chart_api_endpoints():
    """Verify FastAPI chart endpoints for candles, markers, instruments, and backtest runs."""
    await init_db()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Candles endpoint
        res = await client.get("/api/market/candles?symbol=NIFTY%2050&timeframe=5m&range_preset=5D")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "SUCCESS"
        assert len(data["candles"]) > 0

        # 2. Trade markers endpoint
        res_m = await client.get("/api/market/chart/trade-markers?mode=LIVE")
        assert res_m.status_code == 200
        assert res_m.json()["status"] == "SUCCESS"

        # 3. Instruments search endpoint
        res_inst = await client.get("/api/market/chart/instruments?query=24500")
        assert res_inst.status_code == 200
        inst_data = res_inst.json()
        assert inst_data["status"] == "SUCCESS"
        assert len(inst_data["instruments"]) > 0

        # 4. Backtest runs endpoint
        res_runs = await client.get("/api/market/chart/backtest-runs")
        assert res_runs.status_code == 200
        assert res_runs.json()["status"] == "SUCCESS"
