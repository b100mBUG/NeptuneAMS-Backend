"""
Analysis endpoints — rate-limited to protect heavy aggregation queries.

Scope:
  Admin / Teacher — student & class analysis (within their school)
  Admin only      — teacher activity analysis
  Platform        — school-level overview only
"""

from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from actions.analysis import (
    class_full_analysis,
    school_attendance_overview,
    student_full_analysis,
)
from actions.teacher_activity import all_teachers_summary, teacher_full_analysis
from auth import get_current_admin, get_current_teacher, get_current_user, get_current_platform
from config_db import get_db
from database.models import Admin, Teacher
from rate_limit import ANALYSIS_LIMIT, limiter
from tenancy import require_can_view_student, require_class_in_school, school_id_from_user

router = APIRouter(prefix="/analysis", tags=["Analysis"])

DB          = Annotated[AsyncSession, Depends(get_db)]
AdminAuth   = Annotated[Admin,          Depends(get_current_admin)]
AnyAuth     = Annotated[Admin | Teacher, Depends(get_current_user)]
TeachAuth   = Annotated[Teacher,         Depends(get_current_teacher)]
PlatformAuth = Annotated[dict,           Depends(get_current_platform)]


def _validate_range(start: date, end: date) -> None:
    if end < start:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="end must be on or after start",
        )
    if (end - start).days > 366:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Date range cannot exceed 366 days",
        )


# ── student ───────────────────────────────────────────────────────────────────

@router.get("/students/{student_id}", response_model=dict)
@limiter.limit(ANALYSIS_LIMIT)
async def student_analysis(
    request: Request,
    student_id: str,
    db: DB,
    user: AnyAuth,
    start: date = Query(...),
    end:   date = Query(...),
) -> Any:
    _validate_range(start, end)
    sid = school_id_from_user(user)
    st  = await require_can_view_student(db, user, sid, student_id)
    data = await student_full_analysis(db, sid, student_id, start, end)
    data["student_name"] = st.name
    return data


# ── class ─────────────────────────────────────────────────────────────────────

@router.get("/classes/{class_id}", response_model=dict)
@limiter.limit(ANALYSIS_LIMIT)
async def class_analysis(
    request: Request,
    class_id: str,
    db: DB,
    user: AnyAuth,
    start: date = Query(...),
    end:   date = Query(...),
) -> Any:
    _validate_range(start, end)
    sid = school_id_from_user(user)
    cls = await require_class_in_school(db, sid, class_id)
    data = await class_full_analysis(db, sid, class_id, start, end)
    data["class_name"] = cls.name
    return data


# ── teacher self-analysis (teacher-facing) ────────────────────────────────────

@router.get("/teachers/me", response_model=dict)
@limiter.limit(ANALYSIS_LIMIT)
async def my_analysis(
    request: Request,
    db: DB,
    teacher: TeachAuth,
    start: date = Query(...),
    end:   date = Query(...),
) -> Any:
    _validate_range(start, end)
    return await teacher_full_analysis(db, teacher.school_id, teacher.id, start, end)


# ── teacher (single, admin-only) ──────────────────────────────────────────────

@router.get("/teachers/{teacher_id}", response_model=dict)
@limiter.limit(ANALYSIS_LIMIT)
async def teacher_analysis(
    request: Request,
    teacher_id: str,
    db: DB,
    admin: AdminAuth,
    start: date = Query(...),
    end:   date = Query(...),
) -> Any:
    _validate_range(start, end)
    return await teacher_full_analysis(db, admin.school_id, teacher_id, start, end)


# ── all teachers comparison ───────────────────────────────────────────────────

@router.get("/teachers", response_model=list)
@limiter.limit(ANALYSIS_LIMIT)
async def all_teachers_analysis(
    request: Request,
    db: DB,
    admin: AdminAuth,
    start: date = Query(...),
    end:   date = Query(...),
) -> Any:
    _validate_range(start, end)
    return await all_teachers_summary(db, admin.school_id, start, end)


# ── school overview (platform only) ──────────────────────────────────────────

@router.get("/schools/{school_id}/overview", response_model=dict)
@limiter.limit(ANALYSIS_LIMIT)
async def school_overview(
    request: Request,
    school_id: str,
    db: DB,
    _platform: PlatformAuth,
    start: date = Query(...),
    end:   date = Query(...),
) -> Any:
    _validate_range(start, end)
    return await school_attendance_overview(db, school_id, start, end)