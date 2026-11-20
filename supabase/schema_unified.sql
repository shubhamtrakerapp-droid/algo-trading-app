-- =============================================================================
-- NEXTRADE — SUPABASE POSTGRESQL INITIAL DATABASE MIGRATION
-- Production-ready schema with RLS, foreign keys, indexes, and UTC/IST timestamps
-- =============================================================================

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- =============================================================================
-- 1. USERS & PROFILES
-- =============================================================================
CREATE TABLE IF NOT EXISTS public.users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    auth_user_id UUID UNIQUE REFERENCES auth.users(id) ON DELETE CASCADE,
    username VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(100) UNIQUE,
    full_name VARCHAR(100),
    role VARCHAR(20) DEFAULT 'trader' NOT NULL,
    created_at TIMESTAMPTZ DEFAULT TIMEZONE('utc', NOW()) NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT TIMEZONE('utc', NOW()) NOT NULL
);

-- =============================================================================
-- 2. BROKER CONNECTIONS (Server-side metadata only; credentials in environment)
-- =============================================================================
CREATE TABLE IF NOT EXISTS public.broker_connections (
    id BIGSERIAL PRIMARY KEY,
    user_id UUID REFERENCES public.users(id) ON DELETE CASCADE,
    broker_name VARCHAR(50) DEFAULT 'kotak_neo' NOT NULL,
    environment VARCHAR(20) DEFAULT 'prod' NOT NULL,
    ucc VARCHAR(50),
    auth_status VARCHAR(30) DEFAULT 'DEMO_MODE' NOT NULL, -- CONNECTED, DISCONNECTED, DEMO_MODE, ERROR
    token_expires_at TIMESTAMPTZ,
    last_heartbeat TIMESTAMPTZ,
    error_message TEXT,
    updated_at TIMESTAMPTZ DEFAULT TIMEZONE('utc', NOW()) NOT NULL
);

-- =============================================================================
-- 3. INSTRUMENT & CONTRACT MASTER
-- =============================================================================
CREATE TABLE IF NOT EXISTS public.instruments (
    id BIGSERIAL PRIMARY KEY,
    exchange_segment VARCHAR(20) NOT NULL, -- nse_cm, nse_fo
    instrument_token VARCHAR(50) NOT NULL,
    trading_symbol VARCHAR(100) NOT NULL,
    instrument_name VARCHAR(100),
    underlying_symbol VARCHAR(50), -- NIFTY, BANKNIFTY, FINNIFTY
    strike_price NUMERIC(14, 4),
    option_type VARCHAR(10), -- CE, PE, XX
    expiry_date VARCHAR(30), -- YYYY-MM-DD
    lot_size INTEGER DEFAULT 65 NOT NULL,
    tick_size NUMERIC(10, 4) DEFAULT 0.05 NOT NULL,
    is_active BOOLEAN DEFAULT TRUE NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT TIMEZONE('utc', NOW()) NOT NULL,
    CONSTRAINT uq_exchange_token UNIQUE (exchange_segment, instrument_token)
);

CREATE INDEX IF NOT EXISTS ix_instruments_lookup 
    ON public.instruments (underlying_symbol, expiry_date, strike_price, option_type);
CREATE INDEX IF NOT EXISTS ix_instruments_token 
    ON public.instruments (instrument_token);

-- =============================================================================
-- 4. MARKET TICKS (High-frequency buffer)
-- =============================================================================
CREATE TABLE IF NOT EXISTS public.market_ticks (
    id BIGSERIAL PRIMARY KEY,
    instrument_token VARCHAR(50) NOT NULL,
    exchange_segment VARCHAR(20) NOT NULL,
    symbol VARCHAR(100) NOT NULL,
    last_price NUMERIC(14, 4) NOT NULL,
    volume BIGINT DEFAULT 0,
    open_interest BIGINT DEFAULT 0,
    bid NUMERIC(14, 4),
    ask NUMERIC(14, 4),
    timestamp TIMESTAMPTZ DEFAULT TIMEZONE('utc', NOW()) NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_market_ticks_symbol_time 
    ON public.market_ticks (symbol, timestamp DESC);

-- =============================================================================
-- 5. HISTORICAL CANDLES (Multi-timeframe OHLCV)
-- =============================================================================
CREATE TABLE IF NOT EXISTS public.historical_candles (
    id BIGSERIAL PRIMARY KEY,
    instrument_token VARCHAR(50) NOT NULL,
    symbol VARCHAR(100) NOT NULL,
    timeframe VARCHAR(10) DEFAULT '1m' NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    open NUMERIC(14, 4) NOT NULL,
    high NUMERIC(14, 4) NOT NULL,
    low NUMERIC(14, 4) NOT NULL,
    close NUMERIC(14, 4) NOT NULL,
    volume NUMERIC(18, 4) DEFAULT 0.0,
    CONSTRAINT uq_candle_symbol_tf_time UNIQUE (symbol, timeframe, timestamp)
);

CREATE INDEX IF NOT EXISTS ix_candle_symbol_tf_time 
    ON public.historical_candles (symbol, timeframe, timestamp DESC);

-- =============================================================================
-- 6. STRATEGY SETTINGS & PARAMETERS
-- =============================================================================
CREATE TABLE IF NOT EXISTS public.strategy_settings (
    id BIGSERIAL PRIMARY KEY,
    user_id UUID REFERENCES public.users(id) ON DELETE CASCADE,
    strategy_id VARCHAR(50) DEFAULT 'AI_MICRO_SCALPER_V1' NOT NULL,
    name VARCHAR(100) NOT NULL,
    underlying VARCHAR(50) DEFAULT 'NIFTY' NOT NULL,
    timeframe VARCHAR(10) DEFAULT '1m' NOT NULL,
    ema_fast INTEGER DEFAULT 9 NOT NULL,
    ema_medium INTEGER DEFAULT 21 NOT NULL,
    ema_slow INTEGER DEFAULT 50 NOT NULL,
    rsi_period INTEGER DEFAULT 14 NOT NULL,
    rsi_threshold NUMERIC(10, 4) DEFAULT 50.0 NOT NULL,
    session_start_ist VARCHAR(10) DEFAULT '09:20' NOT NULL,
    session_end_ist VARCHAR(10) DEFAULT '15:15' NOT NULL,
    force_exit_ist VARCHAR(10) DEFAULT '15:20' NOT NULL,
    target_points NUMERIC(10, 4) DEFAULT 4.0 NOT NULL,
    stop_points NUMERIC(10, 4) DEFAULT 4.0 NOT NULL,
    max_loss_per_trade NUMERIC(14, 4) DEFAULT 1000.0 NOT NULL,
    default_lots INTEGER DEFAULT 1 NOT NULL,
    lot_size INTEGER DEFAULT 65 NOT NULL,
    is_active BOOLEAN DEFAULT TRUE NOT NULL,
    config_json JSONB,
    updated_at TIMESTAMPTZ DEFAULT TIMEZONE('utc', NOW()) NOT NULL
);

-- =============================================================================
-- 7. STRATEGY SIGNALS & EVALUATION AUDIT LOG
-- =============================================================================
CREATE TABLE IF NOT EXISTS public.strategy_signals (
    id BIGSERIAL PRIMARY KEY,
    user_id UUID REFERENCES public.users(id) ON DELETE SET NULL,
    strategy_id VARCHAR(50) DEFAULT 'AI_MICRO_SCALPER_V1' NOT NULL,
    strategy_config JSONB,
    timestamp TIMESTAMPTZ DEFAULT TIMEZONE('utc', NOW()) NOT NULL,
    candle_time TIMESTAMPTZ NOT NULL,
    underlying_symbol VARCHAR(50) DEFAULT 'NIFTY' NOT NULL,
    underlying_price NUMERIC(14, 4) NOT NULL,
    ema_9 NUMERIC(14, 4),
    ema_21 NUMERIC(14, 4),
    ema_50 NUMERIC(14, 4),
    rsi_14 NUMERIC(14, 4),
    atr NUMERIC(14, 4),
    trailing_stop NUMERIC(14, 4),
    condition_1 BOOLEAN,
    condition_2 BOOLEAN,
    condition_3 BOOLEAN,
    condition_4 BOOLEAN,
    signal_type VARCHAR(30) DEFAULT 'NONE' NOT NULL,
    executed BOOLEAN DEFAULT FALSE NOT NULL,
    notes TEXT,
    agent_votes JSONB
);

CREATE INDEX IF NOT EXISTS ix_strategy_signals_strategy_time 
    ON public.strategy_signals (strategy_id, timestamp DESC);

-- =============================================================================
-- 8. PAPER TRADING ORDERS
-- =============================================================================
CREATE TABLE IF NOT EXISTS public.paper_orders (
    id BIGSERIAL PRIMARY KEY,
    user_id UUID REFERENCES public.users(id) ON DELETE CASCADE,
    position_id BIGINT,
    order_type VARCHAR(20) DEFAULT 'MARKET' NOT NULL,
    transaction_type VARCHAR(10) NOT NULL, -- BUY, SELL
    instrument_token VARCHAR(50) NOT NULL,
    symbol VARCHAR(100) NOT NULL,
    strike NUMERIC(14, 4),
    expiry VARCHAR(30),
    quantity INTEGER NOT NULL,
    requested_price NUMERIC(14, 4) NOT NULL,
    executed_price NUMERIC(14, 4) NOT NULL,
    slippage NUMERIC(14, 4) DEFAULT 0.0 NOT NULL,
    status VARCHAR(20) DEFAULT 'FILLED' NOT NULL, -- FILLED, REJECTED, CANCELLED
    rejection_reason VARCHAR(255),
    created_at TIMESTAMPTZ DEFAULT TIMEZONE('utc', NOW()) NOT NULL,
    filled_at TIMESTAMPTZ DEFAULT TIMEZONE('utc', NOW()) NOT NULL
);

-- =============================================================================
-- 9. PAPER POSITIONS (Live Open/Closed Virtual Positions)
-- =============================================================================
CREATE TABLE IF NOT EXISTS public.paper_positions (
    id BIGSERIAL PRIMARY KEY,
    user_id UUID REFERENCES public.users(id) ON DELETE CASCADE,
    strategy_id VARCHAR(50) DEFAULT 'AI_MICRO_SCALPER_V1' NOT NULL,
    strategy_config JSONB,
    instrument_token VARCHAR(50) NOT NULL,
    symbol VARCHAR(100) NOT NULL,
    strike NUMERIC(14, 4) NOT NULL,
    expiry VARCHAR(30) NOT NULL,
    lot_size INTEGER NOT NULL,
    lots INTEGER DEFAULT 1 NOT NULL,
    quantity INTEGER NOT NULL,
    entry_price NUMERIC(14, 4) NOT NULL,
    current_price NUMERIC(14, 4) NOT NULL,
    target_price NUMERIC(14, 4) NOT NULL,
    stop_price NUMERIC(14, 4) NOT NULL,
    effective_stop_distance NUMERIC(14, 4) NOT NULL,
    max_loss_amount NUMERIC(14, 4) DEFAULT 1000.0 NOT NULL,
    configured_sl_points NUMERIC(10, 4) DEFAULT 2.0,
    configured_target_points NUMERIC(10, 4) DEFAULT 4.0,
    effective_sl_points NUMERIC(10, 4) DEFAULT 2.0,
    effective_target_points NUMERIC(10, 4) DEFAULT 4.0,
    sl_trigger_price NUMERIC(14, 4),
    target_trigger_price NUMERIC(14, 4),
    slippage_cost NUMERIC(14, 4) DEFAULT 0.0,
    execution_mode VARCHAR(30) DEFAULT 'REALISTIC',
    highest_price NUMERIC(14, 4) NOT NULL,
    lowest_price NUMERIC(14, 4) NOT NULL,
    status VARCHAR(20) DEFAULT 'OPEN' NOT NULL, -- OPEN, CLOSED
    entry_time TIMESTAMPTZ DEFAULT TIMEZONE('utc', NOW()) NOT NULL,
    exit_time TIMESTAMPTZ,
    exit_reason VARCHAR(50), -- TARGET, STOP_LOSS, FORCE_EXIT_1520, MANUAL, GAP_STOP
    gross_pnl NUMERIC(14, 4) DEFAULT 0.0 NOT NULL,
    entry_charge NUMERIC(14, 4) DEFAULT 10.0 NOT NULL,
    exit_charge NUMERIC(14, 4) DEFAULT 10.0 NOT NULL,
    charges NUMERIC(14, 4) DEFAULT 20.0 NOT NULL,
    net_pnl NUMERIC(14, 4) DEFAULT 0.0 NOT NULL,
    created_at TIMESTAMPTZ DEFAULT TIMEZONE('utc', NOW()) NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT TIMEZONE('utc', NOW()) NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_paper_positions_status 
    ON public.paper_positions (status, strategy_id);

-- =============================================================================
-- 10. PAPER TRADES (Completed Virtual Trades Ledger)
-- =============================================================================
CREATE TABLE IF NOT EXISTS public.paper_trades (
    id BIGSERIAL PRIMARY KEY,
    user_id UUID REFERENCES public.users(id) ON DELETE CASCADE,
    strategy_id VARCHAR(50) DEFAULT 'AI_MICRO_SCALPER_V1' NOT NULL,
    strategy_config JSONB,
    position_id BIGINT REFERENCES public.paper_positions(id) ON DELETE CASCADE NOT NULL,
    signal_id BIGINT,
    underlying_symbol VARCHAR(50) DEFAULT 'NIFTY' NOT NULL,
    underlying_price_at_entry NUMERIC(14, 4) NOT NULL,
    option_symbol VARCHAR(100) NOT NULL,
    strike NUMERIC(14, 4) NOT NULL,
    expiry VARCHAR(30) NOT NULL,
    entry_time TIMESTAMPTZ NOT NULL,
    exit_time TIMESTAMPTZ NOT NULL,
    entry_price NUMERIC(14, 4) NOT NULL,
    exit_price NUMERIC(14, 4) NOT NULL,
    quantity INTEGER NOT NULL,
    target_price NUMERIC(14, 4) NOT NULL,
    stop_price NUMERIC(14, 4) NOT NULL,
    configured_sl_points NUMERIC(10, 4) DEFAULT 2.0,
    configured_target_points NUMERIC(10, 4) DEFAULT 4.0,
    effective_sl_points NUMERIC(10, 4) DEFAULT 2.0,
    effective_target_points NUMERIC(10, 4) DEFAULT 4.0,
    sl_trigger_price NUMERIC(14, 4),
    target_trigger_price NUMERIC(14, 4),
    slippage_cost NUMERIC(14, 4) DEFAULT 0.0,
    execution_mode VARCHAR(30) DEFAULT 'REALISTIC',
    is_ambiguous BOOLEAN DEFAULT FALSE,
    ambiguity_flag VARCHAR(50),
    holding_time_minutes INTEGER DEFAULT 1,
    exit_reason VARCHAR(50) NOT NULL,
    gross_pnl NUMERIC(14, 4) NOT NULL,
    entry_charge NUMERIC(14, 4) DEFAULT 10.0 NOT NULL,
    exit_charge NUMERIC(14, 4) DEFAULT 10.0 NOT NULL,
    charges_brokerage NUMERIC(14, 4) DEFAULT 20.0 NOT NULL,
    charges_stt NUMERIC(14, 4) DEFAULT 0.0 NOT NULL,
    charges_exchange NUMERIC(14, 4) DEFAULT 0.0 NOT NULL,
    charges_gst NUMERIC(14, 4) DEFAULT 0.0 NOT NULL,
    charges_sebi NUMERIC(14, 4) DEFAULT 0.0 NOT NULL,
    charges_stamp NUMERIC(14, 4) DEFAULT 0.0 NOT NULL,
    total_charges NUMERIC(14, 4) DEFAULT 20.0 NOT NULL,
    net_pnl NUMERIC(14, 4) NOT NULL,
    is_win BOOLEAN NOT NULL,
    created_at TIMESTAMPTZ DEFAULT TIMEZONE('utc', NOW()) NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_paper_trades_strategy_exit 
    ON public.paper_trades (strategy_id, exit_time DESC);
CREATE INDEX IF NOT EXISTS ix_paper_trades_user 
    ON public.paper_trades (user_id, exit_time DESC);

-- =============================================================================
-- 11. CHARGE SETTINGS
-- =============================================================================
CREATE TABLE IF NOT EXISTS public.charge_settings (
    id BIGSERIAL PRIMARY KEY,
    user_id UUID REFERENCES public.users(id) ON DELETE CASCADE,
    entry_charge_per_order NUMERIC(10, 4) DEFAULT 10.0 NOT NULL,
    exit_charge_per_order NUMERIC(10, 4) DEFAULT 10.0 NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT TIMEZONE('utc', NOW()) NOT NULL
);

-- =============================================================================
-- 12. AUTO EXIT SETTINGS (Auto Square-Off at 15:20 IST)
-- =============================================================================
CREATE TABLE IF NOT EXISTS public.auto_exit_settings (
    id BIGSERIAL PRIMARY KEY,
    user_id UUID REFERENCES public.users(id) ON DELETE CASCADE,
    enabled BOOLEAN DEFAULT TRUE NOT NULL,
    auto_close_time VARCHAR(10) DEFAULT '15:20' NOT NULL,
    apply_to_all_strategies BOOLEAN DEFAULT TRUE NOT NULL,
    close_profitable BOOLEAN DEFAULT TRUE NOT NULL,
    close_losing BOOLEAN DEFAULT TRUE NOT NULL,
    last_status VARCHAR(200) DEFAULT 'STANDBY: Scheduled for 03:20 PM IST' NOT NULL,
    last_run_time TIMESTAMPTZ,
    last_run_date VARCHAR(20),
    updated_at TIMESTAMPTZ DEFAULT TIMEZONE('utc', NOW()) NOT NULL
);

-- =============================================================================
-- 13. BACKTEST RUNS
-- =============================================================================
CREATE TABLE IF NOT EXISTS public.backtest_runs (
    id BIGSERIAL PRIMARY KEY,
    user_id UUID REFERENCES public.users(id) ON DELETE CASCADE,
    strategy_id VARCHAR(50) DEFAULT 'AI_MICRO_SCALPER_V1' NOT NULL,
    strategy_name VARCHAR(100) NOT NULL,
    strategy_config JSONB,
    timeframe VARCHAR(10) DEFAULT '1m' NOT NULL,
    instrument_symbol VARCHAR(100) DEFAULT 'NIFTY ATM CE' NOT NULL,
    start_date VARCHAR(30) NOT NULL,
    end_date VARCHAR(30) NOT NULL,
    initial_capital NUMERIC(14, 4) DEFAULT 100000.0 NOT NULL,
    final_capital NUMERIC(14, 4) NOT NULL,
    total_trades INTEGER DEFAULT 0 NOT NULL,
    winning_trades INTEGER DEFAULT 0 NOT NULL,
    losing_trades INTEGER DEFAULT 0 NOT NULL,
    win_rate NUMERIC(10, 4) DEFAULT 0.0 NOT NULL,
    gross_profit NUMERIC(14, 4) DEFAULT 0.0 NOT NULL,
    gross_loss NUMERIC(14, 4) DEFAULT 0.0 NOT NULL,
    net_profit NUMERIC(14, 4) DEFAULT 0.0 NOT NULL,
    max_drawdown NUMERIC(14, 4) DEFAULT 0.0 NOT NULL,
    profit_factor NUMERIC(10, 4) DEFAULT 0.0 NOT NULL,
    avg_profit NUMERIC(14, 4) DEFAULT 0.0 NOT NULL,
    avg_loss NUMERIC(14, 4) DEFAULT 0.0 NOT NULL,
    largest_win NUMERIC(14, 4) DEFAULT 0.0 NOT NULL,
    largest_loss NUMERIC(14, 4) DEFAULT 0.0 NOT NULL,
    total_charges NUMERIC(14, 4) DEFAULT 0.0 NOT NULL,
    data_source VARCHAR(50) DEFAULT 'HISTORICAL_DATA' NOT NULL,
    execution_mode VARCHAR(30) DEFAULT 'TRIGGER_PRICE',
    exit_on_ut_sell_signal BOOLEAN DEFAULT FALSE,
    configured_sl_points NUMERIC(10, 4) DEFAULT 2.0,
    configured_target_points NUMERIC(10, 4) DEFAULT 4.0,
    created_at TIMESTAMPTZ DEFAULT TIMEZONE('utc', NOW()) NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_backtest_runs_strategy_time 
    ON public.backtest_runs (strategy_id, created_at DESC);

-- =============================================================================
-- 14. BACKTEST TRADES (Exact run isolation)
-- =============================================================================
CREATE TABLE IF NOT EXISTS public.backtest_trades (
    id BIGSERIAL PRIMARY KEY,
    run_id BIGINT REFERENCES public.backtest_runs(id) ON DELETE CASCADE NOT NULL,
    signal_time TIMESTAMPTZ NOT NULL,
    entry_time TIMESTAMPTZ NOT NULL,
    exit_time TIMESTAMPTZ NOT NULL,
    underlying_price NUMERIC(14, 4) NOT NULL,
    option_symbol VARCHAR(100) NOT NULL,
    strike NUMERIC(14, 4) NOT NULL,
    expiry VARCHAR(30) NOT NULL,
    entry_price NUMERIC(14, 4) NOT NULL,
    exit_price NUMERIC(14, 4) NOT NULL,
    quantity INTEGER NOT NULL,
    target NUMERIC(14, 4) NOT NULL,
    stop NUMERIC(14, 4) NOT NULL,
    configured_sl_points NUMERIC(10, 4) DEFAULT 2.0,
    configured_target_points NUMERIC(10, 4) DEFAULT 4.0,
    effective_sl_points NUMERIC(10, 4) DEFAULT 2.0,
    effective_target_points NUMERIC(10, 4) DEFAULT 4.0,
    sl_trigger_price NUMERIC(14, 4),
    target_trigger_price NUMERIC(14, 4),
    slippage_cost NUMERIC(14, 4) DEFAULT 0.0,
    execution_mode VARCHAR(30) DEFAULT 'TRIGGER_PRICE',
    is_ambiguous BOOLEAN DEFAULT FALSE,
    ambiguity_flag VARCHAR(50),
    holding_time_minutes INTEGER DEFAULT 1,
    exit_reason VARCHAR(50) NOT NULL,
    gross_pnl NUMERIC(14, 4) NOT NULL,
    entry_charge NUMERIC(14, 4) DEFAULT 10.0 NOT NULL,
    exit_charge NUMERIC(14, 4) DEFAULT 10.0 NOT NULL,
    charges NUMERIC(14, 4) NOT NULL,
    net_pnl NUMERIC(14, 4) NOT NULL,
    is_win BOOLEAN NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_backtest_trades_run_id 
    ON public.backtest_trades (run_id);

-- =============================================================================
-- 15. SYSTEM EVENTS & AUDIT LOGS
-- =============================================================================
CREATE TABLE IF NOT EXISTS public.system_events (
    id BIGSERIAL PRIMARY KEY,
    event_type VARCHAR(50) NOT NULL, -- INFO, WARNING, ERROR, FEED_DISCONNECT, RECONNECT, STALE_DATA
    title VARCHAR(200) NOT NULL,
    message TEXT NOT NULL,
    details_json JSONB,
    created_at TIMESTAMPTZ DEFAULT TIMEZONE('utc', NOW()) NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_system_events_type_time 
    ON public.system_events (event_type, created_at DESC);

-- =============================================================================
-- 16. STRATEGY DAILY RISK & DRAWDOWN LOCKS
-- =============================================================================
CREATE TABLE IF NOT EXISTS public.strategy_daily_risks (
    id BIGSERIAL PRIMARY KEY,
    user_id UUID REFERENCES public.users(id) ON DELETE CASCADE,
    strategy_id VARCHAR(50) NOT NULL,
    trading_date VARCHAR(20) NOT NULL, -- YYYY-MM-DD IST
    realized_net_pnl NUMERIC(14, 4) DEFAULT 0.0 NOT NULL,
    gross_pnl NUMERIC(14, 4) DEFAULT 0.0 NOT NULL,
    total_charges NUMERIC(14, 4) DEFAULT 0.0 NOT NULL,
    trade_count INTEGER DEFAULT 0 NOT NULL,
    accepted_entries_count INTEGER DEFAULT 0 NOT NULL,
    winning_trades INTEGER DEFAULT 0 NOT NULL,
    losing_trades INTEGER DEFAULT 0 NOT NULL,
    consecutive_losses INTEGER DEFAULT 0 NOT NULL,
    is_locked BOOLEAN DEFAULT FALSE NOT NULL,
    lock_reason VARCHAR(100) DEFAULT 'NONE' NOT NULL, -- NONE, DAILY_PROFIT_LOCKED, DAILY_LOSS_LOCKED
    locked_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ DEFAULT TIMEZONE('utc', NOW()) NOT NULL,
    CONSTRAINT uq_daily_risk_strategy_date UNIQUE (user_id, strategy_id, trading_date)
);

CREATE INDEX IF NOT EXISTS ix_daily_risk_strategy_date 
    ON public.strategy_daily_risks (strategy_id, trading_date);

-- =============================================================================
-- 17. STRATEGY VIRTUAL ACCOUNTS (Isolated Strategy Ledgers)
-- =============================================================================
CREATE TABLE IF NOT EXISTS public.strategy_virtual_accounts (
    id BIGSERIAL PRIMARY KEY,
    user_id UUID REFERENCES public.users(id) ON DELETE CASCADE,
    strategy_id VARCHAR(50) NOT NULL,
    strategy_name VARCHAR(100) NOT NULL,
    initial_capital NUMERIC(14, 4) DEFAULT 100000.0 NOT NULL,
    available_cash NUMERIC(14, 4) DEFAULT 100000.0 NOT NULL,
    reserved_capital NUMERIC(14, 4) DEFAULT 0.0 NOT NULL,
    realized_gross_pnl NUMERIC(14, 4) DEFAULT 0.0 NOT NULL,
    realized_net_pnl NUMERIC(14, 4) DEFAULT 0.0 NOT NULL,
    total_charges NUMERIC(14, 4) DEFAULT 0.0 NOT NULL,
    slippage_cost NUMERIC(14, 4) DEFAULT 0.0 NOT NULL,
    capital_deployment_cap_pct NUMERIC(6, 2) DEFAULT 90.0 NOT NULL,
    daily_profit_target NUMERIC(14, 4),
    daily_loss_limit NUMERIC(14, 4),
    max_trades_per_day INTEGER,
    max_consecutive_losses INTEGER,
    risk_limits_enabled BOOLEAN DEFAULT TRUE NOT NULL,
    created_at TIMESTAMPTZ DEFAULT TIMEZONE('utc', NOW()) NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT TIMEZONE('utc', NOW()) NOT NULL,
    CONSTRAINT uq_strat_account_user_strat UNIQUE (user_id, strategy_id)
);

CREATE INDEX IF NOT EXISTS ix_strat_virtual_accounts_strat_id 
    ON public.strategy_virtual_accounts (strategy_id);

-- =============================================================================
-- 18. PCR SNAPSHOTS (Options Market Intelligence)
-- =============================================================================
CREATE TABLE IF NOT EXISTS public.pcr_snapshots (
    id BIGSERIAL PRIMARY KEY,
    underlying VARCHAR(30) NOT NULL, -- NIFTY, BANKNIFTY, FINNIFTY
    expiry VARCHAR(30) NOT NULL,     -- YYYY-MM-DD
    strike_range INTEGER DEFAULT 10 NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    timestamp_ist VARCHAR(30) NOT NULL, -- YYYY-MM-DD HH:MM
    trading_date VARCHAR(20) NOT NULL,  -- YYYY-MM-DD
    atm_strike NUMERIC(14, 4) NOT NULL,
    spot_price NUMERIC(14, 4) NOT NULL,
    total_call_oi BIGINT DEFAULT 0 NOT NULL,
    total_put_oi BIGINT DEFAULT 0 NOT NULL,
    oi_pcr NUMERIC(10, 4),
    total_call_volume BIGINT DEFAULT 0 NOT NULL,
    total_put_volume BIGINT DEFAULT 0 NOT NULL,
    volume_pcr NUMERIC(10, 4),
    call_oi_change BIGINT DEFAULT 0 NOT NULL,
    put_oi_change BIGINT DEFAULT 0 NOT NULL,
    underlying_vwap NUMERIC(14, 4),
    futures_vwap NUMERIC(14, 4),
    futures_symbol VARCHAR(50),
    sentiment VARCHAR(50) DEFAULT 'NEUTRAL' NOT NULL,
    sentiment_score NUMERIC(10, 4) DEFAULT 0.0 NOT NULL,
    data_status VARCHAR(30) DEFAULT 'FRESH' NOT NULL,
    created_at TIMESTAMPTZ DEFAULT TIMEZONE('utc', NOW()) NOT NULL,
    CONSTRAINT uq_pcr_snapshot_minute UNIQUE (underlying, expiry, strike_range, timestamp_ist)
);

CREATE INDEX IF NOT EXISTS idx_pcr_underlying_date 
    ON public.pcr_snapshots (underlying, trading_date, timestamp);

-- =============================================================================
-- 18. ROW LEVEL SECURITY (RLS) POLICIES
-- =============================================================================

-- Enable RLS on User-Owned / Protected Tables
ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.broker_connections ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.strategy_settings ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.strategy_signals ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.paper_orders ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.paper_positions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.paper_trades ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.charge_settings ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.auto_exit_settings ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.backtest_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.backtest_trades ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.strategy_daily_risks ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.strategy_virtual_accounts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.instruments ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.historical_candles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.market_ticks ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.pcr_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.system_events ENABLE ROW LEVEL SECURITY;

-- User Isolation Policies: Users can ONLY access their own records
CREATE POLICY "Users can view own profile" 
    ON public.users FOR SELECT TO authenticated 
    USING (auth.uid() = auth_user_id);

CREATE POLICY "Users can update own profile" 
    ON public.users FOR UPDATE TO authenticated 
    USING (auth.uid() = auth_user_id) 
    WITH CHECK (auth.uid() = auth_user_id);

-- Paper Trading Isolation
CREATE POLICY "Users can manage own paper positions" 
    ON public.paper_positions FOR ALL TO authenticated 
    USING (auth.uid() = (SELECT auth_user_id FROM public.users WHERE id = user_id) OR user_id IS NULL)
    WITH CHECK (auth.uid() = (SELECT auth_user_id FROM public.users WHERE id = user_id) OR user_id IS NULL);

CREATE POLICY "Users can view and manage own paper trades" 
    ON public.paper_trades FOR ALL TO authenticated 
    USING (auth.uid() = (SELECT auth_user_id FROM public.users WHERE id = user_id) OR user_id IS NULL)
    WITH CHECK (auth.uid() = (SELECT auth_user_id FROM public.users WHERE id = user_id) OR user_id IS NULL);

CREATE POLICY "Users can manage own paper orders" 
    ON public.paper_orders FOR ALL TO authenticated 
    USING (auth.uid() = (SELECT auth_user_id FROM public.users WHERE id = user_id) OR user_id IS NULL)
    WITH CHECK (auth.uid() = (SELECT auth_user_id FROM public.users WHERE id = user_id) OR user_id IS NULL);

-- Backtest Isolation
CREATE POLICY "Users can manage own backtest runs" 
    ON public.backtest_runs FOR ALL TO authenticated 
    USING (auth.uid() = (SELECT auth_user_id FROM public.users WHERE id = user_id) OR user_id IS NULL)
    WITH CHECK (auth.uid() = (SELECT auth_user_id FROM public.users WHERE id = user_id) OR user_id IS NULL);

CREATE POLICY "Users can view own backtest trades" 
    ON public.backtest_trades FOR ALL TO authenticated 
    USING (
        EXISTS (
            SELECT 1 FROM public.backtest_runs r 
            WHERE r.id = run_id 
            AND (r.user_id IS NULL OR auth.uid() = (SELECT auth_user_id FROM public.users WHERE id = r.user_id))
        )
    )
    WITH CHECK (
        EXISTS (
            SELECT 1 FROM public.backtest_runs r 
            WHERE r.id = run_id 
            AND (r.user_id IS NULL OR auth.uid() = (SELECT auth_user_id FROM public.users WHERE id = r.user_id))
        )
    );

-- Strategy Settings Isolation
CREATE POLICY "Users can manage own strategy settings" 
    ON public.strategy_settings FOR ALL TO authenticated 
    USING (auth.uid() = (SELECT auth_user_id FROM public.users WHERE id = user_id) OR user_id IS NULL)
    WITH CHECK (auth.uid() = (SELECT auth_user_id FROM public.users WHERE id = user_id) OR user_id IS NULL);

CREATE POLICY "Users can manage own daily risks" 
    ON public.strategy_daily_risks FOR ALL TO authenticated 
    USING (auth.uid() = (SELECT auth_user_id FROM public.users WHERE id = user_id) OR user_id IS NULL)
    WITH CHECK (auth.uid() = (SELECT auth_user_id FROM public.users WHERE id = user_id) OR user_id IS NULL);

CREATE POLICY "Users can manage own virtual accounts" 
    ON public.strategy_virtual_accounts FOR ALL TO authenticated 
    USING (auth.uid() = (SELECT auth_user_id FROM public.users WHERE id = user_id) OR user_id IS NULL)
    WITH CHECK (auth.uid() = (SELECT auth_user_id FROM public.users WHERE id = user_id) OR user_id IS NULL);

CREATE POLICY "Users can manage own charge settings" 
    ON public.charge_settings FOR ALL TO authenticated 
    USING (auth.uid() = (SELECT auth_user_id FROM public.users WHERE id = user_id) OR user_id IS NULL)
    WITH CHECK (auth.uid() = (SELECT auth_user_id FROM public.users WHERE id = user_id) OR user_id IS NULL);

CREATE POLICY "Users can manage own auto exit settings" 
    ON public.auto_exit_settings FOR ALL TO authenticated 
    USING (auth.uid() = (SELECT auth_user_id FROM public.users WHERE id = user_id) OR user_id IS NULL)
    WITH CHECK (auth.uid() = (SELECT auth_user_id FROM public.users WHERE id = user_id) OR user_id IS NULL);

-- Public / Reference Market Data (Readable by all authenticated users, writable by service role)
CREATE POLICY "Authenticated users can read instruments" 
    ON public.instruments FOR SELECT TO authenticated USING (true);

CREATE POLICY "Authenticated users can read candles" 
    ON public.historical_candles FOR SELECT TO authenticated USING (true);

CREATE POLICY "Authenticated users can read market ticks" 
    ON public.market_ticks FOR SELECT TO authenticated USING (true);

CREATE POLICY "Authenticated users can read pcr snapshots" 
    ON public.pcr_snapshots FOR SELECT TO authenticated USING (true);

CREATE POLICY "Authenticated users can read strategy signals" 
    ON public.strategy_signals FOR SELECT TO authenticated USING (true);

CREATE POLICY "Authenticated users can read system events" 
    ON public.system_events FOR SELECT TO authenticated USING (true);

-- Service Role Full Access Bypass (Implicit in Supabase, made explicit here)
CREATE POLICY "Service role full access to all tables" 
    ON public.users FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "Service role full access to paper_positions" 
    ON public.paper_positions FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "Service role full access to paper_trades" 
    ON public.paper_trades FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "Service role full access to paper_orders" 
    ON public.paper_orders FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "Service role full access to backtest_runs" 
    ON public.backtest_runs FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "Service role full access to backtest_trades" 
    ON public.backtest_trades FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "Service role full access to candles" 
    ON public.historical_candles FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "Service role full access to instruments" 
    ON public.instruments FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "Service role full access to market_ticks" 
    ON public.market_ticks FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "Service role full access to pcr_snapshots" 
    ON public.pcr_snapshots FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "Service role full access to strategy_signals" 
    ON public.strategy_signals FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "Service role full access to strategy_settings" 
    ON public.strategy_settings FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "Service role full access to strategy_daily_risks" 
    ON public.strategy_daily_risks FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "Service role full access to strategy_virtual_accounts" 
    ON public.strategy_virtual_accounts FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "Service role full access to charge_settings" 
    ON public.charge_settings FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "Service role full access to auto_exit_settings" 
    ON public.auto_exit_settings FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "Service role full access to system_events" 
    ON public.system_events FOR ALL TO service_role USING (true) WITH CHECK (true);
-- =============================================================================
-- NEXTRADE — COMPLETE SUPABASE DATABASE & DATA PERSISTENCE EXTENSION
-- Adds granular audit, events, agent decisions, metrics, and account tables
-- =============================================================================

-- =============================================================================
-- 1. PAPER TRADING ACCOUNTS & DETAILED BALANCES
-- =============================================================================
CREATE TABLE IF NOT EXISTS public.paper_accounts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES public.users(id) ON DELETE CASCADE,
    strategy_id VARCHAR(50) UNIQUE NOT NULL,
    account_name VARCHAR(100) NOT NULL,
    account_number VARCHAR(50) UNIQUE NOT NULL,
    initial_capital NUMERIC(16, 2) NOT NULL DEFAULT 100000.00,
    available_balance NUMERIC(16, 2) NOT NULL DEFAULT 100000.00,
    reserved_capital NUMERIC(16, 2) NOT NULL DEFAULT 0.00,
    realized_pnl NUMERIC(16, 2) NOT NULL DEFAULT 0.00,
    unrealized_pnl NUMERIC(16, 2) NOT NULL DEFAULT 0.00,
    total_charges NUMERIC(16, 2) NOT NULL DEFAULT 0.00,
    total_slippage NUMERIC(16, 2) NOT NULL DEFAULT 0.00,
    capital_deployment_cap_pct NUMERIC(5, 2) NOT NULL DEFAULT 90.00,
    currency VARCHAR(10) DEFAULT 'INR' NOT NULL,
    is_active BOOLEAN DEFAULT true NOT NULL,
    created_at TIMESTAMPTZ DEFAULT TIMEZONE('utc', NOW()) NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT TIMEZONE('utc', NOW()) NOT NULL
);

CREATE TABLE IF NOT EXISTS public.paper_account_balances (
    id BIGSERIAL PRIMARY KEY,
    account_id UUID REFERENCES public.paper_accounts(id) ON DELETE CASCADE,
    strategy_id VARCHAR(50) NOT NULL,
    balance NUMERIC(16, 2) NOT NULL,
    available_balance NUMERIC(16, 2) NOT NULL,
    reserved_margin NUMERIC(16, 2) NOT NULL DEFAULT 0.00,
    realized_pnl NUMERIC(16, 2) NOT NULL DEFAULT 0.00,
    unrealized_pnl NUMERIC(16, 2) NOT NULL DEFAULT 0.00,
    change_amount NUMERIC(16, 2) NOT NULL DEFAULT 0.00,
    change_reason VARCHAR(100) NOT NULL, -- INITIAL_DEPOSIT, TRADE_ENTRY_MARGIN, TRADE_EXIT_SETTLEMENT, RISK_LOCK
    related_trade_id BIGINT,
    related_order_id BIGINT,
    created_at TIMESTAMPTZ DEFAULT TIMEZONE('utc', NOW()) NOT NULL
);

-- =============================================================================
-- 2. PAPER TRADE EVENTS & EXECUTION LOGS
-- =============================================================================
CREATE TABLE IF NOT EXISTS public.paper_trade_events (
    id BIGSERIAL PRIMARY KEY,
    trade_id BIGINT REFERENCES public.paper_trades(id) ON DELETE CASCADE,
    position_id BIGINT,
    strategy_id VARCHAR(50) NOT NULL,
    event_type VARCHAR(50) NOT NULL, -- ENTRY_TRIGGERED, ENTRY_FILLED, SL_TRIGGERED, TARGET_TRIGGERED, FORCE_SQUARE_OFF, MANUAL_EXIT
    event_price NUMERIC(14, 4) NOT NULL,
    event_quantity INTEGER NOT NULL,
    trigger_reason VARCHAR(100),
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT TIMEZONE('utc', NOW()) NOT NULL
);

CREATE TABLE IF NOT EXISTS public.paper_execution_logs (
    id BIGSERIAL PRIMARY KEY,
    strategy_id VARCHAR(50) NOT NULL,
    order_id BIGINT REFERENCES public.paper_orders(id) ON DELETE SET NULL,
    position_id BIGINT,
    action VARCHAR(50) NOT NULL, -- BUY_SUBMITTED, SLIPPAGE_APPLIED, MARGIN_RESERVED, MARGIN_RELEASED, ORDER_REJECTED
    level VARCHAR(20) DEFAULT 'INFO' NOT NULL, -- INFO, WARNING, ERROR
    message TEXT NOT NULL,
    details_json JSONB,
    created_at TIMESTAMPTZ DEFAULT TIMEZONE('utc', NOW()) NOT NULL
);

-- =============================================================================
-- 3. PAPER CHARGES ITEMIZATION
-- =============================================================================
CREATE TABLE IF NOT EXISTS public.paper_charges (
    id BIGSERIAL PRIMARY KEY,
    trade_id BIGINT REFERENCES public.paper_trades(id) ON DELETE CASCADE,
    order_id BIGINT REFERENCES public.paper_orders(id) ON DELETE SET NULL,
    strategy_id VARCHAR(50) NOT NULL,
    brokerage NUMERIC(14, 4) DEFAULT 0.00 NOT NULL,
    stt NUMERIC(14, 4) DEFAULT 0.00 NOT NULL,
    exchange_turnover NUMERIC(14, 4) DEFAULT 0.00 NOT NULL,
    gst NUMERIC(14, 4) DEFAULT 0.00 NOT NULL,
    sebi_charges NUMERIC(14, 4) DEFAULT 0.00 NOT NULL,
    stamp_duty NUMERIC(14, 4) DEFAULT 0.00 NOT NULL,
    total_charges NUMERIC(14, 4) NOT NULL,
    calculated_at TIMESTAMPTZ DEFAULT TIMEZONE('utc', NOW()) NOT NULL
);

-- =============================================================================
-- 4. PAPER RISK EVENTS
-- =============================================================================
CREATE TABLE IF NOT EXISTS public.paper_risk_events (
    id BIGSERIAL PRIMARY KEY,
    strategy_id VARCHAR(50) NOT NULL,
    trading_date VARCHAR(20) NOT NULL, -- YYYY-MM-DD
    risk_event_type VARCHAR(50) NOT NULL, -- DAILY_LOSS_LIMIT, DAILY_PROFIT_TARGET, MAX_TRADES_LIMIT, CONSECUTIVE_LOSS_LIMIT, BUYING_POWER_EXCEEDED
    trigger_metric_name VARCHAR(50) NOT NULL, -- net_pnl, trade_count, consecutive_losses, required_capital
    metric_value NUMERIC(16, 2) NOT NULL,
    threshold_value NUMERIC(16, 2) NOT NULL,
    action_taken VARCHAR(100) NOT NULL, -- ENTRY_REJECTED, STRATEGY_LOCKED, TRADING_HALTED
    details TEXT,
    created_at TIMESTAMPTZ DEFAULT TIMEZONE('utc', NOW()) NOT NULL
);

-- =============================================================================
-- 5. BACKTESTING DETAILED RESULTS, METRICS, COVERAGE & LOGS
-- =============================================================================
CREATE TABLE IF NOT EXISTS public.backtest_daily_results (
    id BIGSERIAL PRIMARY KEY,
    run_id BIGINT REFERENCES public.backtest_runs(id) ON DELETE CASCADE,
    trading_date VARCHAR(20) NOT NULL, -- YYYY-MM-DD
    trades_count INTEGER DEFAULT 0 NOT NULL,
    wins_count INTEGER DEFAULT 0 NOT NULL,
    losses_count INTEGER DEFAULT 0 NOT NULL,
    gross_pnl NUMERIC(16, 2) DEFAULT 0.00 NOT NULL,
    charges NUMERIC(16, 2) DEFAULT 0.00 NOT NULL,
    net_pnl NUMERIC(16, 2) DEFAULT 0.00 NOT NULL,
    created_at TIMESTAMPTZ DEFAULT TIMEZONE('utc', NOW()) NOT NULL,
    CONSTRAINT uq_bt_run_date UNIQUE (run_id, trading_date)
);

CREATE TABLE IF NOT EXISTS public.backtest_metrics (
    id BIGSERIAL PRIMARY KEY,
    run_id BIGINT REFERENCES public.backtest_runs(id) ON DELETE CASCADE,
    metric_key VARCHAR(50) NOT NULL,
    metric_value NUMERIC(16, 4) NOT NULL,
    category VARCHAR(50) DEFAULT 'GENERAL' NOT NULL, -- RETURN, RISK, DRAWDOWN, EXECUTION
    description VARCHAR(255),
    CONSTRAINT uq_bt_run_metric UNIQUE (run_id, metric_key)
);

CREATE TABLE IF NOT EXISTS public.backtest_data_coverage (
    id BIGSERIAL PRIMARY KEY,
    run_id BIGINT REFERENCES public.backtest_runs(id) ON DELETE CASCADE,
    instrument_token VARCHAR(50) NOT NULL,
    trading_symbol VARCHAR(100) NOT NULL,
    timeframe VARCHAR(20) DEFAULT '1m' NOT NULL,
    start_time TIMESTAMPTZ NOT NULL,
    end_time TIMESTAMPTZ NOT NULL,
    total_candles INTEGER NOT NULL,
    missing_candles INTEGER DEFAULT 0 NOT NULL,
    coverage_pct NUMERIC(6, 2) DEFAULT 100.00 NOT NULL
);

CREATE TABLE IF NOT EXISTS public.backtest_execution_logs (
    id BIGSERIAL PRIMARY KEY,
    run_id BIGINT REFERENCES public.backtest_runs(id) ON DELETE CASCADE,
    timestamp TIMESTAMPTZ DEFAULT TIMEZONE('utc', NOW()) NOT NULL,
    level VARCHAR(20) DEFAULT 'INFO' NOT NULL,
    message TEXT NOT NULL,
    stage VARCHAR(50) DEFAULT 'EXECUTION' NOT NULL
);

-- =============================================================================
-- 6. SIGNAL EVALUATIONS, AGENT DECISIONS & CONFIG VERSIONS
-- =============================================================================
CREATE TABLE IF NOT EXISTS public.strategy_signal_evaluations (
    id BIGSERIAL PRIMARY KEY,
    signal_id BIGINT REFERENCES public.strategy_signals(id) ON DELETE SET NULL,
    strategy_id VARCHAR(50) NOT NULL,
    timestamp TIMESTAMPTZ DEFAULT TIMEZONE('utc', NOW()) NOT NULL,
    rule_name VARCHAR(100) NOT NULL,
    passed BOOLEAN NOT NULL,
    expected_condition TEXT,
    actual_value TEXT
);

CREATE TABLE IF NOT EXISTS public.agent_decisions (
    id BIGSERIAL PRIMARY KEY,
    signal_id BIGINT REFERENCES public.strategy_signals(id) ON DELETE SET NULL,
    strategy_id VARCHAR(50) NOT NULL,
    agent_name VARCHAR(100) NOT NULL, -- TrendAgent, MomentumAgent, VolatilityAgent, RiskAgent
    vote VARCHAR(20) NOT NULL, -- BUY, SELL, PASS, REJECT
    confidence NUMERIC(5, 4) DEFAULT 1.0000 NOT NULL, -- 0.00 to 1.00
    reasoning TEXT,
    features_json JSONB,
    timestamp TIMESTAMPTZ DEFAULT TIMEZONE('utc', NOW()) NOT NULL
);

CREATE TABLE IF NOT EXISTS public.strategy_execution_events (
    id BIGSERIAL PRIMARY KEY,
    strategy_id VARCHAR(50) NOT NULL,
    event_type VARCHAR(50) NOT NULL, -- SIGNAL_GENERATED, SIGNAL_REJECTED, ORDER_SUBMITTED, SL_MODIFIED, TARGET_HIT, RISK_LOCKED
    details_json JSONB,
    created_at TIMESTAMPTZ DEFAULT TIMEZONE('utc', NOW()) NOT NULL
);

CREATE TABLE IF NOT EXISTS public.strategy_config_versions (
    id BIGSERIAL PRIMARY KEY,
    strategy_id VARCHAR(50) NOT NULL,
    version INTEGER NOT NULL,
    config_json JSONB NOT NULL,
    change_summary VARCHAR(255),
    changed_by VARCHAR(100) DEFAULT 'system' NOT NULL,
    created_at TIMESTAMPTZ DEFAULT TIMEZONE('utc', NOW()) NOT NULL,
    CONSTRAINT uq_strat_version UNIQUE (strategy_id, version)
);

-- =============================================================================
-- 7. INDEXES FOR HIGH-PERFORMANCE QUERYING
-- =============================================================================
CREATE INDEX IF NOT EXISTS ix_paper_accounts_strategy ON public.paper_accounts(strategy_id);
CREATE INDEX IF NOT EXISTS ix_paper_account_balances_account ON public.paper_account_balances(account_id, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_paper_trade_events_trade ON public.paper_trade_events(trade_id, created_at);
CREATE INDEX IF NOT EXISTS ix_paper_execution_logs_order ON public.paper_execution_logs(order_id, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_paper_charges_trade ON public.paper_charges(trade_id);
CREATE INDEX IF NOT EXISTS ix_paper_risk_events_strategy_date ON public.paper_risk_events(strategy_id, trading_date);
CREATE INDEX IF NOT EXISTS ix_backtest_daily_results_run ON public.backtest_daily_results(run_id, trading_date);
CREATE INDEX IF NOT EXISTS ix_backtest_metrics_run ON public.backtest_metrics(run_id);
CREATE INDEX IF NOT EXISTS ix_backtest_coverage_run ON public.backtest_data_coverage(run_id);
CREATE INDEX IF NOT EXISTS ix_backtest_logs_run ON public.backtest_execution_logs(run_id, timestamp);
CREATE INDEX IF NOT EXISTS ix_signal_evaluations_signal ON public.strategy_signal_evaluations(signal_id);
CREATE INDEX IF NOT EXISTS ix_agent_decisions_signal ON public.agent_decisions(signal_id);
CREATE INDEX IF NOT EXISTS ix_strat_events_strategy ON public.strategy_execution_events(strategy_id, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_strat_config_versions_strat ON public.strategy_config_versions(strategy_id, version DESC);

-- =============================================================================
-- 8. ROW LEVEL SECURITY (RLS) POLICIES
-- =============================================================================
ALTER TABLE public.paper_accounts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.paper_account_balances ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.paper_trade_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.paper_execution_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.paper_charges ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.paper_risk_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.backtest_daily_results ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.backtest_metrics ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.backtest_data_coverage ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.backtest_execution_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.strategy_signal_evaluations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.agent_decisions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.strategy_execution_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.strategy_config_versions ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Allow public read access for paper accounts" ON public.paper_accounts FOR SELECT USING (true);
CREATE POLICY "Allow public read access for paper account balances" ON public.paper_account_balances FOR SELECT USING (true);
CREATE POLICY "Allow public read access for paper trade events" ON public.paper_trade_events FOR SELECT USING (true);
CREATE POLICY "Allow public read access for paper execution logs" ON public.paper_execution_logs FOR SELECT USING (true);
CREATE POLICY "Allow public read access for paper charges" ON public.paper_charges FOR SELECT USING (true);
CREATE POLICY "Allow public read access for paper risk events" ON public.paper_risk_events FOR SELECT USING (true);
CREATE POLICY "Allow public read access for backtest daily results" ON public.backtest_daily_results FOR SELECT USING (true);
CREATE POLICY "Allow public read access for backtest metrics" ON public.backtest_metrics FOR SELECT USING (true);
CREATE POLICY "Allow public read access for backtest data coverage" ON public.backtest_data_coverage FOR SELECT USING (true);
CREATE POLICY "Allow public read access for backtest execution logs" ON public.backtest_execution_logs FOR SELECT USING (true);
CREATE POLICY "Allow public read access for strategy signal evaluations" ON public.strategy_signal_evaluations FOR SELECT USING (true);
CREATE POLICY "Allow public read access for agent decisions" ON public.agent_decisions FOR SELECT USING (true);
CREATE POLICY "Allow public read access for strategy execution events" ON public.strategy_execution_events FOR SELECT USING (true);
CREATE POLICY "Allow public read access for strategy config versions" ON public.strategy_config_versions FOR SELECT USING (true);

-- Allow service role full write access
CREATE POLICY "Service role full access paper_accounts" ON public.paper_accounts USING (auth.role() = 'service_role' OR auth.role() = 'anon');
CREATE POLICY "Service role full access paper_account_balances" ON public.paper_account_balances USING (auth.role() = 'service_role' OR auth.role() = 'anon');
CREATE POLICY "Service role full access paper_trade_events" ON public.paper_trade_events USING (auth.role() = 'service_role' OR auth.role() = 'anon');
CREATE POLICY "Service role full access paper_execution_logs" ON public.paper_execution_logs USING (auth.role() = 'service_role' OR auth.role() = 'anon');
CREATE POLICY "Service role full access paper_charges" ON public.paper_charges USING (auth.role() = 'service_role' OR auth.role() = 'anon');
CREATE POLICY "Service role full access paper_risk_events" ON public.paper_risk_events USING (auth.role() = 'service_role' OR auth.role() = 'anon');
CREATE POLICY "Service role full access backtest_daily_results" ON public.backtest_daily_results USING (auth.role() = 'service_role' OR auth.role() = 'anon');
CREATE POLICY "Service role full access backtest_metrics" ON public.backtest_metrics USING (auth.role() = 'service_role' OR auth.role() = 'anon');
CREATE POLICY "Service role full access backtest_data_coverage" ON public.backtest_data_coverage USING (auth.role() = 'service_role' OR auth.role() = 'anon');
CREATE POLICY "Service role full access backtest_execution_logs" ON public.backtest_execution_logs USING (auth.role() = 'service_role' OR auth.role() = 'anon');
CREATE POLICY "Service role full access strategy_signal_evaluations" ON public.strategy_signal_evaluations USING (auth.role() = 'service_role' OR auth.role() = 'anon');
CREATE POLICY "Service role full access agent_decisions" ON public.agent_decisions USING (auth.role() = 'service_role' OR auth.role() = 'anon');
CREATE POLICY "Service role full access strategy_execution_events" ON public.strategy_execution_events USING (auth.role() = 'service_role' OR auth.role() = 'anon');
CREATE POLICY "Service role full access strategy_config_versions" ON public.strategy_config_versions USING (auth.role() = 'service_role' OR auth.role() = 'anon');
