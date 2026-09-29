# System Architecture & Technical Specifications

## 1. Modular Monorepo Architecture

The framework is architected as an asynchronous, decoupled client-server application:

```text
[Frontend: React 19 + TypeScript + Vite + Tailwind + MapLibre + Three.js]
                             │
                             ▼ REST & WebSocket API (JSON & Binary Rasters)
[Backend: FastAPI + Pydantic v2 + SQLAlchemy ORM]
                             │
         ┌───────────────────┼───────────────────┐
         ▼                   ▼                   ▼
 [GIS Engine]        [Hydrology Engine]  [Hydrodynamic Solvers]
  • DEMProcessor      • Froehlich (2008)  • Experimental SPH
  • OSMFetcher        • MacDonald (1984)  • Delft3D Adapter
  • InundationEngine  • Von Thun (1990)   • Future Solvers (SWE)
         │                   │                   │
         └───────────────────┼───────────────────┘
                             ▼
         [Analysis & Impact / Satellite Validation]
          • Building Risk Categorization (Low, Mod, High, Very High)
          • Road Lifeline Disruption (km by class)
          • Land Use Submersion (ESA WorldCover)
          • Population Exposure Estimation
          • Sentinel-1 SAR Overlap (IoU, Precision, Recall, F1)
```

## 2. Background Simulation Queue & Job System

Large 2D hydrodynamic simulations cannot execute synchronously within a single HTTP request lifecycle. The framework implements a non-blocking `JobManager` singleton in `backend/app/core/jobs.py`:
- **States**: `QUEUED` $\to$ `PREPROCESSING` $\to$ `RUNNING` $\to$ `POSTPROCESSING` $\to$ `COMPLETED` / `FAILED`.
- **Progress Tracking**: 0.0% to 100.0% float value with real-time log messages.
- **Frontend Sync**: Polled at 1-second intervals by the client, animating a live progress bar.

## 3. Database Layer & Portability

- **Local Development**: Built-in SQLite (`./data/dam_break.db`) with thread-safety configurations.
- **Production Enterprise**: Full PostgreSQL + PostGIS support via SQLAlchemy ORM without modifying core application logic. Simply configure `DATABASE_URL=postgresql://user:pass@localhost:5432/dam_break` in `.env`.
