from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database.models import Class, Teacher, teacher_classes
from pagination import PageParams

async def fetch_class(db: AsyncSession, school_id: str, class_id: str) -> Class | None:
    stmt = select(Class).where(
        Class.id == class_id,
        Class.school_id == school_id,
        Class.is_deleted.is_(False),
    )
    result = await db.execute(stmt)
    return result.scalars().first()

async def create_class(db: AsyncSession, school_id: str, name: str) -> Class:
    class_ = Class(school_id=school_id, name=name.strip())
    db.add(class_)
    await db.commit()
    await db.refresh(class_)
    return class_


async def fetch_classes_page(
    db: AsyncSession,
    school_id: str,
    page: PageParams,
) -> tuple[list[Class], int]:
    filt = (Class.school_id == school_id, Class.is_deleted.is_(False))
    count_stmt = select(func.count()).select_from(Class).where(*filt)
    total = (await db.execute(count_stmt)).scalar_one()
    stmt = (
        select(Class)
        .where(*filt)
        .options(selectinload(Class.teachers))
        .order_by(Class.name)
        .offset(page.offset)
        .limit(page.page_size)
    )
    rows = (await db.execute(stmt)).scalars().unique().all()
    return list(rows), total


async def search_classes_page(
    db: AsyncSession,
    school_id: str,
    search_term: str,
    page: PageParams,
) -> tuple[list[Class], int]:
    if len(search_term) > 64:
        return [], 0
    pattern = f"{search_term}%"
    filt = (
        Class.school_id == school_id,
        Class.is_deleted.is_(False),
        Class.name.ilike(pattern),
    )
    count_stmt = select(func.count()).select_from(Class).where(*filt)
    total = (await db.execute(count_stmt)).scalar_one()
    stmt = (
        select(Class)
        .where(*filt)
        .options(selectinload(Class.teachers))
        .order_by(Class.name)
        .offset(page.offset)
        .limit(page.page_size)
    )
    rows = (await db.execute(stmt)).scalars().unique().all()
    return list(rows), total


async def edit_class(db: AsyncSession, school_id: str, class_id: str, name: str) -> Class | None:
    stmt = select(Class).where(Class.id == class_id, Class.school_id == school_id, Class.is_deleted.is_(False))
    class_ = (await db.execute(stmt)).scalars().first()
    if not class_:
        return None
    class_.name = name.strip()
    await db.commit()
    await db.refresh(class_)
    return class_


async def delete_class(db: AsyncSession, school_id: str, class_id: str) -> Class | None:
    stmt = select(Class).where(Class.id == class_id, Class.school_id == school_id, Class.is_deleted.is_(False))
    class_ = (await db.execute(stmt)).scalars().first()
    if not class_:
        return None
    class_.is_deleted = True
    await db.commit()
    return class_


async def undo_delete_class(db: AsyncSession, school_id: str, class_id: str) -> Class | None:
    stmt = select(Class).where(Class.id == class_id, Class.school_id == school_id, Class.is_deleted.is_(True))
    class_ = (await db.execute(stmt)).scalars().first()
    if not class_:
        return None
    class_.is_deleted = False
    await db.commit()
    await db.refresh(class_)
    return class_


async def list_teachers_for_class(db: AsyncSession, school_id: str, class_id: str) -> list[Teacher]:
    stmt = (
        select(Teacher)
        .join(teacher_classes, teacher_classes.c.teacher_id == Teacher.id)
        .where(
            teacher_classes.c.class_id == class_id,
            Teacher.school_id == school_id,
            Teacher.is_deleted.is_(False),
        )
        .order_by(Teacher.name)
    )
    return list((await db.execute(stmt)).scalars().all())
