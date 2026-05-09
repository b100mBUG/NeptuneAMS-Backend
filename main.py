from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from config_db import AsyncSessionLocal, init_db
from rate_limit import limiter
from routers import admins, analysis, attendance, auth, classes, payments, platform, reports, schools, students, teachers
from settings import get_settings

scheduler = AsyncIOScheduler()


async def _expire_schools_job():
    """Daily job — deactivate schools with lapsed subscriptions."""
    async with AsyncSessionLocal() as db:
        from actions.payments import expire_inactive_schools
        count = await expire_inactive_schools(db)
        if count:
            print(f"[scheduler] Deactivated {count} expired school(s).")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    scheduler.add_job(_expire_schools_job, "interval", hours=24, id="expire_schools")
    scheduler.start()
    # Run once immediately on startup so nothing slips through on restart
    await _expire_schools_job()
    yield
    scheduler.shutdown(wait=False)


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Attendance API",
        description="Multi-tenant school attendance (classes, students, attendance, reports).",
        version="3.0.0",
        lifespan=lifespan,
    )
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    origins = settings.cors_origins_list()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(platform.router)
    app.include_router(auth.router)
    app.include_router(payments.router)
    app.include_router(schools.router)
    app.include_router(admins.router)
    app.include_router(classes.router)
    app.include_router(students.router)
    app.include_router(teachers.router)
    app.include_router(attendance.router)
    app.include_router(reports.router)
    app.include_router(analysis.router)

    @app.get("/", tags=["Health"])
    async def root():
        return {"status": "ok", "message": "Attendance API"}

    return app


app = create_app()
