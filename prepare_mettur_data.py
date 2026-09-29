import os
import json
import gzip
import shutil
import time
import logging
import zipfile
from pathlib import Path

import requests
import numpy as np
import rasterio
from rasterio.transform import from_origin
from rasterio.warp import calculate_default_transform, reproject, Resampling
from pyproj import Transformer


# ============================================================
# METTUR DAM DIGITAL TWIN
# PHASE 1 — REAL DEM + REAL OSM DATA
# ============================================================

BASE = Path(r"E:\dam\mettur_data")

RAW_DEM = BASE / "raw" / "dem"
RAW_OSM = BASE / "raw" / "osm"
TERRAIN_DIR = BASE / "terrain"
VECTOR_DIR = BASE / "vector"
META_DIR = BASE / "metadata"

for p in [
    RAW_DEM,
    RAW_OSM,
    TERRAIN_DIR,
    VECTOR_DIR,
    META_DIR,
]:
    p.mkdir(parents=True, exist_ok=True)


# ============================================================
# ACTUAL METTUR DAM LOCATION
# ============================================================

DAM_LAT = 11.80346
DAM_LON = 77.80627

# AOI radius in degrees.
# About 10 km around the dam.
LAT_RADIUS = 0.09
LON_RADIUS = 0.09

SOUTH = DAM_LAT - LAT_RADIUS
WEST = DAM_LON - LON_RADIUS
NORTH = DAM_LAT + LAT_RADIUS
EAST = DAM_LON + LON_RADIUS

# UTM zone 43N
PROJECTED_CRS = "EPSG:32643"

OSM_FILE = VECTOR_DIR / "mettur.osm"
DEM_FILE = TERRAIN_DIR / "terrain.tif"
METADATA_FILE = META_DIR / "metadata.json"


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

log = logging.getLogger("METTUR")


# ============================================================
# 1. DOWNLOAD SRTM DEM
# ============================================================

def download_dem():

    log.info("=" * 70)
    log.info("ACQUIRING REAL SRTM DEM")
    log.info("=" * 70)

    # Mettur lies in N11E077
    tile_name = "N11E077"
    url = (
        "https://s3.amazonaws.com/"
        "elevation-tiles-prod/skadi/"
        "N11/N11E077.hgt.gz"
    )

    gz_path = RAW_DEM / f"{tile_name}.hgt.gz"
    hgt_path = RAW_DEM / f"{tile_name}.hgt"

    if not gz_path.exists():

        log.info("Downloading:")
        log.info(url)

        r = requests.get(
            url,
            timeout=120,
            headers={
                "User-Agent":
                "Mettur-Dam-Digital-Twin/1.0"
            }
        )

        r.raise_for_status()

        gz_path.write_bytes(r.content)

        log.info(
            f"Downloaded: {gz_path}"
        )

    else:
        log.info(
            "Using existing DEM download."
        )

    # --------------------------------------------------------
    # Extract HGT
    # --------------------------------------------------------

    if not hgt_path.exists():

        log.info("Extracting HGT...")

        with gzip.open(gz_path, "rb") as src:
            with open(hgt_path, "wb") as dst:
                shutil.copyfileobj(src, dst)

    # --------------------------------------------------------
    # Read HGT
    # --------------------------------------------------------

    log.info("Reading SRTM HGT...")

    data = np.fromfile(
        hgt_path,
        dtype=">i2"
    )

    expected = 3601 * 3601

    if data.size != expected:
        raise RuntimeError(
            f"Unexpected HGT size: "
            f"{data.size}, expected {expected}"
        )

    data = data.reshape(
        (3601, 3601)
    )

    # --------------------------------------------------------
    # Crop approximately to AOI
    # --------------------------------------------------------

    # SRTM N11E077:
    # north = 12
    # south = 11
    # west  = 77
    # east  = 78

    lat_resolution = 1.0 / 3600.0
    lon_resolution = 1.0 / 3600.0

    row_top = int(
        (12.0 - NORTH) / lat_resolution
    )

    row_bottom = int(
        (12.0 - SOUTH) / lat_resolution
    )

    col_left = int(
        (WEST - 77.0) / lon_resolution
    )

    col_right = int(
        (EAST - 77.0) / lon_resolution
    )

    row_top = max(0, row_top)
    row_bottom = min(3601, row_bottom)

    col_left = max(0, col_left)
    col_right = min(3601, col_right)

    cropped = data[
        row_top:row_bottom,
        col_left:col_right
    ]

    if cropped.size == 0:
        raise RuntimeError(
            "DEM crop is empty. "
            "Check AOI coordinates."
        )

    log.info(
        f"DEM crop size: {cropped.shape}"
    )

    # --------------------------------------------------------
    # Replace SRTM void values
    # --------------------------------------------------------

    cropped = cropped.astype(np.float32)

    invalid = cropped <= -32000

    if np.any(invalid):

        log.warning(
            f"DEM contains "
            f"{np.sum(invalid)} void pixels."
        )

        # nearest valid value
        valid_values = cropped[~invalid]

        if valid_values.size == 0:
            raise RuntimeError(
                "DEM contains no valid elevations."
            )

        fill_value = float(
            np.median(valid_values)
        )

        cropped[invalid] = fill_value

    # --------------------------------------------------------
    # Write temporary WGS84 DEM
    # --------------------------------------------------------

    west_pixel = (
        77.0 +
        col_left / 3600.0
    )

    north_pixel = (
        12.0 -
        row_top / 3600.0
    )

    transform = from_origin(
        west_pixel,
        north_pixel,
        lon_resolution,
        lat_resolution
    )

    temp_wgs84 = RAW_DEM / "mettur_dem_wgs84.tif"

    with rasterio.open(
        temp_wgs84,
        "w",
        driver="GTiff",
        height=cropped.shape[0],
        width=cropped.shape[1],
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=transform,
        nodata=-32768,
        compress="deflate"
    ) as dst:

        dst.write(
            cropped,
            1
        )

    # --------------------------------------------------------
    # Reproject to UTM 43N
    # --------------------------------------------------------

    log.info(
        "Reprojecting DEM to EPSG:32643..."
    )

    with rasterio.open(
        temp_wgs84
    ) as src:

        transform2, width2, height2 = (
            calculate_default_transform(
                src.crs,
                PROJECTED_CRS,
                src.width,
                src.height,
                *src.bounds
            )
        )

        profile = src.profile.copy()

        profile.update(
            crs=PROJECTED_CRS,
            transform=transform2,
            width=width2,
            height=height2,
            dtype="float32",
            compress="deflate",
            nodata=-32768
        )

        with rasterio.open(
            DEM_FILE,
            "w",
            **profile
        ) as dst:

            reproject(
                source=rasterio.band(
                    src,
                    1
                ),
                destination=rasterio.band(
                    dst,
                    1
                ),
                src_transform=src.transform,
                src_crs=src.crs,
                dst_transform=transform2,
                dst_crs=PROJECTED_CRS,
                resampling=Resampling.bilinear
            )

    log.info(
        f"Terrain written: {DEM_FILE}"
    )


# ============================================================
# 2. DOWNLOAD REAL OSM DATA
# ============================================================

def download_osm():

    log.info("=" * 70)
    log.info("ACQUIRING REAL OPENSTREETMAP DATA")
    log.info("=" * 70)

    # Overpass query.
    #
    # IMPORTANT:
    # We explicitly request:
    #
    # buildings
    # roads
    # waterways
    # water bodies
    # dams
    #
    query = f"""
[out:json][timeout:180];

(
  way["building"](
    {SOUTH},
    {WEST},
    {NORTH},
    {EAST}
  );

  relation["building"](
    {SOUTH},
    {WEST},
    {NORTH},
    {EAST}
  );

  way["highway"](
    {SOUTH},
    {WEST},
    {NORTH},
    {EAST}
  );

  way["waterway"](
    {SOUTH},
    {WEST},
    {NORTH},
    {EAST}
  );

  way["natural"="water"](
    {SOUTH},
    {WEST},
    {NORTH},
    {EAST}
  );

  relation["natural"="water"](
    {SOUTH},
    {WEST},
    {NORTH},
    {EAST}
  );

  way["landuse"="reservoir"](
    {SOUTH},
    {WEST},
    {NORTH},
    {EAST}
  );

  relation["landuse"="reservoir"](
    {SOUTH},
    {WEST},
    {NORTH},
    {EAST}
  );

  way["waterway"="dam"](
    {SOUTH},
    {WEST},
    {NORTH},
    {EAST}
  );
);

out geom;
"""

    endpoints = [
        "https://overpass-api.de/api/interpreter",
        "https://overpass.kumi.systems/api/interpreter",
        "https://overpass.private.coffee/api/interpreter",
    ]

    result = None

    for endpoint in endpoints:

        log.info(
            f"Trying: {endpoint}"
        )

        try:

            response = requests.post(
                endpoint,
                data=query.encode("utf-8"),
                timeout=240,
                headers={
                    "User-Agent":
                    "Mettur-Dam-Digital-Twin/1.0"
                }
            )

            response.raise_for_status()

            result = response.json()

            log.info(
                f"OSM elements received: "
                f"{len(result.get('elements', []))}"
            )

            break

        except Exception as e:

            log.warning(
                f"Endpoint failed: {e}"
            )

            time.sleep(2)

    if result is None:

        raise RuntimeError(
            "All Overpass endpoints failed. "
            "No OSM data was downloaded."
        )

    # --------------------------------------------------------
    # Save exact Overpass JSON
    # --------------------------------------------------------

    with open(
        OSM_FILE,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            result,
            f,
            indent=2
        )

    log.info(
        f"OSM data saved: {OSM_FILE}"
    )

    # --------------------------------------------------------
    # Basic statistics
    # --------------------------------------------------------

    elements = result.get(
        "elements",
        []
    )

    buildings = 0
    roads = 0
    waterways = 0
    water = 0
    dams = 0

    for el in elements:

        tags = el.get(
            "tags",
            {}
        )

        if "building" in tags:
            buildings += 1

        if "highway" in tags:
            roads += 1

        if "waterway" in tags:
            waterways += 1

        if (
            tags.get("natural") == "water"
            or
            tags.get("landuse") == "reservoir"
        ):
            water += 1

        if tags.get("waterway") == "dam":
            dams += 1

    log.info(
        "--------------------------------------------------"
    )

    log.info(
        f"Buildings : {buildings}"
    )

    log.info(
        f"Roads     : {roads}"
    )

    log.info(
        f"Waterways : {waterways}"
    )

    log.info(
        f"Water      : {water}"
    )

    log.info(
        f"Dams       : {dams}"
    )


# ============================================================
# 3. METADATA
# ============================================================

def write_metadata():

    log.info("=" * 70)
    log.info("WRITING METADATA")
    log.info("=" * 70)

    metadata = {
        "project": "Mettur Dam Digital Twin",

        "location": {
            "latitude": DAM_LAT,
            "longitude": DAM_LON
        },

        "aoi": {
            "south": SOUTH,
            "west": WEST,
            "north": NORTH,
            "east": EAST
        },

        "crs": PROJECTED_CRS,

        "data_sources": {
            "terrain": "SRTM",
            "buildings": "OpenStreetMap",
            "roads": "OpenStreetMap",
            "waterways": "OpenStreetMap",
            "water_bodies": "OpenStreetMap",
            "dam": "OpenStreetMap"
        },

        "files": {
            "terrain": str(
                DEM_FILE
            ),
            "osm": str(
                OSM_FILE
            )
        },

        "notes": [
            "Building geometry comes from OSM.",
            "Road geometry comes from OSM.",
            "Water geometry comes from OSM.",
            "Terrain elevation comes from SRTM.",
            "No synthetic building locations are generated."
        ]
    }

    with open(
        METADATA_FILE,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            metadata,
            f,
            indent=2
        )

    log.info(
        f"Metadata written: {METADATA_FILE}"
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print("=" * 70)
    print("METTUR DAM DIGITAL TWIN — PHASE 1")
    print("=" * 70)
    print(
        f"Dam location: "
        f"{DAM_LAT}, {DAM_LON}"
    )
    print(
        f"CRS: {PROJECTED_CRS}"
    )
    print(
        f"AOI: "
        f"{SOUTH:.6f}, "
        f"{WEST:.6f}, "
        f"{NORTH:.6f}, "
        f"{EAST:.6f}"
    )
    print("=" * 70)
    print()

    download_dem()

    print()

    download_osm()

    print()

    write_metadata()

    print()
    print("=" * 70)
    print("METTUR PHASE 1 COMPLETE")
    print("=" * 70)
    print()
    print("REAL DATA:")
    print(
        f"  Terrain : {DEM_FILE}"
    )
    print(
        f"  OSM     : {OSM_FILE}"
    )
    print(
        f"  Metadata: {METADATA_FILE}"
    )
    print()
    print("Next:")
    print("  python convert_mettur_osm.py")
    print("=" * 70)


if __name__ == "__main__":
    main()