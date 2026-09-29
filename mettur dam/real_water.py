import bpy

# ==========================================
# Helper: Safely move object to a collection
# ==========================================
def move_to_collection(obj, target_collection):
    # Link to target if not already there
    if target_collection.name not in [c.name for c in obj.users_collection]:
        target_collection.objects.link(obj)
    # Unlink from all other collections (prevents the RuntimeError)
    for coll in obj.users_collection:
        if coll.name != target_collection.name:
            coll.objects.unlink(obj)

# ==========================================
# 1. SETUP & REALISTIC WATER MATERIAL
# ==========================================
sim_collection_name = "Water_Simulation"
if sim_collection_name in bpy.data.collections:
    sim_collection = bpy.data.collections[sim_collection_name]
else:
    sim_collection = bpy.data.collections.new(sim_collection_name)
    bpy.context.scene.collection.children.link(sim_collection)

mat_water = bpy.data.materials.new(name="Realistic_Water")
mat_water.use_nodes = True
bsdf = mat_water.node_tree.nodes.get("Principled BSDF")

if bsdf:
    if "Transmission Weight" in bsdf.inputs: # Blender 4.0+
        bsdf.inputs["Transmission Weight"].default_value = 1.0
    elif "Transmission" in bsdf.inputs:      # Blender 3.x
        bsdf.inputs["Transmission"].default_value = 1.0
        
    bsdf.inputs["Roughness"].default_value = 0.02
    bsdf.inputs["IOR"].default_value = 1.333 
    bsdf.inputs["Base Color"].default_value = (0.85, 0.95, 1.0, 1.0) 

# ==========================================
# 2. CREATE THE EFFECTOR (Collision Basin)
# ==========================================
tub_verts = [
    (-4, -4, 0), (4, -4, 0), (4, 4, 0), (-4, 4, 0),
    (-4, -4, 3), (4, -4, 3), (4, 4, 3), (-4, 4, 3),
    (-3.5, -3.5, 0.5), (3.5, -3.5, 0.5), (3.5, 3.5, 0.5), (-3.5, 3.5, 0.5),
    (-3.5, -3.5, 3), (3.5, -3.5, 3), (3.5, 3.5, 3), (-3.5, 3.5, 3)
]
tub_faces = [
    (0,1,5,4), (1,2,6,5), (2,3,7,6), (3,0,4,7), (0,3,2,1),
    (4,5,13,12), (5,6,14,13), (6,7,15,14), (7,4,12,15),
    (12,13,9,8), (13,14,10,9), (14,15,11,10), (15,12,8,11),
    (8,9,10,11)
]

tub_mesh = bpy.data.meshes.new("Basin_Mesh")
tub_mesh.from_pydata(tub_verts, [], tub_faces)
tub_obj = bpy.data.objects.new("Collision_Basin", tub_mesh)

move_to_collection(tub_obj, sim_collection)

bpy.context.view_layer.objects.active = tub_obj
bpy.ops.object.modifier_add(type='FLUID')
tub_obj.modifiers["Fluid"].fluid_type = 'EFFECTOR'
tub_obj.modifiers["Fluid"].effector_settings.effector_type = 'COLLISION'
tub_obj.modifiers["Fluid"].effector_settings.surface_distance = 0.1 

# ==========================================
# 3. CREATE THE FLOW (Water Entity)
# ==========================================
bpy.ops.mesh.primitive_uv_sphere_add(radius=1.5, location=(0, 0, 6.5))
water_entity = bpy.context.active_object
water_entity.name = "Water_Sphere_Entity"

move_to_collection(water_entity, sim_collection)

bpy.ops.object.modifier_add(type='FLUID')
water_entity.modifiers["Fluid"].fluid_type = 'FLOW'
water_entity.modifiers["Fluid"].flow_settings.flow_type = 'LIQUID'
water_entity.modifiers["Fluid"].flow_settings.flow_behavior = 'GEOMETRY' 

# ==========================================
# 4. CREATE THE DOMAIN (The Simulation Box)
# ==========================================
bpy.ops.mesh.primitive_cube_add(size=10, location=(0, 0, 4.5))
domain = bpy.context.active_object
domain.name = "Water_Domain"

move_to_collection(domain, sim_collection)

bpy.ops.object.modifier_add(type='FLUID')
domain.modifiers["Fluid"].fluid_type = 'DOMAIN'
domain.modifiers["Fluid"].domain_settings.domain_type = 'LIQUID'

domain_settings = domain.modifiers["Fluid"].domain_settings
domain_settings.resolution_max = 64
domain_settings.use_mesh = True
domain_settings.cache_type = 'REPLAY'

domain.data.materials.append(mat_water)
bpy.ops.object.shade_smooth()
domain.display_type = 'WIRE'

print("Water simulation rig generated successfully! Press Spacebar to play/simulate.")