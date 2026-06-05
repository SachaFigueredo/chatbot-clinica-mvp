import uuid
from datetime import datetime

from sqlalchemy import String, Text, Boolean, DateTime, ForeignKey, func, CheckConstraint
from sqlalchemy import Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database.session import Base
from app.domain.enums import AppointmentStatus


class Appointment(Base):
    __tablename__ = "appointments"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("patients.id", ondelete="CASCADE"), nullable=False
    )
    doctor_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("doctors.id", ondelete="SET NULL"), nullable=True
    )
    google_event_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[AppointmentStatus] = mapped_column(
        String(20), default=AppointmentStatus.confirmed
    )
    start_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    end_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    reminder_1_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    reminder_2_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    reminder_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    cancelled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cancellation_reason: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        CheckConstraint("end_time > start_time", name="valid_time_range"),
    )

    # Relationships
    tenant = relationship("Tenant", back_populates="appointments")
    patient = relationship("Patient", back_populates="appointments")
    doctor = relationship("Doctor", back_populates="appointments")
