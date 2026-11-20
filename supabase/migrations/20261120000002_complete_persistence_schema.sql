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
