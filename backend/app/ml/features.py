import math
import numpy as np
from typing import Dict, List, Any, Tuple
import rasterio
from shapely.geometry import Point, shape
import geopandas as gpd

FEATURE_NAMES = [
    "elevation_m",
    "rel_elev_river_m",
    "slope_deg",
    "dist_to_river_m",
    "dist_to_dam_km",
    "active_volume_mcm",
    "peak_discharge_m3s",
    "dam_height_m",
    "manning_n",
    "downstream_slope"
]

def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2)**2
    return 2 * R * math.asin(math.sqrt(max(0.0, min(1.0, a))))

def extract_features_at_point(
    lat: float,
    lon: float,
    dem_dataset: rasterio.io.DatasetReader,
    river_gdf: gpd.GeoDataFrame,
    dam_lat: float,
    dam_lon: float,
    scenario_params: Dict[str, Any]
) -> Dict[str, float]:
    """Extract physical and hydraulic features at a specific (lat, lon) coordinate."""
    # 1. Elevation from DEM
    try:
        row, col = dem_dataset.index(lon, lat)
        h_arr = dem_dataset.read(1, window=((row, row + 1), (col, col + 1)))
        elev = float(h_arr[0, 0])
        if elev < -1000 or np.isnan(elev):
            elev = 100.0
    except Exception:
        elev = 100.0

    # 2. Local slope (approximate using 3x3 window if possible)
    try:
        w_size = 3
        r_start = max(0, row - 1)
        c_start = max(0, col - 1)
        sub_elev = dem_dataset.read(1, window=((r_start, r_start + w_size), (c_start, c_start + w_size)))
        if sub_elev.shape == (3, 3):
            # Finite difference
            dx = 30.0
            dz_dx = (sub_elev[1, 2] - sub_elev[1, 0]) / (2 * dx)
            dz_dy = (sub_elev[2, 1] - sub_elev[0, 1]) / (2 * dx)
            slope_rad = math.atan(math.sqrt(dz_dx**2 + dz_dy**2))
            slope_deg = math.degrees(slope_rad)
        else:
            slope_deg = 2.0
    except Exception:
        slope_deg = 2.0

    # 3. Distance to River and River elevation
    pt = Point(lon, lat)
    nearest_river_pt = None
    try:
        if hasattr(river_gdf, "unary_union"):
            river_geom = river_gdf.unary_union
        else:
            river_geom = river_gdf

        min_dist_deg = river_geom.distance(pt)
        nearest_river_pt = river_geom.interpolate(river_geom.project(pt))
        dist_river_m = min_dist_deg * 111139.0
    except Exception:
        dist_river_m = 500.0

    # River elevation at nearest river point
    river_elev = elev
    if nearest_river_pt is not None:
        try:
            r_r, r_c = dem_dataset.index(nearest_river_pt.x, nearest_river_pt.y)
            r_h = dem_dataset.read(1, window=((r_r, r_r + 1), (r_c, r_c + 1)))
            val = float(r_h[0, 0])
            if val > -1000 and not np.isnan(val):
                river_elev = val
        except Exception:
            pass

    rel_elev_river = max(0.0, elev - river_elev)

    # 4. Distance to Dam
    dist_dam_km = haversine_km(lat, lon, dam_lat, dam_lon)

    # 5. Scenario features
    active_vol_mcm = float(scenario_params.get("active_volume_mcm", 500.0))
    peak_q = float(scenario_params.get("peak_discharge_m3s", 80000.0))
    dam_h = float(scenario_params.get("dam_height_m", 65.0))
    manning_n = float(scenario_params.get("manning_n", 0.035))
    ds_slope = float(scenario_params.get("downstream_slope", 0.002))

    return {
        "elevation_m": round(elev, 2),
        "rel_elev_river_m": round(rel_elev_river, 2),
        "slope_deg": round(slope_deg, 2),
        "dist_to_river_m": round(dist_river_m, 2),
        "dist_to_dam_km": round(dist_dam_km, 2),
        "active_volume_mcm": active_vol_mcm,
        "peak_discharge_m3s": peak_q,
        "dam_height_m": dam_h,
        "manning_n": manning_n,
        "downstream_slope": ds_slope
    }
