import numpy as np
import pytest

from backend.app.ml.flood_impact_predictor import (
    FloodImpactPredictor,
    IMPACT_FEATURE_NAMES,
    flood_hazard_rating,
    hazard_class_from_rating,
    building_state_from_depth,
    BUILDING_STATE_THRESHOLDS_M,
    INUNDATION_THRESHOLD_M,
    HIGH_IMPACT_HR_THRESHOLD,
    MODEL_STATUS,
)


def _synthetic_samples(n=400, seed=0):
    """Physically plausible feature dicts spanning safe->severe hazard."""
    rng = np.random.RandomState(seed)
    samples = []
    for _ in range(n):
        depth = float(rng.uniform(0.0, 6.0))
        vel = float(rng.uniform(0.0, 5.0))
        samples.append({
            "depth_m": depth,
            "velocity_ms": vel,
            "arrival_time_min": float(rng.uniform(0, 180)),
            "elevation_m": float(rng.uniform(150, 260)),
            "slope_deg": float(rng.uniform(0, 10)),
            "dist_to_river_m": float(rng.uniform(0, 2000)),
            "dist_to_dam_km": float(rng.uniform(0, 7)),
            "chainage_norm": float(rng.uniform(0, 1)),
            "building_area_m2": float(rng.uniform(0, 300)),
            "road_distance_m": float(rng.uniform(0, 500)),
        })
    return samples


def test_impact_feature_vector_contains_expected_features():
    expected = [
        "depth_m", "velocity_ms", "arrival_time_min", "elevation_m", "slope_deg",
        "dist_to_river_m", "dist_to_dam_km", "chainage_norm",
        "building_area_m2", "road_distance_m",
    ]
    assert IMPACT_FEATURE_NAMES == expected


def test_hazard_rating_matches_defra_formula():
    # HR = D*(V+0.5)+DF ; below inundation threshold -> 0
    assert flood_hazard_rating(0.05, 3.0, 0.5) == 0.0
    hr = flood_hazard_rating(2.0, 1.5, 0.5)
    assert abs(hr - (2.0 * (1.5 + 0.5) + 0.5)) < 1e-9
    assert hazard_class_from_rating(0.3) == "LOW"
    assert hazard_class_from_rating(1.0) == "MODERATE"
    assert hazard_class_from_rating(1.5) == "HIGH"
    assert hazard_class_from_rating(3.0) == "SEVERE"


def test_building_states_follow_documented_thresholds():
    assert building_state_from_depth(0.05) == "NORMAL"
    assert building_state_from_depth(0.3) == "WATCH"
    assert building_state_from_depth(1.0) == "AFFECTED"
    assert building_state_from_depth(2.5) == "FLOODED"
    assert BUILDING_STATE_THRESHOLDS_M["WATCH"] == (0.15, 0.5)
    assert INUNDATION_THRESHOLD_M == 0.15


def test_predictor_status_is_honest_no_fabricated_accuracy():
    p = FloodImpactPredictor()
    meta = p.fit(_synthetic_samples())
    # Never claims calibration against real observations
    assert meta["calibrated_against_observations"] is False
    assert "Research prototype" in meta["status"]
    # CV metric is explicitly labelled as physics-agreement, not real accuracy
    cv = meta["cross_validation"]
    assert "surrogate_vs_physics_accuracy" in cv
    assert "NOT observed-flood accuracy" in cv["metric_meaning"]
    # No top-level fabricated "accuracy" masquerading as validated
    assert "accuracy" not in meta


def test_ml_cannot_override_hydraulic_depth_or_velocity():
    p = FloodImpactPredictor()
    p.fit(_synthetic_samples())
    feat = {
        "depth_m": 2.41, "velocity_ms": 4.82, "arrival_time_min": 21.0,
        "elevation_m": 195.0, "slope_deg": 1.2, "dist_to_river_m": 120.0,
        "dist_to_dam_km": 3.1, "chainage_norm": 0.45,
        "building_area_m2": 88.0, "road_distance_m": 40.0,
    }
    out = p.predict_impact(feat)
    # Authoritative fields pass through unchanged (ML may not alter them)
    assert out["depth_m"] == pytest.approx(2.41, abs=1e-6)
    assert out["velocity_ms"] == pytest.approx(4.82, abs=1e-6)
    assert 0.0 <= out["impact_probability"] <= 1.0
    assert out["risk_class"] in {"LOW", "MODERATE", "HIGH", "SEVERE"}
    assert out["building_state"] == "FLOODED"


def test_high_impact_label_threshold_consistent():
    # A deep, fast flow must classify as HIGH or SEVERE (>= high HR threshold)
    hr = flood_hazard_rating(3.0, 3.0, 0.5)
    assert hr >= HIGH_IMPACT_HR_THRESHOLD
    assert hazard_class_from_rating(hr) in {"HIGH", "SEVERE"}


def test_predict_impact_dry_cell_is_normal_low():
    p = FloodImpactPredictor()
    p.fit(_synthetic_samples())
    out = p.predict_impact({"depth_m": 0.0, "velocity_ms": 0.0, "arrival_time_min": 0.0})
    assert out["building_state"] == "NORMAL"
    assert out["risk_class"] == "LOW"
    assert out["hazard_rating"] == 0.0
