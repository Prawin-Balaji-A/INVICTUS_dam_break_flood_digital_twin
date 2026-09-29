from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List, Dict, Any
from datetime import datetime

class ProjectCreate(BaseModel):
    name: str = Field(..., json_schema_extra={"example": "Machchhu Dam-II Disaster Simulation"})
    river_name: str = Field(..., json_schema_extra={"example": "Machchhu River"})
    country: str = Field("India", json_schema_extra={"example": "India"})
    state: Optional[str] = Field("Gujarat", json_schema_extra={"example": "Gujarat"})
    district: Optional[str] = Field("Morbi", json_schema_extra={"example": "Morbi"})
    dam_name: str = Field(..., json_schema_extra={"example": "Machchhu Dam-II"})
    dam_lat: float = Field(..., json_schema_extra={"example": 22.7750})
    dam_lon: float = Field(..., json_schema_extra={"example": 70.8986})
    min_lat: float = Field(..., json_schema_extra={"example": 22.7400})
    min_lon: float = Field(..., json_schema_extra={"example": 70.8300})
    max_lat: float = Field(..., json_schema_extra={"example": 22.8400})
    max_lon: float = Field(..., json_schema_extra={"example": 70.9300})
    crs: str = Field("EPSG:4326")
    slug: Optional[str] = None
    is_demo: bool = False
    simulation_enabled: bool = False
    dam_type: Optional[str] = None
    operator: Optional[str] = None
    source_provenance: Optional[str] = None
    data_status: str = "NOT CONFIGURED"
    downstream_bearing_deg: Optional[float] = 0.0
    dam_height_m: Optional[float] = None
    crest_length_m: Optional[float] = None
    crest_elevation_m: Optional[float] = None
    full_reservoir_level_m: Optional[float] = None
    reservoir_capacity_m3: Optional[float] = None
    reservoir_area_m2: Optional[float] = None

class ProjectResponse(BaseModel):
    id: str
    slug: Optional[str] = None
    name: str
    river_name: str
    country: str
    state: Optional[str] = None
    district: Optional[str] = None
    dam_name: str
    dam_lat: float
    dam_lon: float
    min_lat: float
    min_lon: float
    max_lat: float
    max_lon: float
    crs: str
    projected_crs: Optional[str] = None
    downstream_bearing_deg: Optional[float] = 0.0
    dam_height_m: Optional[float] = None
    crest_length_m: Optional[float] = None
    crest_elevation_m: Optional[float] = None
    full_reservoir_level_m: Optional[float] = None
    reservoir_capacity_m3: Optional[float] = None
    reservoir_area_m2: Optional[float] = None
    is_demo: bool = False
    simulation_enabled: bool = False
    dam_type: Optional[str] = None
    operator: Optional[str] = None
    source_provenance: Optional[str] = None
    data_status: str = "NOT CONFIGURED"
    dem_path: Optional[str] = None
    hillshade_path: Optional[str] = None
    slope_path: Optional[str] = None
    river_path: Optional[str] = None
    buildings_path: Optional[str] = None
    roads_path: Optional[str] = None
    landuse_path: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class ProjectStatusResponse(BaseModel):
    project_id: str
    slug: Optional[str] = None
    name: str
    data_status: str
    is_demo: bool
    simulation_enabled: bool = False
    datasets: Dict[str, str]
    scenarios: Dict[str, str]
    simulations_count: int
    validation_status: str

class DatasetItem(BaseModel):
    name: str
    type: str
    status: str
    path: Optional[str] = None
    source: Optional[str] = None
    resolution: Optional[str] = None
    crs: Optional[str] = None

class DatasetsResponse(BaseModel):
    dam_id: Optional[str] = None
    project_id: str
    slug: Optional[str] = None
    dam_name: str
    data_status: str
    datasets: Dict[str, Any]

class ScenarioCreate(BaseModel):
    project_id: str
    name: str = Field(..., json_schema_extra={"example": "Scenario 01 - 50% Breach Froehlich"})
    dam_height: float = Field(..., json_schema_extra={"example": 26.0}) # meters
    dam_length: float = Field(..., json_schema_extra={"example": 1000.0}) # meters
    dam_crest_elev: Optional[float] = Field(60.0, json_schema_extra={"example": 60.0})
    reservoir_volume: float = Field(..., json_schema_extra={"example": 110000000.0}) # m^3
    reservoir_level: float = Field(..., json_schema_extra={"example": 24.0}) # meters
    reservoir_area: Optional[float] = Field(20000000.0, json_schema_extra={"example": 20000000.0}) # m^2
    breach_formulation: str = Field("Froehlich_2008", json_schema_extra={"example": "Froehlich_2008"}) # Froehlich_2008, MacDonald_1984, VonThun_1990
    breach_type: str = Field("Gradual", json_schema_extra={"example": "Gradual"})
    breach_depth: Optional[float] = None
    breach_width: Optional[float] = None
    breach_time: Optional[float] = None
    breach_side_slope: float = Field(1.0, json_schema_extra={"example": 1.0})
    manning_n: Optional[float] = Field(0.035, json_schema_extra={"example": 0.035})
    status: str = "ready"

class ScenarioResponse(BaseModel):
    id: str
    project_id: str
    name: str
    dam_height: float
    dam_length: float
    dam_crest_elev: Optional[float]
    reservoir_volume: float
    reservoir_level: float
    reservoir_area: Optional[float]
    breach_formulation: str
    breach_type: str
    breach_depth: float
    breach_width: float
    breach_time: float
    breach_side_slope: float
    manning_n: Optional[float] = 0.035
    status: str = "ready"
    hydrograph_json: Optional[str]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class SimulationCreate(BaseModel):
    project_id: str
    scenario_id: str
    engine_name: str = Field("Experimental SPH Solver", json_schema_extra={"example": "Experimental SPH Solver"}) # or "Delft3D"

class SimulationStatusResponse(BaseModel):
    id: str
    project_id: str
    scenario_id: str
    engine_name: str
    engine_status: str
    status: str
    progress: float
    message: Optional[str] = None
    error_message: Optional[str] = None
    logs: List[str] = []

    model_config = ConfigDict(from_attributes=True)

class BenchmarkRunRequest(BaseModel):
    benchmark_name: str = Field("Ritter_1892", json_schema_extra={"example": "Ritter_1892"}) # "Ritter_1892" or "Martin_Moyce_1952"
    num_particles: int = Field(1000, json_schema_extra={"example": 1000})
    total_time: float = Field(2.0, json_schema_extra={"example": 2.0})
