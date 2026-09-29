import os
import json
import math
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Tuple
import numpy as np
import rasterio
import geopandas as gpd
from shapely.geometry import Point
import joblib

from backend.app.ml.model import RandomForestSurrogate
from backend.app.ml.features import FEATURE_NAMES, extract_features_at_point

def compute_metrics(y_true: np.ndarray, y_pred: np.ndarray, y_prob: np.ndarray) -> Dict[str, float]:
    tp = float(np.sum((y_true == 1) & (y_pred == 1)))
    fp = float(np.sum((y_true == 0) & (y_pred == 1)))
    fn = float(np.sum((y_true == 1) & (y_pred == 0)))
    tn = float(np.sum((y_true == 0) & (y_pred == 0)))

    n = float(len(y_true))
    acc = (tp + tn) / n if n > 0 else 0.0
    prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (2.0 * prec * rec) / (prec + rec) if (prec + rec) > 0 else 0.0
    iou = tp / (tp + fp + fn) if (tp + fp + fn) > 0 else 0.0

    # ROC AUC
    n_pos = np.sum(y_true == 1)
    n_neg = np.sum(y_true == 0)
    if n_pos == 0 or n_neg == 0:
        roc_auc = 1.0
    else:
        desc_indices = np.argsort(y_prob)[::-1]
        y_sorted = y_true[desc_indices]
        tp_cum = np.cumsum(y_sorted == 1)
        fp_cum = np.cumsum(y_sorted == 0)
        tpr = np.r_[0, tp_cum / n_pos]
        fpr = np.r_[0, fp_cum / n_neg]
        roc_auc = float(np.trapz(tpr, fpr))

    return {
        "accuracy": round(acc, 4),
        "precision": round(prec, 4),
        "recall": round(rec, 4),
        "f1_score": round(f1, 4),
        "iou": round(iou, 4),
        "roc_auc": round(roc_auc, 4)
    }

MODEL_DIR = Path("data/ml/flood_predictor")
MODEL_DIR.mkdir(parents=True, exist_ok=True)

def train_surrogate_model():
    """
    Physically trains an ensemble ML surrogate model using parameterized hydrodynamic simulation scenarios.
    Extracts features from authentic Copernicus DEMs and OSM river corridors across Mettur and Idukki.
    """
    print("=== Training Physical-Hydraulic ML Flood Predictor ===")
    
    # 1. Dataset parameters across study domains
    domains = [
        {
            "dam_id": "mettur",
            "dam_lat": 11.8028,
            "dam_lon": 77.8017,
            "dam_height_m": 65.23,
            "dem_path": "data/mettur/dem/processed/mettur_dem_30m.tif",
            "river_path": "data/mettur/river/cauvery_river.geojson",
            "downstream_slope": 0.0004,
            "scenarios": [
                {"name": "Mettur Baseline", "active_volume_mcm": 500.0, "peak_discharge_m3s": 88699.2, "manning_n": 0.035, "is_val": False},
                {"name": "Mettur Moderate", "active_volume_mcm": 350.0, "peak_discharge_m3s": 62000.0, "manning_n": 0.035, "is_val": False},
                {"name": "Mettur Extreme", "active_volume_mcm": 650.0, "peak_discharge_m3s": 115000.0, "manning_n": 0.035, "is_val": True}
            ]
        },
        {
            "dam_id": "idukki",
            "dam_lat": 9.8497,
            "dam_lon": 76.9744,
            "dam_height_m": 168.91,
            "dem_path": "data/idukki/dem/processed/idukki_dem_30m.tif",
            "river_path": "data/idukki/river/periyar_river.geojson",
            "downstream_slope": 0.0113,
            "scenarios": [
                {"name": "Idukki Baseline", "active_volume_mcm": 450.0, "peak_discharge_m3s": 74941.0, "manning_n": 0.040, "is_val": False},
                {"name": "Idukki Low Vol", "active_volume_mcm": 300.0, "peak_discharge_m3s": 51000.0, "manning_n": 0.040, "is_val": False},
                {"name": "Idukki High Vol", "active_volume_mcm": 550.0, "peak_discharge_m3s": 92000.0, "manning_n": 0.040, "is_val": True}
            ]
        }
    ]

    train_X, train_y = [], []
    val_X, val_y = [], []
    training_manifest_records = []

    for dom in domains:
        if not Path(dom["dem_path"]).exists() or not Path(dom["river_path"]).exists():
            print(f"Skipping domain {dom['dam_id']} - datasets missing")
            continue

        with rasterio.open(dom["dem_path"]) as dem:
            river_gdf = gpd.read_file(dom["river_path"])
            river_union = river_gdf.unary_union
            
            # Generate sample grid points around river corridor
            bounds = dem.bounds
            # Downsample grid for balanced representative training (~625 points per scenario)
            lons = np.linspace(bounds.left + 0.02, bounds.right - 0.02, 25)
            lats = np.linspace(bounds.bottom + 0.02, bounds.top - 0.02, 25)

            for scen in dom["scenarios"]:
                scen_record = {
                    "domain": dom["dam_id"],
                    "scenario": scen["name"],
                    "active_volume_mcm": scen["active_volume_mcm"],
                    "peak_discharge_m3s": scen["peak_discharge_m3s"],
                    "is_validation": scen["is_val"]
                }
                training_manifest_records.append(scen_record)

                for lat in lats:
                    for lon in lons:
                        feats = extract_features_at_point(
                            lat=lat,
                            lon=lon,
                            dem_dataset=dem,
                            river_gdf=river_union,
                            dam_lat=dom["dam_lat"],
                            dam_lon=dom["dam_lon"],
                            scenario_params={
                                "active_volume_mcm": scen["active_volume_mcm"],
                                "peak_discharge_m3s": scen["peak_discharge_m3s"],
                                "dam_height_m": dom["dam_height_m"],
                                "manning_n": scen["manning_n"],
                                "downstream_slope": dom["downstream_slope"]
                            }
                        )

                        # Ground truth physical flood condition derived from hydraulic stage-discharge:
                        # Stage estimate from Manning equation h = (Q * n / (W * S^0.5))^(3/5)
                        Q = scen["peak_discharge_m3s"]
                        n = scen["manning_n"]
                        S = max(0.0001, dom["downstream_slope"])
                        W = 80.0
                        h_peak = ((Q * n) / (W * math.sqrt(S))) ** 0.6
                        
                        # Attenuation downstream: h(x) = h_peak * exp(-0.04 * dist_dam_km)
                        h_local = h_peak * math.exp(-0.035 * feats["dist_to_dam_km"])
                        
                        # Flooded if relative elevation above river is less than local flood wave stage
                        # and distance to river is within floodplain conveyance reach
                        max_fp_reach_m = min(1500.0, 300.0 + (Q / 80.0))
                        is_flooded = 1 if (feats["rel_elev_river_m"] < h_local and feats["dist_to_river_m"] < max_fp_reach_m) else 0

                        feature_vector = [feats[col] for col in FEATURE_NAMES]
                        if scen["is_val"]:
                            val_X.append(feature_vector)
                            val_y.append(is_flooded)
                        else:
                            train_X.append(feature_vector)
                            train_y.append(is_flooded)

    X_train = np.array(train_X)
    y_train = np.array(train_y)
    X_val = np.array(val_X)
    y_val = np.array(val_y)

    print(f"Dataset generated: {len(X_train)} training samples, {len(X_val)} held-out validation samples")
    print(f"Positive training class balance: {np.mean(y_train):.2%}")

    # 2. Train Random Forest Classifier with probability calibration
    clf = RandomForestSurrogate(
        n_estimators=40,
        max_depth=10,
        min_samples_split=4,
        random_state=42
    )
    clf.fit(X_train, y_train)

    # 3. Validation Evaluation on held-out scenarios
    val_preds = clf.predict(X_val)
    val_probs = clf.predict_proba(X_val)[:, 1]

    metrics = compute_metrics(y_val, val_preds, val_probs)
    metrics["validation_samples"] = len(y_val)
    metrics["training_samples"] = len(y_train)
    metrics["evaluated_at"] = datetime.utcnow().isoformat() + "Z"

    print(f"Validation Metrics: IoU={metrics['iou']}, F1={metrics['f1_score']}, Accuracy={metrics['accuracy']}, Recall={metrics['recall']}")

    # 4. Save model artifact
    model_path = MODEL_DIR / "model.pkl"
    joblib.dump(clf, model_path)
    
    # Compute SHA256 hash
    hasher = hashlib.sha256()
    with open(model_path, "rb") as f:
        hasher.update(f.read())
    model_hash = hasher.hexdigest()

    # 5. Save Feature Schema
    with open(MODEL_DIR / "feature_schema.json", "w", encoding="utf-8") as f:
        json.dump({
            "features": FEATURE_NAMES,
            "feature_count": len(FEATURE_NAMES),
            "feature_importances": {
                name: round(float(imp), 4) for name, imp in zip(FEATURE_NAMES, clf.feature_importances_)
            }
        }, f, indent=2)

    # 6. Save Training Manifest
    with open(MODEL_DIR / "training_manifest.json", "w", encoding="utf-8") as f:
        json.dump({
            "model_version": "1.0.0",
            "algorithm": "RandomForestClassifier",
            "model_hash": model_hash,
            "trained_at": datetime.utcnow().isoformat() + "Z",
            "scenarios_used": training_manifest_records,
            "total_training_samples": len(X_train),
            "total_validation_samples": len(X_val)
        }, f, indent=2)

    # 7. Save Validation Metrics
    with open(MODEL_DIR / "validation_metrics.json", "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2)

    print(f"[SUCCESS] ML Flood Predictor successfully trained & saved to {MODEL_DIR}")
    return metrics

if __name__ == "__main__":
    train_surrogate_model()
