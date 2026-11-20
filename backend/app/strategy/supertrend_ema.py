import logging
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional, Tuple, Union

from backend.app.adapters.base import CandleData
from backend.app.strategy.indicators import calculate_ema, calculate_supertrend

logger = logging.getLogger("nextrade.strategy.supertrend_ema")

IST = timezone(timedelta(hours=5, minutes=30))


@dataclass
class SupertrendEMAEvaluation:
    timestamp: datetime
    candle_time: datetime
    symbol: str
    underlying_price: float  # NIFTY 50 close price
    supertrend: float
    supertrend_direction: int  # 1 = Bullish, -1 = Bearish
    supertrend_upper: float
    supertrend_lower: float
    supertrend_atr: float
    trend_str: str  # "BULLISH" or "BEARISH"
    ema_9: float
    ema_21: float
    # Conditions for BUY CE
    c_st_bull: bool     # Supertrend direction == 1
    c_ema_bull: bool    # EMA 9 > EMA 21
    c_close_bull: bool  # Candle close > EMA 9 and Close > EMA 21
    # Conditions for BUY PE
    c_st_bear: bool     # Supertrend direction == -1
    c_ema_bear: bool    # EMA 9 < EMA 21
    c_close_bear: bool  # Candle close < EMA 9 and Close < EMA 21
    # Signal
    signal: str         # "BUY_CE", "BUY_PE", "NONE"
    is_buy_ce: bool
    is_buy_pe: bool
    is_buy: bool        # True if either BUY_CE or BUY_PE
    target_contract_type: str  # "CE" if is_buy_ce else "PE" if is_buy_pe else "NONE"
    time_ist: str
    session_valid: bool
    action_reason: str
    strategy_id: str = "SUPERTREND_EMA"


class SupertrendEMAStrategy:
    """
    SUPERTREND EMA SCALPER Strategy.
    Timeframe: 1 minute.
    Underlying Signal: NIFTY 50 index completed candles.
    Execution Instrument: ATM CE or ATM PE option contracts.

    BUY CE Entry:
      1. Supertrend direction is bullish (direction == 1).
      2. EMA 9 > EMA 21.
      3. Candle close > EMA 9 and Candle close > EMA 21.
      4. Confirmed on the same completed 1-minute candle.
      5. No existing open position.
      6. Session (09:20 - 15:15 IST) and daily risk limits permit entry.
      -> Execute Paper BUY using selected ATM CE option premium.

    BUY PE Entry:
      1. Supertrend direction is bearish (direction == -1).
      2. EMA 9 < EMA 21.
      3. Candle close < EMA 9 and Candle close < EMA 21.
      4. Confirmed on the same completed 1-minute candle.
      5. No existing open position.
      6. Session (09:20 - 15:15 IST) and daily risk limits permit entry.
      -> Execute Paper BUY using selected ATM PE option premium.

    Dynamic Net P&L:
      - Target: ₹200 net profit per completed trade.
      - Max loss: ₹1,000 net loss per completed trade.
      Target pts = (200 + roundtrip_charges + slippage) / quantity
      Stop pts   = (1000 - roundtrip_charges - slippage) / quantity

    Daily Risk Management:
      - Daily NET profit target: +₹1,000.
      - Daily NET loss limit: -₹2,000.
      - When limits reached, block new entries.
      - Manage open position to normal exit.
      - Persistent lock until next trading session.

    Exit Rules:
      1. Net profit target reached.
      2. Net loss limit reached.
      3. Opposite confirmed Supertrend direction (Close position, do NOT reverse automatically).
      4. 15:20 IST auto square-off.
    """

    def __init__(
        self,
        atr_period: int = 10,
        multiplier: float = 3.0,
        ema_fast: int = 9,
        ema_slow: int = 21,
        lots: int = 5,
        lot_size: int = 65,
        target_net_profit: float = 200.0,
        max_loss_per_trade: float = 1000.0,
        daily_profit_target: float = 1000.0,
        daily_loss_limit: float = -2000.0,
        roundtrip_charges: float = 20.0,
        session_start_ist: str = "09:20",
        session_end_ist: str = "15:15",
        force_exit_ist: str = "15:20",
    ):
        self.atr_period = int(atr_period)
        self.multiplier = float(multiplier)
        self.ema_fast = int(ema_fast)
        self.ema_slow = int(ema_slow)
        self.lots = int(lots)
        self.lot_size = int(lot_size)
        self.quantity = self.lots * self.lot_size
        self.target_net_profit = float(target_net_profit)
        self.max_loss_per_trade = float(max_loss_per_trade)
        self.daily_profit_target = float(daily_profit_target)
        self.daily_loss_limit = float(daily_loss_limit)
        self.roundtrip_charges = float(roundtrip_charges)
        self.session_start_ist = session_start_ist
        self.session_end_ist = session_end_ist
        self.force_exit_ist = force_exit_ist

        self.last_evaluation: Optional[SupertrendEMAEvaluation] = None

    def calculate_target_and_stop_points(
        self,
        quantity: Optional[int] = None,
        target_net_profit: Optional[float] = None,
        max_loss_per_trade: Optional[float] = None,
        roundtrip_charges: Optional[float] = None,
        slippage_points: float = 0.0
    ) -> Dict[str, float]:
        """
        Dynamically calculate target and stop points based on net P&L formula:
        Net P&L = Gross P&L - Total Charges - Slippage
        Target Points = (Target Net Profit + Total Charges + Slippage Cost) / Quantity
        Stop Points   = (Max Loss Budget - Total Charges - Slippage Cost) / Quantity
        For 325 qty and ₹20 charges:
        Target pts = (200 + 20) / 325 = 0.6769 -> ~0.68 pts
        Stop pts   = (1000 - 20) / 325 = 980 / 325 = 3.0154 -> ~3.02 pts
        """
        qty = max(1, int(quantity if quantity is not None else self.quantity))
        t_net = float(target_net_profit if target_net_profit is not None else self.target_net_profit)
        l_max = float(max_loss_per_trade if max_loss_per_trade is not None else self.max_loss_per_trade)
        chg = float(roundtrip_charges if roundtrip_charges is not None else self.roundtrip_charges)

        slip_cost = (2.0 * slippage_points * qty) if slippage_points > 0 else 0.0

        # Target calculation
        target_pts = round((t_net + chg + slip_cost) / qty, 4)

        # Stop loss calculation (never permit a loss beyond the configured risk budget)
        stop_pts = round((l_max - chg - slip_cost) / qty, 4)
        if stop_pts <= 0:
            stop_pts = 0.50  # Minimum safe floor

        return {
            "quantity": qty,
            "target_net_profit": t_net,
            "max_loss_per_trade": l_max,
            "roundtrip_charges": chg,
            "slippage_cost": round(slip_cost, 2),
            "target_points": target_pts,
            "stop_points": stop_pts,
            "theoretical_target_pts": round((t_net + chg) / qty, 2),
            "theoretical_stop_pts": round((l_max - chg) / qty, 2),
        }

    def is_within_trading_session(self, dt: datetime) -> bool:
        """Check if datetime falls within 09:20 AM to 03:15 PM IST entry window."""
        ist_dt = dt.astimezone(IST)
        time_str = ist_dt.strftime("%H:%M")
        return self.session_start_ist <= time_str <= self.session_end_ist

    def is_force_exit_time(self, dt: datetime) -> bool:
        """Check if datetime is at or past 03:20 PM IST auto square-off."""
        ist_dt = dt.astimezone(IST)
        time_str = ist_dt.strftime("%H:%M")
        return time_str >= self.force_exit_ist

    def evaluate_completed_candle(
        self, completed_candles: List[Union[CandleData, Dict[str, Any]]]
    ) -> Optional[SupertrendEMAEvaluation]:
        """
        Evaluate SUPERTREND EMA SCALPER on the latest completed NIFTY 50 1-minute candle.
        Requires at least 25 candles to establish EMA 21 and Supertrend ATR 10.
        Uses completed candles only. No repainting or look-ahead bias.
        """
        min_required = max(self.ema_slow + 2, self.atr_period + 2)
        if not completed_candles or len(completed_candles) < min_required:
            logger.debug(f"Not enough completed candles: {len(completed_candles)} / {min_required}")
            return None

        # Extract OHLC
        highs = []
        lows = []
        closes = []
        for c in completed_candles:
            if isinstance(c, CandleData):
                highs.append(float(c.high))
                lows.append(float(c.low))
                closes.append(float(c.close))
            else:
                highs.append(float(c["high"]))
                lows.append(float(c["low"]))
                closes.append(float(c["close"]))

        latest_candle = completed_candles[-1]
        candle_ts = latest_candle.timestamp if isinstance(latest_candle, CandleData) else latest_candle["timestamp"]
        if isinstance(candle_ts, (int, float)):
            candle_dt = datetime.fromtimestamp(int(candle_ts), tz=timezone.utc)
        elif isinstance(candle_ts, str):
            candle_dt = datetime.fromisoformat(candle_ts.replace("Z", "+00:00"))
        elif isinstance(candle_ts, datetime):
            candle_dt = candle_ts if candle_ts.tzinfo else candle_ts.replace(tzinfo=timezone.utc)
        else:
            candle_dt = datetime.now(timezone.utc)

        ist_dt = candle_dt.astimezone(IST)
        time_ist = ist_dt.strftime("%H:%M")

        # 1. Supertrend Calculation
        st_data = calculate_supertrend(
            highs=highs,
            lows=lows,
            closes=closes,
            atr_period=self.atr_period,
            multiplier=self.multiplier
        )
        st_val = st_data["supertrend"][-1]
        st_dir = st_data["direction"][-1]  # 1 = Bullish, -1 = Bearish
        st_upper = st_data["upper_band"][-1]
        st_lower = st_data["lower_band"][-1]
        st_atr = st_data["atr"][-1]
        trend_str = "BULLISH" if st_dir == 1 else "BEARISH"

        # 2. EMA Calculation
        ema_fast_series = calculate_ema(closes, self.ema_fast)
        ema_slow_series = calculate_ema(closes, self.ema_slow)
        ema_9 = round(ema_fast_series[-1], 2)
        ema_21 = round(ema_slow_series[-1], 2)

        close_price = closes[-1]

        # 3. Session filter (09:20 to 15:15 IST)
        session_valid = self.session_start_ist <= time_ist <= self.session_end_ist

        # 4. Conditions for BUY CE:
        # 1. Supertrend direction is bullish (st_dir == 1)
        # 2. EMA 9 > EMA 21
        # 3. Candle closes above EMA 9 and EMA 21
        c_st_bull = bool(st_dir == 1)
        c_ema_bull = bool(ema_9 > ema_21)
        c_close_bull = bool(close_price > ema_9 and close_price > ema_21)
        is_buy_ce = c_st_bull and c_ema_bull and c_close_bull and session_valid

        # 5. Conditions for BUY PE:
        # 1. Supertrend direction is bearish (st_dir == -1)
        # 2. EMA 9 < EMA 21
        # 3. Candle closes below EMA 9 and EMA 21
        c_st_bear = bool(st_dir == -1)
        c_ema_bear = bool(ema_9 < ema_21)
        c_close_bear = bool(close_price < ema_9 and close_price < ema_21)
        is_buy_pe = c_st_bear and c_ema_bear and c_close_bear and session_valid

        if is_buy_ce:
            sig = "BUY_CE"
            action = f"BUY ATM CE Confirmed: ST Bullish ({st_val}), EMA9 ({ema_9}) > EMA21 ({ema_21}), Close ({close_price})"
            target_contract = "CE"
        elif is_buy_pe:
            sig = "BUY_PE"
            action = f"BUY ATM PE Confirmed: ST Bearish ({st_val}), EMA9 ({ema_9}) < EMA21 ({ema_21}), Close ({close_price})"
            target_contract = "PE"
        else:
            sig = "NONE"
            action = "Conditions not satisfied for CE or PE entry"
            target_contract = "NONE"

        res = SupertrendEMAEvaluation(
            timestamp=datetime.now(timezone.utc),
            candle_time=candle_dt,
            symbol="NIFTY 50",
            underlying_price=round(close_price, 2),
            supertrend=st_val,
            supertrend_direction=st_dir,
            supertrend_upper=st_upper,
            supertrend_lower=st_lower,
            supertrend_atr=st_atr,
            trend_str=trend_str,
            ema_9=ema_9,
            ema_21=ema_21,
            c_st_bull=c_st_bull,
            c_ema_bull=c_ema_bull,
            c_close_bull=c_close_bull,
            c_st_bear=c_st_bear,
            c_ema_bear=c_ema_bear,
            c_close_bear=c_close_bear,
            signal=sig,
            is_buy_ce=is_buy_ce,
            is_buy_pe=is_buy_pe,
            is_buy=bool(is_buy_ce or is_buy_pe),
            target_contract_type=target_contract,
            time_ist=time_ist,
            session_valid=session_valid,
            action_reason=action,
            strategy_id="SUPERTREND_EMA"
        )
        self.last_evaluation = res
        return res

    def calculate_series(
        self, candles: List[Dict[str, Any]]
    ) -> List[SupertrendEMAEvaluation]:
        """
        Calculate full vectorized series for historical backtesting on completed NIFTY candles.
        Guarantees no lookahead bias: each bar `i` uses only candles up to `i`.
        """
        n = len(candles)
        if n == 0:
            return []

        highs = [float(c["high"]) for c in candles]
        lows = [float(c["low"]) for c in candles]
        closes = [float(c["close"]) for c in candles]

        st_data = calculate_supertrend(
            highs=highs,
            lows=lows,
            closes=closes,
            atr_period=self.atr_period,
            multiplier=self.multiplier
        )
        ema_fast_series = calculate_ema(closes, self.ema_fast)
        ema_slow_series = calculate_ema(closes, self.ema_slow)

        evaluations: List[SupertrendEMAEvaluation] = []
        min_start = max(self.ema_slow + 2, self.atr_period + 2)

        for i in range(n):
            c = candles[i]
            c_ts = c["timestamp"]
            if isinstance(c_ts, (int, float)):
                c_dt = datetime.fromtimestamp(int(c_ts), tz=timezone.utc)
            elif isinstance(c_ts, str):
                c_dt = datetime.fromisoformat(c_ts.replace("Z", "+00:00"))
            elif isinstance(c_ts, datetime):
                c_dt = c_ts if c_ts.tzinfo else c_ts.replace(tzinfo=timezone.utc)
            else:
                c_dt = datetime.now(timezone.utc)

            ist_dt = c_dt.astimezone(IST)
            time_ist = ist_dt.strftime("%H:%M")

            if i < min_start:
                # Warm-up period
                evaluations.append(
                    SupertrendEMAEvaluation(
                        timestamp=datetime.now(timezone.utc),
                        candle_time=c_dt,
                        symbol="NIFTY 50",
                        underlying_price=closes[i],
                        supertrend=st_data["supertrend"][i] if i < len(st_data["supertrend"]) else 0.0,
                        supertrend_direction=st_data["direction"][i] if i < len(st_data["direction"]) else 1,
                        supertrend_upper=st_data["upper_band"][i] if i < len(st_data["upper_band"]) else 0.0,
                        supertrend_lower=st_data["lower_band"][i] if i < len(st_data["lower_band"]) else 0.0,
                        supertrend_atr=st_data["atr"][i] if i < len(st_data["atr"]) else 0.0,
                        trend_str="WARMUP",
                        ema_9=round(ema_fast_series[i], 2),
                        ema_21=round(ema_slow_series[i], 2),
                        c_st_bull=False,
                        c_ema_bull=False,
                        c_close_bull=False,
                        c_st_bear=False,
                        c_ema_bear=False,
                        c_close_bear=False,
                        signal="NONE",
                        is_buy_ce=False,
                        is_buy_pe=False,
                        is_buy=False,
                        target_contract_type="NONE",
                        time_ist=time_ist,
                        session_valid=False,
                        action_reason="Indicator warm-up period",
                        strategy_id="SUPERTREND_EMA"
                    )
                )
                continue

            st_val = st_data["supertrend"][i]
            st_dir = st_data["direction"][i]
            st_upper = st_data["upper_band"][i]
            st_lower = st_data["lower_band"][i]
            st_atr = st_data["atr"][i]
            trend_str = "BULLISH" if st_dir == 1 else "BEARISH"

            ema_9 = round(ema_fast_series[i], 2)
            ema_21 = round(ema_slow_series[i], 2)
            close_price = closes[i]

            session_valid = self.session_start_ist <= time_ist <= self.session_end_ist

            # Conditions
            c_st_bull = bool(st_dir == 1)
            c_ema_bull = bool(ema_9 > ema_21)
            c_close_bull = bool(close_price > ema_9 and close_price > ema_21)
            is_buy_ce = c_st_bull and c_ema_bull and c_close_bull and session_valid

            c_st_bear = bool(st_dir == -1)
            c_ema_bear = bool(ema_9 < ema_21)
            c_close_bear = bool(close_price < ema_9 and close_price < ema_21)
            is_buy_pe = c_st_bear and c_ema_bear and c_close_bear and session_valid

            if is_buy_ce:
                sig = "BUY_CE"
                action = f"BUY ATM CE: ST Bullish, EMA 9>21, Close>EMAs"
                target_contract = "CE"
            elif is_buy_pe:
                sig = "BUY_PE"
                action = f"BUY ATM PE: ST Bearish, EMA 9<21, Close<EMAs"
                target_contract = "PE"
            else:
                sig = "NONE"
                action = "Neutral / Wait"
                target_contract = "NONE"

            evaluations.append(
                SupertrendEMAEvaluation(
                    timestamp=datetime.now(timezone.utc),
                    candle_time=c_dt,
                    symbol="NIFTY 50",
                    underlying_price=round(close_price, 2),
                    supertrend=st_val,
                    supertrend_direction=st_dir,
                    supertrend_upper=st_upper,
                    supertrend_lower=st_lower,
                    supertrend_atr=st_atr,
                    trend_str=trend_str,
                    ema_9=ema_9,
                    ema_21=ema_21,
                    c_st_bull=c_st_bull,
                    c_ema_bull=c_ema_bull,
                    c_close_bull=c_close_bull,
                    c_st_bear=c_st_bear,
                    c_ema_bear=c_ema_bear,
                    c_close_bear=c_close_bear,
                    signal=sig,
                    is_buy_ce=is_buy_ce,
                    is_buy_pe=is_buy_pe,
                    is_buy=bool(is_buy_ce or is_buy_pe),
                    target_contract_type=target_contract,
                    time_ist=time_ist,
                    session_valid=session_valid,
                    action_reason=action,
                    strategy_id="SUPERTREND_EMA"
                )
            )

        return evaluations

    def get_config_dict(self) -> Dict[str, Any]:
        pts = self.calculate_target_and_stop_points()
        return {
            "strategy_id": "SUPERTREND_EMA",
            "strategy_name": "SUPERTREND EMA SCALPER",
            "underlying": "NIFTY",
            "signal_instrument": "NIFTY 50",
            "execution_instruments": ["ATM CE", "ATM PE"],
            "timeframe": "1m",
            "atr_period": self.atr_period,
            "multiplier": self.multiplier,
            "ema_fast": self.ema_fast,
            "ema_slow": self.ema_slow,
            "lots": self.lots,
            "lot_size": self.lot_size,
            "quantity": self.quantity,
            "target_net_profit": self.target_net_profit,
            "max_loss_per_trade": self.max_loss_per_trade,
            "daily_profit_target": self.daily_profit_target,
            "daily_loss_limit": self.daily_loss_limit,
            "roundtrip_charges": self.roundtrip_charges,
            "target_points": pts["target_points"],
            "stop_points": pts["stop_points"],
            "theoretical_target_pts": pts["theoretical_target_pts"],
            "theoretical_stop_pts": pts["theoretical_stop_pts"],
            "session_start_ist": self.session_start_ist,
            "session_end_ist": self.session_end_ist,
            "force_exit_ist": self.force_exit_ist,
        }
