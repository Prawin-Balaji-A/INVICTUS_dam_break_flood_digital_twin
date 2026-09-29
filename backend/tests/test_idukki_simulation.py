"""
Phase 4 Automated Tests: Idukki Dam-Break Scenario & Hydrodynamic Simulation.
Scientific Verification Checkpoint Test Suite.

Mandatory verification for:
1. test_strict_mass_conservation()
2. test_reservoir_storage_never_negative()
3. test_hydrograph_independent_peak_check()
4. test_routing_follows_periyar_geometry()
5. test_river_geometry_actually_used()
6. test_timestep_sensitivity()
7. test_spatial_resolution_sensitivity()
8. test_simulation_reproducibility()
9. test_inundation_derived_from_depth()
10. test_export_matches_inundation_mask()
"""

import os
import sys
import json
import math
import numpy as np
import pandas as pd
import pytest
import rasterio
from rasterio.enums import Resampling
from rasterio.transform import Affine
import geopandas as gpd
from pathlib import Path
from shapely.geometry import Point, box, LineString
from shapely.ops import linemerge, unary_union, substring
from scipy.integrate import solve_ivp

BASE_DIR = Path(__file__).resolve().parent.parent.parent
IDUKKI_DIR = BASE_DIR / "data" / "idukki"
SCENARIO_PATH = IDUKKI_DIR / "scenarios" / "baseline_breach.json"
SIM_DIR = IDUKKI_DIR / "simulations" / "baseline_breach"
HYDROGRAPH_PATH = SIM_DIR / "hydrograph.csv"
MANIFEST_PATH = SIM_DIR / "simulation_manifest.json"
DEPTH_TIF = SIM_DIR / "maximum_depth.tif"
VEL_TIF = SIM_DIR / "maximum_velocity.tif"
ARR_TIF = SIM_DIR / "arrival_time.tif"
MASK_TIF = SIM_DIR / "inundation_mask.tif"
GEOJSON_PATH = SIM_DIR / "flood_extent.geojson"
KML_PATH = SIM_DIR / "flood_extent.kml"
DEM_PATH = IDUKKI_DIR / "dem" / "processed" / "idukki_dem_30m.tif"
RIVER_PATH = IDUKKI_DIR / "river" / "periyar_river.geojson"

sys.path.insert(0, str(BASE_DIR))
from scripts.run_idukki_simulation import (
    load_scenario,
    compute_hydrograph,
    verify_mass_conservation,
    run_hydrodynamic_routing,
    extract_periyar_downstream_reach
)


def test_breach_scenario_schema():
    """Verify breach scenario has valid schema, hypothetical classification, and full provenance."""
    assert SCENARIO_PATH.exists(), f"Scenario file missing at {SCENARIO_PATH}"
    with open(SCENARIO_PATH, "r", encoding="utf-8") as f:
        scen = json.load(f)

    assert scen["scenario_id"] == "baseline_breach"
    assert scen["scenario_type"] == "HYPOTHETICAL DAM-BREAK"
    assert "hypothetical" in scen.get("disclaimer", "").lower()

    bp = scen["breach_parameters"]
    required_bp = [
        "breach_formulation", "breach_bottom_width_m", "breach_depth_m",
        "breach_side_slope_z", "breach_formation_time_hr"
    ]
    for param in required_bp:
        assert param in bp, f"Missing parameter {param} in breach_parameters"
        assert "value" in bp[param], f"Missing 'value' for {param}"
        assert "provenance" in bp[param], f"Missing 'provenance' for {param}"
        assert "type" in bp[param], f"Missing 'type' for {param}"

    rc = scen["reservoir_parameters"]
    assert rc["initial_water_level_m"]["value"] == 732.43
    assert rc["active_breach_volume_basis_m3"]["value"] == 450000000.0

    sc = scen["simulation_controls"]
    assert sc["simulation_duration_hr"] == 6.0
    assert sc["timestep_seconds"] == 60.0
    assert sc["manning_roughness_n"]["main_channel"] == 0.035
    assert sc["manning_roughness_n"]["floodplain"] == 0.055


def test_hydrograph_monotonic_time():
    """Verify simulation time array is strictly monotonically increasing."""
    assert HYDROGRAPH_PATH.exists(), f"Hydrograph missing at {HYDROGRAPH_PATH}"
    df = pd.read_csv(HYDROGRAPH_PATH)
    assert len(df) > 10, "Hydrograph must contain multiple timesteps"

    times_s = df["time_sec"].to_numpy()
    assert times_s[0] == 0.0, "Simulation time must start at 0.0 s"
    diffs = np.diff(times_s)
    assert np.all(diffs > 0), "Time steps must be strictly monotonically increasing"
    assert np.allclose(diffs, 60.0), "Uniform 60-second time steps expected"


def test_hydrograph_nonnegative_discharge():
    """Verify outflow discharge is non-negative and contains a valid peak."""
    df = pd.read_csv(HYDROGRAPH_PATH)
    q = df["discharge_m3s"].to_numpy()

    assert np.all(q >= 0.0), "Breach discharge cannot be negative"
    assert q[0] == 0.0 or q[0] < 50.0, "Initial discharge should start near zero"

    peak_q = float(np.max(q))
    assert peak_q > 1000.0, f"Expected realistic dam-break peak discharge, got {peak_q}"
    assert peak_q < 200000.0, f"Discharge exceeds physical upper bound, got {peak_q}"


def test_hydrograph_no_nan():
    """Verify hydrograph contains zero NaN, Null, or infinite values."""
    df = pd.read_csv(HYDROGRAPH_PATH)
    for col in ["time_sec", "time_min", "time_hr", "discharge_m3s", "stage_m_msl", "reservoir_volume_m3"]:
        assert col in df.columns, f"Missing column {col} in hydrograph"
        assert not df[col].isna().any(), f"Column {col} contains NaN values"
        assert not np.isinf(df[col]).any(), f"Column {col} contains Inf values"


def test_strict_mass_conservation():
    """Verify released volume does not exceed available reservoir storage within strict tolerance."""
    df = pd.read_csv(HYDROGRAPH_PATH)
    time_s = df["time_sec"].to_numpy()
    q = df["discharge_m3s"].to_numpy()

    with open(SCENARIO_PATH, "r", encoding="utf-8") as f:
        scen = json.load(f)
    v_active_m3 = scen["reservoir_parameters"]["active_breach_volume_basis_m3"]["value"]

    # Integrate discharge Q(t) using trapezoidal rule
    dt = np.diff(time_s)
    q_avg = 0.5 * (q[:-1] + q[1:])
    v_released_m3 = float(np.sum(q_avg * dt))

    # Released volume must NOT exceed initial volume + 100 m3 machine tolerance (< 0.0001%)
    tolerance_m3 = 100.0
    assert v_released_m3 <= v_active_m3 + tolerance_m3, (
        f"Released volume {v_released_m3/1e6:.4f} MCM exceeds initial storage {v_active_m3/1e6:.4f} MCM!"
    )
    rel_error_pct = abs(v_released_m3 - v_active_m3) / v_active_m3 * 100.0
    assert rel_error_pct < 0.01, f"Relative mass balance error {rel_error_pct:.6f}% exceeds 0.01%"


def test_reservoir_storage_never_negative():
    """Verify remaining reservoir storage V(t) >= 0 at every single timestep."""
    df = pd.read_csv(HYDROGRAPH_PATH)
    v_storage = df["reservoir_volume_m3"].to_numpy()
    assert np.all(v_storage >= -1e-6), "Reservoir storage became negative at one or more timesteps"


def test_hydrograph_independent_peak_check():
    """
    Independently calculate the peak breach discharge using a separate ODE solver (RK45)
    and compare against the simulation result without calling compute_hydrograph().
    """
    with open(SCENARIO_PATH, "r", encoding="utf-8") as f:
        scen = json.load(f)

    V_init = float(scen["reservoir_parameters"]["active_breach_volume_basis_m3"]["value"])
    H_init = float(scen["reservoir_parameters"]["initial_water_level_m"]["value"])
    A_res = float(scen["reservoir_parameters"]["surface_area_m2"]["value"])
    Wb = float(scen["breach_parameters"]["breach_bottom_width_m"]["value"])
    z = float(scen["breach_parameters"]["breach_side_slope_z"]["value"])
    hb = float(scen["breach_parameters"]["breach_depth_m"]["value"])
    tf = float(scen["breach_parameters"]["breach_formation_time_hr"]["value"]) * 3600.0
    z_top = H_init
    Cw = 1.70
    Cs = 1.20

    # Independent ODE formulation for reservoir drawdown: dV/dt = -Q(t, V)
    def independent_dVdt(t, V_val):
        V = V_val[0]
        if V <= 0:
            return [0.0]
        eta = 0.5 * (1.0 - math.cos(math.pi * t / tf)) if t <= tf else 1.0
        Wb_t = max(1.0, Wb * eta)
        z_inv = z_top - hb * eta
        dH = (V_init - V) / A_res
        H_cur = max(z_top - hb, H_init - dH)
        head = max(0.0, H_cur - z_inv)
        if head <= 0:
            return [0.0]
        Q = (Cw * Wb_t * (head ** 1.5)) + (Cs * z * (head ** 2.5))
        return [-Q]

    sol = solve_ivp(independent_dVdt, [0, 6 * 3600], [V_init], max_step=15.0, method="RK45")
    q_independent = []
    for t, V in zip(sol.t, sol.y[0]):
        eta = 0.5 * (1.0 - math.cos(math.pi * t / tf)) if t <= tf else 1.0
        Wb_t = max(1.0, Wb * eta)
        z_inv = z_top - hb * eta
        dH = (V_init - V) / A_res
        H_cur = max(z_top - hb, H_init - dH)
        head = max(0.0, H_cur - z_inv)
        Q = (Cw * Wb_t * (head ** 1.5)) + (Cs * z * (head ** 2.5)) if (head > 0 and V > 0) else 0.0
        q_independent.append(Q)

    independent_peak_q = float(np.max(q_independent))
    df = pd.read_csv(HYDROGRAPH_PATH)
    sim_peak_q = float(np.max(df["discharge_m3s"]))

    # Compare simulation peak against independent RK45 peak
    pct_diff = abs(sim_peak_q - independent_peak_q) / independent_peak_q * 100.0
    print(f"\nIndependent Peak Q: {independent_peak_q:.1f} m³/s vs Sim Peak Q: {sim_peak_q:.1f} m³/s (Diff: {pct_diff:.2f}%)")
    assert pct_diff < 1.0, f"Independent hydrograph check failed! Difference {pct_diff:.2f}% exceeds 1.0%"


def test_hydraulic_depth_nonnegative():
    """Verify maximum computed flood depth is non-negative and physically bounded."""
    assert DEPTH_TIF.exists(), f"Depth raster missing at {DEPTH_TIF}"
    with rasterio.open(DEPTH_TIF) as src:
        arr = src.read(1)
        nodata = src.nodata if src.nodata is not None else -32767.0
        assert str(src.crs).upper() == "EPSG:4326"

        valid = (arr != nodata) & ~np.isnan(arr)
        assert np.any(valid), "Raster has no valid data pixels"
        assert np.all(arr[valid] >= 0.0), "Computed water depth cannot be negative"

        max_depth = float(np.max(arr[valid]))
        mean_depth = float(np.mean(arr[valid & (arr > 0.05)]))
        assert max_depth >= mean_depth, "Maximum depth must be >= mean positive depth"
        assert 1.0 < max_depth < 80.0, f"Peak depth {max_depth} m outside realistic range"


def test_hydraulic_velocity_nonnegative():
    """Verify maximum flow velocity magnitude is non-negative and physically plausible."""
    assert VEL_TIF.exists(), f"Velocity raster missing at {VEL_TIF}"
    with rasterio.open(VEL_TIF) as src:
        arr = src.read(1)
        nodata = src.nodata if src.nodata is not None else -32767.0
        assert str(src.crs).upper() == "EPSG:4326"

        valid = (arr != nodata) & ~np.isnan(arr)
        assert np.any(valid), "Raster has no valid data pixels"
        assert np.all(arr[valid] >= 0.0), "Velocity magnitude cannot be negative"

        max_vel = float(np.max(arr[valid]))
        mean_vel = float(np.mean(arr[valid & (arr > 0.05)]))
        assert max_vel >= mean_vel, "Maximum velocity must be >= mean positive velocity"
        assert 1.0 < max_vel < 60.0, f"Peak velocity {max_vel} m/s outside realistic range"


def test_inundation_derived_from_depth():
    """Verify inundation mask is directly derived from computed depth > 0.15m."""
    with rasterio.open(DEPTH_TIF) as d_src, rasterio.open(MASK_TIF) as m_src:
        depth = d_src.read(1)
        mask = m_src.read(1)
        nodata = d_src.nodata if d_src.nodata is not None else -32767.0

        valid = (depth != nodata) & ~np.isnan(depth)
        expected_mask = np.where(valid & (depth >= 0.15), 1, 0).astype(np.uint8)

        # Check mask matches depth condition
        assert np.array_equal(mask, expected_mask), "Inundation mask does not match depth >= 0.15m condition"


def test_export_matches_inundation_mask():
    """Verify exported GeoJSON polygon matches raster mask area within vector simplification tolerance."""
    with rasterio.open(MASK_TIF) as m_src:
        mask = m_src.read(1)
        wet_cells = int(np.sum(mask == 1))
        dx_m = abs(m_src.transform[0]) * 111320.0 * math.cos(math.radians(9.85))
        dy_m = abs(m_src.transform[4]) * 111320.0
        raster_area_sqkm = (wet_cells * dx_m * dy_m) / 1e6

    gdf = gpd.read_file(GEOJSON_PATH)
    assert len(gdf) > 0, "Flood extent GeoJSON has no features"
    polygon_area_sqkm = gdf.geometry.to_crs(epsg=32643).area.sum() / 1e6

    area_diff_pct = abs(polygon_area_sqkm - raster_area_sqkm) / raster_area_sqkm * 100.0
    print(f"\nRaster Wet Area: {raster_area_sqkm:.2f} km² vs Polygon Area: {polygon_area_sqkm:.2f} km² (Diff: {area_diff_pct:.2f}%)")
    assert area_diff_pct < 5.0, f"Polygon area diverges from raster wet cells by {area_diff_pct:.2f}% (> 5% tolerance)"


def test_routing_follows_periyar_geometry():
    """Verify active flood propagation coordinates directly align with the Periyar River centerline."""
    with rasterio.open(DEM_PATH) as src:
        bounds = src.bounds
        trans = src.transform
        inv_trans = ~trans

    reach = extract_periyar_downstream_reach(str(RIVER_PATH), bounds, (9.85, 76.97))
    assert reach.length * 111.32 > 30.0, "Periyar downstream reach must exceed 30 km"

    # Sample points along the river and check they correspond to positive depth in maximum_depth.tif
    with rasterio.open(DEPTH_TIF) as d_src:
        depth = d_src.read(1)
        nodata = d_src.nodata

        hit_count = 0
        total_test_points = 50
        for i in range(total_test_points):
            frac = i / total_test_points
            pt = reach.interpolate(frac, normalized=True)
            r, c = rasterio.transform.rowcol(trans, pt.x, pt.y)
            if 0 <= r < depth.shape[0] and 0 <= c < depth.shape[1]:
                # Check within local 3x3 neighborhood of centerline
                r_min, r_max = max(0, r - 2), min(depth.shape[0], r + 3)
                c_min, c_max = max(0, c - 2), min(depth.shape[1], c + 3)
                patch = depth[r_min:r_max, c_min:c_max]
                if np.any(patch > 0.15):
                    hit_count += 1

        hit_rate = hit_count / total_test_points
        print(f"\nRiver centerline inundation overlap: {hit_count}/{total_test_points} ({hit_rate*100:.1f}%)")
        assert hit_rate >= 0.90, f"Flood wave failed to track Periyar river corridor (hit rate {hit_rate*100:.1f}% < 90%)"


def test_river_geometry_actually_used():
    """
    Substantially perturb the river geometry and verify that the hydraulic propagation
    changes accordingly, proving the simulation is genuinely coupled to river geometry.
    """
    scen = load_scenario()
    hydro_records, _ = compute_hydrograph(scen)

    # 1. Baseline routing with real Periyar geometry
    sim_baseline = run_hydrodynamic_routing(scen, hydro_records, river_path=str(RIVER_PATH))
    mask_baseline = sim_baseline["inundation_mask"]

    # 2. Perturbed geometry: shift river coordinates north by 0.05 degrees (~5.5 km)
    gdf_real = gpd.read_file(RIVER_PATH)
    gdf_perturbed = gdf_real.copy()
    gdf_perturbed["geometry"] = gdf_real["geometry"].translate(xoff=0.0, yoff=0.05)

    scratch_dir = IDUKKI_DIR / "scratch"
    scratch_dir.mkdir(parents=True, exist_ok=True)
    perturbed_river_path = scratch_dir / "perturbed_river.geojson"
    gdf_perturbed.to_file(perturbed_river_path, driver="GeoJSON")

    try:
        sim_perturbed = run_hydrodynamic_routing(scen, hydro_records, river_path=str(perturbed_river_path))
        mask_perturbed = sim_perturbed["inundation_mask"]

        # The two masks must NOT be identical
        is_identical = np.array_equal(mask_baseline, mask_perturbed)
        assert not is_identical, "Perturbing river geometry had zero effect on the flood inundation mask!"

        # Jaccard overlap between baseline and perturbed flood masks must be low
        intersection = np.sum((mask_baseline == 1) & (mask_perturbed == 1))
        union = np.sum((mask_baseline == 1) | (mask_perturbed == 1))
        jaccard = intersection / union if union > 0 else 1.0
        print(f"\nRiver Perturbation Test Jaccard Similarity: {jaccard:.4f}")
        assert jaccard < 0.25, f"River perturbation caused insufficient spatial response (Jaccard {jaccard:.2f} >= 0.25)"
    finally:
        if perturbed_river_path.exists():
            perturbed_river_path.unlink()


def test_timestep_sensitivity():
    """Verify simulation numerical sensitivity across dt = 60s, 30s, and 15s."""
    scen = load_scenario()

    hydro_60, V_act = compute_hydrograph(scen, dt_override=60.0)
    mass_60 = verify_mass_conservation(hydro_60, V_act)

    hydro_30, _ = compute_hydrograph(scen, dt_override=30.0)
    mass_30 = verify_mass_conservation(hydro_30, V_act)

    diff_q = abs(mass_60["peak_discharge_m3s"] - mass_30["peak_discharge_m3s"]) / mass_60["peak_discharge_m3s"] * 100.0
    print(f"\nTimestep 60s vs 30s Peak Q diff: {diff_q:.3f}%")
    assert diff_q < 1.0, f"Timestep sensitivity too high: peak Q diff {diff_q:.2f}% exceeds 1.0%"
    assert mass_60["mass_balance_error_pct"] < 0.01
    assert mass_30["mass_balance_error_pct"] < 0.01


def test_spatial_resolution_sensitivity():
    """Verify spatial resolution sensitivity between baseline 30m and coarsened 60m DEM."""
    from scripts.test_spatial_resolution import run_spatial_sensitivity
    results = run_spatial_sensitivity()
    assert "baseline_30m" in results
    assert "coarsened_60m" in results
    assert results["baseline_30m"]["peak_depth_m"] > 0
    assert results["coarsened_60m"]["peak_depth_m"] > 0


def test_simulation_reproducibility():
    """Verify running baseline simulation twice with identical inputs produces identical results."""
    scen = load_scenario()

    hydro_1, v_1 = compute_hydrograph(scen)
    mass_1 = verify_mass_conservation(hydro_1, v_1)

    hydro_2, v_2 = compute_hydrograph(scen)
    mass_2 = verify_mass_conservation(hydro_2, v_2)

    assert mass_1["peak_discharge_m3s"] == mass_2["peak_discharge_m3s"]
    assert mass_1["released_volume_mcm"] == mass_2["released_volume_mcm"]
    assert mass_1["mass_balance_error_pct"] == mass_2["mass_balance_error_pct"]

    # Verify hydrograph records match
    q1 = [r["discharge_m3s"] for r in hydro_1]
    q2 = [r["discharge_m3s"] for r in hydro_2]
    assert np.allclose(q1, q2, atol=1e-5), "Hydrograph discharges diverged across repeated runs"


def test_simulation_uses_idukki_dem():
    """Verify simulation is grounded in the validated Copernicus Idukki DEM."""
    assert MANIFEST_PATH.exists()
    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    manifest_dem = manifest["inputs"]["dem"]
    assert "idukki_dem_30m.tif" in manifest_dem
    assert Path(manifest_dem).exists()


def test_simulation_does_not_use_machchhu():
    """Verify strict isolation from legacy Machchhu-II dataset or coordinates."""
    with open(SCENARIO_PATH, "r", encoding="utf-8") as f:
        scen_text = f.read().lower()
    assert "machchhu" not in scen_text

    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        manifest_text = f.read().lower()
    assert "machchhu" not in manifest_text
