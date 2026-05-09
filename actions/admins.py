from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Admin
from pagination import PageParams


async def create_admin(db: AsyncSession, detail: dict) -> Admin:
    admin = Admin(
        school_id=detail["school_id"],
        name=detail["name"],
        email=detail["email"],
        pwd_hash=detail["pwd_hash"],
    )
    db.add(admin)
    await db.commit()
    await db.refresh(admin)
    return admin


async def fetch_admin_by_email(db: AsyncSession, school_id: str, email: str) -> Admin | None:
    stmt = select(Admin).where(
        Admin.school_id == school_id,
        Admin.email == email,
        Admin.is_deleted.is_(False),
    )
    return (await db.execute(stmt)).scalars().first()


async def fetch_admins_page(
    db: AsyncSession,
    school_id: str,
    page: PageParams,
) -> tuple[list[Admin], int]:
    base = select(Admin).where(Admin.school_id == school_id, Admin.is_deleted.is_(False))
    count_stmt = select(func.count()).select_from(Admin).where(
        Admin.school_id == school_id,
        Admin.is_deleted.is_(False),
    )
    total = (await db.execute(count_stmt)).scalar_one()
    q = base.order_by(Admin.name).offset(page.offset).limit(page.page_size)
    rows = (await db.execute(q)).scalars().all()
    return list(rows), total
