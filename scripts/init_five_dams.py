import sys
import os
import json
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.app.core.database import SessionLocal, engine, Base
from backend.app.models.project import Project
from backend.app.models.scenario import Scenario
from backend.app.hydrology.breach_base import BreachParameters
from backend.app.hydrology.hydrograph import HydrographGenerator

def init_five_dams_database():
    print("=== Initializing Generalized Five-Dam Architecture & Database ===")
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    data_dir = Path("data")
    slugs = ["idukki", "mettur", "hirakud", "srisailam", "tehri", "machchhu_demo"]

    for slug in slugs:
        cfg_dir = data_dir / slug
        meta_file = cfg_dir / "metadata.json"
        scen_file = cfg_dir / "scenarios.json"
        
        if not meta_file.exists():
            print(f"Warning: {meta_file} not found, skipping.")
            continue

        with open(meta_file, "r", encoding="utf-8") as f:
            meta = json.load(f)

        # Check existing by slug or name
        proj = db.query(Project).filter((Project.slug == slug) | (Project.name == meta["name"])).first()
        if not proj:
            proj = Project(
                slug=slug,
                name=meta["name"],
                river_name=meta["river_name"],
                country=meta.get("country", "India"),
                state=meta.get("state"),
                district=meta.get("district"),
                dam_name=meta["dam_name"],
                dam_lat=meta["latitude"],
                dam_lon=meta["longitude"],
                min_lat=meta["study_domain"]["min_lat"],
                min_lon=meta["study_domain"]["min_lon"],
                max_lat=meta["study_domain"]["max_lat"],
                max_lon=meta["study_domain"]["max_lon"],
                crs="EPSG:4326",
                projected_crs="EPSG:32643" if meta["longitude"] < 78.0 else "EPSG:32644",
                dam_height_m=meta.get("dam_height_m"),
                crest_length_m=meta.get("crest_length_m"),
                crest_elevation_m=meta.get("crest_elevation_m"),
                full_reservoir_level_m=meta.get("full_reservoir_level_m"),
                reservoir_capacity_m3=meta.get("reservoir_capacity_m3"),
                reservoir_area_m2=meta.get("reservoir_area_m2"),
                downstream_bearing_deg=meta.get("downstream_bearing_deg", 0.0),
                is_demo=meta.get("is_demo", False),
                data_status=meta.get("data_status", "NOT CONFIGURED")
            )
            # If Machchhu demo, set paths to existing demo files
            if slug == "machchhu_demo":
                dem_f = data_dir / "dem" / "ab1c93cc-c249-405d-bff1-23db8e347c11_dem.tif"
                if dem_f.exists():
                    proj.dem_path = str(dem_f)
                bldg_f = data_dir / "buildings" / "ab1c93cc-c249-405d-bff1-23db8e347c11_buildings.geojson"
                if bldg_f.exists():
                    proj.buildings_path = str(bldg_f)
                road_f = data_dir / "rivers" / "ab1c93cc-c249-405d-bff1-23db8e347c11_roads.geojson"
                if road_f.exists():
                    proj.roads_path = str(road_f)
                river_f = data_dir / "rivers" / "ab1c93cc-c249-405d-bff1-23db8e347c11_river.geojson"
                if river_f.exists():
                    proj.river_path = str(river_f)

            db.add(proj)
            db.commit()
            db.refresh(proj)
            print(f"[OK] Created Project: {proj.name} ({proj.slug}) -> ID: {proj.id}")
        else:
            # Update fields
            proj.slug = slug
            proj.dam_height_m = meta.get("dam_height_m")
            proj.crest_length_m = meta.get("crest_length_m")
            proj.crest_elevation_m = meta.get("crest_elevation_m")
            proj.full_reservoir_level_m = meta.get("full_reservoir_level_m")
            proj.reservoir_capacity_m3 = meta.get("reservoir_capacity_m3")
            proj.reservoir_area_m2 = meta.get("reservoir_area_m2")
            proj.downstream_bearing_deg = meta.get("downstream_bearing_deg", 0.0)
            proj.is_demo = meta.get("is_demo", False)
            proj.data_status = meta.get("data_status", "NOT CONFIGURED")
            db.commit()
            print(f"[OK] Updated Project: {proj.name} ({proj.slug}) -> ID: {proj.id}")

        # Seed scenarios for this project
        if scen_file.exists():
            with open(scen_file, "r", encoding="utf-8") as f:
                scens = json.load(f)

            for s_in in scens:
                existing_s = db.query(Scenario).filter(
                    Scenario.project_id == proj.id,
                    Scenario.name == s_in["name"]
                ).first()

                if not existing_s:
                    # Calculate breach parameters and hydrograph
                    params = BreachParameters(
                        dam_height=s_in["dam_height"],
                        dam_length=s_in["dam_length"],
                        reservoir_volume=s_in["reservoir_volume"],
                        reservoir_level=s_in["reservoir_level"],
                        reservoir_area=s_in.get("reservoir_area") or (s_in["reservoir_volume"] / max(1.0, s_in["reservoir_level"] * 0.5)),
                        failure_mode=s_in["breach_type"]
                    )
                    model = HydrographGenerator.get_model(s_in["breach_formulation"])
                    geom = model.calculate_geometry(params)

                    hydro_pts = HydrographGenerator.generate_hydrograph(
                        params=params,
                        formulation=s_in["breach_formulation"],
                        custom_geometry=geom,
                        total_duration_hours=6.0,
                        dt_seconds=60.0
                    )
                    hydro_json = json.dumps([p.dict() for p in hydro_pts])

                    s_obj = Scenario(
                        project_id=proj.id,
                        name=s_in["name"],
                        dam_height=s_in["dam_height"],
                        dam_length=s_in["dam_length"],
                        dam_crest_elev=s_in.get("dam_crest_elev", 0.0),
                        reservoir_volume=s_in["reservoir_volume"],
                        reservoir_level=s_in["reservoir_level"],
                        reservoir_area=params.reservoir_area,
                        breach_formulation=s_in["breach_formulation"],
                        breach_type=s_in["breach_type"],
                        breach_depth=geom.breach_depth,
                        breach_width=geom.breach_width_avg,
                        breach_time=geom.breach_time_sec,
                        breach_side_slope=geom.breach_side_slope_z,
                        status=s_in.get("status", "ready"),
                        hydrograph_json=hydro_json
                    )
                    db.add(s_obj)
                    db.commit()
                    print(f"     + Created Scenario: {s_obj.name} (Bavg={s_obj.breach_width:.1f}m, Qp={geom.peak_discharge_m3s:.0f} m³/s)")

    # Clean up any empty test dummy projects (projects with null slug and no scenarios)
    test_dummies = db.query(Project).filter(Project.slug.is_(None)).all()
    for td in test_dummies:
        has_scen = db.query(Scenario).filter(Scenario.project_id == td.id).count()
        if has_scen == 0:
            print(f"Removing empty test dummy project: {td.name} ({td.id})")
            db.delete(td)
    db.commit()

    db.close()
    
    # Run full canonical sync
    try:
        from backend.app.core.sync import sync_projects_and_scenarios
        sync_projects_and_scenarios()
        print("[OK] Synchronized projects & baseline scenarios with canonical disk datasets")
    except Exception as e:
        print(f"Sync warning: {e}")

    print("=== Five-Dam Database Seeding Complete ===")

if __name__ == "__main__":
    init_five_dams_database()
