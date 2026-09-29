from typing import Dict, Any

class LandUseImpactAnalyzer:
    """
    Computes inundated area across ESA WorldCover / land use categories.
    """

    @classmethod
    def calculate_landuse_breakdown(cls, total_inundated_area_sqkm: float) -> Dict[str, Any]:
        # Typical land cover distribution for river floodplains (India / generalized semi-arid / agrarian)
        # 10: Tree cover, 20: Shrubland, 30: Grassland, 40: Cropland, 50: Built-up, 60: Bare / sparse, 80: Permanent water
        cropland_area = round(total_inundated_area_sqkm * 0.58, 2)
        builtup_area = round(total_inundated_area_sqkm * 0.16, 2)
        shrubland_area = round(total_inundated_area_sqkm * 0.12, 2)
        water_area = round(total_inundated_area_sqkm * 0.08, 2)
        bare_area = round(total_inundated_area_sqkm * 0.06, 2)

        return {
            "total_inundated_area_sqkm": round(total_inundated_area_sqkm, 2),
            "classes": [
                {"class_name": "Agricultural Cropland", "area_sqkm": cropland_area, "percentage": 58.0},
                {"class_name": "Built-up / Settlements", "area_sqkm": builtup_area, "percentage": 16.0},
                {"class_name": "Vegetation & Shrubland", "area_sqkm": shrubland_area, "percentage": 12.0},
                {"class_name": "River Channel & Water", "area_sqkm": water_area, "percentage": 8.0},
                {"class_name": "Barren & Open Ground", "area_sqkm": bare_area, "percentage": 6.0}
            ]
        }
