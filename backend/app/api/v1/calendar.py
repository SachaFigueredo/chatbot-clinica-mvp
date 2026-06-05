from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from app.api.deps import CurrentUser, SessionDep
from app.infrastructure.calendar.google import GoogleCalendarProvider

router = APIRouter(prefix="/calendar", tags=["calendar"])


# -- Dependencies -------------------------------------------------------------


async def get_calendar_provider(
    db: SessionDep,
    user: CurrentUser,
) -> GoogleCalendarProvider:
    """Build a GoogleCalendarProvider scoped to the current user's tenant."""
    return GoogleCalendarProvider(tenant_id=str(user.tenant_id), db=db)


CalendarProviderDep = Depends(get_calendar_provider)


# -- Schemas ------------------------------------------------------------------


class CallbackRequest(BaseModel):
    code: str


# -- Endpoints ----------------------------------------------------------------


@router.get("/auth-url")
async def get_auth_url(
    doctor_id: str | None = Query(None, description="Optional doctor UUID"),
    provider: GoogleCalendarProvider = CalendarProviderDep,
):
    """Return the Google OAuth 2.0 consent URL for the current tenant.

    The admin should redirect the user's browser to this URL so they can
    grant the application access to their Google Calendar.
    """
    try:
        url = await provider.get_auth_url(doctor_id=doctor_id)
        return {"url": url}
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        )


@router.post("/callback")
async def handle_callback(
    body: CallbackRequest,
    doctor_id: str | None = Query(None, description="Optional doctor UUID"),
    provider: GoogleCalendarProvider = CalendarProviderDep,
):
    """Exchange the OAuth authorization code for encrypted tokens.

    After the user grants permission on the Google consent page they are
    redirected here with a ``code`` query parameter.  This endpoint
    exchanges that code for access/refresh tokens, encrypts them with
    Fernet, and stores them in the database.
    """
    try:
        await provider.handle_callback(code=body.code, doctor_id=doctor_id)
        return {"message": "Calendar connected successfully"}
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )


@router.get("/status")
async def get_status(
    doctor_id: str | None = Query(None, description="Optional doctor UUID"),
    provider: GoogleCalendarProvider = CalendarProviderDep,
):
    """Return the current Google Calendar connection status."""
    try:
        status_obj = await provider.get_connection_status(doctor_id=doctor_id)
        return {
            "connected": status_obj.connected,
            "calendar_email": status_obj.calendar_email,
            "expires_at": status_obj.expires_at.isoformat() if status_obj.expires_at else None,
        }
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to check connection status: {exc}",
        )


@router.delete("/disconnect")
async def disconnect(
    doctor_id: str | None = Query(None, description="Optional doctor UUID"),
    provider: GoogleCalendarProvider = CalendarProviderDep,
):
    """Deactivate the stored tokens and disconnect the calendar.

    The token record is soft-deleted (``is_active = False``) so the
    connection can be audited later.
    """
    try:
        await provider.disconnect(doctor_id=doctor_id)
        return {"message": "Calendar disconnected successfully"}
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to disconnect calendar: {exc}",
        )
