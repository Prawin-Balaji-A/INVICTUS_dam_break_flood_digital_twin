import json
from typing import Dict, Any, List
import shapely.geometry
import shapely.ops

class RoadImpactAnalyzer:
    """
    Computes affected road network segments and flooded length in kilometers,
    stratified by highway classification.
    """

    @classmethod
    def analyze_roads(cls, roads_geojson_path: str, flood_polygon: shapely.geometry.base.BaseGeometry) -> Dict[str, Any]:
        with open(roads_geojson_path, "r", encoding="utf-8") as f:
            roads_data = json.load(f)

        features = roads_data.get("features", [])
        total_len_km = 0.0
        affected_len_km = 0.0
        by_class: Dict[str, float] = {}
        affected_features: List[Dict[str, Any]] = []

        for feat in features:
            geom = feat.get("geometry")
            if not geom:
                continue
            line = shapely.geometry.shape(geom)
            # Approximate degree to meters conversion in local latitudes (~111.32 km / degree)
            len_deg = line.length
            seg_len_km = len_deg * 111.0
            total_len_km += seg_len_km

            hw_type = feat.get("properties", {}).get("highway", "other")
            if flood_polygon.intersects(line):
                inter = flood_polygon.intersection(line)
                if not inter.is_empty:
                    aff_km = inter.length * 111.0
                    affected_len_km += aff_km
                    by_class[hw_type] = by_class.get(hw_type, 0.0) + aff_km

                    props = feat.get("properties", {}).copy()
                    props["affected_length_km"] = round(aff_km, 2)
                    affected_features.append({
                        "type": "Feature",
                        "id": feat.get("id"),
                        "properties": props,
                        "geometry": shapely.geometry.mapping(inter)
                    })

        return {
            "total_road_network_km": round(total_len_km, 2),
            "total_affected_roads_km": round(affected_len_km, 2),
            "breakdown_by_highway_type_km": {k: round(v, 2) for k, v in by_class.items()},
            "affected_segments_count": len(affected_features),
            "affected_features": affected_features
        }
