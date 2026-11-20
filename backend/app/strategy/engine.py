import logging
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Any, Union

from backend.app.adapters.base import CandleData
from backend.app.strategy.indicators import calculate_ema, calculate_rsi
from backend.app.strategy.ut_bot import UTBotStrategy, UTBotEvaluation
from backend.app.strategy.supertrend_ema import SupertrendEMAStrategy, SupertrendEMAEvaluation
from backend.app.strategy.ai_micro_scalper.strategy import AIMicroScalperStrategy, AIMicroScalperEvaluation

logger = logging.getLogger("nextrade.strategy")

IST = timezone(timedelta(hours=5, minutes=30))


@dataclass
class StrategyEvaluationResult:
    timestamp: datetime
    candle_time: datetime
    underlying_price: float
    ema_9: float
    ema_21: float
    ema_50: float
    rsi_14: float
    time_ist: str
    condition_1: bool  # EMA 9 > EMA 21
    condition_2: bool  # NIFTY Index close > EMA 50
    condition_3: bool  # RSI 14 > 50
    condition_4: bool  # 09:20 AM to 03:15 PM IST
    signal: str        # "BUY_ATM_CE" or "NONE"
    is_buy: bool
    is_sell: bool = False
    strategy_id: str = "EMA_RSI"


class EMAStrategyEngine:
    """
    Evaluates the original NIFTY 1-Minute EMA + RSI Strategy.
    DO NOT MODIFY OR OPTIMIZE RULES.
    Strictly state-based:
    Condition 1: EMA 9 > EMA 21
    Condition 2: NIFTY close > EMA 50
    Condition 3: RSI 14 > 50
    Condition 4: Trading session filter (09:20 AM to 03:15 PM IST)
    Signal confirmation: Evaluated strictly on COMPLETED 1-minute candles.
    """

    def __init__(
        self,
        session_start_ist: str = "09:20",
        session_end_ist: str = "15:15",
        force_exit_ist: str = "15:20",
        lots: int = 1,
        lot_size: int = 65,
        target_points: float = 4.0,
        stop_points: float = 2.0,
        max_loss_per_trade: float = 1000.0,
    ):
        self.session_start_ist = session_start_ist
        self.session_end_ist = session_end_ist
        self.force_exit_ist = force_exit_ist
        self.lots = lots
        self.lot_size = lot_size
        self.quantity = lots * lot_size
        self.target_points = target_points
        self.stop_points = stop_points
        self.max_loss_per_trade = max_loss_per_trade
        self.last_evaluation: Optional[StrategyEvaluationResult] = None

    def calculate_effective_stop_points(self) -> float:
        """Calculate effective stop loss points with optional ₹1,000 risk cap."""
        if self.max_loss_per_trade and self.max_loss_per_trade > 0:
            max_loss_pts = self.max_loss_per_trade / max(1, self.quantity)
            return round(min(self.stop_points, max_loss_pts), 4)
        return self.stop_points

    def is_within_trading_session(self, dt: datetime) -> bool:
        """Check if datetime falls within 09:20 AM to 03:15 PM IST."""
        ist_dt = dt.astimezone(IST)
        time_str = ist_dt.strftime("%H:%M")
        return self.session_start_ist <= time_str <= self.session_end_ist

    def is_force_exit_time(self, dt: datetime) -> bool:
        """Check if datetime is at or past 03:20 PM IST force exit cutoff."""
        ist_dt = dt.astimezone(IST)
        time_str = ist_dt.strftime("%H:%M")
        return time_str >= self.force_exit_ist

    def evaluate_completed_candle(self, completed_candles: List[CandleData]) -> Optional[StrategyEvaluationResult]:
        """
        Evaluate strategy on the latest COMPLETED 1-minute candle.
        Requires at least 50 candles for reliable EMA 50 calculation.
        """
        if not completed_candles or len(completed_candles) < 50:
            logger.debug(f"Not enough completed candles for evaluation: {len(completed_candles)} / 50")
            return None

        closes = [c.close for c in completed_candles]
        latest_candle = completed_candles[-1]

        # Calculate indicators
        ema_9_series = calculate_ema(closes, 9)
        ema_21_series = calculate_ema(closes, 21)
        ema_50_series = calculate_ema(closes, 50)
        rsi_14_series = calculate_rsi(closes, 14)

        ema_9 = round(ema_9_series[-1], 2)
        ema_21 = round(ema_21_series[-1], 2)
        ema_50 = round(ema_50_series[-1], 2)
        rsi_14 = round(rsi_14_series[-1], 2)
        close_price = latest_candle.close

        # IST conversion
        ist_dt = latest_candle.timestamp.astimezone(IST)
        time_ist = ist_dt.strftime("%H:%M")

        # Evaluate the 4 EXACT conditions
        c1 = bool(ema_9 > ema_21)
        c2 = bool(close_price > ema_50)
        c3 = bool(rsi_14 > 50.0)
        c4 = bool(self.session_start_ist <= time_ist <= self.session_end_ist)

        is_buy = c1 and c2 and c3 and c4
        signal = "BUY_ATM_CE" if is_buy else "NONE"

        res = StrategyEvaluationResult(
            timestamp=datetime.now(timezone.utc),
            candle_time=latest_candle.timestamp,
            underlying_price=close_price,
            ema_9=ema_9,
            ema_21=ema_21,
            ema_50=ema_50,
            rsi_14=rsi_14,
            time_ist=time_ist,
            condition_1=c1,
            condition_2=c2,
            condition_3=c3,
            condition_4=c4,
            signal=signal,
            is_buy=is_buy,
            is_sell=False,
            strategy_id="EMA_RSI"
        )

        self.last_evaluation = res
        return res

    def get_config_dict(self) -> Dict[str, Any]:
        return {
            "strategy_id": "EMA_RSI",
            "strategy_name": "NIFTY 1M EMA+RSI ATM CE",
            "underlying": "NIFTY",
            "timeframe": "1m",
            "ema_fast": 9,
            "ema_medium": 21,
            "ema_slow": 50,
            "rsi_period": 14,
            "rsi_threshold": 50.0,
            "session_start_ist": self.session_start_ist,
            "session_end_ist": self.session_end_ist,
            "force_exit_ist": self.force_exit_ist,
            "lots": self.lots,
            "lot_size": self.lot_size,
            "quantity": self.quantity,
            "target_points": self.target_points,
            "stop_points": self.stop_points,
            "max_loss_per_trade": self.max_loss_per_trade,
            "effective_stop_points": self.calculate_effective_stop_points(),
        }


# Maintain backward-compatible alias
StrategyEngine = EMAStrategyEngine


class MultiStrategyManager:
    """
    Coordinates multi-strategy selection, execution, and monitoring.
    Supports:
      1. 'EMA_RSI' — Original NIFTY EMA 9/21/50 + RSI 14 Strategy.
      2. 'UT_BOT' — Pine Script v4 UT Bot ATM Option Strategy.
      3. 'SUPERTREND_EMA' — SUPERTREND EMA SCALPER 1-minute ATM Option Strategy.
    """

    def __init__(self):
        self.ema_strategy = EMAStrategyEngine()
        self.ut_bot_strategy = UTBotStrategy(
            key_value=1.0,
            atr_period=10,
            use_heikin_ashi=False,
            lots=5,
            lot_size=65,
            target_points=4.0,
            stop_points=4.0,
            max_loss_per_trade=None,  # Baseline 4-point SL by default
            signal_source="CHART_INSTRUMENT"
        )
        self.supertrend_ema_strategy = SupertrendEMAStrategy(
            atr_period=10,
            multiplier=3.0,
            ema_fast=9,
            ema_slow=21,
            lots=5,
            lot_size=65,
            target_net_profit=200.0,
            max_loss_per_trade=1000.0,
            daily_profit_target=1000.0,
            daily_loss_limit=-2000.0,
            roundtrip_charges=20.0
        )
        self.ai_micro_scalper_strategy = AIMicroScalperStrategy(
            initial_capital=20000.0,
            lots=2,
            lot_size=65,
            target_net_profit=200.0,
            max_loss_per_trade=300.0,
            daily_profit_target=500.0,
            daily_loss_limit=-500.0,
            max_trades_per_day=5,
            max_consecutive_losses=2,
            max_holding_time_minutes=5,
            roundtrip_charges=20.0,
        )
        self.active_strategy_id = "UT_BOT"  # Default active strategy is UT Bot per prompt

    @property
    def session_start_ist(self) -> str:
        return self.get_active_strategy().session_start_ist

    @property
    def session_end_ist(self) -> str:
        return self.get_active_strategy().session_end_ist

    @property
    def force_exit_ist(self) -> str:
        return self.get_active_strategy().force_exit_ist

    @property
    def last_evaluation(self) -> Optional[Union[StrategyEvaluationResult, UTBotEvaluation, SupertrendEMAEvaluation, AIMicroScalperEvaluation]]:
        return self.get_active_strategy().last_evaluation

    def set_active_strategy(self, strategy_id: str) -> bool:
        normalized = "SUPERTREND_EMA" if strategy_id == "SUPERTREND_EMA_SCALPER" else strategy_id
        if normalized in ("EMA_RSI", "UT_BOT", "SUPERTREND_EMA", "AI_MICRO_SCALPER_V1"):
            self.active_strategy_id = normalized
            logger.info(f"Active trading strategy switched to: {normalized}")
            return True
        return False

    def get_active_strategy(self) -> Union[EMAStrategyEngine, UTBotStrategy, SupertrendEMAStrategy, AIMicroScalperStrategy]:
        if self.active_strategy_id == "UT_BOT":
            return self.ut_bot_strategy
        elif self.active_strategy_id == "SUPERTREND_EMA":
            return self.supertrend_ema_strategy
        elif self.active_strategy_id == "AI_MICRO_SCALPER_V1":
            return self.ai_micro_scalper_strategy
        return self.ema_strategy

    def is_within_trading_session(self, dt: datetime) -> bool:
        return self.get_active_strategy().is_within_trading_session(dt)

    def is_force_exit_time(self, dt: datetime) -> bool:
        return self.get_active_strategy().is_force_exit_time(dt)

    def evaluate_completed_candle(
        self, completed_candles: List[Any], symbol: str = "NIFTY 50"
    ) -> Optional[Union[StrategyEvaluationResult, UTBotEvaluation, SupertrendEMAEvaluation, AIMicroScalperEvaluation]]:
        """
        Evaluate candle for the currently active strategy.
        Respects each strategy's signal_source configuration.
        """
        if self.active_strategy_id == "UT_BOT":
            # If UT Bot is configured for CHART_INSTRUMENT, evaluate on that instrument
            # If configured for NIFTY_INDEX, only evaluate if symbol is NIFTY index
            if self.ut_bot_strategy.signal_source == "NIFTY_INDEX" and ("CE" in symbol or "PE" in symbol):
                return None
            return self.ut_bot_strategy.evaluate_completed_candle(completed_candles)
        elif self.active_strategy_id == "SUPERTREND_EMA":
            # Supertrend EMA Scalper strictly evaluates NIFTY 50 underlying completed candles
            if "CE" in symbol or "PE" in symbol:
                return None
            return self.supertrend_ema_strategy.evaluate_completed_candle(completed_candles)
        elif self.active_strategy_id == "AI_MICRO_SCALPER_V1":
            # AI Micro-Scalper strictly evaluates NIFTY 50 underlying completed candles
            if "CE" in symbol or "PE" in symbol:
                return None
            return self.ai_micro_scalper_strategy.evaluate_completed_candle(completed_candles)
        else:
            # EMA strategy strictly evaluates NIFTY Index completed candles
            if "CE" in symbol or "PE" in symbol:
                return None
            return self.ema_strategy.evaluate_completed_candle(completed_candles)

    def get_all_profiles(self) -> List[Dict[str, Any]]:
        return [
            {
                **self.ema_strategy.get_config_dict(),
                "is_active": self.active_strategy_id == "EMA_RSI"
            },
            {
                **self.ut_bot_strategy.get_config_dict(),
                "is_active": self.active_strategy_id == "UT_BOT"
            },
            {
                **self.supertrend_ema_strategy.get_config_dict(),
                "is_active": self.active_strategy_id == "SUPERTREND_EMA"
            },
            {
                **self.ai_micro_scalper_strategy.get_config_dict(),
                "is_active": self.active_strategy_id == "AI_MICRO_SCALPER_V1"
            }
        ]
