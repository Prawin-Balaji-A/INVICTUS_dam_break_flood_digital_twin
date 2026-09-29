import os
import numpy as np
import rasterio
from rasterio.warp import calculate_default_transform, reproject, Resampling
from rasterio.transform import Affine
from pathlib import Path
from typing import Dict, Any, Tuple

class DEMProcessor:
    """
    Physical GIS processing pipeline for Digital Elevation Models (DEM).
    Computes topographic derivatives preserving spatial georeferencing.
    Vectorized with high-performance NumPy operations.
    """

    @staticmethod
    def get_utm_crs(lon: float, lat: float) -> str:
        zone = int((lon + 180) / 6) + 1
        epsg = 32600 + zone if lat >= 0 else 32700 + zone
        return f"EPSG:{epsg}"

    @classmethod
    def fill_sinks(cls, elevation: np.ndarray, nodata: float = -9999.0, max_fill: float = 5.0) -> np.ndarray:
        filled = np.copy(elevation)
        mask = (elevation != nodata) & (~np.isnan(elevation))
        
        # Fast vectorized 3x3 local minimum neighbor filter
        for _ in range(2):
            interior = filled[1:-1, 1:-1]
            interior_mask = mask[1:-1, 1:-1]
            
            n_up = filled[:-2, 1:-1]
            n_down = filled[2:, 1:-1]
            n_left = filled[1:-1, :-2]
            n_right = filled[1:-1, 2:]

            min_neighbor = np.minimum(np.minimum(n_up, n_down), np.minimum(n_left, n_right))
            pit_condition = interior_mask & (interior < min_neighbor) & ((min_neighbor - interior) <= max_fill)
            interior[pit_condition] = min_neighbor[pit_condition]
            filled[1:-1, 1:-1] = interior

        return filled

    @classmethod
    def compute_topographic_derivatives(cls, dem_path: str, output_dir: str) -> Dict[str, str]:
        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        with rasterio.open(dem_path) as src:
            elevation = src.read(1).astype(np.float32)
            meta = src.meta.copy()
            nodata = src.nodata if src.nodata is not None else -9999.0
            dx = abs(src.transform[0])
            dy = abs(src.transform[4])

        filled_elev = cls.fill_sinks(elevation, nodata=nodata)

        # Gradients using Horn's algorithm
        padded = np.pad(filled_elev, 1, mode='edge')
        dz_dx = ((padded[:-2, 2:] + 2 * padded[1:-1, 2:] + padded[2:, 2:]) -
                 (padded[:-2, :-2] + 2 * padded[1:-1, :-2] + padded[2:, :-2])) / (8.0 * dx)
        dz_dy = ((padded[2:, :-2] + 2 * padded[2:, 1:-1] + padded[2:, 2:]) -
                 (padded[:-2, :-2] + 2 * padded[:-2, 1:-1] + padded[:-2, 2:])) / (8.0 * dy)

        # Slope (degrees)
        slope_rad = np.arctan(np.sqrt(dz_dx**2 + dz_dy**2))
        slope_deg = np.degrees(slope_rad)
        slope_deg[elevation == nodata] = nodata

        # Aspect (degrees clockwise from North)
        aspect_rad = np.arctan2(dz_dy, -dz_dx)
        aspect_deg = np.degrees(aspect_rad)
        aspect_deg = 90.0 - aspect_deg
        aspect_deg[aspect_deg < 0] += 360.0
        aspect_deg[elevation == nodata] = nodata

        # Hillshade (Azimuth=315°, Altitude=45°)
        azimuth_rad = np.radians(315.0)
        altitude_rad = np.radians(45.0)
        hillshade = 255.0 * (
            (np.cos(altitude_rad) * np.cos(slope_rad)) +
            (np.sin(altitude_rad) * np.sin(slope_rad) * np.cos(azimuth_rad - aspect_rad))
        )
        hillshade = np.clip(hillshade, 0.0, 255.0)
        hillshade[elevation == nodata] = 0

        # Vectorized D8 Flow Direction
        # Codes: 1=E, 2=SE, 4=S, 8=SW, 16=W, 32=NW, 64=N, 128=NE
        rows, cols = filled_elev.shape
        flow_dir = np.zeros((rows, cols), dtype=np.int16)
        
        # Directions and shifts: (shift_r, shift_c, code, dist)
        directions = [
            (0, 1, 1, dx), (1, 1, 2, np.hypot(dx, dy)), (1, 0, 4, dy), (1, -1, 8, np.hypot(dx, dy)),
            (0, -1, 16, dx), (-1, -1, 32, np.hypot(dx, dy)), (-1, 0, 64, dy), (-1, 1, 128, np.hypot(dx, dy))
        ]
        
        center = padded[1:-1, 1:-1]
        max_drop = np.zeros_like(center)
        best_code = np.zeros_like(center, dtype=np.int16)

        for dr, dc, code, dist in directions:
            neighbor = padded[1+dr : 1+dr+rows, 1+dc : 1+dc+cols]
            drop = (center - neighbor) / dist
            steeper = drop > max_drop
            max_drop[steeper] = drop[steeper]
            best_code[steeper] = code

        flow_dir = best_code

        # Flow accumulation approximation based on local convergence / inverted curvature
        laplacian = ((padded[:-2, 1:-1] + padded[2:, 1:-1] + padded[1:-1, :-2] + padded[1:-1, 2:]) - 4.0 * center)
        flow_acc = np.clip(1.0 + np.maximum(0.0, laplacian * 50.0), 1.0, 5000.0).astype(np.int32)
        flow_acc[elevation == nodata] = 0

        # Save rasters
        results = {}
        layers = [
            ("hillshade.tif", hillshade.astype(np.uint8), "uint8", 0),
            ("slope.tif", slope_deg.astype(np.float32), "float32", nodata),
            ("aspect.tif", aspect_deg.astype(np.float32), "float32", nodata),
            ("flow_dir.tif", flow_dir.astype(np.int16), "int16", 0),
            ("flow_acc.tif", flow_acc.astype(np.int32), "int32", 0)
        ]

        for fname, data, dtype, nd in layers:
            fpath = str(out_dir / fname)
            layer_meta = meta.copy()
            layer_meta.update({'dtype': dtype, 'nodata': nd, 'count': 1})
            with rasterio.open(fpath, 'w', **layer_meta) as dst:
                dst.write(data, 1)
            results[fname.split('.')[0]] = fpath

        return results
