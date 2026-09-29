from sqlalchemy import Column, String, Float, DateTime, Text, Boolean
from datetime import datetime
import uuid
from backend.app.core.database import Base

class Project(Base):
    __tablename__ = "projects"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    slug = Column(String(100), unique=True, index=True, nullable=True)
    name = Column(String(255), nullable=False)
    river_name = Column(String(255), nullable=False)
    country = Column(String(100), default="India")
    state = Column(String(100), nullable=True)
    district = Column(String(100), nullable=True)
    dam_name = Column(String(255), nullable=False)
    
    dam_lat = Column(Float, nullable=False)
    dam_lon = Column(Float, nullable=False)
    
    # Study area bounding box
    min_lat = Column(Float, nullable=False)
    min_lon = Column(Float, nullable=False)
    max_lat = Column(Float, nullable=False)
    max_lon = Column(Float, nullable=False)
    
    crs = Column(String(50), default="EPSG:4326")
    projected_crs = Column(String(50), nullable=True)
    downstream_bearing_deg = Column(Float, default=0.0)

    # Engineering Specifications
    dam_height_m = Column(Float, nullable=True)
    crest_length_m = Column(Float, nullable=True)
    crest_elevation_m = Column(Float, nullable=True)
    full_reservoir_level_m = Column(Float, nullable=True)
    reservoir_capacity_m3 = Column(Float, nullable=True)
    reservoir_area_m2 = Column(Float, nullable=True)

    is_demo = Column(Boolean, default=False)
    simulation_enabled = Column(Boolean, default=False)
    dam_type = Column(String(100), nullable=True)
    operator = Column(String(200), nullable=True)
    source_provenance = Column(Text, nullable=True)
    data_status = Column(String(50), default="NOT CONFIGURED")
    
    # Paths to ingested spatial assets
    dem_path = Column(Text, nullable=True)
    hillshade_path = Column(Text, nullable=True)
    slope_path = Column(Text, nullable=True)
    river_path = Column(Text, nullable=True)
    buildings_path = Column(Text, nullable=True)
    roads_path = Column(Text, nullable=True)
    landuse_path = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
