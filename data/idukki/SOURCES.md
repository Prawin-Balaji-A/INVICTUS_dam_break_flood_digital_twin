# Idukki Dam Study Case — Dataset Provenance & Sources

This document details the authentic provenance, lineage, provider information, and licensing for all datasets ingested for the **Idukki Dam (Periyar River, Kerala)** reference study case.

In accordance with Project Data Integrity Rule 1, **no scientific or geospatial datasets are fabricated, simulated, or cosmetically generated**.

---

## 1. Digital Elevation Model (DEM)

- **Dataset Name**: Copernicus DEM GLO-30 (Global 30m Digital Surface Model)
- **Data Provider**: European Space Agency (ESA) / Airbus Defence and Space / AWS Open Data
- **Source URL**:
  - `https://copernicus-dem-30m.s3.amazonaws.com/Copernicus_DSM_COG_10_N09_00_E076_00_DEM/Copernicus_DSM_COG_10_N09_00_E076_00_DEM.tif`
  - `https://copernicus-dem-30m.s3.amazonaws.com/Copernicus_DSM_COG_10_N10_00_E076_00_DEM/Copernicus_DSM_COG_10_N10_00_E076_00_DEM.tif`
  - `https://copernicus-dem-30m.s3.amazonaws.com/Copernicus_DSM_COG_10_N09_00_E077_00_DEM/Copernicus_DSM_COG_10_N09_00_E077_00_DEM.tif`
  - `https://copernicus-dem-30m.s3.amazonaws.com/Copernicus_DSM_COG_10_N10_00_E077_00_DEM/Copernicus_DSM_COG_10_N10_00_E077_00_DEM.tif`
- **Dataset Year / Version**: 2021 Release (GLO-30 Public Release)
- **Access / Download Date**: 2026-09-23
- **License / Terms**: Free and open access under Copernicus WorldDEM-30 open data policy.
- **Local Source Files (Unmodified)**:
  - `data/idukki/dem/source/Copernicus_DSM_COG_10_N09_00_E076_00_DEM.tif` (34.25 MB)
  - `data/idukki/dem/source/Copernicus_DSM_COG_10_N10_00_E076_00_DEM.tif` (45.92 MB)
  - `data/idukki/dem/source/Copernicus_DSM_COG_10_N09_00_E077_00_DEM.tif` (43.92 MB)
  - `data/idukki/dem/source/Copernicus_DSM_COG_10_N10_00_E077_00_DEM.tif` (42.76 MB)
- **Local Processed File**:
  - `data/idukki/dem/processed/idukki_dem_30m.tif` (6.28 MB)
- **Coordinate Reference System (CRS)**: EPSG:4326 (WGS 84 geographic 2D)
- **Spatial Resolution**: 1 arc-second (~30.8 meters at the equator)
- **Dimensions**: 1,189 rows × 1,189 columns (100.0% coverage of study area)
- **Elevation Range**: Min: 17.00 m MSL, Max: 1,921.43 m MSL, Mean: 598.32 m MSL
- **Configured Nodata**: -32767.0 (zero-elevation pixels: 0, no nodata converted to zero)
- **Processing Performed**:
  1. Mosaicked all 4 tiles (N09E076, N10E076, N09E077, N10E077) using `rasterio.merge` covering Lat 9-11N, Lon 76-78E.
  2. Clipped to the full Idukki Periyar study bounding box (`[76.75°E, 9.75°N]` to `[77.08°E, 10.08°N]`).
  3. LZW lossless compression applied. Unmodified source tiles strictly preserved.
- **Limitations**: Digital Surface Model includes canopy height in heavily forested Western Ghats mountain reserves; ground filtering or bathymetric sounding required for deep riverbed cross-sections.

---

## 2. River & Waterway Network

- **Dataset Name**: OpenStreetMap Waterway Elements (Periyar River Basin)
- **Data Provider**: OpenStreetMap Contributors / Overpass API
- **Source URL**: `https://overpass-api.de/api/interpreter`
- **Access / Download Date**: 2026-09-23
- **License / Terms**: Open Database License (ODbL) 1.0
- **Local File**: `data/idukki/river/periyar_river.geojson` (7.07 MB)
- **Coordinate Reference System (CRS)**: EPSG:4326 (WGS 84)
- **Feature Count**: 4,734 line segments
  - Periyar River main stem: 12 segments
  - Tributaries & streams (Cheruthoni River, Mudirapuzha, Muthirappuzha, etc.): 4,722 segments
- **Processing Performed**:
  1. Queried all `waterway=river|stream|canal` elements within the Idukki study domain.
  2. Extracted topological LineStrings with OSM node coordinates.
  3. Tagged main stem segments matching the Periyar naming convention.
- **Limitations**: Surface centerlines only; channel cross-sections, depths, and roughness parameters must be parameterized or surveyed for hydraulic routing.

---

## 3. Road Infrastructure Network

- **Dataset Name**: OpenStreetMap Road Network
- **Data Provider**: OpenStreetMap Contributors / Overpass API
- **Source URL**: `https://overpass-api.de/api/interpreter`
- **Access / Download Date**: 2026-09-23
- **License / Terms**: Open Database License (ODbL) 1.0
- **Local File**: `data/idukki/roads/idukki_roads.geojson` (1.33 MB)
- **Coordinate Reference System (CRS)**: EPSG:4326 (WGS 84)
- **Feature Count**: 863 road segments
- **Classification**: Trunk, primary, secondary, and tertiary highways connecting Idukki, Cheruthoni, Painavu, Karimban, Chelachuvadu, and Neriamangalam.
- **Processing Performed**:
  1. Queried `highway~"trunk|primary|secondary|tertiary"` within study bounds.
  2. Structured into standard GeoJSON LineStrings with road classifications.
- **Limitations**: Rural dirt tracks omitted to focus on arterial evacuation routes.

---

## 4. Building Footprints

- **Dataset Name**: OpenStreetMap Building Footprints
- **Data Provider**: OpenStreetMap Contributors / Overpass API
- **Source URL**: `https://maps.mail.ru/osm/tools/overpass/api/interpreter`
- **Access / Download Date**: 2026-09-23
- **License / Terms**: Open Database License (ODbL) 1.0
- **Local File**: `data/idukki/buildings/idukki_buildings.geojson` (242 KB)
- **Coordinate Reference System (CRS)**: EPSG:4326 (WGS 84)
- **Feature Count**: 516 building polygon footprints
- **Coverage**: Settlements along the downstream canyon corridor (Cheruthoni, Painavu, Karimban).
- **Processing Performed**:
  1. Queried `building=*` within downstream settlement bounding box (`9.80°N, 76.90°E` to `9.95°N, 77.02°E`).
  2. Extracted closed polygonal boundaries and validated topology with Shapely.
- **Limitations**: Remote mountainous rural dwellings may be under-represented in OSM.

---

## 5. Reservoir & Waterbody Boundaries

- **Dataset Name**: OpenStreetMap Reservoir & Waterbody Polygons
- **Data Provider**: OpenStreetMap Contributors / Overpass API
- **Source URL**: `https://overpass-api.de/api/interpreter`
- **Access / Download Date**: 2026-09-23
- **License / Terms**: Open Database License (ODbL) 1.0
- **Local File**: `data/idukki/reservoir/idukki_reservoir.geojson` (140 KB)
- **Coordinate Reference System (CRS)**: EPSG:4326 (WGS 84)
- **Feature Count**: 49 waterbody polygons
- **Processing Performed**:
  1. Extracted `water=reservoir` and `natural=water` with name matching Idukki/Cheruthoni.
  2. Formatted as standard GeoJSON polygons.

---

## 6. Dam & Engineering Specifications

- **Dataset Name**: Central Water Commission National Register of Large Dams (NRLD) & KSEB Engineering Records
- **Data Providers**:
  - Central Water Commission (CWC), Ministry of Jal Shakti, Government of India
  - Kerala State Electricity Board (KSEB), Dam Safety Organisation
- **Official References**:
  - CWC Dam Code: `KL09HH0001`
  - KSEB Operation & Maintenance Manual for Idukki Hydroelectric Project
- **Key Parameters (Verified)**:
  - Dam Name: Idukki Dam
  - Type: Concrete Double-Curvature Arch Dam
  - River: Periyar
  - Height: 168.91 m (554 ft)
  - Crest Length: 365.85 m
  - Crest Elevation: 735.60 m MSL
  - Full Reservoir Level (FRL): 732.43 m MSL
  - Maximum Water Level (MWL): 732.60 m MSL
  - Gross Storage: 1,996.00 MCM (1.996 × 10^9 m³)
  - Live Storage: 1,459.50 MCM (1.4595 × 10^9 m³)
  - Spillway: Cheruthoni Dam (Concrete Gravity, 138m height, 5 radial gates)

---

## 7. Population & Exposure Data

- **Status**: `NOT_CONFIGURED`
- **Candidate Provider**: WorldPop (University of Southampton) / Census of India
- **Rationale**: Local high-resolution census block or WorldPop 100m geotiff not downloaded in Phase 3. Synthetic population fallback is strictly forbidden by project integrity rules.

---

## 8. Satellite Inundation Data

- **Status**: `NOT_CONFIGURED`
- **Candidate Provider**: Copernicus Sentinel-1 SAR (Ground Range Detected) via Copernicus Data Space Ecosystem
- **Rationale**: Live satellite acquisition and flood extent segmentation belongs to a dedicated validation phase. Fake satellite masks or synthetic IoU/F1 metrics are strictly prohibited.
