from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
from pathlib import Path
import json
from backend.app.core.database import get_db
from backend.app.core.config import settings
from backend.app.models.project import Project
from backend.app.models.scenario import Scenario
from backend.app.models.simulation import Simulation
from backend.app.models.schemas import ProjectCreate, ProjectResponse, ProjectStatusResponse, DatasetsResponse

router = APIRouter(prefix="/api/projects", tags=["projects"])

def get_utm_epsg(lon: float, lat: float) -> str:
    zone = int((lon + 180) / 6) + 1
    if lat >= 0:
        return f"EPSG:{32600 + zone}"
    else:
        return f"EPSG:{32700 + zone}"

@router.get("", response_model=List[ProjectResponse])
def list_projects(
    search: Optional[str] = None,
    state: Optional[str] = None,
    river: Optional[str] = None,
    simulation_enabled: Optional[bool] = None,
    db: Session = Depends(get_db)
):
    query = db.query(Project)
    if search:
        search_term = f"%{search}%"
        query = query.filter(
            Project.name.ilike(search_term) |
            Project.dam_name.ilike(search_term) |
            Project.river_name.ilike(search_term) |
            Project.state.ilike(search_term)
        )
    if state:
        query = query.filter(Project.state.ilike(f"%{state}%"))
    if river:
        query = query.filter(Project.river_name.ilike(f"%{river}%"))
    if simulation_enabled is not None:
        query = query.filter(Project.simulation_enabled == simulation_enabled)

    return query.order_by(Project.simulation_enabled.desc(), Project.is_demo.asc(), Project.name.asc()).all()

@router.post("", response_model=ProjectResponse)
def create_project(project_in: ProjectCreate, db: Session = Depends(get_db)):
    utm_crs = get_utm_epsg(project_in.dam_lon, project_in.dam_lat)
    project = Project(
        name=project_in.name,
        slug=project_in.slug or project_in.name.lower().replace(" ", "_"),
        river_name=project_in.river_name,
        country=project_in.country,
        state=project_in.state,
        district=project_in.district,
        dam_name=project_in.dam_name,
        dam_lat=project_in.dam_lat,
        dam_lon=project_in.dam_lon,
        min_lat=project_in.min_lat,
        min_lon=project_in.min_lon,
        max_lat=project_in.max_lat,
        max_lon=project_in.max_lon,
        crs=project_in.crs,
        projected_crs=utm_crs,
        is_demo=project_in.is_demo,
        data_status=project_in.data_status,
        downstream_bearing_deg=project_in.downstream_bearing_deg or 0.0,
        dam_height_m=project_in.dam_height_m,
        crest_length_m=project_in.crest_length_m,
        crest_elevation_m=project_in.crest_elevation_m,
        full_reservoir_level_m=project_in.full_reservoir_level_m,
        reservoir_capacity_m3=project_in.reservoir_capacity_m3,
        reservoir_area_m2=project_in.reservoir_area_m2
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return project

@router.get("/{project_id}", response_model=ProjectResponse)
def get_project(project_id: str, db: Session = Depends(get_db)):
    project = db.query(Project).filter((Project.id == project_id) | (Project.slug == project_id)).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project

@router.get("/{project_id}/status", response_model=ProjectStatusResponse)
def get_project_status(project_id: str, db: Session = Depends(get_db)):
    project = db.query(Project).filter((Project.id == project_id) | (Project.slug == project_id)).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Read datasets registry from canonical files if present
    slug = project.slug or project_id
    config_dir = settings.DATA_DIR / slug
    datasets_file = config_dir / "datasets.json"

    datasets_map = {
        "dem": "ready" if (project.dem_path and Path(project.dem_path).exists()) else "not_configured",
        "river": "ready" if (project.river_path and Path(project.river_path).exists()) else "not_configured",
        "reservoir": "not_configured",
        "buildings": "ready" if (project.buildings_path and Path(project.buildings_path).exists()) else "not_configured",
        "roads": "ready" if (project.roads_path and Path(project.roads_path).exists()) else "not_configured",
        "population": "not_configured",
        "satellite": "not_configured"
    }

    if datasets_file.exists():
        try:
            with open(datasets_file, "r", encoding="utf-8") as f:
                d_data = json.load(f)
                for k, v in d_data.get("datasets", {}).items():
                    if isinstance(v, dict):
                        st = v.get("status", "not_configured").lower()
                        if st in ["ready", "valid", "configured", "available"]:
                            datasets_map[k] = "ready"
                        else:
                            datasets_map[k] = st
        except Exception:
            pass

    # If reservoir GeoJSON file exists on disk, mark as ready
    res_path = config_dir / "reservoir"
    if res_path.exists() and any(res_path.glob("*.geojson")):
        datasets_map["reservoir"] = "ready"

    scenarios = db.query(Scenario).filter(Scenario.project_id == project.id).all()
    scenarios_map = {}
    for s in scenarios:
        scenarios_map[s.breach_formulation] = getattr(s, "status", "ready")

    sim_count = db.query(Simulation).filter(Simulation.project_id == project.id).count()

    return ProjectStatusResponse(
        project_id=project.id,
        slug=project.slug,
        name=project.name,
        data_status=project.data_status,
        is_demo=project.is_demo,
        simulation_enabled=getattr(project, "simulation_enabled", False) or False,
        datasets=datasets_map,
        scenarios=scenarios_map,
        simulations_count=sim_count,
        validation_status="ready" if (sim_count > 0 and project.data_status in ["READY", "CONFIGURED"]) else "unvalidated"
    )

@router.get("/{project_id}/datasets", response_model=DatasetsResponse)
def get_project_datasets(project_id: str, db: Session = Depends(get_db)):
    project = db.query(Project).filter((Project.id == project_id) | (Project.slug == project_id)).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    slug = project.slug or project_id
    config_dir = settings.DATA_DIR / slug
    datasets_file = config_dir / "datasets.json"

    datasets_dict = {
        "dem": {
            "status": "ready" if (project.dem_path and Path(project.dem_path).exists()) else "not_configured",
            "path": project.dem_path,
            "source": "Copernicus DEM GLO-30 / SRTM" if (project.dem_path and Path(project.dem_path).exists()) else None,
            "resolution_m": 30.0 if (project.dem_path and Path(project.dem_path).exists()) else None,
            "crs": project.crs
        },
        "river": {
            "status": "ready" if (project.river_path and Path(project.river_path).exists()) else "not_configured",
            "path": project.river_path,
            "source": "OpenStreetMap Waterways" if (project.river_path and Path(project.river_path).exists()) else None,
            "crs": project.crs
        },
        "reservoir": {
            "status": "not_configured",
            "path": None,
            "source": "OpenStreetMap Waterbody / State WRD",
            "crs": project.crs
        },
        "buildings": {
            "status": "ready" if (project.buildings_path and Path(project.buildings_path).exists()) else "not_configured",
            "path": project.buildings_path,
            "source": "OpenStreetMap Building Footprints" if (project.buildings_path and Path(project.buildings_path).exists()) else None,
            "crs": project.crs
        },
        "roads": {
            "status": "ready" if (project.roads_path and Path(project.roads_path).exists()) else "not_configured",
            "path": project.roads_path,
            "source": "OpenStreetMap Road Network" if (project.roads_path and Path(project.roads_path).exists()) else None,
            "crs": project.crs
        },
        "population": {
            "status": "not_configured",
            "path": None,
            "source": "Census of India / WorldPop",
            "resolution": "100m"
        },
        "satellite": {
            "status": "not_configured",
            "source": "Copernicus Sentinel-1 SAR (requires GEE or localized files)"
        }
    }

    if datasets_file.exists():
        try:
            with open(datasets_file, "r", encoding="utf-8") as f:
                raw_d = json.load(f)
                file_datasets = raw_d.get("datasets", {})
                for k, v in file_datasets.items():
                    if isinstance(v, dict):
                        # Normalize path
                        p = v.get("path") or v.get("local_path")
                        st = v.get("status", "not_configured")
                        entry = {**v, "status": st}
                        if p:
                            entry["path"] = p
                        datasets_dict[k] = entry
        except Exception:
            pass

    # Ensure reservoir status if file is present
    res_dir = config_dir / "reservoir"
    if res_dir.exists():
        res_files = list(res_dir.glob("*.geojson"))
        if res_files:
            if datasets_dict["reservoir"].get("status") in [None, "not_configured"]:
                datasets_dict["reservoir"]["status"] = "READY"
            datasets_dict["reservoir"]["path"] = str(res_files[0])

    return DatasetsResponse(
        dam_id=slug,
        project_id=project.id,
        slug=project.slug,
        dam_name=project.dam_name,
        data_status=project.data_status,
        datasets=datasets_dict
    )

@router.get("/{project_id}/scenarios")
def get_project_scenarios(project_id: str, db: Session = Depends(get_db)):
    project = db.query(Project).filter((Project.id == project_id) | (Project.slug == project_id)).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    scenarios = db.query(Scenario).filter(Scenario.project_id == project.id).all()
    res = []
    for s in scenarios:
        item = {
            "id": s.id,
            "project_id": s.project_id,
            "name": s.name,
            "dam_height": s.dam_height,
            "dam_length": s.dam_length,
            "reservoir_volume": s.reservoir_volume,
            "reservoir_level": s.reservoir_level,
            "breach_formulation": s.breach_formulation,
            "breach_type": s.breach_type,
            "breach_width": s.breach_width,
            "breach_depth": s.breach_depth,
            "breach_time": s.breach_time,
            "status": getattr(s, "status", "ready"),
            "created_at": s.created_at
        }
        res.append(item)
    return res

@router.delete("/{project_id}")
def delete_project(project_id: str, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    db.delete(project)
    db.commit()
    return {"status": "success", "message": f"Project {project_id} deleted"}
