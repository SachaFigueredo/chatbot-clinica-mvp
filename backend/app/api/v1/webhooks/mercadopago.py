"""Mercado Pago webhook — subscription lifecycle notifications.

Receives IPN (Instant Payment Notification) events for Checkout Pro
subscriptions (preapprovals). Verifies the ``X-Signature`` header via
HMAC-SHA256 before processing.

No authentication is required — MP sends these directly. The signature
verification is the sole authentication mechanism.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select

from app.api.deps import SessionDep
from app.domain.enums import TenantPlan, TenantStatus
from app.domain.services.billing_service import BillingService
from app.infrastructure.database.models.tenant import Tenant

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


SUBSCRIPTION_EVENTS = frozenset({
    "subscription_authorized",
    "subscription_cancelled",
    "subscription_updated",
})

PAYMENT_EVENTS = frozenset({
    "payment",
})


@router.post("/mercadopago")
async def receive_mp_webhook(
    request: Request,
    db: SessionDep,
) -> dict[str, str]:
    """Receive and process Mercado Pago subscription notifications.

    Steps:
    1. Read the raw request body.
    2. Verify the ``X-Signature`` HMAC-SHA256 header.
    3. Match the event to a tenant via ``mercadopago_subscription_id``.
    4. Update the tenant's plan/status accordingly.

    Returns ``{"status": "ok"}`` after processing (MP expects 200 for
    successful delivery). On signature mismatch returns **401**.
    """
    raw_body = await request.body()

    # 1. Signature verification
    x_signature = request.headers.get("X-Signature", "")
    x_request_id = request.headers.get("X-Request-Id", None)

    if not BillingService.verify_webhook_signature(raw_body, x_signature, x_request_id):
        logger.warning("Invalid MP webhook signature")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook signature",
        )

    # 2. Parse the event
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON body",
        )

    event_type: str = payload.get("type", "")
    action: str = payload.get("action", "")
    event_data: dict = payload.get("data", {})
    subscription_id: str | None = event_data.get("id")

    logger.info(
        "MP webhook: type=%s action=%s data_id=%s",
        event_type,
        action,
        subscription_id,
    )

    # 3. Look up the tenant by mercadopago_subscription_id
    if not subscription_id:
        logger.warning("Webhook has no data.id — ignoring")
        return {"status": "ok"}

    result = await db.execute(
        select(Tenant).where(
            Tenant.mercadopago_subscription_id == subscription_id
        )
    )
    tenant = result.scalar_one_or_none()

    if not tenant:
        # Try matching by external_reference from payment events
        if event_type in PAYMENT_EVENTS:
            payment_id = subscription_id
            try:
                payment = await BillingService.get_payment(payment_id)
            except Exception:
                logger.exception("Failed to fetch payment %s", payment_id)
                return {"status": "ok"}

            external_ref = payment.get("external_reference")
            if external_ref:
                result = await db.execute(
                    select(Tenant).where(Tenant.id == external_ref)
                )
                tenant = result.scalar_one_or_none()

        if not tenant:
            logger.warning(
                "No tenant found for subscription %s", subscription_id
            )
            return {"status": "ok"}

    # 4. Process the event
    if event_type == "subscription_authorized" or action == "subscription.authorized":
        tenant.plan = TenantPlan.subscription
        tenant.status = TenantStatus.active
        db.add(tenant)
        await db.commit()
        logger.info("Activated subscription for tenant %s", tenant.id)

    elif event_type == "subscription_cancelled" or action == "subscription.cancelled":
        tenant.status = TenantStatus.suspended
        tenant.suspended_at = datetime.now(timezone.utc)
        db.add(tenant)
        await db.commit()
        logger.info("Suspended subscription for tenant %s", tenant.id)

    else:
        # Payment events: check payment status
        if event_type in PAYMENT_EVENTS:
            payment_id = subscription_id
            try:
                payment = await BillingService.get_payment(payment_id)
            except Exception:
                logger.exception("Failed to fetch payment %s", payment_id)
                return {"status": "ok"}

            payment_status = payment.get("status", "")
            if payment_status == "approved":
                tenant.plan = TenantPlan.subscription
                tenant.status = TenantStatus.active
                # Store the preapproval ID if available
                preapproval_id = payment.get("preapproval_id")
                if preapproval_id:
                    tenant.mercadopago_subscription_id = preapproval_id
                db.add(tenant)
                await db.commit()
                logger.info("Payment approved for tenant %s", tenant.id)

            elif payment_status in ("refunded", "cancelled", "charged_back"):
                tenant.status = TenantStatus.suspended
                tenant.suspended_at = datetime.now(timezone.utc)
                db.add(tenant)
                await db.commit()
                logger.info("Payment %s for tenant %s", payment_status, tenant.id)

        else:
            logger.debug("Ignoring unhandled event type: %s", event_type)

    return {"status": "ok"}
