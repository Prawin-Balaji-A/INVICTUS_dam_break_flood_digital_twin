"""
Blender 5.2 scene inspector for mettur_dam_digital_twin.blend
Outputs a comprehensive JSON report.
"""
import bpy
import json
import os
import math

def safe_list(v):
    try:
        return [round(float(x), 4) for x in v]
    except Exception:
        return str(v)

def inspect_material(mat):
    if mat is None:
        return None
    info = {"name": mat.name, "blend_method": mat.blend_method, "nodes": []}
    if mat.use_nodes and mat.node_tree:
        for node in mat.node_tree.nodes:
            nd = {"type": node.type, "name": node.name}
            if node.type == "BSDF_PRINCIPLED":
                nd["base_color"] = safe_list(node.inputs["Base Color"].default_value) if "Base Color" in node.inputs else None
                nd["roughness"] = round(float(node.inputs["Roughness"].default_value), 4) if "Roughness" in node.inputs else None
                nd["metallic"] = round(float(node.inputs["Metallic"].default_value), 4) if "Metallic" in node.inputs else None
                nd["alpha"] = round(float(node.inputs["Alpha"].default_value), 4) if "Alpha" in node.inputs else None
                nd["emission"] = safe_list(node.inputs["Emission Color"].default_value) if "Emission Color" in node.inputs else None
                nd["transmission"] = round(float(node.inputs["Transmission Weight"].default_value), 4) if "Transmission Weight" in node.inputs else None
            info["nodes"].append(nd)
    return info

def inspect_collection(col, depth=0):
    info = {
        "name": col.name,
        "depth": depth,
        "hide_viewport": col.hide_viewport,
        "objects": [o.name for o in col.objects],
        "children": [inspect_collection(c, depth + 1) for c in col.children]
    }
    return info

def get_action_frame_range(action):
    if action is None:
        return None
    fcurves = action.fcurves
    if not fcurves:
        return None
    frames = []
    for fc in fcurves:
        for kp in fc.keyframe_points:
            frames.append(kp.co.x)
    if not frames:
        return None
    return [min(frames), max(frames)]

def inspect_object(obj):
    info = {
        "name": obj.name,
        "type": obj.type,
        "location": safe_list(obj.location),
        "rotation_euler_deg": [round(math.degrees(r), 2) for r in obj.rotation_euler],
        "scale": safe_list(obj.scale),
        "visible": not obj.hide_get(),
        "render_visible": not obj.hide_render,
        "collections": [c.name for c in obj.users_collection],
        "parent": obj.parent.name if obj.parent else None,
    }

    if obj.type == "MESH" and obj.data:
        mesh = obj.data
        info["mesh_name"] = mesh.name
        info["vertices"] = len(mesh.vertices)
        info["polygons"] = len(mesh.polygons)
        info["has_uv"] = bool(mesh.uv_layers)
        info["uv_layers"] = [uv.name for uv in mesh.uv_layers]
        info["materials"] = [inspect_material(m) for m in mesh.materials]
        info["modifiers"] = [{"name": m.name, "type": m.type} for m in obj.modifiers]
        info["shape_keys"] = list(obj.data.shape_keys.key_blocks.keys()) if obj.data.shape_keys else []
        # Particle systems
        info["particle_systems"] = [ps.name for ps in obj.particle_systems]

    elif obj.type == "CAMERA" and obj.data:
        cam = obj.data
        info["lens_mm"] = cam.lens
        info["clip_start"] = cam.clip_start
        info["clip_end"] = cam.clip_end

    elif obj.type == "LIGHT" and obj.data:
        light = obj.data
        info["light_type"] = light.type
        info["energy"] = round(light.energy, 2)
        info["color"] = safe_list(light.color)
        if hasattr(light, "shadow_soft_size"):
            info["shadow_soft_size"] = round(light.shadow_soft_size, 4)

    elif obj.type == "EMPTY":
        info["empty_display_type"] = obj.empty_display_type

    # Animation
    if obj.animation_data and obj.animation_data.action:
        action = obj.animation_data.action
        info["animation_action"] = action.name
        info["frame_range"] = get_action_frame_range(action)

    return info

def inspect_action(action):
    frame_range = get_action_frame_range(action)
    return {
        "name": action.name,
        "frame_range": frame_range,
        "fcurves": len(action.fcurves),
        "id_type": action.id_root if hasattr(action, "id_root") else "OBJECT",
    }

# ----- MAIN -----
print("[INSPECT] Starting Mettur blend inspection...")

scene = bpy.context.scene
report = {
    "blend_file": bpy.data.filepath,
    "scene_name": scene.name,
    "frame_start": scene.frame_start,
    "frame_end": scene.frame_end,
    "fps": scene.render.fps,
    "summary": {
        "total_objects": len(bpy.data.objects),
        "total_meshes": sum(1 for o in bpy.data.objects if o.type == "MESH"),
        "total_lights": sum(1 for o in bpy.data.objects if o.type == "LIGHT"),
        "total_cameras": sum(1 for o in bpy.data.objects if o.type == "CAMERA"),
        "total_empties": sum(1 for o in bpy.data.objects if o.type == "EMPTY"),
        "total_materials": len(bpy.data.materials),
        "total_actions": len(bpy.data.actions),
        "total_images": len(bpy.data.images),
        "total_particles": len(bpy.data.particles),
    },
    "collections": [inspect_collection(c) for c in bpy.data.collections if c.name not in ["Collection"]],
    "objects": [inspect_object(obj) for obj in bpy.data.objects],
    "actions": [inspect_action(a) for a in bpy.data.actions],
    "images": [
        {
            "name": img.name,
            "filepath": img.filepath,
            "packed": bool(img.packed_files),
            "size": list(img.size),
        }
        for img in bpy.data.images
    ],
    "world": {
        "name": scene.world.name if scene.world else None,
    } if scene.world else None,
}

out_path = r"E:\dam\scripts\mettur_inspection_report.json"
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(report, f, indent=2, ensure_ascii=False)

print(f"[INSPECT] Report written to: {out_path}")
print(f"[INSPECT] Total objects: {report['summary']['total_objects']}")
print(f"[INSPECT] Total meshes: {report['summary']['total_meshes']}")
print(f"[INSPECT] Frame range: {scene.frame_start} - {scene.frame_end} @ {scene.render.fps} fps")
