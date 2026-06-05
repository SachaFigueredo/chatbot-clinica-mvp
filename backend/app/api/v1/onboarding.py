from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select

from app.api.deps import CurrentUser, SessionDep
from app.infrastructure.database.models.tenant_settings import TenantSettings

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class OnboardingStep(BaseModel):
    id: int
    name: str
    completed: bool


class OnboardingStatusResponse(BaseModel):
    completed: bool
    current_step: int
    steps: list[OnboardingStep]


class MarkStepRequest(BaseModel):
    step_id: int


class FAQTemplate(BaseModel):
    question: str
    answer: str
    category: str


class FAQTemplatesResponse(BaseModel):
    templates: list[FAQTemplate]


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

STEPS = [
    {"id": 1, "name": "Conectar WhatsApp"},
    {"id": 2, "name": "Conectar Google Calendar"},
    {"id": 3, "name": "Configurar clínica"},
    {"id": 4, "name": "Cargar preguntas frecuentes"},
    {"id": 5, "name": "¡Bot activo!"},
]

FAQ_TEMPLATES = [
    FAQTemplate(
        question="¿Cuáles son los horarios de atención?",
        answer="Nuestros horarios son de lunes a viernes de 8:00 a 18:00 y sábados de 9:00 a 13:00.",
        category="horarios",
    ),
    FAQTemplate(
        question="¿Aceptan obras sociales?",
        answer="Sí, trabajamos con [lista de obras sociales]. Consultá las disponibles en nuestra clínica.",
        category="precios",
    ),
    FAQTemplate(
        question="¿Cómo puedo cancelar un turno?",
        answer="Podés cancelar tu turno respondiendo este mensaje. Recordá hacerlo con al menos 2 horas de anticipación.",
        category="turnos",
    ),
    FAQTemplate(
        question="¿Cuánto cuesta una consulta particular?",
        answer="El valor de la consulta particular es de $[precio]. Aceptamos efectivo, transferencia y tarjetas.",
        category="precios",
    ),
    FAQTemplate(
        question="¿Dónde están ubicados?",
        answer="Estamos en [dirección de la clínica]. Contamos con estacionamiento y acceso para discapacitados.",
        category="general",
    ),
    FAQTemplate(
        question="¿Hacen análisis clínicos?",
        answer="Sí, contamos con laboratorio propio. Los resultados están listos en 24 a 48 horas hábiles.",
        category="servicios",
    ),
    FAQTemplate(
        question="¿Qué especialidades tienen?",
        answer="Somos una clínica de medicina general. Atendemos consultas de clínica médica, pediatría, ginecología y cardiología.",
        category="servicios",
    ),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_status(settings: TenantSettings | None) -> OnboardingStatusResponse:
    """Build onboarding status from tenant settings (or defaults)."""
    if settings is None or not settings.onboarding_state:
        return OnboardingStatusResponse(
            completed=False,
            current_step=1,
            steps=[OnboardingStep(**s, completed=False) for s in STEPS],
        )

    completed_steps = set(settings.onboarding_state.get("completed_steps", []))
    steps = [
        OnboardingStep(
            id=s["id"],
            name=s["name"],
            completed=s["id"] in completed_steps,
        )
        for s in STEPS
    ]

    # Determine current step (first incomplete, or last if all done)
    current_step = 1
    for s in steps:
        if not s.completed:
            current_step = s.id
            break
        current_step = s.id

    return OnboardingStatusResponse(
        completed=settings.onboarding_completed or False,
        current_step=current_step,
        steps=steps,
    )


async def _get_or_create_settings(
    db: SessionDep,
    user: CurrentUser,
) -> TenantSettings:
    """Get existing TenantSettings or create default ones."""
    stmt = select(TenantSettings).where(TenantSettings.tenant_id == user.tenant_id)
    result = await db.execute(stmt)
    settings = result.scalar_one_or_none()

    if settings is None:
        settings = TenantSettings(
            tenant_id=user.tenant_id,
            onboarding_state={},
            onboarding_completed=False,
        )
        db.add(settings)
        await db.commit()
        await db.refresh(settings)

    return settings


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/status", response_model=OnboardingStatusResponse)
async def get_onboarding_status(
    db: SessionDep,
    user: CurrentUser,
):
    """Return the current onboarding state for the user's tenant.

    Returns default state (step 1, all incomplete) if onboarding has
    not been started yet.
    """
    stmt = select(TenantSettings).where(TenantSettings.tenant_id == user.tenant_id)
    result = await db.execute(stmt)
    settings = result.scalar_one_or_none()
    return _build_status(settings)


@router.put("/step", response_model=OnboardingStatusResponse)
async def mark_step_completed(
    body: MarkStepRequest,
    db: SessionDep,
    user: CurrentUser,
):
    """Mark an onboarding step as completed.

    When all 5 steps are completed, ``onboarding_completed`` is set to
    ``true`` on the tenant settings record.
    """
    if body.step_id < 1 or body.step_id > 5:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Step ID must be between 1 and 5",
        )

    settings = await _get_or_create_settings(db, user)

    # Ensure onboarding_state exists
    if settings.onboarding_state is None:
        settings.onboarding_state = {}

    completed_steps = set(settings.onboarding_state.get("completed_steps", []))
    completed_steps.add(body.step_id)
    # Replace the entire dict so SQLAlchemy detects the change (JSON/mutable
    # types do not track in-place mutations).
    new_state = dict(settings.onboarding_state)
    new_state["completed_steps"] = list(completed_steps)
    settings.onboarding_state = new_state

    # Check if all 5 steps are done
    if len(completed_steps) >= 5:
        settings.onboarding_completed = True

    db.add(settings)
    await db.commit()
    await db.refresh(settings)

    return _build_status(settings)


@router.get("/faq-templates", response_model=FAQTemplatesResponse)
async def get_faq_templates():
    """Return FAQ templates for common clinic questions.

    These templates can be pre-loaded by the clinic during onboarding
    to give the bot a basic knowledge base immediately.
    """
    return FAQTemplatesResponse(templates=FAQ_TEMPLATES)
