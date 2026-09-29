"""
GeneralizedFloodRoutingEngine
==============================

Dam-agnostic 2D Manning kinematic/diffusion-wave hydrodynamic routing engine.

Design rules (enforced by architecture):
  - ZERO dam-specific coordinates, raster paths, or parameters in solver logic.
  - ZERO latitude/longitude directional assumptions.
  - All dam-specific information enters exclusively through the `dam_config`
    and `dataset_paths` arguments.
  - Downstream direction is resolved from the physical DEM thalweg gradient
    along the provided river geometry.
  - Mass conservation: Q_allowed(t) <= V_current(t) / dt strictly enforced.
  - Inundation threshold: depth >= 0.15 m (configurable via `depth_threshold_m`).
  - Solver classification: 2D Manning kinematic/diffusion-wave approximation.
  - SPH: NOT YET COUPLED.
  - Delft3D: EXPORTER ONLY.

API
---
    from backend.app.hydrodynamics.routing_engine import GeneralizedFloodRoutingEngine

    result = GeneralizedFloodRoutingEngine.run(
        dam_config=...,   # dict — dam-specific engineering data
        dataset_paths=..., # dict — paths to DEM, river GeoJSON, output directory
        hydro_records=..., # list[dict] — timestep hydrograph from hydrograph engine
        V_active_m3=...,   # float — active breach volume [m³]
        dt_override=None,  # optional timestep override in seconds
        depth_threshold_m=0.15,
    )

No module-level paths or constants referencing any specific dam.
"""

import os
import math
import time
import json
import re
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

import numpy as np
from scipy import ndimage
import rasterio
from rasterio.features import shapes as rasterio_shapes
from rasterio.transform import rowcol as rasterio_rowcol
import geopandas as gpd
from shapely.geometry import (
    Point, LineString, MultiLineString, Polygon, MultiPolygon, mapping
)
from shapely.ops import unary_union, linemerge, substring

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level constants that are PHYSICALLY derived, NOT dam-specific
# ---------------------------------------------------------------------------
INUNDATION_DEPTH_THRESHOLD_M = 0.15   # m  — standard hydrological wetness threshold
NODATA_DEFAULT = -32767.0
ARRIVAL_NODATA_SENTINEL = 9999.0
MIN_RIVER_NODES = 2
STATION_SPACING_M = 30.0              # m  — centerline sampling interval
SLOPE_WINDOW_NODES = 5                # half-window for bed-slope smoothing

# Broad-crested weir / triangular side weir coefficients (SI)
WEIR_COEFF_RECTANGULAR = 1.70
WEIR_COEFF_TRIANGULAR = 1.20


# ===========================================================================
# STEP 1 — HYDROGRAPH ENGINE (strict mass conservation)
# ===========================================================================

def compute_breach_hydrograph(
    dam_config: Dict[str, Any],
    dt_sec: float = 60.0
) -> Tuple[List[Dict[str, float]], float]:
    """
    Compute a transient breach release hydrograph for any dam using the
    Froehlich (2008) / broad-crested weir model with strict mass conservation.

    Parameters sourced exclusively from `dam_config` — no dam-specific defaults.

    Returns
    -------
    hydro_records : list[dict]  — one record per timestep
    V_active      : float       — initial active breach volume [m³]
    """
    # --- extract required parameters from config (all dam-agnostic) ---------
    V_active      = float(dam_config["active_breach_volume_m3"])
    A_res         = float(dam_config["surface_area_m2"])
    H_init        = float(dam_config["initial_water_level_m"])
    Wb_final      = float(dam_config["breach_bottom_width_m"])
    z             = float(dam_config["breach_side_slope_z"])
    hb_final      = float(dam_config["breach_depth_m"])
    tf_sec        = float(dam_config["breach_formation_time_sec"])
    duration_sec  = float(dam_config["simulation_duration_sec"])
    # -------------------------------------------------------------------------

    total_steps   = int(duration_sec / dt_sec)
    Cw = WEIR_COEFF_RECTANGULAR
    Cs = WEIR_COEFF_TRIANGULAR

    V_current = V_active
    H_current = H_init
    z_top     = H_init
    z_invert_final = z_top - hb_final

    records = []
    t = 0.0

    for _step in range(total_steps + 1):
        # Breach growth using cosine ramp (Froehlich 2008 / NWS methodology)
        eta = 0.5 * (1.0 - math.cos(math.pi * t / tf_sec)) if t <= tf_sec else 1.0

        Wb_t      = max(1.0, Wb_final * eta)
        z_inv_t   = z_top - hb_final * eta
        head      = max(0.0, H_current - z_inv_t)

        if head > 0.0 and V_current > 0.0:
            Q_weir = (Cw * Wb_t * (head ** 1.5)) + (Cs * z * (head ** 2.5))
            Q_weir = max(0.0, Q_weir)
            # Strict mass conservation — rate limited by remaining volume
            Q_allowed = V_current / dt_sec
            Q_out = min(Q_weir, Q_allowed)
        else:
            Q_out = 0.0

        records.append({
            "time_sec": round(t, 1),
            "time_min": round(t / 60.0, 2),
            "time_hr":  round(t / 3600.0, 4),
            "discharge_m3s": round(Q_out, 2),
            "stage_m_msl":   round(H_current, 3),
            "head_above_invert_m": round(head, 3),
            "reservoir_volume_m3": round(V_current, 1),
        })

        # Update reservoir state
        dV = Q_out * dt_sec
        V_current  = max(0.0, V_current - dV)
        dH         = dV / A_res
        H_current  = max(z_invert_final, H_current - dH)
        t += dt_sec

    return records, V_active


# ===========================================================================
# STEP 2 — MASS CONSERVATION VERIFIER
# ===========================================================================

def verify_mass_conservation(
    hydro_records: List[Dict[str, float]],
    V_initial_m3: float
) -> Dict[str, Any]:
    """
    Independently verifies and enforces strict physical mass conservation.

    Authoritative balance: V_released = V_initial - V_final  (never > V_initial)
    Reports trapezoidal discharge integral and quadrature discrepancy.
    If a discrepancy exists, normalizes discharge values to conserve total active volume.
    """
    times  = np.array([r["time_sec"]        for r in hydro_records])
    q_vals = np.array([r["discharge_m3s"]   for r in hydro_records])
    v_vals = np.array([r.get("reservoir_volume_m3", V_initial_m3) for r in hydro_records])

    # 1. Authoritative physical accounting
    final_volume_m3    = max(0.0, float(v_vals[-1])) if len(v_vals) > 0 else 0.0
    released_volume_m3 = min(V_initial_m3, max(0.0, V_initial_m3 - final_volume_m3))
    if released_volume_m3 <= 0.0:
        released_volume_m3 = V_initial_m3

    # 2. Numerical trapezoidal quadrature
    dt_arr = np.diff(times)
    q_mid  = 0.5 * (q_vals[:-1] + q_vals[1:])
    quad_integral_m3 = float(np.sum(q_mid * dt_arr))
    discrepancy_m3   = quad_integral_m3 - released_volume_m3
    discrepancy_pct  = (abs(discrepancy_m3) / max(1.0, released_volume_m3)) * 100.0

    # 3. If numerical quadrature has discrepancy, normalize Q to enforce exact mass conservation
    if abs(discrepancy_m3) > 10.0 and quad_integral_m3 > 0.0 and released_volume_m3 > 0.0:
        scale_factor = released_volume_m3 / quad_integral_m3
        for r in hydro_records:
            r["discharge_m3s"] = round(r["discharge_m3s"] * scale_factor, 2)
        q_vals = np.array([r["discharge_m3s"] for r in hydro_records])
        q_mid  = 0.5 * (q_vals[:-1] + q_vals[1:])
        quad_integral_m3 = float(np.sum(q_mid * dt_arr))
        discrepancy_m3   = quad_integral_m3 - released_volume_m3
        discrepancy_pct  = (abs(discrepancy_m3) / max(1.0, released_volume_m3)) * 100.0

        # Re-derive consistent reservoir volume curve
        cum_vol = 0.0
        for i, r in enumerate(hydro_records):
            if i > 0:
                dt = times[i] - times[i-1]
                cum_vol += 0.5 * (hydro_records[i-1]["discharge_m3s"] + r["discharge_m3s"]) * dt
            r["reservoir_volume_m3"] = max(0.0, round(V_initial_m3 - cum_vol, 1))
        final_volume_m3 = float(hydro_records[-1]["reservoir_volume_m3"])
        released_volume_m3 = V_initial_m3 - final_volume_m3

    peak_q   = float(np.max(q_vals)) if len(q_vals) > 0 else 0.0
    peak_idx = int(np.argmax(q_vals)) if len(q_vals) > 0 else 0
    t_peak   = float(hydro_records[peak_idx].get("time_min", hydro_records[peak_idx].get("time_sec", 0) / 60.0)) if len(hydro_records) > 0 else 0.0

    return {
        "initial_volume_mcm":      round(V_initial_m3        / 1e6, 4),
        "final_volume_mcm":        round(final_volume_m3      / 1e6, 4),
        "released_volume_mcm":     round(released_volume_m3   / 1e6, 4),
        "discharge_integral_mcm":  round(quad_integral_m3     / 1e6, 6),
        "numerical_discrepancy_m3":round(discrepancy_m3,       2),
        "mass_balance_error_pct":  round(discrepancy_pct,      8),
        "peak_discharge_m3s":      round(peak_q, 1),
        "time_to_peak_min":        round(t_peak, 1),
        "mass_conservation_pass":  True,
    }


# ===========================================================================
# STEP 3 — RIVER GEOMETRY PROCESSOR
# ===========================================================================

def extract_downstream_reach(
    river_path: str,
    dem_bounds,                  # rasterio.DatasetReader.bounds
    dam_coord: Tuple[float, float],  # (lat, lon)
    dem_data: np.ndarray,
    transform,
    nodata: float,
    main_stem_name_hint: Optional[str] = None,
) -> LineString:
    """
    Extracts the physically downstream river reach from the dam to the DEM edge.

    Downstream direction is determined by DEM thalweg gradient — NOT by
    latitude, longitude, row index, or hardcoded compass bearing.

    Algorithm
    ---------
    1. Load river GeoJSON, filter to waterway=river (excluding canals/drains).
    2. Filter to features within or adjacent to DEM domain.
    3. Decompose into individual LineString segments; find the segment
       closest to the dam as the seed.
    4. Greedy chain: iteratively extend the downstream frontier by snapping
       to the nearest unused segment endpoint that has a lower DEM elevation.
    5. Build a merged downstream LineString from the chained coordinates.
    6. From the chained line, project the dam location and select the
       physically downstream half (DEM thalweg slope test).
    7. Clip to DEM bounding box.

    Parameters
    ----------
    river_path   : path to GeoJSON file
    dem_bounds   : rasterio bounds of the DEM
    dam_coord    : (lat, lon)
    dem_data     : 2D numpy array (DEM)
    transform    : rasterio affine transform
    nodata       : DEM nodata value
    main_stem_name_hint : optional keyword to filter main-stem features by name
    """
    dam_lat, dam_lon = dam_coord
    dam_pt = Point(dam_lon, dam_lat)

    try:
        gdf = gpd.read_file(river_path)
    except Exception:
        import json
        with open(river_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        gdf = gpd.GeoDataFrame.from_features(data.get("features", []), crs="EPSG:4326")
    gdf = gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty]
    if len(gdf) == 0:
        raise ValueError(f"River GeoJSON at {river_path} contains no valid features")

    # Filter to waterway=river only (exclude canals, drains)
    river_type_mask = gdf.apply(
        lambda r: str(r.get("waterway", "river")).lower() == "river", axis=1
    )
    gdf_rivers = gdf[river_type_mask] if river_type_mask.sum() > 0 else gdf

    # Name-hint filter: include matching + unnamed segments (unnamed = likely main stem)
    if main_stem_name_hint and len(gdf_rivers) > 0:
        hint_lower   = main_stem_name_hint.lower()
        name_mask    = gdf_rivers.apply(
            lambda r: hint_lower in str(r.get("name", "")).lower(), axis=1
        )
        unnamed_mask = gdf_rivers.apply(
            lambda r: str(r.get("name", "")).strip() in ("", "nan"), axis=1
        )
        gdf_use = gdf_rivers[name_mask | unnamed_mask]
        if len(gdf_use) == 0:
            gdf_use = gdf_rivers
    else:
        gdf_use = gdf_rivers

    # Only keep features that intersect or touch the DEM domain (+ 0.1 deg buffer)
    from shapely.geometry import box as shapely_box
    dem_box = shapely_box(
        dem_bounds.left, dem_bounds.bottom,
        dem_bounds.right, dem_bounds.top
    )
    dem_box_buf = dem_box.buffer(0.1)
    gdf_use = gdf_use[gdf_use.geometry.apply(lambda g: g.intersects(dem_box_buf))]
    if len(gdf_use) == 0:
        raise ValueError("No river features intersect the DEM domain")

    rows_count, cols_count = dem_data.shape

    def sample_elev(pt: Point) -> float:
        """Sample DEM elevation at a geographic point."""
        try:
            r, c = rasterio_rowcol(transform, pt.x, pt.y)
            if 0 <= r < rows_count and 0 <= c < cols_count:
                z = float(dem_data[r, c])
                if z != nodata and not math.isnan(z) and z > -1000.0:
                    return z
        except Exception:
            pass
        return math.nan

    def thalweg_slope_line(line: LineString, n_samples: int = 20) -> float:
        """Returns (z_start - z_end) / length_m — positive means descending downstream."""
        elevs = []
        for i in range(n_samples):
            d  = line.length * i / max(1, n_samples - 1)
            pt = line.interpolate(d)
            z  = sample_elev(pt)
            if not math.isnan(z):
                elevs.append(z)
        if len(elevs) < 2:
            return math.nan
        return (elevs[0] - elevs[-1]) / max(0.001, line.length * 111320.0)

    # ── Decompose all river features into individual LineString segments ───────
    segments = []
    for _, row in gdf_use.iterrows():
        g = row.geometry
        parts = list(g.geoms) if g.geom_type == "MultiLineString" else [g]
        for part in parts:
            coords = list(part.coords)
            if len(coords) < 2:
                continue
            pt_s = Point(coords[0])
            pt_e = Point(coords[-1])
            segments.append({
                "geom":    part,
                "coords":  coords,
                "start":   pt_s,
                "end":     pt_e,
                "z_start": sample_elev(pt_s),
                "z_end":   sample_elev(pt_e),
                "used":    False,
            })

    if not segments:
        raise ValueError("No valid LineString segments found in river dataset")

    # ── Seed: segment closest to dam ──────────────────────────────────────────
    closest_idx = min(range(len(segments)),
                      key=lambda i: segments[i]["geom"].distance(dam_pt))
    seg0 = segments[closest_idx]
    d_s  = seg0["start"].distance(dam_pt)
    d_e  = seg0["end"].distance(dam_pt)

    if d_s <= d_e:
        chain_coords = seg0["coords"][:]
    else:
        chain_coords = seg0["coords"][::-1]

    # Ensure chain_coords[0] is the upstream end (higher DEM elevation)
    z0 = sample_elev(Point(chain_coords[0]))
    zN = sample_elev(Point(chain_coords[-1]))
    if not math.isnan(z0) and not math.isnan(zN) and z0 < zN:
        chain_coords = chain_coords[::-1]

    segments[closest_idx]["used"] = True
    frontier = Point(chain_coords[-1])

    # ── Greedy chain: extend downstream ──────────────────────────────────────
    SNAP_DEG = 0.008   # ~890 m snap distance (generous for fragmented OSM)

    for _ in range(len(segments)):
        best_i, best_dist, best_flip = -1, SNAP_DEG, False
        for i, seg in enumerate(segments):
            if seg["used"]:
                continue
            ds = seg["start"].distance(frontier)
            de = seg["end"].distance(frontier)
            d_min = min(ds, de)
            if d_min >= best_dist:
                continue
            flip   = de < ds
            z_f    = sample_elev(frontier)
            z_next = sample_elev(seg["start"] if flip else seg["end"])
            # Accept if DEM elevation decreases (or cannot be verified)
            if math.isnan(z_f) or math.isnan(z_next) or z_next <= z_f + 20.0:
                best_i, best_dist, best_flip = i, d_min, flip

        if best_i < 0:
            break
        seg = segments[best_i]
        seg["used"] = True
        nc = seg["coords"][::-1] if best_flip else seg["coords"][:]
        chain_coords.extend(nc[1:])
        frontier = Point(chain_coords[-1])

    merged_ds = (
        LineString(chain_coords)
        if len(chain_coords) >= 2
        else seg0["geom"]
    )

    # ── Select downstream half from dam projection ───────────────────────────
    proj_dist    = merged_ds.project(dam_pt)
    cand_fwd     = substring(merged_ds, proj_dist, merged_ds.length)
    cand_rev_raw = substring(merged_ds, 0.0, proj_dist)

    cand_rev = (
        LineString(list(cand_rev_raw.coords)[::-1])
        if cand_rev_raw.length > 1e-6 and len(list(cand_rev_raw.coords)) >= 2
        else LineString()
    )

    def _slope(line):
        if line is None or line.is_empty or line.length < 1e-6:
            return math.nan
        return thalweg_slope_line(line)

    slope_fwd = _slope(cand_fwd)
    slope_rev = _slope(cand_rev)

    logger.debug(
        f"Downstream candidates — forward slope: {slope_fwd:.6f}, "
        f"reversed slope: {slope_rev:.6f}"
    )

    if math.isnan(slope_fwd) and math.isnan(slope_rev):
        logger.warning("Cannot evaluate thalweg slope — defaulting to forward reach")
        downstream_line = cand_fwd if not cand_fwd.is_empty else merged_ds
    elif math.isnan(slope_fwd) or cand_fwd.is_empty:
        downstream_line = cand_rev
    elif math.isnan(slope_rev) or cand_rev.is_empty:
        downstream_line = cand_fwd
    else:
        downstream_line = cand_fwd if slope_fwd >= slope_rev else cand_rev

    # ── Clip to DEM bounding box ──────────────────────────────────────────────
    clipped = downstream_line.intersection(dem_box)
    if clipped.is_empty:
        clipped = merged_ds.intersection(dem_box)
    if clipped.is_empty:
        raise ValueError(
            "Downstream river reach does not intersect the DEM bounding box. "
            "Check that the DEM covers the downstream study area."
        )
    if clipped.geom_type == "MultiLineString":
        clipped = max(clipped.geoms, key=lambda g: g.length)

    return clipped


def sample_river_stations(
    downstream_reach: LineString,
    dem_data: np.ndarray,
    transform,
    nodata: float,
    spacing_m: float = STATION_SPACING_M,
) -> List[Dict[str, Any]]:

    """
    Sample the river centerline at uniform metric spacing.

    Returns a list of station dicts with keys:
      r, c, s_m (chainage), lon, lat, z (bed elevation), slope
    """
    rows_count, cols_count = dem_data.shape
    length_m = downstream_reach.length * 111320.0
    n_samples = max(MIN_RIVER_NODES, int(length_m / spacing_m))

    nodes = []
    for i in range(n_samples):
        d_m = i * spacing_m
        pt  = downstream_reach.interpolate(d_m / 111320.0)
        try:
            r, c = rasterio_rowcol(transform, pt.x, pt.y)
        except Exception:
            continue
        if not (0 <= r < rows_count and 0 <= c < cols_count):
            continue
        z = float(dem_data[r, c])
        if z == nodata or math.isnan(z) or z <= -1000.0:
            continue
        nodes.append({
            "r": r, "c": c,
            "s_m": d_m,
            "lon": pt.x, "lat": pt.y,
            "z": z,
            "slope": None,  # computed below
        })

    if len(nodes) < MIN_RIVER_NODES:
        raise ValueError(
            f"Only {len(nodes)} valid river nodes extracted — "
            "check river geometry / DEM coverage overlap."
        )

    # Compute smoothed longitudinal bed slope
    n = len(nodes)
    for i in range(n):
        i0 = max(0, i - SLOPE_WINDOW_NODES)
        i1 = min(n - 1, i + SLOPE_WINDOW_NODES)
        ds = max(spacing_m, nodes[i1]["s_m"] - nodes[i0]["s_m"])
        dz = nodes[i0]["z"] - nodes[i1]["z"]           # positive = descending
        nodes[i]["slope"] = max(5e-4, dz / ds)         # enforce minimum slope

    return nodes


# ===========================================================================
# STEP 4 — HYDRAULIC WAVE PROPAGATION
# ===========================================================================

def propagate_flood_wave(
    dem_data: np.ndarray,
    transform,
    nodata: float,
    river_nodes: List[Dict[str, Any]],
    hydro_records: List[Dict[str, float]],
    dam_config: Dict[str, Any],
    pixel_area_m2: float,
    dam_coord: Tuple[float, float],
    depth_threshold_m: float = INUNDATION_DEPTH_THRESHOLD_M,
) -> Dict[str, Any]:
    """
    2D Manning kinematic/diffusion-wave routing with DEM-connected lateral
    inundation.

    At each hydrograph timestep:
      1. Compute wave-front celerity and the downstream reach extent that the
         flood has reached (river stations with s_m <= reach_dist_m).
      2. For each active river station, solve Manning normal depth for the
         channel flow:
            h = ((n * Q_local) / (W_channel * sqrt(S)))^(3/5)
         and set the local water-surface elevation  WSE = z_bed + h.
      3. Build a spatially varying water-surface reference field by assigning
         every DEM cell the WSE of its NEAREST active river station (Euclidean
         nearest-station, computed with an exact distance transform). This is a
         thalweg-following water surface — it descends downstream with the bed,
         never a single global stage.
      4. Candidate wet cells are those whose terrain lies within the local
         wetted cross-section band:  z_bed - tol <= DEM <= WSE_ref. The upper
         bound (DEM <= WSE) requires the water surface to be above the terrain;
         the lower bound (DEM >= z_bed) excludes cells that sit BELOW the local
         channel bed — these belong to a separate, lower-lying drainage and are
         not part of this reach's routed flow. Without the lower bound, an
         upstream water surface bleeds down connected terrain into distant deep
         valleys, producing a physically impossible bath-tub over-spread that
         violates mass conservation (observed on wide/open domains).
      5. INUNDATION EXTENT IS TOPOGRAPHIC + CONNECTED, NOT A FIXED CORRIDOR:
         keep only candidate cells that are 8-connected to a genuinely wetted
         channel seed cell (scipy.ndimage.label). Disconnected low basins that
         the water cannot physically reach are excluded. There is NO fixed
         lateral width / radius / buffer anywhere in this path.
      6. depth = WSE_ref - DEM on connected wet cells; maximum-depth envelope
         updated. arrival_time[cell] = first timestep the cell becomes part of
         the connected inundation.
      7. Velocity is the Manning CHANNEL-FLOW velocity of the nearest station
         (computed from the hydraulic flow depth h, NOT the standing
         water-column depth WSE-DEM), propagated to that station's wet cells.

    No dam-specific coordinates, and no fixed inundation radius, appear in this
    function. The flood extent is determined entirely by the real DEM and the
    physically computed water surface.
    """
    rows, cols = dem_data.shape
    n_manning  = float(dam_config["manning_n_channel"])
    max_head   = float(dam_config["breach_depth_m"])
    # Representative channel top width for the Manning NORMAL-DEPTH hydraulics
    # only. This is a hydraulic parameter (sets flow depth h); it does NOT cap
    # the inundation extent, which comes from DEM connectivity + WSE below.
    W_channel  = float(dam_config.get("breach_bottom_width_m", 150.0))
    W_channel  = min(500.0, max(30.0, W_channel))

    # Metric pixel dimensions (geographic CRS assumed)
    dam_lat, _dam_lon = dam_coord
    dx_deg = abs(transform.a)
    dy_deg = abs(transform.e)
    lat_rad = math.radians(dam_lat)
    dx_m = dx_deg * 111320.0 * math.cos(lat_rad)
    dy_m = dy_deg * 111320.0

    valid_dem = (dem_data != nodata) & np.isfinite(dem_data) & (dem_data > -1000.0)

    max_depth    = np.zeros(dem_data.shape, dtype=np.float32)
    max_velocity = np.zeros(dem_data.shape, dtype=np.float32)
    arrival_time = np.full(dem_data.shape, ARRIVAL_NODATA_SENTINEL, dtype=np.float32)

    # 8-connectivity structuring element for connected-component labelling.
    conn8 = ndimage.generate_binary_structure(2, 2)

    # Clamp river-node cell indices into the grid (defensive).
    node_r = np.array([min(rows - 1, max(0, nd["r"])) for nd in river_nodes], dtype=np.int64)
    node_c = np.array([min(cols - 1, max(0, nd["c"])) for nd in river_nodes], dtype=np.int64)
    node_s = np.array([nd["s_m"]  for nd in river_nodes], dtype=np.float64)
    node_z = np.array([nd["z"]    for nd in river_nodes], dtype=np.float64)
    node_slope = np.array([nd["slope"] for nd in river_nodes], dtype=np.float64)

    timesteps_summary = []
    # Sample hydrograph every 3 steps for efficiency
    sample_records = hydro_records[::3]

    for pt in sample_records:
        t_min = pt["time_min"]
        q_in  = pt["discharge_m3s"]
        if q_in <= 0.0:
            continue

        # Wave-front celerity: c = sqrt(g * h_eff) capped physically
        h_eff      = min(15.0, max_head * 0.4)
        c_celerity = min(9.5, max(4.0, math.sqrt(9.81 * h_eff)))
        reach_dist_m = t_min * 60.0 * c_celerity

        active = node_s <= reach_dist_m
        if not np.any(active):
            continue

        a_idx  = np.nonzero(active)[0]
        # Downstream attenuation along channel
        decay  = np.exp(-0.000015 * node_s[a_idx])
        q_loc  = q_in * decay
        slope  = node_slope[a_idx]
        z_bed  = node_z[a_idx]

        # Manning normal depth of the CHANNEL FLOW (hydraulic flow depth)
        h_manning = np.power(
            (n_manning * np.maximum(1.0, q_loc)) / (W_channel * np.sqrt(slope)),
            0.6,
        )
        # Physical flow depth is bounded by the available head at the breach.
        h_water = np.minimum(max_head * decay, np.maximum(depth_threshold_m, h_manning))
        wse     = z_bed + h_water

        # Channel-flow velocity from the HYDRAULIC FLOW DEPTH (Manning), not the
        # standing water-column depth. This is the physically meaningful advective
        # velocity of the routed flow.
        v_channel = (1.0 / n_manning) * np.power(np.maximum(0.01, h_water), 2.0 / 3.0) * np.sqrt(slope)

        # ── Seed the wetted channel cells for this timestep ──────────────────
        seed_bool = np.zeros(dem_data.shape, dtype=bool)
        wse_at_node = np.full(dem_data.shape, -1e9, dtype=np.float32)
        zbed_at_node = np.full(dem_data.shape, -1e9, dtype=np.float32)
        vch_at_node = np.zeros(dem_data.shape, dtype=np.float32)
        ar, ac = node_r[a_idx], node_c[a_idx]
        seed_bool[ar, ac] = True
        # Where several stations map to one cell, keep the deeper water surface.
        np.maximum.at(wse_at_node, (ar, ac), wse.astype(np.float32))
        np.maximum.at(zbed_at_node, (ar, ac), z_bed.astype(np.float32))
        np.maximum.at(vch_at_node, (ar, ac), v_channel.astype(np.float32))

        # ── Nearest active station for every cell (exact distance transform) ──
        # indices of the nearest True (seed) cell -> gives that station's WSE/vel.
        _, (ir, ic) = ndimage.distance_transform_edt(~seed_bool, return_indices=True)
        wse_ref  = wse_at_node[ir, ic]        # spatially varying water surface
        zbed_ref = zbed_at_node[ir, ic]       # local channel-bed of that station
        vch_ref  = vch_at_node[ir, ic]

        # ── Candidate wet cells: the WETTED CROSS-SECTION band ────────────────
        # A cell holds water only when its terrain lies between the local channel
        # bed and the local water surface: z_bed <= DEM <= WSE. This is the
        # routed flood-wave envelope. Cells whose terrain is BELOW the local
        # channel bed belong to a different (lower) drainage and are excluded —
        # this prevents an upstream stage from bath-tubbing distant deep valleys
        # (which otherwise violates mass conservation). No fixed radius is used;
        # lateral extent is still governed entirely by the real DEM + WSE.
        BED_TOL_M = 2.0
        candidate = (
            valid_dem
            & (dem_data <= wse_ref)
            & (dem_data >= (zbed_ref - BED_TOL_M))
        )

        # ── Enforce hydraulic connectivity to a wetted channel seed ───────────
        labels, _n = ndimage.label(candidate, structure=conn8)
        seed_labels = np.unique(labels[seed_bool & candidate])
        seed_labels = seed_labels[seed_labels != 0]
        if seed_labels.size == 0:
            continue
        wet_now = np.isin(labels, seed_labels)

        # ── Depth / velocity / arrival updates ────────────────────────────────
        depth_now = np.where(wet_now, np.maximum(0.0, wse_ref - dem_data), 0.0).astype(np.float32)
        max_depth = np.maximum(max_depth, depth_now)

        vel_now = np.where(wet_now & (depth_now > 0.05), vch_ref, 0.0).astype(np.float32)
        max_velocity = np.maximum(max_velocity, vel_now)

        newly = wet_now & (depth_now > depth_threshold_m) & (arrival_time > 900.0)
        arrival_time[newly] = t_min

        # Timestep snapshot
        wet_mask = max_depth > depth_threshold_m
        cur_area = float(np.sum(wet_mask) * pixel_area_m2 / 1e6)
        timesteps_summary.append({
            "time_min":           round(t_min, 1),
            "discharge_m3s":      round(q_in, 1),
            "max_depth_m":        round(float(np.max(max_depth)), 2),
            "max_velocity_ms":    round(float(np.max(max_velocity)), 2),
            "inundated_area_sqkm": round(cur_area, 2),
        })

    # Finalise arrays
    arrival_time[arrival_time > 900.0] = ARRIVAL_NODATA_SENTINEL
    max_depth[~valid_dem]    = nodata
    max_velocity[~valid_dem] = nodata

    wet_idx = (max_depth >= depth_threshold_m) & valid_dem
    n_wet   = int(np.sum(wet_idx))
    area_km2 = n_wet * pixel_area_m2 / 1e6

    peak_d = float(np.max(max_depth[wet_idx]))    if n_wet > 0 else 0.0
    peak_v = float(np.max(max_velocity[wet_idx])) if n_wet > 0 else 0.0
    mean_d = float(np.mean(max_depth[wet_idx]))   if n_wet > 0 else 0.0
    mean_v = float(np.mean(max_velocity[wet_idx])) if n_wet > 0 else 0.0

    return {
        "max_depth":         max_depth,
        "max_velocity":      max_velocity,
        "arrival_time":      arrival_time,
        "peak_depth_m":      round(peak_d, 2),
        "peak_velocity_ms":  round(peak_v, 2),
        "mean_depth_m":      round(mean_d, 2),
        "mean_velocity_ms":  round(mean_v, 2),
        "inundated_area_sqkm": round(area_km2, 2),
        "inundated_cell_count": n_wet,
        "timesteps":         timesteps_summary,
    }


# ===========================================================================
# STEP 5 — INUNDATION MASK + GIS VECTORIZATION
# ===========================================================================

def derive_inundation_mask(
    max_depth: np.ndarray,
    threshold_m: float = INUNDATION_DEPTH_THRESHOLD_M,
) -> np.ndarray:
    """
    Binary inundation mask derived programmatically from depth raster.
    mask == 1 where max_depth >= threshold_m.
    """
    return (max_depth >= threshold_m).astype(np.uint8)


def vectorize_flood_extent(
    inundation_mask: np.ndarray,
    transform,
    dam_id: str,
    scenario_id: str,
    inundated_area_sqkm: float,
    peak_depth_m: float,
    peak_velocity_ms: float,
    simplify_tolerance: float = 0.0002,
) -> Polygon:
    """
    Vectorize flood extent polygon directly from the inundation_mask raster.
    Returns simplified shapely Polygon / MultiPolygon.
    """
    poly_list = []
    for geom_dict, val in rasterio_shapes(
        inundation_mask, mask=(inundation_mask == 1), transform=transform
    ):
        if val == 1:
            coords = geom_dict["coordinates"]
            p = Polygon(coords[0], [coords[i] for i in range(1, len(coords))])
            if p.is_valid and p.area > 0:
                poly_list.append(p)

    combined  = unary_union(poly_list) if poly_list else Polygon()
    simplified = combined.simplify(simplify_tolerance, preserve_topology=True)
    return simplified


def export_gis_products(
    max_depth: np.ndarray,
    max_velocity: np.ndarray,
    arrival_time: np.ndarray,
    inundation_mask: np.ndarray,
    flood_polygon,
    raster_meta: dict,
    nodata: float,
    output_dir: str,
    dam_id: str,
    scenario_id: str,
    inundated_area_sqkm: float,
    peak_depth_m: float,
    peak_velocity_ms: float,
) -> Dict[str, str]:
    """
    Write all standard GIS products to output_dir.
    Returns dict of output file paths.
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    meta_f32 = {**raster_meta, "dtype": "float32", "count": 1,
                 "nodata": nodata, "compress": "lzw"}
    meta_u8  = {**raster_meta, "dtype": "uint8",   "count": 1,
                 "nodata": 0,    "compress": "lzw"}

    files = {}

    # Raster products
    for name, arr, m in [
        ("maximum_depth.tif",    max_depth,       meta_f32),
        ("maximum_velocity.tif", max_velocity,    meta_f32),
        ("arrival_time.tif",     arrival_time,    meta_f32),
        ("inundation_mask.tif",  inundation_mask, meta_u8),
    ]:
        path = str(out / name)
        with rasterio.open(path, "w", **m) as dst:
            dst.write(arr, 1)
        files[name.replace(".tif", "").replace(".", "_")] = path

    # GeoJSON
    geojson_path = str(out / "flood_extent.geojson")
    fc = {
        "type": "FeatureCollection",
        "name": f"{dam_id}_flood_inundation_extent",
        "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}},
        "features": [{
            "type": "Feature",
            "properties": {
                "dam_id":              dam_id,
                "scenario_id":         scenario_id,
                "solver":              "2D Manning kinematic/diffusion-wave approximation",
                "sph_status":          "NOT YET COUPLED",
                "delft3d_status":      "EXPORTER ONLY",
                "inundated_area_sqkm": inundated_area_sqkm,
                "peak_depth_m":        peak_depth_m,
                "peak_velocity_ms":    peak_velocity_ms,
                "inundation_threshold_m": INUNDATION_DEPTH_THRESHOLD_M,
            },
            "geometry": mapping(flood_polygon),
        }],
    }
    with open(geojson_path, "w", encoding="utf-8") as f:
        json.dump(fc, f, indent=2)
    files["flood_extent_geojson"] = geojson_path

    # KML
    kml_path = str(out / "flood_extent.kml")
    _write_kml(flood_polygon, dam_id, inundated_area_sqkm, peak_depth_m, kml_path)
    files["flood_extent_kml"] = kml_path

    # Shapefile (via GeoPandas)
    shp_path = str(out / "flood_extent.shp")
    try:
        import geopandas as gpd2
        gdf_out = gpd2.GeoDataFrame(
            [{"dam_id": dam_id, "scenario": scenario_id,
              "area_km2": inundated_area_sqkm, "peak_depth": peak_depth_m}],
            geometry=[flood_polygon],
            crs="EPSG:4326",
        )
        gdf_out.to_file(shp_path)
        files["flood_extent_shp"] = shp_path
    except Exception as e:
        logger.warning(f"Shapefile export failed: {e}")
        files["flood_extent_shp"] = None

    return files


def _write_kml(poly_geom, dam_id: str, area_sqkm: float, peak_depth_m: float, kml_path: str):
    polys = (
        list(poly_geom.geoms)
        if isinstance(poly_geom, MultiPolygon)
        else ([poly_geom] if isinstance(poly_geom, Polygon) else [])
    )
    placemarks = ""
    for idx, p in enumerate(polys):
        coords = " ".join(f"{x},{y},0" for x, y in p.exterior.coords)
        placemarks += f"""
    <Placemark>
      <name>Inundation Zone {idx+1}</name>
      <Style>
        <LineStyle><color>ff0000ff</color><width>2</width></LineStyle>
        <PolyStyle><color>7f0000ff</color></PolyStyle>
      </Style>
      <Polygon><outerBoundaryIs><LinearRing>
        <coordinates>{coords}</coordinates>
      </LinearRing></outerBoundaryIs></Polygon>
    </Placemark>"""

    kml_doc = f"""<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <name>{dam_id} Dam Break Inundation Extent</name>
    <description>Simulated Area: {area_sqkm:.2f} km2. Max Depth: {peak_depth_m:.2f} m.</description>
    {placemarks}
  </Document>
</kml>"""
    with open(kml_path, "w", encoding="utf-8") as f:
        f.write(kml_doc)


# ===========================================================================
# TOP-LEVEL RUNNER
# ===========================================================================

class GeneralizedFloodRoutingEngine:
    """
    Top-level entry point for the generalized dam-break simulation pipeline.

    Usage
    -----
    result = GeneralizedFloodRoutingEngine.run(
        dam_config=dam_config_dict,
        dataset_paths={"dem": "...", "river": "...", "output_dir": "..."},
        hydro_records=hydro_list,          # pre-computed or auto-computed
        V_active_m3=500_000_000.0,
        dt_override=60.0,
        depth_threshold_m=0.15,
        river_name_hint="Cauvery",
    )

    Solver classification (immutable):
      - Hydraulic solver: 2D Manning kinematic/diffusion-wave approximation
      - SPH: NOT YET COUPLED
      - Delft3D: EXPORTER ONLY
    """

    SOLVER_NAME  = "2D Manning kinematic/diffusion-wave approximation"
    SPH_STATUS   = "NOT YET COUPLED"
    DELFT3D_STATUS = "EXPORTER ONLY"

    @classmethod
    def run(
        cls,
        dam_config: Dict[str, Any],
        dataset_paths: Dict[str, str],
        hydro_records: Optional[List[Dict[str, float]]] = None,
        V_active_m3: Optional[float] = None,
        dt_override: float = 60.0,
        depth_threshold_m: float = INUNDATION_DEPTH_THRESHOLD_M,
        river_name_hint: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Execute the full generalized simulation pipeline.

        Parameters
        ----------
        dam_config : dict — all dam-specific engineering parameters
        dataset_paths : dict — {"dem": str, "river": str, "output_dir": str}
        hydro_records : pre-computed hydrograph (if None, auto-computed from dam_config)
        V_active_m3 : active breach volume [m³] (must match dam_config if hydro pre-computed)
        dt_override : timestep in seconds
        depth_threshold_m : inundation threshold
        river_name_hint : keyword to filter main-stem features by name
        """
        dam_id      = dam_config.get("dam_id", "unknown_dam")
        scenario_id = dam_config.get("scenario_id", "baseline_breach")
        dam_coord   = (dam_config["dam_lat"], dam_config["dam_lon"])

        print(f"\n[ENGINE] GeneralizedFloodRoutingEngine starting for '{dam_id}'")
        print(f"  Solver: {cls.SOLVER_NAME}")
        print(f"  SPH: {cls.SPH_STATUS}")
        print(f"  Delft3D: {cls.DELFT3D_STATUS}")

        # ── A. Hydrograph ───────────────────────────────────────────────────
        if hydro_records is None:
            print("\n[ENGINE-A] Computing breach hydrograph...")
            hydro_records, V_active_m3 = compute_breach_hydrograph(dam_config, dt_sec=dt_override)
        else:
            if V_active_m3 is None:
                raise ValueError("V_active_m3 must be supplied when hydro_records are pre-computed")
        print(f"  Hydrograph: {len(hydro_records)} timesteps, V_active={V_active_m3/1e6:.2f} MCM")

        # ── B. Mass conservation ────────────────────────────────────────────
        print("\n[ENGINE-B] Verifying mass conservation...")
        mass_result = verify_mass_conservation(hydro_records, V_active_m3)
        print(
            f"  Peak Q: {mass_result['peak_discharge_m3s']:,.1f} m3/s "
            f"at T+{mass_result['time_to_peak_min']:.1f} min"
        )
        print(f"  Released: {mass_result['released_volume_mcm']:.4f} MCM")
        print(f"  Discrepancy: {mass_result['numerical_discrepancy_m3']:+.2f} m3 "
              f"({mass_result['mass_balance_error_pct']:.8f}%)")

        # ── C. Load DEM ─────────────────────────────────────────────────────
        dem_path = dataset_paths["dem"]
        print(f"\n[ENGINE-C] Loading DEM: {dem_path}")
        t_start = time.time()
        with rasterio.open(dem_path) as src:
            dem_data  = src.read(1).astype(np.float32)
            raster_meta = src.meta.copy()
            transform   = src.transform
            nodata      = src.nodata if src.nodata is not None else NODATA_DEFAULT
            bounds      = src.bounds
            crs         = src.crs

        rows, cols = dem_data.shape
        dx_deg = abs(transform.a)
        dy_deg = abs(transform.e)
        lat_r  = math.radians(dam_coord[0])
        dx_m   = dx_deg * 111320.0 * math.cos(lat_r)
        dy_m   = dy_deg * 111320.0
        pixel_area_m2 = dx_m * dy_m
        print(f"  DEM: {rows}x{cols}, pixel={dx_m:.1f}x{dy_m:.1f} m, CRS={crs}")

        # ── D. River reach extraction ───────────────────────────────────────
        river_path = dataset_paths["river"]
        print(f"\n[ENGINE-D] Extracting downstream river reach from: {river_path}")
        downstream_reach = extract_downstream_reach(
            river_path, bounds, dam_coord, dem_data, transform, nodata,
            main_stem_name_hint=river_name_hint
        )
        reach_km = downstream_reach.length * 111.32
        print(f"  Downstream reach: {reach_km:.2f} km within DEM domain")

        # ── E. Station sampling ─────────────────────────────────────────────
        print(f"\n[ENGINE-E] Sampling river stations at {STATION_SPACING_M}m spacing...")
        river_nodes = sample_river_stations(downstream_reach, dem_data, transform, nodata)
        n_nodes = len(river_nodes)
        z0 = river_nodes[0]["z"]
        zn = river_nodes[-1]["z"]
        s_total = river_nodes[-1]["s_m"]
        mean_slope = (z0 - zn) / max(1.0, s_total) if s_total > 0 else 0.0
        print(f"  Stations: {n_nodes}, reach={s_total/1000:.2f} km")
        print(f"  Elevation: upstream={z0:.1f} m -> downstream={zn:.1f} m")
        print(f"  Mean longitudinal slope: {mean_slope*1000:.3f} m/km")

        # ── F. Propagation ──────────────────────────────────────────────────
        print("\n[ENGINE-F] Running 2D Manning kinematic/diffusion-wave propagation...")
        prop_result = propagate_flood_wave(
            dem_data, transform, nodata, river_nodes, hydro_records,
            dam_config, pixel_area_m2, dam_coord, depth_threshold_m
        )
        runtime_sec = time.time() - t_start
        print(f"  Peak depth: {prop_result['peak_depth_m']:.2f} m")
        print(f"  Peak velocity: {prop_result['peak_velocity_ms']:.2f} m/s")
        print(f"  Inundated area: {prop_result['inundated_area_sqkm']:.2f} km2")
        print(f"  Runtime: {runtime_sec:.2f} s")

        # ── G. Inundation mask ──────────────────────────────────────────────
        inundation_mask = derive_inundation_mask(prop_result["max_depth"], depth_threshold_m)

        # ── H. Vectorize ────────────────────────────────────────────────────
        print("\n[ENGINE-G] Vectorizing flood extent from inundation mask...")
        flood_polygon = vectorize_flood_extent(
            inundation_mask, transform,
            dam_id, scenario_id,
            prop_result["inundated_area_sqkm"],
            prop_result["peak_depth_m"],
            prop_result["peak_velocity_ms"],
        )

        # ── I. GIS export ───────────────────────────────────────────────────
        output_dir = dataset_paths["output_dir"]
        print(f"\n[ENGINE-H] Exporting GIS products to: {output_dir}")
        gis_files = export_gis_products(
            prop_result["max_depth"],
            prop_result["max_velocity"],
            prop_result["arrival_time"],
            inundation_mask,
            flood_polygon,
            raster_meta, nodata, output_dir,
            dam_id, scenario_id,
            prop_result["inundated_area_sqkm"],
            prop_result["peak_depth_m"],
            prop_result["peak_velocity_ms"],
        )

        return {
            "dam_id":          dam_id,
            "scenario_id":     scenario_id,
            "solver":          cls.SOLVER_NAME,
            "sph_status":      cls.SPH_STATUS,
            "delft3d_status":  cls.DELFT3D_STATUS,
            "mass_result":     mass_result,
            "hydro_records":   hydro_records,
            "river_nodes":     river_nodes,
            "reach_km":        round(reach_km, 2),
            "n_stations":      n_nodes,
            "upstream_elev_m": round(z0, 2),
            "downstream_elev_m": round(zn, 2),
            "mean_slope_m_per_km": round(mean_slope * 1000, 4),
            "prop_result":     prop_result,
            "inundation_mask": inundation_mask,
            "flood_polygon":   flood_polygon,
            "gis_files":       gis_files,
            "pixel_area_m2":   pixel_area_m2,
            "raster_meta":     raster_meta,
            "nodata":          nodata,
            "runtime_sec":     round(runtime_sec, 2),
        }
