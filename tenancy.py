from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Admin, Class, Student, Teacher, teacher_classes


async def get_class_for_school(
    db: AsyncSession,
    school_id: str,
    class_id: str,
    *,
    include_deleted: bool = False,
) -> Class | None:
    stmt = select(Class).where(Class.id == class_id, Class.school_id == school_id)
    if not include_deleted:
        stmt = stmt.where(Class.is_deleted.is_(False))
    return (await db.execute(stmt)).scalars().first()


async def require_class_in_school(db: AsyncSession, school_id: str, class_id: str) -> Class:
    cls = await get_class_for_school(db, school_id, class_id)
    if not cls:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Class not found")
    return cls


async def teacher_has_class(db: AsyncSession, teacher: Teacher, class_id: str) -> bool:
    stmt = (
        select(Class.id)
        .join(teacher_classes, teacher_classes.c.class_id == Class.id)
        .where(
            teacher_classes.c.teacher_id == teacher.id,
            Class.id == class_id,
            Class.school_id == teacher.school_id,
            Class.is_deleted.is_(False),
        )
    )
    return (await db.execute(stmt)).first() is not None


async def require_teacher_class(db: AsyncSession, teacher: Teacher, class_id: str) -> None:
    if not await teacher_has_class(db, teacher, class_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not assigned to this class",
        )


async def get_student_in_school(
    db: AsyncSession,
    school_id: str,
    student_admission_id: str,
    *,
    class_id: str | None = None,
) -> Student | None:
    stmt = select(Student).where(
        Student.school_id == school_id,
        Student.id == student_admission_id,
        Student.is_deleted.is_(False),
    )
    if class_id is not None:
        stmt = stmt.where(Student.c_id == class_id)
    return (await db.execute(stmt)).scalars().first()


async def require_student_in_class(
    db: AsyncSession,
    school_id: str,
    class_id: str,
    student_admission_id: str,
) -> Student:
    s = await get_student_in_school(db, school_id, student_admission_id, class_id=class_id)
    if not s:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found in class")
    return s


def school_id_from_user(user: Admin | Teacher) -> str:
    return user.school_id


async def require_can_view_student(
    db: AsyncSession,
    user: Admin | Teacher,
    school_id: str,
    student_admission_id: str,
) -> Student:
    st = await get_student_in_school(db, school_id, student_admission_id)
    if not st:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found")
    if isinstance(user, Admin):
        return st
    await require_teacher_class(db, user, st.c_id)
    return st
