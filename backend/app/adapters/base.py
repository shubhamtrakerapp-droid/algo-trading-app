from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Callable, List, Dict, Any


@dataclass
class MarketTickData:
    instrument_token: str
    exchange_segment: str
    symbol: str
    last_price: float
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    volume: int = 0
    open_interest: int = 0
    bid: Optional[float] = None
    ask: Optional[float] = None
    is_index: bool = False


@dataclass
class CandleData:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0
    complete: bool = False


class BaseMarketDataAdapter(ABC):
    def __init__(self):
        self.on_tick_callback: Optional[Callable[[MarketTickData], Any]] = None
        self.on_status_callback: Optional[Callable[[str, str], Any]] = None
        self.on_error_callback: Optional[Callable[[str], Any]] = None
        self.is_connected: bool = False
        self.is_demo: bool = False
        self.last_tick_time: Optional[datetime] = None

    def register_callbacks(
        self,
        on_tick: Optional[Callable[[MarketTickData], Any]] = None,
        on_status: Optional[Callable[[str, str], Any]] = None,
        on_error: Optional[Callable[[str], Any]] = None,
    ):
        if on_tick:
            self.on_tick_callback = on_tick
        if on_status:
            self.on_status_callback = on_status
        if on_error:
            self.on_error_callback = on_error

    @abstractmethod
    async def start(self):
        """Start feed connection / loop."""
        pass

    @abstractmethod
    async def stop(self):
        """Stop connection."""
        pass

    @abstractmethod
    async def subscribe(self, tokens: List[Dict[str, str]], is_index: bool = False):
        """Subscribe to tokens."""
        pass

    @abstractmethod
    async def unsubscribe(self, tokens: List[Dict[str, str]], is_index: bool = False):
        """Unsubscribe from tokens."""
        pass

    @abstractmethod
    async def get_historical_candles(
        self,
        symbol: str,
        token: str,
        exchange_segment: str,
        interval: str,
        from_date: str,
        to_date: str
    ) -> List[CandleData]:
        """Fetch historical candles."""
        pass
