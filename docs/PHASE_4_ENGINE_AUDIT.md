# Phase 4 Simulation Engine Audit & Architectural Assessment

**Target Dam**: Idukki Dam Reference Case (Periyar River, Kerala)  
**Evaluation Date**: 2026-09-23  
**Status**: Pre-Phase 4 Baseline Verification

---

## 1. Executive Summary & Audit Answers

| # | Question | Finding | Technical Detail |
|---|---|---|---|
| 1 | **What solver currently exists?** | `FloodInundationEngine` (in `backend/app/gis/inundation_engine.py`), `SPHSolver` (in `backend/app/hydrodynamics/sph/solver.py`), and `Delft3DAdapter` (in `backend/app/hydrodynamics/delft3d/adapter.py`). | Only `FloodInundationEngine` is wired into the simulation execution pipeline. `SPHSolver` and `Delft3DAdapter` exist as standalone modules. |
| 2 | **Is it actually called by the simulation API?** | **YES**, `FloodInundationEngine.run_inundation_simulation()` is called by `backend/app/api/simulation.py:102`. | Neither SPH nor Delft3D are called by the main simulation route. |
| 3 | **What equations does it solve?** | Manning's open-channel normal depth equation coupled with wave celerity: $h = \left( \frac{n \cdot Q}{W \cdot \sqrt{S_0}} \right)^{3/5}$ and $v = \frac{1}{n} R^{2/3} S_0^{1/2}$. | $Q(t)$ hydrograph wave attenuation: $Q_{local} = Q_{in} \cdot e^{-\alpha x}$; wave front propagation velocity: $c = \sqrt{g \cdot h}$. |
| 4 | **What inputs does it consume?** | Digital Elevation Model (`dem_path`), Dam breach source coordinate (`dam_coord`), Precalculated breach hydrograph (`hydrograph` list of $t, Q$), dam height and reservoir level, downstream orientation angle (`downstream_bearing_deg`). | In Phase 3, authentic Copernicus DEM GLO-30 and OSM Periyar river vectors were ingested. |
| 5 | **What outputs does it generate?** | Georeferenced GeoTIFF rasters (`maximum_depth.tif`, `maximum_velocity.tif`, `arrival_time.tif`), Vector polygons (`flood_extent.geojson`, `flood_extent.kml`), Time-series metrics (`timesteps.json`), and infrastructure impact tables. | Output rasters are written with LZW compression and CRS preserved from input DEM. |
| 6 | **Is SPH actually coupled to the simulation?** | **NO**. | `SPHSolver` is an independent 2D flume solver solving the Navier-Stokes equations via Wendland C2 kernel and Tait's EOS. It is not coupled to the DEM or 2D floodplain topography. |
| 7 | **Is Manning actually used?** | **YES**. | Manning's roughness coefficient ($n = 0.035 \ \text{s/m}^{1/3}$) is explicitly used to compute normal depth and velocity in `inundation_engine.py`. |
| 8 | **Is Delft3D merely an exporter/template or actually executable?** | **EXPORTER / TEMPLATE ONLY**. | `Delft3DAdapter` generates Delft3D-FLOW input files (`.grd`, `.dep`, `.bnd`, `.bcc`, `.mdf`). The proprietary Delft3D binary (`d_hydro.exe` / `flow2d3d`) is not installed on the system. |
| 9 | **Are current results synthetic?** | **PARTIAL**. | The breach hydrographs are computed from empirical equations (Froehlich 2008). In Machchhu demo mode, DEM was synthetic. For Idukki, the DEM is real (Copernicus 30m), but the existing 1D/2D routing in `inundation_engine.py` was constrained to a directional bearing angle rather than following the true curvilinear 2D Periyar river channel. |

---

## 2. In-Depth Component Analysis

### 2.1 Breach & Hydrology Engine (`backend/app/hydrology/`)
- **Implemented Formulations**:
  1. **Froehlich (2008)**: $B_{avg} = 0.27 K_0 V_w^{0.32} h_b^{0.04}$, $t_f = 63.2 \sqrt{V_w / (g h_b^2)}$, $Q_p = 0.607 V_w^{0.295} h_w^{1.24}$.
  2. **Von Thun & Gillette (1990)**: Erosion rates and empirical breach width formulations.
  3. **MacDonald & Langridge-Monopolis (1984)**: Breaching volume and development time equations.
- **Hydrograph Generation (`hydrograph.py`)**:
  - Dynamically calculates outflow $Q(t) = C_w W_b(t) H_{eff}^{1.5} + C_s z H_{eff}^{2.5}$ using a broad-crested weir equation ($C_w = 1.70, C_s = 1.20$).
  - Mass balance routing: $\Delta V = Q_{out} \Delta t$, $H(t+\Delta t) = H(t) - \frac{\Delta V}{A_{res}}$.
- **Assessment**: Mathematically sound, mass-conserving, but requires explicit scenario parameterization for Idukki Dam.

### 2.2 Smoothed Particle Hydrodynamics (`backend/app/hydrodynamics/sph/`)
- **Implementation**: Weakly Compressible SPH (WCSPH) in `solver.py` with XSPH velocity correction, artificial viscosity (Monaghan 1992), and density summation.
- **Limitation**: Evaluated on benchmark flume tanks (2.0m × 1.0m domain). Scaling 2D particle simulation to 1,321 km² of rugged mountain terrain would require $>10^9$ particles and weeks of GPU compute.
- **Phase 4 Determination**: **SPH STATUS = NOT YET COUPLED**. Honest reporting required.

### 2.3 Delft3D Integration (`backend/app/hydrodynamics/delft3d/`)
- **Implementation**: `adapter.py` generates standard Delft3D grid and boundary files from DEM.
- **Limitation**: Executable engine missing from host system.
- **Phase 4 Determination**: Must remain marked as an exporter. No fake Delft3D execution claim allowed.

### 2.4 Hydraulic Routing Engine (`backend/app/gis/inundation_engine.py`)
- **Limitation of Previous Implementation**:
  - Used directional projection along `downstream_bearing_deg` (`315°`).
  - While acceptable for linear valleys, the Periyar river gorge bends and winds across the Western Ghats topography.
- **Phase 4 Upgrade Requirement**:
  - Implement a dedicated 2D hydraulic wave routing model that directly propagates along the validated Periyar river centerline and adjacent DEM terrain cells, computing physically constrained water depth, flow velocity, arrival time, and inundation masks based on Manning's equation and mass conservation.
