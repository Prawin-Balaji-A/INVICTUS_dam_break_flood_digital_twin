import bpy

# ============================================================
# METTUR DAM — SCALE ENTIRE SCENE
# ============================================================

SCALE = 0.10

print("=" * 60)
print("SCALING METTUR DAM DIGITAL TWIN")
print("=" * 60)

# Create a parent empty
bpy.ops.object.empty_add(type='PLAIN_AXES', location=(0, 0, 0))
root = bpy.context.object
root.name = "METTUR_SCENE_ROOT"

# Parent every existing object except the new root
objects = [obj for obj in bpy.context.scene.objects if obj != root]

for obj in objects:
    obj.parent = root

# Scale entire scene uniformly
root.scale = (SCALE, SCALE, SCALE)

# Apply scale to root
bpy.context.view_layer.objects.active = root
root.select_set(True)

bpy.ops.object.transform_apply(
    location=False,
    rotation=False,
    scale=True
)

# Select everything
bpy.ops.object.select_all(action='SELECT')

# Frame everything in viewport
for area in bpy.context.screen.areas:
    if area.type == 'VIEW_3D':
        region = next(
            (r for r in area.regions if r.type == 'WINDOW'),
            None
        )

        if region:
            with bpy.context.temp_override(
                area=area,
                region=region
            ):
                bpy.ops.view3d.view_all()

# Save
output = r"E:\dam\mettur_dam_digital_twin_scaled.blend"

bpy.ops.wm.save_as_mainfile(filepath=output)

print("=" * 60)
print("SCALING COMPLETE")
print("Scale:", SCALE)
print("Saved:", output)
print("=" * 60)