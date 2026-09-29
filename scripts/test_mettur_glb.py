import bpy
import os

print("=== TESTING METTUR GLB EXPORT ===")

# Check if curves export directly to glTF in Blender 5.2
test_output = r"E:\dam\frontend\public\models\mettur\test_direct.glb"
os.makedirs(os.path.dirname(test_output), exist_ok=True)

# Let's see what happens if we select all objects except lights and cameras
bpy.ops.object.select_all(action='DESELECT')
for obj in bpy.data.objects:
    if obj.type not in ('CAMERA', 'LIGHT'):
        obj.select_set(True)

print(f"Selected {len([o for o in bpy.data.objects if o.select_get()])} objects")

try:
    bpy.ops.export_scene.gltf(
        filepath=test_output,
        export_format='GLB',
        use_selection=True,
        export_yup=True,
        export_apply=True
    )
    if os.path.exists(test_output):
        sz = os.path.getsize(test_output) / (1024*1024)
        print(f"Direct export succeeded! Size: {sz:.2f} MB")
except Exception as e:
    print(f"Direct export failed: {e}")
