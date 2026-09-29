"""
Acquire real OpenStreetMap data for the Tehri Dam study area:
  - Bhagirathi River and tributaries (waterways)
  - Building footprints (New Tehri and downstream valley settlements)
  - Road infrastructure

Uses the Overpass API with a proper POST + User-Agent (mirrors
scripts/acquire_idukki_osm.py). Saves standard GeoJSON FeatureCollections.
No fabricated geometry — only what OSM returns for the bbox.
"""

import os
import time
import requests
import json

OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]

HEADERS = {"User-Agent": "DamBreakFloodModel/1.0 (Geospatial Digital Twin; contact@dambreak.org)"}

BBOX = "30.30,78.40,30.45,78.56"  # min_lat, min_lon, max_lat, max_lon

OUTPUT_DIRS = {
    "river": r"E:\dam\data\tehri\river",
    "buildings": r"E:\dam\data\tehri\buildings",
    "roads": r"E:\dam\data\tehri\roads",
    "reservoir": r"E:\dam\data\tehri\reservoir",
}
for d in OUTPUT_DIRS.values():
    os.makedirs(d, exist_ok=True)


def query_overpass(query_body, timeout=120):
    query = f"[out:json][timeout:{timeout}];{query_body}out body;>;out skel qt;"
    for endpoint in OVERPASS_URLS:
        try:
            print(f"Querying Overpass endpoint: {endpoint}...", flush=True)
            resp = requests.post(endpoint, data={"data": query}, headers=HEADERS, timeout=timeout + 30)
            if resp.status_code == 200:
                data = resp.json()
                print(f"Success. Received {len(data.get('elements', []))} elements.", flush=True)
                return data
            print(f"Endpoint returned HTTP {resp.status_code}: {resp.text[:200]}", flush=True)
        except Exception as e:
            print(f"Error connecting to {endpoint}: {e}", flush=True)
        time.sleep(2)
    raise RuntimeError("All Overpass endpoints failed.")


def parse_ways_to_lines(osm_data):
    nodes = {el["id"]: (el["lon"], el["lat"]) for el in osm_data.get("elements", []) if el["type"] == "node"}
    features = []
    for el in osm_data.get("elements", []):
        if el["type"] == "way" and "nodes" in el:
            coords = [nodes[n] for n in el["nodes"] if n in nodes]
            if len(coords) >= 2:
                features.append({"type": "Feature", "id": el["id"],
                                 "properties": el.get("tags", {}),
                                 "geometry": {"type": "LineString", "coordinates": coords}})
    return {"type": "FeatureCollection", "features": features}


def parse_ways_to_polygons(osm_data):
    nodes = {el["id"]: (el["lon"], el["lat"]) for el in osm_data.get("elements", []) if el["type"] == "node"}
    features = []
    for el in osm_data.get("elements", []):
        if el["type"] == "way" and "nodes" in el:
            coords = [nodes[n] for n in el["nodes"] if n in nodes]
            if len(coords) >= 4 and coords[0] == coords[-1]:
                features.append({"type": "Feature", "id": el["id"],
                                 "properties": el.get("tags", {}),
                                 "geometry": {"type": "Polygon", "coordinates": [coords]}})
    return {"type": "FeatureCollection", "features": features}


def acquire_waterways():
    out_path = os.path.join(OUTPUT_DIRS["river"], "bhagirathi_river.geojson")
    if os.path.exists(out_path) and os.path.getsize(out_path) > 1000:
        print(f"Waterways already acquired: {out_path}", flush=True)
        return
    print("\n--- Acquiring Bhagirathi River and Waterways ---", flush=True)
    query = f"""
    (
      way["waterway"~"river|stream|canal"]({BBOX});
      relation["waterway"~"river|stream|canal"]({BBOX});
    );
    """
    fc = parse_ways_to_lines(query_overpass(query, timeout=120))
    main = sum(1 for f in fc["features"] if "bhagirathi" in f["properties"].get("name", "").lower())
    for f in fc["features"]:
        if "bhagirathi" in f["properties"].get("name", "").lower():
            f["properties"]["is_main_stem"] = True
    print(f"Extracted {len(fc['features'])} waterway segments ({main} Bhagirathi main-stem).", flush=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(fc, f, indent=2)
    print(f"Saved: {out_path}", flush=True)


def acquire_roads():
    out_path = os.path.join(OUTPUT_DIRS["roads"], "tehri_roads.geojson")
    if os.path.exists(out_path) and os.path.getsize(out_path) > 1000:
        print(f"Roads already acquired: {out_path}", flush=True)
        return
    print("\n--- Acquiring Road Infrastructure ---", flush=True)
    query = f"""
    (
      way["highway"~"trunk|primary|secondary|tertiary"]({BBOX});
    );
    """
    fc = parse_ways_to_lines(query_overpass(query, timeout=120))
    print(f"Extracted {len(fc['features'])} road segments.", flush=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(fc, f, indent=2)
    print(f"Saved: {out_path}", flush=True)


def acquire_buildings():
    out_path = os.path.join(OUTPUT_DIRS["buildings"], "tehri_buildings.geojson")
    if os.path.exists(out_path) and os.path.getsize(out_path) > 1000:
        print(f"Buildings already acquired: {out_path}", flush=True)
        return
    print("\n--- Acquiring Building Footprints ---", flush=True)
    query = f"""
    (
      way["building"]({BBOX});
    );
    """
    fc = parse_ways_to_polygons(query_overpass(query, timeout=180))
    print(f"Extracted {len(fc['features'])} building footprints.", flush=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(fc, f, indent=2)
    print(f"Saved: {out_path}", flush=True)


def acquire_reservoir():
    out_path = os.path.join(OUTPUT_DIRS["reservoir"], "tehri_reservoir.geojson")
    if os.path.exists(out_path) and os.path.getsize(out_path) > 1000:
        print(f"Reservoir already acquired: {out_path}", flush=True)
        return
    print("\n--- Acquiring Reservoir Waterbody ---", flush=True)
    query = f"""
    (
      way["water"="reservoir"]({BBOX});
      relation["water"="reservoir"]({BBOX});
      way["natural"="water"]({BBOX});
      relation["natural"="water"]({BBOX});
    );
    """
    fc = parse_ways_to_polygons(query_overpass(query, timeout=90))
    print(f"Extracted {len(fc['features'])} water polygon features.", flush=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(fc, f, indent=2)
    print(f"Saved: {out_path}", flush=True)


if __name__ == "__main__":
    acquire_waterways()
    acquire_roads()
    acquire_buildings()
    acquire_reservoir()
