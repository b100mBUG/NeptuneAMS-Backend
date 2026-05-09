from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import School
from slug_utils import normalize_slug


async def create_school(db: AsyncSession, name: str, slug: str) -> School:
    slug = normalize_slug(slug)
    school = School(name=name.strip(), slug=slug)
    db.add(school)
    await db.commit()
    await db.refresh(school)
    return school


async def fetch_school_by_slug(db: AsyncSession, slug: str) -> School | None:
    stmt = select(School).where(School.slug == slug.lower().strip(), School.is_active.is_(True))
    return (await db.execute(stmt)).scalars().first()


async def fetch_school(db: AsyncSession, school_id: str) -> School | None:
    return (await db.execute(select(School).where(School.id == school_id))).scalars().first()
