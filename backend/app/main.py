from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

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
# Tenant middleware must run after CORS
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


# --- Frontend (static files) ---
frontend_dist = Path(__file__).resolve().parent / "frontend"

if frontend_dist.exists():
    # Serve static assets (JS, CSS, images)
    app.mount("/assets", StaticFiles(directory=str(frontend_dist / "assets")), name="assets")

    # SPA catch-all: serve index.html for all non-API routes
    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        if full_path.startswith("api/") or full_path.startswith("health"):
            return {"error": "not found"}, 404
        index = frontend_dist / "index.html"
        if index.exists():
            return FileResponse(str(index))
        return {"error": "not found"}, 404
else:
    print("Frontend dist not found, API-only mode")
