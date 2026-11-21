import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List, Callable
from sqlalchemy import select, update

from backend.app.database import AsyncSessionLocal
from backend.app.models import (
    PaperPosition,
    PaperOrder,
    PaperTrade,
    SystemEvent,
    StrategyDailyRisk,
    StrategyVirtualAccount,
    PaperAccount,
    PaperAccountBalance,
    PaperTradeEvent,
    PaperExecutionLog,
    PaperCharge,
    PaperRiskEvent,
)
from backend.app.paper.charges import ChargesCalculator, TransactionCharges

logger = logging.getLogger("nextrade.paper_broker")

IST = timezone(timedelta(hours=5, minutes=30))


@dataclass
class StrategyLedger:
    strategy_id: str
    strategy_name: str
    initial_capital: float = 100000.0
    available_cash: float = 100000.0
    reserved_capital: float = 0.0
    realized_gross_pnl: float = 0.0
    realized_net_pnl: float = 0.0
    total_charges: float = 0.0
    slippage_cost: float = 0.0
    capital_deployment_cap_pct: float = 90.0
    daily_profit_target: Optional[float] = None
    daily_loss_limit: Optional[float] = None
    max_trades_per_day: Optional[int] = None
    max_consecutive_losses: Optional[int] = None
    risk_limits_enabled: bool = True
    active_position: Optional[Dict[str, Any]] = None

    @property
    def total_equity(self) -> float:
        unrealized = self.active_position["net_pnl"] if self.active_position else 0.0
        return round(self.available_cash + self.reserved_capital + unrealized, 2)


@dataclass
class PaperTradeResult:
    position_id: int
    symbol: str
    entry_price: float
    exit_price: float
    quantity: int
    exit_reason: str
    gross_pnl: float
    total_charges: float
    net_pnl: float
    is_win: bool
    entry_time: datetime
    exit_time: datetime


class PaperBroker:
    """
    Independent Virtual Broker for Simulated Paper Trading.
    STRICTLY PAPER TRADING ONLY. NEVER SENDS ORDERS TO REAL BROKERS.
    """

    def __init__(
        self,
        initial_capital: float = 100000.0,
        default_lots: int = 1,
        target_points: float = 4.0,
        stop_points: float = 2.0,
        max_loss_per_trade: float = 1000.0,
        force_exit_time_ist: str = "15:20",
        slippage_points: float = 0.10,
        execution_mode: str = "REALISTIC",
        exit_on_ut_sell_signal: bool = True,
    ):
        self.initial_capital = initial_capital
        self.cash_balance = initial_capital
        self.default_lots = default_lots
        self.target_points = target_points
        self.stop_points = stop_points
        self.max_loss_per_trade = max_loss_per_trade
        self.force_exit_time_ist = force_exit_time_ist
        self.slippage_points = slippage_points
        self.execution_mode = execution_mode  # TRIGGER_PRICE or REALISTIC
        self.exit_on_ut_sell_signal = exit_on_ut_sell_signal  # Default True (UT SELL exits position)

        self.charges_calc = ChargesCalculator(entry_charge_per_order=10.0, exit_charge_per_order=10.0)
        self.active_position: Optional[Dict[str, Any]] = None
        self.closed_trades: List[Dict[str, Any]] = []

        # Isolated Strategy Ledgers & Concurrency Lock
        self.ledgers: Dict[str, StrategyLedger] = {}
        self._execution_lock = asyncio.Lock()

        # Auto Exit Settings (Configurable Cutoff)
        self.auto_exit_enabled: bool = True
        self.auto_close_time_ist: str = force_exit_time_ist or "15:20"
        self.auto_exit_apply_all: bool = True
        self.auto_exit_close_profitable: bool = True
        self.auto_exit_close_losing: bool = True
        self.auto_exit_last_status: str = "STANDBY: Scheduled for 03:20 PM IST"
        self.auto_exit_last_run_time: Optional[datetime] = None
        self.auto_exit_last_run_date: Optional[str] = None
        self.auto_exit_awaiting_valid_data: bool = False
        self.auto_exit_warning: Optional[str] = None
        self.session_cutoff_active: bool = False

        self.on_order_callback: Optional[Callable[[Dict[str, Any]], Any]] = None
        self.on_position_callback: Optional[Callable[[Dict[str, Any]], Any]] = None
        self.on_trade_callback: Optional[Callable[[Dict[str, Any]], Any]] = None

    def _format_time_ist(self, time_str: str) -> str:
        try:
            parts = time_str.split(":")
            h, m = int(parts[0]), int(parts[1])
            return datetime.strptime(f"{h:02d}:{m:02d}", "%H:%M").strftime("%I:%M %p IST")
        except Exception:
            return f"{time_str} IST"

    def get_strategy_ledger(self, strategy_id: Optional[str] = "UT_BOT") -> StrategyLedger:
        """Resolve or initialize isolated strategy virtual ledger."""
        norm_id = strategy_id or "UT_BOT"
        if norm_id not in self.ledgers:
            if norm_id == "AI_MICRO_SCALPER_V1":
                self.ledgers[norm_id] = StrategyLedger(
                    strategy_id=norm_id,
                    strategy_name="NEXTRADE AI MICRO-SCALPER V1",
                    initial_capital=20000.0,
                    available_cash=20000.0,
                    capital_deployment_cap_pct=90.0,
                    daily_profit_target=500.0,
                    daily_loss_limit=-500.0,
                    max_trades_per_day=5,
                    max_consecutive_losses=2,
                    risk_limits_enabled=True,
                )
            elif norm_id == "UT_BOT":
                self.ledgers[norm_id] = StrategyLedger(
                    strategy_id=norm_id,
                    strategy_name="UT Bot ATM Option Strategy",
                    initial_capital=100000.0,
                    available_cash=100000.0,
                    capital_deployment_cap_pct=90.0,
                    daily_profit_target=None,
                    daily_loss_limit=None,
                    max_trades_per_day=None,
                    max_consecutive_losses=None,
                    risk_limits_enabled=False,  # Explicitly disabled until user approves
                )
            elif norm_id in ("SUPERTREND_EMA", "SUPERTREND_EMA_SCALPER"):
                self.ledgers[norm_id] = StrategyLedger(
                    strategy_id=norm_id,
                    strategy_name="Supertrend + EMA Scalper",
                    initial_capital=50000.0,
                    available_cash=50000.0,
                    capital_deployment_cap_pct=90.0,
                    daily_profit_target=1000.0,
                    daily_loss_limit=-2000.0,
                    max_trades_per_day=10,
                    max_consecutive_losses=3,
                    risk_limits_enabled=True,
                )
            else:
                self.ledgers[norm_id] = StrategyLedger(
                    strategy_id=norm_id,
                    strategy_name=norm_id,
                    initial_capital=self.initial_capital,
                    available_cash=self.cash_balance,
                    capital_deployment_cap_pct=90.0,
                    risk_limits_enabled=False,
                )
        return self.ledgers[norm_id]

    def get_strategy_cash(self, strategy_id: Optional[str] = "UT_BOT") -> float:
        """Return available cash for a strategy's isolated virtual ledger."""
        return self.get_strategy_ledger(strategy_id).available_cash

    def reset(self, strategy_id: Optional[str] = None):
        """Reset broker virtual capital, active position, and closed trades history."""
        if strategy_id:
            ledger = self.get_strategy_ledger(strategy_id)
            ledger.available_cash = ledger.initial_capital
            ledger.reserved_capital = 0.0
            ledger.realized_gross_pnl = 0.0
            ledger.realized_net_pnl = 0.0
            ledger.total_charges = 0.0
            ledger.slippage_cost = 0.0
            ledger.active_position = None
            if self.active_position and self.active_position.get("strategy_id") == strategy_id:
                self.active_position = None
        else:
            self.cash_balance = self.initial_capital
            self.active_position = None
            self.closed_trades.clear()
            for ledger in self.ledgers.values():
                ledger.available_cash = ledger.initial_capital
                ledger.reserved_capital = 0.0
                ledger.realized_gross_pnl = 0.0
                ledger.realized_net_pnl = 0.0
                ledger.total_charges = 0.0
                ledger.slippage_cost = 0.0
                ledger.active_position = None
        self.session_cutoff_active = False
        self.auto_exit_awaiting_valid_data = False
        self.auto_exit_warning = None
        self.auto_exit_last_status = f"STANDBY: Scheduled for {self._format_time_ist(self.auto_close_time_ist)}"

    def calculate_risk_parameters(
        self,
        lots: int,
        lot_size: int,
        entry_price: float,
        target_points: Optional[float] = None,
        stop_points: Optional[float] = None,
        max_loss_per_trade: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Calculate quantity, maximum loss points, effective stop distance, target, and stop prices.
        Supports baseline profile (pure point stop) and capped profile (₹1,000 maximum loss cap).
        Effective SL Distance = MIN(Configured SL Points, Max Loss Amount / Quantity)
        """
        quantity = lots * lot_size
        tp = float(target_points) if target_points is not None else self.target_points
        sl = float(stop_points) if stop_points is not None else self.stop_points
        ml = float(max_loss_per_trade) if max_loss_per_trade is not None else self.max_loss_per_trade

        if ml and ml > 0:
            max_loss_pts = round(ml / max(1, quantity), 4)
            effective_stop_dist = min(sl, max_loss_pts)
        else:
            max_loss_pts = sl
            effective_stop_dist = sl

        target_price = round(entry_price + tp, 2)
        stop_price = round(entry_price - effective_stop_dist, 2)

        return {
            "entry_price": entry_price,
            "quantity": quantity,
            "configured_target_points": round(tp, 2),
            "configured_stop_points": round(sl, 2),
            "configured_sl_points": round(sl, 2),
            "effective_stop_distance": round(effective_stop_dist, 2),
            "effective_sl_points": round(effective_stop_dist, 4),
            "effective_target_distance": round(tp, 2),
            "effective_target_points": round(tp, 2),
            "target_price": target_price,
            "stop_price": stop_price,
            "sl_trigger_price": stop_price,
            "target_trigger_price": target_price,
            "max_loss_points": round(max_loss_pts, 2),
        }

    async def load_charges_settings(self):
        """Load configured paper trading charges from database."""
        try:
            from backend.app.models import ChargeSetting
            async with AsyncSessionLocal() as session:
                stmt = select(ChargeSetting).order_by(ChargeSetting.id.desc())
                res = await session.execute(stmt)
                setting = res.scalars().first()
                if setting:
                    self.charges_calc.entry_charge_per_order = float(setting.entry_charge_per_order)
                    self.charges_calc.exit_charge_per_order = float(setting.exit_charge_per_order)
                    logger.info(
                        f"Loaded paper trading charges: Entry ₹{self.charges_calc.entry_charge_per_order}, "
                        f"Exit ₹{self.charges_calc.exit_charge_per_order} (Total: ₹{round(self.charges_calc.entry_charge_per_order + self.charges_calc.exit_charge_per_order, 2)})"
                    )
        except Exception as e:
            logger.warning(f"Could not load charge settings from DB (using defaults): {e}")

    async def update_charges_settings(self, entry_charge: float, exit_charge: float) -> Dict[str, float]:
        """Update and persist paper trading charges settings."""
        self.charges_calc.entry_charge_per_order = float(entry_charge)
        self.charges_calc.exit_charge_per_order = float(exit_charge)
        from backend.app.models import ChargeSetting
        async with AsyncSessionLocal() as session:
            stmt = select(ChargeSetting).order_by(ChargeSetting.id.desc())
            res = await session.execute(stmt)
            setting = res.scalars().first()
            if setting:
                setting.entry_charge_per_order = float(entry_charge)
                setting.exit_charge_per_order = float(exit_charge)
            else:
                setting = ChargeSetting(
                    entry_charge_per_order=float(entry_charge),
                    exit_charge_per_order=float(exit_charge)
                )
                session.add(setting)
            await session.commit()
        logger.info(f"Updated paper trading charge settings: Entry ₹{entry_charge}, Exit ₹{exit_charge}")
        return {
            "entry_charge_per_order": float(entry_charge),
            "exit_charge_per_order": float(exit_charge),
            "total_roundtrip_charge": round(float(entry_charge) + float(exit_charge), 2)
        }

    async def load_auto_exit_settings(self):
        """Load configured Auto Exit settings from database."""
        try:
            from backend.app.models import AutoExitSetting
            async with AsyncSessionLocal() as session:
                stmt = select(AutoExitSetting).order_by(AutoExitSetting.id.desc())
                res = await session.execute(stmt)
                setting = res.scalars().first()
                if setting:
                    self.auto_exit_enabled = bool(setting.enabled)
                    self.auto_close_time_ist = setting.auto_close_time or "15:20"
                    self.auto_exit_apply_all = bool(setting.apply_to_all_strategies)
                    self.auto_exit_close_profitable = bool(setting.close_profitable)
                    self.auto_exit_close_losing = bool(setting.close_losing)
                    if setting.last_status:
                        self.auto_exit_last_status = setting.last_status
                    self.auto_exit_last_run_time = setting.last_run_time
                    self.auto_exit_last_run_date = setting.last_run_date
                    logger.info(
                        f"Loaded Auto Exit settings: Enabled={self.auto_exit_enabled}, "
                        f"Time={self.auto_close_time_ist} IST, ApplyAll={self.auto_exit_apply_all}, "
                        f"CloseProfitable={self.auto_exit_close_profitable}, CloseLosing={self.auto_exit_close_losing}"
                    )
        except Exception as e:
            logger.warning(f"Could not load auto exit settings from DB (using defaults): {e}")

    async def update_auto_exit_settings(
        self,
        enabled: bool,
        auto_close_time: str,
        apply_to_all_strategies: bool = True,
        close_profitable: bool = True,
        close_losing: bool = True
    ) -> Dict[str, Any]:
        """Update and persist Auto Exit configuration."""
        self.auto_exit_enabled = bool(enabled)
        clean_time = auto_close_time.strip()
        if len(clean_time) == 4 and clean_time[1] == ":":
            clean_time = "0" + clean_time
        self.auto_close_time_ist = clean_time
        self.auto_exit_apply_all = bool(apply_to_all_strategies)
        self.auto_exit_close_profitable = bool(close_profitable)
        self.auto_exit_close_losing = bool(close_losing)

        from backend.app.models import AutoExitSetting
        async with AsyncSessionLocal() as session:
            stmt = select(AutoExitSetting).order_by(AutoExitSetting.id.desc())
            res = await session.execute(stmt)
            setting = res.scalars().first()
            if setting:
                setting.enabled = self.auto_exit_enabled
                setting.auto_close_time = self.auto_close_time_ist
                setting.apply_to_all_strategies = self.auto_exit_apply_all
                setting.close_profitable = self.auto_exit_close_profitable
                setting.close_losing = self.auto_exit_close_losing
            else:
                setting = AutoExitSetting(
                    enabled=self.auto_exit_enabled,
                    auto_close_time=self.auto_close_time_ist,
                    apply_to_all_strategies=self.auto_exit_apply_all,
                    close_profitable=self.auto_exit_close_profitable,
                    close_losing=self.auto_exit_close_losing,
                    last_status=self.auto_exit_last_status
                )
                session.add(setting)
            await session.commit()

        logger.info(
            f"Persisted Auto Exit settings: Enabled={self.auto_exit_enabled}, Time={self.auto_close_time_ist} IST, "
            f"ApplyAll={self.auto_exit_apply_all}, CloseProfitable={self.auto_exit_close_profitable}, CloseLosing={self.auto_exit_close_losing}"
        )
        return self.get_auto_exit_status_dict()

    def get_auto_exit_status_dict(self, now: Optional[datetime] = None) -> Dict[str, Any]:
        """Return comprehensive auto exit status, schedule, countdown, and active warnings."""
        curr_dt = now or datetime.now(timezone.utc)
        ist_now = curr_dt.astimezone(IST)
        today_date = ist_now.date()

        try:
            parts = self.auto_close_time_ist.split(":")
            h, m = int(parts[0]), int(parts[1])
        except Exception:
            h, m = 15, 20

        target_time = datetime(today_date.year, today_date.month, today_date.day, h, m, 0, tzinfo=IST)
        diff = (target_time - ist_now).total_seconds()
        if diff > 0:
            remaining_seconds = int(diff)
            hrs = remaining_seconds // 3600
            mins = (remaining_seconds % 3600) // 60
            secs = remaining_seconds % 60
            if hrs > 0:
                time_remaining_str = f"{hrs}h {mins}m {secs}s"
            else:
                time_remaining_str = f"{mins}m {secs}s"
            session_ended = False
        else:
            remaining_seconds = 0
            time_remaining_str = "Cutoff passed (Session Ended)"
            session_ended = True

        display_12h = datetime.strptime(f"{h:02d}:{m:02d}", "%H:%M").strftime("%I:%M %p IST")

        return {
            "enabled": self.auto_exit_enabled,
            "auto_close_time": self.auto_close_time_ist,
            "auto_close_time_display": display_12h,
            "apply_to_all_strategies": self.auto_exit_apply_all,
            "close_profitable": self.auto_exit_close_profitable,
            "close_losing": self.auto_exit_close_losing,
            "last_status": self.auto_exit_last_status,
            "last_run_time": self.auto_exit_last_run_time.isoformat() if self.auto_exit_last_run_time else None,
            "awaiting_valid_data": self.auto_exit_awaiting_valid_data,
            "execution_warning": self.auto_exit_warning,
            "time_remaining_seconds": remaining_seconds,
            "time_remaining_display": time_remaining_str,
            "session_cutoff_active": self.session_cutoff_active or (self.auto_exit_enabled and session_ended),
            "open_positions_count": 1 if self.active_position is not None else 0,
            "unrealized_pnl": self.active_position["net_pnl"] if self.active_position is not None else 0.0
        }

    async def restore_from_db(self):
        """
        Restore virtual ledgers, open positions, and daily risk counters from database upon backend startup.
        Reconciles cash balance and trade history independently per strategy ledger.
        """
        try:
            # 0. Load persisted paper trading charge settings & auto-exit settings
            await self.load_charges_settings()
            await self.load_auto_exit_settings()

            async with AsyncSessionLocal() as session:
                # 1. Load persisted StrategyVirtualAccount records
                stmt_acc = select(StrategyVirtualAccount)
                res_acc = await session.execute(stmt_acc)
                accounts = res_acc.scalars().all()
                for acc in accounts:
                    self.ledgers[acc.strategy_id] = StrategyLedger(
                        strategy_id=acc.strategy_id,
                        strategy_name=acc.strategy_name,
                        initial_capital=float(acc.initial_capital),
                        available_cash=float(acc.available_cash),
                        reserved_capital=float(acc.reserved_capital),
                        realized_gross_pnl=float(acc.realized_gross_pnl),
                        realized_net_pnl=float(acc.realized_net_pnl),
                        total_charges=float(acc.total_charges),
                        slippage_cost=float(acc.slippage_cost),
                        capital_deployment_cap_pct=float(acc.capital_deployment_cap_pct),
                        daily_profit_target=float(acc.daily_profit_target) if acc.daily_profit_target is not None else None,
                        daily_loss_limit=float(acc.daily_loss_limit) if acc.daily_loss_limit is not None else None,
                        max_trades_per_day=int(acc.max_trades_per_day) if acc.max_trades_per_day is not None else None,
                        max_consecutive_losses=int(acc.max_consecutive_losses) if acc.max_consecutive_losses is not None else None,
                        risk_limits_enabled=bool(acc.risk_limits_enabled),
                    )

                # Ensure standard strategy ledgers exist with exact configured settings
                self.get_strategy_ledger("UT_BOT")
                self.get_strategy_ledger("AI_MICRO_SCALPER_V1")
                self.get_strategy_ledger("SUPERTREND_EMA")
                self.get_strategy_ledger("SUPERTREND_EMA_SCALPER")

                # 2. Reconcile trade P&L from PaperTrade per strategy (Strict accounting ledger)
                stmt_trades = select(PaperTrade)
                res_trades = await session.execute(stmt_trades)
                trades = res_trades.scalars().all()

                strat_trades: Dict[str, List[PaperTrade]] = {}
                for t in trades:
                    sid = getattr(t, "strategy_id", "UT_BOT")
                    strat_trades.setdefault(sid, []).append(t)

                for sid, t_list in strat_trades.items():
                    ledger = self.get_strategy_ledger(sid)
                    tot_gross = sum(float(t.gross_pnl) for t in t_list)
                    tot_chg = sum(float(t.total_charges) for t in t_list)
                    tot_net = sum(float(t.net_pnl) for t in t_list)
                    tot_slip = sum(float(getattr(t, "slippage_cost", 0.0) or 0.0) for t in t_list)

                    ledger.realized_gross_pnl = round(tot_gross, 2)
                    ledger.total_charges = round(tot_chg, 2)
                    ledger.realized_net_pnl = round(tot_net, 2)
                    ledger.slippage_cost = round(tot_slip, 2)
                    ledger.available_cash = round(ledger.initial_capital + tot_net - ledger.reserved_capital, 2)
                    logger.info(
                        f"Reconciled Strategy Ledger '{sid}': Initial ₹{ledger.initial_capital}, "
                        f"Net P&L ₹{ledger.realized_net_pnl} ({len(t_list)} trades), Available Cash ₹{ledger.available_cash}"
                    )

                # 2b. Sync or upsert PaperAccount records for all active strategy ledgers
                for sid, ledger in self.ledgers.items():
                    stmt_pa = select(PaperAccount).where(PaperAccount.strategy_id == sid)
                    res_pa = await session.execute(stmt_pa)
                    pa = res_pa.scalar_one_or_none()
                    if not pa:
                        pa = PaperAccount(
                            strategy_id=sid,
                            account_name=ledger.strategy_name,
                            account_number=f"ACC-{sid}",
                            initial_capital=ledger.initial_capital,
                            available_balance=ledger.available_cash,
                            reserved_capital=ledger.reserved_capital,
                            realized_pnl=ledger.realized_net_pnl,
                            unrealized_pnl=0.0,
                            total_charges=ledger.total_charges,
                            total_slippage=ledger.slippage_cost,
                            capital_deployment_cap_pct=ledger.capital_deployment_cap_pct,
                            currency="INR",
                            is_active=True
                        )
                        session.add(pa)
                    else:
                        pa.account_name = ledger.strategy_name
                        pa.initial_capital = ledger.initial_capital
                        pa.available_balance = ledger.available_cash
                        pa.reserved_capital = ledger.reserved_capital
                        pa.realized_pnl = ledger.realized_net_pnl
                        pa.total_charges = ledger.total_charges
                        pa.total_slippage = ledger.slippage_cost
                        pa.capital_deployment_cap_pct = ledger.capital_deployment_cap_pct

                # Backward compatibility: set global cash_balance to active strategy or UT_BOT
                self.cash_balance = self.get_strategy_ledger("UT_BOT").available_cash

                # 3. Restore genuine OPEN position if one exists
                stmt_pos = select(PaperPosition).where(PaperPosition.status == "OPEN").order_by(PaperPosition.id.desc())
                res_pos = await session.execute(stmt_pos)
                open_candidates = res_pos.scalars().all()
                open_pos = None

                for cand in open_candidates:
                    # Check if a newer closed position exists for this strategy
                    stmt_newer = select(PaperPosition).where(
                        PaperPosition.strategy_id == cand.strategy_id,
                        PaperPosition.id > cand.id,
                        PaperPosition.status == "CLOSED"
                    )
                    res_newer = await session.execute(stmt_newer)
                    if res_newer.scalars().first():
                        # Orphaned duplicate from past race condition - mark closed
                        cand.status = "CLOSED"
                        cand.exit_reason = "ORPHANED_CONCURRENCY_CLEANUP"
                        cand.exit_time = cand.entry_time
                    else:
                        if open_pos is None:
                            open_pos = cand
                        else:
                            cand.status = "CLOSED"
                            cand.exit_reason = "DUPLICATE_CONCURRENCY_CLEANUP"
                            cand.exit_time = cand.entry_time

                await session.commit()

                if open_pos:
                    pos_sid = getattr(open_pos, "strategy_id", "UT_BOT")
                    pos_dict = {
                        "id": open_pos.id,
                        "strategy_id": pos_sid,
                        "strategy_config": getattr(open_pos, "strategy_config", None),
                        "instrument_token": open_pos.instrument_token,
                        "symbol": open_pos.symbol,
                        "strike": open_pos.strike,
                        "expiry": open_pos.expiry,
                        "lot_size": open_pos.lot_size,
                        "lots": open_pos.lots,
                        "quantity": open_pos.quantity,
                        "entry_price": open_pos.entry_price,
                        "current_price": open_pos.current_price,
                        "target_price": open_pos.target_price,
                        "stop_price": open_pos.stop_price,
                        "effective_stop_distance": open_pos.effective_stop_distance,
                        "max_loss_amount": open_pos.max_loss_amount,
                        "highest_price": open_pos.highest_price,
                        "lowest_price": open_pos.lowest_price,
                        "entry_time": open_pos.entry_time,
                        "status": "OPEN",
                        "gross_pnl": open_pos.gross_pnl,
                        "net_pnl": open_pos.net_pnl,
                        "charges": open_pos.charges
                    }
                    self.active_position = pos_dict
                    pos_ledger = self.get_strategy_ledger(pos_sid)
                    pos_ledger.active_position = pos_dict
                    req_margin = round(open_pos.entry_price * open_pos.quantity, 2)
                    pos_ledger.reserved_capital = req_margin
                    pos_ledger.available_cash = round(pos_ledger.initial_capital + pos_ledger.realized_net_pnl - req_margin, 2)
                    logger.info(f"Restored open paper position from DB: ID {open_pos.id} for {open_pos.symbol} (Strategy: {pos_sid})")

                    # Record system event
                    evt = SystemEvent(
                        event_type="RESTART_RECOVERY",
                        title="Open Position Restored",
                        message=f"Restored open position #{open_pos.id} ({open_pos.symbol}) after restart.",
                        details_json=f'{{"position_id": {open_pos.id}, "symbol": "{open_pos.symbol}", "strategy_id": "{pos_sid}"}}'
                    )
                    session.add(evt)
                    await session.commit()
        except Exception as e:
            logger.error(f"Error restoring ledgers and positions from DB: {e}", exc_info=True)

    async def get_daily_risk_status(
        self,
        strategy_id: str = "SUPERTREND_EMA",
        now: Optional[datetime] = None,
        daily_profit_target: Optional[float] = None,
        daily_loss_limit: Optional[float] = None,
        max_trades_per_day: Optional[int] = None,
        max_consecutive_losses: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Calculate and persist daily net P&L, trade counters, and risk locks for a strategy.
        Enforces:
        - Daily NET profit target (+₹500 for Micro-Scalper): blocks new entries when reached.
        - Daily NET loss limit (-₹500 for Micro-Scalper): blocks new entries when reached.
        - Daily maximum accepted trade count (5 trades for Micro-Scalper): blocks new entries when reached.
        - Consecutive losses limit (2 for Micro-Scalper): blocks new entries when reached.
        - Recalculated from actual trade ledger (PaperTrade & PaperPosition).
        - Persisted across page refreshes and backend restarts.
        - Resets only on the next valid trading session date (in IST).
        """
        curr_dt = now or datetime.now(timezone.utc)
        ist_now = curr_dt.astimezone(IST)
        today_date_str = ist_now.strftime("%Y-%m-%d")

        ledger = self.get_strategy_ledger(strategy_id)
        pt = daily_profit_target if daily_profit_target is not None else ledger.daily_profit_target
        ll = daily_loss_limit if daily_loss_limit is not None else ledger.daily_loss_limit
        mt = max_trades_per_day if max_trades_per_day is not None else ledger.max_trades_per_day
        mcl = max_consecutive_losses if max_consecutive_losses is not None else ledger.max_consecutive_losses
        risk_enabled = ledger.risk_limits_enabled

        realized_net = 0.0
        gross_total = 0.0
        charges_total = 0.0
        trade_count = 0
        winning_trades = 0
        losing_trades = 0
        consecutive_losses = 0
        accepted_entries_count = 0

        try:
            async with AsyncSessionLocal() as session:
                # 1. Query all closed paper trades for this strategy today
                stmt = select(PaperTrade).where(
                    PaperTrade.strategy_id == strategy_id
                ).order_by(PaperTrade.exit_time.asc())
                res = await session.execute(stmt)
                all_trades = res.scalars().all()

                today_trades: List[PaperTrade] = []
                for t in all_trades:
                    t_exit_ist = t.exit_time.astimezone(IST) if t.exit_time.tzinfo else t.exit_time.replace(tzinfo=timezone.utc).astimezone(IST)
                    if t_exit_ist.strftime("%Y-%m-%d") == today_date_str:
                        today_trades.append(t)
                        realized_net += float(t.net_pnl)
                        gross_total += float(t.gross_pnl)
                        charges_total += float(t.total_charges)
                        trade_count += 1
                        if t.is_win:
                            winning_trades += 1
                        else:
                            losing_trades += 1

                # Calculate consecutive losses streak at end of day
                for t in today_trades:
                    if not t.is_win or float(t.net_pnl) < 0:
                        consecutive_losses += 1
                    else:
                        consecutive_losses = 0

                realized_net = round(realized_net, 2)
                gross_total = round(gross_total, 2)
                charges_total = round(charges_total, 2)

                # 2. Count accepted entries today from PaperPosition (includes active open positions)
                stmt_pos = select(PaperPosition).where(
                    PaperPosition.strategy_id == strategy_id
                )
                res_pos = await session.execute(stmt_pos)
                all_pos = res_pos.scalars().all()

                accepted_today = 0
                for p in all_pos:
                    p_entry_ist = p.entry_time.astimezone(IST) if p.entry_time.tzinfo else p.entry_time.replace(tzinfo=timezone.utc).astimezone(IST)
                    if p_entry_ist.strftime("%Y-%m-%d") == today_date_str:
                        accepted_today += 1

                accepted_entries_count = max(trade_count, accepted_today)

                # 3. Determine lock status
                is_locked = False
                lock_reason = "NONE"
                status_text = "ACTIVE"

                if not risk_enabled:
                    is_locked = False
                    lock_reason = "NONE"
                    status_text = "RISK_LIMITS_DISABLED"
                else:
                    if pt is not None and realized_net >= pt:
                        is_locked = True
                        lock_reason = "DAILY_PROFIT_LOCKED"
                        status_text = f"Daily Profit Target Reached (+₹{realized_net})"
                    elif ll is not None and realized_net <= ll:
                        is_locked = True
                        lock_reason = "DAILY_LOSS_LOCKED"
                        status_text = f"Daily Loss Limit Reached (-₹{abs(realized_net)})"
                    elif mt is not None and (trade_count >= mt or accepted_entries_count >= mt):
                        is_locked = True
                        lock_reason = "MAX_DAILY_TRADES_LOCKED"
                        status_text = f"Maximum Daily Trades Reached ({max(trade_count, accepted_entries_count)}/{mt})"
                    elif mcl is not None and consecutive_losses >= mcl:
                        is_locked = True
                        lock_reason = "CONSECUTIVE_LOSS_LOCKED"
                        status_text = f"Consecutive Loss Limit Reached ({consecutive_losses}/{mcl})"

                # 4. Persist or update StrategyDailyRisk record
                stmt_risk = select(StrategyDailyRisk).where(
                    StrategyDailyRisk.strategy_id == strategy_id,
                    StrategyDailyRisk.trading_date == today_date_str
                )
                res_risk = await session.execute(stmt_risk)
                risk_rec = res_risk.scalars().first()

                if risk_rec:
                    # Preserve existing active lock across restart if already locked today
                    if risk_rec.is_locked and risk_rec.lock_reason and risk_rec.lock_reason != "NONE":
                        is_locked = True
                        lock_reason = risk_rec.lock_reason
                        status_text = f"Strategy Locked ({lock_reason})"

                    risk_rec.realized_net_pnl = realized_net
                    risk_rec.gross_pnl = gross_total
                    risk_rec.total_charges = charges_total
                    risk_rec.trade_count = trade_count
                    risk_rec.accepted_entries_count = accepted_entries_count
                    risk_rec.winning_trades = winning_trades
                    risk_rec.losing_trades = losing_trades
                    risk_rec.consecutive_losses = consecutive_losses
                    risk_rec.is_locked = is_locked
                    risk_rec.lock_reason = lock_reason
                    if is_locked and not risk_rec.locked_at:
                        risk_rec.locked_at = curr_dt
                else:
                    risk_rec = StrategyDailyRisk(
                        strategy_id=strategy_id,
                        trading_date=today_date_str,
                        realized_net_pnl=realized_net,
                        gross_pnl=gross_total,
                        total_charges=charges_total,
                        trade_count=trade_count,
                        accepted_entries_count=accepted_entries_count,
                        winning_trades=winning_trades,
                        losing_trades=losing_trades,
                        consecutive_losses=consecutive_losses,
                        is_locked=is_locked,
                        lock_reason=lock_reason,
                        locked_at=curr_dt if is_locked else None
                    )
                    session.add(risk_rec)

                await session.commit()

        except Exception as e:
            logger.error(f"Error checking/persisting daily risk status for {strategy_id}: {e}")

        # Compute progress percentages
        profit_progress = round(min(100.0, max(0.0, (realized_net / pt) * 100.0)), 1) if pt and pt > 0 else 0.0
        loss_progress = round(min(100.0, max(0.0, (abs(min(0.0, realized_net)) / abs(ll)) * 100.0)), 1) if ll and ll < 0 else 0.0

        return {
            "strategy_id": strategy_id,
            "trading_date": today_date_str,
            "realized_net_pnl": realized_net,
            "gross_pnl": gross_total,
            "total_charges": charges_total,
            "trade_count": trade_count,
            "accepted_entries_count": accepted_entries_count,
            "winning_trades": winning_trades,
            "losing_trades": losing_trades,
            "consecutive_losses": consecutive_losses,
            "daily_profit_target": pt,
            "daily_loss_limit": ll,
            "max_trades_per_day": mt,
            "max_consecutive_losses": mcl,
            "profit_target_progress_pct": profit_progress,
            "loss_limit_progress_pct": loss_progress,
            "is_locked": is_locked,
            "lock_reason": lock_reason,
            "status_text": status_text
        }

    async def execute_buy(
        self,
        contract: Dict[str, Any],
        current_premium: float,
        underlying_price: float,
        signal_id: Optional[int] = None,
        lots: Optional[int] = None,
        timestamp: Optional[datetime] = None,
        bypass_session_check: bool = False,
        strategy_id: str = "EMA_RSI",
        strategy_config: Optional[str] = None,
        target_points: Optional[float] = None,
        stop_points: Optional[float] = None,
        max_loss_per_trade: Optional[float] = None,
        execution_mode: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Execute paper BUY order for ATM CE option.
        Enforces:
        - Atomic concurrency locking via _execution_lock.
        - Strategy-isolated buying power and capital deployment cap validation.
        - Strategy-specific daily risk limit check (profit lock, loss lock, max trade gate).
        - Capital margin reservation on entry.
        - Only 1 open position per strategy / broker.
        - Slippage on entry (in REALISTIC mode; zero in TRIGGER_PRICE mode).
        - Strategy identification and config snapshot persistence.
        - Transaction-safe DB persistence and virtual ledger updates.
        """
        async with self._execution_lock:
            if self.active_position is not None:
                logger.warning("Paper BUY rejected: Already have an open position.")
                return None

            ledger = self.get_strategy_ledger(strategy_id)
            if ledger.active_position is not None:
                logger.warning(f"Paper BUY rejected: Strategy {strategy_id} already has an open position.")
                return None

            # Check force exit time cutoff and auto-close session cutoff
            now = timestamp or datetime.now(timezone.utc)
            ist_time = now.astimezone(IST).strftime("%H:%M")
            if not bypass_session_check:
                if self.auto_exit_enabled and (ist_time >= self.auto_close_time_ist or self.session_cutoff_active):
                    logger.warning(
                        f"Paper BUY rejected: Auto-close session cutoff active (IST: {ist_time} >= {self.auto_close_time_ist}). "
                        f"New entries prohibited for remainder of session."
                    )
                    return None
                elif ist_time >= self.force_exit_time_ist or ist_time > "15:15":
                    logger.warning(f"Paper BUY rejected: Outside permissible entry time window (Current IST: {ist_time}).")
                    return None

            # Check strategy daily risk limit
            if not bypass_session_check and ledger.risk_limits_enabled:
                daily_risk = await self.get_daily_risk_status(strategy_id=strategy_id, now=now)
                if daily_risk.get("is_locked", False):
                    reason = daily_risk.get("lock_reason", "DAILY_RISK_LOCKED")
                    status_txt = daily_risk.get("status_text", "")
                    logger.warning(
                        f"Paper BUY rejected: {strategy_id} daily risk lock active ({reason}: {status_txt}). "
                        f"Net P&L: ₹{daily_risk.get('realized_net_pnl')}."
                    )
                    try:
                        async with AsyncSessionLocal() as session:
                            evt = SystemEvent(
                                event_type="RISK_REJECTION",
                                title=f"{strategy_id} Risk Lock Rejection",
                                message=f"Order rejected: {reason} - {status_txt}",
                                details_json=json.dumps({
                                    "strategy_id": strategy_id,
                                    "reason": reason,
                                    "status_text": status_txt,
                                    "daily_risk": daily_risk
                                })
                            )
                            session.add(evt)
                            risk_evt = PaperRiskEvent(
                                strategy_id=strategy_id,
                                trading_date=now.strftime("%Y-%m-%d"),
                                risk_event_type="DAILY_RISK_LOCKED",
                                trigger_metric_name="net_pnl",
                                metric_value=float(daily_risk.get('realized_net_pnl', 0.0)),
                                threshold_value=0.0,
                                action_taken="ENTRY_REJECTED",
                                details=f"{reason}: {status_txt}"
                            )
                            session.add(risk_evt)
                            exec_log = PaperExecutionLog(
                                strategy_id=strategy_id,
                                action="ORDER_REJECTED",
                                level="WARNING",
                                message=f"Risk Lock Rejection: {reason} - {status_txt}"
                            )
                            session.add(exec_log)
                            await session.commit()
                    except Exception as e:
                        logger.error(f"Could not persist risk rejection event: {e}")
                    return None

            num_lots = lots or self.default_lots
            lot_size = contract.get("lot_size", 65)

            mode = execution_mode or getattr(self, "execution_mode", "TRIGGER_PRICE")
            if mode == "TRIGGER_PRICE":
                entry_slip = 0.0
                executed_entry_price = round(current_premium, 2)
            else:
                entry_slip = self.slippage_points
                executed_entry_price = round(current_premium + self.slippage_points, 2)

            risk = self.calculate_risk_parameters(
                num_lots,
                lot_size,
                executed_entry_price,
                target_points=target_points,
                stop_points=stop_points,
                max_loss_per_trade=max_loss_per_trade
            )

            entry_chg = self.charges_calc.entry_charge_per_order
            exit_chg = self.charges_calc.exit_charge_per_order
            est_total_chg = round(entry_chg + exit_chg, 2)

            # Buying power & Capital deployment validation
            required_margin = round(executed_entry_price * risk["quantity"], 2)
            max_deployable = round(ledger.available_cash * (ledger.capital_deployment_cap_pct / 100.0), 2)

            if required_margin > max_deployable or (required_margin + est_total_chg) > ledger.available_cash:
                rej_msg = (
                    f"Paper BUY rejected: Insufficient buying power for {strategy_id}. "
                    f"Required margin ₹{required_margin:.2f} (charges ~₹{est_total_chg:.2f}) exceeds "
                    f"deployable capital ₹{max_deployable:.2f} (Available cash: ₹{ledger.available_cash:.2f}, "
                    f"Cap: {ledger.capital_deployment_cap_pct}%)."
                )
                logger.warning(rej_msg)
                try:
                    async with AsyncSessionLocal() as session:
                        evt = SystemEvent(
                            event_type="RISK_REJECTION",
                            title=f"{strategy_id} Buying Power Rejection",
                            message=rej_msg,
                            details_json=json.dumps({
                                "strategy_id": strategy_id,
                                "required_margin": required_margin,
                                "max_deployable": max_deployable,
                                "available_cash": ledger.available_cash,
                                "cap_pct": ledger.capital_deployment_cap_pct
                            })
                        )
                        session.add(evt)
                        risk_evt = PaperRiskEvent(
                            strategy_id=strategy_id,
                            trading_date=now.strftime("%Y-%m-%d"),
                            risk_event_type="BUYING_POWER_EXCEEDED",
                            trigger_metric_name="required_margin",
                            metric_value=required_margin,
                            threshold_value=max_deployable,
                            action_taken="ENTRY_REJECTED",
                            details=rej_msg
                        )
                        session.add(risk_evt)
                        exec_log = PaperExecutionLog(
                            strategy_id=strategy_id,
                            action="ORDER_REJECTED",
                            level="WARNING",
                            message=rej_msg
                        )
                        session.add(exec_log)
                        await session.commit()
                except Exception as e:
                    logger.error(f"Could not persist buying power rejection event: {e}")
                return None

            # Reserve capital in virtual ledger
            ledger.available_cash = round(ledger.available_cash - required_margin, 2)
            ledger.reserved_capital = round(ledger.reserved_capital + required_margin, 2)

            position_data = {
                "strategy_id": strategy_id,
                "strategy_config": strategy_config,
                "instrument_token": contract.get("instrument_token") or contract.get("token", "OPT"),
                "symbol": contract["symbol"],
                "strike": contract["strike"],
                "expiry": contract["expiry"],
                "lot_size": lot_size,
                "lots": num_lots,
                "quantity": risk["quantity"],
                "entry_price": executed_entry_price,
                "current_price": executed_entry_price,
                "target_price": risk["target_price"],
                "stop_price": risk["stop_price"],
                "configured_sl_points": risk.get("configured_stop_points", 2.0),
                "configured_target_points": risk.get("configured_target_points", 4.0),
                "effective_sl_points": risk.get("effective_stop_distance", 2.0),
                "effective_target_points": risk.get("effective_target_distance", 4.0),
                "sl_trigger_price": risk.get("sl_trigger_price", risk["stop_price"]),
                "target_trigger_price": risk.get("target_trigger_price", risk["target_price"]),
                "effective_stop_distance": risk["effective_stop_distance"],
                "max_loss_amount": max_loss_per_trade if max_loss_per_trade is not None else self.max_loss_per_trade,
                "highest_price": executed_entry_price,
                "lowest_price": executed_entry_price,
                "entry_time": now,
                "status": "OPEN",
                "underlying_price_at_entry": underlying_price,
                "signal_id": signal_id,
                "gross_pnl": 0.0,
                "net_pnl": -est_total_chg,
                "entry_charge": entry_chg,
                "exit_charge": exit_chg,
                "charges": est_total_chg,
                "entry_slippage": entry_slip,
                "execution_mode": mode
            }

            # Persist position, order, and virtual account state to DB
            async with AsyncSessionLocal() as session:
                pos_db = PaperPosition(
                    strategy_id=position_data["strategy_id"],
                    strategy_config=position_data["strategy_config"],
                    instrument_token=position_data["instrument_token"],
                    symbol=position_data["symbol"],
                    strike=position_data["strike"],
                    expiry=position_data["expiry"],
                    lot_size=position_data["lot_size"],
                    lots=position_data["lots"],
                    quantity=position_data["quantity"],
                    entry_price=position_data["entry_price"],
                    current_price=position_data["current_price"],
                    target_price=position_data["target_price"],
                    stop_price=position_data["stop_price"],
                    effective_stop_distance=position_data["effective_stop_distance"],
                    max_loss_amount=position_data["max_loss_amount"],
                    configured_sl_points=position_data["configured_sl_points"],
                    configured_target_points=position_data["configured_target_points"],
                    effective_sl_points=position_data["effective_sl_points"],
                    effective_target_points=position_data["effective_target_points"],
                    sl_trigger_price=position_data["sl_trigger_price"],
                    target_trigger_price=position_data["target_trigger_price"],
                    slippage_cost=0.0,
                    execution_mode=position_data["execution_mode"],
                    highest_price=position_data["highest_price"],
                    lowest_price=position_data["lowest_price"],
                    status="OPEN",
                    entry_time=now,
                    gross_pnl=0.0,
                    entry_charge=entry_chg,
                    exit_charge=exit_chg,
                    charges=est_total_chg,
                    net_pnl=-est_total_chg
                )
                session.add(pos_db)
                await session.flush()

                order_db = PaperOrder(
                    position_id=pos_db.id,
                    order_type="MARKET",
                    transaction_type="BUY",
                    instrument_token=position_data["instrument_token"],
                    symbol=position_data["symbol"],
                    strike=position_data["strike"],
                    expiry=position_data["expiry"],
                    quantity=position_data["quantity"],
                    requested_price=current_premium,
                    executed_price=executed_entry_price,
                    slippage=entry_slip,
                    status="FILLED",
                    created_at=now,
                    filled_at=now
                )
                session.add(order_db)
                await session.flush()

                exec_log = PaperExecutionLog(
                    strategy_id=strategy_id,
                    order_id=order_db.id,
                    position_id=pos_db.id,
                    action="BUY_FILLED",
                    level="INFO",
                    message=f"Paper Buy order filled for {position_data['symbol']} @ ₹{executed_entry_price} (Qty: {position_data['quantity']})"
                )
                session.add(exec_log)

                bal_record = PaperAccountBalance(
                    strategy_id=strategy_id,
                    balance=round(ledger.available_cash + ledger.reserved_capital, 2),
                    available_balance=ledger.available_cash,
                    reserved_margin=ledger.reserved_capital,
                    realized_pnl=ledger.realized_net_pnl,
                    unrealized_pnl=0.0,
                    change_amount=-required_margin,
                    change_reason="TRADE_ENTRY_MARGIN",
                    related_order_id=order_db.id,
                    created_at=now
                )
                session.add(bal_record)

                stmt_acc = update(StrategyVirtualAccount).where(
                    StrategyVirtualAccount.strategy_id == strategy_id
                ).values(
                    available_cash=ledger.available_cash,
                    reserved_capital=ledger.reserved_capital,
                    updated_at=now
                )
                await session.execute(stmt_acc)
                await session.commit()

                position_data["id"] = pos_db.id

            self.active_position = position_data
            ledger.active_position = position_data
            self.cash_balance = ledger.available_cash

            # Update daily risk record to register the accepted entry
            await self.get_daily_risk_status(strategy_id=strategy_id, now=now)

            logger.info(
                f"Paper Position OPENED: {position_data['symbol']} @ ₹{executed_entry_price} | Mode: {mode} | "
                f"Qty: {position_data['quantity']} | Target: ₹{position_data['target_price']} | "
                f"Stop: ₹{position_data['stop_price']} (SL: {position_data['configured_sl_points']} pts, Eff: {position_data['effective_sl_points']} pts)"
            )

            if self.on_position_callback:
                self.on_position_callback(self.active_position)

            return self.active_position
        logger.info(
            f"Paper Position OPENED: {position_data['symbol']} @ ₹{executed_entry_price} | Mode: {mode} | "
            f"Qty: {position_data['quantity']} | Target: ₹{position_data['target_price']} | "
            f"Stop: ₹{position_data['stop_price']} (SL: {position_data['configured_sl_points']} pts, Eff: {position_data['effective_sl_points']} pts)"
        )

        if self.on_position_callback:
            self.on_position_callback(self.active_position)

        return self.active_position

    async def update_tick(self, token: str, current_price: float, timestamp: Optional[datetime] = None) -> Optional[PaperTradeResult]:
        """
        Continuously monitor active position against incoming option ticks.
        Evaluates:
        - Target hit (+4 points)
        - Stop loss hit (-effective stop points)
        - Gaps through stop (honest fill at actual gap price minus slippage)
        - 15:20 IST force exit cutoff
        """
        if self.active_position is None:
            return None

        # Verify token matches active position's contract
        if str(token) != str(self.active_position["instrument_token"]):
            return None

        now = timestamp or datetime.now(timezone.utc)
        pos = self.active_position

        # Update high / low and running P&L
        pos["current_price"] = current_price
        pos["highest_price"] = max(pos.get("highest_price", current_price), current_price)
        pos["lowest_price"] = min(pos.get("lowest_price", current_price), current_price)

        gross_pnl = round((current_price - pos["entry_price"]) * pos["quantity"], 2)
        entry_chg = pos.get("entry_charge", self.charges_calc.entry_charge_per_order)
        exit_chg = pos.get("exit_charge", self.charges_calc.exit_charge_per_order)
        charges = round(entry_chg + exit_chg, 2)
        net_pnl = round(gross_pnl - charges, 2)
        pos["gross_pnl"] = gross_pnl
        pos["net_pnl"] = net_pnl
        pos["charges"] = charges

        # Check Exit Conditions:
        exit_reason: Optional[str] = None
        executed_exit_price = current_price
        exit_slip = 0.0
        mode = pos.get("execution_mode", self.execution_mode)

        # 1. Target Hit (Limit Order Assumption)
        if current_price >= pos["target_price"]:
            exit_reason = "TARGET"
            executed_exit_price = pos["target_price"]
            exit_slip = 0.0

        # 2. Stop Loss Hit (Stop Market Assumption)
        elif current_price <= pos["stop_price"]:
            exit_reason = "GAP_STOP" if current_price < pos["stop_price"] else "STOP_LOSS"
            if mode == "TRIGGER_PRICE":
                executed_exit_price = current_price if current_price < pos["stop_price"] else pos["stop_price"]
                exit_slip = 0.0
            else:
                if current_price < pos["stop_price"]:
                    executed_exit_price = round(current_price - self.slippage_points, 2)
                    exit_slip = round(pos["stop_price"] - executed_exit_price, 2)
                else:
                    executed_exit_price = round(pos["stop_price"] - self.slippage_points, 2)
                    exit_slip = self.slippage_points

        # 3. Force Exit / Auto Close at configured time (default 03:20 PM IST)
        ist_time = now.astimezone(IST).strftime("%H:%M")
        if not exit_reason and self.auto_exit_enabled and ist_time >= self.auto_close_time_ist:
            self.session_cutoff_active = True
            is_profit = gross_pnl > 0 or net_pnl >= 0
            is_loss = gross_pnl < 0 or net_pnl < 0
            should_close = (is_profit and self.auto_exit_close_profitable) or (is_loss and self.auto_exit_close_losing)
            if should_close:
                exit_reason = "AUTO_CLOSE_3_20_PM"
                if mode == "TRIGGER_PRICE":
                    executed_exit_price = current_price
                    exit_slip = 0.0
                else:
                    executed_exit_price = round(current_price - self.slippage_points, 2)
                    exit_slip = self.slippage_points
        elif not exit_reason and ist_time >= self.force_exit_time_ist:
            self.session_cutoff_active = True
            exit_reason = "AUTO_CLOSE_3_20_PM"
            if mode == "TRIGGER_PRICE":
                executed_exit_price = current_price
                exit_slip = 0.0
            else:
                executed_exit_price = round(current_price - self.slippage_points, 2)
                exit_slip = self.slippage_points

        if exit_reason:
            trade_res = await self._close_position(executed_exit_price, exit_reason, now, exit_slippage=exit_slip)
            if exit_reason == "AUTO_CLOSE_3_20_PM":
                self.auto_exit_awaiting_valid_data = False
                self.auto_exit_warning = None
                self.auto_exit_last_status = f"SUCCESS: Position closed at ₹{executed_exit_price} | Net P&L: ₹{trade_res.net_pnl}"
                self.auto_exit_last_run_time = now
            return trade_res

        if self.on_position_callback:
            self.on_position_callback(pos)

        return None

    async def check_and_run_auto_close(
        self,
        now: Optional[datetime] = None,
        latest_option_price: Optional[float] = None,
        is_feed_stale: bool = False,
        is_feed_connected: bool = True,
        strategy_id: Optional[str] = None,
        force_now: bool = False
    ) -> Optional[PaperTradeResult]:
        """
        Evaluate and execute Auto Close for open paper positions at configured time (default 03:20 PM IST).
        Enforces:
        - Must be enabled (unless force_now is True).
        - Must reach configured IST time (unless force_now is True).
        - Closes regardless of profit or loss (according to close_profitable and close_losing settings).
        - Uses latest valid executable option price.
        - NEVER invents prices if market data is stale or disconnected: flags awaiting valid data with execution warning.
        - Saves exit reason as AUTO_CLOSE_3_20_PM.
        - Prevents duplicate exit orders.
        - Blocks new entries for remainder of session.
        """
        curr_dt = now or datetime.now(timezone.utc)
        ist_now = curr_dt.astimezone(IST)
        ist_time = ist_now.strftime("%H:%M")
        today_str = ist_now.strftime("%Y-%m-%d")

        if not self.auto_exit_enabled and not force_now:
            return None

        # Check time condition
        if ist_time < self.auto_close_time_ist and not force_now:
            return None

        # Cutoff reached: activate session cutoff to prevent new entries
        self.session_cutoff_active = True

        # Check open positions
        if self.active_position is None:
            if self.auto_exit_last_run_date != today_str:
                self.auto_exit_last_run_date = today_str
                self.auto_exit_last_status = f"STANDBY: No open positions to close at {ist_time} IST."
                self.auto_exit_awaiting_valid_data = False
                self.auto_exit_warning = None
            return None

        pos = self.active_position

        # Strategy check
        if not self.auto_exit_apply_all and strategy_id and pos.get("strategy_id") != strategy_id and not force_now:
            return None

        # Profit / Loss check
        gross_pnl = pos.get("gross_pnl", 0.0)
        net_pnl = pos.get("net_pnl", 0.0)
        is_profit = gross_pnl > 0 or net_pnl >= 0
        is_loss = gross_pnl < 0 or net_pnl < 0

        if not force_now:
            if is_profit and not self.auto_exit_close_profitable:
                self.auto_exit_last_status = "SKIPPED: Profitable position held per configuration."
                return None
            if is_loss and not self.auto_exit_close_losing:
                self.auto_exit_last_status = "SKIPPED: Losing position held per configuration."
                return None

        # Validate market data freshness and connectivity
        # "If market data is stale or disconnected, do not invent an exit price. Mark the position as awaiting valid exit data and display an execution warning."
        eff_price = latest_option_price
        if eff_price is None or eff_price <= 0:
            eff_price = pos.get("current_price")

        if (not is_feed_connected or is_feed_stale or eff_price is None or eff_price <= 0) and not force_now:
            self.auto_exit_awaiting_valid_data = True
            self.auto_exit_warning = (
                f"Market data disconnected or stale at auto close cutoff ({self.auto_close_time_ist} IST). "
                f"Position #{pos['id']} ({pos['symbol']}) held awaiting valid executable quote — not inventing exit price."
            )
            self.auto_exit_last_status = "WARNING: Awaiting valid market data to execute auto close."
            logger.warning(self.auto_exit_warning)
            return None

        # Valid price exists! Execute auto close
        executed_exit_price = round(eff_price - self.slippage_points, 2)
        trade_res = await self._close_position(
            exit_price=executed_exit_price,
            exit_reason="AUTO_CLOSE_3_20_PM",
            exit_time=curr_dt
        )

        self.auto_exit_awaiting_valid_data = False
        self.auto_exit_warning = None
        self.auto_exit_last_status = (
            f"SUCCESS: Auto-closed {pos['symbol']} at ₹{executed_exit_price} | Net P&L: ₹{trade_res.net_pnl}"
        )
        self.auto_exit_last_run_time = curr_dt
        self.auto_exit_last_run_date = today_str

        # Update AutoExitSetting record in DB
        try:
            from backend.app.models import AutoExitSetting
            async with AsyncSessionLocal() as session:
                stmt = select(AutoExitSetting).order_by(AutoExitSetting.id.desc())
                res = await session.execute(stmt)
                setting = res.scalars().first()
                if setting:
                    setting.last_status = self.auto_exit_last_status
                    setting.last_run_time = self.auto_exit_last_run_time
                    setting.last_run_date = self.auto_exit_last_run_date
                    await session.commit()
        except Exception as e:
            logger.warning(f"Could not persist auto-exit run status to DB: {e}")

        logger.info(f"Auto-Close Executed: {self.auto_exit_last_status}")
        return trade_res

    async def manual_close(self, exit_price: float, reason: str = "MANUAL") -> Optional[PaperTradeResult]:
        """Square off active paper position (from UI or opposite strategy signal)."""
        if not self.active_position:
            return None
        now = datetime.now(timezone.utc)
        executed_price = round(exit_price - self.slippage_points, 2)
        return await self._close_position(executed_price, reason, now)

    async def _close_position(
        self,
        exit_price: float,
        exit_reason: str,
        exit_time: datetime,
        exit_slippage: float = 0.0
    ) -> Optional[PaperTradeResult]:
        """Square off active paper position and commit trade and order records."""
        async with self._execution_lock:
            pos = self.active_position
            if not pos:
                logger.warning("_close_position called but active_position is None.")
                return None

            strat_id = pos.get("strategy_id", "EMA_RSI")
            ledger = self.get_strategy_ledger(strat_id)

            qty = pos["quantity"]
            gross_pnl = round((exit_price - pos["entry_price"]) * qty, 2)
            entry_chg = pos.get("entry_charge", self.charges_calc.entry_charge_per_order)
            exit_chg = pos.get("exit_charge", self.charges_calc.exit_charge_per_order)
            chg = self.charges_calc.calculate_charges(
                entry_order_count=1,
                exit_order_count=1,
                entry_charge_override=entry_chg,
                exit_charge_override=exit_chg
            )
            net_pnl = round(gross_pnl - chg.total_charges, 2)
            is_win = bool(net_pnl > 0)
            entry_slip = pos.get("entry_slippage", 0.0)
            slippage_cost = round((entry_slip + exit_slippage) * qty, 2)
            ent_time = pos["entry_time"]
            calc_exit = exit_time
            if hasattr(ent_time, "tzinfo") and ent_time.tzinfo is not None and getattr(calc_exit, "tzinfo", None) is None:
                calc_exit = calc_exit.replace(tzinfo=timezone.utc)
            elif hasattr(ent_time, "tzinfo") and ent_time.tzinfo is None and getattr(calc_exit, "tzinfo", None) is not None:
                calc_exit = calc_exit.replace(tzinfo=None)
            hold_time_mins = max(1, int((calc_exit - ent_time).total_seconds() // 60))

            # Double-entry release and P&L update on strategy isolated virtual ledger
            required_margin = round(pos["entry_price"] * qty, 2)
            ledger.reserved_capital = max(0.0, round(ledger.reserved_capital - required_margin, 2))
            ledger.available_cash = round(ledger.available_cash + required_margin + net_pnl, 2)
            ledger.realized_gross_pnl = round(ledger.realized_gross_pnl + gross_pnl, 2)
            ledger.realized_net_pnl = round(ledger.realized_net_pnl + net_pnl, 2)
            ledger.total_charges = round(ledger.total_charges + chg.total_charges, 2)
            ledger.slippage_cost = round(ledger.slippage_cost + slippage_cost, 2)
            ledger.active_position = None

            # Update backward-compatibility cash_balance
            self.cash_balance = ledger.available_cash

            trade_result = PaperTradeResult(
                position_id=pos["id"],
                symbol=pos["symbol"],
                entry_price=pos["entry_price"],
                exit_price=exit_price,
                quantity=qty,
                exit_reason=exit_reason,
                gross_pnl=gross_pnl,
                total_charges=chg.total_charges,
                net_pnl=net_pnl,
                is_win=is_win,
                entry_time=pos["entry_time"],
                exit_time=exit_time
            )

            # Database transaction: update position, insert exit order, insert trade record, update virtual account
            async with AsyncSessionLocal() as session:
                # 1. Update PaperPosition
                stmt = update(PaperPosition).where(PaperPosition.id == pos["id"]).values(
                    current_price=exit_price,
                    status="CLOSED",
                    exit_time=exit_time,
                    exit_reason=exit_reason,
                    gross_pnl=gross_pnl,
                    charges=chg.total_charges,
                    slippage_cost=slippage_cost,
                    net_pnl=net_pnl,
                    updated_at=exit_time
                )
                await session.execute(stmt)

                # 2. Insert exit sell order
                order_db = PaperOrder(
                    position_id=pos["id"],
                    order_type="MARKET",
                    transaction_type="SELL",
                    instrument_token=pos["instrument_token"],
                    symbol=pos["symbol"],
                    strike=pos["strike"],
                    expiry=pos["expiry"],
                    quantity=qty,
                    requested_price=exit_price,
                    executed_price=exit_price,
                    slippage=exit_slippage,
                    status="FILLED",
                    created_at=exit_time,
                    filled_at=exit_time
                )
                session.add(order_db)

                # 3. Insert PaperTrade record
                trade_db = PaperTrade(
                    position_id=pos["id"],
                    strategy_id=pos.get("strategy_id", "EMA_RSI"),
                    strategy_config=pos.get("strategy_config"),
                    signal_id=pos.get("signal_id"),
                    underlying_symbol="NIFTY",
                    underlying_price_at_entry=pos.get("underlying_price_at_entry", 24500.0),
                    option_symbol=pos["symbol"],
                    strike=pos["strike"],
                    expiry=pos["expiry"],
                    entry_time=pos["entry_time"],
                    exit_time=exit_time,
                    entry_price=pos["entry_price"],
                    exit_price=exit_price,
                    quantity=qty,
                    target_price=pos["target_price"],
                    stop_price=pos["stop_price"],
                    configured_sl_points=pos.get("configured_sl_points", 2.0),
                    configured_target_points=pos.get("configured_target_points", 4.0),
                    effective_sl_points=pos.get("effective_sl_points", 2.0),
                    effective_target_points=pos.get("effective_target_points", 4.0),
                    sl_trigger_price=pos.get("sl_trigger_price", pos["stop_price"]),
                    target_trigger_price=pos.get("target_trigger_price", pos["target_price"]),
                    slippage_cost=slippage_cost,
                    execution_mode=pos.get("execution_mode", self.execution_mode),
                    is_ambiguous=pos.get("is_ambiguous", False),
                    ambiguity_flag=pos.get("ambiguity_flag"),
                    holding_time_minutes=hold_time_mins,
                    exit_reason=exit_reason,
                    gross_pnl=gross_pnl,
                    entry_charge=chg.entry_charge,
                    exit_charge=chg.exit_charge,
                    charges_brokerage=chg.total_charges,
                    charges_stt=0.0,
                    charges_exchange=0.0,
                    charges_gst=0.0,
                    charges_sebi=0.0,
                    charges_stamp=0.0,
                    total_charges=chg.total_charges,
                    net_pnl=net_pnl,
                    is_win=is_win,
                    created_at=exit_time
                )
                session.add(trade_db)
                await session.flush()

                trade_evt = PaperTradeEvent(
                    trade_id=trade_db.id,
                    position_id=pos["id"],
                    strategy_id=strat_id,
                    event_type=exit_reason,
                    event_price=exit_price,
                    event_quantity=qty,
                    trigger_reason=exit_reason,
                    notes=f"Net P&L: ₹{net_pnl:.2f}",
                    created_at=exit_time
                )
                session.add(trade_evt)

                chg_record = PaperCharge(
                    trade_id=trade_db.id,
                    order_id=order_db.id,
                    strategy_id=strat_id,
                    brokerage=chg.total_charges,
                    stt=0.0,
                    exchange_turnover=0.0,
                    gst=0.0,
                    sebi_charges=0.0,
                    stamp_duty=0.0,
                    total_charges=chg.total_charges,
                    calculated_at=exit_time
                )
                session.add(chg_record)

                exec_log = PaperExecutionLog(
                    strategy_id=strat_id,
                    order_id=order_db.id,
                    position_id=pos["id"],
                    action="POSITION_CLOSED",
                    level="INFO",
                    message=f"Position closed @ ₹{exit_price} ({exit_reason}). Net P&L: ₹{net_pnl:.2f}"
                )
                session.add(exec_log)

                bal_record = PaperAccountBalance(
                    strategy_id=strat_id,
                    balance=round(ledger.available_cash + ledger.reserved_capital, 2),
                    available_balance=ledger.available_cash,
                    reserved_margin=ledger.reserved_capital,
                    realized_pnl=ledger.realized_net_pnl,
                    unrealized_pnl=0.0,
                    change_amount=net_pnl,
                    change_reason="TRADE_EXIT_SETTLEMENT",
                    related_trade_id=trade_db.id,
                    created_at=exit_time
                )
                session.add(bal_record)

                # 4. Update StrategyVirtualAccount & PaperAccount
                stmt_acc = update(StrategyVirtualAccount).where(
                    StrategyVirtualAccount.strategy_id == strat_id
                ).values(
                    available_cash=ledger.available_cash,
                    reserved_capital=ledger.reserved_capital,
                    realized_gross_pnl=ledger.realized_gross_pnl,
                    realized_net_pnl=ledger.realized_net_pnl,
                    total_charges=ledger.total_charges,
                    slippage_cost=ledger.slippage_cost,
                    updated_at=exit_time
                )
                await session.execute(stmt_acc)

                stmt_pa = update(PaperAccount).where(
                    PaperAccount.strategy_id == strat_id
                ).values(
                    available_balance=ledger.available_cash,
                    reserved_capital=ledger.reserved_capital,
                    realized_pnl=ledger.realized_net_pnl,
                    total_charges=ledger.total_charges,
                    total_slippage=ledger.slippage_cost,
                    updated_at=exit_time
                )
                await session.execute(stmt_pa)
                await session.commit()

            logger.info(
                f"Paper Position CLOSED: {pos['symbol']} | Reason: {exit_reason} | "
                f"Exit: ₹{exit_price} | Gross: ₹{gross_pnl} | Charges: ₹{chg.total_charges} | Net: ₹{net_pnl}"
            )

            trade_dict = {
                "id": pos["id"],
                "symbol": pos["symbol"],
                "strike": pos["strike"],
                "expiry": pos["expiry"],
                "quantity": qty,
                "entry_price": pos["entry_price"],
                "exit_price": exit_price,
                "target_price": pos["target_price"],
                "stop_price": pos["stop_price"],
                "exit_reason": exit_reason,
                "gross_pnl": gross_pnl,
                "charges": chg.total_charges,
                "net_pnl": net_pnl,
                "is_win": is_win,
                "entry_time": pos["entry_time"].isoformat(),
                "exit_time": exit_time.isoformat()
            }
            self.closed_trades.append(trade_dict)
            self.active_position = None

            # Re-evaluate and persist daily risk status
            await self.get_daily_risk_status(strategy_id=strat_id, now=exit_time)

            if self.on_trade_callback:
                self.on_trade_callback(trade_dict)

            return trade_result

        if self.on_trade_callback:
            self.on_trade_callback(trade_dict)

        return trade_result
