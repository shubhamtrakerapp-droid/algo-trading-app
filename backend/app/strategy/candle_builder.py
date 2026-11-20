from datetime import datetime, timezone
from typing import Dict, List, Optional, Callable, Any
from backend.app.adapters.base import MarketTickData, CandleData


class CandleBuilder:
    """
    Aggregates raw market ticks into 1-minute OHLCV bars.
    Emits completed candles strictly when the 1-minute period concludes.
    """

    def __init__(self, on_candle_completed: Optional[Callable[[str, CandleData], Any]] = None):
        self.on_candle_completed = on_candle_completed
        # Current in-progress candle per symbol
        self._current_candles: Dict[str, Dict[str, Any]] = {}
        # Completed candles history per symbol (last 500)
        self._history: Dict[str, List[CandleData]] = {}

    def get_history(self, symbol: str) -> List[CandleData]:
        return self._history.get(symbol, [])

    def get_current_candle(self, symbol: str) -> Optional[CandleData]:
        curr = self._current_candles.get(symbol)
        if not curr:
            return None
        return CandleData(
            timestamp=curr["minute_start"],
            open=curr["open"],
            high=curr["high"],
            low=curr["low"],
            close=curr["close"],
            volume=curr["volume"],
            complete=False
        )

    def process_tick(self, tick: MarketTickData) -> Optional[CandleData]:
        """
        Process incoming tick.
        If a new minute has arrived, seals the previous candle as complete
        and triggers callback.
        """
        # Truncate timestamp to minute boundary
        dt = tick.timestamp.astimezone(timezone.utc)
        minute_start = dt.replace(second=0, microsecond=0)
        symbol = tick.symbol

        completed_candle: Optional[CandleData] = None

        if symbol in self._current_candles:
            curr = self._current_candles[symbol]
            if minute_start > curr["minute_start"]:
                # The previous minute is now complete!
                completed_candle = CandleData(
                    timestamp=curr["minute_start"],
                    open=curr["open"],
                    high=curr["high"],
                    low=curr["low"],
                    close=curr["close"],
                    volume=curr["volume"],
                    complete=True
                )
                if symbol not in self._history:
                    self._history[symbol] = []
                self._history[symbol].append(completed_candle)
                if len(self._history[symbol]) > 500:
                    self._history[symbol] = self._history[symbol][-500:]

                if self.on_candle_completed:
                    self.on_candle_completed(symbol, completed_candle)

                # Initialize new minute candle
                self._current_candles[symbol] = {
                    "minute_start": minute_start,
                    "open": tick.last_price,
                    "high": tick.last_price,
                    "low": tick.last_price,
                    "close": tick.last_price,
                    "volume": float(tick.volume)
                }
            else:
                # Update current running candle
                curr["high"] = max(curr["high"], tick.last_price)
                curr["low"] = min(curr["low"], tick.last_price)
                curr["close"] = tick.last_price
                curr["volume"] += float(tick.volume)
        else:
            # First tick for symbol
            self._current_candles[symbol] = {
                "minute_start": minute_start,
                "open": tick.last_price,
                "high": tick.last_price,
                "low": tick.last_price,
                "close": tick.last_price,
                "volume": float(tick.volume)
            }

        return completed_candle
