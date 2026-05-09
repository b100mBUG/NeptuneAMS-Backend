from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field


class InitiatePaymentRequest(BaseModel):
    """Platform initiates payment for a school — email is required for Paystack."""
    email: str = Field(..., description="Billing contact email sent to Paystack")


class InitiatePaymentResponse(BaseModel):
    authorization_url: str
    access_code: str
    reference: str
    amount: int           # KES (human-readable)
    student_count: int


class PaymentVerifyResponse(BaseModel):
    success: bool
    message: str
    school_id: str
    amount_paid: int      # KES
    student_count: int
    subscription_start: Optional[date]
    subscription_end: Optional[date]


class PaymentLogResponse(BaseModel):
    id: str
    school_id: str
    paystack_reference: str
    amount: int           # KES
    student_count: int
    status: str
    gateway_response: Optional[str]
    paid_at: Optional[datetime]
    created_at: datetime

    model_config = {"from_attributes": True}


class SubscriptionResponse(BaseModel):
    school_id: str
    school_name: str
    is_active: bool
    subscription_start: Optional[date]
    subscription_end: Optional[date]
    student_count_at_payment: int
    amount_paid: int      # KES
    is_expired: bool
    days_remaining: Optional[int]

    model_config = {"from_attributes": True}
