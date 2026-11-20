import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Text, Index, UniqueConstraint, BigInteger
)
from sqlalchemy.orm import relationship
from backend.app.database import Base


def generate_uuid():
    return str(uuid.uuid4())


def utc_now():
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False)
    email = Column(String(100), unique=True, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)


class BrokerConnection(Base):
    __tablename__ = "broker_connections"

    id = Column(Integer, primary_key=True, index=True)
    broker_name = Column(String(50), default="kotak_neo", nullable=False)
    environment = Column(String(20), default="prod", nullable=False)
    ucc = Column(String(50), nullable=True)
    auth_status = Column(String(30), default="DEMO_MODE", nullable=False)  # CONNECTED, DISCONNECTED, DEMO_MODE, ERROR
    token_expires_at = Column(DateTime(timezone=True), nullable=True)
    last_heartbeat = Column(DateTime(timezone=True), nullable=True)
    error_message = Column(Text, nullable=True)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)


class Instrument(Base):
    __tablename__ = "instruments"

    id = Column(Integer, primary_key=True, index=True)
    exchange_segment = Column(String(20), nullable=False, index=True)  # nse_cm, nse_fo
    instrument_token = Column(String(50), nullable=False, index=True)
    trading_symbol = Column(String(100), nullable=False, index=True)
    instrument_name = Column(String(100), nullable=True)
    underlying_symbol = Column(String(50), nullable=True, index=True)  # NIFTY
    strike_price = Column(Float, nullable=True, index=True)
    option_type = Column(String(10), nullable=True, index=True)  # CE, PE, XX
    expiry_date = Column(String(30), nullable=True, index=True)  # YYYY-MM-DD or DDMMMYYYY
    lot_size = Column(Integer, default=65, nullable=False)  # Nifty current lot size is 65 (or 25/50/75 historically)
    tick_size = Column(Float, default=0.05, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    __table_args__ = (
        Index("ix_instrument_lookup", "underlying_symbol", "expiry_date", "strike_price", "option_type"),
        UniqueConstraint("exchange_segment", "instrument_token", name="uq_exchange_token"),
    )


class MarketTick(Base):
    __tablename__ = "market_ticks"

    id = Column(Integer, primary_key=True, index=True)
    instrument_token = Column(String(50), nullable=False, index=True)
    exchange_segment = Column(String(20), nullable=False)
    symbol = Column(String(100), nullable=False)
    last_price = Column(Float, nullable=False)
    volume = Column(Integer, default=0)
    open_interest = Column(Integer, default=0)
    bid = Column(Float, nullable=True)
    ask = Column(Float, nullable=True)
    timestamp = Column(DateTime(timezone=True), default=utc_now, index=True, nullable=False)


class HistoricalCandle(Base):
    __tablename__ = "historical_candles"

    id = Column(Integer, primary_key=True, index=True)
    instrument_token = Column(String(50), nullable=False, index=True)
    symbol = Column(String(100), nullable=False, index=True)
    timeframe = Column(String(10), default="1m", nullable=False)
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    open = Column(Float, nullable=False)
    high = Column(Float, nullable=False)
    low = Column(Float, nullable=False)
    close = Column(Float, nullable=False)
    volume = Column(Float, default=0.0)

    __table_args__ = (
        Index("ix_candle_symbol_tf_time", "symbol", "timeframe", "timestamp"),
    )


class StrategySetting(Base):
    __tablename__ = "strategy_settings"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), default="NIFTY 1M EMA+RSI ATM CE", nullable=False)
    underlying = Column(String(50), default="NIFTY", nullable=False)
    timeframe = Column(String(10), default="1m", nullable=False)
    ema_fast = Column(Integer, default=9, nullable=False)
    ema_medium = Column(Integer, default=21, nullable=False)
    ema_slow = Column(Integer, default=50, nullable=False)
    rsi_period = Column(Integer, default=14, nullable=False)
    rsi_threshold = Column(Float, default=50.0, nullable=False)
    session_start_ist = Column(String(10), default="09:20", nullable=False)
    session_end_ist = Column(String(10), default="15:15", nullable=False)
    force_exit_ist = Column(String(10), default="15:20", nullable=False)
    target_points = Column(Float, default=4.0, nullable=False)
    stop_points = Column(Float, default=4.0, nullable=False)
    max_loss_per_trade = Column(Float, default=1000.0, nullable=False)
    default_lots = Column(Integer, default=1, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)


class StrategySignal(Base):
    __tablename__ = "strategy_signals"

    id = Column(Integer, primary_key=True, index=True)
    strategy_id = Column(String(50), default="EMA_RSI", nullable=False, index=True)  # EMA_RSI, UT_BOT
    strategy_config = Column(Text, nullable=True)  # JSON snapshot of strategy parameters
    timestamp = Column(DateTime(timezone=True), default=utc_now, index=True, nullable=False)
    candle_time = Column(DateTime(timezone=True), nullable=False)
    underlying_symbol = Column(String(50), default="NIFTY", nullable=False)
    underlying_price = Column(Float, nullable=False)
    ema_9 = Column(Float, nullable=True)
    ema_21 = Column(Float, nullable=True)
    ema_50 = Column(Float, nullable=True)
    rsi_14 = Column(Float, nullable=True)
    atr = Column(Float, nullable=True)
    trailing_stop = Column(Float, nullable=True)
    condition_1 = Column(Boolean, nullable=True)  # EMA 9 > EMA 21 or UT above
    condition_2 = Column(Boolean, nullable=True)  # Close > EMA 50 or UT src > stop
    condition_3 = Column(Boolean, nullable=True)  # RSI 14 > 50 or UT session
    condition_4 = Column(Boolean, nullable=True)  # 09:20 - 15:15 IST
    signal_type = Column(String(30), default="NONE", nullable=False)  # BUY_ATM_CE, BUY, SELL, NONE
    executed = Column(Boolean, default=False, nullable=False)
    notes = Column(Text, nullable=True)


class PaperOrder(Base):
    __tablename__ = "paper_orders"

    id = Column(Integer, primary_key=True, index=True)
    position_id = Column(Integer, nullable=True, index=True)
    order_type = Column(String(20), default="MARKET", nullable=False)
    transaction_type = Column(String(10), nullable=False)  # BUY, SELL
    instrument_token = Column(String(50), nullable=False)
    symbol = Column(String(100), nullable=False)
    strike = Column(Float, nullable=True)
    expiry = Column(String(30), nullable=True)
    quantity = Column(Integer, nullable=False)
    requested_price = Column(Float, nullable=False)
    executed_price = Column(Float, nullable=False)
    slippage = Column(Float, default=0.0, nullable=False)
    status = Column(String(20), default="FILLED", nullable=False)  # FILLED, REJECTED, CANCELLED
    rejection_reason = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    filled_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)


class PaperPosition(Base):
    __tablename__ = "paper_positions"

    id = Column(Integer, primary_key=True, index=True)
    strategy_id = Column(String(50), default="EMA_RSI", nullable=False, index=True)  # EMA_RSI, UT_BOT
    strategy_config = Column(Text, nullable=True)  # JSON snapshot
    instrument_token = Column(String(50), nullable=False)
    symbol = Column(String(100), nullable=False)
    strike = Column(Float, nullable=False)
    expiry = Column(String(30), nullable=False)
    lot_size = Column(Integer, nullable=False)
    lots = Column(Integer, default=1, nullable=False)
    quantity = Column(Integer, nullable=False)
    entry_price = Column(Float, nullable=False)
    current_price = Column(Float, nullable=False)
    target_price = Column(Float, nullable=False)
    stop_price = Column(Float, nullable=False)
    effective_stop_distance = Column(Float, nullable=False)
    max_loss_amount = Column(Float, default=1000.0, nullable=False)
    configured_sl_points = Column(Float, default=2.0, nullable=True)
    configured_target_points = Column(Float, default=4.0, nullable=True)
    effective_sl_points = Column(Float, default=2.0, nullable=True)
    effective_target_points = Column(Float, default=4.0, nullable=True)
    sl_trigger_price = Column(Float, nullable=True)
    target_trigger_price = Column(Float, nullable=True)
    slippage_cost = Column(Float, default=0.0, nullable=True)
    execution_mode = Column(String(30), default="REALISTIC", nullable=True)
    highest_price = Column(Float, nullable=False)
    lowest_price = Column(Float, nullable=False)
    status = Column(String(20), default="OPEN", index=True, nullable=False)  # OPEN, CLOSED
    entry_time = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    exit_time = Column(DateTime(timezone=True), nullable=True)
    exit_reason = Column(String(50), nullable=True)  # TARGET, STOP_LOSS, FORCE_EXIT_1520, MANUAL, GAP_STOP
    gross_pnl = Column(Float, default=0.0, nullable=False)
    entry_charge = Column(Float, default=10.0, nullable=False)
    exit_charge = Column(Float, default=10.0, nullable=False)
    charges = Column(Float, default=20.0, nullable=False)
    net_pnl = Column(Float, default=0.0, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)


class PaperTrade(Base):
    __tablename__ = "paper_trades"

    id = Column(Integer, primary_key=True, index=True)
    strategy_id = Column(String(50), default="EMA_RSI", nullable=False, index=True)  # EMA_RSI, UT_BOT
    strategy_config = Column(Text, nullable=True)  # JSON snapshot
    position_id = Column(Integer, ForeignKey("paper_positions.id"), nullable=False)
    signal_id = Column(Integer, nullable=True)
    underlying_symbol = Column(String(50), default="NIFTY", nullable=False)
    underlying_price_at_entry = Column(Float, nullable=False)
    option_symbol = Column(String(100), nullable=False)
    strike = Column(Float, nullable=False)
    expiry = Column(String(30), nullable=False)
    entry_time = Column(DateTime(timezone=True), nullable=False)
    exit_time = Column(DateTime(timezone=True), nullable=False)
    entry_price = Column(Float, nullable=False)
    exit_price = Column(Float, nullable=False)
    quantity = Column(Integer, nullable=False)
    target_price = Column(Float, nullable=False)
    stop_price = Column(Float, nullable=False)
    configured_sl_points = Column(Float, default=2.0, nullable=True)
    configured_target_points = Column(Float, default=4.0, nullable=True)
    effective_sl_points = Column(Float, default=2.0, nullable=True)
    effective_target_points = Column(Float, default=4.0, nullable=True)
    sl_trigger_price = Column(Float, nullable=True)
    target_trigger_price = Column(Float, nullable=True)
    slippage_cost = Column(Float, default=0.0, nullable=True)
    execution_mode = Column(String(30), default="REALISTIC", nullable=True)
    is_ambiguous = Column(Boolean, default=False, nullable=True)
    ambiguity_flag = Column(String(50), nullable=True)
    holding_time_minutes = Column(Integer, default=1, nullable=True)
    exit_reason = Column(String(50), nullable=False)
    gross_pnl = Column(Float, nullable=False)
    entry_charge = Column(Float, default=10.0, nullable=False)
    exit_charge = Column(Float, default=10.0, nullable=False)
    charges_brokerage = Column(Float, default=20.0, nullable=False)
    charges_stt = Column(Float, default=0.0, nullable=False)
    charges_exchange = Column(Float, default=0.0, nullable=False)
    charges_gst = Column(Float, default=0.0, nullable=False)
    charges_sebi = Column(Float, default=0.0, nullable=False)
    charges_stamp = Column(Float, default=0.0, nullable=False)
    total_charges = Column(Float, default=20.0, nullable=False)
    net_pnl = Column(Float, nullable=False)
    is_win = Column(Boolean, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)


class ChargeSetting(Base):
    __tablename__ = "charge_settings"

    id = Column(Integer, primary_key=True, index=True)
    entry_charge_per_order = Column(Float, default=10.0, nullable=False)
    exit_charge_per_order = Column(Float, default=10.0, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)


class AutoExitSetting(Base):
    __tablename__ = "auto_exit_settings"

    id = Column(Integer, primary_key=True, index=True)
    enabled = Column(Boolean, default=True, nullable=False)
    auto_close_time = Column(String(10), default="15:20", nullable=False)
    apply_to_all_strategies = Column(Boolean, default=True, nullable=False)
    close_profitable = Column(Boolean, default=True, nullable=False)
    close_losing = Column(Boolean, default=True, nullable=False)
    last_status = Column(String(200), default="STANDBY: Scheduled for 03:20 PM IST", nullable=False)
    last_run_time = Column(DateTime(timezone=True), nullable=True)
    last_run_date = Column(String(20), nullable=True)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)


class BacktestRun(Base):
    __tablename__ = "backtest_runs"

    id = Column(Integer, primary_key=True, index=True)
    strategy_id = Column(String(50), default="EMA_RSI", nullable=False, index=True)  # EMA_RSI, UT_BOT
    strategy_name = Column(String(100), nullable=False)
    strategy_config = Column(Text, nullable=True)  # JSON snapshot
    timeframe = Column(String(10), default="1m", nullable=False)
    instrument_symbol = Column(String(100), default="NIFTY ATM CE", nullable=False)
    start_date = Column(String(30), nullable=False)
    end_date = Column(String(30), nullable=False)
    initial_capital = Column(Float, default=100000.0, nullable=False)
    final_capital = Column(Float, nullable=False)
    total_trades = Column(Integer, default=0, nullable=False)
    winning_trades = Column(Integer, default=0, nullable=False)
    losing_trades = Column(Integer, default=0, nullable=False)
    win_rate = Column(Float, default=0.0, nullable=False)
    gross_profit = Column(Float, default=0.0, nullable=False)
    gross_loss = Column(Float, default=0.0, nullable=False)
    net_profit = Column(Float, default=0.0, nullable=False)
    max_drawdown = Column(Float, default=0.0, nullable=False)
    profit_factor = Column(Float, default=0.0, nullable=False)
    avg_profit = Column(Float, default=0.0, nullable=False)
    avg_loss = Column(Float, default=0.0, nullable=False)
    largest_win = Column(Float, default=0.0, nullable=False)
    largest_loss = Column(Float, default=0.0, nullable=False)
    total_charges = Column(Float, default=0.0, nullable=False)
    data_source = Column(String(50), default="HISTORICAL_DATA", nullable=False)  # HISTORICAL_DATA, SYNTHETIC_TEST
    execution_mode = Column(String(30), default="TRIGGER_PRICE", nullable=True)  # TRIGGER_PRICE, REALISTIC
    exit_on_ut_sell_signal = Column(Boolean, default=False, nullable=True)
    configured_sl_points = Column(Float, default=2.0, nullable=True)
    configured_target_points = Column(Float, default=4.0, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    trades = relationship("BacktestTrade", back_populates="run", cascade="all, delete-orphan")


class BacktestTrade(Base):
    __tablename__ = "backtest_trades"

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(Integer, ForeignKey("backtest_runs.id"), nullable=False)
    signal_time = Column(DateTime(timezone=True), nullable=False)
    entry_time = Column(DateTime(timezone=True), nullable=False)
    exit_time = Column(DateTime(timezone=True), nullable=False)
    underlying_price = Column(Float, nullable=False)
    option_symbol = Column(String(100), nullable=False)
    strike = Column(Float, nullable=False)
    expiry = Column(String(30), nullable=False)
    entry_price = Column(Float, nullable=False)
    exit_price = Column(Float, nullable=False)
    quantity = Column(Integer, nullable=False)
    target = Column(Float, nullable=False)
    stop = Column(Float, nullable=False)
    configured_sl_points = Column(Float, default=2.0, nullable=True)
    configured_target_points = Column(Float, default=4.0, nullable=True)
    effective_sl_points = Column(Float, default=2.0, nullable=True)
    effective_target_points = Column(Float, default=4.0, nullable=True)
    sl_trigger_price = Column(Float, nullable=True)
    target_trigger_price = Column(Float, nullable=True)
    slippage_cost = Column(Float, default=0.0, nullable=True)
    execution_mode = Column(String(30), default="TRIGGER_PRICE", nullable=True)
    is_ambiguous = Column(Boolean, default=False, nullable=True)
    ambiguity_flag = Column(String(50), nullable=True)
    holding_time_minutes = Column(Integer, default=1, nullable=True)
    exit_reason = Column(String(50), nullable=False)
    gross_pnl = Column(Float, nullable=False)
    entry_charge = Column(Float, default=10.0, nullable=False)
    exit_charge = Column(Float, default=10.0, nullable=False)
    charges = Column(Float, nullable=False)
    net_pnl = Column(Float, nullable=False)
    is_win = Column(Boolean, nullable=False)

    run = relationship("BacktestRun", back_populates="trades")


class SystemEvent(Base):
    __tablename__ = "system_events"

    id = Column(Integer, primary_key=True, index=True)
    event_type = Column(String(50), nullable=False, index=True)  # INFO, WARNING, ERROR, FEED_DISCONNECT, RECONNECT, STALE_DATA, RESTART_RECOVERY
    title = Column(String(200), nullable=False)
    message = Column(Text, nullable=False)
    details_json = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, index=True, nullable=False)


class StrategyDailyRisk(Base):
    __tablename__ = "strategy_daily_risks"

    id = Column(Integer, primary_key=True, index=True)
    strategy_id = Column(String(50), nullable=False, index=True)
    trading_date = Column(String(20), nullable=False, index=True)  # YYYY-MM-DD IST
    realized_net_pnl = Column(Float, default=0.0, nullable=False)
    gross_pnl = Column(Float, default=0.0, nullable=False)
    total_charges = Column(Float, default=0.0, nullable=False)
    trade_count = Column(Integer, default=0, nullable=False)
    accepted_entries_count = Column(Integer, default=0, nullable=False)
    winning_trades = Column(Integer, default=0, nullable=False)
    losing_trades = Column(Integer, default=0, nullable=False)
    consecutive_losses = Column(Integer, default=0, nullable=False)
    is_locked = Column(Boolean, default=False, nullable=False)
    lock_reason = Column(String(100), default="NONE", nullable=False)  # NONE, DAILY_PROFIT_LOCKED, DAILY_LOSS_LOCKED
    locked_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)


class PCRSnapshot(Base):
    __tablename__ = "pcr_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    underlying = Column(String(30), nullable=False, index=True)  # NIFTY, BANKNIFTY, FINNIFTY
    expiry = Column(String(30), nullable=False, index=True)      # YYYY-MM-DD
    strike_range = Column(Integer, nullable=False, default=10)   # 5, 10, 15, 20, 25, 0 (all)
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    timestamp_ist = Column(String(30), nullable=False)           # YYYY-MM-DD HH:MM
    trading_date = Column(String(20), nullable=False, index=True)# YYYY-MM-DD
    atm_strike = Column(Float, nullable=False)
    spot_price = Column(Float, nullable=False)
    total_call_oi = Column(BigInteger, default=0, nullable=False)
    total_put_oi = Column(BigInteger, default=0, nullable=False)
    oi_pcr = Column(Float, nullable=True)
    total_call_volume = Column(BigInteger, default=0, nullable=False)
    total_put_volume = Column(BigInteger, default=0, nullable=False)
    volume_pcr = Column(Float, nullable=True)
    call_oi_change = Column(BigInteger, default=0, nullable=False)
    put_oi_change = Column(BigInteger, default=0, nullable=False)
    underlying_vwap = Column(Float, nullable=True)
    futures_vwap = Column(Float, nullable=True)
    futures_symbol = Column(String(50), nullable=True)
    sentiment = Column(String(50), default="NEUTRAL", nullable=False)
    sentiment_score = Column(Float, default=0.0, nullable=False)
    data_status = Column(String(30), default="FRESH", nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    __table_args__ = (
        Index("idx_pcr_underlying_date", "underlying", "trading_date", "timestamp"),
        UniqueConstraint("underlying", "expiry", "strike_range", "timestamp_ist", name="uq_pcr_snapshot_minute"),
    )


class StrategyVirtualAccount(Base):
    __tablename__ = "strategy_virtual_accounts"

    id = Column(Integer, primary_key=True, index=True)
    strategy_id = Column(String(50), unique=True, nullable=False, index=True)
    strategy_name = Column(String(100), nullable=False)
    initial_capital = Column(Float, default=100000.0, nullable=False)
    available_cash = Column(Float, default=100000.0, nullable=False)
    reserved_capital = Column(Float, default=0.0, nullable=False)
    realized_gross_pnl = Column(Float, default=0.0, nullable=False)
    realized_net_pnl = Column(Float, default=0.0, nullable=False)
    total_charges = Column(Float, default=0.0, nullable=False)
    slippage_cost = Column(Float, default=0.0, nullable=False)
    capital_deployment_cap_pct = Column(Float, default=90.0, nullable=False)
    daily_profit_target = Column(Float, nullable=True)
    daily_loss_limit = Column(Float, nullable=True)
    max_trades_per_day = Column(Integer, nullable=True)
    max_consecutive_losses = Column(Integer, nullable=True)
    risk_limits_enabled = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)


class PaperAccount(Base):
    __tablename__ = "paper_accounts"

    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)
    user_id = Column(Integer, nullable=True)
    strategy_id = Column(String(50), unique=True, nullable=False, index=True)
    account_name = Column(String(100), nullable=False)
    account_number = Column(String(50), unique=True, nullable=False)
    initial_capital = Column(Float, default=100000.0, nullable=False)
    available_balance = Column(Float, default=100000.0, nullable=False)
    reserved_capital = Column(Float, default=0.0, nullable=False)
    realized_pnl = Column(Float, default=0.0, nullable=False)
    unrealized_pnl = Column(Float, default=0.0, nullable=False)
    total_charges = Column(Float, default=0.0, nullable=False)
    total_slippage = Column(Float, default=0.0, nullable=False)
    capital_deployment_cap_pct = Column(Float, default=90.0, nullable=False)
    currency = Column(String(10), default="INR", nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)


class PaperAccountBalance(Base):
    __tablename__ = "paper_account_balances"

    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(String(36), ForeignKey("paper_accounts.id", ondelete="CASCADE"), nullable=True)
    strategy_id = Column(String(50), nullable=False, index=True)
    balance = Column(Float, nullable=False)
    available_balance = Column(Float, nullable=False)
    reserved_margin = Column(Float, default=0.0, nullable=False)
    realized_pnl = Column(Float, default=0.0, nullable=False)
    unrealized_pnl = Column(Float, default=0.0, nullable=False)
    change_amount = Column(Float, default=0.0, nullable=False)
    change_reason = Column(String(100), nullable=False)
    related_trade_id = Column(Integer, nullable=True)
    related_order_id = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, index=True, nullable=False)


class PaperTradeEvent(Base):
    __tablename__ = "paper_trade_events"

    id = Column(Integer, primary_key=True, index=True)
    trade_id = Column(Integer, ForeignKey("paper_trades.id", ondelete="CASCADE"), nullable=False, index=True)
    position_id = Column(Integer, nullable=True)
    strategy_id = Column(String(50), nullable=False, index=True)
    event_type = Column(String(50), nullable=False)
    event_price = Column(Float, nullable=False)
    event_quantity = Column(Integer, nullable=False)
    trigger_reason = Column(String(100), nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, index=True, nullable=False)


class PaperExecutionLog(Base):
    __tablename__ = "paper_execution_logs"

    id = Column(Integer, primary_key=True, index=True)
    strategy_id = Column(String(50), nullable=False, index=True)
    order_id = Column(Integer, ForeignKey("paper_orders.id", ondelete="SET NULL"), nullable=True, index=True)
    position_id = Column(Integer, nullable=True)
    action = Column(String(50), nullable=False)
    level = Column(String(20), default="INFO", nullable=False)
    message = Column(Text, nullable=False)
    details_json = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, index=True, nullable=False)


class PaperCharge(Base):
    __tablename__ = "paper_charges"

    id = Column(Integer, primary_key=True, index=True)
    trade_id = Column(Integer, ForeignKey("paper_trades.id", ondelete="CASCADE"), nullable=False, index=True)
    order_id = Column(Integer, ForeignKey("paper_orders.id", ondelete="SET NULL"), nullable=True)
    strategy_id = Column(String(50), nullable=False, index=True)
    brokerage = Column(Float, default=0.0, nullable=False)
    stt = Column(Float, default=0.0, nullable=False)
    exchange_turnover = Column(Float, default=0.0, nullable=False)
    gst = Column(Float, default=0.0, nullable=False)
    sebi_charges = Column(Float, default=0.0, nullable=False)
    stamp_duty = Column(Float, default=0.0, nullable=False)
    total_charges = Column(Float, nullable=False)
    calculated_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)


class PaperRiskEvent(Base):
    __tablename__ = "paper_risk_events"

    id = Column(Integer, primary_key=True, index=True)
    strategy_id = Column(String(50), nullable=False, index=True)
    trading_date = Column(String(20), nullable=False, index=True)
    risk_event_type = Column(String(50), nullable=False)
    trigger_metric_name = Column(String(50), nullable=False)
    metric_value = Column(Float, nullable=False)
    threshold_value = Column(Float, nullable=False)
    action_taken = Column(String(100), nullable=False)
    details = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, index=True, nullable=False)


class BacktestDailyResult(Base):
    __tablename__ = "backtest_daily_results"

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(Integer, ForeignKey("backtest_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    trading_date = Column(String(20), nullable=False, index=True)
    trades_count = Column(Integer, default=0, nullable=False)
    wins_count = Column(Integer, default=0, nullable=False)
    losses_count = Column(Integer, default=0, nullable=False)
    gross_pnl = Column(Float, default=0.0, nullable=False)
    charges = Column(Float, default=0.0, nullable=False)
    net_pnl = Column(Float, default=0.0, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    __table_args__ = (
        UniqueConstraint("run_id", "trading_date", name="uq_bt_run_date"),
    )


class BacktestMetric(Base):
    __tablename__ = "backtest_metrics"

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(Integer, ForeignKey("backtest_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    metric_key = Column(String(50), nullable=False)
    metric_value = Column(Float, nullable=False)
    category = Column(String(50), default="GENERAL", nullable=False)
    description = Column(String(255), nullable=True)

    __table_args__ = (
        UniqueConstraint("run_id", "metric_key", name="uq_bt_run_metric"),
    )


class BacktestDataCoverage(Base):
    __tablename__ = "backtest_data_coverage"

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(Integer, ForeignKey("backtest_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    instrument_token = Column(String(50), nullable=False)
    trading_symbol = Column(String(100), nullable=False)
    timeframe = Column(String(20), default="1m", nullable=False)
    start_time = Column(DateTime(timezone=True), nullable=False)
    end_time = Column(DateTime(timezone=True), nullable=False)
    total_candles = Column(Integer, nullable=False)
    missing_candles = Column(Integer, default=0, nullable=False)
    coverage_pct = Column(Float, default=100.0, nullable=False)


class BacktestExecutionLog(Base):
    __tablename__ = "backtest_execution_logs"

    id = Column(Integer, primary_key=True, index=True)
    run_id = Column(Integer, ForeignKey("backtest_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    timestamp = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    level = Column(String(20), default="INFO", nullable=False)
    message = Column(Text, nullable=False)
    stage = Column(String(50), default="EXECUTION", nullable=False)


class StrategySignalEvaluation(Base):
    __tablename__ = "strategy_signal_evaluations"

    id = Column(Integer, primary_key=True, index=True)
    signal_id = Column(Integer, ForeignKey("strategy_signals.id", ondelete="SET NULL"), nullable=True, index=True)
    strategy_id = Column(String(50), nullable=False, index=True)
    timestamp = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    rule_name = Column(String(100), nullable=False)
    passed = Column(Boolean, nullable=False)
    expected_condition = Column(Text, nullable=True)
    actual_value = Column(Text, nullable=True)


class AgentDecision(Base):
    __tablename__ = "agent_decisions"

    id = Column(Integer, primary_key=True, index=True)
    signal_id = Column(Integer, ForeignKey("strategy_signals.id", ondelete="SET NULL"), nullable=True, index=True)
    strategy_id = Column(String(50), nullable=False, index=True)
    agent_name = Column(String(100), nullable=False)
    vote = Column(String(20), nullable=False)
    confidence = Column(Float, default=1.0, nullable=False)
    reasoning = Column(Text, nullable=True)
    features_json = Column(Text, nullable=True)
    timestamp = Column(DateTime(timezone=True), default=utc_now, nullable=False)


class StrategyExecutionEvent(Base):
    __tablename__ = "strategy_execution_events"

    id = Column(Integer, primary_key=True, index=True)
    strategy_id = Column(String(50), nullable=False, index=True)
    event_type = Column(String(50), nullable=False)
    details_json = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, index=True, nullable=False)


class StrategyConfigVersion(Base):
    __tablename__ = "strategy_config_versions"

    id = Column(Integer, primary_key=True, index=True)
    strategy_id = Column(String(50), nullable=False, index=True)
    version = Column(Integer, nullable=False)
    config_json = Column(Text, nullable=False)
    change_summary = Column(String(255), nullable=True)
    changed_by = Column(String(100), default="system", nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    __table_args__ = (
        UniqueConstraint("strategy_id", "version", name="uq_strat_version"),
    )



