"""Shared test configuration and fixtures for the Chatbot Clínicas test suite.

Environment variables are set BEFORE any app imports to ensure the test
database and test secrets are used throughout.
"""

# =============================================================================
# 1. Test environment — must be set BEFORE any app imports
# =============================================================================
import os

os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///file:testdb?mode=memory&cache=shared&uri=true"
os.environ["JWT_SECRET"] = "test-jwt-secret-for-testing-only"
os.environ["SECRET_KEY"] = "test-secret-key"
os.environ["OPENAI_API_KEY"] = "sk-test-fake-key"
os.environ["DEBUG"] = "False"

# Generate a valid Fernet key so Google Calendar tests don't blow up
from cryptography.fernet import Fernet  # noqa: E402

os.environ["ENCRYPTION_KEY"] = Fernet.generate_key().decode()

# =============================================================================
# 2. Imports — now safe because env vars are set
# =============================================================================
import uuid
from collections.abc import AsyncGenerator
from datetime import datetime, timezone, timedelta
from typing import Any

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import text

# Register SQLite-compatible compilers for PostgreSQL-specific types
# before any model is imported.
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID  # noqa: E402
from sqlalchemy.ext.compiler import compiles  # noqa: E402


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(type_, compiler, **kw):
    """Render JSONB as TEXT for SQLite (JSON affinity)."""
    return compiler.visit_JSON(type_, **kw)


@compiles(PG_UUID, "sqlite")
def _compile_uuid_sqlite(type_, compiler, **kw):
    """Render PostgreSQL UUID as VARCHAR for SQLite."""
    return compiler.visit_VARCHAR(type_, **kw)


# =============================================================================
# 2b. Fix Uuid bind_processor for SQLite — handle both uuid.UUID and str values
# =============================================================================
# SQLAlchemy's Uuid.as_uuid bind processor calls .hex directly, assuming the
# value is already a uuid.UUID. But many call sites pass strings (JWT claims,
# URL params). PostgreSQL handles strings natively; SQLite does not.
# We monkey-patch to convert strings to uuid.UUID first.
import sqlalchemy.sql.sqltypes as _sqlt  # noqa: E402

_orig_uuid_bind = _sqlt.Uuid.bind_processor


def _patched_uuid_bind(self, dialect):
    char_based = not dialect.supports_native_uuid or not self.native_uuid
    if char_based and self.as_uuid:

        def process(value):
            if value is not None:
                if isinstance(value, str):
                    value = uuid.UUID(value)
                value = value.hex
            return value

        return process
    return _orig_uuid_bind(self, dialect)


_sqlt.Uuid.bind_processor = _patched_uuid_bind


from app.main import app
from app.config import settings
from app.infrastructure.database.session import Base, engine
from app.domain.enums import (
    TenantStatus,
    TenantPlan,
    ConversationStatus,
    ConversationChannel,
    MessageOrigin,
    AppointmentStatus,
    UserRole,
)
from app.infrastructure.database.models.tenant import Tenant
from app.infrastructure.database.models.user import User
from app.infrastructure.database.models.patient import Patient
from app.infrastructure.database.models.conversation import (
    Conversation,
    ConversationMessage,
)
from app.infrastructure.database.models.appointment import Appointment
from app.infrastructure.database.models.faq import FAQ
from app.infrastructure.database.models.clinic_config import ClinicConfig
from app.infrastructure.database.models.tenant_settings import TenantSettings
from app.domain.services.auth_service import AuthService

# =============================================================================
# 3. App configuration for tests
# =============================================================================
# Disable lifespan so we control DB lifecycle entirely via fixtures
app.router.lifespan_context = None

# Inherit any existing dependency overrides, then add ours if needed
# (currently no overrides are required because engine is already pointing at
# the shared in-memory SQLite DB — the module-level `get_session` works fine)

# =============================================================================
# 4. Fixtures
# =============================================================================

# ---------------------------------------------------------------------------
# 4a. Database lifecycle
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(autouse=True)
async def _setup_database() -> AsyncGenerator[None, None]:
    """Create all tables before each test, drop them after.

    This runs **autouse** so every test starts with a clean slate.
    Tables are created via the shared in-memory SQLite engine so that
    *all* sessions — middleware, API handlers, and fixtures — see the
    same data.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.execute(text("PRAGMA foreign_keys = OFF"))
        await conn.run_sync(Base.metadata.drop_all)


# ---------------------------------------------------------------------------
# 4b. Session-level helpers
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def db_session():
    """Provide an isolated database session (function-scoped).

    Uses the module-level ``async_session`` from session.py, which in
    turn uses the module-level ``engine``.  Both point at the shared
    in-memory SQLite database because ``DATABASE_URL`` was overridden
    before any import.
    """
    from app.infrastructure.database.session import async_session

    async with async_session() as session:
        yield session


# ---------------------------------------------------------------------------
# 4c. Data fixtures — Tenant / User / Auth
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def test_tenant(db_session) -> Tenant:
    """Create a single active tenant for testing."""
    tenant = Tenant(
        name="Clínica Test",
        slug="test-clinic",
        phone_number="541112345678",
        status=TenantStatus.active,
        plan=TenantPlan.basic,
    )
    db_session.add(tenant)
    await db_session.commit()
    await db_session.refresh(tenant)
    return tenant


@pytest_asyncio.fixture
async def test_tenant_2(db_session) -> Tenant:
    """A second tenant for isolation tests."""
    tenant = Tenant(
        name="Otra Clínica",
        slug="other-clinic",
        phone_number="541198765432",
        status=TenantStatus.active,
        plan=TenantPlan.basic,
    )
    db_session.add(tenant)
    await db_session.commit()
    await db_session.refresh(tenant)
    return tenant


@pytest_asyncio.fixture
async def test_user(db_session, test_tenant) -> User:
    """Create a test user (recepcionista) scoped to ``test_tenant``."""
    user = User(
        tenant_id=test_tenant.id,
        email="test@clinicatest.com",
        password_hash=AuthService.hash_password("test-password"),
        name="Test User",
        role=UserRole.recepcionista,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def test_admin_user(db_session, test_tenant) -> User:
    """Create an admin test user."""
    user = User(
        tenant_id=test_tenant.id,
        email="admin@clinicatest.com",
        password_hash=AuthService.hash_password("admin-password"),
        name="Admin User",
        role=UserRole.admin,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def other_tenant_user(db_session, test_tenant_2) -> User:
    """Create a user belonging to ``test_tenant_2`` for isolation checks."""
    user = User(
        tenant_id=test_tenant_2.id,
        email="other@otherclinic.com",
        password_hash=AuthService.hash_password("other-password"),
        name="Other User",
        role=UserRole.recepcionista,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
def auth_token(test_user, test_tenant) -> str:
    """Generate a valid JWT for ``test_user``."""
    return AuthService.create_access_token(
        str(test_user.id), str(test_tenant.id)
    )


@pytest_asyncio.fixture
def auth_token_admin(test_admin_user, test_tenant) -> str:
    """Generate a valid JWT for the admin user."""
    return AuthService.create_access_token(
        str(test_admin_user.id), str(test_tenant.id)
    )


@pytest_asyncio.fixture
def auth_token_other(other_tenant_user, test_tenant_2) -> str:
    """JWT for a user in a *different* tenant (isolation tests)."""
    return AuthService.create_access_token(
        str(other_tenant_user.id), str(test_tenant_2.id)
    )


@pytest_asyncio.fixture
def auth_headers(auth_token, test_tenant) -> dict[str, str]:
    """Headers with valid JWT + tenant slug for ``test_tenant``."""
    return {
        "Authorization": f"Bearer {auth_token}",
        "X-Tenant-Slug": test_tenant.slug,
    }


@pytest_asyncio.fixture
def auth_headers_other(auth_token_other, test_tenant_2) -> dict[str, str]:
    """Headers for a user in the *other* tenant."""
    return {
        "Authorization": f"Bearer {auth_token_other}",
        "X-Tenant-Slug": test_tenant_2.slug,
    }


@pytest_asyncio.fixture
def tenant_headers(test_tenant) -> dict[str, str]:
    """Headers with tenant slug but **no** Authorization (for public endpoints)."""
    return {
        "X-Tenant-Slug": test_tenant.slug,
    }


# ---------------------------------------------------------------------------
# 4d. Data fixtures — Patient + Conversation + Messages
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def test_patient(db_session, test_tenant) -> Patient:
    """Create a patient belonging to ``test_tenant``."""
    patient = Patient(
        tenant_id=test_tenant.id,
        phone_number="5491111111111",
        name="Juan Pérez",
    )
    db_session.add(patient)
    await db_session.commit()
    await db_session.refresh(patient)
    return patient


@pytest_asyncio.fixture
async def test_conversation(
    db_session, test_tenant, test_patient
) -> Conversation:
    """Create an *active* WhatsApp conversation for the test patient."""
    conv = Conversation(
        tenant_id=test_tenant.id,
        patient_id=test_patient.id,
        status=ConversationStatus.active,
        channel=ConversationChannel.whatsapp,
    )
    db_session.add(conv)
    await db_session.commit()
    await db_session.refresh(conv)
    return conv


@pytest_asyncio.fixture
async def test_escalated_conversation(
    db_session, test_tenant, test_patient
) -> Conversation:
    """Create an *escalated* conversation (not yet taken by a human)."""
    conv = Conversation(
        tenant_id=test_tenant.id,
        patient_id=test_patient.id,
        status=ConversationStatus.escalated,
        channel=ConversationChannel.whatsapp,
        escalated_at=datetime.now(timezone.utc),
    )
    db_session.add(conv)
    await db_session.commit()
    await db_session.refresh(conv)
    return conv


@pytest_asyncio.fixture
async def test_taken_conversation(
    db_session, test_tenant, test_patient, test_user
) -> Conversation:
    """Create an escalated conversation that has been taken by a human."""
    conv = Conversation(
        tenant_id=test_tenant.id,
        patient_id=test_patient.id,
        status=ConversationStatus.escalated,
        channel=ConversationChannel.whatsapp,
        escalated_at=datetime.now(timezone.utc),
        escalated_to=test_user.id,
    )
    db_session.add(conv)
    await db_session.commit()
    await db_session.refresh(conv)
    return conv


@pytest_asyncio.fixture
async def test_messages(
    db_session, test_conversation
) -> list[ConversationMessage]:
    """Create sample messages for the active conversation."""
    now = datetime.now(timezone.utc)
    msgs = [
        ConversationMessage(
            conversation_id=test_conversation.id,
            origin=MessageOrigin.patient,
            content="Hola, quiero un turno",
            created_at=now,
        ),
        ConversationMessage(
            conversation_id=test_conversation.id,
            origin=MessageOrigin.bot,
            content="¡Hola! Claro, te ayudo a agendar un turno.",
            created_at=now + timedelta(seconds=1),
        ),
    ]
    for m in msgs:
        db_session.add(m)
    await db_session.commit()
    for m in msgs:
        await db_session.refresh(m)
    return msgs


# ---------------------------------------------------------------------------
# 4e. Data fixtures — FAQ
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def test_faqs(db_session, test_tenant) -> list[FAQ]:
    """Create sample FAQs for the test tenant."""
    faqs = [
        FAQ(
            tenant_id=test_tenant.id,
            question="¿Cuáles son los horarios de atención?",
            answer="Lunes a viernes de 8 a 18h.",
            category="horarios",
            sort_order=1,
            is_active=True,
        ),
        FAQ(
            tenant_id=test_tenant.id,
            question="¿Aceptan obras sociales?",
            answer="Sí, trabajamos con varias obras sociales.",
            category="precios",
            sort_order=2,
            is_active=True,
        ),
        FAQ(
            tenant_id=test_tenant.id,
            question="¿Cómo cancelo un turno?",
            answer="Podés cancelar con 2 horas de anticipación.",
            category="turnos",
            sort_order=3,
            is_active=True,
        ),
        FAQ(
            tenant_id=test_tenant.id,
            question="Inactive FAQ",
            answer="This one is inactive.",
            category="general",
            sort_order=99,
            is_active=False,  # <-- soft-deleted / inactive
        ),
    ]
    for faq in faqs:
        db_session.add(faq)
    await db_session.commit()
    for faq in faqs:
        await db_session.refresh(faq)
    return faqs


# ---------------------------------------------------------------------------
# 4f. Data fixtures — Appointment
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def test_appointment(
    db_session, test_tenant, test_patient
) -> Appointment:
    """Create a confirmed appointment for tomorrow."""
    tomorrow = datetime.now(timezone.utc) + timedelta(days=1)
    apt = Appointment(
        tenant_id=test_tenant.id,
        patient_id=test_patient.id,
        google_event_id="google-event-id-test",
        start_time=tomorrow.replace(hour=10, minute=0, second=0, microsecond=0),
        end_time=tomorrow.replace(hour=10, minute=20, second=0, microsecond=0),
        status=AppointmentStatus.confirmed,
    )
    db_session.add(apt)
    await db_session.commit()
    await db_session.refresh(apt)
    return apt


# ---------------------------------------------------------------------------
# 4g. Domain-service fixtures (mocked)
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
def mock_llm_provider(mocker) -> Any:
    """Return a mocked ``LLMProvider`` that returns a canned response."""
    from app.domain.interfaces.llm import LLMProvider

    mock = mocker.AsyncMock(spec=LLMProvider)
    mock.chat.return_value = (
        '{"intent": "saludo", "confidence": 0.95, '
        '"message": "¡Hola! ¿En qué puedo ayudarte?", "params": {}}'
    )
    return mock


@pytest_asyncio.fixture
def mock_calendar_provider(mocker) -> Any:
    """Return a mocked ``CalendarProvider``."""
    from app.domain.interfaces.calendar import CalendarProvider

    mock = mocker.AsyncMock(spec=CalendarProvider)
    mock.create_event.return_value = "google-event-id-123"
    mock.delete_event.return_value = None
    return mock


# ---------------------------------------------------------------------------
# 4h. HTTP client
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    """Provide an HTTP client wired to the FastAPI test app.

    Lifespan is disabled via ``lifespan_context=None`` at the top of
    this module, so table creation is entirely handled by our
    ``_setup_database`` fixture.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest_asyncio.fixture
async def async_client_raw() -> AsyncGenerator[AsyncClient, None]:
    """HTTP client **without** any tenant or auth headers.

    Use this for testing public/unauthenticated endpoints.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
