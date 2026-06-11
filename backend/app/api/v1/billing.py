"""Billing API endpoints — Mercado Pago Checkout Pro subscription management.

All endpoints require authentication (any tenant user). The SubscriptionGuard
is intentionally NOT applied here so that suspended tenants can still access
billing to re-subscribe.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import SessionDep, CurrentUser
from app.domain.enums import TenantPlan, TenantStatus
from app.domain.services.billing_service import (
    BillingService,
    BillingServiceError,
)
from app.infrastructure.database.models.tenant import Tenant

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/billing", tags=["billing"])


# ---------------------------------------------------------------------------
# POST /billing/checkout — create MP subscription preapproval
# ---------------------------------------------------------------------------


@router.post("/checkout")
async def create_checkout(
    user: CurrentUser,
    db: SessionDep,
) -> dict[str, Any]:
    """Create an MP preapproval (recurring subscription checkout).

    Returns a ``preference_id`` and ``init_point`` URL that redirects the
    user to Mercado Pago's checkout. If the tenant already has an active
    subscription, returns **409 Conflict**.
    """
    result = await db.execute(
        select(Tenant).where(Tenant.id == user.tenant_id)
    )
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found",
        )

    # Reject if the tenant already has an active subscription
    if tenant.plan == TenantPlan.subscription and tenant.status == TenantStatus.active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Tenant already has an active subscription",
        )

    try:
        preapproval = await BillingService.create_preapproval(
            payer_email=user.email,
            external_reference=str(tenant.id),
            reason=f"Suscripción {tenant.name} - Chatbot Clínicas",
        )
    except BillingServiceError:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Payment provider error. Please try again later.",
        )

    # Store the preapproval ID on the tenant
    tenant.mercadopago_subscription_id = preapproval["id"]
    db.add(tenant)
    await db.commit()
    await db.refresh(tenant)

    logger.info(
        "Created preapproval %s for tenant %s",
        preapproval["id"],
        tenant.id,
    )

    return {
        "preference_id": preapproval["id"],
        "init_point": preapproval["init_point"],
    }


# ---------------------------------------------------------------------------
# GET /billing/status — current billing state
# ---------------------------------------------------------------------------


@router.get("/status")
async def get_billing_status(
    user: CurrentUser,
    db: SessionDep,
) -> dict[str, Any]:
    """Return the current billing status for the authenticated user's tenant.

    Includes plan, status, trial end date, days remaining in the trial,
    and the MP preapproval ID (if one exists).
    """
    result = await db.execute(
        select(Tenant).where(Tenant.id == user.tenant_id)
    )
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found",
        )

    # Calculate remaining trial days
    days_remaining: int | None = None
    if tenant.trial_ends_at is not None:
        trial_end = tenant.trial_ends_at
        if trial_end.tzinfo is None:
            trial_end = trial_end.replace(tzinfo=timezone.utc)
        remaining = (trial_end - datetime.now(timezone.utc)).days
        days_remaining = max(0, remaining)

    return {
        "plan": tenant.plan.value if hasattr(tenant.plan, "value") else tenant.plan,
        "status": tenant.status.value if hasattr(tenant.status, "value") else tenant.status,
        "trial_ends_at": (
            tenant.trial_ends_at.isoformat() if tenant.trial_ends_at else None
        ),
        "days_remaining": days_remaining,
        "mp_preference_id": tenant.mercadopago_subscription_id,
    }


# ---------------------------------------------------------------------------
# POST /billing/cancel — cancel subscription
# ---------------------------------------------------------------------------


@router.post("/cancel")
async def cancel_subscription(
    user: CurrentUser,
    db: SessionDep,
) -> dict[str, str]:
    """Cancel the tenant's subscription.

    Sets ``plan = cancelled`` and ``status = suspended``. Returns the
    new status.
    """
    result = await db.execute(
        select(Tenant).where(Tenant.id == user.tenant_id)
    )
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found",
        )

    tenant.plan = TenantPlan.cancelled
    tenant.status = TenantStatus.suspended
    tenant.suspended_at = datetime.now(timezone.utc)
    db.add(tenant)
    await db.commit()
    await db.refresh(tenant)

    logger.info("Cancelled subscription for tenant %s", tenant.id)

    return {"status": "cancelled"}
