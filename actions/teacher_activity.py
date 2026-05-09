"""
Teacher activity monitoring and analytics.
Tracks marking behaviour, consistency, class coverage and output quality.
All queries are batched — no per-teacher loops.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import case, extract, func, select, and_, distinct
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Attendance, AttendanceStatus, Class, Student, Teacher, teacher_classes


_PRESENT = Attendance.status == AttendanceStatus.present.value
_ABSENT  = Attendance.status == AttendanceStatus.absent.value
_LATE    = Attendance.status == AttendanceStatus.late.value
_EXCUSED = Attendance.status == AttendanceStatus.excused.value


def _rate(a: int, b: int) -> float:
    return round(a / b * 100, 1) if b else 0.0


# ── single teacher ────────────────────────────────────────────────────────────

async def teacher_full_analysis(
    db: AsyncSession,
    school_id: str,
    teacher_id: str,
    start: date,
    end: date,
) -> dict[str, Any]:
    """
    Full activity profile for one teacher:
    - total records marked, breakdown by status
    - records marked per class
    - weekly + monthly marking trend
    - daily marking volume (how many records marked per day)
    - session days worked vs total school days in range
    - notes usage rate
    - per-period marking breakdown
    - days with zero marking activity (absent days for the teacher)
    """
    base_filter = [
        Attendance.school_id == school_id,
        Attendance.marked_by_teacher_id == teacher_id,
        Attendance.session_date >= start,
        Attendance.session_date <= end,
    ]

    # ── overall counts ────────────────────────────────────────────────────────
    ov = (await db.execute(
        select(
            func.count().label("total"),
            func.sum(case((_PRESENT, 1), else_=0)).label("present"),
            func.sum(case((_ABSENT,  1), else_=0)).label("absent"),
            func.sum(case((_LATE,   1), else_=0)).label("late"),
            func.sum(case((_EXCUSED,1), else_=0)).label("excused"),
            func.sum(case((Attendance.note.isnot(None), 1), else_=0)).label("with_notes"),
        ).where(*base_filter)
    )).one()

    total   = ov.total or 0
    present = ov.present or 0
    absent  = ov.absent  or 0
    late    = ov.late    or 0
    excused = ov.excused or 0
    with_notes = ov.with_notes or 0

    # ── per-class breakdown ───────────────────────────────────────────────────
    per_class_stmt = (
        select(
            Student.c_id,
            func.count().label("total"),
            func.sum(case((_PRESENT, 1), else_=0)).label("present"),
            func.sum(case((_ABSENT,  1), else_=0)).label("absent"),
            func.sum(case((_LATE,   1), else_=0)).label("late"),
            func.sum(case((_EXCUSED,1), else_=0)).label("excused"),
            func.count(distinct(Attendance.session_date)).label("active_days"),
        )
        .join(Student, and_(
            Attendance.std_id == Student.id,
            Attendance.school_id == Student.school_id,
        ))
        .where(*base_filter, Student.is_deleted.is_(False))
        .group_by(Student.c_id)
    )
    pc_rows = (await db.execute(per_class_stmt)).all()

    class_ids = [r.c_id for r in pc_rows]
    class_names: dict[str, str] = {}
    if class_ids:
        cn_rows = (await db.execute(
            select(Class.id, Class.name).where(Class.id.in_(class_ids))
        )).all()
        class_names = {r.id: r.name for r in cn_rows}

    per_class = [
        {
            "class_id": r.c_id,
            "class_name": class_names.get(r.c_id, r.c_id),
            "total": r.total, "present": r.present or 0,
            "absent": r.absent or 0, "late": r.late or 0,
            "excused": r.excused or 0,
            "active_days": r.active_days,
            "rate_marked_present": _rate(r.present or 0, r.total),
        }
        for r in pc_rows
    ]
    per_class.sort(key=lambda x: x["class_name"])

    # ── weekly trend ─────────────────────────────────────────────────────────
    weekly_rows = (await db.execute(
        select(
            extract("year", Attendance.session_date).label("yr"),
            extract("week",    Attendance.session_date).label("wk"),
            func.count().label("total"),
            func.sum(case((_PRESENT, 1), else_=0)).label("present"),
            func.sum(case((_ABSENT,  1), else_=0)).label("absent"),
            func.count(distinct(Attendance.session_date)).label("days_active"),
        )
        .where(*base_filter)
        .group_by("yr", "wk")
        .order_by("yr", "wk")
    )).all()
    weekly_trend = [
        {
            "label": f"{int(r.yr)}-W{int(r.wk):02d}",
            "total_marked": r.total,
            "present": r.present or 0,
            "absent": r.absent or 0,
            "days_active": r.days_active,
        }
        for r in weekly_rows
    ]

    # ── monthly trend ─────────────────────────────────────────────────────────
    monthly_rows = (await db.execute(
        select(
            extract("year",  Attendance.session_date).label("yr"),
            extract("month", Attendance.session_date).label("mo"),
            func.count().label("total"),
            func.sum(case((_PRESENT, 1), else_=0)).label("present"),
            func.sum(case((_ABSENT,  1), else_=0)).label("absent"),
            func.count(distinct(Attendance.session_date)).label("days_active"),
        )
        .where(*base_filter)
        .group_by("yr", "mo")
        .order_by("yr", "mo")
    )).all()
    monthly_trend = [
        {
            "label": f"{int(r.yr)}-{int(r.mo):02d}",
            "total_marked": r.total,
            "present": r.present or 0,
            "absent": r.absent or 0,
            "days_active": r.days_active,
        }
        for r in monthly_rows
    ]

    # ── daily marking volume ──────────────────────────────────────────────────
    daily_rows = (await db.execute(
        select(
            Attendance.session_date,
            func.count().label("total"),
            func.sum(case((_PRESENT, 1), else_=0)).label("present"),
            func.sum(case((_ABSENT,  1), else_=0)).label("absent"),
            func.sum(case((_LATE,   1), else_=0)).label("late"),
            func.sum(case((_EXCUSED,1), else_=0)).label("excused"),
        )
        .where(*base_filter)
        .group_by(Attendance.session_date)
        .order_by(Attendance.session_date)
    )).all()
    daily_volume = [
        {
            "date": r.session_date.isoformat(),
            "total_marked": r.total,
            "present": r.present or 0,
            "absent": r.absent or 0,
            "late": r.late or 0,
            "excused": r.excused or 0,
        }
        for r in daily_rows
    ]

    # ── per-period breakdown ──────────────────────────────────────────────────
    period_rows = (await db.execute(
        select(
            Attendance.period,
            func.count().label("total"),
            func.count(distinct(Attendance.session_date)).label("days_active"),
        )
        .where(*base_filter)
        .group_by(Attendance.period)
        .order_by(Attendance.period)
    )).all()
    by_period = [
        {
            "period": r.period,
            "total_marked": r.total,
            "days_active": r.days_active,
        }
        for r in period_rows
    ]

    active_days_set = {r["date"] for r in daily_volume}
    days_in_range = (end - start).days + 1

    return {
        "teacher_id": teacher_id,
        "date_range": {"start": start.isoformat(), "end": end.isoformat()},
        "overall": {
            "total_marked": total,
            "present": present,
            "absent": absent,
            "late": late,
            "excused": excused,
            "with_notes": with_notes,
            "notes_usage_rate": _rate(with_notes, total),
            "active_days": len(active_days_set),
            "days_in_range": days_in_range,
            "activity_rate": _rate(len(active_days_set), days_in_range),
        },
        "per_class": per_class,
        "weekly_trend": weekly_trend,
        "monthly_trend": monthly_trend,
        "daily_volume": daily_volume,
        "by_period": by_period,
    }


# ── all teachers in school (comparison dashboard) ────────────────────────────

async def all_teachers_summary(
    db: AsyncSession,
    school_id: str,
    start: date,
    end: date,
) -> list[dict[str, Any]]:
    """
    Comparative summary of all teachers for a date range.
    Single query — batched across all teachers.
    Returns list sorted by total records marked desc.
    """
    # fetch all active teachers in school
    teacher_rows = (await db.execute(
        select(Teacher.id, Teacher.name)
        .where(Teacher.school_id == school_id, Teacher.is_deleted.is_(False))
        .order_by(Teacher.name)
    )).all()

    if not teacher_rows:
        return []

    teacher_ids = [t.id for t in teacher_rows]
    teacher_names = {t.id: t.name for t in teacher_rows}

    att_filter = [
        Attendance.school_id == school_id,
        Attendance.marked_by_teacher_id.in_(teacher_ids),
        Attendance.session_date >= start,
        Attendance.session_date <= end,
    ]

    # per-teacher aggregate — one query
    agg_stmt = (
        select(
            Attendance.marked_by_teacher_id.label("teacher_id"),
            func.count().label("total"),
            func.sum(case((_PRESENT, 1), else_=0)).label("present"),
            func.sum(case((_ABSENT,  1), else_=0)).label("absent"),
            func.sum(case((_LATE,   1), else_=0)).label("late"),
            func.sum(case((_EXCUSED,1), else_=0)).label("excused"),
            func.count(distinct(Attendance.session_date)).label("active_days"),
            func.sum(case((Attendance.note.isnot(None), 1), else_=0)).label("with_notes"),
            func.count(distinct(Student.c_id)).label("classes_covered"),
        )
        .join(Student, and_(
            Attendance.std_id == Student.id,
            Attendance.school_id == Student.school_id,
        ))
        .where(*att_filter, Student.is_deleted.is_(False))
        .group_by(Attendance.marked_by_teacher_id)
    )
    agg_rows = (await db.execute(agg_stmt)).all()
    agg_map = {r.teacher_id: r for r in agg_rows}

    days_in_range = (end - start).days + 1
    result = []
    for tid in teacher_ids:
        r = agg_map.get(tid)
        tot    = r.total       if r else 0
        pre    = (r.present  or 0) if r else 0
        ab     = (r.absent   or 0) if r else 0
        lt     = (r.late     or 0) if r else 0
        ex     = (r.excused  or 0) if r else 0
        act    = r.active_days    if r else 0
        notes  = (r.with_notes or 0) if r else 0
        clses  = r.classes_covered if r else 0

        result.append({
            "teacher_id": tid,
            "teacher_name": teacher_names[tid],
            "total_marked": tot,
            "present": pre,
            "absent": ab,
            "late": lt,
            "excused": ex,
            "active_days": act,
            "days_in_range": days_in_range,
            "activity_rate": _rate(act, days_in_range),
            "notes_usage_rate": _rate(notes, tot),
            "classes_covered": clses,
        })

    result.sort(key=lambda x: x["total_marked"], reverse=True)
    return result
