from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from sqlalchemy import select

from app.infrastructure.database.session import async_session
from app.infrastructure.database.models.tenant import Tenant


class TenantMiddleware(BaseHTTPMiddleware):
    """Extract tenant from X-Tenant-Slug header or subdomain.

    The resolved tenant_id is available as request.state.tenant_id.
    """

    async def dispatch(self, request: Request, call_next):
        # Skip tenant resolution for health, docs, and auth endpoints
        path = request.url.path
        if path.startswith("/api/v1/auth/") or path in (
            "/health",
            "/docs",
            "/openapi.json",
            "/redoc",
        ):
            return await call_next(request)

        tenant_slug = request.headers.get("X-Tenant-Slug")

        # Try subdomain extraction as fallback
        if not tenant_slug:
            host = request.headers.get("host", "")
            parts = host.split(".")
            if len(parts) >= 3:
                tenant_slug = parts[0]

        if not tenant_slug:
            # No tenant slug — skip resolution. Auth-dependent endpoints
            # will reject the request with 401 when they cannot find a tenant.
            request.state.tenant_id = None
            request.state.tenant_slug = None
            return await call_next(request)

        async with async_session() as db:
            result = await db.execute(
                select(Tenant).where(Tenant.slug == tenant_slug)
            )
            tenant = result.scalar_one_or_none()

        if not tenant:
            return JSONResponse(
                status_code=404,
                content={"detail": f"Tenant '{tenant_slug}' not found"},
            )

        request.state.tenant_id = str(tenant.id)
        request.state.tenant_slug = tenant_slug
        return await call_next(request)
