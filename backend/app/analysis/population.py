from typing import Dict, Any

class PopulationExposureAnalyzer:
    """
    Estimates human population residing within the physical flood inundation perimeter.
    
    IMPORTANT SCIENTIFIC INTEGRITY NOTE:
    This layer computes POPULATION EXPOSURE (number of people located within the flood zone).
    It does NOT predict casualties, fatalities, or monetary losses, which require specific
    evacuation timing, structural vulnerability, and socio-economic empirical data.
    """

    @classmethod
    def estimate_exposure(
        cls,
        inundated_area_sqkm: float,
        affected_buildings_count: int,
        settlement_type: str = "semi-urban"
    ) -> Dict[str, Any]:
        # Average occupancy per dwelling unit in Indian Census data (~4.6 persons per household)
        avg_occupancy = 4.6
        direct_building_exposure = int(round(affected_buildings_count * avg_occupancy))

        # Regional rural-semi-urban population density (WorldPop / Census baseline: ~380-450 persons/km²)
        regional_density_per_sqkm = 420.0
        regional_basin_population = int(round(inundated_area_sqkm * regional_density_per_sqkm))

        # When vector building footprints are available, building-enumerated exposure is primary
        final_exposure = direct_building_exposure if affected_buildings_count > 0 else regional_basin_population

        return {
            "metric_type": "Population Exposure (Non-Casualty)",
            "estimated_exposed_population": final_exposure,
            "direct_building_exposure": direct_building_exposure,
            "regional_basin_exposure_estimate": regional_basin_population,
            "affected_buildings_considered": affected_buildings_count,
            "average_household_size": avg_occupancy,
            "exposure_methodology": "Direct OSM building footprint occupancy (4.6 persons/building)" if affected_buildings_count > 0 else "Regional spatial area density",
            "definitions": {
                "population_exposure": "Number of individuals whose physical residences or work places intersect the flood inundation zone.",
                "population_at_risk": "Exposed individuals subject to life-threatening hydrodynamic conditions (depth > 1.2m, velocity > 2 m/s).",
                "casualties": "Requires empirical evacuation warning time and building collapse dynamics; strictly NOT inferred here."
            },
            "disclaimer": (
                "Population exposure estimates individuals located inside the flooded footprint for emergency evacuation planning. "
                "It strictly does NOT infer or predict casualties or fatalities."
            )
        }
