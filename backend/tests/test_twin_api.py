import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)
REGISTRY = Path("data/dams/india_dams.json")


# ---- Dam registry & search (Part 24 #1-6) --------------------------------
def _registry():
    with open(REGISTRY, "r", encoding="utf-8") as f:
        return json.load(f)


def test_registry_has_valid_coordinates():
    dams = _registry()
    assert len(dams) >= 4
    for d in dams:
        assert 6.0 <= d["latitude"] <= 37.5, f"{d['id']} lat out of India range"
        assert 68.0 <= d["longitude"] <= 97.5, f"{d['id']} lon out of India range"


def test_list_dams_api_returns_registry():
    res = client.get("/api/dams")
    assert res.status_code == 200
    data = res.json()
    ids = {d["id"] for d in data}
    assert {"idukki", "mettur", "hirakud"}.issubset(ids)


def test_dam_search_prefix():
    for q, expect in [("met", "mettur"), ("idu", "idukki"), ("hir", "hirakud")]:
        res = client.get(f"/api/dams/search?q={q}")
        assert res.status_code == 200
        results = res.json()
        assert results, f"no results for {q}"
        assert results[0]["id"] == expect


def test_marker_coords_match_registry():
    for d in _registry():
        res = client.get(f"/api/dams/{d['id']}/location")
        assert res.status_code == 200
        loc = res.json()
        assert loc["latitude"] == pytest.approx(d["latitude"])
        assert loc["longitude"] == pytest.approx(d["longitude"])


# ---- Digital twin endpoints on verified Mettur outputs (Part 24 #8-11) ---
MET = "mettur"


def test_timeline_derives_from_arrival_raster():
    res = client.get(f"/api/simulation/{MET}/timeline?frames=20")
    assert res.status_code == 200
    data = res.json()
    assert "arrival_time.tif" in data["source"]
    frames = data["frames"]
    assert len(frames) == 20
    # inundated area is monotonically non-decreasing with time (cumulative arrival)
    areas = [f["inundated_area_sqkm"] for f in frames]
    assert all(b >= a - 1e-6 for a, b in zip(areas, areas[1:]))
    assert data["peak_discharge_m3s"] == pytest.approx(88699.2, rel=1e-3)


def test_buildings_from_real_gis_with_states():
    res = client.get(f"/api/simulation/{MET}/buildings?limit=2000")
    assert res.status_code == 200
    data = res.json()
    assert data["type"] == "FeatureCollection"
    meta = data["metadata"]
    assert meta["state_thresholds_m"]["WATCH"] == "0.15-0.5"
    valid_states = {"NORMAL", "WATCH", "AFFECTED", "FLOODED"}
    for f in data["features"][:50]:
        assert f["geometry"]["type"] in ("Polygon", "MultiPolygon")
        assert f["properties"]["building_state"] in valid_states


def test_roads_from_real_gis():
    res = client.get(f"/api/simulation/{MET}/roads")
    assert res.status_code == 200
    data = res.json()
    assert data["type"] == "FeatureCollection"
    assert data["metadata"]["road_impact_depth_threshold_m"] == 0.15
    assert data["metadata"]["affected_length_km"] >= 0.0


def test_impact_is_honest_and_authoritative():
    res = client.get(f"/api/simulation/{MET}/impact")
    assert res.status_code == 200
    data = res.json()
    assert data["hydraulic"]["source"] == "authoritative"
    # ML never claims validation against observed events
    assert data["ai_model"]["calibrated_against_observations"] is False
    assert "Research prototype" in data["ai_model"]["status"]
    assert set(data["ai_impact_zones_sqkm"].keys()) == {"LOW", "MODERATE", "HIGH", "SEVERE"}


def test_flow_vectors_from_velocity_and_arrival():
    res = client.get(f"/api/simulation/{MET}/flow-vectors?step=8")
    assert res.status_code == 200
    data = res.json()
    assert "maximum_velocity.tif" in data["source"]
    for v in data["vectors"][:20]:
        assert -1.001 <= v["u"] <= 1.001 and -1.001 <= v["v"] <= 1.001
        assert v["speed_ms"] >= 0.0


# ---- Phase 6B: honest twin-availability gate (no fabricated simulations) ---
def test_availability_true_for_verified_study_case():
    """Mettur has a real DEM + all four hydraulic rasters on disk -> twin_ready."""
    res = client.get(f"/api/simulation/{MET}/availability")
    assert res.status_code == 200
    data = res.json()
    assert data["twin_ready"] is True
    lyr = data["layers"]
    assert lyr["dem"] is True
    for k in ("raster_maximum_depth", "raster_maximum_velocity",
              "raster_arrival_time", "raster_inundation_mask"):
        assert lyr[k] is True, f"{k} should exist for verified Mettur"


def test_availability_false_for_metadata_only_dam():
    """Registry-listed dams without simulation outputs must NOT report twin_ready
    (no fabricated simulation). Returns 200, not 404, with missing layers flagged."""
    for slug in ("hirakud", "srisailam"):
        res = client.get(f"/api/simulation/{slug}/availability")
        assert res.status_code == 200, slug
        data = res.json()
        assert data["twin_ready"] is False, f"{slug} has no real rasters"
        assert data["layers"]["raster_maximum_depth"] is False


def test_registry_has_simulation_matches_disk_truth():
    """The registry's has_simulation flag must equal real on-disk twin readiness
    for every dam it flags -- no dam may advertise a simulation it does not have."""
    for d in _registry():
        avail = client.get(f"/api/simulation/{d.get('slug', d['id'])}/availability").json()
        assert d["has_simulation"] == avail["twin_ready"], (
            f"{d['id']}: registry has_simulation={d['has_simulation']} but "
            f"on-disk twin_ready={avail['twin_ready']}"
        )
