import json

with open('scripts/blend_inspection_report.json', 'r') as f:
    r = json.load(f)

print('=== SUMMARY ===')
print(r['summary'])
print()

KEY_OBJECTS = [
    'TEHRI_Terrain', 'TEHRI_Dam_Main', 'TEHRI_Dam_Breach_Notch',
    'TEHRI_Reservoir_00.001', 'TEHRI_Flood_01', 'TEHRI_Flood_02',
    'TEHRI_Flood_03', 'TEHRI_Flood_Torrent', 'TEHRI_Water_01.001',
    'TEHRI_Water_02.001', 'TEHRI_DAM_ORIGIN_MARKER', 'TEHRI_Splash_Emitter',
    'TEHRI_Flood_Foam_00'
]

for obj in r['objects']:
    nm = obj.get('name', '')
    if nm in KEY_OBJECTS:
        print('=== ' + nm + ' ===')
        print('  type: ' + obj.get('type', ''))
        print('  location: ' + str(obj.get('location', '')))
        print('  scale: ' + str(obj.get('scale', '')))
        if 'vertices' in obj:
            print('  verts: ' + str(obj['vertices']) + ' polys: ' + str(obj['polygons']))
        mats = obj.get('materials', [])
        for m in mats:
            if m:
                print('  mat: ' + m['name'] + ' blend_method=' + str(m.get('blend_method', '')))
                for n in m.get('nodes', []):
                    if n.get('type') == 'BSDF_PRINCIPLED':
                        print('    roughness=' + str(n.get('roughness')) + 
                              ' metallic=' + str(n.get('metallic')) + 
                              ' alpha=' + str(n.get('alpha')) + 
                              ' transmission=' + str(n.get('transmission', 0)))
        if 'animation_action' in obj:
            print('  animation: ' + obj['animation_action'] + ' frames=' + str(obj['frame_range']))
        if 'particle_systems' in obj:
            print('  particles: ' + str(obj['particle_systems']))
        print()

print('=== ACTIONS ===')
for a in r['actions']:
    print('  ' + a['name'] + ' range=' + str(a.get('frame_range', '?')))

print()
print('=== IMAGES ===')
for img in r['images']:
    print('  ' + img['name'] + ' path=' + str(img['filepath']) + ' packed=' + str(img['packed']) + ' size=' + str(img['size']))
