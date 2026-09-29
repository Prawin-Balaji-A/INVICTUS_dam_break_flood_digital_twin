import os
from pathlib import Path
import backend.app  # Activate robust geopandas JSON fallback for Windows AppLocker environments
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from backend.app.core.config import settings
from backend.app.core.database import engine, Base
import backend.app.models

# Create DB tables
Base.metadata.create_all(bind=engine)

# Auto-sync project datasets and scenarios from disk
try:
    from backend.app.core.sync import sync_projects_and_scenarios
    sync_projects_and_scenarios()
except Exception as e:
    import logging
    logging.getLogger(__name__).warning(f"Project sync warning: {e}")

app = FastAPI(
    title=settings.APP_NAME,
    description="Dam Break Inundation Modelling & Flood Digital Twin Framework",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount data directory for static asset access (GeoJSONs, rasters, images, reports)
data_dir_abs = str(settings.DATA_DIR.resolve())
app.mount("/static/data", StaticFiles(directory=data_dir_abs), name="static_data")

models_dir = Path("models").resolve()
if models_dir.exists():
    app.mount("/models", StaticFiles(directory=str(models_dir)), name="models")

# Register API routers
from backend.app.api import (
    projects,
    datasets,
    scenarios,
    simulation,
    benchmarks,
    analysis,
    satellite,
    exports,
    reports,
    dams,
    ml,
    twin
)

app.include_router(projects.router)
app.include_router(datasets.router)
app.include_router(scenarios.router)
app.include_router(simulation.router)
app.include_router(benchmarks.router)
app.include_router(analysis.router)
app.include_router(satellite.router)
app.include_router(exports.router)
app.include_router(reports.router)
app.include_router(dams.router)
app.include_router(ml.router)
app.include_router(twin.router)

@app.get("/api/health")
def health_check():
    return {
        "status": "healthy",
        "app_name": settings.APP_NAME,
        "environment": settings.APP_ENV,
        "delft3d_available": settings.is_delft3d_available(),
        "delft3d_path": settings.DELFT3D_PATH or "Not configured",
        "gee_available": settings.is_gee_available(),
        "database_url": settings.DATABASE_URL.split("///")[-1] if "sqlite" in settings.DATABASE_URL else "PostgreSQL/PostGIS"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host=settings.HOST, port=settings.PORT, reload=settings.DEBUG)
