import math
from typing import Dict, Any, List, Tuple
from pydantic import BaseModel
import numpy as np
import shapely.geometry

class ValidationIssue(BaseModel):
    category: str        # "CRITICAL", "WARNING", "INFO"
    check_name: str
    message: str
    observed_value: Any
    expected_range: str

class ConsistencyReport(BaseModel):
    is_consistent: bool
    summary: str
    issues: List[ValidationIssue] = []
    diagnostics: Dict[str, Any] = {}

class ResultConsistencyValidator:
    """
    Independent scientific verification & numerical audit engine for flood simulations.
    Validates physical plausibility, unit consistency, raster-vector alignment,
    and asset exposure logic.
    """

    @classmethod
    def validate_simulation_results(
        cls,
        max_depth_m: float,
        max_velocity_ms: float,
        inundated_area_sqkm: float,
        polygon_area_sqkm: float,
        affected_buildings_count: int,
        affected_roads_km: float,
        exposed_population: int,
        dam_height_m: float,
        reservoir_level_m: float,
        dem_min_elev_m: float,
        dem_max_elev_m: float,
        wet_cell_count: int,
        pixel_area_m2: float
    ) -> ConsistencyReport:
        issues: List[ValidationIssue] = []

        # 1. Check: Flooded Area vs Asset Exposure Consistency
        if (affected_buildings_count > 0 or affected_roads_km > 0 or exposed_population > 0) and inundated_area_sqkm <= 0.001:
            issues.append(ValidationIssue(
                category="CRITICAL",
                check_name="Zero Flood Area with Non-Zero Asset Exposure",
                message="Inundated area is 0.00 km² despite reporting affected buildings/roads. Indicates unit conversion bug in cell area.",
                observed_value=inundated_area_sqkm,
                expected_range="> 0.05 km²"
            ))

        # 2. Check: Physical Water Depth Plausibility
        # A dam breach wave downstream cannot physically exceed the dam height / reservoir pool head
        max_allowable_depth = max(dam_height_m, reservoir_level_m) * 1.25
        if max_depth_m > max_allowable_depth:
            issues.append(ValidationIssue(
                category="CRITICAL",
                check_name="Physically Impossible Water Depth",
                message=(
                    f"Peak flood depth ({max_depth_m:.2f} m) exceeds physical reservoir head bound "
                    f"({max_allowable_depth:.1f} m for a {dam_height_m:.1f} m dam). "
                    f"Likely caused by uncalibrated empirical scaling or datum mismatch."
                ),
                observed_value=round(max_depth_m, 2),
                expected_range=f"0.5 m to {max_allowable_depth:.1f} m"
            ))
        elif max_depth_m <= 0.05 and wet_cell_count > 0:
            issues.append(ValidationIssue(
                category="CRITICAL",
                check_name="Zero Peak Depth with Wet Cells",
                message="Raster reported wet cells but maximum depth is near zero.",
                observed_value=round(max_depth_m, 2),
                expected_range="> 0.1 m"
            ))

        # 3. Check: Flow Velocity Physical Bounds
        # Flow velocity in river valley dam breaks typically ranges between 1.0 m/s and 9.0 m/s
        if max_velocity_ms > 20.0:
            issues.append(ValidationIssue(
                category="WARNING",
                check_name="Supercritical Velocity Anomaly",
                message=f"Peak velocity ({max_velocity_ms:.2f} m/s) exceeds normal open-channel flood wave bounds.",
                observed_value=round(max_velocity_ms, 2),
                expected_range="1.0 m/s to 15.0 m/s"
            ))
        elif max_velocity_ms <= 0.01 and wet_cell_count > 0:
            issues.append(ValidationIssue(
                category="CRITICAL",
                check_name="Zero Velocity for Dynamic Wave",
                message="Simulated breach hydrograph flow produced zero velocity.",
                observed_value=round(max_velocity_ms, 2),
                expected_range="> 0.5 m/s"
            ))

        # 4. Check: Raster vs Polygon Area Consistency
        raster_calc_area_sqkm = (wet_cell_count * pixel_area_m2) / 1e6
        if polygon_area_sqkm > 0 and raster_calc_area_sqkm > 0:
            area_ratio = polygon_area_sqkm / raster_calc_area_sqkm
            if area_ratio < 0.5 or area_ratio > 1.5:
                issues.append(ValidationIssue(
                    category="WARNING",
                    check_name="Raster vs Vector Area Discrepancy",
                    message=(
                        f"Vectorized flood polygon area ({polygon_area_sqkm:.2f} km²) differs significantly "
                        f"from raster cell count area ({raster_calc_area_sqkm:.2f} km²). Ratio: {area_ratio:.2f}."
                    ),
                    observed_value=round(area_ratio, 2),
                    expected_range="0.75 to 1.25"
                ))

        # 5. Check: Population Exposure Logic
        if affected_buildings_count > 0 and exposed_population == 0:
            issues.append(ValidationIssue(
                category="WARNING",
                check_name="Zero Population with Affected Buildings",
                message="Buildings are flooded but estimated population exposure is 0.",
                observed_value=exposed_population,
                expected_range="> 0 persons"
            ))

        is_consistent = len([i for i in issues if i.category == "CRITICAL"]) == 0
        summary = (
            "Simulation passes physical and geometric consistency checks."
            if is_consistent else
            f"Simulation failed {len([i for i in issues if i.category == 'CRITICAL'])} critical scientific consistency check(s)."
        )

        return ConsistencyReport(
            is_consistent=is_consistent,
            summary=summary,
            issues=issues,
            diagnostics={
                "max_depth_m": round(max_depth_m, 2),
                "max_velocity_ms": round(max_velocity_ms, 2),
                "inundated_area_sqkm": round(inundated_area_sqkm, 2),
                "raster_area_sqkm": round(raster_calc_area_sqkm, 2),
                "polygon_area_sqkm": round(polygon_area_sqkm, 2),
                "wet_cell_count": wet_cell_count,
                "pixel_area_m2": round(pixel_area_m2, 2),
                "dam_height_m": dam_height_m,
                "reservoir_level_m": reservoir_level_m,
                "dem_elevation_range_m": [round(dem_min_elev_m, 1), round(dem_max_elev_m, 1)],
                "affected_buildings": affected_buildings_count,
                "affected_roads_km": round(affected_roads_km, 2),
                "exposed_population": exposed_population
            }
        )
