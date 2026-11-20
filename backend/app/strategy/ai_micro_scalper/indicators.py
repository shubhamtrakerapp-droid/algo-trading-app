import numpy as np
import pandas as pd
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional, Tuple

from backend.app.strategy.indicators import (
    calculate_ema,
    calculate_rsi,
    calculate_atr,
    aggregate_candles,
    IST
)


def calculate_adx(
    highs: List[float],
    lows: List[float],
    closes: List[float],
    period: int = 14
) -> Dict[str, List[float]]:
    """
    Calculate Wilder's Directional Movement Index (DMI) and Average Directional Index (ADX 14).
    Matches TradingView Pine Script ta.dmi(14, 14) exactly.
    
    Formula:
    - TR = max(high - low, abs(high - close[1]), abs(low - close[1]))
    - +DM = high - high[1] if (high - high[1] > low[1] - low and high - high[1] > 0) else 0
    - -DM = low[1] - low if (low[1] - low > high - high[1] and low[1] - low > 0) else 0
    - Smooth TR, +DM, -DM using Wilder's RMA (alpha = 1 / period)
    - +DI = 100 * (+DM_smoothed / TR_smoothed)
    - -DI = 100 * (-DM_smoothed / TR_smoothed)
    - DX = 100 * abs(+DI - -DI) / max(1e-9, (+DI + -DI))
    - ADX = Wilder's RMA of DX over `period`
    """
    n = len(closes)
    if n == 0:
        return {"adx": [], "plus_di": [], "minus_di": []}
    if n < period:
        return {
            "adx": [0.0] * n,
            "plus_di": [0.0] * n,
            "minus_di": [0.0] * n
        }

    tr = [0.0] * n
    plus_dm = [0.0] * n
    minus_dm = [0.0] * n

    tr[0] = highs[0] - lows[0]
    for i in range(1, n):
        hl = highs[i] - lows[i]
        hc = abs(highs[i] - closes[i - 1])
        lc = abs(lows[i] - closes[i - 1])
        tr[i] = max(hl, hc, lc)

        up_move = highs[i] - highs[i - 1]
        down_move = lows[i - 1] - lows[i]

        if up_move > down_move and up_move > 0.0:
            plus_dm[i] = up_move
        else:
            plus_dm[i] = 0.0

        if down_move > up_move and down_move > 0.0:
            minus_dm[i] = down_move
        else:
            minus_dm[i] = 0.0

    # Wilder's smoothing helper (RMA)
    def rma(series: List[float], length: int) -> List[float]:
        out = [0.0] * n
        if n < length:
            return out
        # Initial seed is SMA
        seed = sum(series[:length]) / length
        for j in range(length - 1):
            out[j] = sum(series[:j + 1]) / (j + 1)
        out[length - 1] = seed
        for j in range(length, n):
            out[j] = ((out[j - 1] * (length - 1)) + series[j]) / length
        return out

    tr_smoothed = rma(tr, period)
    plus_dm_smoothed = rma(plus_dm, period)
    minus_dm_smoothed = rma(minus_dm, period)

    plus_di = [0.0] * n
    minus_di = [0.0] * n
    dx = [0.0] * n

    for i in range(n):
        den = tr_smoothed[i]
        if den > 1e-9:
            p_di = 100.0 * (plus_dm_smoothed[i] / den)
            m_di = 100.0 * (minus_dm_smoothed[i] / den)
        else:
            p_di = 0.0
            m_di = 0.0
        plus_di[i] = round(p_di, 2)
        minus_di[i] = round(m_di, 2)

        di_sum = p_di + m_di
        if di_sum > 1e-9:
            dx_val = 100.0 * abs(p_di - m_di) / di_sum
        else:
            dx_val = 0.0
        dx[i] = dx_val

    adx = rma(dx, period)
    adx_rounded = [round(a, 2) for a in adx]

    return {
        "adx": adx_rounded,
        "plus_di": plus_di,
        "minus_di": minus_di
    }


def calculate_session_vwap(candles: List[Dict[str, Any]]) -> List[float]:
    """
    Calculate intraday session-anchored Volume Weighted Average Price (VWAP).
    Resets at 09:15 IST (market open) on every trading day.
    Typical Price = (High + Low + Close) / 3.0.
    """
    if not candles:
        return []

    vwap_values: List[float] = []
    current_date: Optional[str] = None
    cum_pv = 0.0
    cum_vol = 0.0

    for c in candles:
        ts = c.get("timestamp")
        if isinstance(ts, (int, float)):
            dt = datetime.fromtimestamp(ts, tz=timezone.utc).astimezone(IST)
        elif isinstance(ts, datetime):
            dt = ts.astimezone(IST) if ts.tzinfo else ts.replace(tzinfo=timezone.utc).astimezone(IST)
        elif isinstance(ts, str):
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(IST)
        else:
            dt = datetime.now(IST)

        date_str = dt.strftime("%Y-%m-%d")
        # Reset on new trading day
        if date_str != current_date:
            current_date = date_str
            cum_pv = 0.0
            cum_vol = 0.0

        tp = (float(c["high"]) + float(c["low"]) + float(c["close"])) / 3.0
        vol = max(1.0, float(c.get("volume", 1.0) or 1.0))
        cum_pv += tp * vol
        cum_vol += vol
        vwap_values.append(round(cum_pv / cum_vol, 2))

    return vwap_values
