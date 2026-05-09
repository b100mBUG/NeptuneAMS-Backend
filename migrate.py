"""Run once to create all database tables."""
import asyncio
from config_db import engine
from database.models import Base

async def migrate():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("All tables created successfully.")

asyncio.run(migrate())
