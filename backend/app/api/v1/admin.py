"""Super Admin API — cross-tenant management.

All endpoints require ``super_admin`` role (enforced via
``CurrentSuperAdmin`` dependency). No subscription guard is applied so
that super admins can manage tenants regardless of their own subscription
status.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select

from app.api.deps import SessionDep, CurrentSuperAdmin
from app.domain.enums import TenantPlan, TenantStatus
from app.infrastructure.database.models.tenant import Tenant

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])

_DEFAULT_TRIAL_EXTENSION_DAYS = 7


# ---------------------------------------------------------------------------
# GET /admin/tenants — list tenants
# ---------------------------------------------------------------------------


@router.get("/tenants")
async def list_tenants(
    admin: CurrentSuperAdmin,
    db: SessionDep,
    status: str | None = Query(None, description="Filter by status"),
    plan: str | None = Query(None, description="Filter by plan"),
) -> list[dict[str, Any]]:
    """List all tenants with optional filters.

    Super admins can filter by ``status`` (active, suspended, cancelled)
    and/or ``plan`` (trial, subscription, basic, professional, premium,
    cancelled).
    """
    query = select(Tenant).order_by(Tenant.created_at.desc())

    if status:
        query = query.where(Tenant.status == status)
    if plan:
        query = query.where(Tenant.plan == plan)

    result = await db.execute(query)
    tenants = result.scalars().all()

    return [
        {
            "id": str(t.id),
            "name": t.name,
            "slug": t.slug,
            "plan": t.plan.value if hasattr(t.plan, "value") else t.plan,
            "status": t.status.value if hasattr(t.status, "value") else t.status,
            "trial_ends_at": (
                t.trial_ends_at.isoformat() if t.trial_ends_at else None
            ),
            "mercadopago_subscription_id": t.mercadopago_subscription_id,
            "suspended_at": (
                t.suspended_at.isoformat() if t.suspended_at else None
            ),
            "created_at": t.created_at.isoformat() if t.created_at else None,
        }
        for t in tenants
    ]


# ---------------------------------------------------------------------------
# POST /admin/tenants/{id}/suspend
# ---------------------------------------------------------------------------


@router.post("/tenants/{tenant_id}/suspend")
async def suspend_tenant(
    tenant_id: UUID,
    admin: CurrentSuperAdmin,
    db: SessionDep,
) -> dict[str, str]:
    """Manually suspend a tenant.

    Sets status to ``suspended`` and records the suspension timestamp.
    """
    result = await db.execute(
        select(Tenant).where(Tenant.id == tenant_id)
    )
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found",
        )

    tenant.status = TenantStatus.suspended
    tenant.suspended_at = datetime.now(timezone.utc)
    db.add(tenant)
    await db.commit()

    logger.info("Admin %s suspended tenant %s", admin.id, tenant_id)
    return {"status": "suspended"}


# ---------------------------------------------------------------------------
# POST /admin/tenants/{id}/activate
# ---------------------------------------------------------------------------


class ActivateTenantRequest(BaseModel):
    """Optional request body for activating a tenant."""

    # For Pydantic v2, use model_config for extra fields if needed
    trial_days: int | None = None


@router.post("/tenants/{tenant_id}/activate")
async def activate_tenant(
    tenant_id: UUID,
    admin: CurrentSuperAdmin,
    db: SessionDep,
    body: ActivateTenantRequest | None = None,
) -> dict[str, Any]:
    """Activate a suspended tenant.

    Optionally extends the trial by ``trial_days`` (default 7). Returns
    the new status and ``trial_ends_at``.
    """
    result = await db.execute(
        select(Tenant).where(Tenant.id == tenant_id)
    )
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found",
        )

    trial_days = (body.trial_days if body and body.trial_days is not None
                  else _DEFAULT_TRIAL_EXTENSION_DAYS)
    trial_ends_at = datetime.now(timezone.utc) + timedelta(days=trial_days)

    tenant.status = TenantStatus.active
    tenant.trial_ends_at = trial_ends_at
    db.add(tenant)
    await db.commit()
    await db.refresh(tenant)

    logger.info(
        "Admin %s activated tenant %s (trial +%d days)",
        admin.id,
        tenant_id,
        trial_days,
    )

    return {
        "status": "active",
        "trial_ends_at": trial_ends_at.isoformat(),
    }


# ---------------------------------------------------------------------------
# POST /admin/tenants/{id}/mark-paid
# ---------------------------------------------------------------------------


class MarkPaidRequest(BaseModel):
    """Optional note for manual payment marking."""

    note: str | None = None


@router.post("/tenants/{tenant_id}/mark-paid")
async def mark_tenant_paid(
    tenant_id: UUID,
    admin: CurrentSuperAdmin,
    db: SessionDep,
    body: MarkPaidRequest | None = None,
) -> dict[str, str]:
    """Manually mark a tenant as paid (subscription override).

    Sets plan to ``subscription`` and status to ``active`` without
    involving Mercado Pago. Useful for manual payments, comped accounts,
    or fixing billing issues.
    """
    result = await db.execute(
        select(Tenant).where(Tenant.id == tenant_id)
    )
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found",
        )

    tenant.plan = TenantPlan.subscription
    tenant.status = TenantStatus.active
    tenant.suspended_at = None
    db.add(tenant)
    await db.commit()

    logger.info(
        "Admin %s marked tenant %s as paid (note: %s)",
        admin.id,
        tenant_id,
        body.note if body and body.note else "none",
    )

    return {
        "plan": "subscription",
        "status": "active",
    }
