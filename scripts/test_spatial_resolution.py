"""
Spatial resolution sensitivity experiment:
Compares baseline Copernicus 30.8m DEM vs 61.6m coarsened DEM.
"""

import os
import sys
import json
sys.path.insert(0, os.path.abspath("."))

import rasterio
from rasterio.enums import Resampling
from rasterio.transform import Affine
from scripts.run_idukki_simulation import load_scenario, compute_hydrograph, run_hydrodynamic_routing

def run_spatial_sensitivity():
    scen = load_scenario()
    hydro_records, _ = compute_hydrograph(scen)

    dem_30_path = "data/idukki/dem/processed/idukki_dem_30m.tif"
    scratch_dir = "data/idukki/scratch"
    os.makedirs(scratch_dir, exist_ok=True)
    dem_60_path = os.path.join(scratch_dir, "idukki_dem_60m.tif")

    with rasterio.open(dem_30_path) as src:
        dem_30 = src.read(1)
        trans_30 = src.transform
        meta_30 = src.meta.copy()
        new_h, new_w = dem_30.shape[0] // 2, dem_30.shape[1] // 2
        dem_60 = src.read(1, out_shape=(new_h, new_w), resampling=Resampling.bilinear)
        sx = dem_30.shape[1] / new_w
        sy = dem_30.shape[0] / new_h
        trans_60 = Affine(trans_30.a * sx, trans_30.b, trans_30.c, trans_30.d, trans_30.e * sy, trans_30.f)
        meta_60 = meta_30.copy()
        meta_60.update({'height': new_h, 'width': new_w, 'transform': trans_60})

    with rasterio.open(dem_60_path, 'w', **meta_60) as dst:
        dst.write(dem_60, 1)

    print("--- Running 60m resolution simulation ---")
    res_60 = run_hydrodynamic_routing(scen, hydro_records, dem_path=dem_60_path)

    print("--- Running 30m resolution baseline simulation ---")
    res_30 = run_hydrodynamic_routing(scen, hydro_records, dem_path=dem_30_path)

    diff_depth = abs(res_60['peak_depth_m'] - res_30['peak_depth_m']) / res_30['peak_depth_m'] * 100.0
    diff_vel = abs(res_60['peak_velocity_ms'] - res_30['peak_velocity_ms']) / res_30['peak_velocity_ms'] * 100.0
    diff_area = abs(res_60['inundated_area_sqkm'] - res_30['inundated_area_sqkm']) / res_30['inundated_area_sqkm'] * 100.0

    results = {
        "baseline_30m": {
            "resolution_m": 30.8,
            "dimensions": f"{dem_30.shape[1]}x{dem_30.shape[0]}",
            "peak_depth_m": res_30["peak_depth_m"],
            "peak_velocity_ms": res_30["peak_velocity_ms"],
            "inundated_area_sqkm": res_30["inundated_area_sqkm"],
            "runtime_sec": res_30["runtime_sec"]
        },
        "coarsened_60m": {
            "resolution_m": 61.6,
            "dimensions": f"{dem_60.shape[1]}x{dem_60.shape[0]}",
            "peak_depth_m": res_60["peak_depth_m"],
            "peak_velocity_ms": res_60["peak_velocity_ms"],
            "inundated_area_sqkm": res_60["inundated_area_sqkm"],
            "runtime_sec": res_60["runtime_sec"]
        },
        "percentage_differences": {
            "depth_diff_pct": round(diff_depth, 2),
            "velocity_diff_pct": round(diff_vel, 2),
            "area_diff_pct": round(diff_area, 2)
        }
    }

    print("\nSPATIAL RESOLUTION SENSITIVITY RESULTS:")
    print(json.dumps(results, indent=2))
    return results

if __name__ == "__main__":
    run_spatial_sensitivity()
