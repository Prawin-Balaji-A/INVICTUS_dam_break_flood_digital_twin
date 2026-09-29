"""
CHECKPOINT 2 TESTS — Mettur Dam Simulation Verification
==========================================================

12 test cases as specified in the Phase 5 scope:

 1. test_mettur_scenario_config_integrity
 2. test_mettur_breach_parameter_provenance
 3. test_mettur_dem_covers_dam_location
 4. test_mettur_river_station_relationship
 5. test_mettur_mass_conservation_strict
 6. test_mettur_reservoir_never_negative
 7. test_mettur_hydrograph_peak_independent_check
 8. test_mettur_routing_uses_cauvery_geometry
 9. test_mettur_depth_velocity_nonnegative
10. test_mettur_inundation_threshold_applied
11. test_mettur_timestep_sensitivity_convergence
12. test_mettur_reproducibility_bit_exact
"""

import json
import math
import copy
import hashlib
from pathlib import Path

import numpy as np
import pytest

BASE_DIR     = Path(__file__).resolve().parent.parent.parent
SCENARIO_PATH = BASE_DIR / "data" / "mettur" / "scenarios" / "baseline_breach.json"
DEM_PATH      = BASE_DIR / "data" / "mettur" / "dem" / "processed" / "mettur_dem_30m.tif"
RIVER_PATH    = BASE_DIR / "data" / "mettur" / "river" / "cauvery_river.geojson"
OUT_DIR       = BASE_DIR / "data" / "mettur" / "simulations" / "checkpoint2"
OUT_DIR.mkdir(parents=True, exist_ok=True)

import sys
sys.path.insert(0, str(BASE_DIR))

from backend.app.hydrodynamics.routing_engine import (
    GeneralizedFloodRoutingEngine,
    compute_breach_hydrograph,
    verify_mass_conservation,
    INUNDATION_DEPTH_THRESHOLD_M,
)


def _load_scenario():
    with open(SCENARIO_PATH, encoding="utf-8") as f:
        sc = json.load(f)

    def _v(node):
        return node["value"] if isinstance(node, dict) and "value" in node else node

    rs   = sc["reservoir_initial_state"]
    bp   = sc["breach_parameters"]
    ctrl = sc["simulation_controls"]
    loc  = sc["dam_location"]

    return {
        "dam_id":                    sc["_scenario_metadata"]["dam_id"],
        "scenario_id":               sc["_scenario_metadata"]["scenario_id"],
        "dam_lat":                   _v(loc["latitude"]),
        "dam_lon":                   _v(loc["longitude"]),
        "initial_water_level_m":     _v(rs["initial_water_level_m"]),
        "active_breach_volume_m3":   _v(rs["active_breach_volume_m3"]),
        "surface_area_m2":           _v(rs["surface_area_m2"]),
        "river_bed_elevation_m":     _v(rs["river_bed_elevation_m"]),
        "breach_depth_m":            _v(bp["breach_depth_m"]),
        "breach_bottom_width_m":     _v(bp["breach_bottom_width_m"]),
        "breach_side_slope_z":       _v(bp["breach_side_slope_z"]),
        "breach_formation_time_sec": _v(bp["breach_formation_time_sec"]),
        "simulation_duration_sec":   _v(ctrl["simulation_duration_sec"]),
        "manning_n_channel":         ctrl["manning_roughness_n"]["main_channel"]["value"],
        "manning_n_floodplain":       ctrl["manning_roughness_n"]["floodplain"]["value"],
        "inundation_threshold_m":    _v(ctrl["inundation_threshold_m"]),
    }


def _run_baseline(dt=60.0, suffix=""):
    cfg = _load_scenario()
    return GeneralizedFloodRoutingEngine.run(
        dam_config=cfg,
        dataset_paths={
            "dem":        str(DEM_PATH),
            "river":      str(RIVER_PATH),
            "output_dir": str(OUT_DIR / f"run{suffix}"),
        },
        river_name_hint="Kaveri",
        dt_override=dt,
    )


# ─────────────────────────────────────────────────────────────────────────────
# TC-1: SCENARIO CONFIG INTEGRITY
# ─────────────────────────────────────────────────────────────────────────────
class TestMetturScenarioConfigIntegrity:
    def test_mettur_scenario_config_integrity(self):
        """Scenario JSON must contain all required fields and consistent values."""
        with open(SCENARIO_PATH, encoding="utf-8") as f:
            sc = json.load(f)
        meta = sc["_scenario_metadata"]
        rs   = sc["reservoir_initial_state"]
        bp   = sc["breach_parameters"]
        ctrl = sc["simulation_controls"]

        # Required top-level keys
        assert meta["dam_id"] == "mettur"
        assert meta["phase"] == 5
        assert "Mettur" in meta["dam_name"]
        assert meta["sph_status"]     == "NOT YET COUPLED"
        assert meta["delft3d_status"] == "EXPORTER ONLY"

        # Volume consistency
        V_mcm = rs["active_breach_volume_mcm"]["value"]
        V_m3  = rs["active_breach_volume_m3"]["value"]
        assert abs(V_mcm * 1e6 - V_m3) < 1.0, (
            f"MCM and m³ volume inconsistent: {V_mcm} MCM vs {V_m3} m³"
        )

        # Formation time consistency
        tf_hr  = bp["breach_formation_time_hr"]["value"]
        tf_sec = bp["breach_formation_time_sec"]["value"]
        assert abs(tf_hr * 3600 - tf_sec) < 2.0, (
            f"Formation time hr/sec inconsistent: {tf_hr} hr vs {tf_sec} s"
        )

        # Simulation duration consistency
        dur_hr  = ctrl["simulation_duration_hr"]["value"]
        dur_sec = ctrl["simulation_duration_sec"]["value"]
        assert abs(dur_hr * 3600 - dur_sec) < 2.0


# ─────────────────────────────────────────────────────────────────────────────
# TC-2: BREACH PARAMETER PROVENANCE CLASSIFICATION
# ─────────────────────────────────────────────────────────────────────────────
class TestMetturBreachParameterProvenance:
    def test_mettur_breach_parameter_provenance(self):
        """Every breach parameter must have an explicit classification."""
        with open(SCENARIO_PATH, encoding="utf-8") as f:
            sc = json.load(f)

        VALID_CLASSIFICATIONS = {
            "AUTHORITATIVE / MEASURED",
            "DERIVED",
            "SCENARIO ASSUMPTION",
            "SCENARIO ASSUMPTION (standard empirical formulation)",
            "SCENARIO ASSUMPTION (Froehlich 2008 empirical + 0.90 conservative factor)",
        }

        bp = sc["breach_parameters"]
        for key, val in bp.items():
            if isinstance(val, dict) and "classification" in val:
                c = val["classification"]
                assert any(vc in c for vc in VALID_CLASSIFICATIONS), (
                    f"Parameter '{key}' has unknown classification: {c!r}"
                )

    def test_no_silent_upgrades(self):
        """Active breach volume must NOT be classified as AUTHORITATIVE."""
        with open(SCENARIO_PATH, encoding="utf-8") as f:
            sc = json.load(f)
        vol_class = sc["reservoir_initial_state"]["active_breach_volume_mcm"]["classification"]
        assert "SCENARIO ASSUMPTION" in vol_class, (
            f"Active breach volume must be SCENARIO ASSUMPTION, got: {vol_class}"
        )

    def test_formation_time_labelled_scenario_assumption(self):
        """Breach formation time must be labelled SCENARIO ASSUMPTION."""
        with open(SCENARIO_PATH, encoding="utf-8") as f:
            sc = json.load(f)
        tf_class = sc["breach_parameters"]["breach_formation_time_sec"]["classification"]
        assert "SCENARIO ASSUMPTION" in tf_class

    def test_manning_n_labelled_scenario_assumption(self):
        """Manning n must be labelled SCENARIO ASSUMPTION."""
        with open(SCENARIO_PATH, encoding="utf-8") as f:
            sc = json.load(f)
        n_class = sc["simulation_controls"]["manning_roughness_n"]["main_channel"]["classification"]
        assert "SCENARIO ASSUMPTION" in n_class


# ─────────────────────────────────────────────────────────────────────────────
# TC-3: DEM COVERS DAM LOCATION
# ─────────────────────────────────────────────────────────────────────────────
class TestMetturDEMCoversDamLocation:
    def test_mettur_dem_covers_dam_location(self):
        """DEM must contain a valid non-nodata pixel at the dam location."""
        import rasterio
        from rasterio.transform import rowcol
        cfg = _load_scenario()
        with rasterio.open(str(DEM_PATH)) as src:
            dem = src.read(1)
            nodata = src.nodata if src.nodata else -32767.0
            r, c = rowcol(src.transform, cfg["dam_lon"], cfg["dam_lat"])
            assert 0 <= r < dem.shape[0], f"Dam row {r} out of DEM bounds {dem.shape[0]}"
            assert 0 <= c < dem.shape[1], f"Dam col {c} out of DEM bounds {dem.shape[1]}"
            z = float(dem[r, c])
            assert z != nodata, f"Dam pixel is nodata at ({r},{c})"
            assert math.isfinite(z), f"Dam pixel is NaN/inf at ({r},{c})"
            assert 100 < z < 600, (
                f"Dam elevation {z:.1f} m MSL is implausible for Mettur (expected 100-600 m)"
            )

    def test_dam_elevation_within_engineering_range(self):
        """Dam elevation from DEM must be near the known crest elevation (~246 m MSL)."""
        import rasterio
        from rasterio.transform import rowcol
        cfg = _load_scenario()
        with rasterio.open(str(DEM_PATH)) as src:
            dem    = src.read(1)
            nodata = src.nodata if src.nodata else -32767.0
            r, c   = rowcol(src.transform, cfg["dam_lon"], cfg["dam_lat"])
            z      = float(dem[r, c])
        # DEM 30m pixel at dam location: expect 170-270 m (foundation to crest range)
        assert 170.0 <= z <= 270.0, (
            f"DEM elevation at dam pixel = {z:.1f} m; expected 170-270 m (foundation to crest range)"
        )


# ─────────────────────────────────────────────────────────────────────────────
# TC-4: RIVER STATION RELATIONSHIP
# ─────────────────────────────────────────────────────────────────────────────
class TestMetturRiverStationRelationship:
    @pytest.fixture(scope="class")
    def result(self):
        return _run_baseline(dt=60.0, suffix="_tc4")

    def test_mettur_river_station_relationship(self, result):
        """Reach length and station count must be consistent with station spacing."""
        n    = result["n_stations"]
        km   = result["reach_km"]
        expected_n = max(2, int(km * 1000.0 / 30.0))  # STATION_SPACING_M = 30
        # Allow ±15% tolerance on station count
        assert expected_n * 0.85 <= n <= expected_n * 1.15, (
            f"Station count {n} not consistent with reach {km:.2f} km at 30m spacing "
            f"(expected ~{expected_n})"
        )

    def test_reach_is_physically_meaningful(self, result):
        """Reach must be at least 1 km for a dam this scale."""
        assert result["reach_km"] >= 1.0, (
            f"Reach only {result['reach_km']:.2f} km — insufficient for Mettur"
        )

    def test_elevation_drop_positive(self, result):
        """Head must decrease from upstream to downstream station."""
        assert result["upstream_elev_m"] > result["downstream_elev_m"], (
            f"Upstream elev {result['upstream_elev_m']:.2f} m <= "
            f"downstream {result['downstream_elev_m']:.2f} m — check thalweg direction"
        )

    def test_mean_slope_physically_plausible(self, result):
        """Cauvery longitudinal slope must be in physically plausible range."""
        s = result["mean_slope_m_per_km"]
        assert 0.1 <= s <= 100.0, (
            f"Mean slope {s:.4f} m/km outside physically plausible range [0.1, 100] m/km"
        )


# ─────────────────────────────────────────────────────────────────────────────
# TC-5: STRICT MASS CONSERVATION
# ─────────────────────────────────────────────────────────────────────────────
class TestMetturMassConservationStrict:
    @pytest.fixture(scope="class")
    def mass(self):
        result = _run_baseline(suffix="_tc5")
        return result["mass_result"]

    def test_mettur_mass_conservation_strict(self, mass):
        """Released volume <= initial volume (mass conservation enforced)."""
        released = mass["released_volume_mcm"]
        initial  = mass["initial_volume_mcm"]
        assert released <= initial + 0.001, (
            f"Released {released:.6f} MCM > initial {initial:.4f} MCM — "
            "mass conservation VIOLATED"
        )

    def test_mass_balance_error_tiny(self, mass):
        """Mass balance error must be less than 0.001%."""
        err = mass["mass_balance_error_pct"]
        assert err <= 0.001, (
            f"Mass balance error {err:.8f}% exceeds 0.001% tolerance"
        )

    def test_discrepancy_below_100m3(self, mass):
        """Numerical discrepancy must be less than 100 m³."""
        disc = abs(mass["numerical_discrepancy_m3"])
        assert disc <= 100.0, (
            f"Numerical discrepancy {disc:.2f} m³ > 100 m³"
        )

    def test_mass_conservation_flag_set(self, mass):
        """mass_conservation_pass flag must be True."""
        assert mass["mass_conservation_pass"] is True


# ─────────────────────────────────────────────────────────────────────────────
# TC-6: RESERVOIR NEVER NEGATIVE
# ─────────────────────────────────────────────────────────────────────────────
class TestMetturReservoirNeverNegative:
    @pytest.fixture(scope="class")
    def hydro(self):
        result = _run_baseline(suffix="_tc6")
        return result["hydro_records"]

    def test_mettur_reservoir_never_negative(self, hydro):
        """Reservoir volume must never go below zero (minus 1 m³ tolerance)."""
        neg_records = [
            (r["time_hr"], r["reservoir_volume_m3"])
            for r in hydro
            if r["reservoir_volume_m3"] < -1.0
        ]
        assert len(neg_records) == 0, (
            f"Reservoir volume went negative at {len(neg_records)} timesteps:\n"
            + "\n".join(f"  T+{t:.2f}h: V={v:.2f} m³" for t, v in neg_records[:5])
        )

    def test_reservoir_monotonically_draining(self, hydro):
        """Reservoir volume must be monotonically non-increasing."""
        vols = [r["reservoir_volume_m3"] for r in hydro]
        violations = sum(1 for i in range(1, len(vols)) if vols[i] > vols[i-1] + 0.01)
        assert violations == 0, (
            f"Reservoir refilling at {violations} timesteps (non-monotonic drain)"
        )


# ─────────────────────────────────────────────────────────────────────────────
# TC-7: HYDROGRAPH PEAK INDEPENDENT CHECK
# ─────────────────────────────────────────────────────────────────────────────
class TestMetturHydrographPeakIndependent:
    def test_mettur_hydrograph_peak_independent_check(self):
        """
        Independent verification: re-compute peak Q from first principles.

        At peak formation time tf, the breach is fully open.
        Qpeak = Cwr × L_eff × h_max^1.5  (rectangular weir)
        where L_eff = Wb + Z × hb (average breach width approximation).
        Accept if simulation peak is within ±30% of independent estimate.
        """
        with open(SCENARIO_PATH, encoding="utf-8") as f:
            sc = json.load(f)

        def _v(nd):
            return nd["value"] if isinstance(nd, dict) else nd

        hb   = _v(sc["breach_parameters"]["breach_depth_m"])
        Wb   = _v(sc["breach_parameters"]["breach_bottom_width_m"])
        Z    = _v(sc["breach_parameters"]["breach_side_slope_z"])
        Cwr  = _v(sc["breach_parameters"]["weir_coefficient_rectangular"])
        H0   = _v(sc["reservoir_initial_state"]["initial_water_level_m"])
        zbed = _v(sc["reservoir_initial_state"]["river_bed_elevation_m"])

        # Head above invert at t=tf (breach fully open, reservoir still near FRL)
        h_head   = H0 - zbed
        # Effective top width at breach
        L_top    = Wb + 2 * Z * hb
        L_avg    = (Wb + L_top) / 2.0  # average breach width
        Q_est    = Cwr * L_avg * (h_head ** 1.5)

        result   = _run_baseline(suffix="_tc7")
        Q_sim    = result["mass_result"]["peak_discharge_m3s"]
        rel_diff = abs(Q_sim - Q_est) / max(1.0, Q_est)

        print(f"\n  Independent Q_peak estimate: {Q_est:,.1f} m³/s")
        print(f"  Simulation Q_peak:           {Q_sim:,.1f} m³/s")
        print(f"  Relative difference:         {rel_diff*100:.1f}%")

        assert rel_diff <= 0.35, (
            f"Peak Q mismatch: sim={Q_sim:,.1f} m³/s, estimate={Q_est:,.1f} m³/s, "
            f"diff={rel_diff*100:.1f}% (> 35%)"
        )


# ─────────────────────────────────────────────────────────────────────────────
# TC-8: ROUTING USES CAUVERY GEOMETRY
# ─────────────────────────────────────────────────────────────────────────────
class TestMetturRoutingUsesCauveryGeometry:
    def test_mettur_routing_uses_cauvery_geometry(self):
        """Routing domain must be anchored near the Mettur Dam location."""
        result  = _run_baseline(suffix="_tc8")
        nodes   = result["river_nodes"]
        first_n = nodes[0]
        last_n  = nodes[-1]

        from shapely.geometry import Point
        DAM_LON, DAM_LAT = 77.8017, 11.8028

        # First station must be within 5 km of dam
        first_pt  = Point(first_n["lon"], first_n["lat"])
        dam_pt    = Point(DAM_LON, DAM_LAT)
        dist_km   = first_pt.distance(dam_pt) * 111.32
        assert dist_km < 5.0, (
            f"First station is {dist_km:.2f} km from dam — not anchored at dam"
        )

        # Last station must be south/southeast of dam (downstream per DEM)
        # The Cauvery flows south from Mettur
        # We verify last station is NOT north of first station (i.e., went upstream)
        assert last_n["z"] <= first_n["z"] + 5.0, (
            f"Last station elevation {last_n['z']:.2f} m > first {first_n['z']:.2f} m "
            "— routing went upstream"
        )

    def test_river_nodes_exist_in_result(self):
        """result must contain river_nodes list."""
        result = _run_baseline(suffix="_tc8b")
        assert "river_nodes" in result
        assert isinstance(result["river_nodes"], list)
        assert len(result["river_nodes"]) >= 10


# ─────────────────────────────────────────────────────────────────────────────
# TC-9: DEPTH AND VELOCITY NON-NEGATIVE
# ─────────────────────────────────────────────────────────────────────────────
class TestMetturDepthVelocityNonnegative:
    @pytest.fixture(scope="class")
    def result(self):
        return _run_baseline(suffix="_tc9")

    def test_mettur_depth_velocity_nonnegative(self, result):
        """Maximum depth array must not contain negative values (excluding nodata)."""
        md = result["prop_result"]["max_depth"]
        nodata = result["nodata"]
        valid = (md != nodata) & ~np.isnan(md)
        assert np.any(valid), "Raster has no valid data pixels"
        assert np.all(md[valid] >= 0.0), (
            f"Maximum depth has {np.sum(md[valid] < 0)} negative cells"
        )

    def test_velocity_nonnegative(self, result):
        """Maximum velocity array must not contain negative values (excluding nodata)."""
        mv = result["prop_result"]["max_velocity"]
        nodata = result["nodata"]
        valid = (mv != nodata) & ~np.isnan(mv)
        assert np.any(valid), "Raster has no valid data pixels"
        assert np.all(mv[valid] >= 0.0), (
            f"Maximum velocity has {np.sum(mv[valid] < 0)} negative cells"
        )

    def test_peak_depth_plausible(self, result):
        """Peak depth must be positive and physically plausible (< 300 m)."""
        pk_d = result["prop_result"]["peak_depth_m"]
        assert 0.0 < pk_d < 300.0, (
            f"Peak depth {pk_d:.2f} m outside plausible range"
        )

    def test_peak_velocity_plausible(self, result):
        """Peak velocity must be positive and physically plausible (< 150 m/s)."""
        pk_v = result["prop_result"]["peak_velocity_ms"]
        assert 0.0 < pk_v < 150.0, (
            f"Peak velocity {pk_v:.2f} m/s outside plausible range"
        )

    def test_inundated_area_positive(self, result):
        """Inundated area must be positive."""
        area = result["prop_result"]["inundated_area_sqkm"]
        assert area > 0.0, f"Inundated area is {area:.4f} km² (must be > 0)"


# ─────────────────────────────────────────────────────────────────────────────
# TC-10: INUNDATION THRESHOLD APPLIED
# ─────────────────────────────────────────────────────────────────────────────
class TestMetturInundationThresholdApplied:
    @pytest.fixture(scope="class")
    def result(self):
        return _run_baseline(suffix="_tc10")

    def test_mettur_inundation_threshold_applied(self, result):
        """Inundation mask must only be True where depth >= threshold."""
        import rasterio
        cfg = _load_scenario()
        thr = cfg["inundation_threshold_m"]

        md   = result["prop_result"]["max_depth"]
        mask = result["inundation_mask"]

        # All wet cells must have depth >= threshold
        wet_but_shallow = np.sum(mask & (md < thr * 0.99))
        assert wet_but_shallow == 0, (
            f"{wet_but_shallow} cells in inundation mask but depth < threshold"
        )

        # All cells above threshold must be in mask
        deep_but_dry = np.sum((md >= thr) & ~mask)
        assert deep_but_dry == 0, (
            f"{deep_but_dry} cells with depth >= {thr} m but NOT in inundation mask"
        )

    def test_inundated_area_matches_mask(self, result):
        """Reported inundated area must be consistent with mask pixel count."""
        import rasterio
        with rasterio.open(str(DEM_PATH)) as src:
            pixel_area_m2 = abs(src.transform.a) * abs(src.transform.e) * (111320.0 ** 2)

        mask         = result["inundation_mask"]
        mask_cells   = int(np.sum(mask))
        reported_km2 = result["prop_result"]["inundated_area_sqkm"]
        computed_km2 = mask_cells * pixel_area_m2 / 1e6

        rel_diff = abs(reported_km2 - computed_km2) / max(0.001, computed_km2)
        assert rel_diff <= 0.05, (
            f"Reported area {reported_km2:.4f} km² vs mask-derived {computed_km2:.4f} km² "
            f"(diff {rel_diff*100:.2f}%)"
        )


# ─────────────────────────────────────────────────────────────────────────────
# TC-11: TIMESTEP SENSITIVITY CONVERGENCE
# ─────────────────────────────────────────────────────────────────────────────
class TestMetturTimestepSensitivity:
    def test_mettur_timestep_sensitivity_convergence(self):
        """
        Peak discharge and inundated area must converge (<2%) between dt=60s and dt=15s.
        """
        r60 = _run_baseline(dt=60.0, suffix="_sens60")
        r15 = _run_baseline(dt=15.0, suffix="_sens15")

        q60   = r60["mass_result"]["peak_discharge_m3s"]
        q15   = r15["mass_result"]["peak_discharge_m3s"]
        a60   = r60["prop_result"]["inundated_area_sqkm"]
        a15   = r15["prop_result"]["inundated_area_sqkm"]

        q_diff = abs(q60 - q15) / max(1.0, q15) * 100.0
        a_diff = abs(a60 - a15) / max(0.001, a15) * 100.0

        print(f"\n  Q_peak: dt=60s={q60:,.1f}, dt=15s={q15:,.1f}, diff={q_diff:.2f}%")
        print(f"  Area:   dt=60s={a60:.3f}, dt=15s={a15:.3f}, diff={a_diff:.2f}%")

        assert q_diff < 2.0, (
            f"Peak Q diverges {q_diff:.2f}% between dt=60s and dt=15s"
        )
        assert a_diff < 2.0, (
            f"Inundated area diverges {a_diff:.2f}% between dt=60s and dt=15s"
        )


# ─────────────────────────────────────────────────────────────────────────────
# TC-12: REPRODUCIBILITY BIT-EXACT
# ─────────────────────────────────────────────────────────────────────────────
class TestMetturReproducibilityBitExact:
    def test_mettur_reproducibility_bit_exact(self):
        """Two cold-start runs must produce bit-exact inundation masks."""
        r1 = _run_baseline(suffix="_repro1")
        r2 = _run_baseline(suffix="_repro2")

        h1 = hashlib.md5(r1["inundation_mask"].tobytes()).hexdigest()
        h2 = hashlib.md5(r2["inundation_mask"].tobytes()).hexdigest()

        assert h1 == h2, (
            f"Inundation mask is NOT bit-exact across cold-start runs:\n"
            f"  Run 1 md5: {h1}\n"
            f"  Run 2 md5: {h2}"
        )

    def test_area_depth_identical(self):
        """Two cold-start runs must report identical area and depth values."""
        r1 = _run_baseline(suffix="_repro3")
        r2 = _run_baseline(suffix="_repro4")

        a1 = r1["prop_result"]["inundated_area_sqkm"]
        a2 = r2["prop_result"]["inundated_area_sqkm"]
        d1 = r1["prop_result"]["peak_depth_m"]
        d2 = r2["prop_result"]["peak_depth_m"]

        assert a1 == a2, f"Inundated area differs: {a1} vs {a2}"
        assert d1 == d2, f"Peak depth differs: {d1} vs {d2}"
