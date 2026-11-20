import json
import logging
import math
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional, Tuple

from backend.app.strategy.indicators import calculate_ema, calculate_rsi, aggregate_candles
from backend.app.strategy.ut_bot import UTBotStrategy, UTBotEvaluation
from backend.app.strategy.supertrend_ema import SupertrendEMAStrategy, SupertrendEMAEvaluation
from backend.app.paper.charges import ChargesCalculator
from backend.app.database import AsyncSessionLocal
from backend.app.models import BacktestRun, BacktestTrade
from backend.app.analytics.calendar import parse_trade_datetime_ist

logger = logging.getLogger("nextrade.backtest")

IST = timezone(timedelta(hours=5, minutes=30))


def is_valid_exchange_session_candle(ts_val: Any) -> bool:
    """
    Validate that a candle's timestamp falls strictly within the NSE regular trading session:
    - Monday through Friday (weekday < 5).
    - Regular market trading hours: 09:15:00 IST to 15:30:00 IST inclusive.
    - Quarantines post-market, pre-market, weekend, and after-hours ticks.
    """
    dt_ist = parse_trade_datetime_ist(ts_val)
    if not dt_ist:
        return False
    if dt_ist.weekday() >= 5:
        return False
    time_str = dt_ist.strftime("%H:%M")
    return "09:15" <= time_str <= "15:30"


class BacktestEngine:
    """
    Advanced Multi-Strategy Historical Backtesting Engine with Universal Fixed Premium SL/Target Execution.
    
    EXACT PREMIUM-BASED RULE:
    - Entry premium = actual executed entry price.
    - Stop Loss = Entry Premium - configured SL points (default 2.0 pts).
    - Target = Entry Premium + configured Target points (default 4.0 pts).
    - Optional ₹1,000 risk cap: Effective SL = MIN(Configured SL, 1000 / Quantity).
    
    EXECUTION MODES:
    1. TRIGGER_PRICE MODE: Idealized execution.
       - SL fills exactly at configured SL trigger price when touched.
       - Target fills exactly at configured Target trigger price when touched.
       - Zero artificial slippage.
    2. REALISTIC MODE: Real-market execution assumptions.
       - Entry fills at candle open + slippage.
       - Target uses limit-order execution (fills at target price or open if gapped up).
       - Stop uses stop-market execution (fills at stop - slippage, or open - slippage on gaps).
       - Shows trigger price, actual fill, and slippage cost separately.
    
    CANDLE-BASED RULES:
    - Same-candle ambiguity: If both SL and Target are touched on the same candle,
      resolves conservatively (default STOP_LOSS) and marks trade as ambiguous.
    - UT Sell Signal exit: Configurable toggle (default OFF for strict SL/Target testing).
    """

    def __init__(
        self,
        initial_capital: float = 100000.0,
        lots: int = 5,
        lot_size: int = 65,
        target_points: float = 4.0,
        stop_points: float = 2.0,
        max_loss_per_trade: Optional[float] = None,
        slippage_points: float = 0.10,
        entry_charge_per_order: float = 10.0,
        exit_charge_per_order: float = 10.0,
        session_start_ist: str = "09:20",
        session_end_ist: str = "15:15",
        force_exit_ist: str = "15:20",
        execution_mode: str = "TRIGGER_PRICE",
        exit_on_ut_sell_signal: bool = True,
        same_candle_resolution: str = "CONSERVATIVE_STOP"
    ):
        self.initial_capital = float(initial_capital)
        self.lots = int(lots)
        self.lot_size = int(lot_size)
        self.quantity = self.lots * self.lot_size
        self.target_points = float(target_points)
        self.stop_points = float(stop_points)
        self.max_loss_per_trade = float(max_loss_per_trade) if max_loss_per_trade is not None else None
        self.slippage_points = float(slippage_points)
        self.session_start_ist = session_start_ist
        self.session_end_ist = session_end_ist
        self.force_exit_ist = force_exit_ist
        self.execution_mode = execution_mode
        self.exit_on_ut_sell_signal = exit_on_ut_sell_signal
        self.same_candle_resolution = same_candle_resolution

        self.charges_calc = ChargesCalculator(
            entry_charge_per_order=entry_charge_per_order,
            exit_charge_per_order=exit_charge_per_order
        )

    def evaluate_candle_exit(
        self,
        active_trade: Dict[str, Any],
        opt_c: Optional[Dict[str, Any]],
        mode: Optional[str] = None,
        same_candle_res: Optional[str] = None
    ) -> Optional[Tuple[float, str, float, bool, Optional[str]]]:
        """
        Evaluate candle exit conditions against active trade position.
        Returns:
            (exit_price, exit_reason, exit_slip, is_ambiguous, ambiguity_flag) or None if no exit.
        """
        if not opt_c:
            return None

        mode = mode or getattr(self, "execution_mode", "TRIGGER_PRICE")
        same_candle_res = same_candle_res or getattr(self, "same_candle_resolution", "CONSERVATIVE_STOP")

        c_open = opt_c["open"]
        c_high = opt_c["high"]
        c_low = opt_c["low"]
        c_close = opt_c["close"]

        sl_trigger = active_trade.get("sl_trigger_price") or active_trade.get("sl_trigger") or (active_trade["entry_price"] - active_trade.get("effective_sl_points", 2.0))
        target_trigger = active_trade.get("target_trigger_price") or active_trade.get("target_trigger") or (active_trade["entry_price"] + active_trade.get("effective_target_points", 4.0))

        sl_touched = bool(c_low <= sl_trigger)
        target_touched = bool(c_high >= target_trigger)

        if not sl_touched and not target_touched:
            return None

        is_ambiguous = False
        ambiguity_flag = None

        if sl_touched and target_touched:
            is_ambiguous = True
            ambiguity_flag = "BOTH_TOUCHED_SAME_CANDLE"
            target_exit = bool(same_candle_res == "TARGET_FIRST")
        elif target_touched:
            target_exit = True
        else:
            target_exit = False

        if target_exit:
            exit_reason = "TARGET"
            if mode == "TRIGGER_PRICE":
                # TRIGGER_PRICE: Target fills strictly at configured trigger price with zero slippage
                exit_price = target_trigger
                exit_slip = 0.0
            else:
                # REALISTIC: limit order fills at open if gapped above target, else at target trigger
                exit_price = c_open if c_open >= target_trigger else target_trigger
                exit_slip = 0.0
        else:
            exit_reason = "STOP_LOSS"
            if mode == "TRIGGER_PRICE":
                # TRIGGER_PRICE: SL fills strictly at configured trigger price with zero slippage
                exit_price = sl_trigger
                exit_slip = 0.0
            else:
                # REALISTIC: stop-market order suffers gap down fill if bar opened below stop
                if c_open <= sl_trigger:
                    exit_price = round(c_open - self.slippage_points, 2)
                    exit_slip = round(sl_trigger - exit_price, 2)
                else:
                    exit_price = round(sl_trigger - self.slippage_points, 2)
                    exit_slip = self.slippage_points

        return exit_price, exit_reason, exit_slip, is_ambiguous, ambiguity_flag

    _evaluate_candle_exit = evaluate_candle_exit

    def run_backtest(
        self,
        nifty_candles: List[Dict[str, Any]],
        option_candles: List[Dict[str, Any]],
        strategy_id: str = "UT_BOT",
        ut_bot_params: Optional[Dict[str, Any]] = None,
        supertrend_ema_params: Optional[Dict[str, Any]] = None,
        timeframe_minutes: int = 1,
        instrument_symbol: str = "NIFTY ATM CE",
        data_source: str = "HISTORICAL_DATA",
        metadata: Optional[Dict[str, Any]] = None,
        execution_mode: Optional[str] = None,
        exit_on_ut_sell_signal: Optional[bool] = None,
        same_candle_resolution: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Run backtest across aligned historical candles with specified strategy, timeframe, and execution mode.
        """
        mode = execution_mode or self.execution_mode
        exit_ut_sell = exit_on_ut_sell_signal if exit_on_ut_sell_signal is not None else self.exit_on_ut_sell_signal
        same_candle_res = same_candle_resolution or self.same_candle_resolution

        # 1. Multi-timeframe resampling if timeframe > 1m
        if timeframe_minutes > 1:
            nifty_candles = aggregate_candles(nifty_candles, timeframe_minutes)
            option_candles = aggregate_candles(option_candles, timeframe_minutes)

        # Quarantine invalid candles outside NSE trading session (09:15 to 15:30 IST, weekdays only)
        nifty_candles = [c for c in nifty_candles if is_valid_exchange_session_candle(c.get("timestamp"))]
        option_candles = [c for c in option_candles if is_valid_exchange_session_candle(c.get("timestamp"))]

        min_req = 15 if strategy_id in ("UT_BOT", "SUPERTREND_EMA", "SUPERTREND_EMA_SCALPER") else 55
        if len(nifty_candles) < min_req or len(option_candles) < min_req:
            return {
                "error": f"Insufficient candle data for backtesting (minimum {min_req} candles required for {strategy_id})."
            }

        # Build index map for option and nifty candles by normalized IST timestamp
        option_map: Dict[str, Dict[str, Any]] = {}
        for oc in option_candles:
            dt_ist = parse_trade_datetime_ist(oc.get("timestamp"))
            if dt_ist:
                option_map[dt_ist.isoformat()] = oc

        nifty_map: Dict[str, Dict[str, Any]] = {}
        for nc in nifty_candles:
            dt_ist = parse_trade_datetime_ist(nc.get("timestamp"))
            if dt_ist:
                nifty_map[dt_ist.isoformat()] = nc

        trades: List[Dict[str, Any]] = []
        active_trade: Optional[Dict[str, Any]] = None
        equity = self.initial_capital
        equity_curve = [{"trade": 0, "equity": equity, "time": "Start"}]
        drawdown_curve = [{"trade": 0, "drawdown": 0.0, "drawdown_pct": 0.0}]
        peak_equity = equity
        max_drawdown = 0.0
        max_drawdown_pct = 0.0

        daily_pnl_tracker: Dict[str, float] = {}
        daily_locks: Dict[str, str] = {}

        buy_entries_count = 0
        sell_exits_count = 0
        target_exits_count = 0
        stop_loss_exits_count = 0
        auto_close_exits_count = 0
        other_exits_count = 0
        buy_signals_ignored = 0
        sell_signals_ignored = 0
        execution_diagnostics: List[Dict[str, Any]] = []

        meta = metadata or {}
        is_direct_index = instrument_symbol.upper() in ("NIFTY 50", "NIFTY 50 INDEX", "NIFTY INDEX", "NIFTY50")
        contract_sym = meta.get("contract_symbol", instrument_symbol)

        # Precompute strategy signals
        if strategy_id == "UT_BOT":
            params = ut_bot_params or {}
            ut_lots = int(params.get("lots", self.lots))
            ut_lot_size = int(params.get("lot_size", self.lot_size))
            trade_qty = ut_lots * ut_lot_size
            key_val = float(params.get("key_value", 1.0))
            atr_per = int(params.get("atr_period", 10))
            use_ha = bool(params.get("use_heikin_ashi", False))
            target_pts = float(params.get("target_points", self.target_points))
            stop_pts = float(params.get("stop_points", self.stop_points))
            max_loss_cap = params.get("max_loss_per_trade", self.max_loss_per_trade)
            max_loss_cap = float(max_loss_cap) if max_loss_cap is not None and float(max_loss_cap) > 0 else None
            sig_src = params.get("signal_source", "CHART_INSTRUMENT")

            if is_direct_index:
                signal_instrument = "NIFTY 50 Index"
                execution_instrument = "NIFTY 50 Index (Direct)"
            elif sig_src == "NIFTY_INDEX":
                signal_instrument = "NIFTY 50 Spot Index"
                execution_instrument = f"{contract_sym} (Option Premium)"
            else:
                signal_instrument = f"{contract_sym} (Option Premium Chart)"
                execution_instrument = f"{contract_sym} (Option Premium)"

            ut_strat = UTBotStrategy(
                key_value=key_val,
                atr_period=atr_per,
                use_heikin_ashi=use_ha,
                lots=ut_lots,
                lot_size=ut_lot_size,
                target_points=target_pts,
                stop_points=stop_pts,
                max_loss_per_trade=max_loss_cap,
                signal_source=sig_src,
                exit_on_ut_sell_signal=exit_ut_sell
            )

            # Signal series: evaluate option candles if CHART_INSTRUMENT, else index candles
            sig_candles = option_candles if sig_src == "CHART_INSTRUMENT" else nifty_candles
            eval_series = ut_strat.calculate_series(sig_candles)
            eval_map: Dict[str, UTBotEvaluation] = {}
            for ev in eval_series:
                ev_dt = parse_trade_datetime_ist(ev.candle_time)
                if ev_dt:
                    eval_map[ev_dt.isoformat()] = ev

            effective_stop = ut_strat.calculate_effective_stop_points()
            eval_bars = sig_candles
            start_idx = atr_per + 2

        elif strategy_id in ("SUPERTREND_EMA", "SUPERTREND_EMA_SCALPER"):
            st_p = supertrend_ema_params or {}
            st_lots = int(st_p.get("lots", self.lots))
            st_lot_size = int(st_p.get("lot_size", self.lot_size))
            trade_qty = st_lots * st_lot_size
            st_atr = int(st_p.get("atr_period", 10))
            st_mult = float(st_p.get("multiplier", 3.0))
            st_ema_f = int(st_p.get("ema_fast", 9))
            st_ema_s = int(st_p.get("ema_slow", 21))
            st_target_net = float(st_p.get("target_net_profit", 200.0))
            st_max_loss = float(st_p.get("max_loss_per_trade", 1000.0))
            st_daily_target = float(st_p.get("daily_profit_target", 1000.0))
            st_daily_limit = float(st_p.get("daily_loss_limit", -2000.0))

            signal_instrument = "NIFTY 50 Spot Index"
            execution_instrument = "NIFTY 50 Index (Direct)" if is_direct_index else f"{contract_sym} (Option Premium)"

            st_strat = SupertrendEMAStrategy(
                atr_period=st_atr,
                multiplier=st_mult,
                ema_fast=st_ema_f,
                ema_slow=st_ema_s,
                lots=st_lots,
                lot_size=st_lot_size,
                target_net_profit=st_target_net,
                max_loss_per_trade=st_max_loss,
                daily_profit_target=st_daily_target,
                daily_loss_limit=st_daily_limit,
                roundtrip_charges=self.charges_calc.entry_charge_per_order + self.charges_calc.exit_charge_per_order
            )

            # Precalculate dynamic target & stop points
            pts = st_strat.calculate_target_and_stop_points(
                quantity=trade_qty,
                target_net_profit=st_target_net,
                max_loss_per_trade=st_max_loss,
                roundtrip_charges=self.charges_calc.entry_charge_per_order + self.charges_calc.exit_charge_per_order,
                slippage_points=self.slippage_points if mode == "REALISTIC" else 0.0
            )
            target_pts = pts["target_points"]
            stop_pts = pts["stop_points"]
            effective_stop = stop_pts

            # Signals are strictly evaluated on NIFTY index completed candles
            eval_series_st = st_strat.calculate_series(nifty_candles)
            st_eval_map: Dict[str, SupertrendEMAEvaluation] = {}
            for ev_s in eval_series_st:
                ev_dt = parse_trade_datetime_ist(ev_s.candle_time)
                if ev_dt:
                    st_eval_map[ev_dt.isoformat()] = ev_s

            eval_bars = nifty_candles
            start_idx = max(st_ema_s + 2, st_atr + 2)

        else:
            # EMA RSI Strategy
            trade_qty = self.lots * self.lot_size
            signal_instrument = "NIFTY 50 Spot Index"
            execution_instrument = "NIFTY 50 Index (Direct)" if is_direct_index else f"{contract_sym} (Option Premium)"
            closes = [c["close"] for c in nifty_candles]
            ema_9 = calculate_ema(closes, 9)
            ema_21 = calculate_ema(closes, 21)
            ema_50 = calculate_ema(closes, 50)
            rsi_14 = calculate_rsi(closes, 14)
            eval_bars = nifty_candles
            start_idx = 50
            target_pts = float(self.target_points)
            stop_pts = float(self.stop_points)
            if self.max_loss_per_trade and self.max_loss_per_trade > 0:
                max_loss_pts = self.max_loss_per_trade / max(1, trade_qty)
                effective_stop = round(min(stop_pts, max_loss_pts), 4)
            else:
                effective_stop = round(stop_pts, 4)

        n = len(eval_bars)

        def close_active_trade(
            exit_price: float,
            exit_reason: str,
            exit_slip: float,
            exit_time_dt: datetime,
            is_ambiguous: bool = False,
            ambiguity_flag: Optional[str] = None
        ):
            nonlocal active_trade, equity, peak_equity, max_drawdown, max_drawdown_pct
            if active_trade is None:
                return

            qty = active_trade["quantity"]
            gross_pnl = round((exit_price - active_trade["entry_price"]) * qty, 2)
            chg = self.charges_calc.calculate_charges(
                entry_price=active_trade["entry_price"],
                exit_price=exit_price,
                quantity=qty,
                entry_order_count=1,
                exit_order_count=1
            )
            net_pnl = round(gross_pnl - chg.total_charges, 2)
            is_win = bool(net_pnl > 0)
            entry_slip = active_trade.get("entry_slippage", 0.0)
            slippage_cost = round((entry_slip + exit_slip) * qty, 2)

            trade_date_key = exit_time_dt.strftime("%Y-%m-%d")
            daily_pnl_tracker[trade_date_key] = round(daily_pnl_tracker.get(trade_date_key, 0.0) + net_pnl, 2)
            if strategy_id in ("SUPERTREND_EMA", "SUPERTREND_EMA_SCALPER"):
                if daily_pnl_tracker[trade_date_key] >= st_daily_target:
                    daily_locks[trade_date_key] = "DAILY_PROFIT_LOCKED"
                elif daily_pnl_tracker[trade_date_key] <= st_daily_limit:
                    daily_locks[trade_date_key] = "DAILY_LOSS_LOCKED"

            equity = round(equity + net_pnl, 2)
            peak_equity = max(peak_equity, equity)
            dd = round(peak_equity - equity, 2)
            dd_pct = round((dd / peak_equity) * 100.0, 2) if peak_equity > 0 else 0.0
            max_drawdown = max(max_drawdown, dd)
            max_drawdown_pct = max(max_drawdown_pct, dd_pct)

            trade_num = len(trades) + 1
            equity_curve.append({
                "trade": trade_num,
                "equity": equity,
                "time": exit_time_dt.strftime("%d %b %H:%M")
            })
            drawdown_curve.append({
                "trade": trade_num,
                "drawdown": dd,
                "drawdown_pct": dd_pct
            })

            hold_time_mins = max(1, int((exit_time_dt - active_trade["entry_time"]).total_seconds() // 60))

            trade_entry = {
                "id": trade_num,
                "signal_time": active_trade["signal_time"],
                "entry_time": active_trade["entry_time"],
                "exit_time": exit_time_dt,
                "underlying_price": active_trade["underlying_price"],
                "option_symbol": active_trade["option_symbol"],
                "contract_type": active_trade.get("contract_type", "CE"),
                "strike": active_trade["strike"],
                "expiry": active_trade["expiry"],
                "entry_premium": active_trade["entry_premium"],
                "entry_price": active_trade["entry_price"],
                "exit_price": exit_price,
                "quantity": qty,
                "configured_sl_points": active_trade["configured_sl_points"],
                "configured_target_points": active_trade["configured_target_points"],
                "effective_sl_points": active_trade["effective_sl_points"],
                "effective_target_points": active_trade["effective_target_points"],
                "sl_trigger_price": active_trade["sl_trigger_price"],
                "target_trigger_price": active_trade["target_trigger_price"],
                "target": active_trade["target_trigger_price"],
                "stop": active_trade["sl_trigger_price"],
                "exit_reason": exit_reason,
                "execution_mode": mode,
                "is_ambiguous": is_ambiguous,
                "ambiguity_flag": ambiguity_flag,
                "entry_slippage": entry_slip,
                "exit_slippage": exit_slip,
                "slippage_cost": slippage_cost,
                "gross_pnl": gross_pnl,
                "entry_charge": chg.entry_charge,
                "exit_charge": chg.exit_charge,
                "charges": chg.total_charges,
                "net_pnl": net_pnl,
                "is_win": is_win,
                "holding_time_minutes": hold_time_mins
            }
            trades.append(trade_entry)

            execution_diagnostics.append({
                "timestamp": exit_time_dt.isoformat(),
                "signal_time": exit_time_dt.strftime("%Y-%m-%d %H:%M:%S"),
                "signal_type": "SELL" if "SELL" in exit_reason else "EXIT_TRIGGER",
                "signal_instrument": signal_instrument,
                "execution_instrument": execution_instrument,
                "position_before_signal": f"LONG {active_trade.get('contract_type', 'CE')} @ {active_trade.get('entry_price')}",
                "action_taken": "EXIT",
                "action_reason": f"{exit_reason} executed ({exit_price})",
                "entry_price": active_trade["entry_price"],
                "exit_price": exit_price,
                "exit_reason": exit_reason,
                "gross_pnl": gross_pnl,
                "charges": chg.total_charges,
                "slippage": exit_slip,
                "net_pnl": net_pnl
            })

            active_trade = None

        for i in range(start_idx, n - 1):
            curr_candle = eval_bars[i]
            next_candle = eval_bars[i + 1]

            ts_dt = parse_trade_datetime_ist(curr_candle.get("timestamp"))
            next_ts_dt = parse_trade_datetime_ist(next_candle.get("timestamp"))
            if not ts_dt or not next_ts_dt:
                continue

            next_ts_key = next_ts_dt.isoformat()
            opt_c = option_map.get(next_ts_key)

            time_str = ts_dt.strftime("%H:%M")
            next_time_str = next_ts_dt.strftime("%H:%M")

            ev = eval_map.get(ts_dt.isoformat()) if strategy_id == "UT_BOT" else None
            ev_s = st_eval_map.get(ts_dt.isoformat()) if strategy_id in ("SUPERTREND_EMA", "SUPERTREND_EMA_SCALPER") else None

            # Check if strategy produced a confirmed SELL signal on completed candle `i`
            is_strat_sell_signal = False
            strat_sell_reason = "UT_SELL_SIGNAL"
            if strategy_id == "UT_BOT":
                if ev and ev.is_sell:
                    is_strat_sell_signal = True
                    strat_sell_reason = "UT_SELL_SIGNAL"
            elif strategy_id in ("SUPERTREND_EMA", "SUPERTREND_EMA_SCALPER"):
                if ev_s and active_trade:
                    pos_type = active_trade.get("contract_type", "CE")
                    if (pos_type == "CE" and ev_s.supertrend_direction == -1) or (pos_type == "PE" and ev_s.supertrend_direction == 1):
                        is_strat_sell_signal = True
                        strat_sell_reason = "OPPOSITE_SUPERTREND_DIRECTION"

            # 1. Manage Active Position Exits
            if active_trade is not None:
                # A. Strategy SELL signal exit at open of next_candle
                if is_strat_sell_signal and (exit_ut_sell if strategy_id == "UT_BOT" else True):
                    sell_exits_count += 1
                    if mode == "TRIGGER_PRICE":
                        exit_price = opt_c["open"] if opt_c else active_trade["entry_price"]
                        exit_slip = 0.0
                    else:
                        exit_price = round(opt_c["open"] - self.slippage_points, 2) if opt_c else active_trade["entry_price"]
                        exit_slip = self.slippage_points
                    close_active_trade(
                        exit_price=exit_price,
                        exit_reason=strat_sell_reason,
                        exit_slip=exit_slip,
                        exit_time_dt=next_ts_dt
                    )
                    continue

                # B. Suppress duplicate BUY signal while already in position
                if strategy_id == "UT_BOT" and ev and ev.is_buy:
                    buy_signals_ignored += 1
                    execution_diagnostics.append({
                        "timestamp": ts_dt.isoformat(),
                        "signal_time": ts_dt.strftime("%Y-%m-%d %H:%M:%S"),
                        "signal_type": "BUY",
                        "signal_instrument": signal_instrument,
                        "execution_instrument": execution_instrument,
                        "position_before_signal": f"LONG {active_trade.get('contract_type', 'CE')} @ {active_trade.get('entry_price')}",
                        "action_taken": "IGNORED",
                        "action_reason": "Position already open; duplicate BUY entry suppressed",
                        "entry_price": active_trade["entry_price"],
                        "exit_price": None,
                        "exit_reason": None,
                        "gross_pnl": 0.0,
                        "charges": 0.0,
                        "slippage": 0.0,
                        "net_pnl": 0.0
                    })

                # C. Check intra-candle SL and Target on next_candle
                candle_res = self.evaluate_candle_exit(
                    active_trade=active_trade,
                    opt_c=opt_c,
                    mode=mode,
                    same_candle_res=same_candle_res
                )
                if candle_res:
                    exit_price, exit_reason, exit_slip, is_ambiguous, ambiguity_flag = candle_res
                    if "TARGET" in exit_reason:
                        target_exits_count += 1
                    elif "STOP" in exit_reason or "LOSS" in exit_reason:
                        stop_loss_exits_count += 1
                    else:
                        other_exits_count += 1
                    close_active_trade(
                        exit_price=exit_price,
                        exit_reason=exit_reason,
                        exit_slip=exit_slip,
                        exit_time_dt=next_ts_dt,
                        is_ambiguous=is_ambiguous,
                        ambiguity_flag=ambiguity_flag
                    )
                    continue

                # D. Check 15:20 IST auto close
                if next_time_str >= self.force_exit_ist:
                    auto_close_exits_count += 1
                    exit_reason = "AUTO_CLOSE_3_20_PM"
                    if mode == "TRIGGER_PRICE":
                        exit_price = opt_c["close"] if opt_c else active_trade["entry_price"]
                        exit_slip = 0.0
                    else:
                        exit_price = round(opt_c["close"] - self.slippage_points, 2) if opt_c else active_trade["entry_price"]
                        exit_slip = self.slippage_points
                    close_active_trade(
                        exit_price=exit_price,
                        exit_reason=exit_reason,
                        exit_slip=exit_slip,
                        exit_time_dt=next_ts_dt
                    )
                    continue

            # 2. When No Position is Open (active_trade is None)
            if active_trade is None and opt_c:
                # A. Handle SELL signal with no open position -> Ignore (Short selling disabled)
                if is_strat_sell_signal:
                    sell_signals_ignored += 1
                    execution_diagnostics.append({
                        "timestamp": ts_dt.isoformat(),
                        "signal_time": ts_dt.strftime("%Y-%m-%d %H:%M:%S"),
                        "signal_type": "SELL",
                        "signal_instrument": signal_instrument,
                        "execution_instrument": execution_instrument,
                        "position_before_signal": "FLAT",
                        "action_taken": "IGNORED",
                        "action_reason": "SELL signal with no open position (Short selling disabled)",
                        "entry_price": None,
                        "exit_price": None,
                        "exit_reason": None,
                        "gross_pnl": 0.0,
                        "charges": 0.0,
                        "slippage": 0.0,
                        "net_pnl": 0.0
                    })

                # B. Evaluate BUY signal
                is_buy_signal = False
                entry_contract_type = "CE"
                curr_date_key = ts_dt.strftime("%Y-%m-%d")
                is_daily_locked = bool(curr_date_key in daily_locks)

                if strategy_id == "UT_BOT":
                    if ev and ev.is_buy:
                        is_buy_signal = True
                        inst_upper = instrument_symbol.upper()
                        if "PE" in inst_upper:
                            entry_contract_type = "PE"
                        elif is_direct_index:
                            entry_contract_type = "INDEX"
                        else:
                            entry_contract_type = "CE"
                elif strategy_id in ("SUPERTREND_EMA", "SUPERTREND_EMA_SCALPER"):
                    if ev_s and not is_daily_locked:
                        is_pe_sym = "PE" in instrument_symbol.upper()
                        is_ce_sym = "CE" in instrument_symbol.upper()
                        if ev_s.is_buy_ce and (is_ce_sym or not is_pe_sym):
                            is_buy_signal = True
                            entry_contract_type = "CE"
                        elif ev_s.is_buy_pe and (is_pe_sym or not is_ce_sym):
                            is_buy_signal = True
                            entry_contract_type = "PE"
                else: # EMA_RSI
                    c1 = bool(ema_9[i] > ema_21[i])
                    c2 = bool(curr_candle["close"] > ema_50[i])
                    c3 = bool(rsi_14[i] > 50.0)
                    if c1 and c2 and c3:
                        is_buy_signal = True
                        entry_contract_type = "CE"

                if is_buy_signal:
                    session_valid = (
                        self.session_start_ist <= time_str <= self.session_end_ist
                        and next_time_str < self.force_exit_ist
                        and next_time_str <= "15:30"
                    )

                    if not session_valid:
                        buy_signals_ignored += 1
                        reason_desc = (
                            f"Outside allowed trading session hours ({self.session_start_ist} - {self.session_end_ist} IST)"
                            if not (self.session_start_ist <= time_str <= self.session_end_ist)
                            else f"Approaching force square-off cutoff ({self.force_exit_ist} IST)"
                        )
                        execution_diagnostics.append({
                            "timestamp": ts_dt.isoformat(),
                            "signal_time": ts_dt.strftime("%Y-%m-%d %H:%M:%S"),
                            "signal_type": "BUY",
                            "signal_instrument": signal_instrument,
                            "execution_instrument": execution_instrument,
                            "position_before_signal": "FLAT",
                            "action_taken": "IGNORED",
                            "action_reason": reason_desc,
                            "entry_price": None,
                            "exit_price": None,
                            "exit_reason": None,
                            "gross_pnl": 0.0,
                            "charges": 0.0,
                            "slippage": 0.0,
                            "net_pnl": 0.0
                        })
                    else:
                        buy_entries_count += 1
                        if mode == "TRIGGER_PRICE":
                            entry_slip = 0.0
                            entry_premium = opt_c["open"]
                        else:
                            entry_slip = self.slippage_points
                            entry_premium = round(opt_c["open"] + self.slippage_points, 2)

                        target_trigger = round(entry_premium + target_pts, 2)
                        sl_trigger = round(entry_premium - effective_stop, 2)

                        spot_c = nifty_map.get(ts_dt.isoformat())
                        spot_price = spot_c["close"] if spot_c else (curr_candle["close"] if strategy_id not in ("UT_BOT", "SUPERTREND_EMA", "SUPERTREND_EMA_SCALPER") else 24500.0)

                        active_trade = {
                            "signal_time": ts_dt,
                            "entry_time": next_ts_dt,
                            "underlying_price": spot_price,
                            "option_symbol": opt_c.get("symbol", instrument_symbol),
                            "contract_type": entry_contract_type,
                            "strike": opt_c.get("strike", round(spot_price / 50.0) * 50.0),
                            "expiry": opt_c.get("expiry", "WEEKLY"),
                            "entry_premium": entry_premium,
                            "entry_price": entry_premium,
                            "quantity": trade_qty,
                            "configured_sl_points": stop_pts,
                            "configured_target_points": target_pts,
                            "effective_sl_points": effective_stop,
                            "effective_target_points": target_pts,
                            "sl_trigger_price": sl_trigger,
                            "target_trigger_price": target_trigger,
                            "target": target_trigger,
                            "stop": sl_trigger,
                            "entry_slippage": entry_slip
                        }

                        execution_diagnostics.append({
                            "timestamp": ts_dt.isoformat(),
                            "signal_time": ts_dt.strftime("%Y-%m-%d %H:%M:%S"),
                            "signal_type": "BUY",
                            "signal_instrument": signal_instrument,
                            "execution_instrument": execution_instrument,
                            "position_before_signal": "FLAT",
                            "action_taken": "ENTRY",
                            "action_reason": f"BUY {entry_contract_type} entry executed at next candle open ({entry_premium})",
                            "entry_price": entry_premium,
                            "exit_price": None,
                            "exit_reason": None,
                            "gross_pnl": 0.0,
                            "charges": self.charges_calc.entry_charge_per_order,
                            "slippage": entry_slip,
                            "net_pnl": -self.charges_calc.entry_charge_per_order
                        })

                        # Intra-candle exit check on same entry candle
                        candle_res = self.evaluate_candle_exit(
                            active_trade=active_trade,
                            opt_c=opt_c,
                            mode=mode,
                            same_candle_res=same_candle_res
                        )
                        if candle_res:
                            exit_price, exit_reason, exit_slip, is_ambiguous, ambiguity_flag = candle_res
                            if "TARGET" in exit_reason:
                                target_exits_count += 1
                            elif "STOP" in exit_reason or "LOSS" in exit_reason:
                                stop_loss_exits_count += 1
                            else:
                                other_exits_count += 1
                            close_active_trade(
                                exit_price=exit_price,
                                exit_reason=exit_reason,
                                exit_slip=exit_slip,
                                exit_time_dt=next_ts_dt,
                                is_ambiguous=is_ambiguous,
                                ambiguity_flag=ambiguity_flag
                            )

        # Ensure no lingering unclosed trade at end of candle data
        if active_trade is not None and len(eval_bars) > 0:
            last_c = eval_bars[-1]
            last_ts_dt = parse_trade_datetime_ist(last_c.get("timestamp")) or active_trade["entry_time"]
            last_opt_c = option_map.get(last_ts_dt.isoformat()) or last_c
            exit_price = last_opt_c.get("close", active_trade["entry_price"])
            exit_reason = "SESSION_CLOSE"
            exit_slip = self.slippage_points if mode == "REALISTIC" else 0.0
            if mode == "REALISTIC":
                exit_price = round(exit_price - exit_slip, 2)
            auto_close_exits_count += 1
            close_active_trade(
                exit_price=exit_price,
                exit_reason=exit_reason,
                exit_slip=exit_slip,
                exit_time_dt=last_ts_dt
            )

        # Calculate comprehensive analytics with exact mathematical reconciliation
        total_trades = len(trades)
        wins = [t for t in trades if t["is_win"]]
        losses = [t for t in trades if not t["is_win"]]
        win_count = len(wins)
        loss_count = len(losses)
        win_rate = round((win_count / total_trades) * 100, 2) if total_trades > 0 else 0.0

        gross_profit = round(sum(t["gross_pnl"] for t in trades if t["gross_pnl"] > 0), 2)
        gross_loss = round(sum(abs(t["gross_pnl"]) for t in trades if t["gross_pnl"] < 0), 2)
        total_charges = round(sum(t["charges"] for t in trades), 2)
        net_profit = round(sum(t["net_pnl"] for t in trades), 2)

        # Enforce exact mathematical identity: Gross Profit - Gross Loss - Charges == Net Profit
        reconciled_net = round(gross_profit - gross_loss - total_charges, 2)
        if abs(reconciled_net - net_profit) <= 0.10:
            net_profit = reconciled_net

        profit_factor = round(gross_profit / gross_loss, 2) if gross_loss > 0 else (999.0 if gross_profit > 0 else 0.0)
        avg_profit = round(gross_profit / win_count, 2) if win_count > 0 else 0.0
        avg_loss = round(gross_loss / loss_count, 2) if loss_count > 0 else 0.0
        largest_win = round(max([t["net_pnl"] for t in wins], default=0.0), 2)
        largest_loss = round(min([t["net_pnl"] for t in losses], default=0.0), 2)

        total_slippage_cost = round(sum(t.get("slippage_cost", 0.0) for t in trades), 2)
        avg_holding_time = round(sum(t["holding_time_minutes"] for t in trades) / total_trades, 1) if total_trades > 0 else 0.0

        final_capital = round(self.initial_capital + net_profit, 2)

        # Consecutive streaks
        max_cw = 0
        curr_cw = 0
        max_cl = 0
        curr_cl = 0
        for t in trades:
            if t["is_win"]:
                curr_cw += 1
                curr_cl = 0
                max_cw = max(max_cw, curr_cw)
            else:
                curr_cl += 1
                curr_cw = 0
                max_cl = max(max_cl, curr_cl)

        meta = metadata or {}
        first_ts = eval_bars[0]["timestamp"]
        last_ts = eval_bars[-1]["timestamp"]
        first_dt = parse_trade_datetime_ist(first_ts)
        last_dt = parse_trade_datetime_ist(last_ts)
        actual_first_candle_str = first_dt.strftime("%Y-%m-%d") if first_dt else "2026-11-09"
        actual_last_candle_str = last_dt.strftime("%Y-%m-%d") if last_dt else "2026-11-13"

        selected_start_date_str = meta.get("start_date") or actual_first_candle_str
        selected_end_date_str = meta.get("end_date") or actual_last_candle_str

        # Group bars by date to identify available days
        candles_by_date: Dict[str, List[Any]] = {}
        for c in eval_bars:
            c_dt = parse_trade_datetime_ist(c.get("timestamp"))
            if c_dt:
                d_key = c_dt.strftime("%Y-%m-%d")
                candles_by_date.setdefault(d_key, []).append(c)

        # Group trades by date (using exit_time or entry_time)
        trades_by_date: Dict[str, List[Dict[str, Any]]] = {}
        for t in trades:
            d_key = t["exit_time"].strftime("%Y-%m-%d")
            trades_by_date.setdefault(d_key, []).append(t)

        from backend.app.analytics.nse_holidays import is_weekend, get_nse_holiday_name

        s_date_obj = datetime.strptime(selected_start_date_str, "%Y-%m-%d").date()
        e_date_obj = datetime.strptime(selected_end_date_str, "%Y-%m-%d").date()
        if s_date_obj > e_date_obj:
            s_date_obj, e_date_obj = e_date_obj, s_date_obj

        all_calendar_days = []
        cur = s_date_obj
        while cur <= e_date_obj:
            all_calendar_days.append(cur)
            cur += timedelta(days=1)

        date_wise_summary = []
        daily_summary = []
        missing_data_days = []
        trading_days_with_trades = 0
        trading_days_without_trades = 0
        trading_days_tested = 0

        for cur_d in all_calendar_days:
            d_str = cur_d.strftime("%Y-%m-%d")
            day_name = cur_d.strftime("%A")
            is_wknd = is_weekend(cur_d)
            holiday = get_nse_holiday_name(cur_d)
            c_list = candles_by_date.get(d_str, [])
            day_trades = trades_by_date.get(d_str, [])

            if len(day_trades) > 0:
                status = "TRADED"
                reason = f"{len(day_trades)} strategy trades executed"
                trading_days_with_trades += 1
                trading_days_tested += 1
            elif is_wknd:
                status = "WEEKEND"
                reason = "Exchange closed (Weekend)"
            elif holiday:
                status = "HOLIDAY"
                reason = f"Exchange Holiday ({holiday})"
            elif len(c_list) == 0:
                status = "MISSING_DATA"
                reason = "No historical candle data available for this trading day"
                missing_data_days.append(d_str)
            else:
                trading_days_tested += 1
                status = "NO_TRADE"
                reason = "No strategy entries generated on this trading day"
                trading_days_without_trades += 1

            # Day metrics calculation
            d_trade_count = len(day_trades)
            d_wins = [t for t in day_trades if t.get("is_win", False)]
            d_losses = [t for t in day_trades if not t.get("is_win", False)]
            d_win_cnt = len(d_wins)
            d_loss_cnt = len(d_losses)
            d_win_rate = round((d_win_cnt / d_trade_count) * 100.0, 1) if d_trade_count > 0 else 0.0

            d_gross_profit = round(sum(float(t.get("gross_pnl", 0.0)) for t in day_trades if float(t.get("gross_pnl", 0.0)) > 0), 2)
            d_gross_loss = round(sum(abs(float(t.get("gross_pnl", 0.0))) for t in day_trades if float(t.get("gross_pnl", 0.0)) < 0), 2)
            d_charges = round(sum(float(t.get("charges", 0.0)) for t in day_trades), 2)
            d_slippage = round(sum(float(t.get("slippage_cost", 0.0)) for t in day_trades), 2)
            d_net_pnl = round(sum(float(t.get("net_pnl", 0.0)) for t in day_trades), 2)
            if abs((d_gross_profit - d_gross_loss - d_charges) - d_net_pnl) <= 0.10:
                d_net_pnl = round(d_gross_profit - d_gross_loss - d_charges, 2)

            d_best = round(max([float(t.get("net_pnl", 0.0)) for t in day_trades], default=0.0), 2)
            d_worst = round(min([float(t.get("net_pnl", 0.0)) for t in day_trades], default=0.0), 2)

            # Daily drawdown
            running_peak = 0.0
            cur_dd = 0.0
            run_eq = 0.0
            for t in day_trades:
                run_eq += float(t.get("net_pnl", 0.0))
                running_peak = max(running_peak, run_eq)
                cur_dd = max(cur_dd, running_peak - run_eq)
            d_drawdown = round(cur_dd, 2)

            day_entry = {
                "date": d_str,
                "day_name": day_name,
                "status": status,
                "reason": reason,
                "has_trades": bool(d_trade_count > 0),
                "trades": d_trade_count,
                "trades_count": d_trade_count,
                "winning_trades": d_win_cnt,
                "losing_trades": d_loss_cnt,
                "wins": d_win_cnt,
                "losses": d_loss_cnt,
                "win_rate": d_win_rate,
                "gross_profit": d_gross_profit,
                "gross_loss": d_gross_loss,
                "grossProfit": d_gross_profit,
                "grossLoss": d_gross_loss,
                "gross_pnl": round(d_gross_profit - d_gross_loss, 2),
                "charges": d_charges,
                "slippage": d_slippage,
                "slippage_cost": d_slippage,
                "net_pnl": d_net_pnl,
                "pnl": d_net_pnl,
                "best_trade": d_best,
                "worst_trade": d_worst,
                "daily_drawdown": d_drawdown,
            }

            date_wise_summary.append(day_entry)

            # Only valid tested trading days go into daily_summary
            if status in ("TRADED", "NO_TRADE"):
                daily_summary.append(day_entry)

        period_summary = {
            "selected_start_date": selected_start_date_str,
            "selected_end_date": selected_end_date_str,
            "actual_first_candle_date": actual_first_candle_str,
            "actual_last_candle_date": actual_last_candle_str,
            "trading_days_available": len(candles_by_date),
            "trading_days_tested": trading_days_tested,
            "trading_days_with_trades": trading_days_with_trades,
            "trading_days_without_trades": trading_days_without_trades,
            "missing_data_days": missing_data_days,
            "missing_data_count": len(missing_data_days)
        }

        if strategy_id in ("SUPERTREND_EMA", "SUPERTREND_EMA_SCALPER"):
            strat_name = "SUPERTREND EMA SCALPER"
        elif strategy_id == "UT_BOT":
            strat_name = "UT Bot ATM Option Strategy"
        else:
            strat_name = "NIFTY 1M EMA+RSI ATM CE"

        data_src = meta.get("data_source", data_source)
        data_quality = meta.get("data_quality_status", "DETERMINISTIC_SYNTHETIC" if data_src == "SYNTHETIC_TEST" else "AUTHENTIC_MARKET_DATA")
        contract_sym = meta.get("contract_symbol", instrument_symbol)
        expiry_str = meta.get("expiry", "WEEKLY")
        valid_cnt = meta.get("valid_candles_count", len(option_candles))
        missing_cnt = meta.get("missing_candles_count", 0)

        diagnostics_summary = {
            "buy_entries_count": buy_entries_count,
            "sell_exits_count": sell_exits_count,
            "target_exits_count": target_exits_count,
            "stop_loss_exits_count": stop_loss_exits_count,
            "auto_close_exits_count": auto_close_exits_count,
            "other_exits_count": other_exits_count,
            "buy_signals_ignored": buy_signals_ignored,
            "sell_signals_ignored": sell_signals_ignored,
            "total_signals_logged": len(execution_diagnostics)
        }

        return {
            "strategy_id": strategy_id,
            "strategy_name": strat_name,
            "timeframe": f"{timeframe_minutes}m",
            "instrument": contract_sym,
            "contract_symbol": contract_sym,
            "expiry": expiry_str,
            "start_date": selected_start_date_str,
            "end_date": selected_end_date_str,
            "data_source": data_src,
            "data_quality_status": data_quality,
            "execution_mode": mode,
            "exit_on_ut_sell_signal": exit_ut_sell,
            "signal_instrument": signal_instrument,
            "execution_instrument": execution_instrument,
            "configured_sl_points": stop_pts,
            "configured_target_points": target_pts,
            "effective_sl_points": effective_stop,
            "valid_candles_count": valid_cnt,
            "missing_candles_count": missing_cnt,
            "initial_capital": self.initial_capital,
            "final_capital": final_capital,
            "total_trades": total_trades,
            "buy_entries_count": buy_entries_count,
            "sell_exits_count": sell_exits_count,
            "target_exits_count": target_exits_count,
            "stop_loss_exits_count": stop_loss_exits_count,
            "auto_close_exits_count": auto_close_exits_count,
            "winning_trades": win_count,
            "losing_trades": loss_count,
            "win_rate": win_rate,
            "gross_profit": gross_profit,
            "gross_loss": gross_loss,
            "net_profit": net_profit,
            "profit_factor": profit_factor,
            "avg_profit": avg_profit,
            "avg_loss": avg_loss,
            "largest_win": largest_win,
            "largest_loss": largest_loss,
            "max_drawdown": round(max_drawdown, 2),
            "max_drawdown_percent": max_drawdown_pct,
            "total_charges": total_charges,
            "total_slippage": total_slippage_cost,
            "slippage_cost": total_slippage_cost,
            "consecutive_wins_max": max_cw,
            "consecutive_losses_max": max_cl,
            "avg_holding_time": avg_holding_time,
            "avg_holding_time_minutes": avg_holding_time,
            "equity_curve": equity_curve,
            "drawdown_curve": drawdown_curve,
            "daily_summary": daily_summary,
            "date_wise_summary": date_wise_summary,
            "period_summary": period_summary,
            "diagnostics_summary": diagnostics_summary,
            "execution_diagnostics": execution_diagnostics,
            "trades": trades
        }

    async def save_backtest_run(self, results: Dict[str, Any], inputs_snapshot: Optional[Dict[str, Any]] = None) -> int:
        """Persist backtest run and trades to database with input snapshots and ledger fields."""
        snapshot = dict(inputs_snapshot or {})
        snapshot["period_summary"] = results.get("period_summary", {})
        snapshot["date_wise_summary"] = results.get("date_wise_summary", [])
        snapshot["daily_summary"] = results.get("daily_summary", [])
        snapshot["diagnostics_summary"] = results.get("diagnostics_summary", {})
        snapshot["signal_instrument"] = results.get("signal_instrument", "")
        snapshot["execution_instrument"] = results.get("execution_instrument", "")
        snapshot["buy_entries_count"] = results.get("buy_entries_count", 0)
        snapshot["sell_exits_count"] = results.get("sell_exits_count", 0)
        config_snapshot = json.dumps(snapshot, default=str)
        async with AsyncSessionLocal() as session:
            run_db = BacktestRun(
                strategy_id=results.get("strategy_id", "UT_BOT"),
                strategy_name=results["strategy_name"],
                strategy_config=config_snapshot,
                timeframe=results.get("timeframe", "1m"),
                instrument_symbol=results.get("contract_symbol", results.get("instrument", "NIFTY ATM CE")),
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
                data_source=results.get("data_source", "HISTORICAL_DATA"),
                execution_mode=results.get("execution_mode", "TRIGGER_PRICE"),
                exit_on_ut_sell_signal=results.get("exit_on_ut_sell_signal", False),
                configured_sl_points=results.get("configured_sl_points", 2.0),
                configured_target_points=results.get("configured_target_points", 4.0)
            )
            session.add(run_db)
            await session.flush()

            for t in results["trades"]:
                bt_trade = BacktestTrade(
                    run_id=run_db.id,
                    signal_time=t["signal_time"],
                    entry_time=t["entry_time"],
                    exit_time=t["exit_time"],
                    underlying_price=t["underlying_price"],
                    option_symbol=t["option_symbol"],
                    strike=t["strike"],
                    expiry=t["expiry"],
                    entry_price=t["entry_price"],
                    exit_price=t["exit_price"],
                    quantity=t["quantity"],
                    target=t["target"],
                    stop=t["stop"],
                    configured_sl_points=t.get("configured_sl_points", 2.0),
                    configured_target_points=t.get("configured_target_points", 4.0),
                    effective_sl_points=t.get("effective_sl_points", 2.0),
                    effective_target_points=t.get("effective_target_points", 4.0),
                    sl_trigger_price=t.get("sl_trigger_price", t["stop"]),
                    target_trigger_price=t.get("target_trigger_price", t["target"]),
                    slippage_cost=t.get("slippage_cost", 0.0),
                    execution_mode=t.get("execution_mode", "TRIGGER_PRICE"),
                    is_ambiguous=t.get("is_ambiguous", False),
                    ambiguity_flag=t.get("ambiguity_flag"),
                    holding_time_minutes=t.get("holding_time_minutes", 1),
                    exit_reason=t["exit_reason"],
                    gross_pnl=t["gross_pnl"],
                    entry_charge=t.get("entry_charge", 10.0),
                    exit_charge=t.get("exit_charge", 10.0),
                    charges=t["charges"],
                    net_pnl=t["net_pnl"],
                    is_win=t["is_win"]
                )
                session.add(bt_trade)

            await session.commit()
            return run_db.id
