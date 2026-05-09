"""
Payment actions — Paystack integration, subscription management, pricing logic.

Pricing:
  For every 500 students (or part thereof), the school pays KES 10,000/year.
  ≤  500 → 10,000
  ≤ 1000 → 20,000
  ≤ 1500 → 30,000
  … and so on.
"""
import math
from datetime import date, datetime, timezone, timedelta
from uuid import uuid4

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import PaymentLog, PaymentStatus, School, SchoolSubscription, Student
from settings import get_settings

PRICE_PER_500 = 10_000          # KES per 500-student band
SUBSCRIPTION_DAYS = 365


def compute_price(student_count: int) -> int:
    """Return the annual fee in KES for the given student count."""
    if student_count <= 0:
        student_count = 1          # at least 1 band
    bands = math.ceil(student_count / 500)
    return bands * PRICE_PER_500


async def get_active_student_count(db: AsyncSession, school_id: str) -> int:
    result = await db.execute(
        select(func.count())
        .select_from(Student)
        .where(Student.school_id == school_id, Student.is_deleted.is_(False))
    )
    return result.scalar_one()


async def initiate_paystack_payment(
    db: AsyncSession,
    school_id: str,
    email: str,
) -> dict:
    settings = get_settings()
    school = (await db.execute(select(School).where(School.id == school_id))).scalars().first()
    if not school:
        raise ValueError("School not found")

    student_count = await get_active_student_count(db, school_id)
    amount_kes = compute_price(student_count)
    amount_kobo = amount_kes * 100          # Paystack uses smallest currency unit

    reference = f"ATTEND-{school.slug}-{uuid4().hex[:12].upper()}"

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://api.paystack.co/transaction/initialize",
            headers={
                "Authorization": f"Bearer {settings.paystack_secret_key}",
                "Content-Type": "application/json",
            },
            json={
                "email": email,
                "amount": amount_kobo,
                "reference": reference,
                "metadata": {
                    "school_id": school_id,
                    "school_name": school.name,
                    "student_count": student_count,
                },
                "callback_url": settings.paystack_callback_url,
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

    if not data.get("status") or not data.get("data"):
        raise ValueError(f"Paystack error: {data.get('message', 'Unknown error')}")

    ps_data = data["data"]

    log = PaymentLog(
        school_id=school_id,
        paystack_reference=reference,
        paystack_access_code=ps_data.get("access_code"),
        amount=amount_kobo,
        student_count=student_count,
        status=PaymentStatus.pending.value,
    )
    db.add(log)
    await db.commit()

    return {
        "authorization_url": ps_data["authorization_url"],
        "access_code": ps_data["access_code"],
        "reference": reference,
        "amount": amount_kes,
        "student_count": student_count,
    }


async def verify_paystack_payment(db: AsyncSession, reference: str) -> dict:
    settings = get_settings()

    log = (
        await db.execute(select(PaymentLog).where(PaymentLog.paystack_reference == reference))
    ).scalars().first()
    if not log:
        raise ValueError("Payment reference not found")

    # Idempotency — if already verified successfully, don't process again
    if log.status == PaymentStatus.success.value:
        sub = (
            await db.execute(
                select(SchoolSubscription).where(SchoolSubscription.school_id == log.school_id)
            )
        ).scalars().first()
        return {
            "success": True,
            "message": "Payment already verified.",
            "school_id": log.school_id,
            "amount_paid": log.amount // 100,
            "student_count": log.student_count,
            "subscription_start": sub.subscription_start if sub else None,
            "subscription_end": sub.subscription_end if sub else None,
        }

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"https://api.paystack.co/transaction/verify/{reference}",
            headers={"Authorization": f"Bearer {settings.paystack_secret_key}"},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

    ps_data = data.get("data", {})
    ps_status = ps_data.get("status", "")
    gateway_response = ps_data.get("gateway_response", "")

    if ps_status == "success":
        log.status = PaymentStatus.success.value
        log.gateway_response = gateway_response
        log.paid_at = datetime.now(timezone.utc)

        # Activate / extend the school subscription
        sub = (
            await db.execute(
                select(SchoolSubscription).where(SchoolSubscription.school_id == log.school_id)
            )
        ).scalars().first()

        today = date.today()
        # If there's an unexpired subscription, extend from its end date
        if sub and sub.subscription_end and sub.subscription_end >= today:
            new_start = sub.subscription_start
            new_end = sub.subscription_end + timedelta(days=SUBSCRIPTION_DAYS)
        else:
            new_start = today
            new_end = today + timedelta(days=SUBSCRIPTION_DAYS)

        if sub:
            sub.subscription_start = new_start
            sub.subscription_end = new_end
            sub.student_count_at_payment = log.student_count
            sub.amount_paid = log.amount // 100   # store as KES
        else:
            sub = SchoolSubscription(
                school_id=log.school_id,
                subscription_start=new_start,
                subscription_end=new_end,
                student_count_at_payment=log.student_count,
                amount_paid=log.amount // 100,
            )
            db.add(sub)

        # Ensure school is marked active
        school = (
            await db.execute(select(School).where(School.id == log.school_id))
        ).scalars().first()
        if school:
            school.is_active = True

        await db.commit()

        return {
            "success": True,
            "message": "Payment verified. Subscription activated.",
            "school_id": log.school_id,
            "amount_paid": log.amount // 100,
            "student_count": log.student_count,
            "subscription_start": new_start,
            "subscription_end": new_end,
        }
    else:
        log.status = PaymentStatus.failed.value
        log.gateway_response = gateway_response
        await db.commit()
        return {
            "success": False,
            "message": f"Payment not successful: {gateway_response or ps_status}",
            "school_id": log.school_id,
            "amount_paid": 0,
            "student_count": log.student_count,
            "subscription_start": None,
            "subscription_end": None,
        }


async def get_subscription(db: AsyncSession, school_id: str) -> dict | None:
    school = (await db.execute(select(School).where(School.id == school_id))).scalars().first()
    if not school:
        return None

    sub = (
        await db.execute(
            select(SchoolSubscription).where(SchoolSubscription.school_id == school_id)
        )
    ).scalars().first()

    today = date.today()
    if sub and sub.subscription_end:
        is_expired = sub.subscription_end < today
        days_remaining = (sub.subscription_end - today).days if not is_expired else 0
    else:
        is_expired = True
        days_remaining = None

    return {
        "school_id": school.id,
        "school_name": school.name,
        "is_active": school.is_active,
        "subscription_start": sub.subscription_start if sub else None,
        "subscription_end": sub.subscription_end if sub else None,
        "student_count_at_payment": sub.student_count_at_payment if sub else 0,
        "amount_paid": sub.amount_paid if sub else 0,
        "is_expired": is_expired,
        "days_remaining": days_remaining,
    }


async def list_payment_logs(
    db: AsyncSession,
    school_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[PaymentLog], int]:
    stmt = select(PaymentLog)
    count_stmt = select(func.count()).select_from(PaymentLog)
    if school_id:
        stmt = stmt.where(PaymentLog.school_id == school_id)
        count_stmt = count_stmt.where(PaymentLog.school_id == school_id)
    stmt = stmt.order_by(PaymentLog.created_at.desc()).limit(limit).offset(offset)
    total = (await db.execute(count_stmt)).scalar_one()
    logs = list((await db.execute(stmt)).scalars().all())
    return logs, total


async def expire_inactive_schools(db: AsyncSession) -> int:
    """
    Deactivate schools whose subscription has expired.
    Call this from a scheduled job (e.g. APScheduler / cron).
    Returns the number of schools deactivated.
    """
    today = date.today()
    expired_subs = list(
        (
            await db.execute(
                select(SchoolSubscription).where(SchoolSubscription.subscription_end < today)
            )
        ).scalars().all()
    )
    count = 0
    for sub in expired_subs:
        school = (
            await db.execute(select(School).where(School.id == sub.school_id))
        ).scalars().first()
        if school and school.is_active:
            school.is_active = False
            count += 1
    if count:
        await db.commit()
    return count
