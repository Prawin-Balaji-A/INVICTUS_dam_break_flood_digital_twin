# Delft3D Integration Architecture

## 1. External Engine Isolation Principle

Delft3D-FLOW (Deltares) is an industry-standard, multi-dimensional hydrodynamic simulation program solving the shallow-water equations.

To maintain absolute scientific integrity:
1. **No Synthetic Fabrication**: The system never generates synthetic data and labels it as Delft3D output.
2. **Automated Detection**: The backend probes system paths for `d_flow.exe` or `dimr`.
3. **Uninstalled Behavior**: When Delft3D is unavailable, the UI and API explicitly state:
   ```text
   Delft3D engine not installed.
   Configure DELFT3D_PATH in your .env file to enable Delft3D execution.
   ```

---

## 2. Input Deck Generation

When a scenario is configured, `backend/app/hydrodynamics/delft3d/adapter.py` creates a complete native Delft3D input deck:
- `<run_id>.mdf`: Master Definition File containing computational timesteps, Manning roughness ($n$), turbulence closures, and output frequency.
- `<run_id>.dep`: Depth / Bathymetry ASCII grid sampled from the project DEM.
- `<run_id>.grd`: Orthogonal curvilinear or rectilinear computational grid.
- `<run_id>.bnd`: Open boundary location defining the inflow breach cross-section.
- `<run_id>.bcc`: Dynamic discharge hydrograph time-series $Q(t)$.

---

## 3. Installation Guide for Users
To integrate a real Delft3D executable:
1. Download the Delft3D Open Source Suite from [Deltares OSS](https://oss.deltares.nl/web/delft3d).
2. Install the `FLOW` module.
3. In your `.env` file, specify the absolute path:
   ```bash
   DELFT3D_PATH="C:\Program Files\Deltares\Delft3D\w32\flow\bin\d_flow.exe"
   ```
4. Restart the backend server. The framework will automatically detect and execute Delft3D via background subprocesses.
