"""
============================================================================
 METTUR DAM  -  Procedural environment + REAL Mantaflow liquid simulation
============================================================================
One self-contained Blender 4.x script.

    Blender  ->  Scripting  ->  New  ->  paste  ->  Run Script

It builds a curved, modular concrete spillway dam, a calm reservoir, rocky
downstream terrain, cube houses, roads, rocks and vegetation, and sets up a
FLIP liquid Mantaflow simulation whose water is emitted upstream of the OPEN
spillway gates, pours through the openings, races down the chute and turns
turbulent (with foam / spray / bubbles) in the stilling basin below.

The primary water is a baked Mantaflow simulation - NOT scrolling textures,
alpha planes, deformed meshes or particle-only fakes.

Baking is left to the user by default (AUTO_BAKE = False) so the script always
finishes; clear bake instructions are printed at the end.
============================================================================
"""

import bpy
import bmesh
import math
import random
import os
from mathutils import Vector, Euler, Matrix, noise

# ===========================================================================
#  1. USER CONFIGURATION  (edit these - everything scales from here)
# ===========================================================================

# ---- Workflow toggles ------------------------------------------------------
DEBUG_MODE            = False   # True  -> lighter scene, low sim res, proxies visible
AUTO_BAKE             = False   # True  -> attempt to bake the fluid from Python
ENABLE_CAMERA_ANIMATION = True  # cinematic fly-through on the active camera
SEED                  = 20260928

# ---- Scale (real-world metres) --------------------------------------------
DAM_LENGTH        = 600.0       # crest length along the arc
DAM_HEIGHT        = 60.0        # foundation -> crest road
DAM_WIDTH         = 35.0        # upstream/downstream thickness of the body
RESERVOIR_SIZE    = 1000.0      # reservoir reach behind the dam
DOWNSTREAM_LENGTH = 900.0       # downstream valley reach
ENV_WIDTH         = 1500.0      # terrain extent along X
ENV_DEPTH         = 1900.0      # terrain extent along Y

# ---- Elevations (metres, Z up).  Downstream is -Y, reservoir is +Y --------
FOUNDATION_Z    = 0.0           # base of the dam / valley floor at the toe
GATE_SILL_Z     = 30.0          # bottom of each spillway opening (weir sill)
SPILLWAY_CREST_Z= 42.0          # top of the ogee weir / start of the chute
RESERVOIR_LEVEL = 46.0          # calm reservoir water surface
CREST_ROAD_Z    = DAM_HEIGHT    # crest bridge / road deck
TOE_Z           = 3.0           # stilling-basin floor just below the chute
RIVER_END_Z     = -22.0         # riverbed elevation at the far downstream edge

# ---- Dam / gate layout -----------------------------------------------------
N_GATES         = 16            # number of spillway bays / gates
ARC_ANGLE_DEG   = 34.0          # total sweep of the curved crest (subtle arch)
# Which gates are OPEN.  Mantaflow inflow is created only for these bays, so
# discharge always matches the open spillways.  Change freely.
OPEN_GATE_INDICES = [2, 3, 6, 7, 8, 11, 12]
# Optional per-gate open fraction (0..1).  Missing entries default to 1.0.
GATE_OPEN_FRACTIONS = {2: 1.0, 3: 0.8, 6: 0.6, 7: 1.0, 8: 1.0, 11: 0.5, 12: 1.0}

# ---- Reservoir / flow controls --------------------------------------------
RESERVOIR_WATER_LEVEL = RESERVOIR_LEVEL   # alias used by the sim setup
GATE_OPEN_AMOUNT      = 1.0     # global multiplier on every gate opening angle
INFLOW_RATE           = 12.0    # m/s initial downstream speed of emitted water
FLOW_DURATION         = 999     # frames the inflow keeps emitting (>= cache end = always)

# ---- Mantaflow simulation --------------------------------------------------
DOMAIN_RESOLUTION = 128         # voxels on the longest domain axis.
                                # 80 = draft | 128 = balanced | 192/256 = final.
SIMULATION_RESOLUTION = DOMAIN_RESOLUTION   # alias
CACHE_FRAME_START = 1
CACHE_FRAME_END   = 220         # long enough for the surge to flood the near town
MAX_TIME_STEP     = 6           # domain timesteps_max (higher = more stable / slower)
ENABLE_WHITEWATER = True        # foam / spray / bubbles at high-energy zones
USE_ADAPTIVE_DOMAIN = True      # grid tracks the fluid -> big optimisation on a
                                # domain this large (empty valley cells cost nothing)
# 'REPLAY' simulates on timeline playback (like real_water.py: just press Space).
# 'MODULAR'/'ALL' require Physics > Bake All, but are needed to bake whitewater.
SIM_CACHE_TYPE    = 'REPLAY'
FPS               = 24


# ---- Output ----------------------------------------------------------------
OUTPUT_FILE = "//mettur_dam_mantaflow.blend"
RENDER_RES_X, RENDER_RES_Y = 1920, 1080

# ---- Downstream town (grid of streets / houses / buildings) ----------------
# Sits on the low flood plain just below the stilling basin so the spillway
# discharge floods its streets.  Sizes are proportionate to the 600 m dam.
ENABLE_TOWN        = True
TOWN_NEAR_Y        = -225.0     # town edge nearest the dam (just past the basin)
TOWN_FAR_Y         = -560.0     # far edge of the built-up area
TOWN_HALF_WIDTH    = 235.0      # half of the town's X extent
TOWN_BLOCK         = 58.0       # block pitch (building plot + half a street)
TOWN_STREET_W      = 13.0       # street width between blocks (metres)
TOWN_CORE_RADIUS   = 130.0      # within this radius of town centre -> tall buildings
TOWN_FLOOD_ZONE    = True       # town buildings become Mantaflow collision effectors
# building height bands (metres) - kept well under the 60 m dam so scale reads
HOUSE_H_RANGE      = (5.0, 8.0)
MIDRISE_H_RANGE    = (12.0, 24.0)
TOWER_H_RANGE      = (26.0, 44.0)


# ---- DEBUG_MODE overrides (kept practical for troubleshooting the sim) -----
if DEBUG_MODE:
    N_GATES           = 6
    OPEN_GATE_INDICES = [1, 2, 4]
    GATE_OPEN_FRACTIONS = {1: 1.0, 2: 0.6, 4: 1.0}
    DOMAIN_RESOLUTION = 56
    SIMULATION_RESOLUTION = 56
    CACHE_FRAME_END   = 110
    TOWN_FAR_Y        = -430.0
    TOWN_HALF_WIDTH   = 170.0

random.seed(SEED)

# Collection name -> Collection ; Material name -> Material (filled at runtime)
COLLS = {}
MATS  = {}

# ===========================================================================
#  2. LOW-LEVEL HELPERS  (version-safe wrappers)
# ===========================================================================

def log(msg):
    print("[METTUR] " + str(msg))


def set_enum_safe(owner, prop, candidates):
    """Set an enum property to the first candidate its RNA actually supports."""
    try:
        valid = owner.bl_rna.properties[prop].enum_items.keys()
    except Exception:
        valid = []
    for c in candidates:
        if valid and c not in valid:
            continue
        try:
            setattr(owner, prop, c)
            return c
        except Exception:
            continue
    return None


def set_attr_safe(owner, prop, value):
    """Set a property only if it exists on this Blender version."""
    if hasattr(owner, prop):
        try:
            setattr(owner, prop, value)
            return True
        except Exception as e:
            log("  (skip %s = %r : %s)" % (prop, value, e))
    return False


def set_socket(node, names, value):
    """Set the first matching input socket (handles renamed 4.x sockets)."""
    if isinstance(names, str):
        names = [names]
    for n in names:
        if n in node.inputs:
            try:
                node.inputs[n].default_value = value
                return True
            except Exception:
                pass
    return False

def get_collection(name, parent=None):
    """Create (once) a collection and link it under parent (scene root default)."""
    coll = bpy.data.collections.get(name)
    if coll is None:
        coll = bpy.data.collections.new(name)
    parent = parent or bpy.context.scene.collection
    if coll.name not in parent.children:
        try:
            parent.children.link(coll)
        except Exception:
            pass
    return coll


def link_object(obj, coll):
    coll.objects.link(obj)
    return obj


def set_principled(bsdf, base_color=None, metallic=None, roughness=None, ior=None,
                   transmission=None, specular=None, alpha=None,
                   emission_color=None, emission_strength=None):
    """Set Principled BSDF inputs using both legacy and Blender 4.x socket names."""
    if base_color is not None:
        set_socket(bsdf, "Base Color", base_color)
    if metallic is not None:
        set_socket(bsdf, "Metallic", metallic)
    if roughness is not None:
        set_socket(bsdf, "Roughness", roughness)
    if ior is not None:
        set_socket(bsdf, "IOR", ior)
    if transmission is not None:
        set_socket(bsdf, ["Transmission Weight", "Transmission"], transmission)
    if specular is not None:
        set_socket(bsdf, ["Specular IOR Level", "Specular"], specular)
    if alpha is not None:
        set_socket(bsdf, "Alpha", alpha)
    if emission_color is not None:
        set_socket(bsdf, ["Emission Color", "Emission"], emission_color)
    if emission_strength is not None:
        set_socket(bsdf, "Emission Strength", emission_strength)


def new_material(name):
    mat = bpy.data.materials.get(name)
    if mat is None:
        mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    mat.node_tree.nodes.clear()
    return mat

def assign_material(obj, mat):
    if mat is None:
        return
    if obj.data and hasattr(obj.data, "materials"):
        obj.data.materials.clear()
        obj.data.materials.append(mat)


def add_bevel(obj, width=0.3, segments=2, angle_deg=40.0):
    """Non-destructive bevel so concrete/steel edges are not razor-sharp CG edges."""
    m = obj.modifiers.new("Bevel", 'BEVEL')
    m.width = width
    m.segments = segments
    m.limit_method = 'ANGLE'
    m.angle_limit = math.radians(angle_deg)
    return m


def box_mesh(name, sx, sy, sz):
    """Cuboid mesh datablock of full dimensions (sx, sy, sz), centred on origin."""
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=(sx, sy, sz), verts=bm.verts)
    bm.to_mesh(me)
    bm.free()
    return me


def add_box(name, sx, sy, sz, coll, location=(0, 0, 0), rotation=(0, 0, 0), mat=None):
    obj = bpy.data.objects.new(name, box_mesh(name, sx, sy, sz))
    obj.location = location
    obj.rotation_euler = rotation
    link_object(obj, coll)
    if mat:
        assign_material(obj, mat)
    return obj


def add_empty(name, location=(0, 0, 0), rotation=(0, 0, 0), coll=None, size=4.0):
    e = bpy.data.objects.new(name, None)
    e.empty_display_type = 'ARROWS'
    e.empty_display_size = size
    e.location = location
    e.rotation_euler = rotation
    if coll:
        link_object(e, coll)
    return e

def fbm(x, y, z=0.0, octaves=5, lacunarity=2.0, gain=0.5, scale=1.0):
    """Fractal Perlin noise in [-1, 1]-ish, built from mathutils.noise.noise."""
    total = 0.0
    amp = 1.0
    freq = scale
    norm = 0.0
    for _ in range(octaves):
        total += amp * noise.noise(Vector((x * freq, y * freq, z * freq)))
        norm += amp
        amp *= gain
        freq *= lacunarity
    return total / norm if norm else 0.0


def mesh_from_pydata(name, verts, faces, coll, mat=None, smooth=False):
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.update()
    if smooth:
        for p in me.polygons:
            p.use_smooth = True
    obj = bpy.data.objects.new(name, me)
    link_object(obj, coll)
    if mat:
        assign_material(obj, mat)
    return obj


def make_rock(name, radius, coll, subdiv=2, jag=0.35, seed=0, mat=None):
    """An irregular faceted boulder from a displaced icosphere (never symmetrical)."""
    rng = random.Random(seed)
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=subdiv, radius=radius)
    for v in bm.verts:
        n = fbm(v.co.x + seed, v.co.y - seed, v.co.z, octaves=3, scale=0.9)
        f = 1.0 + jag * n + rng.uniform(-0.12, 0.12) * jag
        v.co *= f
    bmesh.ops.scale(bm, vec=(rng.uniform(0.8, 1.3), rng.uniform(0.8, 1.3),
                             rng.uniform(0.6, 1.0)), verts=bm.verts)
    bm.to_mesh(me)
    bm.free()
    for p in me.polygons:      # flat shading -> faceted rock look
        p.use_smooth = False
    obj = bpy.data.objects.new(name, me)
    link_object(obj, coll)
    if mat:
        assign_material(obj, mat)
    return obj

def add_cylinder(name, radius, depth, coll, location=(0, 0, 0), rotation=(0, 0, 0),
                 segments=12, mat=None):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=segments,
                          radius1=radius, radius2=radius, depth=depth)
    bm.to_mesh(me)
    bm.free()
    obj = bpy.data.objects.new(name, me)
    obj.location = location
    obj.rotation_euler = rotation
    link_object(obj, coll)
    if mat:
        assign_material(obj, mat)
    return obj


def add_cone(name, r_bottom, r_top, depth, coll, location=(0, 0, 0), segments=8, mat=None):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=True, segments=segments,
                          radius1=r_bottom, radius2=r_top, depth=depth)
    bm.to_mesh(me)
    bm.free()
    obj = bpy.data.objects.new(name, me)
    obj.location = location
    link_object(obj, coll)
    if mat:
        assign_material(obj, mat)
    return obj


# --- Fluid modifier wrappers -----------------------------------------------

def make_fluid_domain(obj):
    m = obj.modifiers.new("Fluid", 'FLUID')
    m.fluid_type = 'DOMAIN'
    return m.domain_settings


def make_fluid_flow(obj, behavior='INFLOW'):
    m = obj.modifiers.new("Fluid", 'FLUID')
    m.fluid_type = 'FLOW'
    fs = m.flow_settings
    set_enum_safe(fs, "flow_type", ['LIQUID'])
    set_enum_safe(fs, "flow_behavior", [behavior])
    return fs


def make_fluid_effector(obj, surface_distance=0.5):
    m = obj.modifiers.new("Fluid", 'FLUID')
    m.fluid_type = 'EFFECTOR'
    es = m.effector_settings
    set_enum_safe(es, "effector_type", ['COLLISION'])
    set_attr_safe(es, "surface_distance", surface_distance)
    set_attr_safe(es, "use_effector", True)
    return es

# ===========================================================================
#  3. DAM ARC GEOMETRY  (shared by dam, gates, inflow and collision proxy)
# ===========================================================================

def compute_bays():
    """Return one dict per spillway bay positioned along a subtle upstream arch.

    Local bay frame: +X = along crest, +Y = upstream (toward reservoir), +Z = up.
    The bay is placed at 'pos' and rotated by 'rot_z' about world Z so its local
    +Y points radially outward (upstream)."""
    span = math.radians(ARC_ANGLE_DEG)
    R = DAM_LENGTH / span                 # arc radius so arc length == DAM_LENGTH
    bay_w = DAM_LENGTH / N_GATES
    bays = []
    for i in range(N_GATES):
        t = -span / 2.0 + (i + 0.5) * (span / N_GATES)
        pos = Vector((R * math.sin(t), R * (math.cos(t) - 1.0), 0.0))
        rot_z = -t
        is_open = i in OPEN_GATE_INDICES
        frac = GATE_OPEN_FRACTIONS.get(i, 1.0) if is_open else 0.0
        bays.append({
            "i": i, "pos": pos, "rot_z": rot_z,
            "bay_w": bay_w, "open": is_open, "frac": frac,
        })
    return bays


def bay_to_world(bay, local):
    """Transform a local (x, y, z) offset in a bay's frame to a world Vector."""
    lx, ly, lz = local
    c, s = math.cos(bay["rot_z"]), math.sin(bay["rot_z"])
    wx = c * lx - s * ly
    wy = s * lx + c * ly
    return bay["pos"] + Vector((wx, wy, lz))


def open_bays_bounds(bays, pad=25.0):
    """World XY bounding region of the OPEN bays (used to size the sim domain)."""
    pts = [b["pos"] for b in bays if b["open"]] or [b["pos"] for b in bays]
    xs = [p.x for p in pts]
    ys = [p.y for p in pts]
    return (min(xs) - pad, max(xs) + pad, min(ys) - pad, max(ys) + pad)

# ===========================================================================
#  4. SCENE SETUP  /  COLLECTIONS
# ===========================================================================

def clear_scene():
    """Remove all objects and data-blocks so the script is idempotent."""
    for obj in list(bpy.data.objects):
        try:
            bpy.data.objects.remove(obj, do_unlink=True)
        except Exception:
            pass
    for coll in list(bpy.data.collections):
        try:
            bpy.data.collections.remove(coll)
        except Exception:
            pass
    for lib in (bpy.data.meshes, bpy.data.materials, bpy.data.curves,
                bpy.data.cameras, bpy.data.lights, bpy.data.textures,
                bpy.data.node_groups, bpy.data.particles):
        for block in list(lib):
            if block.users == 0:
                try:
                    lib.remove(block)
                except Exception:
                    pass
    log("Scene cleared.")


def create_collections():
    names = ["00_ENVIRONMENT", "01_TERRAIN", "02_DAM", "03_GATES", "04_WATER",
             "05_ROCKS", "06_HOUSES", "07_VEGETATION", "08_ROADS",
             "09_LIGHTING", "10_CAMERAS", "11_TOWN"]
    for n in names:
        COLLS[n] = get_collection(n)
    log("Collections created.")


def setup_scene():
    scene = bpy.context.scene
    scene.unit_settings.system = 'METRIC'
    scene.unit_settings.scale_length = 1.0
    scene.frame_start = CACHE_FRAME_START
    scene.frame_end = CACHE_FRAME_END
    scene.render.fps = FPS
    scene.use_gravity = True
    scene.gravity = (0.0, 0.0, -9.81)
    scene.cursor.location = (0.0, 0.0, 0.0)
    log("Scene units = METRIC, frames %d-%d." % (CACHE_FRAME_START, CACHE_FRAME_END))

# ===========================================================================
#  5. PROCEDURAL MATERIALS  (shader nodes only - no image textures)
# ===========================================================================

def _flat_material(name, color, roughness=0.8, metallic=0.0):
    mat = new_material(name)
    nt = mat.node_tree
    out = nt.nodes.new('ShaderNodeOutputMaterial')
    out.location = (300, 0)
    bsdf = nt.nodes.new('ShaderNodeBsdfPrincipled')
    set_principled(bsdf, base_color=color, roughness=roughness, metallic=metallic)
    nt.links.new(bsdf.outputs[0], out.inputs['Surface'])
    return mat


def _concrete_material(name):
    if DEBUG_MODE:
        return _flat_material(name, (0.55, 0.55, 0.53, 1.0), roughness=0.85)
    mat = new_material(name)
    nt = mat.node_tree
    N = nt.nodes.new
    L = nt.links.new
    out = N('ShaderNodeOutputMaterial'); out.location = (600, 0)
    bsdf = N('ShaderNodeBsdfPrincipled'); bsdf.location = (350, 0)
    set_principled(bsdf, metallic=0.0, specular=0.15)
    tc = N('ShaderNodeTexCoord'); tc.location = (-900, 0)
    # broad tonal variation of the concrete
    n1 = N('ShaderNodeTexNoise'); n1.location = (-700, 200)
    n1.inputs['Scale'].default_value = 3.5
    n1.inputs['Detail'].default_value = 6.0
    ramp1 = N('ShaderNodeValToRGB'); ramp1.location = (-480, 220)
    ramp1.color_ramp.elements[0].color = (0.38, 0.38, 0.37, 1)
    ramp1.color_ramp.elements[1].color = (0.62, 0.61, 0.58, 1)
    L(tc.outputs['Object'], n1.inputs['Vector'])
    L(n1.outputs['Fac'], ramp1.inputs['Fac'])
    # dark vertical water stains (stretched noise) multiplied on top
    map_s = N('ShaderNodeMapping'); map_s.location = (-700, -160)
    map_s.inputs['Scale'].default_value = (1.0, 1.0, 0.18)
    n2 = N('ShaderNodeTexNoise'); n2.location = (-480, -160)
    n2.inputs['Scale'].default_value = 8.0
    n2.inputs['Detail'].default_value = 8.0
    ramp2 = N('ShaderNodeValToRGB'); ramp2.location = (-260, -160)
    ramp2.color_ramp.elements[0].color = (0.15, 0.14, 0.12, 1)
    ramp2.color_ramp.elements[1].color = (1, 1, 1, 1)
    ramp2.color_ramp.elements[0].position = 0.35
    ramp2.color_ramp.elements[1].position = 0.7
    L(tc.outputs['Object'], map_s.inputs['Vector'])
    L(map_s.outputs['Vector'], n2.inputs['Vector'])
    L(n2.outputs['Fac'], ramp2.inputs['Fac'])
    # ===__CONCRETE_TAIL__===
    mix_stain = N('ShaderNodeMixRGB'); mix_stain.location = (-40, 100)
    mix_stain.blend_type = 'MULTIPLY'
    mix_stain.inputs['Fac'].default_value = 0.7
    L(ramp1.outputs['Color'], mix_stain.inputs['Color1'])
    L(ramp2.outputs['Color'], mix_stain.inputs['Color2'])
    # patchy green moss in low/damp zones
    n3 = N('ShaderNodeTexNoise'); n3.location = (-260, 360)
    n3.inputs['Scale'].default_value = 5.0
    ramp3 = N('ShaderNodeValToRGB'); ramp3.location = (-40, 360)
    ramp3.color_ramp.elements[0].position = 0.55
    ramp3.color_ramp.elements[1].position = 0.75
    ramp3.color_ramp.elements[0].color = (0, 0, 0, 1)
    ramp3.color_ramp.elements[1].color = (1, 1, 1, 1)
    L(tc.outputs['Object'], n3.inputs['Vector'])
    L(n3.outputs['Fac'], ramp3.inputs['Fac'])
    moss = N('ShaderNodeMixRGB'); moss.location = (180, 200)
    moss.blend_type = 'MIX'
    moss.inputs['Color2'].default_value = (0.12, 0.20, 0.09, 1)
    L(mix_stain.outputs['Color'], moss.inputs['Color1'])
    L(ramp3.outputs['Color'], moss.inputs['Fac'])
    L(moss.outputs['Color'], bsdf.inputs['Base Color'])
    # roughness + bump micro detail
    rramp = N('ShaderNodeValToRGB'); rramp.location = (180, -120)
    rramp.color_ramp.elements[0].color = (0.6, 0.6, 0.6, 1)
    rramp.color_ramp.elements[1].color = (0.95, 0.95, 0.95, 1)
    L(n1.outputs['Fac'], rramp.inputs['Fac'])
    L(rramp.outputs['Color'], bsdf.inputs['Roughness'])
    bump = N('ShaderNodeBump'); bump.location = (180, -320)
    bump.inputs['Strength'].default_value = 0.25
    L(n2.outputs['Fac'], bump.inputs['Height'])
    if 'Normal' in bsdf.inputs:
        L(bump.outputs['Normal'], bsdf.inputs['Normal'])
    L(bsdf.outputs[0], out.inputs['Surface'])
    return mat


def _metal_material(name):
    mat = new_material(name)
    nt = mat.node_tree
    out = nt.nodes.new('ShaderNodeOutputMaterial'); out.location = (400, 0)
    bsdf = nt.nodes.new('ShaderNodeBsdfPrincipled'); bsdf.location = (150, 0)
    set_principled(bsdf, base_color=(0.05, 0.06, 0.08, 1), metallic=1.0, roughness=0.42)
    if not DEBUG_MODE:
        n = nt.nodes.new('ShaderNodeTexNoise'); n.location = (-260, -150)
        n.inputs['Scale'].default_value = 12.0
        ramp = nt.nodes.new('ShaderNodeValToRGB'); ramp.location = (-40, -150)
        ramp.color_ramp.elements[0].color = (0.30, 0.30, 0.35, 1)
        ramp.color_ramp.elements[1].color = (0.55, 0.55, 0.60, 1)
        nt.links.new(n.outputs['Fac'], ramp.inputs['Fac'])
        nt.links.new(ramp.outputs['Color'], bsdf.inputs['Roughness'])
    nt.links.new(bsdf.outputs[0], out.inputs['Surface'])
    return mat

def _water_material(name, turbulent=False):
    """Transmissive Principled water - reservoir (clear) vs downstream (turbid)."""
    mat = new_material(name)
    nt = mat.node_tree
    out = nt.nodes.new('ShaderNodeOutputMaterial'); out.location = (400, 0)
    bsdf = nt.nodes.new('ShaderNodeBsdfPrincipled'); bsdf.location = (120, 0)
    # Realistic transmissive water (recipe mirrored from real_water.py:
    # full Transmission, IOR 1.333, very low roughness, pale blue tint).
    if turbulent:
        # aerated discharge - slightly rougher / more tinted, still refractive
        tint = (0.62, 0.80, 0.92, 1.0)
        set_principled(bsdf, base_color=tint, roughness=0.06, ior=1.333,
                       transmission=1.0, specular=0.5)
    else:
        # clear reservoir / river water
        tint = (0.75, 0.90, 1.0, 1.0)
        set_principled(bsdf, base_color=tint, roughness=0.02, ior=1.333,
                       transmission=1.0, specular=0.5)
    nt.links.new(bsdf.outputs[0], out.inputs['Surface'])
    # help EEVEE show refraction where the option exists
    set_attr_safe(mat, "use_screen_refraction", True)
    set_attr_safe(mat, "use_raytrace_refraction", True)
    return mat


def _foam_material(name):
    mat = _flat_material(name, (0.92, 0.94, 0.96, 1.0), roughness=0.75)
    # a touch of emission so whitewater reads bright against dark water
    bsdf = mat.node_tree.nodes.get('Principled BSDF')
    if bsdf:
        set_principled(bsdf, emission_color=(1, 1, 1, 1), emission_strength=0.15)
    return mat


def _terrain_material(name):
    if DEBUG_MODE:
        return _flat_material(name, (0.32, 0.28, 0.22, 1.0), roughness=1.0)
    mat = new_material(name)
    nt = mat.node_tree
    N, L = nt.nodes.new, nt.links.new
    out = N('ShaderNodeOutputMaterial'); out.location = (600, 0)
    bsdf = N('ShaderNodeBsdfPrincipled'); bsdf.location = (380, 0)
    set_principled(bsdf, roughness=0.95, specular=0.1)
    tc = N('ShaderNodeTexCoord'); tc.location = (-800, 0)
    geo = N('ShaderNodeNewGeometry'); geo.location = (-800, -260)
    # rock vs soil by fractured noise
    n1 = N('ShaderNodeTexNoise'); n1.location = (-560, 120)
    n1.inputs['Scale'].default_value = 2.2
    n1.inputs['Detail'].default_value = 8.0
    rock = N('ShaderNodeValToRGB'); rock.location = (-320, 120)
    rock.color_ramp.elements[0].color = (0.14, 0.12, 0.10, 1)
    rock.color_ramp.elements[1].color = (0.42, 0.36, 0.30, 1)
    L(tc.outputs['Object'], n1.inputs['Vector'])
    L(n1.outputs['Fac'], rock.inputs['Fac'])
    # ===__TERRAIN_TAIL__===
    # green vegetation only on near-flat ground (normal Z high)
    sep = N('ShaderNodeSeparateXYZ'); sep.location = (-560, -260)
    L(geo.outputs['Normal'], sep.inputs['Vector'])
    slope = N('ShaderNodeValToRGB'); slope.location = (-320, -260)
    slope.color_ramp.elements[0].position = 0.75
    slope.color_ramp.elements[1].position = 0.92
    slope.color_ramp.elements[0].color = (0, 0, 0, 1)
    slope.color_ramp.elements[1].color = (1, 1, 1, 1)
    L(sep.outputs['Z'], slope.inputs['Fac'])
    # break up the grass edge with noise
    ng = N('ShaderNodeTexNoise'); ng.location = (-320, -60)
    ng.inputs['Scale'].default_value = 4.0
    grassmix = N('ShaderNodeMixRGB'); grassmix.location = (-60, -160)
    grassmix.blend_type = 'MULTIPLY'
    L(slope.outputs['Color'], grassmix.inputs['Color1'])
    L(ng.outputs['Fac'], grassmix.inputs['Color2'])
    final = N('ShaderNodeMixRGB'); final.location = (160, 60)
    final.inputs['Color2'].default_value = (0.14, 0.26, 0.10, 1)
    L(rock.outputs['Color'], final.inputs['Color1'])
    L(grassmix.outputs['Color'], final.inputs['Fac'])
    L(final.outputs['Color'], bsdf.inputs['Base Color'])
    bump = N('ShaderNodeBump'); bump.location = (160, -220)
    bump.inputs['Strength'].default_value = 0.35
    L(n1.outputs['Fac'], bump.inputs['Height'])
    if 'Normal' in bsdf.inputs:
        L(bump.outputs['Normal'], bsdf.inputs['Normal'])
    L(bsdf.outputs[0], out.inputs['Surface'])
    return mat


def _rock_material(name, tint):
    mat = new_material(name)
    nt = mat.node_tree
    N, L = nt.nodes.new, nt.links.new
    out = N('ShaderNodeOutputMaterial'); out.location = (400, 0)
    bsdf = N('ShaderNodeBsdfPrincipled'); bsdf.location = (150, 0)
    set_principled(bsdf, base_color=tint, roughness=0.9, specular=0.1)
    if not DEBUG_MODE:
        n = N('ShaderNodeTexNoise'); n.location = (-300, 0)
        n.inputs['Scale'].default_value = 6.0
        n.inputs['Detail'].default_value = 8.0
        ramp = N('ShaderNodeValToRGB'); ramp.location = (-60, 0)
        ramp.color_ramp.elements[0].color = tuple(c * 0.6 for c in tint[:3]) + (1,)
        ramp.color_ramp.elements[1].color = tint
        L(n.outputs['Fac'], ramp.inputs['Fac'])
        L(ramp.outputs['Color'], bsdf.inputs['Base Color'])
        bump = N('ShaderNodeBump'); bump.location = (-60, -220)
        bump.inputs['Strength'].default_value = 0.4
        L(n.outputs['Fac'], bump.inputs['Height'])
        if 'Normal' in bsdf.inputs:
            L(bump.outputs['Normal'], bsdf.inputs['Normal'])
    L(bsdf.outputs[0], out.inputs['Surface'])
    return mat

def create_materials():
    MATS["concrete"] = _concrete_material("MAT_Concrete")
    MATS["metal"]    = _metal_material("MAT_GateSteel")
    MATS["water"]    = _water_material("MAT_ReservoirWater", turbulent=False)
    MATS["water_sim"] = _water_material("MAT_SimWater", turbulent=True)
    MATS["foam"]     = _foam_material("MAT_Foam")
    MATS["terrain"]  = _terrain_material("MAT_Terrain")
    MATS["rock_dark"]  = _rock_material("MAT_RockDark",  (0.16, 0.15, 0.14, 1))
    MATS["rock_gray"]  = _rock_material("MAT_RockGray",  (0.34, 0.34, 0.33, 1))
    MATS["rock_brown"] = _rock_material("MAT_RockBrown", (0.30, 0.24, 0.18, 1))
    MATS["road"]     = _flat_material("MAT_Road", (0.05, 0.05, 0.055, 1), roughness=0.8)
    MATS["trunk"]    = _flat_material("MAT_Trunk", (0.16, 0.10, 0.06, 1), roughness=1.0)
    MATS["leaf"]     = _flat_material("MAT_Leaf", (0.10, 0.24, 0.08, 1), roughness=1.0)
    MATS["leaf2"]    = _flat_material("MAT_Leaf2", (0.14, 0.30, 0.10, 1), roughness=1.0)
    MATS["shrub"]    = _flat_material("MAT_Shrub", (0.16, 0.26, 0.12, 1), roughness=1.0)
    MATS["window"]   = _flat_material("MAT_Window", (0.02, 0.03, 0.05, 1),
                                      roughness=0.15, metallic=0.3)
    # a small palette for the cube houses
    house_cols = [(0.80, 0.78, 0.72, 1), (0.72, 0.55, 0.42, 1),
                  (0.85, 0.85, 0.85, 1), (0.60, 0.62, 0.66, 1),
                  (0.78, 0.68, 0.55, 1), (0.55, 0.30, 0.25, 1)]
    MATS["house"] = [_flat_material("MAT_House_%02d" % k, c, roughness=0.7)
                     for k, c in enumerate(house_cols)]
    roof_cols = [(0.35, 0.12, 0.10, 1), (0.20, 0.22, 0.26, 1), (0.28, 0.18, 0.12, 1)]
    MATS["roof"] = [_flat_material("MAT_Roof_%02d" % k, c, roughness=0.6)
                    for k, c in enumerate(roof_cols)]
    log("Materials created: %d datablocks." % len(bpy.data.materials))

# ===========================================================================
#  6. TERRAIN  (elevation profile that drives water downhill)
# ===========================================================================

def _smoothstep(e0, e1, v):
    if e0 == e1:
        return 0.0 if v < e0 else 1.0
    t = max(0.0, min(1.0, (v - e0) / (e1 - e0)))
    return t * t * (3.0 - 2.0 * t)


def _town_plain_z(y):
    """Graded flood-plain height under the town: gently downhill, dam -> valley."""
    f = _smoothstep(TOWN_NEAR_Y, TOWN_FAR_Y, y)     # 0 at near edge, 1 at far
    return (TOE_Z - 1.0) + f * (-6.0 - (TOE_Z - 1.0))


def _town_mask(x, y):
    """1 inside the town footprint, feathering to 0 over ~45 m outside it."""
    if not ENABLE_TOWN:
        return 0.0
    hw = TOWN_HALF_WIDTH + 15.0
    feather = 45.0
    mx = _smoothstep(hw + feather, hw, abs(x))
    my = (_smoothstep(TOWN_FAR_Y - 25.0 - feather, TOWN_FAR_Y - 25.0, y) *
          _smoothstep(TOWN_NEAR_Y + 25.0 + feather, TOWN_NEAR_Y + 25.0, y))
    return mx * my


def terrain_height(x, y):
    """World height at (x, y). Reservoir bed upstream (+Y), descending valley
    with a meandering, widening river channel downstream (-Y)."""
    if y >= 0.0:                                  # upstream / reservoir side
        up = min(y / RESERVOIR_SIZE, 1.0)
        base = (RESERVOIR_LEVEL - 24.0) + up * up * 95.0   # submerged -> rim hills
    else:                                         # downstream valley
        dn = min(-y / DOWNSTREAM_LENGTH, 1.0)
        base = TOE_Z + (RIVER_END_Z - TOE_Z) * dn
    ax = abs(x)
    valley_half = 250.0
    if ax > valley_half:                          # side hills flanking the valley
        base += (ax - valley_half) * 0.30
    # layered fractal relief
    base += fbm(x, y, octaves=5, scale=0.0045) * (8.0 + 0.015 * ax)
    base += fbm(x, y, octaves=3, scale=0.02) * 2.2
    # carve the downstream river channel (meanders and widens)
    if y < 0.0:
        dn = min(-y / DOWNSTREAM_LENGTH, 1.0)
        cx = 65.0 * math.sin((-y) * 0.006)
        d = abs(x - cx)
        cw = 55.0 + 45.0 * dn
        if d < cw:
            base -= (1.0 - d / cw) ** 2 * (11.0 + 15.0 * dn)
    # grade the town footprint into a gentle low flood plain (so the discharge
    # spreads through its streets instead of racing past in a deep gorge)
    m = _town_mask(x, y)
    if m > 0.0:
        base = base * (1.0 - m) + _town_plain_z(y) * m
    return base


def create_terrain():
    global TERRAIN_OBJ
    coll = COLLS["01_TERRAIN"]
    nx = 60 if DEBUG_MODE else 150
    ny = 70 if DEBUG_MODE else 180
    x0, x1 = -ENV_WIDTH / 2.0, ENV_WIDTH / 2.0
    y0, y1 = -DOWNSTREAM_LENGTH, RESERVOIR_SIZE
    verts, faces = [], []
    for j in range(ny + 1):
        v = j / ny
        y = y0 + (y1 - y0) * v
        for i in range(nx + 1):
            u = i / nx
            x = x0 + (x1 - x0) * u
            verts.append((x, y, terrain_height(x, y)))
    row = nx + 1
    for j in range(ny):
        for i in range(nx):
            a = j * row + i
            faces.append((a, a + 1, a + 1 + row, a + row))
    obj = mesh_from_pydata("TERRAIN_Valley", verts, faces, coll,
                           mat=MATS["terrain"], smooth=True)
    TERRAIN_OBJ = obj
    log("Terrain built (%d x %d)." % (nx, ny))
    return obj

# ===========================================================================
#  7. RESERVOIR SURFACE  (calm static water - NOT the primary sim water)
# ===========================================================================

def create_reservoir():
    coll = COLLS["04_WATER"]
    n = 40 if DEBUG_MODE else 90
    x0, x1 = -ENV_WIDTH / 2.0 * 0.98, ENV_WIDTH / 2.0 * 0.98
    y0, y1 = 6.0, RESERVOIR_SIZE * 0.98
    verts, faces = [], []
    for j in range(n + 1):
        y = y0 + (y1 - y0) * (j / n)
        for i in range(n + 1):
            x = x0 + (x1 - x0) * (i / n)
            # gentle broad swell + fine ripple, kept small so it stays calm
            z = (RESERVOIR_LEVEL
                 + fbm(x, y, octaves=3, scale=0.004) * 0.7
                 + fbm(x, y, octaves=2, scale=0.03) * 0.12)
            verts.append((x, y, z))
    row = n + 1
    for j in range(n):
        for i in range(n):
            a = j * row + i
            faces.append((a, a + 1, a + 1 + row, a + row))
    obj = mesh_from_pydata("WATER_Reservoir", verts, faces, coll,
                           mat=MATS["water"], smooth=True)
    log("Reservoir surface built.")
    return obj


def create_downstream_channels():
    """Calm river surface far downstream, continuing the sim water visually."""
    coll = COLLS["04_WATER"]
    n = 24 if DEBUG_MODE else 60
    # near end starts past the sim domain / town so it does not overlap the FLIP mesh
    y_near = (TOWN_FAR_Y - 70.0) if ENABLE_TOWN else -180.0
    y0, y1 = -DOWNSTREAM_LENGTH * 0.98, y_near
    verts, faces = [], []
    for j in range(n + 1):
        v = j / n
        y = y0 + (y1 - y0) * v
        cx = 65.0 * math.sin((-y) * 0.006)
        dn = min(-y / DOWNSTREAM_LENGTH, 1.0)
        cw = 48.0 + 40.0 * dn
        bed = TOE_Z + (RIVER_END_Z - TOE_Z) * dn
        wz = bed + 4.0                            # shallow river surface
        for i in range(n + 1):
            x = cx + (-cw + 2.0 * cw * (i / n))
            verts.append((x, y, wz))
    row = n + 1
    for j in range(n):
        for i in range(n):
            a = j * row + i
            faces.append((a, a + 1, a + 1 + row, a + row))
    obj = mesh_from_pydata("WATER_DownstreamRiver", verts, faces, coll,
                           mat=MATS["water"], smooth=True)
    log("Downstream river surface built.")
    return obj

# ===========================================================================
#  8. DAM  (many separate, individually editable objects - never one mesh)
# ===========================================================================

# Vertical layout of a spillway opening (ogee crest -> gate -> deck)
OPENING_BOTTOM = SPILLWAY_CREST_Z            # ogee crest = bottom of the opening
OPENING_TOP    = CREST_ROAD_Z - 4.0          # bottom of the crest bridge deck
CHUTE_LEN      = 75.0                         # downstream chute reach
BASIN_LEN      = 70.0                         # stilling-basin reach
DAM_OBJECTS    = []                           # for the final summary count


def _dam_obj(obj):
    DAM_OBJECTS.append(obj)
    return obj


def create_dam(bays):
    coll = COLLS["02_DAM"]
    # continuous foundation footing under the whole structure
    found = add_box("DAM_Foundation", DAM_LENGTH + 70, DAM_WIDTH * 1.5, 10.0,
                    coll, location=(0, -2, 3.0), mat=MATS["concrete"])
    add_bevel(found, 0.8, 2)
    _dam_obj(found)
    # solid lower body of each bay (0 -> ogee crest), holds back the reservoir
    for b in bays:
        bay_w = b["bay_w"]
        open_w = bay_w * 0.80
        h = OPENING_BOTTOM
        c = bay_to_world(b, (0.0, 0.0, h / 2.0))
        body = add_box("DAM_MainSection_%02d" % b["i"], open_w, DAM_WIDTH, h,
                       coll, location=c, rotation=(0, 0, b["rot_z"]),
                       mat=MATS["concrete"])
        add_bevel(body, 0.4, 2)
        _dam_obj(body)
        # upstream inclined face plate (visual heft on the reservoir side)
        up = bay_to_world(b, (0.0, DAM_WIDTH * 0.5, h * 0.5))
        face = add_box("DAM_UpstreamFace_%02d" % b["i"], open_w, 3.0, h,
                       coll, location=up, rotation=(0, 0, b["rot_z"]),
                       mat=MATS["concrete"])
        _dam_obj(face)
    create_dam_piers(bays)
    create_spillway_bays(bays)
    create_dam_apron(bays)
    create_dam_details(bays)
    # side embankments / abutments at both ends of the arc
    for sgn, tag in ((-1, "L"), (1, "R")):
        end = bays[0] if sgn < 0 else bays[-1]
        ex = bay_to_world(end, (sgn * end["bay_w"] * 1.2, -10.0, CREST_ROAD_Z * 0.5))
        ab = add_box("DAM_Abutment_%s" % tag, 90, DAM_WIDTH * 2.2, CREST_ROAD_Z,
                     coll, location=(ex.x, ex.y, CREST_ROAD_Z * 0.5),
                     rotation=(0, 0, end["rot_z"]), mat=MATS["concrete"])
        add_bevel(ab, 1.0, 2)
        _dam_obj(ab)
    log("Dam core built: %d objects." % len(DAM_OBJECTS))

def create_dam_piers(bays):
    """Vertical concrete piers separating the bays (N_GATES + 1 of them)."""
    coll = COLLS["02_DAM"]
    span = math.radians(ARC_ANGLE_DEG)
    R = DAM_LENGTH / span
    pier_w = (DAM_LENGTH / N_GATES) * 0.20
    for k in range(N_GATES + 1):
        t = -span / 2.0 + k * (span / N_GATES)
        pos = Vector((R * math.sin(t), R * (math.cos(t) - 1.0), 0.0))
        rot = -t
        # pier reaches from foundation to crest, slightly nosed downstream
        loc = pos + Vector((0, 0, CREST_ROAD_Z / 2.0))
        p = add_box("DAM_Pier_%02d" % k, pier_w, DAM_WIDTH * 1.05, CREST_ROAD_Z,
                    coll, location=loc, rotation=(0, 0, rot), mat=MATS["concrete"])
        add_bevel(p, 0.5, 2)
        _dam_obj(p)
        # rounded upstream cutwater nose
        nose = add_cylinder("DAM_PierNose_%02d" % k, pier_w * 0.5, CREST_ROAD_Z,
                            coll, segments=12, location=(0, 0, 0),
                            mat=MATS["concrete"])
        up = Vector((-math.sin(t), math.cos(t), 0)) * (DAM_WIDTH * 0.52)
        nose.location = (pos.x + up.x, pos.y + up.y, CREST_ROAD_Z / 2.0)
        _dam_obj(nose)


def create_spillway_bays(bays):
    """Bridge deck beam + parapet railings above every bay opening."""
    coll = COLLS["02_DAM"]
    for b in bays:
        bay_w = b["bay_w"]
        deck_h = CREST_ROAD_Z - OPENING_TOP
        cz = OPENING_TOP + deck_h / 2.0
        c = bay_to_world(b, (0.0, 0.0, cz))
        deck = add_box("DAM_Deck_%02d" % b["i"], bay_w * 0.82, DAM_WIDTH * 0.7,
                       deck_h, coll, location=c, rotation=(0, 0, b["rot_z"]),
                       mat=MATS["concrete"])
        add_bevel(deck, 0.3, 2)
        _dam_obj(deck)
        # parapet railings on the upstream & downstream edges of the crest road
        for sgn in (-1, 1):
            rc = bay_to_world(b, (0.0, sgn * DAM_WIDTH * 0.32, CREST_ROAD_Z + 0.7))
            rail = add_box("DAM_Railing_%02d_%s" % (b["i"], "U" if sgn > 0 else "D"),
                           bay_w, 0.35, 1.4, coll, location=rc,
                           rotation=(0, 0, b["rot_z"]), mat=MATS["metal"])
            _dam_obj(rail)

# --- shared apron geometry (used by render dam AND the collision proxy) -----
CHUTE_TOP_Y = DAM_WIDTH * 0.4
CHUTE_BOT_Y = -135.0
CHUTE_TOP_Z = OPENING_BOTTOM
CHUTE_BOT_Z = TOE_Z
BASIN_Y1    = -210.0                          # downstream end of stilling basin
APRON_WIDTH = DAM_LENGTH + 130.0


def _chute_transform():
    dy = CHUTE_TOP_Y - CHUTE_BOT_Y
    dz = CHUTE_TOP_Z - CHUTE_BOT_Z
    slope = math.atan2(dz, dy)
    length = math.hypot(dy, dz)
    y_mid = (CHUTE_TOP_Y + CHUTE_BOT_Y) / 2.0
    z_mid = (CHUTE_TOP_Z + CHUTE_BOT_Z) / 2.0
    return slope, length, y_mid, z_mid


def create_dam_apron(bays):
    coll = COLLS["02_DAM"]
    slope, length, y_mid, z_mid = _chute_transform()
    chute = add_box("DAM_SpillwayChute", APRON_WIDTH, length, 6.0, coll,
                    location=(0, y_mid, z_mid), rotation=(slope, 0, 0),
                    mat=MATS["concrete"])
    _dam_obj(chute)
    # training walls down both sides of the chute
    for sgn, tag in ((-1, "L"), (1, "R")):
        w = add_box("DAM_ChuteWall_%s" % tag, 4.0, length, 16.0, coll,
                    location=(sgn * APRON_WIDTH / 2.0, y_mid, z_mid + 7.0),
                    rotation=(slope, 0, 0), mat=MATS["concrete"])
        _dam_obj(w)
    # stilling basin floor
    basin = add_box("DAM_StillingBasin", APRON_WIDTH, (CHUTE_BOT_Y - BASIN_Y1),
                    5.0, coll,
                    location=(0, (CHUTE_BOT_Y + BASIN_Y1) / 2.0, TOE_Z - 1.0),
                    mat=MATS["concrete"])
    _dam_obj(basin)
    # energy-dissipating baffle blocks across the basin (also nice collision)
    n_baf = 5 if DEBUG_MODE else 12
    by = (CHUTE_BOT_Y + BASIN_Y1) / 2.0
    for k in range(n_baf):
        bx = -APRON_WIDTH / 2.0 * 0.8 + APRON_WIDTH * 0.8 * (k / (n_baf - 1))
        blk = add_box("DAM_Baffle_%02d" % k, 8.0, 6.0, 7.0, coll,
                      location=(bx, by, TOE_Z + 2.0), mat=MATS["concrete"])
        _dam_obj(blk)

def create_dam_details(bays):
    """Low-poly extras: walkway kerb, weep holes, expansion joints, utility cabins."""
    coll = COLLS["02_DAM"]
    dark = _flat_material("MAT_DamDark", (0.03, 0.03, 0.03, 1), roughness=0.9)
    for b in bays:
        bay_w = b["bay_w"]
        # downstream drainage / weep opening on the lower body face
        wp = bay_to_world(b, (0.0, -DAM_WIDTH * 0.5 - 0.2, OPENING_BOTTOM * 0.45))
        _dam_obj(add_box("DAM_Weep_%02d" % b["i"], bay_w * 0.12, 0.6, 2.0, coll,
                         location=wp, rotation=(0, 0, b["rot_z"]), mat=dark))
        # expansion joint seam on the upstream face
        js = bay_to_world(b, (bay_w * 0.5, DAM_WIDTH * 0.5 + 0.1, OPENING_BOTTOM * 0.5))
        _dam_obj(add_box("DAM_Joint_%02d" % b["i"], 0.25, 0.4, OPENING_BOTTOM, coll,
                         location=js, rotation=(0, 0, b["rot_z"]), mat=dark))
        # inspection platform cantilevered downstream every few bays
        if b["i"] % 3 == 0:
            pp = bay_to_world(b, (0.0, -DAM_WIDTH * 0.5 - 3.0, CREST_ROAD_Z - 6.0))
            _dam_obj(add_box("DAM_Platform_%02d" % b["i"], bay_w * 0.5, 6.0, 0.6,
                             coll, location=pp, rotation=(0, 0, b["rot_z"]),
                             mat=MATS["concrete"]))
    # small utility cabins on the crest at a few piers
    span = math.radians(ARC_ANGLE_DEG)
    R = DAM_LENGTH / span
    for k in range(0, N_GATES + 1, 4):
        t = -span / 2.0 + k * (span / N_GATES)
        pos = Vector((R * math.sin(t), R * (math.cos(t) - 1.0), CREST_ROAD_Z + 2.0))
        _dam_obj(add_box("DAM_Cabin_%02d" % k, 6.0, 5.0, 4.0, coll,
                         location=pos, rotation=(0, 0, -t), mat=MATS["concrete"]))

def parent_keep_local(child, parent):
    """Parent using child's transform as a pure local offset (no inverse jump)."""
    child.parent = parent
    child.matrix_parent_inverse = Matrix.Identity(4)


# ===========================================================================
#  9. SPILLWAY GATES  (individual radial/flap gates on real pivots)
# ===========================================================================

GATE_HEIGHT       = OPENING_TOP - OPENING_BOTTOM      # covered opening height
FULL_OPEN_ANGLE   = math.radians(72.0)                # rotation at 100% open
GATE_CONTROLLERS  = []                                # (ctrl, target_angle, i)


def create_gates(bays):
    coll = COLLS["03_GATES"]
    open_mid = (OPENING_BOTTOM + OPENING_TOP) / 2.0
    ty = -DAM_WIDTH * 0.15
    tz = OPENING_TOP + 4.0
    for b in bays:
        bay_w = b["bay_w"]
        open_w = bay_w * 0.80
        # pivot / trunnion controller empty
        tw = bay_to_world(b, (0.0, ty, tz))
        ctrl = add_empty("GATE_CTRL_%02d" % b["i"], location=tw,
                         rotation=(0.0, 0.0, b["rot_z"]), coll=coll, size=6.0)
        # local offsets (in the bay frame, relative to the trunnion)
        p_plate = (0.0, -ty, open_mid - tz)
        dy, dz = p_plate[1], p_plate[2]
        arm_len = math.hypot(dy, dz)
        arm_rot = math.atan2(dz, dy)
        # skinplate
        plate = add_box("GATE_%02d" % b["i"], open_w, 1.3, GATE_HEIGHT, coll,
                        location=p_plate, rotation=(0, 0, 0), mat=MATS["metal"])
        add_bevel(plate, 0.15, 1)
        parent_keep_local(plate, ctrl)
        # horizontal stiffener ribs
        for r in range(3):
            rz = -GATE_HEIGHT * 0.35 + r * GATE_HEIGHT * 0.35
            rib = add_box("GATE_Rib_%02d_%d" % (b["i"], r), open_w, 0.9, 0.6, coll,
                          location=(p_plate[0], p_plate[1] - 0.9, p_plate[2] + rz),
                          mat=MATS["metal"])
            parent_keep_local(rib, ctrl)
        # two radial arms from the trunnion to the skinplate
        for sgn in (-1, 1):
            arm = add_box("GATE_Arm_%02d_%s" % (b["i"], "L" if sgn < 0 else "R"),
                          0.7, arm_len, 0.7, coll,
                          location=(sgn * open_w * 0.4, dy / 2.0, dz / 2.0),
                          rotation=(arm_rot, 0, 0), mat=MATS["metal"])
            parent_keep_local(arm, ctrl)
        GATE_CONTROLLERS.append((ctrl, FULL_OPEN_ANGLE * b["frac"] * GATE_OPEN_AMOUNT,
                                 b["i"]))
    create_gate_mechanisms(bays)
    log("Gates built: %d." % len(GATE_CONTROLLERS))

def create_gate_mechanisms(bays):
    """Static hoist houses, lifting cables and counterweights on the crest."""
    coll = COLLS["03_GATES"]
    for b in bays:
        bay_w = b["bay_w"]
        # hoist house sitting on the crest bridge above the gate
        hh = bay_to_world(b, (0.0, 0.0, CREST_ROAD_Z + 3.0))
        add_box("GATE_Hoist_%02d" % b["i"], bay_w * 0.4, DAM_WIDTH * 0.35, 6.0,
                coll, location=hh, rotation=(0, 0, b["rot_z"]), mat=MATS["metal"])
        # two lifting cables/rods running down toward the gate top
        for sgn in (-1, 1):
            top = bay_to_world(b, (sgn * bay_w * 0.28, -2.0, CREST_ROAD_Z))
            add_cylinder("GATE_Cable_%02d_%s" % (b["i"], "L" if sgn < 0 else "R"),
                         0.25, 12.0, coll, segments=6,
                         location=(top.x, top.y, CREST_ROAD_Z - 5.0),
                         mat=MATS["metal"])


def animate_gates():
    """Keyframe each controller open; staggered timing and varied final states."""
    for ctrl, target, i in GATE_CONTROLLERS:
        start = 20 + (i % 5) * 4          # stagger so gates don't move identically
        ctrl.rotation_euler.x = 0.0
        ctrl.keyframe_insert("rotation_euler", index=0, frame=1)
        ctrl.keyframe_insert("rotation_euler", index=0, frame=start)
        ctrl.rotation_euler.x = target * 0.5
        ctrl.keyframe_insert("rotation_euler", index=0, frame=start + 50)
        ctrl.rotation_euler.x = target
        ctrl.keyframe_insert("rotation_euler", index=0, frame=start + 95)
        ctrl.keyframe_insert("rotation_euler", index=0, frame=CACHE_FRAME_END)
        # keep the resting pose at the target so the sim frames show open gates
        ctrl.rotation_euler.x = target
        # smooth interpolation (Bezier is the default, but set it defensively)
        ad = getattr(ctrl, "animation_data", None)
        act = getattr(ad, "action", None) if ad else None
        fcurves = getattr(act, "fcurves", None) if act else None
        if fcurves:
            try:
                for fc in fcurves:
                    for kp in fc.keyframe_points:
                        kp.interpolation = 'BEZIER'
                        kp.handle_left_type = kp.handle_right_type = 'AUTO_CLAMPED'
            except Exception as e:
                log("  (gate fcurve tweak skipped: %s)" % e)
    log("Gate animation keyframed (%d controllers)." % len(GATE_CONTROLLERS))

# ===========================================================================
#  10. MANTAFLOW LIQUID  (domain + inflow + collision proxy + config)
# ===========================================================================

DOMAIN_OBJ = None
CACHE_DIR  = ""
TERRAIN_OBJ = None
TOWN_BUILDINGS = []


def create_water_domain(bays):
    """Box domain covering: behind the OPEN gates -> chute -> stilling basin,
    and (when ENABLE_TOWN) the downstream flood plain where the town sits."""
    global DOMAIN_OBJ
    coll = COLLS["04_WATER"]
    x0, x1, _, _ = open_bays_bounds(bays, pad=35.0)
    y_max = 55.0                                   # a little into the reservoir
    if ENABLE_TOWN:
        x0 = min(x0, -TOWN_HALF_WIDTH - 25.0)      # widen to span the town
        x1 = max(x1, TOWN_HALF_WIDTH + 25.0)
        y_min = TOWN_FAR_Y - 45.0                  # reach past the far streets
        z_min = min(TOE_Z - 14.0, RIVER_END_Z - 16.0)  # contain the deep channel
    else:
        y_min = BASIN_Y1 - 35.0                    # past the stilling basin
        z_min = TOE_Z - 14.0
    z_max = RESERVOIR_LEVEL + 12.0
    cx, cy, cz = (x0 + x1) / 2.0, (y_max + y_min) / 2.0, (z_min + z_max) / 2.0
    sx, sy, sz = (x1 - x0), (y_max - y_min), (z_max - z_min)
    dom = add_box("WATER_Domain", sx, sy, sz, coll, location=(cx, cy, cz))
    assign_material(dom, MATS["water_sim"])
    dom.display_type = 'WIRE' if not DEBUG_MODE else 'SOLID'
    dom.hide_render = False
    make_fluid_domain(dom)                         # configured later
    DOMAIN_OBJ = dom
    log("Water domain: %.0f x %.0f x %.0f m at res %d (adaptive=%s)." %
        (sx, sy, sz, DOMAIN_RESOLUTION, USE_ADAPTIVE_DOMAIN))
    return dom


def create_water_inflow(bays):
    """One liquid INFLOW per OPEN bay, straddling the crest and aimed downstream."""
    coll = COLLS["04_WATER"]
    count = 0
    for b in bays:
        if not b["open"]:
            continue
        open_w = b["bay_w"] * 0.80
        c = bay_to_world(b, (0.0, -2.0, OPENING_BOTTOM + 4.0))
        src = add_box("WATER_Inflow_%02d" % b["i"], open_w * 0.92, 12.0, 10.0,
                      coll, location=c, rotation=(0, 0, b["rot_z"]))
        src.display_type = 'WIRE' if not DEBUG_MODE else 'SOLID'
        src.hide_render = True
        fs = make_fluid_flow(src, behavior='INFLOW')
        set_attr_safe(fs, "use_initial_velocity", True)
        # aim downstream (-Y world) and slightly down; curvature is mild so world is fine
        set_attr_safe(fs, "velocity_coord", (0.0, -INFLOW_RATE, -2.0))
        set_attr_safe(fs, "use_inflow", True)
        set_attr_safe(fs, "volume_density", 1.0)
        set_attr_safe(fs, "surface_distance", 1.5)
        # stop emitting after FLOW_DURATION frames if the user shortened it
        if FLOW_DURATION < CACHE_FRAME_END and hasattr(fs, "use_inflow"):
            fs.use_inflow = True
            fs.keyframe_insert("use_inflow", frame=FLOW_DURATION)
            fs.use_inflow = False
            fs.keyframe_insert("use_inflow", frame=FLOW_DURATION + 1)
        count += 1
    log("Liquid inflows created for %d open bays." % count)

def create_water_obstacle_geometry(bays, rocks=None):
    """Simple, watertight COLLISION proxies (kept separate from render geometry).

    The dam wall is solid everywhere EXCEPT the openings of OPEN bays, so the
    emitted water can only escape through the open spillways."""
    coll = COLLS["04_WATER"]
    prox_mat = _flat_material("MAT_Proxy", (0.15, 0.45, 0.9, 1.0), roughness=1.0)
    proxies = []

    def _proxy(obj, sd=0.6):
        obj.hide_render = not DEBUG_MODE
        obj.display_type = 'SOLID' if DEBUG_MODE else 'WIRE'
        assign_material(obj, prox_mat)
        make_fluid_effector(obj, surface_distance=sd)
        proxies.append(obj)
        return obj

    # --- dam wall (solid, gaps only at open bay openings) -------------------
    for b in bays:
        bw = b["bay_w"]
        if b["open"]:
            hl = OPENING_BOTTOM
            _proxy(add_box("COL_DamLo_%02d" % b["i"], bw, DAM_WIDTH, hl, coll,
                           location=bay_to_world(b, (0, 0, hl / 2.0)),
                           rotation=(0, 0, b["rot_z"])))
            hu0, hu1 = OPENING_TOP, CREST_ROAD_Z
            _proxy(add_box("COL_DamHi_%02d" % b["i"], bw, DAM_WIDTH, hu1 - hu0, coll,
                           location=bay_to_world(b, (0, 0, (hu0 + hu1) / 2.0)),
                           rotation=(0, 0, b["rot_z"])))
        else:
            _proxy(add_box("COL_Dam_%02d" % b["i"], bw, DAM_WIDTH, CREST_ROAD_Z, coll,
                           location=bay_to_world(b, (0, 0, CREST_ROAD_Z / 2.0)),
                           rotation=(0, 0, b["rot_z"])))

    # --- chute, training walls, basin ---------------------------------------
    slope, length, y_mid, z_mid = _chute_transform()
    _proxy(add_box("COL_Chute", APRON_WIDTH, length, 3.0, coll,
                   location=(0, y_mid, z_mid), rotation=(slope, 0, 0)))
    for sgn, tag in ((-1, "L"), (1, "R")):
        _proxy(add_box("COL_ChuteWall_%s" % tag, 3.0, length, 16.0, coll,
                       location=(sgn * APRON_WIDTH / 2.0, y_mid, z_mid + 7.0),
                       rotation=(slope, 0, 0)))
    _proxy(add_box("COL_Basin", APRON_WIDTH, (CHUTE_BOT_Y - BASIN_Y1), 3.0, coll,
                   location=(0, (CHUTE_BOT_Y + BASIN_Y1) / 2.0, TOE_Z - 1.0)))
    # downstream channel floor carrying water to the domain edge
    y_edge = BASIN_Y1 - 40.0
    _proxy(add_box("COL_Channel", APRON_WIDTH, (BASIN_Y1 - y_edge), 3.0, coll,
                   location=(0, (BASIN_Y1 + y_edge) / 2.0, TOE_Z - 3.0)))

    # --- selected rocks in the flow path act as collision -------------------
    n_rock_col = 0
    for r in (rocks or []):
        if r.location.y < CHUTE_TOP_Y and r.location.y > BASIN_Y1 - 40.0 \
                and abs(r.location.x) < APRON_WIDTH / 2.0:
            make_fluid_effector(r, surface_distance=0.4)
            n_rock_col += 1
    # --- terrain floor + town structures as collision -----------------------
    # The valley terrain becomes a static effector so the flood rests on the
    # graded plain (not the domain floor) and washes through the streets; the
    # nearest town buildings are flagged too (bounded count for solver speed).
    n_terrain = 0
    if ENABLE_TOWN and TERRAIN_OBJ is not None:
        make_fluid_effector(TERRAIN_OBJ, surface_distance=0.4)
        n_terrain = 1
    n_town = 0
    if ENABLE_TOWN and TOWN_FLOOD_ZONE and TOWN_BUILDINGS:
        cap = 24 if DEBUG_MODE else 60
        reach = sorted(TOWN_BUILDINGS,
                       key=lambda b: math.hypot(b["x"], b["y"] - TOWN_NEAR_Y))
        for b in reach[:cap]:
            make_fluid_effector(b["obj"], surface_distance=0.35)
            n_town += 1
    log("Collision proxies: %d  (+%d rocks, +%d terrain, +%d town effectors)."
        % (len(proxies), n_rock_col, n_terrain, n_town))
    return proxies

def _domain_settings(domain):
    mod = next((m for m in domain.modifiers if m.type == 'FLUID'), None)
    return mod.domain_settings if mod else None


def configure_whitewater(ds):
    """Foam / spray / bubbles, biased to high-energy zones (all guarded)."""
    for p in ("use_spray_particles", "use_foam_particles", "use_bubble_particles"):
        set_attr_safe(ds, p, True)
    set_attr_safe(ds, "sndparticle_potential_min_wavecrest", 2.0)
    set_attr_safe(ds, "sndparticle_potential_max_wavecrest", 8.0)
    set_attr_safe(ds, "sndparticle_potential_min_trappedair", 5.0)
    set_attr_safe(ds, "sndparticle_potential_max_trappedair", 25.0)
    set_attr_safe(ds, "sndparticle_potential_min_energy", 1.0)
    set_attr_safe(ds, "sndparticle_potential_max_energy", 12.0)
    set_attr_safe(ds, "sndparticle_sampling_trappedair", 150)
    set_attr_safe(ds, "sndparticle_sampling_wavecrest", 150)
    set_attr_safe(ds, "sndparticle_bubble_buoyancy", -8.0)
    set_attr_safe(ds, "sndparticle_bubble_drag", 0.8)
    set_attr_safe(ds, "particle_scale", 1.0)


def configure_mantaflow(domain):
    global CACHE_DIR
    ds = _domain_settings(domain)
    if ds is None:
        log("ERROR: domain settings missing - Mantaflow not configured.")
        return
    set_enum_safe(ds, "domain_type", ['LIQUID'])
    set_attr_safe(ds, "resolution_max", DOMAIN_RESOLUTION)
    set_enum_safe(ds, "simulation_method", ['FLIP', 'APIC'])   # FLIP liquid
    set_attr_safe(ds, "use_adaptive_timesteps", True)
    set_attr_safe(ds, "timesteps_max", MAX_TIME_STEP)
    set_attr_safe(ds, "timesteps_min", 1)
    set_attr_safe(ds, "cfl_condition", 1.0)
    set_attr_safe(ds, "flip_ratio", 0.97)
    set_attr_safe(ds, "particle_radius", 1.2)
    set_attr_safe(ds, "particle_number", 2)
    set_attr_safe(ds, "use_fractions", True)          # thin-obstacle accuracy
    set_attr_safe(ds, "use_mesh", True)               # smooth liquid surface mesh
    set_attr_safe(ds, "use_flip_particles", True)
    # --- optimisation: adaptive domain only allocates cells near the fluid ---
    if USE_ADAPTIVE_DOMAIN:
        set_attr_safe(ds, "use_adaptive_domain", True)
        set_attr_safe(ds, "additional_res", 0)
        set_attr_safe(ds, "adapt_margin", 4)
        set_attr_safe(ds, "adapt_threshold", 0.02)
    # cache (absolute path so it is valid even before the .blend is saved)
    base = bpy.path.abspath("//") if bpy.data.filepath else \
        os.path.join(os.path.expanduser("~"), "mettur_dam")
    CACHE_DIR = os.path.join(base, "mettur_cache")
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
    except Exception as e:
        log("  (could not create cache dir: %s)" % e)
    set_attr_safe(ds, "cache_directory", CACHE_DIR)
    set_attr_safe(ds, "cache_frame_start", CACHE_FRAME_START)
    set_attr_safe(ds, "cache_frame_end", CACHE_FRAME_END)
    # prefer the user's choice (REPLAY = simulate on playback, no manual bake)
    set_enum_safe(ds, "cache_type", [SIM_CACHE_TYPE, 'REPLAY', 'MODULAR', 'ALL'])
    if ENABLE_WHITEWATER:
        configure_whitewater(ds)
    log("Mantaflow configured (res %d, cache '%s')." % (DOMAIN_RESOLUTION, CACHE_DIR))

def create_rocks(bays):
    """Boulders downstream. Returns the list of rock objects (flow-path ones
    are later flagged as Mantaflow effectors by create_water_obstacle_geometry)."""
    coll = COLLS["05_ROCKS"]
    rng = random.Random(SEED + 501)
    rocks = []
    rock_mats = [MATS["rock_gray"], MATS["rock_brown"], MATS["rock_dark"]]
    xmin, xmax, _, _ = open_bays_bounds(bays, pad=40.0)
    cx = (xmin + xmax) * 0.5
    n_big = 5 if DEBUG_MODE else 11
    n_med = 8 if DEBUG_MODE else 26
    n_small = 10 if DEBUG_MODE else 50
    # Large boulders lining / studding the discharge channel (collision candidates)
    for i in range(n_big):
        x = cx + rng.uniform(-160.0, 160.0)
        y = rng.uniform(-260.0, -560.0)
        r = rng.uniform(6.0, 12.0)
        z = terrain_height(x, y) + r * 0.35
        rk = make_rock("ROCK_Large_%02d" % i, r, coll, subdiv=2,
                       jag=0.42, seed=SEED + i * 7 + 1, mat=rng.choice(rock_mats))
        rk.location = Vector((x, y, z))
        rk.rotation_euler = Euler((rng.uniform(0, 0.4), rng.uniform(0, 0.4),
                                   rng.uniform(0, 6.28)))
        rocks.append(rk)
    # Medium scatter across the downstream apron and banks
    for i in range(n_med):
        x = rng.uniform(-ENV_WIDTH * 0.35, ENV_WIDTH * 0.35)
        y = rng.uniform(-220.0, -DOWNSTREAM_LENGTH)
        r = rng.uniform(2.5, 5.5)
        z = terrain_height(x, y) + r * 0.3
        rk = make_rock("ROCK_Medium_%02d" % i, r, coll, subdiv=1,
                       jag=0.38, seed=SEED + i * 13 + 3, mat=rng.choice(rock_mats))
        rk.location = Vector((x, y, z))
        rk.rotation_euler = Euler((0, 0, rng.uniform(0, 6.28)))
        rocks.append(rk)
    # Small debris
    for i in range(n_small):
        x = rng.uniform(-ENV_WIDTH * 0.4, ENV_WIDTH * 0.4)
        y = rng.uniform(-200.0, -ENV_DEPTH * 0.5)
        r = rng.uniform(0.8, 2.2)
        z = terrain_height(x, y) + r * 0.25
        rk = make_rock("ROCK_Small_%02d" % i, r, coll, subdiv=1,
                       jag=0.33, seed=SEED + i * 17 + 5, mat=rng.choice(rock_mats))
        rk.location = Vector((x, y, z))
        rk.rotation_euler = Euler((0, 0, rng.uniform(0, 6.28)))
        rocks.append(rk)
    log("Created %d rocks/boulders." % len(rocks))
    return rocks

def _gable_roof(name, sx, sy, rh, coll, mat):
    hx, hy = sx * 0.5, sy * 0.5
    verts = [(-hx, -hy, 0), (hx, -hy, 0), (hx, hy, 0), (-hx, hy, 0),
             (0, -hy, rh), (0, hy, rh)]
    faces = [(0, 1, 4), (2, 5, 3), (0, 4, 5, 3), (1, 2, 5, 4), (0, 3, 2, 1)]
    return mesh_from_pydata(name, verts, faces, coll, mat=mat, smooth=False)


def _house_materials():
    if "house_wall" not in MATS:
        MATS["house_wall"] = _flat_material("MAT_HouseWall", (0.72, 0.66, 0.55), 0.85)
        MATS["house_wall2"] = _flat_material("MAT_HouseWall2", (0.80, 0.78, 0.74), 0.85)
        MATS["house_roof"] = _flat_material("MAT_HouseRoof", (0.35, 0.10, 0.07), 0.7)
        MATS["house_glass"] = _flat_material("MAT_HouseGlass", (0.05, 0.08, 0.10), 0.15, 0.0)


def create_houses():
    """Cube-based village houses on elevated ground beside the flood plain."""
    coll = COLLS["06_HOUSES"]
    _house_materials()
    rng = random.Random(SEED + 707)
    count = 6 if DEBUG_MODE else 18
    placed = 0
    attempts = 0
    while placed < count and attempts < count * 12:
        attempts += 1
        side = -1 if rng.random() < 0.5 else 1
        x = side * rng.uniform(ENV_WIDTH * 0.20, ENV_WIDTH * 0.44)
        y = rng.uniform(-260.0, -ENV_DEPTH * 0.55)
        gz = terrain_height(x, y)
        if gz < TOE_Z + 6.0:            # keep dwellings off the low flood channel
            continue
        w = rng.uniform(7.0, 12.0)
        d = rng.uniform(7.0, 12.0)
        h = rng.uniform(4.5, 7.0)
        wall = MATS["house_wall"] if rng.random() < 0.6 else MATS["house_wall2"]
        body = add_box("HOUSE_%02d_Body" % placed, w, d, h, coll,
                       location=(x, y, gz + h * 0.5), mat=wall)
        rot = rng.uniform(0, 6.28)
        body.rotation_euler = Euler((0, 0, rot))
        roof = _gable_roof("HOUSE_%02d_Roof" % placed, w * 1.08, d * 1.08,
                           rng.uniform(2.5, 4.0), coll, MATS["house_roof"])
        roof.location = Vector((x, y, gz + h))
        roof.rotation_euler = Euler((0, 0, rot))
        # front window strip
        win = add_box("HOUSE_%02d_Win" % placed, w * 0.5, 0.3, h * 0.35, coll,
                      location=(x, y - d * 0.5, gz + h * 0.5), mat=MATS["house_glass"])
        win.rotation_euler = Euler((0, 0, rot))
        placed += 1
    log("Created %d houses." % placed)

def _frange(a, b, step):
    vals, v = [], a
    while v <= b + 1e-6:
        vals.append(v)
        v += step
    return vals


def _town_materials():
    if "town_road" in MATS:
        return
    MATS["town_road"] = _flat_material("MAT_TownRoad", (0.045, 0.045, 0.05), 0.85)
    MATS["town_wall"] = [
        _flat_material("MAT_TownWall_0", (0.78, 0.72, 0.62), 0.85),
        _flat_material("MAT_TownWall_1", (0.66, 0.69, 0.72), 0.80),
        _flat_material("MAT_TownWall_2", (0.82, 0.78, 0.70), 0.85),
        _flat_material("MAT_TownWall_3", (0.58, 0.54, 0.50), 0.85),
        _flat_material("MAT_TownWall_4", (0.70, 0.60, 0.52), 0.85),
    ]
    MATS["town_glass"] = _flat_material("MAT_TownGlass", (0.08, 0.14, 0.20), 0.10, 0.0)
    MATS["town_roof"] = _flat_material("MAT_TownRoof", (0.28, 0.11, 0.08), 0.7)
    MATS["town_parapet"] = _flat_material("MAT_TownParapet", (0.52, 0.52, 0.54), 0.7)


def _town_building(coll, ox, oy, tier, rng, idx, cell):
    """Build one town structure on the graded plain at (ox, oy).

    tier is 'tower', 'midrise' or 'house'. Returns its record dict, or None if
    the plot falls in the deep river gorge (nothing is built there)."""
    gz = terrain_height(ox, oy)
    if gz < RIVER_END_Z + 2.0:
        return None
    if tier == 'tower':
        h = rng.uniform(*TOWER_H_RANGE)
    elif tier == 'midrise':
        h = rng.uniform(*MIDRISE_H_RANGE)
    else:
        h = rng.uniform(*HOUSE_H_RANGE)
    fw = cell * rng.uniform(0.60, 0.82)
    fd = cell * rng.uniform(0.60, 0.82)
    body = add_box("TOWN_B%04d" % idx, fw, fd, h, coll,
                   location=(ox, oy, gz + h * 0.5), mat=rng.choice(MATS["town_wall"]))
    if tier == 'house':                     # pitched-roof cottage
        rf = _gable_roof("TOWN_B%04d_Rf" % idx, fw * 1.06, fd * 1.06,
                         rng.uniform(1.8, 3.0), coll, MATS["town_roof"])
        rf.location = Vector((ox, oy, gz + h))
    else:                                   # flat parapet cap + a facade glass band
        add_box("TOWN_B%04d_Cap" % idx, fw * 1.04, fd * 1.04, 1.3, coll,
                location=(ox, oy, gz + h + 0.65), mat=MATS["town_parapet"])
        add_box("TOWN_B%04d_Gl" % idx, fw * 0.9, fd * 0.92, h * 0.7, coll,
                location=(ox, oy - fd * 0.5, gz + h * 0.52), mat=MATS["town_glass"])
    return {"obj": body, "x": ox, "y": oy, "gz": gz, "h": h, "tall": tier != 'house'}


def create_town():
    """Downstream town on the graded flood plain: a street grid filled with
    cottages on the outskirts and mid-rise / tower blocks in the core, so the
    spillway discharge floods through its streets. Building bodies are recorded
    in TOWN_BUILDINGS for the Mantaflow collision pass."""
    if not ENABLE_TOWN:
        return []
    coll = COLLS["11_TOWN"]
    _town_materials()
    rng = random.Random(SEED + 1200)
    cy = (TOWN_NEAR_Y + TOWN_FAR_Y) * 0.5
    prof_main = _road_profile(TOWN_STREET_W + 4.0, coll)
    prof_side = _road_profile(TOWN_STREET_W, coll)
    xs = _frange(-TOWN_HALF_WIDTH, TOWN_HALF_WIDTH, TOWN_BLOCK)
    ys = _frange(TOWN_FAR_Y, TOWN_NEAR_Y, TOWN_BLOCK)
    # --- street grid (ribbons follow the graded plain) -----------------------
    n_st = 0
    for j, sy in enumerate(ys):
        pts = [(x, sy, terrain_height(x, sy) + 0.20)
               for x in _frange(-TOWN_HALF_WIDTH, TOWN_HALF_WIDTH, 12.0)]
        _road_curve("TOWN_St_EW_%02d" % j, pts, coll, MATS["town_road"],
                    prof_main if j % 2 == 0 else prof_side)
        n_st += 1
    for i, sx in enumerate(xs):
        pts = [(sx, y, terrain_height(sx, y) + 0.20)
               for y in _frange(TOWN_FAR_Y, TOWN_NEAR_Y, 12.0)]
        _road_curve("TOWN_St_NS_%02d" % i, pts, coll, MATS["town_road"],
                    prof_side if i % 2 else prof_main)
        n_st += 1
    # --- building blocks between the streets ---------------------------------
    plot = TOWN_BLOCK - TOWN_STREET_W
    buildings = []
    for bx in xs[:-1]:
        for by in ys[:-1]:
            cxb, cyb = bx + TOWN_BLOCK * 0.5, by + TOWN_BLOCK * 0.5
            dist = math.hypot(cxb, cyb - cy)
            tier = ('tower' if dist < TOWN_CORE_RADIUS else
                    'midrise' if dist < TOWN_CORE_RADIUS * 1.9 else 'house')
            sub = 1 if tier != 'house' else 2       # denser small houses outside
            step = plot / sub
            for pu in range(sub):
                for pv in range(sub):
                    ox = cxb - plot * 0.5 + step * (pu + 0.5)
                    oy = cyb - plot * 0.5 + step * (pv + 0.5)
                    rec = _town_building(coll, ox, oy, tier, rng,
                                         len(buildings), step)
                    if rec:
                        buildings.append(rec)
    TOWN_BUILDINGS.extend(buildings)
    log("Town: %d streets, %d buildings on the flood plain." % (n_st, len(buildings)))
    return buildings


def _tree_mesh(name, kind, rng):
    """Low-poly tree as ONE mesh (slot 0 = bark, slot 1 = leaves)."""
    bm = bmesh.new()
    trunk_h = rng.uniform(2.0, 4.0)
    trunk_r = rng.uniform(0.18, 0.35)
    bmesh.ops.create_cone(bm, cap_ends=True, segments=7,
                          radius1=trunk_r * 1.25, radius2=trunk_r, depth=trunk_h,
                          matrix=Matrix.Translation((0, 0, trunk_h * 0.5)))
    if kind == 'pine':
        z = trunk_h
        for k in range(3):
            r = rng.uniform(1.7, 2.3) * (1.0 - k * 0.22)
            h = rng.uniform(2.2, 3.0)
            bmesh.ops.create_cone(bm, cap_ends=True, segments=9, radius1=r,
                                  radius2=0.02, depth=h,
                                  matrix=Matrix.Translation((0, 0, z + h * 0.5 - 0.3)))
            z += h * 0.6
    else:
        r = rng.uniform(1.9, 2.8)
        bmesh.ops.create_icosphere(bm, subdivisions=1, radius=r,
                                   matrix=Matrix.Translation((0, 0, trunk_h + r * 0.65)))
    bm.faces.ensure_lookup_table()
    for f in bm.faces:
        f.material_index = 1 if f.calc_center_median().z > trunk_h * 0.85 else 0
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    return mesh

def create_vegetation():
    """Instanced low-poly trees: a few base meshes, many linked-data copies."""
    coll = COLLS["07_VEGETATION"]
    rng = random.Random(SEED + 909)
    bark = _flat_material("MAT_Bark", (0.20, 0.13, 0.07), 0.9)
    leaf_cols = [(0.10, 0.28, 0.08), (0.14, 0.34, 0.10), (0.08, 0.22, 0.06)]
    leaves = [_flat_material("MAT_Leaf_%d" % i, c, 0.85)
              for i, c in enumerate(leaf_cols)]
    bases = []
    for i, kind in enumerate(['pine', 'broad', 'broad', 'pine']):
        m = _tree_mesh("VEG_base_%d" % i, kind, random.Random(SEED + i * 31))
        m.materials.append(bark)
        m.materials.append(leaves[i % len(leaves)])
        bases.append(m)
    count = 30 if DEBUG_MODE else 140
    placed = 0
    attempts = 0
    while placed < count and attempts < count * 8:
        attempts += 1
        x = rng.uniform(-ENV_WIDTH * 0.48, ENV_WIDTH * 0.48)
        y = rng.uniform(-120.0, -ENV_DEPTH * 0.5)
        gz = terrain_height(x, y)
        if gz < TOE_Z + 1.0:                          # not in the wet channel
            continue
        slope = (abs(terrain_height(x + 3, y) - gz) +
                 abs(terrain_height(x, y + 3) - gz)) / 3.0
        if slope > 0.9:                               # avoid steep exposed rock
            continue
        s = rng.uniform(0.7, 1.6)
        o = bpy.data.objects.new("TREE_%03d" % placed, rng.choice(bases))
        link_object(o, coll)
        o.location = Vector((x, y, gz))
        o.scale = Vector((s * rng.uniform(0.8, 1.2), s * rng.uniform(0.8, 1.2),
                          s * rng.uniform(0.9, 1.3)))
        o.rotation_euler = Euler((0, 0, rng.uniform(0, 6.28)))
        placed += 1
    log("Created %d trees over %d base meshes." % (placed, len(bases)))

def _road_profile(width, coll):
    prof = bpy.data.curves.new("ROAD_Profile", "CURVE")
    prof.dimensions = '2D'
    sp = prof.splines.new('POLY')
    sp.points.add(1)
    h = width * 0.5
    sp.points[0].co = (-h, 0.0, 0.0, 1.0)
    sp.points[1].co = (h, 0.0, 0.0, 1.0)
    o = bpy.data.objects.new("ROAD_Profile", prof)
    link_object(o, coll)
    o.hide_render = True
    o.hide_viewport = True
    return o


def _road_curve(name, pts, coll, mat, profile):
    cu = bpy.data.curves.new(name, "CURVE")
    cu.dimensions = '3D'
    cu.bevel_object = profile
    cu.use_fill_caps = True
    sp = cu.splines.new('POLY')
    sp.points.add(len(pts) - 1)
    for i, p in enumerate(pts):
        sp.points[i].co = (p[0], p[1], p[2], 1.0)
    o = bpy.data.objects.new(name, cu)
    link_object(o, coll)
    cu.materials.append(mat)
    return o

def create_roads(bays):
    """Curve-based roads: the dam crest road plus downstream approach roads."""
    coll = COLLS["08_ROADS"]
    asphalt = _flat_material("MAT_Asphalt", (0.045, 0.045, 0.05), 0.85)
    prof_wide = _road_profile(9.0, coll)
    prof_narrow = _road_profile(6.0, coll)
    # crest road following the curved dam top
    crest = [(b['pos'].x, b['pos'].y, CREST_ROAD_Z + 0.45) for b in bays]
    if crest:
        first, last = bays[0], bays[-1]
        crest.insert(0, (first['pos'].x * 1.06 - 18.0, first['pos'].y,
                         CREST_ROAD_Z + 0.45))
        crest.append((last['pos'].x * 1.06 + 18.0, last['pos'].y,
                      CREST_ROAD_Z + 0.45))
        _road_curve("ROAD_Crest", crest, coll, asphalt, prof_wide)
    # left-bank approach descending toward the village
    rng = random.Random(SEED + 313)
    approach = []
    x0 = -DAM_LENGTH * 0.55 - 20.0
    for k in range(9):
        f = k / 8.0
        x = x0 - f * (ENV_WIDTH * 0.30)
        y = -30.0 - f * (ENV_DEPTH * 0.42)
        x += rng.uniform(-14.0, 14.0)
        approach.append((x, y, terrain_height(x, y) + 0.4))
    _road_curve("ROAD_Approach_L", approach, coll, asphalt, prof_narrow)
    # right-bank downstream road
    river = []
    x1 = DAM_LENGTH * 0.45
    for k in range(9):
        f = k / 8.0
        x = x1 + rng.uniform(-12.0, 12.0)
        y = -60.0 - f * (DOWNSTREAM_LENGTH)
        river.append((x, y, terrain_height(x, y) + 0.4))
    _road_curve("ROAD_River_R", river, coll, asphalt, prof_narrow)
    log("Created 3 roads (crest + 2 downstream).")

def setup_lighting():
    """Cinematic daylight: warm key sun + cool fill sun (scale-independent)."""
    coll = COLLS["09_LIGHTING"]
    key = bpy.data.lights.new("SUN_Key", "SUN")
    key.energy = 4.5
    key.color = (1.0, 0.95, 0.84)
    set_attr_safe(key, "angle", math.radians(1.5))       # soft-edged shadows
    ko = bpy.data.objects.new("SUN_Key", key)
    link_object(ko, coll)
    ko.location = (250.0, -250.0, 500.0)
    ko.rotation_euler = Euler((math.radians(52.0), math.radians(6.0),
                               math.radians(38.0)))
    fill = bpy.data.lights.new("SUN_Fill", "SUN")
    fill.energy = 1.1
    fill.color = (0.72, 0.82, 1.0)                        # cool sky bounce
    set_attr_safe(fill, "angle", math.radians(4.0))
    fo = bpy.data.objects.new("SUN_Fill", fill)
    link_object(fo, coll)
    fo.rotation_euler = Euler((math.radians(60.0), 0.0, math.radians(-140.0)))
    log("Lighting: key + fill suns created.")

def setup_world():
    """Procedural daytime Nishita sky with dust haze (flat-blue fallback)."""
    world = bpy.data.worlds.get("World") or bpy.data.worlds.new("World")
    bpy.context.scene.world = world
    world.use_nodes = True
    nt = world.node_tree
    nt.nodes.clear()
    bg = nt.nodes.new("ShaderNodeBackground")
    out = nt.nodes.new("ShaderNodeOutputWorld")
    bg.location = (0, 0)
    out.location = (240, 0)
    try:
        sky = nt.nodes.new("ShaderNodeTexSky")
        sky.location = (-280, 0)
        set_enum_safe(sky, "sky_type", ['NISHITA', 'HOSEK_WILKIE', 'PREETHAM'])
        set_attr_safe(sky, "sun_elevation", math.radians(38.0))
        set_attr_safe(sky, "sun_rotation", math.radians(220.0))
        set_attr_safe(sky, "altitude", 300.0)
        set_attr_safe(sky, "air_density", 1.2)
        set_attr_safe(sky, "dust_density", 3.0)        # daytime atmospheric haze
        set_attr_safe(sky, "ozone_density", 1.0)
        set_attr_safe(sky, "sun_intensity", 0.3)
        set_attr_safe(sky, "sun_disc", False)          # our sun lamps are the key
        nt.links.new(sky.outputs[0], bg.inputs["Color"])
    except Exception as e:
        log("  (sky texture unavailable: %s; flat blue sky)" % e)
        bg.inputs["Color"].default_value = (0.16, 0.30, 0.56, 1.0)
    bg.inputs["Strength"].default_value = 1.0
    nt.links.new(bg.outputs["Background"], out.inputs["Surface"])
    log("World sky created.")

def _add_camera(name, loc, lens, coll, target):
    cd = bpy.data.cameras.new(name)
    cd.lens = lens
    set_attr_safe(cd, "clip_start", 0.5)
    set_attr_safe(cd, "clip_end", 12000.0)          # scene spans ~2 km
    o = bpy.data.objects.new(name, cd)
    link_object(o, coll)
    o.location = Vector(loc)
    c = o.constraints.new('TRACK_TO')
    c.target = target
    set_enum_safe(c, "track_axis", ['TRACK_NEGATIVE_Z'])
    set_enum_safe(c, "up_axis", ['UP_Y'])
    return o


def create_cameras(bays):
    coll = COLLS["10_CAMERAS"]
    xmin, xmax, _, _ = open_bays_bounds(bays, pad=0.0)
    cx = (xmin + xmax) * 0.5
    tgt = add_empty("CAM_TARGET", location=(cx, -120.0, TOE_Z + 8.0),
                    coll=coll, size=6.0)
    cams = {
        'aerial': _add_camera("CAM_AERIAL", (cx * 0.4, 260.0, 340.0), 35.0, coll, tgt),
        'down': _add_camera("CAM_DOWNSTREAM", (cx + 30.0, -340.0, 58.0), 50.0, coll, tgt),
        'close': _add_camera("CAM_CLOSE_WATER", (cx + 55.0, -140.0, 24.0), 28.0, coll, tgt),
    }
    # top-down orthographic "minimap" over the whole dam -> town flood corridor
    corr_y = (TOWN_FAR_Y * 0.5) if ENABLE_TOWN else -260.0
    span = (abs(TOWN_FAR_Y) + 160.0) if ENABLE_TOWN else 520.0
    map_tgt = add_empty("CAM_MAP_TARGET", location=(0.0, corr_y, 0.0),
                        coll=coll, size=6.0)
    cams['map'] = _add_camera("CAM_MINIMAP", (0.0, corr_y + 0.01, span * 1.2),
                              50.0, coll, map_tgt)
    set_enum_safe(cams['map'].data, "type", ['ORTHO'])
    set_attr_safe(cams['map'].data, "ortho_scale", span * 2.1)
    # eye-level view looking back over the town toward the dam (flood front)
    if ENABLE_TOWN:
        ty = (TOWN_NEAR_Y + TOWN_FAR_Y) * 0.5
        town_tgt = add_empty("CAM_TOWN_TARGET", location=(0.0, ty, 4.0),
                             coll=coll, size=6.0)
        cams['town'] = _add_camera("CAM_TOWN", (TOWN_HALF_WIDTH * 0.7,
                                   TOWN_FAR_Y - 150.0, 72.0), 40.0, coll, town_tgt)
    bpy.context.scene.camera = cams['down']
    log("Created %d cameras + tracking targets." % len(cams))
    return cams, tgt

def animate_camera(cams):
    """Optional slow aerial push-in across the sim (TRACK_TO keeps it aimed)."""
    if not ENABLE_CAMERA_ANIMATION:
        return
    cam = cams['aerial']
    bpy.context.scene.camera = cam
    start = Vector((cam.location.x - 120.0, 420.0, 430.0))
    end = Vector((cam.location.x + 40.0, 120.0, 180.0))
    cam.location = start
    cam.keyframe_insert("location", frame=CACHE_FRAME_START)
    cam.location = end
    cam.keyframe_insert("location", frame=CACHE_FRAME_END)
    try:
        act = cam.animation_data.action if cam.animation_data else None
        if act:
            for fc in act.fcurves:
                for kp in fc.keyframe_points:
                    kp.interpolation = 'BEZIER'
                    kp.handle_left_type = 'AUTO_CLAMPED'
                    kp.handle_right_type = 'AUTO_CLAMPED'
    except Exception:
        pass
    log("Camera fly-through keyframed on CAM_AERIAL.")

def setup_render():
    """Version-safe engine + resolution + color management."""
    scene = bpy.context.scene
    r = scene.render
    try:
        engines = [i.identifier for i in scene.bl_rna.properties['engine'].enum_items]
    except Exception:
        engines = []
    for eng in ('BLENDER_EEVEE_NEXT', 'BLENDER_EEVEE', 'CYCLES'):
        if eng in engines:
            r.engine = eng
            break
    log("Render engine: %s" % r.engine)
    r.resolution_x = RENDER_RES_X
    r.resolution_y = RENDER_RES_Y
    r.resolution_percentage = 50 if DEBUG_MODE else 100
    r.fps = FPS
    scene.frame_start = CACHE_FRAME_START
    scene.frame_end = CACHE_FRAME_END
    ee = getattr(scene, "eevee", None)
    if ee:                                            # names differ across 4.x
        for p, v in (("use_bloom", True), ("use_gtao", True), ("use_ssr", True),
                     ("use_ssr_refraction", True), ("use_raytracing", True),
                     ("use_volumetric_lights", True), ("taa_render_samples", 64)):
            set_attr_safe(ee, p, v)
    cy = getattr(scene, "cycles", None)
    if cy and r.engine == 'CYCLES':
        set_attr_safe(cy, "samples", 48 if DEBUG_MODE else 160)
        set_enum_safe(cy, "device", ['GPU', 'CPU'])
    try:
        vs = scene.view_settings
        set_enum_safe(vs, "view_transform", ['AgX', 'Filmic', 'Standard'])
        set_enum_safe(vs, "look", ['AgX - Medium High Contrast',
                                   'Medium High Contrast', 'None'])
        vs.exposure = 0.0
        vs.gamma = 1.0
    except Exception as e:
        log("  (color management: %s)" % e)
    log("Render %dx%d @ %dfps, frames %d-%d." % (RENDER_RES_X, RENDER_RES_Y,
        FPS, CACHE_FRAME_START, CACHE_FRAME_END))

def setup_compositor():
    """Subtle fog-glow bloom on highlights (fully guarded)."""
    scene = bpy.context.scene
    try:
        scene.use_nodes = True
        nt = scene.node_tree
        nt.nodes.clear()
        rl = nt.nodes.new("CompositorNodeRLayers")
        glare = nt.nodes.new("CompositorNodeGlare")
        set_enum_safe(glare, "glare_type", ['FOG_GLOW', 'BLOOM', 'STREAKS'])
        set_enum_safe(glare, "quality", ['MEDIUM' if DEBUG_MODE else 'HIGH',
                                         'MEDIUM', 'LOW'])
        set_attr_safe(glare, "threshold", 1.0)
        set_attr_safe(glare, "mix", -0.25)
        comp = nt.nodes.new("CompositorNodeComposite")
        rl.location = (-320, 0)
        glare.location = (0, 0)
        comp.location = (320, 0)
        nt.links.new(rl.outputs["Image"], glare.inputs["Image"])
        nt.links.new(glare.outputs["Image"], comp.inputs["Image"])
        log("Compositor: fog-glow glare added.")
    except Exception as e:
        log("  (compositor skipped: %s)" % e)

def save_blend():
    """Save the .blend, falling back to ~/mettur_dam if // cannot resolve."""
    path = bpy.path.abspath(OUTPUT_FILE)
    if OUTPUT_FILE.startswith("//") and not bpy.data.filepath:
        path = os.path.join(os.path.expanduser("~"), "mettur_dam",
                            os.path.basename(OUTPUT_FILE.strip("/")))
    try:
        d = os.path.dirname(path)
        if d:
            os.makedirs(d, exist_ok=True)
        bpy.ops.wm.save_as_mainfile(filepath=path)
        log("Saved .blend -> %s" % path)
        return path
    except Exception as e:
        log("ERROR saving .blend: %s" % e)
        return None


def bake_fluid(domain):
    """Bake all fluid data when AUTO_BAKE is on. Returns True on success."""
    if not AUTO_BAKE:
        return False
    log("AUTO_BAKE enabled: baking fluid - this may take a long time...")
    try:
        for o in bpy.context.view_layer.objects:
            o.select_set(False)
        domain.select_set(True)
        bpy.context.view_layer.objects.active = domain
        try:
            with bpy.context.temp_override(active_object=domain,
                                           selected_objects=[domain]):
                bpy.ops.fluid.bake_all()
        except (TypeError, RuntimeError):
            bpy.ops.fluid.bake_all()
        log("Fluid bake complete.")
        return True
    except Exception as e:
        log("AUTO_BAKE failed (%s)." % e)
        log("  -> Bake manually: select the LIQUID domain, Physics > Fluid > Bake All.")
        return False

def print_summary(bays, domain, baked, blend_path):
    open_idx = [i for i, b in enumerate(bays) if b["open"]]
    line = "=" * 66
    print("\n" + line)
    print("  METTUR-DAM-INSPIRED MANTAFLOW SCENE - BUILD COMPLETE")
    print(line)
    print("  Modular dam objects     : %d" % len(DAM_OBJECTS))
    print("  Spillway gates          : %d   (OPEN: %s)" % (len(bays), open_idx))
    print("  Water domain (FLIP)     : %s" % (domain.name if domain else "MISSING!"))
    print("  Domain resolution max   : %d" % DOMAIN_RESOLUTION)
    print("  Sim frames              : %d - %d  @ %d fps" %
          (CACHE_FRAME_START, CACHE_FRAME_END, FPS))
    print("  Whitewater (foam/spray) : %s" % ("ON" if ENABLE_WHITEWATER else "OFF"))
    _eff = min(len(TOWN_BUILDINGS), 24 if DEBUG_MODE else 60) if TOWN_FLOOD_ZONE else 0
    print("  Town buildings          : %d  (on flood plain, %d as water effectors)"
          % (len(TOWN_BUILDINGS), _eff))
    print("  Cache type              : %s" % SIM_CACHE_TYPE)
    print("  Cache directory         : %s" % (CACHE_DIR or "(unset)"))
    print("  Saved .blend            : %s" % (blend_path or "NOT SAVED"))
    print("  DEBUG_MODE              : %s" % DEBUG_MODE)
    print(line)
    if baked:
        print("  FLUID IS BAKED. Scrub / play the timeline to watch the discharge.")
    elif SIM_CACHE_TYPE == 'REPLAY':
        print("  CACHE = REPLAY: just press SPACEBAR / play the timeline.")
        print("     Mantaflow simulates on playback - water pours through the OPEN")
        print("     gates, down the chute and floods the town streets below.")
        print("     Play from frame 1 so the cache builds in order (don't jump ahead).")
        if ENABLE_WHITEWATER:
            print("     Foam/spray: select the domain > Physics > Fluid > Bake All.")
    else:
        print("  >> BAKE REQUIRED to see water <<")
        print("     1. Select the LIQUID domain object '%s'." %
              (domain.name if domain else "WATER_Domain"))
        print("     2. Properties > Physics > Fluid > click 'Bake All'.")
        print("     3. Play the timeline: water flows through the OPEN gates only.")
        print("     (Set AUTO_BAKE = True at the top to bake on run.)")
    print(line + "\n")

def main():
    random.seed(SEED)
    log("=== Building Mettur-dam Mantaflow scene (DEBUG_MODE=%s) ===" % DEBUG_MODE)
    clear_scene()
    setup_scene()
    create_collections()
    create_materials()
    # environment + terrain
    create_terrain()
    create_reservoir()
    # dam + gates (curved arc, modular objects, real hinged gates)
    bays = compute_bays()
    create_dam(bays)
    create_gates(bays)
    animate_gates()
    create_downstream_channels()
    # environment dressing
    rocks = create_rocks(bays)
    create_houses()
    create_town()
    create_vegetation()
    create_roads(bays)
    # === Mantaflow FLIP liquid: domain + inflow-at-open-gates + collisions ===
    domain = create_water_domain(bays)
    create_water_inflow(bays)
    create_water_obstacle_geometry(bays, rocks)
    configure_mantaflow(domain)
    # lighting / sky / cameras / output
    setup_lighting()
    setup_world()
    cams, _ = create_cameras(bays)
    animate_camera(cams)
    setup_render()
    setup_compositor()
    # bake (optional) + save + report
    baked = bake_fluid(domain)
    blend_path = save_blend()
    print_summary(bays, domain, baked, blend_path)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        import traceback
        print("\n" + "!" * 66)
        print("SCRIPT FAILED")
        print("  WHAT : an exception stopped the build -> %r" % exc)
        print("  WHY  : see the full traceback printed below.")
        print("  FIX  : run in Blender 4.x, read the traceback's last frame,")
        print("         set DEBUG_MODE=True for a lighter build, and re-run.")
        print("!" * 66 + "\n")
        traceback.print_exc()
