import asyncio
import logging
import math
import random
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional, Callable, Any

from backend.app.adapters.base import BaseMarketDataAdapter, MarketTickData, CandleData

logger = logging.getLogger("nextrade.synthetic_feed")


class SyntheticMarketFeed(BaseMarketDataAdapter):
    """
    Realistic Synthetic Market Data Generator for NIFTY Index & ATM CE Option Premiums.
    Used when Kotak Neo credentials are not provided or market is closed.
    Clearly labelled as DEMO / SYNTHETIC. Never represented as live broker feed.
    """

    def __init__(self, initial_nifty_price: float = 24500.0):
        super().__init__()
        self.is_connected = False
        self.is_demo = True
        self.nifty_price = initial_nifty_price
        self.nifty_token = "26000"
        self.nifty_symbol = "NIFTY 50"

        # Option state
        self.atm_strike = round(initial_nifty_price / 50.0) * 50.0
        self.option_symbol = f"NIFTY {int(self.atm_strike)} CE"
        self.option_token = f"OPT_{int(self.atm_strike)}_CE"
        self.option_premium = 145.0  # Base realistic ATM CE premium
        self.pe_premium = 135.0  # Base realistic ATM PE premium
        self.option_delta = 0.52

        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._trend = 0.05  # Slight upward drift
        self._volatility = 4.5  # Nifty 1-second price standard deviation

    def update_atm_strike(self, strike: float, symbol: Optional[str] = None, token: Optional[str] = None):
        """Update the tracked ATM CE contract."""
        self.atm_strike = strike
        self.option_symbol = symbol or f"NIFTY {int(strike)} CE"
        self.option_token = token or f"OPT_{int(strike)}_CE"
        # Reset base premium based on moneyness
        intrinsic = max(0.0, self.nifty_price - self.atm_strike)
        time_value = max(20.0, 130.0 - abs(self.nifty_price - self.atm_strike) * 0.15)
        self.option_premium = round(intrinsic + time_value, 2)
        logger.info(f"Synthetic feed updated ATM contract: {self.option_symbol} (strike: {strike}, premium: {self.option_premium})")

    async def start(self):
        """Start generating synthetic 1-second ticks."""
        self._running = True
        self.is_connected = True
        logger.info("Starting Synthetic Market Feed (DEMO MODE)...")
        if self.on_status_callback:
            self.on_status_callback("DEMO_CONNECTED", "Synthetic demo feed active (Kotak Neo simulated)")

        self._task = asyncio.create_task(self._generator_loop())

    async def _generator_loop(self):
        """Tick generation loop running every 1 second."""
        while self._running:
            try:
                now = datetime.now(timezone.utc)
                self.last_tick_time = now

                # 1. Update NIFTY spot price via geometric brownian motion with mean reversion
                shock = random.gauss(0, 1)
                delta_nifty = (self._trend * 0.1) + (self._volatility * shock)
                self.nifty_price = max(1000.0, round(self.nifty_price + delta_nifty, 2))

                # Bid/Ask spread for Nifty Index (Index usually has LTP, but simulate narrow spread)
                nifty_tick = MarketTickData(
                    instrument_token=self.nifty_token,
                    exchange_segment="nse_cm",
                    symbol=self.nifty_symbol,
                    last_price=self.nifty_price,
                    timestamp=now,
                    volume=int(random.randint(50, 400)),
                    open_interest=0,
                    bid=round(self.nifty_price - 0.25, 2),
                    ask=round(self.nifty_price + 0.25, 2),
                    is_index=True
                )

                # 2. Update ATM CE Option Premium based on Delta + slight volatility
                # CE price moves in same direction as underlying spot: delta * delta_nifty
                option_shock = random.gauss(0, 0.3)
                delta_option = (delta_nifty * self.option_delta) + option_shock
                self.option_premium = max(1.0, round(self.option_premium + delta_option, 2))

                option_spread = 0.20  # 20 paise bid-ask spread
                option_tick = MarketTickData(
                    instrument_token=self.option_token,
                    exchange_segment="nse_fo",
                    symbol=self.option_symbol,
                    last_price=self.option_premium,
                    timestamp=now,
                    volume=int(random.randint(100, 1500)),
                    open_interest=int(random.randint(50000, 120000)),
                    bid=round(self.option_premium - (option_spread / 2), 2),
                    ask=round(self.option_premium + (option_spread / 2), 2),
                    is_index=False
                )

                # 3. Update ATM PE Option Premium
                delta_pe = - (1.0 - self.option_delta)
                delta_pe_opt = (delta_nifty * delta_pe) + random.gauss(0, 0.3)
                self.pe_premium = max(2.0, round(self.pe_premium + delta_pe_opt, 2))
                pe_symbol = f"NIFTY {int(self.atm_strike)} PE"
                pe_token = f"OPT_{int(self.atm_strike)}_PE"
                pe_tick = MarketTickData(
                    instrument_token=pe_token,
                    exchange_segment="nse_fo",
                    symbol=pe_symbol,
                    last_price=self.pe_premium,
                    timestamp=now,
                    volume=int(random.randint(100, 1500)),
                    open_interest=int(random.randint(50000, 120000)),
                    bid=round(self.pe_premium - (option_spread / 2), 2),
                    ask=round(self.pe_premium + (option_spread / 2), 2),
                    is_index=False
                )

                if self.on_tick_callback:
                    self.on_tick_callback(nifty_tick)
                    self.on_tick_callback(option_tick)
                    self.on_tick_callback(pe_tick)

                    # Emit +-50 and +-100 adjacent strikes for Option Chain live testing
                    for offset in (-100, -50, 50, 100):
                        s = self.atm_strike + offset
                        ce_prem = max(2.0, round(self.option_premium - (offset * 0.45) + random.gauss(0, 0.2), 2))
                        pe_prem = max(2.0, round(self.pe_premium + (offset * 0.45) + random.gauss(0, 0.2), 2))
                        self.on_tick_callback(MarketTickData(
                            instrument_token=f"OPT_{int(s)}_CE",
                            exchange_segment="nse_fo",
                            symbol=f"NIFTY {int(s)} CE",
                            last_price=ce_prem,
                            timestamp=now,
                            volume=int(random.randint(50, 800)),
                            open_interest=int(random.randint(30000, 90000)),
                            bid=round(ce_prem - 0.10, 2),
                            ask=round(ce_prem + 0.10, 2),
                            is_index=False
                        ))
                        self.on_tick_callback(MarketTickData(
                            instrument_token=f"OPT_{int(s)}_PE",
                            exchange_segment="nse_fo",
                            symbol=f"NIFTY {int(s)} PE",
                            last_price=pe_prem,
                            timestamp=now,
                            volume=int(random.randint(50, 800)),
                            open_interest=int(random.randint(30000, 90000)),
                            bid=round(pe_prem - 0.10, 2),
                            ask=round(pe_prem + 0.10, 2),
                            is_index=False
                        ))

                await asyncio.sleep(1.0)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in synthetic tick generator: {e}", exc_info=True)
                await asyncio.sleep(1.0)

    async def stop(self):
        """Stop synthetic feed."""
        self._running = False
        self.is_connected = False
        if self._task:
            self._task.cancel()
        if self.on_status_callback:
            self.on_status_callback("DISCONNECTED", "Synthetic demo feed stopped")

    async def subscribe(self, tokens: List[Dict[str, str]], is_index: bool = False):
        """Subscription placeholder for synthetic feed."""
        logger.info(f"Synthetic feed subscribed to: {tokens}")

    async def unsubscribe(self, tokens: List[Dict[str, str]], is_index: bool = False):
        """Unsubscribe placeholder."""
        pass

    async def get_historical_candles(
        self,
        symbol: str,
        token: str,
        exchange_segment: str,
        interval: str,
        from_date: str,
        to_date: str,
        base_price: Optional[float] = None
    ) -> List[CandleData]:
        """
        Generate realistic historical 1-minute candles for testing and chart display.
        Uses completed 1-minute bars with realistic intraday trend and volatility.
        """
        candles = []
        is_index = "NIFTY" in symbol and "CE" not in symbol and "PE" not in symbol

        if base_price is None or base_price <= 0:
            base_price = 25220.0 if is_index else 150.0
        vol = 6.0 if is_index else 1.5

        now = datetime.now(timezone.utc)
        # Generate 120 completed 1-minute candles back in time
        start_time = now - timedelta(minutes=120)

        curr = base_price
        for i in range(120):
            c_time = start_time + timedelta(minutes=i)
            # Create a realistic bar
            c_open = curr
            drift = random.gauss(0.1, 1.0) * (vol * 0.4)
            c_close = round(c_open + drift, 2)
            c_high = round(max(c_open, c_close) + abs(random.gauss(0, vol * 0.5)), 2)
            c_low = round(min(c_open, c_close) - abs(random.gauss(0, vol * 0.5)), 2)
            volume = random.randint(1000, 15000)

            candles.append(CandleData(
                timestamp=c_time,
                open=c_open,
                high=c_high,
                low=c_low,
                close=c_close,
                volume=float(volume),
                complete=True
            ))
            curr = c_close

        return candles
