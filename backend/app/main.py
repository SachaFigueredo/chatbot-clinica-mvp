from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import settings
from app.infrastructure.database.session import engine
from app.infrastructure.database.session import Base
from app.api.middleware.tenant import TenantMiddleware
from app.api.v1.appointments import router as appointments_router
from app.api.v1.auth import router as auth_router
from app.api.v1.calendar import router as calendar_router
from app.api.v1.conversations import router as conversations_router
from app.api.v1.dashboard import router as dashboard_router
from app.api.v1.faqs import router as faqs_router
from app.api.v1.onboarding import router as onboarding_router
from app.api.v1.clinic_config import router as clinic_config_router
from app.api.v1.webhooks.evolution import router as evolution_webhook_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    async with engine.begin() as conn:
        if settings.app_env == "development":
            await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


app = FastAPI(
    title="Chatbot Clínicas API",
    description="SaaS chatbot para clínicas de medicina general",
    version="0.1.0",
    lifespan=lifespan,
)

# --- Middleware ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(TenantMiddleware)

# --- API Routers ---
app.include_router(appointments_router, prefix="/api/v1")
app.include_router(auth_router, prefix="/api/v1")
app.include_router(calendar_router, prefix="/api/v1")
app.include_router(conversations_router, prefix="/api/v1")
app.include_router(dashboard_router, prefix="/api/v1")
app.include_router(faqs_router, prefix="/api/v1")
app.include_router(onboarding_router, prefix="/api/v1")
app.include_router(clinic_config_router, prefix="/api/v1")
app.include_router(evolution_webhook_router, prefix="/api/v1")


@app.get("/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}


# --- Frontend (SPA) ---
frontend_dist = Path(__file__).resolve().parent / "frontend"
frontend_index = frontend_dist / "index.html"


@app.exception_handler(StarletteHTTPException)
async def spa_fallback(request, exc):
    """Serve index.html for non-API 404s (SPA routing)."""
    if exc.status_code == 404 and not request.url.path.startswith("/api/"):
        if frontend_index.exists():
            return FileResponse(str(frontend_index))
    return JSONResponse({"detail": "Not found"}, status_code=exc.status_code)


if frontend_dist.exists():
    app.mount("/assets", StaticFiles(directory=str(frontend_dist / "assets")), name="assets")
    print(f"Frontend assets mounted from {frontend_dist}")
