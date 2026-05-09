from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from actions.schools import fetch_school
from auth import get_current_user
from subscription_guard import SubscriptionGuard
from config_db import get_db
from database.models import Admin, Teacher
from schemas.schools import SchoolMeResponse, SchoolPublic
from tenancy import school_id_from_user

router = APIRouter(prefix="/schools", tags=["Schools"], dependencies=[Depends(SubscriptionGuard)])

DB = Annotated[AsyncSession, Depends(get_db)]
UserDep = Annotated[Admin | Teacher, Depends(get_current_user)]


@router.get("/me", response_model=SchoolMeResponse)
async def school_me(user: UserDep, db: DB):
    sid = school_id_from_user(user)
    school = await fetch_school(db, sid)
    role = "admin" if isinstance(user, Admin) else "teacher"
    return SchoolMeResponse(
        school=SchoolPublic.model_validate(school),
        role=role,
    )
