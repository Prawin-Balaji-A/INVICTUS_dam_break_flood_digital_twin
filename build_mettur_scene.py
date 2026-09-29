import bpy
import os
import json
import math
import struct

from mathutils import Vector

# ============================================================
# METTUR DAM DIGITAL TWIN
# Blender 5.2 compatible
# ============================================================

BASE = r"E:\dam\mettur_data"
READY = os.path.join(BASE, "blender_ready")
OUTPUT = r"E:\dam\mettur_dam_digital_twin.blend"

TERRAIN_FILE = os.path.join(READY, "terrain_heightmap.f32")
TERRAIN_META = os.path.join(READY, "terrain_meta.json")

BUILDINGS_FILE = os.path.join(READY, "buildings.geojson")
ROADS_FILE = os.path.join(READY, "roads.geojson")
WATERWAYS_FILE = os.path.join(READY, "waterways.geojson")
WATER_FILE = os.path.join(READY, "water.geojson")

print("=" * 70)
print("METTUR DAM DIGITAL TWIN")
print("=" * 70)


# ============================================================
# CLEAN SCENE
# ============================================================

bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)

for datablocks in (
    bpy.data.meshes,
    bpy.data.curves,
    bpy.data.materials,
    bpy.data.cameras,
    bpy.data.lights,
):
    pass


# ============================================================
# MATERIAL
# ============================================================

def material(name, color, metallic=0.0, roughness=0.6):

    mat = bpy.data.materials.get(name)

    if mat is None:
        mat = bpy.data.materials.new(name)

    mat.diffuse_color = (*color, 1.0)

    mat.use_nodes = True

    bsdf = mat.node_tree.nodes.get("Principled BSDF")

    if bsdf:
        bsdf.inputs["Base Color"].default_value = (*color, 1.0)
        bsdf.inputs["Roughness"].default_value = roughness
        bsdf.inputs["Metallic"].default_value = metallic

    return mat


MAT_TERRAIN = material(
    "Terrain",
    (0.24, 0.38, 0.18),
    0.0,
    0.9
)

MAT_ROAD = material(
    "Road",
    (0.08, 0.08, 0.07),
    0.0,
    0.9
)

MAT_BUILDING = material(
    "Buildings",
    (0.55, 0.48, 0.38),
    0.0,
    0.8
)

MAT_WATER = material(
    "Reservoir",
    (0.03, 0.22, 0.55),
    0.1,
    0.25
)

MAT_WATERWAY = material(
    "Waterways",
    (0.02, 0.30, 0.65),
    0.1,
    0.25
)

MAT_DAM = material(
    "Mettur Dam",
    (0.32, 0.30, 0.27),
    0.0,
    0.8
)

MAT_DAM_TOP = material(
    "Dam Concrete",
    (0.55, 0.53, 0.49),
    0.0,
    0.65
)


# ============================================================
# LOAD TERRAIN
# ============================================================

print("[1/7] Loading terrain...")

with open(TERRAIN_META, "r") as f:
    meta = json.load(f)

width = meta["width"]
height = meta["height"]

bounds = meta["bounds"]

left = bounds["left"]
right = bounds["right"]
bottom = bounds["bottom"]
top = bounds["top"]

with open(TERRAIN_FILE, "rb") as f:
    data = f.read()

elevations = struct.unpack(
    "<" + "f" * (len(data) // 4),
    data
)

if len(elevations) != width * height:
    raise RuntimeError("Terrain data size mismatch.")

print("    Grid:", width, "x", height)
print(
    "    Elevation:",
    min(elevations),
    "to",
    max(elevations)
)


# ============================================================
# TERRAIN MESH
# ============================================================

print("[2/7] Creating terrain mesh...")

# Local coordinate dimensions
terrain_width = right - left
terrain_depth = top - bottom

# Convert metres to Blender units.
# 1 Blender unit = 10 metres.
SCALE = 0.1

vertices = []
faces = []

for y in range(height):

    fy = y / (height - 1)

    for x in range(width):

        fx = x / (width - 1)

        px = (fx - 0.5) * terrain_width * SCALE
        py = (fy - 0.5) * terrain_depth * SCALE

        elevation = elevations[y * width + x]

        pz = elevation * SCALE

        vertices.append((px, py, pz))


for y in range(height - 1):

    for x in range(width - 1):

        a = y * width + x
        b = a + 1
        c = a + width + 1
        d = a + width

        faces.append((a, b, c, d))


mesh = bpy.data.meshes.new("Mettur_Terrain_Mesh")
mesh.from_pydata(vertices, [], faces)
mesh.update()

terrain = bpy.data.objects.new(
    "METTUR_REAL_TERRAIN",
    mesh
)

bpy.context.collection.objects.link(terrain)

terrain.data.materials.append(MAT_TERRAIN)

print(
    "    Terrain vertices:",
    len(vertices)
)

print(
    "    Terrain faces:",
    len(faces)
)


# ============================================================
# GEOJSON HELPERS
# ============================================================

def load_geojson(path):

    if not os.path.exists(path):
        print("    Missing:", path)
        return []

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f).get("features", [])


def lonlat_to_local(lon, lat):

    # Approximate local conversion around Mettur.
    # Suitable for visual scene construction.

    center_lon = 77.75
    center_lat = 11.75

    meters_per_degree_lon = (
        111320 * math.cos(math.radians(center_lat))
    )

    meters_per_degree_lat = 111320

    x = (
        (lon - center_lon)
        * meters_per_degree_lon
        * SCALE
    )

    y = (
        (lat - center_lat)
        * meters_per_degree_lat
        * SCALE
    )

    return x, y


# ============================================================
# BUILDINGS
# ============================================================

print("[3/7] Creating OSM buildings...")

building_features = load_geojson(BUILDINGS_FILE)

building_count = 0

for feature in building_features:

    geometry = feature.get("geometry")

    if not geometry:
        continue

    coords = geometry.get("coordinates")

    if geometry["type"] == "Polygon":
        polygons = [coords]

    elif geometry["type"] == "MultiPolygon":

        polygons = []

        for p in coords:
            polygons.extend(p)

    else:
        continue

    for polygon in polygons:

        if not polygon:
            continue

        ring = polygon[0]

        points = []

        for lon, lat in ring:

            x, y = lonlat_to_local(lon, lat)

            points.append((x, y))

        if len(points) < 3:
            continue

        minx = min(p[0] for p in points)
        maxx = max(p[0] for p in points)

        miny = min(p[1] for p in points)
        maxy = max(p[1] for p in points)

        cx = (minx + maxx) / 2
        cy = (miny + maxy) / 2

        sx = max(0.5, maxx - minx)
        sy = max(0.5, maxy - miny)

        bpy.ops.mesh.primitive_cube_add(
            location=(cx, cy, 3.0)
        )

        obj = bpy.context.object

        obj.name = "OSM_BUILDING"

        obj.scale = (
            sx / 2,
            sy / 2,
            0.3
        )

        obj.data.materials.append(
            MAT_BUILDING
        )

        building_count += 1

print("    Buildings:", building_count)


# ============================================================
# ROADS
# ============================================================

print("[4/7] Creating OSM roads...")

road_features = load_geojson(ROADS_FILE)

road_count = 0

for feature in road_features:

    geometry = feature.get("geometry")

    if not geometry:
        continue

    if geometry["type"] == "LineString":

        lines = [geometry["coordinates"]]

    elif geometry["type"] == "MultiLineString":

        lines = geometry["coordinates"]

    else:
        continue

    for line in lines:

        if len(line) < 2:
            continue

        curve = bpy.data.curves.new(
            "OSM_ROAD",
            "CURVE"
        )

        curve.dimensions = "3D"
        curve.bevel_depth = 0.045
        curve.bevel_resolution = 1

        spline = curve.splines.new("POLY")
        spline.points.add(len(line) - 1)

        for i, point in enumerate(line):

            lon = point[0]
            lat = point[1]

            x, y = lonlat_to_local(
                lon,
                lat
            )

            spline.points[i].co = (
                x,
                y,
                0.15,
                1
            )

        obj = bpy.data.objects.new(
            "OSM_ROAD",
            curve
        )

        bpy.context.collection.objects.link(obj)

        curve.materials.append(
            MAT_ROAD
        )

        road_count += 1

print("    Roads:", road_count)


# ============================================================
# WATER
# ============================================================

print("[5/7] Creating OSM water bodies...")

water_features = load_geojson(WATER_FILE)

water_count = 0

for feature in water_features:

    geometry = feature.get("geometry")

    if not geometry:
        continue

    if geometry["type"] == "Polygon":

        polygons = [geometry["coordinates"]]

    elif geometry["type"] == "MultiPolygon":

        polygons = []

        for p in geometry["coordinates"]:
            polygons.extend(p)

    else:
        continue

    for polygon in polygons:

        if not polygon:
            continue

        ring = polygon[0]

        verts = []

        for lon, lat in ring:

            x, y = lonlat_to_local(
                lon,
                lat
            )

            verts.append(
                (x, y, 5.0)
            )

        if len(verts) < 3:
            continue

        mesh = bpy.data.meshes.new(
            "ReservoirMesh"
        )

        mesh.from_pydata(
            verts,
            [],
            [tuple(range(len(verts)))]
        )

        mesh.update()

        obj = bpy.data.objects.new(
            "METTUR_RESERVOIR",
            mesh
        )

        bpy.context.collection.objects.link(obj)

        mesh.materials.append(
            MAT_WATER
        )

        water_count += 1

print("    Water bodies:", water_count)


# ============================================================
# WATERWAYS
# ============================================================

print("[6/7] Creating waterways...")

waterway_features = load_geojson(
    WATERWAYS_FILE
)

waterway_count = 0

for feature in waterway_features:

    geometry = feature.get("geometry")

    if not geometry:
        continue

    if geometry["type"] == "LineString":

        lines = [geometry["coordinates"]]

    elif geometry["type"] == "MultiLineString":

        lines = geometry["coordinates"]

    else:
        continue

    for line in lines:

        if len(line) < 2:
            continue

        curve = bpy.data.curves.new(
            "Waterway",
            "CURVE"
        )

        curve.dimensions = "3D"
        curve.bevel_depth = 0.06
        curve.bevel_resolution = 2

        spline = curve.splines.new("POLY")

        spline.points.add(
            len(line) - 1
        )

        for i, point in enumerate(line):

            x, y = lonlat_to_local(
                point[0],
                point[1]
            )

            spline.points[i].co = (
                x,
                y,
                0.20,
                1
            )

        obj = bpy.data.objects.new(
            "OSM_WATERWAY",
            curve
        )

        bpy.context.collection.objects.link(obj)

        curve.materials.append(
            MAT_WATERWAY
        )

        waterway_count += 1

print("    Waterways:", waterway_count)


# ============================================================
# METTUR DAM
# ============================================================

print("[7/7] Creating Mettur Dam...")

# Approximate visual location near Mettur reservoir.
# Positioned near the geographic center of the supplied AOI.

dam_x, dam_y = lonlat_to_local(
    77.80,
    11.78
)

# Dam dimensions in Blender units.
# Real-world dimensions are represented approximately.

dam_length = 170.0
dam_height = 16.0
dam_width = 6.0

bpy.ops.mesh.primitive_cube_add(
    location=(
        dam_x,
        dam_y,
        dam_height / 2
    )
)

dam = bpy.context.object

dam.name = "METTUR_DAM"

dam.scale = (
    dam_length / 2,
    dam_width / 2,
    dam_height / 2
)

dam.data.materials.append(
    MAT_DAM
)

# Crest
bpy.ops.mesh.primitive_cube_add(
    location=(
        dam_x,
        dam_y,
        dam_height + 1
    )
)

crest = bpy.context.object

crest.name = "METTUR_DAM_CREST"

crest.scale = (
    dam_length / 2,
    dam_width / 2 + 0.5,
    0.7
)

crest.data.materials.append(
    MAT_DAM_TOP
)


# ============================================================
# DAM TOWERS / STRUCTURES
# ============================================================

for i in range(8):

    x = (
        dam_x
        - dam_length / 2
        + (i + 0.5)
        * dam_length / 8
    )

    bpy.ops.mesh.primitive_cube_add(
        location=(
            x,
            dam_y,
            dam_height + 5
        )
    )

    tower = bpy.context.object

    tower.name = "METTUR_DAM_STRUCTURE"

    tower.scale = (
        1.5,
        2.0,
        4.0
    )

    tower.data.materials.append(
        MAT_DAM_TOP
    )


# ============================================================
# CAMERA
# ============================================================

print("\nCreating full-scene camera...")

# Calculate overall scene dimensions.
scene_size = max(
    terrain_width,
    terrain_depth
) * SCALE

camera_distance = scene_size * 0.75

bpy.ops.object.camera_add(
    location=(
        camera_distance * 0.65,
        -camera_distance * 0.65,
        camera_distance * 0.55
    )
)

camera = bpy.context.object

camera.name = "METTUR_MAIN_CAMERA"

bpy.context.scene.camera = camera

# Point camera toward origin
direction = Vector((0, 0, 0)) - camera.location

camera.rotation_euler = direction.to_track_quat(
    "-Z",
    "Y"
).to_euler()

camera.data.lens = 42


# ============================================================
# LIGHTING
# ============================================================

print("Creating lighting...")

bpy.ops.object.light_add(
    type="SUN",
    location=(0, 0, 1000)
)

sun = bpy.context.object

sun.name = "SUN"

sun.data.energy = 4.0

sun.rotation_euler = (
    math.radians(25),
    math.radians(-20),
    math.radians(25)
)


bpy.ops.object.light_add(
    type="AREA",
    location=(0, -300, 500)
)

area = bpy.context.object

area.name = "AREA_FILL"

area.data.energy = 1500
area.data.shape = "DISK"
area.data.size = 500


# ============================================================
# WORLD
# ============================================================

world = bpy.context.scene.world

if world is None:
    world = bpy.data.worlds.new("World")
    bpy.context.scene.world = world

world.use_nodes = True

bg = world.node_tree.nodes.get(
    "Background"
)

if bg:
    bg.inputs["Color"].default_value = (
        0.05,
        0.08,
        0.12,
        1
    )

    bg.inputs["Strength"].default_value = 0.35


# ============================================================
# RENDER SETTINGS
# ============================================================

scene = bpy.context.scene

scene.render.engine = "BLENDER_EEVEE"

scene.render.resolution_x = 1280
scene.render.resolution_y = 720
scene.render.resolution_percentage = 60

scene.render.image_settings.file_format = "PNG"

scene.render.filepath = (
    r"E:\dam\mettur_dam_preview.png"
)


# ============================================================
# SCENE METADATA
# ============================================================

scene["PROJECT"] = "Mettur Dam Digital Twin"

scene["TERRAIN_SOURCE"] = "SRTM DEM"

scene["VECTOR_SOURCE"] = (
    "OpenStreetMap / Overpass API"
)

scene["BUILDINGS"] = building_count
scene["ROADS"] = road_count
scene["WATER_BODIES"] = water_count
scene["WATERWAYS"] = waterway_count


# ============================================================
# SAVE
# ============================================================

print("\nSaving Blender file...")

bpy.ops.wm.save_as_mainfile(
    filepath=OUTPUT
)

print("\nRendering preview...")

bpy.ops.render.render(
    write_still=True
)

print("\n" + "=" * 70)
print("METTUR DAM DIGITAL TWIN COMPLETE")
print("=" * 70)

print("BLEND:")
print(OUTPUT)

print("\nPREVIEW:")
print(r"E:\dam\mettur_dam_preview.png")

print("=" * 70)