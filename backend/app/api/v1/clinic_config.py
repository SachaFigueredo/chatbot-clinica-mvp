from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, SessionDep
from app.infrastructure.database.models.clinic_config import ClinicConfig
from app.infrastructure.database.models.tenant import Tenant

router = APIRouter(prefix="/clinic-config", tags=["clinic-config"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class DayHours(BaseModel):
    start: str = ""
    end: str = ""
    closed: bool = False


class Prices(BaseModel):
    particular: float = 0
    obras_sociales: float = 0


class ClinicConfigResponse(BaseModel):
    name: str
    address: str | None = None
    phone: str | None = None
    email: str | None = None
    business_hours: dict[str, DayHours] = {}
    appointment_duration_minutes: int = 20
    prices: Prices = Prices()
    welcome_message: str | None = None


class ClinicConfigUpdate(BaseModel):
    name: str | None = None
    address: str | None = None
    phone: str | None = None
    email: str | None = None
    business_hours: dict[str, dict] | None = None
    appointment_duration_minutes: int | None = None
    prices: dict | None = None
    welcome_message: str | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _day_hours_to_dict(hours: dict) -> dict[str, DayHours]:
    """Convert raw business_hours dict to DayHours objects."""
    result: dict[str, DayHours] = {}
    for day, config in (hours or {}).items():
        if isinstance(config, dict):
            result[day] = DayHours(
                start=config.get("start", ""),
                end=config.get("end", ""),
                closed=config.get("closed", False),
            )
    return result


async def _get_clinic_config_or_default(
    db: AsyncSession,
    tenant_id,
) -> tuple[ClinicConfig | None, Tenant]:
    """Get clinic config and tenant, return defaults if no config exists."""
    # Always load tenant for name.
    stmt_tenant = select(Tenant).where(Tenant.id == tenant_id)
    result = await db.execute(stmt_tenant)
    tenant = result.scalar_one_or_none()
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant not found")

    stmt = select(ClinicConfig).where(ClinicConfig.tenant_id == tenant_id)
    result = await db.execute(stmt)
    config = result.scalar_one_or_none()

    return config, tenant


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("", response_model=ClinicConfigResponse)
async def get_clinic_config(
    db: SessionDep,
    user: CurrentUser,
):
    """Return the clinic configuration for the current tenant.

    Includes the tenant name and all config fields. Missing optional
    fields return ``null``.  If no explicit config row exists, sensible
    defaults are returned based on the tenant name only.
    """
    config, tenant = await _get_clinic_config_or_default(db, user.tenant_id)

    return ClinicConfigResponse(
        name=tenant.name,
        address=config.address if config else None,
        phone=config.phone if config else None,
        email=config.email_contact if config else None,
        business_hours=_day_hours_to_dict(
            config.business_hours if config else None
        ),
        appointment_duration_minutes=(
            config.appointment_duration_minutes if config else 20
        ),
        prices=(
            Prices(
                particular=(config.prices.get("particular") or 0) if hasattr(config, "prices") and config.prices else 0,
                obras_sociales=(config.prices.get("obras_sociales") or 0) if hasattr(config, "prices") and config.prices else 0,
            )
            if config
            else Prices()
        ),
        welcome_message=config.welcome_message if config else None,
    )


@router.put("", response_model=ClinicConfigResponse)
async def update_clinic_config(
    body: ClinicConfigUpdate,
    db: SessionDep,
    user: CurrentUser,
):
    """Update the clinic configuration.

    Creates a config row if one doesn't exist yet.  Only provided
    fields are updated (partial update).
    """
    config, tenant = await _get_clinic_config_or_default(db, user.tenant_id)

    if config is None:
        config = ClinicConfig(tenant_id=user.tenant_id)
        db.add(config)

    # Update tenant name if provided
    if body.name is not None:
        tenant.name = body.name
        db.add(tenant)

    # Update config fields
    if body.address is not None:
        config.address = body.address
    if body.phone is not None:
        config.phone = body.phone
    if body.email is not None:
        config.email_contact = body.email
    if body.business_hours is not None:
        config.business_hours = body.business_hours
    if body.appointment_duration_minutes is not None:
        config.appointment_duration_minutes = body.appointment_duration_minutes
    if body.prices is not None:
        config.prices = body.prices
    if body.welcome_message is not None:
        config.welcome_message = body.welcome_message

    await db.commit()
    await db.refresh(config)

    return ClinicConfigResponse(
        name=tenant.name,
        address=config.address,
        phone=config.phone,
        email=config.email_contact,
        business_hours=_day_hours_to_dict(config.business_hours),
        appointment_duration_minutes=config.appointment_duration_minutes,
        prices=(
            Prices(
                particular=config.prices.get("particular", 0) if config.prices else 0,
                obras_sociales=config.prices.get("obras_sociales", 0) if config.prices else 0,
            )
        ),
        welcome_message=config.welcome_message,
    )
