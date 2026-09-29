import pytest
from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)

def test_health_check():
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["delft3d_available"] is False

def test_project_crud():
    payload = {
        "name": "Periyar River Inundation Study",
        "river_name": "Periyar River",
        "country": "India",
        "state": "Kerala",
        "district": "Idukki",
        "dam_name": "Idukki Dam",
        "dam_lat": 9.8500,
        "dam_lon": 76.9700,
        "min_lat": 9.8000,
        "min_lon": 76.9000,
        "max_lat": 9.9500,
        "max_lon": 77.0500,
        "crs": "EPSG:4326"
    }
    create_res = client.post("/api/projects", json=payload)
    assert create_res.status_code == 200
    proj_data = create_res.json()
    assert proj_data["name"] == payload["name"]
    proj_id = proj_data["id"]

    get_res = client.get(f"/api/projects/{proj_id}")
    assert get_res.status_code == 200
    assert get_res.json()["dam_name"] == "Idukki Dam"

def test_sph_benchmark_status_endpoint():
    res = client.get("/api/benchmarks/status")
    assert res.status_code == 200
    data = res.json()
    assert "Experimental SPH Solver" in data["engine_name"]
    assert len(data["benchmarks_available"]) >= 2
