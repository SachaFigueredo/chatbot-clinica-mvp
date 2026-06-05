import uuid
from datetime import datetime

from sqlalchemy import String, Text, Boolean, DateTime, ForeignKey, func, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database.session import Base


class TenantSettings(Base):
    __tablename__ = "tenant_settings"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("tenants.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    operating_hours: Mapped[dict] = mapped_column(JSONB, default=dict)
    holidays: Mapped[list] = mapped_column(JSONB, default=list)
    bot_tone: Mapped[str] = mapped_column(String(50), default="professional")
    max_scheduling_days_ahead: Mapped[int] = mapped_column(default=60)
    reminder_1_minutes: Mapped[int] = mapped_column(default=1440)
    reminder_2_minutes: Mapped[int] = mapped_column(default=120)
    timezone: Mapped[str] = mapped_column(String(50), default="America/Argentina/Buenos_Aires")
    onboarding_state: Mapped[dict] = mapped_column(JSONB, default=dict)
    onboarding_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    tenant = relationship("Tenant", back_populates="tenant_settings")
