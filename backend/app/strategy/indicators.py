import numpy as np
import pandas as pd
from typing import List, Dict, Any, Optional


def calculate_ema(prices: List[float], period: int) -> List[float]:
    """
    Calculate Exponential Moving Average (EMA).
    Multiplier alpha = 2 / (period + 1).
    Initial seed is simple moving average (SMA) of first `period` prices.
    Returns list of EMA values aligned with input prices.
    """
    n = len(prices)
    if n == 0:
        return []
    if n < period:
        # Not enough data yet; return simple averages or running values
        result = []
        running_sum = 0.0
        for i, p in enumerate(prices):
            running_sum += p
            result.append(running_sum / (i + 1))
        return result

    result = [0.0] * n
    # Seed with SMA
    sma = sum(prices[:period]) / period
    for i in range(period - 1):
        result[i] = sum(prices[:i+1]) / (i + 1)
    result[period - 1] = sma

    alpha = 2.0 / (period + 1.0)
    for i in range(period, n):
        result[i] = (prices[i] * alpha) + (result[i - 1] * (1.0 - alpha))

    return result


def calculate_rsi(prices: List[float], period: int = 14) -> List[float]:
    """
    Calculate Wilder's Relative Strength Index (RSI).
    Standard 14-period RSI using exponential smoothing.
    """
    n = len(prices)
    if n == 0:
        return []
    if n <= period:
        # Return neutral 50.0 until enough bars are available
        return [50.0] * n

    result = [50.0] * n
    gains = [0.0] * n
    losses = [0.0] * n

    for i in range(1, n):
        diff = prices[i] - prices[i - 1]
        if diff > 0:
            gains[i] = diff
        else:
            losses[i] = -diff

    # First average
    avg_gain = sum(gains[1:period + 1]) / period
    avg_loss = sum(losses[1:period + 1]) / period

    if avg_loss == 0.0 and avg_gain == 0.0:
        result[period] = 50.0
    elif avg_loss == 0.0:
        result[period] = 100.0
    else:
        rs = avg_gain / avg_loss
        result[period] = 100.0 - (100.0 / (1.0 + rs))

    # Wilder's smoothing
    for i in range(period + 1, n):
        avg_gain = ((avg_gain * (period - 1)) + gains[i]) / period
        avg_loss = ((avg_loss * (period - 1)) + losses[i]) / period

        if avg_loss == 0.0 and avg_gain == 0.0:
            result[i] = 50.0
        elif avg_loss == 0.0:
            result[i] = 100.0
        else:
            rs = avg_gain / avg_loss
            result[i] = 100.0 - (100.0 / (1.0 + rs))

    return result


def calculate_vwap(candles: List[Dict[str, float]]) -> List[float]:
    """
    Calculate Volume Weighted Average Price (VWAP).
    Typical Price = (High + Low + Close) / 3.
    Cumulative (Typical Price * Volume) / Cumulative Volume.
    """
    if not candles:
        return []

    vwap_values = []
    cum_pv = 0.0
    cum_vol = 0.0

    for c in candles:
        tp = (c["high"] + c["low"] + c["close"]) / 3.0
        vol = max(1.0, c.get("volume", 1.0))
        cum_pv += tp * vol
        cum_vol += vol
        vwap_values.append(round(cum_pv / cum_vol, 2))

    return vwap_values


def calculate_atr(highs: List[float], lows: List[float], closes: List[float], period: int = 10) -> List[float]:
    """
    Calculate Average True Range (ATR) matching TradingView Pine Script atr(c).
    True Range = max(high - low, abs(high - close[1]), abs(low - close[1])).
    Uses Wilder's RMA (Running Moving Average) where alpha = 1 / period.
    """
    n = len(closes)
    if n == 0:
        return []
    if n == 1:
        return [round(highs[0] - lows[0], 4)]

    tr = [0.0] * n
    tr[0] = highs[0] - lows[0]
    for i in range(1, n):
        hl = highs[i] - lows[i]
        hc = abs(highs[i] - closes[i - 1])
        lc = abs(lows[i] - closes[i - 1])
        tr[i] = max(hl, hc, lc)

    atr = [0.0] * n
    if n <= period:
        running_sum = 0.0
        for i in range(n):
            running_sum += tr[i]
            atr[i] = round(running_sum / (i + 1), 4)
        return atr

    # First ATR is simple SMA of first `period` true ranges
    first_atr = sum(tr[:period]) / period
    for i in range(period - 1):
        atr[i] = round(sum(tr[:i + 1]) / (i + 1), 4)
    atr[period - 1] = round(first_atr, 4)

    # Wilder's smoothing: RMA_t = (RMA_{t-1} * (period - 1) + TR_t) / period
    prev_atr = first_atr
    for i in range(period, n):
        curr_atr = ((prev_atr * (period - 1)) + tr[i]) / period
        atr[i] = round(curr_atr, 4)
        prev_atr = curr_atr

    return atr


def calculate_supertrend(
    highs: List[float],
    lows: List[float],
    closes: List[float],
    atr_period: int = 10,
    multiplier: float = 3.0
) -> Dict[str, Any]:
    """
    Calculate standard Supertrend indicator matching TradingView / Pine Script ta.supertrend.
    Uses Wilder's ATR(atr_period) and multiplier.
    Returns:
      - supertrend: List[float] (the active trailing band)
      - direction: List[int] (1 for Bullish / Uptrend, -1 for Bearish / Downtrend)
      - upper_band: List[float] (final upper band)
      - lower_band: List[float] (final lower band)
      - atr: List[float]
    """
    n = len(closes)
    if n == 0:
        return {"supertrend": [], "direction": [], "upper_band": [], "lower_band": [], "atr": []}

    atr = calculate_atr(highs, lows, closes, period=atr_period)

    upper_band = [0.0] * n
    lower_band = [0.0] * n
    supertrend = [0.0] * n
    direction = [1] * n  # 1 = Bullish, -1 = Bearish

    # Calculate basic bands and final bands iteratively
    for i in range(n):
        hl2 = (highs[i] + lows[i]) / 2.0
        basic_upper = hl2 + (multiplier * atr[i])
        basic_lower = hl2 - (multiplier * atr[i])

        if i == 0:
            upper_band[0] = basic_upper
            lower_band[0] = basic_lower
            direction[0] = 1 if closes[0] >= basic_lower else -1
            supertrend[0] = round(lower_band[0] if direction[0] == 1 else upper_band[0], 2)
            upper_band[0] = round(upper_band[0], 2)
            lower_band[0] = round(lower_band[0], 2)
            continue

        # Final Upper Band: can only move down or stay flat during downtrend
        if basic_upper < upper_band[i - 1] or closes[i - 1] > upper_band[i - 1]:
            upper_band[i] = basic_upper
        else:
            upper_band[i] = upper_band[i - 1]

        # Final Lower Band: can only move up or stay flat during uptrend
        if basic_lower > lower_band[i - 1] or closes[i - 1] < lower_band[i - 1]:
            lower_band[i] = basic_lower
        else:
            lower_band[i] = lower_band[i - 1]

        # Direction determination
        prev_dir = direction[i - 1]
        if prev_dir == 1:
            if closes[i] < lower_band[i]:
                direction[i] = -1  # Bearish flip
            else:
                direction[i] = 1
        else:  # prev_dir == -1
            if closes[i] > upper_band[i]:
                direction[i] = 1  # Bullish flip
            else:
                direction[i] = -1

        supertrend[i] = round(lower_band[i] if direction[i] == 1 else upper_band[i], 2)
        upper_band[i] = round(upper_band[i], 2)
        lower_band[i] = round(lower_band[i], 2)

    return {
        "supertrend": supertrend,
        "direction": direction,
        "upper_band": upper_band,
        "lower_band": lower_band,
        "atr": atr
    }


def calculate_heikin_ashi(
    opens: List[float], highs: List[float], lows: List[float], closes: List[float]
) -> Dict[str, List[float]]:
    """
    Calculate Heikin Ashi OHLC series matching Pine Script security(heikinashi(...)).
    ha_close = (open + high + low + close) / 4
    ha_open = (ha_open[1] + ha_close[1]) / 2 (seeded with (open[0] + close[0]) / 2)
    ha_high = max(high, ha_open, ha_close)
    ha_low = min(low, ha_open, ha_close)
    """
    n = len(closes)
    if n == 0:
        return {"open": [], "high": [], "low": [], "close": []}

    ha_open = [0.0] * n
    ha_high = [0.0] * n
    ha_low = [0.0] * n
    ha_close = [0.0] * n

    ha_close[0] = round((opens[0] + highs[0] + lows[0] + closes[0]) / 4.0, 4)
    ha_open[0] = round((opens[0] + closes[0]) / 2.0, 4)
    ha_high[0] = max(highs[0], ha_open[0], ha_close[0])
    ha_low[0] = min(lows[0], ha_open[0], ha_close[0])

    for i in range(1, n):
        ha_close[i] = round((opens[i] + highs[i] + lows[i] + closes[i]) / 4.0, 4)
        ha_open[i] = round((ha_open[i - 1] + ha_close[i - 1]) / 2.0, 4)
        ha_high[i] = max(highs[i], ha_open[i], ha_close[i])
        ha_low[i] = min(lows[i], ha_open[i], ha_close[i])

    return {
        "open": ha_open,
        "high": ha_high,
        "low": ha_low,
        "close": ha_close
    }


from datetime import datetime, timezone, timedelta

IST = timezone(timedelta(hours=5, minutes=30))


def aggregate_candles(candles: List[Dict[str, Any]], target_minutes: int) -> List[Dict[str, Any]]:
    """
    Aggregate 1-minute candles into higher timeframe bars (e.g. 2m, 3m, 5m, 15m, 30m, 60m/1h, 240m/4h, 1440m/1D).
    Session-aware:
    - Anchored to Indian market trading hours (09:15 to 15:30 IST).
    - Multi-minute bars reset at market open (09:15 IST) of each trading day.
    - Candles from different trading days are NEVER merged across session closes!
    - Daily (1440m / 1D): Merges all candles within the same IST date into a single daily candle.
    """
    if target_minutes <= 1 or not candles:
        return candles

    aggregated: List[Dict[str, Any]] = []
    current_bucket: Optional[Dict[str, Any]] = None

    for c in candles:
        raw_ts = c["timestamp"]
        if isinstance(raw_ts, (int, float)):
            dt_utc = datetime.fromtimestamp(int(raw_ts), tz=timezone.utc)
            is_int_ts = True
        elif isinstance(raw_ts, datetime):
            dt_utc = raw_ts if raw_ts.tzinfo else raw_ts.replace(tzinfo=timezone.utc)
            is_int_ts = False
        elif isinstance(raw_ts, str):
            dt_utc = datetime.fromisoformat(raw_ts.replace("Z", "+00:00"))
            is_int_ts = False
        else:
            continue

        dt_ist = dt_utc.astimezone(IST)
        ist_date = dt_ist.date()

        if target_minutes >= 1440:
            # Daily bar: group by IST calendar date
            bucket_key = (ist_date, 0)
            # Daily candle timestamp: 09:15:00 IST on that date
            session_open_ist = datetime(ist_date.year, ist_date.month, ist_date.day, 9, 15, 0, tzinfo=IST)
            bucket_dt_utc = session_open_ist.astimezone(timezone.utc)
            bucket_start_epoch = int(bucket_dt_utc.timestamp())
        else:
            # Intraday bar anchored to 09:15 IST session open (555 minutes from midnight)
            minute_of_day = dt_ist.hour * 60 + dt_ist.minute
            market_open_min = 555  # 9 * 60 + 15

            if minute_of_day >= market_open_min:
                mins_from_open = minute_of_day - market_open_min
                bucket_idx = mins_from_open // target_minutes
                bucket_min_of_day = market_open_min + (bucket_idx * target_minutes)
            else:
                # Before 09:15 AM
                bucket_idx = minute_of_day // target_minutes
                bucket_min_of_day = bucket_idx * target_minutes

            bucket_key = (ist_date, bucket_min_of_day)
            b_hour = bucket_min_of_day // 60
            b_min = bucket_min_of_day % 60
            bucket_dt_ist = datetime(ist_date.year, ist_date.month, ist_date.day, b_hour, b_min, 0, tzinfo=IST)
            bucket_dt_utc = bucket_dt_ist.astimezone(timezone.utc)
            bucket_start_epoch = int(bucket_dt_utc.timestamp())

        if current_bucket is None or current_bucket["bucket_key"] != bucket_key:
            if current_bucket is not None:
                aggregated.append(current_bucket["candle"])

            ts_val = bucket_start_epoch if is_int_ts else bucket_dt_utc
            current_bucket = {
                "bucket_key": bucket_key,
                "candle": {
                    "timestamp": ts_val,
                    "time_iso": bucket_dt_utc.isoformat(),
                    "open": float(c["open"]),
                    "high": float(c["high"]),
                    "low": float(c["low"]),
                    "close": float(c["close"]),
                    "volume": float(c.get("volume", 0.0) or 0.0),
                    "symbol": c.get("symbol", ""),
                    "strike": c.get("strike"),
                    "expiry": c.get("expiry"),
                }
            }
        else:
            cand = current_bucket["candle"]
            cand["high"] = max(cand["high"], float(c["high"]))
            cand["low"] = min(cand["low"], float(c["low"]))
            cand["close"] = float(c["close"])
            cand["volume"] += float(c.get("volume", 0.0) or 0.0)

    if current_bucket is not None:
        aggregated.append(current_bucket["candle"])

    return aggregated
