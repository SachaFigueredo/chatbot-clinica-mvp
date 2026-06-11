from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.session import get_session
from app.infrastructure.database.models.user import User
from app.infrastructure.database.models.tenant import Tenant
from app.domain.enums import TenantPlan, TenantStatus, UserRole
from app.domain.services.auth_service import AuthService

bearer_scheme = HTTPBearer(auto_error=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async for session in get_session():
        yield session


SessionDep = Annotated[AsyncSession, Depends(get_db)]


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: SessionDep,
) -> User:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    try:
        payload = AuthService.decode_access_token(credentials.credentials)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    user_id: str | None = payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


# ---------------------------------------------------------------------------
# Subscription Guard
# ---------------------------------------------------------------------------


def check_subscription_access(
    plan: TenantPlan,
    status: TenantStatus,
    trial_ends_at: datetime | None,
) -> bool:
    """Determine if a tenant has access to restricted (non-billing) routes.

    Returns ``True`` if the tenant may pass, ``False`` if they should be
    blocked (402 Payment Required).

    Logic:
    - Paying subscribers (plan=subscription) are always allowed.
    - Active trial tenants are allowed (trial_ends_at is still in the future
      OR the Celery task hasn't suspended them yet).
    - Tenants with ``status != active`` whose trial has expired are blocked.
    """
    # Paying subscribers are always allowed.
    if plan == TenantPlan.subscription:
        return True

    # Active status means the tenant can access the system.
    if status == TenantStatus.active:
        return True

    # Suspended/cancelled tenants are blocked only if their trial has expired.
    if trial_ends_at is not None:
        now = datetime.now(timezone.utc)
        # SQLite may return naive datetimes; make comparison robust
        trial_end = trial_ends_at
        if trial_end.tzinfo is None:
            trial_end = trial_end.replace(tzinfo=timezone.utc)
        if trial_end < now:
            return False

    # Otherwise (e.g., suspended but still within trial period) — allowed.
    return True


async def get_subscription_guard(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: SessionDep,
) -> None:
    """FastAPI dependency: block requests from tenants with expired trials.

    Public/unauthenticated requests pass through (the route's own auth
    handling will reject them if needed).  Authenticated users whose
    tenant has an expired trial get 402 Payment Required.
    """
    # No auth → public endpoint → skip guard
    if credentials is None:
        return

    # Try to decode the token — if it's invalid, let the route handle auth
    try:
        payload = AuthService.decode_access_token(credentials.credentials)
    except Exception:
        return

    user_id: str | None = payload.get("sub")
    if user_id is None:
        return

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        return

    # Now check the tenant's subscription status
    result = await db.execute(
        select(Tenant).where(Tenant.id == user.tenant_id)
    )
    tenant = result.scalar_one_or_none()
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found",
        )

    if not check_subscription_access(tenant.plan, tenant.status, tenant.trial_ends_at):
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Subscription required. Trial has expired.",
        )


SubscriptionGuard = Annotated[None, Depends(get_subscription_guard)]


# ---------------------------------------------------------------------------
# Super Admin Guard
# ---------------------------------------------------------------------------


async def get_current_super_admin(
    user: CurrentUser,
) -> User:
    """FastAPI dependency: allow only super_admin users.

    Raises 403 Forbidden for non-super-admin users.
    """
    if user.role != UserRole.super_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Super admin access required",
        )
    return user


CurrentSuperAdmin = Annotated[User, Depends(get_current_super_admin)]
