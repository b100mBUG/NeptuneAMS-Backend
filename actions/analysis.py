"""
Exhaustive analytics queries.
All aggregations are done in a single DB round-trip where possible — no N+1 loops.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy import case, extract, func, select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Attendance, AttendanceStatus, Class, Student, Teacher, teacher_classes


# ── helpers ───────────────────────────────────────────────────────────────────

_PRESENT = Attendance.status == AttendanceStatus.present.value
_ABSENT  = Attendance.status == AttendanceStatus.absent.value
_LATE    = Attendance.status == AttendanceStatus.late.value
_EXCUSED = Attendance.status == AttendanceStatus.excused.value

def _rate(present: int, total: int) -> float:
    return round(present / total * 100, 1) if total else 0.0


# ── student-level ─────────────────────────────────────────────────────────────

async def student_full_analysis(
    db: AsyncSession,
    school_id: str,
    std_id: str,
    start: date,
    end: date,
) -> dict[str, Any]:
    """
    Complete per-student analytics for a date range:
    - overall counts + rate
    - weekly trend (ISO week buckets)
    - monthly trend
    - worst absence streaks
    - per-period breakdown
    - daily status list (for calendar heatmap)
    """
    base_filter = [
        Attendance.school_id == school_id,
        Attendance.std_id == std_id,
        Attendance.session_date >= start,
        Attendance.session_date <= end,
    ]

    # ── overall counts ────────────────────────────────────────────────────────
    overall_stmt = select(
        func.count().label("total"),
        func.sum(case((_PRESENT, 1), else_=0)).label("present"),
        func.sum(case((_ABSENT,  1), else_=0)).label("absent"),
        func.sum(case((_LATE,   1), else_=0)).label("late"),
        func.sum(case((_EXCUSED,1), else_=0)).label("excused"),
    ).where(*base_filter)
    ov = (await db.execute(overall_stmt)).one()
    total, present, absent, late, excused = (
        ov.total or 0, ov.present or 0, ov.absent or 0,
        ov.late or 0, ov.excused or 0,
    )

    # ── weekly trend ─────────────────────────────────────────────────────────
    weekly_stmt = (
        select(
            extract("year", Attendance.session_date).label("yr"),
            extract("week",    Attendance.session_date).label("wk"),
            func.count().label("total"),
            func.sum(case((_PRESENT, 1), else_=0)).label("present"),
            func.sum(case((_ABSENT,  1), else_=0)).label("absent"),
            func.sum(case((_LATE,   1), else_=0)).label("late"),
            func.sum(case((_EXCUSED,1), else_=0)).label("excused"),
        )
        .where(*base_filter)
        .group_by("yr", "wk")
        .order_by("yr", "wk")
    )
    weekly_rows = (await db.execute(weekly_stmt)).all()
    weekly_trend = [
        {
            "label": f"{int(r.yr)}-W{int(r.wk):02d}",
            "total": r.total, "present": r.present or 0,
            "absent": r.absent or 0, "late": r.late or 0,
            "excused": r.excused or 0,
            "rate": _rate(r.present or 0, r.total),
        }
        for r in weekly_rows
    ]

    # ── monthly trend ─────────────────────────────────────────────────────────
    monthly_stmt = (
        select(
            extract("year",  Attendance.session_date).label("yr"),
            extract("month", Attendance.session_date).label("mo"),
            func.count().label("total"),
            func.sum(case((_PRESENT, 1), else_=0)).label("present"),
            func.sum(case((_ABSENT,  1), else_=0)).label("absent"),
            func.sum(case((_LATE,   1), else_=0)).label("late"),
            func.sum(case((_EXCUSED,1), else_=0)).label("excused"),
        )
        .where(*base_filter)
        .group_by("yr", "mo")
        .order_by("yr", "mo")
    )
    monthly_rows = (await db.execute(monthly_stmt)).all()
    monthly_trend = [
        {
            "label": f"{int(r.yr)}-{int(r.mo):02d}",
            "total": r.total, "present": r.present or 0,
            "absent": r.absent or 0, "late": r.late or 0,
            "excused": r.excused or 0,
            "rate": _rate(r.present or 0, r.total),
        }
        for r in monthly_rows
    ]

    # ── per-period breakdown ──────────────────────────────────────────────────
    period_stmt = (
        select(
            Attendance.period,
            func.count().label("total"),
            func.sum(case((_PRESENT, 1), else_=0)).label("present"),
            func.sum(case((_ABSENT,  1), else_=0)).label("absent"),
            func.sum(case((_LATE,   1), else_=0)).label("late"),
            func.sum(case((_EXCUSED,1), else_=0)).label("excused"),
        )
        .where(*base_filter)
        .group_by(Attendance.period)
        .order_by(Attendance.period)
    )
    period_rows = (await db.execute(period_stmt)).all()
    by_period = [
        {
            "period": r.period,
            "total": r.total, "present": r.present or 0,
            "absent": r.absent or 0, "late": r.late or 0,
            "excused": r.excused or 0,
            "rate": _rate(r.present or 0, r.total),
        }
        for r in period_rows
    ]

    # ── daily status list (for heatmap / calendar) ───────────────────────────
    daily_stmt = (
        select(
            Attendance.session_date,
            Attendance.period,
            Attendance.status,
            Attendance.note,
        )
        .where(*base_filter)
        .order_by(Attendance.session_date, Attendance.period)
    )
    daily_rows = (await db.execute(daily_stmt)).all()
    daily = [
        {
            "date": r.session_date.isoformat(),
            "period": r.period,
            "status": r.status,
            "note": r.note,
        }
        for r in daily_rows
    ]

    # ── absence streaks ───────────────────────────────────────────────────────
    # Compute from daily data in Python — lightweight since it's one student
    absence_streaks = _compute_streaks(daily_rows)

    return {
        "student_id": std_id,
        "date_range": {"start": start.isoformat(), "end": end.isoformat()},
        "overall": {
            "total": total, "present": present, "absent": absent,
            "late": late, "excused": excused, "rate": _rate(present, total),
        },
        "weekly_trend": weekly_trend,
        "monthly_trend": monthly_trend,
        "by_period": by_period,
        "daily": daily,
        "absence_streaks": absence_streaks,
    }


def _compute_streaks(daily_rows) -> list[dict]:
    """Find consecutive absence runs from ordered daily records."""
    streaks = []
    streak_start: date | None = None
    streak_last: date | None = None
    streak_len = 0

    # deduplicate by date (multiple periods per day — a day is absent only if ALL absent)
    by_date: dict[date, list[str]] = {}
    for r in daily_rows:
        by_date.setdefault(r.session_date, []).append(r.status)

    for d in sorted(by_date):
        statuses = by_date[d]
        all_absent = all(s == AttendanceStatus.absent.value for s in statuses)
        if all_absent:
            if streak_start is None:
                streak_start = d
            streak_last = d
            streak_len += 1
        else:
            if streak_len >= 2:
                streaks.append({
                    "start": streak_start.isoformat(),
                    "end": streak_last.isoformat(),
                    "days": streak_len,
                })
            streak_start = None
            streak_last = None
            streak_len = 0

    if streak_len >= 2:
        streaks.append({
            "start": streak_start.isoformat(),
            "end": streak_last.isoformat(),
            "days": streak_len,
        })

    streaks.sort(key=lambda x: x["days"], reverse=True)
    return streaks[:10]


# ── class-level ───────────────────────────────────────────────────────────────

async def class_full_analysis(
    db: AsyncSession,
    school_id: str,
    class_id: str,
    start: date,
    end: date,
) -> dict[str, Any]:
    """
    Complete per-class analytics:
    - per-student summary (single batched query, no N+1)
    - class-level aggregates
    - weekly + monthly class trend
    - daily class-level totals
    - per-period breakdown
    - at-risk students (rate < 75%)
    - perfect attendance students (rate == 100%)
    """
    student_filter = [
        Student.school_id == school_id,
        Student.c_id == class_id,
        Student.is_deleted.is_(False),
    ]

    # ── all students in class ─────────────────────────────────────────────────
    students_stmt = (
        select(Student.id, Student.name)
        .where(*student_filter)
        .order_by(Student.name)
    )
    students = (await db.execute(students_stmt)).all()
    student_ids = [s.id for s in students]

    if not student_ids:
        return _empty_class_analysis(class_id, start, end)

    att_filter = [
        Attendance.school_id == school_id,
        Attendance.std_id.in_(student_ids),
        Attendance.session_date >= start,
        Attendance.session_date <= end,
    ]

    # ── per-student aggregates (single query, batched) ───────────────────────
    per_student_stmt = (
        select(
            Attendance.std_id,
            func.count().label("total"),
            func.sum(case((_PRESENT, 1), else_=0)).label("present"),
            func.sum(case((_ABSENT,  1), else_=0)).label("absent"),
            func.sum(case((_LATE,   1), else_=0)).label("late"),
            func.sum(case((_EXCUSED,1), else_=0)).label("excused"),
        )
        .where(*att_filter)
        .group_by(Attendance.std_id)
    )
    per_student_rows = (await db.execute(per_student_stmt)).all()
    ps_map = {r.std_id: r for r in per_student_rows}

    student_summaries = []
    for s in students:
        r = ps_map.get(s.id)
        tot = r.total if r else 0
        pre = (r.present or 0) if r else 0
        ab  = (r.absent  or 0) if r else 0
        lt  = (r.late    or 0) if r else 0
        ex  = (r.excused or 0) if r else 0
        student_summaries.append({
            "student_id": s.id,
            "student_name": s.name,
            "total": tot, "present": pre, "absent": ab,
            "late": lt, "excused": ex,
            "rate": _rate(pre, tot),
        })

    student_summaries.sort(key=lambda x: x["rate"])

    # ── class overall ─────────────────────────────────────────────────────────
    class_overall_stmt = select(
        func.count().label("total"),
        func.sum(case((_PRESENT, 1), else_=0)).label("present"),
        func.sum(case((_ABSENT,  1), else_=0)).label("absent"),
        func.sum(case((_LATE,   1), else_=0)).label("late"),
        func.sum(case((_EXCUSED,1), else_=0)).label("excused"),
    ).where(*att_filter)
    ov = (await db.execute(class_overall_stmt)).one()
    total_rec = ov.total or 0
    total_pre = ov.present or 0

    # ── weekly trend ─────────────────────────────────────────────────────────
    weekly_stmt = (
        select(
            extract("year", Attendance.session_date).label("yr"),
            extract("week",    Attendance.session_date).label("wk"),
            func.count().label("total"),
            func.sum(case((_PRESENT, 1), else_=0)).label("present"),
            func.sum(case((_ABSENT,  1), else_=0)).label("absent"),
            func.sum(case((_LATE,   1), else_=0)).label("late"),
            func.sum(case((_EXCUSED,1), else_=0)).label("excused"),
        )
        .where(*att_filter)
        .group_by("yr", "wk")
        .order_by("yr", "wk")
    )
    weekly_trend = [
        {
            "label": f"{int(r.yr)}-W{int(r.wk):02d}",
            "total": r.total, "present": r.present or 0,
            "absent": r.absent or 0, "late": r.late or 0,
            "excused": r.excused or 0,
            "rate": _rate(r.present or 0, r.total),
        }
        for r in (await db.execute(weekly_stmt)).all()
    ]

    # ── monthly trend ─────────────────────────────────────────────────────────
    monthly_stmt = (
        select(
            extract("year",  Attendance.session_date).label("yr"),
            extract("month", Attendance.session_date).label("mo"),
            func.count().label("total"),
            func.sum(case((_PRESENT, 1), else_=0)).label("present"),
            func.sum(case((_ABSENT,  1), else_=0)).label("absent"),
            func.sum(case((_LATE,   1), else_=0)).label("late"),
            func.sum(case((_EXCUSED,1), else_=0)).label("excused"),
        )
        .where(*att_filter)
        .group_by("yr", "mo")
        .order_by("yr", "mo")
    )
    monthly_trend = [
        {
            "label": f"{int(r.yr)}-{int(r.mo):02d}",
            "total": r.total, "present": r.present or 0,
            "absent": r.absent or 0, "late": r.late or 0,
            "excused": r.excused or 0,
            "rate": _rate(r.present or 0, r.total),
        }
        for r in (await db.execute(monthly_stmt)).all()
    ]

    # ── daily totals ─────────────────────────────────────────────────────────
    daily_stmt = (
        select(
            Attendance.session_date,
            func.count().label("total"),
            func.sum(case((_PRESENT, 1), else_=0)).label("present"),
            func.sum(case((_ABSENT,  1), else_=0)).label("absent"),
            func.sum(case((_LATE,   1), else_=0)).label("late"),
            func.sum(case((_EXCUSED,1), else_=0)).label("excused"),
        )
        .where(*att_filter)
        .group_by(Attendance.session_date)
        .order_by(Attendance.session_date)
    )
    daily_trend = [
        {
            "date": r.session_date.isoformat(),
            "total": r.total, "present": r.present or 0,
            "absent": r.absent or 0, "late": r.late or 0,
            "excused": r.excused or 0,
            "rate": _rate(r.present or 0, r.total),
        }
        for r in (await db.execute(daily_stmt)).all()
    ]

    # ── per-period ────────────────────────────────────────────────────────────
    period_stmt = (
        select(
            Attendance.period,
            func.count().label("total"),
            func.sum(case((_PRESENT, 1), else_=0)).label("present"),
            func.sum(case((_ABSENT,  1), else_=0)).label("absent"),
            func.sum(case((_LATE,   1), else_=0)).label("late"),
            func.sum(case((_EXCUSED,1), else_=0)).label("excused"),
        )
        .where(*att_filter)
        .group_by(Attendance.period)
        .order_by(Attendance.period)
    )
    by_period = [
        {
            "period": r.period,
            "total": r.total, "present": r.present or 0,
            "absent": r.absent or 0, "late": r.late or 0,
            "excused": r.excused or 0,
            "rate": _rate(r.present or 0, r.total),
        }
        for r in (await db.execute(period_stmt)).all()
    ]

    at_risk    = [s for s in student_summaries if s["total"] > 0 and s["rate"] < 75.0]
    perfect    = [s for s in student_summaries if s["total"] > 0 and s["rate"] == 100.0]

    return {
        "class_id": class_id,
        "date_range": {"start": start.isoformat(), "end": end.isoformat()},
        "student_count": len(students),
        "overall": {
            "total": total_rec, "present": total_pre,
            "absent": ov.absent or 0, "late": ov.late or 0,
            "excused": ov.excused or 0, "rate": _rate(total_pre, total_rec),
        },
        "weekly_trend": weekly_trend,
        "monthly_trend": monthly_trend,
        "daily_trend": daily_trend,
        "by_period": by_period,
        "student_summaries": student_summaries,   # sorted by rate asc
        "at_risk_students": at_risk,
        "perfect_attendance": perfect,
    }


def _empty_class_analysis(class_id: str, start: date, end: date) -> dict:
    return {
        "class_id": class_id,
        "date_range": {"start": start.isoformat(), "end": end.isoformat()},
        "student_count": 0,
        "overall": {"total": 0, "present": 0, "absent": 0, "late": 0, "excused": 0, "rate": 0.0},
        "weekly_trend": [], "monthly_trend": [], "daily_trend": [],
        "by_period": [], "student_summaries": [],
        "at_risk_students": [], "perfect_attendance": [],
    }


# ── school-level overview (superadmin) ───────────────────────────────────────

async def school_attendance_overview(
    db: AsyncSession,
    school_id: str,
    start: date,
    end: date,
) -> dict[str, Any]:
    """
    School-wide attendance overview for a date range.
    Returns aggregate counts, monthly trend, and per-class summary.
    """
    att_filter = [
        Attendance.school_id == school_id,
        Attendance.session_date >= start,
        Attendance.session_date <= end,
    ]

    # overall
    ov = (await db.execute(
        select(
            func.count().label("total"),
            func.sum(case((_PRESENT, 1), else_=0)).label("present"),
            func.sum(case((_ABSENT,  1), else_=0)).label("absent"),
            func.sum(case((_LATE,   1), else_=0)).label("late"),
            func.sum(case((_EXCUSED,1), else_=0)).label("excused"),
        ).where(*att_filter)
    )).one()
    total = ov.total or 0
    present = ov.present or 0

    # monthly trend
    monthly_rows = (await db.execute(
        select(
            extract("year",  Attendance.session_date).label("yr"),
            extract("month", Attendance.session_date).label("mo"),
            func.count().label("total"),
            func.sum(case((_PRESENT, 1), else_=0)).label("present"),
        )
        .where(*att_filter)
        .group_by("yr", "mo")
        .order_by("yr", "mo")
    )).all()
    monthly_trend = [
        {
            "label": f"{int(r.yr)}-{int(r.mo):02d}",
            "total": r.total,
            "present": r.present or 0,
            "rate": _rate(r.present or 0, r.total),
        }
        for r in monthly_rows
    ]

    # per-class summary (batched)
    per_class_stmt = (
        select(
            Student.c_id,
            func.count().label("total"),
            func.sum(case((_PRESENT, 1), else_=0)).label("present"),
            func.sum(case((_ABSENT,  1), else_=0)).label("absent"),
            func.sum(case((_LATE,   1), else_=0)).label("late"),
            func.sum(case((_EXCUSED,1), else_=0)).label("excused"),
        )
        .join(Student, and_(
            Attendance.std_id == Student.id,
            Attendance.school_id == Student.school_id,
        ))
        .where(*att_filter, Student.is_deleted.is_(False))
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
            "rate": _rate(r.present or 0, r.total),
        }
        for r in pc_rows
    ]
    per_class.sort(key=lambda x: x["rate"])

    return {
        "school_id": school_id,
        "date_range": {"start": start.isoformat(), "end": end.isoformat()},
        "overall": {
            "total": total, "present": present,
            "absent": ov.absent or 0, "late": ov.late or 0,
            "excused": ov.excused or 0, "rate": _rate(present, total),
        },
        "monthly_trend": monthly_trend,
        "per_class": per_class,
    }
