"""
Phase 6 Digital Twin API
========================
Additive endpoints that expose the AUTHORITATIVE hydraulic simulation outputs
(depth/velocity/arrival rasters + flood-extent polygon) plus the physics-informed
impact layer to the 3D digital twin frontend. These endpoints never recompute or
alter hydraulics -- they read the verified rasters produced by
GeneralizedFloodRoutingEngine and layer GIS + impact classification on top.

A simulation is addressed by `sim_ref`, which resolves in order:
  1. A Simulation DB row id (a live/previous run).
  2. A project slug/id -> its canonical verified simulation directory on disk
     (data/<slug>/simulations/baseline_breach). This lets the twin render the
     verified Mettur/Idukki scenarios without re-running a job.
"""
import json
from pathlib import Path
from functools import lru_cache
from typing import Dict, Any, List, Optional, Tuple

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy.orm import Session
from fastapi import Depends
import numpy as np

from backend.app.core.database import get_db
from backend.app.core.config import settings
from backend.app.models.project import Project
from backend.app.models.simulation import Simulation
from backend.app.ml.flood_impact_predictor import (
    FloodImpactPredictor,
    sample_features_at_points,
    building_state_from_depth,
    flood_hazard_rating,
    hazard_class_from_rating,
    INUNDATION_THRESHOLD_M,
    MODEL_STATUS,
)

router = APIRouter(prefix="/api/simulation", tags=["Digital Twin"])

# Dam metadata for coordinates (also available via /api/dams registry).
_DAM_META = {
    "mettur": {"lat": 11.8028, "lon": 77.8017, "height_m": 65.23},
    "idukki": {"lat": 9.8497, "lon": 76.9744, "height_m": 168.91},
    "hirakud": {"lat": 21.5700, "lon": 83.8700, "height_m": 60.96},
    "srisailam": {"lat": 16.0872, "lon": 78.8986, "height_m": 145.1},
    "tehri": {"lat": 30.3783, "lon": 78.4800, "height_m": 260.5},
}


def _resolve_sim(sim_ref: str, db: Session) -> Dict[str, Any]:
    """Resolve sim_ref to an output directory + project context."""
    sim = db.query(Simulation).filter(Simulation.id == sim_ref).first()
    slug = None
    out_dir = None
    if sim is not None:
        proj = db.query(Project).filter(Project.id == sim.project_id).first()
        slug = (proj.slug or proj.id) if proj else None
        if sim.flood_extent_geojson and Path(sim.flood_extent_geojson).exists():
            out_dir = Path(sim.flood_extent_geojson).parent
        else:
            cand = settings.SIMULATIONS_DIR / sim.id
            out_dir = cand if cand.exists() else None

    if out_dir is None:
        # Treat sim_ref as a project slug -> canonical verified simulation.
        slug = sim_ref.lower()
        cand = settings.DATA_DIR / slug / "simulations" / "baseline_breach"
        if cand.exists():
            out_dir = cand

    if out_dir is None or not out_dir.exists():
        raise HTTPException(status_code=404,
                            detail=f"No simulation outputs found for '{sim_ref}'")

    manifest = {}
    man_p = out_dir / "simulation_manifest.json"
    if man_p.exists():
        with open(man_p, "r", encoding="utf-8") as f:
            manifest = json.load(f)

    meta = _DAM_META.get(slug, {})
    dam_lat = manifest.get("dam_config", {}).get("dam_lat", meta.get("lat"))
    dam_lon = manifest.get("dam_config", {}).get("dam_lon", meta.get("lon"))
    reach_km = manifest.get("hydraulic_summary", {}).get("reach_km", 5.0) or 5.0

    return {
        "slug": slug, "out_dir": out_dir, "manifest": manifest,
        "dam_lat": dam_lat, "dam_lon": dam_lon, "reach_km": reach_km,
    }


def _project_gis(slug: str) -> Dict[str, Optional[Path]]:
    base = settings.DATA_DIR / slug
    def _first(*globs):
        for g in globs:
            hits = list(base.glob(g))
            if hits:
                return hits[0]
        return None
    return {
        "dem": _first("dem/processed/*_dem_30m.tif", "dem/processed/*.tif", "dem/*.tif"),
        "river": _first("river/*.geojson"),
        "buildings": _first("buildings/*.geojson"),
        "roads": _first("roads/*.geojson"),
    }


def _load_geom(path: Optional[Path]):
    if not path or not Path(path).exists():
        return None, None
    import geopandas as gpd
    gdf = gpd.read_file(path)
    try:
        union = gdf.geometry.union_all()
    except Exception:
        union = gdf.unary_union
    return gdf, union


def _prop(row, key):
    """Return a JSON-safe scalar from a GeoDataFrame row (NaN -> None)."""
    try:
        v = row.get(key)
    except Exception:
        return None
    if v is None:
        return None
    try:
        if isinstance(v, float) and (np.isnan(v) or np.isinf(v)):
            return None
    except Exception:
        pass
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        return float(v)
    return v


def _json_safe(obj):
    """Recursively replace non-finite floats with None for JSON compliance."""
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    if isinstance(obj, float):
        return obj if (obj == obj and obj not in (float("inf"), float("-inf"))) else None
    return obj


# Cache trained impact surrogates per project slug (physics-labelled, per scenario).
_predictor_cache: Dict[str, FloodImpactPredictor] = {}


def _get_predictor(ctx: Dict[str, Any]) -> FloodImpactPredictor:
    slug = ctx["slug"]
    if slug in _predictor_cache:
        return _predictor_cache[slug]

    import rasterio
    gis = _project_gis(slug)
    _, river_geom = _load_geom(gis["river"])
    _, roads_geom = _load_geom(gis["roads"])

    depth_p = ctx["out_dir"] / "maximum_depth.tif"
    pts: List[Tuple[float, float]] = []
    if depth_p.exists():
        with rasterio.open(depth_p) as ds:
            b = ds.bounds
            n = 45
            lons = np.linspace(b.left, b.right, n)
            lats = np.linspace(b.bottom, b.top, n)
            for la in lats:
                for lo in lons:
                    pts.append((float(la), float(lo)))

    predictor = FloodImpactPredictor()
    if pts:
        feats = sample_features_at_points(
            pts, ctx["out_dir"], dem_path=gis["dem"], river_geom=river_geom,
            roads_geom=roads_geom, dam_lat=ctx["dam_lat"], dam_lon=ctx["dam_lon"],
            reach_km=ctx["reach_km"],
        )
        try:
            predictor.fit(feats)
        except Exception:
            pass
    _predictor_cache[slug] = predictor
    return predictor


@router.get("/{sim_ref}/availability")
def get_availability(sim_ref: str, db: Session = Depends(get_db)):
    """
    Report EXACTLY which authoritative data layers exist on disk for a study
    case, WITHOUT fabricating a simulation. Never raises 404 -- a dam with only
    metadata returns twin_ready=False with each missing layer flagged. This is
    the honest gate the frontend uses before offering "Explore Digital Twin":
    a Digital Twin is only opened when every required hydraulic raster + DEM is
    genuinely present.
    """
    slug = sim_ref.lower()
    # Prefer a real DB simulation output dir; else the canonical verified dir.
    out_dir: Optional[Path] = None
    sim = db.query(Simulation).filter(Simulation.id == sim_ref).first()
    if sim is not None and sim.flood_extent_geojson and Path(sim.flood_extent_geojson).exists():
        out_dir = Path(sim.flood_extent_geojson).parent
        proj = db.query(Project).filter(Project.id == sim.project_id).first()
        slug = (proj.slug or proj.id) if proj else slug
    if out_dir is None:
        cand = settings.DATA_DIR / slug / "simulations" / "baseline_breach"
        out_dir = cand if cand.exists() else None

    def _exists(name: str) -> bool:
        return out_dir is not None and (out_dir / name).exists()

    rasters = {
        "maximum_depth": _exists("maximum_depth.tif"),
        "maximum_velocity": _exists("maximum_velocity.tif"),
        "arrival_time": _exists("arrival_time.tif"),
        "inundation_mask": _exists("inundation_mask.tif"),
    }
    gis = _project_gis(slug)
    layers = {
        "dam_metadata": slug in _DAM_META,
        "dem": gis["dem"] is not None and gis["dem"].exists(),
        "river": gis["river"] is not None and gis["river"].exists(),
        "buildings": gis["buildings"] is not None and gis["buildings"].exists(),
        "roads": gis["roads"] is not None and gis["roads"].exists(),
        "manifest": _exists("simulation_manifest.json"),
        **{f"raster_{k}": v for k, v in rasters.items()},
    }
    # Twin requires the real DEM plus the four hydraulic rasters. GIS overlays
    # (river/buildings/roads) are enhancements, not a hard requirement.
    twin_ready = layers["dem"] and all(rasters.values())
    meta = _DAM_META.get(slug, {})
    return {
        "sim_ref": slug,
        "twin_ready": bool(twin_ready),
        "layers": layers,
        "dam": {"lat": meta.get("lat"), "lon": meta.get("lon")},
        "note": (
            "twin_ready is True only when the real DEM and all four hydraulic "
            "rasters (depth, velocity, arrival, mask) exist on disk. No simulation "
            "is synthesised for dams that have only metadata."
        ),
    }


@router.get("/{sim_ref}/terrain")
def get_terrain(sim_ref: str, res: int = Query(default=160, ge=32, le=400),
                db: Session = Depends(get_db)):
    """
    Resampled, co-registered grid for the 3D twin, built ENTIRELY from the
    authoritative rasters that share one grid/CRS/bounds:
      - elevation  <- real DEM (data/<slug>/dem/processed/*_dem_30m.tif)
      - depth      <- maximum_depth.tif      (0 where dry / nodata)
      - arrival    <- arrival_time.tif        (min; -1 where never reached)
      - mask       <- inundation_mask.tif     (1 wet / 0 dry)

    The DEM DRIVES the terrain (no mathematical valley), and depth+arrival give a
    per-cell water surface: WSE(x,y) = elevation(x,y) + depth(x,y), revealed as
    arrival(x,y) <= t. Nothing here is synthesised. Decimated to `res` (longest
    axis) so the browser can build a heightmap without millions of vertices.
    """
    import rasterio
    ctx = _resolve_sim(sim_ref, db)
    out = ctx["out_dir"]
    depth_p = out / "maximum_depth.tif"
    arr_p = out / "arrival_time.tif"
    mask_p = out / "inundation_mask.tif"
    dem_p = _project_gis(ctx["slug"]) ["dem"]
    if not depth_p.exists():
        raise HTTPException(status_code=404, detail="Depth raster missing")
    if not dem_p or not Path(dem_p).exists():
        raise HTTPException(status_code=404, detail="DEM raster missing for project")

    with rasterio.open(depth_p) as d_ds:
        depth_full = d_ds.read(1).astype(float)
        bounds = d_ds.bounds
        H, W = depth_full.shape
        transform = d_ds.transform
        px_area = abs(transform.a * transform.e)

    # Longest axis -> res; preserve aspect ratio.
    if W >= H:
        cols = res
        rows = max(2, int(round(res * H / W)))
    else:
        rows = res
        cols = max(2, int(round(res * W / H)))
    row_idx = np.linspace(0, H - 1, rows).astype(int)
    col_idx = np.linspace(0, W - 1, cols).astype(int)
    # Block edges for AREA-AWARE aggregation of the SPARSE flood layers. The
    # flood occupies a thin river channel (well under 1% of cells); plain strided
    # sampling (fine for the smooth DEM) lands between the channel cells and drops
    # almost all of it, leaving the 3D scene visually dry. So depth/mask/arrival
    # are aggregated over each output cell's FULL source block: depth -> max,
    # mask -> any-wet, arrival -> earliest. This preserves the authoritative flood
    # extent through downsampling without inventing or moving any water.
    row_edges = np.linspace(0, H, rows + 1).astype(int)
    col_edges = np.linspace(0, W, cols + 1).astype(int)

    def _block(a, op):
        r = op.reduceat(a, row_edges[:-1], axis=0)
        r = op.reduceat(r, col_edges[:-1], axis=1)
        return r

    def _decimate(path, nodata_lt=-9990.0):
        with rasterio.open(path) as ds:
            a = ds.read(1).astype(float)
        g = a[np.ix_(row_idx, col_idx)]
        g = np.where((g <= nodata_lt) | ~np.isfinite(g), np.nan, g)
        return g

    # DEM: strided nearest sample keeps the true elevation range (a smooth,
    # continuous surface downsamples faithfully this way).
    dem_g = _decimate(dem_p)

    # Depth: clean nodata, then block-MAX so any wet sub-cell survives the resample.
    depth_clean = np.where(np.isfinite(depth_full) & (depth_full > -9990.0), depth_full, 0.0)
    depth_clean = np.clip(depth_clean, 0.0, None)
    depth_g = _block(depth_clean, np.maximum)

    # Arrival: block-MIN (earliest arrival in the block) over reached cells only;
    # the "never reached"/nodata sentinel becomes +inf so it never wins the min.
    with rasterio.open(arr_p) as a_ds0:
        arr_full = a_ds0.read(1).astype(float)
    arr_reach = np.where(np.isfinite(arr_full) & (arr_full >= 0) & (arr_full < 9999.0), arr_full, np.inf)
    arr_g = _block(arr_reach, np.minimum)

    if mask_p.exists():
        with rasterio.open(mask_p) as m_ds:
            mask_full = m_ds.read(1).astype(float)
        mask_g = (_block((mask_full >= 0.5).astype(float), np.maximum) >= 0.5).astype(int)
    else:
        mask_g = (depth_g >= INUNDATION_THRESHOLD_M).astype(int)

    # Keep the three flood layers mutually consistent: water only where wet.
    depth_g = np.where(mask_g >= 1, depth_g, 0.0)
    arr_g = np.where((mask_g >= 1) & np.isfinite(arr_g), arr_g, -1.0)

    valid_dem = dem_g[np.isfinite(dem_g)]
    dem_min = float(np.nanmin(valid_dem)) if valid_dem.size else 0.0
    dem_max = float(np.nanmax(valid_dem)) if valid_dem.size else 0.0
    # Fill DEM voids with the min so the mesh has no NaN vertices.
    dem_filled = np.where(np.isfinite(dem_g), dem_g, dem_min)

    man = ctx["manifest"]
    mass = man.get("mass_conservation", {})
    hs = man.get("hydraulic_summary", {})

    def _flat(a):
        return [round(float(x), 3) for x in a.ravel(order="C").tolist()]

    return {
        "sim_ref": sim_ref,
        "project": ctx["slug"],
        "grid": {"cols": cols, "rows": rows},
        "bounds": {"west": bounds.left, "south": bounds.bottom,
                   "east": bounds.right, "north": bounds.top},
        "crs": "EPSG:4326",
        "elevation_m": {"min": round(dem_min, 2), "max": round(dem_max, 2),
                        "values": _flat(dem_filled)},
        "depth_m": {"max": round(float(np.nanmax(depth_g)), 3), "values": _flat(depth_g)},
        "arrival_min": {"values": _flat(arr_g)},
        "inundation_mask": {"wet_cells": int(np.sum(mask_g)),
                            "values": mask_g.ravel(order="C").astype(int).tolist()},
        "dam": {"lat": ctx["dam_lat"], "lon": ctx["dam_lon"]},
        "inundation_threshold_m": INUNDATION_THRESHOLD_M,
        "peak_discharge_m3s": mass.get("peak_discharge_m3s"),
        "peak_depth_m": hs.get("peak_depth_m"),
        "released_volume_mcm": mass.get("released_volume_mcm"),
        "source": "authoritative DEM + maximum_depth.tif + arrival_time.tif + inundation_mask.tif",
        "solver": man.get("solver", "2D Manning kinematic/diffusion-wave approximation"),
        "scenario_type": "Hypothetical dam-break / visualization derived from maximum-depth + arrival-time outputs",
    }


@router.get("/{sim_ref}/timeline")
def get_timeline(sim_ref: str, frames: int = Query(default=40, ge=5, le=200),
                 db: Session = Depends(get_db)):
    """
    Timeline frames derived from the AUTHORITATIVE arrival_time raster: at each
    frame time the inundated area is exactly the cells whose simulated arrival
    time <= t. Drives the 3D water animation from real output (Part 16).
    """
    import rasterio
    ctx = _resolve_sim(sim_ref, db)
    arr_p = ctx["out_dir"] / "arrival_time.tif"
    depth_p = ctx["out_dir"] / "maximum_depth.tif"
    if not arr_p.exists() or not depth_p.exists():
        raise HTTPException(status_code=404, detail="Arrival/depth rasters missing")

    with rasterio.open(arr_p) as a_ds, rasterio.open(depth_p) as d_ds:
        arr = a_ds.read(1).astype(float)
        depth = d_ds.read(1).astype(float)
        # Cell area in REAL square kilometres. The rasters are EPSG:4326, so
        # transform.a/e are in DEGREES; multiplying them directly gives deg^2
        # (~1e-13 km^2/cell) and collapsed every reported area to ~0.00 km^2.
        # Convert degrees->metres with the standard 111320 m/deg, correcting
        # longitude by cos(latitude) at the raster centre.
        import math
        lat_c = (a_ds.bounds.top + a_ds.bounds.bottom) / 2.0
        m_per_deg_lat = 111320.0
        m_per_deg_lon = 111320.0 * math.cos(math.radians(lat_c))
        cell_w_m = abs(a_ds.transform.a) * m_per_deg_lon
        cell_h_m = abs(a_ds.transform.e) * m_per_deg_lat
        cell_km2 = (cell_w_m * cell_h_m) / 1e6

    wet = depth >= INUNDATION_THRESHOLD_M
    valid_arr = arr[wet & (arr >= 0)]
    if valid_arr.size == 0:
        raise HTTPException(status_code=404, detail="No inundated cells with arrival time")
    t_max = float(np.nanmax(valid_arr))
    total_wet_cells = int(np.sum(wet))

    man = ctx["manifest"]
    mass = man.get("mass_conservation", {})
    times = np.linspace(0.0, t_max, frames)
    out_frames = []
    for t in times:
        reached = wet & (arr >= 0) & (arr <= t)
        n_reached = int(np.sum(reached))
        max_d = float(np.nanmax(depth[reached])) if n_reached > 0 else 0.0
        out_frames.append({
            "time_min": round(float(t), 2),
            "inundated_area_sqkm": round(n_reached * cell_km2, 4),
            "wet_cell_fraction": round(n_reached / total_wet_cells, 4) if total_wet_cells else 0.0,
            "max_depth_reached_m": round(max_d, 3),
        })

    return {
        "sim_ref": sim_ref,
        "project": ctx["slug"],
        "frames": out_frames,
        "t_max_min": round(t_max, 2),
        "peak_discharge_m3s": mass.get("peak_discharge_m3s"),
        "time_to_peak_min": mass.get("time_to_peak_min"),
        "source": "authoritative arrival_time.tif + maximum_depth.tif",
        "solver": man.get("solver", "2D Manning kinematic/diffusion-wave approximation"),
    }


# Documented default building-height estimate (no measured height in OSM data).
DEFAULT_STOREY_HEIGHT_M = 3.0
DEFAULT_BUILDING_HEIGHT_M = 6.0


def _estimate_building_height(props: Dict[str, Any]) -> Tuple[float, bool]:
    """Return (height_m, is_measured). OSM height/levels used if present."""
    for key in ("height", "building:height"):
        v = props.get(key)
        if v is not None:
            try:
                return float(str(v).split()[0]), True
            except Exception:
                pass
    for key in ("building:levels", "levels"):
        v = props.get(key)
        if v is not None:
            try:
                return float(str(v).split()[0]) * DEFAULT_STOREY_HEIGHT_M, False
            except Exception:
                pass
    return DEFAULT_BUILDING_HEIGHT_M, False


@router.get("/{sim_ref}/buildings")
def get_buildings(sim_ref: str, limit: int = Query(default=6000, ge=1, le=50000),
                  db: Session = Depends(get_db)):
    """Real OSM building footprints with AUTHORITATIVE simulated depth per building
    and impact classification. Buildings come only from GIS; nothing is fabricated."""
    import rasterio
    ctx = _resolve_sim(sim_ref, db)
    gis = _project_gis(ctx["slug"])
    if not gis["buildings"]:
        raise HTTPException(status_code=404, detail="No building GIS data for project")

    import geopandas as gpd
    gdf = gpd.read_file(gis["buildings"])
    depth_p = ctx["out_dir"] / "maximum_depth.tif"
    vel_p = ctx["out_dir"] / "maximum_velocity.tif"
    arr_p = ctx["out_dir"] / "arrival_time.tif"
    predictor = _get_predictor(ctx)
    _, river_geom = _load_geom(gis["river"])
    _, roads_geom = _load_geom(gis["roads"])

    d_ds = rasterio.open(depth_p) if depth_p.exists() else None
    with rasterio.open(depth_p) as _tmp:
        b = _tmp.bounds

    feats_out = []
    counts = {"NORMAL": 0, "WATCH": 0, "AFFECTED": 0, "FLOODED": 0}
    risk_counts = {"LOW": 0, "MODERATE": 0, "HIGH": 0, "SEVERE": 0}
    processed = 0
    try:
        for _, row in gdf.iterrows():
            if processed >= limit:
                break
            geom = row.geometry
            if geom is None or geom.is_empty:
                continue
            c = geom.centroid
            lon, lat = float(c.x), float(c.y)
            if not (b.left <= lon <= b.right and b.bottom <= lat <= b.top):
                continue
            processed += 1
            fv = sample_features_at_points(
                [(lat, lon)], ctx["out_dir"], dem_path=gis["dem"],
                river_geom=river_geom, roads_geom=roads_geom,
                dam_lat=ctx["dam_lat"], dam_lon=ctx["dam_lon"], reach_km=ctx["reach_km"],
            )[0]
            try:
                area_m2 = float(gpd.GeoSeries([geom], crs=4326).to_crs(3857).area.iloc[0])
                if not np.isfinite(area_m2):
                    area_m2 = 0.0
            except Exception:
                area_m2 = 0.0
            fv["building_area_m2"] = area_m2
            imp = predictor.predict_impact(fv)
            height, measured = _estimate_building_height(dict(row.drop("geometry")))
            state = imp["building_state"]
            counts[state] = counts.get(state, 0) + 1
            risk_counts[imp["risk_class"]] = risk_counts.get(imp["risk_class"], 0) + 1
            feats_out.append({
                "type": "Feature",
                "geometry": _json_safe(geom.__geo_interface__),
                "properties": _json_safe({
                    "osm_id": _prop(row, "osm_id"),
                    "name": _prop(row, "name"),
                    "depth_m": imp["depth_m"],
                    "velocity_ms": imp["velocity_ms"],
                    "building_state": state,
                    "risk_class": imp["risk_class"],
                    "impact_probability": imp["impact_probability"],
                    "impact_probability_calibrated": imp["impact_probability_calibrated"],
                    "height_m": round(height, 1),
                    "height_is_measured": measured,
                    "area_m2": round(area_m2, 1),
                }),
            })
    finally:
        if d_ds is not None:
            d_ds.close()

    affected = counts["WATCH"] + counts["AFFECTED"] + counts["FLOODED"]
    return {
        "type": "FeatureCollection",
        "metadata": {
            "project": ctx["slug"],
            "buildings_in_domain": processed,
            "affected_buildings": affected,
            "state_counts": counts,
            "risk_counts": risk_counts,
            "default_building_height_m": DEFAULT_BUILDING_HEIGHT_M,
            "height_note": "Heights estimated (OSM levels x 3 m, or 6 m default) unless height_is_measured=true",
            "state_thresholds_m": {"NORMAL": "<0.15", "WATCH": "0.15-0.5", "AFFECTED": "0.5-1.5", "FLOODED": ">1.5"},
            "impact_model_status": MODEL_STATUS["status"],
        },
        "features": feats_out,
    }


# Road is impassable/affected once simulated depth exceeds this (documented, configurable).
ROAD_IMPACT_DEPTH_M = 0.15


@router.get("/{sim_ref}/roads")
def get_roads(sim_ref: str, db: Session = Depends(get_db)):
    """Real OSM roads with affected flag driven by AUTHORITATIVE simulated depth."""
    import rasterio
    from backend.app.ml.flood_impact_predictor import _sample_raster
    ctx = _resolve_sim(sim_ref, db)
    gis = _project_gis(ctx["slug"])
    if not gis["roads"]:
        raise HTTPException(status_code=404, detail="No road GIS data for project")

    import geopandas as gpd
    gdf = gpd.read_file(gis["roads"])
    depth_p = ctx["out_dir"] / "maximum_depth.tif"
    if not depth_p.exists():
        raise HTTPException(status_code=404, detail="Depth raster missing")

    # Length via metric CRS.
    try:
        gdf_m = gdf.to_crs(3857)
    except Exception:
        gdf_m = gdf

    feats_out = []
    affected_km = 0.0
    affected_segments = 0
    total_km = 0.0
    with rasterio.open(depth_p) as d_ds:
        b = d_ds.bounds
        for i, (_, row) in enumerate(gdf.iterrows()):
            geom = row.geometry
            if geom is None or geom.is_empty:
                continue
            seg_len_km = float(gdf_m.geometry.iloc[i].length) / 1000.0
            total_km += seg_len_km
            coords = []
            try:
                if geom.geom_type == "LineString":
                    coords = list(geom.coords)
                elif geom.geom_type == "MultiLineString":
                    for part in geom.geoms:
                        coords.extend(list(part.coords))
            except Exception:
                coords = []
            max_d = 0.0
            for (lo, la) in coords:
                if b.left <= lo <= b.right and b.bottom <= la <= b.top:
                    max_d = max(max_d, _sample_raster(d_ds, lo, la))
            is_affected = max_d >= ROAD_IMPACT_DEPTH_M
            if is_affected:
                affected_km += seg_len_km
                affected_segments += 1
            feats_out.append({
                "type": "Feature",
                "geometry": _json_safe(geom.__geo_interface__),
                "properties": _json_safe({
                    "osm_id": _prop(row, "osm_id"),
                    "highway": _prop(row, "highway"),
                    "name": _prop(row, "name"),
                    "max_depth_m": round(max_d, 3),
                    "is_affected": bool(is_affected),
                    "length_km": round(seg_len_km, 4),
                }),
            })

    return {
        "type": "FeatureCollection",
        "metadata": {
            "project": ctx["slug"],
            "total_segments": len(feats_out),
            "affected_segments": affected_segments,
            "affected_length_km": round(affected_km, 3),
            "total_length_km": round(total_km, 3),
            "road_impact_depth_threshold_m": ROAD_IMPACT_DEPTH_M,
        },
        "features": feats_out,
    }


@router.get("/{sim_ref}/river")
def get_river(sim_ref: str, db: Session = Depends(get_db)):
    """Real river centreline geometry (OSM waterway) for the SELECTED study case,
    clipped to the simulation domain bounds. Nothing is synthesised: the polyline
    comes straight from the project's authoritative river GeoJSON."""
    import rasterio
    ctx = _resolve_sim(sim_ref, db)
    gis = _project_gis(ctx["slug"])
    if not gis["river"]:
        raise HTTPException(status_code=404, detail="No river GIS data for project")

    import geopandas as gpd
    gdf = gpd.read_file(gis["river"])

    # Domain bounds from the authoritative DEM (fallback to depth raster).
    bounds = None
    for cand in ("maximum_depth.tif",):
        p = ctx["out_dir"] / cand
        if p.exists():
            with rasterio.open(p) as ds:
                bb = ds.bounds
                bounds = {"west": bb.left, "south": bb.bottom, "east": bb.right, "north": bb.top}
            break
    if bounds is None and gis["dem"] and Path(gis["dem"]).exists():
        with rasterio.open(gis["dem"]) as ds:
            bb = ds.bounds
            bounds = {"west": bb.left, "south": bb.bottom, "east": bb.right, "north": bb.top}

    feats_out = []
    total_km = 0.0
    try:
        gdf_m = gdf.to_crs(3857)
    except Exception:
        gdf_m = gdf
    # Clip to the simulation domain so the 3D overlay stays aligned with the DEM
    # terrain (the OSM river polyline may extend well beyond the study raster).
    clip_box = None
    if bounds is not None:
        from shapely.geometry import box as _box
        clip_box = _box(bounds["west"], bounds["south"], bounds["east"], bounds["north"])
    for i, (_, row) in enumerate(gdf.iterrows()):
        geom = row.geometry
        if geom is None or geom.is_empty:
            continue
        if clip_box is not None:
            try:
                geom = geom.intersection(clip_box)
            except Exception:
                pass
            if geom.is_empty:
                continue
        try:
            seg_len_km = float(gpd.GeoSeries([geom], crs=4326).to_crs(3857).geometry.iloc[0].length) / 1000.0
        except Exception:
            seg_len_km = 0.0
        total_km += seg_len_km
        feats_out.append({
            "type": "Feature",
            "geometry": _json_safe(geom.__geo_interface__),
            "properties": _json_safe({
                "osm_id": _prop(row, "osm_id"),
                "name": _prop(row, "name:en") or _prop(row, "name"),
                "waterway": _prop(row, "waterway"),
                "width_m": _prop(row, "width"),
                "length_km": round(seg_len_km, 4),
            }),
        })

    return {
        "type": "FeatureCollection",
        "metadata": {
            "project": ctx["slug"],
            "segments": len(feats_out),
            "total_length_km": round(total_km, 3),
            "bounds": bounds,
            "source": f"authoritative river GeoJSON ({Path(gis['river']).name})",
        },
        "features": feats_out,
    }


@router.get("/{sim_ref}/impact")
def get_impact(sim_ref: str, db: Session = Depends(get_db)):
    """Dashboard payload: authoritative hydraulic headline metrics + AI hazard-zone
    area breakdown (DEFRA hazard rating per wet cell). Model status is honest."""
    import rasterio
    ctx = _resolve_sim(sim_ref, db)
    depth_p = ctx["out_dir"] / "maximum_depth.tif"
    vel_p = ctx["out_dir"] / "maximum_velocity.tif"
    if not depth_p.exists() or not vel_p.exists():
        raise HTTPException(status_code=404, detail="Depth/velocity rasters missing")

    with rasterio.open(depth_p) as d_ds, rasterio.open(vel_p) as v_ds:
        depth = d_ds.read(1).astype(float)
        vel = v_ds.read(1).astype(float)
        px_area = abs(d_ds.transform.a * d_ds.transform.e)
    cell_km2 = px_area / 1e6

    wet = depth >= INUNDATION_THRESHOLD_M
    zone_area = {"LOW": 0.0, "MODERATE": 0.0, "HIGH": 0.0, "SEVERE": 0.0}
    wet_idx = np.argwhere(wet)
    for (r, c) in wet_idx:
        hr = flood_hazard_rating(depth[r, c], vel[r, c])
        zone_area[hazard_class_from_rating(hr)] += cell_km2

    man = ctx["manifest"]
    hs = man.get("hydraulic_summary", {})
    mass = man.get("mass_conservation", {})
    predictor = _get_predictor(ctx)

    return {
        "sim_ref": sim_ref,
        "project": ctx["slug"],
        "hydraulic": {
            "peak_discharge_m3s": mass.get("peak_discharge_m3s"),
            "max_depth_m": hs.get("peak_depth_m", round(float(np.nanmax(depth)), 2)),
            "max_velocity_ms": hs.get("peak_velocity_ms", round(float(np.nanmax(vel)), 2)),
            "inundated_area_sqkm": hs.get("inundated_area_sqkm", round(float(np.sum(wet)) * cell_km2, 3)),
            "time_to_peak_min": mass.get("time_to_peak_min"),
            "source": "authoritative",
        },
        "ai_impact_zones_sqkm": {k: round(v, 4) for k, v in zone_area.items()},
        "ai_model": predictor.metadata(),
        "solver": man.get("solver", "2D Manning kinematic/diffusion-wave approximation"),
        "scenario_type": "Hypothetical dam-break / AI-Assisted Flood Impact Prediction",
    }


@router.get("/{sim_ref}/flow-vectors")
def get_flow_vectors(sim_ref: str, step: int = Query(default=6, ge=1, le=40),
                     db: Session = Depends(get_db)):
    """Flow vectors from AUTHORITATIVE velocity magnitude + arrival-time gradient
    (water flows from earlier to later arrival). No arbitrary arrows."""
    import rasterio
    ctx = _resolve_sim(sim_ref, db)
    depth_p = ctx["out_dir"] / "maximum_depth.tif"
    vel_p = ctx["out_dir"] / "maximum_velocity.tif"
    arr_p = ctx["out_dir"] / "arrival_time.tif"
    if not (depth_p.exists() and vel_p.exists() and arr_p.exists()):
        raise HTTPException(status_code=404, detail="Required rasters missing")

    with rasterio.open(depth_p) as d_ds, rasterio.open(vel_p) as v_ds, rasterio.open(arr_p) as a_ds:
        depth = d_ds.read(1).astype(float)
        vel = v_ds.read(1).astype(float)
        arr = a_ds.read(1).astype(float)
        transform = d_ds.transform
    arr_masked = np.where(arr >= 0, arr, np.nan)
    gy, gx = np.gradient(arr_masked)  # increasing arrival direction
    H, W = depth.shape
    vectors = []
    for r in range(0, H, step):
        for c in range(0, W, step):
            if depth[r, c] < INUNDATION_THRESHOLD_M:
                continue
            dx, dy = gx[r, c], gy[r, c]
            if not np.isfinite(dx) or not np.isfinite(dy) or (dx == 0 and dy == 0):
                continue
            mag = float(np.hypot(dx, dy))
            ux, uy = dx / mag, dy / mag  # unit flow dir (col, row) toward later arrival
            lon, lat = transform * (c + 0.5, r + 0.5)  # Affine apply (col,row)->(x,y)
            bearing = (np.degrees(np.arctan2(ux, -uy)) + 360.0) % 360.0
            vectors.append({
                "lat": round(float(lat), 6),
                "lon": round(float(lon), 6),
                "u": round(float(ux), 4),
                "v": round(float(-uy), 4),
                "speed_ms": round(float(vel[r, c]), 3),
                "bearing_deg": round(float(bearing), 1),
            })
    return {
        "sim_ref": sim_ref,
        "project": ctx["slug"],
        "count": len(vectors),
        "vectors": vectors,
        "source": "authoritative maximum_velocity.tif + arrival_time.tif gradient",
    }
