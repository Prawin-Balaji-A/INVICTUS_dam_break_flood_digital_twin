# ==============================================================
#  generate_dam.py
#  High-detail 3D concrete gravity dam generator for Blender
#  ------------------------------------------------------------
#  Run:   blender --background --python generate_dam.py
#  or paste into the Blender Text Editor and hit "Run Script".
#
#  Produces: concrete gravity dam + central spillway + radial
#  gates + stilling basin + crest works + materials + cameras
#  + lighting + gate animation + rigid-body setup.
#
#  NO terrain, NO water, NO vegetation, NO buildings.
# ==============================================================

import bpy
import bmesh
import math
import os
import random
from mathutils import Vector

random.seed(7)

# ==============================================================
# 1.  MASTER DIMENSIONS  (metres)
# ==============================================================
DAM_LEN_HALF   = 210.0          # dam runs  x = -210 .. +210  (420 m long)
CREST_Z        = 120.0          # crest elevation
FOUNDATION_Z   = -18.0          # bottom of the concrete mass
FOUNDATION_BOT = -30.0          # bottom of the foundation mat

UP_Y_TOP       = -6.0           # upstream face @ crest
UP_Y_BOT       = -14.0          # upstream face @ foundation
DOWN_Y_TOP     = 6.0            # downstream face @ crest
DOWN_Y_TOE     = 104.0          # downstream toe @ foundation

SPILL_CREST_Z  = 108.0          # ogee crest elevation
SPILL_HALF     = 60.0           # half-length of the spillway section
FLANK_W        = 8.0            # thickness of the end / flank walls
PIER_W         = 3.5            # intermediate pier thickness
N_BAYS         = 5              # number of spillway bays
PIER_TOP_Z     = 122.0          # top of the piers

SPILL_INNER_HALF = SPILL_HALF - FLANK_W
BAY_W = (2.0 * SPILL_INNER_HALF - (N_BAYS - 1) * PIER_W) / float(N_BAYS)

# ---- radial (Tainter) gate geometry, measured in the Y-Z plane
GATE_SILL      = (-2.0, SPILL_CREST_Z)
GATE_TRUNNION  = (14.0, 112.0)
GATE_R         = math.hypot(GATE_TRUNNION[0] - GATE_SILL[0],
                            GATE_TRUNNION[1] - GATE_SILL[1])
GATE_PHI_BOT   = math.atan2(GATE_SILL[1] - GATE_TRUNNION[1],
                            GATE_SILL[0] - GATE_TRUNNION[0])
GATE_PHI_TOP   = GATE_PHI_BOT - math.radians(60.0)
GATE_OPEN_DEG  = 40.0            # max opening rotation
GATE_WIDTH     = BAY_W - 0.4

GATE_OBJECTS   = []              # filled while building
DAM_OBJECTS    = []              # static structure (used for rigid body)


# ==============================================================
# 2.  SMALL HELPERS
# ==============================================================
def link_obj(obj, coll):
    """Link an object into exactly one collection."""
    for c in list(obj.users_collection):
        c.objects.unlink(obj)
    coll.objects.link(obj)


def new_collection(name, parent):
    c = bpy.data.collections.new(name)
    parent.children.link(c)
    return c


class MeshBuilder:
    """Accumulates vertices / faces so several primitives can be
    merged into one single Blender object."""

    def __init__(self):
        self.verts = []
        self.faces = []

    # ----------------------------------------------------------
    def add_prism(self, profile, x0, x1):
        """profile : list of (y, z) describing a closed polygon.
           The polygon is extruded along X from x0 to x1."""
        n = len(profile)
        if n < 3:
            return
        base = len(self.verts)
        for (y, z) in profile:
            self.verts.append((x0, y, z))
        for (y, z) in profile:
            self.verts.append((x1, y, z))

        for i in range(n):
            j = (i + 1) % n
            self.faces.append((base + i, base + j,
                               base + n + j, base + n + i))
        self.faces.append(tuple(range(base + n - 1, base - 1, -1)))
        self.faces.append(tuple(range(base + n, base + 2 * n)))

    # ----------------------------------------------------------
    def add_box(self, x0, x1, y0, y1, z0, z1):
        self.add_prism([(y0, z0), (y1, z0), (y1, z1), (y0, z1)], x0, x1)

    # ----------------------------------------------------------
    def add_cylinder_x(self, radius, cx0, cx1, cy, cz, segments=16):
        base = len(self.verts)
        for i in range(segments):
            a = 2.0 * math.pi * i / segments
            self.verts.append((cx0, cy + radius * math.cos(a),
                                    cz + radius * math.sin(a)))
        for i in range(segments):
            a = 2.0 * math.pi * i / segments
            self.verts.append((cx1, cy + radius * math.cos(a),
                                    cz + radius * math.sin(a)))
        for i in range(segments):
            j = (i + 1) % segments
            self.faces.append((base + i, base + j,
                               base + segments + j, base + segments + i))
        self.faces.append(tuple(range(base + segments - 1, base - 1, -1)))
        self.faces.append(tuple(range(base + segments, base + 2 * segments)))

    # ----------------------------------------------------------
    def build(self, name, coll, mat=None, bevel=None):
        if not self.verts:
            return None
        mesh = bpy.data.meshes.new(name + "_mesh")
        mesh.from_pydata(self.verts, [], self.faces)
        mesh.validate(verbose=False)
        mesh.update()

        bm = bmesh.new()
        bm.from_mesh(mesh)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        bm.to_mesh(mesh)
        bm.free()

        obj = bpy.data.objects.new(name, mesh)
        if mat:
            obj.data.materials.append(mat)
        link_obj(obj, coll)

        if bevel:
            m = obj.modifiers.new("Bevel", 'BEVEL')
            m.width = bevel
            m.segments = 2
            m.limit_method = 'ANGLE'
            m.angle_limit = math.radians(35.0)
        return obj


def add_bevel(obj, width=0.12, segments=2, angle=35.0):
    m = obj.modifiers.new("Bevel", 'BEVEL')
    m.width = width
    m.segments = segments
    m.limit_method = 'ANGLE'
    m.angle_limit = math.radians(angle)


# ==============================================================
# 3.  MATERIALS  (fully procedural)
# ==============================================================
def _clear_nodes(nt):
    for n in list(nt.nodes):
        nt.nodes.remove(n)


def _mix_rgb(nodes, links, blend, fac, col_a, col_b, loc):
    """MixRGB with a fallback for Blender versions that renamed it."""
    try:
        node = nodes.new("ShaderNodeMixRGB")
        node.blend_type = blend
        node.inputs["Fac"].default_value = fac
        links.new(col_a, node.inputs["Color1"])
        links.new(col_b, node.inputs["Color2"])
        node.location = loc
        return node.outputs["Color"]
    except Exception:
        node = nodes.new("ShaderNodeMix")
        node.data_type = 'RGBA'
        node.blend_type = blend
        node.location = loc
        for sock in node.inputs:
            if sock.name == "Factor":
                sock.default_value = fac
        links.new(col_a, node.inputs[6])
        links.new(col_b, node.inputs[7])
        return node.outputs[2]


def create_concrete_material(name,
                             base=(0.67, 0.67, 0.65),
                             dark=(0.46, 0.46, 0.45),
                             stain_dark=(0.36, 0.35, 0.33),
                             roughness=0.88,
                             noise_scale=0.014,
                             stain_scale=0.0035,
                             bump=0.30):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nodes, links = nt.nodes, nt.links
    _clear_nodes(nt)

    out = nodes.new("ShaderNodeOutputMaterial"); out.location = (1100, 0)
    bsdf = nodes.new("ShaderNodeBsdfPrincipled"); bsdf.location = (800, 0)
    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])

    tc = nodes.new("ShaderNodeTexCoord"); tc.location = (-1300, 0)

    # --- large scale colour blotching -------------------------
    n1 = nodes.new("ShaderNodeTexNoise"); n1.location = (-1100, 320)
    n1.inputs["Scale"].default_value = noise_scale
    n1.inputs["Detail"].default_value = 6.0
    n1.inputs["Roughness"].default_value = 0.55
    links.new(tc.outputs["Object"], n1.inputs["Vector"])

    r1 = nodes.new("ShaderNodeValToRGB"); r1.location = (-880, 320)
    r1.color_ramp.elements[0].position = 0.38
    r1.color_ramp.elements[0].color = (*dark, 1.0)
    r1.color_ramp.elements[1].position = 0.64
    r1.color_ramp.elements[1].color = (*base, 1.0)
    links.new(n1.outputs["Fac"], r1.inputs["Fac"])

    # --- fine surface grain -----------------------------------
    n2 = nodes.new("ShaderNodeTexNoise"); n2.location = (-1100, 60)
    n2.inputs["Scale"].default_value = noise_scale * 70.0
    n2.inputs["Detail"].default_value = 8.0
    n2.inputs["Roughness"].default_value = 0.7
    links.new(tc.outputs["Object"], n2.inputs["Vector"])

    # --- weathering / stains ----------------------------------
    n3 = nodes.new("ShaderNodeTexNoise"); n3.location = (-1100, -220)
    n3.inputs["Scale"].default_value = stain_scale
    n3.inputs["Detail"].default_value = 5.0
    n3.inputs["Roughness"].default_value = 0.75
    links.new(tc.outputs["Object"], n3.inputs["Vector"])

    r3 = nodes.new("ShaderNodeValToRGB"); r3.location = (-880, -220)
    r3.color_ramp.elements[0].position = 0.28
    r3.color_ramp.elements[0].color = (*stain_dark, 1.0)
    r3.color_ramp.elements[1].position = 0.58
    r3.color_ramp.elements[1].color = (1.0, 1.0, 1.0, 1.0)
    links.new(n3.outputs["Fac"], r3.inputs["Fac"])

    col = _mix_rgb(nodes, links, 'MULTIPLY', 0.85,
                   r1.outputs["Color"], r3.outputs["Color"], (-560, 200))
    links.new(col, bsdf.inputs["Base Color"])

    # --- roughness --------------------------------------------
    r2 = nodes.new("ShaderNodeValToRGB"); r2.location = (-880, 60)
    r2.color_ramp.elements[0].position = 0.30
    r2.color_ramp.elements[0].color = (max(roughness - 0.10, 0.05),) * 3 + (1.0,)
    r2.color_ramp.elements[1].position = 0.72
    r2.color_ramp.elements[1].color = (min(roughness + 0.08, 1.0),) * 3 + (1.0,)
    links.new(n2.outputs["Fac"], r2.inputs["Fac"])
    links.new(r2.outputs["Color"], bsdf.inputs["Roughness"])

    # --- bump --------------------------------------------------
    bmp = nodes.new("ShaderNodeBump"); bmp.location = (500, -320)
    bmp.inputs["Strength"].default_value = bump
    bmp.inputs["Distance"].default_value = 0.35
    links.new(n2.outputs["Fac"], bmp.inputs["Height"])
    links.new(bmp.outputs["Normal"], bsdf.inputs["Normal"])

    bsdf.inputs["Metallic"].default_value = 0.0
    return mat


def create_metal_material(name,
                          base=(0.26, 0.27, 0.29),
                          roughness=0.42,
                          metallic=1.0,
                          wear=0.55):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nodes, links = nt.nodes, nt.links
    _clear_nodes(nt)

    out = nodes.new("ShaderNodeOutputMaterial"); out.location = (800, 0)
    bsdf = nodes.new("ShaderNodeBsdfPrincipled"); bsdf.location = (520, 0)
    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])

    bsdf.inputs["Base Color"].default_value = (*base, 1.0)
    bsdf.inputs["Metallic"].default_value = metallic

    tc = nodes.new("ShaderNodeTexCoord"); tc.location = (-1000, 0)
    n = nodes.new("ShaderNodeTexNoise"); n.location = (-800, 0)
    n.inputs["Scale"].default_value = 0.28
    n.inputs["Detail"].default_value = 7.0
    n.inputs["Roughness"].default_value = 0.6
    links.new(tc.outputs["Object"], n.inputs["Vector"])

    r = nodes.new("ShaderNodeValToRGB"); r.location = (-560, 0)
    r.color_ramp.elements[0].position = 0.30
    r.color_ramp.elements[0].color = (max(roughness * 0.55, 0.05),) * 3 + (1.0,)
    r.color_ramp.elements[1].position = 0.75
    r.color_ramp.elements[1].color = (min(roughness * 1.7, 1.0),) * 3 + (1.0,)
    links.new(n.outputs["Fac"], r.inputs["Fac"])
    links.new(r.outputs["Color"], bsdf.inputs["Roughness"])

    # subtle wear darkening of the base colour
    r2 = nodes.new("ShaderNodeValToRGB"); r2.location = (-560, -260)
    r2.color_ramp.elements[0].position = 0.35
    r2.color_ramp.elements[0].color = (*[c * 0.55 for c in base], 1.0)
    r2.color_ramp.elements[1].position = 0.75
    r2.color_ramp.elements[1].color = (*base, 1.0)
    links.new(n.outputs["Fac"], r2.inputs["Fac"])

    col = _mix_rgb(nodes, links, 'MIX', wear,
                   r2.outputs["Color"], r2.outputs["Color"], (-300, -260))
    links.new(r2.outputs["Color"], bsdf.inputs["Base Color"])

    bmp = nodes.new("ShaderNodeBump"); bmp.location = (260, -320)
    bmp.inputs["Strength"].default_value = 0.10
    links.new(n.outputs["Fac"], bmp.inputs["Height"])
    links.new(bmp.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def create_simple_material(name, color, roughness=0.6, metallic=0.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = (*color, 1.0)
        bsdf.inputs["Roughness"].default_value = roughness
        bsdf.inputs["Metallic"].default_value = metallic
    return mat


# ==============================================================
# 4.  GEOMETRY PROFILES
# ==============================================================
NON_OVERFLOW_PROFILE = [
    (UP_Y_BOT,  FOUNDATION_Z),
    (UP_Y_TOP,  CREST_Z),
    (DOWN_Y_TOP, CREST_Z),
    (DOWN_Y_TOE, FOUNDATION_Z),
]


def spillway_profile():
    """Ogee crest + chute surface for the central spillway section."""
    apex_y = -2.0
    Hd = 10.0                       # design head (m)
    K = 2.0 * (Hd ** 0.85)

    pts = [(UP_Y_BOT, FOUNDATION_Z),
           (UP_Y_TOP, SPILL_CREST_Z),
           (apex_y,   SPILL_CREST_Z)]

    x_end = 14.15                   # where the ogee tangent matches the chute
    steps = 16
    for i in range(1, steps + 1):
        x_ = x_end * i / steps
        y = apex_y + x_
        z = SPILL_CREST_Z - (x_ ** 1.85) / K
        pts.append((y, z))

    pts.append((DOWN_Y_TOE, FOUNDATION_Z))
    return pts


SPILL_PROFILE = spillway_profile()
# slope of the straight chute portion, used for the pier tops
_dy = DOWN_Y_TOE - SPILL_PROFILE[-2][0]
_dz = SPILL_PROFILE[-2][1] - FOUNDATION_Z
CHUTE_SLOPE = _dy / _dz            # H per V


def pier_profile():
    """Vertical wall profile for one spillway pier / flank wall."""
    prof = [(UP_Y_TOP, SPILL_CREST_Z)]      # (-6, 108)
    prof += SPILL_PROFILE[2:]               # ogee + chute  ->  (104, -18)
    # downstream vertical end face + sloped top + flat top
    top_end_z = PIER_TOP_Z - (DOWN_Y_TOE - 4.0) / CHUTE_SLOPE
    prof += [(DOWN_Y_TOE, top_end_z),
             (4.0, PIER_TOP_Z),
             (UP_Y_TOP, PIER_TOP_Z)]
    return prof


PIER_PROFILE = pier_profile()


def bay_centres():
    c = []
    x = -SPILL_INNER_HALF
    for _ in range(N_BAYS):
        c.append(x + BAY_W * 0.5)
        x += BAY_W + PIER_W
    return c


def pier_ranges():
    r = [(-SPILL_HALF, -SPILL_INNER_HALF)]
    x = -SPILL_INNER_HALF
    for _ in range(N_BAYS - 1):
        x0 = x + BAY_W
        r.append((x0, x0 + PIER_W))
        x = x0 + PIER_W
    r.append((SPILL_INNER_HALF, SPILL_HALF))
    return r


# ==============================================================
# 5.  MAIN STRUCTURE
# ==============================================================
def create_dam_body(coll, mat):
    mb = MeshBuilder()
    mb.add_prism(NON_OVERFLOW_PROFILE, -DAM_LEN_HALF, -SPILL_HALF)
    mb.add_prism(NON_OVERFLOW_PROFILE,  SPILL_HALF,  DAM_LEN_HALF)
    obj = mb.build("Dam_Body", coll, mat, bevel=0.30)
    DAM_OBJECTS.append(obj)
    return obj


def create_spillway_section(coll, mat):
    mb = MeshBuilder()
    mb.add_prism(SPILL_PROFILE, -SPILL_HALF, SPILL_HALF)
    obj = mb.build("Spillway_Chute", coll, mat, bevel=0.25)
    DAM_OBJECTS.append(obj)
    return obj


def create_spillway_piers(coll, mat):
    objs = []
    for i, (x0, x1) in enumerate(pier_ranges()):
        mb = MeshBuilder()
        mb.add_prism(PIER_PROFILE, x0, x1)
        obj = mb.build("Spillway_Pier_%02d" % (i + 1), coll, mat, bevel=0.22)
        DAM_OBJECTS.append(obj)
        objs.append(obj)
    return objs


def create_foundation(coll, mat):
    mb = MeshBuilder()
    mb.add_box(-DAM_LEN_HALF - 8.0, DAM_LEN_HALF + 8.0,
               UP_Y_BOT - 14.0, DOWN_Y_TOE + 14.0,
               FOUNDATION_BOT, FOUNDATION_Z)
    obj = mb.build("Foundation_Mat", coll, mat, bevel=0.5)
    DAM_OBJECTS.append(obj)
    return obj


# --------------------------------------------------------------
# 6.  SPILLWAY GATES  (radial / Tainter, fully 3D)
# --------------------------------------------------------------
def create_gate(name, centre_x, coll_steel, coll_mech,
                mat_steel, mat_metal):
    """Build one radial gate.  Object origin == trunnion centre."""
    mb = MeshBuilder()
    R = GATE_R
    t = 0.75
    w = GATE_WIDTH
    ph0, ph1 = GATE_PHI_TOP, GATE_PHI_BOT
    N = 30

    # ---------- curved skin plate ----------
    outer, inner = [], []
    for i in range(N + 1):
        a = ph0 + (ph1 - ph0) * i / N
        outer.append(((R + t * 0.5) * math.cos(a),
                      (R + t * 0.5) * math.sin(a)))
        inner.append(((R - t * 0.5) * math.cos(a),
                      (R - t * 0.5) * math.sin(a)))
    mb.add_prism(outer + inner[::-1], -w * 0.5, w * 0.5)

    # ---------- horizontal stiffener ribs ----------
    for k in range(1, 7):
        a_c = ph0 + (ph1 - ph0) * k / 7.0
        da = math.radians(1.0)
        ri = R + t * 0.5
        ro = ri + 0.45
        p_out, p_in = [], []
        for m in range(5):
            a = a_c - da + 2.0 * da * m / 4.0
            p_out.append((ro * math.cos(a), ro * math.sin(a)))
            p_in.append((ri * math.cos(a), ri * math.sin(a)))
        mb.add_prism(p_out + p_in[::-1], -w * 0.5, w * 0.5)

    # ---------- vertical edge beams ----------
    for xx in (-w * 0.5 + 0.35, w * 0.5 - 0.35):
        rib_o, rib_i = [], []
        for i in range(N + 1):
            a = ph0 + (ph1 - ph0) * i / N
            rib_o.append(((R + t * 0.5 + 0.5) * math.cos(a),
                          (R + t * 0.5 + 0.5) * math.sin(a)))
            rib_i.append(((R - t * 0.5) * math.cos(a),
                          (R - t * 0.5) * math.sin(a)))
        mb.add_prism(rib_o + rib_i[::-1], xx - 0.35, xx + 0.35)

    # ---------- radial arms ----------
    arm_angles = [ph0 + (ph1 - ph0) * f for f in (0.16, 0.5, 0.84)]
    for ax in (-w * 0.5 + 2.2, 0.0, w * 0.5 - 2.2):
        for a in arm_angles:
            ca, sa = math.cos(a), math.sin(a)
            px, py = -sa, ca
            hw = 0.70
            p = [(1.4 * ca + hw * px, 1.4 * sa + hw * py),
                 (R * ca + hw * px,   R * sa + hw * py),
                 (R * ca - hw * px,   R * sa - hw * py),
                 (1.4 * ca - hw * px, 1.4 * sa - hw * py)]
            mb.add_prism(p, ax - 0.75, ax + 0.75)

    # ---------- trunnion shaft + hubs ----------
    mb.add_cylinder_x(0.95, -w * 0.5, w * 0.5, 0.0, 0.0, 20)
    mb.add_cylinder_x(1.70, -w * 0.5 - 0.40, -w * 0.5, 0.0, 0.0, 20)
    mb.add_cylinder_x(1.70,  w * 0.5,  w * 0.5 + 0.40, 0.0, 0.0, 20)

    obj = mb.build(name, coll_steel, mat_steel, bevel=0.05)
    obj.location = (centre_x, GATE_TRUNNION[0], GATE_TRUNNION[1])
    obj.rotation_mode = 'XYZ'
    obj.rotation_euler = (0.0, 0.0, 0.0)

    # ---------- hydraulic lifting mechanism (on the pier) ----------
    mech = MeshBuilder()
    # cylinder body
    mech.add_cylinder_x(1.05, centre_x - 1.5, centre_x + 1.5,
                        GATE_TRUNNION[0] + 10.0, GATE_TRUNNION[1] + 8.0, 16)
    # piston rod towards the gate arm
    mech.add_cylinder_x(0.38, centre_x - 0.6, centre_x + 0.6,
                        GATE_TRUNNION[0] + 1.0, GATE_TRUNNION[1] + 5.0, 12)
    # anchor bracket
    mech.add_box(centre_x - 2.0, centre_x + 2.0,
                 GATE_TRUNNION[0] + 9.0, GATE_TRUNNION[0] + 13.0,
                 GATE_TRUNNION[1] + 6.0, GATE_TRUNNION[1] + 9.5)
    m_obj = mech.build(name + "_Hoist", coll_mech, mat_metal)

    GATE_OBJECTS.append(obj)
    return obj


# ==============================================================
# 7.  STILLING BASIN
# ==============================================================
def create_stilling_basin(coll, mat):
    mb = MeshBuilder()

    # apron slab
    mb.add_box(-68.0, 68.0, 104.0, 182.0, FOUNDATION_BOT, -20.0)
    # end sill
    mb.add_box(-68.0, 68.0, 172.0, 182.0, -20.0, -13.0)
    # side training walls
    for s in (-1.0, 1.0):
        x0 = 68.0 * s
        x1 = 78.0 * s
        if x0 > x1:
            x0, x1 = x1, x0
        mb.add_box(x0, x1, 104.0, 182.0, FOUNDATION_BOT, 6.0)

    # baffle / energy dissipation blocks
    row = 0
    yy = 126.0
    while yy < 168.0:
        xx = -60.0 + (4.0 if row % 2 else 0.0)
        while xx < 58.0:
            mb.add_box(xx, xx + 5.0, yy, yy + 5.0, -20.0, -14.5)
            xx += 10.0
        yy += 12.0
        row += 1

    obj = mb.build("Stilling_Basin", coll, mat, bevel=0.18)
    DAM_OBJECTS.append(obj)
    return obj


# ==============================================================
# 8.  CREST, WALKWAYS, RAILINGS, DETAILS
# ==============================================================
def _railing(mb, x0, x1, y, z_base, height=1.15,
             spacing=4.0, post=0.09, rail=0.06):
    n = max(2, int(abs(x1 - x0) / spacing) + 1)
    for i in range(n):
        x = x0 + (x1 - x0) * i / (n - 1)
        mb.add_box(x - post, x + post, y - post, y + post,
                   z_base, z_base + height)
    for zz in (z_base + height, z_base + height * 0.55):
        mb.add_box(min(x0, x1), max(x0, x1),
                   y - rail, y + rail, zz - rail, zz + rail)


def create_crest(coll_crest, coll_walk, coll_rail, coll_det,
                 mat_conc, mat_old, mat_metal):
    # ---------------- parapets + road on non-overflow sections -----
    mb = MeshBuilder()
    for x0, x1 in ((-DAM_LEN_HALF, -SPILL_HALF), (SPILL_HALF, DAM_LEN_HALF)):
        # road surface
        mb.add_box(x0, x1, -5.2, 5.2, CREST_Z, CREST_Z + 0.25)
        # parapets
        mb.add_box(x0, x1, -6.2, -5.2, CREST_Z, CREST_Z + 1.35)
        mb.add_box(x0, x1,  5.2,  6.2, CREST_Z, CREST_Z + 1.35)
    crest_obj = mb.build("Crest_Roadway", coll_crest, mat_conc, bevel=0.12)

    # ---------------- railings on top of the parapets ---------------
    mb = MeshBuilder()
    for x0, x1 in ((-DAM_LEN_HALF, -SPILL_HALF), (SPILL_HALF, DAM_LEN_HALF)):
        _railing(mb, x0, x1, -5.7, CREST_Z + 1.35)
        _railing(mb, x0, x1,  5.7, CREST_Z + 1.35)
    rail_obj = mb.build("Crest_Railings", coll_rail, mat_metal)

    # ---------------- walkway bridge across the spillway ------------
    mb = MeshBuilder()
    mb.add_box(-SPILL_HALF, SPILL_HALF, -6.0, -3.0,
               PIER_TOP_Z - 0.6, PIER_TOP_Z + 0.3)
    # support brackets on each pier
    for (x0, x1) in pier_ranges():
        mb.add_box(x0 + 0.4, x1 - 0.4, -6.0, -3.0,
                   PIER_TOP_Z - 1.4, PIER_TOP_Z - 0.6)
    walk_obj = mb.build("Crest_Walkway", coll_walk, mat_conc, bevel=0.10)

    mb = MeshBuilder()
    _railing(mb, -SPILL_HALF, SPILL_HALF, -6.0, PIER_TOP_Z + 0.3)
    rail2 = mb.build("Walkway_Railings", coll_rail, mat_metal)

    # ---------------- service buildings & towers --------------------
    mb = MeshBuilder()
    buildings = [(-168.0, -146.0), (146.0, 168.0)]
    for (x0, x1) in buildings:
        mb.add_box(x0, x1, -4.0, 4.5, CREST_Z, CREST_Z + 7.0)
        mb.add_box(x0 - 0.8, x1 + 0.8, -4.8, 5.3,
                   CREST_Z + 7.0, CREST_Z + 7.8)
    b_obj = mb.build("Service_Buildings", coll_crest, mat_old, bevel=0.2)

    # tall intake / gate tower
    mb = MeshBuilder()
    mb.add_box(-26.0, -14.0, -13.0, -2.0, FOUNDATION_Z, CREST_Z + 18.0)
    mb.add_box(-27.5, -12.5, -14.5, -0.5,
               CREST_Z + 18.0, CREST_Z + 20.0)
    t_obj = mb.build("Service_Tower", coll_crest, mat_old, bevel=0.3)

    # ---------------- machinery houses on the spillway piers --------
    mb = MeshBuilder()
    for (x0, x1) in pier_ranges():
        mb.add_box(x0 + 0.5, x1 - 0.5, -1.0, 4.0,
                   PIER_TOP_Z, PIER_TOP_Z + 4.0)
        mb.add_box(x0 + 0.0, x1 - 0.0, -1.8, 4.8,
                   PIER_TOP_Z + 4.0, PIER_TOP_Z + 4.8)
    m_obj = mb.build("Gate_Machinery_Houses", coll_det, mat_old, bevel=0.2)

    # ---------------- maintenance walkway along the chute ----------
    mb = MeshBuilder()
    for (x0, x1) in pier_ranges():
        mb.add_box(x0 + 0.2, x1 - 0.2, 20.0, 100.0, 0.0, 0.5)
    # handrails along those walkways
    for (x0, x1) in pier_ranges():
        for yy in (20.0, 100.0):
            mb.add_box(x0 + 0.2, x1 - 0.2, yy - 0.1, yy + 0.1, 0.5, 1.5)
    w_obj = mb.build("Maintenance_Walkways", coll_walk, mat_conc, bevel=0.08)

    # ---------------- drainage channels on the crest ---------------
    mb = MeshBuilder()
    for x0, x1 in ((-DAM_LEN_HALF, -SPILL_HALF), (SPILL_HALF, DAM_LEN_HALF)):
        mb.add_box(x0, x1, -0.35, 0.35, CREST_Z + 0.25, CREST_Z + 0.45)
    d_obj = mb.build("Drainage_Channels", coll_det, mat_old, bevel=0.06)

    return [crest_obj, rail_obj, walk_obj, rail2, b_obj,
            t_obj, m_obj, w_obj, d_obj]


def create_expansion_joints(coll, mat):
    """Vertical contraction joints on the dam faces."""
    mb = MeshBuilder()

    def strip(x, p0, p1, normal, half_w=0.16, offset=0.06):
        (y0, z0), (y1, z1) = p0, p1
        dy, dz = y1 - y0, z1 - z0
        L = math.hypot(dy, dz)
        if L < 1e-6:
            return
        uy, uz = dy / L, dz / L
        py, pz = -uz, uy
        ny, nz = normal
        pts = [(y0 + py * half_w + ny * offset, z0 + pz * half_w + nz * offset),
               (y1 + py * half_w + ny * offset, z1 + pz * half_w + nz * offset),
               (y1 - py * half_w + ny * offset, z1 - pz * half_w + nz * offset),
               (y0 - py * half_w + ny * offset, z0 - pz * half_w + nz * offset)]
        mb.add_prism(pts, x - 0.16, x + 0.16)

    # --- downstream face: normal points downstream / up ---
    d_dy, d_dz = DOWN_Y_TOE - DOWN_Y_TOP, FOUNDATION_Z - CREST_Z
    Ld = math.hypot(d_dy, d_dz)
    n_down = (d_dz / Ld * -1.0, d_dy / Ld)
    # make sure the normal points away from the dam (+Y / +Z)
    if n_down[0] < 0:
        n_down = (-n_down[0], -n_down[1])

    xs = []
    x = -DAM_LEN_HALF + 18.0
    while x < DAM_LEN_HALF:
        xs.append(x)
        x += 18.0
    for x in xs:
        if abs(x) < SPILL_HALF + 1e-6:
            continue
        strip(x, (DOWN_Y_TOP, CREST_Z), (DOWN_Y_TOE, FOUNDATION_Z), n_down)

    # --- upstream face ---
    u_dy, u_dz = UP_Y_TOP - UP_Y_BOT, CREST_Z - FOUNDATION_Z
    Lu = math.hypot(u_dy, u_dz)
    n_up = (-u_dz / Lu, u_dy / Lu)
    if n_up[0] > 0:
        n_up = (-n_up[0], -n_up[1])
    for x in xs:
        if abs(x) < SPILL_HALF + 1e-6:
            continue
        strip(x, (UP_Y_BOT, FOUNDATION_Z), (UP_Y_TOP, CREST_Z), n_up)

    # --- horizontal construction lifts on the downstream face ---
    for zz in (104.0, 88.0, 72.0, 56.0, 40.0, 24.0, 8.0):
        yy = DOWN_Y_TOP + (CREST_Z - zz) * (DOWN_Y_TOE - DOWN_Y_TOP) / \
             (CREST_Z - FOUNDATION_Z)
        for x0, x1 in ((-DAM_LEN_HALF, -SPILL_HALF), (SPILL_HALF, DAM_LEN_HALF)):
            mb.add_prism(
                [(yy - 0.16 + n_down[0] * 0.06, zz - 0.16 + n_down[1] * 0.06),
                 (yy + 0.16 + n_down[0] * 0.06, zz + 0.16 + n_down[1] * 0.06),
                 (yy + 0.16 + n_down[0] * 0.06 + 0.16, zz + 0.16 + n_down[1] * 0.06),
                 (yy - 0.16 + n_down[0] * 0.06 + 0.16, zz - 0.16 + n_down[1] * 0.06)],
                x0, x1)

    obj = mb.build("Expansion_Joints", coll, mat)
    return obj


def create_small_details(coll, mat_old, mat_metal):
    mb_pipes = MeshBuilder()
    mb_misc = MeshBuilder()

    # --- pipes / conduits on the downstream face of one block ---
    for i in range(5):
        y0 = 12.0 + i * 0.0
        mb_pipes.add_cylinder_x(0.22, -132.0, -128.0, 4.0 + i * 2.0, CREST_Z - 4.0, 10)

    # --- inspection gallery openings (dark recess boxes) ---
    for x in (-150.0, -96.0, 96.0, 150.0):
        for zz in (30.0, 60.0, 90.0):
            yy = DOWN_Y_TOP + (CREST_Z - zz) * (DOWN_Y_TOE - DOWN_Y_TOP) / \
                 (CREST_Z - FOUNDATION_Z)
            mb_misc.add_box(x - 1.6, x + 1.6, yy - 0.9, yy + 0.2,
                            zz - 1.6, zz + 1.6)

    # --- small maintenance doors at the toe ---
    for x in (-180.0, -120.0, -70.0, 70.0, 120.0, 180.0):
        mb_misc.add_box(x - 2.0, x + 2.0, DOWN_Y_TOE - 0.6, DOWN_Y_TOE + 0.3,
                        FOUNDATION_Z + 2.0, FOUNDATION_Z + 6.5)

    # --- stairs from the crest down to the walkway ---
    for side in (-1.0, 1.0):
        x = 66.0 * side
        y = -3.5
        z = CREST_Z
        for i in range(22):
            mb_misc.add_box(min(x, x + 2.4 * side), max(x, x + 2.4 * side),
                            y, y + 3.0,
                            z - 0.35, z)
            z -= 0.7
            y += 0.35

    o1 = mb_pipes.build("Conduits", coll, mat_metal)
    o2 = mb_misc.build("Structural_Details", coll, mat_old, bevel=0.08)
    return [o1, o2]


# ==============================================================
# 9.  CAMERAS
# ==============================================================
def _look_at(obj, target):
    direction = Vector(target) - obj.location
    rot = direction.to_track_quat('-Z', 'Y').to_euler()
    obj.rotation_euler = rot


def create_cameras(scene, coll):
    cams = {}

    def add_cam(name, loc, target, lens=45.0):
        cd = bpy.data.cameras.new(name)
        cd.lens = lens
        cd.clip_end = 5000.0
        cd.clip_start = 1.0
        ob = bpy.data.objects.new(name, cd)
        ob.location = loc
        link_obj(ob, coll)
        _look_at(ob, target)
        cams[name] = ob
        return ob

    add_cam("Camera_Aerial",   (175.0, 400.0, 250.0), (0.0, 30.0, 60.0), 42.0)
    add_cam("Camera_Front",    (0.0, 430.0, 90.0),    (0.0, 30.0, 65.0), 55.0)
    add_cam("Camera_Side",     (520.0, 40.0, 120.0),  (0.0, 30.0, 45.0), 55.0)
    add_cam("Camera_Spillway", (0.0, 230.0, 120.0),   (0.0, 10.0, 100.0), 35.0)
    add_cam("Camera_Closeup",  (-43.0, 70.0, 132.0),  (-43.0, 6.0, 112.0), 50.0)

    scene.camera = cams["Camera_Aerial"]
    return cams


# ==============================================================
# 10.  LIGHTING
# ==============================================================
def create_lighting(scene, coll):
    world = bpy.data.worlds.new("Dam_World")
    scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs[0].default_value = (0.55, 0.62, 0.72, 1.0)
        bg.inputs[1].default_value = 1.0

    sun_d = bpy.data.lights.new("Sun_Key", 'SUN')
    sun_d.energy = 4.0
    sun_d.angle = math.radians(3.0)
    sun = bpy.data.objects.new("Sun_Key", sun_d)
    sun.location = (300.0, 200.0, 500.0)
    link_obj(sun, coll)
    _look_at(sun, (0.0, 30.0, 40.0))

    fill_d = bpy.data.lights.new("Sun_Fill", 'SUN')
    fill_d.energy = 1.1
    fill_d.angle = math.radians(25.0)
    fill = bpy.data.objects.new("Sun_Fill", fill_d)
    fill.location = (-350.0, -300.0, 350.0)
    link_obj(fill, coll)
    _look_at(fill, (0.0, 30.0, 40.0))

    area_d = bpy.data.lights.new("Area_Ambient", 'AREA')
    area_d.energy = 250000.0
    area_d.size = 600.0
    area = bpy.data.objects.new("Area_Ambient", area_d)
    area.location = (0.0, 250.0, 320.0)
    link_obj(area, coll)
    _look_at(area, (0.0, 40.0, 60.0))

    return sun, fill, area


# ==============================================================
# 11.  GATE ANIMATION
# ==============================================================
def set_gate_opening(percentage, frame=None):
    """0 = fully closed, 100 = fully open."""
    p = max(0.0, min(100.0, float(percentage))) / 100.0
    angle = -math.radians(GATE_OPEN_DEG) * p
    for g in GATE_OBJECTS:
        g.rotation_euler = (angle, 0.0, 0.0)
        if frame is not None:
            g.keyframe_insert(data_path="rotation_euler",
                              index=0, frame=frame)


def build_gate_animation():
    keys = ((1, 0.0), (30, 12.0), (60, 50.0), (90, 88.0), (120, 100.0))
    for f, p in keys:
        set_gate_opening(p, frame=f)

    for g in GATE_OBJECTS:
        if g.animation_data and g.animation_data.action:
            try:
                fcurves = g.animation_data.action.fcurves
            except Exception:
                fcurves = []
            for fc in fcurves:
                for kp in fc.keyframe_points:
                    kp.interpolation = 'BEZIER'

    # return to the closed pose so the saved file opens closed
    set_gate_opening(0.0)


# ==============================================================
# 12.  PHYSICS / RIGID BODIES
# ==============================================================
def setup_physics(scene, coll_physics, mat_debris, dam_objs):
    # --- make sure the rigid body world exists ---
    try:
        if scene.rigidbody_world is None:
            bpy.ops.rigidbody.world_add()
    except Exception as exc:
        print("[physics] world_add failed:", exc)

    if scene.rigidbody_world is not None:
        try:
            scene.rigidbody_world.time_scale = 1.0
            scene.rigidbody_world.substeps_per_frame = 12
            scene.rigidbody_world.solver_iterations = 20
        except Exception:
            pass

    # --- static (passive) structure ---
    for obj in dam_objs:
        try:
            bpy.ops.object.select_all(action='DESELECT')
            obj.select_set(True)
            bpy.context.view_layer.objects.active = obj
            bpy.ops.rigidbody.object_add()
            obj.rigid_body.type = 'PASSIVE'
            obj.rigid_body.friction = 0.9
            obj.rigid_body.restitution = 0.02
        except Exception as exc:
            print("[physics] passive body failed for", obj.name, exc)

    # --- active debris / test blocks (they will actually fall) ---
    mb = MeshBuilder()
    for i in range(9):
        x = -180.0 + i * 45.0
        y = 12.0
        mb.add_box(x, x + 2.4, y, y + 2.4,
                   CREST_Z + 0.3, CREST_Z + 2.7)
    debris = mb.build("Physics_Test_Blocks", coll_physics, mat_debris, bevel=0.05)

    if debris:
        bpy.ops.object.select_all(action='DESELECT')
        debris.select_set(True)
        bpy.context.view_layer.objects.active = debris
        try:
            bpy.ops.rigidbody.object_add()
            debris.rigid_body.type = 'ACTIVE'
            debris.rigid_body.mass = 6000.0
            debris.rigid_body.friction = 0.7
            debris.rigid_body.restitution = 0.05
            bpy.ops.mesh.separate(type='LOOSE')
        except Exception as exc:
            print("[physics] active body failed:", exc)

    return debris

# ==============================================================
#  WATER SYSTEM  —  realistic flowing water
# ==============================================================
#
# This block replaces the previous WATER section + main().
# The concrete dam/gates/crest/physics/cameras/lighting above
# remain unchanged.
# ==============================================================

WATER_RESERVOIR_Z = 110.5
WATER_BASIN_Z     = -6.0
WATER_RIVER_Z     = -13.0

WATER_OBJECTS = []
WATER_MATS    = {}


# --------------------------------------------------------------
def _water_socket(bsdf, names, value):
    """Set the first existing socket (Blender 3.x / 4.x safe)."""
    for name in names:
        sock = bsdf.inputs.get(name)
        if sock is not None:
            try:
                sock.default_value = value
                return True
            except Exception:
                pass
    return False


# --------------------------------------------------------------
def _water_mix(nodes, links, fac=0.0, c1=None, c2=None, loc=(0, 0)):
    """
    Blender 3.x/4.x-safe color mix.

    ShaderNodeMixRGB is intentionally used because its sockets are
    consistently addressable by name:
        Fac / Color1 / Color2 / Color
    """
    n = nodes.new("ShaderNodeMixRGB")
    n.blend_type = 'MIX'
    n.inputs["Fac"].default_value = fac
    n.location = loc

    if c1 is not None:
        links.new(c1, n.inputs["Color1"])
    if c2 is not None:
        links.new(c2, n.inputs["Color2"])

    return (
        n,
        n.inputs["Fac"],
        n.inputs["Color1"],
        n.inputs["Color2"],
        n.outputs["Color"],
    )


# --------------------------------------------------------------
def create_water_materials():
    """Create procedural reservoir, spillway and turbulent water."""
    mats = {}

    # ============ 1. RESERVOIR =============
    mat = bpy.data.materials.new("Water_Reservoir")
    mat.use_nodes = True
    nt = mat.node_tree
    nodes, links = nt.nodes, nt.links

    for n in list(nodes):
        nodes.remove(n)

    out = nodes.new("ShaderNodeOutputMaterial")
    out.location = (900, 0)

    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (600, 0)
    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])

    _water_socket(bsdf, ("Base Color",), (0.05, 0.14, 0.18, 1.0))
    _water_socket(bsdf, ("Roughness",), 0.04)
    _water_socket(bsdf, ("IOR",), 1.333)
    _water_socket(bsdf, ("Transmission Weight", "Transmission"), 1.0)

    tc = nodes.new("ShaderNodeTexCoord")
    tc.location = (-1100, 0)

    mp = nodes.new("ShaderNodeMapping")
    mp.location = (-900, 0)
    links.new(tc.outputs["Object"], mp.inputs["Vector"])

    n1 = nodes.new("ShaderNodeTexNoise")
    n1.location = (-650, 200)
    n1.inputs["Scale"].default_value = 0.35
    n1.inputs["Detail"].default_value = 5.0
    n1.inputs["Roughness"].default_value = 0.55
    links.new(mp.outputs["Vector"], n1.inputs["Vector"])

    bmp = nodes.new("ShaderNodeBump")
    bmp.location = (300, -250)
    bmp.inputs["Strength"].default_value = 0.10
    bmp.inputs["Distance"].default_value = 1.0
    links.new(n1.outputs["Fac"], bmp.inputs["Height"])
    links.new(bmp.outputs["Normal"], bsdf.inputs["Normal"])

    vol = nodes.new("ShaderNodeVolumeAbsorption")
    vol.location = (300, -450)
    vol.inputs["Color"].default_value = (0.25, 0.45, 0.55, 1.0)
    vol.inputs["Density"].default_value = 0.006
    links.new(vol.outputs["Volume"], out.inputs["Volume"])

    mats["reservoir"] = mat
    mats["reservoir_map"] = mp

    # ============ 2. SPILLWAY FLOW =============
    mat = bpy.data.materials.new("Water_Spillway_Flow")
    mat.use_nodes = True
    nt = mat.node_tree
    nodes, links = nt.nodes, nt.links

    for n in list(nodes):
        nodes.remove(n)

    out = nodes.new("ShaderNodeOutputMaterial")
    out.location = (1100, 0)

    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (800, 0)
    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])

    water_col = (0.08, 0.17, 0.21, 1.0)
    foam_col = (0.92, 0.94, 0.95, 1.0)

    _water_socket(bsdf, ("Base Color",), water_col)
    _water_socket(bsdf, ("Roughness",), 0.12)
    _water_socket(bsdf, ("IOR",), 1.333)
    _water_socket(bsdf, ("Transmission Weight", "Transmission"), 0.7)

    tc = nodes.new("ShaderNodeTexCoord")
    tc.location = (-1400, 0)

    mp = nodes.new("ShaderNodeMapping")
    mp.location = (-1200, 0)
    links.new(tc.outputs["Object"], mp.inputs["Vector"])

    # Foam amount increases toward the spillway toe.
    sep = nodes.new("ShaderNodeSeparateXYZ")
    sep.location = (-1200, -350)
    links.new(tc.outputs["Object"], sep.inputs["Vector"])

    mr = nodes.new("ShaderNodeMapRange")
    mr.location = (-1000, -350)
    mr.inputs["From Min"].default_value = -18.0
    mr.inputs["From Max"].default_value = 100.0
    mr.inputs["To Min"].default_value = 0.85
    mr.inputs["To Max"].default_value = 0.05
    links.new(sep.outputs["Z"], mr.inputs["Value"])

    nf = nodes.new("ShaderNodeTexNoise")
    nf.location = (-1200, 100)
    nf.inputs["Scale"].default_value = 0.9
    nf.inputs["Detail"].default_value = 7.0
    nf.inputs["Roughness"].default_value = 0.6
    links.new(mp.outputs["Vector"], nf.inputs["Vector"])

    cr = nodes.new("ShaderNodeValToRGB")
    cr.location = (-900, 100)
    cr.color_ramp.elements[0].position = 0.40
    cr.color_ramp.elements[0].color = (0, 0, 0, 1)
    cr.color_ramp.elements[1].position = 0.65
    cr.color_ramp.elements[1].color = (1, 1, 1, 1)
    links.new(nf.outputs["Fac"], cr.inputs["Fac"])

    (
        foam_mix,
        foam_fac_socket,
        foam_a,
        foam_b,
        foam_out,
    ) = _water_mix(
        nodes,
        links,
        fac=1.0,
        c1=mr.outputs["Result"],
        c2=cr.outputs["Color"],
        loc=(-700, -200)
    )
    foam_mix.blend_type = 'MULTIPLY'

    (
        color_mix,
        color_fac_socket,
        color_a,
        color_b,
        color_out,
    ) = _water_mix(
        nodes,
        links,
        fac=0.0,
        loc=(400, 100)
    )

    color_a.default_value = water_col
    color_b.default_value = foam_col

    links.new(foam_out, color_fac_socket)
    links.new(color_out, bsdf.inputs["Base Color"])

    bmp = nodes.new("ShaderNodeBump")
    bmp.location = (500, -250)
    bmp.inputs["Strength"].default_value = 0.40
    bmp.inputs["Distance"].default_value = 0.4
    links.new(nf.outputs["Fac"], bmp.inputs["Height"])
    links.new(bmp.outputs["Normal"], bsdf.inputs["Normal"])

    mats["spillway"] = mat
    mats["spillway_map"] = mp

    # ============ 3. TURBULENT BASIN =============
    mat = bpy.data.materials.new("Water_Turbulent")
    mat.use_nodes = True
    nt = mat.node_tree
    nodes, links = nt.nodes, nt.links

    for n in list(nodes):
        nodes.remove(n)

    out = nodes.new("ShaderNodeOutputMaterial")
    out.location = (900, 0)

    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (600, 0)
    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])

    _water_socket(bsdf, ("Base Color",), (0.65, 0.72, 0.75, 1.0))
    _water_socket(bsdf, ("Roughness",), 0.35)
    _water_socket(bsdf, ("IOR",), 1.333)
    _water_socket(bsdf, ("Transmission Weight", "Transmission"), 0.25)

    tc = nodes.new("ShaderNodeTexCoord")
    tc.location = (-1100, 0)

    mp = nodes.new("ShaderNodeMapping")
    mp.location = (-900, 0)
    links.new(tc.outputs["Object"], mp.inputs["Vector"])

    n1 = nodes.new("ShaderNodeTexNoise")
    n1.location = (-650, 100)
    n1.inputs["Scale"].default_value = 1.5
    n1.inputs["Detail"].default_value = 8.0
    n1.inputs["Roughness"].default_value = 0.7
    links.new(mp.outputs["Vector"], n1.inputs["Vector"])

    n2 = nodes.new("ShaderNodeTexNoise")
    n2.location = (-650, -250)
    n2.inputs["Scale"].default_value = 4.0
    n2.inputs["Detail"].default_value = 6.0
    links.new(mp.outputs["Vector"], n2.inputs["Vector"])

    cr = nodes.new("ShaderNodeValToRGB")
    cr.location = (-400, -250)
    cr.color_ramp.elements[0].position = 0.40
    cr.color_ramp.elements[0].color = (0.45, 0.55, 0.60, 1.0)
    cr.color_ramp.elements[1].position = 0.65
    cr.color_ramp.elements[1].color = (0.95, 0.96, 0.97, 1.0)
    links.new(n2.outputs["Fac"], cr.inputs["Fac"])
    links.new(cr.outputs["Color"], bsdf.inputs["Base Color"])

    bmp = nodes.new("ShaderNodeBump")
    bmp.location = (300, -250)
    bmp.inputs["Strength"].default_value = 0.60
    bmp.inputs["Distance"].default_value = 0.6
    links.new(n1.outputs["Fac"], bmp.inputs["Height"])
    links.new(bmp.outputs["Normal"], bsdf.inputs["Normal"])

    mats["basin"] = mat
    mats["basin_map"] = mp

    return mats


# --------------------------------------------------------------
def _grid_object(name, x0, x1, y0, y1, z, coll, mat,
                 x_sub=60, y_sub=60):
    """Create a subdivided grid plane."""
    bm = bmesh.new()

    bmesh.ops.create_grid(
        bm,
        x_segments=x_sub,
        y_segments=y_sub,
        size=1.0
    )

    mesh = bpy.data.meshes.new(name + "_mesh")
    bm.to_mesh(mesh)
    bm.free()

    obj = bpy.data.objects.new(name, mesh)
    link_obj(obj, coll)

    obj.scale = ((x1 - x0) * 0.5, (y1 - y0) * 0.5, 1.0)
    obj.location = (
        (x0 + x1) * 0.5,
        (y0 + y1) * 0.5,
        z
    )

    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)

    bpy.ops.object.transform_apply(
        location=False,
        rotation=False,
        scale=True
    )

    obj.select_set(False)

    if mat:
        obj.data.materials.append(mat)

    WATER_OBJECTS.append(obj)
    return obj


# --------------------------------------------------------------
def create_reservoir(coll, mat):
    """Large upstream reservoir surface."""
    obj = _grid_object(
        "Water_Reservoir",
        -DAM_LEN_HALF - 120,
        DAM_LEN_HALF + 120,
        -520.0,
        UP_Y_TOP + 0.2,
        WATER_RESERVOIR_Z,
        coll,
        mat,
        x_sub=80,
        y_sub=80
    )

    tex = bpy.data.textures.new("Reservoir_Waves", 'CLOUDS')
    tex.noise_scale = 22.0
    tex.noise_depth = 3

    disp = obj.modifiers.new("Waves", 'DISPLACE')
    disp.texture = tex
    disp.strength = 0.55
    disp.mid_level = 0.5
    disp.texture_coords = 'GLOBAL'

    sub = obj.modifiers.new("Smooth", 'SUBSURF')
    sub.levels = 1

    return obj


# --------------------------------------------------------------
def create_spillway_flow(coll, mat):
    """Water ribbon in each bay following the existing chute profile."""
    mb = MeshBuilder()
    prof = SPILL_PROFILE[2:]

    for cx in bay_centres():
        half_w = (BAY_W - 1.0) * 0.5

        top = [(y, z + 1.50) for (y, z) in prof]
        bot = [(y, z + 0.25) for (y, z) in prof]

        mb.add_prism(
            top + bot[::-1],
            cx - half_w,
            cx + half_w
        )

    obj = mb.build(
        "Spillway_Water_Flow",
        coll,
        mat
    )

    if obj:
        sub = obj.modifiers.new("Subsurf", 'SUBSURF')
        sub.levels = 1

    return obj


# --------------------------------------------------------------
def create_stilling_basin_water(coll, mat):
    """Turbulent water inside the stilling basin."""
    obj = _grid_object(
        "Stilling_Basin_Water",
        -67.0,
        67.0,
        104.0,
        182.0,
        WATER_BASIN_Z,
        coll,
        mat,
        x_sub=70,
        y_sub=40
    )

    tex = bpy.data.textures.new("Basin_Chop", 'CLOUDS')
    tex.noise_scale = 6.0
    tex.noise_depth = 4

    disp = obj.modifiers.new("Chop", 'DISPLACE')
    disp.texture = tex
    disp.strength = 1.8
    disp.mid_level = 0.5
    disp.texture_coords = 'GLOBAL'

    sub = obj.modifiers.new("Smooth", 'SUBSURF')
    sub.levels = 2

    return obj


# --------------------------------------------------------------
def create_downstream_river(coll, mat):
    """Downstream water surface."""
    mb = MeshBuilder()

    y0, y1 = 182.0, 520.0
    z0, z1 = WATER_BASIN_Z, WATER_RIVER_Z

    profile = [
        (y0, z0 - 8.0),
        (y1, z1 - 8.0),
        (y1, z1),
        (y0, z0)
    ]

    mb.add_prism(
        profile,
        -67.0,
        67.0
    )

    obj = mb.build(
        "Downstream_River",
        coll,
        mat
    )

    if obj:
        sub = obj.modifiers.new("Subsurf", 'SUBSURF')
        sub.levels = 2

    WATER_OBJECTS.append(obj)
    return obj


# --------------------------------------------------------------
def create_water_spray(coll):
    """
    Create optional spray particles at the basin impact zone.

    If a build cannot create the legacy particle system, the main
    water system continues without spray.
    """
    try:
        bpy.ops.object.select_all(action='DESELECT')

        bpy.ops.mesh.primitive_plane_add(
            size=2.0,
            location=(0.0, 120.0, -4.0)
        )

        emitter = bpy.context.view_layer.objects.active

        if emitter is None:
            raise RuntimeError("Could not obtain spray emitter.")

        emitter.name = "Water_Spray_Emitter"
        emitter.scale = (65.0, 6.0, 1.0)

        bpy.ops.object.transform_apply(
            location=False,
            rotation=False,
            scale=True
        )

        link_obj(emitter, coll)

        bpy.ops.object.particle_system_add()

        if len(emitter.particle_systems) == 0:
            return emitter

        psys = emitter.particle_systems[-1]
        st = psys.settings

        st.type = 'EMITTER'
        st.count = 2500
        st.lifetime = 45
        st.lifetime_random = 0.5
        st.emit_from = 'FACE'
        st.distribution = 'RAND'
        st.physics_type = 'NEWTON'
        st.normal_factor = 6.0
        st.factor_random = 4.0
        st.object_align_factor = (0.0, 0.0, 1.0)
        st.effector_weights.gravity = 0.7
        st.mass = 0.02
        st.particle_size = 0.35
        st.size_random = 0.7

        try:
            st.render_type = 'HALO'
        except Exception:
            st.render_type = 'NONE'

        mat = bpy.data.materials.new("Water_Spray")
        mat.use_nodes = True

        nt = mat.node_tree
        for n in list(nt.nodes):
            nt.nodes.remove(n)

        out = nt.nodes.new("ShaderNodeOutputMaterial")
        emi = nt.nodes.new("ShaderNodeEmission")

        emi.inputs["Color"].default_value = (
            0.90, 0.94, 0.97, 1.0
        )
        emi.inputs["Strength"].default_value = 1.4

        nt.links.new(
            emi.outputs["Emission"],
            out.inputs["Surface"]
        )

        try:
            mat.surface_render_method = 'BLENDED'
        except Exception:
            try:
                mat.blend_method = 'BLEND'
            except Exception:
                pass

        emitter.data.materials.append(mat)
        return emitter

    except Exception as exc:
        print("[water] spray skipped:", exc)
        return None


# --------------------------------------------------------------
def animate_water(scene):
    """Animate water texture movement downstream."""
    f0, f1 = 1, 120

    def key_mapping(mp, start, end):
        if mp is None:
            return

        loc = mp.inputs.get("Location")
        if loc is None:
            return

        loc.default_value = start
        loc.keyframe_insert(
            data_path="default_value",
            frame=f0
        )

        loc.default_value = end
        loc.keyframe_insert(
            data_path="default_value",
            frame=f1
        )

       
    if WATER_MATS.get("reservoir_map"):
        key_mapping(
            WATER_MATS["reservoir_map"],
            (0.0, 0.0, 0.0),
            (0.0, -20.0, 0.0)
        )

    if WATER_MATS.get("spillway_map"):
        key_mapping(
            WATER_MATS["spillway_map"],
            (0.0, 0.0, 0.0),
            (0.0, -18.0, 0.0)
        )

    if WATER_MATS.get("basin_map"):
        key_mapping(
            WATER_MATS["basin_map"],
            (0.0, 0.0, 0.0),
            (0.0, -26.0, 0.0)
        )

    scene.frame_set(1)


# --------------------------------------------------------------
def setup_mantaflow(scene, dam_objs, gate_objs):
    """
    Optional true liquid simulation.

    The default main() does not run this because it uses the
    deterministic procedural water surfaces above.

    To enable:
        Uncomment the setup_mantaflow(...) line in main().
        Then select Fluid_Domain and bake Liquid Data + Mesh.
    """
    try:
        bpy.ops.object.select_all(action='DESELECT')
        bpy.ops.mesh.primitive_cube_add(
            size=2,
            location=(0, 40, 55)
        )

        dom = bpy.context.view_layer.objects.active
        if dom is None:
            raise RuntimeError("Could not create fluid domain.")

        dom.name = "Fluid_Domain"
        dom.scale = (240.0, 320.0, 100.0)

        bpy.ops.object.transform_apply(
            location=False,
            rotation=False,
            scale=True
        )

        m = dom.modifiers.new("Fluid_Domain", 'FLUID')
        m.fluid_type = 'DOMAIN'

        d = m.domain_settings
        if d is None:
            raise RuntimeError("Liquid domain settings unavailable.")

        d.domain_type = 'LIQUID'
        d.resolution_max = 128
        d.use_adaptive_timesteps = True
        d.cache_frame_start = 1
        d.cache_frame_end = 120

        # Upstream inflow.
        bpy.ops.object.select_all(action='DESELECT')
        bpy.ops.mesh.primitive_cube_add(
            size=2,
            location=(0, -300, WATER_RESERVOIR_Z - 5.0)
        )

        inf = bpy.context.view_layer.objects.active
        if inf is None:
            raise RuntimeError("Could not create fluid inflow.")

        inf.name = "Fluid_Inflow"
        inf.scale = (200.0, 60.0, 5.0)

        bpy.ops.object.transform_apply(
            location=False,
            rotation=False,
            scale=True
        )

        mi = inf.modifiers.new("Fluid_Inflow", 'FLUID')
        mi.fluid_type = 'FLOW'

        fi = mi.flow_settings
        fi.flow_type = 'LIQUID'
        fi.flow_behavior = 'INFLOW'
        fi.use_inflow = True

        # Downstream outflow.
        bpy.ops.object.select_all(action='DESELECT')
        bpy.ops.mesh.primitive_cube_add(
            size=2,
            location=(0, 480, -10)
        )

        outf = bpy.context.view_layer.objects.active
        if outf is None:
            raise RuntimeError("Could not create fluid outflow.")

        outf.name = "Fluid_Outflow"
        outf.scale = (80.0, 20.0, 20.0)

        bpy.ops.object.transform_apply(
            location=False,
            rotation=False,
            scale=True
        )

        mo = outf.modifiers.new("Fluid_Outflow", 'FLUID')
        mo.fluid_type = 'FLOW'

        fo = mo.flow_settings
        fo.flow_type = 'LIQUID'
        fo.flow_behavior = 'OUTFLOW'

        # Concrete and gates as fluid effectors.
        for obj in dam_objs + gate_objs:
            try:
                mod = obj.modifiers.get("Fluid_Effector")

                if mod is None:
                    mod = obj.modifiers.new(
                        "Fluid_Effector",
                        'FLUID'
                    )

                mod.fluid_type = 'EFFECTOR'

                settings = mod.effector_settings
                settings.effector_type = 'COLLISION'
                settings.use_effector = True

            except Exception as exc:
                print(
                    "[mantaflow] collision failed for",
                    obj.name,
                    exc
                )

        print(
            "[mantaflow] domain, inflow, outflow and "
            "collisions configured."
        )
        print(
            "[mantaflow] Bake Fluid_Domain: Physics > Liquid > "
            "Bake Data, then Bake Mesh."
        )

    except Exception as exc:
        print("[mantaflow] setup failed:", exc)


# ==============================================================
#  MAIN
# ==============================================================
def main():
    # --- scene reset / units / gravity -------------------------
    bpy.ops.wm.read_factory_settings(use_empty=True)

    scene = bpy.context.scene

    scene.unit_settings.system = 'METRIC'
    scene.unit_settings.scale_length = 1.0

    try:
        scene.unit_settings.length_unit = 'METERS'
    except Exception:
        pass

    scene.use_gravity = True
    scene.gravity = (0.0, 0.0, -9.81)

    scene.frame_start = 1
    scene.frame_end = 120
    scene.frame_set(1)

    # --- collections -------------------------------------------
    root = bpy.data.collections.new("DAM")
    scene.collection.children.link(root)

    c_body    = new_collection("Dam_Body",           root)
    c_spill   = new_collection("Spillway",           root)
    c_piers   = new_collection("Spillway_Piers",     root)
    c_gates   = new_collection("Spillway_Gates",     root)
    c_mech    = new_collection("Gate_Machinery",     root)
    c_crest   = new_collection("Crest",              root)
    c_walk    = new_collection("Walkways",           root)
    c_rails   = new_collection("Railings",           root)
    c_basin   = new_collection("Stilling_Basin",     root)
    c_detail  = new_collection("Structural_Details", root)
    c_phys    = new_collection("Physics",            root)
    c_lights  = new_collection("Lighting",           root)
    c_cams    = new_collection("Cameras",            root)
    c_water   = new_collection("Water",              root)

    # --- concrete + metal materials ----------------------------
    mat_concrete = create_concrete_material(
        "Concrete_Fresh",
        base=(0.68, 0.68, 0.66),
        dark=(0.47, 0.47, 0.46),
        stain_dark=(0.38, 0.37, 0.35),
        roughness=0.88,
        noise_scale=0.013,
        stain_scale=0.0032,
        bump=0.30
    )

    mat_old = create_concrete_material(
        "Concrete_Weathered",
        base=(0.56, 0.55, 0.53),
        dark=(0.36, 0.35, 0.34),
        stain_dark=(0.26, 0.25, 0.23),
        roughness=0.93,
        noise_scale=0.022,
        stain_scale=0.0060,
        bump=0.45
    )

    mat_joint = create_concrete_material(
        "Concrete_Joint",
        base=(0.34, 0.33, 0.32),
        dark=(0.22, 0.21, 0.20),
        stain_dark=(0.16, 0.15, 0.14),
        roughness=0.95,
        noise_scale=0.05,
        stain_scale=0.01,
        bump=0.25
    )

    mat_steel = create_metal_material(
        "Gate_Steel",
        base=(0.24, 0.25, 0.27),
        roughness=0.40,
        metallic=1.0,
        wear=0.5
    )

    mat_metal = create_metal_material(
        "Machinery_Metal",
        base=(0.33, 0.34, 0.35),
        roughness=0.48,
        metallic=1.0,
        wear=0.6
    )

    mat_debris = create_simple_material(
        "Debris_Concrete",
        (0.52, 0.51, 0.49),
        roughness=0.9
    )

    # --- water materials ---------------------------------------
    global WATER_MATS
    WATER_MATS = create_water_materials()

    # --- build the dam -----------------------------------------
    print("[dam] building concrete mass ...")

    create_foundation(c_body, mat_concrete)
    create_dam_body(c_body, mat_concrete)
    create_spillway_section(c_spill, mat_concrete)
    create_spillway_piers(c_piers, mat_concrete)
    create_stilling_basin(c_basin, mat_concrete)

    print("[dam] building crest works ...")

    create_crest(
        c_crest,
        c_walk,
        c_rails,
        c_detail,
        mat_concrete,
        mat_old,
        mat_metal
    )

    print("[dam] building expansion joints ...")
    create_expansion_joints(c_detail, mat_joint)

    print("[dam] building structural details ...")
    create_small_details(c_detail, mat_old, mat_metal)

    # --- gates --------------------------------------------------
    print("[dam] building radial gates ...")

    for i, cx in enumerate(bay_centres()):
        create_gate(
            "Gate_%02d" % (i + 1),
            cx,
            c_gates,
            c_mech,
            mat_steel,
            mat_metal
        )

    # --- WATER --------------------------------------------------
    print(
        "[water] building reservoir, spillway flow, "
        "basin, river ..."
    )

    create_reservoir(
        c_water,
        WATER_MATS["reservoir"]
    )

    create_spillway_flow(
        c_water,
        WATER_MATS["spillway"]
    )

    create_stilling_basin_water(
        c_water,
        WATER_MATS["basin"]
    )

    create_downstream_river(
        c_water,
        WATER_MATS["basin"]
    )

    create_water_spray(c_water)

    print("[water] animating flow ...")
    animate_water(scene)

    # --- gate animation ----------------------------------------
    print("[dam] creating gate animation ...")
    build_gate_animation()

    # --- cameras + lights --------------------------------------
    print("[dam] creating cameras and lighting ...")

    create_cameras(scene, c_cams)
    create_lighting(scene, c_lights)

    # --- rigid bodies ------------------------------------------
    print("[dam] setting up rigid bodies ...")

    setup_physics(
        scene,
        c_phys,
        mat_debris,
        DAM_OBJECTS
    )

    # --- OPTIONAL TRUE MANTAFlOW -------------------------------
    # Uncomment to configure an actual liquid solver domain.
    #
    # setup_mantaflow(scene, DAM_OBJECTS, GATE_OBJECTS)

    # --- save ---------------------------------------------------
    scene.frame_set(1)

    try:
        out_dir = os.path.dirname(bpy.data.filepath) or os.getcwd()
    except Exception:
        out_dir = os.getcwd()

    blend_path = os.path.join(
        out_dir,
        "concrete_dam_with_water.blend"
    )

    try:
        bpy.ops.wm.save_as_mainfile(
            filepath=blend_path
        )
        saved = blend_path
    except Exception as exc:
        print("[dam] save failed:", exc)
        saved = "(not saved)"

    # --- summary ------------------------------------------------
    print("")
    print("=" * 62)
    print("DAM GENERATION COMPLETE")
    print("=" * 62)

    print(
        "Dimensions:        %d m long  x  %d m wide  x  %d m high"
        % (
            int(DAM_LEN_HALF * 2),
            int(DOWN_Y_TOE - UP_Y_BOT),
            int(CREST_Z - FOUNDATION_Z)
        )
    )

    print("Spillway Bays:     %d" % N_BAYS)
    print("Gates:             %d radial gates" % len(GATE_OBJECTS))

    print(
        "Gate Animation:    READY  "
        "(1 / 60 / 120 = closed / half / open)"
    )

    print("Gravity:           -9.81 m/s2")
    print("Units:             METERS")

    print(
        "Water:             Reservoir + Spillway flow + "
        "Stilling basin + Downstream river + Spray"
    )

    print("Terrain:           NONE")

    print(
        "Collections:       DAM > Dam_Body, Spillway, "
        "Spillway_Piers,"
    )
    print(
        "                        Spillway_Gates, Gate_Machinery, "
        "Crest,"
    )
    print(
        "                        Walkways, Railings, Stilling_Basin, "
        "Physics, Water"
    )

    print(
        "Cameras:           Camera_Aerial, Camera_Front, "
        "Camera_Side,"
    )
    print(
        "                   Camera_Spillway, Camera_Closeup"
    )

    print("Saved .blend:      %s" % saved)
    print("=" * 62)
    print("")


# ==============================================================
if __name__ == "__main__":
    main()
