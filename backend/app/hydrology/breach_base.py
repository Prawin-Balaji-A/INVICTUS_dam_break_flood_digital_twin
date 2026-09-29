from abc import ABC, abstractmethod
from pydantic import BaseModel, Field
from typing import Dict, Any, List

class BreachParameters(BaseModel):
    dam_height: float = Field(..., description="Dam height in meters (Hd)")
    dam_length: float = Field(..., description="Dam crest length in meters (Ld)")
    reservoir_volume: float = Field(..., description="Reservoir volume in cubic meters (Vw)")
    reservoir_level: float = Field(..., description="Initial water depth above breach invert in meters (Hw)")
    reservoir_area: float = Field(..., description="Reservoir surface area in square meters (As)")
    failure_mode: str = Field("Overtopping", description="'Overtopping' or 'Piping'")
    tailwater_depth: float = Field(0.0, description="Tailwater depth in meters")
    manning_n: float = Field(0.035, description="Downstream channel roughness")

class BreachGeometry(BaseModel):
    formulation_name: str
    breach_width_avg: float
    breach_bottom_width: float
    breach_top_width: float
    breach_depth: float
    breach_time_sec: float
    breach_side_slope_z: float
    peak_discharge_m3s: float

class HydrographPoint(BaseModel):
    time_sec: float
    time_min: float
    discharge_m3s: float
    stage_m: float
    velocity_ms: float
    reservoir_volume_m3: float

class BreachModel(ABC):
    """
    Abstract Base Class for empirical dam breach geometry and formation calculations.
    """
    @abstractmethod
    def calculate_geometry(self, params: BreachParameters) -> BreachGeometry:
        pass
