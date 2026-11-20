from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List, Dict, Any


class MarketStatusResponse(BaseModel):
    is_connected: bool
    is_demo: bool
    broker_name: str
    auth_status: str
    feed_status: str
    last_tick_time: Optional[datetime]
    nifty_price: float
    option_symbol: str
    option_premium: float
    atm_strike: float
    expiry: str
    lot_size: int


class CandleResponse(BaseModel):
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    complete: bool


class StrategySettingsSchema(BaseModel):
    id: Optional[int] = None
    name: str = "NIFTY 1M EMA+RSI ATM CE"
    underlying: str = "NIFTY"
    timeframe: str = "1m"
    ema_fast: int = 9
    ema_medium: int = 21
    ema_slow: int = 50
    rsi_period: int = 14
    rsi_threshold: float = 50.0
    session_start_ist: str = "09:20"
    session_end_ist: str = "15:15"
    force_exit_ist: str = "15:20"
    target_points: float = 4.0
    stop_points: float = 4.0
    max_loss_per_trade: float = 1000.0
    default_lots: int = 1
    is_active: bool = True


class SignalResponse(BaseModel):
    id: Optional[int] = None
    timestamp: datetime
    candle_time: datetime
    underlying_price: float
    ema_9: float
    ema_21: float
    ema_50: float
    rsi_14: float
    time_ist: str
    condition_1: bool
    condition_2: bool
    condition_3: bool
    condition_4: bool
    signal_type: str
    executed: bool


class PaperPositionResponse(BaseModel):
    id: int
    instrument_token: str
    symbol: str
    strike: float
    expiry: str
    lot_size: int
    lots: int
    quantity: int
    entry_price: float
    current_price: float
    target_price: float
    stop_price: float
    effective_stop_distance: float
    max_loss_amount: float
    highest_price: float
    lowest_price: float
    status: str
    entry_time: datetime
    exit_time: Optional[datetime] = None
    exit_reason: Optional[str] = None
    gross_pnl: float
    charges: float
    net_pnl: float
    configured_sl_points: Optional[float] = None
    configured_target_points: Optional[float] = None
    effective_sl_points: Optional[float] = None
    effective_target_points: Optional[float] = None
    sl_trigger_price: Optional[float] = None
    target_trigger_price: Optional[float] = None
    execution_mode: Optional[str] = "TRIGGER_PRICE"


class PaperTradeResponse(BaseModel):
    id: int
    position_id: int
    underlying_symbol: str
    underlying_price_at_entry: float
    option_symbol: str
    strike: float
    expiry: str
    entry_time: datetime
    exit_time: datetime
    entry_price: float
    exit_price: float
    quantity: int
    target_price: float
    stop_price: float
    exit_reason: str
    gross_pnl: float
    entry_charge: float = 10.0
    exit_charge: float = 10.0
    total_charges: float
    net_pnl: float
    is_win: bool
    configured_sl_points: Optional[float] = None
    configured_target_points: Optional[float] = None
    effective_sl_points: Optional[float] = None
    effective_target_points: Optional[float] = None
    sl_trigger_price: Optional[float] = None
    target_trigger_price: Optional[float] = None
    slippage_cost: Optional[float] = 0.0
    execution_mode: Optional[str] = "TRIGGER_PRICE"
    is_ambiguous: Optional[bool] = False
    ambiguity_flag: Optional[str] = None
    holding_time_minutes: Optional[int] = 0


class BacktestRequest(BaseModel):
    strategy_id: str = "UT_BOT"  # UT_BOT or EMA_RSI
    instrument_symbol: str = "NIFTY ATM CE"  # NIFTY 50, NIFTY ATM CE, NIFTY ATM PE, or custom
    timeframe_minutes: int = 1  # 1, 3, 5, 15
    days: Optional[int] = 5  # 1, 2, 3, 5, 10, 30, 60, 90, 180, 365
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    data_source: str = "SYNTHETIC_TEST"  # SYNTHETIC_TEST or REAL_MARKET
    use_synthetic_data: bool = True  # True: deterministic synthetic, False: Kotak Neo real market
    initial_capital: float = 100000.0
    lots: int = 5
    lot_size: int = 65
    target_points: float = 4.0
    stop_points: float = 2.0
    max_loss_per_trade: Optional[float] = 1000.0
    use_risk_cap: bool = False  # If True, applies ₹1,000 loss cap
    key_value: float = 1.0
    atr_period: int = 10
    use_heikin_ashi: bool = False
    signal_source: str = "CHART_INSTRUMENT"  # CHART_INSTRUMENT or NIFTY_INDEX
    slippage_points: float = 0.10
    execution_mode: str = "TRIGGER_PRICE"  # TRIGGER_PRICE or REALISTIC
    exit_on_ut_sell_signal: bool = True  # UT Sell Signal exit toggle (default ON)
    same_candle_resolution: str = "CONSERVATIVE_STOP"
    seed: int = 42
    ut_bot: Optional[Dict[str, Any]] = None
    supertrend_ema: Optional[Dict[str, Any]] = None
    supertrend_atr_period: Optional[int] = 10
    supertrend_multiplier: Optional[float] = 3.0
    ema_fast: Optional[int] = 9
    ema_slow: Optional[int] = 21
    target_net_profit: Optional[float] = 200.0
    daily_profit_target: Optional[float] = 1000.0
    daily_loss_limit: Optional[float] = -2000.0


class DailyAnalyticsSchema(BaseModel):
    date: str
    trades: int = 0
    wins: int = 0
    losses: int = 0
    win_rate: float = 0.0
    grossProfit: float = 0.0
    grossLoss: float = 0.0
    gross_profit: float = 0.0
    gross_loss: float = 0.0
    charges: float = 0.0
    pnl: float = 0.0
    net_pnl: float = 0.0


class AnalyticsSummaryResponse(BaseModel):
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    gross_profit: float = 0.0
    gross_loss: float = 0.0
    net_profit: float = 0.0
    profit_factor: float = 0.0
    avg_profit_per_trade: float = 0.0
    avg_loss_per_trade: float = 0.0
    max_drawdown: float = 0.0
    max_drawdown_percent: float = 0.0
    largest_winning_trade: float = 0.0
    largest_losing_trade: float = 0.0
    total_brokerage_charges: float = 0.0
    consecutive_wins_max: int = 0
    consecutive_losses_max: int = 0
    daily_summary: List[DailyAnalyticsSchema] = []
    monthly_summary: List[Dict[str, Any]] = []
    equity_curve: List[Dict[str, Any]] = []


class ManualTradeRequest(BaseModel):
    action: str = "BUY"  # BUY
    lots: int = 1
    contract_strike: Optional[float] = None
    expiry: Optional[str] = None


class SystemEventResponse(BaseModel):
    id: int
    event_type: str
    title: str
    message: str
    created_at: datetime


class ChargeSettingsRequest(BaseModel):
    entry_charge_per_order: float = Field(default=10.0, ge=0.0)
    exit_charge_per_order: float = Field(default=10.0, ge=0.0)


class ChargeSettingsResponse(BaseModel):
    entry_charge_per_order: float
    exit_charge_per_order: float
    total_roundtrip_charge: float
    status: Optional[str] = "SUCCESS"
    message: Optional[str] = None


class AutoExitSettingsSchema(BaseModel):
    enabled: bool = True
    auto_close_time: str = "15:20"
    auto_close_time_display: Optional[str] = "03:20 PM IST"
    apply_to_all_strategies: bool = True
    close_profitable: bool = True
    close_losing: bool = True
    last_status: Optional[str] = "STANDBY: Scheduled for 03:20 PM IST"
    last_run_time: Optional[str] = None
    awaiting_valid_data: bool = False
    execution_warning: Optional[str] = None
    time_remaining_seconds: int = 0
    time_remaining_display: str = "0m 0s"
    session_cutoff_active: bool = False
    open_positions_count: int = 0
    unrealized_pnl: float = 0.0


class AutoExitSettingsUpdateRequest(BaseModel):
    enabled: bool = True
    auto_close_time: str = "15:20"
    apply_to_all_strategies: bool = True
    close_profitable: bool = True
    close_losing: bool = True


class AIMicroScalperConfigUpdateRequest(BaseModel):
    initial_capital: Optional[float] = Field(default=20000.0, ge=1000.0)
    lots: Optional[int] = Field(default=2, ge=1, le=20)
    lot_size: Optional[int] = Field(default=65, ge=1)
    preferred_premium_min: Optional[float] = Field(default=100.0, ge=10.0)
    preferred_premium_max: Optional[float] = Field(default=150.0, ge=20.0)
    target_net_profit: Optional[float] = Field(default=200.0, ge=10.0)
    max_loss_per_trade: Optional[float] = Field(default=300.0, ge=10.0)
    daily_profit_target: Optional[float] = Field(default=500.0, ge=50.0)
    daily_loss_limit: Optional[float] = Field(default=-500.0, le=-50.0)
    max_trades_per_day: Optional[int] = Field(default=5, ge=1, le=20)
    max_consecutive_losses: Optional[int] = Field(default=2, ge=1, le=10)
    max_holding_time_minutes: Optional[int] = Field(default=5, ge=1, le=60)
    entry_start_ist: Optional[str] = "09:25"
    entry_end_ist: Optional[str] = "14:45"
    force_exit_ist: Optional[str] = "15:20"
    roundtrip_charges: Optional[float] = Field(default=20.0, ge=0.0)
    max_spread: Optional[float] = Field(default=0.50, ge=0.05)
    slippage_points: Optional[float] = Field(default=0.05, ge=0.0)


class AIMicroScalperBacktestRequest(BaseModel):
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    duration_days: Optional[int] = None
    data_source: str = "KOTAK_NEO_HISTORICAL"  # KOTAK_NEO_HISTORICAL or SYNTHETIC_TEST
    execution_mode: str = "TRIGGER_PRICE"      # TRIGGER_PRICE or REALISTIC
    initial_capital: float = 20000.0
    lots: int = 2
    lot_size: int = 65
    target_net_profit: float = 200.0
    max_loss_per_trade: float = 300.0
    daily_profit_target: float = 500.0
    daily_loss_limit: float = -500.0
    max_trades_per_day: int = 5
    max_consecutive_losses: int = 2
    max_holding_time_minutes: int = 5
    roundtrip_charges: float = 20.0
    slippage_points: float = 0.05
    split_type: Optional[str] = None           # TRAIN, VALIDATION, TEST, or None (ALL)
