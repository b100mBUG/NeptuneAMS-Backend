from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from actions.admins import fetch_admins_page
from auth import get_current_admin
from subscription_guard import SubscriptionGuard
from config_db import get_db
from database.models import Admin
from pagination import Page, PageDep
from schemas.admins import AdminResponse

router = APIRouter(prefix="/admins", tags=["Admins"], dependencies=[Depends(SubscriptionGuard)])

DB = Annotated[AsyncSession, Depends(get_db)]
AdminAuth = Annotated[Admin, Depends(get_current_admin)]


@router.get("/me", response_model=AdminResponse)
async def get_me(admin: AdminAuth):
    return admin


@router.get("/", response_model=Page[AdminResponse])
async def list_admins(db: DB, admin: AdminAuth, page: PageDep):
    items, total = await fetch_admins_page(db, admin.school_id, page)
    return Page(
        items=[AdminResponse.model_validate(a) for a in items],
        total=total,
        page=page.page,
        page_size=page.page_size,
    )
