import asyncio
import logging
import math
import random
import hashlib
from datetime import datetime, timezone, timedelta, date
from typing import List, Dict, Any, Optional, Tuple

from sqlalchemy import select, and_, or_, desc, asc
from backend.app.database import AsyncSessionLocal
from backend.app.models import HistoricalCandle, PaperTrade, BacktestTrade, BacktestRun
from backend.app.coordinator import coordinator
from backend.app.config import settings
from backend.app.backtest.data_loader import BacktestDataLoader
from backend.app.strategy.indicators import (
    calculate_ema,
    calculate_rsi,
    calculate_vwap,
    calculate_atr,
    calculate_heikin_ashi,
    aggregate_candles,
    IST
)

logger = logging.getLogger("nextrade.history_service")

TIMEFRAME_MINUTES = {
    "1m": 1,
    "2m": 2,
    "3m": 3,
    "5m": 5,
    "15m": 15,
    "30m": 30,
    "1h": 60,
    "4h": 240,
    "1D": 1440,
    "1d": 1440,
    "daily": 1440,
}

PRESET_DAYS = {
    "TODAY": 1,
    "1D": 1,
    "5D": 5,
    "1M": 22,
    "3M": 66,
    "6M": 130,
    "1Y": 252,
    "CUSTOM": 5,
}


class HistoricalMarketDataService:
    """
    Complete Historical Market Data and Chart Visualization Service.
    Supports:
    - Multi-timeframe aggregation (1m, 2m, 3m, 5m, 15m, 30m, 1h, 4h, 1D).
    - Session-aware trading day boundaries (09:15 - 15:30 IST).
    - Database caching in `historical_candles` table with duplicate prevention.
    - True Kotak Neo historical data or deterministic synthetic test data.
    - Synchronized trade markers with full 26-column ledger metadata for Backtest & Paper trading.
    - Lazy loading / backwards pagination.
    """

    @classmethod
    def resolve_symbol_info(cls, symbol: str) -> Dict[str, Any]:
        """Resolve symbol into underlying index, CE or PE contract metadata."""
        symbol_upper = symbol.strip().upper()
        now = datetime.now(timezone.utc)
        ist_now = now.astimezone(IST)

        # 1. NIFTY Index
        if symbol_upper in ("NIFTY 50", "NIFTY", "NIFTY_INDEX", "INDEX"):
            ltp = coordinator.latest_nifty_tick.last_price if coordinator.latest_nifty_tick else 24500.0
            return {
                "symbol": "NIFTY 50",
                "instrument_token": "Nifty 50",
                "exchange_segment": "nse_cm",
                "is_index": True,
                "strike": None,
                "option_type": None,
                "expiry": "PERPETUAL",
                "current_ltp": ltp,
                "lot_size": 65,
            }

        spot_price = coordinator.latest_nifty_tick.last_price if coordinator.latest_nifty_tick else 24500.0
        atm_strike = round(spot_price / 50.0) * 50.0

        # 2. Dynamic ATM CE
        if symbol_upper in ("NIFTY ATM CE", "ATM CE", "CE", "ATM_CE"):
            contract = coordinator.current_contract or {}
            c_symbol = contract.get("symbol") or f"NIFTY {int(atm_strike)} CE"
            c_token = contract.get("instrument_token") or f"OPT_{int(atm_strike)}_CE"
            ltp = coordinator.latest_option_tick.last_price if coordinator.latest_option_tick else 145.0
            return {
                "symbol": c_symbol,
                "instrument_token": c_token,
                "exchange_segment": "nse_fo",
                "is_index": False,
                "strike": float(contract.get("strike", atm_strike)),
                "option_type": "CE",
                "expiry": contract.get("expiry", "WEEKLY"),
                "current_ltp": ltp,
                "lot_size": int(contract.get("lot_size", 65)),
            }

        # 3. Dynamic ATM PE
        if symbol_upper in ("NIFTY ATM PE", "ATM PE", "PE", "ATM_PE"):
            c_symbol = f"NIFTY {int(atm_strike)} PE"
            c_token = f"OPT_{int(atm_strike)}_PE"
            # Estimate PE LTP from spot moneyness
            pe_ltp = max(5.0, round(140.0 - (spot_price - atm_strike) * 0.45, 2))
            return {
                "symbol": c_symbol,
                "instrument_token": c_token,
                "exchange_segment": "nse_fo",
                "is_index": False,
                "strike": float(atm_strike),
                "option_type": "PE",
                "expiry": "WEEKLY",
                "current_ltp": pe_ltp,
                "lot_size": 65,
            }

        # 4. Explicit Strike Contract (e.g. NIFTY 24500 CE, NIFTY 24600 PE)
        import re
        match = re.search(r"(\d{4,5})\s*(CE|PE)", symbol_upper)
        if match:
            strike_val = float(match.group(1))
            opt_type = match.group(2)
            c_symbol = f"NIFTY {int(strike_val)} {opt_type}"
            c_token = f"OPT_{int(strike_val)}_{opt_type}"
            intrinsic = max(0.0, (spot_price - strike_val) if opt_type == "CE" else (strike_val - spot_price))
            ltp = round(intrinsic + max(10.0, 120.0 - abs(spot_price - strike_val) * 0.15), 2)
            return {
                "symbol": c_symbol,
                "instrument_token": c_token,
                "exchange_segment": "nse_fo",
                "is_index": False,
                "strike": strike_val,
                "option_type": opt_type,
                "expiry": "WEEKLY",
                "current_ltp": ltp,
                "lot_size": 65,
            }

        # Default fallback
        return {
            "symbol": symbol,
            "instrument_token": symbol,
            "exchange_segment": "nse_fo" if ("CE" in symbol_upper or "PE" in symbol_upper) else "nse_cm",
            "is_index": "CE" not in symbol_upper and "PE" not in symbol_upper,
            "strike": atm_strike if ("CE" in symbol_upper or "PE" in symbol_upper) else None,
            "option_type": "CE" if "CE" in symbol_upper else ("PE" if "PE" in symbol_upper else None),
            "expiry": "WEEKLY",
            "current_ltp": 145.0,
            "lot_size": 65,
        }

    @classmethod
    async def load_candles_from_cache(
        cls,
        symbol: str,
        start_dt: Optional[datetime] = None,
        end_dt: Optional[datetime] = None,
        before_dt: Optional[datetime] = None,
        limit: int = 1500
    ) -> List[Dict[str, Any]]:
        """Query stored 1-minute historical candles from the SQLite database."""
        async with AsyncSessionLocal() as session:
            stmt = select(HistoricalCandle).where(
                HistoricalCandle.symbol == symbol,
                HistoricalCandle.timeframe == "1m"
            )

            if start_dt:
                stmt = stmt.where(HistoricalCandle.timestamp >= start_dt)
            if end_dt:
                stmt = stmt.where(HistoricalCandle.timestamp <= end_dt)
            if before_dt:
                stmt = stmt.where(HistoricalCandle.timestamp < before_dt)

            stmt = stmt.order_by(HistoricalCandle.timestamp.desc()).limit(limit)
            res = await session.execute(stmt)
            rows = res.scalars().all()

            # Return in chronological order
            candles = [
                {
                    "timestamp": r.timestamp,
                    "open": r.open,
                    "high": r.high,
                    "low": r.low,
                    "close": r.close,
                    "volume": r.volume,
                    "symbol": r.symbol,
                }
                for r in reversed(rows)
            ]
            return candles

    @classmethod
    async def save_candles_to_cache(
        cls,
        symbol: str,
        instrument_token: str,
        candles: List[Dict[str, Any]],
        timeframe: str = "1m"
    ) -> int:
        """Cache 1-minute candles into the database with duplicate prevention."""
        if not candles:
            return 0

        async with AsyncSessionLocal() as session:
            # Query existing timestamps in this range to avoid duplicates
            min_ts = min(c["timestamp"] for c in candles)
            max_ts = max(c["timestamp"] for c in candles)

            stmt = select(HistoricalCandle.timestamp).where(
                HistoricalCandle.symbol == symbol,
                HistoricalCandle.timeframe == timeframe,
                HistoricalCandle.timestamp >= min_ts,
                HistoricalCandle.timestamp <= max_ts
            )
            res = await session.execute(stmt)
            existing_ts_set = set(res.scalars().all())

            new_entries = []
            for c in candles:
                ts = c["timestamp"]
                # Normalize timezone to UTC
                ts_utc = ts if isinstance(ts, datetime) else datetime.fromtimestamp(int(ts), tz=timezone.utc)
                if ts_utc.tzinfo is None:
                    ts_utc = ts_utc.replace(tzinfo=timezone.utc)

                if ts_utc not in existing_ts_set:
                    existing_ts_set.add(ts_utc)
                    new_entries.append(
                        HistoricalCandle(
                            instrument_token=instrument_token,
                            symbol=symbol,
                            timeframe=timeframe,
                            timestamp=ts_utc,
                            open=float(c["open"]),
                            high=float(c["high"]),
                            low=float(c["low"]),
                            close=float(c["close"]),
                            volume=float(c.get("volume", 0.0) or 0.0)
                        )
                    )

            if new_entries:
                session.add_all(new_entries)
                await session.commit()
                logger.info(f"Cached {len(new_entries)} new candles for {symbol} ({timeframe}) in database.")
                return len(new_entries)
            return 0

    @classmethod
    async def get_candles(
        cls,
        symbol: str = "NIFTY 50",
        timeframe: str = "1m",
        chart_type: str = "candlestick",
        mode: str = "LIVE",
        data_source: str = "REAL_MARKET",
        range_preset: str = "5D",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        before_timestamp: Optional[int] = None,
        limit: int = 500,
        run_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Main query entrypoint for chart candles.
        Fetches 1-minute historical data, merges today's live feed if LIVE mode,
        aggregates to target timeframe, and computes all requested indicators.
        """
        inst_info = cls.resolve_symbol_info(symbol)
        resolved_symbol = inst_info["symbol"]
        token = inst_info["instrument_token"]
        is_index = inst_info["is_index"]
        target_mins = TIMEFRAME_MINUTES.get(timeframe, 1)

        # Date range boundaries
        now_utc = datetime.now(timezone.utc)
        ist_now = now_utc.astimezone(IST)

        before_dt = datetime.fromtimestamp(before_timestamp, tz=timezone.utc) if before_timestamp else None

        # Determine effective days or start/end dates
        days = PRESET_DAYS.get(range_preset.upper(), 5)
        if range_preset.upper() == "TODAY":
            start_date = ist_now.strftime("%Y-%m-%d")
            end_date = ist_now.strftime("%Y-%m-%d")

        # 1. Check if backtest mode with run_id
        if mode == "BACKTEST" and run_id:
            async with AsyncSessionLocal() as session:
                b_run = await session.get(BacktestRun, run_id)
                if b_run:
                    if not start_date:
                        start_date = b_run.start_date
                    if not end_date:
                        end_date = b_run.end_date
                    data_source = b_run.data_source
                    if resolved_symbol in ("NIFTY 50", "NIFTY ATM CE", "NIFTY ATM PE") and b_run.instrument_symbol:
                        resolved_symbol = b_run.instrument_symbol

        # 2. Query cached candles from database
        s_dt = datetime.strptime(start_date, "%Y-%m-%d").replace(hour=0, minute=0, second=0) if start_date else None
        e_dt = datetime.strptime(end_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59) if end_date else None

        cached_candles = await cls.load_candles_from_cache(
            symbol=resolved_symbol,
            start_dt=s_dt,
            end_dt=e_dt,
            before_dt=before_dt,
            limit=limit * 3  # Fetch enough 1m bars to construct aggregated timeframe
        )

        raw_1m_candles = list(cached_candles)

        # 3. If cached candles are insufficient, fetch from provider or generate
        needed_count = 375 * max(1, min(days, 30)) if range_preset.upper() != "TODAY" else 375
        if len(raw_1m_candles) < min(needed_count, 150) and not before_dt:
            loader = BacktestDataLoader(kotak_adapter=coordinator.kotak_adapter)

            if data_source == "REAL_MARKET":
                if settings.has_kotak_credentials and coordinator.kotak_adapter:
                    try:
                        s_str = start_date or (ist_now.date() - timedelta(days=days * 2)).strftime("%Y-%m-%d")
                        e_str = end_date or ist_now.strftime("%Y-%m-%d")
                        fetched = await loader.fetch_kotak_historical(
                            symbol=resolved_symbol,
                            token=token,
                            from_date=s_str,
                            to_date=e_str,
                            exchange_segment=inst_info["exchange_segment"],
                            interval="1min"
                        )
                        if fetched:
                            await cls.save_candles_to_cache(resolved_symbol, token, fetched, timeframe="1m")
                            raw_1m_candles = fetched
                        else:
                            logger.warning(f"Kotak Neo returned 0 historical candles for {resolved_symbol}")
                    except Exception as e:
                        logger.error(f"Error fetching historical data from Kotak: {e}")
                        # In REAL_MARKET mode, do not silently fallback to synthetic
                        return {
                            "status": "ERROR",
                            "error": f"Broker historical data error: {e}",
                            "symbol": resolved_symbol,
                            "timeframe": timeframe,
                            "mode": mode,
                            "data_source": "REAL_MARKET",
                            "candles": [],
                            "has_more": False
                        }
                else:
                    return {
                        "status": "ERROR",
                        "error": "Kotak Neo credentials not configured. Please configure broker credentials or select SYNTHETIC_TEST mode.",
                        "symbol": resolved_symbol,
                        "timeframe": timeframe,
                        "mode": mode,
                        "data_source": "REAL_MARKET",
                        "candles": [],
                        "has_more": False
                    }
            elif data_source == "SYNTHETIC_TEST":
                # Deterministic synthetic data generator for historical simulation / demo
                n_c, o_c = loader.generate_synthetic_backtest_dataset(
                    days=max(1, days),
                    start_date=start_date,
                    end_date=end_date,
                    seed=42,
                    instrument_symbol=resolved_symbol
                )
                source_candles = n_c if is_index else o_c
                if source_candles:
                    await cls.save_candles_to_cache(resolved_symbol, token, source_candles, timeframe="1m")
                    raw_1m_candles = source_candles

        # 4. If LIVE mode, append today's completed 1m candles from CandleBuilder in-memory history
        if mode == "LIVE":
            live_history = coordinator.candle_builder.get_history(resolved_symbol)
            if not live_history and is_index:
                live_history = coordinator.candle_builder.get_history("NIFTY 50")
            elif not live_history and not is_index:
                # check active contract
                curr_sym = coordinator.current_contract.get("symbol", "")
                if curr_sym:
                    live_history = coordinator.candle_builder.get_history(curr_sym)

            if live_history:
                existing_timestamps = {
                    int(c["timestamp"].timestamp()) if isinstance(c["timestamp"], datetime) else int(c["timestamp"])
                    for c in raw_1m_candles
                }
                for lc in live_history:
                    lc_ts = int(lc.timestamp.timestamp())
                    if lc_ts not in existing_timestamps:
                        existing_timestamps.add(lc_ts)
                        raw_1m_candles.append({
                            "timestamp": lc.timestamp,
                            "open": lc.open,
                            "high": lc.high,
                            "low": lc.low,
                            "close": lc.close,
                            "volume": float(lc.volume),
                            "symbol": resolved_symbol,
                            "complete": True
                        })

            # Also attach current forming in-progress candle if available
            forming = coordinator.candle_builder.get_current_candle(resolved_symbol)
            if not forming and is_index:
                forming = coordinator.candle_builder.get_current_candle("NIFTY 50")
            elif not forming and not is_index:
                curr_sym = coordinator.current_contract.get("symbol", "")
                if curr_sym:
                    forming = coordinator.candle_builder.get_current_candle(curr_sym)

            if forming:
                forming_ts = int(forming.timestamp.timestamp())
                existing_timestamps = {
                    int(c["timestamp"].timestamp()) if isinstance(c["timestamp"], datetime) else int(c["timestamp"])
                    for c in raw_1m_candles
                }
                if forming_ts not in existing_timestamps:
                    raw_1m_candles.append({
                        "timestamp": forming.timestamp,
                        "open": forming.open,
                        "high": forming.high,
                        "low": forming.low,
                        "close": forming.close,
                        "volume": float(forming.volume),
                        "symbol": resolved_symbol,
                        "complete": False
                    })

        # Ensure sorted chronologically
        def get_epoch(c):
            ts = c["timestamp"]
            return int(ts.timestamp()) if isinstance(ts, datetime) else int(ts)

        raw_1m_candles.sort(key=get_epoch)

        # Slice to requested limit before aggregation if paging
        if before_dt and len(raw_1m_candles) > limit * 3:
            raw_1m_candles = raw_1m_candles[-(limit * 3):]

        # 5. Aggregate to target timeframe
        if target_mins > 1:
            aggregated = aggregate_candles(raw_1m_candles, target_mins)
        else:
            aggregated = raw_1m_candles

        # Format timestamps to epoch seconds for Lightweight Charts
        formatted_candles: List[Dict[str, Any]] = []
        for c in aggregated:
            ts = c["timestamp"]
            epoch_sec = int(ts.timestamp()) if isinstance(ts, datetime) else int(ts)
            formatted_candles.append({
                "timestamp": epoch_sec,
                "time_iso": datetime.fromtimestamp(epoch_sec, tz=timezone.utc).isoformat(),
                "open": round(float(c["open"]), 2),
                "high": round(float(c["high"]), 2),
                "low": round(float(c["low"]), 2),
                "close": round(float(c["close"]), 2),
                "volume": round(float(c.get("volume", 0.0) or 0.0), 2),
                "symbol": resolved_symbol
            })

        # Apply Chart Type transformation (Heikin Ashi)
        if chart_type == "heikin_ashi" and formatted_candles:
            opens = [c["open"] for c in formatted_candles]
            highs = [c["high"] for c in formatted_candles]
            lows = [c["low"] for c in formatted_candles]
            closes = [c["close"] for c in formatted_candles]
            ha = calculate_heikin_ashi(opens, highs, lows, closes)
            for i, c in enumerate(formatted_candles):
                c["ha_open"] = ha["open"][i]
                c["ha_high"] = ha["high"][i]
                c["ha_low"] = ha["low"][i]
                c["ha_close"] = ha["close"][i]
                # In Heikin Ashi mode, set open/high/low/close to the smoothed values
                c["open"] = ha["open"][i]
                c["high"] = ha["high"][i]
                c["low"] = ha["low"][i]
                c["close"] = ha["close"][i]

        # 6. Compute Technical Indicators
        if formatted_candles:
            closes = [c["close"] for c in formatted_candles]
            highs = [c["high"] for c in formatted_candles]
            lows = [c["low"] for c in formatted_candles]

            ema_9 = calculate_ema(closes, 9)
            ema_21 = calculate_ema(closes, 21)
            ema_50 = calculate_ema(closes, 50)
            rsi_14 = calculate_rsi(closes, 14)
            vwap = calculate_vwap(formatted_candles)
            atr = calculate_atr(highs, lows, closes, 10)

            # UT Bot series
            ut_strat = coordinator.strategy_engine.ut_bot_strategy
            ut_evals = ut_strat.calculate_series(formatted_candles)

            for i, item in enumerate(formatted_candles):
                item["ema_9"] = round(ema_9[i], 2)
                item["ema_21"] = round(ema_21[i], 2)
                item["ema_50"] = round(ema_50[i], 2)
                item["rsi_14"] = round(rsi_14[i], 2)
                item["vwap"] = round(vwap[i], 2) if vwap[i] is not None else None
                item["atr"] = round(atr[i], 2) if atr[i] is not None else None
                if i < len(ut_evals):
                    ev = ut_evals[i]
                    item["trailing_stop"] = ev.trailing_stop
                    item["is_ut_buy"] = ev.is_buy
                    item["is_ut_sell"] = ev.is_sell
                    item["signal_type"] = "BUY" if ev.is_buy else ("SELL" if ev.is_sell else None)
                else:
                    item["trailing_stop"] = item["close"]
                    item["is_ut_buy"] = False
                    item["is_ut_sell"] = False
                    item["signal_type"] = None

        # Truncate to limit
        if len(formatted_candles) > limit:
            formatted_candles = formatted_candles[-limit:]

        oldest_ts = formatted_candles[0]["timestamp"] if formatted_candles else None
        newest_ts = formatted_candles[-1]["timestamp"] if formatted_candles else None

        return {
            "status": "SUCCESS",
            "symbol": resolved_symbol,
            "timeframe": timeframe,
            "chart_type": chart_type,
            "mode": mode,
            "data_source": data_source,
            "range_preset": range_preset,
            "candles_count": len(formatted_candles),
            "oldest_timestamp": oldest_ts,
            "newest_timestamp": newest_ts,
            "has_more": len(raw_1m_candles) >= limit * 2,
            "instrument_info": inst_info,
            "candles": formatted_candles
        }

    @classmethod
    async def get_trade_markers(
        cls,
        mode: str = "LIVE",
        run_id: Optional[int] = None,
        symbol: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Extract trade execution markers from stored ledger.
        Each trade produces:
        1. BUY entry marker at entry time and entry price.
        2. EXIT marker at exit time and exit price (with exit reason: TARGET, STOP_LOSS, AUTO_CLOSE, UT_SELL).
        """
        markers: List[Dict[str, Any]] = []

        async with AsyncSessionLocal() as session:
            if mode == "BACKTEST":
                stmt = select(BacktestTrade).order_by(BacktestTrade.entry_time.asc())
                if run_id:
                    stmt = stmt.where(BacktestTrade.run_id == run_id)
                if start_date:
                    s_dt = datetime.strptime(start_date, "%Y-%m-%d").replace(hour=0, minute=0, second=0)
                    stmt = stmt.where(BacktestTrade.entry_time >= s_dt)
                if end_date:
                    e_dt = datetime.strptime(end_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
                    stmt = stmt.where(BacktestTrade.entry_time <= e_dt)
                res = await session.execute(stmt)
                trades = res.scalars().all()

                for t in trades:
                    entry_dt = t.entry_time if t.entry_time.tzinfo else t.entry_time.replace(tzinfo=timezone.utc)
                    exit_dt = t.exit_time if t.exit_time.tzinfo else t.exit_time.replace(tzinfo=timezone.utc)

                    entry_epoch = int(entry_dt.timestamp())
                    exit_epoch = int(exit_dt.timestamp())

                    trade_identifier = getattr(t, "trade_num", None) or t.id

                    # Entry marker
                    markers.append({
                        "id": f"entry_{t.id}",
                        "trade_id": t.id,
                        "time": entry_epoch,
                        "position": "belowBar",
                        "color": "#10b981",
                        "shape": "arrowUp",
                        "text": f"BUY #{trade_identifier} @ ₹{t.entry_price:.2f}",
                        "trade_type": "ENTRY",
                        "strategy_id": getattr(t, "strategy_id", "UT_BOT"),
                        "contract": t.option_symbol,
                        "price": t.entry_price,
                        "quantity": t.quantity,
                        "sl_trigger": getattr(t, "sl_trigger_price", t.stop),
                        "target_trigger": getattr(t, "target_trigger_price", t.target),
                        "entry_time": entry_dt.isoformat(),
                    })

                    # Exit marker
                    reason = t.exit_reason
                    is_target = reason == "TARGET"
                    is_stop = reason in ("STOP_LOSS", "GAP_STOP")
                    is_auto = reason == "AUTO_CLOSE_3_20_PM"
                    is_ut_sell = reason == "UT_SELL_SIGNAL"

                    exit_color = "#10b981" if is_target else ("#ef4444" if is_stop else ("#f59e0b" if is_auto else "#3b82f6"))
                    exit_shape = "arrowDown"

                    markers.append({
                        "id": f"exit_{t.id}",
                        "trade_id": t.id,
                        "time": exit_epoch,
                        "position": "aboveBar",
                        "color": exit_color,
                        "shape": exit_shape,
                        "text": f"{reason} #{trade_identifier} @ ₹{t.exit_price:.2f}",
                        "trade_type": "EXIT",
                        "exit_reason": reason,
                        "strategy_id": getattr(t, "strategy_id", "UT_BOT"),
                        "contract": t.option_symbol,
                        "price": t.exit_price,
                        "quantity": t.quantity,
                        "gross_pnl": t.gross_pnl,
                        "charges": getattr(t, "charges", 20.0),
                        "slippage": getattr(t, "slippage_cost", 0.0),
                        "net_pnl": t.net_pnl,
                        "is_ambiguous": getattr(t, "is_ambiguous", False),
                        "entry_time": entry_dt.isoformat(),
                        "exit_time": exit_dt.isoformat(),
                    })

            else:
                # LIVE Paper trades
                stmt = select(PaperTrade).order_by(PaperTrade.entry_time.asc())
                res = await session.execute(stmt)
                trades = res.scalars().all()

                for t in trades:
                    entry_dt = t.entry_time if t.entry_time.tzinfo else t.entry_time.replace(tzinfo=timezone.utc)
                    exit_dt = t.exit_time if t.exit_time.tzinfo else t.exit_time.replace(tzinfo=timezone.utc)

                    entry_epoch = int(entry_dt.timestamp())
                    exit_epoch = int(exit_dt.timestamp())

                    markers.append({
                        "id": f"entry_{t.id}",
                        "trade_id": t.id,
                        "time": entry_epoch,
                        "position": "belowBar",
                        "color": "#10b981",
                        "shape": "arrowUp",
                        "text": f"BUY #{t.id} @ ₹{t.entry_price:.2f}",
                        "trade_type": "ENTRY",
                        "strategy_id": t.strategy_id,
                        "contract": t.option_symbol,
                        "price": t.entry_price,
                        "quantity": t.quantity,
                        "sl_trigger": getattr(t, "sl_trigger_price", t.stop_price),
                        "target_trigger": getattr(t, "target_trigger_price", t.target_price),
                        "entry_time": entry_dt.isoformat(),
                    })

                    reason = t.exit_reason
                    is_target = reason == "TARGET"
                    is_stop = reason in ("STOP_LOSS", "GAP_STOP")
                    is_auto = reason == "AUTO_CLOSE_3_20_PM"
                    exit_color = "#10b981" if is_target else ("#ef4444" if is_stop else ("#f59e0b" if is_auto else "#3b82f6"))

                    markers.append({
                        "id": f"exit_{t.id}",
                        "trade_id": t.id,
                        "time": exit_epoch,
                        "position": "aboveBar",
                        "color": exit_color,
                        "shape": "arrowDown",
                        "text": f"{reason} #{t.id} @ ₹{t.exit_price:.2f}",
                        "trade_type": "EXIT",
                        "exit_reason": reason,
                        "strategy_id": t.strategy_id,
                        "contract": t.option_symbol,
                        "price": t.exit_price,
                        "quantity": t.quantity,
                        "gross_pnl": t.gross_pnl,
                        "charges": t.total_charges,
                        "slippage": getattr(t, "slippage_cost", 0.0),
                        "net_pnl": t.net_pnl,
                        "entry_time": entry_dt.isoformat(),
                        "exit_time": exit_dt.isoformat(),
                    })

        return markers

    @classmethod
    def search_instruments(cls, query: str = "") -> List[Dict[str, Any]]:
        """Search supported trading and charting instruments."""
        spot = coordinator.latest_nifty_tick.last_price if coordinator.latest_nifty_tick else 24500.0
        atm = round(spot / 50.0) * 50.0

        instruments = [
            {
                "symbol": "NIFTY 50",
                "name": "NIFTY 50 INDEX",
                "type": "INDEX",
                "strike": None,
                "current_price": spot,
                "token": "Nifty 50",
                "exchange": "nse_cm"
            },
            {
                "symbol": f"NIFTY {int(atm)} CE",
                "name": f"NIFTY ATM CE ({int(atm)})",
                "type": "CE",
                "strike": atm,
                "current_price": coordinator.latest_option_tick.last_price if coordinator.latest_option_tick else 145.0,
                "token": f"OPT_{int(atm)}_CE",
                "exchange": "nse_fo"
            },
            {
                "symbol": f"NIFTY {int(atm)} PE",
                "name": f"NIFTY ATM PE ({int(atm)})",
                "type": "PE",
                "strike": atm,
                "current_price": 140.0,
                "token": f"OPT_{int(atm)}_PE",
                "exchange": "nse_fo"
            },
        ]

        # Add surrounding strikes
        for offset in [-100, -50, 50, 100]:
            st = atm + offset
            instruments.append({
                "symbol": f"NIFTY {int(st)} CE",
                "name": f"NIFTY {int(st)} CALL",
                "type": "CE",
                "strike": st,
                "current_price": max(5.0, round(145.0 - offset * 0.45, 2)),
                "token": f"OPT_{int(st)}_CE",
                "exchange": "nse_fo"
            })
            instruments.append({
                "symbol": f"NIFTY {int(st)} PE",
                "name": f"NIFTY {int(st)} PUT",
                "type": "PE",
                "strike": st,
                "current_price": max(5.0, round(140.0 + offset * 0.45, 2)),
                "token": f"OPT_{int(st)}_PE",
                "exchange": "nse_fo"
            })

        if query:
            q = query.strip().upper()
            instruments = [inst for inst in instruments if q in inst["symbol"].upper() or q in inst["name"].upper()]

        return instruments
