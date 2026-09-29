import bpy
import os

print("=== METTUR BLEND INSPECTION ===")
print("Scene objects count:", len(bpy.data.objects))
print("Meshes count:", len(bpy.data.meshes))
print("Curves count:", len(bpy.data.curves))
print("Materials count:", len(bpy.data.materials))

for mat in bpy.data.materials:
    print(f"Material: {mat.name}")
    if mat.use_nodes:
        for node in mat.node_tree.nodes:
            if node.type == 'BSDF_PRINCIPLED':
                color = node.inputs['Base Color'].default_value[:]
                print(f"  Principled color: {color}, rough: {node.inputs['Roughness'].default_value}")

# Check curve objects
curve_objs = [o for o in bpy.data.objects if o.type == 'CURVE']
print(f"Total curve objects: {len(curve_objs)}")
if curve_objs:
    first = curve_objs[0]
    print(f"Sample curve: {first.name}, bevel_depth={first.data.bevel_depth}, splines={len(first.data.splines)}")

# Check mesh objects
mesh_objs = [o for o in bpy.data.objects if o.type == 'MESH']
print(f"Total mesh objects: {len(mesh_objs)}")
for m in mesh_objs[:10]:
    print(f"Mesh obj: {m.name}, verts={len(m.data.vertices)}, faces={len(m.data.polygons)}")

# Check camera and lights
for o in bpy.data.objects:
    if o.type in ('CAMERA', 'LIGHT'):
        print(f"{o.type}: {o.name}, loc={o.location[:]}")
