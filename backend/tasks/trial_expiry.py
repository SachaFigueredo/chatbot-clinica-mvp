"""Celery periodic task for trial expiry suspension.

Finds tenants whose trial has ended (trial_ends_at < now AND status=active)
and suspends them by setting status=suspended. Runs daily via Celery Beat.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from celery import shared_task
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.config import settings
from app.domain.enums import TenantPlan, TenantStatus
from app.infrastructure.database.models.tenant import Tenant
from app.infrastructure.database.models.audit_log import AuditLog

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Sync engine for Celery workers
# ---------------------------------------------------------------------------

_SYNC_DATABASE_URL = settings.database_url.replace("+asyncpg", "+psycopg2")
_sync_engine = create_engine(_SYNC_DATABASE_URL)


def _get_sync_session() -> Session:
    """Return a new synchronous SQLAlchemy session for Celery tasks."""
    return Session(_sync_engine)


# ---------------------------------------------------------------------------
# Pure logic
# ---------------------------------------------------------------------------


def is_trial_expired(
    plan: TenantPlan,
    status: TenantStatus,
    trial_ends_at: datetime | None,
) -> bool:
    """Determine if a tenant's trial has expired and should be suspended.

    Returns ``True`` when the tenant is a trial user whose trial period
    has passed and who still has active status (i.e., hasn't been suspended
    yet by a previous task run).
    """
    if plan != TenantPlan.trial:
        return False
    if status != TenantStatus.active:
        return False
    if trial_ends_at is None:
        return False

    # SQLite may return naive datetimes; make comparison robust
    trial_end = trial_ends_at
    if trial_end.tzinfo is None:
        trial_end = trial_end.replace(tzinfo=timezone.utc)

    return trial_end < datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Task
# ---------------------------------------------------------------------------


@shared_task(name="tasks.trial_expiry.check_trial_expiry")
def check_trial_expiry() -> None:
    """Find active tenants with expired trials and suspend them.

    Runs daily via Celery Beat. Processes all eligible tenants in a single
    transaction.
    """
    logger.info("[trial_expiry] Starting daily trial expiry check")
    session = _get_sync_session()
    try:
        # Find active trial tenants whose trial has ended
        now = datetime.now(timezone.utc)
        stmt = (
            select(Tenant)
            .where(
                Tenant.status == TenantStatus.active,
                Tenant.plan == TenantPlan.trial,
                Tenant.trial_ends_at.isnot(None),
            )
            .execution_options(stream_results=False)
        )
        tenants = list(session.execute(stmt).scalars().all())
        logger.info("[trial_expiry] Found %d active trial tenants", len(tenants))

        suspended_count = 0
        for tenant in tenants:
            # Check if trial is expired (handle naive/aware datetime)
            trial_end = tenant.trial_ends_at
            if trial_end is not None:
                if trial_end.tzinfo is None:
                    trial_end = trial_end.replace(tzinfo=timezone.utc)
                if trial_end >= now:
                    continue  # trial still valid

            # Suspend the tenant
            tenant.status = TenantStatus.suspended
            tenant.suspended_at = now
            session.add(tenant)

            # Audit log
            audit = AuditLog(
                tenant_id=tenant.id,
                action="trial_expired",
                entity_type="tenant",
                entity_id=str(tenant.id),
                details={
                    "plan": str(tenant.plan),
                    "trial_ends_at": str(tenant.trial_ends_at),
                },
            )
            session.add(audit)

            suspended_count += 1
            logger.info(
                "[trial_expiry] Suspended tenant %s (%s) — trial ended",
                tenant.id, tenant.slug,
            )

        session.commit()
        logger.info(
            "[trial_expiry] Completed — %d tenants suspended",
            suspended_count,
        )

    except Exception:
        logger.exception("[trial_expiry] Unhandled error")
        session.rollback()
        raise
    finally:
        session.close()
