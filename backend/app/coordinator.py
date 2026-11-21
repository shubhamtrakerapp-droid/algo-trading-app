import asyncio
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional, Set, Union
from fastapi import WebSocket

from backend.app.config import settings
from backend.app.adapters.base import BaseMarketDataAdapter, MarketTickData, CandleData
from backend.app.adapters.kotak_neo import KotakNeoAdapter
from backend.app.adapters.synthetic_feed import SyntheticMarketFeed
from backend.app.options.selector import OptionContractSelector
from backend.app.strategy.candle_builder import CandleBuilder
from backend.app.strategy.engine import MultiStrategyManager, StrategyEvaluationResult
from backend.app.strategy.ut_bot import UTBotEvaluation
from backend.app.strategy.supertrend_ema import SupertrendEMAEvaluation
from backend.app.paper.broker import PaperBroker
from backend.app.database import AsyncSessionLocal
from backend.app.models import (
    StrategySignal,
    SystemEvent,
    BrokerConnection,
    MarketTick,
    HistoricalCandle,
    StrategySignalEvaluation,
    AgentDecision,
    StrategyExecutionEvent,
)

logger = logging.getLogger("nextrade.coordinator")


class SystemCoordinator:
    """
    Central Coordinator orchestrating market feeds, strategy evaluation,
    option selection, paper trading, and real-time WebSocket distribution.
    """

    def __init__(self):
        self.kotak_adapter = KotakNeoAdapter()
        self.synthetic_adapter = SyntheticMarketFeed(initial_nifty_price=24500.0)

        # Decide primary active adapter based on available credentials
        if settings.has_kotak_credentials:
            self.active_adapter: BaseMarketDataAdapter = self.kotak_adapter
            logger.info("Credentials found: Primary adapter is KotakNeoAdapter.")
        else:
            self.active_adapter: BaseMarketDataAdapter = self.synthetic_adapter
            logger.info("No Kotak credentials found: Primary adapter is SyntheticMarketFeed (DEMO MODE).")

        self.option_selector = OptionContractSelector(default_lot_size=65)
        self.strategy_engine = MultiStrategyManager()
        self.paper_broker = PaperBroker(
            initial_capital=settings.paper_initial_capital,
            default_lots=settings.paper_default_lots,
            target_points=settings.paper_target_points,
            stop_points=settings.paper_stop_points,
            max_loss_per_trade=settings.paper_max_loss_per_trade,
            force_exit_time_ist=settings.paper_force_exit_time,
            slippage_points=0.10
        )
        self.candle_builder = CandleBuilder(on_candle_completed=self.on_candle_completed)

        # State cache
        self.latest_nifty_tick: Optional[MarketTickData] = None
        self.latest_option_tick: Optional[MarketTickData] = None
        self.current_contract: Dict[str, Any] = {}
        self.is_stale = False
        self.last_tick_received_at: Optional[datetime] = None
        self.active_subscriptions: Set[str] = {"NIFTY 50", "NIFTY ATM CE"}

        # Connected WebSockets
        self.active_websockets: Set[WebSocket] = set()

        # Monitoring tasks
        self._stale_monitor_task: Optional[asyncio.Task] = None
        self._auto_exit_task: Optional[asyncio.Task] = None
        self._running = False
        self._main_loop: Optional[asyncio.AbstractEventLoop] = None

    async def initialize(self):
        """Bootstrap database state, restore open positions, and connect feeds."""
        self._running = True
        self._main_loop = asyncio.get_running_loop()
        logger.info("Initializing NEXTRADE Trading System...")

        # 1. Restore any open position from DB
        await self.paper_broker.restore_from_db()
        if self.paper_broker.active_position:
            self.option_selector.set_position_open_state(True)

        # 2. Select initial ATM CE contract
        initial_spot = 24500.0
        self.current_contract = self.option_selector.select_atm_ce(initial_spot)

        # 3. Setup callbacks on adapters
        self.active_adapter.register_callbacks(
            on_tick=self.on_tick,
            on_status=self.on_status,
            on_error=self.on_error
        )

        # Check if running in a serverless environment (Vercel, AWS Lambda)
        import os
        is_serverless = os.getenv("VERCEL") == "1" or os.getenv("AWS_LAMBDA_FUNCTION_NAME") is not None
        if is_serverless:
            logger.info("Running in SERVERLESS environment (Vercel): Restored DB state and option selector; skipping persistent WebSocket background loops.")
            return

        # 4. Start active feed
        await self.active_adapter.start()

        # 5. Populate initial history for charts if empty
        await self._ensure_chart_history()

        # 6. Start stale feed monitor & auto exit scheduler
        self._stale_monitor_task = asyncio.create_task(self._monitor_stale_data())
        self._auto_exit_task = asyncio.create_task(self._auto_exit_scheduler_loop())

        logger.info("NEXTRADE Trading System initialized successfully.")

    async def _ensure_chart_history(self):
        """Populate initial 1-minute completed bars for charts."""
        nifty_history = self.candle_builder.get_history("NIFTY 50")
        if len(nifty_history) < 60:
            spot = self.latest_nifty_tick.last_price if self.latest_nifty_tick else 25227.95
            prem = self.latest_option_tick.last_price if self.latest_option_tick else 150.1
            hist = await self.synthetic_adapter.get_historical_candles(
                symbol="NIFTY 50",
                token="26000",
                exchange_segment="nse_cm",
                interval="1min",
                from_date="",
                to_date="",
                base_price=spot
            )
            for c in hist:
                self.candle_builder._history.setdefault("NIFTY 50", []).append(c)

            # Also for current option
            opt_hist = await self.synthetic_adapter.get_historical_candles(
                symbol=self.current_contract["symbol"],
                token=self.current_contract["instrument_token"],
                exchange_segment="nse_fo",
                interval="1min",
                from_date="",
                to_date="",
                base_price=prem
            )
            for oc in opt_hist:
                self.candle_builder._history.setdefault(self.current_contract["symbol"], []).append(oc)

    def _safe_broadcast(self, msg: Dict[str, Any]):
        """Safely schedule broadcast on active event loop."""
        if self._main_loop and self._main_loop.is_running():
            try:
                current_loop = asyncio.get_running_loop()
                if current_loop is self._main_loop:
                    self._main_loop.create_task(self.broadcast(msg))
                    return
            except RuntimeError:
                pass
            asyncio.run_coroutine_threadsafe(self.broadcast(msg), self._main_loop)
            return

        try:
            loop = asyncio.get_running_loop()
            self._main_loop = loop
            loop.create_task(self.broadcast(msg))
        except RuntimeError:
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.run_coroutine_threadsafe(self.broadcast(msg), loop)
                else:
                    loop.run_until_complete(self.broadcast(msg))
            except Exception:
                pass

    def on_tick(self, tick: MarketTickData):
        """Handle incoming market tick."""
        self.last_tick_received_at = datetime.now(timezone.utc)
        self.is_stale = False

        if tick.is_index:
            self.latest_nifty_tick = tick
            # Update ATM selection if no position is open
            if not self.paper_broker.active_position:
                self.current_contract = self.option_selector.select_atm_ce(tick.last_price)
                if isinstance(self.active_adapter, SyntheticMarketFeed):
                    self.active_adapter.update_atm_strike(
                        self.current_contract["strike"],
                        self.current_contract["symbol"],
                        self.current_contract["instrument_token"]
                    )
            # Send tick to candle builder
            self.candle_builder.process_tick(tick)
        else:
            self.latest_option_tick = tick
            if not self.paper_broker.active_position and self.current_contract:
                if tick.symbol and tick.symbol != "NIFTY ATM CE":
                    self.current_contract["symbol"] = tick.symbol
                if tick.instrument_token and not tick.instrument_token.startswith("OPT_"):
                    self.current_contract["instrument_token"] = tick.instrument_token
            self.candle_builder.process_tick(tick)

            # Continuous Target / Stop / Force-exit monitoring against live option premium
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self.paper_broker.update_tick(
                    token=tick.instrument_token,
                    current_price=tick.last_price,
                    timestamp=tick.timestamp
                ))
            except RuntimeError:
                pass

        # Broadcast live tick to WebSocket clients
        self._safe_broadcast({
            "type": "TICK",
            "data": {
                "symbol": tick.symbol,
                "token": tick.instrument_token,
                "price": tick.last_price,
                "is_index": tick.is_index,
                "volume": tick.volume,
                "bid": tick.bid,
                "ask": tick.ask,
                "timestamp": tick.timestamp.isoformat()
            }
        })

        # Broadcast real-time forming candle for chart live display
        forming = self.candle_builder.get_current_candle(tick.symbol)
        if forming:
            self._safe_broadcast({
                "type": "FORMING_CANDLE",
                "data": {
                    "symbol": tick.symbol,
                    "timestamp": int(forming.timestamp.timestamp()),
                    "time_iso": forming.timestamp.isoformat(),
                    "open": forming.open,
                    "high": forming.high,
                    "low": forming.low,
                    "close": forming.close,
                    "volume": float(forming.volume),
                    "complete": False
                }
            })

        # Broadcast Option Chain updates
        if tick.is_index:
            self._safe_broadcast({
                "type": "OPTION_CHAIN_SPOT",
                "data": {
                    "spot_price": tick.last_price,
                    "atm_strike": round(tick.last_price / 50.0) * 50.0,
                    "timestamp": tick.timestamp.isoformat()
                }
            })
        else:
            self._safe_broadcast({
                "type": "OPTION_CHAIN_TICK",
                "data": {
                    "symbol": tick.symbol,
                    "token": tick.instrument_token,
                    "price": tick.last_price,
                    "bid": tick.bid,
                    "ask": tick.ask,
                    "volume": tick.volume,
                    "open_interest": tick.open_interest,
                    "timestamp": tick.timestamp.isoformat()
                }
            })

    def on_candle_completed(self, symbol: str, candle: CandleData):
        """
        Triggered when a 1-minute candle completes.
        Broadcasts completed candle and evaluates active strategy.
        """
        # Broadcast completed candle immediately to all connected charts
        self._safe_broadcast({
            "type": "CANDLE_COMPLETED",
            "data": {
                "symbol": symbol,
                "timestamp": int(candle.timestamp.timestamp()),
                "time_iso": candle.timestamp.isoformat(),
                "open": candle.open,
                "high": candle.high,
                "low": candle.low,
                "close": candle.close,
                "volume": float(candle.volume),
                "complete": True
            }
        })

        history = self.candle_builder.get_history(symbol)
        if not history:
            return

        active_id = self.strategy_engine.active_strategy_id

        if active_id == "UT_BOT":
            ut_bot = self.strategy_engine.ut_bot_strategy
            # Route by signal_source
            if ut_bot.signal_source == "NIFTY_INDEX" and ("CE" in symbol or "PE" in symbol):
                return
            if ut_bot.signal_source == "CHART_INSTRUMENT" and "NIFTY" in symbol and "CE" not in symbol and "PE" not in symbol:
                return

            eval_res: Optional[UTBotEvaluation] = ut_bot.evaluate_completed_candle(history)
            if eval_res:
                logger.info(
                    f"UT Bot Evaluated on Completed Candle ({eval_res.time_ist} IST): "
                    f"Src={eval_res.src_price}, ATR={eval_res.atr}, TrailingStop={eval_res.trailing_stop}, "
                    f"PrevStop={eval_res.prev_trailing_stop}, Pos={eval_res.pos} | Signal={eval_res.signal} | Action={eval_res.action_reason}"
                )

                asyncio.create_task(self.broadcast({
                    "type": "STRATEGY_SIGNAL",
                    "data": {
                        "strategy_id": "UT_BOT",
                        "candle_time": eval_res.candle_time.isoformat(),
                        "symbol": eval_res.symbol,
                        "src_price": eval_res.src_price,
                        "underlying_price": eval_res.src_price,
                        "atr": eval_res.atr,
                        "trailing_stop": eval_res.trailing_stop,
                        "prev_trailing_stop": eval_res.prev_trailing_stop,
                        "pos": eval_res.pos,
                        "above": eval_res.above,
                        "below": eval_res.below,
                        "time_ist": eval_res.time_ist,
                        "signal": eval_res.signal,
                        "is_buy": eval_res.is_buy,
                        "is_sell": eval_res.is_sell,
                        "session_valid": eval_res.session_valid,
                        "action_reason": eval_res.action_reason,
                    }
                }))

                asyncio.create_task(self._save_ut_bot_signal(eval_res))

                # BUY execution
                if eval_res.is_buy and not self.paper_broker.active_position:
                    curr_premium = 150.1
                    if self.latest_option_tick:
                        curr_premium = self.latest_option_tick.last_price

                    logger.info(
                        f"Triggering automated paper BUY (UT Bot 5 Lots) for "
                        f"{self.current_contract['symbol']} @ ₹{curr_premium}"
                    )
                    asyncio.create_task(self.paper_broker.execute_buy(
                        contract=self.current_contract,
                        current_premium=curr_premium,
                        underlying_price=eval_res.src_price,
                        lots=ut_bot.lots,
                        strategy_id="UT_BOT",
                        strategy_config=json.dumps(ut_bot.get_config_dict()),
                        target_points=ut_bot.target_points,
                        stop_points=ut_bot.stop_points,
                        max_loss_per_trade=ut_bot.max_loss_per_trade
                    ))
                    self.option_selector.set_position_open_state(True)

                # Opposite SELL execution (governed by exit_on_ut_sell_signal setting)
                elif eval_res.is_sell and self.paper_broker.active_position:
                    should_exit_ut = bool(
                        getattr(self.strategy_engine.ut_bot_strategy, "exit_on_ut_sell_signal", True) and
                        getattr(self.paper_broker, "exit_on_ut_sell_signal", True)
                    )
                    if should_exit_ut:
                        curr_premium = (
                            self.latest_option_tick.last_price
                            if self.latest_option_tick
                            else self.paper_broker.active_position["current_price"]
                        )
                        logger.info(
                            f"Triggering automated paper SELL (UT Sell Signal) for "
                            f"{self.current_contract['symbol']} @ ₹{curr_premium}"
                        )
                        asyncio.create_task(self.paper_broker.manual_close(
                            exit_price=curr_premium,
                            reason="UT_SELL_SIGNAL"
                        ))
                        self.option_selector.set_position_open_state(False)
                    else:
                        logger.debug("UT Sell Signal observed, but 'Exit on UT Sell Signal' is disabled (strict SL/Target mode).")

        elif active_id in ("SUPERTREND_EMA", "SUPERTREND_EMA_SCALPER"):
            st_strat = self.strategy_engine.supertrend_ema_strategy
            # Strictly evaluates on NIFTY index completed candles
            if "NIFTY" in symbol and "CE" not in symbol and "PE" not in symbol:
                eval_res_st = st_strat.evaluate_completed_candle(history)
                if eval_res_st:
                    logger.info(
                        f"Supertrend EMA Evaluated ({eval_res_st.time_ist} IST): "
                        f"Close={eval_res_st.underlying_price}, ST={eval_res_st.supertrend} ({eval_res_st.trend_str}), "
                        f"EMA9={eval_res_st.ema_9}, EMA21={eval_res_st.ema_21} | Signal={eval_res_st.signal} | Action={eval_res_st.action_reason}"
                    )

                    async def handle_supertrend_ema():
                        daily_risk = await self.paper_broker.get_daily_risk_status(
                            strategy_id="SUPERTREND_EMA",
                            daily_profit_target=st_strat.daily_profit_target,
                            daily_loss_limit=st_strat.daily_loss_limit
                        )

                        await self.broadcast({
                            "type": "STRATEGY_SIGNAL",
                            "data": {
                                "strategy_id": "SUPERTREND_EMA",
                                "candle_time": eval_res_st.candle_time.isoformat(),
                                "symbol": eval_res_st.symbol,
                                "underlying_price": eval_res_st.underlying_price,
                                "supertrend": eval_res_st.supertrend,
                                "supertrend_direction": eval_res_st.supertrend_direction,
                                "trend_str": eval_res_st.trend_str,
                                "supertrend_upper": eval_res_st.supertrend_upper,
                                "supertrend_lower": eval_res_st.supertrend_lower,
                                "supertrend_atr": eval_res_st.supertrend_atr,
                                "ema_9": eval_res_st.ema_9,
                                "ema_21": eval_res_st.ema_21,
                                "signal": eval_res_st.signal,
                                "is_buy_ce": eval_res_st.is_buy_ce,
                                "is_buy_pe": eval_res_st.is_buy_pe,
                                "is_buy": eval_res_st.is_buy,
                                "target_contract_type": eval_res_st.target_contract_type,
                                "time_ist": eval_res_st.time_ist,
                                "session_valid": eval_res_st.session_valid,
                                "action_reason": eval_res_st.action_reason,
                                "daily_risk": daily_risk
                            }
                        })

                        await self._save_supertrend_ema_signal(eval_res_st)

                        # 1. Exit active position on opposite confirmed Supertrend direction
                        if self.paper_broker.active_position:
                            open_strat = self.paper_broker.active_position.get("strategy_id")
                            if open_strat in ("SUPERTREND_EMA", "SUPERTREND_EMA_SCALPER"):
                                open_sym = self.paper_broker.active_position.get("symbol", "")
                                is_ce_pos = "CE" in open_sym
                                is_pe_pos = "PE" in open_sym

                                should_exit = False
                                if is_ce_pos and eval_res_st.supertrend_direction == -1:
                                    should_exit = True
                                    exit_why = "OPPOSITE_SUPERTREND_DIRECTION (Flipped Bearish)"
                                elif is_pe_pos and eval_res_st.supertrend_direction == 1:
                                    should_exit = True
                                    exit_why = "OPPOSITE_SUPERTREND_DIRECTION (Flipped Bullish)"

                                if should_exit:
                                    curr_prem = (
                                        self.latest_option_tick.last_price
                                        if self.latest_option_tick
                                        else self.paper_broker.active_position["current_price"]
                                    )
                                    logger.info(f"Triggering automated paper exit for {open_sym}: {exit_why}")
                                    await self.paper_broker.manual_close(
                                        exit_price=curr_prem,
                                        reason="OPPOSITE_SUPERTREND_DIRECTION"
                                    )
                                    self.option_selector.set_position_open_state(False)

                        # 2. Open new position if no open position and daily risk limits permit entry
                        if not self.paper_broker.active_position and not daily_risk.get("is_locked", False):
                            pts = st_strat.calculate_target_and_stop_points(
                                quantity=st_strat.quantity,
                                roundtrip_charges=self.paper_broker.charges_calc.entry_charge_per_order + self.paper_broker.charges_calc.exit_charge_per_order,
                                slippage_points=self.paper_broker.slippage_points if self.paper_broker.execution_mode == "REALISTIC" else 0.0
                            )

                            if eval_res_st.is_buy_ce:
                                contract = self.option_selector.select_atm_ce(eval_res_st.underlying_price)
                                curr_prem = 150.0
                                if self.latest_option_tick:
                                    curr_prem = self.latest_option_tick.last_price

                                logger.info(
                                    f"Triggering automated paper BUY CE (Supertrend EMA) for {contract['symbol']} @ ₹{curr_prem} | "
                                    f"Target +{pts['target_points']} pts, SL -{pts['stop_points']} pts"
                                )
                                await self.paper_broker.execute_buy(
                                    contract=contract,
                                    current_premium=curr_prem,
                                    underlying_price=eval_res_st.underlying_price,
                                    lots=st_strat.lots,
                                    strategy_id="SUPERTREND_EMA",
                                    strategy_config=json.dumps(st_strat.get_config_dict()),
                                    target_points=pts["target_points"],
                                    stop_points=pts["stop_points"],
                                    max_loss_per_trade=st_strat.max_loss_per_trade,
                                    execution_mode=self.paper_broker.execution_mode
                                )
                                self.option_selector.set_position_open_state(True)

                            elif eval_res_st.is_buy_pe:
                                contract = self.option_selector.select_atm_pe(eval_res_st.underlying_price)
                                curr_prem = 150.0
                                if self.latest_option_tick:
                                    curr_prem = self.latest_option_tick.last_price

                                logger.info(
                                    f"Triggering automated paper BUY PE (Supertrend EMA) for {contract['symbol']} @ ₹{curr_prem} | "
                                    f"Target +{pts['target_points']} pts, SL -{pts['stop_points']} pts"
                                )
                                await self.paper_broker.execute_buy(
                                    contract=contract,
                                    current_premium=curr_prem,
                                    underlying_price=eval_res_st.underlying_price,
                                    lots=st_strat.lots,
                                    strategy_id="SUPERTREND_EMA",
                                    strategy_config=json.dumps(st_strat.get_config_dict()),
                                    target_points=pts["target_points"],
                                    stop_points=pts["stop_points"],
                                    max_loss_per_trade=st_strat.max_loss_per_trade,
                                    execution_mode=self.paper_broker.execution_mode
                                )
                                self.option_selector.set_position_open_state(True)

                    asyncio.create_task(handle_supertrend_ema())

        elif active_id == "AI_MICRO_SCALPER_V1":
            ai_strat = self.strategy_engine.ai_micro_scalper_strategy
            if "NIFTY" in symbol and "CE" not in symbol and "PE" not in symbol:
                eval_res_ai = ai_strat.evaluate_completed_candle(
                    completed_candles=history,
                    current_capital=self.paper_broker.get_strategy_cash("AI_MICRO_SCALPER_V1"),
                    open_position=self.paper_broker.active_position,
                )
                if eval_res_ai:
                    logger.info(
                        f"AI Micro-Scalper Evaluated ({eval_res_ai.time_ist} IST): "
                        f"Close={eval_res_ai.underlying_price}, Signal={eval_res_ai.signal} | "
                        f"Votes: {eval_res_ai.voting_result.get('approved_count', 0) if eval_res_ai.voting_result else 0}/5 | "
                        f"Reason={eval_res_ai.action_reason}"
                    )

                    async def handle_ai_micro_scalper():
                        daily_risk = await self.paper_broker.get_daily_risk_status(
                            strategy_id="AI_MICRO_SCALPER_V1",
                            daily_profit_target=ai_strat.daily_profit_target,
                            daily_loss_limit=ai_strat.daily_loss_limit
                        )

                        await self.broadcast({
                            "type": "STRATEGY_SIGNAL",
                            "data": {
                                "strategy_id": "AI_MICRO_SCALPER_V1",
                                "candle_time": eval_res_ai.candle_time.isoformat(),
                                "symbol": eval_res_ai.symbol,
                                "underlying_price": eval_res_ai.underlying_price,
                                "time_ist": eval_res_ai.time_ist,
                                "signal": eval_res_ai.signal,
                                "is_buy_ce": eval_res_ai.is_buy_ce,
                                "is_buy_pe": eval_res_ai.is_buy_pe,
                                "is_buy": eval_res_ai.is_buy,
                                "target_contract_type": eval_res_ai.target_contract_type,
                                "contract_symbol": eval_res_ai.contract_symbol,
                                "contract_strike": eval_res_ai.contract_strike,
                                "contract_premium": eval_res_ai.contract_premium,
                                "lots": eval_res_ai.lots,
                                "lot_size": eval_res_ai.lot_size,
                                "quantity": eval_res_ai.quantity,
                                "target_points": eval_res_ai.target_points,
                                "stop_points": eval_res_ai.stop_points,
                                "agent_votes": eval_res_ai.agent_votes,
                                "action_reason": eval_res_ai.action_reason,
                                "session_valid": eval_res_ai.session_valid,
                            }
                        })

                        # Check if opposite signal arrived while in a position (Exit, don't reverse)
                        if self.paper_broker.active_position and self.paper_broker.active_position.get("strategy_id") == "AI_MICRO_SCALPER_V1":
                            pos = self.paper_broker.active_position
                            pos_type = pos.get("contract_type", "CE")
                            if (pos_type == "CE" and eval_res_ai.is_buy_pe) or (pos_type == "PE" and eval_res_ai.is_buy_ce):
                                curr_prem = self.latest_option_tick.last_price if self.latest_option_tick else pos["current_price"]
                                logger.info(f"AI Micro-Scalper opposite signal detected ({eval_res_ai.signal}). Exiting {pos['symbol']} @ ₹{curr_prem}")
                                await self.paper_broker.manual_close(
                                    exit_price=curr_prem,
                                    reason="OPPOSITE_SIGNAL"
                                )
                                self.option_selector.set_position_open_state(False)
                                return

                        # Check entry
                        if eval_res_ai.is_buy and not self.paper_broker.active_position:
                            if daily_risk.get("is_locked", False):
                                logger.info(f"AI Micro-Scalper trade blocked by daily risk lock: {daily_risk.get('status_text')}")
                                return

                            contract = {
                                "symbol": eval_res_ai.contract_symbol or f"NIFTY {eval_res_ai.target_contract_type}",
                                "strike": eval_res_ai.contract_strike or 24500.0,
                                "expiry": eval_res_ai.contract_expiry or "WEEKLY",
                                "token": "AI_OPT",
                                "exchange_segment": "nse_fo",
                                "option_type": eval_res_ai.target_contract_type,
                                "lot_size": eval_res_ai.lot_size,
                            }
                            curr_prem = eval_res_ai.contract_premium or 125.0
                            if self.latest_option_tick:
                                curr_prem = self.latest_option_tick.last_price

                            logger.info(
                                f"Triggering automated paper BUY ({eval_res_ai.target_contract_type} - AI Micro-Scalper) for "
                                f"{contract['symbol']} @ ₹{curr_prem} | Target +{eval_res_ai.target_points} pts, SL -{eval_res_ai.stop_points} pts"
                            )
                            await self.paper_broker.execute_buy(
                                contract=contract,
                                current_premium=curr_prem,
                                underlying_price=eval_res_ai.underlying_price,
                                lots=eval_res_ai.lots,
                                strategy_id="AI_MICRO_SCALPER_V1",
                                strategy_config=json.dumps(ai_strat.get_config_dict()),
                                target_points=eval_res_ai.target_points,
                                stop_points=eval_res_ai.stop_points,
                                max_loss_per_trade=ai_strat.max_loss_per_trade,
                                execution_mode=self.paper_broker.execution_mode
                            )
                            self.option_selector.set_position_open_state(True)

                    asyncio.create_task(handle_ai_micro_scalper())

        else:
            # EMA RSI Strategy strictly on NIFTY index completed candles
            if "NIFTY" in symbol and "CE" not in symbol and "PE" not in symbol:
                eval_res_ema: Optional[StrategyEvaluationResult] = self.strategy_engine.ema_strategy.evaluate_completed_candle(history)
                if eval_res_ema:
                    logger.info(
                        f"EMA Strategy Evaluated on Completed 1M Candle ({eval_res_ema.time_ist} IST): "
                        f"Close={eval_res_ema.underlying_price}, EMA9={eval_res_ema.ema_9}, EMA21={eval_res_ema.ema_21}, "
                        f"EMA50={eval_res_ema.ema_50}, RSI14={eval_res_ema.rsi_14} | Signal={eval_res_ema.signal} | "
                        f"C1={eval_res_ema.condition_1}, C2={eval_res_ema.condition_2}, C3={eval_res_ema.condition_3}, C4={eval_res_ema.condition_4}"
                    )

                    asyncio.create_task(self.broadcast({
                        "type": "STRATEGY_SIGNAL",
                        "data": {
                            "strategy_id": "EMA_RSI",
                            "candle_time": eval_res_ema.candle_time.isoformat(),
                            "underlying_price": eval_res_ema.underlying_price,
                            "ema_9": eval_res_ema.ema_9,
                            "ema_21": eval_res_ema.ema_21,
                            "ema_50": eval_res_ema.ema_50,
                            "rsi_14": eval_res_ema.rsi_14,
                            "time_ist": eval_res_ema.time_ist,
                            "condition_1": eval_res_ema.condition_1,
                            "condition_2": eval_res_ema.condition_2,
                            "condition_3": eval_res_ema.condition_3,
                            "condition_4": eval_res_ema.condition_4,
                            "signal": eval_res_ema.signal,
                            "is_buy": eval_res_ema.is_buy,
                            "is_sell": False
                        }
                    }))

                    asyncio.create_task(self._save_ema_signal(eval_res_ema))

                    if eval_res_ema.is_buy and not self.paper_broker.active_position:
                        curr_premium = 145.0
                        if self.latest_option_tick:
                            curr_premium = self.latest_option_tick.last_price

                        logger.info(f"Triggering automated paper BUY for {self.current_contract['symbol']} @ ₹{curr_premium}")
                        asyncio.create_task(self.paper_broker.execute_buy(
                            contract=self.current_contract,
                            current_premium=curr_premium,
                            underlying_price=eval_res_ema.underlying_price,
                            lots=self.strategy_engine.ema_strategy.lots,
                            strategy_id="EMA_RSI",
                            strategy_config=json.dumps(self.strategy_engine.ema_strategy.get_config_dict()),
                            target_points=self.strategy_engine.ema_strategy.target_points,
                            stop_points=self.strategy_engine.ema_strategy.stop_points,
                            max_loss_per_trade=self.strategy_engine.ema_strategy.max_loss_per_trade
                        ))
                        self.option_selector.set_position_open_state(True)

    async def _save_ut_bot_signal(self, eval_res: UTBotEvaluation):
        try:
            async with AsyncSessionLocal() as session:
                sig = StrategySignal(
                    strategy_id="UT_BOT",
                    strategy_config=json.dumps(self.strategy_engine.ut_bot_strategy.get_config_dict()),
                    timestamp=eval_res.timestamp,
                    candle_time=eval_res.candle_time,
                    underlying_symbol=eval_res.symbol,
                    underlying_price=eval_res.src_price,
                    atr=eval_res.atr,
                    trailing_stop=eval_res.trailing_stop,
                    condition_1=eval_res.above,
                    condition_2=bool(eval_res.src_price > eval_res.trailing_stop),
                    condition_3=eval_res.session_valid,
                    condition_4=True,
                    signal_type=eval_res.signal,
                    executed=eval_res.is_buy or (eval_res.is_sell and self.paper_broker.active_position is not None),
                    notes=eval_res.action_reason
                )
                session.add(sig)
                await session.flush()

                # Granular persistence: signal evaluations & agent decision
                eval_1 = StrategySignalEvaluation(
                    signal_id=sig.id,
                    strategy_id="UT_BOT",
                    timestamp=eval_res.timestamp,
                    rule_name="Price Above Trailing Stop",
                    passed=bool(eval_res.above),
                    expected_condition="Source price > Trailing stop",
                    actual_value=f"Price: {eval_res.src_price}, Stop: {eval_res.trailing_stop}"
                )
                session.add(eval_1)

                eval_2 = StrategySignalEvaluation(
                    signal_id=sig.id,
                    strategy_id="UT_BOT",
                    timestamp=eval_res.timestamp,
                    rule_name="Session Time Valid",
                    passed=bool(eval_res.session_valid),
                    expected_condition="09:20 - 15:15 IST",
                    actual_value=f"Session valid: {eval_res.session_valid}"
                )
                session.add(eval_2)

                decision = AgentDecision(
                    signal_id=sig.id,
                    strategy_id="UT_BOT",
                    agent_name="UTBotTrendAgent",
                    vote="BUY" if eval_res.is_buy else "SELL" if eval_res.is_sell else "HOLD",
                    confidence=1.0 if (eval_res.is_buy or eval_res.is_sell) else 0.5,
                    reasoning=eval_res.action_reason or f"Signal: {eval_res.signal}",
                    timestamp=eval_res.timestamp
                )
                session.add(decision)

                strat_evt = StrategyExecutionEvent(
                    strategy_id="UT_BOT",
                    event_type="SIGNAL_EXECUTED" if sig.executed else "SIGNAL_EVALUATED",
                    details_json=json.dumps({
                        "signal_id": sig.id,
                        "signal_type": sig.signal_type,
                        "executed": sig.executed,
                        "price": eval_res.src_price
                    }),
                    created_at=eval_res.timestamp
                )
                session.add(strat_evt)
                await session.commit()
        except Exception as e:
            logger.error(f"Error saving UT Bot signal to DB: {e}")

    async def _save_ema_signal(self, eval_res: StrategyEvaluationResult):
        try:
            async with AsyncSessionLocal() as session:
                sig = StrategySignal(
                    strategy_id="EMA_RSI",
                    strategy_config=json.dumps(self.strategy_engine.ema_strategy.get_config_dict()),
                    timestamp=eval_res.timestamp,
                    candle_time=eval_res.candle_time,
                    underlying_symbol="NIFTY",
                    underlying_price=eval_res.underlying_price,
                    ema_9=eval_res.ema_9,
                    ema_21=eval_res.ema_21,
                    ema_50=eval_res.ema_50,
                    rsi_14=eval_res.rsi_14,
                    condition_1=eval_res.condition_1,
                    condition_2=eval_res.condition_2,
                    condition_3=eval_res.condition_3,
                    condition_4=eval_res.condition_4,
                    signal_type=eval_res.signal,
                    executed=eval_res.is_buy
                )
                session.add(sig)
                await session.flush()

                # Granular persistence: signal evaluations & agent decision
                eval_1 = StrategySignalEvaluation(
                    signal_id=sig.id,
                    strategy_id="UT_BOT",
                    timestamp=eval_res.timestamp,
                    rule_name="Price Above Trailing Stop",
                    passed=bool(eval_res.above),
                    expected_condition="Source price > Trailing stop",
                    actual_value=f"Price: {eval_res.src_price}, Stop: {eval_res.trailing_stop}"
                )
                session.add(eval_1)

                eval_2 = StrategySignalEvaluation(
                    signal_id=sig.id,
                    strategy_id="UT_BOT",
                    timestamp=eval_res.timestamp,
                    rule_name="Session Time Valid",
                    passed=bool(eval_res.session_valid),
                    expected_condition="09:20 - 15:15 IST",
                    actual_value=f"Session valid: {eval_res.session_valid}"
                )
                session.add(eval_2)

                decision = AgentDecision(
                    signal_id=sig.id,
                    strategy_id="UT_BOT",
                    agent_name="UTBotTrendAgent",
                    vote="BUY" if eval_res.is_buy else "SELL" if eval_res.is_sell else "HOLD",
                    confidence=1.0 if (eval_res.is_buy or eval_res.is_sell) else 0.5,
                    reasoning=eval_res.action_reason or f"Signal: {eval_res.signal}",
                    timestamp=eval_res.timestamp
                )
                session.add(decision)

                strat_evt = StrategyExecutionEvent(
                    strategy_id="UT_BOT",
                    event_type="SIGNAL_EXECUTED" if sig.executed else "SIGNAL_EVALUATED",
                    details_json=json.dumps({
                        "signal_id": sig.id,
                        "signal_type": sig.signal_type,
                        "executed": sig.executed,
                        "price": eval_res.src_price
                    }),
                    created_at=eval_res.timestamp
                )
                session.add(strat_evt)
                await session.commit()
        except Exception as e:
            logger.error(f"Error saving EMA signal to DB: {e}")

    async def _save_supertrend_ema_signal(self, eval_res: SupertrendEMAEvaluation):
        try:
            async with AsyncSessionLocal() as session:
                sig = StrategySignal(
                    strategy_id="SUPERTREND_EMA",
                    strategy_config=json.dumps(self.strategy_engine.supertrend_ema_strategy.get_config_dict()),
                    timestamp=eval_res.timestamp,
                    candle_time=eval_res.candle_time,
                    underlying_symbol="NIFTY 50",
                    underlying_price=eval_res.underlying_price,
                    atr=eval_res.supertrend_atr,
                    trailing_stop=eval_res.supertrend,
                    ema_9=eval_res.ema_9,
                    ema_21=eval_res.ema_21,
                    condition_1=bool(eval_res.supertrend_direction == 1),
                    condition_2=bool(eval_res.ema_9 > eval_res.ema_21),
                    condition_3=bool(eval_res.underlying_price > eval_res.ema_9 and eval_res.underlying_price > eval_res.ema_21),
                    condition_4=eval_res.session_valid,
                    signal_type=eval_res.signal,
                    executed=eval_res.is_buy and not self.paper_broker.active_position,
                    notes=eval_res.action_reason
                )
                session.add(sig)
                await session.flush()

                # Granular persistence: signal evaluations & agent decision
                eval_1 = StrategySignalEvaluation(
                    signal_id=sig.id,
                    strategy_id="UT_BOT",
                    timestamp=eval_res.timestamp,
                    rule_name="Price Above Trailing Stop",
                    passed=bool(eval_res.above),
                    expected_condition="Source price > Trailing stop",
                    actual_value=f"Price: {eval_res.src_price}, Stop: {eval_res.trailing_stop}"
                )
                session.add(eval_1)

                eval_2 = StrategySignalEvaluation(
                    signal_id=sig.id,
                    strategy_id="UT_BOT",
                    timestamp=eval_res.timestamp,
                    rule_name="Session Time Valid",
                    passed=bool(eval_res.session_valid),
                    expected_condition="09:20 - 15:15 IST",
                    actual_value=f"Session valid: {eval_res.session_valid}"
                )
                session.add(eval_2)

                decision = AgentDecision(
                    signal_id=sig.id,
                    strategy_id="UT_BOT",
                    agent_name="UTBotTrendAgent",
                    vote="BUY" if eval_res.is_buy else "SELL" if eval_res.is_sell else "HOLD",
                    confidence=1.0 if (eval_res.is_buy or eval_res.is_sell) else 0.5,
                    reasoning=eval_res.action_reason or f"Signal: {eval_res.signal}",
                    timestamp=eval_res.timestamp
                )
                session.add(decision)

                strat_evt = StrategyExecutionEvent(
                    strategy_id="UT_BOT",
                    event_type="SIGNAL_EXECUTED" if sig.executed else "SIGNAL_EVALUATED",
                    details_json=json.dumps({
                        "signal_id": sig.id,
                        "signal_type": sig.signal_type,
                        "executed": sig.executed,
                        "price": eval_res.src_price
                    }),
                    created_at=eval_res.timestamp
                )
                session.add(strat_evt)
                await session.commit()
        except Exception as e:
            logger.error(f"Error saving Supertrend EMA signal to DB: {e}")

    def on_status(self, status: str, message: str):
        logger.info(f"Market Adapter Status: {status} - {message}")
        asyncio.create_task(self.broadcast({
            "type": "FEED_STATUS",
            "data": {
                "status": status,
                "message": message,
                "is_demo": self.active_adapter.is_demo,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        }))

    def on_error(self, err_msg: str):
        logger.error(f"Market Adapter Error: {err_msg}")
        asyncio.create_task(self.broadcast({
            "type": "FEED_ERROR",
            "data": {
                "error": err_msg,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        }))

    async def _monitor_stale_data(self):
        """Detect stale market data if ticks pause for more than 15 seconds."""
        while self._running:
            await asyncio.sleep(5)
            if self.last_tick_received_at:
                elapsed = (datetime.now(timezone.utc) - self.last_tick_received_at).total_seconds()
                if elapsed > 15.0 and not self.is_stale:
                    self.is_stale = True
                    logger.warning(f"Market data stale: No ticks received in {int(elapsed)} seconds.")
                    await self.broadcast({
                        "type": "STALE_DATA_WARNING",
                        "data": {
                            "is_stale": True,
                            "elapsed_seconds": int(elapsed),
                            "message": "Market feed is stale. New automated entries paused."
                        }
                    })

    async def _auto_exit_scheduler_loop(self):
        """Dedicated high-resolution timer checking Auto Close time every second."""
        while self._running:
            try:
                await asyncio.sleep(1)
                if not self._running:
                    break
                now = datetime.now(timezone.utc)
                latest_price = self.latest_option_tick.last_price if self.latest_option_tick else None
                is_connected = bool(self.active_adapter.is_connected)
                trade = await self.paper_broker.check_and_run_auto_close(
                    now=now,
                    latest_option_price=latest_price,
                    is_feed_stale=self.is_stale,
                    is_feed_connected=is_connected,
                    strategy_id=self.strategy_engine.active_strategy_id
                )
                if trade:
                    self.option_selector.set_position_open_state(False)
                    await self.broadcast({
                        "type": "AUTO_EXIT_TRIGGERED",
                        "data": {
                            "position_id": trade.position_id,
                            "symbol": trade.symbol,
                            "exit_price": trade.exit_price,
                            "gross_pnl": trade.gross_pnl,
                            "total_charges": trade.total_charges,
                            "net_pnl": trade.net_pnl,
                            "reason": trade.exit_reason,
                            "status": self.paper_broker.auto_exit_last_status
                        }
                    })
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in auto exit scheduler loop: {e}", exc_info=True)

    async def subscribe_symbols(self, symbols: List[str]):
        """Register active symbol subscriptions from frontend clients."""
        tokens = []
        for s in symbols:
            self.active_subscriptions.add(s)
            s_up = s.strip().upper()
            if s_up in ("NIFTY 50", "NIFTY", "NIFTY_INDEX"):
                tokens.append({"segment": "nse_cm", "token": "26000", "symbol": "NIFTY 50"})
            elif "CE" in s_up or "PE" in s_up:
                resolved = KotakNeoAdapter.resolve_fo_contract(symbol=s_up)
                if resolved:
                    tokens.append({"segment": "nse_fo", "token": resolved["token"], "symbol": resolved["symbol"]})
        if tokens and hasattr(self.active_adapter, "subscribe"):
            await self.active_adapter.subscribe(tokens)

    async def unsubscribe_symbols(self, symbols: List[str]):
        """Unregister active symbol subscriptions."""
        tokens = []
        for s in symbols:
            self.active_subscriptions.discard(s)
            s_up = s.strip().upper()
            if s_up in ("NIFTY 50", "NIFTY", "NIFTY_INDEX"):
                tokens.append({"segment": "nse_cm", "token": "26000", "symbol": "NIFTY 50"})
            elif "CE" in s_up or "PE" in s_up:
                resolved = KotakNeoAdapter.resolve_fo_contract(symbol=s_up)
                if resolved:
                    tokens.append({"segment": "nse_fo", "token": resolved["token"], "symbol": resolved["symbol"]})
        if tokens and hasattr(self.active_adapter, "unsubscribe"):
            await self.active_adapter.unsubscribe(tokens)

    def get_current_snapshot(self) -> Dict[str, Any]:
        """Return full market and trading state snapshot for clients."""
        spot = self.latest_nifty_tick.last_price if self.latest_nifty_tick else 24500.0
        opt_prem = self.latest_option_tick.last_price if self.latest_option_tick else 145.0
        contract = self.current_contract or {}
        pos = self.paper_broker.active_position
        pos_dict = None
        if pos and isinstance(pos, dict):
            pos_dict = dict(pos)
            for k, v in pos_dict.items():
                if isinstance(v, datetime):
                    pos_dict[k] = v.isoformat()

        conn_state = getattr(self.active_adapter, "connection_state", "CONNECTED" if self.active_adapter.is_connected else "DISCONNECTED")
        return {
            "is_connected": self.active_adapter.is_connected,
            "connection_state": conn_state,
            "is_demo": self.active_adapter.is_demo,
            "nifty_price": spot,
            "option_symbol": contract.get("symbol", "NIFTY ATM CE"),
            "option_premium": opt_prem,
            "atm_strike": contract.get("strike", round(spot / 50.0) * 50.0),
            "expiry": contract.get("expiry", "WEEKLY"),
            "lot_size": contract.get("lot_size", 65),
            "active_position": pos_dict,
            "cash_balance": self.paper_broker.cash_balance,
            "active_subscriptions": list(self.active_subscriptions),
            "last_tick_time": self.last_tick_received_at.isoformat() if self.last_tick_received_at else None,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    async def broadcast(self, message: Dict[str, Any]):
        """Broadcast JSON message to all active WebSocket clients."""
        import json
        payload_str = json.dumps(message, default=str)
        dead_sockets = set()
        for ws in self.active_websockets:
            try:
                await ws.send_text(payload_str)
            except Exception:
                dead_sockets.add(ws)
        self.active_websockets -= dead_sockets

    async def shutdown(self):
        """Graceful shutdown of feeds and tasks."""
        self._running = False
        if self._stale_monitor_task:
            self._stale_monitor_task.cancel()
        if self._auto_exit_task:
            self._auto_exit_task.cancel()
        await self.active_adapter.stop()


# Global singleton instance
coordinator = SystemCoordinator()
