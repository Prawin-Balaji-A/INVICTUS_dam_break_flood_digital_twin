"""
Script to acquire and process full Copernicus DEM GLO-30 data covering 100% of Idukki study area.
Sources: 4 tiles from Copernicus DEM GLO-30 (Public AWS S3):
  1. Copernicus_DSM_COG_10_N09_00_E076_00_DEM (Lat 9-10 N, Lon 76-77 E)
  2. Copernicus_DSM_COG_10_N10_00_E076_00_DEM (Lat 10-11 N, Lon 76-77 E)
  3. Copernicus_DSM_COG_10_N09_00_E077_00_DEM (Lat 9-10 N, Lon 77-78 E)
  4. Copernicus_DSM_COG_10_N10_00_E077_00_DEM (Lat 10-11 N, Lon 77-78 E)

Together these 4 tiles cover Lat 9.0-11.0 N and Lon 76.0-78.0 E (40,000 km²),
providing 100% complete raster coverage for the entire Idukki study area [76.75, 9.75] to [77.08, 10.08].
"""

import os
import sys
import requests
import rasterio
from rasterio.merge import merge
from rasterio.mask import mask
from shapely.geometry import box
import json
import numpy as np

TILES = [
    {
        "name": "Copernicus_DSM_COG_10_N09_00_E076_00_DEM.tif",
        "url": "https://copernicus-dem-30m.s3.amazonaws.com/Copernicus_DSM_COG_10_N09_00_E076_00_DEM/Copernicus_DSM_COG_10_N09_00_E076_00_DEM.tif"
    },
    {
        "name": "Copernicus_DSM_COG_10_N10_00_E076_00_DEM.tif",
        "url": "https://copernicus-dem-30m.s3.amazonaws.com/Copernicus_DSM_COG_10_N10_00_E076_00_DEM/Copernicus_DSM_COG_10_N10_00_E076_00_DEM.tif"
    },
    {
        "name": "Copernicus_DSM_COG_10_N09_00_E077_00_DEM.tif",
        "url": "https://copernicus-dem-30m.s3.amazonaws.com/Copernicus_DSM_COG_10_N09_00_E077_00_DEM/Copernicus_DSM_COG_10_N09_00_E077_00_DEM.tif"
    },
    {
        "name": "Copernicus_DSM_COG_10_N10_00_E077_00_DEM.tif",
        "url": "https://copernicus-dem-30m.s3.amazonaws.com/Copernicus_DSM_COG_10_N10_00_E077_00_DEM/Copernicus_DSM_COG_10_N10_00_E077_00_DEM.tif"
    }
]

DEM_SOURCE_DIR = r"E:\dam\data\idukki\dem\source"
DEM_PROCESSED_DIR = r"E:\dam\data\idukki\dem\processed"
BOUNDARIES_DIR = r"E:\dam\data\idukki\boundaries"

os.makedirs(DEM_SOURCE_DIR, exist_ok=True)
os.makedirs(DEM_PROCESSED_DIR, exist_ok=True)
os.makedirs(BOUNDARIES_DIR, exist_ok=True)

# Full Idukki Study Area Bounding Box:
# Lat 9.75N to 10.08N, Lon 76.75E to 77.08E
STUDY_BBOX = {
    "min_lon": 76.75,
    "min_lat": 9.75,
    "max_lon": 77.08,
    "max_lat": 10.08
}

NODATA_VALUE = -32767.0

def download_file(url, dest_path):
    print(f"Downloading {url} -> {dest_path}...", flush=True)
    headers = {"User-Agent": "DamBreakFloodModel/1.0 (Geospatial Research Prototype)"}
    with requests.get(url, headers=headers, stream=True) as r:
        r.raise_for_status()
        total_size = int(r.headers.get('content-length', 0))
        downloaded = 0
        with open(dest_path, 'wb') as f:
            for chunk in r.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total_size > 0:
                        pct = (downloaded / total_size) * 100
                        sys.stdout.write(f"\rProgress: {downloaded / (1024*1024):.1f}/{total_size / (1024*1024):.1f} MB ({pct:.1f}%)")
                        sys.stdout.flush()
    print("\nDownload complete.", flush=True)

def create_study_area_geojson():
    study_polygon = {
        "type": "FeatureCollection",
        "name": "Idukki Study Area Boundary (Preliminary)",
        "crs": {
            "type": "name",
            "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}
        },
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "study_area": "Idukki Dam & Downstream Periyar Floodplain",
                    "boundary_status": "preliminary",
                    "dam_name": "Idukki Dam",
                    "river": "Periyar",
                    "state": "Kerala",
                    "min_lat": STUDY_BBOX["min_lat"],
                    "max_lat": STUDY_BBOX["max_lat"],
                    "min_lon": STUDY_BBOX["min_lon"],
                    "max_lon": STUDY_BBOX["max_lon"],
                    "area_km2": 1334.0,
                    "description": "Encompasses Idukki double-curvature arch dam, Cheruthoni concrete gravity spillway dam, Kulamavu masonry dam, the reservoir basin, and ~40 km of the downstream Periyar river corridor towards Neriamangalam."
                },
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[
                        [STUDY_BBOX["min_lon"], STUDY_BBOX["min_lat"]],
                        [STUDY_BBOX["max_lon"], STUDY_BBOX["min_lat"]],
                        [STUDY_BBOX["max_lon"], STUDY_BBOX["max_lat"]],
                        [STUDY_BBOX["min_lon"], STUDY_BBOX["max_lat"]],
                        [STUDY_BBOX["min_lon"], STUDY_BBOX["min_lat"]]
                    ]]
                }
            }
        ]
    }
    path = os.path.join(BOUNDARIES_DIR, "study_area.geojson")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(study_polygon, f, indent=2)
    print(f"Created study boundary at {path}", flush=True)

def acquire_and_process_dem():
    tile_paths = []
    for tile in TILES:
        dest = os.path.join(DEM_SOURCE_DIR, tile["name"])
        tile_paths.append(dest)
        if not os.path.exists(dest) or os.path.getsize(dest) < 10000000:
            download_file(tile["url"], dest)
        else:
            print(f"Tile exists: {tile['name']} ({os.path.getsize(dest) / (1024*1024):.1f} MB)", flush=True)

    print("\nOpening all 4 source DEM tiles for mosaicking...", flush=True)
    src_datasets = [rasterio.open(p) for p in tile_paths]
    
    mosaic, out_trans = merge(src_datasets, nodata=NODATA_VALUE)
    out_meta = src_datasets[0].meta.copy()
    out_meta.update({
        "driver": "GTiff",
        "height": mosaic.shape[1],
        "width": mosaic.shape[2],
        "transform": out_trans,
        "nodata": NODATA_VALUE,
        "dtype": "float32"
    })
    
    for s in src_datasets:
        s.close()

    print(f"Mosaic dimensions: {mosaic.shape[2]} x {mosaic.shape[1]}", flush=True)
    temp_mosaic_path = os.path.join(DEM_SOURCE_DIR, "mosaic_4tiles_temp.tif")
    with rasterio.open(temp_mosaic_path, "w", **out_meta) as dest:
        dest.write(mosaic.astype(np.float32))

    print("Cropping 4-tile mosaic to full Idukki study bbox [76.75, 9.75] to [77.08, 10.08]...", flush=True)
    geom = [box(STUDY_BBOX["min_lon"], STUDY_BBOX["min_lat"], STUDY_BBOX["max_lon"], STUDY_BBOX["max_lat"])]
    
    with rasterio.open(temp_mosaic_path) as src_merged:
        out_image, out_transform = mask(src_merged, geom, crop=True, nodata=NODATA_VALUE)
        out_meta = src_merged.meta.copy()
        out_meta.update({
            "driver": "GTiff",
            "height": out_image.shape[1],
            "width": out_image.shape[2],
            "transform": out_transform,
            "compress": "lzw",
            "nodata": NODATA_VALUE,
            "dtype": "float32"
        })

        processed_path = os.path.join(DEM_PROCESSED_DIR, "idukki_dem_30m.tif")
        with rasterio.open(processed_path, "w", **out_meta) as dest:
            dest.write(out_image.astype(np.float32))
        print(f"Saved processed DEM: {processed_path}", flush=True)

    if os.path.exists(temp_mosaic_path):
        os.remove(temp_mosaic_path)

    # Detailed raster stats & nodata verification
    with rasterio.open(processed_path) as ds:
        data = ds.read(1)
        total_pixels = data.size
        nodata_mask = (data == ds.nodata) | np.isnan(data)
        valid_mask = ~nodata_mask
        valid_elev = data[valid_mask]
        zero_count = int((data == 0.0).sum())
        nodata_count = int(nodata_mask.sum())
        
        print("\n" + "="*50)
        print("PROCESSED DEM DETAILED QUALITY STATS:")
        print("="*50)
        print(f"Dimensions: {ds.width} x {ds.height} ({total_pixels} total pixels)")
        print(f"CRS: {ds.crs}")
        print(f"Resolution (deg): {ds.res}")
        print(f"Bounds: left={ds.bounds.left:.6f}, bottom={ds.bounds.bottom:.6f}, right={ds.bounds.right:.6f}, top={ds.bounds.top:.6f}")
        print(f"Nodata value configured: {ds.nodata}")
        print(f"Nodata pixels: {nodata_count} ({nodata_count / total_pixels * 100:.2f}%)")
        print(f"Zero-elevation pixels: {zero_count} ({zero_count / total_pixels * 100:.4f}%)")
        print(f"Valid pixels: {len(valid_elev)} ({len(valid_elev) / total_pixels * 100:.2f}%)")
        print(f"Min elevation: {valid_elev.min():.2f} m MSL")
        print(f"Max elevation: {valid_elev.max():.2f} m MSL")
        print(f"Mean elevation: {valid_elev.mean():.2f} m MSL")
        
        # Verify coverage of study bounds
        cov_left = ds.bounds.left <= STUDY_BBOX["min_lon"] + 1e-4
        cov_right = ds.bounds.right >= STUDY_BBOX["max_lon"] - 1e-4
        cov_bottom = ds.bounds.bottom <= STUDY_BBOX["min_lat"] + 1e-4
        cov_top = ds.bounds.top >= STUDY_BBOX["max_lat"] - 1e-4
        fully_covered = cov_left and cov_right and cov_bottom and cov_top
        print(f"Full study area coverage: {fully_covered}")
        print("="*50, flush=True)

if __name__ == "__main__":
    create_study_area_geojson()
    acquire_and_process_dem()
