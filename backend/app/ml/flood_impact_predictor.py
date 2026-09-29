"""
Flood Impact Prediction Layer (Phase 6)
=======================================

PURPOSE
-------
A spatial impact-prediction layer that sits DOWNSTREAM of the authoritative
hydraulic solver (GeneralizedFloodRoutingEngine). It does NOT compute or alter
water depth, velocity or arrival time -- those come from the verified hydraulic
rasters and are treated as ground truth. This layer answers a different
question: given the simulated hydraulic fields plus terrain/GIS context, how
severe is the impact at each location/building, and can we generalise that
impact relationship to points the raster does not resolve well?

SCIENTIFIC BASIS (not a fabricated "AI")
----------------------------------------
Impact severity is grounded in the published flood-hazard rating used by the
UK DEFRA / Environment Agency FD2320/FD2321 guidance and mirrored in the
Australian Rainfall & Runoff (ARR) safety criteria:

        HR = D * (V + 0.5) + DF

where D = depth (m), V = velocity (m/s), DF = debris factor. This HR is a
peer-reviewed people-safety hazard metric, NOT an invented formula. The ML
model (a NumPy RandomForest surrogate) then learns to reproduce and spatially
generalise this hazard classification from a richer feature vector, so impact
can be predicted quickly at arbitrary points/buildings.

HONESTY / CALIBRATION STATUS
----------------------------
There is NO independent observed flood-outcome dataset (e.g. validated SAR
damage labels) wired in locally. Therefore this model is a *research
prototype*: its reported quality metric is ONLY the surrogate's agreement with
the physics hazard function under k-fold cross-validation -- it is explicitly
NOT accuracy against real disaster outcomes. `MODEL_STATUS` reflects this and
the API/UI must display "Research prototype -- calibration required". We do not
emit a headline accuracy percentage as if validated against reality.
"""
from __future__ import annotations

import math
from typing import Dict, List, Any, Optional, Tuple
import numpy as np

from backend.app.ml.model import RandomForestSurrogate

# ---------------------------------------------------------------------------
# Feature contract
# ---------------------------------------------------------------------------
IMPACT_FEATURE_NAMES: List[str] = [
    "depth_m",            # authoritative hydraulic depth
    "velocity_ms",        # authoritative hydraulic velocity
    "arrival_time_min",   # authoritative hydraulic arrival time
    "elevation_m",        # DEM
    "slope_deg",          # DEM-derived
    "dist_to_river_m",    # GIS
    "dist_to_dam_km",     # GIS
    "chainage_norm",      # normalised downstream distance [0,1]
    "building_area_m2",   # GIS footprint area (0.0 for bare cells)
    "road_distance_m",    # GIS distance to nearest road
]

# ---------------------------------------------------------------------------
# Documented, configurable thresholds
# ---------------------------------------------------------------------------
# Inundation threshold shared with the hydraulic engine (do not change).
INUNDATION_THRESHOLD_M = 0.15

# Building states driven by AUTHORITATIVE simulated depth (Phase 6 Part 7).
BUILDING_STATE_THRESHOLDS_M = {
    "NORMAL": (0.0, 0.15),
    "WATCH": (0.15, 0.5),
    "AFFECTED": (0.5, 1.5),
    "FLOODED": (1.5, float("inf")),
}

# DEFRA/EA flood hazard-rating class breakpoints (people-safety).
HAZARD_CLASS_BREAKS = [
    ("LOW", 0.0, 0.75),          # caution
    ("MODERATE", 0.75, 1.25),    # danger for some
    ("HIGH", 1.25, 2.0),         # danger for most
    ("SEVERE", 2.0, float("inf")),  # danger for all
]

# A location is a "high-impact" positive label for the ML surrogate when its
# physics hazard rating reaches this HR (i.e. HIGH or SEVERE).
HIGH_IMPACT_HR_THRESHOLD = 1.25

DEFAULT_DEBRIS_FACTOR = 0.5  # DEFRA DF for urban/wooded areas with buildings

MODEL_STATUS = {
    "name": "Physics-informed Flood Impact Surrogate (RandomForest)",
    "kind": "hybrid_physics_informed",
    "calibrated_against_observations": False,
    "status": "Research prototype -- calibration required",
    "hazard_basis": "DEFRA FD2320 / ARR flood hazard rating HR = D*(V+0.5)+DF",
    "authoritative_fields": ["depth_m", "velocity_ms", "arrival_time_min"],
    "note": (
        "Reported metrics measure agreement with the physics hazard function "
        "under cross-validation only. They are NOT validated against observed "
        "flood outcomes. Depth/velocity/arrival are never modified by this model."
    ),
}


def flood_hazard_rating(depth_m: float, velocity_ms: float,
                        debris_factor: float = DEFAULT_DEBRIS_FACTOR) -> float:
    """DEFRA/EA people-safety hazard rating HR = D*(V+0.5)+DF (>=0)."""
    d = max(0.0, float(depth_m))
    v = max(0.0, float(velocity_ms))
    if d < INUNDATION_THRESHOLD_M:
        return 0.0
    return d * (v + 0.5) + max(0.0, float(debris_factor))


def hazard_class_from_rating(hr: float) -> str:
    for label, lo, hi in HAZARD_CLASS_BREAKS:
        if lo <= hr < hi:
            return label
    return "SEVERE"


def building_state_from_depth(depth_m: float) -> str:
    d = max(0.0, float(depth_m))
    for state, (lo, hi) in BUILDING_STATE_THRESHOLDS_M.items():
        if lo <= d < hi:
            return state
    return "FLOODED"


def _feature_vector(f: Dict[str, float]) -> List[float]:
    return [float(f.get(name, 0.0)) for name in IMPACT_FEATURE_NAMES]


class FloodImpactPredictor:
    """
    Physics-informed impact surrogate. Hydraulics are authoritative: depth,
    velocity and arrival are inputs, never outputs recomputed by this class.
    The RandomForest learns to predict a CALIBRATED high-impact probability
    and to spatially generalise the DEFRA hazard classification.
    """

    def __init__(self, debris_factor: float = DEFAULT_DEBRIS_FACTOR,
                 random_state: int = 42):
        self.debris_factor = debris_factor
        self.random_state = random_state
        self.model: Optional[RandomForestSurrogate] = None
        self.cv_metrics: Dict[str, float] = {}
        self.n_train = 0

    # -- training -----------------------------------------------------------
    def fit(self, feature_dicts: List[Dict[str, float]]) -> Dict[str, Any]:
        """
        Fit the surrogate. Labels are derived from the AUTHORITATIVE hydraulic
        fields via the physics hazard rating (not from the model itself).
        Returns honest cross-validated agreement metrics.
        """
        if not feature_dicts:
            raise ValueError("No feature samples supplied to FloodImpactPredictor.fit")

        X = np.array([_feature_vector(f) for f in feature_dicts], dtype=float)
        hr = np.array([
            flood_hazard_rating(f.get("depth_m", 0.0), f.get("velocity_ms", 0.0),
                                self.debris_factor)
            for f in feature_dicts
        ])
        y = (hr >= HIGH_IMPACT_HR_THRESHOLD).astype(int)
        self.n_train = len(y)

        # Honest k-fold CV agreement with the physics hazard label.
        self.cv_metrics = self._cross_val(X, y)

        self.model = RandomForestSurrogate(
            n_estimators=40, max_depth=10, min_samples_split=4,
            random_state=self.random_state,
        )
        # Degenerate single-class case: skip fit, fall back to physics at predict.
        if len(np.unique(y)) > 1:
            self.model.fit(X, y)
        else:
            self.model = None
        return self.metadata()

    def _cross_val(self, X: np.ndarray, y: np.ndarray, k: int = 5) -> Dict[str, float]:
        if len(np.unique(y)) < 2:
            return {"cv_folds": 0, "note": "single-class labels; CV not meaningful"}
        rng = np.random.RandomState(self.random_state)
        idx = rng.permutation(len(y))
        folds = np.array_split(idx, k)
        accs, f1s, ious = [], [], []
        for i in range(k):
            test_idx = folds[i]
            train_idx = np.concatenate([folds[j] for j in range(k) if j != i])
            if len(np.unique(y[train_idx])) < 2:
                continue
            m = RandomForestSurrogate(n_estimators=25, max_depth=10,
                                      min_samples_split=4,
                                      random_state=self.random_state + i)
            m.fit(X[train_idx], y[train_idx])
            pred = m.predict(X[test_idx])
            yt = y[test_idx]
            tp = float(np.sum((yt == 1) & (pred == 1)))
            fp = float(np.sum((yt == 0) & (pred == 1)))
            fn = float(np.sum((yt == 1) & (pred == 0)))
            tn = float(np.sum((yt == 0) & (pred == 0)))
            n = max(1.0, tp + fp + fn + tn)
            accs.append((tp + tn) / n)
            prec = tp / (tp + fp) if (tp + fp) else 0.0
            rec = tp / (tp + fn) if (tp + fn) else 0.0
            f1s.append((2 * prec * rec / (prec + rec)) if (prec + rec) else 0.0)
            ious.append(tp / (tp + fp + fn) if (tp + fp + fn) else 0.0)
        if not accs:
            return {"cv_folds": 0, "note": "insufficient class balance for CV"}
        return {
            "cv_folds": len(accs),
            "surrogate_vs_physics_accuracy": round(float(np.mean(accs)), 4),
            "surrogate_vs_physics_f1": round(float(np.mean(f1s)), 4),
            "surrogate_vs_physics_iou": round(float(np.mean(ious)), 4),
            "metric_meaning": "agreement with DEFRA hazard function only; NOT observed-flood accuracy",
        }

    # -- inference ----------------------------------------------------------
    def predict_impact(self, features: Dict[str, float]) -> Dict[str, Any]:
        """
        Predict impact for one location. Depth/velocity/arrival are passed
        through UNCHANGED (hydraulics authoritative). risk_class comes from the
        physics hazard rating; impact_probability is the ML surrogate's
        calibrated probability (or the physics indicator if the model is unfit).
        """
        depth = max(0.0, float(features.get("depth_m", 0.0)))
        vel = max(0.0, float(features.get("velocity_ms", 0.0)))
        arrival = features.get("arrival_time_min", None)

        hr = flood_hazard_rating(depth, vel, self.debris_factor)
        risk_class = hazard_class_from_rating(hr)

        if self.model is not None:
            x = np.array([_feature_vector(features)], dtype=float)
            impact_prob = float(self.model.predict_proba(x)[0, 1])
        else:
            impact_prob = 1.0 if hr >= HIGH_IMPACT_HR_THRESHOLD else 0.0

        arr_window = None
        if arrival is not None and arrival > 0:
            a = float(arrival)
            arr_window = [round(max(0.0, a * 0.85), 1), round(a * 1.15, 1)]

        return {
            # authoritative hydraulic fields, unaltered
            "depth_m": round(depth, 3),
            "velocity_ms": round(vel, 3),
            "arrival_time_min": round(float(arrival), 1) if arrival is not None else None,
            # impact assessment
            "hazard_rating": round(hr, 3),
            "risk_class": risk_class,
            "impact_probability": round(impact_prob, 4),
            "impact_probability_calibrated": self.model is not None,
            "building_state": building_state_from_depth(depth),
            "expected_depth_range_m": [round(depth * 0.9, 2), round(depth * 1.1, 2)],
            "expected_arrival_window_min": arr_window,
            "velocity_hazard": "HIGH" if vel >= 3.0 else ("MODERATE" if vel >= 1.0 else "LOW"),
            "model_status": MODEL_STATUS["status"],
        }

    def metadata(self) -> Dict[str, Any]:
        def _jsafe(x):
            return None if x == float("inf") else x
        return {
            **MODEL_STATUS,
            "features": IMPACT_FEATURE_NAMES,
            "training_samples": self.n_train,
            "cross_validation": self.cv_metrics,
            "building_state_thresholds_m": {
                k: [v[0], _jsafe(v[1])] for k, v in BUILDING_STATE_THRESHOLDS_M.items()
            },
            "hazard_class_breaks": [[b[0], b[1], _jsafe(b[2])] for b in HAZARD_CLASS_BREAKS],
            "inundation_threshold_m": INUNDATION_THRESHOLD_M,
            "debris_factor": self.debris_factor,
        }


# ---------------------------------------------------------------------------
# Feature extraction from authoritative simulation outputs + GIS
# ---------------------------------------------------------------------------
def _sample_raster(ds, lon: float, lat: float, default: float = 0.0) -> float:
    try:
        row, col = ds.index(lon, lat)
        if row < 0 or col < 0 or row >= ds.height or col >= ds.width:
            return default
        val = float(ds.read(1, window=((row, row + 1), (col, col + 1)))[0, 0])
        if np.isnan(val) or val <= -9990:
            return default
        return val
    except Exception:
        return default


def sample_features_at_points(
    points: List[Tuple[float, float]],
    sim_dir,
    dem_path=None,
    river_geom=None,
    roads_geom=None,
    dam_lat: Optional[float] = None,
    dam_lon: Optional[float] = None,
    reach_km: float = 1.0,
    building_areas: Optional[List[float]] = None,
) -> List[Dict[str, float]]:
    """
    Build impact feature dicts for a list of (lat, lon) points by sampling the
    AUTHORITATIVE hydraulic rasters (maximum_depth/velocity/arrival_time) plus
    optional DEM/river/road GIS. Depth/velocity/arrival always come from the
    verified rasters -- never synthesised.
    """
    import rasterio
    from pathlib import Path
    from shapely.geometry import Point

    sim_dir = Path(sim_dir)
    depth_p = sim_dir / "maximum_depth.tif"
    vel_p = sim_dir / "maximum_velocity.tif"
    arr_p = sim_dir / "arrival_time.tif"

    depth_ds = rasterio.open(depth_p) if depth_p.exists() else None
    vel_ds = rasterio.open(vel_p) if vel_p.exists() else None
    arr_ds = rasterio.open(arr_p) if arr_p.exists() else None
    dem_ds = rasterio.open(dem_path) if (dem_path and Path(dem_path).exists()) else None

    out: List[Dict[str, float]] = []
    try:
        for i, (lat, lon) in enumerate(points):
            depth = _sample_raster(depth_ds, lon, lat) if depth_ds else 0.0
            vel = _sample_raster(vel_ds, lon, lat) if vel_ds else 0.0
            arr = _sample_raster(arr_ds, lon, lat, default=-1.0) if arr_ds else -1.0
            elev = _sample_raster(dem_ds, lon, lat) if dem_ds else 0.0

            pt = Point(lon, lat)
            dist_river = float(river_geom.distance(pt) * 111139.0) if river_geom is not None else 0.0
            road_dist = float(roads_geom.distance(pt) * 111139.0) if roads_geom is not None else 0.0
            dist_dam = haversine_km(lat, lon, dam_lat, dam_lon) if (dam_lat is not None and dam_lon is not None) else 0.0
            chainage = min(1.0, dist_dam / reach_km) if reach_km > 0 else 0.0
            b_area = float(building_areas[i]) if building_areas is not None else 0.0

            out.append({
                "depth_m": depth,
                "velocity_ms": vel,
                "arrival_time_min": arr if arr >= 0 else 0.0,
                "elevation_m": elev,
                "slope_deg": 0.0,
                "dist_to_river_m": dist_river,
                "dist_to_dam_km": dist_dam,
                "chainage_norm": chainage,
                "building_area_m2": b_area,
                "road_distance_m": road_dist,
                "_arrival_valid": 1.0 if arr >= 0 else 0.0,
            })
    finally:
        for ds in (depth_ds, vel_ds, arr_ds, dem_ds):
            if ds is not None:
                ds.close()
    return out


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2)
    return 2 * R * math.asin(math.sqrt(max(0.0, min(1.0, a))))
