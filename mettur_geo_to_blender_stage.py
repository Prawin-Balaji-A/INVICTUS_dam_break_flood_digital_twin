import os
import json
import numpy as np
import geopandas as gpd
import rasterio
from rasterio.transform import rowcol
from scipy.ndimage import zoom

BASE = r"E:\dam\mettur_data"
OUT = os.path.join(BASE, "blender_ready")

os.makedirs(OUT, exist_ok=True)

TERRAIN = os.path.join(BASE, "terrain", "terrain.tif")
VECTOR = os.path.join(BASE, "vector")

print("=" * 70)
print("METTUR DAM — GEOSPATIAL DATA → BLENDER")
print("=" * 70)

# ---------------------------------------------------------
# TERRAIN
# ---------------------------------------------------------

print("\n[1/5] Reading terrain...")

with rasterio.open(TERRAIN) as src:

    elevation = src.read(1).astype(np.float32)

    transform = src.transform
    crs = src.crs

    nodata = src.nodata

    bounds = src.bounds

    print("  CRS:", crs)
    print("  Size:", elevation.shape)
    print("  Bounds:", bounds)
    print("  Nodata:", nodata)

    if nodata is not None:
        mask = elevation == nodata
        if np.any(mask):
            valid = elevation[~mask]
            elevation[mask] = np.mean(valid)
            print("  Filled nodata using mean elevation.")

    # Downsample for Blender
    max_size = 350

    h, w = elevation.shape

    step = max(1, int(max(h, w) / max_size))

    terrain = elevation[::step, ::step]

    print("  Blender terrain:", terrain.shape)
    print(
        "  Elevation:",
        float(np.min(terrain)),
        "to",
        float(np.max(terrain))
    )

    # Save raw terrain values
    terrain.astype(np.float32).tofile(
        os.path.join(OUT, "terrain_heightmap.f32")
    )

    terrain_meta = {
        "width": int(terrain.shape[1]),
        "height": int(terrain.shape[0]),
        "native_width": int(w),
        "native_height": int(h),
        "crs": str(crs),
        "bounds": {
            "left": bounds.left,
            "bottom": bounds.bottom,
            "right": bounds.right,
            "top": bounds.top
        },
        "transform": [
            transform.a,
            transform.b,
            transform.c,
            transform.d,
            transform.e,
            transform.f
        ],
        "downsample_step": step,
        "elevation_min": float(np.min(terrain)),
        "elevation_max": float(np.max(terrain))
    }

with open(
    os.path.join(OUT, "terrain_meta.json"),
    "w",
    encoding="utf-8"
) as f:
    json.dump(terrain_meta, f, indent=2)

print("  Terrain exported.")


# ---------------------------------------------------------
# VECTOR DATA
# ---------------------------------------------------------

def process_vector(filename, output_name):

    source = os.path.join(VECTOR, filename)

    if not os.path.exists(source):
        print("  Missing:", source)
        return

    gdf = gpd.read_file(source)

    print(
        f"  {filename}:",
        len(gdf),
        "features",
        "| CRS:",
        gdf.crs
    )

    if gdf.empty:
        return

    # Convert to local projected CRS
    if gdf.crs != crs:
        gdf = gdf.to_crs(crs)

    # Save
    output = os.path.join(
        OUT,
        output_name
    )

    # GeoJSON requires geographic CRS
    gdf_geo = gdf.to_crs("EPSG:4326")

    gdf_geo.to_file(
        output,
        driver="GeoJSON"
    )

    print("  Written:", output)


print("\n[2/5] Processing buildings...")
process_vector(
    "buildings.geojson",
    "buildings.geojson"
)

print("\n[3/5] Processing roads...")
process_vector(
    "roads.geojson",
    "roads.geojson"
)

print("\n[4/5] Processing waterways...")
process_vector(
    "waterways.geojson",
    "waterways.geojson"
)

print("\n[5/5] Processing water...")
process_vector(
    "water.geojson",
    "water.geojson"
)


# ---------------------------------------------------------
# METTUR LOCATION
# ---------------------------------------------------------

print("\nCreating scene metadata...")

# Approximate center used by Phase 1.
LAT = 11.75
LON = 77.75

# UTM zone 43N
PROJECTED_CRS = "EPSG:32643"

scene_metadata = {
    "name": "Mettur Dam Digital Twin",
    "location": {
        "latitude": LAT,
        "longitude": LON
    },
    "projected_crs": PROJECTED_CRS,
    "source": {
        "terrain": "SRTM DEM",
        "vector": "OpenStreetMap via Overpass API"
    },
    "files": {
        "terrain": "terrain_heightmap.f32",
        "terrain_meta": "terrain_meta.json",
        "buildings": "buildings.geojson",
        "roads": "roads.geojson",
        "waterways": "waterways.geojson",
        "water": "water.geojson"
    }
}

with open(
    os.path.join(OUT, "scene_metadata.json"),
    "w",
    encoding="utf-8"
) as f:
    json.dump(scene_metadata, f, indent=2)


print("\n" + "=" * 70)
print("METTUR BLENDER-READY DATA COMPLETE")
print("=" * 70)

print("\nOutput:")
print(OUT)

print("\nFiles:")

for name in os.listdir(OUT):
    print(" ", name)

print("=" * 70)