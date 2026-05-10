from functools import lru_cache
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # ── Database ─────────────────────────────────────────────────────────
    database_url: str  # 

    # ── Security ──────────────────────────────────────────────────────────
    secret_key:      str  # 
    platform_secret: str  #

    # ── App ───────────────────────────────────────────────────────────────
    cors_origins:     str  = ""
    debug:            bool = False
    sql_echo:         bool = False
    migrate_on_start: bool = False

    # ── Paystack ──────────────────────────────────────────────────────────
    paystack_secret_key:   str  # ← no default
    paystack_callback_url: str = "http://localhost:8765/payment/callback"

    # ── Rate limits ───────────────────────────────────────────────────────
    rate_limit_default:  str = "120/minute"
    rate_limit_login:    str = "10/minute"
    rate_limit_bulk:     str = "5/minute"
    rate_limit_analysis: str = "30/minute"
    rate_limit_payment:  str = "10/minute"

    # ── Pagination ────────────────────────────────────────────────────────
    max_page_size:     int = 100
    default_page_size: int = 25

    # ── Pool ──────────────────────────────────────────────────────────────
    db_pool_size:    int = 10
    db_max_overflow: int = 20
    db_pool_timeout: int = 30
    db_pool_recycle: int = 1800

    @model_validator(mode="after")
    def require_secret_in_prod(self):
        if not self.debug and len(self.secret_key.strip()) < 8:
            raise ValueError("SECRET_KEY must be set (min 8 chars) when DEBUG=false")
        return self

    def cors_origins_list(self) -> list[str]:
        if not self.cors_origins.strip():
            return ["http://localhost:3000", "http://127.0.0.1:8000"]
        return [x.strip() for x in self.cors_origins.split(",") if x.strip()]

@lru_cache
def get_settings() -> Settings:
    return Settings()