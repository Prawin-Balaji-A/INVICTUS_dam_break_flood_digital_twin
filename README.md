# Dam Break Inundation Modelling & Flood Digital Twin

> **Smart India Hackathon 2026** | **Problem Statement ID:** 26161 — *Dam Break Inundation Modelling Using Hydrodynamic Modelling of any River*  
> **Theme:** Disaster Management | **Team:** InVictus_165 | **Category:** Software  
> 📖 **Full System Documentation:** [DOCUMENTATION.md](DOCUMENTATION.md)

A generalized, open-access, full-stack GIS and hydrodynamic simulation framework for automated dam-break and river-blockage flood hazard modeling, impact assessment, and 2D/3D digital twin visualization across Indian and global river basins (including **Mettur Dam** on Cauvery River, **Tehri Dam** on Bhagirathi River, and **Idukki Dam**).

---

## 1. Project Overview & Scientific Purpose

Dam breach events generate catastrophic, high-velocity unsteady flood waves that threaten downstream human settlements, critical infrastructure, and ecology. Traditional dam break analyses rely on proprietary software or fragmented tools requiring manual data preparation across multiple GIS packages.

This framework generalizes dam break inundation modeling for **any river system** (with an out-of-the-box demonstration project configured for the historic **Machchhu Dam-II / Machchhu River** disaster in Morbi, Gujarat, India).

### Key Capabilities
- **Automated Open Data Ingestion**: DEM elevation (SRTM, Copernicus 30m), OpenStreetMap waterways, building footprints with levels/heights, and road networks.
- **Topographic Preprocessing**: Automated UTM metric reprojection, priority-flood depression filling, hillshade, slope, aspect, D8 flow direction, and flow accumulation.
- **Empirical Breach Mechanics**: Implementation of Froehlich (2008), MacDonald & Langridge-Monopolis (1984), and Von Thun & Gillette (1990) breach geometry equations coupled with broad-crested weir hydraulics for dynamic discharge $Q(t)$ hydrograph generation.
- **Dual Hydrodynamic Solver Architecture**:
  - **Internal Experimental SPH Solver**: Smooth Particle Hydrodynamics engine with Wendland $C^2$ kernel, Tait equation of state, Navier-Stokes momentum, and Monaghan artificial viscosity. Strictly labeled **`Experimental SPH Solver [Unvalidated]`** until passing analytical benchmark test suites.
  - **Delft3D Engine Adapter**: Modular adapter generating authentic Delft3D-FLOW decks (`.mdf`, `.dep`, `.grd`, `.bnd`). If Delft3D binaries are missing, the UI cleanly reports `Delft3D engine not installed` without generating fabricated results.
- **Infrastructure Impact Assessment**: Spatial intersection of maximum flood envelopes against buildings (stratified into Low, Moderate, High, Very High risk), road network losses (km), land use breakdown, and population exposure.
- **Satellite Validation (SAR)**: Bitemporal Sentinel-1 SAR change detection comparison against model prediction (IoU, Precision, Recall, F1 score).
- **Dual Visual Twin**:
  - **2D GIS Dashboard**: MapLibre GL JS engine with timeline animation playback, vector tile rendering, and real-time metric telemetry.
  - **3D Digital Twin**: Three.js viewport with 3D digital elevation mesh, extruded 3D buildings, dam impoundment, and dynamic flood surge wave propagation.
- **GIS Export Center**: Automated shapefile packaging (`.shp`, `.shx`, `.dbf`, `.prj` in ZIP), GeoTIFF rasters (depth, velocity, arrival time), GeoJSON, and printable scientific reports.

---

## 2. Scientific Integrity & Solver Status System

To uphold academic and engineering integrity:
1. **Experimental SPH Solver**:
   - The SPH implementation is strictly labeled `Experimental SPH Solver`.
   - Results are labeled `Experimental / Unvalidated` until verified by the built-in benchmark runner.
   - Includes automated tests against the **Ritter (1892)** analytical solution and **Martin & Moyce (1952)** experimental column collapse.
2. **Delft3D Engine Separation**:
   - Delft3D is kept strictly as an external-engine integration.
   - If Delft3D is not installed on the host machine, the status displays `Delft3D engine not installed`.
   - **Synthetic data is never substituted and claimed to be Delft3D output.**

---

## 3. Technology Stack & Architecture

```text
dam-break-modelling/
├── backend/
│   ├── app/
│   │   ├── api/             # FastAPI REST endpoints
│   │   ├── core/            # Config, SQLite/PostGIS DB session, Background Job Worker
│   │   ├── models/          # SQLAlchemy ORM models & Pydantic schemas
│   │   ├── gis/             # DEMProcessor, OSMFetcher, FloodInundationEngine
│   │   ├── hydrology/       # Froehlich, MacDonald, Von Thun, HydrographGenerator
│   │   ├── hydrodynamics/   # SPHSolver, SPHBenchmarkSuite, Delft3DAdapter, Delft3DParser
│   │   ├── satellite/       # Sentinel1FloodProcessor, SatelliteValidationEngine
│   │   ├── analysis/        # BuildingImpact, RoadImpact, LandUse, PopulationExposure
│   │   └── exports/         # ShapefileExporter, ScientificReportGenerator
│   ├── tests/               # Pytest suites for hydrology, SPH, and API routes
│   └── main.py              # FastAPI server entry point
├── frontend/
│   ├── src/
│   │   ├── components/      # Navbar, TimelineSlider, MetricCards, SPHBenchmarkModal, ExportModal
│   │   ├── map/             # MapLibreMap (2D GIS layers)
│   │   ├── pages/           # ProjectView, DigitalTwin3D, DataSourcesView, ReportView
│   │   ├── services/        # API client
│   │   └── types/           # TypeScript interfaces
│   └── vite.config.ts       # Vite configuration with Tailwind CSS
├── data/                    # Persistent storage (dem, rivers, buildings, simulations)
├── docs/                    # Detailed technical documentation
├── scripts/
│   ├── init_demo_project.py # Seeds Machchhu Dam-II project
│   └── test_framework.py    # End-to-end integration test runner
└── README.md
```

---

## 4. Installation & Quick Start

### Prerequisites
- **Python**: 3.11+
- **Node.js**: v18+ (tested on Node v24)
- **Database**: Built-in local SQLite (`./data/dam_break.db`) for immediate out-of-the-box execution; PostgreSQL + PostGIS supported by configuring `DATABASE_URL` in `.env`.

### Step 1: Environment Setup
```powershell
# Clone or navigate to workspace
cd e:\dam

# Install Python requirements
pip install -r backend/requirements.txt

# Install Frontend dependencies
cd frontend
npm install
cd ..
```

### Step 2: Seed Demonstration Project
Seeds the Machchhu Dam-II (Morbi, Gujarat) project, DEM elevation, OSM layers, and 3 breach scenarios:
```powershell
python scripts/init_demo_project.py
```

### Step 3: Launch Servers

#### Start Backend (Port 8000)
```powershell
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```
- API Docs: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- Health Check: [http://127.0.0.1:8000/api/health](http://127.0.0.1:8000/api/health)

#### Start Frontend (Port 5173)
```powershell
cd frontend
npm run dev
```
- Dashboard: [http://127.0.0.1:5173/](http://127.0.0.1:5173/)

---

## 5. Automated Testing

Run the full suite of automated tests:
```powershell
# Run backend test suites (Hydrology, SPH, and REST APIs)
python -m pytest backend/tests/

# Run complete end-to-end simulation acceptance test
python scripts/test_framework.py
```

---

## 6. Scientific Limitations

1. **Hydraulic Approximations**: Empirically-derived breach formulas provide statistical estimates based on historical embankment failures. Actual geotechnical erosion rates depend on site-specific geotechnical parameters (soil cohesiveness, plasticity index, compaction energy).
2. **SPH Computational Resolution**: The internal SPH solver is an academic/demonstrative engine. For certified regulatory emergency action plans (EAP), Delft3D, TELEMAC-2D, or HEC-RAS 2D should be executed via the provided external adapters.
3. **Population Exposure vs Casualties**: Reported population exposure reflects dwelling footprints within the inundation zone and must not be conflated with fatality predictions, which require dynamic agent-based evacuation modeling.
