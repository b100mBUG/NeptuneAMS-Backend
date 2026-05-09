from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from database.models import Base
from settings import get_settings

_settings = get_settings()

_is_sqlite = _settings.database_url.startswith("sqlite")

engine = create_async_engine(
    _settings.database_url,
    echo=_settings.sql_echo,
    pool_pre_ping=True,
    pool_recycle=_settings.db_pool_recycle,
    **(
        {"poolclass": NullPool}
        if _is_sqlite else
        {
            "pool_size":    _settings.db_pool_size,
            "max_overflow": _settings.db_max_overflow,
            "pool_timeout": _settings.db_pool_timeout,
        }
    ),
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def init_db() -> None:
    if _settings.debug or _settings.migrate_on_start:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session
