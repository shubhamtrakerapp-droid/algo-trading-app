-- =============================================================================
-- NEXTRADE — SUPABASE INITIAL SEED CONFIGURATION
-- Seeds default system parameters if not already present
-- =============================================================================

-- 1. Default Charge Settings (₹10 entry, ₹10 exit = ₹20 roundtrip per order)
INSERT INTO public.charge_settings (id, entry_charge_per_order, exit_charge_per_order, updated_at)
VALUES (1, 10.0, 10.0, TIMEZONE('utc', NOW()))
ON CONFLICT (id) DO UPDATE 
SET entry_charge_per_order = EXCLUDED.entry_charge_per_order,
    exit_charge_per_order = EXCLUDED.exit_charge_per_order,
    updated_at = TIMEZONE('utc', NOW());

-- 2. Default Auto-Exit Setting (15:20 IST mandatory square-off)
INSERT INTO public.auto_exit_settings (
    id, enabled, auto_close_time, apply_to_all_strategies, 
    close_profitable, close_losing, last_status, updated_at
)
VALUES (
    1, TRUE, '15:20', TRUE, 
    TRUE, TRUE, 'STANDBY: Scheduled for 03:20 PM IST', TIMEZONE('utc', NOW())
)
ON CONFLICT (id) DO UPDATE
SET auto_close_time = EXCLUDED.auto_close_time,
    enabled = EXCLUDED.enabled,
    updated_at = TIMEZONE('utc', NOW());

-- 3. Default Strategy Setting: AI MICRO-SCALPER V1
INSERT INTO public.strategy_settings (
    id, strategy_id, name, underlying, timeframe,
    ema_fast, ema_medium, ema_slow, rsi_period, rsi_threshold,
    session_start_ist, session_end_ist, force_exit_ist,
    target_points, stop_points, max_loss_per_trade,
    default_lots, lot_size, is_active, config_json, updated_at
)
VALUES (
    1, 'AI_MICRO_SCALPER_V1', 'NEXTRADE AI MICRO-SCALPER V1', 'NIFTY', '1m',
    9, 21, 50, 14, 50.0,
    '09:20', '15:15', '15:20',
    4.0, 2.0, 1000.0,
    1, 65, TRUE,
    '{"capital": 100000.0, "daily_profit_target": 1000.0, "daily_loss_limit": -2000.0, "max_trades_per_day": 8, "execution_mode": "REALISTIC"}'::jsonb,
    TIMEZONE('utc', NOW())
)
ON CONFLICT (id) DO UPDATE
SET is_active = EXCLUDED.is_active,
    updated_at = TIMEZONE('utc', NOW());

-- 4. Initial Strategy Virtual Accounts
INSERT INTO public.strategy_virtual_accounts (
    strategy_id, strategy_name, initial_capital, available_cash, reserved_capital,
    capital_deployment_cap_pct, daily_profit_target, daily_loss_limit,
    max_trades_per_day, max_consecutive_losses, risk_limits_enabled, updated_at
)
VALUES 
('UT_BOT', 'UT Bot ATM Option Strategy', 100000.0, 100000.0, 0.0, 90.0, NULL, NULL, NULL, NULL, FALSE, TIMEZONE('utc', NOW())),
('AI_MICRO_SCALPER_V1', 'NEXTRADE AI MICRO-SCALPER V1', 20000.0, 20000.0, 0.0, 90.0, 500.0, -500.0, 5, 2, TRUE, TIMEZONE('utc', NOW())),
('SUPERTREND_EMA', 'Supertrend + EMA Scalper', 50000.0, 50000.0, 0.0, 90.0, 1000.0, -2000.0, 10, 3, TRUE, TIMEZONE('utc', NOW())),
('SUPERTREND_EMA_SCALPER', 'Supertrend + EMA Scalper (Alias)', 50000.0, 50000.0, 0.0, 90.0, 1000.0, -2000.0, 10, 3, TRUE, TIMEZONE('utc', NOW()))
ON CONFLICT (user_id, strategy_id) DO NOTHING;
