from pathlib import Path
import geopandas as gpd

OSM_FILE = Path(r"E:\dam\tehri_data\vector\tehri.osm")
OUT_DIR = Path(r"E:\dam\tehri_data\vector")

print("=" * 70)
print("TEHRI OSM → GEOSPATIAL LAYERS")
print("=" * 70)

if not OSM_FILE.exists():
    raise FileNotFoundError(f"OSM file not found: {OSM_FILE}")

def load_layer(layer_name):
    print(f"\nReading: {layer_name}")
    try:
        gdf = gpd.read_file(
            OSM_FILE,
            layer=layer_name,
            engine="pyogrio"
        )
        print(f"  Features: {len(gdf)}")
        print(f"  CRS: {gdf.crs}")
        return gdf
    except Exception as e:
        print(f"  Could not read {layer_name}: {e}")
        return None


# ------------------------------------------------------------
# BUILDINGS
# ------------------------------------------------------------

buildings = load_layer("multipolygons")

if buildings is not None and len(buildings) > 0:

    if "building" in buildings.columns:
        buildings = buildings[
            buildings["building"].notna()
        ].copy()

    if len(buildings) > 0:

        # Keep only useful columns where available
        wanted = [
            "building",
            "name",
            "addr:housenumber",
            "addr:street",
            "geometry"
        ]

        buildings = buildings[
            [c for c in wanted if c in buildings.columns]
        ]

        output = OUT_DIR / "buildings.geojson"

        buildings.to_file(
            output,
            driver="GeoJSON",
            engine="pyogrio"
        )

        print(f"\nBUILDINGS exported:")
        print(output)
        print(f"Count: {len(buildings)}")


# ------------------------------------------------------------
# ROADS
# ------------------------------------------------------------

roads = load_layer("lines")

if roads is not None and len(roads) > 0:

    if "highway" in roads.columns:

        roads = roads[
            roads["highway"].notna()
        ].copy()

        wanted = [
            "highway",
            "name",
            "ref",
            "surface",
            "lanes",
            "maxspeed",
            "geometry"
        ]

        roads = roads[
            [c for c in wanted if c in roads.columns]
        ]

        output = OUT_DIR / "roads.geojson"

        roads.to_file(
            output,
            driver="GeoJSON",
            engine="pyogrio"
        )

        print(f"\nROADS exported:")
        print(output)
        print(f"Count: {len(roads)}")


# ------------------------------------------------------------
# WATERWAYS
# ------------------------------------------------------------

if roads is not None and len(roads) > 0:

    # Reload lines because roads has been filtered
    lines = load_layer("lines")

    if lines is not None and "waterway" in lines.columns:

        waterways = lines[
            lines["waterway"].notna()
        ].copy()

        if len(waterways) > 0:

            wanted = [
                "waterway",
                "name",
                "geometry"
            ]

            waterways = waterways[
                [c for c in wanted if c in waterways.columns]
            ]

            output = OUT_DIR / "waterways.geojson"

            waterways.to_file(
                output,
                driver="GeoJSON",
                engine="pyogrio"
            )

            print(f"\nWATERWAYS exported:")
            print(output)
            print(f"Count: {len(waterways)}")


# ------------------------------------------------------------
# WATER BODIES
# ------------------------------------------------------------

if buildings is not None:

    multipolygons = load_layer("multipolygons")

    if (
        multipolygons is not None
        and "natural" in multipolygons.columns
    ):

        water = multipolygons[
            multipolygons["natural"].isin(["water"])
        ].copy()

        if len(water) > 0:

            wanted = [
                "natural",
                "water",
                "name",
                "geometry"
            ]

            water = water[
                [c for c in wanted if c in water.columns]
            ]

            output = OUT_DIR / "water.geojson"

            water.to_file(
                output,
                driver="GeoJSON",
                engine="pyogrio"
            )

            print(f"\nWATER BODIES exported:")
            print(output)
            print(f"Count: {len(water)}")


print("\n" + "=" * 70)
print("CONVERSION COMPLETE")
print("=" * 70)

print("\nOutput directory:")
print(OUT_DIR)

print("\nExpected files:")
print("  buildings.geojson")
print("  roads.geojson")
print("  waterways.geojson")
print("  water.geojson")