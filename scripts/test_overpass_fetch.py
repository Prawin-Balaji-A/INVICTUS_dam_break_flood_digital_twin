import requests
import json

def test_fetch():
    query = """
[out:json][timeout:30];
(
  way["waterway"~"river|stream"](9.78,76.85,10.02,77.02);
);
out geom;
"""
    endpoints = [
        "https://overpass-api.de/api/interpreter",
        "https://overpass.kumi.systems/api/interpreter",
        "https://lz4.overpass-api.de/api/interpreter",
        "https://maps.mail.ru/osm/tools/overpass/api/interpreter"
    ]
    headers = {
        "User-Agent": "DamBreakFloodModel/1.0 (Geospatial Research Prototype; contact@dambreak.org)"
    }
    for ep in endpoints:
        try:
            print(f"Testing {ep}...")
            r = requests.post(ep, data={"data": query}, headers=headers, timeout=20)
            if r.status_code == 200:
                data = r.json()
                elements = data.get("elements", [])
                print(f"Success! Elements fetched: {len(elements)}")
                names = {e.get("tags", {}).get("name") for e in elements if e.get("tags", {}).get("name")}
                print(f"Waterways identified: {names}")
                return True
            else:
                print(f"Failed with status: {r.status_code}")
        except Exception as e:
            print(f"Error connecting to {ep}: {e}")
    return False

if __name__ == "__main__":
    test_fetch()
