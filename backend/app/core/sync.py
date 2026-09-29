import json
import logging
from pathlib import Path
from sqlalchemy.orm import Session
from backend.app.core.database import SessionLocal
from backend.app.core.config import settings
from backend.app.models.project import Project
from backend.app.models.scenario import Scenario
from backend.app.hydrodynamics.routing_engine import compute_breach_hydrograph

logger = logging.getLogger(__name__)

def sync_projects_and_scenarios(db: Session = None):
    """
    Synchronizes projects and scenarios from canonical files in data/<slug>/
    with the application SQLite database.
    Ensures that real validated datasets (DEM, river, buildings, roads) are registered,
    data_status is correctly assigned, and scenarios carry authoritative parameters.
    """
    should_close = False
    if db is None:
        db = SessionLocal()
        should_close = True

    try:
        data_dir = settings.DATA_DIR
        slugs = ["idukki", "mettur", "hirakud", "srisailam", "tehri", "machchhu_demo"]

        for slug in slugs:
            cfg_dir = data_dir / slug
            meta_file = cfg_dir / "metadata.json"
            datasets_file = cfg_dir / "datasets.json"
            baseline_file = cfg_dir / "scenarios" / "baseline_breach.json"

            if not meta_file.exists():
                continue

            with open(meta_file, "r", encoding="utf-8") as f:
                meta = json.load(f)

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
                    data_status="NOT CONFIGURED",
                    simulation_enabled=meta.get("simulation_enabled", False)
                )
                db.add(proj)
                db.commit()
                db.refresh(proj)

            # Sync dataset paths from datasets.json if available
            if datasets_file.exists():
                try:
                    with open(datasets_file, "r", encoding="utf-8") as f:
                        ds_meta = json.load(f)
                    datasets_cfg = ds_meta.get("datasets", {})

                    # DEM
                    dem_cfg = datasets_cfg.get("dem", {})
                    dem_p = dem_cfg.get("path") or dem_cfg.get("local_path")
                    if dem_p and (Path(dem_p).exists() or (data_dir.parent / dem_p).exists()):
                        proj.dem_path = dem_p

                    # River
                    riv_cfg = datasets_cfg.get("river", {})
                    riv_p = riv_cfg.get("path") or riv_cfg.get("local_path")
                    if riv_p and (Path(riv_p).exists() or (data_dir.parent / riv_p).exists()):
                        proj.river_path = riv_p

                    # Buildings
                    bldg_cfg = datasets_cfg.get("buildings", {})
                    bldg_p = bldg_cfg.get("path") or bldg_cfg.get("local_path")
                    if bldg_p and (Path(bldg_p).exists() or (data_dir.parent / bldg_p).exists()):
                        proj.buildings_path = bldg_p

                    # Roads
                    road_cfg = datasets_cfg.get("roads", {})
                    road_p = road_cfg.get("path") or road_cfg.get("local_path")
                    if road_p and (Path(road_p).exists() or (data_dir.parent / road_p).exists()):
                        proj.roads_path = road_p
                except Exception as e:
                    logger.warning(f"Error parsing datasets.json for {slug}: {e}")

            # Specific known locations for Mettur & Idukki
            if slug == "mettur":
                mettur_dem = "data/mettur/dem/processed/mettur_dem_30m.tif"
                mettur_riv = "data/mettur/river/cauvery_river.geojson"
                mettur_bldg = "data/mettur/buildings/buildings.geojson"
                mettur_road = "data/mettur/roads/roads.geojson"
                if Path(mettur_dem).exists():
                    proj.dem_path = mettur_dem
                if Path(mettur_riv).exists():
                    proj.river_path = mettur_riv
                if Path(mettur_bldg).exists():
                    proj.buildings_path = mettur_bldg
                if Path(mettur_road).exists():
                    proj.roads_path = mettur_road
                proj.data_status = "CONFIGURED"
                proj.simulation_enabled = True

            elif slug == "idukki":
                idukki_dem = "data/idukki/dem/processed/idukki_dem_30m.tif"
                idukki_riv = "data/idukki/river/periyar_river.geojson"
                idukki_bldg = "data/idukki/buildings/idukki_buildings.geojson"
                idukki_road = "data/idukki/roads/idukki_roads.geojson"
                if Path(idukki_dem).exists():
                    proj.dem_path = idukki_dem
                if Path(idukki_riv).exists():
                    proj.river_path = idukki_riv
                if Path(idukki_bldg).exists():
                    proj.buildings_path = idukki_bldg
                if Path(idukki_road).exists():
                    proj.roads_path = idukki_road
                proj.data_status = "READY"
                proj.simulation_enabled = True

            elif slug == "tehri":
                tehri_dem = "data/tehri/dem/processed/tehri_dem_30m.tif"
                tehri_riv = "data/tehri/river/bhagirathi_river.geojson"
                tehri_bldg = "data/tehri/buildings/tehri_buildings.geojson"
                tehri_road = "data/tehri/roads/tehri_roads.geojson"
                if Path(tehri_dem).exists():
                    proj.dem_path = tehri_dem
                if Path(tehri_riv).exists():
                    proj.river_path = tehri_riv
                if Path(tehri_bldg).exists():
                    proj.buildings_path = tehri_bldg
                if Path(tehri_road).exists():
                    proj.roads_path = tehri_road
                proj.data_status = "READY"
                proj.simulation_enabled = True

            elif slug == "machchhu_demo":
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
                proj.data_status = "READY"
                proj.simulation_enabled = True

            # General status determination
            if proj.dem_path and Path(proj.dem_path).exists() and proj.river_path and Path(proj.river_path).exists():
                if proj.data_status not in ["READY", "CONFIGURED"]:
                    proj.data_status = "CONFIGURED"

            # Always ensure the 5 target study dams have simulation_enabled=True
            if slug in ["idukki", "mettur", "hirakud", "srisailam", "tehri"]:
                proj.simulation_enabled = True

            db.commit()

            # Sync Scenario 01 from baseline_breach.json if present
            if baseline_file.exists():
                try:
                    with open(baseline_file, "r", encoding="utf-8") as f:
                        sc_raw = json.load(f)

                    # Extract parameters
                    def _val(node):
                        return node["value"] if isinstance(node, dict) and "value" in node else node

                    if slug in ("mettur", "tehri"):
                        rs = sc_raw["reservoir_initial_state"]
                        bp = sc_raw["breach_parameters"]
                        ctrl = sc_raw["simulation_controls"]

                        v_active = float(_val(rs["active_breach_volume_m3"]))
                        h_init = float(_val(rs["initial_water_level_m"]))
                        a_surf = float(_val(rs["surface_area_m2"]))
                        wb = float(_val(bp["breach_bottom_width_m"]))
                        hb = float(_val(bp["breach_depth_m"]))
                        z_slope = float(_val(bp["breach_side_slope_z"]))
                        tf_sec = float(_val(bp["breach_formation_time_sec"]))
                        dur_sec = float(_val(ctrl["simulation_duration_sec"]))

                        dam_cfg = {
                            "active_breach_volume_m3": v_active,
                            "surface_area_m2": a_surf,
                            "initial_water_level_m": h_init,
                            "breach_bottom_width_m": wb,
                            "breach_side_slope_z": z_slope,
                            "breach_depth_m": hb,
                            "breach_formation_time_sec": tf_sec,
                            "simulation_duration_sec": dur_sec
                        }
                        hydro_recs, _ = compute_breach_hydrograph(dam_cfg, dt_sec=60.0)
                        hydro_json = json.dumps(hydro_recs)

                        # Update or create scenario in DB
                        scen = db.query(Scenario).filter(
                            Scenario.project_id == proj.id,
                            Scenario.name.ilike("%Scenario 01%")
                        ).first()
                        if scen:
                            scen.reservoir_volume = v_active
                            scen.reservoir_level = h_init
                            scen.reservoir_area = a_surf
                            scen.dam_height = hb
                            scen.breach_width = wb
                            scen.breach_depth = hb
                            scen.breach_time = tf_sec
                            scen.breach_side_slope = z_slope
                            scen.hydrograph_json = hydro_json
                            scen.status = "ready"
                            db.commit()

                    elif slug == "idukki":
                        rs = sc_raw["reservoir_parameters"]
                        bp = sc_raw["breach_parameters"]
                        ctrl = sc_raw["simulation_controls"]

                        v_active = float(_val(rs["active_breach_volume_basis_m3"]))
                        h_init = float(_val(rs["initial_water_level_m"]))
                        a_surf = float(_val(rs["surface_area_m2"]))
                        wb = float(_val(bp["breach_bottom_width_m"]))
                        hb = float(_val(bp["breach_depth_m"]))
                        z_slope = float(_val(bp["breach_side_slope_z"]))
                        tf_sec = float(_val(bp["breach_formation_time_hr"])) * 3600.0
                        dur_sec = float(ctrl.get("simulation_duration_hr", 6.0)) * 3600.0

                        dam_cfg = {
                            "active_breach_volume_m3": v_active,
                            "surface_area_m2": a_surf,
                            "initial_water_level_m": h_init,
                            "breach_bottom_width_m": wb,
                            "breach_side_slope_z": z_slope,
                            "breach_depth_m": hb,
                            "breach_formation_time_sec": tf_sec,
                            "simulation_duration_sec": dur_sec
                        }
                        hydro_recs, _ = compute_breach_hydrograph(dam_cfg, dt_sec=60.0)
                        hydro_json = json.dumps(hydro_recs)

                        scen = db.query(Scenario).filter(
                            Scenario.project_id == proj.id,
                            Scenario.name.ilike("%Scenario 01%")
                        ).first()
                        if scen:
                            scen.reservoir_volume = v_active
                            scen.reservoir_level = h_init
                            scen.reservoir_area = a_surf
                            scen.dam_height = 168.91
                            scen.breach_width = wb
                            scen.breach_depth = hb
                            scen.breach_time = tf_sec
                            scen.breach_side_slope = z_slope
                            scen.hydrograph_json = hydro_json
                            scen.status = "ready"
                            db.commit()
                except Exception as e:
                    logger.warning(f"Error syncing baseline scenario for {slug}: {e}")

        # Seed Natural Disaster & River Blockage Scenarios (Rishi Ganga / Phuktal / Kosi analogs)
        sync_natural_hazard_scenarios(db)

    finally:
        if should_close:
            db.close()

def sync_natural_hazard_scenarios(db: Session):
    """
    Seeds authoritative River Blockage, Landslide Lake Outburst (GLOF / Rishi Ganga 2021 analog),
    and Sudden Water Surge scenarios into the database for Tehri and Mettur dams.
    """
    # 1. Tehri Dam (Uttarakhand - Himalayan river blockage & rock-ice avalanche analog)
    tehri = db.query(Project).filter(Project.slug == "tehri").first()
    if tehri:
        scen_name = "Scenario 04 — River Blockage & Landslide Lake Outburst (Rishi Ganga 2021 Analog)"
        existing = db.query(Scenario).filter(
            Scenario.project_id == tehri.id,
            Scenario.name == scen_name
        ).first()

        dam_cfg = {
            "active_breach_volume_m3": 350e6,
            "surface_area_m2": 28e6,
            "initial_water_level_m": 255.0,
            "breach_bottom_width_m": 95.0,
            "breach_side_slope_z": 0.8,
            "breach_depth_m": 180.0,
            "breach_formation_time_sec": 1800.0,  # 30 min rapid surge
            "simulation_duration_sec": 14400.0
        }
        hydro_recs, _ = compute_breach_hydrograph(dam_cfg, dt_sec=60.0)
        hydro_json = json.dumps(hydro_recs)

        if not existing:
            new_scen = Scenario(
                project_id=tehri.id,
                name=scen_name,
                dam_height=260.5,
                dam_length=575.0,
                dam_crest_elev=839.5,
                reservoir_volume=350e6,
                reservoir_level=255.0,
                reservoir_area=28e6,
                breach_formulation="Froehlich_2008",
                breach_type="Landslide Dam Burst",
                breach_depth=180.0,
                breach_width=95.0,
                breach_time=1800.0,
                breach_side_slope=0.8,
                manning_n=0.040,
                status="ready",
                hydrograph_json=hydro_json
            )
            db.add(new_scen)
            db.commit()

    # 2. Mettur Dam (Tamil Nadu - River blockage collapse & sudden inflow surge)
    mettur = db.query(Project).filter(Project.slug == "mettur").first()
    if mettur:
        scen_name = "Scenario 04 — River Blockage & Sudden Water Surge Release (Extreme Flash Flood)"
        existing = db.query(Scenario).filter(
            Scenario.project_id == mettur.id,
            Scenario.name == scen_name
        ).first()

        dam_cfg = {
            "active_breach_volume_m3": 450e6,
            "surface_area_m2": 153e6,
            "initial_water_level_m": 65.0,
            "breach_bottom_width_m": 140.0,
            "breach_side_slope_z": 1.2,
            "breach_depth_m": 55.0,
            "breach_formation_time_sec": 3600.0,  # 1 hour sudden release
            "simulation_duration_sec": 21600.0
        }
        hydro_recs, _ = compute_breach_hydrograph(dam_cfg, dt_sec=60.0)
        hydro_json = json.dumps(hydro_recs)

        if not existing:
            new_scen = Scenario(
                project_id=mettur.id,
                name=scen_name,
                dam_height=65.23,
                dam_length=1615.0,
                dam_crest_elev=240.79,
                reservoir_volume=450e6,
                reservoir_level=65.0,
                reservoir_area=153e6,
                breach_formulation="MacDonald_1984",
                breach_type="River Blockage Sudden Surge",
                breach_depth=55.0,
                breach_width=140.0,
                breach_time=3600.0,
                breach_side_slope=1.2,
                manning_n=0.035,
                status="ready",
                hydrograph_json=hydro_json
            )
            db.add(new_scen)
            db.commit()
