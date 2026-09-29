import json
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from sqlalchemy.orm import Session
from backend.app.core.database import get_db
from backend.app.models.project import Project
from backend.app.models.scenario import Scenario
from backend.app.models.simulation import Simulation
from backend.app.exports.report_generator import ScientificReportGenerator

router = APIRouter(prefix="/api/reports", tags=["reports"])

@router.get("/generate/{sim_id}", response_class=HTMLResponse)
def generate_report(sim_id: str, db: Session = Depends(get_db)):
    sim = db.query(Simulation).filter(Simulation.id == sim_id).first()
    if not sim:
        raise HTTPException(status_code=404, detail="Simulation not found")
    proj = db.query(Project).filter(Project.id == sim.project_id).first()
    scen = db.query(Scenario).filter(Scenario.id == sim.scenario_id).first()

    impact = {}
    if sim.impact_json and Path(sim.impact_json).exists():
        with open(sim.impact_json, "r", encoding="utf-8") as f:
            impact = json.load(f)

    project_dict = {
        "name": proj.name,
        "river_name": proj.river_name,
        "dam_name": proj.dam_name,
        "dam_lat": proj.dam_lat,
        "dam_lon": proj.dam_lon
    }
    scenario_dict = {
        "dam_height": scen.dam_height,
        "dam_length": scen.dam_length,
        "reservoir_volume": scen.reservoir_volume,
        "reservoir_level": scen.reservoir_level,
        "breach_formulation": scen.breach_formulation,
        "breach_width": scen.breach_width,
        "breach_depth": scen.breach_depth,
        "breach_time": scen.breach_time,
        "breach_side_slope": scen.breach_side_slope
    }
    sim_dict = {
        "engine_name": sim.engine_name,
        "engine_status": sim.engine_status,
        "max_depth": sim.max_depth,
        "max_velocity": sim.max_velocity,
        "inundated_area_sqkm": sim.inundated_area_sqkm,
        "peak_discharge": sim.peak_discharge
    }
    impact_dict = {
        "affected_buildings_count": sim.affected_buildings_count,
        "affected_roads_km": sim.affected_roads_km,
        "exposed_population": sim.exposed_population,
        "building_risk": impact.get("buildings", {}).get("risk_breakdown", {})
    }

    out_html = Path(sim.results_dir) / "report.html" if sim.results_dir else None
    report_html = ScientificReportGenerator.generate_html_report(
        project_data=project_dict,
        scenario_data=scenario_dict,
        simulation_data=sim_dict,
        impact_data=impact_dict,
        output_path=str(out_html) if out_html else ""
    )

    return HTMLResponse(content=report_html, status_code=200)
