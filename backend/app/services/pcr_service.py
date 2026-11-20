import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional, Tuple
from sqlalchemy import select, desc

from backend.app.coordinator import coordinator
from backend.app.database import AsyncSessionLocal
from backend.app.models import PCRSnapshot

logger = logging.getLogger("nextrade.pcr_service")
IST = timezone(timedelta(hours=5, minutes=30))


def normalize_underlying(underlying: str) -> str:
    """Normalize user input to canonical underlying name."""
    u = underlying.strip().upper()
    if "BANK" in u:
        return "BANKNIFTY"
    elif "FIN" in u:
        return "FINNIFTY"
    elif "NIFTY" in u:
        return "NIFTY"
    return u


def get_strike_step(underlying: str) -> float:
    """Return appropriate strike interval for underlying index."""
    u = normalize_underlying(underlying)
    if u == "BANKNIFTY":
        return 100.0
    return 50.0  # NIFTY, FINNIFTY


class PCRService:
    """
    Isolated service for Put-Call Ratio (PCR) analytics, live option-chain metrics,
    VWAP analysis, support/resistance detection, rules-based sentiment, and snapshot storage.
    """

    # In-memory cache to respect Kotak Neo API rate limits:
    # Key: (underlying, expiry) -> {"timestamp": datetime, "raw_chain": dict, "futures_quote": dict}
    _cache: Dict[Tuple[str, str], Dict[str, Any]] = {}
    CACHE_TTL_SECONDS = 15  # Short-term cache to avoid 429 when user flips filters

    @classmethod
    def get_cache_key(cls, underlying: str, expiry: str) -> Tuple[str, str]:
        return (normalize_underlying(underlying), expiry.strip())

    @classmethod
    async def get_expiries(cls, underlying: str = "NIFTY") -> List[str]:
        """Fetch available expiry dates for given underlying."""
        u = normalize_underlying(underlying)
        if coordinator.kotak_adapter and coordinator.kotak_adapter.client:
            try:
                loop = asyncio.get_running_loop()
                res = await loop.run_in_executor(
                    None,
                    lambda: coordinator.kotak_adapter.client.expiries(exchange="nse_fo", underlying=u)
                )
                if res and isinstance(res, dict) and "expiries" in res:
                    exps = res.get("expiries", [])
                    if exps:
                        return sorted(exps)
            except Exception as e:
                logger.warning(f"Error fetching expiries from Kotak for {u}: {e}")

        # Fallback upcoming Thursday dates if offline/error
        today = datetime.now(timezone.utc).astimezone(IST).date()
        thursdays = []
        for i in range(1, 35):
            d = today + timedelta(days=i)
            if d.weekday() == 3:  # Thursday
                thursdays.append(d.isoformat())
                if len(thursdays) >= 6:
                    break
        return thursdays

    @classmethod
    async def fetch_raw_chain(
        cls,
        underlying: str,
        expiry: Optional[str] = None,
        force_refresh: bool = False
    ) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]], str, Optional[str]]:
        """
        Fetches raw option chain and futures quote from Kotak Neo with caching and rate limit handling.
        Returns: (raw_chain, futures_quote, data_status, warning_msg)
        """
        u = normalize_underlying(underlying)
        cache_key = cls.get_cache_key(u, expiry or "DEFAULT")
        now = datetime.now(timezone.utc)

        # 1. Check in-memory cache
        cached = cls._cache.get(cache_key)
        if cached and not force_refresh:
            age = (now - cached["timestamp"]).total_seconds()
            if age < cls.CACHE_TTL_SECONDS:
                return cached["raw_chain"], cached.get("futures_quote"), cached.get("data_status", "FRESH"), None

        # 2. Fetch from Kotak Neo client
        client = coordinator.kotak_adapter.client if coordinator.kotak_adapter else None
        if not client:
            # Fallback if in demo or client unavailable
            if cached:
                return cached["raw_chain"], cached.get("futures_quote"), "STALE", "Broker client not ready; showing cached data."
            return None, None, "API ERROR", "Kotak Neo client not initialized."

        loop = asyncio.get_running_loop()
        raw_chain = None
        futures_quote = None
        warning_msg = None

        try:
            # Request count=30 to fetch ±30 strikes around ATM in a single call
            raw_chain = await loop.run_in_executor(
                None,
                lambda: client.option_chain(
                    exchange="nse_fo",
                    underlying=u,
                    expiry=expiry,
                    count=30
                )
            )

            # Check for API-level 429 or error payload
            if isinstance(raw_chain, dict):
                code = raw_chain.get("code") or (raw_chain.get("fault", {}).get("code"))
                if str(code) == "429":
                    warning_msg = "Kotak Neo API rate limit exceeded (HTTP 429). Returning cached data."
                    if cached:
                        return cached["raw_chain"], cached.get("futures_quote"), "STALE", warning_msg
                    return None, None, "RATE_LIMITED", warning_msg

            # Fetch futures quote for VWAP if future contract present
            if raw_chain and isinstance(raw_chain, dict):
                fut = raw_chain.get("future", {})
                fut_token = fut.get("exchId")
                if fut_token:
                    try:
                        q_res = await loop.run_in_executor(
                            None,
                            lambda: client.quotes(
                                instrument_tokens=[{"instrument_token": str(fut_token), "exchange_segment": "nse_fo"}],
                                quote_type="all"
                            )
                        )
                        if q_res and isinstance(q_res, list) and len(q_res) > 0:
                            futures_quote = q_res[0]
                    except Exception as q_err:
                        logger.debug(f"Could not fetch futures quote for {fut_token}: {q_err}")

        except Exception as e:
            err_str = str(e)
            logger.error(f"Error calling option_chain for {u}: {err_str}")
            if "429" in err_str:
                warning_msg = "Kotak Neo API rate limit exceeded (HTTP 429). Using cached data."
            else:
                warning_msg = f"Kotak Neo API error: {err_str}"

            if cached:
                return cached["raw_chain"], cached.get("futures_quote"), "STALE", warning_msg
            return None, None, "API ERROR", warning_msg

        if not raw_chain or not isinstance(raw_chain, dict) or "spot" not in raw_chain:
            if cached:
                return cached["raw_chain"], cached.get("futures_quote"), "STALE", "Incomplete response from market feed."
            return None, None, "API ERROR", "Incomplete option chain data received."

        # Cache valid response
        actual_expiry = raw_chain.get("common_data", {}).get("expiryDt", expiry or "DEFAULT")
        save_key = cls.get_cache_key(u, actual_expiry)
        cls._cache[save_key] = {
            "timestamp": now,
            "raw_chain": raw_chain,
            "futures_quote": futures_quote,
            "data_status": "FRESH"
        }
        if save_key != cache_key:
            cls._cache[cache_key] = cls._cache[save_key]

        return raw_chain, futures_quote, "FRESH", warning_msg

    @classmethod
    async def analyze_pcr(
        cls,
        underlying: str = "NIFTY",
        expiry: Optional[str] = None,
        strike_range: int = 10,
        force_refresh: bool = False,
        oi_pcr_bullish_threshold: float = 1.05,
        oi_pcr_bearish_threshold: float = 0.95
    ) -> Dict[str, Any]:
        """
        Core analytical calculation for the PCR & Options Market Intelligence page.
        """
        u = normalize_underlying(underlying)
        step = get_strike_step(u)
        raw_chain, futures_quote, data_status, warning_msg = await cls.fetch_raw_chain(
            underlying=u,
            expiry=expiry,
            force_refresh=force_refresh
        )

        now_utc = datetime.now(timezone.utc)
        ist_now = now_utc.astimezone(IST)
        ist_str = ist_now.strftime("%Y-%m-%d %H:%M:%S IST")
        trading_date = ist_now.strftime("%Y-%m-%d")

        # Market session status check
        is_weekday = ist_now.weekday() < 5
        time_str = ist_now.strftime("%H:%M")
        is_market_open = bool(is_weekday and ("09:15" <= time_str <= "15:30"))
        if not is_market_open and data_status == "FRESH":
            data_status = "MARKET CLOSED"

        if not raw_chain:
            return {
                "status": "ERROR",
                "message": warning_msg or "Failed to retrieve option chain data.",
                "underlying": u,
                "data_status": data_status,
                "timestamp_ist": ist_str,
                "is_market_open": is_market_open
            }

        # 1. Spot and Underlying Details
        spot_data = raw_chain.get("spot", {})
        spot_price = float(spot_data.get("ltp", 0.0))
        prev_close = float(spot_data.get("prevClose", spot_price) or spot_price)
        spot_change = round(spot_price - prev_close, 2)
        spot_change_pct = round((spot_change / prev_close * 100), 2) if prev_close > 0 else 0.0

        common_data = raw_chain.get("common_data", {})
        resolved_expiry = common_data.get("expiryDt", expiry or "")
        lot_size = int(common_data.get("mktLot", 65) or 65)

        # 2. VWAP & Futures Details
        futures_data = raw_chain.get("future", {})
        futures_symbol = futures_data.get("symbol", "")
        futures_ltp = float(futures_data.get("ltp", 0.0)) if futures_data.get("ltp") else None

        futures_vwap = None
        if futures_quote and isinstance(futures_quote, dict):
            try:
                avg_cost_val = float(futures_quote.get("avg_cost", 0.0))
                if avg_cost_val > 0:
                    futures_vwap = round(avg_cost_val, 2)
            except Exception:
                futures_vwap = None

        spot_vwap_diff = round(spot_price - futures_vwap, 2) if futures_vwap else None
        spot_vwap_diff_pct = round((spot_vwap_diff / futures_vwap * 100), 2) if (futures_vwap and spot_vwap_diff) else None

        # 3. Calculate ATM and Map Strikes
        atm_strike = round(spot_price / step) * step

        calls_list = raw_chain.get("call", [])
        puts_list = raw_chain.get("put", [])

        # Index calls and puts by strike
        calls_by_strike: Dict[float, Dict[str, Any]] = {}
        for c in calls_list:
            strk = float(c.get("inst", {}).get("strkPrc", 0.0))
            if strk > 0:
                calls_by_strike[strk] = c

        puts_by_strike: Dict[float, Dict[str, Any]] = {}
        for p in puts_list:
            strk = float(p.get("inst", {}).get("strkPrc", 0.0))
            if strk > 0:
                puts_by_strike[strk] = p

        all_strikes = sorted(list(set(calls_by_strike.keys()).union(set(puts_by_strike.keys()))))
        if not all_strikes:
            return {
                "status": "ERROR",
                "message": "No valid strike prices found in option chain.",
                "underlying": u,
                "data_status": data_status,
                "timestamp_ist": ist_str
            }

        # 4. Strike Range Selection (AutoTrender Experience)
        # Find index closest to ATM
        atm_idx = min(range(len(all_strikes)), key=lambda i: abs(all_strikes[i] - atm_strike))
        
        if strike_range > 0:
            start_idx = max(0, atm_idx - strike_range)
            end_idx = min(len(all_strikes), atm_idx + strike_range + 1)
            selected_strikes = all_strikes[start_idx:end_idx]
            requested_count = 2 * strike_range + 1
            actual_count = len(selected_strikes)
            if actual_count < requested_count and not warning_msg:
                warning_msg = f"Requested ±{strike_range} strikes ({requested_count}), provider returned {actual_count} available strikes."
        else:
            selected_strikes = all_strikes
            requested_count = len(all_strikes)
            actual_count = len(all_strikes)

        # 5. Build Strike-by-Strike Analytics Table
        table_rows: List[Dict[str, Any]] = []
        tot_call_oi = 0
        tot_put_oi = 0
        tot_call_prev_oi = 0
        tot_put_prev_oi = 0
        tot_call_vol = 0
        tot_put_vol = 0
        tot_call_oi_chg = 0
        tot_put_oi_chg = 0

        max_call_oi = -1
        max_call_oi_strike = 0.0
        max_put_oi = -1
        max_put_oi_strike = 0.0

        max_call_oi_chg = -1000000000
        max_call_oi_chg_strike = 0.0
        max_put_oi_chg = -1000000000
        max_put_oi_chg_strike = 0.0

        for s in selected_strikes:
            c_data = calls_by_strike.get(s, {})
            p_data = puts_by_strike.get(s, {})

            # Call parsing
            c_inst = c_data.get("inst", {})
            c_quote = c_data.get("quote", {})
            c_oi = c_data.get("oi", {})

            ce_ltp = float(c_quote.get("ltp", 0.0))
            ce_vol = int(c_quote.get("vol", 0) or 0)
            ce_oi_cur = int(c_oi.get("cur", 0) or 0)
            ce_oi_prev = int(c_oi.get("prev", ce_oi_cur) or ce_oi_cur)
            # True contract OI change = cur - prev (Do NOT use oi["chg"] which is price change in Kotak API)
            ce_oi_chg = ce_oi_cur - ce_oi_prev
            ce_oi_chg_pct = round((ce_oi_chg / ce_oi_prev * 100), 2) if ce_oi_prev > 0 else 0.0

            # Put parsing
            p_inst = p_data.get("inst", {})
            p_quote = p_data.get("quote", {})
            p_oi = p_data.get("oi", {})

            pe_ltp = float(p_quote.get("ltp", 0.0))
            pe_vol = int(p_quote.get("vol", 0) or 0)
            pe_oi_cur = int(p_oi.get("cur", 0) or 0)
            pe_oi_prev = int(p_oi.get("prev", pe_oi_cur) or pe_oi_cur)
            pe_oi_chg = pe_oi_cur - pe_oi_prev
            pe_oi_chg_pct = round((pe_oi_chg / pe_oi_prev * 100), 2) if pe_oi_prev > 0 else 0.0

            # Aggregates
            tot_call_oi += ce_oi_cur
            tot_put_oi += pe_oi_cur
            tot_call_prev_oi += ce_oi_prev
            tot_put_prev_oi += pe_oi_prev
            tot_call_vol += ce_vol
            tot_put_vol += pe_vol
            tot_call_oi_chg += ce_oi_chg
            tot_put_oi_chg += pe_oi_chg

            # Track Max Strikes
            if ce_oi_cur > max_call_oi:
                max_call_oi = ce_oi_cur
                max_call_oi_strike = s
            if pe_oi_cur > max_put_oi:
                max_put_oi = pe_oi_cur
                max_put_oi_strike = s
            if ce_oi_chg > max_call_oi_chg:
                max_call_oi_chg = ce_oi_chg
                max_call_oi_chg_strike = s
            if pe_oi_chg > max_put_oi_chg:
                max_put_oi_chg = pe_oi_chg
                max_put_oi_chg_strike = s

            # Strike-wise ratios
            strike_oi_pcr = round(pe_oi_cur / ce_oi_cur, 2) if ce_oi_cur > 0 else None
            strike_vol_ratio = round(pe_vol / ce_vol, 2) if ce_vol > 0 else None

            is_atm = bool(abs(s - atm_strike) < (step / 2.0))
            moneyness_ce = "ITM" if s < spot_price else ("ATM" if is_atm else "OTM")
            moneyness_pe = "ITM" if s > spot_price else ("ATM" if is_atm else "OTM")

            table_rows.append({
                "strike": s,
                "is_atm": is_atm,
                # CALL SIDE
                "ce_symbol": c_inst.get("symbol", f"{u}{int(s)}CE"),
                "ce_token": c_inst.get("neoSymbol", "").replace("nse_fo|", ""),
                "ce_ltp": ce_ltp if ce_ltp > 0 else None,
                "ce_volume": ce_vol,
                "ce_oi": ce_oi_cur,
                "ce_oi_change": ce_oi_chg,
                "ce_oi_change_pct": ce_oi_chg_pct,
                "ce_moneyness": moneyness_ce,
                # PUT SIDE
                "pe_symbol": p_inst.get("symbol", f"{u}{int(s)}PE"),
                "pe_token": p_inst.get("neoSymbol", "").replace("nse_fo|", ""),
                "pe_ltp": pe_ltp if pe_ltp > 0 else None,
                "pe_volume": pe_vol,
                "pe_oi": pe_oi_cur,
                "pe_oi_change": pe_oi_chg,
                "pe_oi_change_pct": pe_oi_chg_pct,
                "pe_moneyness": moneyness_pe,
                # STRIKE-WISE RATIOS
                "strike_oi_pcr": strike_oi_pcr,
                "strike_vol_ratio": strike_vol_ratio,
            })

        # 6. Primary Aggregate Metrics
        oi_pcr = round(tot_put_oi / tot_call_oi, 2) if tot_call_oi > 0 else None
        volume_pcr = round(tot_put_vol / tot_call_vol, 2) if tot_call_vol > 0 else None

        tot_call_oi_chg_pct = round((tot_call_oi_chg / tot_call_prev_oi * 100), 2) if tot_call_prev_oi > 0 else 0.0
        tot_put_oi_chg_pct = round((tot_put_oi_chg / tot_put_prev_oi * 100), 2) if tot_put_prev_oi > 0 else 0.0

        # Retrieve previous snapshot for delta calculation
        prev_snapshot = await cls._get_latest_snapshot(u, resolved_expiry, strike_range)
        prev_oi_pcr = prev_snapshot.oi_pcr if prev_snapshot else None
        prev_vol_pcr = prev_snapshot.volume_pcr if prev_snapshot else None

        oi_pcr_delta = round(oi_pcr - prev_oi_pcr, 2) if (oi_pcr is not None and prev_oi_pcr is not None) else None
        vol_pcr_delta = round(volume_pcr - prev_vol_pcr, 2) if (volume_pcr is not None and prev_vol_pcr is not None) else None

        # 7. Transparent Rules-Based Sentiment Engine
        sentiment_data = cls._evaluate_sentiment(
            oi_pcr=oi_pcr,
            volume_pcr=volume_pcr,
            put_oi_change=tot_put_oi_chg,
            call_oi_change=tot_call_oi_chg,
            spot_price=spot_price,
            futures_vwap=futures_vwap,
            prev_oi_pcr=prev_oi_pcr,
            bullish_threshold=oi_pcr_bullish_threshold,
            bearish_threshold=oi_pcr_bearish_threshold
        )

        # 8. Persist 1-minute historical snapshot
        if is_market_open or data_status != "API ERROR":
            try:
                await cls._save_snapshot(
                    underlying=u,
                    expiry=resolved_expiry,
                    strike_range=strike_range,
                    timestamp=now_utc,
                    timestamp_ist=ist_now.strftime("%Y-%m-%d %H:%M"),
                    trading_date=trading_date,
                    atm_strike=atm_strike,
                    spot_price=spot_price,
                    total_call_oi=tot_call_oi,
                    total_put_oi=tot_put_oi,
                    oi_pcr=oi_pcr,
                    total_call_volume=tot_call_vol,
                    total_put_volume=tot_put_vol,
                    volume_pcr=volume_pcr,
                    call_oi_change=tot_call_oi_chg,
                    put_oi_change=tot_put_oi_chg,
                    underlying_vwap=None,
                    futures_vwap=futures_vwap,
                    futures_symbol=futures_symbol,
                    sentiment=sentiment_data["sentiment_bias"],
                    sentiment_score=sentiment_data["score"],
                    data_status=data_status
                )
            except Exception as s_err:
                logger.debug(f"Snapshot storage throttled or duplicate minute: {s_err}")

        return {
            "status": "SUCCESS",
            "underlying": u,
            "expiry": resolved_expiry,
            "lot_size": lot_size,
            "timestamp_ist": ist_str,
            "trading_date": trading_date,
            "data_status": data_status,
            "warning": warning_msg,
            "is_market_open": is_market_open,
            "range_info": {
                "atm_strike": atm_strike,
                "strike_range": strike_range,
                "requested_levels": requested_count,
                "selected_levels": actual_count,
            },
            # 6 SUMMARY CARDS
            "cards": {
                # Card 1: OI PCR
                "oi_pcr": {
                    "value": oi_pcr,
                    "previous": prev_oi_pcr,
                    "delta": oi_pcr_delta,
                    "total_put_oi": tot_put_oi,
                    "total_call_oi": tot_call_oi,
                    "sentiment_label": sentiment_data["factors"]["oi_pcr_bias"],
                    "description": "Total Put OI divided by Total Call OI across selected strikes."
                },
                # Card 2: Volume PCR
                "volume_pcr": {
                    "value": volume_pcr,
                    "previous": prev_vol_pcr,
                    "delta": vol_pcr_delta,
                    "total_put_volume": tot_put_vol,
                    "total_call_volume": tot_call_vol,
                    "sentiment_label": sentiment_data["factors"]["volume_pcr_bias"],
                    "description": "Total Put Traded Volume divided by Total Call Traded Volume."
                },
                # Card 3: Total Call OI
                "call_oi": {
                    "total_oi": tot_call_oi,
                    "oi_change": tot_call_oi_chg,
                    "oi_change_pct": tot_call_oi_chg_pct,
                    "highest_oi_strike": max_call_oi_strike,
                    "highest_oi_value": max_call_oi,
                    "highest_oi_change_strike": max_call_oi_chg_strike,
                    "highest_oi_change_value": max_call_oi_chg
                },
                # Card 4: Total Put OI
                "put_oi": {
                    "total_oi": tot_put_oi,
                    "oi_change": tot_put_oi_chg,
                    "oi_change_pct": tot_put_oi_chg_pct,
                    "highest_oi_strike": max_put_oi_strike,
                    "highest_oi_value": max_put_oi,
                    "highest_oi_change_strike": max_put_oi_chg_strike,
                    "highest_oi_change_value": max_put_oi_chg
                },
                # Card 5: Underlying Price & VWAP
                "price_vwap": {
                    "spot_price": spot_price,
                    "spot_change": spot_change,
                    "spot_change_pct": spot_change_pct,
                    "index_vwap": None,
                    "index_vwap_label": "Index VWAP unavailable",
                    "futures_symbol": futures_symbol,
                    "futures_ltp": futures_ltp,
                    "futures_vwap": futures_vwap,
                    "futures_vwap_label": "NIFTY FUTURES VWAP",
                    "spot_vwap_diff": spot_vwap_diff,
                    "spot_vwap_diff_pct": spot_vwap_diff_pct
                },
                # Card 6: Market Bias & Combined Sentiment
                "market_bias": {
                    "bias": sentiment_data["sentiment_bias"],
                    "headline": sentiment_data["headline"],
                    "explanation": sentiment_data["explanation"],
                    "score": sentiment_data["score"],
                    "breakdown": sentiment_data["factors"]
                }
            },
            # SUPPORT & RESISTANCE CONCENTRATION ZONES
            "levels": {
                "support_1": max_put_oi_strike,
                "support_1_oi": max_put_oi,
                "resistance_1": max_call_oi_strike,
                "resistance_1_oi": max_call_oi,
                "support_addition_strike": max_put_oi_chg_strike,
                "resistance_addition_strike": max_call_oi_chg_strike,
                "atm_strike": atm_strike
            },
            # OPTION CHAIN STRIKES TABLE
            "strikes": table_rows
        }

    @classmethod
    def _evaluate_sentiment(
        cls,
        oi_pcr: Optional[float],
        volume_pcr: Optional[float],
        put_oi_change: int,
        call_oi_change: int,
        spot_price: float,
        futures_vwap: Optional[float],
        prev_oi_pcr: Optional[float],
        bullish_threshold: float = 1.05,
        bearish_threshold: float = 0.95
    ) -> Dict[str, Any]:
        """
        Transparent, deterministic rules-based market sentiment engine.
        Does not use an LLM. Returns verifiable score and factor breakdown.
        """
        score = 0.0
        factors = {}

        # 1. OI PCR Bias
        if oi_pcr is None:
            factors["oi_pcr_bias"] = "UNAVAILABLE"
        elif oi_pcr > bullish_threshold:
            factors["oi_pcr_bias"] = "BULLISH"
            score += 1.0
        elif oi_pcr < bearish_threshold:
            factors["oi_pcr_bias"] = "BEARISH"
            score -= 1.0
        else:
            factors["oi_pcr_bias"] = "NEUTRAL"

        # 2. Volume PCR Bias
        if volume_pcr is None:
            factors["volume_pcr_bias"] = "UNAVAILABLE"
        elif volume_pcr > 1.05:
            factors["volume_pcr_bias"] = "BULLISH"
            score += 1.0
        elif volume_pcr < 0.95:
            factors["volume_pcr_bias"] = "BEARISH"
            score -= 1.0
        else:
            factors["volume_pcr_bias"] = "NEUTRAL"

        # 3. OI Addition Bias (Put Writing vs Call Writing)
        if put_oi_change > 0 and call_oi_change > 0:
            if put_oi_change > call_oi_change * 1.15:
                factors["oi_addition_bias"] = "BULLISH"
                score += 1.0
            elif call_oi_change > put_oi_change * 1.15:
                factors["oi_addition_bias"] = "BEARISH"
                score -= 1.0
            else:
                factors["oi_addition_bias"] = "NEUTRAL"
        elif put_oi_change > 0 and call_oi_change <= 0:
            factors["oi_addition_bias"] = "BULLISH"
            score += 1.0
        elif call_oi_change > 0 and put_oi_change <= 0:
            factors["oi_addition_bias"] = "BEARISH"
            score -= 1.0
        else:
            factors["oi_addition_bias"] = "NEUTRAL"

        # 4. Spot Price vs Futures VWAP
        if futures_vwap and futures_vwap > 0:
            if spot_price > futures_vwap + 5:
                factors["price_vwap_bias"] = "BULLISH"
                score += 1.0
            elif spot_price < futures_vwap - 5:
                factors["price_vwap_bias"] = "BEARISH"
                score -= 1.0
            else:
                factors["price_vwap_bias"] = "NEUTRAL"
        else:
            factors["price_vwap_bias"] = "UNAVAILABLE"

        # 5. Intraday PCR Trend
        if prev_oi_pcr is not None and oi_pcr is not None:
            diff = oi_pcr - prev_oi_pcr
            if diff > 0.02:
                factors["pcr_trend"] = "RISING"
                score += 0.5
            elif diff < -0.02:
                factors["pcr_trend"] = "FALLING"
                score -= 0.5
            else:
                factors["pcr_trend"] = "STABLE"
        else:
            factors["pcr_trend"] = "STABLE"

        # Combined Decision Logic
        oi_bias = factors.get("oi_pcr_bias")
        price_bias = factors.get("price_vwap_bias")
        vol_bias = factors.get("volume_pcr_bias")

        if oi_bias == "BULLISH" and price_bias == "BEARISH":
            bias = "CONFLICTING"
            headline = "Conflicting Signals"
            explanation = "OI positioning is bullish (high Put writing), but underlying price trades below Futures VWAP."
        elif oi_bias == "BEARISH" and price_bias == "BULLISH":
            bias = "CONFLICTING"
            headline = "Conflicting Signals"
            explanation = "OI positioning is bearish (high Call writing), but underlying price trades above Futures VWAP."
        elif oi_bias != "UNAVAILABLE" and vol_bias != "UNAVAILABLE" and oi_bias != "NEUTRAL" and vol_bias != "NEUTRAL" and oi_bias != vol_bias:
            bias = "CONFLICTING"
            headline = "Mixed Volume & OI"
            explanation = f"OI PCR indicates {oi_bias} positioning, while Volume PCR indicates {vol_bias} activity."
        elif score >= 2.0:
            bias = "BULLISH"
            headline = "Bullish Alignment"
            explanation = "Positive confluence across Put writing, PCR ratio, and intraday price structure."
        elif score <= -2.0:
            bias = "BEARISH"
            headline = "Bearish Alignment"
            explanation = "Heavy Call writing, bearish PCR ratio, and price context pointing downward."
        elif oi_bias == "UNAVAILABLE":
            bias = "INSUFFICIENT_DATA"
            headline = "Insufficient Data"
            explanation = "Market feed or option chain fields incomplete to determine conclusive positioning."
        else:
            bias = "NEUTRAL"
            headline = "Neutral / Balanced"
            explanation = "Options open interest and volume evenly matched across strikes around ATM."

        return {
            "sentiment_bias": bias,
            "headline": headline,
            "explanation": explanation,
            "score": round(score, 2),
            "factors": factors
        }

    @classmethod
    async def _get_latest_snapshot(cls, underlying: str, expiry: str, strike_range: int) -> Optional[PCRSnapshot]:
        """Fetch the most recent snapshot for the same contract."""
        async with AsyncSessionLocal() as session:
            stmt = select(PCRSnapshot).where(
                PCRSnapshot.underlying == underlying,
                PCRSnapshot.expiry == expiry,
                PCRSnapshot.strike_range == strike_range
            ).order_by(PCRSnapshot.id.desc()).limit(1)
            res = await session.execute(stmt)
            return res.scalar_one_or_none()

    @classmethod
    async def _save_snapshot(
        cls,
        underlying: str,
        expiry: str,
        strike_range: int,
        timestamp: datetime,
        timestamp_ist: str,
        trading_date: str,
        atm_strike: float,
        spot_price: float,
        total_call_oi: int,
        total_put_oi: int,
        oi_pcr: Optional[float],
        total_call_volume: int,
        total_put_volume: int,
        volume_pcr: Optional[float],
        call_oi_change: int,
        put_oi_change: int,
        underlying_vwap: Optional[float],
        futures_vwap: Optional[float],
        futures_symbol: Optional[str],
        sentiment: str,
        sentiment_score: float,
        data_status: str
    ):
        """Save a snapshot record, avoiding duplicates within the same minute."""
        async with AsyncSessionLocal() as session:
            # Check if record for this minute already exists
            stmt = select(PCRSnapshot).where(
                PCRSnapshot.underlying == underlying,
                PCRSnapshot.expiry == expiry,
                PCRSnapshot.strike_range == strike_range,
                PCRSnapshot.timestamp_ist == timestamp_ist
            ).limit(1)
            res = await session.execute(stmt)
            existing = res.scalar_one_or_none()

            if existing:
                # Update latest values for this minute
                existing.spot_price = spot_price
                existing.total_call_oi = total_call_oi
                existing.total_put_oi = total_put_oi
                existing.oi_pcr = oi_pcr
                existing.total_call_volume = total_call_volume
                existing.total_put_volume = total_put_volume
                existing.volume_pcr = volume_pcr
                existing.call_oi_change = call_oi_change
                existing.put_oi_change = put_oi_change
                existing.futures_vwap = futures_vwap
                existing.sentiment = sentiment
                existing.sentiment_score = sentiment_score
                existing.data_status = data_status
            else:
                snap = PCRSnapshot(
                    underlying=underlying,
                    expiry=expiry,
                    strike_range=strike_range,
                    timestamp=timestamp,
                    timestamp_ist=timestamp_ist,
                    trading_date=trading_date,
                    atm_strike=atm_strike,
                    spot_price=spot_price,
                    total_call_oi=total_call_oi,
                    total_put_oi=total_put_oi,
                    oi_pcr=oi_pcr,
                    total_call_volume=total_call_volume,
                    total_put_volume=total_put_volume,
                    volume_pcr=volume_pcr,
                    call_oi_change=call_oi_change,
                    put_oi_change=put_oi_change,
                    underlying_vwap=underlying_vwap,
                    futures_vwap=futures_vwap,
                    futures_symbol=futures_symbol,
                    sentiment=sentiment,
                    sentiment_score=sentiment_score,
                    data_status=data_status
                )
                session.add(snap)
            await session.commit()

    @classmethod
    async def get_history(
        cls,
        underlying: str = "NIFTY",
        trading_date: Optional[str] = None,
        strike_range: int = 10
    ) -> List[Dict[str, Any]]:
        """Retrieve 1-minute historical intraday PCR time series for chart."""
        u = normalize_underlying(underlying)
        if not trading_date:
            now_ist = datetime.now(timezone.utc).astimezone(IST)
            trading_date = now_ist.strftime("%Y-%m-%d")

        async with AsyncSessionLocal() as session:
            stmt = select(PCRSnapshot).where(
                PCRSnapshot.underlying == u,
                PCRSnapshot.trading_date == trading_date,
                PCRSnapshot.strike_range == strike_range
            ).order_by(PCRSnapshot.timestamp.asc())
            res = await session.execute(stmt)
            rows = res.scalars().all()

            # If no rows for specific strike range, fallback to any range for that date
            if not rows:
                stmt_fallback = select(PCRSnapshot).where(
                    PCRSnapshot.underlying == u,
                    PCRSnapshot.trading_date == trading_date
                ).order_by(PCRSnapshot.timestamp.asc())
                res_fallback = await session.execute(stmt_fallback)
                rows = res_fallback.scalars().all()

            return [
                {
                    "timestamp": int(r.timestamp.timestamp()),
                    "time_ist": r.timestamp_ist,
                    "spot_price": r.spot_price,
                    "oi_pcr": r.oi_pcr,
                    "volume_pcr": r.volume_pcr,
                    "futures_vwap": r.futures_vwap,
                    "total_call_oi": r.total_call_oi,
                    "total_put_oi": r.total_put_oi,
                    "total_call_volume": r.total_call_volume,
                    "total_put_volume": r.total_put_volume,
                    "sentiment": r.sentiment
                }
                for r in rows
            ]

    @classmethod
    async def get_available_dates(cls, underlying: str = "NIFTY") -> List[str]:
        """Return distinct trading dates that have saved PCR snapshots."""
        u = normalize_underlying(underlying)
        async with AsyncSessionLocal() as session:
            stmt = select(PCRSnapshot.trading_date).distinct().where(
                PCRSnapshot.underlying == u
            ).order_by(PCRSnapshot.trading_date.desc()).limit(30)
            res = await session.execute(stmt)
            dates = [r[0] for r in res.all() if r[0]]
            today_str = datetime.now(timezone.utc).astimezone(IST).strftime("%Y-%m-%d")
            if today_str not in dates:
                dates.insert(0, today_str)
            return dates
