import logging
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional

from backend.app.strategy.indicators import calculate_atr, calculate_heikin_ashi

logger = logging.getLogger("nextrade.strategy.ut_bot")

IST = timezone(timedelta(hours=5, minutes=30))


@dataclass
class UTBotEvaluation:
    timestamp: datetime
    candle_time: datetime
    symbol: str
    src_price: float
    atr: float
    n_loss: float
    trailing_stop: float
    prev_trailing_stop: float
    pos: int
    prev_pos: int
    above: bool
    below: bool
    is_buy: bool
    is_sell: bool
    signal: str  # "BUY", "SELL", "NONE"
    time_ist: str
    session_valid: bool
    action_reason: str


class UTBotStrategy:
    """
    Pine Script v4 UT Bot ATM Option Strategy Implementation.
    Preserves exact Pine Script v4 mathematical behavior:
      a = Sensitivity / Key Value (default 1)
      c = ATR Period (default 10)
      h = Heikin Ashi option (default False)
      Lots = 5 (default), Lot Size = 65 (default)
      Target = 4 points, Stop = 4 points
      Trailing stop = xATRTrailingStop
      BUY = src > xATRTrailingStop and crossover(src, xATRTrailingStop)
      SELL = src < xATRTrailingStop and crossover(xATRTrailingStop, src)
    """

    def __init__(
        self,
        key_value: float = 1.0,
        atr_period: int = 10,
        use_heikin_ashi: bool = False,
        lots: int = 5,
        lot_size: int = 65,
        target_points: float = 4.0,
        stop_points: float = 2.0,
        max_loss_per_trade: Optional[float] = None,  # Optional ₹1,000 risk cap overlay
        signal_source: str = "CHART_INSTRUMENT",      # "CHART_INSTRUMENT" or "NIFTY_INDEX"
        session_start_ist: str = "09:20",
        session_end_ist: str = "15:15",
        force_exit_ist: str = "15:20",
        exit_on_ut_sell_signal: bool = True,
    ):
        self.key_value = float(key_value)
        self.atr_period = int(atr_period)
        self.use_heikin_ashi = bool(use_heikin_ashi)
        self.lots = int(lots)
        self.lot_size = int(lot_size)
        self.quantity = self.lots * self.lot_size
        self.target_points = float(target_points)
        self.stop_points = float(stop_points)
        self.max_loss_per_trade = float(max_loss_per_trade) if max_loss_per_trade is not None else None
        self.signal_source = signal_source
        self.session_start_ist = session_start_ist
        self.session_end_ist = session_end_ist
        self.force_exit_ist = force_exit_ist
        self.exit_on_ut_sell_signal = bool(exit_on_ut_sell_signal)

        self.last_evaluation: Optional[UTBotEvaluation] = None

    def calculate_effective_stop_points(
        self,
        stop_points: Optional[float] = None,
        max_loss: Optional[float] = None,
        quantity: Optional[int] = None
    ) -> float:
        """
        Calculate effective stop loss points.
        Baseline: configured stop points (default 2.0).
        Optional risk cap: if max_loss_per_trade is set (e.g. ₹1,000),
        effective_stop = min(stop_points, max_loss / quantity).
        For 5 lots * 65 = 325 qty: 1000 / 325 = 3.0769 points -> min(2.0, 3.0769) = 2.0 points.
        For 600 qty: 1000 / 600 = 1.6667 points -> min(2.0, 1.6667) = 1.6667 points.
        """
        sl = float(stop_points) if stop_points is not None else self.stop_points
        ml = float(max_loss) if max_loss is not None else self.max_loss_per_trade
        qty = int(quantity) if quantity is not None else self.quantity

        if ml and ml > 0:
            max_loss_pts = ml / max(1, qty)
            return round(min(sl, max_loss_pts), 4)
        return round(sl, 4)

    def is_within_trading_session(self, dt: datetime) -> bool:
        """Check if datetime falls within 09:20 AM to 03:15 PM IST."""
        ist_dt = dt.astimezone(IST)
        time_str = ist_dt.strftime("%H:%M")
        return self.session_start_ist <= time_str <= self.session_end_ist

    def is_force_exit_time(self, dt: datetime) -> bool:
        """Check if datetime is at or past 03:20 PM IST."""
        ist_dt = dt.astimezone(IST)
        time_str = ist_dt.strftime("%H:%M")
        return time_str >= self.force_exit_ist

    def calculate_series(self, candles: List[Any]) -> List[UTBotEvaluation]:
        """
        Calculate full historical UT Bot indicator and signal series on candles.
        `candles` may be list of CandleData objects or dicts.
        """
        n = len(candles)
        if n == 0:
            return []

        # Extract OHLC and timestamps
        opens: List[float] = []
        highs: List[float] = []
        lows: List[float] = []
        closes: List[float] = []
        timestamps: List[datetime] = []
        symbols: List[str] = []

        for c in candles:
            if isinstance(c, dict):
                opens.append(float(c["open"]))
                highs.append(float(c["high"]))
                lows.append(float(c["low"]))
                closes.append(float(c["close"]))
                ts = c["timestamp"]
                if isinstance(ts, (int, float)):
                    timestamps.append(datetime.fromtimestamp(ts, tz=timezone.utc))
                elif isinstance(ts, datetime):
                    timestamps.append(ts)
                else:
                    timestamps.append(datetime.fromisoformat(str(ts)))
                symbols.append(c.get("symbol", "CHART"))
            else:
                opens.append(float(c.open))
                highs.append(float(c.high))
                lows.append(float(c.low))
                closes.append(float(c.close))
                timestamps.append(c.timestamp)
                symbols.append(getattr(c, "symbol", "CHART"))

        # 1. Source Price: Heikin Ashi close or standard close
        if self.use_heikin_ashi:
            ha = calculate_heikin_ashi(opens, highs, lows, closes)
            src = ha["close"]
        else:
            src = closes

        # 2. xATR and nLoss
        atr_series = calculate_atr(highs, lows, closes, self.atr_period)
        n_loss_series = [round(self.key_value * a, 4) for a in atr_series]

        # 3. Recursive xATRTrailingStop and pos calculation
        trailing_stops: List[float] = [0.0] * n
        pos_series: List[int] = [0] * n
        evaluations: List[UTBotEvaluation] = []

        # Bar 0 initialization
        trailing_stops[0] = round(src[0] - n_loss_series[0], 4)
        pos_series[0] = 1 if src[0] > 0 else 0

        for i in range(n):
            curr_src = src[i]
            n_loss = n_loss_series[i]
            curr_atr = atr_series[i]
            c_time = timestamps[i]
            sym = symbols[i]
            ist_dt = c_time.astimezone(IST)
            time_ist = ist_dt.strftime("%H:%M")
            session_valid = self.session_start_ist <= time_ist <= self.session_end_ist

            if i == 0:
                prev_stop = 0.0
                curr_stop = trailing_stops[0]
                prev_pos = 0
                curr_pos = pos_series[0]
                above = False
                below = False
                buy = False
                sell = False
                reason = "Initial warm-up candle"
            else:
                prev_stop = trailing_stops[i - 1]
                prev_src = src[i - 1]
                prev_pos = pos_series[i - 1]

                # Exact Pine Script xATRTrailingStop formula
                if curr_src > prev_stop and prev_src > prev_stop:
                    curr_stop = max(prev_stop, curr_src - n_loss)
                elif curr_src < prev_stop and prev_src < prev_stop:
                    curr_stop = min(prev_stop, curr_src + n_loss)
                elif curr_src > prev_stop:
                    curr_stop = curr_src - n_loss
                else:
                    curr_stop = curr_src + n_loss

                curr_stop = round(curr_stop, 4)
                trailing_stops[i] = curr_stop

                # pos calculation
                if prev_src < prev_stop and curr_src > prev_stop:
                    curr_pos = 1
                elif prev_src > prev_stop and curr_src < prev_stop:
                    curr_pos = -1
                else:
                    curr_pos = prev_pos
                pos_series[i] = curr_pos

                # Pine Script crossover / crossunder
                # above = crossover(src, xATRTrailingStop) -> prev_src <= prev_stop and curr_src > curr_stop
                above = bool((prev_src <= prev_stop) and (curr_src > curr_stop))
                below = bool((prev_src >= prev_stop) and (curr_src < curr_stop))

                buy = bool(curr_src > curr_stop and above)
                sell = bool(curr_src < curr_stop and below)

                if buy:
                    reason = "UT Bot Crossover: Source price crossed above ATR trailing stop"
                elif sell:
                    reason = "UT Bot Crossunder: Source price crossed below ATR trailing stop"
                else:
                    reason = "No crossover event on completed candle"

            signal = "BUY" if buy else ("SELL" if sell else "NONE")

            ev = UTBotEvaluation(
                timestamp=datetime.now(timezone.utc),
                candle_time=c_time,
                symbol=sym,
                src_price=round(curr_src, 2),
                atr=round(curr_atr, 4),
                n_loss=round(n_loss, 4),
                trailing_stop=curr_stop,
                prev_trailing_stop=prev_stop,
                pos=curr_pos,
                prev_pos=prev_pos,
                above=above,
                below=below,
                is_buy=buy,
                is_sell=sell,
                signal=signal,
                time_ist=time_ist,
                session_valid=session_valid,
                action_reason=reason
            )
            evaluations.append(ev)

        return evaluations

    def evaluate_completed_candle(self, completed_candles: List[Any]) -> Optional[UTBotEvaluation]:
        """
        Evaluate UT Bot on the latest completed candle.
        Requires at least atr_period + 2 completed candles.
        """
        if not completed_candles or len(completed_candles) < self.atr_period + 2:
            return None

        series = self.calculate_series(completed_candles)
        if not series:
            return None

        last_ev = series[-1]
        self.last_evaluation = last_ev
        return last_ev

    def get_config_dict(self) -> Dict[str, Any]:
        """Return full configuration snapshot for trade and signal audit records."""
        return {
            "strategy_id": "UT_BOT",
            "strategy_name": "UT Bot ATM Option Strategy",
            "key_value": self.key_value,
            "atr_period": self.atr_period,
            "use_heikin_ashi": self.use_heikin_ashi,
            "lots": self.lots,
            "lot_size": self.lot_size,
            "quantity": self.quantity,
            "target_points": self.target_points,
            "stop_points": self.stop_points,
            "max_loss_per_trade": self.max_loss_per_trade,
            "effective_stop_points": self.calculate_effective_stop_points(),
            "exit_on_ut_sell_signal": self.exit_on_ut_sell_signal,
            "signal_source": self.signal_source,
            "session_start_ist": self.session_start_ist,
            "session_end_ist": self.session_end_ist,
            "force_exit_ist": self.force_exit_ist
        }
