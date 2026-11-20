import asyncio
import io
import logging
import re
from datetime import datetime, timezone, timedelta, date
from typing import List, Dict, Any, Optional, Tuple

import pandas as pd
from neo_api_client import NeoAPI
from neo_api_client.utils import scrip_cache
from backend.app.adapters.base import BaseMarketDataAdapter, MarketTickData, CandleData
from backend.app.config import settings

logger = logging.getLogger("nextrade.kotak_neo")
IST = timezone(timedelta(hours=5, minutes=30))


import asyncio
import io
import logging
import re
from datetime import datetime, timezone, timedelta, date
from typing import List, Dict, Any, Optional, Tuple, Set

import pandas as pd
from neo_api_client import NeoAPI
from neo_api_client.utils import scrip_cache
from neo_api_client.websocket.feed import SFeedWebSocket, WsToken, SFeedScrip, SFeedIndex, SFeedMarketStatus
from backend.app.adapters.base import BaseMarketDataAdapter, MarketTickData, CandleData
from backend.app.config import settings

logger = logging.getLogger("nextrade.kotak_neo")
IST = timezone(timedelta(hours=5, minutes=30))


def is_market_hours() -> bool:
    """Return True if current time is within Indian equity market trading hours (Mon-Fri 09:15-15:30 IST)."""
    now_ist = datetime.now(timezone.utc).astimezone(IST)
    if now_ist.weekday() >= 5:
        return False
    time_str = now_ist.strftime("%H:%M")
    return "09:15" <= time_str <= "15:30"


class KotakNeoHistoricalDataError(Exception):
    """Raised when Kotak Neo API returns an explicit error or fault."""
    def __init__(self, message: str, status_code: int = 400, neosymbol: str = "", details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.neosymbol = neosymbol
        self.details = details or {}


class KotakNeoAdapter(BaseMarketDataAdapter):
    """
    Dedicated Kotak Neo Market Data Adapter using official neo_api_client SDK (v2.2.0+).
    Supports persistent SFeedWebSocket streaming, dynamic subscription of indices and FO contracts,
    comprehensive option chain multi-strike broadcasting, and connection health states.
    """

    def __init__(self):
        super().__init__()
        self.client: Optional[NeoAPI] = None
        self.is_connected = False
        self.is_demo = False
        self._running = False
        self._loop_task: Optional[asyncio.Task] = None
        self._ws: Optional[SFeedWebSocket] = None
        self._last_tick_time: Optional[datetime] = None
        self.latest_option_chain_data: Optional[Dict[str, Any]] = None
        self.connection_state: str = "DISCONNECTED"
        self.connection_message: str = "Initialized"
        self.subscribed_tokens: Set[Tuple[str, str]] = set()  # (exchange_segment, token)
        self.subscribed_symbols: Set[str] = set()

    def set_connection_state(self, state: str, message: str = ""):
        """Update connection state and notify status callback."""
        self.connection_state = state
        self.connection_message = message or state
        self.is_connected = (state in ("CONNECTED", "LIVE_STREAMING"))
        if self.on_status_callback:
            try:
                self.on_status_callback(state, self.connection_message)
            except Exception as e:
                logger.error(f"Error in on_status_callback: {e}")

    def initialize_client(self) -> bool:
        """Initialize NeoAPI client with Kotak consumer key and attempt session auth if credentials provided."""
        if not settings.kotak_consumer_key:
            logger.warning("Kotak consumer key missing; live connection cannot initialize.")
            self.set_connection_state("DISCONNECTED", "Kotak consumer key missing")
            return False

        try:
            self.client = NeoAPI(
                consumer_key=settings.kotak_consumer_key,
                environment=settings.kotak_environment,
                access_token=settings.kotak_access_token if settings.kotak_access_token else None
            )
            logger.info("Kotak Neo client initialized successfully with consumer key.")

            # Attempt automatic TOTP login if credentials are provided in settings
            if (
                settings.kotak_mobile_number and
                settings.kotak_ucc and
                settings.kotak_totp_key and
                settings.kotak_mpin
            ):
                try:
                    import pyotp
                    totp_val = pyotp.TOTP(settings.kotak_totp_key).now()
                    logger.info("Attempting automated Kotak Neo TOTP login...")
                    self.client.totp_login(
                        mobile_number=settings.kotak_mobile_number,
                        ucc=settings.kotak_ucc,
                        totp=totp_val
                    )
                    self.client.totp_validate(mpin=settings.kotak_mpin)
                    logger.info("Kotak Neo TOTP login and validation succeeded!")
                except Exception as auth_err:
                    logger.warning(f"Kotak Neo TOTP authentication skipped or failed: {auth_err}")

            return True
        except Exception as e:
            logger.error(f"Error initializing Kotak Neo client: {e}", exc_info=True)
            self.set_connection_state("DISCONNECTED", f"Client initialization failed: {e}")
            if self.on_error_callback:
                self.on_error_callback(f"Kotak Neo client initialization failed: {e}")
            return False

    async def start(self):
        """Start the live market data stream (SFeed WebSocket or REST multi-strike feed)."""
        self._running = True
        self.set_connection_state("CONNECTING", "Connecting to Kotak Neo feed...")

        if not self.client:
            success = self.initialize_client()
            if not success:
                logger.warning("Could not initialize Kotak client.")
                self.set_connection_state("DISCONNECTED", "Failed to initialize Kotak Neo client.")
                return

        # Start default subscriptions (Nifty 50)
        self.subscribed_tokens.add(("nse_cm", "26000"))
        self.subscribed_symbols.add("NIFTY 50")

        # Launch the unified feed orchestrator task
        self._loop_task = asyncio.create_task(self._feed_orchestrator_loop())

    async def _feed_orchestrator_loop(self):
        """
        Orchestrates feed connection:
        1. Tries persistent SFeedWebSocket if session credentials (edit_token/edit_sid) are valid.
        2. Falls back to multi-strike option chain polling if WebSocket cannot authenticate or drops.
        3. Monitors market session status (MARKET CLOSED outside 09:15-15:30 IST).
        """
        while self._running:
            # Check market session
            market_open = is_market_hours()
            if not market_open:
                # If after hours, update state to MARKET CLOSED
                self.set_connection_state("MARKET CLOSED", "Market session closed (09:15-15:30 IST weekdays)")

            # Check if WebSocket can be initialized
            can_use_ws = bool(
                self.client and
                getattr(self.client, "configuration", None) and
                getattr(self.client.configuration, "edit_token", None) and
                getattr(self.client.configuration, "edit_sid", None)
            )

            if can_use_ws and market_open:
                try:
                    logger.info("Attempting Kotak Neo SFeed WebSocket connection...")
                    self.set_connection_state("CONNECTING", "Establishing SFeed WebSocket...")
                    await self._run_sfeed_websocket()
                except asyncio.CancelledError:
                    break
                except Exception as ws_err:
                    logger.warning(f"SFeed WebSocket disconnected or error: {ws_err}. Reconnecting / falling back...")
                    self.set_connection_state("RECONNECTING", f"WebSocket reconnecting: {ws_err}")
                    await asyncio.sleep(2.0)
            else:
                # Run REST multi-strike option chain feed
                try:
                    await self._run_rest_multi_strike_tick()
                    # Sleep 1.0s between REST quotes during market hours, 3.0s outside market hours
                    sleep_dur = 1.0 if market_open else 3.0
                    await asyncio.sleep(sleep_dur)
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"Error in Kotak Neo REST feed tick: {e}", exc_info=True)
                    if not market_open:
                        self.set_connection_state("MARKET CLOSED", "Market session closed")
                    else:
                        self.set_connection_state("RECONNECTING", f"Feed error: {e}")
                    await asyncio.sleep(2.5)

    async def _run_sfeed_websocket(self):
        """Connects and consumes from Kotak Neo SFeedWebSocket."""
        if not self.client:
            return

        ws = self.client.create_websocket()
        self._ws = ws

        async with ws:
            self.set_connection_state("CONNECTED", "SFeed WebSocket Streaming Live")
            logger.info("Kotak Neo SFeed WebSocket connected successfully!")

            # Subscribe to initial tokens
            index_tokens = [WsToken(seg, tok) for seg, tok in self.subscribed_tokens if seg == "nse_cm"]
            scrip_tokens = [WsToken(seg, tok) for seg, tok in self.subscribed_tokens if seg != "nse_cm"]

            if index_tokens:
                await ws.subscribe_index(index_tokens)
            if scrip_tokens:
                await ws.subscribe_scrips(scrip_tokens)

            # Consume async iterator
            async for message in ws:
                if not self._running:
                    break
                now = datetime.now(timezone.utc)
                self._last_tick_time = now

                if isinstance(message, SFeedIndex):
                    ltp = float(message.last_traded_price)
                    if ltp > 0:
                        tick = MarketTickData(
                            instrument_token=str(message.instrument_token),
                            exchange_segment=message.exchange_segment or "nse_cm",
                            symbol=message.trading_symbol or "NIFTY 50",
                            last_price=ltp,
                            timestamp=now,
                            volume=0,
                            open_interest=0,
                            bid=round(ltp - 0.25, 2),
                            ask=round(ltp + 0.25, 2),
                            is_index=True
                        )
                        if self.on_tick_callback:
                            self.on_tick_callback(tick)

                elif isinstance(message, SFeedScrip):
                    ltp = float(message.last_traded_price)
                    if ltp > 0:
                        bid_p = float(message.buy[0].price) if message.buy and len(message.buy) > 0 else round(ltp - 0.10, 2)
                        ask_p = float(message.sell[0].price) if message.sell and len(message.sell) > 0 else round(ltp + 0.10, 2)
                        tick = MarketTickData(
                            instrument_token=str(message.instrument_token),
                            exchange_segment=message.exchange_segment or "nse_fo",
                            symbol=message.trading_symbol or f"TOKEN_{message.instrument_token}",
                            last_price=ltp,
                            timestamp=now,
                            volume=int(message.volume_traded_today or 0),
                            open_interest=int(message.open_interest or 0),
                            bid=bid_p,
                            ask=ask_p,
                            is_index=False
                        )
                        if self.on_tick_callback:
                            self.on_tick_callback(tick)

                elif isinstance(message, SFeedMarketStatus):
                    status_text = getattr(message, "status", "UNKNOWN")
                    logger.info(f"Kotak Neo Market Status update: {status_text}")

    async def _run_rest_multi_strike_tick(self):
        """
        Fetches option chain and emits ticks for:
        1. NIFTY 50 spot (is_index=True)
        2. ATM CE (primary active contract)
        3. All available CE and PE strikes in the returned chain (for Option Chain live updates)
        """
        if not self.client:
            return

        loop = asyncio.get_running_loop()
        oc = await loop.run_in_executor(
            None,
            lambda: self.client.option_chain(exchange="nse_fo", underlying="NIFTY", count=16)
        )

        if not oc or not isinstance(oc, dict) or "spot" not in oc:
            return

        self.latest_option_chain_data = oc
        now = datetime.now(timezone.utc)
        self._last_tick_time = now

        if is_market_hours():
            self.set_connection_state("CONNECTED", "Kotak Neo Live REST Streaming")
        else:
            self.set_connection_state("MARKET CLOSED", "Market session closed (Last settled prices)")

        # 1. Process NIFTY Spot Index
        spot_data = oc.get("spot", {})
        spot_ltp = float(spot_data.get("ltp", 0.0))
        if spot_ltp > 0:
            nifty_tick = MarketTickData(
                instrument_token="26000",
                exchange_segment="nse_cm",
                symbol="NIFTY 50",
                last_price=spot_ltp,
                timestamp=now,
                volume=1000,
                open_interest=0,
                bid=round(spot_ltp - 0.25, 2),
                ask=round(spot_ltp + 0.25, 2),
                is_index=True
            )
            if self.on_tick_callback:
                self.on_tick_callback(nifty_tick)

            # 2. Extract ATM strike and emit all CE strikes
            atm_strike = round(spot_ltp / 50.0) * 50.0
            calls = oc.get("call", [])
            for c in calls:
                inst = c.get("inst", {})
                quote = c.get("quote", {})
                oi_data = c.get("oi", {})
                ce_ltp = float(quote.get("ltp", 0.0))
                if ce_ltp <= 0:
                    continue
                strk = float(inst.get("strkPrc", 0))
                ce_symbol = inst.get("symbol", f"NIFTY {int(strk)} CE")
                ce_token = inst.get("neoSymbol", f"OPT_{int(strk)}_CE").replace("nse_fo|", "")

                ce_tick = MarketTickData(
                    instrument_token=ce_token,
                    exchange_segment="nse_fo",
                    symbol=ce_symbol,
                    last_price=ce_ltp,
                    timestamp=now,
                    volume=int(quote.get("vol", 1000) or 1000),
                    open_interest=int(oi_data.get("cur", 50000) or 50000),
                    bid=round(ce_ltp - 0.10, 2),
                    ask=round(ce_ltp + 0.10, 2),
                    is_index=False
                )
                if self.on_tick_callback:
                    self.on_tick_callback(ce_tick)

            # 3. Emit all PE strikes
            puts = oc.get("put", [])
            for p in puts:
                inst = p.get("inst", {})
                quote = p.get("quote", {})
                oi_data = p.get("oi", {})
                pe_ltp = float(quote.get("ltp", 0.0))
                if pe_ltp <= 0:
                    continue
                strk = float(inst.get("strkPrc", 0))
                pe_symbol = inst.get("symbol", f"NIFTY {int(strk)} PE")
                pe_token = inst.get("neoSymbol", f"OPT_{int(strk)}_PE").replace("nse_fo|", "")

                pe_tick = MarketTickData(
                    instrument_token=pe_token,
                    exchange_segment="nse_fo",
                    symbol=pe_symbol,
                    last_price=pe_ltp,
                    timestamp=now,
                    volume=int(quote.get("vol", 1000) or 1000),
                    open_interest=int(oi_data.get("cur", 50000) or 50000),
                    bid=round(pe_ltp - 0.10, 2),
                    ask=round(pe_ltp + 0.10, 2),
                    is_index=False
                )
                if self.on_tick_callback:
                    self.on_tick_callback(pe_tick)

    async def subscribe(self, tokens: List[Dict[str, str]], is_index: bool = False):
        """Add tokens to subscription set and register with SFeedWebSocket if connected."""
        ws_tokens = []
        for item in tokens:
            seg = item.get("segment", "nse_fo")
            tok = item.get("token", "")
            sym = item.get("symbol", "")
            if tok:
                self.subscribed_tokens.add((seg, tok))
                ws_tokens.append(WsToken(seg, tok))
            if sym:
                self.subscribed_symbols.add(sym)

        if self._ws and ws_tokens:
            try:
                if is_index:
                    await self._ws.subscribe_index(ws_tokens)
                else:
                    await self._ws.subscribe_scrips(ws_tokens)
            except Exception as e:
                logger.warning(f"Error subscribing scrips on live SFeed: {e}")

    async def unsubscribe(self, tokens: List[Dict[str, str]], is_index: bool = False):
        """Remove tokens from subscription set and unregister from SFeedWebSocket."""
        ws_tokens = []
        for item in tokens:
            seg = item.get("segment", "nse_fo")
            tok = item.get("token", "")
            sym = item.get("symbol", "")
            self.subscribed_tokens.discard((seg, tok))
            if sym:
                self.subscribed_symbols.discard(sym)
            if tok:
                ws_tokens.append(WsToken(seg, tok))

        if self._ws and ws_tokens:
            try:
                if is_index:
                    await self._ws.unsubscribe_index(ws_tokens)
                else:
                    await self._ws.unsubscribe_scrips(ws_tokens)
            except Exception as e:
                logger.warning(f"Error unsubscribing scrips on live SFeed: {e}")

    async def stop(self):
        """Graceful shutdown of Kotak Neo adapter."""
        self._running = False
        self.set_connection_state("DISCONNECTED", "Adapter stopped")
        if self._loop_task:
            self._loop_task.cancel()
        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None

    @classmethod
    def resolve_fo_contract(cls, symbol: str = "", strike: Optional[float] = None, opt_type: Optional[str] = None, from_date: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Look up contract in nse_fo scrip cache."""
        try:
            content = scrip_cache.read_csv('nse_fo')
            if not content:
                return None

            df = pd.read_csv(io.BytesIO(content), low_memory=False)

            # Parse strike & opt_type if not provided
            if strike is None or opt_type is None:
                m = re.search(r'(\d{4,5})\s*(CE|PE)', symbol.upper())
                if m:
                    strike = float(m.group(1))
                    opt_type = m.group(2)

            if strike is None or opt_type is None:
                return None

            target_strike = float(strike) * 100.0
            matches = df[
                (df['pSymbolName'] == 'NIFTY') &
                (df['pOptionType'] == opt_type.upper()) &
                (df['dStrikePrice;'] == target_strike)
            ].sort_values('pExpiryDate', ascending=True)

            if matches.empty:
                return None

            best = matches.iloc[0]
            return {
                "token": str(best['pSymbol']),
                "symbol": str(best['pTrdSymbol']),
                "strike": strike,
                "option_type": opt_type.upper(),
                "expiry": str(best['pExpiryDate'])
            }
        except Exception as e:
            logger.warning(f"Error resolving FO contract for {symbol}: {e}")
            return None

    @classmethod
    def resolve_neosymbol(cls, symbol: str, token: str, exchange_segment: str) -> str:
        """
        Resolve symbol & token into Kotak Neo's wire neosymbol format.
        Indices: nse_cm|Nifty 50, nse_cm|Nifty Bank, etc.
        Options: nse_fo|<numeric_token>.
        Equities: nse_cm|<numeric_token>.
        """
        sym_up = symbol.strip().upper() if symbol else ""
        tok_str = str(token).strip() if token is not None else ""

        # 1. Major Indices (require exact case-sensitive name in nse_cm)
        if sym_up in ("NIFTY 50", "NIFTY", "NIFTY_INDEX", "NIFTY 50 INDEX") or tok_str in ("26000", "Nifty 50", "NIFTY 50", "NIFTY"):
            return "nse_cm|Nifty 50"
        if sym_up in ("BANK NIFTY", "BANKNIFTY", "NIFTY BANK") or tok_str in ("26009", "BANKNIFTY", "Nifty Bank", "BANK NIFTY"):
            return "nse_cm|Nifty Bank"
        if sym_up in ("FIN NIFTY", "FINNIFTY", "NIFTY FIN SERVICE") or tok_str in ("26037", "FINNIFTY", "Nifty Fin Service", "FIN NIFTY"):
            return "nse_cm|Nifty Fin Service"
        if sym_up in ("MIDCPNIFTY", "NIFTY MID SELECT") or tok_str in ("26074", "MIDCPNIFTY", "Nifty Mid Select"):
            return "nse_cm|Nifty Mid Select"

        # 2. Options Segment (nse_fo)
        if exchange_segment == "nse_fo":
            if tok_str.isdigit():
                return f"nse_fo|{tok_str}"
            # If token is not numeric (e.g. OPT_25100_CE or symbol like NIFTY 25100 CE), resolve it
            resolved = cls.resolve_fo_contract(symbol=sym_up or tok_str)
            if resolved and resolved.get("token"):
                return f"nse_fo|{resolved['token']}"
            # Fallback if already contains nse_fo
            if tok_str.startswith("nse_fo|"):
                return tok_str
            return f"nse_fo|{tok_str}"

        # 3. Cash Segment (nse_cm)
        if exchange_segment == "nse_cm":
            if tok_str.isdigit():
                return f"nse_cm|{tok_str}"
            return f"nse_cm|{tok_str}"

        return f"{exchange_segment}|{tok_str}"

    @staticmethod
    def map_interval(interval: str) -> str:
        """Map application timeframes to Kotak Neo supported intervals: 1min, 3min, 5min, 10min, 15min, 30min, 60min, D, W"""
        norm = interval.strip().lower()
        mapping = {
            "1m": "1min", "1min": "1min",
            "3m": "3min", "3min": "3min",
            "5m": "5min", "5min": "5min",
            "10m": "10min", "10min": "10min",
            "15m": "15min", "15min": "15min",
            "30m": "30min", "30min": "30min",
            "60m": "60min", "1h": "60min", "60min": "60min",
            "1d": "D", "d": "D", "daily": "D", "day": "D",
            "1w": "W", "w": "W", "weekly": "W", "week": "W"
        }
        return mapping.get(norm, "1min")

    @staticmethod
    def chunk_date_range(from_date_str: str, to_date_str: str, max_days: int = 25) -> List[Tuple[str, str]]:
        """Split date range into chronological slices within Kotak Neo's limits (<= 30 days for 1min, <= 180 days for D)."""
        s_dt = datetime.strptime(from_date_str, "%Y-%m-%d").date()
        e_dt = datetime.strptime(to_date_str, "%Y-%m-%d").date()
        if s_dt > e_dt:
            s_dt, e_dt = e_dt, s_dt

        chunks = []
        cur = s_dt
        while cur <= e_dt:
            cur_end = min(e_dt, cur + timedelta(days=max_days - 1))
            chunks.append((cur.strftime("%Y-%m-%d"), cur_end.strftime("%Y-%m-%d")))
            cur = cur_end + timedelta(days=1)
        return chunks

    async def get_historical_candles(
        self,
        symbol: str,
        token: str,
        exchange_segment: str,
        interval: str,
        from_date: str,
        to_date: str
    ) -> List[CandleData]:
        """Fetch authentic historical candle data via Kotak Neo API."""
        if not self.client:
            success = self.initialize_client()
            if not success or not self.client:
                err_msg = "Kotak Neo client not initialized. Consumer key missing or invalid."
                logger.error(err_msg)
                raise KotakNeoHistoricalDataError(err_msg, status_code=401)

        neosymbol = self.resolve_neosymbol(symbol, token, exchange_segment)
        wire_interval = self.map_interval(interval)

        # Determine chunk size based on wire interval
        max_chunk_days = 150 if wire_interval in ("D", "W") else 25
        chunks = self.chunk_date_range(from_date, to_date, max_days=max_chunk_days)

        all_candles: List[CandleData] = []
        seen_timestamps = set()

        loop = asyncio.get_running_loop()

        for idx, (chunk_start, chunk_end) in enumerate(chunks):
            if idx > 0:
                # Throttle between chunks to respect Kotak Neo rate limits
                await asyncio.sleep(0.8)

            # Secure logging (no secrets or credentials)
            logger.info(
                f"Kotak Neo Historical Request [{idx+1}/{len(chunks)}]: neosymbol={neosymbol}, "
                f"interval={wire_interval}, range={chunk_start} to {chunk_end}, method=GET"
            )

            # Retry loop for rate limits (HTTP 429)
            max_retries = 2
            res = None
            for attempt in range(max_retries + 1):
                try:
                    res = await loop.run_in_executor(
                        None,
                        lambda cs=chunk_start, ce=chunk_end: self.client.historical_data(
                            neosymbol=neosymbol,
                            interval=wire_interval,
                            from_date=cs,
                            to_date=ce
                        )
                    )
                except Exception as req_ex:
                    logger.error(f"Kotak Neo historical_data network exception: {req_ex}")
                    if attempt < max_retries:
                        await asyncio.sleep(1.5 * (attempt + 1))
                        continue
                    raise KotakNeoHistoricalDataError(f"Kotak Neo connection failure: {req_ex}", status_code=500, neosymbol=neosymbol)

                # Check if rate limited
                if isinstance(res, dict) and (
                    res.get("code") == 429 or
                    "Rate limit exceeded" in str(res.get("error", "")) or
                    "too many request" in str(res.get("message", "")).lower()
                ):
                    logger.warning(f"Kotak Neo rate limited (attempt {attempt+1}/{max_retries+1}), backing off 2.0s...")
                    if attempt < max_retries:
                        await asyncio.sleep(2.0 * (attempt + 1))
                        continue
                    else:
                        raise KotakNeoHistoricalDataError(
                            "Kotak Neo rate limit exceeded (HTTP 429). Please retry in a few moments.",
                            status_code=429,
                            neosymbol=neosymbol
                        )
                break

            if not res or not isinstance(res, dict):
                logger.warning(f"Empty or non-dict response from Kotak historical_data: neosymbol={neosymbol}, chunk={chunk_start} to {chunk_end}")
                continue

            # Check for error responses
            if "fault" in res or "Fault" in res or "error" in res or "Error" in res or res.get("status") == "ERROR":
                fault_obj = res.get("fault") or res.get("Fault") or res.get("error") or res.get("Error")
                code = fault_obj.get("code") if isinstance(fault_obj, dict) else res.get("status_code", 400)
                msg = (fault_obj.get("message") or fault_obj.get("description")) if isinstance(fault_obj, dict) else str(fault_obj)
                logger.error(f"Kotak Neo Historical API Error: status_code={code}, message='{msg}', neosymbol={neosymbol}, interval={wire_interval}")
                raise KotakNeoHistoricalDataError(
                    f"Kotak Neo API Error [{code}]: {msg} (neosymbol={neosymbol})",
                    status_code=int(code) if str(code).isdigit() else 400,
                    neosymbol=neosymbol,
                    details=res
                )

            raw_candles = res.get("data") or res.get("candles") or res.get("result") or []
            if isinstance(raw_candles, dict):
                raw_candles = raw_candles.get("candles") or raw_candles.get("data") or []

            chunk_parsed_count = 0
            for item in raw_candles:
                try:
                    if isinstance(item, (list, tuple)) and len(item) >= 5:
                        raw_ts = item[0]
                        if isinstance(raw_ts, str):
                            dt = datetime.fromisoformat(raw_ts.replace("Z", "+00:00"))
                        elif isinstance(raw_ts, (int, float)):
                            dt = datetime.fromtimestamp(raw_ts, tz=timezone.utc)
                        else:
                            continue

                        o = float(item[1])
                        h_raw = float(item[2])
                        l_raw = float(item[3])
                        c = float(item[4])
                        v = float(item[5]) if len(item) > 5 else 0.0

                        # Enforce mathematical OHLC integrity
                        h = max(o, h_raw, c)
                        l = max(0.01, min(o, l_raw, c))

                        if o <= 0 or c <= 0:
                            continue

                        if dt not in seen_timestamps:
                            seen_timestamps.add(dt)
                            all_candles.append(CandleData(
                                timestamp=dt,
                                open=o,
                                high=h,
                                low=l,
                                close=c,
                                volume=v,
                                complete=True
                            ))
                            chunk_parsed_count += 1
                    elif isinstance(item, dict):
                        raw_ts = item.get("time") or item.get("timestamp") or item.get("datetime")
                        if isinstance(raw_ts, str):
                            dt = datetime.fromisoformat(raw_ts.replace("Z", "+00:00"))
                        elif isinstance(raw_ts, (int, float)):
                            dt = datetime.fromtimestamp(raw_ts, tz=timezone.utc)
                        else:
                            continue

                        o = float(item.get("open", 0.0))
                        h_raw = float(item.get("high", 0.0))
                        l_raw = float(item.get("low", 0.0))
                        c = float(item.get("close", 0.0))
                        v = float(item.get("volume", 0.0))

                        h = max(o, h_raw, c)
                        l = max(0.01, min(o, l_raw, c))

                        if o <= 0 or c <= 0:
                            continue

                        if dt not in seen_timestamps:
                            seen_timestamps.add(dt)
                            all_candles.append(CandleData(
                                timestamp=dt,
                                open=o,
                                high=h,
                                low=l,
                                close=c,
                                volume=v,
                                complete=True
                            ))
                            chunk_parsed_count += 1
                except Exception as parse_err:
                    logger.debug(f"Failed to parse candle item {item}: {parse_err}")
                    continue

            logger.info(f"Kotak Neo Historical Response [{idx+1}/{len(chunks)}]: candles_received={len(raw_candles)}, candles_parsed={chunk_parsed_count}")

        # Sort chronologically
        all_candles.sort(key=lambda c: c.timestamp)
        logger.info(f"Kotak Neo Historical Completed: total_valid_candles={len(all_candles)} for {neosymbol} ({from_date} to {to_date})")
        return all_candles


