from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, EmailStr

from sqlalchemy import select

from app.api.deps import SessionDep
from app.domain.services.auth_service import AuthService
from app.infrastructure.database.models.tenant import Tenant
from app.infrastructure.database.models.user import User
from app.domain.enums import UserRole

router = APIRouter(prefix="/auth", tags=["auth"])


# --- Schemas ---

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    name: str
    clinic_name: str | None = None
    tenant_slug: str | None = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class LoginResponse(BaseModel):
    access_token: str
    user_id: str
    tenant_id: str


class MagicLinkRequest(BaseModel):
    email: EmailStr
    tenant_slug: str


class MagicLinkVerifyRequest(BaseModel):
    token: str


# --- Endpoints ---

@router.post("/register")
async def register(body: RegisterRequest, db: SessionDep):
    import re, uuid

    # Create tenant if tenant_slug provided, or auto-create from clinic_name
    if body.tenant_slug:
        result = await db.execute(
            select(Tenant).where(Tenant.slug == body.tenant_slug)
        )
        tenant = result.scalar_one_or_none()
        if not tenant:
            raise HTTPException(status_code=404, detail="Tenant not found")
    else:
        clinic_name = body.clinic_name or body.name
        slug = re.sub(r'[^a-z0-9-]', '', clinic_name.lower().replace(' ', '-'))
        if not slug:
            slug = "default"
        # Ensure unique slug
        result = await db.execute(
            select(Tenant).where(Tenant.slug == slug)
        )
        existing = result.scalar_one_or_none()
        if existing:
            slug = f"{slug}-{uuid.uuid4().hex[:6]}"

        tenant = Tenant(
            name=clinic_name,
            slug=slug,
            phone_number=f"pending-{uuid.uuid4().hex[:8]}",
            status="active",
            plan="free",
        )
        db.add(tenant)
        await db.flush()
        await db.refresh(tenant)

    # Check duplicate email
    result = await db.execute(
        select(User).where(
            User.tenant_id == tenant.id,
            User.email == body.email,
        )
    )
    if result.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already registered")

    role = UserRole.admin if not body.tenant_slug else UserRole.recepcionista
    user = User(
        tenant_id=tenant.id,
        email=body.email,
        password_hash=AuthService.hash_password(body.password),
        name=body.name,
        role=role,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    token = AuthService.create_access_token(str(user.id), str(tenant.id))
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": str(user.id),
            "email": user.email,
            "name": user.name,
            "role": user.role.value,
            "tenant_id": str(tenant.id),
            "is_active": user.is_active,
        },
    }


@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest, db: SessionDep):
    result = await db.execute(
        select(User).where(User.email == body.email)
    )
    user = result.scalar_one_or_none()
    if not user or not user.password_hash:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if not AuthService.verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = AuthService.create_access_token(str(user.id), str(user.tenant_id))
    return LoginResponse(
        access_token=token,
        user_id=str(user.id),
        tenant_id=str(user.tenant_id),
    )


@router.post("/magic-link/request")
async def request_magic_link(body: MagicLinkRequest, db: SessionDep):
    result = await db.execute(
        select(Tenant).where(Tenant.slug == body.tenant_slug)
    )
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    result = await db.execute(
        select(User).where(
            User.tenant_id == tenant.id,
            User.email == body.email,
        )
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    token = AuthService.create_magic_link_token(body.email, str(tenant.id))
    # TODO: enviar token por email
    return {"message": "Magic link sent", "token": token}


@router.post("/magic-link/verify", response_model=LoginResponse)
async def verify_magic_link(body: MagicLinkVerifyRequest, db: SessionDep):
    payload = AuthService.verify_magic_link_token(body.token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    result = await db.execute(
        select(User).where(
            User.tenant_id == payload["tenant_id"],
            User.email == payload["email"],
        )
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    token = AuthService.create_access_token(str(user.id), str(user.tenant_id))
    return LoginResponse(
        access_token=token,
        user_id=str(user.id),
        tenant_id=str(user.tenant_id),
    )
