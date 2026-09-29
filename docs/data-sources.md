# Data Sources & Ingestion Protocols

All geographic layers used by the framework are derived from authoritative, open-access public data repositories without proprietary lock-in.

---

## 1. Digital Elevation Models (DEM)
- **Primary Open Sources**:
  - **SRTM (Shuttle Radar Topography Mission)**: 30-meter global elevation.
  - **Copernicus DEM (GLO-30)**: 30-meter European Space Agency (ESA) radar altimetry DEM.
  - **OpenTopography**: REST API access to high-resolution LiDAR and planetary elevation data.
- **Local Geoprocessing**:
  - Reprojection to the localized Universal Transverse Mercator (UTM) zone for metric consistency.
  - Priority-flood depression filling to eliminate false digital sinks.
  - Calculation of Hillshade ($315^\circ$ azimuth, $45^\circ$ solar altitude), Slope (Horn's algorithm), Aspect, D8 Flow Direction, and Flow Accumulation.

---

## 2. Waterways & Rivers
- **Source**: OpenStreetMap (OSM) via Overpass API.
- **Filters**: `way["waterway"~"river|stream|canal"]`.
- **Attributes**: River centerline coordinates, channel width (where tagged), name, waterway classification.

---

## 3. Infrastructure & Buildings
- **Sources**: OpenStreetMap and Overture Maps Foundation.
- **Filters**: `way["building"]` and `relation["building"]`.
- **Attributes**: Building ID, footprint polygon coordinates, estimated building height ($h$), building levels ($L$), occupancy/building type.

---

## 4. Road Lifelines
- **Source**: OpenStreetMap via Overpass API.
- **Filters**: `way["highway"~"motorway|trunk|primary|secondary|tertiary|residential"]`.
- **Attributes**: Highway classification, road length, lane count, segment IDs.

---

## 5. Satellite Earth Observation
- **Sensor**: Sentinel-1 C-Band Synthetic Aperture Radar (SAR).
- **Product**: Ground Range Detected (GRD), Interferometric Wide (IW) swath, dual polarization (VV + VH).
- **Methodology**: Bitemporal backscatter thresholding ($\Delta \sigma_0 \le -3.2\text{ dB}$) with Refined Lee speckle reduction.
