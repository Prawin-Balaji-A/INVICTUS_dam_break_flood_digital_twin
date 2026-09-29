"""
backend.app.hydrodynamics

Hydrodynamics package.

Exports:
  GeneralizedFloodRoutingEngine — dam-agnostic 2D Manning routing engine
  compute_breach_hydrograph     — Froehlich-based transient breach hydrograph
  verify_mass_conservation      — independent mass-balance verification
  extract_downstream_reach      — DEM-thalweg-guided downstream reach extractor
  sample_river_stations         — river centerline station sampler
  propagate_flood_wave          — 2D kinematic wave propagation
  derive_inundation_mask        — depth-threshold binary mask
  vectorize_flood_extent        — raster-to-polygon vectorizer
  export_gis_products           — GeoTIFF / GeoJSON / KML / SHP exporter
"""

from backend.app.hydrodynamics.routing_engine import (
    GeneralizedFloodRoutingEngine,
    compute_breach_hydrograph,
    verify_mass_conservation,
    extract_downstream_reach,
    sample_river_stations,
    propagate_flood_wave,
    derive_inundation_mask,
    vectorize_flood_extent,
    export_gis_products,
    INUNDATION_DEPTH_THRESHOLD_M,
    STATION_SPACING_M,
)

__all__ = [
    "GeneralizedFloodRoutingEngine",
    "compute_breach_hydrograph",
    "verify_mass_conservation",
    "extract_downstream_reach",
    "sample_river_stations",
    "propagate_flood_wave",
    "derive_inundation_mask",
    "vectorize_flood_extent",
    "export_gis_products",
    "INUNDATION_DEPTH_THRESHOLD_M",
    "STATION_SPACING_M",
]
