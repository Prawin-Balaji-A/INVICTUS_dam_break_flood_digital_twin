"""
Blender 5.2 inspection script: inspect_blend.py
Run with: blender --background tehri_dam_digital_twin.blend --python scripts/inspect_blend.py
"""

import bpy
import json
import math
import os

def vec3(v):
    return [round(v.x, 4), round(v.y, 4), round(v.z, 4)]

def euler3(e):
    return [round(math.degrees(e.x), 2), round(math.degrees(e.y), 2), round(math.degrees(e.z), 2)]

def get_material_info(mat):
    if not mat:
        return None
    info = {
        "name": mat.name,
        "blend_method": getattr(mat, "blend_method", "OPAQUE"),
    }
    try:
        # Blender 5.2 may use mat.node_tree directly
        if mat.node_tree:
            nodes = []
            for node in mat.node_tree.nodes:
                n = {"type": node.type, "name": node.name}
                if node.type == "BSDF_PRINCIPLED":
                    try:
                        n["base_color"] = list(node.inputs["Base Color"].default_value)[:4]
                        n["roughness"] = round(float(node.inputs["Roughness"].default_value), 3)
                        n["metallic"] = round(float(node.inputs["Metallic"].default_value), 3)
                        if "Alpha" in node.inputs:
                            n["alpha"] = round(float(node.inputs["Alpha"].default_value), 3)
                        # Blender 5.x: Transmission Weight
                        for key in ("Transmission Weight", "Transmission"):
                            if key in node.inputs:
                                n["transmission"] = round(float(node.inputs[key].default_value), 3)
                                break
                    except Exception:
                        pass
                nodes.append(n)
            info["nodes"] = nodes
    except Exception as e:
        info["nodes_error"] = str(e)
    return info

def get_object_info(obj):
    info = {
        "name": obj.name,
        "type": obj.type,
        "location": vec3(obj.location),
        "rotation_euler_deg": euler3(obj.rotation_euler),
        "scale": vec3(obj.scale),
        "visible": not obj.hide_viewport,
        "render_visible": not obj.hide_render,
        "collections": [c.name for c in obj.users_collection],
        "parent": obj.parent.name if obj.parent else None,
    }

    if obj.type == "MESH" and obj.data:
        mesh = obj.data
        info["mesh_name"] = mesh.name
        info["vertices"] = len(mesh.vertices)
        info["polygons"] = len(mesh.polygons)
        info["has_uv"] = len(mesh.uv_layers) > 0
        info["uv_layers"] = [uv.name for uv in mesh.uv_layers]
        info["materials"] = [get_material_info(s.material) for s in obj.material_slots]
        info["modifiers"] = [{"name": mod.name, "type": mod.type} for mod in obj.modifiers]

    elif obj.type == "LIGHT":
        lamp = obj.data
        info["light_type"] = lamp.type
        info["energy"] = round(lamp.energy, 2)
        info["color"] = [round(c, 3) for c in lamp.color]

    elif obj.type == "CAMERA":
        cam = obj.data
        info["lens_mm"] = round(cam.lens, 2)
        info["clip_start"] = cam.clip_start
        info["clip_end"] = cam.clip_end

    elif obj.type == "EMPTY":
        info["empty_display_type"] = obj.empty_display_type

    if hasattr(obj, "particle_systems") and obj.particle_systems:
        info["particle_systems"] = [ps.name for ps in obj.particle_systems]

    # Animation data
    try:
        if obj.animation_data and obj.animation_data.action:
            action = obj.animation_data.action
            fr = action.frame_range
            info["animation_action"] = action.name
            info["frame_range"] = [fr[0], fr[1]]
    except Exception:
        pass

    return info

def recurse_collection(col, depth=0):
    return {
        "name": col.name,
        "depth": depth,
        "hide_viewport": col.hide_viewport,
        "objects": [o.name for o in col.objects],
        "children": [recurse_collection(child, depth + 1) for child in col.children]
    }

def inspect_scene():
    scene = bpy.context.scene

    collections = recurse_collection(bpy.context.scene.collection)

    objects = []
    for obj in bpy.data.objects:
        try:
            objects.append(get_object_info(obj))
        except Exception as e:
            objects.append({"name": obj.name, "type": obj.type, "error": str(e)})

    world_info = {}
    try:
        if scene.world:
            world_info["name"] = scene.world.name
            if scene.world.node_tree:
                world_info["nodes"] = [n.type for n in scene.world.node_tree.nodes]
    except Exception as e:
        world_info["error"] = str(e)

    scene_info = {
        "name": scene.name,
        "frame_start": scene.frame_start,
        "frame_end": scene.frame_end,
        "frame_current": scene.frame_current,
        "fps": scene.render.fps,
        "unit_system": scene.unit_settings.system,
        "unit_scale": scene.unit_settings.scale_length,
        "camera": scene.camera.name if scene.camera else None,
    }

    # Actions (Blender 5.2 stores fcurves differently)
    actions = []
    for action in bpy.data.actions:
        a_info = {
            "name": action.name,
        }
        try:
            fr = action.frame_range
            a_info["frame_range"] = [fr[0], fr[1]]
        except Exception:
            pass
        # In Blender 5.2 slots/layers architecture
        try:
            a_info["layers"] = len(list(action.layers))
        except Exception:
            pass
        try:
            # Legacy fcurves may still work via action_group
            a_info["fcurves"] = sum(1 for _ in action.fcurves) if hasattr(action, "fcurves") else "N/A"
        except Exception:
            a_info["fcurves"] = "N/A"
        actions.append(a_info)

    images = []
    for img in bpy.data.images:
        images.append({
            "name": img.name,
            "filepath": img.filepath,
            "packed": img.packed_file is not None,
            "size": list(img.size),
        })

    report = {
        "scene": scene_info,
        "world": world_info,
        "collections": collections,
        "objects": objects,
        "actions": actions,
        "images": images,
        "summary": {
            "total_objects": len(bpy.data.objects),
            "total_meshes": len(bpy.data.meshes),
            "total_materials": len(bpy.data.materials),
            "total_actions": len(bpy.data.actions),
            "total_images": len(bpy.data.images),
        }
    }

    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "blend_inspection_report.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"\n[INSPECTION COMPLETE] Report: {out_path}")
    print(f"  Objects: {len(bpy.data.objects)}, Materials: {len(bpy.data.materials)}, Images: {len(bpy.data.images)}")
    print(f"  Frame range: {scene.frame_start} - {scene.frame_end} @ {scene.render.fps}fps")
    print(f"  Units: {scene.unit_settings.system}, Scale: {scene.unit_settings.scale_length}")

inspect_scene()
