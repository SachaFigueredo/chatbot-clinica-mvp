from __future__ import annotations

import csv
import io
import logging
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Response, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentUser, SessionDep
from app.domain.enums import AppointmentStatus
from app.infrastructure.calendar.google import GoogleCalendarProvider
from app.infrastructure.database.models.appointment import Appointment
from app.infrastructure.database.models.audit_log import AuditLog
from app.infrastructure.database.models.doctor import Doctor
from app.infrastructure.database.models.patient import Patient

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/appointments", tags=["appointments"])

# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class PatientSummary(BaseModel):
    id: str
    name: str | None
    phone_number: str


class DoctorSummary(BaseModel):
    id: str
    name: str
    specialty: str


class AppointmentItem(BaseModel):
    id: str
    patient: PatientSummary
    doctor: DoctorSummary | None
    status: str
    start_time: datetime
    end_time: datetime
    reason: str | None
    created_at: datetime


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _get_appointment_or_404(
    db: Any,
    appointment_id: str,
    tenant_id: str,
) -> Appointment:
    """Get an appointment scoped to the tenant, or raise 404."""
    try:
        apt_uuid = uuid.UUID(appointment_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid appointment ID format",
        )

    tenant_uuid = uuid.UUID(tenant_id)

    stmt = (
        select(Appointment)
        .options(selectinload(Appointment.patient), selectinload(Appointment.doctor))
        .where(
            Appointment.id == apt_uuid,
            Appointment.tenant_id == tenant_uuid,
        )
    )
    result = await db.execute(stmt)
    appointment = result.scalar_one_or_none()
    if appointment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Turno no encontrado",
        )
    return appointment


def _appointment_to_item(apt: Appointment) -> AppointmentItem:
    """Convert an Appointment ORM object to an AppointmentItem schema."""
    patient = apt.patient
    doctor = apt.doctor

    return AppointmentItem(
        id=str(apt.id),
        patient=PatientSummary(
            id=str(patient.id),
            name=patient.name,
            phone_number=patient.phone_number,
        ),
        doctor=(
            DoctorSummary(
                id=str(doctor.id),
                name=doctor.name,
                specialty=doctor.specialty,
            )
            if doctor
            else None
        ),
        status=apt.status.value if hasattr(apt.status, "value") else str(apt.status),
        start_time=apt.start_time,
        end_time=apt.end_time,
        reason=apt.reason,
        created_at=apt.created_at,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

# NOTE: `/export` MUST be defined before `/{appointment_id}` so FastAPI
# resolves the literal path correctly (though FastAPI handles literal vs
# param precedence, keeping this order is clearer).


@router.get("/export")
async def export_appointments_csv(
    db: SessionDep,
    user: CurrentUser,
    export_date: date = Query(
        ..., alias="date", description="Date in YYYY-MM-DD format"
    ),
    doctor_id: str | None = Query(None),
    status_filter: str | None = Query(None, alias="status"),
):
    """Export appointments as CSV for the given date.

    Returns a ``text/csv`` response with ``Content-Disposition`` attachment
    so the browser prompts a file download.
    """
    tenant_uuid = uuid.UUID(str(user.tenant_id))

    conditions: list[Any] = [Appointment.tenant_id == tenant_uuid]

    # Filter by date range (entire day, UTC).
    day_start = datetime.combine(
        export_date, datetime.min.time(), tzinfo=timezone.utc
    )
    day_end = day_start + timedelta(days=1)
    conditions.append(Appointment.start_time >= day_start)
    conditions.append(Appointment.start_time < day_end)

    if doctor_id:
        try:
            conditions.append(Appointment.doctor_id == uuid.UUID(doctor_id))
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Formato de doctor_id inválido",
            )

    if status_filter:
        conditions.append(Appointment.status == status_filter)

    stmt = (
        select(Appointment)
        .options(selectinload(Appointment.patient), selectinload(Appointment.doctor))
        .where(*conditions)
        .order_by(Appointment.start_time.asc())
    )

    result = await db.execute(stmt)
    appointments = result.scalars().all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Paciente", "Teléfono", "Doctor", "Fecha", "Hora", "Estado"])

    for apt in appointments:
        patient = apt.patient
        doctor = apt.doctor
        status_val = (
            apt.status.value if hasattr(apt.status, "value") else str(apt.status)
        )
        writer.writerow(
            [
                patient.name or patient.phone_number,
                patient.phone_number,
                doctor.name if doctor else "",
                apt.start_time.strftime("%Y-%m-%d"),
                apt.start_time.strftime("%H:%M"),
                status_val,
            ]
        )

    csv_content = output.getvalue()

    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={
            "Content-Disposition": (
                f'attachment; filename="turnos-{export_date.isoformat()}.csv"'
            ),
        },
    )


@router.get("", response_model=list[AppointmentItem])
async def list_appointments(
    db: SessionDep,
    user: CurrentUser,
    list_date: date = Query(
        ..., alias="date", description="Date in YYYY-MM-DD format (default today)"
    ),
    doctor_id: str | None = Query(None),
    status_filter: str | None = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """List appointments for the current tenant with filters and pagination."""
    tenant_uuid = uuid.UUID(str(user.tenant_id))

    conditions: list[Any] = [Appointment.tenant_id == tenant_uuid]

    # Filter by date range (entire day, UTC).
    day_start = datetime.combine(
        list_date, datetime.min.time(), tzinfo=timezone.utc
    )
    day_end = day_start + timedelta(days=1)
    conditions.append(Appointment.start_time >= day_start)
    conditions.append(Appointment.start_time < day_end)

    if doctor_id:
        try:
            conditions.append(Appointment.doctor_id == uuid.UUID(doctor_id))
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Formato de doctor_id inválido",
            )

    if status_filter:
        conditions.append(Appointment.status == status_filter)

    offset = (page - 1) * page_size

    stmt = (
        select(Appointment)
        .options(selectinload(Appointment.patient), selectinload(Appointment.doctor))
        .where(*conditions)
        .order_by(Appointment.start_time.asc())
        .offset(offset)
        .limit(page_size)
    )

    result = await db.execute(stmt)
    appointments = result.scalars().all()

    return [_appointment_to_item(apt) for apt in appointments]


@router.get("/{appointment_id}", response_model=AppointmentItem)
async def get_appointment(
    appointment_id: str,
    db: SessionDep,
    user: CurrentUser,
):
    """Get full appointment detail with patient and doctor info."""
    apt = await _get_appointment_or_404(db, appointment_id, str(user.tenant_id))
    return _appointment_to_item(apt)


@router.post("/{appointment_id}/cancel", response_model=AppointmentItem)
async def cancel_appointment(
    appointment_id: str,
    db: SessionDep,
    user: CurrentUser,
):
    """Cancel an appointment.

    Validates that the status allows cancellation (pending, confirmed, or
    unconfirmed).  If a Google Calendar event exists, it is deleted (best
    effort).  An audit log entry is created.
    """
    apt = await _get_appointment_or_404(db, appointment_id, str(user.tenant_id))

    # Validate status allows cancellation.
    valid_statuses = {
        AppointmentStatus.pending,
        AppointmentStatus.confirmed,
        AppointmentStatus.unconfirmed,
    }
    if apt.status not in valid_statuses:
        status_str = (
            apt.status.value
            if hasattr(apt.status, "value")
            else str(apt.status)
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"No se puede cancelar un turno en estado '{status_str}'. "
                "Solo se pueden cancelar turnos pendientes, confirmados o sin confirmar."
            ),
        )

    # Delete Google Calendar event if exists (best effort).
    if apt.google_event_id:
        try:
            provider = GoogleCalendarProvider(str(user.tenant_id), db)
            await provider.delete_event(
                str(apt.doctor_id) if apt.doctor_id else None,
                apt.google_event_id,
            )
        except Exception as exc:
            logger.warning(
                "Failed to delete Google Calendar event %s for appointment %s: %s",
                apt.google_event_id,
                appointment_id,
                exc,
            )

    # Update status.
    apt.status = AppointmentStatus.cancelled_by_clinic
    db.add(apt)

    # Audit log.
    audit_entry = AuditLog(
        tenant_id=user.tenant_id,
        user_id=user.id,
        action="appointment.cancelled",
        entity_type="appointment",
        entity_id=appointment_id,
        details={"cancelled_by": str(user.id)},
    )
    db.add(audit_entry)

    await db.commit()
    await db.refresh(apt)

    logger.info(
        "Appointment %s cancelled by user %s (tenant %s)",
        appointment_id,
        user.id,
        user.tenant_id,
    )

    return _appointment_to_item(apt)


@router.post("/{appointment_id}/confirm", response_model=AppointmentItem)
async def confirm_appointment(
    appointment_id: str,
    db: SessionDep,
    user: CurrentUser,
):
    """Confirm an appointment.

    Validates the status is pending or unconfirmed, then updates to
    confirmed.  Creates an audit log entry.
    """
    apt = await _get_appointment_or_404(db, appointment_id, str(user.tenant_id))

    valid_statuses = {
        AppointmentStatus.pending,
        AppointmentStatus.unconfirmed,
    }
    if apt.status not in valid_statuses:
        status_str = (
            apt.status.value
            if hasattr(apt.status, "value")
            else str(apt.status)
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"No se puede confirmar un turno en estado '{status_str}'. "
                "Solo se pueden confirmar turnos pendientes o sin confirmar."
            ),
        )

    apt.status = AppointmentStatus.confirmed
    db.add(apt)

    audit_entry = AuditLog(
        tenant_id=user.tenant_id,
        user_id=user.id,
        action="appointment.confirmed",
        entity_type="appointment",
        entity_id=appointment_id,
        details={"confirmed_by": str(user.id)},
    )
    db.add(audit_entry)

    await db.commit()
    await db.refresh(apt)

    logger.info(
        "Appointment %s confirmed by user %s (tenant %s)",
        appointment_id,
        user.id,
        user.tenant_id,
    )

    return _appointment_to_item(apt)


@router.post("/{appointment_id}/mark-attended", response_model=AppointmentItem)
async def mark_appointment_attended(
    appointment_id: str,
    db: SessionDep,
    user: CurrentUser,
):
    """Mark an appointment as attended.

    Validates the status is confirmed, then updates to attended.
    Creates an audit log entry.
    """
    apt = await _get_appointment_or_404(db, appointment_id, str(user.tenant_id))

    if apt.status != AppointmentStatus.confirmed:
        status_str = (
            apt.status.value
            if hasattr(apt.status, "value")
            else str(apt.status)
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"No se puede marcar como atendido un turno en estado '{status_str}'. "
                "Solo se pueden marcar turnos confirmados."
            ),
        )

    apt.status = AppointmentStatus.attended
    db.add(apt)

    audit_entry = AuditLog(
        tenant_id=user.tenant_id,
        user_id=user.id,
        action="appointment.attended",
        entity_type="appointment",
        entity_id=appointment_id,
        details={"attended_by": str(user.id)},
    )
    db.add(audit_entry)

    await db.commit()
    await db.refresh(apt)

    logger.info(
        "Appointment %s marked attended by user %s (tenant %s)",
        appointment_id,
        user.id,
        user.tenant_id,
    )

    return _appointment_to_item(apt)
