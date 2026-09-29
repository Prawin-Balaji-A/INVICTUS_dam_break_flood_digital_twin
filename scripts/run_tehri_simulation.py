"""
Tehri Dam Break Hydrodynamic Simulation Pipeline
=================================================

Uses the SAME dam-agnostic GeneralizedFloodRoutingEngine as Idukki and Mettur.
All dam-specific parameters are loaded from:
  data/tehri/scenarios/baseline_breach.json

No Tehri-specific coordinate or elevation is hardcoded in solver logic; this
runner only wires the authoritative Tehri datasets (real Copernicus DEM + real
OSM Bhagirathi river) into the generalized engine and writes the authoritative
rasters + manifest the digital twin consumes.

Run from E:\\dam:
    python scripts/run_tehri_simulation.py
"""

import os
import sys
import json
import copy
import hashlib
import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SCENARIO_PATH = BASE_DIR / "data" / "tehri" / "scenarios" / "baseline_breach.json"
DEM_PATH      = BASE_DIR / "data" / "tehri" / "dem" / "processed" / "tehri_dem_30m.tif"
RIVER_PATH    = BASE_DIR / "data" / "tehri" / "river" / "bhagirathi_river.geojson"
OUT_SIM_DIR   = BASE_DIR / "data" / "tehri" / "simulations" / "baseline_breach"
OUT_SIM_DIR.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(BASE_DIR))

from backend.app.hydrodynamics.routing_engine import (
    GeneralizedFloodRoutingEngine,
    compute_breach_hydrograph,
    verify_mass_conservation,
)

RIVER_HINT = "Bhagirathi"


def load_scenario():
    print("\n[STAGE A] Loading Tehri scenario...")
    with open(SCENARIO_PATH, encoding="utf-8") as f:
        sc = json.load(f)

    meta = sc["_scenario_metadata"]
    rs = sc["reservoir_initial_state"]
    bp = sc["breach_parameters"]
    ctrl = sc["simulation_controls"]

    def _v(node):
        return node["value"] if isinstance(node, dict) and "value" in node else node

    dam_config = {
        "dam_id": meta["dam_id"],
        "scenario_id": meta["scenario_id"],
        "dam_lat": _v(sc["dam_location"]["latitude"]),
        "dam_lon": _v(sc["dam_location"]["longitude"]),
        "initial_water_level_m": _v(rs["initial_water_level_m"]),
        "active_breach_volume_m3": _v(rs["active_breach_volume_m3"]),
        "surface_area_m2": _v(rs["surface_area_m2"]),
        "river_bed_elevation_m": _v(rs["river_bed_elevation_m"]),
        "breach_depth_m": _v(bp["breach_depth_m"]),
        "breach_bottom_width_m": _v(bp["breach_bottom_width_m"]),
        "breach_side_slope_z": _v(bp["breach_side_slope_z"]),
        "breach_formation_time_sec": _v(bp["breach_formation_time_sec"]),
        "simulation_duration_sec": _v(ctrl["simulation_duration_sec"]),
        "manning_n_channel": ctrl["manning_roughness_n"]["main_channel"]["value"],
        "manning_n_floodplain": ctrl["manning_roughness_n"]["floodplain"]["value"],
        "inundation_threshold_m": _v(ctrl["inundation_threshold_m"]),
    }
    print(f"  Dam: {meta['dam_name']} | Scenario: {meta['scenario_id']}")
    print(f"  Active breach volume: {dam_config['active_breach_volume_m3']/1e6:.0f} MCM [SCENARIO ASSUMPTION]")
    print(f"  Formation time: {dam_config['breach_formation_time_sec']/3600:.2f} hr [SCENARIO ASSUMPTION]")
    return dam_config, sc


def run_sensitivity(dam_config):
    print("\n[STAGE F] Timestep sensitivity (dt = 60 / 30 / 15 s)...")
    out = []
    for dt in (60.0, 30.0, 15.0):
        cfg = copy.deepcopy(dam_config)
        hydro, V_act = compute_breach_hydrograph(cfg, dt_sec=dt)
        mass = verify_mass_conservation(hydro, V_act)
        result = GeneralizedFloodRoutingEngine.run(
            dam_config=cfg,
            dataset_paths={"dem": str(DEM_PATH), "river": str(RIVER_PATH),
                           "output_dir": str(OUT_SIM_DIR / f"sensitivity_dt_{int(dt)}s")},
            hydro_records=hydro, V_active_m3=V_act, dt_override=dt, river_name_hint=RIVER_HINT,
        )
        pr = result["prop_result"]
        out.append({
            "dt_sec": dt,
            "peak_discharge_m3s": mass["peak_discharge_m3s"],
            "time_to_peak_min": mass["time_to_peak_min"],
            "released_volume_mcm": mass["released_volume_mcm"],
            "mass_balance_error_pct": mass["mass_balance_error_pct"],
            "maximum_depth_m": pr["peak_depth_m"],
            "maximum_velocity_ms": pr["peak_velocity_ms"],
            "inundated_area_sqkm": pr["inundated_area_sqkm"],
        })
        print(f"  dt={dt:.0f}s: Q_peak={mass['peak_discharge_m3s']:.1f} m3/s, "
              f"area={pr['inundated_area_sqkm']:.2f} km2, max_depth={pr['peak_depth_m']:.2f} m")
    with open(OUT_SIM_DIR / "sensitivity_results.json", "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    return out


def run_reproducibility(dam_config):
    print("\n[STAGE G] Reproducibility check (two cold-start runs)...")

    def _run(label):
        cfg = copy.deepcopy(dam_config)
        result = GeneralizedFloodRoutingEngine.run(
            dam_config=cfg,
            dataset_paths={"dem": str(DEM_PATH), "river": str(RIVER_PATH),
                           "output_dir": str(OUT_SIM_DIR / f"repro_{label}")},
            river_name_hint=RIVER_HINT,
        )
        return {
            "inundated_area_sqkm": result["prop_result"]["inundated_area_sqkm"],
            "peak_depth_m": result["prop_result"]["peak_depth_m"],
            "peak_velocity_ms": result["prop_result"]["peak_velocity_ms"],
            "inundation_mask_md5": hashlib.md5(result["inundation_mask"].tobytes()).hexdigest(),
        }

    r1, r2 = _run("run1"), _run("run2")
    match = r1["inundation_mask_md5"] == r2["inundation_mask_md5"]
    print(f"  Mask reproducibility: {'BIT-EXACT MATCH' if match else 'MISMATCH'}")
    repro = {"run1": r1, "run2": r2, "mask_bit_exact": match,
             "area_diff_km2": round(abs(r1["inundated_area_sqkm"] - r2["inundated_area_sqkm"]), 6),
             "depth_diff_m": round(abs(r1["peak_depth_m"] - r2["peak_depth_m"]), 6)}
    with open(OUT_SIM_DIR / "reproducibility_results.json", "w", encoding="utf-8") as f:
        json.dump(repro, f, indent=2)
    return repro


def main():
    print("=" * 70)
    print("TEHRI DAM BREAK SIMULATION (GeneralizedFloodRoutingEngine)")
    print("=" * 70)

    assert DEM_PATH.exists(), f"Missing DEM: {DEM_PATH}"
    assert RIVER_PATH.exists(), f"Missing river: {RIVER_PATH}"

    dam_config, sc = load_scenario()

    print("\n[STAGE B-D] Baseline simulation (dt=60s)...")
    result = GeneralizedFloodRoutingEngine.run(
        dam_config=dam_config,
        dataset_paths={"dem": str(DEM_PATH), "river": str(RIVER_PATH),
                       "output_dir": str(OUT_SIM_DIR)},
        river_name_hint=RIVER_HINT,
    )
    mass = result["mass_result"]
    pr = result["prop_result"]

    sens = run_sensitivity(dam_config)
    repro = run_reproducibility(dam_config)

    manifest = {
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "project": "tehri",
        "scenario_id": result["scenario_id"],
        "solver": result["solver"],
        "sph_status": result["sph_status"],
        "delft3d_status": result["delft3d_status"],
        "dam_config": {k: v for k, v in dam_config.items()
                       if k not in {"active_breach_volume_m3", "surface_area_m2"}},
        "mass_conservation": mass,
        "hydraulic_summary": {
            "peak_depth_m": pr["peak_depth_m"],
            "peak_velocity_ms": pr["peak_velocity_ms"],
            "inundated_area_sqkm": pr["inundated_area_sqkm"],
            "inundated_cells": pr["inundated_cell_count"],
            "river_stations": result["n_stations"],
            "reach_km": result["reach_km"],
            "upstream_elev_m": result["upstream_elev_m"],
            "downstream_elev_m": result["downstream_elev_m"],
            "mean_slope_m_per_km": result["mean_slope_m_per_km"],
            "runtime_sec": result["runtime_sec"],
        },
        "gis_files": result["gis_files"],
        "sensitivity": sens,
        "reproducibility": repro,
        "inputs": {"dem": str(DEM_PATH), "river": str(RIVER_PATH), "scenario": str(SCENARIO_PATH)},
    }
    with open(OUT_SIM_DIR / "simulation_manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, default=str)

    print("\n" + "=" * 70)
    print("TEHRI SIMULATION SUMMARY")
    print("=" * 70)
    print(f"Solver:            {result['solver']}")
    print(f"Runtime:           {result['runtime_sec']:.2f} s")
    print(f"River stations:    {result['n_stations']}  reach={result['reach_km']:.2f} km")
    print(f"Upstream/Downstream elev: {result['upstream_elev_m']:.1f} / {result['downstream_elev_m']:.1f} m MSL")
    print(f"Mean slope:        {result['mean_slope_m_per_km']:.3f} m/km")
    print(f"Peak discharge:    {mass['peak_discharge_m3s']:,.1f} m3/s at T+{mass['time_to_peak_min']:.1f} min")
    print(f"Released volume:   {mass['released_volume_mcm']:.4f} MCM")
    print(f"Mass balance err:  {mass['mass_balance_error_pct']:.8f}%")
    print(f"Peak depth:        {pr['peak_depth_m']:.2f} m")
    print(f"Peak velocity:     {pr['peak_velocity_ms']:.2f} m/s")
    print(f"Inundated area:    {pr['inundated_area_sqkm']:.2f} km2")
    print(f"Reproducibility:   {'BIT-EXACT' if repro['mask_bit_exact'] else 'MISMATCH'}")
    print(f"GIS files: {json.dumps(result['gis_files'], indent=2, default=str)}")
    print("=" * 70)


if __name__ == "__main__":
    main()
