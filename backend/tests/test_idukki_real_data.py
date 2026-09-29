"""
Phase 3 Automated Tests: Idukki Dam Real Data Acquisition & Validation.

Tests inspect actual files, metadata, raster properties, GeoJSON features,
dataset registry statuses, synthetic fallback prevention, and project isolation.
"""

import os
import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
import rasterio
import geopandas as gpd

from backend.main import app
from backend.app.gis.dataset_adapter import DatasetRegistry, DEMAdapter, RiverAdapter

client = TestClient(app)

IDUKKI_DIR = Path("data/idukki")
DEM_PATH = IDUKKI_DIR / "dem" / "processed" / "idukki_dem_30m.tif"
DEM_SOURCE_DIR = IDUKKI_DIR / "dem" / "source"
RIVER_PATH = IDUKKI_DIR / "river" / "periyar_river.geojson"
BUILDINGS_PATH = IDUKKI_DIR / "buildings" / "idukki_buildings.geojson"
ROADS_PATH = IDUKKI_DIR / "roads" / "idukki_roads.geojson"
RESERVOIR_PATH = IDUKKI_DIR / "reservoir" / "idukki_reservoir.geojson"
BOUNDARY_PATH = IDUKKI_DIR / "boundaries" / "study_area.geojson"
METADATA_PATH = IDUKKI_DIR / "metadata.json"
DATASETS_PATH = IDUKKI_DIR / "datasets.json"
SOURCES_PATH = IDUKKI_DIR / "SOURCES.md"
QUALITY_REPORT_PATH = IDUKKI_DIR / "DATA_QUALITY_REPORT.md"
VALIDATION_REPORT_PATH = IDUKKI_DIR / "validation_report.json"

def test_idukki_project_exists():
    """Verify Idukki Dam exists in database with authentic attributes."""
    res = client.get("/api/projects/idukki")
    assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
    p = res.json()
    assert p["slug"] == "idukki"
    assert "Idukki" in p["dam_name"]
    assert p["river_name"] == "Periyar River"
    assert p["state"] == "Kerala"
    assert p["country"] == "India"
    assert p["dam_lat"] == 9.85
    assert p["dam_lon"] == 76.97
    assert p["dam_height_m"] == 168.91
    assert p["crest_length_m"] == 365.85
    assert p["full_reservoir_level_m"] == 732.43
    assert p["reservoir_capacity_m3"] == 1996000000.0
    assert p["data_status"] == "READY"
    assert p["is_demo"] is False
    assert p["simulation_enabled"] is True

def test_idukki_dem_exists_or_reports_unavailable():
    """Verify authentic Copernicus DEM GLO-30 exists, opens, and contains real elevation."""
    assert DEM_PATH.exists(), f"Processed DEM missing at {DEM_PATH}"
    assert DEM_PATH.stat().st_size > 1_000_000, f"DEM size too small ({DEM_PATH.stat().st_size} bytes)"
    
    with rasterio.open(str(DEM_PATH)) as src:
        assert src.width == 1189
        assert src.height == 1189
        assert src.crs.to_string() == "EPSG:4326"
        assert src.bounds.left <= 76.97 <= src.bounds.right
        assert src.bounds.bottom <= 9.85 <= src.bounds.top
        
        data = src.read(1)
        valid = data[data != src.nodata]
        assert len(valid) > 0
        min_elev = float(valid.min())
        max_elev = float(valid.max())
        assert min_elev >= 0.0
        assert max_elev > 1500.0, f"Expected Western Ghats high ridge >1500m, got {max_elev}m"
        
        # Verify elevation at dam location is realistic gorge foundation
        py, px = src.index(76.97, 9.85)
        dam_elev = float(data[py, px])
        assert 500.0 < dam_elev < 750.0, f"Dam elevation {dam_elev} out of expected gorge range"

    # Verify source tiles are preserved unmodified
    source_files = list(DEM_SOURCE_DIR.glob("*.tif"))
    assert len(source_files) >= 2, "Expected at least 2 source Copernicus DEM tiles preserved"

def test_idukki_dataset_registry_is_valid():
    """Verify datasets.json registry structure, authentic paths, and correct statuses."""
    assert DATASETS_PATH.exists()
    with open(DATASETS_PATH, "r", encoding="utf-8") as f:
        registry = json.load(f)
    
    datasets = registry.get("datasets", {})
    assert datasets["dem"]["status"] == "READY"
    assert "Copernicus" in datasets["dem"]["source"]
    assert Path(datasets["dem"]["local_path"]).exists()
    
    assert datasets["river"]["status"] == "READY"
    assert "OpenStreetMap" in datasets["river"]["source"]
    assert Path(datasets["river"]["local_path"]).exists()
    
    assert datasets["buildings"]["status"] == "READY"
    assert Path(datasets["buildings"]["local_path"]).exists()
    
    assert datasets["roads"]["status"] == "READY"
    assert Path(datasets["roads"]["local_path"]).exists()
    
    # Population and Satellite must be NOT_CONFIGURED, never synthetic
    assert datasets["population"]["status"] == "NOT_CONFIGURED"
    assert datasets["satellite"]["status"] == "NOT_CONFIGURED"

def test_idukki_dataset_provenance_exists():
    """Verify SOURCES.md and DATA_QUALITY_REPORT.md document all real datasets."""
    assert SOURCES_PATH.exists()
    sources_text = SOURCES_PATH.read_text(encoding="utf-8")
    assert "Copernicus DEM GLO-30" in sources_text
    assert "OpenStreetMap" in sources_text
    assert "Central Water Commission" in sources_text or "CWC" in sources_text
    assert "KL09HH0001" in sources_text
    assert "NOT_CONFIGURED" in sources_text

    assert QUALITY_REPORT_PATH.exists()
    quality_text = QUALITY_REPORT_PATH.read_text(encoding="utf-8")
    assert "AVAILABLE" in quality_text
    assert "NOT_CONFIGURED" in quality_text

def test_idukki_does_not_use_machchhu_data():
    """Verify Idukki does not reference Machchhu demo data anywhere."""
    res = client.get("/api/projects/idukki/datasets")
    assert res.status_code == 200
    data_str = json.dumps(res.json()).lower()
    assert "machchhu" not in data_str
    
    with open(METADATA_PATH, "r", encoding="utf-8") as f:
        meta_str = f.read().lower()
    assert "machchhu" not in meta_str

def test_idukki_does_not_use_synthetic_dem():
    """Verify synthetic DEM generation is blocked for real projects like Idukki."""
    res = client.post("/api/datasets/dem/generate-dem?project_id=idukki")
    assert res.status_code == 400
    assert "prohibited" in res.json().get("detail", "").lower() or "real" in res.json().get("detail", "").lower()

def test_idukki_does_not_use_synthetic_river():
    """Verify Idukki river dataset contains genuine OSM geometries, not synthetic sine wave."""
    assert RIVER_PATH.exists()
    gdf = gpd.read_file(str(RIVER_PATH))
    assert len(gdf) > 1000, f"Expected real river network >1000 segments, got {len(gdf)}"
    
    # Check that it covers genuine coordinates around Idukki
    bounds = gdf.total_bounds
    assert bounds[0] < 76.97 < bounds[2]
    assert bounds[1] < 9.85 < bounds[3]

def test_idukki_project_isolation():
    """Verify Idukki data is isolated from other dams and unconfigured projects."""
    res_idukki = client.get("/api/projects/idukki/datasets").json()
    res_hirakud = client.get("/api/projects/hirakud/datasets").json()
    res_mettur = client.get("/api/projects/mettur/datasets").json()
    
    # Idukki DEM is READY; unconfigured catalogue dam (Hirakud) DEM is not_configured
    assert res_idukki["datasets"]["dem"]["status"] == "READY"
    assert res_hirakud["datasets"]["dem"]["status"] == "not_configured"
    assert res_hirakud["datasets"]["dem"].get("path") is None
    
    # Idukki river is READY; unconfigured catalogue dam (Hirakud) river is not_configured
    assert res_idukki["datasets"]["river"]["status"] == "READY"
    assert res_hirakud["datasets"]["river"]["status"] == "not_configured"

    # Mettur (Phase 5) has its own data and must NOT share or leak Idukki paths
    assert "idukki" not in str(res_mettur["datasets"]["dem"].get("path", "")).lower()
    assert "periyar" not in str(res_mettur["datasets"]["river"].get("path", "")).lower()

def test_catalogue_dams_cannot_run_simulation():
    """Verify catalogue-only dams cannot trigger simulations (HTTP 400)."""
    # Fetch catalogue dams
    res = client.get("/api/projects?simulation_enabled=false")
    assert res.status_code == 200
    catalogue_dams = res.json()
    assert len(catalogue_dams) > 0
    
    cat_dam = catalogue_dams[0]
    # Attempt to start simulation
    payload = {
        "project_id": cat_dam["id"],
        "scenario_id": "dummy_scenario",
        "engine_name": "SPH"
    }
    sim_res = client.post("/api/simulation/run", json=payload)
    assert sim_res.status_code == 400
    assert "catalogue" in sim_res.json().get("detail", "").lower() or "simulation is not enabled" in sim_res.json().get("detail", "").lower()

def test_idukki_generalized_dataset_registry():
    """Verify the generalized DatasetRegistry operates correctly on Idukki."""
    with open(METADATA_PATH, "r", encoding="utf-8") as f:
        meta = json.load(f)
    registry = DatasetRegistry(meta)
    summary = registry.get_dataset_summary()
    assert summary["project_id"] == "idukki"
    assert summary["dem"]["status"] == "VALID"
    assert summary["river"]["status"] == "VALID"
    assert summary["buildings"]["status"] == "VALID"
    assert summary["roads"]["status"] == "VALID"
    assert summary["reservoir"]["status"] == "VALID"
    assert summary["population"]["status"] == "NOT_CONFIGURED"
    assert summary["satellite"]["status"] == "NOT_CONFIGURED"
    
    readiness = registry.validate_simulation_readiness()
    assert readiness["ready"] is True

def test_idukki_dem_covers_study_area():
    """Verify DEM covers 100% of the study boundary without leaving any area uncovered."""
    import geopandas as gpd
    from shapely.geometry import box
    
    with rasterio.open(str(DEM_PATH)) as src:
        b = src.bounds
        dem_box = box(b.left, b.bottom, b.right, b.top)
    
    gdf_b = gpd.read_file(str(BOUNDARY_PATH))
    bound_geom = gdf_b.geometry.iloc[0]
    
    # Reproject for metric area comparison
    gdf_bound_utm = gdf_b.to_crs(epsg=32643)
    study_area_m2 = gdf_bound_utm.area.iloc[0]
    
    inter = dem_box.intersection(bound_geom)
    gdf_inter_utm = gpd.GeoSeries([inter], crs="EPSG:4326").to_crs(epsg=32643)
    inter_area_m2 = gdf_inter_utm.area.iloc[0]
    
    cov_pct = (inter_area_m2 / study_area_m2) * 100.0
    assert cov_pct >= 99.99, f"DEM only covers {cov_pct:.2f}% of study area; expected 100%"
    assert b.left <= 76.75
    assert b.right >= 77.08
    assert b.bottom <= 9.75
    assert b.top >= 10.08

def test_idukki_dem_nodata_is_not_zero():
    """Verify DEM nodata is explicitly configured and not converted to 0.0 elevation."""
    with rasterio.open(str(DEM_PATH)) as src:
        assert src.nodata == -32767.0, f"Expected nodata -32767.0, got {src.nodata}"
        data = src.read(1)
        zero_count = int((data == 0.0).sum())
        assert zero_count == 0, f"Found {zero_count} zero-elevation pixels; expected 0"
        
        valid = data[data != src.nodata]
        min_elev = float(valid.min())
        max_elev = float(valid.max())
        assert min_elev > 10.0, f"Expected minimum elevation in Western Ghats gorge > 10m, got {min_elev}m"
        assert max_elev > 1800.0, f"Expected ridge peaks > 1800m, got {max_elev}m"

def test_idukki_dam_inside_dem():
    """Verify Idukki Dam point falls strictly inside DEM bounds and elevation is realistic."""
    with rasterio.open(str(DEM_PATH)) as src:
        assert src.bounds.left <= 76.97 <= src.bounds.right
        assert src.bounds.bottom <= 9.85 <= src.bounds.top
        
        py, px = src.index(76.97, 9.85)
        elev = float(src.read(1)[py, px])
        assert 500.0 < elev < 750.0, f"Dam elevation {elev}m out of realistic gorge range"

def test_idukki_dam_inside_reservoir_or_expected_relationship():
    """Verify Idukki Arch Dam and Cheruthoni Dam spatial relationship to reservoir pool."""
    import geopandas as gpd
    from shapely.geometry import Point
    from shapely.ops import unary_union
    
    gdf_res = gpd.read_file(str(RESERVOIR_PATH))
    assert len(gdf_res) > 0
    res_union_utm = unary_union(gdf_res.to_crs(epsg=32643).geometry)
    
    dam_pt_utm = gpd.GeoSeries([Point(76.97, 9.85)], crs="EPSG:4326").to_crs(epsg=32643).iloc[0]
    dist_m = float(res_union_utm.distance(dam_pt_utm))
    # Arch dam is the downstream retaining wall across the gorge
    assert dist_m < 2500.0, f"Dam to reservoir distance {dist_m}m too far"

def test_idukki_river_mainstem_connectivity():
    """Verify classified Periyar River main stem reaches downstream study corridor."""
    import geopandas as gpd
    gdf = gpd.read_file(str(RIVER_PATH))
    assert "river_classification" in gdf.columns
    
    main_stem = gdf[gdf["river_classification"] == "main_stem"]
    assert len(main_stem) >= 12, f"Expected >=12 main stem segments, got {len(main_stem)}"
    
    # Metric length
    total_km = float(main_stem.to_crs(epsg=32643).length.sum() / 1000.0)
    assert total_km > 50.0, f"Expected >50km total main stem channel, got {total_km}km"
    
    # Check downstream reach towards Neriamangalam (western longitude < 76.75)
    bounds = main_stem.total_bounds
    assert bounds[0] <= 76.75, f"Main stem does not reach western downstream limit: {bounds[0]}"

def test_idukki_no_synthetic_fallback():
    """Verify synthetic DEM generation is blocked and no synthetic fallbacks are referenced."""
    # 1. Blocked API
    res = client.post("/api/datasets/dem/generate-dem?project_id=idukki")
    assert res.status_code == 400
    
    # 2. Registry check
    with open(DATASETS_PATH, "r", encoding="utf-8") as f:
        ds = json.load(f)
    for k, v in ds["datasets"].items():
        if isinstance(v, dict):
            p = str(v.get("local_path", "")).lower()
            assert "synthetic" not in p
            assert "machchhu" not in p
            assert "dummy" not in p

