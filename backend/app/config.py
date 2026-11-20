import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from typing import List


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # Kotak Neo API Credentials (backend only)
    kotak_consumer_key: str = Field(default="", alias="KOTAK_CONSUMER_KEY")
    kotak_consumer_secret: str = Field(default="", alias="KOTAK_CONSUMER_SECRET")
    kotak_mobile_number: str = Field(default="", alias="KOTAK_MOBILE_NUMBER")
    kotak_ucc: str = Field(default="", alias="KOTAK_UCC")
    kotak_access_token: str = Field(default="", alias="KOTAK_ACCESS_TOKEN")
    kotak_mpin: str = Field(default="", alias="KOTAK_MPIN")
    kotak_totp_key: str = Field(default="", alias="KOTAK_TOTP_KEY")
    kotak_environment: str = Field(default="prod", alias="KOTAK_ENVIRONMENT")

    # Supabase Configuration
    supabase_url: str = Field(default="", alias="SUPABASE_URL")
    supabase_service_role_key: str = Field(default="", alias="SUPABASE_SERVICE_ROLE_KEY")
    supabase_anon_key: str = Field(default="", alias="SUPABASE_ANON_KEY")
    supabase_jwt_secret: str = Field(default="", alias="SUPABASE_JWT_SECRET")

    # Authentication & Access Control (Strict 2-User Private Allowlist)
    auth_enabled: bool = Field(default=True, alias="AUTH_ENABLED")
    authorized_emails: str = Field(
        default="admin@nextrade.com,trader@nextrade.com",
        alias="AUTHORIZED_EMAILS"
    )
    jwt_secret_key: str = Field(
        default="nextrade_production_secure_jwt_secret_2026_secured",
        alias="JWT_SECRET_KEY"
    )
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    jwt_access_token_expire_minutes: int = Field(default=1440, alias="JWT_ACCESS_TOKEN_EXPIRE_MINUTES")  # 24 Hours

    @property
    def authorized_email_list(self) -> List[str]:
        return [e.strip().lower() for e in self.authorized_emails.split(",") if e.strip()]

    # Database
    database_url: str = Field(default="sqlite+aiosqlite:///./nextrade.db", alias="DATABASE_URL")

    @property
    def async_database_url(self) -> str:
        """Ensure PostgreSQL connection strings use the asyncpg driver."""
        url = self.database_url.strip()
        if url.startswith("postgres://"):
            return url.replace("postgres://", "postgresql+asyncpg://", 1)
        elif url.startswith("postgresql://") and not url.startswith("postgresql+asyncpg://"):
            return url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return url

    # Application
    app_env: str = Field(default="development", alias="APP_ENV")
    app_host: str = Field(default="0.0.0.0", alias="APP_HOST")
    app_port: int = Field(default=8005, alias="APP_PORT")
    cors_origins: str = Field(default="http://localhost:5173,http://127.0.0.1:5173", alias="CORS_ORIGINS")

    # Paper Trading Risk & Session Settings
    paper_initial_capital: float = Field(default=100000.0, alias="PAPER_INITIAL_CAPITAL")
    paper_default_lots: int = Field(default=1, alias="PAPER_DEFAULT_LOTS")
    paper_target_points: float = Field(default=4.0, alias="PAPER_TARGET_POINTS")
    paper_stop_points: float = Field(default=4.0, alias="PAPER_STOP_POINTS")
    paper_max_loss_per_trade: float = Field(default=1000.0, alias="PAPER_MAX_LOSS_PER_TRADE")
    paper_force_exit_time: str = Field(default="15:20", alias="PAPER_FORCE_EXIT_TIME")
    paper_session_start_time: str = Field(default="09:20", alias="PAPER_SESSION_START_TIME")
    paper_session_end_time: str = Field(default="15:15", alias="PAPER_SESSION_END_TIME")

    @property
    def cors_origin_list(self) -> List[str]:
        return [x.strip() for x in self.cors_origins.split(",") if x.strip()]

    @property
    def has_kotak_credentials(self) -> bool:
        return bool(self.kotak_consumer_key and len(self.kotak_consumer_key.strip()) > 5)


settings = Settings()
