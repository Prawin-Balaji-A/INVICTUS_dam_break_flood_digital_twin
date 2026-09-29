import struct
import json

def inspect_glb(glb_path):
    with open(glb_path, 'rb') as f:
        magic, version, length = struct.unpack('<4sII', f.read(12))
        assert magic == b'glTF'
        chunk_len, chunk_type = struct.unpack('<II', f.read(8))
        assert chunk_type == 0x4E4F534A # JSON
        json_data = f.read(chunk_len).decode('utf-8')
        gltf = json.loads(json_data)
        
    print(f"=== GLB Inspection: {glb_path} ===")
    print(f"Nodes count: {len(gltf.get('nodes', []))}")
    print(f"Meshes count: {len(gltf.get('meshes', []))}")
    print(f"Materials count: {len(gltf.get('materials', []))}")
    print(f"Accessors count: {len(gltf.get('accessors', []))}")
    print(f"Animations count: {len(gltf.get('animations', []))}")
    
    mat_names = [m.get('name') for m in gltf.get('materials', [])]
    print(f"Materials: {mat_names}")
    
    node_names = [n.get('name') for n in gltf.get('nodes', [])]
    mesh_names = [m.get('name') for m in gltf.get('meshes', [])]
    
    print(f"Sample node names: {node_names[:10]}")
    print(f"Sample mesh names: {mesh_names[:10]}")
    
    # Check for specific Mettur objects
    print("\nObject checks:")
    for target in ['METTUR_REAL_TERRAIN', 'METTUR_DAM', 'METTUR_RESERVOIR', 'OSM_BUILDING', 'OSM_ROAD']:
        matching_nodes = [n for n in node_names if n and target in n]
        print(f"  {target}: {len(matching_nodes)} matching nodes")
        
inspect_glb(r"E:\dam\frontend\public\models\mettur\test_direct.glb")
