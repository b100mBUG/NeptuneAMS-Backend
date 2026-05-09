"""
Payments router.

Endpoints:
  POST /platform/schools/{school_id}/payments/initiate  → start Paystack transaction
  GET  /platform/schools/{school_id}/payments/verify    → verify by reference
  GET  /platform/schools/{school_id}/payments/logs      → payment history (platform)
  GET  /platform/schools/{school_id}/subscription       → subscription status (platform)
  GET  /platform/payments/logs                          → all logs (platform)

  GET  /schools/me/subscription                         → subscription status (school admin)
  GET  /schools/me/payments/logs                        → payment history (school admin)

  POST /payments/webhook                                → Paystack webhook (no auth)
"""
import hashlib
import hmac
import json
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from rate_limit import PAYMENT_LIMIT, limiter
from actions.payments import (
    get_subscription,
    initiate_paystack_payment,
    list_payment_logs,
    verify_paystack_payment,
)
from auth import get_current_admin, get_current_platform
from config_db import get_db
from database.models import Admin, PaymentLog
from schemas.payments import (
    InitiatePaymentRequest,
    InitiatePaymentResponse,
    PaymentLogResponse,
    PaymentVerifyResponse,
    SubscriptionResponse,
)
from settings import get_settings

router = APIRouter(tags=["Payments"])

DB          = Annotated[AsyncSession, Depends(get_db)]
PlatformDep = Annotated[dict, Depends(get_current_platform)]
AdminDep    = Annotated[Admin, Depends(get_current_admin)]


def _log_to_response(log: PaymentLog) -> PaymentLogResponse:
    """Convert a PaymentLog ORM object to the response schema (amount in KES)."""
    return PaymentLogResponse(
        id=log.id,
        school_id=log.school_id,
        paystack_reference=log.paystack_reference,
        amount=log.amount // 100,
        student_count=log.student_count,
        status=log.status,
        gateway_response=log.gateway_response,
        paid_at=log.paid_at,
        created_at=log.created_at,
    )


# ─── Platform endpoints ───────────────────────────────────────────────────────

@router.post(
    "/platform/schools/{school_id}/payments/initiate",
    response_model=InitiatePaymentResponse,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit(PAYMENT_LIMIT)
async def platform_initiate_payment(
    request: Request,
    school_id: str,
    body: InitiatePaymentRequest,
    db: DB,
    _: PlatformDep,
):
    try:
        result = await initiate_paystack_payment(db, school_id, body.email)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Paystack error: {e}")
    return InitiatePaymentResponse(**result)


@router.get(
    "/platform/schools/{school_id}/payments/verify",
    response_model=PaymentVerifyResponse,
)
async def platform_verify_payment(
    school_id: str,
    db: DB,
    _: PlatformDep,
    reference: str = Query(..., description="Paystack transaction reference"),
):
    try:
        result = await verify_paystack_payment(db, reference)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Paystack error: {e}")
    return PaymentVerifyResponse(**result)


@router.get(
    "/platform/schools/{school_id}/payments/logs",
    response_model=list[PaymentLogResponse],
)
async def platform_payment_logs(
    school_id: str,
    db: DB,
    _: PlatformDep,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    logs, _ = await list_payment_logs(db, school_id=school_id, limit=limit, offset=offset)
    return [_log_to_response(log) for log in logs]


@router.get(
    "/platform/schools/{school_id}/subscription",
    response_model=SubscriptionResponse,
)
async def platform_school_subscription(school_id: str, db: DB, _: PlatformDep):
    sub = await get_subscription(db, school_id)
    if not sub:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="School not found")
    return SubscriptionResponse(**sub)


# ─── Platform-wide logs ───────────────────────────────────────────────────────

@router.get("/platform/payments/logs", response_model=list[PaymentLogResponse])
async def platform_all_payment_logs(
    db: DB,
    _: PlatformDep,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    logs, _ = await list_payment_logs(db, school_id=None, limit=limit, offset=offset)
    return [_log_to_response(log) for log in logs]


# ─── School admin endpoints ───────────────────────────────────────────────────

@router.post("/schools/me/payments/initiate", response_model=InitiatePaymentResponse,
             status_code=status.HTTP_201_CREATED)
@limiter.limit(PAYMENT_LIMIT)
async def admin_initiate_payment(
    request: Request,
    body: InitiatePaymentRequest,
    db: DB,
    admin: AdminDep,
):
    """School admin initiates payment for their own school."""
    try:
        result = await initiate_paystack_payment(db, admin.school_id, body.email)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Paystack error: {e}")
    return InitiatePaymentResponse(**result)


@router.get("/schools/me/payments/verify", response_model=PaymentVerifyResponse)
async def admin_verify_payment(
    db: DB,
    admin: AdminDep,
    reference: str = Query(..., description="Paystack transaction reference"),
):
    """School admin verifies their own payment."""
    try:
        result = await verify_paystack_payment(db, reference)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Paystack error: {e}")
    return PaymentVerifyResponse(**result)


@router.get("/schools/me/subscription", response_model=SubscriptionResponse)
async def admin_subscription(db: DB, admin: AdminDep):
    sub = await get_subscription(db, admin.school_id)
    if not sub:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="School not found")
    return SubscriptionResponse(**sub)


@router.get("/schools/me/payments/logs", response_model=list[PaymentLogResponse])
async def admin_payment_logs(
    db: DB,
    admin: AdminDep,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    logs, _ = await list_payment_logs(db, school_id=admin.school_id, limit=limit, offset=offset)
    return [_log_to_response(log) for log in logs]


# ─── Paystack Webhook ─────────────────────────────────────────────────────────

@router.post("/payments/webhook", status_code=status.HTTP_200_OK)
async def paystack_webhook(request: Request, db: DB):
    settings = get_settings()
    body = await request.body()

    paystack_sig = request.headers.get("x-paystack-signature", "")
    expected_sig = hmac.new(
        settings.paystack_secret_key.encode(),
        body,
        hashlib.sha512,
    ).hexdigest()

    if not hmac.compare_digest(expected_sig, paystack_sig):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid signature")

    payload = json.loads(body)
    if payload.get("event") == "charge.success":
        reference = payload.get("data", {}).get("reference", "")
        if reference:
            try:
                await verify_paystack_payment(db, reference)
            except Exception:
                pass

    return {"status": "ok"}
