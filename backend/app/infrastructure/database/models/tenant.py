import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Boolean, DateTime, func
from sqlalchemy import Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database.session import Base
from app.domain.enums import TenantStatus, TenantPlan


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    phone_number: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    status: Mapped[TenantStatus] = mapped_column(
        String(20), default=TenantStatus.active
    )
    plan: Mapped[TenantPlan] = mapped_column(String(50), default=TenantPlan.basic)
    trial_ends_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    mercadopago_customer_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, default=None
    )
    mercadopago_subscription_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, default=None
    )
    suspended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    users = relationship("User", back_populates="tenant", cascade="all, delete-orphan")
    clinic_config = relationship("ClinicConfig", back_populates="tenant", uselist=False, cascade="all, delete-orphan")
    doctors = relationship("Doctor", back_populates="tenant", cascade="all, delete-orphan")
    patients = relationship("Patient", back_populates="tenant", cascade="all, delete-orphan")
    appointments = relationship("Appointment", back_populates="tenant", cascade="all, delete-orphan")
    conversations = relationship("Conversation", back_populates="tenant", cascade="all, delete-orphan")
    faqs = relationship("FAQ", back_populates="tenant", cascade="all, delete-orphan")
    tenant_settings = relationship("TenantSettings", back_populates="tenant", uselist=False, cascade="all, delete-orphan")
    google_calendar_tokens = relationship("GoogleCalendarToken", back_populates="tenant", cascade="all, delete-orphan")
    audit_logs = relationship("AuditLog", back_populates="tenant", cascade="all, delete-orphan")
