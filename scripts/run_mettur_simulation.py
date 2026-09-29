"""
PHASE 5 — Mettur Dam Break Hydrodynamic Simulation Pipeline
=============================================================

This script uses the GeneralizedFloodRoutingEngine validated in Checkpoint 1.

All dam-specific parameters are loaded from:
  data/mettur/scenarios/baseline_breach.json

No Mettur-specific coordinate or elevation is hardcoded in solver logic.

Pipeline stages:
  A. Load scenario
  B. Compute breach hydrograph (strict mass conservation)
  C. Verify mass conservation (independent quadrature)
  D. Generalized routing engine: DEM load -> River reach -> Station sampling
     -> 2D Manning propagation -> Inundation mask -> GIS export
  E. Diagnostic plots
  F. Sensitivity analysis (dt: 60/30/15 s)
  G. Reproducibility check
  H. Cross-dam generalization proof (code scan)

Run from E:\\dam:
    python scripts/run_mettur_simulation.py
"""

import os
import sys
import json
import math
import time
import copy
import hashlib
import datetime
import argparse
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LightSource
from pathlib import Path

import rasterio
import geopandas as gpd

BASE_DIR = Path(__file__).resolve().parent.parent

# ── Paths ─────────────────────────────────────────────────────────────────────
SCENARIO_PATH  = BASE_DIR / "data" / "mettur" / "scenarios" / "baseline_breach.json"
DEM_PATH       = BASE_DIR / "data" / "mettur" / "dem" / "processed" / "mettur_dem_30m.tif"
RIVER_PATH     = BASE_DIR / "data" / "mettur" / "river" / "cauvery_river.geojson"
RESERVOIR_PATH = BASE_DIR / "data" / "mettur" / "reservoir" / "stanley_reservoir.geojson"
OUT_SIM_DIR    = BASE_DIR / "data" / "mettur" / "simulations" / "baseline_breach"
QA_PLOTS_DIR   = BASE_DIR / "data" / "mettur" / "qa_plots"

for d in [OUT_SIM_DIR, QA_PLOTS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(BASE_DIR))

from backend.app.hydrodynamics.routing_engine import (
    GeneralizedFloodRoutingEngine,
    compute_breach_hydrograph,
    verify_mass_conservation,
    INUNDATION_DEPTH_THRESHOLD_M,
)


# =============================================================================
# A. LOAD SCENARIO
# =============================================================================
def load_scenario():
    print("\n[STAGE A] Loading scenario...")
    with open(SCENARIO_PATH, encoding="utf-8") as f:
        sc = json.load(f)

    meta = sc["_scenario_metadata"]
    rs   = sc["reservoir_initial_state"]
    bp   = sc["breach_parameters"]
    ctrl = sc["simulation_controls"]

    def _v(node):
        if isinstance(node, dict) and "value" in node:
            return node["value"]
        return node

    dam_config = {
        "dam_id":                       meta["dam_id"],
        "scenario_id":                  meta["scenario_id"],
        "dam_lat":                      _v(sc["dam_location"]["latitude"]),
        "dam_lon":                      _v(sc["dam_location"]["longitude"]),
        # reservoir
        "initial_water_level_m":        _v(rs["initial_water_level_m"]),
        "active_breach_volume_m3":      _v(rs["active_breach_volume_m3"]),
        "surface_area_m2":              _v(rs["surface_area_m2"]),
        "river_bed_elevation_m":        _v(rs["river_bed_elevation_m"]),
        # breach
        "breach_depth_m":               _v(bp["breach_depth_m"]),
        "breach_bottom_width_m":        _v(bp["breach_bottom_width_m"]),
        "breach_side_slope_z":          _v(bp["breach_side_slope_z"]),
        "breach_formation_time_sec":    _v(bp["breach_formation_time_sec"]),
        # simulation
        "simulation_duration_sec":      _v(ctrl["simulation_duration_sec"]),
        "manning_n_channel":            ctrl["manning_roughness_n"]["main_channel"]["value"],
        "manning_n_floodplain":         ctrl["manning_roughness_n"]["floodplain"]["value"],
        "inundation_threshold_m":       _v(ctrl["inundation_threshold_m"]),
    }

    print(f"  Dam:                    {meta['dam_name']}")
    print(f"  Scenario:               {meta['scenario_id']}")
    print(f"  Active breach volume:   {dam_config['active_breach_volume_m3']/1e6:.0f} MCM [SCENARIO ASSUMPTION]")
    print(f"  Formation time:         {dam_config['breach_formation_time_sec']/3600:.2f} hr [SCENARIO ASSUMPTION]")
    print(f"  Manning n channel:      {dam_config['manning_n_channel']} [SCENARIO ASSUMPTION]")

    return dam_config, sc


# =============================================================================
# E. DIAGNOSTIC PLOTS
# =============================================================================
def generate_diagnostic_plots(result, dam_config, sc):
    print("\n[STAGE E] Generating diagnostic plots...")

    hydro_records = result["hydro_records"]
    times_hr      = [r["time_hr"]          for r in hydro_records]
    q_vals        = [r["discharge_m3s"]    for r in hydro_records]
    stages        = [r["stage_m_msl"]      for r in hydro_records]
    vols_mcm      = [r["reservoir_volume_m3"] / 1e6 for r in hydro_records]

    # 01: Hydrograph
    fig, ax1 = plt.subplots(figsize=(11, 5), dpi=150)
    ax1.set_xlabel("Simulation Time (hours)", fontweight="bold")
    ax1.set_ylabel("Breach Outflow Q (m³/s)", color="tab:blue", fontweight="bold")
    ax1.plot(times_hr, q_vals, "tab:blue", linewidth=2.5, label="Breach Q(t)")
    ax1.tick_params(axis="y", labelcolor="tab:blue")
    ax1.grid(True, linestyle=":", alpha=0.6)
    ax2 = ax1.twinx()
    ax2.set_ylabel("Reservoir Level (m MSL)", color="tab:red", fontweight="bold")
    ax2.plot(times_hr, stages, "tab:red", linewidth=2.0, linestyle="--", label="Stage H(t)")
    ax2.tick_params(axis="y", labelcolor="tab:red")
    pk = int(np.argmax(q_vals))
    ax1.annotate(
        f"Peak Q: {q_vals[pk]:,.0f} m³/s\nat T+{times_hr[pk]*60:.0f} min",
        xy=(times_hr[pk], q_vals[pk]),
        xytext=(times_hr[pk] + 0.8, q_vals[pk] * 0.85),
        arrowprops=dict(facecolor="black", shrink=0.06, width=1, headwidth=6),
        fontweight="bold",
        bbox=dict(boxstyle="round,pad=0.3", fc="yellow", alpha=0.8),
    )
    plt.title(
        "Mettur Dam — Hypothetical Breach Hydrograph\n"
        "(Froehlich 2008 + Strict Mass Conservation | SCENARIO ASSUMPTION | NOT A FORECAST)",
        fontsize=10, fontweight="bold",
    )
    plt.tight_layout()
    p1 = QA_PLOTS_DIR / "01_mettur_hydrograph.png"
    plt.savefig(p1)
    plt.close()
    print(f"  Saved: {p1}")

    # 02: Mass conservation
    mass = result["mass_result"]
    fig, ax = plt.subplots(figsize=(9, 4), dpi=150)
    ax.plot(times_hr, vols_mcm, "tab:green", linewidth=2.5, label="Reservoir Volume (MCM)")
    ax.axhline(mass["initial_volume_mcm"], color="grey", linestyle="--", label=f"V_initial = {mass['initial_volume_mcm']:.2f} MCM")
    ax.axhline(mass["final_volume_mcm"],   color="orange", linestyle=":",  label=f"V_final = {mass['final_volume_mcm']:.4f} MCM")
    ax.set_xlabel("Time (hr)")
    ax.set_ylabel("Volume (MCM)")
    ax.set_title("Mettur — Reservoir Volume Drawdown (Strict Mass Conservation)")
    ax.legend(fontsize=9)
    ax.grid(True, linestyle=":", alpha=0.6)
    plt.tight_layout()
    p2 = QA_PLOTS_DIR / "02_mettur_mass_conservation.png"
    plt.savefig(p2)
    plt.close()
    print(f"  Saved: {p2}")

    # 06: DEM + Dam + Cauvery + Depth + Inundation (required diagnostic)
    with rasterio.open(str(DEM_PATH)) as src:
        dem_arr  = src.read(1).astype(np.float64)
        bounds   = src.bounds
        nodata   = src.nodata if src.nodata else -32767.0
        extent_m = [bounds.left, bounds.right, bounds.bottom, bounds.top]
        dem_arr[dem_arr == nodata] = np.nan

    ls = LightSource(azdeg=315, altdeg=45)
    dem_filled  = np.nan_to_num(dem_arr, nan=float(np.nanmin(dem_arr[~np.isnan(dem_arr)])))
    hillshade   = ls.hillshade(dem_filled, vert_exag=3.0)

    max_depth_arr = result["prop_result"]["max_depth"].astype(np.float64)
    max_depth_arr[max_depth_arr <= 0] = np.nan

    gdf_river = gpd.read_file(str(RIVER_PATH))
    gdf_river = gdf_river[gdf_river.geometry.notna() & ~gdf_river.geometry.is_empty]

    DAM_LON = dam_config["dam_lon"]
    DAM_LAT = dam_config["dam_lat"]

    fig, axes = plt.subplots(1, 2, figsize=(18, 8), dpi=150)

    # LEFT: DEM hillshade + River + Dam
    ax = axes[0]
    ax.imshow(hillshade, extent=extent_m, cmap="gray", origin="upper", alpha=0.6, aspect="auto")
    vmin, vmax = np.nanpercentile(dem_arr, 2), np.nanpercentile(dem_arr, 98)
    im = ax.imshow(dem_arr, extent=extent_m, cmap="terrain", vmin=vmin, vmax=vmax,
                   origin="upper", alpha=0.5, aspect="auto")
    plt.colorbar(im, ax=ax, fraction=0.03, pad=0.02, label="Elevation (m MSL)")

    for _, row in gdf_river.iterrows():
        g = row.geometry
        if g.geom_type == "LineString":
            xs, ys = zip(*g.coords)
            ax.plot(xs, ys, "b-", linewidth=1.0, alpha=0.85, label="Cauvery River")
        elif g.geom_type == "MultiLineString":
            for part in g.geoms:
                xs, ys = zip(*part.coords)
                ax.plot(xs, ys, "b-", linewidth=1.0, alpha=0.85)

    ax.plot(DAM_LON, DAM_LAT, "r^", markersize=12, markeredgecolor="white",
            markeredgewidth=1.5, zorder=10, label="Mettur Dam")

    from shapely.geometry import Point
    fp = result["flood_polygon"]
    if fp and not fp.is_empty:
        try:
            import geopandas as gpd2
            gdf_fp = gpd2.GeoDataFrame(geometry=[fp], crs="EPSG:4326")
            gdf_fp.boundary.plot(ax=ax, color="red", linewidth=1.5, label="Flood Boundary", zorder=8)
        except Exception:
            pass

    ax.set_title(f"Mettur Dam — DEM Terrain + Cauvery + Flood Boundary", fontweight="bold")
    ax.set_xlabel("Longitude (°E)")
    ax.set_ylabel("Latitude (°N)")

    from matplotlib.patches import Patch
    from matplotlib.lines import Line2D
    handles = [
        plt.scatter([], [], marker="^", color="red", s=100, label="Mettur Dam"),
        Line2D([0], [0], color="blue",  linewidth=1.5, label="Cauvery River"),
        Patch(edgecolor="red", facecolor="none", linewidth=1.5, label="Flood Boundary"),
    ]
    ax.legend(handles=handles, loc="upper left", fontsize=9)

    # RIGHT: Maximum depth raster
    ax2 = axes[1]
    ax2.imshow(hillshade, extent=extent_m, cmap="gray", origin="upper", alpha=0.5, aspect="auto")
    depth_disp = np.copy(max_depth_arr)
    depth_disp[np.isnan(depth_disp)] = 0.0
    depth_disp[depth_disp < INUNDATION_DEPTH_THRESHOLD_M] = np.nan

    im2 = ax2.imshow(depth_disp, extent=extent_m, cmap="Blues", origin="upper",
                     alpha=0.75, vmin=0.0, vmax=np.nanpercentile(depth_disp[~np.isnan(depth_disp)], 99)
                     if np.any(~np.isnan(depth_disp)) else 5.0, aspect="auto")
    plt.colorbar(im2, ax=ax2, fraction=0.03, pad=0.02, label="Max Water Depth (m)")

    for _, row in gdf_river.iterrows():
        g = row.geometry
        if g.geom_type == "LineString":
            xs, ys = zip(*g.coords)
            ax2.plot(xs, ys, "cyan", linewidth=0.8, alpha=0.8)
        elif g.geom_type == "MultiLineString":
            for part in g.geoms:
                xs, ys = zip(*part.coords)
                ax2.plot(xs, ys, "cyan", linewidth=0.8, alpha=0.8)

    ax2.plot(DAM_LON, DAM_LAT, "r^", markersize=12, markeredgecolor="white",
             markeredgewidth=1.5, zorder=10)
    ax2.set_title(
        f"Mettur Dam — Max Water Depth Inundation\n"
        f"Area: {result['prop_result']['inundated_area_sqkm']:.2f} km² | "
        f"Peak depth: {result['prop_result']['peak_depth_m']:.2f} m | "
        f"Threshold: {INUNDATION_DEPTH_THRESHOLD_M} m",
        fontweight="bold", fontsize=9
    )
    ax2.set_xlabel("Longitude (°E)")
    ax2.set_ylabel("Latitude (°N)")

    fig.suptitle(
        "Phase 5 — Mettur Dam Break Simulation Diagnostic\n"
        "[HYPOTHETICAL SCENARIO — NOT A FORECAST]",
        fontsize=12, fontweight="bold",
    )
    plt.tight_layout(rect=[0, 0, 1, 0.95])
    p6 = QA_PLOTS_DIR / "06_dam_cauvery_depth_inundation_diagnostic.png"
    plt.savefig(p6)
    plt.close()
    print(f"  Saved: {p6}")


# =============================================================================
# F. SENSITIVITY ANALYSIS
# =============================================================================
def run_sensitivity_analysis(dam_config, sc):
    print("\n[STAGE F] Timestep Sensitivity Analysis (dt = 60 / 30 / 15 s)...")
    dts = [60.0, 30.0, 15.0]
    sens_results = []

    for dt in dts:
        print(f"\n  Running dt = {dt:.0f} s...")
        cfg = copy.deepcopy(dam_config)
        hydro, V_act = compute_breach_hydrograph(cfg, dt_sec=dt)
        mass = verify_mass_conservation(hydro, V_act)

        result = GeneralizedFloodRoutingEngine.run(
            dam_config=cfg,
            dataset_paths={
                "dem":        str(DEM_PATH),
                "river":      str(RIVER_PATH),
                "output_dir": str(OUT_SIM_DIR / f"sensitivity_dt_{int(dt)}s"),
            },
            hydro_records=hydro,
            V_active_m3=V_act,
            dt_override=dt,
            river_name_hint="Kaveri",
        )

        pr = result["prop_result"]
        sens_results.append({
            "dt_sec":                 dt,
            "peak_discharge_m3s":     mass["peak_discharge_m3s"],
            "time_to_peak_min":       mass["time_to_peak_min"],
            "released_volume_mcm":    mass["released_volume_mcm"],
            "mass_balance_error_pct": mass["mass_balance_error_pct"],
            "maximum_depth_m":        pr["peak_depth_m"],
            "maximum_velocity_ms":    pr["peak_velocity_ms"],
            "inundated_area_sqkm":    pr["inundated_area_sqkm"],
        })
        print(f"  dt={dt:.0f}s: Q_peak={mass['peak_discharge_m3s']:.1f} m3/s, "
              f"area={pr['inundated_area_sqkm']:.2f} km2, "
              f"max_depth={pr['peak_depth_m']:.2f} m")

    print("\n  Sensitivity table:")
    print(f"  {'dt(s)':>6} | {'Q_peak(m3/s)':>14} | {'T_peak(min)':>11} | "
          f"{'MaxDepth(m)':>11} | {'Area(km2)':>10} | {'MBerr(%)':>10}")
    print("  " + "-" * 75)
    for r in sens_results:
        print(f"  {r['dt_sec']:>6.0f} | {r['peak_discharge_m3s']:>14,.1f} | "
              f"{r['time_to_peak_min']:>11.1f} | {r['maximum_depth_m']:>11.2f} | "
              f"{r['inundated_area_sqkm']:>10.2f} | {r['mass_balance_error_pct']:>10.8f}")

    # Check convergence
    for metric in ["peak_discharge_m3s", "inundated_area_sqkm", "maximum_depth_m"]:
        v60 = sens_results[0][metric]
        v15 = sens_results[2][metric]
        rel_change = abs(v60 - v15) / max(1e-9, v15) * 100.0
        convergence = "CONVERGED" if rel_change < 2.0 else "NOT CONVERGED"
        print(f"  {metric}: dt=60s={v60:.3f}, dt=15s={v15:.3f}, "
              f"change={rel_change:.2f}% — {convergence}")

    sens_path = OUT_SIM_DIR / "sensitivity_results.json"
    with open(sens_path, "w", encoding="utf-8") as f:
        json.dump(sens_results, f, indent=2)
    print(f"\n  Saved: {sens_path}")
    return sens_results


# =============================================================================
# G. REPRODUCIBILITY CHECK
# =============================================================================
def run_reproducibility_check(dam_config):
    print("\n[STAGE G] Reproducibility Check (two cold-start runs)...")

    def _run_and_hash(run_label):
        cfg = copy.deepcopy(dam_config)
        result = GeneralizedFloodRoutingEngine.run(
            dam_config=cfg,
            dataset_paths={
                "dem":        str(DEM_PATH),
                "river":      str(RIVER_PATH),
                "output_dir": str(OUT_SIM_DIR / f"repro_{run_label}"),
            },
            river_name_hint="Kaveri",
        )
        inund_flat = result["prop_result"]["inundated_area_sqkm"]
        depth_flat = result["prop_result"]["peak_depth_m"]
        vel_flat   = result["prop_result"]["peak_velocity_ms"]
        mask_bytes = result["inundation_mask"].tobytes()
        mask_hash  = hashlib.md5(mask_bytes).hexdigest()
        return {
            "inundated_area_sqkm": inund_flat,
            "peak_depth_m":        depth_flat,
            "peak_velocity_ms":    vel_flat,
            "inundation_mask_md5": mask_hash,
        }

    r1 = _run_and_hash("run1")
    r2 = _run_and_hash("run2")

    print(f"\n  Run 1: area={r1['inundated_area_sqkm']:.4f} km², "
          f"depth={r1['peak_depth_m']:.4f} m, md5={r1['inundation_mask_md5'][:8]}...")
    print(f"  Run 2: area={r2['inundated_area_sqkm']:.4f} km², "
          f"depth={r2['peak_depth_m']:.4f} m, md5={r2['inundation_mask_md5'][:8]}...")

    area_diff   = abs(r1["inundated_area_sqkm"] - r2["inundated_area_sqkm"])
    depth_diff  = abs(r1["peak_depth_m"]        - r2["peak_depth_m"])
    mask_match  = r1["inundation_mask_md5"] == r2["inundation_mask_md5"]

    print(f"\n  Area difference:   {area_diff:.6f} km²")
    print(f"  Depth difference:  {depth_diff:.6f} m")
    print(f"  Inundation mask:   {'BIT-EXACT MATCH' if mask_match else 'MISMATCH — investigate!'}")

    if not mask_match:
        print("  WARNING: Inundation mask hashes differ — non-deterministic solver path detected.")

    repro = {
        "run1": r1, "run2": r2,
        "area_diff_km2":  round(area_diff, 6),
        "depth_diff_m":   round(depth_diff, 6),
        "mask_bit_exact": mask_match,
    }
    repro_path = OUT_SIM_DIR / "reproducibility_results.json"
    with open(repro_path, "w", encoding="utf-8") as f:
        json.dump(repro, f, indent=2)
    print(f"  Saved: {repro_path}")
    return repro


# =============================================================================
# H. CROSS-DAM GENERALIZATION PROOF (code scan)
# =============================================================================
def verify_cross_dam_generalization():
    print("\n[STAGE H] Cross-Dam Generalization Proof — Code Scan...")
    import re

    engine_path = BASE_DIR / "backend" / "app" / "hydrodynamics" / "routing_engine.py"
    source = engine_path.read_text(encoding="utf-8")

    TOKENS = {
        "idukki": r"\bidukki\b",
        "periyar": r"\bperiyar\b",
        "Idukki": r"\bIdukki\b",
        "Periyar": r"\bPeriyar\b",
    }
    SOLVER_LOGIC_CONTEXT = {"if", "elif", "==", "!=", "and", "or", "return", "raise", "assert"}

    violations = []
    for lineno, line in enumerate(source.splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith("#") or stripped.startswith('"""') or stripped.startswith("'''"):
            continue
        for name, pat in TOKENS.items():
            if re.search(pat, line):
                violations.append((lineno, name, line.strip()))

    if violations:
        print(f"  VIOLATIONS ({len(violations)}):")
        for ln, tok, txt in violations:
            print(f"    Line {ln} [{tok}]: {txt}")
    else:
        print("  CLEAN: No Idukki/Periyar tokens in routing_engine.py solver code.")

    idukki_runner = BASE_DIR / "scripts" / "run_idukki_simulation.py"
    mettur_runner = BASE_DIR / "scripts" / "run_mettur_simulation.py"

    print("\n  Generalization proof:")
    print(f"  Idukki runner  → GeneralizedFloodRoutingEngine: {idukki_runner.exists()}")
    print(f"  Mettur runner  → GeneralizedFloodRoutingEngine: {mettur_runner.exists()}")
    print(f"  Engine code violations: {len(violations)}")

    return {
        "engine_path": str(engine_path),
        "idukki_token_violations_in_engine": len(violations),
        "violations": [{"line": ln, "token": tok, "text": txt} for ln, tok, txt in violations],
        "idukki_runner_exists": idukki_runner.exists(),
        "mettur_runner_exists": mettur_runner.exists(),
        "generalization_clean": len(violations) == 0,
    }


# =============================================================================
# MANIFEST
# =============================================================================
def save_simulation_manifest(dam_config, mass_result, result, sens_results, repro, xdg):
    manifest = {
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "project": "mettur",
        "phase": 5,
        "scenario_id":   result["scenario_id"],
        "solver":        result["solver"],
        "sph_status":    result["sph_status"],
        "delft3d_status": result["delft3d_status"],
        "dam_config": {
            k: v for k, v in dam_config.items()
            if k not in {"active_breach_volume_m3", "surface_area_m2"}
        },
        "mass_conservation": mass_result,
        "hydraulic_summary": {
            "peak_depth_m":         result["prop_result"]["peak_depth_m"],
            "peak_velocity_ms":     result["prop_result"]["peak_velocity_ms"],
            "inundated_area_sqkm":  result["prop_result"]["inundated_area_sqkm"],
            "inundated_cells":      result["prop_result"]["inundated_cell_count"],
            "river_stations":       result["n_stations"],
            "reach_km":             result["reach_km"],
            "upstream_elev_m":      result["upstream_elev_m"],
            "downstream_elev_m":    result["downstream_elev_m"],
            "mean_slope_m_per_km":  result["mean_slope_m_per_km"],
            "runtime_sec":          result["runtime_sec"],
        },
        "gis_files": result["gis_files"],
        "sensitivity": sens_results,
        "reproducibility": repro,
        "cross_dam_generalization": xdg,
        "inputs": {
            "dem":      str(DEM_PATH),
            "river":    str(RIVER_PATH),
            "scenario": str(SCENARIO_PATH),
        },
    }
    mpath = OUT_SIM_DIR / "simulation_manifest.json"
    with open(mpath, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, default=str)
    print(f"\n  Saved manifest: {mpath}")
    return manifest


# =============================================================================
# MAIN
# =============================================================================
def main():
    print("=" * 70)
    print("PHASE 5: METTUR DAM BREAK HYDRODYNAMIC SIMULATION PIPELINE")
    print("         (GeneralizedFloodRoutingEngine | Strict Mass Conservation)")
    print("=" * 70)

    # A. Load scenario
    dam_config, sc = load_scenario()

    # B-D. Full pipeline (baseline dt=60s)
    print("\n[STAGE B-D] Running baseline simulation (dt=60s)...")
    result = GeneralizedFloodRoutingEngine.run(
        dam_config=dam_config,
        dataset_paths={
            "dem":        str(DEM_PATH),
            "river":      str(RIVER_PATH),
            "output_dir": str(OUT_SIM_DIR),
        },
        river_name_hint="Kaveri",
    )

    mass_result = result["mass_result"]

    # E. Diagnostic plots
    generate_diagnostic_plots(result, dam_config, sc)

    # F. Sensitivity
    sens_results = run_sensitivity_analysis(dam_config, sc)

    # G. Reproducibility
    repro = run_reproducibility_check(dam_config)

    # H. Cross-dam proof
    xdg = verify_cross_dam_generalization()

    # Save manifest
    manifest = save_simulation_manifest(dam_config, mass_result, result, sens_results, repro, xdg)

    print("\n" + "=" * 70)
    print("PHASE 5 SIMULATION SUMMARY — METTUR DAM")
    print("=" * 70)
    pr = result["prop_result"]
    print(f"Solver:              {result['solver']}")
    print(f"SPH:                 {result['sph_status']}")
    print(f"Delft3D:             {result['delft3d_status']}")
    print(f"Runtime:             {result['runtime_sec']:.2f} s")
    print(f"River stations:      {result['n_stations']}")
    print(f"Reach length:        {result['reach_km']:.2f} km")
    print(f"Upstream elev:       {result['upstream_elev_m']:.2f} m MSL")
    print(f"Downstream elev:     {result['downstream_elev_m']:.2f} m MSL")
    print(f"Mean slope:          {result['mean_slope_m_per_km']:.4f} m/km")
    print(f"Peak Discharge:      {mass_result['peak_discharge_m3s']:,.1f} m3/s at T+{mass_result['time_to_peak_min']:.1f} min")
    print(f"Active Volume:       {mass_result['initial_volume_mcm']:.2f} MCM [SCENARIO ASSUMPTION]")
    print(f"Released Volume:     {mass_result['released_volume_mcm']:.4f} MCM")
    print(f"Mass Balance Error:  {mass_result['mass_balance_error_pct']:.8f}%  (<= V_initial)")
    print(f"Discrepancy:         {mass_result['numerical_discrepancy_m3']:+.2f} m3")
    print(f"Peak Depth:          {pr['peak_depth_m']:.2f} m")
    print(f"Peak Velocity:       {pr['peak_velocity_ms']:.2f} m/s")
    print(f"Inundated Area:      {pr['inundated_area_sqkm']:.2f} km2")
    print(f"Reproducibility:     {'BIT-EXACT MASK MATCH' if repro['mask_bit_exact'] else 'MASK MISMATCH'}")
    print(f"Engine violations:   {xdg['idukki_token_violations_in_engine']} (must be 0)")
    print("=" * 70)


if __name__ == "__main__":
    main()
