import json
from pathlib import Path
from typing import Dict, Any, List
import numpy as np
import shapely.geometry
import rasterio

class BuildingImpactAnalyzer:
    """
    Analyzes physical flood exposure of building footprints against simulated depth rasters.
    Categorizes risk based on configurable hydrodynamic thresholds:
    - LOW: < 0.3 m
    - MODERATE: 0.3 m - 1.0 m
    - HIGH: 1.0 m - 2.0 m
    - VERY HIGH: > 2.0 m
    """

    @classmethod
    def analyze_buildings(
        cls,
        buildings_geojson_path: str,
        max_depth_raster_path: str,
        arrival_raster_path: str | None = None
    ) -> Dict[str, Any]:
        with open(buildings_geojson_path, "r", encoding="utf-8") as f:
            bldg_data = json.load(f)

        features = bldg_data.get("features", [])
        if not features:
            return {
                "total_buildings": 0,
                "affected_buildings": 0,
                "low_risk": 0,
                "moderate_risk": 0,
                "high_risk": 0,
                "very_high_risk": 0,
                "affected_features": []
            }

        with rasterio.open(max_depth_raster_path) as src_depth:
            depth_arr = src_depth.read(1)
            transform = src_depth.transform
            inv_transform = ~transform
            nodata = src_depth.nodata if src_depth.nodata is not None else -9999.0
            rows, cols = depth_arr.shape

        arr_time_arr = None
        if arrival_raster_path and Path(arrival_raster_path).exists():
            with rasterio.open(arrival_raster_path) as src_arr:
                arr_time_arr = src_arr.read(1)

        affected_list = []
        counts = {"LOW": 0, "MODERATE": 0, "HIGH": 0, "VERY_HIGH": 0}

        for feat in features:
            geom = feat.get("geometry")
            if not geom:
                continue
            poly = shapely.geometry.shape(geom)
            centroid = poly.centroid
            cx, cy = centroid.x, centroid.y

            # Pixel coordinate in raster
            col, row = inv_transform * (cx, cy)
            c_int, r_int = int(round(col)), int(round(row))

            depth_val = 0.0
            if 0 <= r_int < rows and 0 <= c_int < cols:
                raw_d = depth_arr[r_int, c_int]
                if raw_d != nodata and not np.isnan(raw_d) and raw_d > 0.05:
                    depth_val = float(raw_d)

            if depth_val > 0.05:
                # Assign risk level
                if depth_val < 0.3:
                    risk = "LOW"
                elif depth_val < 1.0:
                    risk = "MODERATE"
                elif depth_val < 2.0:
                    risk = "HIGH"
                else:
                    risk = "VERY_HIGH"

                counts[risk] += 1
                arr_min = 0.0
                if arr_time_arr is not None and 0 <= r_int < rows and 0 <= c_int < cols:
                    arr_min = float(arr_time_arr[r_int, c_int])

                props = feat.get("properties", {})
                props.update({
                    "max_flood_depth_m": round(depth_val, 2),
                    "flood_arrival_min": round(arr_min, 1),
                    "risk_category": risk,
                    "is_affected": True
                })
                affected_list.append({
                    "type": "Feature",
                    "id": feat.get("id"),
                    "properties": props,
                    "geometry": geom
                })

        return {
            "total_buildings": len(features),
            "affected_buildings": len(affected_list),
            "risk_breakdown": {
                "low": counts["LOW"],
                "moderate": counts["MODERATE"],
                "high": counts["HIGH"],
                "very_high": counts["VERY_HIGH"]
            },
            "affected_features": affected_list
        }
