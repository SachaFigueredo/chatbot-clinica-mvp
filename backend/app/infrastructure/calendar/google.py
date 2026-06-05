from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any

import httpx
from cryptography.fernet import Fernet
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.domain.interfaces.calendar import CalendarProvider
from app.infrastructure.calendar.models import AvailableSlot, ConnectionStatus
from app.infrastructure.database.models.clinic_config import ClinicConfig
from app.infrastructure.database.models.google_calendar_token import GoogleCalendarToken

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_CALENDAR_BASE = "https://www.googleapis.com/calendar/v3"

SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/calendar.events",
]

# How finely to slice the business day when searching for free slots (minutes).
SLOT_GRANULARITY_MINUTES = 15

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_fernet() -> Fernet:
    if not settings.encryption_key:
        raise RuntimeError("ENCRYPTION_KEY is not configured")
    return Fernet(settings.encryption_key.encode())


def _encrypt_token(raw: str) -> str:
    return _get_fernet().encrypt(raw.encode()).decode()


def _decrypt_token(encrypted: str) -> str:
    return _get_fernet().decrypt(encrypted.encode()).decode()


def _day_name(date: date) -> str:
    """Return the lowercase English day name (e.g. 'monday') for *date*."""
    return date.strftime("%A").lower()


# ---------------------------------------------------------------------------
# Provider
# ---------------------------------------------------------------------------


class GoogleCalendarProvider(CalendarProvider):
    """Google Calendar API adapter implementing CalendarProvider.

    Requires a tenant context and an active async DB session so it can
    persist / retrieve OAuth tokens transparently.
    """

    def __init__(self, tenant_id: str, db: AsyncSession) -> None:
        self._tenant_id = tenant_id
        self._db = db

    # -- tokens ----------------------------------------------------------------

    async def _get_token(self, doctor_id: str | None) -> GoogleCalendarToken | None:
        stmt = select(GoogleCalendarToken).where(
            GoogleCalendarToken.tenant_id == uuid.UUID(self._tenant_id),
            GoogleCalendarToken.is_active.is_(True),
        )
        if doctor_id:
            stmt = stmt.where(GoogleCalendarToken.doctor_id == doctor_id)
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def _ensure_valid_token(
        self, doctor_id: str | None
    ) -> GoogleCalendarToken:
        token = await self._get_token(doctor_id)
        if token is None:
            raise ConnectionError(
                "No active Google Calendar connection found. "
                "Connect your calendar from the settings panel first."
            )

        # Refresh if expired or about to expire (within 5 minutes).
        if token.token_expiry and token.refresh_token:
            now = datetime.now(timezone.utc)
            if token.token_expiry.replace(tzinfo=timezone.utc) <= now + timedelta(
                minutes=5
            ):
                await self._refresh_token(token)

        return token

    async def _refresh_token(self, token: GoogleCalendarToken) -> None:
        refresh_token = _decrypt_token(token.refresh_token)
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                GOOGLE_TOKEN_URL,
                data={
                    "client_id": settings.google_client_id,
                    "client_secret": settings.google_client_secret,
                    "refresh_token": refresh_token,
                    "grant_type": "refresh_token",
                },
            )
        if resp.status_code != 200:
            token.is_active = False
            await self._db.commit()
            raise ConnectionError(
                "Failed to refresh Google Calendar token. "
                "Please reconnect your calendar from the settings panel."
            )

        data = resp.json()
        new_access = data.get("access_token", "")
        token.access_token = _encrypt_token(new_access)
        # Google may or may not return a new refresh token.
        if "refresh_token" in data:
            token.refresh_token = _encrypt_token(data["refresh_token"])

        expires_in = data.get("expires_in", 3600)
        token.token_expiry = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
        await self._db.commit()
        await self._db.refresh(token)

    async def _get_headers(self, doctor_id: str | None) -> dict[str, str]:
        token = await self._ensure_valid_token(doctor_id)
        access_token = _decrypt_token(token.access_token)
        return {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

    async def _get_calendar_id(self, doctor_id: str | None) -> str:
        token = await self._ensure_valid_token(doctor_id)
        return token.calendar_id

    # -- OAuth 2.0 ------------------------------------------------------------

    async def get_auth_url(self, doctor_id: str | None = None) -> str:
        if not settings.google_client_id:
            raise RuntimeError("GOOGLE_CLIENT_ID is not configured")

        params = {
            "client_id": settings.google_client_id,
            "redirect_uri": settings.google_redirect_uri,
            "response_type": "code",
            "scope": " ".join(SCOPES),
            "access_type": "offline",
            "prompt": "consent",
        }
        if doctor_id:
            params["state"] = doctor_id

        query_string = str(httpx.QueryParams(params))
        return f"{GOOGLE_AUTH_URL}?{query_string}"

    async def handle_callback(self, code: str, doctor_id: str | None = None) -> None:
        if not settings.google_client_id or not settings.google_client_secret:
            raise RuntimeError("Google OAuth credentials are not configured")

        # Exchange authorization code for tokens.
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                GOOGLE_TOKEN_URL,
                data={
                    "code": code,
                    "client_id": settings.google_client_id,
                    "client_secret": settings.google_client_secret,
                    "redirect_uri": settings.google_redirect_uri,
                    "grant_type": "authorization_code",
                },
            )

        if resp.status_code != 200:
            raise RuntimeError(
                f"Failed to exchange authorization code: {resp.text}"
            )

        data = resp.json()
        access_token = data.get("access_token", "")
        refresh_token = data.get("refresh_token", "")
        expires_in = data.get("expires_in", 3600)

        # Use the access token to discover the primary calendar email.
        calendar_id = "primary"
        calendar_email = None
        async with httpx.AsyncClient() as client:
            cal_resp = await client.get(
                f"{GOOGLE_CALENDAR_BASE}/users/me/calendarList/primary",
                headers={"Authorization": f"Bearer {access_token}"},
            )
        if cal_resp.status_code == 200:
            cal_data = cal_resp.json()
            calendar_id = cal_data.get("id", "primary")
            calendar_email = cal_data.get("summary", None)

        # Persist encrypted tokens.
        doctor_uuid = uuid.UUID(doctor_id) if doctor_id else None

        # Deactivate any existing active token for this doctor.
        existing = await self._get_token(doctor_id)
        if existing:
            existing.is_active = False
            self._db.add(existing)
            await self._db.flush()

        token_record = GoogleCalendarToken(
            tenant_id=uuid.UUID(self._tenant_id),
            doctor_id=doctor_uuid,
            calendar_id=calendar_id,
            access_token=_encrypt_token(access_token),
            refresh_token=_encrypt_token(refresh_token) if refresh_token else None,
            token_expiry=datetime.now(timezone.utc) + timedelta(seconds=expires_in),
            calendar_email=calendar_email,
            is_active=True,
        )
        self._db.add(token_record)
        await self._db.commit()

    # -- Availability ---------------------------------------------------------

    async def get_available_slots(
        self,
        doctor_id: str | None,
        day: date,
        duration_minutes: int,
    ) -> list[AvailableSlot]:
        headers = await self._get_headers(doctor_id)
        calendar_id = await self._get_calendar_id(doctor_id)

        # 1. Fetch existing events for the day.
        day_start = datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc)
        day_end = day_start + timedelta(days=1)

        async with httpx.AsyncClient() as client:
            events_resp = await client.get(
                f"{GOOGLE_CALENDAR_BASE}/calendars/{httpx.URL(calendar_id).path}/events",
                headers=headers,
                params={
                    "timeMin": day_start.isoformat(),
                    "timeMax": day_end.isoformat(),
                    "singleEvents": "true",
                    "orderBy": "startTime",
                },
            )

        if events_resp.status_code == 401:
            raise ConnectionError("Token expired — please reconnect your calendar.")
        if events_resp.status_code == 404:
            raise ConnectionError("Calendar not found — it may have been deleted.")
        if events_resp.status_code != 200:
            raise RuntimeError(
                f"Google Calendar API error: {events_resp.status_code} {events_resp.text}"
            )

        events_data = events_resp.json()
        busy_ranges: list[tuple[datetime, datetime]] = []
        for item in events_data.get("items", []):
            start_str = item.get("start", {}).get("dateTime") or item.get("start", {}).get("date")
            end_str = item.get("end", {}).get("dateTime") or item.get("end", {}).get("date")
            if start_str and end_str:
                start_dt = datetime.fromisoformat(start_str)
                end_dt = datetime.fromisoformat(end_str)
                # If the event is all-day, it will have date only (no time).
                # Skip all-day events for slot calculation — they aren't real occupied slots.
                if "T" not in start_str:
                    continue
                busy_ranges.append((start_dt, end_dt))

        # 2. Get business hours.
        business_start, business_end = await self._get_business_hours(day)

        # 3. Generate candidate slots at SLOT_GRANULARITY resolution.
        candidates: list[AvailableSlot] = []
        current = max(day_start, business_start)
        period_end = min(day_end, business_end)

        while current + timedelta(minutes=duration_minutes) <= period_end:
            slot_end = current + timedelta(minutes=duration_minutes)

            # Check overlap with any busy range.
            overlaps = any(
                not (slot_end <= busy_start or current >= busy_end)
                for busy_start, busy_end in busy_ranges
            )

            if not overlaps:
                candidates.append(AvailableSlot(start_time=current, end_time=slot_end))

            current += timedelta(minutes=SLOT_GRANULARITY_MINUTES)

        return candidates

    async def _get_business_hours(self, day: date) -> tuple[datetime, datetime]:
        """Return (start_datetime, end_datetime) for business hours on *day*."""
        stmt = select(ClinicConfig).where(
            ClinicConfig.tenant_id == uuid.UUID(self._tenant_id)
        )
        result = await self._db.execute(stmt)
        config = result.scalar_one_or_none()

        if config is None or not config.business_hours:
            # Default: 08:00 – 17:00
            start_h, start_m = 8, 0
            end_h, end_m = 17, 0
        else:
            day_name = _day_name(day)
            day_schedule = config.business_hours.get(day_name, {})
            if not day_schedule:
                # Clinic is closed on this day — return zero-length range.
                dt = datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc)
                return dt, dt

            start_str = day_schedule.get("start", "08:00")
            end_str = day_schedule.get("end", "17:00")
            start_h, start_m = (int(x) for x in start_str.split(":"))
            end_h, end_m = (int(x) for x in end_str.split(":"))

        start_dt = datetime.combine(
            day, datetime.min.time().replace(hour=start_h, minute=start_m), tzinfo=timezone.utc
        )
        end_dt = datetime.combine(
            day, datetime.min.time().replace(hour=end_h, minute=end_m), tzinfo=timezone.utc
        )
        return start_dt, end_dt

    # -- Events ---------------------------------------------------------------

    async def create_event(
        self,
        doctor_id: str | None,
        patient_name: str,
        patient_phone: str,
        reason: str | None,
        start_time: datetime,
        end_time: datetime,
    ) -> str:
        headers = await self._get_headers(doctor_id)
        calendar_id = await self._get_calendar_id(doctor_id)

        body: dict[str, Any] = {
            "summary": f"[Paciente] {patient_name}",
            "description": (
                f"Tel: {patient_phone}\n"
                f"Motivo: {reason or 'No especificado'}"
            ),
            "start": {
                "dateTime": start_time.isoformat(),
                "timeZone": "America/Argentina/Buenos_Aires",
            },
            "end": {
                "dateTime": end_time.isoformat(),
                "timeZone": "America/Argentina/Buenos_Aires",
            },
        }

        max_retries = 2
        last_error: Exception | None = None

        for attempt in range(max_retries):
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.post(
                        f"{GOOGLE_CALENDAR_BASE}/calendars/{httpx.URL(calendar_id).path}/events",
                        headers=headers,
                        json=body,
                    )

                if resp.status_code == 200:
                    data = resp.json()
                    return data.get("id", "")

                # Retry on 5xx (server errors)
                if resp.status_code >= 500 and attempt < max_retries - 1:
                    last_error = RuntimeError(
                        f"Google Calendar server error (attempt {attempt + 1}): {resp.status_code}"
                    )
                    continue

                raise RuntimeError(
                    f"Failed to create calendar event: {resp.status_code} {resp.text}"
                )

            except (httpx.TimeoutException, httpx.NetworkError) as e:
                last_error = e
                if attempt < max_retries - 1:
                    continue
                raise RuntimeError(
                    f"Failed to create calendar event after {max_retries} attempts: {e}"
                )

        # If we exhausted retries without returning or raising
        raise RuntimeError(
            f"Failed to create calendar event after {max_retries} attempts"
        ) from last_error

    async def delete_event(self, doctor_id: str | None, event_id: str) -> None:
        headers = await self._get_headers(doctor_id)
        calendar_id = await self._get_calendar_id(doctor_id)

        async with httpx.AsyncClient() as client:
            resp = await client.delete(
                f"{GOOGLE_CALENDAR_BASE}/calendars/{httpx.URL(calendar_id).path}/events/{event_id}",
                headers=headers,
            )

        if resp.status_code == 404:
            # Event already gone — not an error.
            return
        if resp.status_code != 204:
            raise RuntimeError(
                f"Failed to delete calendar event: {resp.status_code} {resp.text}"
            )

    # -- Status / Disconnect --------------------------------------------------

    async def get_connection_status(self, doctor_id: str | None) -> ConnectionStatus:
        token = await self._get_token(doctor_id)
        if token is None or not token.is_active:
            return ConnectionStatus(connected=False)

        # If the token has expired and we cannot refresh, report disconnected.
        if token.token_expiry and token.refresh_token:
            try:
                await self._ensure_valid_token(doctor_id)
            except ConnectionError:
                return ConnectionStatus(connected=False)

        return ConnectionStatus(
            connected=True,
            calendar_email=token.calendar_email,
            expires_at=token.token_expiry.replace(tzinfo=timezone.utc) if token.token_expiry else None,
        )

    async def disconnect(self, doctor_id: str | None) -> None:
        token = await self._get_token(doctor_id)
        if token is None:
            return  # Already disconnected.

        token.is_active = False
        self._db.add(token)
        await self._db.commit()
