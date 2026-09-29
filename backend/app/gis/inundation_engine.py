import os
import json
import time
import math
import numpy as np
import rasterio
from rasterio.transform import Affine
from pathlib import Path
from typing import Dict, Any, List, Callable, Tuple
import shapely.geometry
import shapely.ops

class FloodInundationEngine:
    """
    Translates hydrodynamic flood propagation into georeferenced GIS products:
    - maximum_depth.tif
    - maximum_velocity.tif
    - arrival_time.tif
    - flood_extent.geojson
    - temporal timestep snapshots for 2D/3D animation
    """

    @classmethod
    def run_inundation_simulation(
        cls,
        dem_path: str,
        dam_coord: Tuple[float, float], # (lat, lon)
        hydrograph: List[Dict[str, float]],
        output_dir: str,
        dam_height: float = 26.0,
        reservoir_level: float = 24.0,
        downstream_bearing_deg: float = 0.0,
        progress_callback: Callable[[float, str], None] | None = None
    ) -> Dict[str, Any]:
        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        if progress_callback:
            progress_callback(10.0, "Reading terrain digital elevation model")

        with rasterio.open(dem_path) as src:
            dem = src.read(1).astype(np.float32)
            meta = src.meta.copy()
            transform = src.transform
            nodata = src.nodata if src.nodata is not None else -9999.0
            rows, cols = dem.shape
            dx = abs(transform[0])
            dy = abs(transform[4])
            bounds = src.bounds

        # Locate dam breach source cell
        dam_lat, dam_lon = dam_coord
        inv_trans = ~transform
        col_c, row_c = inv_trans * (dam_lon, dam_lat)
        r_dam = max(1, min(rows - 2, int(round(row_c))))
        c_dam = max(1, min(cols - 2, int(round(col_c))))

        # Determine metric cell dimensions and area (handling geographic CRS vs projected CRS)
        is_geo = src.crs.is_geographic if (src.crs and hasattr(src.crs, 'is_geographic')) else True
        if is_geo:
            lat_rad = math.radians(dam_lat)
            dx_m = dx * 111320.0 * math.cos(lat_rad)
            dy_m = dy * 111320.0
        else:
            dx_m = dx
            dy_m = dy
        pixel_area_m2 = dx_m * dy_m
        pixel_area_km2 = pixel_area_m2 / 1.0e6

        if progress_callback:
            progress_callback(20.0, f"Initializing hydrodynamic grid at dam breach cell ({r_dam}, {c_dam}) [dx={dx_m:.1f}m, dy={dy_m:.1f}m]")

        # Initial fields
        max_depth = np.zeros_like(dem, dtype=np.float32)
        max_velocity = np.zeros_like(dem, dtype=np.float32)
        arrival_time = np.full_like(dem, 999.0, dtype=np.float32)

        timesteps_data = []
        n_points = len(hydrograph)
        active_water = np.zeros_like(dem, dtype=np.float32)

        # Elevation at dam base and reservoir head bound (project-specific)
        dam_elev = float(dem[r_dam, c_dam])
        max_physical_head = float(reservoir_level) if (reservoir_level and reservoir_level > 0) else float(dam_height)
        if max_physical_head <= 0:
            raise ValueError("Simulation error: Dam hydraulic head or structural height not configured.")

        # Determine downstream step orientation from bearing
        # Bearing: 0 = North (-r), 90 = East (+c), 180 = South (+r), 270 = West (-c)
        rad = math.radians(downstream_bearing_deg)
        dr_step = int(round(math.cos(rad))) if downstream_bearing_deg != 0.0 else 1
        dc_step = int(round(math.sin(rad))) if downstream_bearing_deg != 0.0 else 0
        if dr_step == 0 and dc_step == 0:
            dr_step = 1

        # Simulate wave evolution over time
        for idx, pt in enumerate(hydrograph[::2]): # Sample hydrograph
            t_min = pt.get("time_min", 0.0)
            q_in = pt.get("discharge_m3s", 0.0)
            percent = 25.0 + (idx / max(1, len(hydrograph) // 2)) * 60.0

            if progress_callback and idx % 5 == 0:
                progress_callback(percent, f"Simulating flood propagation at T+{t_min:.0f} min (Q={q_in:.0f} m³/s)")

            if q_in > 0:
                # Wave propagation downstream:
                # Typical dam break celerity c = sqrt(g * h) ~ 7-10 m/s
                celerity_m_s = min(9.5, max(4.5, math.sqrt(9.81 * min(15.0, max_physical_head * 0.4))))
                wave_reach_dist_m = t_min * 60.0 * celerity_m_s
                reach_steps = int(wave_reach_dist_m / dy_m)
                
                # Flow routing downstream
                if dr_step >= 0:
                    r_range = range(r_dam, min(rows - 1, r_dam + reach_steps + 1))
                else:
                    r_range = range(max(1, r_dam - reach_steps), r_dam + 1)

                for r in r_range:
                    dist_downstream_m = abs(r - r_dam) * dy_m
                    # Valley confinement search along cols (valley widens downstream)
                    col_search = int(max(6, 12 + (dist_downstream_m / 1000.0) * 1.5))
                    c_center = c_dam + int(round(dist_downstream_m / max(1.0, dy_m) * dc_step * 0.4))
                    c_min = max(1, c_center - col_search)
                    c_max = min(cols - 1, c_center + col_search)

                    
                    local_elevs = dem[r, c_min:c_max]
                    min_local_elev = float(np.min(local_elevs))
                    
                    # Bed slope along valley
                    bed_drop = max(0.2, dam_elev - min_local_elev)
                    slope_macro = max(0.0004, bed_drop / max(150.0, dist_downstream_m + 100.0))
                    
                    # Valley width available for flow in meters
                    valley_width_m = max(200.0, (c_max - c_min) * dx_m)
                    
                    # Attenuation of peak discharge downstream due to valley storage:
                    decay = math.exp(-0.000025 * dist_downstream_m)
                    q_local = q_in * decay
                    
                    # Manning's open-channel hydraulic normal depth:
                    # Q = (1/n) * W * h^(5/3) * S^(1/2)  =>  h = ( (n * Q) / (W * sqrt(S)) )^(3/5)
                    # Manning roughness n = 0.035
                    h_manning = math.pow((0.035 * max(5.0, q_local)) / (valley_width_m * math.sqrt(slope_macro)), 0.6)
                    
                    # Physical upper bound: cannot exceed reservoir head at dam, decaying downstream
                    h_water = min(max_physical_head * decay, max(0.15, h_manning))
                    water_surf = min_local_elev + h_water
                    
                    depth_row = np.maximum(0.0, water_surf - local_elevs)
                    active_water[r, c_min:c_max] = depth_row

                    # Flow velocity from Manning: v = (1/n) * R^(2/3) * S^(1/2)
                    vel_row = (1.0 / 0.035) * np.power(np.maximum(0.01, depth_row * 0.8), 2.0 / 3.0) * math.sqrt(slope_macro)
                    vel_row = np.where(depth_row > 0.05, vel_row, 0.0)

                    # Update maximum envelope
                    max_depth[r, c_min:c_max] = np.maximum(max_depth[r, c_min:c_max], depth_row)
                    max_velocity[r, c_min:c_max] = np.maximum(max_velocity[r, c_min:c_max], vel_row)

                    # Update arrival time
                    arr_mask = (depth_row > 0.05) & (arrival_time[r, c_min:c_max] > 900.0)
                    arrival_time[r, c_min:c_max] = np.where(arr_mask, t_min, arrival_time[r, c_min:c_max])

            # Record snapshot metric using true metric pixel area
            wet_cells = int(np.sum(max_depth > 0.05))
            flooded_area_sqkm = float(wet_cells * pixel_area_km2)
            cur_max = float(np.max(max_depth)) if wet_cells > 0 else 0.0
            cur_vel = float(np.max(max_velocity)) if wet_cells > 0 else 0.0

            timesteps_data.append({
                "time_min": round(t_min, 1),
                "discharge_m3s": round(q_in, 1),
                "max_depth_m": round(cur_max, 2),
                "max_velocity_ms": round(cur_vel, 2),
                "inundated_area_sqkm": round(flooded_area_sqkm, 2)
            })

        if progress_callback:
            progress_callback(85.0, "Writing georeferenced output rasters")

        # Set nodata values
        arrival_time[arrival_time > 900.0] = nodata
        max_depth[dem == nodata] = nodata
        max_velocity[dem == nodata] = nodata

        # 1. Save maximum depth GeoTIFF
        depth_tif_path = str(out_dir / "maximum_depth.tif")
        meta_out = meta.copy()
        meta_out.update({'dtype': 'float32', 'nodata': nodata, 'count': 1})
        with rasterio.open(depth_tif_path, 'w', **meta_out) as dst:
            dst.write(max_depth, 1)

        # 2. Save maximum velocity GeoTIFF
        vel_tif_path = str(out_dir / "maximum_velocity.tif")
        with rasterio.open(vel_tif_path, 'w', **meta_out) as dst:
            dst.write(max_velocity, 1)

        # 3. Save arrival time GeoTIFF
        arr_tif_path = str(out_dir / "arrival_time.tif")
        with rasterio.open(arr_tif_path, 'w', **meta_out) as dst:
            dst.write(arrival_time, 1)

        # 4. Generate vectorized flood extent GeoJSON
        if progress_callback:
            progress_callback(92.0, "Vectorizing flood extent perimeter")

        flood_extent_geojson_path = str(out_dir / "flood_extent.geojson")
        extent_geom = cls.vectorize_extent(max_depth, transform, nodata=nodata)
        
        # Calculate polygon area in square kilometers
        if is_geo:
            polygon_area_sqkm = float(extent_geom.area * (111.32 * math.cos(math.radians(dam_lat))) * 111.32)
        else:
            polygon_area_sqkm = float(extent_geom.area / 1.0e6)

        total_wet_cells = int(np.sum((max_depth > 0.05) & (max_depth != nodata)))
        raster_area_sqkm = float(total_wet_cells * pixel_area_km2)
        peak_depth = float(np.max(max_depth[max_depth != nodata])) if total_wet_cells > 0 else 0.0
        peak_vel = float(np.max(max_velocity[max_velocity != nodata])) if total_wet_cells > 0 else 0.0

        geojson_dict = {
            "type": "FeatureCollection",
            "features": [{
                "type": "Feature",
                "id": "flood_perimeter",
                "properties": {
                    "total_area_sqkm": round(raster_area_sqkm, 2),
                    "polygon_area_sqkm": round(polygon_area_sqkm, 2),
                    "peak_flood_depth_m": round(peak_depth, 2),
                    "peak_flow_velocity_ms": round(peak_vel, 2)
                },
                "geometry": shapely.geometry.mapping(extent_geom)
            }]
        }
        with open(flood_extent_geojson_path, "w", encoding="utf-8") as f:
            json.dump(geojson_dict, f, indent=2)

        # Save timesteps animation JSON
        timesteps_path = str(out_dir / "timesteps.json")
        with open(timesteps_path, "w", encoding="utf-8") as f:
            json.dump(timesteps_data, f, indent=2)

        if progress_callback:
            progress_callback(100.0, "Hydrodynamic inundation analysis completed successfully")

        return {
            "max_depth_tif": depth_tif_path,
            "max_velocity_tif": vel_tif_path,
            "arrival_time_tif": arr_tif_path,
            "flood_extent_geojson": flood_extent_geojson_path,
            "timesteps_json": timesteps_path,
            "inundated_area_sqkm": round(raster_area_sqkm, 2),
            "polygon_area_sqkm": round(polygon_area_sqkm, 2),
            "peak_depth_m": round(peak_depth, 2),
            "peak_velocity_ms": round(peak_vel, 2),
            "wet_cell_count": total_wet_cells,
            "pixel_area_m2": round(pixel_area_m2, 2),
            "flood_polygon": extent_geom
        }

    @staticmethod
    def vectorize_extent(max_depth: np.ndarray, transform: Affine, nodata: float = -9999.0) -> shapely.geometry.base.BaseGeometry:
        """
        Creates smooth vector polygon boundary from wet cells.
        """
        wet_mask = (max_depth > 0.05) & (max_depth != nodata)
        rows, cols = wet_mask.shape
        boxes = []
        
        # Coarse bounding boxes to prevent massive polygon complexity
        step = max(1, rows // 150)
        for r in range(0, rows, step):
            for c in range(0, cols, step):
                sub = wet_mask[r:r+step, c:c+step]
                if np.any(sub):
                    x1, y1 = transform * (c, r)
                    x2, y2 = transform * (c + step, r + step)
                    min_x, max_x = min(x1, x2), max(x1, x2)
                    min_y, max_y = min(y1, y2), max(y1, y2)
                    boxes.append(shapely.geometry.box(min_x, min_y, max_x, max_y))

        if not boxes:
            return shapely.geometry.Polygon()

        merged = shapely.ops.unary_union(boxes)
        # Simplify geometry for fast web rendering
        simplified = merged.simplify(0.0005, preserve_topology=True)
        return simplified
