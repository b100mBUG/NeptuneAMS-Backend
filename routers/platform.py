from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from actions.admins import create_admin
from actions.platform_schools import get_school_overview, list_schools_overview, set_school_active
from actions.schools import create_school
from auth import create_access_token, get_current_platform, hash_password
from config_db import get_db
from database.models import School
from pagination import Page, PageDep
from rate_limit import LOGIN_LIMIT, limiter
from schemas.auth import TokenResponse
from schemas.platform import (
    PlatformAuthRequest,
    ProvisionSchoolRequest,
    ProvisionSchoolResponse,
    SchoolActivePatch,
    SchoolOverviewResponse,
)
from settings import get_settings
from slug_utils import normalize_slug

router = APIRouter(prefix="/platform", tags=["Platform"])

DB = Annotated[AsyncSession, Depends(get_db)]
PlatformDep = Annotated[dict, Depends(get_current_platform)]


@router.post("/auth", response_model=TokenResponse)
@limiter.limit(LOGIN_LIMIT)
async def platform_login(request: Request, body: PlatformAuthRequest):
    settings = get_settings()
    if not settings.platform_secret or body.platform_secret != settings.platform_secret:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid platform secret")
    token = create_access_token("platform", "platform", "")
    return TokenResponse(
        access_token=token,
        role="platform",
        school_id="",
        school_slug="",
        school_name="AttendEase Platform",
    )


@router.get("/schools", response_model=Page[SchoolOverviewResponse])
async def list_schools(db: DB, _: PlatformDep, page: PageDep):
    items, total = await list_schools_overview(db, page)
    return Page(
        items=[SchoolOverviewResponse.model_validate(x) for x in items],
        total=total,
        page=page.page,
        page_size=page.page_size,
    )


@router.patch("/schools/{school_id}/active", response_model=SchoolOverviewResponse)
async def set_school_status(
    school_id: str,
    body: SchoolActivePatch,
    db: DB,
    _: PlatformDep,
):
    school = await set_school_active(db, school_id, body.is_active)
    if not school:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="School not found")
    row = await get_school_overview(db, school_id)
    return SchoolOverviewResponse.model_validate(row)


@router.post("/schools", response_model=ProvisionSchoolResponse, status_code=status.HTTP_201_CREATED)
async def provision_school(body: ProvisionSchoolRequest, db: DB, _: PlatformDep):
    slug = normalize_slug(body.school_slug)
    existing = (await db.execute(select(School).where(School.slug == slug))).scalars().first()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="School slug already exists")

    school = await create_school(db, body.school_name, slug)
    admin = await create_admin(
        db,
        {
            "school_id": school.id,
            "name": body.admin_name.strip(),
            "email": body.admin_email,
            "pwd_hash": hash_password(body.admin_password),
        },
    )
    return ProvisionSchoolResponse(school_id=school.id, slug=school.slug, admin_id=admin.id)
