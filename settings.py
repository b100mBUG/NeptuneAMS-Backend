from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # ── Database ──────────────────────────────────────────────────────────────
    database_url: str = "sqlite+aiosqlite:///./database.db"

    # ── Security ──────────────────────────────────────────────────────────────
    secret_key:      str = "28a60971-c743-46ac-829b-0a080db395a1"
    platform_secret: str = "b100mBUG-Platform"

    # ── App ───────────────────────────────────────────────────────────────────
    cors_origins: str  = ""
    debug:        bool = False
    sql_echo:     bool = False
    migrate_on_start: bool = False

    # ── Paystack ──────────────────────────────────────────────────────────────
    paystack_secret_key:  str = "sk_test_ae2f881a9852e13b3a633b514614ee93f4e6d3ef"
    paystack_callback_url: str = "http://localhost:8765/payment/callback"

    # ── Rate limits ───────────────────────────────────────────────────────────
    # Global default: generous for normal usage but blocks abuse
    rate_limit_default: str = "120/minute"
    # Auth: tight to prevent brute-force
    rate_limit_login:   str = "10/minute"
    # Bulk import: expensive ops, keep low
    rate_limit_bulk:    str = "5/minute"
    # Analysis/reports: heavy DB queries
    rate_limit_analysis: str = "30/minute"
    # Payment: Paystack calls are slow, prevent hammering
    rate_limit_payment: str = "10/minute"

    # ── Pagination ────────────────────────────────────────────────────────────
    max_page_size:     int = 100
    default_page_size: int = 25

    # ── Pool (PostgreSQL — ignored for SQLite) ────────────────────────────────
    db_pool_size:     int = 10
    db_max_overflow:  int = 20
    db_pool_timeout:  int = 30
    db_pool_recycle:  int = 1800

    @model_validator(mode="after")
    def require_secret_in_prod(self):
        if not self.debug and (not self.secret_key or len(self.secret_key.strip()) < 8):
            raise ValueError("SECRET_KEY must be set (min 8 chars) when DEBUG=false")
        return self

    def cors_origins_list(self) -> list[str]:
        if not self.cors_origins.strip():
            return ["http://localhost:3000", "http://127.0.0.1:8000"]
        return [x.strip() for x in self.cors_origins.split(",") if x.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
