"""
CHECKPOINT 1 TESTS — Generalized Engine Verification

Must pass before Mettur simulation is permitted to run.

Tests:
  test_generalized_engine_imports()
  test_engine_contains_no_idukki_specific_routing()
  test_mettur_river_geometry_is_loaded()
  test_mettur_river_has_valid_downstream_order()
  test_mettur_station_chainage_is_monotonic()
  test_mettur_downstream_elevation_trend()
"""

import os
import re
import math
import json
import types
import inspect
from pathlib import Path

import numpy as np
import pytest

# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent.parent
ROUTING_ENGINE_PATH = (
    BASE_DIR / "backend" / "app" / "hydrodynamics" / "routing_engine.py"
)
METTUR_DEM_PATH    = BASE_DIR / "data" / "mettur" / "dem" / "processed" / "mettur_dem_30m.tif"
METTUR_RIVER_PATH  = BASE_DIR / "data" / "mettur" / "river" / "cauvery_river.geojson"
METTUR_SCENARIO    = BASE_DIR / "data" / "mettur" / "scenarios" / "baseline_breach.json"

# Strings that MUST NOT control solver logic (allowed only in config/test/docs)
IDUKKI_TOKENS = [
    r"\bidukki\b", r"\bperiyar\b", r"\bidukki_dem\b",
    r"76\.97", r"9\.85", r"76\.75", r"9\.75",
    r"idukki_basin", r"periyar_river",
]
# Lines that are allowed to contain Idukki tokens (test fixtures, docstrings, comments)
ALLOWED_CONTEXTS = {"test", "fixture", "config", "#", '"""', "'''", "doc", "example", "NOTE", "NOTE:"}


# ===========================================================================
# TC-1: ENGINE IMPORTS
# ===========================================================================
class TestGeneralizedEngineImports:
    def test_generalized_engine_imports(self):
        """GeneralizedFloodRoutingEngine must be importable without errors."""
        from backend.app.hydrodynamics.routing_engine import GeneralizedFloodRoutingEngine
        assert GeneralizedFloodRoutingEngine is not None

    def test_all_expected_callables_present(self):
        """All major functions must be importable from the package."""
        from backend.app.hydrodynamics import (
            GeneralizedFloodRoutingEngine,
            compute_breach_hydrograph,
            verify_mass_conservation,
            extract_downstream_reach,
            sample_river_stations,
            propagate_flood_wave,
            derive_inundation_mask,
            vectorize_flood_extent,
            export_gis_products,
        )
        for fn in [
            GeneralizedFloodRoutingEngine,
            compute_breach_hydrograph,
            verify_mass_conservation,
            extract_downstream_reach,
            sample_river_stations,
            propagate_flood_wave,
            derive_inundation_mask,
            vectorize_flood_extent,
            export_gis_products,
        ]:
            assert callable(fn) or isinstance(fn, type), f"{fn} is not callable"

    def test_engine_has_solver_classification(self):
        """Engine must declare its solver classification string."""
        from backend.app.hydrodynamics.routing_engine import GeneralizedFloodRoutingEngine
        assert "Manning" in GeneralizedFloodRoutingEngine.SOLVER_NAME
        assert "kinematic" in GeneralizedFloodRoutingEngine.SOLVER_NAME
        assert GeneralizedFloodRoutingEngine.SPH_STATUS == "NOT YET COUPLED"
        assert GeneralizedFloodRoutingEngine.DELFT3D_STATUS == "EXPORTER ONLY"

    def test_routing_engine_file_exists(self):
        """routing_engine.py must exist at the specified path."""
        assert ROUTING_ENGINE_PATH.exists(), (
            f"routing_engine.py not found at {ROUTING_ENGINE_PATH}"
        )


# ===========================================================================
# TC-2: NO IDUKKI-SPECIFIC ROUTING LOGIC
# ===========================================================================
class TestEngineContainsNoIdukkiSpecificRouting:
    """
    Scan the routing_engine.py source code for any Idukki/Periyar-specific
    tokens that CONTROL solver behavior (outside test fixtures or comments).
    """

    @pytest.fixture(scope="class")
    def engine_source(self):
        return ROUTING_ENGINE_PATH.read_text(encoding="utf-8")

    def _is_allowed_line(self, line: str) -> bool:
        stripped = line.strip()
        for ctx in ALLOWED_CONTEXTS:
            if stripped.startswith(ctx):
                return True
        return False

    def test_engine_contains_no_idukki_specific_routing(self, engine_source):
        """
        routing_engine.py must not contain Idukki-specific identifiers
        outside of comments, docstrings, or test fixtures.
        """
        violations = []
        for lineno, line in enumerate(engine_source.splitlines(), 1):
            if self._is_allowed_line(line):
                continue
            for pat in IDUKKI_TOKENS:
                if re.search(pat, line, re.IGNORECASE):
                    violations.append((lineno, line.strip()))
        assert violations == [], (
            f"Idukki-specific tokens found in routing_engine.py solver logic:\n"
            + "\n".join(f"  Line {ln}: {txt}" for ln, txt in violations)
        )

    def test_engine_has_no_dam_name_conditional(self, engine_source):
        """No if/elif comparing dam name strings to control solver routing."""
        bad_patterns = [
            r'if\s+dam\s*==\s*["\']idukki["\']',
            r'if\s+dam_id\s*==\s*["\']idukki["\']',
            r'elif\s+dam\s*==\s*["\']mettur["\']',
        ]
        for pat in bad_patterns:
            assert not re.search(pat, engine_source, re.IGNORECASE), (
                f"Dam-conditional routing logic found: pattern={pat}"
            )

    def test_engine_has_no_hardcoded_lat_lon(self, engine_source):
        """No hardcoded geographic coordinates in the solver (non-comment lines)."""
        coord_patterns = [
            r'9\.85',  r'9\.75',  r'76\.97', r'76\.75',    # Idukki
            r'10\.08', r'77\.08',                            # Idukki study boundary
        ]
        for pat in coord_patterns:
            for lineno, line in enumerate(engine_source.splitlines(), 1):
                if self._is_allowed_line(line):
                    continue
                if re.search(pat, line):
                    pytest.fail(
                        f"Hardcoded Idukki coordinate found in routing_engine.py line {lineno}: {line.strip()}"
                    )


# ===========================================================================
# TC-3: METTUR RIVER GEOMETRY IS LOADED
# ===========================================================================
class TestMetturRiverGeometryIsLoaded:
    def test_mettur_river_geometry_is_loaded(self):
        """Cauvery river GeoJSON file must exist and contain valid geometries."""
        assert METTUR_RIVER_PATH.exists(), f"River file not found: {METTUR_RIVER_PATH}"
        import geopandas as gpd
        gdf = gpd.read_file(str(METTUR_RIVER_PATH))
        valid = gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty]
        assert len(valid) >= 1, "River GeoJSON contains no valid geometries"

    def test_river_contains_cauvery_features(self):
        """At least one feature must be named Kaveri/Cauvery."""
        import geopandas as gpd
        gdf = gpd.read_file(str(METTUR_RIVER_PATH))
        names = gdf.apply(lambda r: str(r.get("name", "")), axis=1)
        has_kaveri = names.str.lower().str.contains("kaveri|cauvery", na=False).any()
        assert has_kaveri, "No Kaveri/Cauvery named features found in river GeoJSON"

    def test_river_crs_is_wgs84(self):
        """River GeoJSON must be in EPSG:4326 (WGS 84)."""
        import geopandas as gpd
        gdf = gpd.read_file(str(METTUR_RIVER_PATH))
        assert gdf.crs is None or "4326" in str(gdf.crs), (
            f"River CRS is {gdf.crs}, expected EPSG:4326"
        )

    def test_river_is_within_study_domain(self):
        """River bounding box must overlap the Mettur study domain."""
        import geopandas as gpd
        gdf = gpd.read_file(str(METTUR_RIVER_PATH))
        gdf = gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty]
        b = gdf.total_bounds  # [min_lon, min_lat, max_lon, max_lat]
        # Study domain: 11.65-11.92N, 77.65-78.00E
        assert b[0] < 78.00, f"River too far east: min_lon={b[0]}"
        assert b[2] > 77.65, f"River too far west: max_lon={b[2]}"
        assert b[1] < 11.92, f"River too far north: min_lat={b[1]}"
        assert b[3] > 11.65, f"River too far south: max_lat={b[3]}"

    def test_dam_location_within_300m_of_river(self):
        """Dam location must be within 300 m of a river feature."""
        import geopandas as gpd
        from shapely.geometry import Point
        DAM_LAT, DAM_LON = 11.8028, 77.8017
        gdf = gpd.read_file(str(METTUR_RIVER_PATH))
        gdf = gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty]
        dam_pt = Point(DAM_LON, DAM_LAT)
        from shapely.ops import unary_union
        all_geoms = unary_union(gdf.geometry.tolist())
        dist_deg = all_geoms.distance(dam_pt)
        dist_km  = dist_deg * 111.32
        assert dist_km < 0.3, (
            f"Dam is {dist_km:.3f} km from nearest river feature (expected < 0.3 km)"
        )


# ===========================================================================
# TC-4: VALID DOWNSTREAM ORDER (thalweg slope test)
# ===========================================================================
class TestMetturRiverHasValidDownstreamOrder:
    @pytest.fixture(scope="class")
    def downstream_reach_and_dem(self):
        """Extract downstream reach using the generalized engine."""
        import rasterio
        from backend.app.hydrodynamics.routing_engine import extract_downstream_reach

        with rasterio.open(str(METTUR_DEM_PATH)) as src:
            dem_data = src.read(1).astype(float)
            transform = src.transform
            bounds = src.bounds
            nodata = src.nodata if src.nodata is not None else -32767.0

        DAM_COORD = (11.8028, 77.8017)
        reach = extract_downstream_reach(
            str(METTUR_RIVER_PATH), bounds, DAM_COORD,
            dem_data, transform, nodata,
            main_stem_name_hint="Kaveri"
        )
        return reach, dem_data, transform, nodata

    def test_mettur_river_has_valid_downstream_order(self, downstream_reach_and_dem):
        """Downstream reach must be a non-empty LineString with positive length."""
        reach, *_ = downstream_reach_and_dem
        assert not reach.is_empty, "Downstream reach is empty"
        assert reach.geom_type in ("LineString", "MultiLineString"), (
            f"Expected LineString, got {reach.geom_type}"
        )
        reach_km = reach.length * 111.32
        assert reach_km > 0.5, (
            f"Downstream reach is only {reach_km:.3f} km — likely upstream half selected"
        )

    def test_reach_starts_near_dam(self, downstream_reach_and_dem):
        """First coordinate of downstream reach must be near the dam location."""
        from shapely.geometry import Point
        reach, *_ = downstream_reach_and_dem
        first_pt = Point(list(reach.coords)[0])
        dam_pt   = Point(77.8017, 11.8028)
        dist_km  = first_pt.distance(dam_pt) * 111.32
        assert dist_km < 5.0, (
            f"Reach start is {dist_km:.2f} km from dam — not starting at dam"
        )


# ===========================================================================
# TC-5: MONOTONIC CHAINAGE
# ===========================================================================
class TestMetturStationChainageIsMonotonic:
    @pytest.fixture(scope="class")
    def river_nodes(self):
        """Sample stations along the downstream reach."""
        import rasterio
        from backend.app.hydrodynamics.routing_engine import (
            extract_downstream_reach, sample_river_stations
        )

        with rasterio.open(str(METTUR_DEM_PATH)) as src:
            dem_data  = src.read(1).astype(float)
            transform = src.transform
            bounds    = src.bounds
            nodata    = src.nodata if src.nodata is not None else -32767.0

        DAM_COORD = (11.8028, 77.8017)
        reach = extract_downstream_reach(
            str(METTUR_RIVER_PATH), bounds, DAM_COORD,
            dem_data, transform, nodata,
            main_stem_name_hint="Kaveri"
        )
        nodes = sample_river_stations(reach, dem_data, transform, nodata)
        return nodes

    def test_mettur_station_chainage_is_monotonic(self, river_nodes):
        """Chainage s_m must be strictly non-decreasing across all stations."""
        chainages = [nd["s_m"] for nd in river_nodes]
        for i in range(1, len(chainages)):
            assert chainages[i] >= chainages[i - 1], (
                f"Non-monotonic chainage at station {i}: "
                f"{chainages[i-1]:.1f} -> {chainages[i]:.1f}"
            )

    def test_minimum_station_count(self, river_nodes):
        """Must have at least 10 stations."""
        assert len(river_nodes) >= 10, (
            f"Only {len(river_nodes)} stations sampled — need >= 10"
        )

    def test_all_stations_have_valid_elevation(self, river_nodes):
        """All sampled stations must have positive, finite bed elevation."""
        for i, nd in enumerate(river_nodes):
            z = nd["z"]
            assert math.isfinite(z), f"Station {i}: non-finite elevation {z}"
            assert z > 0.0, f"Station {i}: non-positive elevation {z}"
            assert z < 3000.0, f"Station {i}: unreasonably high elevation {z} m"

    def test_all_stations_have_positive_slope(self, river_nodes):
        """Every station slope must be positive (minimum enforced in engine)."""
        for i, nd in enumerate(river_nodes):
            s = nd["slope"]
            assert s is not None, f"Station {i}: slope is None"
            assert s > 0.0, f"Station {i}: slope={s} (must be > 0)"


# ===========================================================================
# TC-6: DOWNSTREAM ELEVATION TREND (physically valid thalweg)
# ===========================================================================
class TestMetturDownstreamElevationTrend:
    @pytest.fixture(scope="class")
    def stations(self, tmp_path_factory):
        """Sample N=20 stations and return them."""
        import rasterio
        from backend.app.hydrodynamics.routing_engine import (
            extract_downstream_reach, sample_river_stations
        )

        with rasterio.open(str(METTUR_DEM_PATH)) as src:
            dem_data  = src.read(1).astype(float)
            transform = src.transform
            bounds    = src.bounds
            nodata    = src.nodata if src.nodata is not None else -32767.0

        DAM_COORD = (11.8028, 77.8017)
        reach = extract_downstream_reach(
            str(METTUR_RIVER_PATH), bounds, DAM_COORD,
            dem_data, transform, nodata,
            main_stem_name_hint="Kaveri"
        )
        nodes = sample_river_stations(reach, dem_data, transform, nodata)
        return nodes

    def test_mettur_downstream_elevation_trend(self, stations):
        """
        Mean elevation of first 25% of stations must exceed
        mean elevation of last 25% of stations.
        Verifies the DEM thalweg gradient is descending (physically downstream).
        """
        n = len(stations)
        q = max(2, n // 4)
        elev_start = np.mean([nd["z"] for nd in stations[:q]])
        elev_end   = np.mean([nd["z"] for nd in stations[-q:]])
        assert elev_start > elev_end, (
            f"Elevation does NOT decrease downstream: "
            f"upstream_mean={elev_start:.2f} m, downstream_mean={elev_end:.2f} m. "
            "The engine may have selected the wrong half of the river geometry."
        )

    def test_total_elevation_drop_positive(self, stations):
        """Total head from station 0 to last station must be positive."""
        z0 = stations[0]["z"]
        zn = stations[-1]["z"]
        drop = z0 - zn
        assert drop > 0.0, (
            f"No elevation drop: z_start={z0:.2f} m, z_end={zn:.2f} m, drop={drop:.2f} m"
        )

    def test_report_station_metrics(self, stations):
        """Report river station metrics (always passes — informational)."""
        n = len(stations)
        z0 = stations[0]["z"]
        zn = stations[-1]["z"]
        s_total = stations[-1]["s_m"]
        slope_mean_mkm = (z0 - zn) / max(1.0, s_total) * 1000.0
        print(f"\n  Cauvery downstream reach metrics:")
        print(f"    Number of stations:      {n}")
        print(f"    Total reach length:      {s_total/1000:.2f} km")
        print(f"    Elevation at station 0:  {z0:.2f} m MSL (upstream)")
        print(f"    Elevation at station N:  {zn:.2f} m MSL (downstream)")
        print(f"    Total elevation drop:    {z0 - zn:.2f} m")
        print(f"    Mean longitudinal slope: {slope_mean_mkm:.3f} m/km")
        assert True  # informational only
