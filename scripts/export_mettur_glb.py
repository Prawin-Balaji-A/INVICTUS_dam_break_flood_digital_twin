"""
Official Blender 5.2 GLB export script for Mettur Dam Digital Twin.
Exports the complete scene:
- METTUR_REAL_TERRAIN (438,900 vertices)
- METTUR_DAM (dam, crest, structures)
- METTUR_RESERVOIR (2 water bodies)
- OSM_BUILDINGS (78 buildings)
- OSM_ROADS (1802 roads)
- OSM_WATERWAYS (24 waterways)
- Materials & textures
"""
import bpy
import os

OUTPUT_PATH = r"E:\dam\frontend\public\models\mettur\mettur_scene.glb"
os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)

print("[EXPORT] Starting Mettur GLB export...")

# Select all scene objects except cameras and lights
bpy.ops.object.select_all(action='DESELECT')

SKIP_TYPES = {"CAMERA", "LIGHT"}

exported_count = 0
for obj in bpy.data.objects:
    if obj.type in SKIP_TYPES:
        continue
    obj.select_set(True)
    exported_count += 1

print(f"[EXPORT] Selected {exported_count} objects for export")

try:
    bpy.ops.export_scene.gltf(
        filepath=OUTPUT_PATH,
        export_format='GLB',
        use_selection=True,
        export_yup=True,
        export_apply=True,
        export_materials='EXPORT',
        export_texcoords=True,
        export_normals=True,
        export_animations=True,
    )
    print(f"[EXPORT] Export completed successfully!")
except Exception as e:
    print(f"[EXPORT] Standard export failed: {e}. Trying fallback...")
    bpy.ops.export_scene.gltf(
        filepath=OUTPUT_PATH,
        export_format='GLB',
        use_selection=True,
        export_yup=True,
        export_apply=True,
    )

if os.path.exists(OUTPUT_PATH):
    size_mb = os.path.getsize(OUTPUT_PATH) / (1024 * 1024)
    print(f"[EXPORT COMPLETE] {OUTPUT_PATH}")
    print(f"  File size: {size_mb:.2f} MB")
    print(f"  Objects exported: {exported_count}")
else:
    print("[EXPORT FAILED] Output file not found!")
