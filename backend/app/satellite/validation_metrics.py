import math
from typing import Dict, Any, List
import shapely.geometry
from pydantic import BaseModel

class SatelliteComparisonMetrics(BaseModel):
    iou_jaccard: float
    precision: float
    recall: float
    f1_score: float
    model_flooded_area_sqkm: float
    satellite_flooded_area_sqkm: float
    overlap_area_sqkm: float
    false_positive_area_sqkm: float
    false_negative_area_sqkm: float
    satellite_sensor: str
    pre_flood_date: str
    post_flood_date: str
    summary: str
    spatial_notes: str

class SatelliteValidationEngine:
    """
    Compares physical model simulation flood extents against satellite-observed
    SAR / Optical inundation footprints.
    
    DISTINCTION: Model predictions and Satellite observations are distinct datasets.
    Low IoU typically results from SAR revisit time offsets (days apart), speckle filtering,
    or vegetation penetration differences.
    """

    @classmethod
    def evaluate_model_vs_satellite(
        cls,
        model_polygon: shapely.geometry.base.BaseGeometry,
        satellite_polygon: shapely.geometry.base.BaseGeometry,
        sensor: str = "Sentinel-1 SAR (IW, VV+VH)",
        pre_date: str = "2023-08-01",
        post_date: str = "2023-08-15",
        center_lat: float = 22.8
    ) -> SatelliteComparisonMetrics:
        # Latitude-corrected degree to km² conversion
        lat_rad = math.radians(center_lat)
        deg2_to_km2 = (111.32 * math.cos(lat_rad)) * 111.32

        area_model = float(model_polygon.area * deg2_to_km2)
        area_sat = float(satellite_polygon.area * deg2_to_km2)

        if model_polygon.intersects(satellite_polygon):
            intersection_poly = model_polygon.intersection(satellite_polygon)
            union_poly = model_polygon.union(satellite_polygon)
            area_overlap = float(intersection_poly.area * deg2_to_km2)
            area_union = float(union_poly.area * deg2_to_km2)
        else:
            area_overlap = 0.0
            area_union = area_model + area_sat

        false_positive = max(0.0, area_model - area_overlap)
        false_negative = max(0.0, area_sat - area_overlap)

        iou = (area_overlap / max(1e-6, area_union)) if area_union > 0 else 0.0
        precision = (area_overlap / max(1e-6, area_model)) if area_model > 0 else 0.0
        recall = (area_overlap / max(1e-6, area_sat)) if area_sat > 0 else 0.0
        f1 = (2.0 * precision * recall / max(1e-6, precision + recall)) if (precision + recall) > 0 else 0.0

        return SatelliteComparisonMetrics(
            iou_jaccard=round(iou, 3),
            precision=round(precision, 3),
            recall=round(recall, 3),
            f1_score=round(f1, 3),
            model_flooded_area_sqkm=round(area_model, 2),
            satellite_flooded_area_sqkm=round(area_sat, 2),
            overlap_area_sqkm=round(area_overlap, 2),
            false_positive_area_sqkm=round(false_positive, 2),
            false_negative_area_sqkm=round(false_negative, 2),
            satellite_sensor=sensor,
            pre_flood_date=pre_date,
            post_flood_date=post_date,
            summary=(
                f"Satellite observation ({sensor}) overlap analysis: "
                f"IoU = {iou:.3f}, F1 = {f1:.3f}, Precision = {precision:.3f}, Recall = {recall:.3f}."
            ),
            spatial_notes=(
                "Low spatial IoU is common in dam break validation due to temporal mismatch between "
                "flash flood peak wave duration (~hours) and satellite revisit orbit pass (~days)."
            )
        )
