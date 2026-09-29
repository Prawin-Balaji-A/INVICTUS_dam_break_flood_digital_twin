r"""
build_tehri_scene.py

Builds the Tehri Dam digital-twin Blender scene, including an animated
dam-break flood visualization, from the pre-processed real geographic
data already produced under E:\dam\tehri_data\blender_ready\.

Uses ONLY Blender's built-in Python API (bpy, bmesh, mathutils) plus the
Python standard library (json, math, array, os, sys). No external
geospatial packages are imported or required.

IMPORTANT: This is a VISUALIZATION. The dam-break flood animation is a
visual approximation, not a hydraulic/engineering simulation. The
terrain, dam location, reservoir, roads, and buildings are derived from
real geographic data already prepared in prior stages; nothing here
fabricates new geography.

Run:
    cd E:\dam
    "C:\Program Files\Blender Foundation\Blender 5.2\blender.exe" ^
        --background --python build_tehri_scene.py
"""

import bpy
import bmesh
import json
import math
import sys
import array
from pathlib import Path
from mathutils import Vector

# ============================================================================
# CONFIG
# ============================================================================

PROJECT_ROOT = Path(r"E:\dam")
DATA_DIR = PROJECT_ROOT / "tehri_data" / "blender_ready"

OUTPUT_BLEND = PROJECT_ROOT / "tehri_dam_digital_twin.blend"
OUTPUT_PREVIEW = PROJECT_ROOT / "tehri_dam_preview.png"

FPS = 30
FRAME_START = 1
FRAME_END = 600

# Animation phase boundaries (frames) — exactly as specified.
PHASE_CALM_END = 120
PHASE_BREACH_BEGIN_END = 180
PHASE_MAJOR_RELEASE_END = 300
PHASE_DOWNSTREAM_TRAVEL_END = 450
PHASE_INFRASTRUCTURE_END = 540
PHASE_FINAL_END = 600

VERTICAL_EXAGGERATION = 1.0
CREST_WIDTH_VIZ_M = 20.0  # not in verified reference dims — documented visualization approximation

REQUIRED_FILES = [
    "terrain_heightmap.f32",
    "terrain_meta.json",
    "buildings.json",
    "roads.json",
    "waterways.json",
    "water.json",
    "dam_placement.json",
    "scene_metadata.json",
]

TOTAL_STEPS = 16
_step_counter = [0]


def step(msg):
    _step_counter[0] += 1
    print(f"[{_step_counter[0]}/{TOTAL_STEPS}] {msg}")


def log(msg):
    print(f"    {msg}")


# ============================================================================
# STEP 1 — VALIDATE REQUIRED FILES
# ============================================================================

step("Validating input files...")
missing = []
for fname in REQUIRED_FILES:
    fpath = DATA_DIR / fname
    if not fpath.exists():
        missing.append(str(fpath))

if missing:
    for m in missing:
        print("MISSING:")
        print(f"    {m}")
    print("\nRun tehri_geo_to_blender_stage.py first to regenerate these files.")
    sys.exit(1)

log("All required files present.")


def load_json(name):
    with open(DATA_DIR / name, "r", encoding="utf-8") as f:
        return json.load(f)


# ============================================================================
# STEP 2 — LOAD TERRAIN
# ============================================================================

step("Loading terrain...")

terrain_meta = load_json("terrain_meta.json")
heightmap_path = DATA_DIR / "terrain_heightmap.f32"

_hm = array.array("f")
with open(heightmap_path, "rb") as f:
    _hm.frombytes(f.read())

TW, TH = terrain_meta["width"], terrain_meta["height"]
if len(_hm) != TW * TH:
    print(f"MISSING:\n    terrain_heightmap.f32 size mismatch "
          f"(expected {TW*TH}, got {len(_hm)})")
    sys.exit(1)

X_COORDS = terrain_meta["x_coords_local_m"]
Y_COORDS = terrain_meta["y_coords_local_m"]
DAM_BASE_ELEVATION = terrain_meta["dam_base_elevation_m"]
MIN_ELEV = terrain_meta["min_elevation_m"]
MAX_ELEV = terrain_meta["max_elevation_m"]

log(f"Terrain grid: {TW} x {TH}, elevation range {MIN_ELEV:.1f}m - {MAX_ELEV:.1f}m")
log(f"Dam base elevation (real, sampled from DEM): {DAM_BASE_ELEVATION:.2f} m")


def heightmap_get(col, row):
    col = max(0, min(TW - 1, col))
    row = max(0, min(TH - 1, row))
    return _hm[row * TW + col]


def terrain_height_local(x, y):
    """Bilinear-sampled elevation at local (x,y) meters, relative to dam base."""
    x0, x1 = X_COORDS[0], X_COORDS[-1]
    y0, y1 = Y_COORDS[0], Y_COORDS[-1]
    if x1 == x0 or y1 == y0:
        return 0.0
    fx = (x - x0) / (x1 - x0) * (TW - 1)
    fy = (y - y0) / (y1 - y0) * (TH - 1)
    fx = max(0.0, min(TW - 1.001, fx))
    fy = max(0.0, min(TH - 1.001, fy))
    c0, r0 = int(fx), int(fy)
    c1, r1 = min(c0 + 1, TW - 1), min(r0 + 1, TH - 1)
    tx, ty = fx - c0, fy - r0
    z00, z10 = heightmap_get(c0, r0), heightmap_get(c1, r0)
    z01, z11 = heightmap_get(c0, r1), heightmap_get(c1, r1)
    z = (z00 * (1 - tx) * (1 - ty) + z10 * tx * (1 - ty) +
         z01 * (1 - tx) * ty + z11 * tx * ty)
    return (z - DAM_BASE_ELEVATION) * VERTICAL_EXAGGERATION


# ============================================================================
# SCENE / COLLECTION SETUP
# ============================================================================

def clear_scene():
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for col in list(bpy.data.collections):
        bpy.data.collections.remove(col)


def make_collection(name):
    if name in bpy.data.collections:
        return bpy.data.collections[name]
    col = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(col)
    return col


def link_only(obj, collection):
    for c in list(obj.users_collection):
        c.objects.unlink(obj)
    collection.objects.link(obj)


clear_scene()

COL_TERRAIN = make_collection("TEHRI_TERRAIN")
COL_DAM = make_collection("TEHRI_DAM")
COL_RESERVOIR = make_collection("TEHRI_RESERVOIR")
COL_ROADS = make_collection("TEHRI_ROADS")
COL_BUILDINGS = make_collection("TEHRI_BUILDINGS")
COL_WATERWAYS = make_collection("TEHRI_WATERWAYS")
COL_FLOOD = make_collection("TEHRI_FLOOD")
COL_EFFECTS = make_collection("TEHRI_EFFECTS")
COL_LIGHTING = make_collection("TEHRI_LIGHTING")
COL_CAMERAS = make_collection("TEHRI_CAMERAS")


def rotate_vec(x, y, angle_rad):
    ca, sa = math.cos(angle_rad), math.sin(angle_rad)
    return (x * ca - y * sa, x * sa + y * ca)


def point_at(obj, target):
    direction = Vector(target) - obj.location
    if direction.length > 1e-6:
        obj.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()


def add_frame_driver(prop_owner, data_path, index, expr):
    fcurve = prop_owner.driver_add(data_path, index) if index is not None else prop_owner.driver_add(data_path)
    drv = fcurve.driver
    drv.type = 'SCRIPTED'
    var = drv.variables.new()
    var.name = "frame"
    var.type = 'SINGLE_PROP'
    var.targets[0].id_type = 'SCENE'
    var.targets[0].id = bpy.context.scene
    var.targets[0].data_path = "frame_current"
    drv.expression = expr
    return fcurve


def smooth_fcurves(obj, extrapolation='CONSTANT'):
    # Blender 5.2 uses layered Actions by default.  In that system
    # Action.fcurves is no longer available directly.  The smoothing here is
    # only cosmetic, so safely skip it when the legacy collection is absent.
    anim = getattr(obj, "animation_data", None)
    action = getattr(anim, "action", None) if anim else None
    if not action:
        return

    fcurves = getattr(action, "fcurves", None)
    if fcurves is None:
        return

    for fcurve in fcurves:
        fcurve.extrapolation = extrapolation
        for kp in fcurve.keyframe_points:
            kp.interpolation = 'BEZIER'
            kp.easing = 'EASE_IN_OUT'


# ----------------------------------------------------------------------------
# ROBUST NODE-SOCKET HELPERS (Blender-version-compatibility safeguard)
#
# Different Blender versions occasionally rename node sockets (e.g. a
# ColorRamp/ShaderNodeValToRGB node only ever exposes "Color" and "Alpha"
# as OUTPUTS -- never "Fac" -- while "Fac" is only a valid INPUT name on
# that node type). These helpers look up a socket by name from a list of
# acceptable candidates and fail loudly with a clear message, or fall
# back to a positional socket with a warning, instead of crashing deep
# inside a KeyError.
# ----------------------------------------------------------------------------

def get_socket(sockets, candidates, context=""):
    for name in candidates:
        if name in sockets:
            return sockets[name]
    if len(sockets) > 0:
        log(f"WARNING: none of {candidates} found for {context}; "
            f"falling back to first available socket '{sockets[0].name}'")
        return sockets[0]
    raise KeyError(f"No sockets available at all for {context} (tried: {candidates})")


def safe_link(links, from_node, from_candidates, to_node, to_candidates, context=""):
    src = get_socket(from_node.outputs, from_candidates,
                      context=f"{from_node.name}.outputs [{context}]")
    dst = get_socket(to_node.inputs, to_candidates,
                      context=f"{to_node.name}.inputs [{context}]")
    links.new(src, dst)


# ============================================================================
# MATERIALS
# ============================================================================

def _set_input(bsdf, names, value):
    for n in names:
        if n in bsdf.inputs:
            bsdf.inputs[n].default_value = value
            return


def mat_terrain():
    """Real-elevation-driven terrain material.

    FIXED: previously attempted to read a "Fac" OUTPUT off a ColorRamp
    (ShaderNodeValToRGB) node, which does not exist -- ColorRamp nodes
    only output "Color" and "Alpha". The slope-based mix factor now comes
    from a dedicated Map Range node instead, while the ColorRamp is used
    only for the Color output it actually provides.
    """
    name = "Mat_Terrain"
    if name in bpy.data.materials:
        return bpy.data.materials[name]
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nodes, links = nt.nodes, nt.links
    nodes.clear()

    out = nodes.new("ShaderNodeOutputMaterial")
    out.location = (700, 0)
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (400, 0)
    _set_input(bsdf, ["Roughness"], 0.9)

    geo = nodes.new("ShaderNodeNewGeometry")
    geo.location = (-900, 0)

    sep_n = nodes.new("ShaderNodeSeparateXYZ")
    sep_n.location = (-700, -150)
    safe_link(links, geo, ["Normal"], sep_n, ["Vector"], context="geo->sep_n")

    sep_p = nodes.new("ShaderNodeSeparateXYZ")
    sep_p.location = (-700, 150)
    safe_link(links, geo, ["Position"], sep_p, ["Vector"], context="geo->sep_p")

    # Elevation-based factor (0..1 across the real DEM elevation range)
    elev_range = nodes.new("ShaderNodeMapRange")
    elev_range.location = (-480, 150)
    elev_range.inputs["From Min"].default_value = MIN_ELEV - DAM_BASE_ELEVATION
    elev_range.inputs["From Max"].default_value = MAX_ELEV - DAM_BASE_ELEVATION
    safe_link(links, sep_p, ["Z"], elev_range, ["Value"], context="sep_p->elev_range")

    # Slope-based MIX FACTOR: a scalar 0..1 value derived from the
    # geometry normal's Z component via Map Range (NOT via a ColorRamp
    # output, which has no "Fac" output socket).
    slope_fac = nodes.new("ShaderNodeMapRange")
    slope_fac.location = (-480, -350)
    slope_fac.inputs["From Min"].default_value = 0.55
    slope_fac.inputs["From Max"].default_value = 0.92
    slope_fac.clamp = True
    safe_link(links, sep_n, ["Z"], slope_fac, ["Value"], context="sep_n->slope_fac")

    # Slope-based COLOR (soil on flatter ground, rock on steep ground).
    # This node is used ONLY for its "Color" output.
    slope_ramp = nodes.new("ShaderNodeValToRGB")
    slope_ramp.location = (-480, -150)
    slope_ramp.color_ramp.elements[0].position = 0.55
    slope_ramp.color_ramp.elements[0].color = (0.30, 0.24, 0.18, 1.0)
    slope_ramp.color_ramp.elements[1].position = 0.92
    slope_ramp.color_ramp.elements[1].color = (0.42, 0.40, 0.38, 1.0)
    safe_link(links, sep_n, ["Z"], slope_ramp, ["Fac"], context="sep_n->slope_ramp")

    # Elevation-based COLOR (vegetation at low elevation, rock/snow at high elevation)
    elev_ramp = nodes.new("ShaderNodeValToRGB")
    elev_ramp.location = (-200, 150)
    elev_ramp.color_ramp.elements[0].position = 0.0
    elev_ramp.color_ramp.elements[0].color = (0.18, 0.30, 0.14, 1.0)
    elev_ramp.color_ramp.elements[1].position = 1.0
    elev_ramp.color_ramp.elements[1].color = (0.85, 0.85, 0.88, 1.0)
    safe_link(links, elev_range, ["Result"], elev_ramp, ["Fac"], context="elev_range->elev_ramp")

    mix = nodes.new("ShaderNodeMixRGB")
    mix.location = (80, 0)
    safe_link(links, slope_fac, ["Result"], mix, ["Fac"], context="slope_fac->mix")
    safe_link(links, elev_ramp, ["Color"], mix, ["Color1"], context="elev_ramp->mix")
    safe_link(links, slope_ramp, ["Color"], mix, ["Color2"], context="slope_ramp->mix")

    noise = nodes.new("ShaderNodeTexNoise")
    noise.location = (-480, -550)
    noise.inputs["Scale"].default_value = 40.0
    bump = nodes.new("ShaderNodeBump")
    bump.location = (80, -250)
    bump.inputs["Strength"].default_value = 0.15
    safe_link(links, noise, ["Fac"], bump, ["Height"], context="noise->bump")
    safe_link(links, bump, ["Normal"], bsdf, ["Normal"], context="bump->bsdf")

    safe_link(links, mix, ["Color"], bsdf, ["Base Color"], context="mix->bsdf")
    safe_link(links, bsdf, ["BSDF"], out, ["Surface"], context="bsdf->out")
    return mat


def mat_asphalt():
    name = "Mat_Asphalt"
    if name in bpy.data.materials:
        return bpy.data.materials[name]
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (0.045, 0.045, 0.05, 1.0)
    _set_input(bsdf, ["Roughness"], 0.9)
    return mat


def mat_dam_rockfill():
    name = "Mat_Dam_Rockfill"
    if name in bpy.data.materials:
        return bpy.data.materials[name]
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nodes, links = nt.nodes, nt.links
    bsdf = nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (0.42, 0.39, 0.35, 1.0)
    _set_input(bsdf, ["Roughness"], 0.95)
    noise = nodes.new("ShaderNodeTexNoise")
    noise.location = (-400, -200)
    noise.inputs["Scale"].default_value = 60.0
    noise.inputs["Detail"].default_value = 8.0
    bump = nodes.new("ShaderNodeBump")
    bump.location = (-100, -200)
    bump.inputs["Strength"].default_value = 0.6
    safe_link(links, noise, ["Fac"], bump, ["Height"], context="noise->bump")
    safe_link(links, bump, ["Normal"], bsdf, ["Normal"], context="bump->bsdf")
    return mat


def mat_dam_crest():
    name = "Mat_Dam_Crest"
    if name in bpy.data.materials:
        return bpy.data.materials[name]
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (0.5, 0.49, 0.46, 1.0)
    _set_input(bsdf, ["Roughness"], 0.75)
    return mat


def mat_breach():
    name = "Mat_Breach_Dark"
    if name in bpy.data.materials:
        return bpy.data.materials[name]
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (0.05, 0.04, 0.03, 1.0)
    _set_input(bsdf, ["Roughness"], 1.0)
    return mat


def mat_building(category):
    name = f"Mat_Building_{category}"
    if name in bpy.data.materials:
        return bpy.data.materials[name]
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    palette = {
        "residential": (0.70, 0.60, 0.48),
        "commercial": (0.55, 0.57, 0.60),
        "industrial": (0.40, 0.40, 0.38),
        "public": (0.62, 0.55, 0.50),
        "unknown": (0.58, 0.58, 0.58),
    }
    c = palette.get(category, palette["unknown"])
    bsdf.inputs["Base Color"].default_value = (*c, 1.0)
    _set_input(bsdf, ["Roughness"], 0.55)
    return mat


def mat_foam():
    name = "Mat_Foam"
    if name in bpy.data.materials:
        return bpy.data.materials[name]
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (0.93, 0.96, 1.0, 1.0)
    _set_input(bsdf, ["Roughness"], 0.55)
    try:
        bsdf.inputs["Emission Color"].default_value = (0.85, 0.92, 1.0, 1.0)
        bsdf.inputs["Emission Strength"].default_value = 0.2
    except KeyError:
        pass
    return mat


def mat_water(name, speed=0.15, wave_scale=6.0, color=(0.05, 0.2, 0.32, 0.9),
              turbulence=0.2, flow_dir=(0, -1), roughness=0.08):
    if name in bpy.data.materials:
        return bpy.data.materials[name]
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    try:
        mat.blend_method = 'BLEND'
    except Exception:
        pass
    nt = mat.node_tree
    nodes, links = nt.nodes, nt.links
    nodes.clear()

    out = nodes.new("ShaderNodeOutputMaterial")
    out.location = (700, 0)
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (400, 0)
    bsdf.inputs["Base Color"].default_value = color
    _set_input(bsdf, ["Roughness"], roughness)
    _set_input(bsdf, ["Metallic"], 0.0)
    _set_input(bsdf, ["Transmission Weight", "Transmission"], 0.55)
    _set_input(bsdf, ["IOR"], 1.333)
    if "Alpha" in bsdf.inputs:
        bsdf.inputs["Alpha"].default_value = color[3] if len(color) > 3 else 1.0

    tex_coord = nodes.new("ShaderNodeTexCoord")
    tex_coord.location = (-900, 0)
    mapping = nodes.new("ShaderNodeMapping")
    mapping.location = (-700, 0)
    safe_link(links, tex_coord, ["Object"], mapping, ["Vector"], context="texcoord->mapping")

    add_frame_driver(mapping.inputs["Location"], "default_value", 0, f"frame * {speed} * {flow_dir[0]}")
    add_frame_driver(mapping.inputs["Location"], "default_value", 1, f"frame * {speed} * {flow_dir[1]}")

    wave = nodes.new("ShaderNodeTexWave")
    wave.location = (-450, 180)
    wave.inputs["Scale"].default_value = wave_scale
    wave.inputs["Distortion"].default_value = turbulence * 5.0
    safe_link(links, mapping, ["Vector"], wave, ["Vector"], context="mapping->wave")

    noise = nodes.new("ShaderNodeTexNoise")
    noise.location = (-450, -120)
    noise.inputs["Scale"].default_value = wave_scale * 2.0
    noise.inputs["Detail"].default_value = 4.0
    safe_link(links, mapping, ["Vector"], noise, ["Vector"], context="mapping->noise")

    combine = nodes.new("ShaderNodeMath")
    combine.operation = 'ADD'
    combine.location = (-180, 60)
    safe_link(links, wave, ["Fac"], combine, ["Value"], context="wave->combine[0]")
    # second Math input has the same socket name "Value" -- link by
    # positional index since Math node inputs are not uniquely named.
    links.new(noise.outputs[get_socket(noise.outputs, ["Fac"], context="noise->combine").name],
              combine.inputs[1])

    bump = nodes.new("ShaderNodeBump")
    bump.location = (80, 180)
    bump.inputs["Strength"].default_value = 0.2 + turbulence * 0.3
    safe_link(links, combine, ["Value"], bump, ["Height"], context="combine->bump")
    safe_link(links, bump, ["Normal"], bsdf, ["Normal"], context="bump->bsdf")

    safe_link(links, bsdf, ["BSDF"], out, ["Surface"], context="bsdf->out")
    return mat


# ============================================================================
# STEP 3 — BUILD TERRAIN MESH
# ============================================================================

step("Creating terrain mesh...")


def build_terrain():
    bm = bmesh.new()
    grid = [[None] * TW for _ in range(TH)]
    for row in range(TH):
        for col in range(TW):
            x, y = X_COORDS[col], Y_COORDS[row]
            z = terrain_height_local(x, y)
            grid[row][col] = bm.verts.new((x, y, z))
    bm.verts.ensure_lookup_table()
    for row in range(TH - 1):
        for col in range(TW - 1):
            v00, v10 = grid[row][col], grid[row][col + 1]
            v01, v11 = grid[row + 1][col], grid[row + 1][col + 1]
            bm.faces.new((v00, v10, v11, v01))
    bm.normal_update()

    mesh = bpy.data.meshes.new("TEHRI_Terrain_Mesh")
    bm.to_mesh(mesh)
    bm.free()

    obj = bpy.data.objects.new("TEHRI_Terrain", mesh)
    bpy.context.scene.collection.objects.link(obj)
    obj.data.materials.append(mat_terrain())
    link_only(obj, COL_TERRAIN)
    log(f"Terrain mesh: {TW*TH} vertices, {(TW-1)*(TH-1)} faces")
    return obj


terrain_obj = build_terrain()


# ============================================================================
# STEP 4 — DAM PLACEMENT / ORIENTATION (derived from real data)
# ============================================================================

step("Loading dam placement and deriving orientation...")

dam_placement = load_json("dam_placement.json")
water_data = load_json("water.json")

REF = dam_placement.get("reference_dimensions", {}) or {}
DAM_HEIGHT_M = REF.get("height_m", 260.5)
DAM_CREST_LENGTH_M = REF.get("top_length_m", 575)
DAM_TOP_LEVEL_M = REF.get("top_level_m", 839.5)
DAM_FRL_M = REF.get("frl_m", 830)
UPSTREAM_SLOPE_RATIO = 2.5
DOWNSTREAM_SLOPE_RATIO = 2.0

DAM_CREST_Z_LOCAL = (DAM_TOP_LEVEL_M - DAM_BASE_ELEVATION) * VERTICAL_EXAGGERATION
DAM_BASE_Z_LOCAL = DAM_CREST_Z_LOCAL - DAM_HEIGHT_M * VERTICAL_EXAGGERATION
DAM_FRL_Z_LOCAL = (DAM_FRL_M - DAM_BASE_ELEVATION) * VERTICAL_EXAGGERATION

crest_angle_deg = dam_placement["dam_axis_angle_deg"]
crest_angle_rad = math.radians(crest_angle_deg)
crest_hat_raw = Vector((math.cos(crest_angle_rad), math.sin(crest_angle_rad)))
perp_a = Vector((-crest_hat_raw.y, crest_hat_raw.x))
perp_b = Vector((crest_hat_raw.y, -crest_hat_raw.x))

reservoir_feat = next((f for f in water_data["features"] if f.get("is_reservoir")), None)
if reservoir_feat is not None:
    ext = reservoir_feat["exterior_local"]
    cx = sum(p[0] for p in ext) / len(ext)
    cy = sum(p[1] for p in ext) / len(ext)
    to_reservoir = Vector((cx, cy))
    if to_reservoir.length > 1e-6:
        to_reservoir.normalize()
        upstream_hat = perp_a if perp_a.dot(to_reservoir) >= perp_b.dot(to_reservoir) else perp_b
    else:
        upstream_hat = perp_a
    orientation_method = "derived_from_reservoir_centroid (real water.json data)"
else:
    upstream_hat = perp_a
    orientation_method = "FALLBACK: no reservoir polygon found; arbitrary perpendicular used"
    log("WARNING: could not confirm upstream direction from reservoir geometry.")

downstream_hat = -upstream_hat
crest_hat = Vector((-downstream_hat.y, downstream_hat.x))

log(f"Crest angle (from dam_placement.json): {crest_angle_deg:.2f} deg "
    f"(method: {dam_placement.get('dam_axis_method')})")
log(f"Downstream direction resolved via: {orientation_method}")
log(f"downstream_hat = ({downstream_hat.x:.3f}, {downstream_hat.y:.3f})")
log(f"Dam height={DAM_HEIGHT_M}m crest_length={DAM_CREST_LENGTH_M}m top_level={DAM_TOP_LEVEL_M}m FRL={DAM_FRL_M}m")


def local_to_axis(x, y):
    """Return (along, across) where along = distance downstream from dam
    origin, across = lateral distance along the crest direction."""
    v = Vector((x, y))
    along = v.dot(downstream_hat)
    across = v.dot(crest_hat)
    return along, across


def axis_to_local(along, across):
    x = downstream_hat.x * along + crest_hat.x * across
    y = downstream_hat.y * along + crest_hat.y * across
    return x, y


# Real terrain extent along the downstream axis (used to scale flood reach —
# not fabricated, derived from actual DEM coordinate bounds).
corner_alongs = []
for cx_ in (X_COORDS[0], X_COORDS[-1]):
    for cy_ in (Y_COORDS[0], Y_COORDS[-1]):
        a, _ = local_to_axis(cx_, cy_)
        corner_alongs.append(a)
MAX_DOWNSTREAM_DISTANCE = max(corner_alongs)
log(f"Max downstream distance available in terrain data: {MAX_DOWNSTREAM_DISTANCE:.1f} m")


# ============================================================================
# STEP 5 — BUILD DAM (embankment) + BREACH VISUAL
# ============================================================================

step("Building Tehri Dam (earth-and-rockfill embankment)...")


def build_dam():
    H = DAM_HEIGHT_M * VERTICAL_EXAGGERATION
    half_crest = DAM_CREST_LENGTH_M / 2.0
    upstream_run = H * UPSTREAM_SLOPE_RATIO
    downstream_run = H * DOWNSTREAM_SLOPE_RATIO

    # Profile in (along-axis "cross", z). Negative cross = upstream, positive = downstream.
    profile = [
        (-upstream_run, DAM_BASE_Z_LOCAL),
        (-CREST_WIDTH_VIZ_M / 2.0, DAM_CREST_Z_LOCAL),
        (CREST_WIDTH_VIZ_M / 2.0, DAM_CREST_Z_LOCAL),
        (downstream_run, DAM_BASE_Z_LOCAL),
    ]

    bm = bmesh.new()
    ring_neg, ring_pos = [], []
    for cross, z in profile:
        x, y = axis_to_local(cross, -half_crest)
        ring_neg.append(bm.verts.new((x, y, z)))
    for cross, z in profile:
        x, y = axis_to_local(cross, half_crest)
        ring_pos.append(bm.verts.new((x, y, z)))

    n = len(profile)
    # The loop above already creates the crest as the i=1 side face:
    # (ring_neg[1], ring_neg[2], ring_pos[2], ring_pos[1]).
    # Do NOT create it a second time; BMesh rejects duplicate faces.
    for i in range(n - 1):
        bm.faces.new((ring_neg[i], ring_neg[i + 1], ring_pos[i + 1], ring_pos[i]))
    bm.faces.new(ring_neg)
    bm.faces.new(list(reversed(ring_pos)))

    bm.normal_update()
    mesh = bpy.data.meshes.new("TEHRI_Dam_Main_Mesh")
    bm.to_mesh(mesh)
    bm.free()

    obj = bpy.data.objects.new("TEHRI_Dam_Main", mesh)
    bpy.context.scene.collection.objects.link(obj)
    obj.data.materials.append(mat_dam_rockfill())
    obj.data.materials.append(mat_dam_crest())

    # Assign the crest material to the already-created horizontal crest face.
    # The crest is the only face whose vertices all sit at DAM_CREST_Z_LOCAL.
    crest_tol = 1e-5
    for poly in obj.data.polygons:
        if len(poly.vertices) == 4:
            z_values = [obj.data.vertices[v].co.z for v in poly.vertices]
            if all(abs(z - DAM_CREST_Z_LOCAL) <= crest_tol for z in z_values):
                poly.material_index = 1
                break

    link_only(obj, COL_DAM)

    marker = bpy.data.objects.new("TEHRI_DAM_ORIGIN_MARKER", None)
    marker.empty_display_type = 'PLAIN_AXES'
    marker.empty_display_size = 20.0
    marker.location = (0, 0, DAM_BASE_Z_LOCAL)
    bpy.context.scene.collection.objects.link(marker)
    link_only(marker, COL_DAM)

    return obj


dam_obj = build_dam()


def build_breach_visual():
    """A visually distinct breach opening at the crest that grows during
    the breach phases. Does not delete/modify the main dam mesh."""
    bx, by = axis_to_local(0.0, 0.0)

    bpy.ops.mesh.primitive_cube_add(size=1, location=(bx, by, DAM_CREST_Z_LOCAL - 2))
    notch = bpy.context.active_object
    notch.name = "TEHRI_Dam_Breach_Notch"
    notch.rotation_euler = (0, 0, math.atan2(crest_hat.y, crest_hat.x))
    notch.data.materials.append(mat_breach())
    link_only(notch, COL_DAM)

    def kf_scale(frame, scale):
        notch.scale = scale
        notch.keyframe_insert(data_path="scale", frame=frame)

    kf_scale(1, (0.001, 0.001, 0.001))
    kf_scale(PHASE_CALM_END, (0.001, 0.001, 0.001))
    kf_scale(PHASE_CALM_END + 15, (10.0, 4.0, 6.0))
    kf_scale(PHASE_BREACH_BEGIN_END, (20.0, 8.0, 14.0))
    kf_scale(PHASE_MAJOR_RELEASE_END, (26.0, 10.0, 20.0))
    smooth_fcurves(notch)

    return notch


breach_notch = build_breach_visual()
log("Dam breach visual created (grows across the breach phases).")


# ============================================================================
# STEP 6 — RESERVOIR (from real water.json)
# ============================================================================

step("Building reservoir from real water body geometry...")


def polygon_to_mesh(name, exterior_local, interior_rings_local, base_z, extrude_height,
                     material, collection):
    if len(exterior_local) < 3:
        return None
    curve_data = bpy.data.curves.new(name + "_Curve", type='CURVE')
    curve_data.dimensions = '2D'
    curve_data.fill_mode = 'BOTH'
    curve_data.extrude = extrude_height / 2.0 if extrude_height > 0.0 else 0.0

    def add_spline(coords):
        spline = curve_data.splines.new('POLY')
        spline.points.add(len(coords) - 1)
        for i, (x, y) in enumerate(coords):
            spline.points[i].co = (x, y, 0.0, 1.0)
        spline.use_cyclic_u = True

    add_spline(exterior_local)
    for ring in interior_rings_local:
        if len(ring) >= 3:
            add_spline(ring)

    obj = bpy.data.objects.new(name, curve_data)
    bpy.context.scene.collection.objects.link(obj)
    z_center = base_z + (extrude_height / 2.0 if extrude_height > 0.0 else 0.0)
    obj.location = (0, 0, z_center)

    try:
        depsgraph = bpy.context.evaluated_depsgraph_get()
        obj_eval = obj.evaluated_get(depsgraph)
        mesh_from_eval = bpy.data.meshes.new_from_object(obj_eval)
        mesh_obj = bpy.data.objects.new(name, mesh_from_eval)
        mesh_obj.location = obj.location
        bpy.context.scene.collection.objects.link(mesh_obj)
        bpy.data.objects.remove(obj, do_unlink=True)
        bpy.data.curves.remove(curve_data)
        obj = mesh_obj
    except Exception as e:
        log(f"WARNING: curve->mesh conversion failed for {name} ({e}); left as curve.")

    if obj.type == 'MESH' and material is not None:
        obj.data.materials.append(material)

    link_only(obj, collection)
    return obj


def build_reservoir():
    reservoir_feats = [f for f in water_data["features"] if f.get("is_reservoir")]
    if not reservoir_feats:
        log("WARNING: no reservoir polygon identified from real data — reservoir NOT created.")
        return []
    built = []
    reservoir_mat = mat_water("Mat_Reservoir_Water", speed=0.08, wave_scale=6.0,
                              color=(0.03, 0.15, 0.28, 0.92), turbulence=0.12, flow_dir=(0.2, 0.1))
    for i, feat in enumerate(reservoir_feats):
        obj = polygon_to_mesh(f"TEHRI_Reservoir_{i:02d}", feat["exterior_local"], [],
                               base_z=DAM_FRL_Z_LOCAL, extrude_height=0.4,
                               material=reservoir_mat, collection=COL_RESERVOIR)
        if obj:
            built.append(obj)
    log(f"Reservoir built from {len(built)} real polygon(s) at FRL={DAM_FRL_M}m")
    return built


reservoir_objs = build_reservoir()


# ============================================================================
# STEP 7 — WATERWAYS + OTHER WATER
# ============================================================================

step("Building waterways and secondary water bodies...")

waterways_data = load_json("waterways.json")


def make_draped_curve(name, coords_local, width, material, collection, z_offset=0.3):
    if len(coords_local) < 2:
        return None
    curve_data = bpy.data.curves.new(name + "_Curve", type='CURVE')
    curve_data.dimensions = '3D'
    curve_data.resolution_u = 4
    spline = curve_data.splines.new('POLY')
    spline.points.add(len(coords_local) - 1)
    for i, (x, y) in enumerate(coords_local):
        z = terrain_height_local(x, y) + z_offset
        spline.points[i].co = (x, y, z, 1.0)
    curve_data.bevel_depth = width / 2.0
    curve_data.bevel_resolution = 1
    curve_data.fill_mode = 'FULL'
    if material:
        curve_data.materials.append(material)

    obj = bpy.data.objects.new(name, curve_data)
    bpy.context.scene.collection.objects.link(obj)
    link_only(obj, collection)
    return obj


def build_waterways():
    mat = mat_water("Mat_Waterway", speed=0.4, wave_scale=3.0,
                     color=(0.06, 0.24, 0.32, 0.85), turbulence=0.3, flow_dir=(0, -1), roughness=0.15)
    count = 0
    for i, feat in enumerate(waterways_data["features"]):
        obj = make_draped_curve(f"TEHRI_Waterway_{i:04d}", feat["coords_local"], feat["width_m"],
                                 mat, COL_WATERWAYS)
        if obj:
            count += 1
    log(f"Waterways built: {count}")
    return count


def build_other_water():
    mat = mat_water("Mat_Water_Other", speed=0.05, wave_scale=5.0,
                     color=(0.06, 0.22, 0.30, 0.85))
    count = 0
    for i, feat in enumerate(water_data["features"]):
        if feat.get("is_reservoir"):
            continue
        ext = feat["exterior_local"]
        cx = sum(p[0] for p in ext) / len(ext)
        cy = sum(p[1] for p in ext) / len(ext)
        z = terrain_height_local(cx, cy)
        obj = polygon_to_mesh(f"TEHRI_Water_{i:02d}", ext, [], base_z=z, extrude_height=0.2,
                               material=mat, collection=COL_WATERWAYS)
        if obj:
            count += 1
    log(f"Other water polygons built: {count}")
    return count


waterway_count = build_waterways()
other_water_count = build_other_water()


# ============================================================================
# STEP 8 — ROADS
# ============================================================================

step("Building roads from real OSM road geometry...")

roads_data = load_json("roads.json")

ROAD_WIDTH_BY_CLASS = {
    "trunk": 9.0, "secondary": 7.5, "tertiary": 6.5, "unclassified": 5.5,
    "residential": 5.0, "service": 3.5, "track": 3.0, "path": 1.5,
}
DEFAULT_ROAD_WIDTH = 5.0


def build_roads():
    mat = mat_asphalt()
    count = 0
    road_objs = []
    class_counts = {}
    for i, feat in enumerate(roads_data["features"]):
        cls = feat.get("highway_class")
        width = feat.get("width_m") or ROAD_WIDTH_BY_CLASS.get(cls, DEFAULT_ROAD_WIDTH)
        class_counts[cls] = class_counts.get(cls, 0) + 1
        obj = make_draped_curve(f"TEHRI_Road_{i:04d}", feat["coords_local"], width, mat, COL_ROADS,
                                 z_offset=0.15)
        if obj:
            obj["highway_class"] = cls or "unknown"
            road_objs.append((obj, feat))
            count += 1
    log(f"Roads built: {count} (classes: {class_counts})")
    return count, road_objs


road_count, road_objs = build_roads()


# ============================================================================
# STEP 9 — BUILDINGS
# ============================================================================

step("Building real OSM buildings...")

buildings_data = load_json("buildings.json")


def build_buildings():
    material_cache = {}
    count = 0
    building_objs = []
    for i, feat in enumerate(buildings_data["features"]):
        cat = feat["category"]
        if cat not in material_cache:
            material_cache[cat] = mat_building(cat)
        exterior = feat["exterior_local"]
        if len(exterior) < 3:
            continue
        cx = sum(p[0] for p in exterior) / len(exterior)
        cy = sum(p[1] for p in exterior) / len(exterior)
        base_z = terrain_height_local(cx, cy)
        obj = polygon_to_mesh(f"TEHRI_Building_{i:04d}", exterior, feat.get("interior_rings_local", []),
                               base_z=base_z, extrude_height=feat["height_m"],
                               material=material_cache[cat], collection=COL_BUILDINGS)
        if obj:
            obj["height_source"] = feat["height_source"]
            obj["category"] = cat
            building_objs.append((obj, (cx, cy), feat))
            count += 1
    log(f"Buildings built: {count} (of {buildings_data['total_available']} in AOI)")
    return count, building_objs


building_count, building_objs = build_buildings()


# ============================================================================
# STEP 10 — FLOOD CORRIDOR + DOWNSTREAM FLOOD SEGMENTS
# ============================================================================

step("Building downstream flood corridor and progressive flood segments...")

FLOOD_REACH_START_ALONG = 30.0  # meters downstream of dam before flood corridor begins
FLOOD_MAX_ALONG = min(MAX_DOWNSTREAM_DISTANCE * 0.95, DAM_CREST_LENGTH_M * 20.0)
CORRIDOR_BASE_HALF_WIDTH = DAM_CREST_LENGTH_M * 0.20
CORRIDOR_WIDEN_RATE = 0.35  # half-width growth per meter downstream


def corridor_half_width(along):
    if along <= FLOOD_REACH_START_ALONG:
        return CORRIDOR_BASE_HALF_WIDTH
    t = (along - FLOOD_REACH_START_ALONG) / max(1.0, FLOOD_MAX_ALONG - FLOOD_REACH_START_ALONG)
    return CORRIDOR_BASE_HALF_WIDTH + t * CORRIDOR_BASE_HALF_WIDTH * 3.0


N_SEGMENTS = 6
flood_water_mat_base = mat_water("Mat_Flood_Water", speed=0.22, wave_scale=4.0,
                                  color=(0.18, 0.24, 0.24, 0.85), turbulence=0.4, flow_dir=(0, -1))


def build_flood_segments():
    segments = []
    seg_len = (FLOOD_MAX_ALONG - FLOOD_REACH_START_ALONG) / N_SEGMENTS
    for i in range(N_SEGMENTS):
        a0 = FLOOD_REACH_START_ALONG + i * seg_len
        a1 = a0 + seg_len * 1.08
        hw0 = corridor_half_width(a0)
        hw1 = corridor_half_width(a1)

        n_cross = 6
        bm = bmesh.new()
        rows = []
        for j in range(n_cross + 1):
            t = j / n_cross
            a = a0 + (a1 - a0) * t
            hw = hw0 + (hw1 - hw0) * t
            row = []
            for s in (-1, 1):
                x, y = axis_to_local(a, s * hw)
                z = terrain_height_local(x, y) + 0.35
                row.append(bm.verts.new((x, y, z)))
            rows.append(row)
        for j in range(n_cross):
            bm.faces.new((rows[j][0], rows[j][1], rows[j + 1][1], rows[j + 1][0]))
        bm.normal_update()

        mesh = bpy.data.meshes.new(f"TEHRI_Flood_{i+1:02d}_Mesh")
        bm.to_mesh(mesh)
        bm.free()

        obj = bpy.data.objects.new(f"TEHRI_Flood_{i+1:02d}", mesh)
        bpy.context.scene.collection.objects.link(obj)
        obj.data.materials.append(flood_water_mat_base)
        link_only(obj, COL_FLOOD)

        reveal_start = PHASE_MAJOR_RELEASE_END + int(
            (PHASE_DOWNSTREAM_TRAVEL_END - PHASE_MAJOR_RELEASE_END) * (i / max(1, N_SEGMENTS - 1))
        )
        reveal_full = min(reveal_start + 30, PHASE_INFRASTRUCTURE_END)

        obj.scale = (0.001, 0.001, 0.001)
        obj.keyframe_insert(data_path="scale", frame=1)
        obj.keyframe_insert(data_path="scale", frame=max(1, reveal_start - 1))
        obj.scale = (1.0, 1.0, 1.0)
        obj.keyframe_insert(data_path="scale", frame=reveal_full)
        smooth_fcurves(obj)

        segments.append({"obj": obj, "a0": a0, "a1": a1, "reveal_start": reveal_start})

    log(f"Flood segments built: {len(segments)} (downstream reach up to {FLOOD_MAX_ALONG:.0f} m)")
    return segments


flood_segments = build_flood_segments()


def build_breach_torrent():
    outlet_along = 5.0
    ox, oy = axis_to_local(outlet_along, 0.0)
    outlet_loc = (ox, oy, DAM_BASE_Z_LOCAL + DAM_HEIGHT_M * 0.08)

    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=3, radius=1.0, location=outlet_loc)
    torrent = bpy.context.active_object
    torrent.name = "TEHRI_Flood_Torrent"
    torrent.data.materials.append(
        mat_water("Mat_Torrent", speed=1.2, wave_scale=1.6, color=(0.45, 0.5, 0.5, 0.95),
                  turbulence=0.8, flow_dir=(0, -1))
    )

    far_along = FLOOD_REACH_START_ALONG + 40
    fx, fy = axis_to_local(far_along, 0.0)
    far_loc = (fx, fy, terrain_height_local(fx, fy) + 1.0)

    def kscale(frame, s):
        torrent.scale = s
        torrent.keyframe_insert(data_path="scale", frame=frame)

    def kloc(frame, loc):
        torrent.location = loc
        torrent.keyframe_insert(data_path="location", frame=frame)

    kscale(1, (0.001, 0.001, 0.001)); kloc(1, outlet_loc)
    kscale(PHASE_CALM_END, (0.001, 0.001, 0.001)); kloc(PHASE_CALM_END, outlet_loc)
    kscale(PHASE_BREACH_BEGIN_END, (2.5, 2.0, 1.6)); kloc(PHASE_BREACH_BEGIN_END, outlet_loc)
    kscale(PHASE_MAJOR_RELEASE_END, (6.0, 5.0, 3.0)); kloc(PHASE_MAJOR_RELEASE_END, far_loc)
    smooth_fcurves(torrent)
    link_only(torrent, COL_EFFECTS)
    return torrent


breach_torrent = build_breach_torrent()


def build_foam():
    mat = mat_foam()
    points_along = [10.0, FLOOD_REACH_START_ALONG + 20, FLOOD_MAX_ALONG * 0.3, FLOOD_MAX_ALONG * 0.6]
    foam_objs = []
    for i, along in enumerate(points_along):
        x, y = axis_to_local(along, 0.0)
        z = terrain_height_local(x, y) + 0.4
        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=DAM_CREST_LENGTH_M * 0.03,
                                               location=(x, y, z))
        foam = bpy.context.active_object
        foam.name = f"TEHRI_Flood_Foam_{i:02d}"
        foam.scale.z = 0.15
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=False)
        foam.data.materials.append(mat)

        reveal = PHASE_BREACH_BEGIN_END + i * 60
        foam.scale = (0.001, 0.001, 0.001)
        foam.keyframe_insert(data_path="scale", frame=max(1, reveal - 10))
        foam.scale = (1.0, 1.0, 0.15)
        foam.keyframe_insert(data_path="scale", frame=reveal + 15)
        smooth_fcurves(foam)
        link_only(foam, COL_EFFECTS)
        foam_objs.append(foam)
    log(f"Foam patches built: {len(foam_objs)}")
    return foam_objs


foam_objs = build_foam()


def build_splash_particles():
    outlet_along = 5.0
    ox, oy = axis_to_local(outlet_along, 0.0)
    outlet_loc = (ox, oy, DAM_BASE_Z_LOCAL + DAM_HEIGHT_M * 0.1)

    bpy.ops.mesh.primitive_plane_add(size=15.0, location=outlet_loc)
    emitter = bpy.context.active_object
    emitter.name = "TEHRI_Splash_Emitter"
    emitter.hide_render = True
    link_only(emitter, COL_EFFECTS)

    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=1, radius=0.4)
    droplet = bpy.context.active_object
    droplet.name = "TEHRI_Splash_Droplet"
    droplet.data.materials.append(mat_foam())
    droplet.hide_render = True
    droplet.hide_viewport = True
    link_only(droplet, COL_EFFECTS)

    try:
        emitter.modifiers.new("Splash", type='PARTICLE_SYSTEM')
        psys = emitter.particle_systems[0]
        settings = psys.settings
        settings.count = 500
        settings.frame_start = PHASE_BREACH_BEGIN_END
        settings.frame_end = PHASE_MAJOR_RELEASE_END
        settings.lifetime = 50
        settings.emit_from = 'FACE'
        settings.physics_type = 'NEWTON'
        settings.normal_factor = 3.0
        settings.factor_random = 2.0
        settings.render_type = 'OBJECT'
        settings.instance_object = droplet
        settings.particle_size = 0.5
        settings.size_random = 0.6
        settings.effector_weights.gravity = 1.0
        log("Splash particle system created.")
    except Exception as e:
        log(f"WARNING: particle system setup failed ({e}); continuing without it.")

    return emitter


splash_emitter = build_splash_particles()


# ============================================================================
# STEP 11 — FLOOD IMPACT ON BUILDINGS + ROADS (visual, from real positions)
# ============================================================================

step("Computing flood impact on real buildings and roads...")


def along_to_frame(along):
    t = max(0.0, min(1.0, (along - FLOOD_REACH_START_ALONG) / max(1.0, FLOOD_MAX_ALONG - FLOOD_REACH_START_ALONG)))
    return int(PHASE_DOWNSTREAM_TRAVEL_END + t * (PHASE_INFRASTRUCTURE_END - PHASE_DOWNSTREAM_TRAVEL_END))


def build_building_impact():
    impacted_mat = mat_water("Mat_Flood_Building_Impact", speed=0.05, wave_scale=3.0,
                              color=(0.20, 0.26, 0.26, 0.8))
    count = 0
    for obj, (cx, cy), feat in building_objs:
        along, across = local_to_axis(cx, cy)
        if along <= 0:
            continue
        hw = corridor_half_width(along)
        if abs(across) > hw:
            continue

        reveal_frame = max(along_to_frame(along), PHASE_MAJOR_RELEASE_END + 10)
        exterior = feat["exterior_local"]
        pad_exterior = []
        for (px, py) in exterior:
            dx, dy = px - cx, py - cy
            pad_exterior.append((cx + dx * 1.4, cy + dy * 1.4))

        base_z = terrain_height_local(cx, cy)
        puddle = polygon_to_mesh(f"{obj.name}_FloodPuddle", pad_exterior, [],
                                  base_z=base_z, extrude_height=0.5,
                                  material=impacted_mat, collection=COL_FLOOD)
        if puddle is None:
            continue

        puddle.scale = (0.001, 0.001, 0.001)
        puddle.keyframe_insert(data_path="scale", frame=max(1, reveal_frame - 10))
        puddle.scale = (1.0, 1.0, 1.0)
        puddle.keyframe_insert(data_path="scale", frame=reveal_frame + 20)
        smooth_fcurves(puddle)
        puddle["impact_reveal_frame"] = reveal_frame
        count += 1
    log(f"Buildings visually impacted by flood corridor: {count} of {building_count}")
    return count


def build_road_impact():
    impacted_mat = mat_water("Mat_Flood_Road_Impact", speed=0.1, wave_scale=3.0,
                              color=(0.18, 0.24, 0.24, 0.75))
    count = 0
    for obj, feat in road_objs:
        coords = feat["coords_local"]
        impacted_points = []
        min_along_impacted = None
        for (x, y) in coords:
            along, across = local_to_axis(x, y)
            if along > 0 and abs(across) <= corridor_half_width(along):
                impacted_points.append((x, y))
                if min_along_impacted is None or along < min_along_impacted:
                    min_along_impacted = along
        if len(impacted_points) < 2 or min_along_impacted is None:
            continue

        reveal_frame = max(along_to_frame(min_along_impacted), PHASE_MAJOR_RELEASE_END + 10)
        strip = make_draped_curve(f"{obj.name}_FloodStrip", impacted_points,
                                   feat.get("width_m", DEFAULT_ROAD_WIDTH) * 1.3,
                                   impacted_mat, COL_FLOOD, z_offset=0.25)
        if strip is None:
            continue

        strip.scale = (0.001, 0.001, 0.001)
        strip.keyframe_insert(data_path="scale", frame=max(1, reveal_frame - 10))
        strip.scale = (1.0, 1.0, 1.0)
        strip.keyframe_insert(data_path="scale", frame=reveal_frame + 15)
        smooth_fcurves(strip)
        strip["impact_reveal_frame"] = reveal_frame
        count += 1
    log(f"Roads visually impacted by flood corridor: {count} of {road_count}")
    return count


buildings_impacted = build_building_impact()
roads_impacted = build_road_impact()


# ============================================================================
# STEP 12 — (folded into step 10/11 above: foam/splash already built)
# ============================================================================

step("Foam and splash effects finalized.")
log(f"Foam patches: {len(foam_objs)}, splash emitter: {splash_emitter.name}")


# ============================================================================
# STEP 13 — LIGHTING
# ============================================================================

step("Setting up lighting...")


def build_lighting():
    span = max(X_COORDS[-1] - X_COORDS[0], Y_COORDS[-1] - Y_COORDS[0])

    sun_data = bpy.data.lights.new("TEHRI_Sun", type='SUN')
    sun_data.energy = 3.0
    sun_data.angle = math.radians(1.0)
    sun = bpy.data.objects.new("TEHRI_Sun", sun_data)
    sun.location = (0, 0, DAM_HEIGHT_M * 5)
    sun.rotation_euler = (math.radians(55), 0, math.radians(35))
    bpy.context.scene.collection.objects.link(sun)
    link_only(sun, COL_LIGHTING)

    world = bpy.context.scene.world or bpy.data.worlds.new("World")
    bpy.context.scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs[0].default_value = (0.6, 0.68, 0.8, 1.0)
        bg.inputs[1].default_value = 1.0
    world.mist_settings.start = span * 0.05
    world.mist_settings.depth = span * 0.6

    fill_data = bpy.data.lights.new("TEHRI_Fill", type='AREA')
    fill_data.energy = 5000
    fill_data.size = span * 0.3
    fill = bpy.data.objects.new("TEHRI_Fill", fill_data)
    fill.location = (-span * 0.2, span * 0.2, DAM_HEIGHT_M * 3)
    fill.rotation_euler = (math.radians(-40), 0, math.radians(-20))
    bpy.context.scene.collection.objects.link(fill)
    link_only(fill, COL_LIGHTING)

    log("Lighting created (sun + area fill + world background/mist).")


build_lighting()


# ============================================================================
# STEP 14 — CAMERAS + ANIMATION (native camera-switch markers)
# ============================================================================

step("Setting up cameras and camera animation...")


def build_cameras():
    span = max(X_COORDS[-1] - X_COORDS[0], Y_COORDS[-1] - Y_COORDS[0])

    def make_cam(name, loc, target):
        cam_data = bpy.data.cameras.new(name)
        cam_data.lens = 32
        cam_obj = bpy.data.objects.new(name, cam_data)
        cam_obj.location = loc
        bpy.context.scene.collection.objects.link(cam_obj)
        point_at(cam_obj, target)
        link_only(cam_obj, COL_CAMERAS)
        return cam_obj

    dam_top = (0, 0, DAM_CREST_Z_LOCAL)
    breach_pt_x, breach_pt_y = axis_to_local(0, 0)
    downstream_far_x, downstream_far_y = axis_to_local(FLOOD_MAX_ALONG * 0.5, 0)
    downstream_end_x, downstream_end_y = axis_to_local(FLOOD_MAX_ALONG * 0.85, 0)

    cam1 = make_cam("CAMERA_01_Aerial_Overview",
                     (span * 0.3, -span * 0.3, DAM_HEIGHT_M * 4.0),
                     (0, 0, DAM_CREST_Z_LOCAL * 0.5))
    cam2 = make_cam("CAMERA_02_Dam_CloseUp",
                     axis_to_local(-DAM_HEIGHT_M * 1.5, 0) + (DAM_CREST_Z_LOCAL * 0.7,),
                     dam_top)
    cam3 = make_cam("CAMERA_03_Breach",
                     axis_to_local(-DAM_HEIGHT_M * 0.6, DAM_CREST_LENGTH_M * 0.15) +
                     (DAM_CREST_Z_LOCAL * 0.35,),
                     (breach_pt_x, breach_pt_y, DAM_BASE_Z_LOCAL + DAM_HEIGHT_M * 0.1))
    cam4 = make_cam("CAMERA_04_Follow_Downstream",
                     axis_to_local(FLOOD_MAX_ALONG * 0.35, DAM_CREST_LENGTH_M * 0.9) +
                     (DAM_HEIGHT_M * 1.2,),
                     (downstream_far_x, downstream_far_y,
                      terrain_height_local(downstream_far_x, downstream_far_y)))
    cam5 = make_cam("CAMERA_05_Infrastructure_Aerial",
                     axis_to_local(FLOOD_MAX_ALONG * 0.6, 0) + (DAM_HEIGHT_M * 2.5,),
                     (downstream_end_x, downstream_end_y,
                      terrain_height_local(downstream_end_x, downstream_end_y)))
    cam6 = make_cam("CAMERA_06_Final_Wide",
                     (0, 0, DAM_HEIGHT_M * 6.0),
                     axis_to_local(FLOOD_MAX_ALONG * 0.5, 0) + (0,))

    cams_in_order = [
        (cam1, 1, PHASE_CALM_END),
        (cam2, PHASE_CALM_END, PHASE_CALM_END + 15),
        (cam3, PHASE_CALM_END + 16, PHASE_MAJOR_RELEASE_END),
        (cam4, PHASE_MAJOR_RELEASE_END + 1, PHASE_DOWNSTREAM_TRAVEL_END),
        (cam5, PHASE_DOWNSTREAM_TRAVEL_END + 1, PHASE_INFRASTRUCTURE_END),
        (cam6, PHASE_INFRASTRUCTURE_END + 1, PHASE_FINAL_END),
    ]

    scene = bpy.context.scene
    for cam_obj, frame_in, frame_out in cams_in_order:
        marker = scene.timeline_markers.new(f"Cut_{cam_obj.name}", frame=frame_in)
        marker.camera = cam_obj

        start_loc = Vector(cam_obj.location)
        end_loc = start_loc + Vector((0, 0, -DAM_HEIGHT_M * 0.05))
        cam_obj.location = start_loc
        cam_obj.keyframe_insert(data_path="location", frame=frame_in)
        cam_obj.location = end_loc
        cam_obj.keyframe_insert(data_path="location", frame=frame_out)
        smooth_fcurves(cam_obj)

    scene.camera = cam1
    log(f"Cameras created: {len(cams_in_order)}, bound to timeline markers for automatic switching.")
    return [c for c, _, _ in cams_in_order]


cameras = build_cameras()


# ============================================================================
# STEP 15 — SCENE METADATA, FRAME RANGE, RENDER SETTINGS
# ============================================================================

step("Applying scene metadata and configuring render settings...")

scene_metadata = load_json("scene_metadata.json")


def apply_scene_metadata():
    scene = bpy.context.scene
    for k, v in scene_metadata.items():
        try:
            scene[f"tehri_{k}"] = json.dumps(v) if isinstance(v, (dict, list)) else v
        except Exception as e:
            log(f"WARNING: could not set scene property {k}: {e}")
    scene["tehri_disclaimer"] = (
        "Real DEM terrain and real OSM building/road/water geometry. Dam "
        "reconstructed using THDC published reference dimensions "
        "(visualization, not survey-grade). Dam-break flood is a visual "
        "approximation, NOT a validated hydraulic/engineering simulation."
    )
    scene["tehri_flood_downstream_direction"] = f"({downstream_hat.x:.4f}, {downstream_hat.y:.4f})"
    scene["tehri_flood_orientation_method"] = orientation_method


apply_scene_metadata()


def configure_render():
    scene = bpy.context.scene
    scene.frame_start = FRAME_START
    scene.frame_end = FRAME_END
    scene.render.fps = FPS
    for engine_id in ('BLENDER_EEVEE_NEXT', 'BLENDER_EEVEE'):
        try:
            scene.render.engine = engine_id
            break
        except TypeError:
            continue
    scene.render.resolution_x = 1920
    scene.render.resolution_y = 1080
    scene.render.resolution_percentage = 100
    if hasattr(scene, "eevee"):
        for attr, val in (("use_ssr", True), ("use_bloom", True), ("taa_render_samples", 32)):
            if hasattr(scene.eevee, attr):
                setattr(scene.eevee, attr, val)


configure_render()
log(f"Render engine: {bpy.context.scene.render.engine}, frames {FRAME_START}-{FRAME_END} @ {FPS}fps")


def validate_scene():
    checks = {
        "Terrain exists with vertices": len(terrain_obj.data.vertices) > 0,
        "Terrain has real elevation range": (MAX_ELEV - MIN_ELEV) > 1.0,
        "Dam mesh has geometry": len(dam_obj.data.vertices) > 0,
        "Reservoir created from real geometry": len(reservoir_objs) > 0,
        "Roads created": road_count > 0,
        "Buildings created": building_count > 0,
        "Flood segments created": len(flood_segments) > 0,
        "Cameras created": len(COL_CAMERAS.objects) > 0,
        "Lighting created": len(COL_LIGHTING.objects) > 0,
        "Breach animation keyframed": (breach_notch.animation_data is not None),
    }
    log("-" * 60)
    log("VALIDATION")
    for k, v in checks.items():
        log(f"  [{'OK' if v else 'FAIL'}] {k}")
    log("-" * 60)


validate_scene()


# ============================================================================
# STEP 16 — SAVE BLEND + RENDER PREVIEW
# ============================================================================

step("Saving .blend and rendering preview...")

bpy.context.scene.frame_set(60)  # calm reservoir / intact dam — establishing shot
bpy.context.scene.camera = cameras[0]

bpy.ops.wm.save_as_mainfile(filepath=str(OUTPUT_BLEND))
log(f"Blend saved: {OUTPUT_BLEND}")

try:
    bpy.context.scene.render.filepath = str(OUTPUT_PREVIEW)
    bpy.ops.render.render(write_still=True)
    log(f"Preview rendered: {OUTPUT_PREVIEW}")
except Exception as e:
    log(f"WARNING: preview render failed ({e}). The .blend file was still saved successfully.")

print("=" * 60)
print("TEHRI BLENDER SCENE COMPLETE")
print("")
print("BLEND:")
print(f"{OUTPUT_BLEND}")
print("")
print("PREVIEW:")
print(f"{OUTPUT_PREVIEW}")
print("")
print("FRAMES:")
print(f"{FRAME_START}-{FRAME_END}")
print("")
print("FPS:")
print(f"{FPS}")
print("=" * 60)