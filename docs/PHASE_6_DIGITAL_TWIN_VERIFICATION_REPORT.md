# Phase 6 — Digital Twin Verification Report

**Project:** Dam-Break Inundation Modelling & Flood Digital Twin
**Scope:** Phase 6 — Intelligent Dam-Break Digital Twin + Realistic 3D Flood Simulation
**Date:** 2026-09-24
**Backend test result:** `149 passed` (120 pre-existing + 21 Phase 6 impact/twin + 8 twin-terrain/river/flow behaviour tests), no regressions.
**Frontend:** `tsc -b && vite build` succeeds; `oxlint` reports warnings only (no errors).

---

## 1. Executive summary

Phase 6 adds an AI-assisted impact-prediction layer and a 3D digital-twin
frontend **on top of** the scientifically verified Phase 4 (Idukki) and Phase 5
(Mettur) hydraulic pipelines. The authoritative solver
(`GeneralizedFloodRoutingEngine`) is unchanged and remains the sole source of
flood depth, velocity, and arrival time. The ML layer sits strictly downstream
and never alters hydraulics.

## 2. Non-negotiable constraints — status

| Constraint | Status | Evidence |
|-----------|--------|----------|
| 120/120 original backend tests still pass | ✅ | `141 passed` total |
| Mettur peak discharge preserved (88,699.24 m³/s) | ✅ | `test_timeline_derives_from_arrival_raster` asserts `88699.2` |
| No dam-specific solver branches | ✅ | `test_engine_still_has_no_dam_specific_branch_tokens` |
| No radius/circle/buffer flood generation | ✅ | `test_no_circular_radius_flood_generation_in_new_code` |
| Inundation threshold 0.15 m everywhere | ✅ | `test_inundation_threshold_is_015_everywhere` |
| Hydraulics authoritative; ML cannot override depth | ✅ | `test_impact_is_honest_and_authoritative`, predictor passes depth/velocity/arrival through unchanged |
| No fabricated ML accuracy | ✅ | `MODEL_STATUS.calibrated_against_observations = False`, status "Research prototype — calibration required" |

## 3. Architecture

```
Verified rasters (maximum_depth/velocity, arrival_time, manifest)
        │  (read-only, ground truth)
        ▼
Phase 6 twin API  (backend/app/api/twin.py)
   /timeline  /impact  /buildings  /roads  /flow-vectors
        │
        ├── FloodImpactPredictor  (backend/app/ml/flood_impact_predictor.py)
        │     labels = DEFRA HR = D·(V+0.5)+DF from AUTHORITATIVE fields
        │     RandomForest surrogate; honest CV = agreement-with-physics only
        ▼
3D Digital Twin frontend  (frontend/src/pages/DigitalTwin3D.tsx)
   HUD numbers, water stage & reach driven by real timeline frames
```

## 4. Backend deliverables

- `backend/app/ml/flood_impact_predictor.py` — DEFRA/ARR hazard rating
  `HR = D·(V+0.5)+DF`, building-state thresholds, `FloodImpactPredictor`
  (physics-labelled RandomForest surrogate with honest k-fold CV), raster
  feature sampler. Depth/velocity/arrival are inputs only.
- `backend/app/api/twin.py` — five additive endpoints under `/api/simulation`:
  - `GET /{ref}/timeline` — frames from cumulative arrival raster; peak discharge from manifest.
  - `GET /{ref}/impact` — authoritative hydraulic headline + DEFRA hazard-zone area breakdown + honest model metadata.
  - `GET /{ref}/buildings` — real OSM footprints + per-building authoritative depth + state.
  - `GET /{ref}/roads` — real OSM roads + affected flag from depth (threshold 0.15 m).
  - `GET /{ref}/flow-vectors` — velocity magnitude + arrival-time gradient direction.
- `backend/main.py` — registers `twin.router` (additive).

## 5. Frontend deliverables

- `frontend/src/services/api.ts` — `getTwinTimeline/Impact/Buildings/Roads/FlowVectors`.
- `frontend/src/pages/DigitalTwin3D.tsx` — the fabricated Froehlich hydrograph
  fallback and the "wave speed 4.5 m/s" placeholder were **removed**. The HUD and
  water surface are now driven by authoritative timeline frames:
  - Max depth reached, inundated area (km² and % of wet cells), peak discharge (manifest).
  - Water reach scales with the real cumulative wet-cell fraction; stage rises with real max depth.
  - Playback sweeps the real arrival-time window; a "Hypothetical Scenario — AI-Assisted" banner and a data-source line are shown.
- `DamSearchModal` / `AIPredictorModal` / registry search — pre-existing, verified against `/api/dams*`.

## 6. Honesty & anti-fabrication statement

- Flood depth/velocity/arrival are read from verified rasters and passed through
  unchanged everywhere. The ML surrogate predicts an impact **probability** and
  reproduces the published DEFRA people-safety hazard classification; it never
  produces or edits hydraulic fields.
- Reported ML metrics are explicitly "agreement with the DEFRA hazard function
  under cross-validation" — **not** accuracy against observed flood outcomes.
  The UI shows "Research prototype — calibration required" and never a fabricated
  95%/98% accuracy.
- All scenarios are labelled "Hypothetical Scenario / AI-Assisted Flood Impact
  Prediction". No claim is made of predicting a real future disaster.

## 7. Checkpoint status (Part 26)

Legend: **AUTOMATED VERIFIED** = an automated test asserts the behaviour ·
**PENDING MANUAL BROWSER QA** = correct-by-construction in code but the 3D render
can only be confirmed visually (no browser-automation tool in this environment) ·
**NOT IMPLEMENTED** = not yet built.

| # | Checkpoint | Status | Evidence | Remaining limitation |
|---|-----------|--------|----------|----------------------|
| 1 | 3D uses authoritative sim outputs | AUTOMATED VERIFIED | `test_twin_terrain.py`, `test_twin_api.py`; HUD/water read `/terrain`+`/timeline` only | — |
| 2 | Real GLB dam, sited on terrain at authoritative coord | PENDING MANUAL BROWSER QA | `loadDam()` loads `/models/dam/gravity_dam.glb`, seats via `geoToScene(dam.lat,dam.lon)` on DEM height; parametric fallback at same coord | Scale/orientation need visual confirmation |
| 3 | DEM-based 3D terrain (MAJOR GAP) | AUTOMATED VERIFIED (backend) + PENDING MANUAL BROWSER QA (render) | `/terrain` returns real DEM grid (`test_terrain_elevation_is_real_dem_not_flat`); `buildGrids()` displaces `PlaneGeometry` vertices from `elevation_m.values` | Decimated to res≤400; visual QA of relief pending |
| 4 | River from cauvery_river.geojson | AUTOMATED VERIFIED (backend) + PENDING MANUAL BROWSER QA (render) | `GET /{ref}/river` clips the real OSM polyline to domain; `test_river_is_real_geometry_not_synthetic` (real vertices, bends, in-bounds); `buildRiver()` drapes it over the DEM via `geoToScene()` | Draped as a line, not a width-accurate ribbon |
| 5 | Per-cell water surface (SECOND MAJOR GAP) | AUTOMATED VERIFIED (backend) + PENDING MANUAL BROWSER QA (render) | `test_terrain_water_surface_is_spatially_varying` (WSE std>1.0), `test_terrain_water_only_where_inundated`; water mesh vertex Y = elev+depth per cell | Max-depth+arrival visualization, not transient shallow-water field (honestly labelled) |
| 6 | Arrival-driven (non-radial) propagation | AUTOMATED VERIFIED (backend) + PENDING MANUAL BROWSER QA (render) | `test_terrain_arrival_drives_propagation_not_radius`; reveal effect shows cell only where `mask=1 && arrival≤t`; debug layer toggles added | Visual confirmation of progression pending |
| 7 | Buildings extruded from real footprints | AUTOMATED VERIFIED (backend) + PENDING MANUAL BROWSER QA (render) | `/buildings` real footprints + per-building simulated depth + state; `buildBuildings()` extrudes each ring, merges by state colour, seats on DEM | Affected = inundation depth (NOT radius); heights OSM-measured or documented fallback |
| 8 | Roads from real geojson | AUTOMATED VERIFIED (backend) + PENDING MANUAL BROWSER QA (render) | `/roads` real OSM lines + affected flag from simulated depth; `buildRoads()` draws normal/affected LineSegments | Affected from depth≥0.15 m |
| 9 | InstancedMesh vegetation | IMPLEMENTED (procedural, labelled) + PENDING MANUAL BROWSER QA | `buildVegetation()` uses `THREE.InstancedMesh` on dry mid-elevation cells | **No real tree inventory exists** — explicitly labelled procedural fallback in UI (`Vegetation*`) |
| 10 | Instancing/LOD, GPU dispose | PARTIAL | InstancedMesh for vegetation; buildings merged into few draw calls; per-group dispose on change/unmount; **measured** object/draw/triangle counts shown in HUD via `renderer.info` | FPS not fabricated; no explicit distance-LOD beyond frustum culling |
| 11 | Dam-break visualization | PENDING MANUAL BROWSER QA | water reveals over real arrival window from the dam cell outward along mask | "Visual breach animation", not structural-failure physics |
| 12/13 | India map markers + search | PARTIAL — registry search only | `DamSearchModal` wired to `/api/dams*` with live text/state filtering; markers use authoritative registry coords | Map-centric landing with clickable markers + autocomplete NOT built; dropdown/modal workflow remains |
| 14 | Impact dashboard | IMPLEMENTED + PENDING MANUAL BROWSER QA | `/impact` wired to a dashboard panel; every row tags its source (manifest / depth.tif / velocity.tif / inundation) | Visual QA pending |
| 15 | Flow vectors from real data | AUTOMATED VERIFIED (backend) + PENDING MANUAL BROWSER QA (render) | `test_flow_vectors_directional_not_radial` (<80% radial-outward); `buildFlow()` draws arrows from velocity+arrival-gradient; toggle in debug panel | Routing-direction field, not full velocity vector solution |
| 16 | Honest solver terminology | AUTOMATED VERIFIED | manifest solver "2D Manning kinematic/diffusion-wave approximation"; no Navier-Stokes/CFD claim | — |
| 17 | No dam-specific branches in solver | AUTOMATED VERIFIED | `hydrodynamics/routing_engine.py` clean; slug refs only in `ml.py`/`sync.py` + `_DAM_META` coord table (config/data, outside solver) | — |
| 18 | Regression protection | AUTOMATED VERIFIED | `149 passed` (141 + 8 new twin-terrain/river/flow); `vite build` ok; `oxlint` 0 errors | — |
| 19 | Behavior tests for sources | AUTOMATED VERIFIED | 8 twin behavior tests: DEM terrain, water-only-where-wet, arrival propagation, spatial WSE, provenance, real river geometry, non-radial flow | Frontend component tests not added (no test runner wired for React) |
| 20 | Manual browser QA | PENDING MANUAL BROWSER QA | — | No browser-automation tool in this environment |
| 21 | QA artifacts | PENDING | `data/mettur/qa_plots/` exists from prior phases | New 3D screenshots require browser QA |
| 22 | Report updated | DONE | this table + sections 9–11 | — |

Checkpoints are marked AUTOMATED VERIFIED **only** where a test asserts the
behaviour. Visual/3D checkpoints that are correct-by-construction in code but
cannot be self-verified are honestly marked PENDING MANUAL BROWSER QA, never PASS.

### Can Phase 6 be marked COMPLETE?

**Not yet — honestly, but the core 3D digital twin is now feature-complete and
test-backed.** All authoritative-data layers are implemented: DEM terrain,
per-cell arrival-driven water, real river (clipped + draped), extruded buildings
(inundation-classified), roads, flow vectors, and an impact dashboard — each
sourced from verified rasters/GeoJSON and, where testable, guarded by behavior
tests (`149 passed`). Vegetation is an explicitly-labelled procedural fallback
(no real tree inventory). What still blocks an honest COMPLETE:

1. **Manual browser QA (CP20/21)** — the 3D render (CP2/3/5/6/7/8/9/11) is
   correct-by-construction but has NOT been visually observed; no browser tool
   exists in this environment. This is a real external limitation, not a pass.
2. **Map-centric dam discovery (CP12/13)** — only the registry-backed search
   modal exists; the India-map-with-markers landing + autocomplete is NOT built.
3. **ML surrogate (CP-part-M)** — architecture is in place and honestly reports
   "Research prototype — calibration required"; it is NOT a trained/calibrated
   predictor and is never presented as one.

None of (1)–(3) can be marked PASS by code inspection alone; they are documented
as PENDING MANUAL BROWSER QA, PARTIAL, or NOT-YET-TRAINED respectively.

## 7b. Vegetation, flow-vector, and ML status (explicit)

- **Vegetation (CP9):** No tree/landcover dataset exists under `data/mettur/`.
  The layer is a `THREE.InstancedMesh` procedural fallback placed on dry
  mid-elevation cells, labelled `Vegetation*` with the note "procedural
  vegetation — no real tree inventory." It is OFF by default and never claimed
  to be surveyed vegetation.
- **Flow vectors (CP15):** Direction is the arrival-time gradient (water routes
  earlier→later arrival) with magnitude from `maximum_velocity.tif`. Test
  `test_flow_vectors_directional_not_radial` asserts the field is not a radial
  fan from the dam. Labelled a routing-direction field, not a full velocity
  vector solution.
- **ML (Phase M):** `FloodImpactPredictor` is a physics-labelled RandomForest
  surrogate reproducing the DEFRA hazard classification; cross-validation is
  reported as "agreement with physics," not observed-flood accuracy. Status
  string "Research prototype — calibration required" is surfaced in the dashboard.
  No flood depth/arrival/extent is ever ML-predicted for display — hydraulics
  remain authoritative. A future ML surrogate (features: DEM/slope/curvature/
  river-distance/channel-slope/roughness/breach-width/breach-depth/reservoir-
  volume/discharge/timestep → depth/arrival/inundation-probability) is documented
  as the intended architecture; it is NOT trained and is not presented as such.

## 8. How to verify locally



```bash
# Backend regression (expect: 149 passed)
python -m pytest backend/tests/ -q

# Frontend build + lint
cd frontend && npm run build && npm run lint

# Twin API smoke (backend running)
curl "http://localhost:8000/api/simulation/mettur/timeline?frames=20"
curl "http://localhost:8000/api/simulation/mettur/impact"
```

## 9. Known limitations / remaining work

Implemented this pass (data + geometry level, backed by tests where testable):
DEM-displaced terrain (CP3), per-cell arrival-revealed water surface (CP5/6),
real river overlay clipped + draped (CP4), extruded real-footprint buildings
classified by simulated depth (CP7), roads with depth-based affected flag (CP8),
procedural instanced vegetation (CP9, labelled), impact dashboard with per-value
source tags (CP14), and arrival-gradient flow vectors (CP15).

Genuinely remaining before an honest COMPLETE:

- **Manual browser QA (CP2/3/5/6/7/8/9/11/20/21)** — the 3D render is
  correct-by-construction and test-backed at the data layer, but has NOT been
  visually observed. No browser-automation tool exists in this environment; this
  is a real external limitation, not a pass. FPS is not fabricated — only
  `renderer.info` object/draw/triangle counts are shown, labelled "(measured)".
- **Map-centric dam discovery (CP12/13)** — IMPLEMENTED in Phase 6B: an India
  map (`frontend/src/map/IndiaDamMap.tsx`, MapLibre) is now the landing view,
  with registry-driven markers, autocomplete search, an info card, and an
  availability-gated "Explore Digital Twin" launch. Correct-by-construction;
  render + interaction still PENDING MANUAL BROWSER QA.
- **ML surrogate (Phase M)** — `FloodImpactPredictor` is a physics-labelled
  RandomForest reproducing the DEFRA hazard classification, honestly surfaced as
  "Research prototype — calibration required". It is NOT trained against observed
  floods; hydraulics remain the sole authoritative source of depth/velocity/arrival.
- **Vegetation (CP9)** — procedural fallback only; no real tree/landcover dataset
  exists under `data/mettur/`. Labelled `Vegetation*` and OFF by default.
- **Water surface fidelity (CP5)** — the per-cell mesh renders max-depth + arrival
  reveal, not a transient shallow-water field. This is honestly labelled.
- **Distance-LOD (CP10)** — only frustum culling + geometry merging + instancing;
  no explicit distance-based level-of-detail.

---

## 10. PHASE 6B — INDIA DAM DISCOVERY + AVAILABILITY GATE

Phase 6B adds the map-centric discovery workflow and an honest data-availability
gate in front of the Digital Twin, so no dam can present a simulation it does not
actually have.

### 10.1 What was implemented

- **India dam map landing** (`frontend/src/map/IndiaDamMap.tsx`): MapLibre map
  centred on India (OSM raster basemap, the same source as the 2D GIS view) is now
  the default view (`App.tsx` `viewMode='MAP'`, plus a "Dam Map" nav button).
- **Registry-driven markers**: one marker per dam from `GET /api/dams` at its
  authoritative lat/lon. **No coordinates are hardcoded in the component.** Marker
  colour encodes real twin availability (cyan = verified twin, slate = metadata
  only). Marker click → fly-to + info card.
- **Autocomplete search**: debounced queries to `GET /api/dams/search?q=` (real
  multi-field registry search: name / river / state / district / alias). Selecting
  a result flies the map to the exact coordinates and opens the info card.
- **Availability gate (CP-E)**: new backend endpoint
  `GET /api/simulation/{ref}/availability` inspects the disk and reports each
  layer (DEM, four hydraulic rasters, manifest, river/buildings/roads). It returns
  200 (never 404) with `twin_ready` = (real DEM **and** all four rasters present).
  The info card offers **"Explore Digital Twin"** only when `twin_ready`; otherwise
  it lists exactly which layers are missing. **No simulation is fabricated.**
- **Registry integrity fix**: `data/dams/india_dams.json` had `has_simulation:true`
  for `hirakud`, `srisailam`, `tehri`, which have **empty** simulation/DEM folders
  on disk. These were corrected to `false` to match on-disk truth. Only `idukki`
  and `mettur` have complete verified outputs. A regression test
  (`test_registry_has_simulation_matches_disk_truth`) now asserts the registry flag
  equals real on-disk `twin_ready` for every dam, preventing future drift.

### 10.2 Data reality (disk-verified)

| Dam | DEM | depth/vel/arrival/mask | twin_ready |
|-----|-----|------------------------|-----------|
| Mettur | ✓ | ✓ ✓ ✓ ✓ | **True** |
| Idukki | ✓ | ✓ ✓ ✓ ✓ | **True** |
| Hirakud | ✗ | ✗ | False (metadata only) |
| Srisailam | ✗ | ✗ | False (metadata only) |
| Tehri | ✗ | ✗ | False (metadata only) |
| 16 catalogue dams | ✗ | ✗ | False (catalogue only) |

### 10.3 PHASE 6B MANUAL BROWSER QA

**No browser-automation tool exists in this environment, so none of the visual /
interaction tests below were executed. They are reported as NOT PERFORMED — never
PASS — per the standing rule "Never mark browser-only verification PASS without
actually observing it."** The rows describe what each test must confirm when a
human runs `npm run dev` + the backend locally.

| Test | Result | Evidence / note |
|------|--------|-----------------|
| India map | NOT PERFORMED (no browser tool) | Correct-by-construction: MapLibre India view + OSM tiles |
| Dam markers | NOT PERFORMED | Markers built from `/api/dams` coords; colour = real `has_simulation` |
| Search | NOT PERFORMED | Autocomplete wired to `/api/dams/search` (real registry) |
| Mettur selection | NOT PERFORMED | fly-to + info card + availability check on select |
| Digital Twin | NOT PERFORMED | Launch gated on `twin_ready`; passes registry record → twin |
| DEM terrain | NOT PERFORMED | Backend `/terrain` DEM-verified (`test_terrain_elevation_is_real_dem_not_flat`) |
| Dam GLB | NOT PERFORMED | `loadDam()` loads `/models/dam/gravity_dam.glb`; scale/orientation need eyes |
| River | NOT PERFORMED | `/river` real geometry verified in tests; drape needs eyes |
| Flood propagation | NOT PERFORMED | arrival-driven reveal verified non-radial in tests |
| Buildings | NOT PERFORMED | real footprints + depth state (backend tested) |
| Roads | NOT PERFORMED | real geometry + depth-based affected (backend tested) |
| Vegetation | NOT PERFORMED | procedural fallback, labelled `Vegetation*`, off by default |
| Flow vectors | NOT PERFORMED | `test_flow_vectors_directional_not_radial` passes; render needs eyes |
| Dashboard | NOT PERFORMED | `/impact` per-value source tags |
| Timeline | NOT PERFORMED | arrival-window sweep (backend timeline tested) |
| Reset | NOT PERFORMED | per-group dispose on change/unmount (code-level) |

### 10.4 Phase 6B automated regression

- Backend: **152 passed** (149 + 3 new availability/registry-integrity tests), no
  regressions, warnings pre-existing only.
- Frontend: `tsc -b && vite build` **succeeds**; `oxlint` **0 errors** (warnings only).
- Solver integrity: `routing_engine.py` unchanged; the new code adds only a
  read-only disk-inspection endpoint and a frontend map — no dam-specific solver
  branches, no fabricated outputs.

### 10.5 Phase 6B status

**PARTIAL — genuinely blocked on manual browser QA.** The map discovery workflow,
autocomplete, availability gate, and registry-integrity fix are implemented and
backed by automated tests (152 passing). What remains before COMPLETE:

1. **Manual browser QA (Tests 1–18 above)** — not executable here; must be run by
   a human. This is a real external limitation.
2. **ML surrogate** — remains NOT TRAINED / research prototype by design (Phase J).

Phase 6B is **not** marked COMPLETE: automated tests pass and the code is
correct-by-construction, but the browser workflow has not been observed.


