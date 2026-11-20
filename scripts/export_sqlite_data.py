#!/usr/bin/env python3
"""
NEXTRADE — SQLite Data Backup & Export Tool
Safely exports all existing SQLite database tables, record counts, and rows
to JSON and SQL seed files before any Supabase migration.
"""

import os
import sqlite3
import json
from datetime import datetime, timezone

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "nextrade.db")
BACKUP_DIR = os.path.join(os.path.dirname(__file__), "..", "backups")


def export_sqlite_data():
    if not os.path.exists(DB_PATH):
        print(f"Error: Database {DB_PATH} not found!")
        return

    os.makedirs(BACKUP_DIR, exist_ok=True)
    timestamp_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_file = os.path.join(BACKUP_DIR, f"nextrade_sqlite_backup_{timestamp_str}.json")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [r[0] for r in cursor.fetchall() if not r[0].startswith("sqlite_")]

    backup_payload = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "database_file": os.path.abspath(DB_PATH),
        "tables_count": len(tables),
        "table_counts": {},
        "data": {}
    }

    print(f"==================================================")
    print(f"NEXTRADE SQLITE BACKUP — {timestamp_str}")
    print(f"Database: {os.path.abspath(DB_PATH)}")
    print(f"==================================================")

    total_rows = 0
    for table in sorted(tables):
        cursor.execute(f"SELECT * FROM {table}")
        rows = cursor.fetchall()
        col_names = [d[0] for d in cursor.description]

        row_dicts = [dict(zip(col_names, row)) for row in rows]
        backup_payload["table_counts"][table] = len(rows)
        backup_payload["data"][table] = row_dicts
        total_rows += len(rows)
        print(f"  ✓ {table:<25}: {len(rows):>6} rows")

    conn.close()

    with open(backup_file, "w", encoding="utf-8") as f:
        json.dump(backup_payload, f, indent=2, default=str)

    print(f"--------------------------------------------------")
    print(f"Total Rows Exported: {total_rows}")
    print(f"Backup JSON Saved: {os.path.abspath(backup_file)}")
    print(f"File Size: {os.path.getsize(backup_file) / (1024*1024):.2f} MB")
    print(f"==================================================")
    return backup_file


if __name__ == "__main__":
    export_sqlite_data()
