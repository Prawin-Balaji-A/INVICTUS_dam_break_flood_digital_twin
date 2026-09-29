import pytest
from backend.app.validation.result_consistency import ResultConsistencyValidator

def test_consistency_validator_pass():
    report = ResultConsistencyValidator.validate_simulation_results(
        max_depth_m=3.5,
        max_velocity_ms=4.2,
        inundated_area_sqkm=14.2,
        polygon_area_sqkm=14.0,
        affected_buildings_count=12,
        affected_roads_km=10.5,
        exposed_population=55,
        dam_height_m=26.0,
        reservoir_level_m=24.0,
        dem_min_elev_m=35.0,
        dem_max_elev_m=110.0,
        wet_cell_count=2200,
        pixel_area_m2=6400.0
    )
    assert report.is_consistent is True
    assert len([i for i in report.issues if i.category == "CRITICAL"]) == 0

def test_consistency_validator_detects_zero_area_bug():
    # Previous bug condition: 0 km² area with 39 buildings and 75 km roads
    report = ResultConsistencyValidator.validate_simulation_results(
        max_depth_m=87.0,
        max_velocity_ms=15.0,
        inundated_area_sqkm=0.00,
        polygon_area_sqkm=0.00,
        affected_buildings_count=39,
        affected_roads_km=75.12,
        exposed_population=179,
        dam_height_m=26.0,
        reservoir_level_m=24.0,
        dem_min_elev_m=35.0,
        dem_max_elev_m=110.0,
        wet_cell_count=12460,
        pixel_area_m2=6400.0
    )
    assert report.is_consistent is False
    issue_names = [i.check_name for i in report.issues]
    assert "Zero Flood Area with Non-Zero Asset Exposure" in issue_names
    assert "Physically Impossible Water Depth" in issue_names

def test_consistency_validator_detects_unphysical_depth():
    report = ResultConsistencyValidator.validate_simulation_results(
        max_depth_m=50.0, # Exceeds 26m dam height * 1.25
        max_velocity_ms=4.0,
        inundated_area_sqkm=10.0,
        polygon_area_sqkm=10.0,
        affected_buildings_count=5,
        affected_roads_km=2.0,
        exposed_population=20,
        dam_height_m=20.0,
        reservoir_level_m=18.0,
        dem_min_elev_m=35.0,
        dem_max_elev_m=110.0,
        wet_cell_count=1500,
        pixel_area_m2=6400.0
    )
    assert report.is_consistent is False
    assert any("Water Depth" in i.check_name for i in report.issues)
