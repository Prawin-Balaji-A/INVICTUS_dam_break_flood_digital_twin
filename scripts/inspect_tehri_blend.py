"""
Blender 5.2 scene inspector for tehri_dam_digital_twin.blend
Handles Blender 5.x Action/Slot API.
"""
import bpy
import json
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
                try:
                    nd["base_color"] = safe_list(node.inputs["Base Color"].default_value) if "Base Color" in node.inputs else None
                    nd["roughness"] = round(float(node.inputs["Roughness"].default_value), 4) if "Roughness" in node.inputs else None
                    nd["metallic"] = round(float(node.inputs["Metallic"].default_value), 4) if "Metallic" in node.inputs else None
                    nd["alpha"] = round(float(node.inputs["Alpha"].default_value), 4) if "Alpha" in node.inputs else None
                except Exception as e:
                    nd["error"] = str(e)
            info["nodes"].append(nd)
    return info

def inspect_collection(col, depth=0):
    return {
        "name": col.name,
        "depth": depth,
        "hide_viewport": col.hide_viewport,
        "objects": [o.name for o in col.objects],
        "children": [inspect_collection(c, depth + 1) for c in col.children]
    }

def get_action_frame_range(action):
    """Works for both old (fcurves) and new (layers/strips) Blender 5.x Action API."""
    try:
        # Blender 5.x: action.layers
        frames = []
        for layer in action.layers:
            for strip in layer.strips:
                if hasattr(strip, 'channelbags'):
                    for cb in strip.channelbags:
                        for fc in cb.fcurves:
                            for kp in fc.keyframe_points:
                                frames.append(kp.co.x)
                elif hasattr(strip, 'fcurves'):
                    for fc in strip.fcurves:
                        for kp in fc.keyframe_points:
                            frames.append(kp.co.x)
        if frames:
            return [min(frames), max(frames)]
    except AttributeError:
        pass
    # Fallback: old API
    try:
        frames = []
        for fc in action.fcurves:
            for kp in fc.keyframe_points:
                frames.append(kp.co.x)
        if frames:
            return [min(frames), max(frames)]
    except AttributeError:
        pass
    return None

def count_fcurves(action):
    try:
        total = 0
        for layer in action.layers:
            for strip in layer.strips:
                if hasattr(strip, 'channelbags'):
                    for cb in strip.channelbags:
                        total += len(cb.fcurves)
                elif hasattr(strip, 'fcurves'):
                    total += len(strip.fcurves)
        return total
    except AttributeError:
        try:
            return len(action.fcurves)
        except AttributeError:
            return 0

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
        try:
            info["materials"] = [inspect_material(m) for m in mesh.materials]
        except Exception:
            info["materials"] = []
        info["modifiers"] = [{"name": m.name, "type": m.type} for m in obj.modifiers]
        info["shape_keys"] = list(obj.data.shape_keys.key_blocks.keys()) if obj.data.shape_keys else []
        info["particle_systems"] = [ps.name for ps in obj.particle_systems]
    elif obj.type == "CAMERA" and obj.data:
        info["lens_mm"] = obj.data.lens
        info["clip_start"] = obj.data.clip_start
        info["clip_end"] = obj.data.clip_end
    elif obj.type == "LIGHT" and obj.data:
        info["light_type"] = obj.data.type
        info["energy"] = round(obj.data.energy, 2)
        info["color"] = safe_list(obj.data.color)
    if obj.animation_data and obj.animation_data.action:
        action = obj.animation_data.action
        info["animation_action"] = action.name
        info["frame_range"] = get_action_frame_range(action)
    return info

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
    },
    "collections": [inspect_collection(c) for c in bpy.data.collections],
    "objects": [inspect_object(obj) for obj in bpy.data.objects],
    "actions": [{"name": a.name, "frame_range": get_action_frame_range(a), "fcurves": count_fcurves(a)} for a in bpy.data.actions],
    "world": {"name": scene.world.name if scene.world else None},
}

out_path = r"E:\dam\scripts\tehri_inspection_report.json"
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(report, f, indent=2, ensure_ascii=False)

print(f"[INSPECT] Report written: {out_path}")
print(f"[INSPECT] Objects: {report['summary']['total_objects']}, Meshes: {report['summary']['total_meshes']}")
print(f"[INSPECT] Frame range: {scene.frame_start}-{scene.frame_end} @ {scene.render.fps}fps")
print(f"[INSPECT] Actions: {report['summary']['total_actions']}")
