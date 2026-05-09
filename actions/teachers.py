from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database.models import Class, Teacher
from pagination import PageParams


async def create_teacher(
    db: AsyncSession,
    *,
    school_id: str,
    name: str,
    email: str,
    pwd_hash: str,
    class_ids: list[str],
) -> Teacher:
    if not class_ids:
        raise ValueError("At least one class assignment is required")

    teacher = Teacher(
        school_id=school_id,
        name=name,
        email=email,
        pwd_hash=pwd_hash,
    )
    classes: list[Class] = []
    for cid in class_ids:
        stmt = select(Class).where(
            Class.id == cid,
            Class.school_id == school_id,
            Class.is_deleted.is_(False),
        )
        cls = (await db.execute(stmt)).scalars().first()
        if not cls:
            raise ValueError(f"Class not found: {cid}")
        classes.append(cls)
    teacher.classes = classes
    db.add(teacher)
    await db.commit()
    await db.refresh(teacher)
    out = await fetch_teacher_by_id(db, school_id, teacher.id)
    assert out is not None
    return out


async def set_teacher_classes(
    db: AsyncSession,
    school_id: str,
    teacher_id: str,
    class_ids: list[str],
) -> Teacher | None:
    if not class_ids:
        raise ValueError("At least one class assignment is required")

    stmt = (
        select(Teacher)
        .where(Teacher.id == teacher_id, Teacher.school_id == school_id, Teacher.is_deleted.is_(False))
        .options(selectinload(Teacher.classes))
    )
    teacher = (await db.execute(stmt)).scalars().first()
    if not teacher:
        return None

    classes: list[Class] = []
    for cid in class_ids:
        q = select(Class).where(
            Class.id == cid,
            Class.school_id == school_id,
            Class.is_deleted.is_(False),
        )
        cls = (await db.execute(q)).scalars().first()
        if not cls:
            raise ValueError(f"Class not found: {cid}")
        classes.append(cls)
    teacher.classes = classes
    await db.commit()
    await db.refresh(teacher)
    return teacher


async def fetch_teacher_by_id(db: AsyncSession, school_id: str, teacher_id: str) -> Teacher | None:
    stmt = (
        select(Teacher)
        .where(Teacher.id == teacher_id, Teacher.school_id == school_id, Teacher.is_deleted.is_(False))
        .options(selectinload(Teacher.classes))
    )
    return (await db.execute(stmt)).scalars().first()


async def search_teachers_page(
    db: AsyncSession,
    school_id: str,
    search_term: str,
    page: PageParams,
) -> tuple[list[Teacher], int]:
    filt = [Teacher.school_id == school_id, Teacher.is_deleted.is_(False)]
    if search_term:
        if len(search_term) > 120:
            return [], 0
        filt.append(Teacher.name.ilike(f"{search_term}%"))
    count_stmt = select(func.count()).select_from(Teacher).where(*filt)
    total = (await db.execute(count_stmt)).scalar_one()
    stmt = (
        select(Teacher)
        .where(*filt)
        .options(selectinload(Teacher.classes))
        .order_by(Teacher.name)
        .offset(page.offset)
        .limit(page.page_size)
    )
    rows = (await db.execute(stmt)).scalars().unique().all()
    return list(rows), total


async def edit_teacher(db: AsyncSession, school_id: str, tch_id: str, name: str) -> Teacher | None:
    stmt = (
        select(Teacher)
        .where(Teacher.id == tch_id, Teacher.school_id == school_id, Teacher.is_deleted.is_(False))
        .options(selectinload(Teacher.classes))
    )
    teacher = (await db.execute(stmt)).scalars().first()
    if not teacher:
        return None
    teacher.name = name
    await db.commit()
    await db.refresh(teacher)
    return teacher


async def delete_teacher(db: AsyncSession, school_id: str, tch_id: str) -> Teacher | None:
    stmt = select(Teacher).where(Teacher.id == tch_id, Teacher.school_id == school_id, Teacher.is_deleted.is_(False))
    teacher = (await db.execute(stmt)).scalars().first()
    if not teacher:
        return None
    teacher.is_deleted = True
    await db.commit()
    return teacher


async def undo_delete_teacher(db: AsyncSession, school_id: str, tch_id: str) -> Teacher | None:
    stmt = select(Teacher).where(Teacher.id == tch_id, Teacher.school_id == school_id, Teacher.is_deleted.is_(True))
    teacher = (await db.execute(stmt)).scalars().first()
    if not teacher:
        return None
    teacher.is_deleted = False
    await db.commit()
    await db.refresh(teacher)
    return teacher
