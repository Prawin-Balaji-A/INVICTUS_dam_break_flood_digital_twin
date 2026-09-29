# Phase 6 — Assets Required for the Dam-Break Digital Twin

This document lists every external asset the Phase 6 digital twin depends on, where
it must live, and what happens when it is missing. Nothing in Phase 6 fabricates
hydraulics — every flood quantity is read from the verified rasters produced by
`GeneralizedFloodRoutingEngine`. Assets here are visualisation/GIS inputs only.

## 1. 3D dam model (required for photorealistic dam)

| Item | Path | Notes |
|------|------|-------|
| Gravity dam GLB | `frontend/public/models/dam/gravity_dam.glb` | Served at `/models/dam/gravity_dam.glb`. If the file is absent or fails to load, the twin falls back to a procedural masonry gravity dam and shows a notice ("GLB asset loading error — using procedural engineering dam"). No functionality is lost. |

## 2. Authoritative hydraulic rasters (required — the ground truth)

Produced per project by the verified solver and read (never recomputed) by the
twin APIs. Canonical location: `data/<slug>/simulations/baseline_breach/`.

| File | Consumed by | Purpose |
|------|-------------|---------|
| `maximum_depth.tif` | timeline, buildings, roads, impact, flow-vectors | Authoritative flood depth. Drives inundation (≥ 0.15 m), building/road states. |
| `maximum_velocity.tif` | impact, flow-vectors | Authoritative velocity for DEFRA hazard rating and flow speed. |
| `arrival_time.tif` | timeline, flow-vectors | Cumulative arrival — drives the timeline frames and flow direction. |
| `simulation_manifest.json` | timeline, impact | Peak discharge, time-to-peak, reach, hydraulic summary. |
| `flood_extent.geojson` | (optional) sim-id resolution | Locates the output directory for a DB simulation row. |

If depth/arrival rasters are missing the twin endpoints return HTTP 404 with a
clear message rather than inventing data.

## 3. GIS overlays (optional — degrade gracefully)

Globbed from `data/<slug>/`:

| Layer | Path glob | Missing behaviour |
|-------|-----------|-------------------|
| DEM | `dem/processed/*_dem_30m.tif`, `dem/processed/*.tif`, `dem/*.tif` | Elevation feature = 0; impact still computed from hydraulics. |
| River | `river/*.geojson` | `dist_to_river_m` feature = 0. |
| Buildings | `buildings/*.geojson` | `/buildings` returns HTTP 404 (no fabricated footprints). |
| Roads | `roads/*.geojson` | `/roads` returns HTTP 404 (no fabricated roads). |

Buildings and roads are **only** ever drawn from real OSM GIS. There is no
synthetic building/road generator anywhere in Phase 6.

## 4. Dam registry (required for discovery/search)

| Item | Path | Notes |
|------|------|-------|
| India dam registry | `data/dams/india_dams.json` | Backs `/api/dams`, `/api/dams/search`, `/api/dams/{id}`, `/api/dams/{id}/location`. Coordinates validated to India's bounding box by the test suite. |

## 5. Verified project datasets currently shipping simulations

`idukki`, `mettur`, `hirakud`, `srisailam`, `tehri` are flagged
`has_simulation=true` in the registry. Mettur and Idukki have full verified
`baseline_breach` outputs on disk and render in the twin immediately (no re-run).

## 6. Building-height data (honesty note)

OSM footprints rarely carry measured heights. The twin estimates height from
`height`/`building:height` (flagged `height_is_measured=true`) or
`building:levels × 3 m`, else a documented 6 m default (`height_is_measured=false`).
Heights are visualisation-only and never influence the hydraulic depth or state.
