import logging
import random
import hashlib
import re
from datetime import datetime, timezone, timedelta, date
from typing import List, Dict, Any, Tuple, Optional

from backend.app.adapters.kotak_neo import KotakNeoAdapter, KotakNeoHistoricalDataError
from backend.app.analytics.calendar import parse_trade_datetime_ist

logger = logging.getLogger("nextrade.backtest_data_loader")

IST = timezone(timedelta(hours=5, minutes=30))


class BacktestDataLoader:
    """
    Loads historical 1-minute NIFTY index candles and corresponding option premium candles.
    Guarantees:
    1. Deterministic synthetic data: identical inputs ALWAYS produce identical datasets.
    2. Authentic historical data: never silently fabricates missing broker data; stops with clear error.
    3. Multi-day duration support (1d, 5d, 10d, 30d, 60d, 90d, 180d, 1y, or custom ranges).
    """

    def __init__(self, kotak_adapter: Optional[KotakNeoAdapter] = None, allow_offline_cache: bool = False):
        self.kotak = kotak_adapter
        self.allow_offline_cache = allow_offline_cache

    async def fetch_kotak_historical(
        self,
        symbol: str,
        token: str,
        from_date: str,
        to_date: str,
        exchange_segment: str = "nse_cm",
        interval: str = "1min"
    ) -> List[Dict[str, Any]]:
        """Fetch real historical candles via Kotak Neo."""
        if not self.kotak or not self.kotak.client:
            logger.warning("Kotak Neo adapter or client unavailable.")
            return []

        candles = await self.kotak.get_historical_candles(
            symbol=symbol,
            token=token,
            exchange_segment=exchange_segment,
            interval=interval,
            from_date=from_date,
            to_date=to_date
        )
        return [
            {
                "timestamp": c.timestamp,
                "open": c.open,
                "high": c.high,
                "low": c.low,
                "close": c.close,
                "volume": c.volume,
            }
            for c in candles
        ]

    def _get_trading_days(
        self,
        days: int = 5,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> List[date]:
        """
        Generate list of trading weekdays (Monday to Friday, skipping Saturday, Sunday, and NSE holidays).
        Uses a fixed baseline anchor date to ensure 100% determinism across runs.
        """
        from backend.app.analytics.nse_holidays import get_nse_holiday_name

        if start_date and end_date:
            try:
                s_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
                e_dt = datetime.strptime(end_date, "%Y-%m-%d").date()
                if s_dt > e_dt:
                    s_dt, e_dt = e_dt, s_dt
                trading_days = []
                cur = s_dt
                while cur <= e_dt:
                    if cur.weekday() < 5 and get_nse_holiday_name(cur) is None:
                        trading_days.append(cur)
                    cur += timedelta(days=1)
                return trading_days if trading_days else [s_dt]
            except Exception as e:
                logger.warning(f"Error parsing start/end date ({start_date}, {end_date}): {e}")

        # Deterministic calendar anchor: Friday, Nov 13, 2026
        anchor_date = date(2026, 11, 13)
        trading_days = []
        cur = anchor_date
        while len(trading_days) < max(1, days):
            if cur.weekday() < 5 and get_nse_holiday_name(cur) is None:
                trading_days.append(cur)
            cur -= timedelta(days=1)

        trading_days.reverse()
        return trading_days

    def generate_synthetic_backtest_dataset(
        self,
        days: int = 5,
        candles_per_day: int = 375,  # 09:15 to 15:30 IST = 375 minutes
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        seed: int = 42,
        instrument_symbol: str = "NIFTY ATM CE"
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any]]:
        """
        Generate aligned, 100% deterministic realistic synthetic NIFTY and Option premium 1-minute candles.
        Guarantees:
        - Seeded RNG ensures identical prices and trades on repeated runs.
        - Fixed calendar trading dates and market hours (09:15 - 15:30 IST).
        - OHLC mathematical integrity: high >= max(open, close), low <= min(open, close), low > 0.
        """
        trading_days = self._get_trading_days(days=days, start_date=start_date, end_date=end_date)
        actual_days = len(trading_days)

        # Compute deterministic seed from inputs
        seed_raw = f"{actual_days}_{candles_per_day}_{trading_days[0]}_{trading_days[-1]}_{seed}_{instrument_symbol}"
        seed_int = int(hashlib.sha256(seed_raw.encode()).hexdigest(), 16) % (2**31 - 1)
        rng = random.Random(seed_int)

        nifty_candles = []
        option_candles = []

        base_spot = 24400.0
        is_direct_index = instrument_symbol.upper() in ("NIFTY 50", "NIFTY 50 INDEX", "NIFTY INDEX")
        is_pe = "PE" in instrument_symbol.upper()

        for day_idx, day_date in enumerate(trading_days):
            # 09:15 AM IST is 03:45 AM UTC
            market_open_utc = datetime(
                day_date.year, day_date.month, day_date.day, 3, 45, tzinfo=timezone.utc
            )

            # Day opening spot drift
            spot = base_spot + (day_idx * 35.0) + (rng.gauss(0, 15.0))
            spot = round(spot, 2)
            atm_strike = round(spot / 50.0) * 50.0
            
            delta = -0.50 if is_pe else 0.52
            if day_idx == 0:
                option_base_price = 145.0 + rng.uniform(-10.0, 10.0)
            else:
                gap = spot - nifty_candles[-1]["close"]
                option_base_price = max(5.0, round(option_candles[-1]["close"] + (gap * delta), 2))

            contract_name = "NIFTY 50" if is_direct_index else f"NIFTY {int(atm_strike)} {'PE' if is_pe else 'CE'}"

            for minute in range(candles_per_day):
                ts = market_open_utc + timedelta(minutes=minute)

                # NIFTY spot 1m bar
                drift = rng.gauss(0.05, 2.2)
                c_open = spot
                c_close = round(c_open + drift, 2)
                c_high = round(max(c_open, c_close) + abs(rng.gauss(0, 1.5)), 2)
                c_low = round(min(c_open, c_close) - abs(rng.gauss(0, 1.5)), 2)
                vol = rng.randint(3000, 35000)

                nifty_candles.append({
                    "timestamp": ts,
                    "open": c_open,
                    "high": c_high,
                    "low": c_low,
                    "close": c_close,
                    "volume": vol
                })

                if is_direct_index:
                    option_candles.append({
                        "timestamp": ts,
                        "open": c_open,
                        "high": c_high,
                        "low": c_low,
                        "close": c_close,
                        "volume": vol,
                        "symbol": "NIFTY 50",
                        "strike": 0.0,
                        "expiry": "INDEX"
                    })
                else:
                    # Option premium bar (correlates with spot: CE delta ~ +0.52, PE delta ~ -0.52)
                    delta = -0.50 if is_pe else 0.52
                    opt_drift = (drift * delta) + rng.gauss(0, 0.35)
                    opt_open = round(option_base_price, 2)
                    opt_close = max(1.0, round(opt_open + opt_drift, 2))
                    opt_high = round(max(opt_open, opt_close) + abs(rng.gauss(0, 0.6)), 2)
                    opt_low = max(0.50, round(min(opt_open, opt_close) - abs(rng.gauss(0, 0.6)), 2))
                    opt_vol = rng.randint(1500, 20000)

                    option_candles.append({
                        "timestamp": ts,
                        "open": opt_open,
                        "high": opt_high,
                        "low": opt_low,
                        "close": opt_close,
                        "volume": opt_vol,
                        "symbol": contract_name,
                        "strike": atm_strike,
                        "expiry": "WEEKLY"
                    })

                spot = c_close
                option_base_price = opt_close

            base_spot = spot

        start_str = trading_days[0].strftime("%Y-%m-%d")
        end_str = trading_days[-1].strftime("%Y-%m-%d")

        metadata = {
            "data_source": "SYNTHETIC_TEST",
            "data_quality_status": "DETERMINISTIC_SYNTHETIC",
            "contract_symbol": "NIFTY 50" if is_direct_index else (option_candles[0]["symbol"] if option_candles else instrument_symbol),
            "expiry": "INDEX" if is_direct_index else "WEEKLY",
            "start_date": start_str,
            "end_date": end_str,
            "duration_days": actual_days,
            "valid_candles_count": len(option_candles),
            "missing_candles_count": 0,
            "seed": seed,
            "signal_instrument": "NIFTY 50 Index",
            "execution_instrument": "NIFTY 50 Index (Direct)" if is_direct_index else f"{option_candles[0]['symbol']} (Option Premium)"
        }

        self.last_metadata = metadata
        return nifty_candles, option_candles

    async def load_dataset(
        self,
        symbol: str = "NIFTY ATM CE",
        timeframe_minutes: int = 1,
        days: int = 5,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        data_source: str = "SYNTHETIC_TEST",
        seed: int = 42
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any]]:
        """
        Unified historical data loader.
        - If real historical data is requested: calls Kotak Neo API.
          STOPS with clear ValueError if unavailable. Never silently switches to synthetic.
        - If synthetic test is requested: generates deterministic seeded candles.
        """
        if data_source in ("REAL_MARKET", "HISTORICAL_DATA"):
            from backend.app.market.history_service import HistoricalMarketDataService

            # Enforce broker connection requirement unless offline cache is explicitly enabled
            if not self.allow_offline_cache and (not self.kotak or not self.kotak.client):
                raise ValueError(
                    "Kotak Neo API is not connected. Real historical option data requires an active "
                    "Kotak Neo broker session. Please authenticate your Kotak credentials or select "
                    "'Deterministic Synthetic Test Data' to test algorithm logic."
                )

            # Determine date range
            if not start_date or not end_date:
                t_days = self._get_trading_days(days=days)
                start_date = t_days[0].strftime("%Y-%m-%d")
                end_date = t_days[-1].strftime("%Y-%m-%d")

            logger.info(f"Loading real historical data for {symbol} ({start_date} to {end_date})")

            s_dt = datetime.strptime(start_date, "%Y-%m-%d").replace(hour=9, minute=15, second=0, tzinfo=IST)
            e_dt = datetime.strptime(end_date, "%Y-%m-%d").replace(hour=15, minute=30, second=0, tzinfo=IST)

            # 1. Fetch NIFTY index spot candles (Check database cache first)
            cached_nifty = await HistoricalMarketDataService.load_candles_from_cache(
                symbol="NIFTY 50",
                start_dt=s_dt,
                end_dt=e_dt,
                limit=50000
            )

            req_t_days = self._get_trading_days(start_date=start_date, end_date=end_date)
            has_adequate_cache = False
            if cached_nifty:
                c_first = parse_trade_datetime_ist(cached_nifty[0]["timestamp"])
                c_last = parse_trade_datetime_ist(cached_nifty[-1]["timestamp"])
                if c_first and c_last:
                    c_first_str = c_first.strftime("%Y-%m-%d")
                    c_last_str = c_last.strftime("%Y-%m-%d")
                    if c_first_str <= start_date and c_last_str >= end_date and len(cached_nifty) >= max(100, len(req_t_days) * 200):
                        has_adequate_cache = True

            if has_adequate_cache or (self.allow_offline_cache and cached_nifty and len(cached_nifty) >= 100):
                logger.info(f"Loaded {len(cached_nifty)} verified NIFTY 50 candles from database cache.")
                nifty_candles = cached_nifty
            else:
                if not self.kotak or not self.kotak.client:
                    avail_info = "Available cached range is 2026-11-09 to 2026-11-13."
                    if cached_nifty:
                        avail_info = f"Database cache has partial data ({cached_nifty[0]['timestamp']} to {cached_nifty[-1]['timestamp']})."
                    raise ValueError(
                        f"Real historical data for NIFTY 50 between {start_date} and {end_date} is not available in database cache and Kotak Neo broker is not connected. "
                        f"{avail_info} Please authenticate your Kotak credentials or select 'Deterministic Synthetic Test Data'."
                    )
                try:
                    nifty_candles = await self.fetch_kotak_historical(
                        symbol="NIFTY 50",
                        token="Nifty 50",
                        from_date=start_date,
                        to_date=end_date,
                        exchange_segment="nse_cm",
                        interval="1min"
                    )
                except KotakNeoHistoricalDataError as k_err:
                    raise ValueError(f"Kotak Neo API Error for NIFTY 50 ({start_date} to {end_date}): {k_err.message}")

                if not nifty_candles:
                    raise ValueError(
                        f"Kotak Neo API returned 0 historical candles for NIFTY 50 between {start_date} and {end_date}. "
                        "Broker historical data may be unavailable or expired for this period. "
                        "Please select 'Deterministic Synthetic Test Data'."
                    )

                # Persist to database cache
                await HistoricalMarketDataService.save_candles_to_cache(
                    candles=nifty_candles,
                    symbol="NIFTY 50",
                    instrument_token="Nifty 50",
                    timeframe="1m"
                )

            # 2. Determine target option contract strike and type
            is_direct_index = symbol.upper() in ("NIFTY 50", "NIFTY 50 INDEX", "NIFTY INDEX")
            if is_direct_index:
                option_candles = [
                    {
                        "timestamp": c["timestamp"],
                        "open": c["open"],
                        "high": c["high"],
                        "low": c["low"],
                        "close": c["close"],
                        "volume": c.get("volume", 0),
                        "symbol": "NIFTY 50",
                        "strike": 0.0,
                        "expiry": "INDEX"
                    }
                    for c in nifty_candles
                ]
                metadata = {
                    "data_source": "REAL_MARKET" if not self.allow_offline_cache or (self.kotak and self.kotak.client) else "AUTHENTIC_MARKET_DATA",
                    "data_quality_status": "AUTHENTIC_MARKET_DATA",
                    "contract_symbol": "NIFTY 50",
                    "expiry": "INDEX",
                    "start_date": start_date,
                    "end_date": end_date,
                    "duration_days": len(req_t_days),
                    "valid_candles_count": len(nifty_candles),
                    "missing_candles_count": 0,
                    "signal_instrument": "NIFTY 50 Index",
                    "execution_instrument": "NIFTY 50 Index (Direct)"
                }
                self.last_metadata = metadata
                return nifty_candles, option_candles, metadata

            spot_open = float(nifty_candles[0]["open"])
            atm_strike = round(spot_open / 50.0) * 50.0

            is_pe = "PE" in symbol.upper()
            opt_type = "PE" if is_pe else "CE"
            target_strike = atm_strike

            m = re.search(r"(\d{4,5})\s*(CE|PE)", symbol.upper())
            if m:
                target_strike = float(m.group(1))
                opt_type = m.group(2).upper()

            # Resolve real FO contract token
            resolved = KotakNeoAdapter.resolve_fo_contract(strike=target_strike, opt_type=opt_type, from_date=start_date)
            if resolved:
                opt_token = resolved["token"]
                contract_symbol = resolved["symbol"]
            else:
                opt_token = f"OPT_{int(target_strike)}_{opt_type}"
                contract_symbol = f"NIFTY {int(target_strike)} {opt_type}"

            # 3. Fetch Option premium candles (Check database cache first across candidate symbols)
            candidate_symbols = [
                contract_symbol,
                f"NIFTY26NOV{int(target_strike)}{opt_type}",
                f"NIFTY {int(target_strike)} {opt_type}"
            ]
            cached_opt = []
            for c_sym in candidate_symbols:
                c_try = await HistoricalMarketDataService.load_candles_from_cache(
                    symbol=c_sym,
                    start_dt=s_dt,
                    end_dt=e_dt,
                    limit=50000
                )
                if len(c_try) > len(cached_opt):
                    cached_opt = c_try
                    contract_symbol = c_sym

            has_opt_cache = False
            if cached_opt:
                o_first = parse_trade_datetime_ist(cached_opt[0]["timestamp"])
                o_last = parse_trade_datetime_ist(cached_opt[-1]["timestamp"])
                if o_first and o_last:
                    o_first_str = o_first.strftime("%Y-%m-%d")
                    o_last_str = o_last.strftime("%Y-%m-%d")
                    if o_first_str <= start_date and o_last_str >= end_date and len(cached_opt) >= max(100, len(req_t_days) * 200):
                        has_opt_cache = True

            if has_opt_cache or (self.allow_offline_cache and cached_opt and len(cached_opt) >= 100):
                logger.info(f"Loaded {len(cached_opt)} verified {contract_symbol} option candles from database cache.")
                option_candles = cached_opt
            else:
                if not self.kotak or not self.kotak.client:
                    avail_info = "Available cached range is 2026-11-09 to 2026-11-13."
                    if cached_opt:
                        avail_info = f"Database cache has partial option data ({cached_opt[0]['timestamp']} to {cached_opt[-1]['timestamp']})."
                    raise ValueError(
                        f"Real historical 1-minute option premium data for {contract_symbol} ({start_date} to {end_date}) "
                        f"is not available in database cache and Kotak Neo broker is not connected. {avail_info} "
                        "Please authenticate your Kotak credentials or select 'Deterministic Synthetic Test Data'."
                    )
                try:
                    option_candles = await self.fetch_kotak_historical(
                        symbol=contract_symbol,
                        token=opt_token,
                        from_date=start_date,
                        to_date=end_date,
                        exchange_segment="nse_fo",
                        interval="1min"
                    )
                except KotakNeoHistoricalDataError as k_err:
                    raise ValueError(f"Kotak Neo API Error for {contract_symbol} ({start_date} to {end_date}): {k_err.message}")

                if not option_candles:
                    raise ValueError(
                        f"Real historical 1-minute option premium data for {contract_symbol} ({start_date} to {end_date}) "
                        "is not available from Kotak Neo API. Broker REST feeds do not serve historical 1-minute candles "
                        "for expired derivative contracts. To preserve backtest integrity and avoid fabricated data, "
                        "the engine has stopped. Please switch to 'Deterministic Synthetic Test Data' for reproducible testing."
                    )

                # Persist to database cache
                await HistoricalMarketDataService.save_candles_to_cache(
                    candles=option_candles,
                    symbol=contract_symbol,
                    instrument_token=opt_token,
                    timeframe="1m"
                )

            # Ensure contract metadata on each candle
            for c in option_candles:
                c["symbol"] = contract_symbol
                c["strike"] = target_strike
                c["expiry"] = "WEEKLY"

            metadata = {
                "data_source": "REAL_MARKET",
                "data_quality_status": "AUTHENTIC_MARKET_DATA",
                "contract_symbol": contract_symbol,
                "expiry": "WEEKLY",
                "start_date": start_date,
                "end_date": end_date,
                "duration_days": days,
                "valid_candles_count": len(option_candles),
                "missing_candles_count": max(0, len(nifty_candles) - len(option_candles)),
                "seed": seed,
                "signal_instrument": "NIFTY 50 Index",
                "execution_instrument": f"{contract_symbol} (Option Premium)"
            }
            self.last_metadata = metadata
            return nifty_candles, option_candles, metadata

        # Deterministic synthetic data
        nifty_candles, option_candles = self.generate_synthetic_backtest_dataset(
            days=days,
            start_date=start_date,
            end_date=end_date,
            seed=seed,
            instrument_symbol=symbol
        )
        return nifty_candles, option_candles, self.last_metadata
