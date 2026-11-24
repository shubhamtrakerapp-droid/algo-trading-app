export interface MarketStatus {
  is_connected: boolean;
  is_demo: boolean;
  broker_name: string;
  feed_status: string;
  data_freshness?: string;
  market_session_status?: string;
  is_market_open?: boolean;
  is_stale: boolean;
  last_tick_time: string | null;
  nifty_price: number;
  option_symbol: string;
  option_premium: number;
  atm_strike: number;
  expiry: string;
  lot_size: number;
  instrument_token: string;
  timestamp: string;
}

export interface Candle {
  timestamp: number;
  time_iso?: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  ema_9?: number;
  ema_21?: number;
  ema_50?: number;
  rsi_14?: number;
  vwap?: number;
  atr?: number;
  trailing_stop?: number;
  signal_type?: string;
  ha_open?: number;
  ha_high?: number;
  ha_low?: number;
  ha_close?: number;
}

export interface OptionChainStrike {
  strike: number;
  is_atm: boolean;
  ce_symbol: string;
  ce_token: string;
  ce_ltp: number;
  ce_oi: number;
  ce_volume: number;
  pe_symbol: string;
  pe_token: string;
  pe_ltp: number;
  pe_oi: number;
  pe_volume: number;
}

export type OptionStrike = OptionChainStrike;

export interface OptionChainResponse {
  underlying: string;
  spot_price: number;
  atm_strike: number;
  expiry: string;
  strikes: OptionChainStrike[];
}

export interface StrategyStatus {
  status: string;
  timestamp?: string;
  candle_time?: string;
  time_ist?: string;
  underlying_price?: number;
  ema_9?: number;
  ema_21?: number;
  ema_50?: number;
  rsi_14?: number;
  condition_1: boolean;
  condition_2: boolean;
  condition_3: boolean;
  condition_4: boolean;
  signal: string;
  is_buy: boolean;
  message?: string;
}

export interface StrategySettings {
  name: string;
  underlying: string;
  timeframe: string;
  ema_fast: number;
  ema_medium: number;
  ema_slow: number;
  rsi_period: number;
  rsi_threshold: number;
  session_start_ist: string;
  session_end_ist: string;
  force_exit_ist: string;
  target_points: number;
  stop_points: number;
  max_loss_per_trade: number;
  default_lots: number;
  lot_size: number;
  is_active: boolean;
}

export type StrategyType = 'EMA_RSI' | 'UT_BOT' | 'SUPERTREND_EMA' | 'AI_MICRO_SCALPER_V1';

export interface SupertrendEMAConfig {
  atr_period: number;
  multiplier: number;
  ema_fast: number;
  ema_slow: number;
  lots: number;
  lot_size: number;
  target_net_profit: number;
  max_loss_per_trade: number;
  daily_profit_target: number;
  daily_loss_limit: number;
  roundtrip_charges?: number;
  target_points?: number;
  stop_points?: number;
  theoretical_target_pts?: number;
  theoretical_stop_pts?: number;
}

export interface StrategyDailyRiskStatus {
  strategy_id: string;
  trading_date: string;
  realized_net_pnl: number;
  gross_pnl: number;
  total_charges: number;
  trade_count: number;
  winning_trades: number;
  losing_trades: number;
  daily_profit_target: number;
  daily_loss_limit: number;
  profit_target_progress_pct: number;
  loss_limit_progress_pct: number;
  is_locked: boolean;
  lock_reason: string;
  status_text: string;
}

export interface UTBotConfig {
  key_value: number;
  atr_period: number;
  use_heikin_ashi: boolean;
  lots: number;
  lot_size: number;
  target_points: number;
  stop_points: number;
  max_loss_per_trade: number | null;
  signal_source: 'CHART_INSTRUMENT' | 'NIFTY_INDEX';
  exit_on_ut_sell_signal?: boolean;
  execution_mode?: 'TRIGGER_PRICE' | 'REALISTIC';
}

export interface StrategyProfile {
  id: StrategyType;
  name: string;
  description: string;
  is_selected: boolean;
  is_active: boolean;
  timeframe: string;
  config: Record<string, any>;
  live_telemetry?: {
    candle_time?: string;
    source_price?: number;
    atr?: number;
    trailing_stop?: number;
    prev_trailing_stop?: number;
    pos?: number;
    above_crossover?: boolean;
    below_crossunder?: boolean;
    is_buy?: boolean;
    is_sell?: boolean;
    session_valid?: boolean;
    action_reason?: string;
  };
}

export type ChartType = 'candlestick' | 'bar' | 'line' | 'area' | 'heikin_ashi';
export type Timeframe = '1m' | '2m' | '3m' | '5m' | '15m' | '30m' | '1h' | '4h' | '1D';
export type ChartMode = 'LIVE' | 'BACKTEST' | 'HISTORICAL';
export type RangePreset = 'TODAY' | '1D' | '5D' | '1M' | '3M' | '6M' | '1Y' | 'CUSTOM';

export interface ChartTradeMarker {
  id: string;
  trade_id: number;
  time: number;
  position: 'belowBar' | 'aboveBar';
  color: string;
  shape: 'arrowUp' | 'arrowDown' | 'circle';
  text: string;
  trade_type: 'ENTRY' | 'EXIT';
  exit_reason?: string;
  strategy_id: string;
  contract: string;
  price: number;
  quantity: number;
  sl_trigger?: number;
  target_trigger?: number;
  gross_pnl?: number;
  charges?: number;
  slippage?: number;
  net_pnl?: number;
  is_ambiguous?: boolean;
  entry_time: string;
  exit_time?: string;
}

export interface ChartCandlesResponse {
  status: string;
  symbol: string;
  timeframe: string;
  chart_type: string;
  mode: string;
  data_source: string;
  range_preset: string;
  candles_count: number;
  oldest_timestamp?: number;
  newest_timestamp?: number;
  has_more: boolean;
  instrument_info?: {
    symbol: string;
    instrument_token: string;
    exchange_segment: string;
    is_index: boolean;
    strike: number | null;
    option_type: string | null;
    expiry: string;
    current_ltp: number;
    lot_size: number;
  };
  candles: Candle[];
}

export interface InstrumentItem {
  symbol: string;
  name: string;
  type: string;
  strike: number | null;
  current_price: number;
  token: string;
  exchange: string;
}

export interface BacktestRunItem {
  id: number;
  run_id?: number;
  strategy_id: string;
  strategy_name: string;
  timeframe?: string;
  instrument_symbol: string;
  start_date: string;
  end_date: string;
  total_trades: number;
  win_rate: number;
  net_profit: number;
  profit_factor?: number;
  max_drawdown?: number;
  data_source: string;
  created_at: string | null;
}

export interface MarketDynamicsStats {
  nifty_open: number;
  nifty_close: number;
  nifty_drift: number;
  nifty_drift_pct: number;
  option_open: number;
  option_close: number;
  option_drift: number;
  option_drift_pct: number;
  avg_1m_candle_range: number;
  max_1m_candle_range: number;
  candle_count: number;
}

export interface ComparisonMatrixItem {
  key: string;
  label: string;
  data_source: string;
  data_quality_status: string;
  execution_mode: string;
  total_trades: number;
  winning_trades: number;
  losing_trades: number;
  win_rate: number;
  gross_profit: number;
  gross_loss: number;
  total_charges: number;
  total_slippage: number;
  net_profit: number;
  profit_factor: number;
  max_drawdown: number;
  max_drawdown_percent: number;
  avg_holding_time_minutes: number;
  equity_curve: { trade: number; equity: number; time: string }[];
}

export interface RootCauseItem {
  category: string;
  impact: string;
  finding: string;
  synthetic_metric: string;
  real_metric: string;
}

export interface ComparisonAuditResponse {
  status: string;
  date_range: { start_date: string; end_date: string };
  strategy: {
    name: string;
    key_value: number;
    atr_period: number;
    target_points: number;
    stop_points: number;
    lots: number;
    lot_size: number;
    quantity: number;
    charges: string;
  };
  market_dynamics: {
    synthetic: MarketDynamicsStats;
    real_market: MarketDynamicsStats;
  };
  comparison_matrix: ComparisonMatrixItem[];
  root_causes: RootCauseItem[];
  runs: Record<string, { summary: ComparisonMatrixItem; trades: any[] }>;
}
export type DrawingType = 'trend' | 'horizontal' | 'vertical' | 'rectangle' | 'price_label' | 'text';

export interface ChartDrawing {
  id: string;
  type: DrawingType;
  points: { price: number; time: number }[];
  color: string;
  text?: string;
  lineWidth?: number;
}

export interface PaperPosition {
  id: number;
  instrument_token: string;
  symbol: string;
  strike: number;
  expiry: string;
  lot_size: number;
  lots: number;
  quantity: number;
  entry_price: number;
  current_price: number;
  target_price: number;
  stop_price: number;
  effective_stop_distance: number;
  max_loss_amount: number;
  highest_price: number;
  lowest_price: number;
  status: string;
  entry_time: string;
  exit_time?: string | null;
  exit_reason?: string | null;
  gross_pnl: number;
  charges: number;
  net_pnl: number;
  configured_sl_points?: number;
  configured_target_points?: number;
  effective_sl_points?: number;
  effective_target_points?: number;
  sl_trigger_price?: number;
  target_trigger_price?: number;
  execution_mode?: 'TRIGGER_PRICE' | 'REALISTIC';
}

export interface PaperTrade {
  id: number;
  position_id: number;
  underlying_symbol: string;
  underlying_price_at_entry: number;
  option_symbol: string;
  strike: number;
  expiry: string;
  entry_time: string;
  exit_time: string;
  entry_price: number;
  exit_price: number;
  quantity: number;
  target_price: number;
  stop_price: number;
  exit_reason: string;
  entry_reason?: string;
  gross_pnl: number;
  entry_charge?: number;
  exit_charge?: number;
  charges_brokerage: number;
  charges_stt: number;
  charges_exchange: number;
  charges_gst: number;
  charges_sebi: number;
  charges_stamp: number;
  total_charges: number;
  net_pnl: number;
  is_win: boolean;
  configured_sl_points?: number;
  configured_target_points?: number;
  effective_sl_points?: number;
  effective_target_points?: number;
  sl_trigger_price?: number;
  target_trigger_price?: number;
  slippage_cost?: number;
  execution_mode?: 'TRIGGER_PRICE' | 'REALISTIC';
  is_ambiguous?: boolean;
  ambiguity_flag?: string;
  holding_time_minutes?: number;
}

export interface ChargeSettings {
  entry_charge_per_order: number;
  exit_charge_per_order: number;
  total_roundtrip_charge: number;
  status?: string;
  message?: string;
}

export interface AutoExitSettings {
  enabled: boolean;
  auto_close_time: string;
  auto_close_time_display?: string;
  apply_to_all_strategies: boolean;
  close_profitable: boolean;
  close_losing: boolean;
  last_status?: string;
  last_run_time?: string | null;
  awaiting_valid_data?: boolean;
  execution_warning?: string | null;
  time_remaining_seconds: number;
  time_remaining_display: string;
  session_cutoff_active: boolean;
  open_positions_count?: number;
  unrealized_pnl?: number;
}

export interface PaperAccountStatus {
  initial_capital: number;
  cash_balance: number;
  portfolio_value: number;
  realized_pnl: number;
  unrealized_pnl: number;
  daily_pnl: number;
  total_trades: number;
  win_rate: number;
  active_position: PaperPosition | null;
  default_lots: number;
  max_loss_per_trade: number;
  target_points: number;
  stop_points: number;
  force_exit_time_ist: string;
  auto_exit_settings?: AutoExitSettings;
}

export interface BacktestTrade {
  id?: number;
  trade_num?: number;
  signal_time: string;
  entry_time: string;
  exit_time: string;
  underlying_price: number;
  option_symbol: string;
  strike: number;
  expiry: string;
  entry_price: number;
  exit_price: number;
  quantity: number;
  target: number;
  stop: number;
  exit_reason: string;
  gross_pnl: number;
  entry_charge?: number;
  exit_charge?: number;
  charges: number;
  net_pnl: number;
  is_win: boolean;
  holding_time_minutes?: number;
  configured_sl_points?: number;
  configured_target_points?: number;
  effective_sl_points?: number;
  effective_target_points?: number;
  sl_trigger_price?: number;
  target_trigger_price?: number;
  slippage_cost?: number;
  execution_mode?: 'TRIGGER_PRICE' | 'REALISTIC';
  is_ambiguous?: boolean;
  ambiguity_flag?: string;
}

export interface DailyAnalytics {
  date: string;
  trades: number;
  wins: number;
  losses: number;
  win_rate: number;
  pnl: number;
  net_pnl?: number;
  grossProfit: number;
  grossLoss: number;
  gross_profit?: number;
  gross_loss?: number;
  charges: number;
}

export interface BacktestResult {
  run_id?: number;
  strategy_id?: string;
  strategy_name: string;
  timeframe?: string;
  instrument?: string;
  contract_symbol?: string;
  expiry?: string;
  start_date: string;
  end_date: string;
  data_source: string;
  data_quality_status?: string;
  execution_mode?: string;
  exit_on_ut_sell_signal?: boolean;
  valid_candles_count?: number;
  missing_candles_count?: number;
  initial_capital: number;
  final_capital: number;
  total_trades: number;
  winning_trades: number;
  losing_trades: number;
  win_rate: number;
  gross_profit: number;
  gross_loss: number;
  net_profit: number;
  max_drawdown: number;
  max_drawdown_pct?: number;
  max_drawdown_percent?: number;
  profit_factor: number;
  avg_profit: number;
  avg_loss: number;
  largest_win: number;
  largest_loss: number;
  total_charges: number;
  consecutive_wins_max?: number;
  consecutive_losses_max?: number;
  total_slippage?: number;
  avg_holding_time?: number;
  avg_holding_time_minutes?: number;
  signal_instrument?: string;
  execution_instrument?: string;
  buy_entries_count?: number;
  sell_exits_count?: number;
  target_exits_count?: number;
  stop_loss_exits_count?: number;
  auto_close_exits_count?: number;
  diagnostics_summary?: {
    buy_entries_count?: number;
    sell_exits_count?: number;
    target_exits_count?: number;
    stop_loss_exits_count?: number;
    auto_close_exits_count?: number;
    other_exits_count?: number;
    buy_signals_ignored?: number;
    sell_signals_ignored?: number;
    total_signals_logged?: number;
  };
  execution_diagnostics?: Array<{
    timestamp: string;
    signal_time: string;
    signal_type: string;
    signal_instrument: string;
    execution_instrument: string;
    position_before_signal: string;
    action_taken: string;
    action_reason: string;
    entry_price?: number | null;
    exit_price?: number | null;
    exit_reason?: string | null;
    gross_pnl: number;
    charges: number;
    slippage: number;
    net_pnl: number;
  }>;
  trades: BacktestTrade[];
  equity_curve?: Array<{
    trade: number;
    equity: number;
    net_pnl?: number;
    time: string;
  }>;
  drawdown_curve?: Array<{
    trade: number;
    drawdown: number;
    drawdown_pct: number;
  }>;
  daily_summary?: DailyAnalytics[];
  date_wise_summary?: DateWiseSummaryItem[];
  period_summary?: BacktestPeriodSummary;
}

export interface BacktestPeriodSummary {
  selected_start_date: string;
  selected_end_date: string;
  actual_first_candle_date: string;
  actual_last_candle_date: string;
  trading_days_available: number;
  trading_days_tested: number;
  trading_days_with_trades: number;
  trading_days_without_trades: number;
  missing_data_days: string[];
  missing_data_count: number;
}

export interface DateWiseSummaryItem {
  date: string;
  day_name: string;
  status: 'TRADED' | 'NO_TRADE' | 'HOLIDAY' | 'WEEKEND' | 'MISSING_DATA';
  reason?: string;
  has_trades: boolean;
  trades: number;
  trades_count: number;
  winning_trades: number;
  losing_trades: number;
  wins: number;
  losses: number;
  win_rate: number;
  gross_profit: number;
  gross_loss: number;
  charges: number;
  slippage: number;
  slippage_cost?: number;
  net_pnl: number;
  pnl?: number;
  best_trade: number;
  worst_trade: number;
  daily_drawdown: number;
}

export interface AnalyticsSummary {
  total_trades: number;
  winning_trades: number;
  losing_trades: number;
  win_rate: number;
  gross_profit: number;
  gross_loss: number;
  net_profit: number;
  profit_factor: number;
  avg_profit_per_trade: number;
  avg_loss_per_trade: number;
  max_drawdown: number;
  max_drawdown_percent: number;
  largest_winning_trade: number;
  largest_losing_trade: number;
  total_brokerage_charges: number;
  consecutive_wins_max: number;
  consecutive_losses_max: number;
  daily_summary: DailyAnalytics[];
  monthly_summary: Array<{
    month: string;
    trades: number;
    pnl: number;
    wins: number;
    win_rate: number;
  }>;
  equity_curve: Array<{
    trade: number;
    equity: number;
    net_pnl?: number;
    time: string;
  }>;
}

export interface SystemEventItem {
  id: number;
  event_type: string;
  title: string;
  message: string;
  details?: string;
  created_at: string;
}

export interface StreakSummary {
  current_streak_type: 'WIN' | 'LOSS' | 'NONE';
  current_streak_count: number;
  max_consecutive_wins: number;
  max_consecutive_losses: number;
  total_winning_days: number;
  total_losing_days: number;
  total_neutral_days: number;
  longest_no_trade_period_days: number;
}

export interface CalendarDayItem {
  day_number: number;
  date: string;
  weekday: number; // 0=Mon .. 6=Sun
  weekday_name: string;
  is_future: boolean;
  has_trades: boolean;
  trades_count: number;
  wins: number;
  losses: number;
  win_rate: number;
  gross_profit: number;
  gross_loss: number;
  total_charges: number;
  slippage_cost: number;
  net_pnl: number;
  status: 'WIN' | 'LOSS' | 'NEUTRAL' | 'NO_TRADE' | 'FUTURE';
  avg_holding_time: number;
}

export interface MonthlySummary {
  year: number;
  month: number;
  month_name: string;
  month_str: string;
  net_pnl: number;
  gross_profit: number;
  gross_loss: number;
  total_charges: number;
  total_slippage: number;
  total_trades: number;
  winning_days: number;
  losing_days: number;
  no_trade_days: number;
  total_trading_days: number;
  win_rate: number;
  avg_daily_pnl: number;
  best_day: { date: string | null; net_pnl: number };
  worst_day: { date: string | null; net_pnl: number };
  streaks: StreakSummary;
  holding_time: {
    avg_minutes: number;
    max_minutes: number;
    min_minutes: number;
  };
}

export interface MonthlyCalendarResponse {
  status: string;
  data_source: string;
  strategy_filter: string;
  execution_mode_filter: string;
  year: number;
  month: number;
  month_name: string;
  first_weekday: number; // 0=Mon, 6=Sun
  num_days: number;
  summary: MonthlySummary;
  days: CalendarDayItem[];
}

export interface YearlyMonthItem {
  month: number;
  month_name: string;
  short_name: string;
  is_future: boolean;
  trades_count: number;
  net_pnl: number;
  gross_profit: number;
  gross_loss: number;
  charges: number;
  slippage: number;
  winning_days: number;
  losing_days: number;
  win_rate: number;
  status: 'PROFIT' | 'LOSS' | 'NEUTRAL' | 'NO_ACTIVITY' | 'FUTURE';
}

export interface AnnualSummary {
  year: number;
  annual_net_pnl: number;
  annual_gross_profit: number;
  annual_gross_loss: number;
  annual_charges: number;
  annual_slippage: number;
  total_trades: number;
  profitable_months: number;
  losing_months: number;
  neutral_months: number;
  winning_days: number;
  losing_days: number;
  best_month: { month: number | null; month_name: string; net_pnl: number };
  worst_month: { month: number | null; month_name: string; net_pnl: number };
  max_consecutive_losing_days: number;
  max_consecutive_winning_days: number;
}

export interface YearlyCalendarResponse {
  status: string;
  data_source: string;
  strategy_filter: string;
  execution_mode_filter: string;
  year: number;
  annual_summary: AnnualSummary;
  months: YearlyMonthItem[];
}

export interface DailyDetailResponse {
  date: string;
  has_trades: boolean;
  status?: string;
  status_description?: string;
  trades_count: number;
  net_pnl: number;
  gross_pnl: number;
  gross_profit: number;
  gross_loss: number;
  total_charges: number;
  slippage_cost: number;
  wins: number;
  losses: number;
  win_rate: number;
  avg_win: number;
  avg_loss: number;
  largest_win: number;
  largest_loss: number;
  avg_holding_time: number;
  max_holding_time: number;
  min_holding_time: number;
  trades: any[];
}

export interface CustomRangeResponse {
  status: string;
  data_source: string;
  strategy_filter: string;
  execution_mode_filter: string;
  start_date: string;
  end_date: string;
  total_trades: number;
  gross_profit: number;
  gross_loss: number;
  total_charges: number;
  total_slippage: number;
  net_pnl: number;
  winning_days: number;
  losing_days: number;
  total_trading_days: number;
  win_rate: number;
  streaks: StreakSummary;
  daily_summary: any[];
  trades: any[];
}


// -------------------------------------------------------------
// PCR & Options Market Analysis Interfaces
// -------------------------------------------------------------

export interface PCRSummaryCard {
  value: number | null;
  previous: number | null;
  delta: number | null;
  total_put_oi?: number;
  total_call_oi?: number;
  total_put_volume?: number;
  total_call_volume?: number;
  sentiment_label: string;
  description: string;
}

export interface PCRCallOICard {
  total_oi: number;
  oi_change: number;
  oi_change_pct: number;
  highest_oi_strike: number;
  highest_oi_value: number;
  highest_oi_change_strike: number;
  highest_oi_change_value: number;
}

export interface PCRPutOICard {
  total_oi: number;
  oi_change: number;
  oi_change_pct: number;
  highest_oi_strike: number;
  highest_oi_value: number;
  highest_oi_change_strike: number;
  highest_oi_change_value: number;
}

export interface PCRPriceVWAPCard {
  spot_price: number;
  spot_change: number;
  spot_change_pct: number;
  index_vwap: number | null;
  index_vwap_label: string;
  futures_symbol: string;
  futures_ltp: number | null;
  futures_vwap: number | null;
  futures_vwap_label: string;
  spot_vwap_diff: number | null;
  spot_vwap_diff_pct: number | null;
}

export interface PCRMarketBiasCard {
  bias: string;
  headline: string;
  explanation: string;
  score: number;
  breakdown: {
    oi_pcr_bias: string;
    volume_pcr_bias: string;
    oi_addition_bias: string;
    price_vwap_bias: string;
    pcr_trend: string;
  };
}

export interface PCRStrikeData {
  strike: number;
  is_atm: boolean;
  // CALL SIDE
  ce_symbol: string;
  ce_token: string;
  ce_ltp: number | null;
  ce_volume: number;
  ce_oi: number;
  ce_oi_change: number;
  ce_oi_change_pct: number;
  ce_moneyness: 'ITM' | 'ATM' | 'OTM';
  // PUT SIDE
  pe_symbol: string;
  pe_token: string;
  pe_ltp: number | null;
  pe_volume: number;
  pe_oi: number;
  pe_oi_change: number;
  pe_oi_change_pct: number;
  pe_moneyness: 'ITM' | 'ATM' | 'OTM';
  // STRIKE-WISE RATIOS
  strike_oi_pcr: number | null;
  strike_vol_ratio: number | null;
}

export interface PCRResponse {
  status: string;
  message?: string;
  underlying: string;
  expiry: string;
  lot_size: number;
  timestamp_ist: string;
  trading_date: string;
  data_status: 'FRESH' | 'UPDATING' | 'STALE' | 'MARKET CLOSED' | 'API ERROR';
  warning?: string | null;
  is_market_open: boolean;
  range_info: {
    atm_strike: number;
    strike_range: number;
    requested_levels: number;
    selected_levels: number;
    range_oi_pcr?: number;
    all_oi_pcr?: number;
    range_volume_pcr?: number;
    all_volume_pcr?: number;
    all_call_oi?: number;
    all_put_oi?: number;
  };
  cards: {
    oi_pcr: PCRSummaryCard;
    volume_pcr: PCRSummaryCard;
    call_oi: PCRCallOICard;
    put_oi: PCRPutOICard;
    price_vwap: PCRPriceVWAPCard;
    market_bias: PCRMarketBiasCard;
  };
  levels: {
    support_1: number;
    support_1_oi: number;
    resistance_1: number;
    resistance_1_oi: number;
    support_addition_strike: number;
    resistance_addition_strike: number;
    atm_strike: number;
  };
  strikes: PCRStrikeData[];
}

export interface PCRHistoryPoint {
  timestamp: number;
  time_ist: string;
  spot_price: number;
  oi_pcr: number | null;
  volume_pcr: number | null;
  futures_vwap: number | null;
  total_call_oi: number;
  total_put_oi: number;
  total_call_volume: number;
  total_put_volume: number;
  sentiment: string;
}

export interface PCRHistoryResponse {
  status: string;
  underlying: string;
  trading_date?: string;
  strike_range: number;
  data_points_count: number;
  history: PCRHistoryPoint[];
}

export interface PCRSettings {
  underlying: string;
  expiry?: string;
  strike_range: number;
  refresh_interval_sec: number;
  bullish_threshold: number;
  bearish_threshold: number;
  neutral_upper: number;
  neutral_lower: number;
  show_volume: boolean;
  show_oi_change_pct: boolean;
  show_strike_ratios: boolean;
}
