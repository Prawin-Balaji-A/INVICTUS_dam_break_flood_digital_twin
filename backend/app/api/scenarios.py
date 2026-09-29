import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from backend.app.core.database import get_db
from backend.app.models.scenario import Scenario
from backend.app.models.schemas import ScenarioCreate, ScenarioResponse
from backend.app.hydrology.breach_base import BreachParameters
from backend.app.hydrology.hydrograph import HydrographGenerator

router = APIRouter(prefix="/api/scenarios", tags=["scenarios"])

@router.get("/project/{project_id}")
def list_project_scenarios(project_id: str, db: Session = Depends(get_db)):
    scenarios = db.query(Scenario).filter(Scenario.project_id == project_id).all()
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
            "created_at": s.created_at
        }
        res.append(item)
    return res

@router.post("", response_model=ScenarioResponse)
def create_scenario(scen_in: ScenarioCreate, db: Session = Depends(get_db)):
    params = BreachParameters(
        dam_height=scen_in.dam_height,
        dam_length=scen_in.dam_length,
        reservoir_volume=scen_in.reservoir_volume,
        reservoir_level=scen_in.reservoir_level,
        reservoir_area=scen_in.reservoir_area or (scen_in.reservoir_volume / max(1.0, scen_in.reservoir_level * 0.5)),
        failure_mode="Overtopping" if "overtop" in scen_in.breach_type.lower() else "Piping"
    )

    # Compute empirical geometry
    model = HydrographGenerator.get_model(scen_in.breach_formulation)
    geom = model.calculate_geometry(params)

    # Override with manual inputs if provided
    b_width = scen_in.breach_width or geom.breach_width_avg
    b_depth = scen_in.breach_depth or geom.breach_depth
    b_time = scen_in.breach_time or geom.breach_time_sec

    geom.breach_bottom_width = b_width
    geom.breach_width_avg = b_width
    geom.breach_depth = b_depth
    geom.breach_time_sec = b_time
    if scen_in.breach_side_slope:
        geom.breach_side_slope_z = scen_in.breach_side_slope
    geom.breach_top_width = b_width + 2 * geom.breach_side_slope_z * b_depth

    # Generate hydrograph
    hydro_pts = HydrographGenerator.generate_hydrograph(
        params=params,
        formulation=scen_in.breach_formulation,
        custom_geometry=geom,
        total_duration_hours=6.0,
        dt_seconds=60.0
    )
    hydro_json = json.dumps([p.dict() for p in hydro_pts])

    scen = Scenario(
        project_id=scen_in.project_id,
        name=scen_in.name,
        dam_height=scen_in.dam_height,
        dam_length=scen_in.dam_length,
        dam_crest_elev=scen_in.dam_crest_elev,
        reservoir_volume=scen_in.reservoir_volume,
        reservoir_level=scen_in.reservoir_level,
        reservoir_area=params.reservoir_area,
        breach_formulation=scen_in.breach_formulation,
        breach_type=scen_in.breach_type,
        breach_depth=b_depth,
        breach_width=b_width,
        breach_time=b_time,
        breach_side_slope=geom.breach_side_slope_z,
        manning_n=scen_in.manning_n or 0.035,
        hydrograph_json=hydro_json
    )
    db.add(scen)
    db.commit()
    db.refresh(scen)
    return scen

@router.post("/preview")
def preview_scenario_hydrograph(scen_in: ScenarioCreate):
    """Compute instant live preview of breach geometry and hydrograph without saving to database."""
    params = BreachParameters(
        dam_height=scen_in.dam_height,
        dam_length=scen_in.dam_length,
        reservoir_volume=scen_in.reservoir_volume,
        reservoir_level=scen_in.reservoir_level,
        reservoir_area=scen_in.reservoir_area or (scen_in.reservoir_volume / max(1.0, scen_in.reservoir_level * 0.5)),
        failure_mode="Overtopping" if "overtop" in scen_in.breach_type.lower() else "Piping"
    )
    model = HydrographGenerator.get_model(scen_in.breach_formulation)
    geom = model.calculate_geometry(params)

    b_width = scen_in.breach_width or geom.breach_width_avg
    b_depth = scen_in.breach_depth or geom.breach_depth
    b_time = scen_in.breach_time or geom.breach_time_sec

    geom.breach_bottom_width = b_width
    geom.breach_width_avg = b_width
    geom.breach_depth = b_depth
    geom.breach_time_sec = b_time
    if scen_in.breach_side_slope:
        geom.breach_side_slope_z = scen_in.breach_side_slope
    geom.breach_top_width = b_width + 2 * geom.breach_side_slope_z * b_depth

    hydro_pts = HydrographGenerator.generate_hydrograph(
        params=params,
        formulation=scen_in.breach_formulation,
        custom_geometry=geom,
        total_duration_hours=6.0,
        dt_seconds=60.0
    )

    max_q = 0.0
    time_to_peak_min = 0.0
    hydro_list = []
    for p in hydro_pts:
        q = p.discharge_m3s
        t_min = p.time_sec / 60.0
        if q > max_q:
            max_q = q
            time_to_peak_min = t_min
        if int(p.time_sec) % 300 == 0:
            hydro_list.append({
                "time_min": round(t_min, 1),
                "discharge_m3s": round(q, 1),
                "stage_m": round(p.stage_m, 2)
            })

    return {
        "peak_discharge_m3s": round(max_q, 1),
        "time_to_peak_min": round(time_to_peak_min, 1),
        "breach_width_m": round(b_width, 1),
        "breach_time_min": round(b_time / 60.0, 1),
        "breach_depth_m": round(b_depth, 1),
        "reservoir_volume_mcm": round(scen_in.reservoir_volume / 1e6, 2),
        "reservoir_level_m": round(scen_in.reservoir_level, 2),
        "hydrograph": hydro_list
    }

@router.post("/custom", response_model=ScenarioResponse)
def create_or_update_custom_scenario(scen_in: ScenarioCreate, db: Session = Depends(get_db)):
    """Create or update a dedicated custom scenario for manual parameter simulation."""
    target_name = scen_in.name or "Scenario — Custom Manual Simulation"

    existing = db.query(Scenario).filter(
        Scenario.project_id == scen_in.project_id,
        Scenario.name == target_name
    ).first()

    params = BreachParameters(
        dam_height=scen_in.dam_height,
        dam_length=scen_in.dam_length,
        reservoir_volume=scen_in.reservoir_volume,
        reservoir_level=scen_in.reservoir_level,
        reservoir_area=scen_in.reservoir_area or (scen_in.reservoir_volume / max(1.0, scen_in.reservoir_level * 0.5)),
        failure_mode="Overtopping" if "overtop" in scen_in.breach_type.lower() else "Piping"
    )

    model = HydrographGenerator.get_model(scen_in.breach_formulation)
    geom = model.calculate_geometry(params)

    b_width = scen_in.breach_width or geom.breach_width_avg
    b_depth = scen_in.breach_depth or geom.breach_depth
    b_time = scen_in.breach_time or geom.breach_time_sec

    geom.breach_bottom_width = b_width
    geom.breach_width_avg = b_width
    geom.breach_depth = b_depth
    geom.breach_time_sec = b_time
    if scen_in.breach_side_slope:
        geom.breach_side_slope_z = scen_in.breach_side_slope
    geom.breach_top_width = b_width + 2 * geom.breach_side_slope_z * b_depth

    hydro_pts = HydrographGenerator.generate_hydrograph(
        params=params,
        formulation=scen_in.breach_formulation,
        custom_geometry=geom,
        total_duration_hours=6.0,
        dt_seconds=60.0
    )
    hydro_json = json.dumps([p.dict() for p in hydro_pts])

    if existing:
        existing.dam_height = scen_in.dam_height
        existing.dam_length = scen_in.dam_length
        existing.dam_crest_elev = scen_in.dam_crest_elev
        existing.reservoir_volume = scen_in.reservoir_volume
        existing.reservoir_level = scen_in.reservoir_level
        existing.reservoir_area = params.reservoir_area
        existing.breach_formulation = scen_in.breach_formulation
        existing.breach_type = scen_in.breach_type
        existing.breach_depth = b_depth
        existing.breach_width = b_width
        existing.breach_time = b_time
        existing.breach_side_slope = geom.breach_side_slope_z
        existing.manning_n = scen_in.manning_n or 0.035
        existing.hydrograph_json = hydro_json
        db.commit()
        db.refresh(existing)
        return existing

    scen = Scenario(
        project_id=scen_in.project_id,
        name=target_name,
        dam_height=scen_in.dam_height,
        dam_length=scen_in.dam_length,
        dam_crest_elev=scen_in.dam_crest_elev,
        reservoir_volume=scen_in.reservoir_volume,
        reservoir_level=scen_in.reservoir_level,
        reservoir_area=params.reservoir_area,
        breach_formulation=scen_in.breach_formulation,
        breach_type=scen_in.breach_type,
        breach_depth=b_depth,
        breach_width=b_width,
        breach_time=b_time,
        breach_side_slope=geom.breach_side_slope_z,
        manning_n=scen_in.manning_n or 0.035,
        hydrograph_json=hydro_json
    )
    db.add(scen)
    db.commit()
    db.refresh(scen)
    return scen

@router.get("/{scenario_id}")
def get_scenario(scenario_id: str, db: Session = Depends(get_db)):
    scen = db.query(Scenario).filter(Scenario.id == scenario_id).first()
    if not scen:
        raise HTTPException(status_code=404, detail="Scenario not found")

    hydro = []
    if scen.hydrograph_json:
        hydro = json.loads(scen.hydrograph_json)

    return {
        "id": scen.id,
        "project_id": scen.project_id,
        "name": scen.name,
        "dam_height": scen.dam_height,
        "dam_length": scen.dam_length,
        "reservoir_volume": scen.reservoir_volume,
        "reservoir_level": scen.reservoir_level,
        "breach_formulation": scen.breach_formulation,
        "breach_type": scen.breach_type,
        "breach_width": scen.breach_width,
        "breach_depth": scen.breach_depth,
        "breach_time": scen.breach_time,
        "breach_side_slope": scen.breach_side_slope,
        "peak_discharge_m3s": max([p.get("discharge_m3s", 0) for p in hydro]) if hydro else 0.0,
        "hydrograph": hydro
    }
