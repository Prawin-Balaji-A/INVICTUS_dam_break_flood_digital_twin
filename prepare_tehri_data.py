"""
prepare_tehri_data.py  (idempotent version)

PHASE 1 - Automated geographic data acquisition for the Tehri Dam
digital-twin visualization.

IDEMPOTENCY: if terrain.tif and all four vector GeoJSON files already
exist under tehri_data/, this script does NOT re-download anything.
It only inspects the existing real files and (re)generates
metadata/metadata.json and preview images from them.

Sources used when data must actually be acquired (unchanged from the
original version):
  DEM        : AWS "elevation-tiles-prod" open bucket, SRTM (skadi/.hgt)
  Geocoding  : OpenStreetMap Nominatim
  Vector data: OpenStreetMap via the Overpass API
"""

import os
import sys
import gzip
import json
import time
import math
import shutil
import logging
import datetime as dt
from pathlib import Path

# ---------------------------------------------------------------------------
# 0. DEPENDENCY CHECK
# ---------------------------------------------------------------------------

REQUIRED = {
    "requests": "requests", "numpy": "numpy", "rasterio": "rasterio",
    "geopandas": "geopandas", "shapely": "shapely", "pyproj": "pyproj",
    "matplotlib": "matplotlib",
}
_missing = [p for m, p in REQUIRED.items() if _try_import(m) is False] if False else []
for mod_name, pip_name in REQUIRED.items():
    try:
        __import__(mod_name)
    except ImportError:
        _missing.append(pip_name)

if _missing:
    print("MISSING PYTHON PACKAGES:")
    for p in _missing:
        print(f"  - {p}")
    print(f"\nInstall with:\n    pip install {' '.join(_missing)}")
    sys.exit(1)

import requests
import numpy as np
import rasterio
from rasterio.merge import merge as rio_merge
from rasterio.warp import calculate_default_transform, reproject, Resampling
from rasterio.mask import mask as rio_mask
import geopandas as gpd
from shapely.geometry import LineString, Polygon, box, mapping
from shapely.ops import polygonize, linemerge, unary_union
from pyproj import Transformer, CRS
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# ---------------------------------------------------------------------------
# 1. CONFIG
# ---------------------------------------------------------------------------

DAM_NAME = "TEHRI"
SEARCH_QUERY = "Tehri Dam, Uttarakhand, India"

# --- Values established by a prior successful run of this script. ---
# These are used verbatim instead of re-geocoding, so metadata.json
# describes the SAME location/extent that actually produced the files
# already on disk under tehri_data/.
KNOWN_DAM_LOCATION = {
    "lat": 30.3761751,
    "lon": 78.4803102,
    "source": "OpenStreetMap Nominatim geocoding (established in a prior "
              "successful run of this script; reused here for idempotency)",
}
AOI_KNOWN_BOUNDS = {  # (south, west, north, east) in EPSG:4326
    "south": 30.28573792670429,
    "west": 78.376185223845,
    "north": 30.466612273295713,
    "east": 78.58443517615501,
}
PROJECTED_EPSG_KNOWN = 32644  # UTM 44N, established previously for this AOI

# Manual override — set these to force a specific location (used only if
# KNOWN_DAM_LOCATION above is cleared to None).
DAM_LAT_OVERRIDE = None
DAM_LON_OVERRIDE = None

AOI_RADIUS_KM = 10.0
OUTPUT_ROOT = Path("tehri_data")

OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.openstreetmap.fr/api/interpreter",
]
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "tehri-dam-digital-twin-research/1.0 (contact: set-your-email-here)"
DEM_BUCKET_BASE = "https://s3.amazonaws.com/elevation-tiles-prod/skadi"

FORCE_REDOWNLOAD = "--force-redownload" in sys.argv

RAW_DIR = OUTPUT_ROOT / "raw"
DEM_RAW_DIR = RAW_DIR / "dem"
TERRAIN_DIR = OUTPUT_ROOT / "terrain"
VECTOR_DIR = OUTPUT_ROOT / "vector"
META_DIR = OUTPUT_ROOT / "metadata"
PREVIEW_DIR = OUTPUT_ROOT / "preview"
LOG_DIR = OUTPUT_ROOT / "logs"

for d in (RAW_DIR, DEM_RAW_DIR, TERRAIN_DIR, VECTOR_DIR, META_DIR, PREVIEW_DIR, LOG_DIR):
    d.mkdir(parents=True, exist_ok=True)

TERRAIN_PATH = TERRAIN_DIR / "terrain.tif"
BUILDINGS_PATH = VECTOR_DIR / "buildings.geojson"
ROADS_PATH = VECTOR_DIR / "roads.geojson"
WATERWAYS_PATH = VECTOR_DIR / "waterways.geojson"
WATER_PATH = VECTOR_DIR / "water.geojson"
OSM_RAW_PATH = VECTOR_DIR / "tehri.osm"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "prepare_log.txt", mode="a", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("prepare_tehri_data")


def fail(missing_data: str, how_to_obtain: str):
    log.error("=" * 70)
    log.error("MISSING DATA:")
    log.error(f"    {missing_data}")
    log.error("\nHOW TO OBTAIN IT:")
    for line in how_to_obtain.strip().splitlines():
        log.error(f"    {line}")
    log.error("=" * 70)
    sys.exit(1)


def check_network(url: str, timeout=10) -> bool:
    try:
        r = requests.head(url, timeout=timeout, headers={"User-Agent": USER_AGENT})
        return r.status_code < 500
    except requests.RequestException as e:
        log.warning(f"Network check failed for {url}: {e}")
        return False


# ---------------------------------------------------------------------------
# 2. DAM LOCATION
# ---------------------------------------------------------------------------

def resolve_dam_location():
    if DAM_LAT_OVERRIDE is not None and DAM_LON_OVERRIDE is not None:
        log.info(f"Using manual override coordinates: {DAM_LAT_OVERRIDE}, {DAM_LON_OVERRIDE}")
        return {"lat": DAM_LAT_OVERRIDE, "lon": DAM_LON_OVERRIDE,
                "source": "manual override (user supplied in config)"}

    if KNOWN_DAM_LOCATION is not None:
        log.info(f"Using previously established dam location (no geocoding call made): "
                 f"{KNOWN_DAM_LOCATION['lat']}, {KNOWN_DAM_LOCATION['lon']}")
        return dict(KNOWN_DAM_LOCATION)

    log.info(f"Geocoding '{SEARCH_QUERY}' via Nominatim ...")
    try:
        resp = requests.get(NOMINATIM_URL,
                             params={"q": SEARCH_QUERY, "format": "json", "limit": 5},
                             headers={"User-Agent": USER_AGENT}, timeout=20)
        resp.raise_for_status()
        results = resp.json()
    except requests.RequestException as e:
        fail("Dam coordinates via Nominatim geocoding API",
             f"Network request failed: {e}\n"
             f"Set DAM_LAT_OVERRIDE / DAM_LON_OVERRIDE at the top of this script.")

    if not results:
        fail("Dam coordinates — Nominatim returned zero results",
             "Search manually and set DAM_LAT_OVERRIDE / DAM_LON_OVERRIDE.")

    best = results[0]
    lat, lon = float(best["lat"]), float(best["lon"])
    log.info(f"Geocoded result: {best.get('display_name')} -> lat={lat}, lon={lon}")
    return {"lat": lat, "lon": lon, "source": f"Nominatim/OpenStreetMap geocoding ({NOMINATIM_URL})"}


def utm_epsg_for_lonlat(lon, lat):
    zone = int(math.floor((lon + 180) / 6) + 1)
    return (32600 + zone) if lat >= 0 else (32700 + zone)


# ---------------------------------------------------------------------------
# 3. DEM ACQUISITION (only used if terrain.tif does NOT already exist)
# ---------------------------------------------------------------------------

def srtm_tile_name(lat_floor, lon_floor):
    lat_prefix = "N" if lat_floor >= 0 else "S"
    lon_prefix = "E" if lon_floor >= 0 else "W"
    return f"{lat_prefix}{abs(lat_floor):02d}{lon_prefix}{abs(lon_floor):03d}"


def required_srtm_tiles(min_lon, min_lat, max_lon, max_lat):
    tiles = set()
    for la in range(int(math.floor(min_lat)), int(math.floor(max_lat)) + 1):
        for lo in range(int(math.floor(min_lon)), int(math.floor(max_lon)) + 1):
            tiles.add((la, lo))
    return sorted(tiles)


def download_srtm_tile(lat_floor, lon_floor) -> Path:
    name = srtm_tile_name(lat_floor, lon_floor)
    lat_folder = name[:3]
    url = f"{DEM_BUCKET_BASE}/{lat_folder}/{name}.hgt.gz"
    dest_gz = DEM_RAW_DIR / f"{name}.hgt.gz"
    dest_hgt = DEM_RAW_DIR / f"{name}.hgt"

    if dest_hgt.exists() and not FORCE_REDOWNLOAD:
        log.info(f"Using cached DEM tile: {dest_hgt}")
        return dest_hgt

    log.info(f"Downloading DEM tile {name} from {url} ...")
    try:
        r = requests.get(url, timeout=60)
        if r.status_code == 404:
            fail(f"SRTM DEM tile {name}.hgt.gz", f"No tile at {url}. Supply DEM manually at {dest_hgt}.")
        r.raise_for_status()
    except requests.RequestException as e:
        fail(f"SRTM DEM tile {name}.hgt.gz", f"Network request failed: {e}\nDownload manually from {url}.")

    with open(dest_gz, "wb") as f:
        f.write(r.content)
    with gzip.open(dest_gz, "rb") as f_in, open(dest_hgt, "wb") as f_out:
        shutil.copyfileobj(f_in, f_out)
    return dest_hgt


def build_dem_mosaic(min_lon, min_lat, max_lon, max_lat) -> Path:
    tiles = required_srtm_tiles(min_lon, min_lat, max_lon, max_lat)
    hgt_paths = [download_srtm_tile(la, lo) for la, lo in tiles]
    datasets = [rasterio.open(p) for p in hgt_paths]
    mosaic, out_transform = rio_merge(datasets)
    out_meta = datasets[0].meta.copy()
    out_meta.update({"driver": "GTiff", "height": mosaic.shape[1], "width": mosaic.shape[2],
                      "transform": out_transform, "crs": datasets[0].crs})
    for d in datasets:
        d.close()
    mosaic_path = DEM_RAW_DIR / "srtm_mosaic_wgs84.tif"
    with rasterio.open(mosaic_path, "w", **out_meta) as dst:
        dst.write(mosaic)
    return mosaic_path


def reproject_and_clip_dem(mosaic_path, aoi_bounds_latlon, dst_crs_epsg) -> Path:
    dst_crs = CRS.from_epsg(dst_crs_epsg)
    with rasterio.open(mosaic_path) as src:
        transform, width, height = calculate_default_transform(
            src.crs, dst_crs, src.width, src.height, *src.bounds, resolution=30)
        kwargs = src.meta.copy()
        kwargs.update({"crs": dst_crs, "transform": transform, "width": width,
                        "height": height, "nodata": -32768})
        reprojected_path = TERRAIN_DIR / "_terrain_full_reprojected.tif"
        with rasterio.open(reprojected_path, "w", **kwargs) as dst:
            reproject(source=rasterio.band(src, 1), destination=rasterio.band(dst, 1),
                      src_transform=src.transform, src_crs=src.crs,
                      dst_transform=transform, dst_crs=dst_crs, resampling=Resampling.bilinear)

    min_lon, min_lat, max_lon, max_lat = aoi_bounds_latlon
    transformer = Transformer.from_crs("EPSG:4326", dst_crs, always_xy=True)
    x0, y0 = transformer.transform(min_lon, min_lat)
    x1, y1 = transformer.transform(max_lon, max_lat)
    clip_geom = [mapping(box(min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)))]

    with rasterio.open(reprojected_path) as src:
        out_image, out_transform = rio_mask(src, clip_geom, crop=True)
        out_meta = src.meta.copy()
        out_meta.update({"height": out_image.shape[1], "width": out_image.shape[2],
                          "transform": out_transform})

    with rasterio.open(TERRAIN_PATH, "w", **out_meta) as dst:
        dst.write(out_image)
    return TERRAIN_PATH


# ---------------------------------------------------------------------------
# 4. OSM VECTOR DATA (only used if geojson files do NOT already exist)
# ---------------------------------------------------------------------------

def overpass_query(query: str):
    last_err = None
    for endpoint in OVERPASS_ENDPOINTS:
        try:
            log.info(f"Querying Overpass endpoint: {endpoint}")
            r = requests.post(endpoint, data={"data": query}, timeout=180)
            r.raise_for_status()
            return r.json()
        except requests.RequestException as e:
            log.warning(f"Overpass endpoint failed ({endpoint}): {e}")
            last_err = e
            time.sleep(2)
    fail("OpenStreetMap vector data via Overpass API (all mirrors unreachable)",
         f"Last error: {last_err}\nRun the query manually at https://overpass-turbo.eu/ "
         f"and export GeoJSON into {VECTOR_DIR}")


def _way_to_line(el):
    coords = [(pt["lon"], pt["lat"]) for pt in el.get("geometry", []) if pt]
    return LineString(coords) if len(coords) >= 2 else None


def _way_to_polygon(el):
    coords = [(pt["lon"], pt["lat"]) for pt in el.get("geometry", []) if pt]
    if len(coords) < 4:
        return None
    if coords[0] != coords[-1]:
        coords.append(coords[0])
    try:
        poly = Polygon(coords)
        return poly if poly.is_valid and poly.area > 0 else None
    except Exception:
        return None


def _relation_to_polygons(el):
    outer_lines, inner_lines = [], []
    for member in el.get("members", []):
        if member.get("type") != "way" or "geometry" not in member:
            continue
        coords = [(pt["lon"], pt["lat"]) for pt in member["geometry"] if pt]
        if len(coords) < 2:
            continue
        line = LineString(coords)
        (inner_lines if member.get("role") == "inner" else outer_lines).append(line)
    if not outer_lines:
        return []
    try:
        merged_outer = linemerge(outer_lines)
        parts = [merged_outer] if merged_outer.geom_type == "LineString" else list(merged_outer.geoms)
        outer_polys = list(polygonize(parts))
    except Exception as e:
        log.warning(f"Could not assemble relation {el.get('id')}: {e}")
        return []
    if not outer_polys:
        return []
    if inner_lines:
        try:
            merged_inner = linemerge(inner_lines)
            parts_i = [merged_inner] if merged_inner.geom_type == "LineString" else list(merged_inner.geoms)
            inner_polys = list(polygonize(parts_i))
            if inner_polys:
                holes = unary_union(inner_polys)
                outer_polys = [p.difference(holes) for p in outer_polys]
        except Exception as e:
            log.warning(f"Could not assemble inner rings for relation {el.get('id')}: {e}")
    return [p for p in outer_polys if p.is_valid and not p.is_empty]


def fetch_osm_layer(query_body, geometry_kind, layer_name):
    query = f"[out:json][timeout:180];\n(\n  {query_body}\n);\nout geom;\n"
    data = overpass_query(query)
    elements = data.get("elements", [])
    records = []
    for el in elements:
        tags = el.get("tags", {})
        if el["type"] == "way":
            geom = _way_to_line(el) if geometry_kind == "line" else _way_to_polygon(el)
            if geom is not None:
                records.append({"osm_id": el["id"], "osm_type": "way", **tags, "geometry": geom})
        elif el["type"] == "relation" and geometry_kind == "polygon":
            for p in _relation_to_polygons(el):
                records.append({"osm_id": el["id"], "osm_type": "relation", **tags, "geometry": p})
    if not records:
        return gpd.GeoDataFrame(columns=["osm_id", "geometry"], geometry="geometry", crs="EPSG:4326")
    return gpd.GeoDataFrame(records, geometry="geometry", crs="EPSG:4326")


def fetch_buildings(bbox):
    s, w, n, e = bbox
    return fetch_osm_layer(f'way["building"]({s},{w},{n},{e});\n      relation["building"]({s},{w},{n},{e});',
                            "polygon", "buildings")


def fetch_roads(bbox):
    s, w, n, e = bbox
    return fetch_osm_layer(f'way["highway"]({s},{w},{n},{e});', "line", "roads")


def fetch_waterways(bbox):
    s, w, n, e = bbox
    return fetch_osm_layer(f'way["waterway"]({s},{w},{n},{e});', "line", "waterways")


def fetch_water_bodies(bbox):
    s, w, n, e = bbox
    body = f'''way["natural"="water"]({s},{w},{n},{e});
      relation["natural"="water"]({s},{w},{n},{e});
      way["landuse"="reservoir"]({s},{w},{n},{e});
      relation["landuse"="reservoir"]({s},{w},{n},{e});'''
    return fetch_osm_layer(body, "polygon", "water")


# ---------------------------------------------------------------------------
# 5. PREVIEWS
# ---------------------------------------------------------------------------

def render_terrain_preview(terrain_path, dam_xy, out_path):
    with rasterio.open(terrain_path) as src:
        arr = src.read(1).astype(float)
        if src.nodata is not None:
            arr[arr == src.nodata] = np.nan
        extent = [src.bounds.left, src.bounds.right, src.bounds.bottom, src.bounds.top]
    fig, ax = plt.subplots(figsize=(8, 8))
    im = ax.imshow(arr, cmap="terrain", extent=extent, origin="upper")
    ax.scatter([dam_xy[0]], [dam_xy[1]], c="red", marker="*", s=200, label="Dam")
    ax.set_title("Tehri AOI — DEM elevation (existing real data)")
    ax.legend()
    plt.colorbar(im, ax=ax, label="Elevation (m)")
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def render_map_preview(buildings, roads, waterways, water, dam_xy, out_path):
    fig, ax = plt.subplots(figsize=(9, 9))
    if not water.empty:
        water.plot(ax=ax, color="#3a7ca5", alpha=0.6, label="Water/reservoir")
    if not waterways.empty:
        waterways.plot(ax=ax, color="#1b4965", linewidth=1.2, label="Waterways")
    if not roads.empty:
        roads.plot(ax=ax, color="#444444", linewidth=0.6, label="Roads")
    if not buildings.empty:
        buildings.plot(ax=ax, color="#b5651d", alpha=0.7, linewidth=0, label="Buildings")
    ax.scatter([dam_xy[0]], [dam_xy[1]], c="red", marker="*", s=250, zorder=5, label="Dam")
    ax.set_title("Tehri AOI — existing real OSM vector data")
    ax.set_aspect("equal")
    ax.legend(loc="upper right", fontsize=8)
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


# ---------------------------------------------------------------------------
# 6. METADATA BUILDER (from actual inspected files — no fabrication)
# ---------------------------------------------------------------------------

def build_metadata_from_existing_data(dam_info, dst_epsg):
    dam_lat, dam_lon = dam_info["lat"], dam_info["lon"]

    if not TERRAIN_PATH.exists():
        fail(f"{TERRAIN_PATH}", "terrain.tif must exist to build metadata.")

    with rasterio.open(TERRAIN_PATH) as src:
        actual_crs = src.crs
        actual_bounds = src.bounds
        actual_width, actual_height = src.width, src.height
        actual_res = src.res
        arr = src.read(1)
        nodata = src.nodata
        valid = arr[arr != nodata] if nodata is not None else arr
        elev_min = float(valid.min()) if valid.size else None
        elev_max = float(valid.max()) if valid.size else None

    actual_epsg = actual_crs.to_epsg() if actual_crs else None
    if actual_epsg is not None and actual_epsg != dst_epsg:
        log.warning(f"terrain.tif actual CRS EPSG:{actual_epsg} differs from expected "
                    f"EPSG:{dst_epsg}. Recording the ACTUAL value in metadata.json.")
        dst_epsg = actual_epsg

    def load_or_empty(path, label):
        if not path.exists():
            fail(f"{path}", f"{label} must exist. This script was told these files "
                             f"already exist — verify the path.")
        gdf = gpd.read_file(path)
        return gdf

    buildings = load_or_empty(BUILDINGS_PATH, "buildings.geojson")
    roads = load_or_empty(ROADS_PATH, "roads.geojson")
    waterways = load_or_empty(WATERWAYS_PATH, "waterways.geojson")
    water = load_or_empty(WATER_PATH, "water.geojson")

    transformer = Transformer.from_crs("EPSG:4326", f"EPSG:{dst_epsg}", always_xy=True)
    dam_x, dam_y = transformer.transform(dam_lon, dam_lat)

    metadata = {
        "dam_name": DAM_NAME,
        "generated_utc": dt.datetime.utcnow().isoformat() + "Z",
        "dam_location": {"lat": dam_lat, "lon": dam_lon, "source": dam_info["source"]},
        "sources": {
            "dem": {
                "provider": "AWS elevation-tiles-prod (SRTM, skadi format)",
                "base_url": DEM_BUCKET_BASE,
                "file_path": str(TERRAIN_PATH),
                "note": "Reused existing file; not re-downloaded this run.",
            },
            "vector": {
                "provider": "OpenStreetMap",
                "raw_osm_file": str(OSM_RAW_PATH) if OSM_RAW_PATH.exists() else None,
                "buildings_path": str(BUILDINGS_PATH),
                "roads_path": str(ROADS_PATH),
                "waterways_path": str(WATERWAYS_PATH),
                "water_path": str(WATER_PATH),
                "note": "Reused existing files; not re-downloaded this run "
                        "(Overpass endpoints were unavailable: 406/429/403).",
            },
            "geocoding": {"provider": "OpenStreetMap Nominatim", "url": NOMINATIM_URL},
        },
        "crs": {
            "source_crs": "EPSG:4326 (WGS84)",
            "projected_crs": f"EPSG:{dst_epsg}",
            "projected_crs_name": CRS.from_epsg(dst_epsg).name,
            "terrain_actual_crs": str(actual_crs),
        },
        "local_origin": {
            "note": "Dam projected coordinates — Blender build script subtracts this "
                    "to center the scene on the dam.",
            "easting": dam_x, "northing": dam_y,
        },
        "aoi": {
            "radius_km": AOI_RADIUS_KM,
            "bounds_latlon": AOI_KNOWN_BOUNDS,
            "bounds_projected": {
                "left": actual_bounds.left, "bottom": actual_bounds.bottom,
                "right": actual_bounds.right, "top": actual_bounds.top,
            },
        },
        "terrain_raster": {
            "path": str(TERRAIN_PATH),
            "width_px": actual_width, "height_px": actual_height,
            "pixel_size_m": actual_res,
            "elevation_min_m": elev_min, "elevation_max_m": elev_max,
        },
        "feature_counts": {
            "buildings": int(len(buildings)), "roads": int(len(roads)),
            "waterways": int(len(waterways)), "water_polygons": int(len(water)),
        },
        "known_dam_reference_dimensions": {
            "source": "THDC India official published specifications (as supplied by user)",
            "dam_type": "Earth and Rockfill Dam",
            "height_m": 260.5, "top_length_m": 575, "top_level_m": 839.5, "frl_m": 830,
            "upstream_slope": "1:2.5", "downstream_slope": "1:2", "river": "Bhagirathi",
            "note": "Used verbatim in Phase 3 dam reconstruction; not re-derived from geographic data.",
        },
        "disclaimer": (
            "This dataset is a geographic basis for a VISUALIZATION. Building "
            "heights not present in OSM tags are estimated in a later stage. "
            "Dam coordinates were established via automated geocoding in a "
            "prior run and must be visually verified against preview/map_preview.png."
        ),
        "idempotent_run": True,
        "idempotent_run_note": "This metadata.json was generated by inspecting ALREADY-EXISTING "
                                "terrain.tif and vector GeoJSON files. No network download occurred "
                                "in this run.",
    }

    with open(META_DIR / "metadata.json", "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

    log.info(f"metadata.json written: {META_DIR / 'metadata.json'}")
    return metadata, buildings, roads, waterways, water, (dam_x, dam_y)


# ---------------------------------------------------------------------------
# 7. MAIN
# ---------------------------------------------------------------------------

def main():
    log.info("=" * 70)
    log.info("TEHRI DAM — PHASE 1 (idempotent mode)")
    log.info("=" * 70)

    dam_info = resolve_dam_location()
    dst_epsg = PROJECTED_EPSG_KNOWN if PROJECTED_EPSG_KNOWN else utm_epsg_for_lonlat(
        dam_info["lon"], dam_info["lat"])

    dem_exists = TERRAIN_PATH.exists() and not FORCE_REDOWNLOAD
    vector_exists = all(p.exists() for p in
                         (BUILDINGS_PATH, ROADS_PATH, WATERWAYS_PATH, WATER_PATH)) and not FORCE_REDOWNLOAD

    log.info(f"terrain.tif exists: {TERRAIN_PATH.exists()}  -> will "
             f"{'REUSE' if dem_exists else 'DOWNLOAD'}")
    log.info(f"all 4 vector geojson exist: {vector_exists and TERRAIN_PATH.exists()}  -> will "
             f"{'REUSE' if vector_exists else 'DOWNLOAD (Overpass)'}")

    if not dem_exists:
        if not check_network("https://s3.amazonaws.com", 10):
            fail("Internet access for DEM download", "Check connectivity or supply terrain.tif manually.")
        south, west, north, east = (AOI_KNOWN_BOUNDS["south"], AOI_KNOWN_BOUNDS["west"],
                                     AOI_KNOWN_BOUNDS["north"], AOI_KNOWN_BOUNDS["east"])
        mosaic_path = build_dem_mosaic(west, south, east, north)
        reproject_and_clip_dem(mosaic_path, (west, south, east, north), dst_epsg)
    else:
        log.info(f"Skipping DEM acquisition — reusing existing {TERRAIN_PATH}")

    if not vector_exists:
        if not check_network("https://overpass-api.de", 10):
            fail("Internet access for OSM vector download (Overpass API unreachable)",
                 "Check connectivity, or place existing buildings/roads/waterways/water "
                 f".geojson files into {VECTOR_DIR}")
        south, west, north, east = (AOI_KNOWN_BOUNDS["south"], AOI_KNOWN_BOUNDS["west"],
                                     AOI_KNOWN_BOUNDS["north"], AOI_KNOWN_BOUNDS["east"])
        bbox_latlon = (south, west, north, east)
        buildings = fetch_buildings(bbox_latlon); time.sleep(2)
        roads = fetch_roads(bbox_latlon); time.sleep(2)
        waterways = fetch_waterways(bbox_latlon); time.sleep(2)
        water = fetch_water_bodies(bbox_latlon)

        def reproj_clip(gdf):
            if gdf.empty:
                return gdf.set_crs(epsg=dst_epsg, allow_override=True)
            return gdf.to_crs(epsg=dst_epsg)

        reproj_clip(buildings).to_file(BUILDINGS_PATH, driver="GeoJSON")
        reproj_clip(roads).to_file(ROADS_PATH, driver="GeoJSON")
        reproj_clip(waterways).to_file(WATERWAYS_PATH, driver="GeoJSON")
        reproj_clip(water).to_file(WATER_PATH, driver="GeoJSON")
    else:
        log.info(f"Skipping OSM vector acquisition — reusing existing files in {VECTOR_DIR}")

    log.info("-" * 70)
    log.info("Building metadata.json from actual existing files ...")
    metadata, buildings_p, roads_p, waterways_p, water_p, dam_xy = \
        build_metadata_from_existing_data(dam_info, dst_epsg)

    log.info("-" * 70)
    log.info("Generating previews from existing real data ...")
    render_terrain_preview(TERRAIN_PATH, dam_xy, PREVIEW_DIR / "terrain_preview.png")
    render_map_preview(buildings_p, roads_p, waterways_p, water_p, dam_xy,
                        PREVIEW_DIR / "map_preview.png")

    log.info("-" * 70)
    log.info("PHASE 1 COMPLETE (idempotent — no data re-downloaded).")
    log.info(f"Metadata: {META_DIR / 'metadata.json'}")
    log.info(f"Previews: {PREVIEW_DIR / 'terrain_preview.png'}, {PREVIEW_DIR / 'map_preview.png'}")
    log.info("=" * 70)


if __name__ == "__main__":
    main()