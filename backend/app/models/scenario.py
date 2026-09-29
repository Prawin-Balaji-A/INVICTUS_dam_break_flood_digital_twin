from sqlalchemy import Column, String, Float, DateTime, Text, ForeignKey
from datetime import datetime
import uuid
from backend.app.core.database import Base

class Scenario(Base):
    __tablename__ = "scenarios"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=False)
    name = Column(String(255), nullable=False)
    
    # Dam parameters
    dam_height = Column(Float, nullable=False)           # meters (Hd)
    dam_length = Column(Float, nullable=False)           # meters (Ld)
    dam_crest_elev = Column(Float, nullable=True)        # meters MSL
    
    # Reservoir parameters
    reservoir_volume = Column(Float, nullable=False)     # m^3 (Vw)
    reservoir_level = Column(Float, nullable=False)      # meters (Hw)
    reservoir_area = Column(Float, nullable=True)        # m^2 (As)
    
    # Breach parameters
    breach_formulation = Column(String(50), default="Froehlich_2008") # Froehlich_2008, MacDonald_1984, VonThun_1990, Custom
    breach_type = Column(String(50), default="Gradual")  # Instantaneous, Gradual, Partial
    breach_depth = Column(Float, nullable=False)         # meters (hb)
    breach_width = Column(Float, nullable=False)         # meters (Bavg)
    breach_time = Column(Float, nullable=False)          # seconds (tf)
    breach_side_slope = Column(Float, default=1.0)       # z (H:V)
    manning_n = Column(Float, nullable=True, default=0.035)  # Manning roughness coefficient
    status = Column(String(50), default="ready")         # ready, awaiting_verified_dam_inputs
    
    # Stored precalculated hydrograph time series JSON (list of {time_sec, discharge_m3s, stage_m})
    hydrograph_json = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
