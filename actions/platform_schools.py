import asyncio

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Admin, Class, School, Student, Teacher
from pagination import PageParams


async def list_schools_overview(
    db: AsyncSession,
    page: PageParams,
) -> tuple[list[dict], int]:
    total = (await db.execute(select(func.count()).select_from(School))).scalar_one()
    stmt = (
        select(School)
        .order_by(School.created_at.desc())
        .offset(page.offset)
        .limit(page.page_size)
    )
    schools = list((await db.execute(stmt)).scalars().all())
    if not schools:
        return [], total

    ids = [s.id for s in schools]

    def cmap(rows):
        return {r[0]: r[1] for r in rows}

    # Batch all 4 count queries in parallel
    ac, tc, cc, sc = await asyncio.gather(
        db.execute(
            select(Admin.school_id, func.count())
            .where(Admin.school_id.in_(ids), Admin.is_deleted.is_(False))
            .group_by(Admin.school_id)
        ),
        db.execute(
            select(Teacher.school_id, func.count())
            .where(Teacher.school_id.in_(ids), Teacher.is_deleted.is_(False))
            .group_by(Teacher.school_id)
        ),
        db.execute(
            select(Class.school_id, func.count())
            .where(Class.school_id.in_(ids), Class.is_deleted.is_(False))
            .group_by(Class.school_id)
        ),
        db.execute(
            select(Student.school_id, func.count())
            .where(Student.school_id.in_(ids), Student.is_deleted.is_(False))
            .group_by(Student.school_id)
        ),
    )

    amap  = cmap(ac.all())
    tmap  = cmap(tc.all())
    cmap_ = cmap(cc.all())
    smap  = cmap(sc.all())

    items = [
        {
            "id":            s.id,
            "name":          s.name,
            "slug":          s.slug,
            "is_active":     s.is_active,
            "created_at":    s.created_at,
            "admin_count":   amap.get(s.id, 0),
            "teacher_count": tmap.get(s.id, 0),
            "class_count":   cmap_.get(s.id, 0),
            "student_count": smap.get(s.id, 0),
        }
        for s in schools
    ]
    return items, total


async def get_school_overview(db: AsyncSession, school_id: str) -> dict | None:
    school = (await db.execute(select(School).where(School.id == school_id))).scalars().first()
    if not school:
        return None

    # Fire all 4 counts in parallel instead of sequentially
    ac_r, tc_r, cc_r, sc_r = await asyncio.gather(
        db.execute(
            select(func.count()).select_from(Admin)
            .where(Admin.school_id == school_id, Admin.is_deleted.is_(False))
        ),
        db.execute(
            select(func.count()).select_from(Teacher)
            .where(Teacher.school_id == school_id, Teacher.is_deleted.is_(False))
        ),
        db.execute(
            select(func.count()).select_from(Class)
            .where(Class.school_id == school_id, Class.is_deleted.is_(False))
        ),
        db.execute(
            select(func.count()).select_from(Student)
            .where(Student.school_id == school_id, Student.is_deleted.is_(False))
        ),
    )

    return {
        "id":            school.id,
        "name":          school.name,
        "slug":          school.slug,
        "is_active":     school.is_active,
        "created_at":    school.created_at,
        "admin_count":   ac_r.scalar_one(),
        "teacher_count": tc_r.scalar_one(),
        "class_count":   cc_r.scalar_one(),
        "student_count": sc_r.scalar_one(),
    }


async def set_school_active(db: AsyncSession, school_id: str, is_active: bool) -> School | None:
    school = (await db.execute(select(School).where(School.id == school_id))).scalars().first()
    if not school:
        return None
    school.is_active = is_active
    await db.commit()
    await db.refresh(school)
    return school
