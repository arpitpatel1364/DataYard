"""
CACTUS INTELLIGENCE SUITE (CIS) - Backend Entrypoint

FastAPI application. Serves the JSON API under /api/* and the vanilla
HTML/CSS/JS frontend as static files, so the whole platform runs as a
single process with zero external services (SQLite + in-process scheduler
replace PostgreSQL/Redis/Celery per project requirements).
"""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.database import init_db
from app.services.scheduler import start_scheduler, shutdown_scheduler, restore_all_monitoring_jobs

from app.api import auth, datasets, compare, reports, models as models_api, admin, dataset_merger, filesystem


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    start_scheduler()
    restore_all_monitoring_jobs()
    yield
    shutdown_scheduler()


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description=f"{settings.APP_NAME} - built for {settings.APP_BRAND}. "
                 "Dataset Intelligence, Validation, Registry, Monitoring, "
                 "Comparison & Model Analytics Platform.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(datasets.router)
app.include_router(compare.router)
app.include_router(reports.router)
app.include_router(models_api.router)
app.include_router(admin.router)
app.include_router(dataset_merger.router)
app.include_router(filesystem.router)


@app.get("/api/health")
def health_check():
    return {"status": "ok", "app": settings.APP_NAME, "version": settings.APP_VERSION,
             "brand": settings.APP_BRAND, "brand_color": settings.BRAND_COLOR}


@app.get("/api/config")
def public_config():
    """Lets the frontend self-configure (brand name/color) without hardcoding values."""
    return {"app_name": settings.APP_NAME, "brand": settings.APP_BRAND,
             "brand_color": settings.BRAND_COLOR, "version": settings.APP_VERSION}


# Serve the vanilla JS frontend (everything outside /api). This makes
# `uvicorn app.main:app` a complete single-process deployment.
FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
