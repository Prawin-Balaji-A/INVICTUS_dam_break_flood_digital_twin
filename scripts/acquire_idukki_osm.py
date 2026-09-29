"""
Script to acquire real OpenStreetMap data for Idukki Dam study area:
- Periyar River and tributaries (waterways)
- Buildings footprints
- Road infrastructure
- Reservoir waterbody

Uses Overpass API with proper User-Agent and error handling.
Saves standard GeoJSON FeatureCollections to data/idukki/.
"""

import os
import time
import requests
import json
from shapely.geometry import shape, LineString, Polygon, MultiPolygon, Point
from shapely.ops import linemerge, unary_union

OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter"
]

HEADERS = {
    "User-Agent": "DamBreakFloodModel/1.0 (Geospatial Research Prototype; contact@dambreak.org)"
}

BBOX = "9.75,76.75,10.08,77.08"  # min_lat, min_lon, max_lat, max_lon

OUTPUT_DIRS = {
    "river": r"E:\dam\data\idukki\river",
    "buildings": r"E:\dam\data\idukki\buildings",
    "roads": r"E:\dam\data\idukki\roads",
    "reservoir": r"E:\dam\data\idukki\reservoir"
}

for d in OUTPUT_DIRS.values():
    os.makedirs(d, exist_ok=True)

def query_overpass(query_body, timeout=120):
    query = f"[out:json][timeout:{timeout}];{query_body}out body;>;out skel qt;"
    for endpoint in OVERPASS_URLS:
        try:
            print(f"Querying Overpass endpoint: {endpoint}...")
            resp = requests.post(endpoint, data={"data": query}, headers=HEADERS, timeout=timeout + 30)
            if resp.status_code == 200:
                data = resp.json()
                print(f"Success. Received {len(data.get('elements', []))} elements.")
                return data
            else:
                print(f"Endpoint returned HTTP {resp.status_code}: {resp.text[:200]}")
        except Exception as e:
            print(f"Error connecting to {endpoint}: {e}")
        time.sleep(2)
    raise RuntimeError("All Overpass endpoints failed.")

def parse_osm_ways_to_lines(osm_data):
    """Convert OSM way elements into GeoJSON FeatureCollection of LineStrings."""
    nodes = {}
    for el in osm_data.get("elements", []):
        if el["type"] == "node":
            nodes[el["id"]] = (el["lon"], el["lat"])
            
    features = []
    for el in osm_data.get("elements", []):
        if el["type"] == "way" and "nodes" in el:
            coords = [nodes[nid] for nid in el["nodes"] if nid in nodes]
            if len(coords) >= 2:
                features.append({
                    "type": "Feature",
                    "id": el["id"],
                    "properties": el.get("tags", {}),
                    "geometry": {
                        "type": "LineString",
                        "coordinates": coords
                    }
                })
    return {"type": "FeatureCollection", "features": features}

def parse_osm_ways_to_polygons(osm_data):
    """Convert OSM closed ways into GeoJSON FeatureCollection of Polygons."""
    nodes = {}
    for el in osm_data.get("elements", []):
        if el["type"] == "node":
            nodes[el["id"]] = (el["lon"], el["lat"])
            
    features = []
    for el in osm_data.get("elements", []):
        if el["type"] == "way" and "nodes" in el:
            coords = [nodes[nid] for nid in el["nodes"] if nid in nodes]
            # Must be closed and at least 4 coords (first == last)
            if len(coords) >= 4 and coords[0] == coords[-1]:
                features.append({
                    "type": "Feature",
                    "id": el["id"],
                    "properties": el.get("tags", {}),
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [coords]
                    }
                })
    return {"type": "FeatureCollection", "features": features}

def acquire_waterways():
    out_path = os.path.join(OUTPUT_DIRS["river"], "periyar_river.geojson")
    if os.path.exists(out_path) and os.path.getsize(out_path) > 1000:
        print(f"Waterways already acquired: {out_path} ({os.path.getsize(out_path)} bytes)", flush=True)
        return
    print("\n--- Acquiring Periyar River and Waterways ---", flush=True)
    query = f"""
    (
      way["waterway"~"river|stream|canal"]({BBOX});
      relation["waterway"~"river|stream|canal"]({BBOX});
    );
    """
    osm_data = query_overpass(query, timeout=120)
    fc = parse_osm_ways_to_lines(osm_data)
    
    periyar_features = []
    other_waterways = []
    for feat in fc["features"]:
        name = feat["properties"].get("name", "").lower()
        if "periyar" in name:
            feat["properties"]["is_main_stem"] = True
            periyar_features.append(feat)
        else:
            other_waterways.append(feat)
            
    print(f"Extracted {len(fc['features'])} total waterway segments.", flush=True)
    print(f"  - Periyar River segments: {len(periyar_features)}", flush=True)
    print(f"  - Tributaries/streams: {len(other_waterways)}", flush=True)
    
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(fc, f, indent=2)
    print(f"Saved: {out_path}", flush=True)

def acquire_roads():
    out_path = os.path.join(OUTPUT_DIRS["roads"], "idukki_roads.geojson")
    if os.path.exists(out_path) and os.path.getsize(out_path) > 1000:
        print(f"Roads already acquired: {out_path}", flush=True)
        return
    print("\n--- Acquiring Road Infrastructure ---", flush=True)
    # Target arterial and connecting roads
    query = f"""
    (
      way["highway"~"trunk|primary|secondary|tertiary"]({BBOX});
    );
    """
    osm_data = query_overpass(query, timeout=120)
    fc = parse_osm_ways_to_lines(osm_data)
    print(f"Extracted {len(fc['features'])} road segments.", flush=True)
    
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(fc, f, indent=2)
    print(f"Saved: {out_path}", flush=True)

def acquire_buildings():
    out_path = os.path.join(OUTPUT_DIRS["buildings"], "idukki_buildings.geojson")
    if os.path.exists(out_path) and os.path.getsize(out_path) > 1000:
        print(f"Buildings already acquired: {out_path}", flush=True)
        return
    print("\n--- Acquiring Building Footprints ---", flush=True)
    # Query building footprints in downstream corridor / key settlements (Cheruthoni, Painavu, Karimban)
    # Centered around downstream corridor Lat 9.80-9.95, Lon 76.90-77.02
    settlement_bbox = "9.80,76.90,9.95,77.02"
    query = f"""
    (
      way["building"]({settlement_bbox});
    );
    """
    osm_data = query_overpass(query, timeout=120)
    fc = parse_osm_ways_to_polygons(osm_data)
    print(f"Extracted {len(fc['features'])} building polygon footprints.", flush=True)
    
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(fc, f, indent=2)
    print(f"Saved: {out_path}", flush=True)

def acquire_reservoir():
    out_path = os.path.join(OUTPUT_DIRS["reservoir"], "idukki_reservoir.geojson")
    if os.path.exists(out_path) and os.path.getsize(out_path) > 1000:
        print(f"Reservoir already acquired: {out_path}", flush=True)
        return
    print("\n--- Acquiring Reservoir Waterbody ---", flush=True)
    query = f"""
    (
      way["water"="reservoir"]({BBOX});
      relation["water"="reservoir"]({BBOX});
      way["natural"="water"]["name"~"Idukki|Cheruthoni|Periyar",i]({BBOX});
      relation["natural"="water"]["name"~"Idukki|Cheruthoni|Periyar",i]({BBOX});
    );
    """
    osm_data = query_overpass(query, timeout=60)
    fc = parse_osm_ways_to_polygons(osm_data)
    print(f"Extracted {len(fc['features'])} reservoir polygon features.", flush=True)
    
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(fc, f, indent=2)
    print(f"Saved: {out_path}", flush=True)

if __name__ == "__main__":
    acquire_waterways()
    acquire_roads()
    acquire_buildings()
    acquire_reservoir()
