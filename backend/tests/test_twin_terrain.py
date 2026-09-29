"""
Phase 6 CP3/CP5/CP6 verification: the 3D terrain + water are driven by the
AUTHORITATIVE, co-registered rasters (real DEM, depth, arrival, mask) -- not by
mathematical primitives or radius-based flooding. These tests assert BEHAVIOUR
of the /terrain payload, not mere file existence.
"""
import numpy as np
import rasterio
from pathlib import Path
from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)
MET = "mettur"
DEM = Path("data/mettur/dem/processed/mettur_dem_30m.tif")


def _terrain(res=120):
    res_obj = client.get(f"/api/simulation/{MET}/terrain?res={res}")
    assert res_obj.status_code == 200, res_obj.text
    return res_obj.json()


def test_terrain_grid_shape_and_bounds_match_study_area():
    t = _terrain(120)
    cols, rows = t["grid"]["cols"], t["grid"]["rows"]
    assert cols == 120  # longest axis honoured
    n = cols * rows
    assert len(t["elevation_m"]["values"]) == n
    assert len(t["depth_m"]["values"]) == n
    assert len(t["arrival_min"]["values"]) == n
    assert len(t["inundation_mask"]["values"]) == n
    # Bounds must equal the real raster study-area bounds (Mettur / Cauvery).
    with rasterio.open(DEM) as ds:
        b = ds.bounds
    assert abs(t["bounds"]["west"] - b.left) < 1e-6
    assert abs(t["bounds"]["north"] - b.top) < 1e-6
    assert t["crs"] == "EPSG:4326"


def test_terrain_elevation_is_real_dem_not_flat():
    t = _terrain(120)
    with rasterio.open(DEM) as ds:
        a = ds.read(1).astype(float)
        a = a[a > -9990]
    dem_min, dem_max = float(a.min()), float(a.max())
    # Reported range is the decimated grid's range: it must lie within the real
    # DEM range and cover most of it (decimation may miss the single peak cell).
    assert dem_min - 5.0 <= t["elevation_m"]["min"] <= dem_max
    assert t["elevation_m"]["max"] <= dem_max + 1e-6
    assert (t["elevation_m"]["max"] - t["elevation_m"]["min"]) > 0.8 * (dem_max - dem_min)
    vals = np.array(t["elevation_m"]["values"])
    # Genuine terrain has substantial elevation variation (not a synthetic plane).
    assert (vals.max() - vals.min()) > 100.0
    assert vals.std() > 10.0


def test_terrain_water_only_where_inundated():
    t = _terrain(120)
    mask = np.array(t["inundation_mask"]["values"])
    depth = np.array(t["depth_m"]["values"])
    assert t["inundation_mask"]["wet_cells"] > 0
    # No dry cell may carry a wet depth (water only where inundation occurs).
    assert np.all(depth[mask == 0] < 0.15 + 1e-6)
    # The wettest cells carry the real peak depth order of magnitude.
    assert depth.max() > 5.0
    assert t["depth_m"]["max"] <= 78.0  # authoritative peak ~77.36 m


def test_terrain_arrival_drives_propagation_not_radius():
    t = _terrain(120)
    arr = np.array(t["arrival_min"]["values"])
    mask = np.array(t["inundation_mask"]["values"])
    wet_arr = arr[(mask == 1) & (arr >= 0)]
    assert wet_arr.size > 0
    # Arrival spans a real range (progressive propagation), not a single instant.
    assert wet_arr.max() - wet_arr.min() > 10.0
    # Dry cells are flagged -1 (never reached), never a positive radius fill.
    assert np.all(arr[mask == 0] <= 0.0 + 1e-9) or np.all(arr[mask == 0] == -1.0)


def test_terrain_water_surface_is_spatially_varying():
    """WSE = elevation + depth must differ cell-to-cell (per-cell surface, not a
    single uniform plane over the whole flood)."""
    t = _terrain(120)
    elev = np.array(t["elevation_m"]["values"])
    depth = np.array(t["depth_m"]["values"])
    mask = np.array(t["inundation_mask"]["values"])
    wse = elev + depth
    wet_wse = wse[mask == 1]
    assert wet_wse.size > 5
    # A uniform-plane cheat would have ~zero std across wet cells.
    assert wet_wse.std() > 1.0


def test_terrain_reports_authoritative_provenance():
    t = _terrain(80)
    assert t["peak_discharge_m3s"] == 88699.2
    assert "DEM" in t["source"] and "arrival_time" in t["source"]
    assert "diffusion-wave" in t["solver"]
    assert "Hypothetical" in t["scenario_type"]
    assert t["dam"]["lat"] and t["dam"]["lon"]


def test_river_is_real_geometry_not_synthetic():
    """CP4: the /river overlay must be the authoritative OSM river polyline, not a
    straight/procedural curve. It must have real vertices and lie in the domain."""
    r = client.get(f"/api/simulation/{MET}/river")
    assert r.status_code == 200, r.text
    fc = r.json()
    assert fc["type"] == "FeatureCollection"
    feats = fc["features"]
    assert len(feats) > 0
    # Provenance names the actual source GeoJSON file.
    assert "authoritative river GeoJSON" in fc["metadata"]["source"]
    assert fc["metadata"]["total_length_km"] > 0.5
    # Gather all vertices; a real river has many bends (not 2 endpoints).
    verts = []
    for f in feats:
        g = f["geometry"]
        lines = g["coordinates"] if g["type"] == "MultiLineString" else [g["coordinates"]]
        for ln in lines:
            verts.extend(ln)
    assert len(verts) > 10
    lons = np.array([v[0] for v in verts]); lats = np.array([v[1] for v in verts])
    # Not a perfectly straight segment: both axes vary.
    assert lons.max() - lons.min() > 1e-4
    assert lats.max() - lats.min() > 1e-4
    # Vertices fall within the study-area bounds.
    with rasterio.open(DEM) as ds:
        b = ds.bounds
    assert lons.min() >= b.left - 0.05 and lons.max() <= b.right + 0.05
    assert lats.min() >= b.bottom - 0.05 and lats.max() <= b.top + 0.05


def test_flow_vectors_directional_not_radial():
    """CP15: flow vectors come from the velocity + arrival-gradient field. They must
    NOT all point radially away from the dam (that would be a fake field)."""
    r = client.get(f"/api/simulation/{MET}/flow-vectors?step=6")
    assert r.status_code == 200, r.text
    data = r.json()
    vecs = data["vectors"]
    assert len(vecs) > 5
    assert "arrival_time" in data["source"]
    dam_lat, dam_lon = 11.8028, 77.8017
    # Fraction of vectors pointing radially outward from the dam. A radial fake
    # field would push this near 1.0; a real routed field should be well below.
    outward = 0
    for v in vecs:
        rx, ry = v["lon"] - dam_lon, v["lat"] - dam_lat
        rn = (rx * rx + ry * ry) ** 0.5
        if rn < 1e-9:
            continue
        dot = (v["u"] * rx + v["v"] * ry) / rn
        if dot > 0.9:
            outward += 1
    assert outward / len(vecs) < 0.8
