"""
tehri_geo_to_blender_stage.py

Converts the ALREADY-DOWNLOADED Tehri geographic data
(tehri_data/terrain/terrain.tif, tehri_data/vector/*.geojson) into a
plain JSON + raw-binary format that Blender's bundled Python (which has
NO rasterio/geopandas/pyogrio) can read using only its standard library.

This performs NO network access and downloads NOTHING. It only reads
files that already exist under tehri_data/.

It INSPECTS actual CRS/columns/schema at runtime and prints what it
finds -- it does not assume property names. Fallback/estimation logic
(e.g. building height when no OSM height tag exists) is applied only
when the real data lacks the field, and is recorded per-feature via a
"*_source" field so nothing fabricated is silently indistinguishable
from real data.

Run with the SAME Python environment used for prepare_tehri_data.py:
    python tehri_geo_to_blender_stage.py
"""

import os
import re
import json
import math
import datetime as dt
from pathlib import Path

import numpy as np
import rasterio
import geopandas as gpd
from shapely.geometry import mapping
from pyproj import CRS

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------

DATA_ROOT = Path("tehri_data")
TERRAIN_PATH = DATA_ROOT / "terrain" / "terrain.tif"
VECTOR_DIR = DATA_ROOT / "vector"
META_PATH = DATA_ROOT / "metadata" / "metadata.json"

OUT_DIR = DATA_ROOT / "blender_ready"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Terrain mesh resolution cap (visualization performance, NOT a claim about
# native DEM resolution -- native resolution is recorded in metadata).
TERRAIN_MAX_GRID = 400

# Building processing limits (visualization performance cutoff, NOT a claim
# that unlisted buildings don't exist -- both counts are logged/stored).
BUILDING_DETAIL_RADIUS_M = 8000.0
BUILDING_MAX_COUNT = 4000

ROAD_MAX_COUNT = 3000
WATERWAY_MAX_COUNT = 1500

# Height estimation fallback (documented assumption, used ONLY when OSM has
# no height/levels tag for a given building).
METERS_PER_LEVEL = 3.0
CATEGORY_HEIGHT_M = {
    "residential": 7.0,
    "commercial": 10.0,
    "industrial": 9.0,
    "public": 12.0,
}
AREA_HEIGHT_TIERS = [  # (max_area_m2, height_m)
    (60.0, 6.0),
    (150.0, 8.0),
    (400.0, 11.0),
    (float("inf"), 15.0),
]

RESIDENTIAL_TAGS = {"house", "residential", "apartments", "detached", "terrace",
                    "semidetached_house", "bungalow", "dormitory", "hut", "cabin"}
COMMERCIAL_TAGS = {"commercial", "retail", "office", "supermarket", "shop", "kiosk"}
INDUSTRIAL_TAGS = {"industrial", "warehouse", "manufacture", "factory"}
PUBLIC_TAGS = {"school", "hospital", "government", "civic", "church", "religious",
               "university", "college", "public"}

ROAD_WIDTH_BY_CLASS = {
    "motorway": 12.0, "trunk": 10.0, "primary": 8.0, "secondary": 7.0,
    "tertiary": 6.0, "residential": 5.0, "unclassified": 5.0,
    "service": 3.5, "track": 3.0, "path": 1.5, "footway": 1.5,
}
DEFAULT_ROAD_WIDTH = 5.0

WATERWAY_WIDTH_BY_CLASS = {"river": 12.0, "canal": 8.0, "stream": 4.0, "drain": 2.0, "ditch": 1.5}
DEFAULT_WATERWAY_WIDTH = 4.0


def log(msg):
    print(f"[stage] {msg}")


def fail(what_missing, how_to_fix):
    print("=" * 70)
    print("MISSING DATA:")
    print(f"    {what_missing}")
    print()
    print("HOW TO FIX:")
    for line in how_to_fix.strip().splitlines():
        print(f"    {line}")
    print("=" * 70)
    raise SystemExit(1)


# ---------------------------------------------------------------------------
# 1. LOAD PHASE-1 METADATA (dam location, CRS, reference dam dimensions)
# ---------------------------------------------------------------------------

def load_phase1_metadata():
    if not META_PATH.exists():
        fail(f"{META_PATH}", "Run prepare_tehri_data.py first.")
    with open(META_PATH, "r", encoding="utf-8") as f:
        meta = json.load(f)
    return meta


meta = load_phase1_metadata()
dam_lat = meta["dam_location"]["lat"]
dam_lon = meta["dam_location"]["lon"]
dam_easting = meta["local_origin"]["easting"]
dam_northing = meta["local_origin"]["northing"]
projected_crs_str = meta["crs"]["projected_crs"]  # e.g. "EPSG:32644"
projected_epsg = int(projected_crs_str.split(":")[1])
dam_ref = meta.get("known_dam_reference_dimensions", {})

log(f"Dam location: {dam_lat:.6f}, {dam_lon:.6f} (source: {meta['dam_location']['source']})")
log(f"Projected CRS: {projected_crs_str}")
log(f"Local origin (dam projected coords): E={dam_easting:.2f}, N={dam_northing:.2f}")


def to_local(x, y):
    return (x - dam_easting, y - dam_northing)


# ---------------------------------------------------------------------------
# 2. TERRAIN — INSPECT, VALIDATE, CONVERT
# ---------------------------------------------------------------------------

def process_terrain():
    if not TERRAIN_PATH.exists():
        fail(f"{TERRAIN_PATH}", "Run prepare_tehri_data.py first.")

    with rasterio.open(TERRAIN_PATH) as src:
        log("---- TERRAIN INSPECTION (actual file, not assumed) ----")
        log(f"  Driver: {src.driver}")
        log(f"  CRS: {src.crs}")
        log(f"  Dimensions: {src.width} x {src.height}")
        log(f"  Dtype: {src.dtypes[0]}")
        log(f"  Transform: {src.transform}")
        log(f"  Nodata: {src.nodata}")
        log(f"  Bounds: {src.bounds}")

        if src.crs is None or src.crs.to_epsg() != projected_epsg:
            log(f"  WARNING: terrain CRS EPSG={src.crs.to_epsg() if src.crs else None} "
                f"differs from expected EPSG:{projected_epsg}. Reprojection was expected "
                f"to have occurred in prepare_tehri_data.py. Proceeding using terrain's "
                f"OWN transform for coordinate conversion (still geometrically correct "
                f"for this file), but verify this is intentional.")

        transform = src.transform
        if abs(transform.b) > 1e-9 or abs(transform.d) > 1e-9:
            fail(
                "terrain.tif has a rotated/sheared affine transform "
                f"(b={transform.b}, d={transform.d})",
                """
                This script assumes a north-up, non-rotated raster (the normal case
                for SRTM/most DEM downloads). A rotated raster requires per-vertex
                coordinate transform support that this stage script does not
                implement. Re-generate terrain.tif without rotation, or request
                the per-vertex transform variant of this script.
                """,
            )

        arr = src.read(1).astype(np.float64)
        nodata = src.nodata

        nodata_mask = (arr == nodata) if nodata is not None else np.zeros_like(arr, dtype=bool)
        void_count = int(nodata_mask.sum())
        if void_count > 0:
            log(f"  WARNING: {void_count} nodata/void pixels found in DEM.")
            try:
                from scipy.ndimage import distance_transform_edt
                idx = distance_transform_edt(nodata_mask, return_distances=False, return_indices=True)
                arr = arr[tuple(idx)]
                fill_method = "scipy_nearest_neighbor_fill"
                log("  Voids filled via nearest-neighbor (scipy). Marked as 'interpolated', not measured.")
            except ImportError:
                valid_mean = float(arr[~nodata_mask].mean()) if (~nodata_mask).any() else 0.0
                arr[nodata_mask] = valid_mean
                fill_method = "coarse_global_mean_fill_scipy_unavailable"
                log("  scipy not installed -- voids filled with GLOBAL VALID MEAN as a "
                    "coarse fallback. This is a documented approximation, not measured "
                    "elevation. Install scipy for a better nearest-neighbor fill if needed.")
        else:
            fill_method = "none_needed"

        pixel_w = abs(transform.a)
        pixel_h = abs(transform.e)

        h, w = arr.shape
        step_h = max(1, math.ceil(h / TERRAIN_MAX_GRID))
        step_w = max(1, math.ceil(w / TERRAIN_MAX_GRID))
        arr_ds = arr[::step_h, ::step_w]
        ds_h, ds_w = arr_ds.shape
        log(f"  Downsampled terrain grid: {ds_w} x {ds_h} (step_w={step_w}, step_h={step_h}) "
            f"for Blender mesh performance. Native resolution recorded in metadata.")

        # Precompute per-row / per-column LOCAL coordinates (north-up raster;
        # rotation already ruled out above).
        col_indices = np.arange(ds_w) * step_w
        row_indices = np.arange(ds_h) * step_h

        xs_world = transform.c + (col_indices + 0.5) * transform.a
        ys_world = transform.f + (row_indices + 0.5) * transform.e

        xs_local = (xs_world - dam_easting).tolist()
        ys_local = (ys_world - dam_northing).tolist()

        # Dam base elevation: bilinear-sample the FULL-RES (pre-downsample) array
        # at the dam's exact projected location.
        inv_transform = ~transform
        col_f, row_f = inv_transform * (dam_easting, dam_northing)
        col_f -= 0.5
        row_f -= 0.5
        c0, r0 = int(math.floor(col_f)), int(math.floor(row_f))
        c1, r1 = min(c0 + 1, w - 1), min(r0 + 1, h - 1)
        c0, r0 = max(c0, 0), max(r0, 0)
        fx, fy = col_f - c0, row_f - r0
        try:
            z00, z10 = arr[r0, c0], arr[r0, c1]
            z01, z11 = arr[r1, c0], arr[r1, c1]
            dam_base_elevation = float(
                z00 * (1 - fx) * (1 - fy) + z10 * fx * (1 - fy) +
                z01 * (1 - fx) * fy + z11 * fx * fy
            )
        except IndexError:
            fail(
                "Dam projected location falls outside terrain.tif raster extent",
                "The AOI radius in prepare_tehri_data.py may be too small, or the "
                "geocoded dam point is wrong. Re-check preview/verification_preview.png.",
            )

        log(f"  Dam base elevation (bilinear sampled, absolute m): {dam_base_elevation:.2f}")

        min_elev = float(arr.min())
        max_elev = float(arr.max())

        arr_ds.astype(np.float32).tofile(OUT_DIR / "terrain_heightmap.f32")

        terrain_meta = {
            "width": ds_w, "height": ds_h,
            "x_coords_local_m": xs_local,
            "y_coords_local_m": ys_local,
            "min_elevation_m": min_elev, "max_elevation_m": max_elev,
            "dam_base_elevation_m": dam_base_elevation,
            "native_pixel_size_m": [pixel_w, pixel_h],
            "downsample_step": [step_w, step_h],
            "nodata_fill_method": fill_method,
            "nodata_void_pixel_count": void_count,
            "source_crs": str(src.crs),
        }
        with open(OUT_DIR / "terrain_meta.json", "w", encoding="utf-8") as f:
            json.dump(terrain_meta, f, indent=2)

        log(f"  Written: {OUT_DIR / 'terrain_heightmap.f32'} and terrain_meta.json")
        return terrain_meta


terrain_meta = process_terrain()


# ---------------------------------------------------------------------------
# 3. VECTOR LAYERS — INSPECT SCHEMA, THEN CONVERT
# ---------------------------------------------------------------------------

def load_and_normalize_crs(path, layer_name):
    if not path.exists():
        fail(f"{path}", "Run prepare_tehri_data.py first.")
    gdf = gpd.read_file(path)
    log(f"---- {layer_name.upper()} INSPECTION ----")
    log(f"  Features: {len(gdf)}")
    log(f"  Columns: {list(gdf.columns)}")
    log(f"  CRS: {gdf.crs}")
    if len(gdf) > 0:
        current_epsg = gdf.crs.to_epsg() if gdf.crs else None
        if current_epsg != projected_epsg:
            log(f"  Reprojecting from EPSG:{current_epsg} to EPSG:{projected_epsg}")
            gdf = gdf.to_crs(epsg=projected_epsg)
    return gdf


def numeric_from_tag(value):
    if value is None:
        return None
    if isinstance(value, (int, float)) and not (isinstance(value, float) and math.isnan(value)):
        return float(value)
    if isinstance(value, str):
        m = re.search(r"[-+]?\d*\.?\d+", value)
        if m:
            try:
                return float(m.group())
            except ValueError:
                return None
    return None


def get_first_present(row, columns, candidates):
    for c in candidates:
        if c in columns:
            v = row.get(c)
            if v is not None and not (isinstance(v, float) and math.isnan(v)):
                return v
    return None


def classify_building_category(building_tag):
    if not isinstance(building_tag, str):
        return "unknown"
    b = building_tag.lower()
    if b in RESIDENTIAL_TAGS:
        return "residential"
    if b in COMMERCIAL_TAGS:
        return "commercial"
    if b in INDUSTRIAL_TAGS:
        return "industrial"
    if b in PUBLIC_TAGS:
        return "public"
    return "unknown"


def estimate_height_by_area(area_m2):
    for max_area, h in AREA_HEIGHT_TIERS:
        if area_m2 <= max_area:
            return h
    return AREA_HEIGHT_TIERS[-1][1]


def process_buildings():
    gdf = load_and_normalize_crs(VECTOR_DIR / "buildings.geojson", "buildings")
    columns = set(gdf.columns)

    candidate_height_cols = [c for c in ["height", "building:height"] if c in columns]
    candidate_level_cols = [c for c in ["building:levels", "levels"] if c in columns]
    log(f"  Height-related columns found: {candidate_height_cols or 'NONE'}")
    log(f"  Level-related columns found: {candidate_level_cols or 'NONE'}")

    total = len(gdf)
    if total == 0:
        log("  No buildings found in AOI.")
        return {"features": [], "total_available": 0, "included": 0}

    gdf["__local_x"] = gdf.geometry.centroid.x - dam_easting
    gdf["__local_y"] = gdf.geometry.centroid.y - dam_northing
    gdf["__dist"] = np.sqrt(gdf["__local_x"] ** 2 + gdf["__local_y"] ** 2)

    within_radius = gdf[gdf["__dist"] <= BUILDING_DETAIL_RADIUS_M].copy()
    within_radius = within_radius.sort_values("__dist").head(BUILDING_MAX_COUNT)

    log(f"  Total buildings in AOI: {total}")
    log(f"  Included after radius/count cutoff ({BUILDING_DETAIL_RADIUS_M}m, "
        f"max {BUILDING_MAX_COUNT}): {len(within_radius)}")

    features = []
    height_source_counts = {}

    for _, row in within_radius.iterrows():
        geom = row.geometry
        if geom is None or geom.is_empty:
            continue
        polys = list(geom.geoms) if geom.geom_type == "MultiPolygon" else [geom]
        poly = max(polys, key=lambda p: p.area)  # largest part if multipolygon

        try:
            poly_simplified = poly.simplify(0.5, preserve_topology=True)
            if poly_simplified.is_empty or poly_simplified.geom_type != "Polygon":
                poly_simplified = poly
        except Exception:
            poly_simplified = poly

        exterior_local = [to_local(x, y) for x, y in poly_simplified.exterior.coords]
        interior_rings_local = [
            [to_local(x, y) for x, y in ring.coords] for ring in poly_simplified.interiors
        ]

        height_val = None
        height_source = None
        for c in candidate_height_cols:
            height_val = numeric_from_tag(row.get(c))
            if height_val is not None:
                height_source = f"osm_tag:{c}"
                break
        if height_val is None:
            for c in candidate_level_cols:
                lv = numeric_from_tag(row.get(c))
                if lv is not None:
                    height_val = lv * METERS_PER_LEVEL
                    height_source = f"osm_tag:{c}*{METERS_PER_LEVEL}m_per_level"
                    break

        category = classify_building_category(row.get("building"))
        if height_val is None:
            if category in CATEGORY_HEIGHT_M:
                height_val = CATEGORY_HEIGHT_M[category]
                height_source = f"estimated_by_category:{category}"
            else:
                area = poly.area
                height_val = estimate_height_by_area(area)
                height_source = f"estimated_by_footprint_area:{area:.0f}m2"

        height_source_counts[height_source] = height_source_counts.get(height_source, 0) + 1

        features.append({
            "osm_id": row.get("osm_id"),
            "exterior_local": exterior_local,
            "interior_rings_local": interior_rings_local,
            "height_m": round(float(height_val), 2),
            "height_source": height_source,
            "category": category,
            "footprint_area_m2": round(float(poly.area), 1),
        })

    log(f"  Height source breakdown: {height_source_counts}")
    return {"features": features, "total_available": int(total), "included": len(features)}


def process_roads():
    gdf = load_and_normalize_crs(VECTOR_DIR / "roads.geojson", "roads")
    total = len(gdf)
    if total == 0:
        return {"features": [], "total_available": 0, "included": 0}

    if len(gdf) > ROAD_MAX_COUNT:
        log(f"  WARNING: {len(gdf)} roads exceeds cap {ROAD_MAX_COUNT}; truncating "
            f"(kept in file order, not distance-sorted).")
        gdf = gdf.iloc[:ROAD_MAX_COUNT]

    features = []
    class_counts = {}
    for _, row in gdf.iterrows():
        geom = row.geometry
        if geom is None or geom.is_empty or geom.geom_type != "LineString":
            continue
        highway_class = row.get("highway") if "highway" in gdf.columns else None
        width = ROAD_WIDTH_BY_CLASS.get(highway_class, DEFAULT_ROAD_WIDTH)
        class_counts[highway_class] = class_counts.get(highway_class, 0) + 1
        coords_local = [to_local(x, y) for x, y in geom.coords]
        features.append({
            "osm_id": row.get("osm_id"), "highway_class": highway_class,
            "width_m": width, "coords_local": coords_local,
        })

    log(f"  Road class breakdown: {class_counts}")
    return {"features": features, "total_available": int(total), "included": len(features)}


def process_waterways():
    gdf = load_and_normalize_crs(VECTOR_DIR / "waterways.geojson", "waterways")
    total = len(gdf)
    if total == 0:
        return {"features": [], "total_available": 0, "included": 0}

    if len(gdf) > WATERWAY_MAX_COUNT:
        gdf = gdf.iloc[:WATERWAY_MAX_COUNT]

    features = []
    for _, row in gdf.iterrows():
        geom = row.geometry
        if geom is None or geom.is_empty or geom.geom_type != "LineString":
            continue
        wtype = row.get("waterway") if "waterway" in gdf.columns else None
        width = WATERWAY_WIDTH_BY_CLASS.get(wtype, DEFAULT_WATERWAY_WIDTH)
        coords_local = [to_local(x, y) for x, y in geom.coords]
        features.append({
            "osm_id": row.get("osm_id"), "waterway_type": wtype,
            "width_m": width, "coords_local": coords_local,
        })

    return {"features": features, "total_available": int(total), "included": len(features)}


def process_water():
    gdf = load_and_normalize_crs(VECTOR_DIR / "water.geojson", "water")
    total = len(gdf)
    if total == 0:
        log("  WARNING: No water polygons found -- reservoir cannot be built from real geometry.")
        return {"features": [], "total_available": 0, "included": 0, "reservoir_index": None}

    gdf["__local_x"] = gdf.geometry.centroid.x - dam_easting
    gdf["__local_y"] = gdf.geometry.centroid.y - dam_northing
    gdf["__dist"] = np.sqrt(gdf["__local_x"] ** 2 + gdf["__local_y"] ** 2)
    gdf["__area"] = gdf.geometry.area

    nearby = gdf[gdf["__dist"] <= 6000.0]
    reservoir_row_idx = None
    if not nearby.empty:
        reservoir_row_idx = nearby["__area"].idxmax()
        log(f"  Reservoir candidate: OSM id {gdf.loc[reservoir_row_idx].get('osm_id')}, "
            f"area={gdf.loc[reservoir_row_idx]['__area']:.0f} m^2, "
            f"dist_to_dam={gdf.loc[reservoir_row_idx]['__dist']:.0f} m")
    else:
        log("  WARNING: No water polygon found within 6000m of dam -- reservoir flag not set.")

    features = []
    for idx, row in gdf.iterrows():
        geom = row.geometry
        if geom is None or geom.is_empty:
            continue
        polys = list(geom.geoms) if geom.geom_type == "MultiPolygon" else [geom]
        for poly in polys:
            exterior_local = [to_local(x, y) for x, y in poly.exterior.coords]
            features.append({
                "osm_id": row.get("osm_id"),
                "exterior_local": exterior_local,
                "is_reservoir": bool(idx == reservoir_row_idx),
                "area_m2": round(float(poly.area), 1),
            })

    return {"features": features, "total_available": int(total), "included": len(features),
            "reservoir_found": reservoir_row_idx is not None}


buildings_out = process_buildings()
roads_out = process_roads()
waterways_out = process_waterways()
water_out = process_water()

with open(OUT_DIR / "buildings.json", "w", encoding="utf-8") as f:
    json.dump(buildings_out, f)
with open(OUT_DIR / "roads.json", "w", encoding="utf-8") as f:
    json.dump(roads_out, f)
with open(OUT_DIR / "waterways.json", "w", encoding="utf-8") as f:
    json.dump(waterways_out, f)
with open(OUT_DIR / "water.json", "w", encoding="utf-8") as f:
    json.dump(water_out, f)


# ---------------------------------------------------------------------------
# 4. DAM AXIS ORIENTATION — DERIVED FROM REAL WATERWAY GEOMETRY
# ---------------------------------------------------------------------------

def derive_dam_axis():
    method = None
    angle_deg = 0.0

    best_dist = float("inf")
    best_tangent = None
    for feat in waterways_out["features"]:
        coords = feat["coords_local"]
        for i in range(len(coords) - 1):
            (x0, y0), (x1, y1) = coords[i], coords[i + 1]
            mx, my = (x0 + x1) / 2.0, (y0 + y1) / 2.0
            d = math.hypot(mx, my)
            if d < best_dist:
                best_dist = d
                best_tangent = (x1 - x0, y1 - y0)

    if best_tangent is not None and best_dist < 3000.0:
        tx, ty = best_tangent
        tangent_angle = math.degrees(math.atan2(ty, tx))
        angle_deg = tangent_angle + 90.0  # dam axis perpendicular to river tangent
        method = f"derived_from_nearest_waterway_segment(dist={best_dist:.0f}m)"
    else:
        reservoir_feat = next((f for f in water_out["features"] if f.get("is_reservoir")), None)
        if reservoir_feat:
            xs = [p[0] for p in reservoir_feat["exterior_local"]]
            ys = [p[1] for p in reservoir_feat["exterior_local"]]
            cx, cy = sum(xs) / len(xs), sum(ys) / len(ys)
            upstream_angle = math.degrees(math.atan2(cy, cx))
            angle_deg = upstream_angle + 90.0
            method = "derived_from_reservoir_centroid_fallback"
        else:
            angle_deg = 0.0
            method = "DEFAULT_NORTH_SOUTH_NO_GEOMETRY_AVAILABLE"
            log("  WARNING: could not derive dam axis from waterway or reservoir geometry. "
                "Defaulting to North-South. Verify orientation manually in Blender.")

    log(f"  Dam axis angle: {angle_deg:.2f} deg (method: {method})")
    return angle_deg, method


dam_axis_angle_deg, dam_axis_method = derive_dam_axis()

dam_placement = {
    "origin_note": "Dam is placed at local (0,0). All other layers are already local-meter "
                   "coordinates relative to this same origin.",
    "dam_base_elevation_m": terrain_meta["dam_base_elevation_m"],
    "dam_axis_angle_deg": dam_axis_angle_deg,
    "dam_axis_method": dam_axis_method,
    "reference_dimensions": dam_ref,
}
with open(OUT_DIR / "dam_placement.json", "w", encoding="utf-8") as f:
    json.dump(dam_placement, f, indent=2)


# ---------------------------------------------------------------------------
# 5. CONSOLIDATED SCENE METADATA (for Blender custom properties)
# ---------------------------------------------------------------------------

scene_metadata = {
    "dam_name": meta.get("dam_name", "TEHRI"),
    "generation_date_utc": dt.datetime.utcnow().isoformat() + "Z",
    "dam_lat": dam_lat, "dam_lon": dam_lon,
    "dam_location_source": meta["dam_location"]["source"],
    "source_crs": "EPSG:4326",
    "projected_crs": projected_crs_str,
    "dem_source": meta["sources"]["dem"],
    "osm_source": meta["sources"]["vector"],
    "coordinate_transformation": (
        f"WGS84 lon/lat -> {projected_crs_str} (pyproj) -> local meters via "
        f"subtraction of dam projected origin (E={dam_easting:.3f}, N={dam_northing:.3f})"
    ),
    "terrain_native_pixel_size_m": terrain_meta["native_pixel_size_m"],
    "terrain_mesh_resolution": [terrain_meta["width"], terrain_meta["height"]],
    "terrain_nodata_fill_method": terrain_meta["nodata_fill_method"],
    "buildings_total_in_aoi": buildings_out["total_available"],
    "buildings_included_in_scene": buildings_out["included"],
    "roads_total_in_aoi": roads_out["total_available"],
    "roads_included_in_scene": roads_out["included"],
    "waterways_total_in_aoi": waterways_out["total_available"],
    "water_polygons_total_in_aoi": water_out["total_available"],
    "reservoir_identified_from_real_geometry": water_out.get("reservoir_found", False),
    "dam_axis_derivation_method": dam_axis_method,
    "known_dam_reference_dimensions": dam_ref,
    "disclaimer": (
        "Visualization based on real OSM/DEM geographic data and reconstructed dam "
        "geometry using THDC-published reference dimensions. Building heights not "
        "present in OSM are estimated (see per-building height_source field). This "
        "is NOT a validated hydraulic or engineering-survey reconstruction."
    ),
}
with open(OUT_DIR / "scene_metadata.json", "w", encoding="utf-8") as f:
    json.dump(scene_metadata, f, indent=2)

log("=" * 70)
log(f"STAGE COMPLETE. Output written to: {OUT_DIR.resolve()}")
log("Files: terrain_heightmap.f32, terrain_meta.json, buildings.json, roads.json, "
    "waterways.json, water.json, dam_placement.json, scene_metadata.json")
log("=" * 70)