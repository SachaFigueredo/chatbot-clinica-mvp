from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel

from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, SessionDep
from app.infrastructure.database.models.faq import FAQ
from app.application.faq.answer import clear_faq_search_cache

router = APIRouter(prefix="/faqs", tags=["faqs"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class FAQCreate(BaseModel):
    question: str
    answer: str
    category: str = "general"
    sort_order: int = 0


class FAQUpdate(BaseModel):
    question: str | None = None
    answer: str | None = None
    category: str | None = None
    sort_order: int | None = None


class FAQResponse(BaseModel):
    id: str
    question: str
    answer: str
    category: str
    sort_order: int
    is_active: bool
    created_at: str | None = None
    updated_at: str | None = None


def _faq_to_response(faq: FAQ) -> FAQResponse:
    """Convert a FAQ ORM model to a Pydantic response."""
    return FAQResponse(
        id=str(faq.id),
        question=faq.question,
        answer=faq.answer,
        category=faq.category,
        sort_order=faq.sort_order,
        is_active=faq.is_active,
        created_at=faq.created_at.isoformat() if faq.created_at else None,
        updated_at=faq.updated_at.isoformat() if faq.updated_at else None,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _get_tenant_faq(
    db: AsyncSession,
    faq_id: str,
    tenant_id: uuid.UUID,
) -> FAQ:
    """Fetch an active FAQ by id scoped to the current tenant.

    Raises ``HTTPException(404)`` if not found or not owned by tenant.
    """
    try:
        faq_uuid = uuid.UUID(faq_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="FAQ not found",
        )

    stmt = select(FAQ).where(
        FAQ.id == faq_uuid,
        FAQ.tenant_id == tenant_id,
    )
    result = await db.execute(stmt)
    faq = result.scalar_one_or_none()

    if faq is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="FAQ not found",
        )
    return faq


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/faqs", response_model=list[FAQResponse])
async def list_faqs(
    db: SessionDep,
    user: CurrentUser,
    category: str | None = Query(None, description="Filter by category"),
    search: str | None = Query(None, description="Text search on question + answer"),
) -> Any:
    """List all FAQs for the current tenant.

    Supports optional ``?category=`` and ``?search=`` filters.
    Results are sorted by ``sort_order``.
    """
    stmt = (
        select(FAQ)
        .where(
            FAQ.tenant_id == user.tenant_id,
            FAQ.is_active.is_(True),
        )
    )

    if category:
        stmt = stmt.where(FAQ.category == category)

    if search:
        pattern = f"%{search}%"
        stmt = stmt.where(
            or_(
                FAQ.question.ilike(pattern),
                FAQ.answer.ilike(pattern),
            )
        )

    stmt = stmt.order_by(FAQ.sort_order, FAQ.question)
    result = await db.execute(stmt)
    faqs = result.scalars().all()

    return [_faq_to_response(faq) for faq in faqs]


@router.post("/faqs", response_model=FAQResponse, status_code=status.HTTP_201_CREATED)
async def create_faq(
    body: FAQCreate,
    db: SessionDep,
    user: CurrentUser,
) -> Any:
    """Create a new FAQ entry for the current tenant."""
    faq = FAQ(
        tenant_id=user.tenant_id,
        question=body.question,
        answer=body.answer,
        category=body.category,
        sort_order=body.sort_order,
    )
    db.add(faq)
    await db.commit()
    await db.refresh(faq)

    clear_faq_search_cache()

    return _faq_to_response(faq)


@router.put("/faqs/{faq_id}", response_model=FAQResponse)
async def update_faq(
    faq_id: str,
    body: FAQUpdate,
    db: SessionDep,
    user: CurrentUser,
) -> Any:
    """Update an existing FAQ entry.

    Only FAQs belonging to the current tenant can be updated.
    Partial updates are supported — only provided fields are changed.
    """
    faq = await _get_tenant_faq(db, faq_id, user.tenant_id)

    if body.question is not None:
        faq.question = body.question
    if body.answer is not None:
        faq.answer = body.answer
    if body.category is not None:
        faq.category = body.category
    if body.sort_order is not None:
        faq.sort_order = body.sort_order

    db.add(faq)
    await db.commit()
    await db.refresh(faq)

    clear_faq_search_cache()

    return _faq_to_response(faq)


@router.delete("/faqs/{faq_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_faq(
    faq_id: str,
    db: SessionDep,
    user: CurrentUser,
) -> None:
    """Soft-delete a FAQ entry (set ``is_active = False``).

    Only FAQs belonging to the current tenant can be deleted.
    """
    faq = await _get_tenant_faq(db, faq_id, user.tenant_id)

    faq.is_active = False
    db.add(faq)
    await db.commit()

    clear_faq_search_cache()
