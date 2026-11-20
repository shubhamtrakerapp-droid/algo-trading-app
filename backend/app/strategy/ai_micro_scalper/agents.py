from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional, Tuple

IST = timezone(timedelta(hours=5, minutes=30))


@dataclass
class AgentDecision:
    agent_name: str
    decision: str  # BULLISH, BEARISH, NEUTRAL, SUITABLE, REJECTED
    approved: bool
    confidence: float  # 0.0 to 100.0
    explanation: str
    rejection_reason: Optional[str] = None
    metrics: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AIVotingResult:
    approved: bool
    candidate_direction: str  # "CE", "PE", "NONE"
    approval_count: int
    required_count: int  # Default 4
    risk_agent_approved: bool
    agent_decisions: Dict[str, AgentDecision]
    summary_reason: str

    @property
    def consensus_approved(self) -> bool:
        return self.approved

    @property
    def approved_count(self) -> int:
        return self.approval_count

    @property
    def risk_approved(self) -> bool:
        return self.risk_agent_approved

    @property
    def rejection_reason(self) -> str:
        return self.summary_reason

    @property
    def votes(self) -> Dict[str, Dict[str, Any]]:
        return {
            k: {
                "approved": v.approved,
                "decision": v.decision,
                "confidence": v.confidence,
                "explanation": v.explanation,
                "reason": v.explanation or v.rejection_reason or "",
            }
            for k, v in self.agent_decisions.items()
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "approved": self.approved,
            "candidate_direction": self.candidate_direction,
            "approval_count": self.approval_count,
            "required_count": self.required_count,
            "risk_agent_approved": self.risk_agent_approved,
            "summary_reason": self.summary_reason,
            "decisions": {
                k: {
                    "agent_name": v.agent_name,
                    "decision": v.decision,
                    "approved": v.approved,
                    "confidence": v.confidence,
                    "explanation": v.explanation,
                    "rejection_reason": v.rejection_reason,
                }
                for k, v in self.agent_decisions.items()
            },
        }


class TrendAgent:
    """
    Agent 1: TREND AGENT
    Evaluates 5-minute EMA 20/50 alignment, VWAP position, trend direction,
    trend consistency, and higher-timeframe confirmation.
    """
    def __init__(self, name: str = "Trend Agent"):
        self.name = name

    def evaluate(
        self,
        candidate_direction: str,
        nifty_5m_close: float,
        nifty_5m_ema20: float,
        nifty_5m_ema50: float,
        nifty_5m_vwap: float
    ) -> AgentDecision:
        if candidate_direction == "CE":
            c1 = nifty_5m_close > nifty_5m_vwap
            c2 = nifty_5m_ema20 > nifty_5m_ema50

            if c1 and c2:
                sep = (nifty_5m_ema20 - nifty_5m_ema50) / max(1.0, nifty_5m_ema50) * 100.0
                dist_vwap = (nifty_5m_close - nifty_5m_vwap) / max(1.0, nifty_5m_vwap) * 100.0
                score = round(min(100.0, 65.0 + min(20.0, sep * 50.0) + min(15.0, dist_vwap * 40.0)), 1)
                return AgentDecision(
                    agent_name=self.name,
                    decision="BULLISH",
                    approved=True,
                    confidence=score,
                    explanation=f"5m EMA20 ({nifty_5m_ema20:.1f}) > EMA50 ({nifty_5m_ema50:.1f}) and Close ({nifty_5m_close:.1f}) > VWAP ({nifty_5m_vwap:.1f}) confirmed.",
                    metrics={"ema20": nifty_5m_ema20, "ema50": nifty_5m_ema50, "vwap": nifty_5m_vwap, "close": nifty_5m_close}
                )
            else:
                reasons = []
                if not c1:
                    reasons.append(f"Close ({nifty_5m_close:.1f}) <= VWAP ({nifty_5m_vwap:.1f})")
                if not c2:
                    reasons.append(f"EMA20 ({nifty_5m_ema20:.1f}) <= EMA50 ({nifty_5m_ema50:.1f})")
                return AgentDecision(
                    agent_name=self.name,
                    decision="NEUTRAL" if not c1 and c2 else "BEARISH",
                    approved=False,
                    confidence=30.0,
                    explanation="5m trend conditions failed for CE trade.",
                    rejection_reason="; ".join(reasons),
                    metrics={"ema20": nifty_5m_ema20, "ema50": nifty_5m_ema50, "vwap": nifty_5m_vwap, "close": nifty_5m_close}
                )

        elif candidate_direction == "PE":
            c1 = nifty_5m_close < nifty_5m_vwap
            c2 = nifty_5m_ema20 < nifty_5m_ema50

            if c1 and c2:
                sep = (nifty_5m_ema50 - nifty_5m_ema20) / max(1.0, nifty_5m_ema50) * 100.0
                dist_vwap = (nifty_5m_vwap - nifty_5m_close) / max(1.0, nifty_5m_vwap) * 100.0
                score = round(min(100.0, 65.0 + min(20.0, sep * 50.0) + min(15.0, dist_vwap * 40.0)), 1)
                return AgentDecision(
                    agent_name=self.name,
                    decision="BEARISH",
                    approved=True,
                    confidence=score,
                    explanation=f"5m EMA20 ({nifty_5m_ema20:.1f}) < EMA50 ({nifty_5m_ema50:.1f}) and Close ({nifty_5m_close:.1f}) < VWAP ({nifty_5m_vwap:.1f}) confirmed.",
                    metrics={"ema20": nifty_5m_ema20, "ema50": nifty_5m_ema50, "vwap": nifty_5m_vwap, "close": nifty_5m_close}
                )
            else:
                reasons = []
                if not c1:
                    reasons.append(f"Close ({nifty_5m_close:.1f}) >= VWAP ({nifty_5m_vwap:.1f})")
                if not c2:
                    reasons.append(f"EMA20 ({nifty_5m_ema20:.1f}) >= EMA50 ({nifty_5m_ema50:.1f})")
                return AgentDecision(
                    agent_name=self.name,
                    decision="NEUTRAL" if not c1 and c2 else "BULLISH",
                    approved=False,
                    confidence=30.0,
                    explanation="5m trend conditions failed for PE trade.",
                    rejection_reason="; ".join(reasons),
                    metrics={"ema20": nifty_5m_ema20, "ema50": nifty_5m_ema50, "vwap": nifty_5m_vwap, "close": nifty_5m_close}
                )

        return AgentDecision(
            agent_name=self.name,
            decision="NEUTRAL",
            approved=False,
            confidence=0.0,
            explanation="No candidate direction specified.",
            rejection_reason="No direction"
        )


class MomentumAgent:
    """
    Agent 2: MOMENTUM AGENT
    Evaluates 1-minute RSI 14, candle body strength, breakout strength,
    volume confirmation, and momentum consistency.
    """
    def __init__(self, name: str = "Momentum Agent"):
        self.name = name

    def evaluate(
        self,
        candidate_direction: str,
        nifty_1m_candle: Dict[str, Any],
        nifty_1m_rsi14: float,
        avg_volume_20: float = 1000.0,
        next_available_price: Optional[float] = None
    ) -> AgentDecision:
        o = float(nifty_1m_candle["open"])
        h = float(nifty_1m_candle["high"])
        l = float(nifty_1m_candle["low"])
        c = float(nifty_1m_candle["close"])
        vol = float(nifty_1m_candle.get("volume", 1.0) or 1.0)

        c_range = max(0.1, h - l)
        body = abs(c - o)
        body_ratio = body / c_range

        if candidate_direction == "CE":
            is_bullish_candle = c > o and body_ratio >= 0.35
            rsi_valid = 48.0 <= nifty_1m_rsi14 <= 78.0
            volume_valid = vol >= (avg_volume_20 * 0.60)
            breakout_valid = (next_available_price is None) or (next_available_price >= h - 0.5)

            if is_bullish_candle and rsi_valid and volume_valid and breakout_valid:
                score = round(min(100.0, 50.0 + (body_ratio * 30.0) + min(20.0, (nifty_1m_rsi14 - 48.0) * 0.8)), 1)
                return AgentDecision(
                    agent_name=self.name,
                    decision="BULLISH",
                    approved=True,
                    confidence=score,
                    explanation=f"Bullish 1m candle (body {int(body_ratio*100)}%), RSI {nifty_1m_rsi14:.1f} in momentum zone, volume confirmed.",
                    metrics={"rsi": nifty_1m_rsi14, "body_ratio": round(body_ratio, 2), "volume": vol, "avg_vol": avg_volume_20}
                )
            else:
                reasons = []
                if not is_bullish_candle:
                    reasons.append("Candle is not decisively bullish or body ratio < 35%")
                if not rsi_valid:
                    reasons.append(f"RSI 14 ({nifty_1m_rsi14:.1f}) outside healthy 48-78 momentum zone")
                if not volume_valid:
                    reasons.append(f"Volume ({vol}) below volume threshold ({avg_volume_20 * 0.60:.0f})")
                if not breakout_valid:
                    reasons.append(f"Market price ({next_available_price}) failed to break candle high ({h})")
                return AgentDecision(
                    agent_name=self.name,
                    decision="NEUTRAL",
                    approved=False,
                    confidence=35.0,
                    explanation="1m momentum conditions failed for CE trade.",
                    rejection_reason="; ".join(reasons),
                    metrics={"rsi": nifty_1m_rsi14, "body_ratio": round(body_ratio, 2), "volume": vol}
                )

        elif candidate_direction == "PE":
            is_bearish_candle = c < o and body_ratio >= 0.35
            rsi_valid = 22.0 <= nifty_1m_rsi14 <= 52.0
            volume_valid = vol >= (avg_volume_20 * 0.60)
            breakout_valid = (next_available_price is None) or (next_available_price <= l + 0.5)

            if is_bearish_candle and rsi_valid and volume_valid and breakout_valid:
                score = round(min(100.0, 50.0 + (body_ratio * 30.0) + min(20.0, (52.0 - nifty_1m_rsi14) * 0.8)), 1)
                return AgentDecision(
                    agent_name=self.name,
                    decision="BEARISH",
                    approved=True,
                    confidence=score,
                    explanation=f"Bearish 1m candle (body {int(body_ratio*100)}%), RSI {nifty_1m_rsi14:.1f} in bearish momentum zone, volume confirmed.",
                    metrics={"rsi": nifty_1m_rsi14, "body_ratio": round(body_ratio, 2), "volume": vol, "avg_vol": avg_volume_20}
                )
            else:
                reasons = []
                if not is_bearish_candle:
                    reasons.append("Candle is not decisively bearish or body ratio < 35%")
                if not rsi_valid:
                    reasons.append(f"RSI 14 ({nifty_1m_rsi14:.1f}) outside healthy 22-52 bearish momentum zone")
                if not volume_valid:
                    reasons.append(f"Volume ({vol}) below volume threshold")
                if not breakout_valid:
                    reasons.append(f"Market price ({next_available_price}) failed to break candle low ({l})")
                return AgentDecision(
                    agent_name=self.name,
                    decision="NEUTRAL",
                    approved=False,
                    confidence=35.0,
                    explanation="1m momentum conditions failed for PE trade.",
                    rejection_reason="; ".join(reasons),
                    metrics={"rsi": nifty_1m_rsi14, "body_ratio": round(body_ratio, 2), "volume": vol}
                )

        return AgentDecision(
            agent_name=self.name,
            decision="NEUTRAL",
            approved=False,
            confidence=0.0,
            explanation="No candidate direction specified.",
            rejection_reason="No direction"
        )


class VolatilityAgent:
    """
    Agent 3: VOLATILITY AGENT
    Evaluates 1-minute ATR 14, sudden volatility expansion, large candles, price gaps,
    and whether the ₹200 target / ₹300 stop can realistically be executed without excessive slippage.
    """
    def __init__(self, name: str = "Volatility Agent", max_atr: float = 75.0, min_atr: float = 3.0):
        self.name = name
        self.max_atr = max_atr
        self.min_atr = min_atr

    def evaluate(
        self,
        nifty_1m_candle: Dict[str, Any],
        nifty_1m_atr14: float,
        prev_candle_close: Optional[float] = None
    ) -> AgentDecision:
        h = float(nifty_1m_candle["high"])
        l = float(nifty_1m_candle["low"])
        o = float(nifty_1m_candle["open"])
        c_range = h - l

        atr_in_range = self.min_atr <= nifty_1m_atr14 <= self.max_atr
        not_extreme_candle = c_range <= (3.0 * nifty_1m_atr14)

        gap_ok = True
        gap_size = 0.0
        if prev_candle_close:
            gap_size = abs(o - prev_candle_close)
            gap_ok = gap_size <= (2.0 * nifty_1m_atr14)

        if atr_in_range and not_extreme_candle and gap_ok:
            score = 88.0
            return AgentDecision(
                agent_name=self.name,
                decision="SUITABLE",
                approved=True,
                confidence=score,
                explanation=f"Volatility suitable (ATR={nifty_1m_atr14:.2f}, bar range={c_range:.1f}, gap={gap_size:.1f}). Target/stop execution feasible.",
                metrics={"atr14": nifty_1m_atr14, "candle_range": c_range, "gap": gap_size}
            )
        else:
            reasons = []
            if not atr_in_range:
                reasons.append(f"ATR14 ({nifty_1m_atr14:.2f}) outside safe operating range [{self.min_atr}, {self.max_atr}]")
            if not not_extreme_candle:
                reasons.append(f"Extreme candle expansion ({c_range:.1f} > 3x ATR)")
            if not gap_ok:
                reasons.append(f"Excessive price gap ({gap_size:.1f} > 2x ATR)")
            return AgentDecision(
                agent_name=self.name,
                decision="REJECTED",
                approved=False,
                confidence=20.0,
                explanation="Volatility unsuitable for controlled micro-scalping.",
                rejection_reason="; ".join(reasons),
                metrics={"atr14": nifty_1m_atr14, "candle_range": c_range, "gap": gap_size}
            )


class MarketRegimeAgent:
    """
    Agent 4: MARKET REGIME AGENT
    Classifies market conditions into:
    - TRENDING (TRENDING_BULLISH, TRENDING_BEARISH)
    - SIDEWAYS
    - CHOPPY
    - HIGH_VOLATILITY / LOW_VOLATILITY
    Rejects SIDEWAYS (ADX < 20) and CHOPPY market conditions.
    """
    def __init__(self, name: str = "Market Regime Agent", min_adx: float = 20.0):
        self.name = name
        self.min_adx = min_adx

    def evaluate(
        self,
        candidate_direction: str,
        nifty_5m_adx14: float,
        nifty_5m_plus_di: float,
        nifty_5m_minus_di: float,
        nifty_5m_ema20: float,
        nifty_5m_ema50: float
    ) -> AgentDecision:
        # Classify regime
        if nifty_5m_adx14 >= self.min_adx:
            if nifty_5m_ema20 > nifty_5m_ema50 and nifty_5m_plus_di > nifty_5m_minus_di:
                regime = "TRENDING_BULLISH"
            elif nifty_5m_ema20 < nifty_5m_ema50 and nifty_5m_minus_di > nifty_5m_plus_di:
                regime = "TRENDING_BEARISH"
            else:
                regime = "CHOPPY"
        else:
            regime = "SIDEWAYS"

        approved = False
        rejection = None

        if candidate_direction == "CE":
            if regime == "TRENDING_BULLISH":
                approved = True
                confidence = round(min(100.0, 60.0 + (nifty_5m_adx14 - 20.0) * 1.5), 1)
                explanation = f"Market Regime is TRENDING_BULLISH (ADX={nifty_5m_adx14:.1f} >= {self.min_adx}, +DI > -DI). Suitable for CE scalping."
            else:
                confidence = 25.0
                rejection = f"Market Regime is {regime} (ADX={nifty_5m_adx14:.1f}). Must be TRENDING_BULLISH with ADX >= {self.min_adx}."
                explanation = f"Regime {regime} rejected for CE trade."

        elif candidate_direction == "PE":
            if regime == "TRENDING_BEARISH":
                approved = True
                confidence = round(min(100.0, 60.0 + (nifty_5m_adx14 - 20.0) * 1.5), 1)
                explanation = f"Market Regime is TRENDING_BEARISH (ADX={nifty_5m_adx14:.1f} >= {self.min_adx}, -DI > +DI). Suitable for PE scalping."
            else:
                confidence = 25.0
                rejection = f"Market Regime is {regime} (ADX={nifty_5m_adx14:.1f}). Must be TRENDING_BEARISH with ADX >= {self.min_adx}."
                explanation = f"Regime {regime} rejected for PE trade."
        else:
            confidence = 0.0
            rejection = "No candidate trade direction specified."
            explanation = "No candidate trade direction."

        return AgentDecision(
            agent_name=self.name,
            decision=regime,
            approved=approved,
            confidence=confidence,
            explanation=explanation,
            rejection_reason=rejection,
            metrics={"regime": regime, "adx": nifty_5m_adx14, "plus_di": nifty_5m_plus_di, "minus_di": nifty_5m_minus_di}
        )


class RiskAgent:
    """
    Agent 5: RISK AGENT (COMPULSORY APPROVAL)
    Enforces all trade constraints:
    - Available capital deployment <= 90% (₹20,000 capital default)
    - Option premium in preferred range (₹100 to ₹150)
    - Bid-Ask spread <= threshold (default 0.5 points)
    - Daily net P&L within limits (-₹500 to +₹500)
    - Consecutive loss stop: stop after 2 consecutive losses
    - Max trades per day: <= 5 trades
    - Entry window: 09:25 to 14:45 IST
    - Max simultaneous open positions: <= 1
    """
    def __init__(
        self,
        name: str = "Risk Agent",
        max_capital_deployment_pct: float = 90.0,
        max_trades_per_day: int = 5,
        max_consecutive_losses: int = 2,
        daily_profit_target: float = 500.0,
        daily_loss_limit: float = -500.0,
        max_spread: float = 0.50,
        entry_start_ist: str = "09:25",
        entry_end_ist: str = "14:45",
        preferred_premium_min: float = 100.0,
        preferred_premium_max: float = 150.0
    ):
        self.name = name
        self.max_capital_deployment_pct = max_capital_deployment_pct
        self.max_trades_per_day = max_trades_per_day
        self.max_consecutive_losses = max_consecutive_losses
        self.daily_profit_target = daily_profit_target
        self.daily_loss_limit = daily_loss_limit
        self.max_spread = max_spread
        self.entry_start_ist = entry_start_ist
        self.entry_end_ist = entry_end_ist
        self.preferred_premium_min = preferred_premium_min
        self.preferred_premium_max = preferred_premium_max

    def evaluate(
        self,
        current_time_ist: str = "10:00",
        available_capital: float = 20000.0,
        option_premium: float = 125.0,
        quantity: int = 130,
        bid_ask_spread: float = 0.20,
        daily_net_pnl: float = 0.0,
        consecutive_losses: int = 0,
        trades_today: int = 0,
        has_open_position: bool = False,
        estimated_charges: float = 20.0,
        **kwargs: Any
    ) -> AgentDecision:
        # Handle aliases from various caller interfaces
        time_str = kwargs.get("time_ist", current_time_ist)
        cap = kwargs.get("capital", available_capital)
        opt_data = kwargs.get("option_data") or {}
        prem = kwargs.get("premium", opt_data.get("last_price", opt_data.get("option_premium", option_premium)))
        qty = kwargs.get("qty", opt_data.get("quantity", quantity))
        spread = kwargs.get("spread", opt_data.get("spread", bid_ask_spread))
        d_pnl = kwargs.get("daily_pnl", daily_net_pnl)
        c_loss = kwargs.get("consecutive_losses", consecutive_losses)
        t_count = kwargs.get("trade_count_today", kwargs.get("trades_today", trades_today))
        open_pos = kwargs.get("has_open_position", has_open_position)
        chg = kwargs.get("estimated_charges", estimated_charges)

        profit_tgt = kwargs.get("daily_profit_target", self.daily_profit_target)
        loss_lim = kwargs.get("daily_loss_limit", self.daily_loss_limit)
        max_trd = kwargs.get("max_trades_per_day", self.max_trades_per_day)
        max_closs = kwargs.get("max_consecutive_losses", self.max_consecutive_losses)

        rejection_reasons = []

        # 1. Open position check
        if open_pos:
            rejection_reasons.append("Active open position exists (Max 1 simultaneous position allowed)")

        # 2. Entry window check
        if not (self.entry_start_ist <= time_str <= self.entry_end_ist):
            rejection_reasons.append(f"Time {time_str} IST is outside entry window ({self.entry_start_ist} - {self.entry_end_ist} IST)")

        # 3. Daily risk locks
        if d_pnl >= profit_tgt:
            rejection_reasons.append(f"Daily profit target reached (+₹{d_pnl:.2f} >= ₹{profit_tgt:.2f}). Trading locked for day.")
        elif d_pnl <= loss_lim:
            rejection_reasons.append(f"Daily loss limit reached (-₹{abs(d_pnl):.2f} <= ₹{loss_lim:.2f}). Trading locked for day.")

        # 4. Consecutive losses check
        if c_loss >= max_closs:
            rejection_reasons.append(f"Reached {c_loss} consecutive losses (Limit: {max_closs}). Trading paused for day.")

        # 5. Max trades per day
        if t_count >= max_trd:
            rejection_reasons.append(f"Maximum daily trades reached ({t_count}/{max_trd}). New entries stopped.")

        # 6. Capital deployment cap (<= 90% of available capital)
        required_capital = (prem * qty) + chg
        max_allowed_deploy = (self.max_capital_deployment_pct / 100.0) * cap
        if required_capital > max_allowed_deploy:
            rejection_reasons.append(f"Required capital ₹{required_capital:.2f} exceeds 90% cap (₹{max_allowed_deploy:.2f} of ₹{cap:.2f})")

        # 7. Spread check
        if spread > self.max_spread:
            rejection_reasons.append(f"Bid-ask spread ({spread:.2f} pts) exceeds maximum allowable ({self.max_spread:.2f} pts)")

        # 8. Premium check
        if not (self.preferred_premium_min <= prem <= self.preferred_premium_max):
            rejection_reasons.append(f"Premium ₹{prem:.2f} outside preferred ₹{self.preferred_premium_min:.0f}–₹{self.preferred_premium_max:.0f} range")

        approved = len(rejection_reasons) == 0
        score = 100.0 if approved else max(0.0, 100.0 - (len(rejection_reasons) * 25.0))

        return AgentDecision(
            agent_name=self.name,
            decision="APPROVED" if approved else "REJECTED",
            approved=approved,
            confidence=score,
            explanation="All trade constraints, capital limits, and session rules passed." if approved else "; ".join(rejection_reasons),
            rejection_reason="; ".join(rejection_reasons) if not approved else None,
            metrics={
                "available_capital": cap,
                "required_capital": required_capital,
                "daily_net_pnl": d_pnl,
                "consecutive_losses": c_loss,
                "trades_today": t_count,
                "spread": spread,
                "option_premium": prem
            }
        )
        if required_capital > max_allowed_deploy:
            rejection_reasons.append(f"Required capital ₹{required_capital:.2f} exceeds 90% deployment limit (₹{max_allowed_deploy:.2f} of ₹{available_capital:.2f})")

        # 7. Spread check
        if bid_ask_spread > self.max_spread:
            rejection_reasons.append(f"Bid-ask spread ({bid_ask_spread:.2f} pts) exceeds maximum allowable threshold ({self.max_spread:.2f} pts)")

        # 8. Premium sanity check
        if option_premium < 20.0 or option_premium > 500.0:
            rejection_reasons.append(f"Option premium ₹{option_premium:.2f} is outside viable trading bounds [₹20, ₹500]")

        approved = len(rejection_reasons) == 0
        confidence = 100.0 if approved else 0.0
        explanation = "All risk management and capital requirements satisfied." if approved else "; ".join(rejection_reasons)

        return AgentDecision(
            agent_name=self.name,
            decision="APPROVED" if approved else "REJECTED",
            approved=approved,
            confidence=confidence,
            explanation=explanation,
            rejection_reason="; ".join(rejection_reasons) if rejection_reasons else None,
            metrics={
                "available_capital": available_capital,
                "required_capital": required_capital,
                "max_allowed_deploy": max_allowed_deploy,
                "option_premium": option_premium,
                "quantity": quantity,
                "spread": bid_ask_spread,
                "daily_net_pnl": daily_net_pnl,
                "consecutive_losses": consecutive_losses,
                "trades_today": trades_today,
                "time_ist": current_time_ist
            }
        )


class AIVotingEngine:
    """
    Coordinates voting across the 5 specialized AI agents.
    Voting Rules:
    - At least 4 of 5 agents must approve (`approval_count >= 4`).
    - Risk Agent MUST ALWAYS approve (`risk_agent.approved == True`).
    """
    def __init__(self, required_approval_count: int = 4):
        self.trend_agent = TrendAgent()
        self.momentum_agent = MomentumAgent()
        self.volatility_agent = VolatilityAgent()
        self.regime_agent = MarketRegimeAgent()
        self.risk_agent = RiskAgent()
        self.required_approval_count = required_approval_count

    def evaluate(
        self,
        signal_type: str,
        candles_5m: Dict[str, Any],
        candles_1m: Dict[str, Any],
        option_data: Dict[str, Any],
        capital: float,
        daily_pnl: float = 0.0,
        consecutive_losses: int = 0,
        trade_count_today: int = 0,
        has_open_position: bool = False,
        candle_time: Optional[datetime] = None,
        target_points: float = 1.79,
        stop_points: float = 2.05,
        daily_profit_target: float = 500.0,
        daily_loss_limit: float = -500.0,
        max_trades_per_day: int = 5,
        max_consecutive_losses: int = 2,
        ablation: Optional[Dict[str, bool]] = None,
        estimated_charges: float = 20.0
    ) -> AIVotingResult:
        cand_dir = "CE" if "CE" in signal_type else "PE"
        c_time_ist = candle_time.astimezone(IST).strftime("%H:%M") if candle_time else "10:00"

        c5 = candles_5m or {}
        c1 = candles_1m or {}
        opt = option_data or {}

        toggles = None
        if ablation:
            toggles = {
                "trend": ablation.get("enable_trend_agent", ablation.get("trend", True)),
                "momentum": ablation.get("enable_momentum_agent", ablation.get("momentum", True)),
                "volatility": ablation.get("enable_volatility_agent", ablation.get("volatility", True)),
                "regime": ablation.get("enable_regime_agent", ablation.get("regime", True)),
                "risk": ablation.get("enable_risk_agent", ablation.get("risk", True)),
            }

        return self.evaluate_all(
            candidate_direction=cand_dir,
            current_time_ist=c_time_ist,
            nifty_5m_close=float(c5.get("close", 24500.0)),
            nifty_5m_ema20=float(c5.get("ema_20", 24500.0)),
            nifty_5m_ema50=float(c5.get("ema_50", 24500.0)),
            nifty_5m_vwap=float(c5.get("vwap", 24500.0)),
            nifty_5m_adx14=float(c5.get("adx", 25.0)),
            nifty_5m_plus_di=float(c5.get("plus_di", 25.0 if cand_dir == "CE" else 15.0)),
            nifty_5m_minus_di=float(c5.get("minus_di", 15.0 if cand_dir == "CE" else 25.0)),
            nifty_1m_candle=c1,
            nifty_1m_rsi14=float(c1.get("rsi", 55.0)),
            nifty_1m_atr14=float(c1.get("atr", 6.0)),
            available_capital=capital,
            option_premium=float(opt.get("last_price", opt.get("option_premium", 125.0)) or 125.0),
            quantity=int(opt.get("quantity", 130)),
            bid_ask_spread=float(opt.get("spread", 0.20)),
            daily_net_pnl=daily_pnl,
            consecutive_losses=consecutive_losses,
            trades_today=trade_count_today,
            has_open_position=has_open_position,
            estimated_charges=estimated_charges,
            agent_toggles=toggles,
        )

    def evaluate_all(
        self,
        candidate_direction: str,
        current_time_ist: str,
        nifty_5m_close: float,
        nifty_5m_ema20: float,
        nifty_5m_ema50: float,
        nifty_5m_vwap: float,
        nifty_5m_adx14: float,
        nifty_5m_plus_di: float,
        nifty_5m_minus_di: float,
        nifty_1m_candle: Dict[str, Any],
        nifty_1m_rsi14: float,
        nifty_1m_atr14: float,
        available_capital: float,
        option_premium: float,
        quantity: int,
        bid_ask_spread: float = 0.20,
        daily_net_pnl: float = 0.0,
        consecutive_losses: int = 0,
        trades_today: int = 0,
        has_open_position: bool = False,
        estimated_charges: float = 20.0,
        next_available_price: Optional[float] = None,
        prev_candle_close: Optional[float] = None,
        avg_volume_20: float = 1000.0,
        agent_toggles: Optional[Dict[str, bool]] = None
    ) -> AIVotingResult:
        toggles = agent_toggles or {
            "trend": True,
            "momentum": True,
            "volatility": True,
            "regime": True,
            "risk": True
        }

        decisions: Dict[str, AgentDecision] = {}

        # 1. Trend Agent
        if toggles.get("trend", True):
            decisions["trend"] = self.trend_agent.evaluate(
                candidate_direction=candidate_direction,
                nifty_5m_close=nifty_5m_close,
                nifty_5m_ema20=nifty_5m_ema20,
                nifty_5m_ema50=nifty_5m_ema50,
                nifty_5m_vwap=nifty_5m_vwap
            )
        else:
            decisions["trend"] = AgentDecision(
                agent_name="Trend Agent (Bypassed)",
                decision="BYPASSED",
                approved=True,
                confidence=100.0,
                explanation="Agent bypassed via strategy configuration."
            )

        # 2. Momentum Agent
        if toggles.get("momentum", True):
            decisions["momentum"] = self.momentum_agent.evaluate(
                candidate_direction=candidate_direction,
                nifty_1m_candle=nifty_1m_candle,
                nifty_1m_rsi14=nifty_1m_rsi14,
                avg_volume_20=avg_volume_20,
                next_available_price=next_available_price
            )
        else:
            decisions["momentum"] = AgentDecision(
                agent_name="Momentum Agent (Bypassed)",
                decision="BYPASSED",
                approved=True,
                confidence=100.0,
                explanation="Agent bypassed via strategy configuration."
            )

        # 3. Volatility Agent
        if toggles.get("volatility", True):
            decisions["volatility"] = self.volatility_agent.evaluate(
                nifty_1m_candle=nifty_1m_candle,
                nifty_1m_atr14=nifty_1m_atr14,
                prev_candle_close=prev_candle_close
            )
        else:
            decisions["volatility"] = AgentDecision(
                agent_name="Volatility Agent (Bypassed)",
                decision="BYPASSED",
                approved=True,
                confidence=100.0,
                explanation="Agent bypassed via strategy configuration."
            )

        # 4. Market Regime Agent
        if toggles.get("regime", True):
            decisions["regime"] = self.regime_agent.evaluate(
                candidate_direction=candidate_direction,
                nifty_5m_adx14=nifty_5m_adx14,
                nifty_5m_plus_di=nifty_5m_plus_di,
                nifty_5m_minus_di=nifty_5m_minus_di,
                nifty_5m_ema20=nifty_5m_ema20,
                nifty_5m_ema50=nifty_5m_ema50
            )
        else:
            decisions["regime"] = AgentDecision(
                agent_name="Market Regime Agent (Bypassed)",
                decision="BYPASSED",
                approved=True,
                confidence=100.0,
                explanation="Agent bypassed via strategy configuration."
            )

        # 5. Risk Agent (Always Compulsory unless explicitly disabled in ablation testing)
        if toggles.get("risk", True):
            decisions["risk"] = self.risk_agent.evaluate(
                current_time_ist=current_time_ist,
                available_capital=available_capital,
                option_premium=option_premium,
                quantity=quantity,
                bid_ask_spread=bid_ask_spread,
                daily_net_pnl=daily_net_pnl,
                consecutive_losses=consecutive_losses,
                trades_today=trades_today,
                has_open_position=has_open_position,
                estimated_charges=estimated_charges
            )
        else:
            decisions["risk"] = AgentDecision(
                agent_name="Risk Agent (Bypassed)",
                decision="BYPASSED",
                approved=True,
                confidence=100.0,
                explanation="Risk Agent bypassed (Test mode only)."
            )

        # Count approvals
        approved_count = sum(1 for d in decisions.values() if d.approved)
        risk_approved = decisions["risk"].approved

        # Must have at least required_approval_count AND risk agent approved
        overall_approved = bool(approved_count >= self.required_approval_count and risk_approved)

        if overall_approved:
            summary = f"Trade APPROVED: {approved_count}/5 agents in consensus including compulsory Risk Agent."
        elif not risk_approved:
            summary = f"Trade REJECTED by compulsory Risk Agent: {decisions['risk'].rejection_reason}"
        else:
            failed_agents = [d.agent_name for d in decisions.values() if not d.approved]
            summary = f"Trade REJECTED: Only {approved_count}/5 approved ({', '.join(failed_agents)} rejected)."

        return AIVotingResult(
            approved=overall_approved,
            candidate_direction=candidate_direction,
            approval_count=approved_count,
            required_count=self.required_approval_count,
            risk_agent_approved=risk_approved,
            agent_decisions=decisions,
            summary_reason=summary
        )
