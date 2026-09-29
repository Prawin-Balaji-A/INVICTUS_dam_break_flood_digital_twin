import json
import os
from shapely.geometry import LineString, Polygon, MultiPolygon
from shapely.geometry import mapping
import geopandas as gpd

BASE = r"E:\dam\mettur_data\vector"
OSM = os.path.join(BASE, "mettur.osm")

print("=" * 70)
print("METTUR OVERPASS JSON → GEOSPATIAL LAYERS")
print("=" * 70)

# ---------------------------------------------------------
# LOAD OSM JSON
# ---------------------------------------------------------

with open(OSM, "r", encoding="utf-8") as f:
    data = json.load(f)

elements = data.get("elements", [])

print(f"OSM elements: {len(elements)}")

# Overpass returned ways with geometry embedded inside them.
ways = [
    e for e in elements
    if e.get("type") == "way"
]

relations = [
    e for e in elements
    if e.get("type") == "relation"
]

print(f"Ways: {len(ways)}")
print(f"Relations: {len(relations)}")


# ---------------------------------------------------------
# HELPERS
# ---------------------------------------------------------

def get_coords(element):
    geometry = element.get("geometry", [])

    coords = []

    for point in geometry:
        if "lon" in point and "lat" in point:
            coords.append(
                (point["lon"], point["lat"])
            )

    return coords


def feature(properties, geometry):
    return {
        "type": "Feature",
        "properties": properties,
        "geometry": mapping(geometry)
    }


# ---------------------------------------------------------
# BUILDINGS
# ---------------------------------------------------------

print("\nProcessing buildings...")

building_features = []

for e in ways:

    tags = e.get("tags", {})

    if "building" not in tags:
        continue

    coords = get_coords(e)

    if len(coords) < 3:
        continue

    try:
        polygon = Polygon(coords)

        if not polygon.is_valid:
            polygon = polygon.buffer(0)

        if polygon.is_empty:
            continue

        building_features.append(
            feature(
                {
                    "building": tags.get("building"),
                    "name": tags.get("name")
                },
                polygon
            )
        )

    except Exception:
        continue


buildings = gpd.GeoDataFrame.from_features(
    building_features,
    crs="EPSG:4326"
)

buildings_path = os.path.join(
    BASE,
    "buildings.geojson"
)

buildings.to_file(
    buildings_path,
    driver="GeoJSON"
)

print(f"Buildings: {len(buildings)}")
print(f"Written: {buildings_path}")


# ---------------------------------------------------------
# ROADS
# ---------------------------------------------------------

print("\nProcessing roads...")

road_features = []

for e in ways:

    tags = e.get("tags", {})

    if "highway" not in tags:
        continue

    coords = get_coords(e)

    if len(coords) < 2:
        continue

    try:

        line = LineString(coords)

        road_features.append(
            feature(
                {
                    "highway": tags.get("highway"),
                    "name": tags.get("name")
                },
                line
            )
        )

    except Exception:
        continue


roads = gpd.GeoDataFrame.from_features(
    road_features,
    crs="EPSG:4326"
)

roads_path = os.path.join(
    BASE,
    "roads.geojson"
)

roads.to_file(
    roads_path,
    driver="GeoJSON"
)

print(f"Roads: {len(roads)}")
print(f"Written: {roads_path}")


# ---------------------------------------------------------
# WATERWAYS
# ---------------------------------------------------------

print("\nProcessing waterways...")

waterway_features = []

for e in ways:

    tags = e.get("tags", {})

    if "waterway" not in tags:
        continue

    coords = get_coords(e)

    if len(coords) < 2:
        continue

    try:

        line = LineString(coords)

        waterway_features.append(
            feature(
                {
                    "waterway": tags.get("waterway"),
                    "name": tags.get("name")
                },
                line
            )
        )

    except Exception:
        continue


waterways = gpd.GeoDataFrame.from_features(
    waterway_features,
    crs="EPSG:4326"
)

waterways_path = os.path.join(
    BASE,
    "waterways.geojson"
)

waterways.to_file(
    waterways_path,
    driver="GeoJSON"
)

print(f"Waterways: {len(waterways)}")
print(f"Written: {waterways_path}")


# ---------------------------------------------------------
# WATER BODIES
# ---------------------------------------------------------

print("\nProcessing water bodies...")

water_features = []

for e in ways:

    tags = e.get("tags", {})

    natural = str(tags.get("natural", "")).lower()

    if natural != "water":
        continue

    coords = get_coords(e)

    if len(coords) < 3:
        continue

    try:

        polygon = Polygon(coords)

        if not polygon.is_valid:
            polygon = polygon.buffer(0)

        if polygon.is_empty:
            continue

        water_features.append(
            feature(
                {
                    "natural": "water",
                    "name": tags.get("name")
                },
                polygon
            )

        )

    except Exception:
        continue


water = gpd.GeoDataFrame.from_features(
    water_features,
    crs="EPSG:4326"
)

water_path = os.path.join(
    BASE,
    "water.geojson"
)

water.to_file(
    water_path,
    driver="GeoJSON"
)

print(f"Water bodies: {len(water)}")
print(f"Written: {water_path}")


# ---------------------------------------------------------
# COMPLETE
# ---------------------------------------------------------

print("\n" + "=" * 70)
print("METTUR OSM CONVERSION COMPLETE")
print("=" * 70)

print("""
Created:

  buildings.geojson
  roads.geojson
  waterways.geojson
  water.geojson
""")

print(f"Directory: {BASE}")

print("=" * 70)