from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from actions.admins import create_admin, fetch_admin_by_email
from actions.schools import fetch_school_by_slug
from actions.teachers import create_teacher
from auth import create_access_token, get_current_admin, hash_password, verify_password
from config_db import get_db
from database.models import Admin, Teacher
from schemas.admins import AdminResponse
from schemas.auth import AdminBootstrapRequest, LoginRequest, TokenResponse
from schemas.teachers import TeacherCreate
from serializers import teacher_to_response
from rate_limit import LOGIN_LIMIT, limiter

router = APIRouter(prefix="/auth", tags=["Auth"])

DB = Annotated[AsyncSession, Depends(get_db)]


async def _fetch_teacher_by_email(db: AsyncSession, school_id: str, email: str) -> Teacher | None:
    stmt = select(Teacher).where(
        Teacher.school_id == school_id,
        Teacher.email == email,
        Teacher.is_deleted.is_(False),
    )
    return (await db.execute(stmt)).scalars().first()


@router.post("/login", response_model=TokenResponse)
@limiter.limit(LOGIN_LIMIT)
async def login(request: Request, body: LoginRequest, db: DB):
    school = await fetch_school_by_slug(db, body.school_slug)
    if not school:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unknown school or inactive")

    admin = await fetch_admin_by_email(db, school.id, body.email)
    if admin and verify_password(body.password, admin.pwd_hash):
        return TokenResponse(
            access_token=create_access_token(admin.id, "admin", school.id),
            role="admin",
            school_id=school.id,
            school_slug=school.slug,
            school_name=school.name,
        )

    teacher = await _fetch_teacher_by_email(db, school.id, body.email)
    if teacher and verify_password(body.password, teacher.pwd_hash):
        return TokenResponse(
            access_token=create_access_token(teacher.id, "teacher", school.id),
            role="teacher",
            school_id=school.id,
            school_slug=school.slug,
            school_name=school.name,
        )

    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")


@router.post("/teacher/register", status_code=status.HTTP_201_CREATED)
async def teacher_register(
    body: TeacherCreate,
    db: DB,
    admin: Annotated[Admin, Depends(get_current_admin)],
):
    existing = (
        await db.execute(
            select(Teacher).where(
                Teacher.school_id == admin.school_id,
                Teacher.email == body.email,
            )
        )
    ).scalars().first()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    try:
        teacher = await create_teacher(
            db,
            school_id=admin.school_id,
            name=body.name,
            email=body.email,
            pwd_hash=hash_password(body.password),
            class_ids=body.class_ids,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    return teacher_to_response(teacher)


@router.post("/admin/register", response_model=AdminResponse, status_code=status.HTTP_201_CREATED)
async def add_school_admin(body: AdminBootstrapRequest, db: DB, admin: Annotated[Admin, Depends(get_current_admin)]):
    exists = (
        await db.execute(
            select(Admin).where(
                Admin.school_id == admin.school_id,
                Admin.email == body.email,
                Admin.is_deleted.is_(False),
            )
        )
    ).scalars().first()
    if exists:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    return await create_admin(
        db,
        {
            "school_id": admin.school_id,
            "name": body.name.strip(),
            "email": body.email,
            "pwd_hash": hash_password(body.password),
        },
    )
