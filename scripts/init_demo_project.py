import sys
import os
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.app.core.database import SessionLocal, engine, Base
from backend.app.models.project import Project
from backend.app.models.scenario import Scenario
from backend.app.models.schemas import ScenarioCreate
from backend.app.api.scenarios import create_scenario
from backend.app.api.datasets import generate_dem, fetch_osm_layers

def init_machchhu_demo():
    print("=== Initializing Machchhu Dam-II Demonstration Project ===")
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    # Check if project already exists
    existing = db.query(Project).filter((Project.slug == "machchhu_demo") | (Project.name == "Machchhu Dam-II (Historical Demo)")).first()
    if existing:
        print(f"Project already exists with ID: {existing.id}")
        proj = existing
    else:
        proj = Project(
            slug="machchhu_demo",
            name="Machchhu Dam-II (Historical Demo)",
            river_name="Machchhu River",
            country="India",
            state="Gujarat",
            district="Morbi",
            dam_name="Machchhu Dam-II",
            dam_lat=22.7750,
            dam_lon=70.8986,
            min_lat=22.7200,
            min_lon=70.8200,
            max_lat=22.8600,
            max_lon=70.9500,
            crs="EPSG:4326",
            projected_crs="EPSG:32642",
            is_demo=True,
            data_status="DEMO / SAMPLE DATA"
        )
        db.add(proj)
        db.commit()
        db.refresh(proj)
        print(f"Created Project: {proj.name} ({proj.id})")

    # Ingest DEM and Topography
    print("Generating regional DEM and topographic derivatives...")
    dem_res = generate_dem(proj.id, db)
    print(f"DEM processed: {dem_res['dem_path']}, Elevation: {dem_res['elevation_min_m']}m - {dem_res['elevation_max_m']}m")

    # Fetch OSM Rivers, Buildings, Roads
    print("Fetching OpenStreetMap waterways, buildings, and roads...")
    osm_res = fetch_osm_layers(proj.id, db)
    print(f"OSM layers loaded: {osm_res['waterways_count']} waterways, {osm_res['buildings_count']} buildings, {osm_res['roads_count']} roads")

    # Seed Scenarios
    scenarios_data = [
        ScenarioCreate(
            project_id=proj.id,
            name="Scenario 01 — 50% Breach (Froehlich 2008)",
            dam_height=26.0,
            dam_length=1000.0,
            dam_crest_elev=60.0,
            reservoir_volume=110000000.0,
            reservoir_level=24.0,
            reservoir_area=20000000.0,
            breach_formulation="Froehlich_2008",
            breach_type="Overtopping",
            breach_side_slope=1.0
        ),
        ScenarioCreate(
            project_id=proj.id,
            name="Scenario 02 — 25% Breach (MacDonald 1984)",
            dam_height=26.0,
            dam_length=1000.0,
            dam_crest_elev=60.0,
            reservoir_volume=110000000.0,
            reservoir_level=24.0,
            reservoir_area=20000000.0,
            breach_formulation="MacDonald_1984",
            breach_type="Piping",
            breach_side_slope=0.5
        ),
        ScenarioCreate(
            project_id=proj.id,
            name="Scenario 03 — Full Breach (Von Thun 1990)",
            dam_height=26.0,
            dam_length=1000.0,
            dam_crest_elev=60.0,
            reservoir_volume=110000000.0,
            reservoir_level=26.0,
            reservoir_area=20000000.0,
            breach_formulation="VonThun_1990",
            breach_type="Overtopping",
            breach_side_slope=1.0
        )
    ]

    for s_in in scenarios_data:
        existing_s = db.query(Scenario).filter(Scenario.project_id == proj.id, Scenario.name == s_in.name).first()
        if not existing_s:
            s_obj = create_scenario(s_in, db)
            print(f"Created Scenario: {s_obj.name} (Breach Width: {s_obj.breach_width}m, Time: {s_obj.breach_time/60:.1f} min)")

    db.close()
    print("=== Demo Project Initialization Complete ===")

if __name__ == "__main__":
    init_machchhu_demo()
