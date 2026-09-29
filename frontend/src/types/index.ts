export interface Project {
  id: string;
  name: string;
  river_name: string;
  country: string;
  state?: string;
  district?: string;
  dam_name: string;
  dam_lat: number;
  dam_lon: number;
  min_lat: number;
  min_lon: number;
  max_lat: number;
  max_lon: number;
  crs: string;
  projected_crs?: string;
  slug?: string;
  is_demo?: boolean;
  simulation_enabled?: boolean;
  dam_type?: string;
  operator?: string;
  source_provenance?: string;
  data_status?: 'ready' | 'partial' | 'not_configured' | 'invalid' | string;
  downstream_bearing_deg?: number;
  dam_height_m?: number;
  crest_length_m?: number;
  crest_elevation_m?: number;
  full_reservoir_level_m?: number;
  reservoir_capacity_m3?: number;
  reservoir_area_m2?: number;
  dem_path?: string;
  hillshade_path?: string;
  slope_path?: string;
  river_path?: string;
  buildings_path?: string;
  roads_path?: string;
  landuse_path?: string;
  created_at: string;
}

export interface DatasetItem {
  status: 'ready' | 'partial' | 'not_configured' | 'invalid' | string;
  path?: string | null;
  local_path?: string | null;
  source?: string | null;
  resolution_m?: number | null;
  resolution?: string | number | null;
  crs?: string | null;
  count?: number | null;
  feature_count?: number | null;
  total_km?: number | null;
  coverage?: string | null;
  notes?: string | null;
}

export interface ProjectDatasetsResponse {
  dam_id: string;
  datasets: Record<string, DatasetItem>;
}

export interface ProjectStatusResponse {
  project_id: string;
  name: string;
  river: string;
  state: string;
  is_demo: boolean;
  data_status: 'ready' | 'partial' | 'not_configured' | 'invalid' | string;
  datasets: Record<string, string>;
  scenarios: Record<string, string>;
  simulations: {
    count: number;
    has_results: boolean;
  };
  validation: {
    status: string;
  };
}

export interface Scenario {
  id: string;
  project_id: string;
  name: string;
  dam_height: number;
  dam_length: number;
  dam_crest_elev?: number;
  reservoir_volume: number;
  reservoir_level: number;
  reservoir_area?: number;
  breach_formulation: string;
  breach_type: string;
  breach_width: number;
  breach_depth: number;
  breach_time: number;
  breach_side_slope: number;
  peak_discharge_m3s?: number;
  hydrograph?: HydrographPoint[];
  manning_n?: number;
  is_baseline?: boolean;
}

export interface HydrographPoint {
  time_sec: number;
  time_min: number;
  discharge_m3s: number;
  stage_m: number;
  velocity_ms: number;
  reservoir_volume_m3: number;
}

export interface SimulationResult {
  id: string;
  project_id: string;
  scenario_id: string;
  engine_name: string;
  engine_status: string;
  status: string;
  progress: number;
  max_depth_m?: number;
  max_velocity_ms?: number;
  peak_discharge_m3s?: number;
  inundated_area_sqkm?: number;
  affected_buildings_count?: number;
  affected_roads_km?: number;
  exposed_population?: number;
  impact?: {
    buildings?: {
      total_buildings: number;
      affected_buildings: number;
      risk_breakdown: {
        low: number;
        moderate: number;
        high: number;
        very_high: number;
      };
    };
    roads?: {
      total_road_network_km: number;
      total_affected_roads_km: number;
      breakdown_by_highway_type_km: Record<string, number>;
    };
    landuse?: {
      total_inundated_area_sqkm: number;
      classes: Array<{
        class_name: string;
        area_sqkm: number;
        percentage: number;
      }>;
    };
    population?: {
      metric_type: string;
      estimated_exposed_population: number;
      average_household_size: number;
      disclaimer: string;
    };
  };
  timesteps?: Array<{
    time_min: number;
    discharge_m3s: number;
    max_depth_m: number;
    max_velocity_ms: number;
    inundated_area_sqkm: number;
  }>;
  flood_extent?: any;
}

export interface BenchmarkStatus {
  engine_name: string;
  engine_status: string;
  is_verified: boolean;
  benchmarks_available: Array<{
    id: string;
    name: string;
    description: string;
  }>;
  latest_result?: any;
}
