"""
Generalized Dataset Adapter & Registry Architecture for Dam Break Modelling.

Hierarchy:
DamProject
    ↓
DatasetRegistry
    ↓
DEMAdapter, RiverAdapter, ReservoirAdapter, BuildingAdapter, RoadAdapter, PopulationAdapter, SatelliteAdapter

Receives project configuration / project ID.
Does NOT contain dam-specific hardcoded logic.
Enforces strict validation, integrity checks, and synthetic data protection.
"""

from typing import Dict, Any, Optional, List
from pathlib import Path
import json
import numpy as np
import rasterio
from shapely.geometry import shape, Point, box
import geopandas as gpd

class BaseAdapter:
    """Base class for all dataset adapters."""
    def __init__(self, file_path: Optional[str], project_bounds: Optional[Dict[str, float]] = None):
        self.file_path = file_path
        self.project_bounds = project_bounds
        self._exists = bool(file_path and Path(file_path).exists() and Path(file_path).is_file())

    @property
    def is_available(self) -> bool:
        return self._exists

class DEMAdapter(BaseAdapter):
    """Adapter for Digital Elevation Model rasters."""
    def get_metadata(self) -> Dict[str, Any]:
        if not self.is_available:
            return {"status": "NOT_CONFIGURED", "available": False}
        
        try:
            with rasterio.open(self.file_path) as src:
                data = src.read(1)
                nodata = src.nodata
                valid_mask = (data != nodata) if nodata is not None else ~np.isnan(data)
                valid_elev = data[valid_mask]
                
                return {
                    "status": "VALID",
                    "available": True,
                    "local_path": str(self.file_path),
                    "crs": str(src.crs),
                    "width": src.width,
                    "height": src.height,
                    "resolution": list(src.res),
                    "bounds": {
                        "left": src.bounds.left,
                        "bottom": src.bounds.bottom,
                        "right": src.bounds.right,
                        "top": src.bounds.top
                    },
                    "min_elevation_m": float(np.min(valid_elev)) if len(valid_elev) > 0 else None,
                    "max_elevation_m": float(np.max(valid_elev)) if len(valid_elev) > 0 else None,
                    "mean_elevation_m": float(np.mean(valid_elev)) if len(valid_elev) > 0 else None,
                    "nodata": nodata,
                    "nan_count": int(np.isnan(data).sum()),
                    "inf_count": int(np.isinf(data).sum())
                }
        except Exception as e:
            return {"status": "INVALID", "available": False, "error": str(e)}

    def read_dem_array(self):
        """Returns (data_array, transform, crs)."""
        if not self.is_available:
            raise FileNotFoundError(f"DEM raster not available at {self.file_path}")
        with rasterio.open(self.file_path) as src:
            return src.read(1), src.transform, src.crs

class RiverAdapter(BaseAdapter):
    """Adapter for river & waterway vector geometries."""
    def get_metadata(self) -> Dict[str, Any]:
        if not self.is_available:
            return {"status": "NOT_CONFIGURED", "available": False}
        try:
            gdf = gpd.read_file(self.file_path)
            bounds = gdf.total_bounds
            return {
                "status": "VALID",
                "available": True,
                "local_path": str(self.file_path),
                "crs": str(gdf.crs) if gdf.crs else "EPSG:4326",
                "feature_count": len(gdf),
                "bounds": {
                    "min_lon": float(bounds[0]),
                    "min_lat": float(bounds[1]),
                    "max_lon": float(bounds[2]),
                    "max_lat": float(bounds[3])
                }
            }
        except Exception as e:
            return {"status": "INVALID", "available": False, "error": str(e)}

    def load_geodataframe(self) -> gpd.GeoDataFrame:
        if not self.is_available:
            raise FileNotFoundError(f"River vector data not available at {self.file_path}")
        return gpd.read_file(self.file_path)

class BuildingAdapter(BaseAdapter):
    """Adapter for building footprint polygons."""
    def get_metadata(self) -> Dict[str, Any]:
        if not self.is_available:
            return {"status": "NOT_CONFIGURED", "available": False}
        try:
            gdf = gpd.read_file(self.file_path)
            return {
                "status": "VALID",
                "available": True,
                "local_path": str(self.file_path),
                "crs": str(gdf.crs) if gdf.crs else "EPSG:4326",
                "feature_count": len(gdf)
            }
        except Exception as e:
            return {"status": "INVALID", "available": False, "error": str(e)}

class RoadAdapter(BaseAdapter):
    """Adapter for transportation & evacuation road networks."""
    def get_metadata(self) -> Dict[str, Any]:
        if not self.is_available:
            return {"status": "NOT_CONFIGURED", "available": False}
        try:
            gdf = gpd.read_file(self.file_path)
            return {
                "status": "VALID",
                "available": True,
                "local_path": str(self.file_path),
                "crs": str(gdf.crs) if gdf.crs else "EPSG:4326",
                "feature_count": len(gdf)
            }
        except Exception as e:
            return {"status": "INVALID", "available": False, "error": str(e)}

class ReservoirAdapter(BaseAdapter):
    """Adapter for reservoir waterbody geometries."""
    def get_metadata(self) -> Dict[str, Any]:
        if not self.is_available:
            return {"status": "NOT_CONFIGURED", "available": False}
        try:
            gdf = gpd.read_file(self.file_path)
            return {
                "status": "VALID",
                "available": True,
                "local_path": str(self.file_path),
                "crs": str(gdf.crs) if gdf.crs else "EPSG:4326",
                "feature_count": len(gdf)
            }
        except Exception as e:
            return {"status": "INVALID", "available": False, "error": str(e)}

class PopulationAdapter(BaseAdapter):
    """Adapter for population exposure rasters / census polygons."""
    def get_metadata(self) -> Dict[str, Any]:
        if not self.is_available:
            return {
                "status": "NOT_CONFIGURED",
                "available": False,
                "source": "Census of India / WorldPop",
                "notes": "Raster not downloaded. Synthetic population fallback strictly prohibited."
            }
        return {"status": "VALID", "available": True, "local_path": str(self.file_path)}

class SatelliteAdapter(BaseAdapter):
    """Adapter for Copernicus Sentinel-1/2 Earth observation scenes."""
    def get_metadata(self) -> Dict[str, Any]:
        if not self.is_available:
            return {
                "status": "NOT_CONFIGURED",
                "available": False,
                "source": "Copernicus Sentinel-1 SAR",
                "notes": "Live SAR imagery not configured. Synthetic flood polygon fallback strictly prohibited."
            }
        return {"status": "VALID", "available": True, "local_path": str(self.file_path)}

class DatasetRegistry:
    """
    Central dataset registry for any DamProject.
    Instantiates dedicated adapters and provides unified dataset query interface.
    """
    def __init__(self, project_dict: Dict[str, Any]):
        self.project_id = project_dict.get("id") or project_dict.get("slug")
        self.project_name = project_dict.get("name")
        self.is_demo = project_dict.get("is_demo", False)
        
        bounds = {
            "min_lon": project_dict.get("min_lon"),
            "min_lat": project_dict.get("min_lat"),
            "max_lon": project_dict.get("max_lon"),
            "max_lat": project_dict.get("max_lat")
        }
        
        self.dem = DEMAdapter(project_dict.get("dem_path"), bounds)
        self.river = RiverAdapter(project_dict.get("river_path"), bounds)
        self.buildings = BuildingAdapter(project_dict.get("buildings_path"), bounds)
        self.roads = RoadAdapter(project_dict.get("roads_path"), bounds)
        self.reservoir = ReservoirAdapter(project_dict.get("reservoir_path"), bounds)
        self.population = PopulationAdapter(project_dict.get("population_path"), bounds)
        self.satellite = SatelliteAdapter(project_dict.get("satellite_path"), bounds)

    def get_dataset_summary(self) -> Dict[str, Any]:
        return {
            "project_id": self.project_id,
            "project_name": self.project_name,
            "is_demo": self.is_demo,
            "dem": self.dem.get_metadata(),
            "river": self.river.get_metadata(),
            "buildings": self.buildings.get_metadata(),
            "roads": self.roads.get_metadata(),
            "reservoir": self.reservoir.get_metadata(),
            "population": self.population.get_metadata(),
            "satellite": self.satellite.get_metadata()
        }

    def validate_simulation_readiness(self) -> Dict[str, Any]:
        """
        Validates whether required datasets are present for running simulation.
        Fails clearly if any mandatory dataset is missing.
        """
        missing = []
        if not self.dem.is_available:
            missing.append("DEM dataset is not configured")
        if not self.river.is_available:
            missing.append("River dataset is not configured")

        if missing:
            return {
                "ready": False,
                "error": f"Cannot run real-data workflow for project '{self.project_name}': {', '.join(missing)}."
            }
        return {"ready": True, "error": None}
