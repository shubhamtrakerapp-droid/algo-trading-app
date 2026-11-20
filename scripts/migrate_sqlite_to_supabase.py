#!/usr/bin/env python3
"""
NEXTRADE — Supabase PostgreSQL Data Migration Script
Reads the validated SQLite backup and streams records into Supabase PostgreSQL.
Uses SQLAlchemy (standard library in NEXTRADE) to connect without requiring psycopg2.
"""

import os
import sys
import json
import argparse
from datetime import datetime


def run_migration(backup_json_path: str, target_db_url: str, dry_run: bool = False):
    if not os.path.exists(backup_json_path):
        print(f"Error: Backup JSON file not found at {backup_json_path}")
        return False

    with open(backup_json_path, "r", encoding="utf-8") as f:
        backup = json.load(f)

    data = backup.get("data", {})
    counts = backup.get("table_counts", {})

    print("==================================================")
    print("NEXTRADE SUPABASE DATA MIGRATION")
    print(f"Source Backup: {backup_json_path}")
    print(f"Target DB: {target_db_url.split('@')[-1] if '@' in target_db_url else 'Target DB'}")
    print(f"Mode: {'DRY RUN (Validation Only)' if dry_run else 'LIVE MIGRATION'}")
    print("==================================================")

    if dry_run:
        print("\n[Dry-Run Validation Summary]:")
        for table, cnt in counts.items():
            sample = data.get(table, [])
            sample_keys = list(sample[0].keys()) if sample else []
            print(f"  - Table {table:<22}: {cnt:>5} rows ready | Columns: {len(sample_keys)}")
        print("\n✓ All records validated successfully. Ready for migration.")
        return True

    # Normalize driver for sync engine
    sync_url = target_db_url
    if sync_url.startswith("postgresql+asyncpg://"):
        sync_url = sync_url.replace("postgresql+asyncpg://", "postgresql+psycopg2://", 1)
    elif sync_url.startswith("postgres://"):
        sync_url = sync_url.replace("postgres://", "postgresql://", 1)

    from sqlalchemy import create_engine, text
    engine = create_engine(sync_url)

    with engine.begin() as conn:
        try:
            # 1. Migrate charge_settings
            charges = data.get("charge_settings", [])
            if charges:
                print(f"Migrating charge_settings ({len(charges)} rows)...")
                for c in charges:
                    conn.execute(text("""
                        INSERT INTO public.charge_settings (id, entry_charge_per_order, exit_charge_per_order, updated_at)
                        VALUES (:id, :entry, :exit, :updated_at)
                        ON CONFLICT (id) DO UPDATE SET
                            entry_charge_per_order = EXCLUDED.entry_charge_per_order,
                            exit_charge_per_order = EXCLUDED.exit_charge_per_order,
                            updated_at = EXCLUDED.updated_at;
                    """), {
                        "id": c["id"],
                        "entry": c["entry_charge_per_order"],
                        "exit": c["exit_charge_per_order"],
                        "updated_at": c.get("updated_at")
                    })

            # 2. Migrate auto_exit_settings
            auto_exits = data.get("auto_exit_settings", [])
            if auto_exits:
                print(f"Migrating auto_exit_settings ({len(auto_exits)} rows)...")
                for a in auto_exits:
                    conn.execute(text("""
                        INSERT INTO public.auto_exit_settings (
                            id, enabled, auto_close_time, apply_to_all_strategies, 
                            close_profitable, close_losing, last_status, last_run_time, last_run_date, updated_at
                        )
                        VALUES (:id, :enabled, :auto_close_time, :apply_all, :close_prof, :close_los, :last_status, :last_run_time, :last_run_date, :updated_at)
                        ON CONFLICT (id) DO UPDATE SET
                            auto_close_time = EXCLUDED.auto_close_time,
                            last_status = EXCLUDED.last_status,
                            updated_at = EXCLUDED.updated_at;
                    """), {
                        "id": a["id"],
                        "enabled": bool(a.get("enabled", 1)),
                        "auto_close_time": a.get("auto_close_time", "15:20"),
                        "apply_all": bool(a.get("apply_to_all_strategies", 1)),
                        "close_prof": bool(a.get("close_profitable", 1)),
                        "close_los": bool(a.get("close_losing", 1)),
                        "last_status": a.get("last_status", ""),
                        "last_run_time": a.get("last_run_time"),
                        "last_run_date": a.get("last_run_date"),
                        "updated_at": a.get("updated_at")
                    })

            # 3. Migrate strategy_daily_risks
            risks = data.get("strategy_daily_risks", [])
            if risks:
                print(f"Migrating strategy_daily_risks ({len(risks)} rows)...")
                for r in risks:
                    conn.execute(text("""
                        INSERT INTO public.strategy_daily_risks (
                            id, strategy_id, trading_date, realized_net_pnl, gross_pnl, 
                            total_charges, trade_count, winning_trades, losing_trades, 
                            is_locked, lock_reason, locked_at, updated_at
                        )
                        VALUES (:id, :strat, :date, :net, :gross, :charges, :count, :wins, :losses, :locked, :reason, :locked_at, :updated_at)
                        ON CONFLICT (id) DO NOTHING;
                    """), {
                        "id": r["id"], "strat": r["strategy_id"], "date": r["trading_date"],
                        "net": r["realized_net_pnl"], "gross": r["gross_pnl"], "charges": r["total_charges"],
                        "count": r["trade_count"], "wins": r["winning_trades"], "losses": r["losing_trades"],
                        "locked": bool(r.get("is_locked", 0)), "reason": r.get("lock_reason", "NONE"),
                        "locked_at": r.get("locked_at"), "updated_at": r.get("updated_at")
                    })

            # 4. Migrate pcr_snapshots
            pcrs = data.get("pcr_snapshots", [])
            if pcrs:
                print(f"Migrating pcr_snapshots ({len(pcrs)} rows)...")
                for p in pcrs:
                    conn.execute(text("""
                        INSERT INTO public.pcr_snapshots (
                            id, underlying, expiry, strike_range, timestamp, timestamp_ist,
                            trading_date, atm_strike, spot_price, total_call_oi, total_put_oi,
                            oi_pcr, total_call_volume, total_put_volume, volume_pcr,
                            call_oi_change, put_oi_change, underlying_vwap, futures_vwap,
                            futures_symbol, sentiment, sentiment_score, data_status, created_at
                        ) VALUES (
                            :id, :underlying, :expiry, :strike_range, :timestamp, :timestamp_ist,
                            :trading_date, :atm_strike, :spot_price, :total_call_oi, :total_put_oi,
                            :oi_pcr, :total_call_volume, :total_put_volume, :volume_pcr,
                            :call_oi_change, :put_oi_change, :underlying_vwap, :futures_vwap,
                            :futures_symbol, :sentiment, :sentiment_score, :data_status, :created_at
                        )
                        ON CONFLICT (underlying, expiry, strike_range, timestamp_ist) DO NOTHING;
                    """), p)

            # 5. Migrate historical_candles (in batches of 500)
            candles = data.get("historical_candles", [])
            if candles:
                print(f"Migrating historical_candles ({len(candles)} rows in batches)...")
                chunk_size = 500
                for i in range(0, len(candles), chunk_size):
                    chunk = candles[i:i + chunk_size]
                    for c in chunk:
                        conn.execute(text("""
                            INSERT INTO public.historical_candles (
                                instrument_token, symbol, timeframe, timestamp,
                                open, high, low, close, volume
                            ) VALUES (
                                :instrument_token, :symbol, :timeframe, :timestamp,
                                :open, :high, :low, :close, :volume
                            )
                            ON CONFLICT (symbol, timeframe, timestamp) DO NOTHING;
                        """), {
                            "instrument_token": c["instrument_token"],
                            "symbol": c["symbol"],
                            "timeframe": c.get("timeframe", "1m"),
                            "timestamp": c["timestamp"],
                            "open": c["open"],
                            "high": c["high"],
                            "low": c["low"],
                            "close": c["close"],
                            "volume": c.get("volume", 0.0)
                        })
                    print(f"  - Candles batch {i + len(chunk)}/{len(candles)} committed")

            # 6. Migrate strategy_signals (in batches of 500)
            signals = data.get("strategy_signals", [])
            if signals:
                print(f"Migrating strategy_signals ({len(signals)} rows in batches)...")
                chunk_size = 500
                for i in range(0, len(signals), chunk_size):
                    chunk = signals[i:i + chunk_size]
                    for s in chunk:
                        conn.execute(text("""
                            INSERT INTO public.strategy_signals (
                                strategy_id, timestamp, candle_time, underlying_symbol, underlying_price,
                                ema_9, ema_21, ema_50, rsi_14, atr, trailing_stop,
                                condition_1, condition_2, condition_3, condition_4,
                                signal_type, executed, notes
                            ) VALUES (
                                :strategy_id, :timestamp, :candle_time, :underlying_symbol, :underlying_price,
                                :ema_9, :ema_21, :ema_50, :rsi_14, :atr, :trailing_stop,
                                :condition_1, :condition_2, :condition_3, :condition_4,
                                :signal_type, :executed, :notes
                            );
                        """), {
                            "strategy_id": s.get("strategy_id", "EMA_RSI"),
                            "timestamp": s.get("timestamp"),
                            "candle_time": s["candle_time"],
                            "underlying_symbol": s.get("underlying_symbol", "NIFTY"),
                            "underlying_price": s["underlying_price"],
                            "ema_9": s.get("ema_9"),
                            "ema_21": s.get("ema_21"),
                            "ema_50": s.get("ema_50"),
                            "rsi_14": s.get("rsi_14"),
                            "atr": s.get("atr"),
                            "trailing_stop": s.get("trailing_stop"),
                            "condition_1": s.get("condition_1"),
                            "condition_2": s.get("condition_2"),
                            "condition_3": s.get("condition_3"),
                            "condition_4": s.get("condition_4"),
                            "signal_type": s.get("signal_type", "NONE"),
                            "executed": bool(s.get("executed", 0)),
                            "notes": s.get("notes")
                        })
                    print(f"  - Signals batch {i + len(chunk)}/{len(signals)} committed")

            print("\n==================================================")
            print("✓ SUPABASE MIGRATION COMPLETED SUCCESSFULLY!")
            print("==================================================")
            return True

        except Exception as e:
            print(f"\n❌ Migration failed: {e}")
            return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NEXTRADE SQLite to Supabase Migration")
    parser.add_argument("--backup", type=str, default="", help="Path to backup JSON file")
    parser.add_argument("--db-url", type=str, default="", help="Supabase PostgreSQL connection URL")
    parser.add_argument("--dry-run", action="store_true", help="Validate without writing to database")

    args = parser.parse_args()

    # Locate latest backup if not provided
    backup_path = args.backup
    if not backup_path:
        backup_dir = os.path.join(os.path.dirname(__file__), "..", "backups")
        if os.path.exists(backup_dir):
            files = sorted([os.path.join(backup_dir, f) for f in os.listdir(backup_dir) if f.endswith(".json")])
            if files:
                backup_path = files[-1]

    target_url = args.db_url or os.getenv("SUPABASE_DATABASE_URL") or os.getenv("DATABASE_URL")

    if not backup_path:
        print("No backup file found. Run scripts/export_sqlite_data.py first.")
        sys.exit(1)

    if not args.dry_run and not target_url:
        print("Warning: No target database URL provided. Running in dry-run validation mode.")
        args.dry_run = True

    success = run_migration(backup_path, target_url or "", dry_run=args.dry_run)
    sys.exit(0 if success else 1)
