import json
from collections import Counter

def parse_report(path, name):
    with open(path, encoding='utf-8') as f:
        r = json.load(f)

    print(f"=== {name} ===")
    print(f"Frame range: {r['frame_start']} - {r['frame_end']} @ {r['fps']}fps")
    print(f"Summary: {json.dumps(r['summary'], indent=2)}")
    print()

    print("COLLECTIONS:")
    def print_col(c, indent=0):
        print(' '*indent + c["name"] + f' ({len(c["objects"])} objs)')
        for ch in c.get("children", []):
            print_col(ch, indent+2)
    for c in r['collections']:
        print_col(c)
    print()

    print("ACTIONS:")
    for a in r['actions']:
        print(f"  {a['name']}: frames {a['frame_range']}, fcurves: {a['fcurves']}")
    print()

    print("OBJECTS BY TYPE:")
    type_ct = Counter(o['type'] for o in r['objects'])
    print(dict(type_ct))
    print()

    print("MESH OBJECTS (name, vertices, polygons, action):")
    for o in r['objects']:
        if o['type'] == 'MESH':
            print(f"  {o['name']}: v={o.get('vertices',0)}, f={o.get('polygons',0)}, action={o.get('animation_action','-')}")

    print()
    print("LIGHTS:")
    for o in r['objects']:
        if o['type'] == 'LIGHT':
            print(f"  {o['name']}: type={o.get('light_type','?')}, energy={o.get('energy','?')}")

    print()
    print("CAMERAS:")
    for o in r['objects']:
        if o['type'] == 'CAMERA':
            print(f"  {o['name']}: lens={o.get('lens_mm','?')}mm")

    print()
    print("ANIMATED OBJECTS:")
    for o in r['objects']:
        if o.get('animation_action'):
            print(f"  {o['name']} ({o['type']}): {o['animation_action']} frames={o.get('frame_range')}")
    print()

parse_report(r"E:\dam\scripts\tehri_inspection_report.json", "TEHRI")
print("="*60)
print()
parse_report(r"E:\dam\scripts\mettur_inspection_report.json", "METTUR")
