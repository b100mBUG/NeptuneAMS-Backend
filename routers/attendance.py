from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from actions.attendance import (
    fetch_attendance,
    get_class_summary,
    get_student_summary,
    mark_attendance,
    utc_today,
)
from auth import get_current_teacher, get_current_user
from subscription_guard import SubscriptionGuard
from config_db import get_db
from database.models import Admin, Attendance, Teacher
from schemas.attendance import AttendanceCreate, AttendanceResponse, AttendanceSummary
from tenancy import (
    require_can_view_student,
    require_class_in_school,
    require_student_in_class,
    require_teacher_class,
    school_id_from_user,
)

router = APIRouter(prefix="/attendance", tags=["Attendance"], dependencies=[Depends(SubscriptionGuard)])

DB = Annotated[AsyncSession, Depends(get_db)]
TeachAuth = Annotated[Teacher, Depends(get_current_teacher)]
AnyAuth = Annotated[Admin | Teacher, Depends(get_current_user)]


@router.post("/", response_model=AttendanceResponse, status_code=status.HTTP_201_CREATED)
async def record_attendance(body: AttendanceCreate, db: DB, user: AnyAuth):
    sid = school_id_from_user(user)
    await require_class_in_school(db, sid, body.class_id)
    if isinstance(user, Teacher):
        await require_teacher_class(db, user, body.class_id)
    await require_student_in_class(db, sid, body.class_id, body.std_id)

    session_d = body.session_date or utc_today()
    marked_by = user.id if isinstance(user, Teacher) else None

    record = await mark_attendance(
        db,
        school_id=sid,
        std_id=body.std_id,
        period=body.period.strip() or "morning",
        status=body.status,
        session_date=session_d,
        note=body.note,
        marked_by_teacher_id=marked_by,
    )
    stmt = (
        select(Attendance)
        .options(selectinload(Attendance.student))
        .where(Attendance.id == record.id)
    )
    row = (await db.execute(stmt)).scalars().first()
    return _attendance_to_response(row)


@router.get("/class/{class_id}", response_model=list[AttendanceResponse])
async def get_class_attendance(
    class_id: str,
    db: DB,
    user: AnyAuth,
    period: str = "morning",
    target_date: date | None = None,
):
    sid = school_id_from_user(user)
    await require_class_in_school(db, sid, class_id)
    if isinstance(user, Teacher):
        await require_teacher_class(db, user, class_id)

    rows = await fetch_attendance(db, sid, class_id, period, target_date)
    return [_attendance_to_response(a) for a in rows]


def _attendance_to_response(a: Attendance) -> AttendanceResponse:
    name = a.student.name if a.student else None
    return AttendanceResponse(
        id=a.id,
        school_id=a.school_id,
        std_id=a.std_id,
        period=a.period,
        session_date=a.session_date,
        status=a.status,
        note=a.note,
        marked_by_teacher_id=a.marked_by_teacher_id,
        created_at=a.created_at,
        updated_at=a.updated_at,
        student_name=name,
    )


@router.get("/summary/student/{student_id}", response_model=AttendanceSummary)
async def student_summary(student_id: str, db: DB, user: AnyAuth):
    sid = school_id_from_user(user)
    st = await require_can_view_student(db, user, sid, student_id)
    agg = await get_student_summary(db, sid, student_id)
    return AttendanceSummary(
        student_id=student_id,
        student_name=st.name,
        **agg,
    )


@router.get("/summary/class/{class_id}", response_model=list[AttendanceSummary])
async def class_summary(class_id: str, db: DB, user: AnyAuth):
    sid = school_id_from_user(user)
    await require_class_in_school(db, sid, class_id)
    if isinstance(user, Teacher):
        await require_teacher_class(db, user, class_id)

    rows = await get_class_summary(db, sid, class_id)
    return [AttendanceSummary(**r) for r in rows]
