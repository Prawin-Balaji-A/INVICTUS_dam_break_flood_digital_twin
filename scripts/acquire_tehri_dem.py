"""
Acquire and process Copernicus DEM GLO-30 covering the Tehri Dam study area.

Tehri Dam (Bhagirathi River, Uttarakhand) study domain:
  Lat 30.30 - 30.45 N, Lon 78.40 - 78.56 E

This falls entirely inside a single Copernicus GLO-30 1x1 degree tile:
  Copernicus_DSM_COG_10_N30_00_E078_00_DEM (Lat 30-31 N, Lon 78-79 E)

Mirrors scripts/acquire_idukki_dem.py exactly (same download -> crop -> QA
pipeline); only the tile, bbox and output paths differ. No fabricated terrain.
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
        "name": "Copernicus_DSM_COG_10_N30_00_E078_00_DEM.tif",
        "url": "https://copernicus-dem-30m.s3.amazonaws.com/Copernicus_DSM_COG_10_N30_00_E078_00_DEM/Copernicus_DSM_COG_10_N30_00_E078_00_DEM.tif"
    }
]

DEM_SOURCE_DIR = r"E:\dam\data\tehri\dem\source"
DEM_PROCESSED_DIR = r"E:\dam\data\tehri\dem\processed"
BOUNDARIES_DIR = r"E:\dam\data\tehri\boundaries"

os.makedirs(DEM_SOURCE_DIR, exist_ok=True)
os.makedirs(DEM_PROCESSED_DIR, exist_ok=True)
os.makedirs(BOUNDARIES_DIR, exist_ok=True)

# Tehri study bbox (from data/tehri/metadata.json study_domain).
STUDY_BBOX = {
    "min_lon": 78.40,
    "min_lat": 30.30,
    "max_lon": 78.56,
    "max_lat": 30.45
}

NODATA_VALUE = -32767.0


def download_file(url, dest_path):
    print(f"Downloading {url} -> {dest_path}...", flush=True)
    headers = {"User-Agent": "DamBreakFloodModel/1.0 (Geospatial Digital Twin)"}
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
        "name": "Tehri Study Area Boundary (Preliminary)",
        "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}},
        "features": [{
            "type": "Feature",
            "properties": {
                "study_area": "Tehri Dam & Downstream Bhagirathi Valley",
                "boundary_status": "preliminary",
                "dam_name": "Tehri Dam",
                "river": "Bhagirathi",
                "state": "Uttarakhand",
                "min_lat": STUDY_BBOX["min_lat"], "max_lat": STUDY_BBOX["max_lat"],
                "min_lon": STUDY_BBOX["min_lon"], "max_lon": STUDY_BBOX["max_lon"],
                "description": "Tehri rockfill dam, reservoir basin, and the downstream Bhagirathi gorge toward Devprayag."
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
        }]
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

    print("\nOpening source DEM tile(s) for mosaicking...", flush=True)
    src_datasets = [rasterio.open(p) for p in tile_paths]
    mosaic, out_trans = merge(src_datasets, nodata=NODATA_VALUE)
    out_meta = src_datasets[0].meta.copy()
    out_meta.update({
        "driver": "GTiff", "height": mosaic.shape[1], "width": mosaic.shape[2],
        "transform": out_trans, "nodata": NODATA_VALUE, "dtype": "float32"
    })
    for s in src_datasets:
        s.close()

    temp_mosaic_path = os.path.join(DEM_SOURCE_DIR, "mosaic_temp.tif")
    with rasterio.open(temp_mosaic_path, "w", **out_meta) as dest:
        dest.write(mosaic.astype(np.float32))

    print("Cropping mosaic to Tehri study bbox...", flush=True)
    geom = [box(STUDY_BBOX["min_lon"], STUDY_BBOX["min_lat"], STUDY_BBOX["max_lon"], STUDY_BBOX["max_lat"])]
    with rasterio.open(temp_mosaic_path) as src_merged:
        out_image, out_transform = mask(src_merged, geom, crop=True, nodata=NODATA_VALUE)
        out_meta = src_merged.meta.copy()
        out_meta.update({
            "driver": "GTiff", "height": out_image.shape[1], "width": out_image.shape[2],
            "transform": out_transform, "compress": "lzw", "nodata": NODATA_VALUE, "dtype": "float32"
        })
        processed_path = os.path.join(DEM_PROCESSED_DIR, "tehri_dem_30m.tif")
        with rasterio.open(processed_path, "w", **out_meta) as dest:
            dest.write(out_image.astype(np.float32))
        print(f"Saved processed DEM: {processed_path}", flush=True)

    if os.path.exists(temp_mosaic_path):
        os.remove(temp_mosaic_path)

    with rasterio.open(processed_path) as ds:
        data = ds.read(1)
        total_pixels = data.size
        nodata_mask = (data == ds.nodata) | np.isnan(data)
        valid_elev = data[~nodata_mask]
        print("\n" + "=" * 50)
        print("PROCESSED TEHRI DEM QUALITY STATS:")
        print("=" * 50)
        print(f"Dimensions: {ds.width} x {ds.height} ({total_pixels} px)")
        print(f"CRS: {ds.crs}  Resolution(deg): {ds.res}")
        print(f"Bounds: L={ds.bounds.left:.5f} B={ds.bounds.bottom:.5f} R={ds.bounds.right:.5f} T={ds.bounds.top:.5f}")
        print(f"Nodata pixels: {int(nodata_mask.sum())} ({nodata_mask.sum()/total_pixels*100:.2f}%)")
        print(f"Valid pixels: {len(valid_elev)} ({len(valid_elev)/total_pixels*100:.2f}%)")
        print(f"Min/Mean/Max elev: {valid_elev.min():.1f} / {valid_elev.mean():.1f} / {valid_elev.max():.1f} m MSL")
        cov = (ds.bounds.left <= STUDY_BBOX["min_lon"] + 1e-4 and ds.bounds.right >= STUDY_BBOX["max_lon"] - 1e-4
               and ds.bounds.bottom <= STUDY_BBOX["min_lat"] + 1e-4 and ds.bounds.top >= STUDY_BBOX["max_lat"] - 1e-4)
        print(f"Full study area coverage: {cov}")
        print("=" * 50, flush=True)


if __name__ == "__main__":
    create_study_area_geojson()
    acquire_and_process_dem()
