import pytest
import json
from pathlib import Path
from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)
MODEL_DIR = Path("data/ml/flood_predictor")

def test_ml_metadata_files_exist():
    assert (MODEL_DIR / "model.pkl").exists(), "Trained model.pkl must exist"
    assert (MODEL_DIR / "feature_schema.json").exists(), "feature_schema.json must exist"
    assert (MODEL_DIR / "training_manifest.json").exists(), "training_manifest.json must exist"
    assert (MODEL_DIR / "validation_metrics.json").exists(), "validation_metrics.json must exist"

def test_ml_validation_metrics_rigorous():
    with open(MODEL_DIR / "validation_metrics.json", "r", encoding="utf-8") as f:
        metrics = json.load(f)

    # Verification on held-out scenarios (never training accuracy)
    assert metrics["validation_samples"] >= 1000, "Validation set must have >= 1000 samples"
    assert metrics["accuracy"] >= 0.85, f"Validation accuracy {metrics['accuracy']} must be >= 0.85"
    assert metrics["iou"] >= 0.70, f"Validation IoU (Jaccard) {metrics['iou']} must be >= 0.70"
    assert metrics["f1_score"] >= 0.80, f"Validation F1-score {metrics['f1_score']} must be >= 0.80"
    assert metrics["roc_auc"] >= 0.90, f"Validation ROC-AUC {metrics['roc_auc']} must be >= 0.90"

def test_ml_feature_schema_physical_grounding():
    with open(MODEL_DIR / "feature_schema.json", "r", encoding="utf-8") as f:
        schema = json.load(f)

    expected_features = [
        "elevation_m", "rel_elev_river_m", "slope_deg", "dist_to_river_m",
        "dist_to_dam_km", "active_volume_mcm", "peak_discharge_m3s",
        "dam_height_m", "manning_n", "downstream_slope"
    ]
    for feat in expected_features:
        assert feat in schema["features"], f"Feature {feat} missing from schema"
    
    # Feature importances must be non-empty and sum to ~1.0
    importances = schema["feature_importances"]
    assert len(importances) == len(expected_features)
    assert abs(sum(importances.values()) - 1.0) < 0.05
    # Relative elevation to river or distance to river must be top predictors
    assert importances["rel_elev_river_m"] > 0.10 or importances["dist_to_river_m"] > 0.10

def test_ml_metrics_api():
    res = client.get("/api/ml/metrics")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ready"
    assert "metrics" in data
    assert "feature_importances" in data
    assert "provenance" in data

def test_ml_point_prediction_api():
    payload = {
        "lat": 11.79,
        "lon": 77.81,
        "project_id": "mettur",
        "active_volume_mcm": 500.0,
        "peak_discharge_m3s": 80000.0
    }
    res = client.post("/api/ml/predict-point", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert "flood_probability" in data
    assert 0.0 <= data["flood_probability"] <= 1.0
    assert "uncertainty" in data
    assert 0.0 <= data["uncertainty"] <= 1.0
    assert "features_used" in data
    assert data["provenance"] == "AI/ML Random Forest Surrogate (Fast Inundation Predictor)"

def test_ml_grid_prediction_api():
    payload = {
        "project_id": "mettur",
        "active_volume_mcm": 500.0,
        "grid_resolution": 12
    }
    res = client.post("/api/ml/predict-grid", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["type"] == "FeatureCollection"
    assert len(data["features"]) == 12 * 12
    sample = data["features"][0]
    assert "flood_probability" in sample["properties"]
    assert "uncertainty" in sample["properties"]
    assert "is_inundated" in sample["properties"]
