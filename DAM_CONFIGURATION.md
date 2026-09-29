# DAM CONFIGURATION & GENERALIZED DATA ARCHITECTURE
**Project:** Dam Break Inundation Modelling / Flood Digital Twin  
**Version:** Phase 2 Generalized Multi-Dam Architecture  
**Status:** Completed & Tested

---

## 1. Overview & Architectural Hierarchy

The Dam Break Inundation Modelling framework has been generalized from a single-study demonstration into a fully decoupled, multi-dam geospatial architecture capable of modeling any river system without hardcoded regional assumptions.

The core data hierarchy strictly follows:

```
DAM (Engineering Metadata & Provenance)
  ↓
RIVER (Basin, Stream Centerline & Downstream Bearing)
  ↓
STUDY DOMAIN (Bounding Box, UTM Projection & Coordinate Reference System)
  ↓
DATASETS (DEM, Waterways, Infrastructure, Population, Satellite Imagery)
  ↓
SCENARIOS (Breach Formulations, Failure Modes & Dynamic Physical Inputs)
  ↓
SIMULATION CONFIGURATION (Engine Selection, Numerical Tolerances & Gating)
  ↓
RESULTS (Depth Rasters, Velocity Fields, Inundation Vectors & Impact Audits)
```

---

## 2. The Five Target Dams + Demo Project

Six projects are registered as first-class records in the persistent SQLite database (`data/dam_break.db`) and filesystem registry:

| Dam | River Basin | State / Region | Type | Height ($H_d$) | Crest Length | Capacity ($V_w$) | Status | Mode |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Idukki Dam** | Periyar River | Kerala | Double-curvature Arch | 168.91 m | 365.85 m | 1,996 MCM | `NOT CONFIGURED` | Research |
| **Mettur Dam** | Cauvery River | Tamil Nadu | Concrete Gravity | 65.23 m | 1,615.0 m | 2,640 MCM | `NOT CONFIGURED` | Research |
| **Hirakud Dam** | Mahanadi River | Odisha | Composite / Masonry & Earth | 60.96 m | 4,800.0 m | 5,896 MCM | `NOT CONFIGURED` | Research |
| **Srisailam Dam** | Krishna River | Andhra Pradesh / Telangana | Concrete Gravity | 145.10 m | 512.0 m | 8,722 MCM | `NOT CONFIGURED` | Research |
| **Tehri Dam** | Bhagirathi River | Uttarakhand | Earth and Rock-Fill | 260.50 m | 575.0 m | 3,540 MCM | `NOT CONFIGURED` | Research |
| **Machchhu-II** | Machchhu River | Gujarat | Earth-fill / Masonry Spillway | 26.00 m | 1,000.0 m | 110 MCM | `READY` | Demo |

---

## 2A. India-Wide Dam Catalogue vs Five Simulation Study Cases

The framework strictly distinguishes between two operational concepts:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        ALL-INDIA DAM CATALOGUE                              │
│  • Discovery, search, and filtering across all major Indian river basins    │
│  • Verified CWC National Register of Large Dams (NRLD) engineering metadata │
│  • Geographic coordinates, dam type, crest specs, capacity, and operator    │
│  • simulation_enabled = FALSE                                              │
│  • Status: "CATALOGUE ONLY" (No fake flood runs or synthetic rasters)       │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                ┌──────────────────────┴──────────────────────┐
                ▼                                             ▼
┌──────────────────────────────────────────┐    ┌───────────────────────────┐
│     FIVE SIMULATION STUDY CASES          │    │    HISTORICAL DEMO        │
│  1. Idukki Dam (Periyar, Kerala)         │    │  • Machchhu Dam-II        │
│  2. Mettur Dam (Cauvery, Tamil Nadu)     │    │  • Historical verification│
│  3. Hirakud Dam (Mahanadi, Odisha)       │    │  • is_demo = TRUE         │
│  4. Srisailam Dam (Krishna, AP/Telangana)│    │  • Status: "READY"        │
│  5. Tehri Dam (Bhagirathi, Uttarakhand)  │    └───────────────────────────┘
│  • simulation_enabled = TRUE             │
│  • Full End-to-End Hydrodynamic Pipeline │
│    (DEM → SPH → Manning → Extent →       │
│     Exposure → Satellite → 2D/3D → GIS)  │
└──────────────────────────────────────────┘
```

### Critical Rules:
1. **Zero Fake Results for Catalogue Dams**: Searching for a catalogue dam (e.g., Sardar Sarovar, Bhakra, Nagarjuna Sagar, Koyna) displays verified CWC NRLD specifications and explicitly flags: `Simulation Status: "Not available for this study (Catalogue only)"`. The UI disables the `Run Simulation` button.
2. **Simulation Safety Gate**: Any direct API request to `/api/simulation/run` targeting a catalogue-only dam immediately halts with HTTP 400: `"Simulation not available for this study: [Dam Name] is a catalogue-only entry"`.
3. **No Heavy Dataset Acquisition for Catalogue**: Expensive geospatial pipelines (Copernicus DEM 30m, building footprints, road vectors, and SAR imagery) are ingested exclusively for the **five target simulation cases**, avoiding unnecessary data bloat.

---

## 3. Canonical Filesystem Directory Structure

Each study site maintains an isolated data directory inside `data/<slug>/`:

```
data/
├── idukki/
│   ├── metadata.json           # Authoritative engineering parameters & sources
│   ├── datasets.json           # Layer registry, resolution, CRS, & readiness status
│   ├── scenarios.json          # 3 failure mode templates (Froehlich, MacDonald, Von Thun)
│   ├── dem/                    # Target directory for real DEM rasters (GeoTIFF)
│   ├── river/                  # Target directory for OSM river vector (GeoJSON)
│   ├── reservoir/              # Reservoir boundary vector
│   ├── buildings/              # Target directory for OSM/Overture building footprints
│   ├── roads/                  # Target directory for OSM road network lines
│   ├── population/             # Population density grid (WorldPop)
│   ├── satellite/              # Sentinel-1 SAR pre/post flood imagery
│   └── simulations/            # Output depth/velocity GeoTIFFs, GeoJSONs, logs
│
├── mettur/
├── hirakud/
├── srisailam/
├── tehri/
└── machchhu_demo/
```

> **Strict Scientific Integrity Rule**: No synthetic DEMs, sine-wave river centerlines, or random building footprints are copied into the five target dam directories. If a dataset has not been ingested and verified, its status is explicitly recorded as `"status": "not_configured"`.

---

## 4. Metadata Architecture & Provenance Tracking

Dam engineering parameters are validated against official sources (Central Water Commission National Register of Large Dams, Kerala State Electricity Board, Tamil Nadu WRD, Odisha WRD, THDC India). Where engineering values have not yet been independently verified from authoritative literature, they remain `null` or marked `"not_verified"`.

### Canonical `metadata.json` Schema

```json
{
  "id": "idukki",
  "name": "Idukki Dam — Periyar River (Kerala)",
  "dam_name": "Idukki Arch Dam",
  "river": "Periyar River",
  "state": "Kerala",
  "district": "Idukki",
  "country": "India",
  "latitude": 9.8500,
  "longitude": 76.9700,
  "min_lat": 9.7800,
  "min_lon": 76.8800,
  "max_lat": 9.9800,
  "max_lon": 77.0800,
  "downstream_bearing_deg": 315.0,
  "dam_height_m": 168.91,
  "crest_length_m": 365.85,
  "crest_elevation_m": 735.6,
  "full_reservoir_level_m": 732.43,
  "minimum_drawdown_level_m": 707.0,
  "reservoir_capacity_m3": 1996000000.0,
  "reservoir_area_m2": 60000000.0,
  "data_status": "not_configured",
  "is_demo": false,
  "sources": [
    {
      "name": "National Register of Large Dams (NRLD)",
      "publisher": "Central Water Commission, Government of India",
      "year": 2023,
      "license": "Government Open Data",
      "verified": true
    },
    {
      "name": "Kerala State Electricity Board (KSEB) Dam Safety Organisation",
      "url": "https://kseb.in",
      "verified": true
    }
  ]
}
```

---

## 5. Dataset Registry & Data Readiness States

Every project contains a `datasets.json` registry file defining the availability, source, spatial resolution, and Coordinate Reference System (CRS) for all 6 required spatial layers.

### Readiness States
- **`READY`**: Real dataset file exists on disk, spatial extent is verified, and CRS is transformed into metric UTM.
- **`PARTIAL`**: Metadata or bounding box exists, but raster/vector layers are undergoing preprocessing or incomplete.
- **`NOT CONFIGURED`**: Dataset has not yet been ingested; path is `null`. The system prevents downstream hydrodynamic simulation that relies on this dataset.
- **`INVALID`**: File exists but is corrupt, unprojected, or outside the study bounding box.

### Canonical `datasets.json` Schema

```json
{
  "dam_id": "idukki",
  "datasets": {
    "dem": {
      "status": "not_configured",
      "path": null,
      "source": "Copernicus DEM GLO-30 / SRTM 30m (Planned)",
      "resolution_m": 30.0,
      "crs": "EPSG:32643"
    },
    "river": {
      "status": "not_configured",
      "path": null,
      "source": "OpenStreetMap Waterway Centerline (Planned)",
      "crs": "EPSG:4326"
    },
    "buildings": {
      "status": "not_configured",
      "path": null,
      "source": "OpenStreetMap / Overture Maps Foundation (Planned)",
      "crs": "EPSG:4326"
    },
    "roads": {
      "status": "not_configured",
      "path": null,
      "source": "OpenStreetMap Highway Lines (Planned)",
      "crs": "EPSG:4326"
    },
    "population": {
      "status": "not_configured",
      "path": null,
      "source": "WorldPop / Census of India Disaggregated (Planned)",
      "resolution": "100m"
    },
    "satellite": {
      "status": "not_configured",
      "source": "Copernicus Sentinel-1 SAR (Planned)"
    }
  }
}
```

---

## 6. Scenario Formulation Registry

Each dam is pre-configured with three standardized failure templates in `scenarios.json`:
1. **Froehlich (2008) — Overtopping Failure**: Formulated from empirical regression of historical dam failures, predicting average breach width $B_{avg} = 0.27 K_o V_w^{0.32} h_b^{0.04}$ and formation time $t_f = 63.2 \sqrt{V_w / (g h_b^2)}$.
2. **MacDonald & Langridge-Monopolis (1984) — Piping Failure**: Volume of eroded material $V_{eroded} = 0.0261 (V_w h_w)^{0.76}$ and development time $t_f = 0.0179 V_{eroded}^{0.364}$.
3. **Von Thun & Gillette (1990) — Full / Rapid Breach**: Predicts average breach width $B_{avg} = 2.5 h_w + C_b$ and erosion rates for highly erosive materials.

For the five real target dams, scenarios remain in `status = "awaiting_verified_dam_inputs"` until real terrain and reservoir surveys are coupled.

---

## 7. Project Switching & State Isolation Lifecycle

To prevent stale data leakage between dams (e.g., displaying Machchhu simulation metrics on Idukki, or Mettur flood depths on Hirakud), strict state isolation is enforced across both backend and frontend:

### Frontend State Machine on Project Selection
1. User clicks or selects new project from the selector dropdown.
2. `handleSelectProject(project)` is triggered synchronously:
   - `setSimulation(null)` immediately clears previous simulation results.
   - `setCurrentTimeMin(0)` resets the hydrodynamic timeline scrubber.
   - `setIsPlaying(false)` halts any active playback animation.
   - `setSimProgress(0)` clears the simulation progress bar.
3. Map component executes `flyTo` to the new dam's authoritative latitude/longitude and bounds.
4. GeoJSON layers for river, buildings, and roads are re-fetched specifically for `project.id`.
5. Scenarios for the new project are loaded; unconfigured scenarios display `"Awaiting verified dam inputs"` rather than synthetic peak discharge values.
6. The Sources & Data panel queries `/api/projects/{id}/datasets` and `/api/projects/{id}/status`, presenting the active dam's authentic data readiness grid.

---

## 8. Removal of False Scientific Fallbacks

In Phase 2, all fabricated scientific fallbacks identified in Phase 1 have been completely removed from production execution paths:

| Prior False Fallback | Original Location | Phase 2 Remedy |
| :--- | :--- | :--- |
| **`max_physical_head = 24.0`** | `inundation_engine.py` | Removed. Replaced with dynamic project dam height ($H_d$) and reservoir head ($h_{res}$). |
| **South-only row routing (`+Y`)** | `inundation_engine.py` | Removed. Replaced with project downstream bearing angle and DEM steepest-descent flow direction vector. |
| **Fake peak outflow `8,540 m³/s`** | `ProjectView.tsx` | Removed. Replaced with `'—'` and informational status badge awaiting verified hydrograph. |
| **Fake peak outflow `~ 8,500 m³/s`** | `ScenarioCompareModal.tsx` | Removed. Replaced with `'—'`. |
| **Hardcoded depth bound `h ≤ 24.0m`** | `ValidationView.tsx` | Removed. Dynamically bound to active dam's structural height ($H_d$). |
| **Fake Satellite IoU `0.187`** | `ValidationView.tsx`, `sentinel1_flood.py` | Removed. Returns `'—'` and honest `"status": "not_configured"`. |
| **Synthetic sine-wave river** | `overpass_client.py` | Disabled in research mode. Missing river returns empty GeoJSON with `feature_count: 0`. |
| **Random synthetic buildings** | `overpass_client.py` | Disabled in research mode. Missing buildings returns empty FeatureCollection. |
| **Synthetic DEM mathematical slope** | `dem_processor.py` | Gated in research mode. Real projects require verified GeoTIFF. |

---

## 9. Simulation Safety Gating

The simulation trigger endpoint (`POST /api/simulation/run`) now features strict pre-flight dataset verification:

```python
# Simulation Safety Gate in backend/app/api/simulation.py
if not project.is_demo:
    dem_configured = project.dem_path and Path(project.dem_path).exists()
    if not dem_configured:
        raise HTTPException(
            status_code=400,
            detail=f"Simulation unavailable: DEM dataset not configured for {project.dam_name}. "
                   f"In research mode, real dam simulations require a verified DEM."
        )
```

Clicking **Run Simulation** on an unconfigured real dam immediately halts with HTTP 400 and informs the user:
```
Simulation unavailable:
DEM dataset not configured for Idukki Dam — Periyar River. In research mode, real dam simulations require a verified DEM.
```
This guarantees that no synthetic flood runs can accidentally occur for any of the five real Indian dams.

---

## 10. API Specification

The following endpoints provide full visibility into multi-dam configuration and readiness:

- `GET /api/projects`: List all 6 projects (5 real dams + 1 demo) with metadata, coordinates, and `data_status`.
- `GET /api/projects/{id}`: Detailed project metadata and engineering dimensions.
- `GET /api/projects/{id}/datasets`: Complete dataset registry detailing readiness status for DEM, river, buildings, roads, population, and satellite.
- `GET /api/projects/{id}/scenarios`: List of breach scenarios for the project.
- `GET /api/projects/{id}/status`: High-level data readiness summary (`ready`, `partial`, `not_configured`, `invalid`).
