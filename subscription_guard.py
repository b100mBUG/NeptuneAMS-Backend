"""
SubscriptionGuard — FastAPI dependency.

Raises 402 Payment Required if the school's subscription is expired or missing.
Works for both Admin and Teacher users.

Usage:
    from subscription_guard import SubscriptionGuard

    @router.get("/something")
    async def my_endpoint(user: AnyAuth, _: None = Depends(SubscriptionGuard)):
        ...
"""
from datetime import date

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import get_current_user
from config_db import get_db
from database.models import Admin, SchoolSubscription, Teacher
from tenancy import school_id_from_user


async def require_active_subscription(
    user: Admin | Teacher = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Admin | Teacher:
    school_id = school_id_from_user(user)

    sub = (
        await db.execute(
            select(SchoolSubscription).where(SchoolSubscription.school_id == school_id)
        )
    ).scalars().first()

    if not sub or not sub.subscription_end:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="No active subscription. Please contact your administrator to renew.",
        )

    if sub.subscription_end < date.today():
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=f"Subscription expired on {sub.subscription_end}. Please renew to continue.",
        )

    return user


SubscriptionGuard = require_active_subscription
