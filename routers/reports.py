"""
Reports router.

Existing:
  GET /reports/classes/{class_id}/attendance.csv  — raw CSV (unchanged)
  GET /reports/classes/{class_id}/attendance.pdf  — class attendance detail PDF (unchanged)

New:
  GET /reports/students/{student_id}/analysis.pdf       — full student analysis PDF
  GET /reports/classes/{class_id}/analysis.pdf          — full class analysis PDF (with charts)
  GET /reports/teachers/comparison.pdf                  — all-teachers comparison PDF
  GET /reports/teachers/{teacher_id}/activity.pdf       — single teacher activity PDF
  GET /reports/schools/{school_id}/overview.pdf         — school overview PDF (platform only)
"""
import csv
import io
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from actions.analysis import (
    class_full_analysis,
    school_attendance_overview,
    student_full_analysis,
)
from actions.attendance import attendance_rows_for_report
from actions.classes import fetch_class
from actions.schools import fetch_school
from actions.teacher_activity import all_teachers_summary, teacher_full_analysis
from actions.teachers import fetch_teacher_by_id
from rate_limit import ANALYSIS_LIMIT, limiter
from auth import get_current_admin, get_current_platform, get_current_user
from subscription_guard import SubscriptionGuard
from config_db import get_db
from database.models import Admin, Teacher
from pdf_utils import (
    build_attendance_pdf,
    build_class_analysis_pdf,
    build_school_overview_pdf,
    build_student_analysis_pdf,
    build_teacher_analysis_pdf,
    build_teacher_comparison_pdf,
)
from tenancy import require_can_view_student, require_class_in_school, school_id_from_user

router = APIRouter(prefix="/reports", tags=["Reports"], dependencies=[Depends(SubscriptionGuard)])

DB = Annotated[AsyncSession, Depends(get_db)]
AdminAuth = Annotated[Admin, Depends(get_current_admin)]
AnyAuth = Annotated[Admin | Teacher, Depends(get_current_user)]
PlatformAuth = Annotated[dict, Depends(get_current_platform)]


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


def _stream_pdf(pdf_bytes: bytes, filename: str) -> StreamingResponse:
    return StreamingResponse(
        iter([pdf_bytes]),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _stream_csv(data: bytes, filename: str) -> StreamingResponse:
    return StreamingResponse(
        iter([data]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _safe(name: str) -> str:
    return name.replace(" ", "_").replace("/", "-")


# ══════════════════════════════════════════════════════════════════════════════
# ORIGINAL — class attendance CSV + PDF (unchanged)
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/classes/{class_id}/attendance.csv")
@limiter.limit(ANALYSIS_LIMIT)
async def attendance_report_csv(
    request: Request,
    class_id: str,
    db: DB,
    admin: AdminAuth,
    start: date = Query(..., description="Inclusive start date"),
    end: date = Query(..., description="Inclusive end date"),
    period: str | None = Query(None, max_length=40),
):
    _validate_range(start, end)
    await require_class_in_school(db, admin.school_id, class_id)
    class_ = await fetch_class(db, admin.school_id, class_id)
    if not class_:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Class not found")

    rows = await attendance_rows_for_report(db, admin.school_id, class_id, start, end, period)

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["date", "period", "student_id", "student_name", "status", "note"])
    for session_date, per, sid, name, stat, note in rows:
        writer.writerow([session_date.isoformat(), per, sid, name, stat, note or ""])

    filename = f"attendance_{_safe(class_.name)}_{start}_{end}.csv"
    return _stream_csv(buf.getvalue().encode("utf-8"), filename)


@router.get("/classes/{class_id}/attendance.pdf")
@limiter.limit(ANALYSIS_LIMIT)
async def attendance_report_pdf(
    request: Request,
    class_id: str,
    db: DB,
    admin: AdminAuth,
    start: date = Query(..., description="Inclusive start date"),
    end: date = Query(..., description="Inclusive end date"),
    period: str | None = Query(None, max_length=40),
):
    _validate_range(start, end)
    await require_class_in_school(db, admin.school_id, class_id)

    school = await fetch_school(db, admin.school_id)
    if not school:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="School not found")
    class_ = await fetch_class(db, admin.school_id, class_id)
    if not class_:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Class not found")

    raw_rows = await attendance_rows_for_report(db, admin.school_id, class_id, start, end, period)
    pdf_bytes = build_attendance_pdf(
        school_name=school.name,
        class_name=class_.name,
        start_date=start.isoformat(),
        end_date=end.isoformat(),
        period=period,
        generated_by=getattr(admin, "name", "Admin"),
        rows=raw_rows,
    )
    filename = f"attendance_{_safe(class_.name)}_{start}_{end}.pdf"
    return _stream_pdf(pdf_bytes, filename)


# ══════════════════════════════════════════════════════════════════════════════
# NEW — Student analysis PDF
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/students/{student_id}/analysis.pdf")
@limiter.limit(ANALYSIS_LIMIT)
async def student_analysis_pdf(
    request: Request,
    student_id: str,
    db: DB,
    user: AnyAuth,
    start: date = Query(...),
    end: date = Query(...),
):
    """Full per-student attendance analysis PDF with embedded charts."""
    _validate_range(start, end)
    sid = school_id_from_user(user)
    student = await require_can_view_student(db, user, sid, student_id)

    school = await fetch_school(db, sid)
    school_name = school.name if school else "School"

    data = await student_full_analysis(db, sid, student_id, start, end)
    data["student_name"] = student.name

    pdf_bytes = build_student_analysis_pdf(
        school_name=school_name,
        student_name=student.name,
        student_id=student_id,
        generated_by=getattr(user, "name", "Admin"),
        data=data,
    )
    filename = f"student_analysis_{_safe(student.name)}_{start}_{end}.pdf"
    return _stream_pdf(pdf_bytes, filename)


# ══════════════════════════════════════════════════════════════════════════════
# NEW — Class analysis PDF (with charts, at-risk, perfect attendance, etc.)
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/classes/{class_id}/analysis.pdf")
@limiter.limit(ANALYSIS_LIMIT)
async def class_analysis_pdf(
    request: Request,
    class_id: str,
    db: DB,
    admin: AdminAuth,
    start: date = Query(...),
    end: date = Query(...),
):
    """Full class attendance analysis PDF with embedded charts."""
    _validate_range(start, end)
    await require_class_in_school(db, admin.school_id, class_id)

    school = await fetch_school(db, admin.school_id)
    school_name = school.name if school else "School"
    class_ = await fetch_class(db, admin.school_id, class_id)
    if not class_:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Class not found")

    data = await class_full_analysis(db, admin.school_id, class_id, start, end)
    data["class_name"] = class_.name

    pdf_bytes = build_class_analysis_pdf(
        school_name=school_name,
        class_name=class_.name,
        generated_by=getattr(admin, "name", "Admin"),
        data=data,
    )
    filename = f"class_analysis_{_safe(class_.name)}_{start}_{end}.pdf"
    return _stream_pdf(pdf_bytes, filename)


# ══════════════════════════════════════════════════════════════════════════════
# NEW — All-teachers comparison PDF
# NOTE: this route MUST be before /{teacher_id}/activity.pdf to avoid conflict
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/teachers/comparison.pdf")
@limiter.limit(ANALYSIS_LIMIT)
async def teacher_comparison_pdf(
    request: Request,
    db: DB,
    admin: AdminAuth,
    start: date = Query(...),
    end: date = Query(...),
):
    """Comparative teacher activity PDF — all teachers in the school."""
    _validate_range(start, end)

    school = await fetch_school(db, admin.school_id)
    school_name = school.name if school else "School"

    teachers = await all_teachers_summary(db, admin.school_id, start, end)
    pdf_bytes = build_teacher_comparison_pdf(
        school_name=school_name,
        generated_by=getattr(admin, "name", "Admin"),
        start=start.isoformat(),
        end=end.isoformat(),
        teachers=teachers,
    )
    filename = f"teacher_comparison_{start}_{end}.pdf"
    return _stream_pdf(pdf_bytes, filename)


# ══════════════════════════════════════════════════════════════════════════════
# NEW — Single teacher activity PDF
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/teachers/{teacher_id}/activity.pdf")
@limiter.limit(ANALYSIS_LIMIT)
async def teacher_activity_pdf(
    request: Request,
    teacher_id: str,
    db: DB,
    admin: AdminAuth,
    start: date = Query(...),
    end: date = Query(...),
):
    """Full single-teacher activity analysis PDF with embedded charts."""
    _validate_range(start, end)

    school = await fetch_school(db, admin.school_id)
    school_name = school.name if school else "School"
    teacher = await fetch_teacher_by_id(db, admin.school_id, teacher_id)
    if not teacher:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Teacher not found")

    data = await teacher_full_analysis(db, admin.school_id, teacher_id, start, end)
    pdf_bytes = build_teacher_analysis_pdf(
        school_name=school_name,
        teacher_name=teacher.name,
        generated_by=getattr(admin, "name", "Admin"),
        data=data,
    )
    filename = f"teacher_activity_{_safe(teacher.name)}_{start}_{end}.pdf"
    return _stream_pdf(pdf_bytes, filename)


# ══════════════════════════════════════════════════════════════════════════════
# NEW — School overview PDF (platform/superadmin only)
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/schools/{school_id}/overview.pdf")
@limiter.limit(ANALYSIS_LIMIT)
async def school_overview_pdf(
    request: Request,
    school_id: str,
    db: DB,
    _platform: PlatformAuth,
    start: date = Query(...),
    end: date = Query(...),
):
    """School-wide attendance overview PDF. Platform/superadmin only."""
    _validate_range(start, end)

    school = await fetch_school(db, school_id)
    school_name = school.name if school else school_id

    data = await school_attendance_overview(db, school_id, start, end)
    pdf_bytes = build_school_overview_pdf(
        school_name=school_name,
        generated_by="Platform Admin",
        data=data,
    )
    filename = f"school_overview_{_safe(school_name)}_{start}_{end}.pdf"
    return _stream_pdf(pdf_bytes, filename)
