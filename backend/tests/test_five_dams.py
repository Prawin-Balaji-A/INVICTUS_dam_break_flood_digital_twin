import pytest
from fastapi.testclient import TestClient
from pathlib import Path
import json

from backend.main import app

client = TestClient(app)

TARGET_SLUGS = ["idukki", "mettur", "hirakud", "srisailam", "tehri"]

def test_five_dams_load_and_unique_ids():
    """Verify all five real target dams are registered and IDs are unique."""
    response = client.get("/api/projects")
    assert response.status_code == 200
    projects = response.json()
    assert len(projects) >= 5

    slugs_found = {p.get("slug") for p in projects if p.get("slug")}
    for slug in TARGET_SLUGS:
        assert slug in slugs_found, f"Target dam slug '{slug}' missing from project list"

    # Verify ID uniqueness
    ids = [p["id"] for p in projects]
    assert len(ids) == len(set(ids)), "Project IDs must be strictly unique"

def test_dam_canonical_directories_and_metadata():
    """Verify data/<slug>/metadata.json, datasets.json, scenarios.json exist with genuine provenance."""
    base_data_dir = Path(__file__).resolve().parent.parent.parent / "data"

    for slug in TARGET_SLUGS:
        dam_dir = base_data_dir / slug
        assert dam_dir.exists(), f"Directory missing: {dam_dir}"
        
        meta_file = dam_dir / "metadata.json"
        datasets_file = dam_dir / "datasets.json"
        scenarios_file = dam_dir / "scenarios.json"

        assert meta_file.exists(), f"metadata.json missing for {slug}"
        assert datasets_file.exists(), f"datasets.json missing for {slug}"
        assert scenarios_file.exists(), f"scenarios.json missing for {slug}"

        with open(meta_file, "r", encoding="utf-8") as f:
            meta = json.load(f)
            assert meta["id"] == slug
            assert meta["country"] == "India"
            assert "latitude" in meta and meta["latitude"] is not None
            assert "longitude" in meta and meta["longitude"] is not None
            assert "sources" in meta and isinstance(meta["sources"], list)
            assert len(meta["sources"]) > 0

def test_dataset_registry_endpoint():
    """Verify GET /api/projects/{id}/datasets reports authentic statuses (not_configured) and no fabricated paths."""
    projects_res = client.get("/api/projects")
    projects = projects_res.json()

    for slug in TARGET_SLUGS:
        p = next((x for x in projects if x.get("slug") == slug), None)
        assert p is not None

        ds_res = client.get(f"/api/projects/{p['id']}/datasets")
        assert ds_res.status_code == 200
        ds_data = ds_res.json()

        assert ds_data["dam_id"] == slug
        datasets = ds_data["datasets"]
        assert "dem" in datasets
        assert "river" in datasets
        assert "buildings" in datasets

        # Dataset status must be one of the valid known states
        # 'valid' = fully configured (e.g. Mettur after Phase 5 data acquisition)
        assert datasets["dem"]["status"].lower() in ["not_configured", "partial", "ready", "valid", "invalid"]
        if datasets["dem"]["status"].lower() == "not_configured":
            assert datasets["dem"]["path"] is None

def test_scenario_templates_endpoint():
    """Verify GET /api/projects/{id}/scenarios returns the 3 failure modes without fabricated breach numbers."""
    projects_res = client.get("/api/projects")
    projects = projects_res.json()

    for slug in TARGET_SLUGS:
        p = next((x for x in projects if x.get("slug") == slug), None)
        assert p is not None

        scen_res = client.get(f"/api/projects/{p['id']}/scenarios")
        assert scen_res.status_code == 200
        scenarios = scen_res.json()
        assert len(scenarios) >= 3

        formulations = {s.get("breach_formulation") for s in scenarios}
        assert any("Froehlich" in f for f in formulations)
        assert any("MacDonald" in f for f in formulations)
        assert any("von" in f.lower() for f in formulations)

def test_project_status_endpoint():
    """Verify GET /api/projects/{id}/status endpoint structure."""
    projects_res = client.get("/api/projects")
    projects = projects_res.json()

    for slug in TARGET_SLUGS:
        p = next((x for x in projects if x.get("slug") == slug), None)
        assert p is not None

        status_res = client.get(f"/api/projects/{p['id']}/status")
        assert status_res.status_code == 200
        status_data = status_res.json()

        assert status_data["project_id"] == p["id"]
        assert status_data["is_demo"] is False
        assert "datasets" in status_data
        assert "scenarios" in status_data

def test_state_isolation_no_leakage():
    """Verify Idukki does not inherit Machchhu data, and Mettur does not inherit Idukki data."""
    projects_res = client.get("/api/projects")
    projects = projects_res.json()

    idukki = next(p for p in projects if p.get("slug") == "idukki")
    mettur = next(p for p in projects if p.get("slug") == "mettur")
    machchhu = next(p for p in projects if p.get("slug") == "machchhu_demo")

    assert idukki["river_name"] == "Periyar River"
    assert mettur["river_name"] == "Cauvery River"
    assert machchhu["river_name"] == "Machchhu River"

    assert idukki["dam_lat"] != mettur["dam_lat"]
    assert idukki["dam_lon"] != machchhu["dam_lon"]

    # Machchhu is demo mode; Idukki and Mettur are not demo mode
    assert machchhu.get("is_demo") is True
    assert idukki.get("is_demo") is False
    assert mettur.get("is_demo") is False

def test_simulation_safety_rejects_unconfigured_real_dam():
    """Run Simulation must reject real projects when mandatory datasets (DEM) are missing."""
    projects_res = client.get("/api/projects")
    projects = projects_res.json()

    hirakud = next(p for p in projects if p.get("slug") == "hirakud")
    scens_res = client.get(f"/api/scenarios/project/{hirakud['id']}")
    scenarios = scens_res.json()
    assert len(scenarios) > 0
    scen_id = scenarios[0]["id"]

    sim_res = client.post("/api/simulation/run", json={
        "project_id": hirakud["id"],
        "scenario_id": scen_id,
        "engine_name": "Experimental SPH Solver"
    })
    assert sim_res.status_code == 400
    detail = sim_res.json()["detail"]
    assert "DEM dataset not configured" in detail
    assert "Hirakud" in detail

def test_mettur_simulation_resolves_real_datasets():
    """Verify Mettur has real DEM and River configured and accepts simulation invocation."""
    projects_res = client.get("/api/projects")
    projects = projects_res.json()

    mettur = next(p for p in projects if p.get("slug") == "mettur")
    assert mettur["dem_path"] is not None
    assert Path(mettur["dem_path"]).exists()
    assert mettur["river_path"] is not None
    assert Path(mettur["river_path"]).exists()
    assert mettur["data_status"] in ["CONFIGURED", "READY"]
    assert mettur["simulation_enabled"] is True

    scens_res = client.get(f"/api/scenarios/project/{mettur['id']}")
    scenarios = scens_res.json()
    assert len(scenarios) > 0
    scen_id = scenarios[0]["id"]

    sim_res = client.post("/api/simulation/run", json={
        "project_id": mettur["id"],
        "scenario_id": scen_id,
        "engine_name": "Experimental SPH Solver"
    })
    # Must succeed with 200 and return a simulation_id
    assert sim_res.status_code == 200
    sim_data = sim_res.json()
    assert "simulation_id" in sim_data
    assert sim_data["status"] == "QUEUED"

def test_mettur_dataset_registry_returns_configured():
    """Verify GET /api/projects/{id}/datasets reports Mettur datasets as configured."""
    projects_res = client.get("/api/projects")
    projects = projects_res.json()

    mettur = next(p for p in projects if p.get("slug") == "mettur")
    ds_res = client.get(f"/api/projects/{mettur['id']}/datasets")
    assert ds_res.status_code == 200
    datasets = ds_res.json()["datasets"]

    assert datasets["dem"]["status"].lower() in ["ready", "valid", "configured"]
    assert datasets["dem"]["path"] == "data/mettur/dem/processed/mettur_dem_30m.tif"
    assert datasets["river"]["status"].lower() in ["ready", "valid", "configured"]
    assert datasets["buildings"]["status"].lower() in ["ready", "valid", "configured"]
    assert datasets["roads"]["status"].lower() in ["ready", "valid", "configured"]
    assert datasets["population"]["status"].lower() in ["not_configured", "optional"]
    assert datasets["satellite"]["status"].lower() in ["not_configured", "optional"]

def test_mettur_scenario_active_storage_semantic_distinction():
    """Verify Mettur scenario maintains clear semantic distinction between capacity and active breach storage."""
    projects_res = client.get("/api/projects")
    projects = projects_res.json()

    mettur = next(p for p in projects if p.get("slug") == "mettur")
    # Total reservoir capacity: 2644 MCM
    assert mettur["reservoir_capacity_m3"] == 2644000000.0

    scens_res = client.get(f"/api/scenarios/project/{mettur['id']}")
    scenarios = scens_res.json()
    scen01 = next(s for s in scenarios if "Scenario 01" in s["name"])
    # Scenario active breach storage: 500 MCM
    assert scen01["reservoir_volume"] == 500000000.0
    # Must NOT conflate active storage with total capacity
    assert scen01["reservoir_volume"] != mettur["reservoir_capacity_m3"]

def test_mettur_authoritative_peak_discharge():
    """Verify Mettur baseline scenario peak discharge is authoritative ~88,699 m3/s, not stale 241,347 m3/s."""
    projects_res = client.get("/api/projects")
    projects = projects_res.json()

    mettur = next(p for p in projects if p.get("slug") == "mettur")
    scens_res = client.get(f"/api/scenarios/project/{mettur['id']}")
    scenarios = scens_res.json()
    scen01 = next(s for s in scenarios if "Scenario 01" in s["name"])

    scen_detail = client.get(f"/api/scenarios/{scen01['id']}").json()
    peak_q = scen_detail["peak_discharge_m3s"]
    # Peak must be ~88,699.2 m3/s (within 1%)
    assert abs(peak_q - 88699.2) / 88699.2 < 0.01, f"Peak Q {peak_q} m3/s differs from verified 88,699.2 m3/s"
    assert peak_q < 100000.0, "Peak discharge must not be unrouted 241,347 m3/s"

def test_state_isolation_mettur_idukki_hydrograph():
    """Verify Mettur and Idukki scenarios produce distinct authoritative peaks without cross-contamination."""
    projects_res = client.get("/api/projects")
    projects = projects_res.json()

    mettur = next(p for p in projects if p.get("slug") == "mettur")
    idukki = next(p for p in projects if p.get("slug") == "idukki")

    m_scens = client.get(f"/api/scenarios/project/{mettur['id']}").json()
    i_scens = client.get(f"/api/scenarios/project/{idukki['id']}").json()

    m_s01 = client.get(f"/api/scenarios/{m_scens[0]['id']}").json()
    i_s01 = client.get(f"/api/scenarios/{i_scens[0]['id']}").json()

    # Mettur peak ~88,699.2 m3/s
    assert abs(m_s01["peak_discharge_m3s"] - 88699.2) < 500.0
    # Idukki peak ~74,941.0 m3/s
    assert abs(i_s01["peak_discharge_m3s"] - 74941.0) < 500.0

    assert m_s01["reservoir_volume"] == 500000000.0
    assert i_s01["reservoir_volume"] == 450000000.0

def test_india_catalogue_vs_study_dams_distinction():
    """Verify India-wide catalogue dams exist with simulation_enabled=False and 5 study dams have simulation_enabled=True."""
    projects_res = client.get("/api/projects")
    assert projects_res.status_code == 200
    projects = projects_res.json()

    # The 5 study dams must be simulation-enabled
    for slug in TARGET_SLUGS:
        dam = next((p for p in projects if p.get("slug") == slug), None)
        assert dam is not None, f"Study dam {slug} missing"
        assert dam.get("simulation_enabled") is True, f"Study dam {slug} must have simulation_enabled=True"

    # Catalogue dams must have simulation_enabled=False
    catalogue_slugs = ["sardar_sarovar", "bhakra", "nagarjuna_sagar", "koyna"]
    for slug in catalogue_slugs:
        cat_dam = next((p for p in projects if p.get("slug") == slug), None)
        assert cat_dam is not None, f"Catalogue dam {slug} missing"
        assert cat_dam.get("simulation_enabled") is False, f"Catalogue dam {slug} must have simulation_enabled=False"
        assert cat_dam.get("data_status") == "CATALOGUE ONLY"

def test_catalogue_only_dam_simulation_rejected():
    """Attempting to run simulation on a catalogue-only dam must be cleanly rejected with HTTP 400."""
    projects_res = client.get("/api/projects?search=Nagarjuna")
    projects = projects_res.json()
    assert len(projects) > 0
    ns_dam = projects[0]
    assert ns_dam.get("simulation_enabled") is False

    sim_res = client.post("/api/simulation/run", json={
        "project_id": ns_dam["id"],
        "scenario_id": "dummy-scenario-id",
        "engine_name": "Experimental SPH Solver"
    })
    assert sim_res.status_code == 400
    detail = sim_res.json()["detail"]
    assert "Simulation not available for this study" in detail
    assert "catalogue-only entry" in detail

def test_catalogue_search_and_filtering():
    """Test filtering projects by state, river, search term, and simulation_enabled flag."""
    # Filter by river
    res_krishna = client.get("/api/projects?river=Krishna")
    assert res_krishna.status_code == 200
    krishna_dams = res_krishna.json()
    assert len(krishna_dams) >= 2
    for d in krishna_dams:
        assert "krishna" in d["river_name"].lower()

    # Filter by simulation_enabled
    res_sim = client.get("/api/projects?simulation_enabled=true")
    assert res_sim.status_code == 200
    sim_dams = res_sim.json()
    for d in sim_dams:
        assert d["simulation_enabled"] is True

    # Filter by state
    res_kerala = client.get("/api/projects?state=Kerala")
    assert res_kerala.status_code == 200
    kerala_dams = res_kerala.json()
    assert any(d["slug"] == "idukki" for d in kerala_dams)

def test_cross_project_scenario_simulation_rejection():
    """Verify that submitting a simulation with mismatched project and scenario IDs returns HTTP 400."""
    projects = client.get("/api/projects").json()
    mettur = next(p for p in projects if p.get("slug") == "mettur")
    idukki = next(p for p in projects if p.get("slug") == "idukki")

    i_scens = client.get(f"/api/scenarios/project/{idukki['id']}").json()
    m_scens = client.get(f"/api/scenarios/project/{mettur['id']}").json()

    # Attempt to run Mettur project with Idukki scenario
    bad_res = client.post("/api/simulation/run", json={
        "project_id": mettur["id"],
        "scenario_id": i_scens[0]["id"],
        "engine_name": "Generalized 2D Wave"
    })
    assert bad_res.status_code == 400
    assert "does not belong to project" in bad_res.json()["detail"]

    # Attempt to run Idukki project with Mettur scenario
    bad_res2 = client.post("/api/simulation/run", json={
        "project_id": idukki["id"],
        "scenario_id": m_scens[0]["id"],
        "engine_name": "Generalized 2D Wave"
    })
    assert bad_res2.status_code == 400
    assert "does not belong to project" in bad_res2.json()["detail"]

def test_latest_simulation_endpoint_isolation():
    """Verify latest simulation endpoint returns authoritative outputs for each project without crosstalk."""
    m_latest = client.get("/api/simulation/project/mettur/latest").json()
    i_latest = client.get("/api/simulation/project/idukki/latest").json()

    # Mettur peak ~88,699 m3/s
    assert abs(m_latest["peak_discharge_m3s"] - 88699.2) < 500.0
    # Idukki peak ~74,941 m3/s
    assert abs(i_latest["peak_discharge_m3s"] - 74941.0) < 500.0


