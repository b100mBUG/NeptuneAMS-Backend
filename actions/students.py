from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Student
from pagination import PageParams


async def create_student(
    db: AsyncSession,
    *,
    school_id: str,
    admission_id: str,
    name: str,
    class_id: str,
) -> Student:
    student = Student(
        school_id=school_id,
        id=admission_id.strip(),
        name=name.strip(),
        c_id=class_id,
    )
    db.add(student)
    await db.commit()
    await db.refresh(student)
    return student


async def fetch_students_page(
    db: AsyncSession,
    school_id: str,
    class_id: str,
    page: PageParams,
) -> tuple[list[Student], int]:
    filt = (
        Student.school_id == school_id,
        Student.c_id == class_id,
        Student.is_deleted.is_(False),
    )
    count_stmt = select(func.count()).select_from(Student).where(*filt)
    total = (await db.execute(count_stmt)).scalar_one()
    stmt = (
        select(Student)
        .where(*filt)
        .order_by(Student.name)
        .offset(page.offset)
        .limit(page.page_size)
    )
    rows = (await db.execute(stmt)).scalars().all()
    return list(rows), total


async def search_students_page(
    db: AsyncSession,
    school_id: str,
    class_id: str,
    search_term: str,
    page: PageParams,
) -> tuple[list[Student], int]:
    if len(search_term) > 120:
        return [], 0
    filt = (
        Student.school_id == school_id,
        Student.c_id == class_id,
        Student.is_deleted.is_(False),
        Student.name.ilike(f"{search_term}%"),
    )
    count_stmt = select(func.count()).select_from(Student).where(*filt)
    total = (await db.execute(count_stmt)).scalar_one()
    stmt = (
        select(Student)
        .where(*filt)
        .order_by(Student.name)
        .offset(page.offset)
        .limit(page.page_size)
    )
    rows = (await db.execute(stmt)).scalars().all()
    return list(rows), total


async def edit_student(
    db: AsyncSession,
    school_id: str,
    class_id: str,
    admission_id: str,
    name: str,
) -> Student | None:
    stmt = select(Student).where(
        Student.school_id == school_id,
        Student.id == admission_id,
        Student.c_id == class_id,
        Student.is_deleted.is_(False),
    )
    student = (await db.execute(stmt)).scalars().first()
    if not student:
        return None
    student.name = name.strip()
    await db.commit()
    await db.refresh(student)
    return student


async def delete_student(db: AsyncSession, school_id: str, class_id: str, admission_id: str) -> Student | None:
    stmt = select(Student).where(
        Student.school_id == school_id,
        Student.id == admission_id,
        Student.c_id == class_id,
        Student.is_deleted.is_(False),
    )
    student = (await db.execute(stmt)).scalars().first()
    if not student:
        return None
    student.is_deleted = True
    await db.commit()
    return student


async def undo_delete_student(db: AsyncSession, school_id: str, class_id: str, admission_id: str) -> Student | None:
    stmt = select(Student).where(
        Student.school_id == school_id,
        Student.id == admission_id,
        Student.c_id == class_id,
        Student.is_deleted.is_(True),
    )
    student = (await db.execute(stmt)).scalars().first()
    if not student:
        return None
    student.is_deleted = False
    await db.commit()
    await db.refresh(student)
    return student
