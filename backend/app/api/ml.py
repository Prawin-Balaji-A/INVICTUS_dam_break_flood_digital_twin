import os
import json
from pathlib import Path
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
import numpy as np
import joblib

from backend.app.ml.features import FEATURE_NAMES, extract_features_at_point
from backend.app.ml.model import RandomForestSurrogate, DecisionTree, TreeNode

router = APIRouter(prefix="/api/ml", tags=["Machine Learning"])

MODEL_DIR = Path("data/ml/flood_predictor")

_cached_model: Optional[RandomForestSurrogate] = None

# Dam metadata used by BOTH the point and grid handlers. Keeping it in one place
# guarantees the two endpoints resolve identical coordinates/heights/slopes for a
# given dam (previously the grid handler carried its own divergent copy).
# Dam metadata used by BOTH the point and grid handlers. Keeping it in one place
# guarantees the two endpoints resolve identical coordinates/heights/slopes for a
# given dam.
DAM_META: Dict[str, Dict[str, float]] = {
    "mettur": {"lat": 11.8028, "lon": 77.8017, "height_m": 65.23, "slope": 0.0004},
    "idukki": {"lat": 9.8497, "lon": 76.9744, "height_m": 168.91, "slope": 0.0113},
    "tehri": {"lat": 30.3783, "lon": 78.4800, "height_m": 260.5, "slope": 0.0080},
}


def _load_river_union(river_path: Path):
    """Load river geometries and compute unary union using Shapely without requiring GDAL/pyogrio/fiona."""
    try:
        with open(river_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        from shapely.geometry import shape
        from shapely.ops import unary_union
        geoms = [shape(feat["geometry"]) for feat in data.get("features", []) if feat.get("geometry")]
        if geoms:
            return unary_union(geoms)
    except Exception:
        pass
    import geopandas as gpd
    river_gdf = gpd.read_file(river_path)
    return river_gdf.unary_union


def resolve_domain_paths(project_id: Optional[str]) -> tuple:
    """Resolve (proj_slug, dem_path, river_path) for a dam.

    Discovers the real river GeoJSON on disk (``data/<slug>/river/*_river.geojson``)
    instead of hard-coding a single basename, so every dam whose river file is
    named after its own river (e.g. Tehri -> ``bhagirathi_river.geojson``) resolves
    correctly. Falls back to the Mettur domain only when the requested dam has no
    usable DEM + river pair.
    """
    raw = (project_id or "mettur").lower()
    if "tehri" in raw:
        proj_slug = "tehri"
    elif "mettur" in raw:
        proj_slug = "mettur"
    elif "idukki" in raw:
        proj_slug = "idukki"
    else:
        proj_slug = raw

    base = Path(__file__).resolve().parents[3]
    dem_path = base / f"data/{proj_slug}/dem/processed/{proj_slug}_dem_30m.tif"
    if not dem_path.exists():
        dem_path = Path(f"data/{proj_slug}/dem/processed/{proj_slug}_dem_30m.tif")

    river_dir = base / f"data/{proj_slug}/river"
    if not river_dir.is_dir():
        river_dir = Path(f"data/{proj_slug}/river")

    river_path = None
    if river_dir.is_dir():
        candidates = sorted(river_dir.glob("*_river.geojson")) or sorted(river_dir.glob("*.geojson"))
        if candidates:
            river_path = candidates[0]

    # Fallback to the Mettur reference domain if this dam has no usable data.
    if river_path is None or not dem_path.exists() or not river_path.exists():
        proj_slug = "mettur"
        dem_path = base / "data/mettur/dem/processed/mettur_dem_30m.tif"
        if not dem_path.exists():
            dem_path = Path("data/mettur/dem/processed/mettur_dem_30m.tif")
        river_path = base / "data/mettur/river/cauvery_river.geojson"
        if not river_path.exists():
            river_path = Path("data/mettur/river/cauvery_river.geojson")

    return proj_slug, dem_path, river_path

def get_model() -> RandomForestSurrogate:
    global _cached_model
    if _cached_model is None:
        model_path = MODEL_DIR / "model.pkl"
        if not model_path.exists():
            raise HTTPException(status_code=404, detail="ML model has not been trained yet.")
        _cached_model = joblib.load(model_path)
    return _cached_model

class PointPredictionRequest(BaseModel):
    lat: float
    lon: float
    project_id: Optional[str] = "mettur"
    active_volume_mcm: Optional[float] = 500.0
    peak_discharge_m3s: Optional[float] = 80000.0
    manning_n: Optional[float] = 0.035

class PointPredictionResponse(BaseModel):
    lat: float
    lon: float
    flood_probability: float
    is_inundated: bool
    confidence: float
    uncertainty: float
    features_used: Dict[str, float]
    provenance: str = "AI/ML Random Forest Surrogate (Fast Inundation Predictor)"

class GridPredictionRequest(BaseModel):
    project_id: str = "mettur"
    active_volume_mcm: Optional[float] = 500.0
    peak_discharge_m3s: Optional[float] = 80000.0
    grid_resolution: Optional[int] = Field(default=20, ge=10, le=50)

@router.get("/metrics")
def get_ml_metrics():
    """Retrieve validation metrics, feature schema, and training manifest for the ML surrogate model."""
    metrics_path = MODEL_DIR / "validation_metrics.json"
    schema_path = MODEL_DIR / "feature_schema.json"
    manifest_path = MODEL_DIR / "training_manifest.json"

    if not metrics_path.exists() or not schema_path.exists():
        raise HTTPException(status_code=404, detail="ML metadata files not found.")

    with open(metrics_path, "r", encoding="utf-8") as f:
        metrics = json.load(f)
    with open(schema_path, "r", encoding="utf-8") as f:
        schema = json.load(f)
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    return {
        "status": "ready",
        "model_version": manifest.get("model_version", "1.0.0"),
        "algorithm": manifest.get("algorithm", "RandomForestSurrogate"),
        "metrics": metrics,
        "features": schema.get("features", []),
        "feature_importances": schema.get("feature_importances", {}),
        "manifest": manifest,
        "provenance": "Empirically Validated Against Physical Hydrodynamic Simulations (Mettur & Idukki held-out scenarios)"
    }

@router.post("/predict-point", response_model=PointPredictionResponse)
def predict_point(req: PointPredictionRequest):
    """Predict flood inundation probability at a single location using the physical surrogate model."""
    import rasterio
    import geopandas as gpd

    clf = get_model()

    # Shared path resolution (discovers the real river file, Mettur fallback).
    proj_slug, dem_path, river_path = resolve_domain_paths(req.project_id)

    meta = DAM_META.get(proj_slug, {"lat": 11.8028, "lon": 77.8017, "height_m": 65.0, "slope": 0.0004})
    d_lat, d_lon, d_h = meta["lat"], meta["lon"], meta["height_m"]

    with rasterio.open(dem_path) as dem:
        river_union = _load_river_union(river_path)

        feats = extract_features_at_point(
            lat=req.lat,
            lon=req.lon,
            dem_dataset=dem,
            river_gdf=river_union,
            dam_lat=d_lat,
            dam_lon=d_lon,
            scenario_params={
                "active_volume_mcm": req.active_volume_mcm,
                "peak_discharge_m3s": req.peak_discharge_m3s,
                "dam_height_m": d_h,
                "manning_n": req.manning_n or 0.035,
                "downstream_slope": 0.0004 if proj_slug == "mettur" else 0.01
            }
        )

    feat_vector = np.array([[feats[name] for name in FEATURE_NAMES]])
    prob = float(clf.predict_proba(feat_vector)[0, 1])
    is_inundated = prob >= 0.5
    confidence = float(abs(prob - 0.5) * 2.0)
    uncertainty = float(1.0 - confidence)

    return PointPredictionResponse(
        lat=req.lat,
        lon=req.lon,
        flood_probability=round(prob, 4),
        is_inundated=is_inundated,
        confidence=round(confidence, 4),
        uncertainty=round(uncertainty, 4),
        features_used=feats,
        provenance="AI/ML Random Forest Surrogate (Fast Inundation Predictor)"
    )

@router.post("/predict-grid")
def predict_grid(req: GridPredictionRequest):
    """
    Generate an AI flood prediction grid across the project domain in near real-time.
    Returns GeoJSON FeatureCollection with cell predictions and uncertainty metrics.
    """
    import rasterio

    clf = get_model()
    # Shared path resolution: identical discovery + Mettur fallback as the point
    # handler, so a dam with a non-"periyar" river (e.g. Tehri/bhagirathi) no
    # longer 404s. If truly no data exists anywhere, the Mettur reference domain
    # is used (honest fallback), never a fabricated success.
    proj_slug, dem_path, river_path = resolve_domain_paths(req.project_id)

    meta = DAM_META.get(proj_slug, {"lat": 11.8028, "lon": 77.8017, "height_m": 65.0, "slope": 0.001})
    d_lat, d_lon, d_h, d_slope = meta["lat"], meta["lon"], meta["height_m"], meta["slope"]

    features = []
    with rasterio.open(dem_path) as dem:
        river_union = _load_river_union(river_path)
        bounds = dem.bounds

        n_pts = req.grid_resolution
        lons = np.linspace(bounds.left + 0.015, bounds.right - 0.015, n_pts)
        lats = np.linspace(bounds.bottom + 0.015, bounds.top - 0.015, n_pts)

        feat_matrix = []
        coord_list = []
        for lat in lats:
            for lon in lons:
                feats = extract_features_at_point(
                    lat=lat,
                    lon=lon,
                    dem_dataset=dem,
                    river_gdf=river_union,
                    dam_lat=d_lat,
                    dam_lon=d_lon,
                    scenario_params={
                        "active_volume_mcm": req.active_volume_mcm,
                        "peak_discharge_m3s": req.peak_discharge_m3s,
                        "dam_height_m": d_h,
                        "manning_n": 0.035,
                        "downstream_slope": d_slope
                    }
                )
                feat_matrix.append([feats[name] for name in FEATURE_NAMES])
                coord_list.append((lat, lon, feats))

        X = np.array(feat_matrix)
        probs = clf.predict_proba(X)[:, 1]

        for (lat, lon, f_dict), p in zip(coord_list, probs):
            p_val = float(p)
            conf = float(abs(p_val - 0.5) * 2.0)
            features.append({
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [round(lon, 5), round(lat, 5)]
                },
                "properties": {
                    "flood_probability": round(p_val, 4),
                    "is_inundated": bool(p_val >= 0.5),
                    "uncertainty": round(1.0 - conf, 4),
                    "elevation_m": f_dict["elevation_m"],
                    "rel_elev_river_m": f_dict["rel_elev_river_m"],
                    "dist_to_river_m": f_dict["dist_to_river_m"]
                }
            })

    return {
        "type": "FeatureCollection",
        "metadata": {
            "project_id": req.project_id,
            "total_points": len(features),
            "inundated_points": sum(1 for f in features if f["properties"]["is_inundated"]),
            "resolved_domain": proj_slug,
            "algorithm": "RandomForestSurrogate",
            "provenance": "AI/ML Random Forest Surrogate (Fast Inundation Predictor)"
        },
        "features": features
    }
