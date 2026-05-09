from datetime import date, datetime, timezone
from sqlalchemy import case, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database.models import Attendance, AttendanceStatus, Student


def utc_today() -> date:
    return datetime.now(timezone.utc).date()


async def mark_attendance(
    db: AsyncSession,
    *,
    school_id: str,
    std_id: str,
    period: str,
    status: AttendanceStatus,
    session_date: date,
    note: str | None,
    marked_by_teacher_id: str | None,
) -> Attendance:
    stmt = select(Attendance).where(
        Attendance.school_id  == school_id,
        Attendance.std_id     == std_id,
        Attendance.period     == period,
        Attendance.session_date == session_date,
    )
    existing = (await db.execute(stmt)).scalars().first()

    if existing:
        existing.status               = status.value
        existing.note                 = note
        existing.marked_by_teacher_id = marked_by_teacher_id
        existing.updated_at           = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(existing)
        return existing

    row = Attendance(
        school_id=school_id,
        std_id=std_id,
        period=period,
        session_date=session_date,
        status=status.value,
        note=note,
        marked_by_teacher_id=marked_by_teacher_id,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def fetch_attendance(
    db: AsyncSession,
    school_id: str,
    class_id: str,
    period: str,
    target_date: date | None = None,
) -> list[Attendance]:
    if target_date is None:
        target_date = utc_today()

    stmt = (
        select(Attendance)
        .options(selectinload(Attendance.student))
        .join(Attendance.student)
        .where(
            Student.school_id   == school_id,
            Student.c_id        == class_id,
            Student.is_deleted.is_(False),
            Attendance.period   == period,
            Attendance.session_date == target_date,
        )
        .order_by(Student.name)
    )
    return list((await db.execute(stmt)).scalars().all())


async def get_student_summary(db: AsyncSession, school_id: str, std_id: str) -> dict:
    stmt = (
        select(
            func.count().label("total"),
            func.sum(case((Attendance.status == AttendanceStatus.present.value, 1), else_=0)).label("present"),
            func.sum(case((Attendance.status == AttendanceStatus.absent.value,  1), else_=0)).label("absent"),
            func.sum(case((Attendance.status == AttendanceStatus.late.value,    1), else_=0)).label("late"),
            func.sum(case((Attendance.status == AttendanceStatus.excused.value, 1), else_=0)).label("excused"),
        )
        .where(Attendance.school_id == school_id, Attendance.std_id == std_id)
    )
    row = (await db.execute(stmt)).one()
    total   = row.total   or 0
    present = row.present or 0
    return {
        "total":   total,
        "present": present,
        "absent":  row.absent  or 0,
        "late":    row.late    or 0,
        "excused": row.excused or 0,
        "rate":    round((present / total) * 100, 1) if total else 0.0,
    }


async def get_class_summary(db: AsyncSession, school_id: str, class_id: str) -> list[dict]:
    """
    Per-student attendance summary for a class — single batched query, no N+1.
    Previously this looped and issued one query per student.
    """
    # 1. Fetch all active students in one query
    students_stmt = (
        select(Student.id, Student.name)
        .where(
            Student.school_id   == school_id,
            Student.c_id        == class_id,
            Student.is_deleted.is_(False),
        )
        .order_by(Student.name)
    )
    students = (await db.execute(students_stmt)).all()
    if not students:
        return []

    student_ids = [s.id for s in students]

    # 2. Aggregate all attendance for those students in one query
    agg_stmt = (
        select(
            Attendance.std_id,
            func.count().label("total"),
            func.sum(case((Attendance.status == AttendanceStatus.present.value, 1), else_=0)).label("present"),
            func.sum(case((Attendance.status == AttendanceStatus.absent.value,  1), else_=0)).label("absent"),
            func.sum(case((Attendance.status == AttendanceStatus.late.value,    1), else_=0)).label("late"),
            func.sum(case((Attendance.status == AttendanceStatus.excused.value, 1), else_=0)).label("excused"),
        )
        .where(
            Attendance.school_id == school_id,
            Attendance.std_id.in_(student_ids),
        )
        .group_by(Attendance.std_id)
    )
    agg_rows = (await db.execute(agg_stmt)).all()
    agg_map  = {r.std_id: r for r in agg_rows}

    # 3. Merge in Python
    summaries = []
    for s in students:
        r     = agg_map.get(s.id)
        total = r.total   if r else 0
        pre   = (r.present or 0) if r else 0
        summaries.append({
            "student_id":   s.id,
            "student_name": s.name,
            "total":   total,
            "present": pre,
            "absent":  (r.absent  or 0) if r else 0,
            "late":    (r.late    or 0) if r else 0,
            "excused": (r.excused or 0) if r else 0,
            "rate":    round((pre / total) * 100, 1) if total else 0.0,
        })
    return summaries


# Row cap for reports — prevents a 366-day × 500-student query returning millions of rows
_MAX_REPORT_ROWS = 50_000


async def attendance_rows_for_report(
    db: AsyncSession,
    school_id: str,
    class_id: str,
    start: date,
    end: date,
    period: str | None,
) -> list[tuple]:
    stmt = (
        select(
            Attendance.session_date,
            Attendance.period,
            Student.id,
            Student.name,
            Attendance.status,
            Attendance.note,
        )
        .join(Attendance.student)
        .where(
            Student.school_id       == school_id,
            Student.c_id            == class_id,
            Student.is_deleted.is_(False),
            Attendance.session_date >= start,
            Attendance.session_date <= end,
        )
        .order_by(Attendance.session_date, Student.name)
        .limit(_MAX_REPORT_ROWS)
    )
    if period:
        stmt = stmt.where(Attendance.period == period)
    return list((await db.execute(stmt)).all())
