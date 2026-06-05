import uuid
from datetime import datetime

from sqlalchemy import String, Text, Integer, DateTime, ForeignKey, func, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database.session import Base


class ClinicConfig(Base):
    __tablename__ = "clinic_configs"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("tenants.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    email_contact: Mapped[str | None] = mapped_column(String(255), nullable=True)
    business_hours: Mapped[dict] = mapped_column(JSONB, default=dict)
    appointment_duration_minutes: Mapped[int] = mapped_column(Integer, default=20)
    welcome_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    prices: Mapped[dict | None] = mapped_column(JSONB, nullable=True, default=dict)
    emergency_phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    tenant = relationship("Tenant", back_populates="clinic_config")
