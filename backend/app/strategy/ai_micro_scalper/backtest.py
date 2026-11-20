import json
import logging
import math
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional, Tuple

from backend.app.adapters.base import CandleData
from backend.app.paper.charges import ChargesCalculator
from backend.app.database import AsyncSessionLocal
from backend.app.models import BacktestRun, BacktestTrade
from backend.app.analytics.calendar import parse_trade_datetime_ist
from backend.app.strategy.ai_micro_scalper.strategy import (
    AIMicroScalperStrategy,
    AIMicroScalperEvaluation,
)

logger = logging.getLogger("nextrade.backtest.ai_micro_scalper")

IST = timezone(timedelta(hours=5, minutes=30))


def is_valid_trading_session_bar(ts_val: Any) -> bool:
    """Validate bar falls within regular NSE trading hours (09:15 to 15:30 IST, weekdays only)."""
    dt_ist = parse_trade_datetime_ist(ts_val)
    if not dt_ist or dt_ist.weekday() >= 5:
        return False
    time_str = dt_ist.strftime("%H:%M")
    return "09:15" <= time_str <= "15:30"


class AIMicroScalperBacktestEngine:
    """
    Dedicated Backtest Engine for NEXTRADE AI MICRO-SCALPER V1.
    Strictly follows all quantitative, risk, and non-repainting rules:
      - 5m Trend + 1m Entry on completed bars only.
      - 5 Explainable Deterministic AI Agents.
      - Dual Execution Modes: TRIGGER_PRICE and REALISTIC (bid/ask, slippage, conservative stop-first).
      - Strict Rupee-based Targets: ₹200 net target, ₹300 max net loss.
      - Intraday Risk Locks: +₹500 daily profit, -₹500 daily loss, max 5 trades/day, 2 consecutive loss pause.
      - 90% Capital Deployment Cap on ₹20,000 starting capital.
      - Missing data recorded as MISSING_DATA (never fabricated in real-market mode).
      - Agent Performance Ablation (Experiments A to G).
      - Chronological Train (60%), Validation (20%), and Test (20%) data splits.
    """

    def __init__(
        self,
        initial_capital: float = 20000.0,
        lots: int = 2,
        lot_size: int = 65,
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
        execution_mode: str = "TRIGGER_PRICE",
    ):
        self.initial_capital = float(initial_capital)
        self.lots = int(lots)
        self.lot_size = int(lot_size)
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
        self.execution_mode = execution_mode

        self.strategy = AIMicroScalperStrategy(
            initial_capital=self.initial_capital,
            lots=self.lots,
            lot_size=self.lot_size,
            preferred_premium_min=self.preferred_premium_min,
            preferred_premium_max=self.preferred_premium_max,
            target_net_profit=self.target_net_profit,
            max_loss_per_trade=self.max_loss_per_trade,
            daily_profit_target=self.daily_profit_target,
            daily_loss_limit=self.daily_loss_limit,
            max_trades_per_day=self.max_trades_per_day,
            max_consecutive_losses=self.max_consecutive_losses,
            max_holding_time_minutes=self.max_holding_time_minutes,
            entry_start_ist=self.entry_start_ist,
            entry_end_ist=self.entry_end_ist,
            force_exit_ist=self.force_exit_ist,
            roundtrip_charges=self.roundtrip_charges,
            max_spread=self.max_spread,
            slippage_points=self.slippage_points,
        )
        self.charges_calc = ChargesCalculator(
            entry_charge_per_order=self.roundtrip_charges / 2.0,
            exit_charge_per_order=self.roundtrip_charges / 2.0,
        )

    async def run_backtest(
        self,
        nifty_candles: List[Dict[str, Any]],
        option_candles_ce: Optional[List[Dict[str, Any]]] = None,
        option_candles_pe: Optional[List[Dict[str, Any]]] = None,
        data_source: str = "KOTAK_NEO_HISTORICAL",
        execution_mode: Optional[str] = None,
        ablation_config: Optional[Dict[str, bool]] = None,
        split_type: Optional[str] = None,  # "TRAIN", "VALIDATION", "TEST", or None (ALL)
        save_to_db: bool = True,
    ) -> Dict[str, Any]:
        """
        Execute full historical backtest of AI MICRO-SCALPER V1.
        """
        exec_mode = execution_mode or self.execution_mode

        # Quarantine candles outside regular market hours
        valid_nifty = [c for c in nifty_candles if is_valid_trading_session_bar(c.get("timestamp"))]
        if len(valid_nifty) < 35:
            return {
                "error": f"Insufficient valid 1-minute NIFTY candles ({len(valid_nifty)} < 35 required)."
            }

        # Build fast timestamp index for option candles
        ce_map: Dict[str, Dict[str, Any]] = {}
        for c in (option_candles_ce or []):
            if is_valid_trading_session_bar(c.get("timestamp")):
                dt_ist = parse_trade_datetime_ist(c.get("timestamp"))
                if dt_ist:
                    ce_map[dt_ist.isoformat()] = c

        pe_map: Dict[str, Dict[str, Any]] = {}
        for c in (option_candles_pe or []):
            if is_valid_trading_session_bar(c.get("timestamp")):
                dt_ist = parse_trade_datetime_ist(c.get("timestamp"))
                if dt_ist:
                    pe_map[dt_ist.isoformat()] = c

        # Sort NIFTY candles chronologically
        valid_nifty.sort(key=lambda c: parse_trade_datetime_ist(c.get("timestamp")) or datetime.min.replace(tzinfo=IST))

        # Handle chronological train/validation/test split
        if split_type in ("TRAIN", "VALIDATION", "TEST"):
            # Group candles by IST date
            date_groups: Dict[str, List[Dict[str, Any]]] = {}
            for c in valid_nifty:
                d_ist = parse_trade_datetime_ist(c.get("timestamp"))
                if d_ist:
                    d_str = d_ist.strftime("%Y-%m-%d")
                    date_groups.setdefault(d_str, []).append(c)

            sorted_dates = sorted(date_groups.keys())
            total_days = len(sorted_dates)
            train_cut = max(1, int(total_days * 0.60))
            val_cut = max(train_cut + 1, int(total_days * 0.80))

            if split_type == "TRAIN":
                target_dates = set(sorted_dates[:train_cut])
            elif split_type == "VALIDATION":
                target_dates = set(sorted_dates[train_cut:val_cut])
            else:  # TEST
                target_dates = set(sorted_dates[val_cut:])

            valid_nifty = [c for c in valid_nifty if parse_trade_datetime_ist(c.get("timestamp")).strftime("%Y-%m-%d") in target_dates]
            if len(valid_nifty) < 35:
                return {
                    "error": f"Insufficient candles in split '{split_type}' ({len(valid_nifty)} candles)."
                }

        # Initialize tracking state
        trades: List[Dict[str, Any]] = []
        equity = self.initial_capital
        peak_equity = equity
        max_drawdown = 0.0
        equity_curve = [{"trade": 0, "equity": equity, "time": "Start"}]
        drawdown_curve = [{"trade": 0, "drawdown": 0.0, "drawdown_pct": 0.0}]

        daily_pnl_tracker: Dict[str, float] = {}
        daily_trades_tracker: Dict[str, int] = {}
        daily_consecutive_losses: Dict[str, int] = {}
        daily_locks: Dict[str, str] = {}

        missing_data_events: List[Dict[str, Any]] = []
        execution_diagnostics: List[Dict[str, Any]] = []

        active_trade: Optional[Dict[str, Any]] = None

        # Pre-calculate points parameters
        pts_info = self.strategy.calculate_target_and_stop_points(
            quantity=self.lots * self.lot_size,
            slippage_points=self.slippage_points if exec_mode == "REALISTIC" else 0.0,
        )
        target_pts = pts_info["target_points"]
        stop_pts = pts_info["stop_points"]

        # Run bar-by-bar backtest simulation
        for i in range(30, len(valid_nifty)):
            curr_candle = valid_nifty[i]
            history_slice = valid_nifty[: i + 1]

            ts_dt = parse_trade_datetime_ist(curr_candle.get("timestamp"))
            if not ts_dt:
                continue

            date_str = ts_dt.strftime("%Y-%m-%d")
            time_str = ts_dt.strftime("%H:%M")

            daily_pnl = daily_pnl_tracker.get(date_str, 0.0)
            daily_count = daily_trades_tracker.get(date_str, 0)
            consec_losses = daily_consecutive_losses.get(date_str, 0)
            is_locked = date_str in daily_locks

            # Prepare quotes map for current candle
            current_quotes: Dict[str, Dict[str, Any]] = {}
            ce_c = ce_map.get(ts_dt.isoformat())
            if ce_c:
                current_quotes["ATM_CE"] = {
                    "symbol": ce_c.get("symbol", "NIFTY_CE"),
                    "last_price": float(ce_c.get("close", 125.0)),
                    "bid": float(ce_c.get("close", 125.0)) - 0.25,
                    "ask": float(ce_c.get("close", 125.0)) + 0.25,
                    "strike": float(ce_c.get("strike", 24500.0)),
                    "expiry": ce_c.get("expiry", "WEEKLY"),
                    "lot_size": self.lot_size,
                }
            pe_c = pe_map.get(ts_dt.isoformat())
            if pe_c:
                current_quotes["ATM_PE"] = {
                    "symbol": pe_c.get("symbol", "NIFTY_PE"),
                    "last_price": float(pe_c.get("close", 125.0)),
                    "bid": float(pe_c.get("close", 125.0)) - 0.25,
                    "ask": float(pe_c.get("close", 125.0)) + 0.25,
                    "strike": float(pe_c.get("strike", 24500.0)),
                    "expiry": pe_c.get("expiry", "WEEKLY"),
                    "lot_size": self.lot_size,
                }

            # 1. Active Trade Management (Check exits on current bar)
            if active_trade is not None:
                contract_type = active_trade["contract_type"]
                opt_map = ce_map if contract_type == "CE" else pe_map
                opt_bar = opt_map.get(ts_dt.isoformat())

                # If real market data is missing for option bar, handle cleanly
                if not opt_bar:
                    if data_source == "SYNTHETIC_TEST":
                        # Synthetic approximation based on underlying index move
                        spot_change = curr_candle["close"] - active_trade["underlying_entry"]
                        delta = 0.50 if contract_type == "CE" else -0.50
                        sim_price = max(1.0, active_trade["entry_price"] + (spot_change * delta))
                        opt_bar = {
                            "open": sim_price,
                            "high": sim_price + 0.5,
                            "low": max(0.5, sim_price - 0.5),
                            "close": sim_price,
                        }
                    else:
                        missing_data_events.append({
                            "timestamp": ts_dt.isoformat(),
                            "type": "MISSING_DATA",
                            "symbol": active_trade["contract_symbol"],
                            "message": f"Option candle missing for {active_trade['contract_symbol']} at {time_str} IST"
                        })
                        # Cannot evaluate intra-candle exit without price; advance to next candle
                        opt_bar = None

                if opt_bar:
                    bar_open = float(opt_bar["open"])
                    bar_high = float(opt_bar["high"])
                    bar_low = float(opt_bar["low"])
                    bar_close = float(opt_bar["close"])

                    entry_p = active_trade["entry_price"]
                    target_p = active_trade["target_price"]
                    stop_p = active_trade["stop_price"]
                    qty = active_trade["quantity"]

                    target_hit = bar_high >= target_p
                    stop_hit = bar_low <= stop_p

                    # Holding time check
                    entry_dt = active_trade["entry_time"]
                    holding_mins = max(1, int((ts_dt - entry_dt).total_seconds() // 60))
                    holding_time_exceeded = holding_mins >= self.max_holding_time_minutes

                    # Session cutoff check
                    is_cutoff = time_str >= self.force_exit_ist

                    exit_occurred = False
                    exit_reason = ""
                    exit_price = 0.0

                    if target_hit and stop_hit:
                        # Ambiguous bar: conservative stop-first resolution
                        exit_occurred = True
                        exit_reason = "STOP_LOSS"
                        exit_price = stop_p if exec_mode == "TRIGGER_PRICE" else round(stop_p - self.slippage_points, 2)
                    elif stop_hit:
                        exit_occurred = True
                        exit_reason = "STOP_LOSS"
                        exit_price = stop_p if exec_mode == "TRIGGER_PRICE" else round(stop_p - self.slippage_points, 2)
                    elif target_hit:
                        exit_occurred = True
                        exit_reason = "TARGET"
                        exit_price = target_p if exec_mode == "TRIGGER_PRICE" else round(target_p + self.slippage_points, 2)
                    elif is_cutoff:
                        exit_occurred = True
                        exit_reason = "SESSION_SQUARE_OFF"
                        exit_price = bar_close if exec_mode == "TRIGGER_PRICE" else round(bar_close - self.slippage_points, 2)
                    elif holding_time_exceeded:
                        exit_occurred = True
                        exit_reason = "MAX_HOLDING_TIME"
                        exit_price = bar_close if exec_mode == "TRIGGER_PRICE" else round(bar_close - self.slippage_points, 2)

                    if exit_occurred:
                        exit_price = max(0.05, exit_price)
                        gross_pnl = round((exit_price - entry_p) * qty, 2)
                        charges = self.roundtrip_charges
                        slip_cost = (2.0 * self.slippage_points * qty) if exec_mode == "REALISTIC" else 0.0
                        net_pnl = round(gross_pnl - charges - slip_cost, 2)
                        is_win = net_pnl > 0

                        equity = round(equity + net_pnl, 2)
                        peak_equity = max(peak_equity, equity)
                        dd = round(peak_equity - equity, 2)
                        dd_pct = round((dd / peak_equity) * 100.0, 2) if peak_equity > 0 else 0.0
                        max_drawdown = max(max_drawdown, dd)

                        trade_record = {
                            "trade_number": len(trades) + 1,
                            "strategy_id": "AI_MICRO_SCALPER_V1",
                            "contract_symbol": active_trade["contract_symbol"],
                            "contract_type": active_trade["contract_type"],
                            "strike": active_trade["strike"],
                            "expiry": active_trade["expiry"],
                            "is_itm": active_trade["is_itm"],
                            "entry_time": active_trade["entry_time"].isoformat(),
                            "exit_time": ts_dt.isoformat(),
                            "entry_time_ist": active_trade["entry_time"].astimezone(IST).strftime("%Y-%m-%d %H:%M"),
                            "exit_time_ist": ts_dt.strftime("%Y-%m-%d %H:%M"),
                            "entry_price": entry_p,
                            "exit_price": exit_price,
                            "quantity": qty,
                            "lots": self.lots,
                            "exit_reason": exit_reason,
                            "holding_minutes": holding_mins,
                            "gross_pnl": gross_pnl,
                            "charges": charges,
                            "slippage_cost": round(slip_cost, 2),
                            "net_pnl": net_pnl,
                            "is_win": is_win,
                            "equity_after_trade": equity,
                            "agent_votes": active_trade.get("agent_votes", {}),
                        }
                        trades.append(trade_record)
                        equity_curve.append({
                            "trade": len(trades),
                            "equity": equity,
                            "time": ts_dt.strftime("%d %b %H:%M"),
                        })
                        drawdown_curve.append({
                            "trade": len(trades),
                            "drawdown": dd,
                            "drawdown_pct": dd_pct,
                        })

                        # Update daily metrics
                        daily_pnl = round(daily_pnl + net_pnl, 2)
                        daily_pnl_tracker[date_str] = daily_pnl
                        daily_count += 1
                        daily_trades_tracker[date_str] = daily_count

                        if is_win:
                            daily_consecutive_losses[date_str] = 0
                        else:
                            consec_losses += 1
                            daily_consecutive_losses[date_str] = consec_losses

                        # Check daily risk locks
                        if daily_pnl >= self.daily_profit_target:
                            daily_locks[date_str] = "DAILY_PROFIT_LIMIT"
                        elif daily_pnl <= self.daily_loss_limit:
                            daily_locks[date_str] = "DAILY_LOSS_LIMIT"
                        elif daily_count >= self.max_trades_per_day:
                            daily_locks[date_str] = "MAX_TRADES_LIMIT"
                        elif consec_losses >= self.max_consecutive_losses:
                            daily_locks[date_str] = "CONSECUTIVE_LOSS_LIMIT"

                        active_trade = None

            # 2. Signal Evaluation on Current Completed Candle (if no open position and not risk-locked)
            daily_risk_ctx = {
                "realized_net_pnl": daily_pnl_tracker.get(date_str, 0.0),
                "trade_count": daily_trades_tracker.get(date_str, 0),
                "consecutive_losses": daily_consecutive_losses.get(date_str, 0),
            }

            eval_res: Optional[AIMicroScalperEvaluation] = self.strategy.evaluate_completed_candle(
                completed_candles=history_slice,
                current_capital=equity,
                open_position=active_trade,
                daily_risk_status=daily_risk_ctx,
                option_quotes=current_quotes,
                current_lot_size=self.lot_size,
                ablation_config=ablation_config,
            )

            if eval_res and eval_res.is_buy and active_trade is None and not is_locked:
                # Signal confirmed on completed bar! Prepare entry on NEXT candle open
                if i + 1 < len(valid_nifty):
                    next_candle = valid_nifty[i + 1]
                    next_ts = parse_trade_datetime_ist(next_candle.get("timestamp"))
                    if next_ts and next_ts.strftime("%Y-%m-%d") == date_str:
                        opt_type = eval_res.target_contract_type
                        opt_map = ce_map if opt_type == "CE" else pe_map
                        next_opt_c = opt_map.get(next_ts.isoformat())

                        if not next_opt_c:
                            if data_source == "SYNTHETIC_TEST":
                                next_opt_c = {
                                    "open": eval_res.contract_premium or 125.0,
                                    "high": (eval_res.contract_premium or 125.0) + 1.0,
                                    "low": max(0.5, (eval_res.contract_premium or 125.0) - 1.0),
                                    "close": eval_res.contract_premium or 125.0,
                                    "symbol": eval_res.contract_symbol or f"NIFTY_{opt_type}",
                                    "strike": eval_res.contract_strike or 24500.0,
                                    "expiry": eval_res.contract_expiry or "WEEKLY",
                                }
                            else:
                                missing_data_events.append({
                                    "timestamp": next_ts.isoformat(),
                                    "type": "MISSING_DATA",
                                    "symbol": eval_res.contract_symbol,
                                    "message": f"Historical option bar missing for entry at {next_ts.strftime('%H:%M')} IST. Trade skipped."
                                })
                                continue

                        entry_fill = float(next_opt_c["open"])
                        if exec_mode == "REALISTIC":
                            entry_fill = round(entry_fill + self.slippage_points, 2)

                        # Validate 90% capital deployment cap
                        trade_cost = (entry_fill * eval_res.quantity) + (self.roundtrip_charges / 2.0)
                        if trade_cost > (0.90 * equity):
                            # Skip trade, never downsize quantity silently
                            execution_diagnostics.append({
                                "timestamp": next_ts.isoformat(),
                                "action": "SKIPPED_CAPITAL",
                                "reason": f"Required capital ₹{trade_cost:.2f} exceeds 90% limit (₹{0.90 * equity:.2f})"
                            })
                            continue

                        # Dynamic Target and Stop triggers based on ₹200 net target & ₹300 max loss
                        p_info = self.strategy.calculate_target_and_stop_points(
                            quantity=eval_res.quantity,
                            slippage_points=self.slippage_points if exec_mode == "REALISTIC" else 0.0,
                        )
                        t_trigger = round(entry_fill + p_info["target_points"], 2)
                        s_trigger = round(entry_fill - p_info["stop_points"], 2)

                        active_trade = {
                            "contract_symbol": eval_res.contract_symbol or f"NIFTY_{opt_type}",
                            "contract_type": opt_type,
                            "strike": eval_res.contract_strike or 24500.0,
                            "expiry": eval_res.contract_expiry or "WEEKLY",
                            "is_itm": eval_res.is_itm,
                            "entry_time": next_ts,
                            "entry_price": entry_fill,
                            "underlying_entry": curr_candle["close"],
                            "quantity": eval_res.quantity,
                            "target_price": t_trigger,
                            "stop_price": s_trigger,
                            "target_points": p_info["target_points"],
                            "stop_points": p_info["stop_points"],
                            "agent_votes": eval_res.agent_votes,
                        }

        # Calculate final summary metrics
        total_trades = len(trades)
        winning_trades = [t for t in trades if t["is_win"]]
        losing_trades = [t for t in trades if not t["is_win"]]

        win_count = len(winning_trades)
        loss_count = len(losing_trades)
        win_rate = round((win_count / total_trades) * 100.0, 2) if total_trades > 0 else 0.0

        gross_profit = round(sum(t["gross_pnl"] for t in winning_trades), 2)
        gross_loss = round(abs(sum(t["gross_pnl"] for t in losing_trades)), 2)
        net_profit = round(equity - self.initial_capital, 2)
        total_charges = round(sum(t["charges"] for t in trades), 2)
        total_slippage = round(sum(t["slippage_cost"] for t in trades), 2)

        profit_factor = round(gross_profit / gross_loss, 2) if gross_loss > 0 else (99.99 if gross_profit > 0 else 0.0)
        avg_profit = round(gross_profit / win_count, 2) if win_count > 0 else 0.0
        avg_loss = round(gross_loss / loss_count, 2) if loss_count > 0 else 0.0
        largest_win = round(max((t["net_pnl"] for t in winning_trades), default=0.0), 2)
        largest_loss = round(min((t["net_pnl"] for t in losing_trades), default=0.0), 2)

        # Daily breakdown table
        daily_breakdown: List[Dict[str, Any]] = []
        for d, pnl in sorted(daily_pnl_tracker.items()):
            cnt = daily_trades_tracker.get(d, 0)
            lock = daily_locks.get(d, "NORMAL")
            daily_breakdown.append({
                "date": d,
                "trades": cnt,
                "net_pnl": round(pnl, 2),
                "status": "WIN" if pnl > 0 else ("LOSS" if pnl < 0 else "FLAT"),
                "lock_reason": lock,
            })

        start_date = valid_nifty[0]["timestamp"] if valid_nifty else ""
        end_date = valid_nifty[-1]["timestamp"] if valid_nifty else ""

        results: Dict[str, Any] = {
            "strategy_id": "AI_MICRO_SCALPER_V1",
            "strategy_name": "NEXTRADE AI MICRO-SCALPER V1",
            "timeframe": "1m (5m Trend)",
            "instrument": "NIFTY Options (CE/PE)",
            "contract_symbol": "NIFTY ATM/ITM Options",
            "execution_mode": exec_mode,
            "data_source": data_source,
            "split_type": split_type or "ALL",
            "start_date": str(start_date),
            "end_date": str(end_date),
            "initial_capital": self.initial_capital,
            "final_capital": equity,
            "net_profit": net_profit,
            "gross_profit": gross_profit,
            "gross_loss": gross_loss,
            "total_trades": total_trades,
            "winning_trades": win_count,
            "losing_trades": loss_count,
            "win_rate": win_rate,
            "profit_factor": profit_factor,
            "avg_profit": avg_profit,
            "avg_loss": avg_loss,
            "largest_win": largest_win,
            "largest_loss": largest_loss,
            "max_drawdown": round(max_drawdown, 2),
            "max_drawdown_pct": round((max_drawdown / peak_equity) * 100.0, 2) if peak_equity > 0 else 0.0,
            "total_charges": total_charges,
            "total_slippage": total_slippage,
            "target_net_profit": self.target_net_profit,
            "max_loss_per_trade": self.max_loss_per_trade,
            "target_points": target_pts,
            "stop_points": stop_pts,
            "missing_data_count": len(missing_data_events),
            "missing_data_events": missing_data_events[:20],
            "daily_breakdown": daily_breakdown,
            "equity_curve": equity_curve,
            "drawdown_curve": drawdown_curve,
            "trades": trades,
        }

        # Persist to database if requested
        if save_to_db:
            try:
                run_id = await self._persist_run(results)
                results["run_id"] = run_id
            except Exception as e:
                logger.error(f"Failed to persist AI Micro-Scalper backtest run: {e}")

        return results

    async def _persist_run(self, results: Dict[str, Any]) -> int:
        """Persist backtest run and trades into database."""
        async with AsyncSessionLocal() as session:
            run_db = BacktestRun(
                strategy_id="AI_MICRO_SCALPER_V1",
                strategy_name="NEXTRADE AI MICRO-SCALPER V1",
                strategy_config=json.dumps(self.strategy.get_config_dict()),
                timeframe=results["timeframe"],
                instrument_symbol=results["contract_symbol"],
                start_date=results["start_date"],
                end_date=results["end_date"],
                initial_capital=results["initial_capital"],
                final_capital=results["final_capital"],
                total_trades=results["total_trades"],
                winning_trades=results["winning_trades"],
                losing_trades=results["losing_trades"],
                win_rate=results["win_rate"],
                gross_profit=results["gross_profit"],
                gross_loss=results["gross_loss"],
                net_profit=results["net_profit"],
                max_drawdown=results["max_drawdown"],
                profit_factor=results["profit_factor"],
                avg_profit=results["avg_profit"],
                avg_loss=results["avg_loss"],
                largest_win=results["largest_win"],
                largest_loss=results["largest_loss"],
                total_charges=results["total_charges"],
                data_source=results["data_source"],
                execution_mode=results["execution_mode"],
                exit_on_ut_sell_signal=False,
                configured_sl_points=results["stop_points"],
                configured_target_points=results["target_points"],
            )
            session.add(run_db)
            await session.flush()

            for t in results["trades"]:
                e_time = parse_trade_datetime_ist(t["entry_time"]) or datetime.now(timezone.utc)
                x_time = parse_trade_datetime_ist(t["exit_time"]) or datetime.now(timezone.utc)
                trade_db = BacktestTrade(
                    run_id=run_db.id,
                    symbol=t["contract_symbol"],
                    entry_time=e_time,
                    exit_time=x_time,
                    entry_price=t["entry_price"],
                    exit_price=t["exit_price"],
                    quantity=t["quantity"],
                    gross_pnl=t["gross_pnl"],
                    charges=t["charges"],
                    net_pnl=t["net_pnl"],
                    exit_reason=t["exit_reason"],
                    is_win=t["is_win"],
                    stop_loss_price=t.get("stop_price", 0.0),
                    target_price=t.get("target_price", 0.0),
                    slippage=t.get("slippage_cost", 0.0),
                )
                session.add(trade_db)

            await session.commit()
            return run_db.id

    async def run_ablation_comparison(
        self,
        nifty_candles: List[Dict[str, Any]],
        option_candles_ce: Optional[List[Dict[str, Any]]] = None,
        option_candles_pe: Optional[List[Dict[str, Any]]] = None,
        data_source: str = "KOTAK_NEO_HISTORICAL",
        execution_mode: str = "TRIGGER_PRICE",
    ) -> Dict[str, Any]:
        """
        Run Agent Performance Comparison / Ablation (A through G):
          - A: Base Strategy (Rule-based indicators only, all 5 agents disabled)
          - B: Base + Trend Agent
          - C: Base + Momentum Agent
          - D: Base + Volatility Agent
          - E: Base + Market Regime Agent
          - F: Base + Risk Agent
          - G: Full 5-Agent Consensus System (Production)
        """
        experiments = [
            {
                "id": "A",
                "name": "Base Strategy (No AI Agents)",
                "config": {
                    "enable_trend_agent": False,
                    "enable_momentum_agent": False,
                    "enable_volatility_agent": False,
                    "enable_regime_agent": False,
                    "enable_risk_agent": False,
                },
            },
            {
                "id": "B",
                "name": "Base + Trend Agent",
                "config": {
                    "enable_trend_agent": True,
                    "enable_momentum_agent": False,
                    "enable_volatility_agent": False,
                    "enable_regime_agent": False,
                    "enable_risk_agent": False,
                },
            },
            {
                "id": "C",
                "name": "Base + Momentum Agent",
                "config": {
                    "enable_trend_agent": False,
                    "enable_momentum_agent": True,
                    "enable_volatility_agent": False,
                    "enable_regime_agent": False,
                    "enable_risk_agent": False,
                },
            },
            {
                "id": "D",
                "name": "Base + Volatility Agent",
                "config": {
                    "enable_trend_agent": False,
                    "enable_momentum_agent": False,
                    "enable_volatility_agent": True,
                    "enable_regime_agent": False,
                    "enable_risk_agent": False,
                },
            },
            {
                "id": "E",
                "name": "Base + Market Regime Agent",
                "config": {
                    "enable_trend_agent": False,
                    "enable_momentum_agent": False,
                    "enable_volatility_agent": False,
                    "enable_regime_agent": True,
                    "enable_risk_agent": False,
                },
            },
            {
                "id": "F",
                "name": "Base + Risk Agent",
                "config": {
                    "enable_trend_agent": False,
                    "enable_momentum_agent": False,
                    "enable_volatility_agent": False,
                    "enable_regime_agent": False,
                    "enable_risk_agent": True,
                },
            },
            {
                "id": "G",
                "name": "Full 5-Agent Consensus System (Production)",
                "config": {
                    "enable_trend_agent": True,
                    "enable_momentum_agent": True,
                    "enable_volatility_agent": True,
                    "enable_regime_agent": True,
                    "enable_risk_agent": True,
                },
            },
        ]

        ablation_results: List[Dict[str, Any]] = []

        for exp in experiments:
            res = await self.run_backtest(
                nifty_candles=nifty_candles,
                option_candles_ce=option_candles_ce,
                option_candles_pe=option_candles_pe,
                data_source=data_source,
                execution_mode=execution_mode,
                ablation_config=exp["config"],
                save_to_db=False,  # Don't clutter db with ablation runs
            )

            ablation_results.append({
                "experiment_id": exp["id"],
                "experiment_name": exp["name"],
                "total_trades": res.get("total_trades", 0),
                "win_rate": res.get("win_rate", 0.0),
                "net_profit": res.get("net_profit", 0.0),
                "profit_factor": res.get("profit_factor", 0.0),
                "max_drawdown": res.get("max_drawdown", 0.0),
                "total_charges": res.get("total_charges", 0.0),
            })

        return {
            "strategy_id": "AI_MICRO_SCALPER_V1",
            "execution_mode": execution_mode,
            "data_source": data_source,
            "ablation_comparison": ablation_results,
        }
