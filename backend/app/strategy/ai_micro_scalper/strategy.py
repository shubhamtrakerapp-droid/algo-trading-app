import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional, Union

from backend.app.adapters.base import CandleData
from backend.app.strategy.indicators import (
    calculate_ema,
    calculate_rsi,
    calculate_atr,
    aggregate_candles,
)
from backend.app.strategy.ai_micro_scalper.indicators import (
    calculate_adx,
    calculate_session_vwap,
)
from backend.app.strategy.ai_micro_scalper.agents import (
    AIVotingEngine,
    AIVotingResult,
)
from backend.app.strategy.ai_micro_scalper.option_selector import (
    AIMicroScalperOptionSelector,
)

logger = logging.getLogger("nextrade.strategy.ai_micro_scalper")

IST = timezone(timedelta(hours=5, minutes=30))


@dataclass
class AIMicroScalperEvaluation:
    timestamp: datetime
    candle_time: datetime
    symbol: str
    underlying_price: float
    time_ist: str
    session_valid: bool
    # 5-minute indicators
    ema_5m_20: float
    ema_5m_50: float
    vwap_5m: float
    adx_5m: float
    # 1-minute indicators
    ema_1m_9: float
    ema_1m_20: float
    vwap_1m: float
    rsi_1m: float
    atr_1m: float
    # Signal
    signal: str  # "BUY_CE", "BUY_PE", "NONE"
    is_buy_ce: bool
    is_buy_pe: bool
    is_buy: bool
    target_contract_type: str  # "CE", "PE", "NONE"
    # Option selection details
    contract_symbol: Optional[str] = None
    contract_strike: Optional[float] = None
    contract_expiry: Optional[str] = None
    contract_premium: float = 0.0
    is_itm: bool = False
    spread: float = 0.0
    # Sizing & risk
    lots: int = 2
    lot_size: int = 65
    quantity: int = 130
    target_points: float = 0.0
    stop_points: float = 0.0
    theoretical_target_net: float = 200.0
    theoretical_max_loss: float = 300.0
    capital_required: float = 0.0
    capital_available: float = 20000.0
    capital_ratio: float = 0.0
    # AI Agents details
    agent_votes: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    voting_result: Optional[Dict[str, Any]] = None
    action_reason: str = ""
    strategy_id: str = "AI_MICRO_SCALPER_V1"


class AIMicroScalperStrategy:
    """
    NEXTRADE AI MICRO-SCALPER V1 Strategy.
    Rule-based algorithmic micro-scalping strategy with five explainable AI agents.
    Strictly PAPER TRADING ONLY.

    Parameters:
      - Starting virtual capital: ₹20,000.
      - Instrument: NIFTY Options (CE/PE).
      - Preferred premium range: ₹100–₹150 (if outside, evaluate 1-strike ITM).
      - Position sizing: 2 lots × dynamic lot size from instrument master.
      - Capital cap: Maximum 90% capital deployment (purchase_cost + charges <= 0.90 * capital).
      - Max trades/day: 5.
      - Max consecutive losses: 2 (pause new entries).
      - Daily net P&L limits: +₹500 profit target, -₹500 loss limit.
      - Per-trade net P&L targets: ₹200 net target, ₹300 max net loss.
      - Max holding time: 5 minutes (configurable: 3m, 5m, 8m).
      - Entry window: 09:25–14:45 IST. Mandatory square-off: 15:20 IST.
      - Five deterministic AI agents: Trend, Momentum, Volatility, Market Regime, Risk.
      - Voting: >= 4 of 5 must approve; Risk Agent must always approve.
    """

    def __init__(
        self,
        initial_capital: float = 20000.0,
        lots: int = 2,
        lot_size: int = 65,
        capital_deployment_cap_pct: float = 90.0,
        preferred_premium_min: float = 100.0,
        preferred_premium_max: float = 150.0,
        target_net_profit: float = 200.0,
        max_loss_per_trade: float = 300.0,
        daily_profit_target: float = 500.0,
        daily_loss_limit: float = -500.0,
        max_trades_per_day: int = 5,
        max_consecutive_losses: int = 2,
        max_holding_time_minutes: int = 5,
        entry_start_ist: str = "09:25",
        entry_end_ist: str = "14:45",
        force_exit_ist: str = "15:20",
        roundtrip_charges: float = 20.0,
        max_spread: float = 0.50,
        slippage_points: float = 0.05,
    ):
        self.initial_capital = float(initial_capital)
        self.lots = int(lots)
        self.lot_size = int(lot_size)
        self.quantity = self.lots * self.lot_size
        self.capital_deployment_cap_pct = float(capital_deployment_cap_pct)
        self.preferred_premium_min = float(preferred_premium_min)
        self.preferred_premium_max = float(preferred_premium_max)
        self.target_net_profit = float(target_net_profit)
        self.max_loss_per_trade = float(max_loss_per_trade)
        self.daily_profit_target = float(daily_profit_target)
        self.daily_loss_limit = float(daily_loss_limit)
        self.max_trades_per_day = int(max_trades_per_day)
        self.max_consecutive_losses = int(max_consecutive_losses)
        self.max_holding_time_minutes = int(max_holding_time_minutes)
        self.entry_start_ist = entry_start_ist
        self.entry_end_ist = entry_end_ist
        self.force_exit_ist = force_exit_ist
        self.roundtrip_charges = float(roundtrip_charges)
        self.max_spread = float(max_spread)
        self.slippage_points = float(slippage_points)

        self.option_selector = AIMicroScalperOptionSelector(
            preferred_premium_min=self.preferred_premium_min,
            preferred_premium_max=self.preferred_premium_max,
            max_capital_deployment_pct=self.capital_deployment_cap_pct,
            max_bid_ask_spread=self.max_spread,
            default_lots=self.lots,
        )
        self.voting_engine = AIVotingEngine(required_approval_count=4)
        self.last_evaluation: Optional[AIMicroScalperEvaluation] = None

    def calculate_target_and_stop_points(
        self,
        quantity: Optional[int] = None,
        target_net_profit: Optional[float] = None,
        max_loss_per_trade: Optional[float] = None,
        roundtrip_charges: Optional[float] = None,
        slippage_points: Optional[float] = None,
    ) -> Dict[str, float]:
        """
        Dynamically calculate target and stop points based on net P&L formula:
        Net P&L = (Exit - Entry) * Qty - Roundtrip Charges - Slippage Cost
        Target Points = (Target Net Profit + Roundtrip Charges + Slippage Cost) / Qty
        Stop Points   = (Max Loss Budget - Roundtrip Charges - Slippage Cost) / Qty
        For 130 qty, ₹20 charges, ₹0.05 slippage:
          slip_cost = 2 * 0.05 * 130 = ₹13.00
          Target pts = (200 + 20 + 13) / 130 = 233 / 130 = 1.7923 pts
          Stop pts   = (300 - 20 - 13) / 130 = 267 / 130 = 2.0538 pts
        """
        qty = max(1, int(quantity if quantity is not None else self.quantity))
        t_net = float(target_net_profit if target_net_profit is not None else self.target_net_profit)
        l_max = float(max_loss_per_trade if max_loss_per_trade is not None else self.max_loss_per_trade)
        chg = float(roundtrip_charges if roundtrip_charges is not None else self.roundtrip_charges)
        slip = float(slippage_points if slippage_points is not None else self.slippage_points)

        slip_cost = (2.0 * slip * qty) if slip > 0 else 0.0

        target_pts = round((t_net + chg + slip_cost) / qty, 4)
        stop_pts = round((l_max - chg - slip_cost) / qty, 4)
        if stop_pts <= 0:
            stop_pts = 0.50

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
        """Check if datetime falls within 09:25 to 14:45 IST entry window."""
        ist_dt = dt.astimezone(IST)
        time_str = ist_dt.strftime("%H:%M")
        return self.entry_start_ist <= time_str <= self.entry_end_ist

    def is_force_exit_time(self, dt: datetime) -> bool:
        """Check if datetime is at or past 15:20 IST auto square-off."""
        ist_dt = dt.astimezone(IST)
        time_str = ist_dt.strftime("%H:%M")
        return time_str >= self.force_exit_ist

    def _extract_completed_5m_candles(
        self, completed_1m_candles: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Aggregate 1-minute candles into 5-minute candles anchored to 09:15 IST.
        Returns only COMPLETED 5-minute candles to eliminate look-ahead bias and repainting.
        """
        if not completed_1m_candles:
            return []

        agg_5m = aggregate_candles(completed_1m_candles, target_minutes=5)
        if not agg_5m:
            return []

        # Check if the last 5m bucket is fully completed by examining the latest 1m bar timestamp
        latest_1m = completed_1m_candles[-1]
        raw_ts = latest_1m["timestamp"]
        if isinstance(raw_ts, (int, float)):
            dt_utc = datetime.fromtimestamp(int(raw_ts), tz=timezone.utc)
        elif isinstance(raw_ts, datetime):
            dt_utc = raw_ts if raw_ts.tzinfo else raw_ts.replace(tzinfo=timezone.utc)
        elif isinstance(raw_ts, str):
            dt_utc = datetime.fromisoformat(raw_ts.replace("Z", "+00:00"))
        else:
            return agg_5m

        dt_ist = dt_utc.astimezone(IST)
        minute_of_day = dt_ist.hour * 60 + dt_ist.minute
        market_open_min = 555  # 09:15 IST

        if minute_of_day >= market_open_min:
            mins_from_open = minute_of_day - market_open_min
            # A 5m bar completes at minute 4, 9, 14, 19, 24, etc. from open (mins_from_open + 1) % 5 == 0
            if (mins_from_open + 1) % 5 == 0:
                # The latest 5m bar is fully completed
                return agg_5m
            else:
                # The latest 5m bar is still forming, return completed bars only
                return agg_5m[:-1] if len(agg_5m) > 1 else []
        else:
            if (minute_of_day + 1) % 5 == 0:
                return agg_5m
            return agg_5m[:-1] if len(agg_5m) > 1 else []

    def evaluate_completed_candle(
        self,
        completed_candles: List[Union[CandleData, Dict[str, Any]]],
        current_capital: Optional[float] = None,
        open_position: Optional[Dict[str, Any]] = None,
        daily_risk_status: Optional[Dict[str, Any]] = None,
        option_quotes: Optional[Dict[str, Dict[str, Any]]] = None,
        current_lot_size: Optional[int] = None,
        ablation_config: Optional[Dict[str, bool]] = None,
    ) -> Optional[AIMicroScalperEvaluation]:
        """
        Evaluate AI MICRO-SCALPER V1 on the latest completed NIFTY 50 1-minute candle.
        Ensures strict non-repainting rule:
          1. 5m Trend: EMA 20, EMA 50, VWAP, ADX 14 on completed 5m bars.
          2. 1m Entry: EMA 9, EMA 20, VWAP, RSI 14, ATR 14 on completed 1m bars.
          3. Pullback to EMA 9/20 zone and candle confirmation.
          4. Dynamic option selection (ATM / 1-strike ITM in ₹100–₹150 range).
          5. Five Deterministic AI Agents voting (>= 4 consensus, Risk Agent compulsory).
        """
        if not completed_candles or len(completed_candles) < 30:
            logger.debug(f"Insufficient completed 1m candles: {len(completed_candles)} / 30")
            return None

        # Convert candles to standard dicts
        dict_1m: List[Dict[str, Any]] = []
        for c in completed_candles:
            if isinstance(c, CandleData):
                dict_1m.append({
                    "timestamp": c.timestamp,
                    "open": float(c.open),
                    "high": float(c.high),
                    "low": float(c.low),
                    "close": float(c.close),
                    "volume": float(c.volume or 0.0),
                    "symbol": getattr(c, "symbol", "NIFTY 50"),
                })
            else:
                dict_1m.append({
                    "timestamp": c["timestamp"],
                    "open": float(c["open"]),
                    "high": float(c["high"]),
                    "low": float(c["low"]),
                    "close": float(c["close"]),
                    "volume": float(c.get("volume", 0.0) or 0.0),
                    "symbol": c.get("symbol", "NIFTY 50"),
                })

        latest_1m = dict_1m[-1]
        candle_ts = latest_1m["timestamp"]
        if isinstance(candle_ts, (int, float)):
            candle_dt = datetime.fromtimestamp(int(candle_ts), tz=timezone.utc)
        elif isinstance(candle_ts, str):
            candle_dt = datetime.fromisoformat(candle_ts.replace("Z", "+00:00"))
        elif isinstance(candle_ts, datetime):
            candle_dt = candle_ts if candle_ts.tzinfo else candle_ts.replace(tzinfo=timezone.utc)
        else:
            candle_dt = datetime.now(timezone.utc)

        time_ist = candle_dt.astimezone(IST).strftime("%H:%M")
        session_valid = self.is_within_trading_session(candle_dt)

        # 1-minute indicators
        closes_1m = [c["close"] for c in dict_1m]
        highs_1m = [c["high"] for c in dict_1m]
        lows_1m = [c["low"] for c in dict_1m]

        ema_1m_9_series = calculate_ema(closes_1m, period=9)
        ema_1m_20_series = calculate_ema(closes_1m, period=20)
        vwap_1m_series = calculate_session_vwap(dict_1m)
        rsi_1m_series = calculate_rsi(closes_1m, period=14)
        atr_1m_series = calculate_atr(highs_1m, lows_1m, closes_1m, period=14)

        ema_1m_9 = ema_1m_9_series[-1]
        ema_1m_20 = ema_1m_20_series[-1]
        vwap_1m = vwap_1m_series[-1]
        rsi_1m = rsi_1m_series[-1]
        atr_1m = atr_1m_series[-1]

        # 5-minute completed bars & indicators
        completed_5m = self._extract_completed_5m_candles(dict_1m)
        if not completed_5m or len(completed_5m) < 15:
            # Not enough 5m completed bars yet to establish trend
            logger.debug(f"Insufficient completed 5m candles: {len(completed_5m)} / 15")
            return None

        closes_5m = [c["close"] for c in completed_5m]
        highs_5m = [c["high"] for c in completed_5m]
        lows_5m = [c["low"] for c in completed_5m]

        ema_5m_20_series = calculate_ema(closes_5m, period=20)
        ema_5m_50_series = calculate_ema(closes_5m, period=50)
        vwap_5m_series = calculate_session_vwap(completed_5m)
        adx_5m_res = calculate_adx(highs_5m, lows_5m, closes_5m, period=14)

        ema_5m_20 = ema_5m_20_series[-1]
        ema_5m_50 = ema_5m_50_series[-1]
        vwap_5m = vwap_5m_series[-1]
        adx_5m = adx_5m_res["adx"][-1]
        plus_di_5m = adx_5m_res["plus_di"][-1]
        minus_di_5m = adx_5m_res["minus_di"][-1]

        latest_5m_bar = completed_5m[-1]
        close_5m = latest_5m_bar["close"]
        underlying_price = latest_1m["close"]

        # Pullback and Candle confirmation on 1m
        # For Bullish CE:
        # - 5m close > VWAP
        # - 5m EMA 20 > EMA 50
        # - 5m ADX >= 20
        # - 1m Pullback: current or previous 2 bars' low touched or dipped near EMA 9/20 zone
        # - Completed bullish 1m candle: close > open, close > ema_1m_9 and close > ema_1m_20
        bullish_5m_trend = (close_5m > vwap_5m) and (ema_5m_20 > ema_5m_50) and (adx_5m >= 20.0)

        # Check recent 3 1m bars for pullback to EMA 9/20
        recent_lows = lows_1m[-3:]
        recent_ema_high = [max(ema_1m_9_series[-i], ema_1m_20_series[-i]) for i in (3, 2, 1)]
        recent_ema_low = [min(ema_1m_9_series[-i], ema_1m_20_series[-i]) for i in (3, 2, 1)]
        bullish_pullback = any(
            (l <= h_ema * 1.0008) and (l >= l_ema * 0.9990)
            for l, h_ema, l_ema in zip(recent_lows, recent_ema_high, recent_ema_low)
        )
        bullish_candle_confirm = (
            latest_1m["close"] > latest_1m["open"] and
            latest_1m["close"] > ema_1m_9 and
            latest_1m["close"] > ema_1m_20
        )

        candidate_ce = bullish_5m_trend and bullish_pullback and bullish_candle_confirm

        # For Bearish PE:
        # - 5m close < VWAP
        # - 5m EMA 20 < EMA 50
        # - 5m ADX >= 20
        # - 1m Pullback: current or previous 2 bars' high touched or dipped near EMA 9/20 zone
        # - Completed bearish 1m candle: close < open, close < ema_1m_9 and close < ema_1m_20
        bearish_5m_trend = (close_5m < vwap_5m) and (ema_5m_20 < ema_5m_50) and (adx_5m >= 20.0)

        recent_highs = highs_1m[-3:]
        bearish_pullback = any(
            (h >= l_ema * 0.9992) and (h <= h_ema * 1.0010)
            for h, h_ema, l_ema in zip(recent_highs, recent_ema_high, recent_ema_low)
        )
        bearish_candle_confirm = (
            latest_1m["close"] < latest_1m["open"] and
            latest_1m["close"] < ema_1m_9 and
            latest_1m["close"] < ema_1m_20
        )

        candidate_pe = bearish_5m_trend and bearish_pullback and bearish_candle_confirm

        # Resolve capital and lot size
        cap_avail = float(current_capital if current_capital is not None else self.initial_capital)
        resolved_lot_size = int(
            current_lot_size
            if current_lot_size is not None
            else self.option_selector.resolve_lot_size()
        )
        qty = self.lots * resolved_lot_size

        # Risk state from daily risk status
        realized_daily_pnl = float(daily_risk_status.get("realized_net_pnl", 0.0)) if daily_risk_status else 0.0
        today_trade_count = int(daily_risk_status.get("trade_count", 0)) if daily_risk_status else 0
        consecutive_losses = int(daily_risk_status.get("consecutive_losses", 0)) if daily_risk_status else 0

        # Build context for AI Agents
        candles_5m_ctx = {
            "close": close_5m,
            "ema_20": ema_5m_20,
            "ema_50": ema_5m_50,
            "vwap": vwap_5m,
            "adx": adx_5m,
            "plus_di": plus_di_5m,
            "minus_di": minus_di_5m,
        }
        candles_1m_ctx = {
            "close": latest_1m["close"],
            "open": latest_1m["open"],
            "high": latest_1m["high"],
            "low": latest_1m["low"],
            "volume": latest_1m["volume"],
            "ema_9": ema_1m_9,
            "ema_20": ema_1m_20,
            "vwap": vwap_1m,
            "rsi": rsi_1m,
            "atr": atr_1m,
        }

        # Option selection & AI Voting
        signal = "NONE"
        is_buy_ce = False
        is_buy_pe = False
        target_contract_type = "NONE"
        selected_contract: Dict[str, Any] = {}
        target_pts = 0.0
        stop_pts = 0.0
        points_info: Dict[str, float] = {}
        voting_result: Optional[AIVotingResult] = None
        action_reason = "No trade setup confirmed"

        if candidate_ce or candidate_pe:
            opt_type = "CE" if candidate_ce else "PE"
            selected_contract = self.option_selector.select_contract(
                spot_price=underlying_price,
                option_type=opt_type,
                quotes_map=option_quotes,
                available_capital=cap_avail,
                lots=self.lots,
                lot_size=resolved_lot_size,
                estimated_charges=self.roundtrip_charges,
            )

            # Calculate dynamic target & stop points
            points_info = self.calculate_target_and_stop_points(
                quantity=qty,
                slippage_points=self.slippage_points,
            )
            target_pts = points_info["target_points"]
            stop_pts = points_info["stop_points"]

            # Run AI Voting Engine
            voting_result = self.voting_engine.evaluate(
                signal_type="BUY_CE" if candidate_ce else "BUY_PE",
                candles_5m=candles_5m_ctx,
                candles_1m=candles_1m_ctx,
                option_data=selected_contract,
                capital=cap_avail,
                daily_pnl=realized_daily_pnl,
                consecutive_losses=consecutive_losses,
                trade_count_today=today_trade_count,
                has_open_position=(open_position is not None),
                candle_time=candle_dt,
                target_points=target_pts,
                stop_points=stop_pts,
                daily_profit_target=self.daily_profit_target,
                daily_loss_limit=self.daily_loss_limit,
                max_trades_per_day=self.max_trades_per_day,
                max_consecutive_losses=self.max_consecutive_losses,
                ablation=ablation_config,
            )

            if voting_result.consensus_approved:
                if candidate_ce:
                    signal = "BUY_CE"
                    is_buy_ce = True
                    target_contract_type = "CE"
                else:
                    signal = "BUY_PE"
                    is_buy_pe = True
                    target_contract_type = "PE"
                action_reason = (
                    f"AI Consensus APPROVED ({voting_result.approved_count}/5 votes). "
                    f"Contract: {selected_contract.get('symbol')} @ ₹{selected_contract.get('last_price', 0.0):.2f}. "
                    f"Target: +{target_pts:.2f} pts (₹{self.target_net_profit}), SL: -{stop_pts:.2f} pts (₹{self.max_loss_per_trade})"
                )
            else:
                action_reason = f"AI Consensus REJECTED ({voting_result.approved_count}/5 votes): {voting_result.rejection_reason}"
        else:
            if not session_valid:
                action_reason = f"Outside trading session window ({self.entry_start_ist} - {self.entry_end_ist} IST)"
            elif not (bullish_5m_trend or bearish_5m_trend):
                if adx_5m < 20.0:
                    action_reason = f"5m Trend Neutral/Sideways (ADX={adx_5m:.1f} < 20)"
                else:
                    action_reason = f"5m Trend Neutral (Close={close_5m:.1f}, VWAP={vwap_5m:.1f}, EMA20={ema_5m_20:.1f}, EMA50={ema_5m_50:.1f})"
            elif bullish_5m_trend and not bullish_pullback:
                action_reason = "Bullish 5m trend active, but no 1m pullback to EMA 9/20 zone"
            elif bullish_5m_trend and not bullish_candle_confirm:
                action_reason = "Bullish 5m trend & pullback active, but completed 1m candle failed bullish confirmation"
            elif bearish_5m_trend and not bearish_pullback:
                action_reason = "Bearish 5m trend active, but no 1m pullback to EMA 9/20 zone"
            elif bearish_5m_trend and not bearish_candle_confirm:
                action_reason = "Bearish 5m trend & pullback active, but completed 1m candle failed bearish confirmation"

        # Assemble evaluation result
        eval_result = AIMicroScalperEvaluation(
            timestamp=datetime.now(timezone.utc),
            candle_time=candle_dt,
            symbol=latest_1m.get("symbol", "NIFTY 50"),
            underlying_price=underlying_price,
            time_ist=time_ist,
            session_valid=session_valid,
            ema_5m_20=round(ema_5m_20, 2),
            ema_5m_50=round(ema_5m_50, 2),
            vwap_5m=round(vwap_5m, 2),
            adx_5m=round(adx_5m, 2),
            ema_1m_9=round(ema_1m_9, 2),
            ema_1m_20=round(ema_1m_20, 2),
            vwap_1m=round(vwap_1m, 2),
            rsi_1m=round(rsi_1m, 2),
            atr_1m=round(atr_1m, 2),
            signal=signal,
            is_buy_ce=is_buy_ce,
            is_buy_pe=is_buy_pe,
            is_buy=(is_buy_ce or is_buy_pe),
            target_contract_type=target_contract_type,
            contract_symbol=selected_contract.get("symbol"),
            contract_strike=selected_contract.get("strike"),
            contract_expiry=selected_contract.get("expiry"),
            contract_premium=float(selected_contract.get("last_price", 0.0) or 0.0),
            is_itm=bool(selected_contract.get("is_itm", False)),
            spread=float(selected_contract.get("spread", 0.0) or 0.0),
            lots=self.lots,
            lot_size=resolved_lot_size,
            quantity=qty,
            target_points=target_pts,
            stop_points=stop_pts,
            theoretical_target_net=self.target_net_profit,
            theoretical_max_loss=self.max_loss_per_trade,
            capital_required=float(selected_contract.get("total_purchase_cost", 0.0) or 0.0),
            capital_available=cap_avail,
            capital_ratio=float(selected_contract.get("capital_utilization_pct", 0.0) or 0.0),
            agent_votes=voting_result.votes if voting_result else {},
            voting_result=voting_result.to_dict() if voting_result else None,
            action_reason=action_reason,
            strategy_id="AI_MICRO_SCALPER_V1",
        )

        self.last_evaluation = eval_result
        return eval_result

    def get_config_dict(self) -> Dict[str, Any]:
        """Return strategy configuration dictionary."""
        pts_info = self.calculate_target_and_stop_points()
        return {
            "strategy_id": "AI_MICRO_SCALPER_V1",
            "strategy_name": "NEXTRADE AI MICRO-SCALPER V1",
            "underlying": "NIFTY 50",
            "timeframe": "1m (with 5m Trend)",
            "initial_capital": self.initial_capital,
            "lots": self.lots,
            "lot_size": self.lot_size,
            "quantity": self.quantity,
            "capital_deployment_cap_pct": self.capital_deployment_cap_pct,
            "preferred_premium_min": self.preferred_premium_min,
            "preferred_premium_max": self.preferred_premium_max,
            "target_net_profit": self.target_net_profit,
            "max_loss_per_trade": self.max_loss_per_trade,
            "daily_profit_target": self.daily_profit_target,
            "daily_loss_limit": self.daily_loss_limit,
            "max_trades_per_day": self.max_trades_per_day,
            "max_consecutive_losses": self.max_consecutive_losses,
            "max_holding_time_minutes": self.max_holding_time_minutes,
            "entry_start_ist": self.entry_start_ist,
            "entry_end_ist": self.entry_end_ist,
            "force_exit_ist": self.force_exit_ist,
            "roundtrip_charges": self.roundtrip_charges,
            "max_spread": self.max_spread,
            "slippage_points": self.slippage_points,
            "target_points": pts_info["target_points"],
            "stop_points": pts_info["stop_points"],
            "operating_mode": "PAPER_TRADING_ONLY",
        }
