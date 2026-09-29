import time
import requests

def test_full_pipeline():
    print("=== Testing Dam Break Simulation & GIS Pipeline ===")
    
    # 1. Projects
    r = requests.get('http://127.0.0.1:8000/api/projects')
    assert r.status_code == 200
    projects = r.json()
    # Find project with scenarios (Machchhu Dam-II)
    proj = next((p for p in projects if 'Machchhu' in p['name']), projects[0])
    proj_id = proj['id']
    print(f"[OK] Testing Project: {proj['name']} ({proj_id})")

    # 2. Scenarios
    r = requests.get(f'http://127.0.0.1:8000/api/scenarios/project/{proj_id}')
    assert r.status_code == 200
    scenarios = r.json()
    assert len(scenarios) > 0
    print(f"[OK] Scenarios loaded: {len(scenarios)} ({scenarios[0]['name']})")
    scen_id = scenarios[0]['id']

    # 3. Trigger simulation
    r = requests.post('http://127.0.0.1:8000/api/simulation/run', json={
        'project_id': proj_id,
        'scenario_id': scen_id,
        'engine_name': 'Experimental SPH Solver'
    })
    assert r.status_code == 200
    sim_info = r.json()
    sim_id = sim_info['simulation_id']
    print(f"[OK] Dispatched simulation: {sim_id}")
    print(f"     Engine Name:   {sim_info['engine_name']}")
    print(f"     Engine Status: {sim_info['engine_status']}")

    # 4. Poll status
    completed = False
    for i in range(25):
        time.sleep(0.5)
        status_res = requests.get(f'http://127.0.0.1:8000/api/simulation/{sim_id}/status').json()
        status = status_res['status']
        prog = status_res['progress']
        msg = status_res.get('message', '')
        print(f"     [Step {i+1}] Status: {status:14s} | Progress: {prog:5.1f}% | {msg}")
        if status == 'COMPLETED':
            completed = True
            break
        elif status == 'FAILED':
            raise RuntimeError(f"Simulation failed: {status_res.get('error_message')}")

    assert completed, "Simulation did not complete in time"

    # 5. Verify Results
    res = requests.get(f'http://127.0.0.1:8000/api/simulation/{sim_id}/results').json()
    print("\n=== Hydrodynamic & Impact Results ===")
    print(f"Peak Flood Depth:         {res['max_depth_m']:.2f} m")
    print(f"Peak Flow Velocity:       {res['max_velocity_ms']:.2f} m/s")
    print(f"Inundated Flood Area:     {res['inundated_area_sqkm']:.2f} km²")
    print(f"Affected Buildings:       {res['affected_buildings_count']} structures")
    print(f"Flooded Road Network:     {res['affected_roads_km']:.2f} km")
    print(f"Population Exposure:      {res['exposed_population']:,} persons")

    # Physical & Geometric Consistency Assertions
    assert res['inundated_area_sqkm'] > 0.05, f"Inundated area must be > 0.05 km², got {res['inundated_area_sqkm']}"
    assert 0.5 <= res['max_depth_m'] <= 26.0, f"Depth {res['max_depth_m']}m is outside physical dam height bounds (0.5 - 26m)"
    assert 0.5 <= res['max_velocity_ms'] <= 15.0, f"Velocity {res['max_velocity_ms']}m/s is unphysical"

    # Query Consistency Report
    val_res = requests.get(f'http://127.0.0.1:8000/api/simulation/{sim_id}/validation').json()
    val_data = val_res.get('validation', {})
    print(f"\n[Consistency Check] Status: {'CONSISTENT' if val_data.get('is_consistent') else 'FAILED'}")
    print(f"                    Summary: {val_data.get('summary')}")
    assert val_data.get('is_consistent'), f"Simulation failed consistency check: {val_data.get('issues')}"

    # 6. Verify Sentinel-1 SAR Comparison
    print("\n=== Testing Sentinel-1 SAR Flood Overlap ===")
    sat_res = requests.post(f'http://127.0.0.1:8000/api/satellite/compare-sentinel1/{sim_id}').json()
    assert sat_res['status'] == 'success'
    metrics = sat_res['metrics']
    print(f"Sensor:          {sat_res['sensor']}")
    print(f"IoU (Jaccard):   {metrics['iou_jaccard']}")
    print(f"Precision:       {metrics['precision']}")
    print(f"Recall:          {metrics['recall']}")
    print(f"F1-Score:        {metrics['f1_score']}")

    # 7. Verify Shapefile ZIP Export
    print("\n=== Testing Shapefile ZIP Export ===")
    shp_res = requests.get(f'http://127.0.0.1:8000/api/exports/shapefile/{sim_id}/flood_extent')
    assert shp_res.status_code == 200
    assert len(shp_res.content) > 100
    print(f"[OK] Shapefile ZIP generated successfully ({len(shp_res.content):,} bytes)")

    # 8. Verify Technical Report HTML
    print("\n=== Testing Scientific Report Generation ===")
    rep_res = requests.get(f'http://127.0.0.1:8000/api/reports/generate/{sim_id}')
    assert rep_res.status_code == 200
    assert "DAM BREAK INUNDATION STUDY" in rep_res.text
    print(f"[OK] Scientific technical report generated ({len(rep_res.text):,} characters)")

    print("\n[SUCCESS] SOFTWARE PIPELINE EXECUTED")
    print("Automated software tests:     PASSED")
    print("Scientific validation status: SEE BENCHMARK RESULTS")
    print("Real-world flood validation:  NOT YET ESTABLISHED")

if __name__ == "__main__":
    test_full_pipeline()
