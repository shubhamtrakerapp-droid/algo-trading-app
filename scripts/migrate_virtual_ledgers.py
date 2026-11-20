"""
Migration script for NEXTRADE Strategy-Isolated Virtual Ledgers.
Safely creates strategy_virtual_accounts table, updates strategy_daily_risks schema,
and reconciles all initial balances and historical P&L from paper_trades.
Does NOT modify or delete any historical trades.
"""
import sqlite3
import logging
from datetime import datetime, timezone

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("nextrade.migration")

def migrate_db(db_path: str = "nextrade.db"):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    logger.info(f"Opening database {db_path} for virtual ledger migration...")

    # 1. Create strategy_virtual_accounts table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS strategy_virtual_accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            strategy_id VARCHAR(50) UNIQUE NOT NULL,
            strategy_name VARCHAR(100) NOT NULL,
            initial_capital FLOAT NOT NULL DEFAULT 100000.0,
            available_cash FLOAT NOT NULL DEFAULT 100000.0,
            reserved_capital FLOAT NOT NULL DEFAULT 0.0,
            realized_gross_pnl FLOAT NOT NULL DEFAULT 0.0,
            realized_net_pnl FLOAT NOT NULL DEFAULT 0.0,
            total_charges FLOAT NOT NULL DEFAULT 0.0,
            slippage_cost FLOAT NOT NULL DEFAULT 0.0,
            capital_deployment_cap_pct FLOAT NOT NULL DEFAULT 90.0,
            daily_profit_target FLOAT,
            daily_loss_limit FLOAT,
            max_trades_per_day INTEGER,
            max_consecutive_losses INTEGER,
            risk_limits_enabled BOOLEAN NOT NULL DEFAULT 1,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_strat_account_id ON strategy_virtual_accounts(strategy_id)")

    # 2. Add columns to strategy_daily_risks if not existing
    cursor.execute("PRAGMA table_info(strategy_daily_risks)")
    existing_risk_cols = [r[1] for r in cursor.fetchall()]
    if "accepted_entries_count" not in existing_risk_cols:
        logger.info("Adding accepted_entries_count column to strategy_daily_risks...")
        cursor.execute("ALTER TABLE strategy_daily_risks ADD COLUMN accepted_entries_count INTEGER DEFAULT 0 NOT NULL")
    if "consecutive_losses" not in existing_risk_cols:
        logger.info("Adding consecutive_losses column to strategy_daily_risks...")
        cursor.execute("ALTER TABLE strategy_daily_risks ADD COLUMN consecutive_losses INTEGER DEFAULT 0 NOT NULL")

    # 3. Reconcile historical trades for each strategy
    strategies_config = [
        {
            "strategy_id": "UT_BOT",
            "strategy_name": "UT Bot ATM Option Strategy",
            "initial_capital": 100000.0,
            "capital_deployment_cap_pct": 90.0,
            "daily_profit_target": None,
            "daily_loss_limit": None,
            "max_trades_per_day": None,
            "max_consecutive_losses": None,
            "risk_limits_enabled": 0,  # Disabled by default per user approval
        },
        {
            "strategy_id": "AI_MICRO_SCALPER_V1",
            "strategy_name": "NEXTRADE AI MICRO-SCALPER V1",
            "initial_capital": 20000.0,
            "capital_deployment_cap_pct": 90.0,
            "daily_profit_target": 500.0,
            "daily_loss_limit": -500.0,
            "max_trades_per_day": 5,
            "max_consecutive_losses": 2,
            "risk_limits_enabled": 1,
        },
        {
            "strategy_id": "SUPERTREND_EMA",
            "strategy_name": "Supertrend + EMA Scalper",
            "initial_capital": 50000.0,
            "capital_deployment_cap_pct": 90.0,
            "daily_profit_target": 1000.0,
            "daily_loss_limit": -2000.0,
            "max_trades_per_day": 10,
            "max_consecutive_losses": 3,
            "risk_limits_enabled": 1,
        },
        {
            "strategy_id": "SUPERTREND_EMA_SCALPER",
            "strategy_name": "Supertrend + EMA Scalper (Alias)",
            "initial_capital": 50000.0,
            "capital_deployment_cap_pct": 90.0,
            "daily_profit_target": 1000.0,
            "daily_loss_limit": -2000.0,
            "max_trades_per_day": 10,
            "max_consecutive_losses": 3,
            "risk_limits_enabled": 1,
        },
    ]

    now_iso = datetime.now(timezone.utc).isoformat()

    for sc in strategies_config:
        strat_id = sc["strategy_id"]
        # Query trade sums from paper_trades
        cursor.execute("""
            SELECT 
                COUNT(*) as count,
                COALESCE(SUM(gross_pnl), 0.0) as gross,
                COALESCE(SUM(total_charges), 0.0) as charges,
                COALESCE(SUM(net_pnl), 0.0) as net,
                COALESCE(SUM(slippage_cost), 0.0) as slippage
            FROM paper_trades
            WHERE strategy_id = ?
        """, (strat_id,))
        stats = dict(cursor.fetchone())

        gross_pnl = round(float(stats["gross"]), 2)
        charges = round(float(stats["charges"]), 2)
        net_pnl = round(float(stats["net"]), 2)
        slippage = round(float(stats["slippage"]), 2)
        initial_cap = float(sc["initial_capital"])
        available_cash = round(initial_cap + net_pnl, 2)

        cursor.execute("""
            INSERT INTO strategy_virtual_accounts (
                strategy_id, strategy_name, initial_capital, available_cash, reserved_capital,
                realized_gross_pnl, realized_net_pnl, total_charges, slippage_cost,
                capital_deployment_cap_pct, daily_profit_target, daily_loss_limit,
                max_trades_per_day, max_consecutive_losses, risk_limits_enabled,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, 0.0, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(strategy_id) DO UPDATE SET
                strategy_name=excluded.strategy_name,
                initial_capital=excluded.initial_capital,
                available_cash=excluded.available_cash,
                realized_gross_pnl=excluded.realized_gross_pnl,
                realized_net_pnl=excluded.realized_net_pnl,
                total_charges=excluded.total_charges,
                slippage_cost=excluded.slippage_cost,
                capital_deployment_cap_pct=excluded.capital_deployment_cap_pct,
                daily_profit_target=excluded.daily_profit_target,
                daily_loss_limit=excluded.daily_loss_limit,
                max_trades_per_day=excluded.max_trades_per_day,
                max_consecutive_losses=excluded.max_consecutive_losses,
                risk_limits_enabled=excluded.risk_limits_enabled,
                updated_at=excluded.updated_at
        """, (
            strat_id,
            sc["strategy_name"],
            initial_cap,
            available_cash,
            gross_pnl,
            net_pnl,
            charges,
            slippage,
            sc["capital_deployment_cap_pct"],
            sc["daily_profit_target"],
            sc["daily_loss_limit"],
            sc["max_trades_per_day"],
            sc["max_consecutive_losses"],
            sc["risk_limits_enabled"],
            now_iso,
            now_iso
        ))

        logger.info(
            f"Strategy Ledger '{strat_id}': Initial ₹{initial_cap}, "
            f"Net P&L ₹{net_pnl} ({stats['count']} trades), Available Cash ₹{available_cash}"
        )

    conn.commit()
    conn.close()
    logger.info("Virtual ledger migration completed successfully!")

if __name__ == "__main__":
    migrate_db()
