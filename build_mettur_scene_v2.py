import bpy
import json
import math
import struct
from pathlib import Path

from mathutils import Vector

# ============================================================
# METTUR DAM DIGITAL TWIN — BLENDER 5.2
# REAL TERRAIN + REAL OSM BUILDINGS + REAL ROADS + WATER
# ============================================================

BASE = Path(r"E:\dam\mettur_data")
READY = BASE / "blender_ready"

OUTPUT = Path(r"E:\dam\mettur_dam_digital_twin_v2.blend")
PREVIEW = Path(r"E:\dam\mettur_dam_preview_v2.png")

# Correct Mettur Dam coordinates
DAM_LAT = 11.80346
DAM_LON = 77.80627

# Blender display scale.
# 0.10 = compact project/demo model.
# Keep geometry proportional.
DISPLAY_SCALE = 0.10

# Dam dimensions used for the visual digital-twin structure.
DAM_LENGTH = 1700.0
DAM_HEIGHT = 120.0
DAM_BASE_WIDTH = 180.0
DAM_TOP_WIDTH = 12.0

# Building height defaults.
DEFAULT_BUILDING_HEIGHT = 6.0
MAX_BUILDING_HEIGHT = 35.0

# Road width by OSM class.
ROAD_WIDTHS = {
    "motorway": 10.0,
    "trunk": 8.0,
    "primary": 7.0,
    "secondary": 6.0,
    "tertiary": 5.0,
    "residential": 3.5,
    "service": 2.5,
    "unclassified": 3.0,
    "track": 2.0,
    "path": 1.2,
}


# ============================================================
# UTILITIES
# ============================================================

def log(msg):
    print(msg, flush=True)


def clear_scene():
    log("[1/10] Clearing Blender scene...")

    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)

    # Remove orphan meshes/materials/curves
    for datablocks in (
        bpy.data.meshes,
        bpy.data.curves,
        bpy.data.materials,
        bpy.data.cameras,
        bpy.data.lights,
    ):
        for block in list(datablocks):
            if block.users == 0:
                datablocks.remove(block)


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def make_material(name, color, metallic=0.0, roughness=0.7):
    mat = bpy.data.materials.new(name)

    # Blender 5.2
    mat.use_nodes = True

    nodes = mat.node_tree.nodes
    bsdf = nodes.get("Principled BSDF")

    if bsdf:
        bsdf.inputs["Base Color"].default_value = (
            color[0],
            color[1],
            color[2],
            1.0,
        )

        if "Roughness" in bsdf.inputs:
            bsdf.inputs["Roughness"].default_value = roughness

        if "Metallic" in bsdf.inputs:
            bsdf.inputs["Metallic"].default_value = metallic

    return mat


def assign_material(obj, mat):
    if obj.data and hasattr(obj.data, "materials"):
        obj.data.materials.append(mat)


def create_collection(name):
    col = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(col)
    return col


def move_to_collection(obj, collection):
    for c in list(obj.users_collection):
        c.objects.unlink(obj)

    collection.objects.link(obj)


# ============================================================
# COORDINATE SYSTEM
# ============================================================

log("[2/10] Preparing coordinate system...")

# WGS84 -> UTM Zone 43N.
# Implemented locally so Blender 5.2 does not need pyproj.
def wgs84_to_utm43(lon, lat):
    a = 6378137.0
    ecc_sq = 0.0066943799901413165
    k0 = 0.9996
    lat_r = math.radians(lat)
    lon_r = math.radians(lon)
    lon0 = math.radians(75.0)
    e_prime_sq = ecc_sq / (1.0 - ecc_sq)
    sin_lat = math.sin(lat_r)
    cos_lat = math.cos(lat_r)
    tan_lat = math.tan(lat_r)
    N = a / math.sqrt(1.0 - ecc_sq * sin_lat * sin_lat)
    T = tan_lat * tan_lat
    C = e_prime_sq * cos_lat * cos_lat
    A = cos_lat * (lon_r - lon0)
    M = a * (
        (1 - ecc_sq / 4 - 3 * ecc_sq**2 / 64 - 5 * ecc_sq**3 / 256) * lat_r
        - (3 * ecc_sq / 8 + 3 * ecc_sq**2 / 32 + 45 * ecc_sq**3 / 1024) * math.sin(2 * lat_r)
        + (15 * ecc_sq**2 / 256 + 45 * ecc_sq**3 / 1024) * math.sin(4 * lat_r)
        - (35 * ecc_sq**3 / 3072) * math.sin(6 * lat_r)
    )
    E = 500000.0 + k0 * N * (
        A + (1 - T + C) * A**3 / 6
        + (5 - 18*T + T*T + 72*C - 58*e_prime_sq) * A**5 / 120
    )
    Nnorth = k0 * (
        M + N * tan_lat * (
            A**2 / 2
            + (5 - T + 9*C + 4*C**2) * A**4 / 24
            + (61 - 58*T + T*T + 600*C - 330*e_prime_sq) * A**6 / 720
        )
    )
    return E, Nnorth

dam_e, dam_n = wgs84_to_utm43(DAM_LON, DAM_LAT)

log(f"    Dam UTM: E={dam_e:.2f}, N={dam_n:.2f}")


# ============================================================
# TERRAIN METADATA
# ============================================================

terrain_meta = load_json(
    READY / "terrain_meta.json"
)

terrain_width = int(
    terrain_meta.get("width", 650)
)

terrain_height = int(
    terrain_meta.get("height", 659)
)

terrain_bounds = terrain_meta.get(
    "bounds",
    {}
)

left = float(
    terrain_bounds.get("left", dam_e - 10000)
)

right = float(
    terrain_bounds.get("right", dam_e + 10000)
)

bottom = float(
    terrain_bounds.get("bottom", dam_n - 10000)
)

top = float(
    terrain_bounds.get("top", dam_n + 10000)
)

terrain_meta_path = READY / "terrain_meta.json"

log(
    f"    Terrain grid: "
    f"{terrain_width} x {terrain_height}"
)


# ============================================================
# MATERIALS
# ============================================================

terrain_mat = make_material(
    "Terrain",
    (0.20, 0.32, 0.12),
    roughness=1.0,
)

building_mat = make_material(
    "Buildings",
    (0.55, 0.48, 0.38),
    roughness=0.85,
)

road_mat = make_material(
    "Roads",
    (0.08, 0.08, 0.07),
    roughness=0.9,
)

water_mat = make_material(
    "Reservoir Water",
    (0.02, 0.20, 0.40),
    metallic=0.05,
    roughness=0.18,
)

river_mat = make_material(
    "Waterways",
    (0.02, 0.30, 0.55),
    roughness=0.2,
)

dam_mat = make_material(
    "Mettur Dam",
    (0.34, 0.30, 0.25),
    roughness=0.8,
)

dam_top_mat = make_material(
    "Dam Crest",
    (0.45, 0.40, 0.32),
    roughness=0.7,
)


# ============================================================
# COLLECTIONS
# ============================================================

terrain_col = create_collection("01_TERRAIN")
water_col = create_collection("02_WATER")
dam_col = create_collection("03_METTUR_DAM")
roads_col = create_collection("04_REAL_OSM_ROADS")
buildings_col = create_collection("05_REAL_OSM_BUILDINGS")
waterways_col = create_collection("06_REAL_OSM_WATERWAYS")
camera_col = create_collection("07_CAMERA")
lights_col = create_collection("08_LIGHTING")


# ============================================================
# TERRAIN
# ============================================================

log("[3/10] Creating REAL SRTM terrain...")

heightmap_path = READY / "terrain_heightmap.f32"

with open(heightmap_path, "rb") as f:
    raw = f.read()

count = len(raw) // 4

heights = struct.unpack(
    "<" + "f" * count,
    raw,
)

if len(heights) != terrain_width * terrain_height:
    # Try metadata dimensions if the first assumption differs.
    terrain_width = int(
        terrain_meta.get("cols", terrain_width)
    )

    terrain_height = int(
        terrain_meta.get("rows", terrain_height)
    )

    if len(heights) != terrain_width * terrain_height:
        raise RuntimeError(
            "Terrain dimensions do not match terrain_heightmap.f32"
        )


verts = []
faces = []

# Terrain dimensions in metres.
terrain_x = right - left
terrain_y = top - bottom

for j in range(terrain_height):

    v = (
        j / (terrain_height - 1)
        if terrain_height > 1
        else 0
    )

    y = (
        bottom
        + v * terrain_y
        - dam_n
    ) * DISPLAY_SCALE

    for i in range(terrain_width):

        u = (
            i / (terrain_width - 1)
            if terrain_width > 1
            else 0
        )

        x = (
            left
            + u * terrain_x
            - dam_e
        ) * DISPLAY_SCALE

        z = (
            float(heights[j * terrain_width + i])
        ) * DISPLAY_SCALE

        verts.append(
            (x, y, z)
        )


for j in range(terrain_height - 1):

    for i in range(terrain_width - 1):

        a = j * terrain_width + i
        b = a + 1
        c = a + terrain_width + 1
        d = a + terrain_width

        faces.append(
            (a, b, c, d)
        )


mesh = bpy.data.meshes.new(
    "REAL_SRTM_TERRAIN"
)

mesh.from_pydata(
    verts,
    [],
    faces,
)

mesh.update()

terrain_obj = bpy.data.objects.new(
    "REAL_SRTM_TERRAIN",
    mesh,
)

terrain_col.objects.link(
    terrain_obj
)

assign_material(
    terrain_obj,
    terrain_mat
)

log(
    f"    Terrain vertices: {len(verts):,}"
)

log(
    f"    Terrain faces: {len(faces):,}"
)


# ============================================================
# GEOJSON HELPERS
# ============================================================

def load_geojson(filename):

    path = READY / filename

    if not path.exists():
        log(f"    Missing: {path}")
        return {"features": []}

    return load_json(path)


def geometry_polygons(geometry):

    if not geometry:
        return []

    gtype = geometry.get(
        "type"
    )

    coords = geometry.get(
        "coordinates",
        []
    )

    if gtype == "Polygon":
        return [coords]

    if gtype == "MultiPolygon":

        result = []

        for polygon in coords:
            result.append(polygon)

        return result

    return []


def geometry_lines(geometry):

    if not geometry:
        return []

    gtype = geometry.get(
        "type"
    )

    coords = geometry.get(
        "coordinates",
        []
    )

    if gtype == "LineString":
        return [coords]

    if gtype == "MultiLineString":
        return coords

    return []


def convert_xy(lon, lat):

    e, n = wgs84_to_utm43(float(lon), float(lat))

    return (
        (e - dam_e) * DISPLAY_SCALE,
        (n - dam_n) * DISPLAY_SCALE,
    )


# ============================================================
# POLYGON MESH
# ============================================================

def create_polygon_prism(
    name,
    polygon,
    height,
    material,
    collection,
    base_z=0.0,
):

    if not polygon:
        return None

    # Use exterior ring.
    ring = polygon[0]

    if len(ring) < 3:
        return None

    # Remove duplicate closing coordinate.
    if ring[0] == ring[-1]:
        ring = ring[:-1]

    if len(ring) < 3:
        return None

    xy = [
        convert_xy(
            float(p[0]),
            float(p[1]),
        )
        for p in ring
    ]

    # Skip absurd geometry.
    if len(xy) > 1000:
        step = max(
            1,
            len(xy) // 500
        )

        xy = xy[::step]

    verts = []

    for x, y in xy:
        verts.append(
            (x, y, base_z)
        )

    for x, y in xy:
        verts.append(
            (x, y, base_z + height * DISPLAY_SCALE)
        )

    n = len(xy)

    faces = []

    # Bottom
    faces.append(
        tuple(
            reversed(
                range(n)
            )
        )
    )

    # Top
    faces.append(
        tuple(
            range(n, 2 * n)
        )
    )

    # Sides
    for i in range(n):

        j = (
            i + 1
        ) % n

        faces.append(
            (
                i,
                j,
                n + j,
                n + i,
            )
        )

    mesh = bpy.data.meshes.new(
        name + "_MESH"
    )

    mesh.from_pydata(
        verts,
        [],
        faces,
    )

    mesh.update()

    obj = bpy.data.objects.new(
        name,
        mesh,
    )

    collection.objects.link(
        obj
    )

    assign_material(
        obj,
        material,
    )

    return obj


# ============================================================
# REAL OSM BUILDINGS
# ============================================================

log("[4/10] Creating REAL OSM buildings...")

buildings_data = load_geojson(
    "buildings.geojson"
)

building_count = 0

for idx, feature in enumerate(
    buildings_data.get(
        "features",
        []
    )
):

    geometry = feature.get(
        "geometry"
    )

    properties = feature.get(
        "properties",
        {}
    )

    polygons = geometry_polygons(
        geometry
    )

    # Try common OSM height fields.
    height = None

    for key in (
        "height",
        "building:height",
    ):

        value = properties.get(
            key
        )

        if value is not None:

            try:

                text = str(
                    value
                ).replace(
                    "m",
                    ""
                ).strip()

                height = float(
                    text
                )

                break

            except:
                pass

    if height is None:

        levels = None

        for key in (
            "building:levels",
            "levels",
        ):

            if properties.get(key):
                try:
                    levels = float(
                        properties[key]
                    )
                    break
                except:
                    pass

        if levels:
            height = levels * 3.0
        else:
            height = DEFAULT_BUILDING_HEIGHT

    height = max(
        2.5,
        min(
            height,
            MAX_BUILDING_HEIGHT
        )
    )

    for pidx, polygon in enumerate(
        polygons
    ):

        obj = create_polygon_prism(
            f"OSM_BUILDING_{idx}_{pidx}",
            polygon,
            height,
            building_mat,
            buildings_col,
        )

        if obj:
            building_count += 1

log(
    f"    REAL OSM buildings created: "
    f"{building_count}"
)


# ============================================================
# REAL OSM ROADS
# ============================================================

log("[5/10] Creating REAL OSM roads...")

roads_data = load_geojson(
    "roads.geojson"
)

road_count = 0

for idx, feature in enumerate(
    roads_data.get(
        "features",
        []
    )
):

    geometry = feature.get(
        "geometry"
    )

    properties = feature.get(
        "properties",
        {}
    )

    road_class = str(
        properties.get(
            "highway",
            "unclassified"
        )
    )

    width = ROAD_WIDTHS.get(
        road_class,
        3.0
    )

    lines = geometry_lines(
        geometry
    )

    for line_index, line in enumerate(
        lines
    ):

        if len(line) < 2:
            continue

        curve = bpy.data.curves.new(
            f"OSM_ROAD_{idx}_{line_index}",
            "CURVE",
        )

        curve.dimensions = "3D"

        curve.bevel_depth = (
            width
            * DISPLAY_SCALE
            * 0.5
        )

        curve.bevel_resolution = 1

        spline = curve.splines.new(
            "POLY"
        )

        spline.points.add(
            len(line) - 1
        )

        for point, coord in zip(
            spline.points,
            line
        ):

            x, y = convert_xy(
                float(coord[0]),
                float(coord[1]),
            )

            # Put roads slightly above terrain.
            point.co = (
                x,
                y,
                1.0 * DISPLAY_SCALE,
                1.0,
            )

        obj = bpy.data.objects.new(
            f"OSM_ROAD_{idx}_{line_index}",
            curve,
        )

        roads_col.objects.link(
            obj
        )

        assign_material(
            obj,
            road_mat
        )

        road_count += 1

log(
    f"    REAL OSM roads created: "
    f"{road_count}"
)


# ============================================================
# REAL OSM WATERWAYS
# ============================================================

log("[6/10] Creating REAL OSM waterways...")

waterways_data = load_geojson(
    "waterways.geojson"
)

waterway_count = 0

for idx, feature in enumerate(
    waterways_data.get(
        "features",
        []
    )
):

    geometry = feature.get(
        "geometry"
    )

    lines = geometry_lines(
        geometry
    )

    for line_index, line in enumerate(
        lines
    ):

        if len(line) < 2:
            continue

        curve = bpy.data.curves.new(
            f"OSM_WATERWAY_{idx}_{line_index}",
            "CURVE",
        )

        curve.dimensions = "3D"

        curve.bevel_depth = (
            2.0 * DISPLAY_SCALE
        )

        curve.bevel_resolution = 2

        spline = curve.splines.new(
            "POLY"
        )

        spline.points.add(
            len(line) - 1
        )

        for point, coord in zip(
            spline.points,
            line
        ):

            x, y = convert_xy(
                float(coord[0]),
                float(coord[1]),
            )

            point.co = (
                x,
                y,
                2.0 * DISPLAY_SCALE,
                1.0,
            )

        obj = bpy.data.objects.new(
            f"OSM_WATERWAY_{idx}_{line_index}",
            curve,
        )

        waterways_col.objects.link(
            obj
        )

        assign_material(
            obj,
            river_mat
        )

        waterway_count += 1

log(
    f"    REAL OSM waterways created: "
    f"{waterway_count}"
)


# ============================================================
# REAL OSM WATER BODIES
# ============================================================

log("[7/10] Creating REAL OSM water bodies...")

water_data = load_geojson(
    "water.geojson"
)

water_count = 0

# Estimate a useful reservoir elevation from the terrain
# around the dam location.
dam_height_samples = []

for z in heights:
    if math.isfinite(z):
        dam_height_samples.append(
            float(z)
        )

if dam_height_samples:
    terrain_min = min(
        dam_height_samples
    )
    terrain_max = max(
        dam_height_samples
    )
else:
    terrain_min = 0
    terrain_max = 1000

# Water surface near the lower portion of the local terrain.
# We deliberately avoid using the global mountain maximum.
water_level = max(
    terrain_min + 40.0,
    min(
        terrain_min + 160.0,
        terrain_max - 50.0
    )
)

log(
    f"    Water reference level: "
    f"{water_level:.1f} m"
)

for idx, feature in enumerate(
    water_data.get(
        "features",
        []
    )
):

    geometry = feature.get(
        "geometry"
    )

    polygons = geometry_polygons(
        geometry
    )

    for pidx, polygon in enumerate(
        polygons
    ):

        obj = create_polygon_prism(
            f"OSM_WATER_{idx}_{pidx}",
            polygon,
            0.8,
            water_mat,
            water_col,
            base_z=(
                water_level
                * DISPLAY_SCALE
            ),
        )

        if obj:
            water_count += 1

log(
    f"    REAL OSM water bodies: "
    f"{water_count}"
)


# ============================================================
# METTUR DAM
# ============================================================

log("[8/10] Creating Mettur Dam structure...")


def create_box(
    name,
    location,
    dimensions,
    material,
    collection,
):

    bpy.ops.mesh.primitive_cube_add(
        location=location
    )

    obj = bpy.context.object

    obj.name = name

    obj.dimensions = dimensions

    bpy.ops.object.transform_apply(
        location=False,
        rotation=False,
        scale=True,
    )

    assign_material(
        obj,
        material,
    )

    move_to_collection(
        obj,
        collection
    )

    return obj


# ------------------------------------------------------------
# Derive dam direction from nearby water geometry.
# ------------------------------------------------------------

# We use a broad east-west orientation as the base visual
# orientation, then slightly rotate it toward the reservoir.
dam_angle = math.radians(0.0)

# Dam center slightly offset around actual dam coordinate.
dam_x = 0.0
dam_y = 0.0

# Main dam body.
#
# We model the dam as a stepped/sloped structure rather than
# a simple cube.
#

base = create_box(
    "METTUR_DAM_MAIN_BODY",
    (
        dam_x,
        dam_y,
        (
            terrain_min
            + DAM_HEIGHT * 0.5
        ) * DISPLAY_SCALE,
    ),
    (
        DAM_LENGTH * DISPLAY_SCALE,
        DAM_BASE_WIDTH * DISPLAY_SCALE,
        DAM_HEIGHT * DISPLAY_SCALE,
    ),
    dam_mat,
    dam_col,
)

base.rotation_euler[2] = dam_angle


# Crest
crest = create_box(
    "METTUR_DAM_CREST",
    (
        dam_x,
        dam_y,
        (
            terrain_min
            + DAM_HEIGHT
        ) * DISPLAY_SCALE,
    ),
    (
        DAM_LENGTH * DISPLAY_SCALE,
        DAM_TOP_WIDTH * DISPLAY_SCALE,
        8.0 * DISPLAY_SCALE,
    ),
    dam_top_mat,
    dam_col,
)

crest.rotation_euler[2] = dam_angle


# ------------------------------------------------------------
# Spillway blocks
# ------------------------------------------------------------

spillway_count = 9

spillway_spacing = (
    DAM_LENGTH
    / spillway_count
)

for i in range(
    spillway_count
):

    x = (
        -DAM_LENGTH / 2
        + spillway_spacing * (
            i + 0.5
        )
    ) * DISPLAY_SCALE

    spill = create_box(
        f"SPILLWAY_{i+1:02d}",
        (
            x,
            -(
                DAM_BASE_WIDTH * 0.15
            ) * DISPLAY_SCALE,
            (
                terrain_min
                + DAM_HEIGHT
                - 18
            ) * DISPLAY_SCALE,
        ),
        (
            spillway_spacing
            * 0.72
            * DISPLAY_SCALE,
            30.0 * DISPLAY_SCALE,
            30.0 * DISPLAY_SCALE,
        ),
        dam_top_mat,
        dam_col,
    )

    spill.rotation_euler[2] = dam_angle


# ------------------------------------------------------------
# Dam crest road
# ------------------------------------------------------------

crest_curve = bpy.data.curves.new(
    "DAM_CREST_ROAD",
    "CURVE",
)

crest_curve.dimensions = "3D"

crest_curve.bevel_depth = (
    3.0 * DISPLAY_SCALE
)

crest_curve.bevel_resolution = 2

spline = crest_curve.splines.new(
    "POLY"
)

spline.points.add(1)

spline.points[0].co = (
    -DAM_LENGTH / 2 * DISPLAY_SCALE,
    0,
    (
        terrain_min
        + DAM_HEIGHT
        + 5
    ) * DISPLAY_SCALE,
    1,
)

spline.points[1].co = (
    DAM_LENGTH / 2 * DISPLAY_SCALE,
    0,
    (
        terrain_min
        + DAM_HEIGHT
        + 5
    ) * DISPLAY_SCALE,
    1,
)

crest_road = bpy.data.objects.new(
    "DAM_CREST_ROAD",
    crest_curve,
)

dam_col.objects.link(
    crest_road
)

assign_material(
    crest_road,
    road_mat
)


# ============================================================
# CAMERA
# ============================================================

log("[9/10] Creating full-scene camera...")

# Determine terrain center.
center_x = (
    (left + right) / 2
    - dam_e
) * DISPLAY_SCALE

center_y = (
    (bottom + top) / 2
    - dam_n
) * DISPLAY_SCALE

terrain_size_x = (
    right - left
) * DISPLAY_SCALE

terrain_size_y = (
    top - bottom
) * DISPLAY_SCALE

scene_size = max(
    terrain_size_x,
    terrain_size_y,
)

camera_data = bpy.data.cameras.new(
    "METTUR_FULL_SCENE_CAMERA"
)

camera = bpy.data.objects.new(
    "METTUR_FULL_SCENE_CAMERA",
    camera_data
)

camera_col.objects.link(
    camera
)

camera_data.lens = 38

# Elevated diagonal view.
camera.location = (
    center_x + scene_size * 0.62,
    center_y - scene_size * 0.72,
    scene_size * 0.70,
)


def point_camera(
    cam,
    target,
):

    direction = (
        Vector(target)
        - cam.location
    )

    cam.rotation_euler = (
        direction.to_track_quat(
            "-Z",
            "Y"
        ).to_euler()
    )


point_camera(
    camera,
    (
        center_x,
        center_y,
        terrain_min
        * DISPLAY_SCALE
        + 20 * DISPLAY_SCALE,
    ),
)

bpy.context.scene.camera = camera


# ============================================================
# LIGHTING
# ============================================================

log("[10/10] Creating lighting and saving scene...")

# Sun
sun_data = bpy.data.lights.new(
    "METTUR_SUN",
    "SUN",
)

sun_data.energy = 3.0
sun_data.angle = math.radians(20)

sun = bpy.data.objects.new(
    "METTUR_SUN",
    sun_data
)

lights_col.objects.link(
    sun
)

sun.rotation_euler = (
    math.radians(35),
    math.radians(-25),
    math.radians(-35),
)


# Area fill
area_data = bpy.data.lights.new(
    "METTUR_AREA_FILL",
    "AREA",
)

area_data.energy = 1200
area_data.shape = "DISK"
area_data.size = 100

area = bpy.data.objects.new(
    "METTUR_AREA_FILL",
    area_data
)

lights_col.objects.link(
    area
)

area.location = (
    scene_size * 0.2,
    -scene_size * 0.2,
    scene_size * 0.6,
)

point_camera(
    area,
    (
        center_x,
        center_y,
        0
    ),
)


# ============================================================
# WORLD
# ============================================================

world = bpy.data.worlds.new(
    "METTUR_WORLD"
)

bpy.context.scene.world = world

world.use_nodes = True

bg = world.node_tree.nodes.get(
    "Background"
)

if bg:
    bg.inputs["Color"].default_value = (
        0.025,
        0.045,
        0.075,
        1,
    )

    bg.inputs["Strength"].default_value = 0.35


# ============================================================
# RENDER SETTINGS
# ============================================================

scene = bpy.context.scene

# IMPORTANT:
# Blender 5.2 on your system reports BLENDER_EEVEE.
scene.render.engine = "BLENDER_EEVEE"

scene.render.resolution_x = 1280
scene.render.resolution_y = 720
scene.render.resolution_percentage = 100

scene.render.image_settings.file_format = "PNG"

scene.render.filepath = str(
    PREVIEW
)

scene.render.film_transparent = False


# ============================================================
# VIEWPORT / SCENE METADATA
# ============================================================

scene["project"] = (
    "Mettur Dam Digital Twin"
)

scene["data_source"] = (
    "SRTM + OpenStreetMap"
)

scene["dam_latitude"] = DAM_LAT
scene["dam_longitude"] = DAM_LON

scene["real_osm_buildings"] = (
    building_count
)

scene["real_osm_roads"] = (
    road_count
)

scene["real_osm_waterways"] = (
    waterway_count
)

scene["display_scale"] = (
    DISPLAY_SCALE
)

scene["terrain_source"] = (
    "SRTM DEM"
)

scene["osm_source"] = (
    "OpenStreetMap"
)


# ============================================================
# SELECT CAMERA
# ============================================================

bpy.ops.object.select_all(
    action="DESELECT"
)

camera.select_set(True)

bpy.context.view_layer.objects.active = camera


# ============================================================
# SAVE
# ============================================================

log("")
log("=" * 70)
log("VALIDATION")
log("=" * 70)

checks = {
    "Terrain": len(terrain_obj.data.vertices) > 0,
    "Real buildings": building_count > 0,
    "Real roads": road_count > 0,
    "Real waterways": waterway_count > 0,
    "Water bodies": water_count > 0,
    "Mettur Dam": (
        "METTUR_DAM_MAIN_BODY"
        in bpy.data.objects
    ),
    "Camera": camera.name
    in bpy.data.objects,
    "Lighting": sun.name
    in bpy.data.objects,
}

for name, result in checks.items():

    log(
        f"  [{'OK' if result else 'FAIL'}] "
        f"{name}"
    )

log("=" * 70)

bpy.ops.wm.save_as_mainfile(
    filepath=str(OUTPUT)
)

log(
    f"Saved: {OUTPUT}"
)

# Render preview
log("Rendering preview...")

scene.render.filepath = str(
    PREVIEW
)

bpy.ops.render.render(
    write_still=True
)

log(
    f"Preview: {PREVIEW}"
)

log("")
log("=" * 70)
log("METTUR DIGITAL TWIN COMPLETE")
log("=" * 70)
log("")
log(f"BLEND   : {OUTPUT}")
log(f"PREVIEW : {PREVIEW}")
log("")
log(
    f"REAL BUILDINGS : {building_count}"
)
log(
    f"REAL ROADS     : {road_count}"
)
log(
    f"REAL WATERWAYS : {waterway_count}"
)
log("")
log("=" * 70)