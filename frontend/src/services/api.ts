import { Project, Scenario, SimulationResult, BenchmarkStatus, ProjectDatasetsResponse, ProjectStatusResponse } from '../types';

const API_BASE = '/api';

export const api = {
  // Projects
  async getProjects(): Promise<Project[]> {
    const res = await fetch(`${API_BASE}/projects`);
    if (!res.ok) throw new Error('Failed to fetch projects');
    return res.json();
  },

  async getProjectDatasets(projectId: string): Promise<ProjectDatasetsResponse> {
    const res = await fetch(`${API_BASE}/projects/${projectId}/datasets`);
    if (!res.ok) throw new Error('Failed to fetch project datasets');
    return res.json();
  },

  async getProjectStatus(projectId: string): Promise<ProjectStatusResponse> {
    const res = await fetch(`${API_BASE}/projects/${projectId}/status`);
    if (!res.ok) throw new Error('Failed to fetch project status');
    return res.json();
  },

  async createProject(data: Partial<Project>): Promise<Project> {
    const res = await fetch(`${API_BASE}/projects`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data)
    });
    if (!res.ok) throw new Error('Failed to create project');
    return res.json();
  },

  // Scenarios
  async getScenarios(projectId: string): Promise<Scenario[]> {
    const res = await fetch(`${API_BASE}/scenarios/project/${projectId}`);
    if (!res.ok) throw new Error('Failed to fetch scenarios');
    return res.json();
  },

  async getScenarioDetails(scenarioId: string): Promise<Scenario> {
    const res = await fetch(`${API_BASE}/scenarios/${scenarioId}`);
    if (!res.ok) throw new Error('Failed to fetch scenario details');
    return res.json();
  },

  async createScenario(data: any): Promise<Scenario> {
    const res = await fetch(`${API_BASE}/scenarios`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data)
    });
    if (!res.ok) throw new Error('Failed to create scenario');
    return res.json();
  },

  async previewScenario(data: any): Promise<{
    peak_discharge_m3s: number;
    time_to_peak_min: number;
    breach_width_m: number;
    breach_time_min: number;
    breach_depth_m: number;
    reservoir_volume_mcm: number;
    reservoir_level_m: number;
    hydrograph: Array<{ time_min: number; discharge_m3s: number; stage_m: number }>;
  }> {
    const res = await fetch(`${API_BASE}/scenarios/preview`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data)
    });
    if (!res.ok) throw new Error('Failed to preview scenario hydrograph');
    return res.json();
  },

  async createOrUpdateCustomScenario(data: any): Promise<Scenario> {
    const res = await fetch(`${API_BASE}/scenarios/custom`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data)
    });
    if (!res.ok) throw new Error('Failed to save custom scenario');
    return res.json();
  },

  // Datasets
  async fetchGeojson(layer: 'river' | 'buildings' | 'roads', projectId: string): Promise<any> {
    const res = await fetch(`${API_BASE}/datasets/geojson/${layer}/${projectId}`);
    if (!res.ok) return null;
    return res.json();
  },

  // Simulation
  async runSimulation(projectId: string, scenarioId: string, engineName: string = 'Hydrodynamic 2D Solver'): Promise<{ simulation_id: string; engine_name: string; engine_status: string }> {
    const res = await fetch(`${API_BASE}/simulation/run`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        project_id: projectId,
        scenario_id: scenarioId,
        engine_name: engineName
      })
    });
    if (!res.ok) {
      const errBody = await res.json().catch(() => ({}));
      throw new Error(errBody.detail || 'Failed to trigger simulation');
    }
    return res.json();
  },

  async getSimulationStatus(simId: string): Promise<any> {
    const res = await fetch(`${API_BASE}/simulation/${simId}/status`);
    if (!res.ok) throw new Error('Failed to get simulation status');
    return res.json();
  },

  async getSimulationResults(simId: string): Promise<SimulationResult> {
    const res = await fetch(`${API_BASE}/simulation/${simId}/results`);
    if (!res.ok) throw new Error('Failed to get simulation results');
    return res.json();
  },

  async getLatestSimulation(projectId: string, scenarioId?: string): Promise<SimulationResult | null> {
    const url = scenarioId
      ? `${API_BASE}/simulation/project/${projectId}/latest?scenario_id=${encodeURIComponent(scenarioId)}`
      : `${API_BASE}/simulation/project/${projectId}/latest`;
    const res = await fetch(url);
    if (!res.ok) return null;
    return res.json();
  },

  // SPH Benchmarks
  async getBenchmarkStatus(): Promise<BenchmarkStatus> {
    const res = await fetch(`${API_BASE}/benchmarks/status`);
    if (!res.ok) throw new Error('Failed to fetch benchmark status');
    return res.json();
  },

  async runBenchmark(benchmarkName: string, totalTime: number = 2.0): Promise<any> {
    const res = await fetch(`${API_BASE}/benchmarks/run`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        benchmark_name: benchmarkName,
        total_time: totalTime
      })
    });
    if (!res.ok) throw new Error('Failed to run benchmark');
    return res.json();
  },

  // Satellite Comparison
  async compareSatellite(simId: string): Promise<any> {
    const res = await fetch(`${API_BASE}/satellite/compare-sentinel1/${simId}`, {
      method: 'POST'
    });
    if (!res.ok) throw new Error('Failed to run satellite comparison');
    return res.json();
  },

  // Scientific Consistency & Validation
  async getSimulationValidation(simId: string): Promise<any> {
    const res = await fetch(`${API_BASE}/simulation/${simId}/validation`);
    if (!res.ok) throw new Error('Failed to get simulation validation');
    return res.json();
  },

  // National Dam Registry & Search
  async searchDams(query: string = '', state?: string, river?: string, simulationOnly: boolean = false): Promise<any[]> {
    const params = new URLSearchParams();
    if (query) params.append('q', query);
    if (state) params.append('state', state);
    if (river) params.append('river', river);
    if (simulationOnly) params.append('simulation_only', 'true');
    const res = await fetch(`${API_BASE}/dams/search?${params.toString()}`);
    if (!res.ok) throw new Error('Failed to search dams');
    return res.json();
  },

  async getAllDams(): Promise<any[]> {
    const res = await fetch(`${API_BASE}/dams`);
    if (!res.ok) throw new Error('Failed to fetch dam registry');
    return res.json();
  },

  async getDamDetails(damId: string): Promise<any> {
    const res = await fetch(`${API_BASE}/dams/${damId}`);
    if (!res.ok) throw new Error('Failed to fetch dam details');
    return res.json();
  },

  // Machine Learning Surrogate Model
  async getMLMetrics(): Promise<any> {
    const res = await fetch(`${API_BASE}/ml/metrics`);
    if (!res.ok) throw new Error('Failed to fetch ML metrics');
    return res.json();
  },

  async predictPoint(data: { lat: number; lon: number; project_id?: string; active_volume_mcm?: number; peak_discharge_m3s?: number }): Promise<any> {
    const res = await fetch(`${API_BASE}/ml/predict-point`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data)
    });
    if (!res.ok) throw new Error('Failed to run ML point prediction');
    return res.json();
  },

  async predictGrid(data: { project_id: string; active_volume_mcm?: number; peak_discharge_m3s?: number; grid_resolution?: number }): Promise<any> {
    const res = await fetch(`${API_BASE}/ml/predict-grid`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data)
    });
    if (!res.ok) throw new Error('Failed to run ML grid prediction');
    return res.json();
  },

  // ---- Digital Twin (Phase 6): authoritative-raster-driven endpoints ------
  // Every endpoint below reads the VERIFIED hydraulic rasters
  // (maximum_depth/velocity/arrival_time). Nothing here synthesises flood
  // depth, extent, or discharge — the frontend must render only these values.
  async getTwinTimeline(simRef: string, frames: number = 24): Promise<any> {
    const res = await fetch(`${API_BASE}/simulation/${simRef}/timeline?frames=${frames}`);
    if (!res.ok) throw new Error('Failed to fetch twin timeline');
    return res.json();
  },

  // Co-registered DEM + depth + arrival + mask grid for the real 3D terrain
  // and per-cell water surface. Everything is derived from authoritative rasters.
  async getTwinTerrain(simRef: string, res: number = 160): Promise<any> {
    const r = await fetch(`${API_BASE}/simulation/${simRef}/terrain?res=${res}`);
    if (!r.ok) throw new Error('Failed to fetch twin terrain');
    return r.json();
  },

  async getTwinImpact(simRef: string): Promise<any> {
    const res = await fetch(`${API_BASE}/simulation/${simRef}/impact`);
    if (!res.ok) throw new Error('Failed to fetch twin impact');
    return res.json();
  },

  async getTwinBuildings(simRef: string, limit: number = 2000): Promise<any> {
    const res = await fetch(`${API_BASE}/simulation/${simRef}/buildings?limit=${limit}`);
    if (!res.ok) throw new Error('Failed to fetch twin buildings');
    return res.json();
  },

  async getTwinRoads(simRef: string): Promise<any> {
    const res = await fetch(`${API_BASE}/simulation/${simRef}/roads`);
    if (!res.ok) throw new Error('Failed to fetch twin roads');
    return res.json();
  },

  async getTwinRiver(simRef: string): Promise<any> {
    const res = await fetch(`${API_BASE}/simulation/${simRef}/river`);
    if (!res.ok) throw new Error('Failed to fetch twin river');
    return res.json();
  },

  async getTwinFlowVectors(simRef: string, step: number = 8): Promise<any> {
    const res = await fetch(`${API_BASE}/simulation/${simRef}/flow-vectors?step=${step}`);
    if (!res.ok) throw new Error('Failed to fetch twin flow vectors');
    return res.json();
  },

  // Honest twin-availability gate: reports which authoritative layers exist on
  // disk (DEM + four hydraulic rasters + GIS). `twin_ready` is true ONLY when
  // real data exists — the UI uses this to avoid launching a twin that has no
  // simulation behind it. Never fabricates a simulation.
  async getTwinAvailability(simRef: string): Promise<any> {
    const res = await fetch(`${API_BASE}/simulation/${simRef}/availability`);
    if (!res.ok) throw new Error('Failed to fetch twin availability');
    return res.json();
  },

  // SPH vs Delft3D Hydrodynamic Model Comparison
  async getSPHDelft3DComparison(simIdOrProjectId: string, isProject: boolean = false): Promise<any> {
    const url = isProject 
      ? `${API_BASE}/simulation/comparison/sph-vs-delft3d/project/${simIdOrProjectId}`
      : `${API_BASE}/simulation/comparison/sph-vs-delft3d/${simIdOrProjectId}`;
    const res = await fetch(url);
    if (!res.ok) throw new Error('Failed to fetch SPH vs Delft3D comparison');
    return res.json();
  },

  // Google Earth Engine (GEE) Near Real-Time Flood Analysis
  async getGEERealtimeAnalysis(projectId: string): Promise<any> {
    const res = await fetch(`${API_BASE}/satellite/gee/realtime/${projectId}`);
    if (!res.ok) throw new Error('Failed to fetch GEE real-time flood analysis');
    return res.json();
  },

  async triggerGEEAnalysis(payload: any): Promise<any> {
    const res = await fetch(`${API_BASE}/satellite/gee/analyze`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    if (!res.ok) throw new Error('Failed to trigger custom GEE analysis');
    return res.json();
  }
};

