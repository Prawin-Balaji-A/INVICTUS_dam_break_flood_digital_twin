from sqlalchemy import Column, String, Float, DateTime, Text, ForeignKey, Integer
from datetime import datetime
import uuid
from backend.app.core.database import Base

class Simulation(Base):
    __tablename__ = "simulations"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=False)
    scenario_id = Column(String(36), ForeignKey("scenarios.id"), nullable=False)
    
    engine_name = Column(String(50), default="Experimental SPH Solver") # "Experimental SPH Solver" or "Delft3D"
    engine_status = Column(String(100), default="Experimental / Unvalidated")
    
    status = Column(String(50), default="QUEUED")  # QUEUED, PREPROCESSING, RUNNING, POSTPROCESSING, COMPLETED, FAILED
    progress = Column(Float, default=0.0)
    error_message = Column(Text, nullable=True)
    
    # Impact & Summary Metrics
    max_depth = Column(Float, nullable=True)              # meters
    max_velocity = Column(Float, nullable=True)           # m/s
    peak_discharge = Column(Float, nullable=True)         # m^3/s
    inundated_area_sqkm = Column(Float, nullable=True)    # sq km
    affected_buildings_count = Column(Integer, nullable=True)
    affected_roads_km = Column(Float, nullable=True)
    exposed_population = Column(Integer, nullable=True)
    
    # Output Directory & Assets
    results_dir = Column(Text, nullable=True)
    flood_extent_geojson = Column(Text, nullable=True)
    max_depth_tif = Column(Text, nullable=True)
    max_velocity_tif = Column(Text, nullable=True)
    arrival_time_tif = Column(Text, nullable=True)
    impact_json = Column(Text, nullable=True)
    timesteps_json = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
