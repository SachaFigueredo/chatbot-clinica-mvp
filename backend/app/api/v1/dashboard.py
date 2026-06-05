from __future__ import annotations

import uuid
from datetime import date, datetime, timezone, timedelta

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import func, select

from app.api.deps import CurrentUser, SessionDep
from app.domain.enums import AppointmentStatus, ConversationStatus
from app.infrastructure.database.models.appointment import Appointment
from app.infrastructure.database.models.conversation import Conversation

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class DashboardStats(BaseModel):
    appointments_today: int
    pending_confirmations: int
    active_conversations: int
    escalated_conversations: int
    no_show_rate: float


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/stats", response_model=DashboardStats)
async def get_dashboard_stats(
    db: SessionDep,
    user: CurrentUser,
):
    """Return aggregated statistics for the admin dashboard.

    Computes in a single request:
    - ``appointments_today`` — appointments scheduled for today
    - ``pending_confirmations`` — appointments still in ``pending`` status
    - ``active_conversations`` — conversations currently handled by the bot
    - ``escalated_conversations`` — conversations escalated to a human
    - ``no_show_rate`` — percentage of no-shows this month
    """
    tenant_id = uuid.UUID(str(user.tenant_id))
    today = date.today()

    # Build timezone-aware boundaries for today and this month.
    tz = timezone.utc
    today_start = datetime(today.year, today.month, today.day, tzinfo=tz)
    today_end = today_start + timedelta(days=1)

    this_month_start = datetime(today.year, today.month, 1, tzinfo=tz)
    if today.month == 12:
        next_month_start = datetime(today.year + 1, 1, 1, tzinfo=tz)
    else:
        next_month_start = datetime(today.year, today.month + 1, 1, tzinfo=tz)

    # --- Run all count queries in parallel ---

    # 1. Appointments today
    stmt_today = select(func.count(Appointment.id)).where(
        Appointment.tenant_id == tenant_id,
        Appointment.start_time >= today_start,
        Appointment.start_time < today_end,
    )
    result = await db.execute(stmt_today)
    appointments_today = result.scalar() or 0

    # 2. Pending confirmations (status == pending)
    stmt_pending = select(func.count(Appointment.id)).where(
        Appointment.tenant_id == tenant_id,
        Appointment.status == AppointmentStatus.pending,
    )
    result = await db.execute(stmt_pending)
    pending_confirmations = result.scalar() or 0

    # 3. Active conversations
    stmt_active = select(func.count(Conversation.id)).where(
        Conversation.tenant_id == tenant_id,
        Conversation.status == ConversationStatus.active,
    )
    result = await db.execute(stmt_active)
    active_conversations = result.scalar() or 0

    # 4. Escalated conversations
    stmt_escalated = select(func.count(Conversation.id)).where(
        Conversation.tenant_id == tenant_id,
        Conversation.status == ConversationStatus.escalated,
    )
    result = await db.execute(stmt_escalated)
    escalated_conversations = result.scalar() or 0

    # 5. No-show rate this month
    stmt_no_show = select(func.count(Appointment.id)).where(
        Appointment.tenant_id == tenant_id,
        Appointment.status == AppointmentStatus.no_show,
        Appointment.start_time >= this_month_start,
        Appointment.start_time < next_month_start,
    )
    result = await db.execute(stmt_no_show)
    no_show_count = result.scalar() or 0

    stmt_attended = select(func.count(Appointment.id)).where(
        Appointment.tenant_id == tenant_id,
        Appointment.status == AppointmentStatus.attended,
        Appointment.start_time >= this_month_start,
        Appointment.start_time < next_month_start,
    )
    result = await db.execute(stmt_attended)
    attended_count = result.scalar() or 0

    total = no_show_count + attended_count
    no_show_rate = round((no_show_count / total) * 100, 1) if total > 0 else 0.0

    return DashboardStats(
        appointments_today=appointments_today,
        pending_confirmations=pending_confirmations,
        active_conversations=active_conversations,
        escalated_conversations=escalated_conversations,
        no_show_rate=no_show_rate,
    )
