# COMPREHENSIVE REPOSITORY SCIENTIFIC AUDIT REPORT
**Project:** Dam Break Inundation Modelling & Flood Digital Twin Framework  
**Workspace:** `E:\dam`  
**Date:** September 23, 2026  
**Auditor:** Antigravity Autonomous Hydrodynamic Systems Agent  
**Audit Status:** Phase 1 Complete — Ready for Review

---

## 1. Executive Summary

This audit evaluated all backend modules, numerical solvers, hydrology mechanics, GIS pipelines, frontend views, test suites, and persistent data stores in `E:\dam`. 

The repository contains a substantial, functional full-stack foundation with genuine empirical hydrology, real numerical SPH kernel physics, MapLibre 2D GIS visualization, and Three.js 3D rendering. However, several critical shortcuts, mock fallbacks, hard-coded parameters, and disconnected simulation paths were identified. Most critically:
1. **Five-Dam Generalization**: The current data and database represent only a single project (the historic Machchhu Dam-II in Morbi, Gujarat) with 4 empty/dummy database rows for "Periyar River Inundation Study" created by API unit tests. None of the five required Indian dams (**Idukki**, **Mettur**, **Hirakud**, **Srisailam**, **Tehri**) have their complete operational parameters, real DEM rasters, OSM infrastructure, or breach scenarios initialized.
2. **SPH Solver Disconnect**: A genuine 2D vertical-slice Smoothed Particle Hydrodynamics (SPH) solver exists in `backend/app/hydrodynamics/sph/solver.py`, but it is **not** called during a project flood simulation. The simulation endpoint instead routes through `FloodInundationEngine` (a 1D/2D Manning hydraulic routing model) while stamping the result as `"Experimental SPH Solver"`.
3. **Synthetic Fallback Data**: When external APIs (Overpass OSM, Google Earth Engine) fail or are unconfigured, several modules silently synthesize data (random building footprints, a sine-wave river centerline, a synthetic DEM mathematical surface, and a synthetic SAR flood polygon for IoU metrics), directly violating Rule 1.
4. **Hard-coded Parameters**: Key hydraulic variables (such as a maximum head of 24.0 m and downstream flow in `+Y` row direction) are hard-coded to Machchhu Dam-II and will produce invalid results when applied to dams with structural heights of 60 m to 260 m (e.g., Idukki, Tehri).

Below is the detailed item-by-item audit.

---

## 2. Detailed Technical Audit Findings

### 2.1 What Already Works (Scientifically Genuine & Operational)

1. **Empirical Dam Breach Formulations (`backend/app/hydrology/`)**:
   - `froehlich.py`: Implements Froehlich (2008) empirical equations ($B_{avg}$, $W_b$, $W_t$, $t_f$, $Q_p$) parameterized by reservoir storage volume $V_w$, height above breach $h_b$, and failure mode (Overtopping vs Piping).
   - `macdonald.py`: Implements MacDonald & Langridge-Monopolis (1984) breach volume $V_{eroded}$ and formation time $t_f$.
   - `von_thun.py`: Implements Von Thun & Gillette (1990) breach dimensions and erosion rates based on dam height and reservoir volume.
   - All three models are mathematically sound, parameter-driven, and verified by unit tests in `backend/tests/test_hydrology.py`.

2. **Hydraulic Hydrograph Generator (`backend/app/hydrology/hydrograph.py`)**:
   - Uses broad-crested weir hydraulics ($Q = C_w W_b H^{1.5} + 1.2 z H^{2.5}$) and continuous reservoir mass balance routing ($dV = -Q(t) dt$).
   - Properly obeys mass conservation: the total integral $\int Q(t) dt$ does not exceed initial reservoir storage $V_w$ (tested in `test_hydrology.py`).

3. **SPH Numerical Kernel Physics (`backend/app/hydrodynamics/sph/solver.py`)**:
   - Features authentic 2D SPH physics:
     - 2D Wendland $C^2$ smoothing kernel and kernel gradient.
     - Tait Equation of State (EOS): $P = \frac{\rho_0 c_0^2}{\gamma} [(\rho/\rho_0)^\gamma - 1]$.
     - Density summation over neighboring particles: $\rho_i = \sum m_j W_{ij}$.
     - Momentum equation including pressure gradient acceleration, Monaghan artificial viscosity ($\alpha, \beta$), gravity, and Lennard-Jones style repulsive boundary particles.
     - Symplectic position-Verlet time integration with adaptive CFL stability limiting.

4. **SPH Analytical Benchmark Suite (`backend/app/hydrodynamics/sph/benchmarks.py`)**:
   - Implements Ritter (1892) 1D analytical dam-break solution and Martin & Moyce (1952) physical column collapse benchmark.
   - Computes wavefront RMSE, depth $R^2$, and mass conservation error.
   - Honestly marks status as `"Experimental / Unvalidated"` until benchmarks pass acceptance criteria.

5. **Topographic Derivative Processing (`backend/app/gis/dem_processor.py`)**:
   - Priority-flood depression sink-filling algorithm.
   - Vectorized Horn (1981) gradient computation for slope and aspect.
   - Vectorized hillshade generation.
   - Deterministic D8 flow direction and steepest-descent matrix.

6. **Impact Assessment Engines (`backend/app/analysis/`)**:
   - `building_impact.py`: Spatial intersection of building polygon centroids with simulated depth GeoTIFF; categorizes risk into Low (<0.3 m), Moderate (0.3–1.0 m), High (1.0–2.0 m), and Very High (>2.0 m).
   - `road_impact.py`: Shapely line-intersection of OSM highway geometries with flood envelope polygon; computes total and class-stratified submerged length in km.
   - `population.py`: Estimates exposed population within the flood zone based on dwelling footprint occupancy (4.6 persons/household) with clear scientific disclaimers separating exposure from casualties.

7. **Multi-Criteria Result Consistency Validator (`backend/app/validation/result_consistency.py`)**:
   - Checks physical sanity: flags zero flood area with non-zero asset damage, unphysical water depth ($h > 1.25 \times H_{dam}$), excessive velocities, and area discrepancies between raster wet cells and vectorized polygons. Tested in `test_consistency.py`.

8. **ESRI Shapefile ZIP Export (`backend/app/exports/shapefile_exporter.py`)**:
   - Converts GeoJSON layers into ESRI Shapefiles (`.shp`, `.shx`, `.dbf`, `.prj`, `.cpg`) and bundles them into downloadable `.zip` archives with valid `EPSG:4326` projection metadata.

9. **FastAPI REST Backend (`backend/app/api/`) & Static Asset Serving**:
   - Clean async job execution (`JobManager`) tracking `SUBMITTED -> PREPROCESSING -> RUNNING -> POSTPROCESSING -> COMPLETED / FAILED`.
   - Comprehensive endpoints for projects, datasets, scenarios, simulation, benchmarks, satellite, and exports.

10. **Frontend Build & Framework (`frontend/`)**:
    - Vite + React 19 + TypeScript + Tailwind CSS compiles cleanly (`npm run build` succeeds).
    - MapLibre GL 2D map viewer and Three.js 3D viewport components are functional.

---

### 2.2 What Is Partially Implemented

1. **Delft3D Engine Adapter (`backend/app/hydrodynamics/delft3d/adapter.py`)**:
   - **Implemented**: Authentic generation of Delft3D-FLOW input decks: Master Definition (`.mdf`), Depth/Bathymetry (`.dep`), Grid (`.grd`), Boundary location (`.bnd`), and Hydrograph time-series (`.bcc`).
   - **Partially Implemented**: Detects whether `d_flow.exe` or `dimr` is installed on the host. If missing, it correctly halts with a clear error without generating fake output.
   - **Missing**: When Delft3D *is* present, output parsing via `Delft3DParser` (`parser.py`) is rudimentary (only checks for file existence of `trim-*.def` or `*_map.nc`, but does not convert them into standardized depth/velocity rasters).
   - **Missing UI**: The Compare page does not allow running or comparing Delft3D vs SPH side-by-side.

2. **Inundation Spatial Engine (`backend/app/gis/inundation_engine.py`)**:
   - Produces georeferenced GeoTIFFs (`maximum_depth.tif`, `maximum_velocity.tif`, `arrival_time.tif`), `flood_extent.geojson`, and temporal `timesteps.json`.
   - **Limitation**: The routing algorithm routes along raster rows (`r >= r_dam`), which assumes downstream is strictly in the positive row direction (South in north-up rasters). This fails for rivers flowing North, West, or East.
   - **Limitation**: Manning normal depth equation is used instead of a 2D shallow water hydrodynamic solver across complex terrain.

3. **3D Digital Twin View (`frontend/src/pages/DigitalTwin3D.tsx`)**:
   - Three.js canvas renders a 3D terrain mesh, a dam structure, buildings, and an animated water surface.
   - **Partially Implemented**: The terrain mesh is generated from a hard-coded procedural mathematical formula (`slope + valley + hills`) instead of the project's actual DEM GeoTIFF elevation matrix.
   - **Missing**: GLB dam model loading is completely absent (uses a procedural box geometry).

4. **Scenario Compare Modal (`frontend/src/components/ScenarioCompareModal.tsx`)**:
   - Renders a multi-scenario parameter table (breach formulation, width, formation time, peak discharge).
   - **Partially Implemented**: Only compares predefined scenario input parameters. It does not compare actual simulation outputs (flooded area, max depth, max velocity, asset loss) across completed runs.

5. **GIS Exports (`backend/app/api/exports.py`)**:
   - Exports ESRI Shapefile `.zip` and GeoTIFF rasters.
   - **Missing**: KML export (required by problem statement) and direct GeoJSON download endpoints are not implemented.

---

### 2.3 What Is Mocked / Synthetically Generated (Violations of Rule 1)

1. **Synthetic DEM in `backend/app/api/datasets.py` (`generate_dem`)**:
   - Lines 38–48: When generating DEM, it creates an artificial mathematical grid:
     ```python
     y_grad = np.linspace(80.0, 35.0, rows)[:, np.newaxis]
     valley = 15.0 * (x_cross ** 2)
     noise = 4.0 * np.sin(X * 0.8) * np.cos(Y * 0.8)
     elevation = (y_grad + valley + noise).astype(np.float32)
     ```
   - **Impact**: Real topographical terrain is not being fetched or clipped from actual DEMs (SRTM / Copernicus 30m / local elevation datasets).

2. **Synthetic OSM Fallbacks in `backend/app/gis/osm_fetcher.py`**:
   - Lines 21: Overpass API timeout is set to an aggressive `2` seconds.
   - Lines 180–195 (`generate_river_corridor_fallback`): Creates a synthetic sine-wave river LineString.
   - Lines 197–235 (`generate_buildings_fallback`): Creates 120 pseudo-random building polygons (`np.random.seed(42)`).
   - Lines 237–260 (`generate_roads_fallback`): Creates synthetic grid highways.
   - **Impact**: If an Overpass network query times out or is offline, synthetic data is saved into persistent storage (`data/rivers/`, `data/buildings/`) and presented as real OSM data.

3. **Synthetic Satellite SAR Validation in `backend/app/satellite/sentinel1_flood.py`**:
   - Lines 53–70: When Google Earth Engine (GEE) is not configured, `process_sar_flood()` generates a synthetic sine-wave polygon:
     ```python
     for i, lat in enumerate(lats):
         cx = center_lon + (max_lon - min_lon) * 0.12 * np.sin(i * 0.4)
         w = 0.005 + 0.003 * np.sin(i * 0.6)
         coords.append([cx - w, lat])
     ```
   - It then labels this product `"Sentinel-1 SAR Ground Range Detected (GRD) - Copied Product"` and calculates IoU, Precision, Recall, and F1 against it.
   - **Impact**: Generates completely fabricated satellite validation metrics, directly violating Rule 1 & Rule 18.

---

### 2.4 What Is Hard-Coded

1. **Machchhu Dam-II Elevation Head in `inundation_engine.py`**:
   - Line 85: `max_physical_head = 24.0 # Maximum reservoir water head above valley floor for Machchhu-II (dam height 26m)`. This hard-codes 24 m regardless of whether the dam is 65 m (Mettur) or 260 m (Tehri).
2. **Hard-Coded Hydrograph Curve in `ProjectView.tsx`**:
   - Lines 153–159: SVG hydrograph curve has a fixed path:
     `d="M 0,38 Q 20,38 28,5 Q 40,20 60,32 L 100,38"`.
   - Line 147: Peak discharge fallback string: `'8,540 m³/s'`.
3. **Hard-Coded Satellite IoU in `ValidationView.tsx`**:
   - Line 170 & 436: Falls back to `'0.187'` if satellite metrics are missing.
   - Line 153: Hard-coded text `'h ≤ 24.0m'`.
4. **Hard-Coded Peak Discharge in `ScenarioCompareModal.tsx`**:
   - Line 93: Falls back to `'~ 8,500 m³/s'`.
5. **Static Sources Page in `DataSourcesView.tsx`**:
   - The sources list is an inline hard-coded TypeScript constant that does not reflect active database records or actual dataset provenance for the selected project.

---

### 2.5 What SPH Actually Does

- **In Isolation (`backend/app/hydrodynamics/sph/solver.py`)**:
  - The SPH solver is a genuine implementation of 2D Smoothed Particle Hydrodynamics. It creates fluid and boundary particles, evaluates Wendland $C^2$ kernels, calculates density and Tait pressure, applies Monaghan artificial viscosity, and integrates positions using symplectic Verlet steps.
  - It runs real analytical benchmarks (Ritter 1892, Martin & Moyce 1952) and correctly tracks RMSE and mass conservation.
- **In Simulation Pipeline (`backend/app/api/simulation.py`)**:
  - **It is NOT invoked during scenario execution.** Line 94 of `simulation.py` directly calls `FloodInundationEngine.run_inundation_simulation()`, completely bypassing `SPHSolver`. The database record and API response simply set `engine_name = "Experimental SPH Solver"`.
  - **Resolution Needed**: Implement a 2D shallow-water SPH solver or true grid/particle routing that integrates with real DEM topography, OR honestly delineate the solver architecture so that the SPH solver runs for benchmark/channel verification while the 2D hydrodynamic engine handles basin-scale routing without false claims.

---

### 2.6 What Delft3D Actually Does

- **Adapter Structure (`backend/app/hydrodynamics/delft3d/adapter.py`)**:
  - Checks if `d_flow.exe` / `dimr` is found in PATH or standard installation directories.
  - Can generate valid Deltares input files (`.mdf`, `.dep`, `.grd`, `.bnd`, `.bcc`).
  - If Delft3D is not installed, it halts with an explicit error: `"Delft3D engine not installed on host. Please install Deltares Delft3D and configure DELFT3D_PATH in .env."`
  - It does **not** fabricate fake results. This adheres to scientific integrity.
- **What is Missing**:
  - Output grid parsing from actual NetCDF (`*_map.nc`) or binary files into standard GeoTIFF/GeoJSON when Delft3D *is* run.
  - Clear UI state on the Compare page showing `"Delft3D — Not Configured"`.

---

### 2.7 What Satellite Validation Actually Does

- **GEE Integration (`backend/app/satellite/sentinel1_flood.py`)**:
  - Contains code to connect to Google Earth Engine via `earthengine-api` if `GEE_PROJECT_ID` is set.
- **Fallback Behavior**:
  - If GEE is not authenticated (which is the case currently), it generates an artificial sine-wave polygon and calculates IoU, Precision, and Recall against it.
  - **Resolution Needed**: Replace this fabricated fallback with an explicit, honest state:
    `"Satellite Validation — Not Configured (Requires Google Earth Engine credentials or pre-downloaded Sentinel-1 SAR Geotiff/GeoJSON)"`.

---

### 2.8 What Data Currently Exists

In `data/`:
- `dam_break.db`: SQLite database containing 1 Machchhu Dam-II project, 3 scenarios, and 4 empty "Periyar River Inundation Study" rows created by tests.
- `data/dem/ab1c93cc-c249-405d-bff1-23db8e347c11_dem.tif`: 180x180 synthetic DEM raster generated by math formula.
- `data/rivers/ab1c93cc-c249-405d-bff1-23db8e347c11_river.geojson`: 3 KB river centerline.
- `data/rivers/ab1c93cc-c249-405d-bff1-23db8e347c11_roads.geojson`: 1.59 MB roads GeoJSON (from Overpass query).
- `data/buildings/ab1c93cc-c249-405d-bff1-23db8e347c11_buildings.geojson`: 103 KB buildings GeoJSON (from Overpass query).
- `data/simulations/`: Contains simulation runs for Machchhu Dam-II.
- `data/raw/`: Empty.

**There is currently ZERO operational data for the five target dams (Idukki, Mettur, Hirakud, Srisailam, Tehri).**

---

### 2.9 What Idukki Currently Uses

- `NewProjectModal.tsx` contains pre-filled default form fields for "Idukki Arch Dam" (lat: 9.85, lon: 76.97, min_lat: 9.80, min_lon: 76.90, max_lat: 9.95, max_lon: 77.05).
- `backend/tests/test_api.py` posts a project for "Periyar River Inundation Study".
- However, **no DEM raster, no river vector, no building polygons, and no scenarios exist in the database or filesystem for Idukki.** When selected, the UI shows a blank map and no scenarios.

---

### 2.10 What Is Required to Add the Five Dams

Each of the five dams must have an isolated, authoritative data package in `data/<dam_slug>/` containing:
1. **Accurate Dam & Reservoir Engineering Metadata**:
   - Official structural height $H_d$, crest length $L_d$, crest elevation MSL, gross reservoir capacity $V_w$, and normal full reservoir level (FRL).
2. **Georeferenced DEM Elevation GeoTIFF**:
   - Real topographic elevation raster (SRTM 30m / Copernicus 30m / legitimate open elevation dataset) clipped to the downstream study area bounding box.
   - Pre-computed topographic derivatives: hillshade, slope, aspect, flow accumulation.
3. **OpenStreetMap Waterway, Infrastructure & Population Vectors**:
   - Real OSM river/stream channel GeoJSON.
   - Real OSM building footprints GeoJSON with height/levels where available.
   - Real OSM road network GeoJSON categorized by highway class.
   - Real population exposure baseline data (Census of India / WorldPop density).
4. **Pre-configured Breach Scenarios**:
   - Scenario A: Froehlich (2008) Overtopping failure.
   - Scenario B: MacDonald & Langridge-Monopolis (1984) Piping failure.
   - Scenario C: Von Thun & Gillette (1990) Full breach.
   - Calculated breach geometry ($B_{avg}$, $t_f$, $Q_p$) and dynamic hydrograph $Q(t)$.
5. **State Isolation**:
   - Switching dams in the frontend navbar must wipe all stale simulation results, unload previous map layers, update camera bounds to the new dam coordinates, load the new scenarios, update the hydrograph preview, and refresh the sources table.

---

## 3. Recommended Phased Implementation Plan

To systematically meet all acceptance criteria without breaking working code:

```
[Phase 1: AUDIT & SPECIFICATION]  <--- COMPLETED BY THIS REPORT
       │
       ▼
[Phase 2: GENERALIZED DATA MODEL & FIVE-DAM DATASETS]
  ├── Update database schema & project seeder for 5 real Indian dams
  ├── Provide real DEM rasters & OSM layers in data/<dam_id>/
  └── Implement strict data isolation in Frontend & Backend
       │
       ▼
[Phase 3: END-TO-END IDUKKI DAM PROTOTYPE]
  ├── Verify full pipeline for Idukki Dam (Periyar River, Kerala)
  ├── Real DEM -> Froehlich Breach -> Hydrograph Q(t) -> Flood Inundation -> Impacts -> GIS Exports
  └── Eliminate hard-coded parameters (max head, South-only routing)
       │
       ▼
[Phase 4: SPH BENCHMARK VERIFICATION & SOLVER INTEGRATION]
  ├── Calibrate Ritter (1892) & Martin-Moyce (1952) benchmarks to achieve Verified status
  └── Truthful solver labeling: clear distinction between SPH benchmark verification & 2D inundation routing
       │
       ▼
[Phase 5: GENERALIZE TO METTUR, HIRAKUD, SRISAILAM, TEHRI]
  ├── Initialize complete scenarios and datasets for all 4 remaining dams
  └── Test seamless dam switching with zero cross-contamination
       │
       ▼
[Phase 6: DELFT3D INTEGRATION HONESTY & PARSING]
  ├── Support full deck export for any selected dam
  └── Clearly report "Delft3D — Not Configured" on Compare page when binary absent
       │
       ▼
[Phase 7: SATELLITE VALIDATION TRANSPARENCY]
  ├── Remove synthetic sine-wave polygon fallback
  └── Display "Satellite Validation — Not Configured" unless real SAR data exists
       │
       ▼
[Phase 8: 3D DIGITAL TWIN FROM REAL DEM & OPTIONAL GLB DAM MODELS]
  ├── Generate 3D Three.js terrain mesh from active DEM elevation array
  └── Implement optional GLB model loader (assets/dams/<slug>.glb) with procedural fallback
       │
       ▼
[Phase 9: COMPREHENSIVE GIS EXPORTS & DYNAMIC HUD]
  ├── Implement KML export & direct GeoJSON download
  ├── Connect dynamic SVG hydrograph to actual calculated Q(t) points
  └── Ensure dynamic Sources page shows real dataset provenance
       │
       ▼
[Phase 10: REGRESSION & MULTI-DAM ACCEPTANCE TESTING]
  ├── Expand pytest suite to validate all 5 dams
  ├── Update test_framework.py to execute full pipeline on all 5 dams
  └── Verify zero lint errors, zero build errors, zero fake numbers
```

---

## 4. Audit Checklist vs Problem Statement

| Requirement | Audit Status | Phase 2 Resolution |
| :--- | :---: | :--- |
| **Five Real Indian Dams** | ❌ Was Missing | ✅ **Resolved in Phase 2**. Idukki, Mettur, Hirakud, Srisailam, Tehri fully registered with genuine engineering metadata & directory trees. |
| **No Fabricated Results** | ⚠️ Was Partial | ✅ **Resolved in Phase 2**. Removed 8,540 m³/s, 0.187 IoU, synthetic SAR polygon, and synthetic fallbacks from research mode. |
| **Real DEM Topography** | ⚠️ Partial | 🟡 **Architecture Ready (Phase 2)**. Missing DEMs honestly flagged `NOT CONFIGURED`; simulation safely rejects runs until Phase 3. |
| **Empirical Breach Models** | ✅ Fully Working | ✅ **Preserved**. Froehlich, MacDonald, Von Thun templates initialized for all 5 dams without fabricated values. |
| **Hydrograph Q(t)** | ✅ Fully Working | ✅ **Resolved in Phase 2**. Replaced fake 8,540 m³/s curve in frontend with real points or unconfigured status placeholder. |
| **SPH Solver Physics** | ⚠️ Standalone | 🟡 Scheduled for Phase 4 / Phase 5 numerical coupling. |
| **Delft3D Engine** | ⚠️ Input Only | 🟡 Scheduled for Phase 6. |
| **Impact Analysis** | ✅ Fully Working | ✅ Generalized for multi-dam datasets. |
| **2D MapLibre Viewer** | ✅ Fully Working | ✅ Flies to active dam coordinates and renders isolated layers. |
| **3D Three.js Twin** | ⚠️ Partial | 🟡 Scheduled for Phase 8 real DEM extrusion. |
| **GIS Exports** | ⚠️ Partial | 🟡 Preserved for Phase 9. |
| **State Isolation** | ❌ Was Defective | ✅ **Resolved in Phase 2**. Switching dams immediately wipes stale simulations, layers, timeline, and HUD cards. |

---

## 5. Phase 2 Implementation Status (Completed)

Phase 2 ("Generalized Data Model + Five-Dam Configuration") was successfully implemented on September 23, 2026:

1. **Five Real Indian Dam Configurations Initialized**:
   - `data/idukki/`, `data/mettur/`, `data/hirakud/`, `data/srisailam/`, `data/tehri/` directories created with canonical `metadata.json`, `datasets.json`, `scenarios.json`.
   - `data/machchhu_demo/` created to isolate Machchhu Dam-II historical demonstration data (`is_demo = True`).
   - Zero synthetic DEM rasters or fake infrastructure copied into the five new dam directories.

2. **Database & Schema Generalization**:
   - SQLite `projects` table extended with `slug`, `is_demo`, `data_status`, `dam_height_m`, `crest_length_m`, `crest_elevation_m`, `full_reservoir_level_m`, `reservoir_capacity_m3`, `reservoir_area_m2`, `downstream_bearing_deg`.
   - SQLite `scenarios` table extended with `status`.
   - Pydantic v2 schemas modernized; `ProjectStatusResponse` and `DatasetsResponse` endpoints exposed.

3. **Strict Project State Isolation**:
   - In `frontend/src/App.tsx`, `handleSelectProject` resets `simulation`, `currentTimeMin`, `isPlaying`, `simProgress` to `null`/zero upon switching dams.
   - Prevents stale Idukki data displaying on Mettur, or Machchhu simulation remaining visible on Idukki.

4. **Elimination of False Scientific Fallbacks**:
   - Removed `max_physical_head = 24.0` in `inundation_engine.py`; generalized to dynamic dam structural height.
   - Removed south-only row routing assumption; generalized to downstream bearing angle and D8 flow direction vectors.
   - Removed fake `8,540 m³/s` and `~ 8,500 m³/s` peak discharge fallbacks across `ProjectView.tsx` and `ScenarioCompareModal.tsx`.
   - Removed hardcoded `h ≤ 24.0m` bound and fake `0.187` IoU satellite scores in `ValidationView.tsx`.
   - Disabled synthetic sine-wave SAR polygon in `sentinel1_flood.py`.

5. **Simulation Safety Gating**:
   - `POST /api/simulation/run` verifies DEM presence for non-demo projects. Rejects missing DEMs with HTTP 400 (`"Simulation unavailable: DEM dataset not configured for [Dam Name]"`).

6. **Automated Verification**:
   - Added `backend/tests/test_five_dams.py` (7 multi-dam integration tests). Total backend test suite passes: 19 passed in 1.95s.
   - Frontend build (`npm run build`) and lint (`npm run lint`) pass with 0 errors.

---
*End of Audit Report.*
