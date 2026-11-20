from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import declarative_base
from backend.app.config import settings

# Engine configuration
_db_url = settings.async_database_url
_is_sqlite = "sqlite" in _db_url

_connect_args = {"check_same_thread": False} if _is_sqlite else {"statement_cache_size": 0}

engine = create_async_engine(
    _db_url,
    echo=False,
    future=True,
    connect_args=_connect_args
)

# Async session factory
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)

Base = declarative_base()


async def get_db():
    """Dependency for injecting DB sessions into FastAPI routes."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db():
    """Create all database tables on application startup and perform non-destructive schema migrations."""
    # Ensure all models are registered on Base.metadata
    import backend.app.models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

        if "sqlite" in settings.database_url:
            def migrate_sqlite(sync_conn):
                tables_columns = {
                    "backtest_trades": [
                        ("configured_sl_points", "FLOAT DEFAULT 2.0"),
                        ("configured_target_points", "FLOAT DEFAULT 4.0"),
                        ("effective_sl_points", "FLOAT DEFAULT 2.0"),
                        ("effective_target_points", "FLOAT DEFAULT 4.0"),
                        ("sl_trigger_price", "FLOAT"),
                        ("target_trigger_price", "FLOAT"),
                        ("slippage_cost", "FLOAT DEFAULT 0.0"),
                        ("execution_mode", "VARCHAR(30) DEFAULT 'TRIGGER_PRICE'"),
                        ("is_ambiguous", "BOOLEAN DEFAULT 0"),
                        ("ambiguity_flag", "VARCHAR(50)"),
                        ("holding_time_minutes", "INTEGER DEFAULT 1")
                    ],
                    "paper_trades": [
                        ("configured_sl_points", "FLOAT DEFAULT 2.0"),
                        ("configured_target_points", "FLOAT DEFAULT 4.0"),
                        ("effective_sl_points", "FLOAT DEFAULT 2.0"),
                        ("effective_target_points", "FLOAT DEFAULT 4.0"),
                        ("sl_trigger_price", "FLOAT"),
                        ("target_trigger_price", "FLOAT"),
                        ("slippage_cost", "FLOAT DEFAULT 0.0"),
                        ("execution_mode", "VARCHAR(30) DEFAULT 'REALISTIC'"),
                        ("is_ambiguous", "BOOLEAN DEFAULT 0"),
                        ("ambiguity_flag", "VARCHAR(50)"),
                        ("holding_time_minutes", "INTEGER DEFAULT 1")
                    ],
                    "paper_positions": [
                        ("configured_sl_points", "FLOAT DEFAULT 2.0"),
                        ("configured_target_points", "FLOAT DEFAULT 4.0"),
                        ("effective_sl_points", "FLOAT DEFAULT 2.0"),
                        ("effective_target_points", "FLOAT DEFAULT 4.0"),
                        ("sl_trigger_price", "FLOAT"),
                        ("target_trigger_price", "FLOAT"),
                        ("slippage_cost", "FLOAT DEFAULT 0.0"),
                        ("execution_mode", "VARCHAR(30) DEFAULT 'REALISTIC'")
                    ],
                    "backtest_runs": [
                        ("execution_mode", "VARCHAR(30) DEFAULT 'TRIGGER_PRICE'"),
                        ("exit_on_ut_sell_signal", "BOOLEAN DEFAULT 0"),
                        ("configured_sl_points", "FLOAT DEFAULT 2.0"),
                        ("configured_target_points", "FLOAT DEFAULT 4.0")
                    ]
                }
                for table, cols in tables_columns.items():
                    try:
                        cursor = sync_conn.connection.cursor()
                        cursor.execute(f"PRAGMA table_info({table})")
                        existing = [row[1] for row in cursor.fetchall()]
                        for col_name, col_def in cols:
                            if col_name not in existing:
                                cursor.execute(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_def}")
                    except Exception:
                        pass
            await conn.run_sync(migrate_sqlite)
