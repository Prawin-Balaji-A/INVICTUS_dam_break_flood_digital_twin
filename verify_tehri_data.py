"""
verify_tehri_data.py

PHASE 2 - Verification of the data produced by prepare_tehri_data.py.

Performs NO downloads and NO fabrication. Only reads files already
written under tehri_data/ and reports on them, plus produces a
combined verification preview image.

Run only AFTER prepare_tehri_data.py has completed successfully.
"""

import sys
import json
from pathlib import Path

try:
    import numpy as np
    import rasterio
    import geopandas as gpd
    from shapely.geometry import Point
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
except ImportError as e:
    print(f"MISSING PACKAGE: {e}")
    print("pip install numpy rasterio geopandas shapely matplotlib")
    sys.exit(1)

DATA_ROOT = Path("tehri_data")
TERRAIN_PATH = DATA_ROOT / "terrain" / "terrain.tif"
VECTOR_DIR = DATA_ROOT / "vector"
META_PATH = DATA_ROOT / "metadata" / "metadata.json"
PREVIEW_DIR = DATA_ROOT / "preview"
PREVIEW_DIR.mkdir(parents=True, exist_ok=True)


def require(path: Path, what: str):
    if not path.exists():
        print(f"MISSING DATA: {what} not found at {path}")
        print("Run prepare_tehri_data.py first.")
        sys.exit(1)


def hillshade(elevation, azimuth=315, angle_altitude=45):
    az = np.radians(360.0 - azimuth)
    alt = np.radians(angle_altitude)
    x, y = np.gradient(elevation)
    slope = np.pi / 2.0 - np.arctan(np.sqrt(x * x + y * y))
    aspect = np.arctan2(-x, y)
    shaded = np.sin(alt) * np.sin(slope) + np.cos(alt) * np.cos(slope) * np.cos(az - aspect)
    return (shaded + 1) / 2.0


def main():
    require(META_PATH, "metadata.json")
    require(TERRAIN_PATH, "terrain.tif")

    with open(META_PATH, "r", encoding="utf-8") as f:
        meta = json.load(f)

    dam_easting = meta["local_origin"]["easting"]
    dam_northing = meta["local_origin"]["northing"]
    projected_crs = meta["crs"]["projected_crs"]

    print("=" * 70)
    print("TEHRI DAM — PHASE 2: DATA VERIFICATION REPORT")
    print("=" * 70)

    with rasterio.open(TERRAIN_PATH) as src:
        arr = src.read(1).astype(float)
        nodata = src.nodata
        valid = arr[arr != nodata] if nodata is not None else arr
        print("\n[TERRAIN]")
        print(f"  Path:            {TERRAIN_PATH}")
        print(f"  Dimensions:      {src.width} x {src.height} px")
        print(f"  CRS:             {src.crs}")
        print(f"  Pixel size:      {src.res}")
        print(f"  Bounds:          {src.bounds}")
        if valid.size:
            print(f"  Elevation min:   {float(np.nanmin(valid)):.2f} m")
            print(f"  Elevation max:   {float(np.nanmax(valid)):.2f} m")
            print(f"  Elevation range: {float(np.nanmax(valid) - np.nanmin(valid)):.2f} m")
        void_count = int(np.sum(arr == nodata)) if nodata is not None else 0
        print(f"  Void/nodata px:  {void_count}")
        extent = [src.bounds.left, src.bounds.right, src.bounds.bottom, src.bounds.top]
        fill_val = float(np.nanmin(valid)) if valid.size else 0.0
        shade = hillshade(np.nan_to_num(arr, nan=fill_val))

    def load_layer(name):
        p = VECTOR_DIR / f"{name}.geojson"
        require(p, f"{name}.geojson")
        return gpd.read_file(p)

    buildings = load_layer("buildings")
    roads = load_layer("roads")
    waterways = load_layer("waterways")
    water = load_layer("water")

    print("\n[VECTOR DATA]")
    print(f"  Buildings:        {len(buildings)}")
    print(f"  Roads:            {len(roads)}")
    print(f"  Waterways:        {len(waterways)}")
    print(f"  Water polygons:   {len(water)}")

    dam_point = Point(dam_easting, dam_northing)

    with rasterio.open(TERRAIN_PATH) as src:
        b = src.bounds
        center_point = Point((b.left + b.right) / 2.0, (b.bottom + b.top) / 2.0)
    dist_center_to_dam = dam_point.distance(center_point)

    print("\n[GEOGRAPHIC SANITY CHECKS]")
    print(f"  Dam location (dam_name):   {meta['dam_name']}")
    print(f"  Dam lat/lon:               {meta['dam_location']['lat']:.6f}, {meta['dam_location']['lon']:.6f}")
    print(f"  Dam coordinate source:     {meta['dam_location']['source']}")
    print(f"  Projected CRS:             {projected_crs}")
    print(f"  Dam projected (E,N):       {dam_easting:.2f}, {dam_northing:.2f}")
    print(f"  Dataset raster bounds:     {b}")
    print(f"  Distance (AOI center→dam): {dist_center_to_dam:.2f} m "
          f"(should be small — AOI was built centered on the dam)")

    if not buildings.empty:
        buildings_within_3km = buildings[buildings.geometry.distance(dam_point) <= 3000]
        print(f"  Buildings within 3 km of dam: {len(buildings_within_3km)}")
    else:
        print("  Buildings within 3 km of dam: 0 (no building data)")

    if not water.empty:
        nearest_water_dist = water.geometry.distance(dam_point).min()
        print(f"  Distance from dam to nearest water polygon: {nearest_water_dist:.1f} m "
              f"(expect near 0 if dam sits at/adjacent to reservoir)")
    else:
        print("  No water polygons found — cannot verify reservoir adjacency.")

    fig, ax = plt.subplots(figsize=(10, 10))
    ax.imshow(shade, cmap="gray", extent=extent, origin="upper", alpha=0.6)
    ax.imshow(arr, cmap="terrain", extent=extent, origin="upper", alpha=0.4)

    if not water.empty:
        water.plot(ax=ax, color="#3a7ca5", alpha=0.7, label="Water/reservoir")
    if not waterways.empty:
        waterways.plot(ax=ax, color="#1b4965", linewidth=1.2, label="Waterways")
    if not roads.empty:
        roads.plot(ax=ax, color="#2b2b2b", linewidth=0.6, label="Roads")
    if not buildings.empty:
        buildings.plot(ax=ax, color="#c1440e", linewidth=0, label="Buildings")

    ax.scatter([dam_easting], [dam_northing], c="yellow", edgecolor="black",
               marker="*", s=300, zorder=6, label="Dam (geocoded)")
    ax.set_title(f"{meta['dam_name']} — Verification Preview\n"
                 f"CRS: {projected_crs} | Source: {meta['dam_location']['source']}")
    ax.set_aspect("equal")
    ax.legend(loc="upper right", fontsize=8)

    out_path = PREVIEW_DIR / "verification_preview.png"
    fig.savefig(out_path, dpi=160, bbox_inches="tight")
    plt.close(fig)

    print(f"\n[OUTPUT]")
    print(f"  Verification preview saved: {out_path}")
    print("\nManually inspect this image before proceeding to Blender generation:")
    print("  - Does the yellow star sit at a dam-shaped constriction in the valley?")
    print("  - Is there a large water body (reservoir) immediately upstream of it?")
    print("  - Do roads/buildings look plausible for this region?")
    print("=" * 70)


if __name__ == "__main__":
    main()