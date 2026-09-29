"""
Blender 5.2 GLB export script - Blender 5.x compatible args
"""

import bpy
import os

OUTPUT_PATH = r"E:\dam\frontend\public\models\tehri\tehri_scene.glb"

print("[EXPORT] Starting Tehri GLB export...")

# Select only the mesh/effect objects for export
bpy.ops.object.select_all(action='DESELECT')

SKIP_COLLECTIONS = {"TEHRI_CAMERAS", "TEHRI_LIGHTING"}
SKIP_TYPES = {"CAMERA", "LIGHT"}

exported_count = 0
for obj in bpy.data.objects:
    if obj.type in SKIP_TYPES:
        continue
    in_skip_collection = any(c.name in SKIP_COLLECTIONS for c in obj.users_collection)
    if in_skip_collection:
        continue
    obj.select_set(True)
    exported_count += 1

print(f"[EXPORT] Selected {exported_count} objects for export")

os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)

# First try to see what parameters are available in this version
import inspect
try:
    # Get the RNA type for the operator to know valid parameters
    op = bpy.ops.export_scene.gltf
    print("[EXPORT] Attempting GLB export...")
    
    result = bpy.ops.export_scene.gltf(
        filepath=OUTPUT_PATH,
        export_format='GLB',
        use_selection=True,
        export_apply=True,
        export_animations=True,
        export_frame_range=True,
        export_frame_step=1,
        export_force_sampling=True,
        export_nla_strips=False,
        export_skins=False,
        export_morph=False,
        export_lights=False,
        export_cameras=False,
        export_materials='EXPORT',
        export_image_format='AUTO',
        export_texcoords=True,
        export_normals=True,
        export_yup=True,
    )
    print(f"[EXPORT] Result: {result}")
except TypeError as e:
    print(f"[EXPORT] First attempt failed: {e}")
    print("[EXPORT] Trying minimal parameter set...")
    try:
        result = bpy.ops.export_scene.gltf(
            filepath=OUTPUT_PATH,
            export_format='GLB',
            use_selection=True,
            export_apply=True,
            export_animations=True,
            export_yup=True,
        )
        print(f"[EXPORT] Result: {result}")
    except Exception as e2:
        print(f"[EXPORT] Minimal attempt also failed: {e2}")
        print("[EXPORT] Attempting bare minimum...")
        result = bpy.ops.export_scene.gltf(
            filepath=OUTPUT_PATH,
            export_format='GLB',
            use_selection=True,
        )
        print(f"[EXPORT] Result: {result}")

if os.path.exists(OUTPUT_PATH):
    file_size = os.path.getsize(OUTPUT_PATH) / (1024 * 1024)
    print(f"[EXPORT COMPLETE] {OUTPUT_PATH}")
    print(f"  File size: {file_size:.2f} MB")
    print(f"  Objects selected: {exported_count}")
else:
    print("[EXPORT FAILED] Output file not found!")
