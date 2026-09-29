import React, { useEffect, useState } from 'react';
import { Database, ShieldCheck, CheckCircle, AlertCircle, XCircle, Layers, Activity, FileText, Info } from 'lucide-react';
import { Project, ProjectDatasetsResponse, ProjectStatusResponse } from '../types';
import { api } from '../services/api';

interface DataSourcesViewProps {
  project?: Project | null;
}

export const DataSourcesView: React.FC<DataSourcesViewProps> = ({ project }) => {
  const [datasetsData, setDatasetsData] = useState<ProjectDatasetsResponse | null>(null);
  const [statusData, setStatusData] = useState<ProjectStatusResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(false);

  useEffect(() => {
    if (!project?.id) return;
    setLoading(true);
    Promise.all([
      api.getProjectDatasets(project.id).catch(() => null),
      api.getProjectStatus(project.id).catch(() => null)
    ]).then(([ds, st]) => {
      setDatasetsData(ds);
      setStatusData(st);
    }).finally(() => {
      setLoading(false);
    });
  }, [project?.id]);

  const getStatusBadge = (status?: string) => {
    switch (status?.toLowerCase()) {
      case 'ready':
      case 'valid':
      case 'configured':
      case 'available':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded text-[11px] font-mono bg-emerald-950/70 border border-emerald-500/40 text-emerald-400 font-semibold">
            <CheckCircle className="w-3 h-3" />
            CONFIGURED
          </span>
        );
      case 'partial':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded text-[11px] font-mono bg-amber-950/70 border border-amber-500/40 text-amber-400 font-semibold">
            <AlertCircle className="w-3 h-3" />
            PARTIAL
          </span>
        );
      case 'optional':
      case 'not_ingested':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded text-[11px] font-mono bg-slate-800 border border-slate-600 text-slate-300 font-semibold">
            <Info className="w-3 h-3 text-slate-400" />
            OPTIONAL / NOT INGESTED
          </span>
        );
      case 'missing':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded text-[11px] font-mono bg-rose-950/70 border border-rose-500/40 text-rose-400 font-semibold">
            <XCircle className="w-3 h-3 text-rose-400" />
            MISSING
          </span>
        );
      case 'not_configured':
      default:
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded text-[11px] font-mono bg-slate-800 border border-slate-700 text-slate-400 font-semibold">
            <XCircle className="w-3 h-3 text-slate-500" />
            NOT CONFIGURED
          </span>
        );
    }
  };

  const generalSources = [
    {
      domain: 'Digital Elevation Model (DEM)',
      source: 'Shuttle Radar Topography Mission (SRTM) / Copernicus DEM GLO-30',
      resolution: '30 meters (1 arc-second)',
      coverage: 'Global / Regional Study Watershed',
      crs: 'EPSG:4326 (WGS84) & Local Projected UTM Zone',
      license: 'Public Domain / Open Data License',
      notes: 'Reprojected to metric UTM, sink-filled, and used to derive topographic slope, aspect, and flow direction.'
    },
    {
      domain: 'Waterways & Drainage Centerlines',
      source: 'OpenStreetMap (OSM) via Overpass API',
      resolution: 'Vector Lines',
      coverage: 'Study Area Bounding Box',
      crs: 'EPSG:4326 (WGS84)',
      license: 'Open Data Commons Open Database License (ODbL)',
      notes: 'Queried waterway=river, waterway=stream, and waterway=canal features.'
    },
    {
      domain: 'Infrastructure & Buildings',
      source: 'OpenStreetMap & Overture Maps Foundation',
      resolution: 'Vector Polygons with Height & Levels',
      coverage: 'Downstream Floodplain Corridor',
      crs: 'EPSG:4326 (WGS84)',
      license: 'ODbL / Overture Open Data',
      notes: 'Footprints intersected with maximum depth raster to determine exposure and categorize flood risk.'
    },
    {
      domain: 'Road Network',
      source: 'OpenStreetMap (OSM)',
      resolution: 'Vector Lines (highway=*)',
      coverage: 'Study Area Bounding Box',
      crs: 'EPSG:4326 (WGS84)',
      license: 'ODbL',
      notes: 'Stratified into primary, secondary, and tertiary transportation lifelines to compute submerged length in km.'
    },
    {
      domain: 'Satellite Validation',
      source: 'Copernicus Sentinel-1 SAR (C-Band GRD, IW)',
      resolution: '10 meters Ground Sample Distance',
      coverage: 'Bitemporal Pre/Post Flood Passes',
      crs: 'EPSG:4326 (WGS84)',
      license: 'Copernicus Open Access Policy',
      notes: 'Dual-polarization (VV/VH) backscatter change detection used to independently compute IoU, Precision, Recall, and F1.'
    },
    {
      domain: 'Population Exposure',
      source: 'WorldPop / Census of India Spatial Disaggregation',
      resolution: '100 meters (1 hectare)',
      coverage: 'Administrative District',
      crs: 'EPSG:4326 (WGS84)',
      license: 'Creative Commons Attribution 4.0',
      notes: 'Reports population exposure (inhabitants within flood zone), explicitly distinguished from casualties.'
    }
  ];

  return (
    <div className="flex-1 bg-slate-950 text-slate-200 p-8 overflow-y-auto">
      <div className="max-w-5xl mx-auto space-y-8">
        {/* Header */}
        <div className="flex items-center justify-between pb-6 border-b border-slate-800">
          <div>
            <h1 className="text-2xl font-bold text-white flex items-center gap-2.5">
              <Database className="w-6 h-6 text-blue-400" />
              <span>Project Datasets & Scientific Provenance</span>
            </h1>
            <p className="text-sm text-slate-400 mt-1">
              Data readiness status, registry specifications, and open source attribution.
            </p>
          </div>
          <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-950/60 border border-emerald-500/40 text-emerald-300 text-xs font-mono">
            <ShieldCheck className="w-4 h-4" />
            <span>Zero Fabricated Scientific Data</span>
          </div>
        </div>

        {/* Section 1: Active Dam Data Readiness */}
        {project && (
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-lg font-bold text-white flex items-center gap-2">
                  <Activity className="w-5 h-5 text-indigo-400" />
                  <span>{project.name}</span>
                </h2>
                <p className="text-xs text-slate-400 mt-0.5">
                  River: <span className="text-slate-200 font-medium">{project.river_name}</span> | State: <span className="text-slate-200 font-medium">{project.state || 'India'}</span> | Coordinates: <span className="font-mono text-slate-300">{project.dam_lat.toFixed(4)}°N, {project.dam_lon.toFixed(4)}°E</span>
                </p>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-xs text-slate-400">Dataset Status:</span>
                {getStatusBadge(statusData?.data_status || project.data_status || 'not_configured')}
              </div>
            </div>


            {/* Dam Engineering Parameters Card */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 bg-slate-900/80 border border-slate-800 rounded-xl p-4 text-xs font-mono">
              <div>
                <span className="text-slate-500 block text-[10px]">DAM HEIGHT</span>
                <span className="text-slate-200 font-semibold">{project.dam_height_m ? `${project.dam_height_m} m` : 'Not verified'}</span>
              </div>
              <div>
                <span className="text-slate-500 block text-[10px]">CREST LENGTH</span>
                <span className="text-slate-200 font-semibold">{project.crest_length_m ? `${project.crest_length_m} m` : 'Not verified'}</span>
              </div>
              <div>
                <span className="text-slate-500 block text-[10px]">RESERVOIR CAPACITY</span>
                <span className="text-slate-200 font-semibold">{project.reservoir_capacity_m3 ? `${(project.reservoir_capacity_m3 / 1e6).toFixed(1)} MCM` : 'Not verified'}</span>
              </div>
              <div>
                <span className="text-slate-500 block text-[10px]">FULL RESERVOIR LEVEL</span>
                <span className="text-slate-200 font-semibold">{project.full_reservoir_level_m ? `${project.full_reservoir_level_m} m` : 'Not verified'}</span>
              </div>
            </div>

            {/* Individual Dataset Registry Cards */}
            {loading ? (
              <div className="p-6 text-center text-xs text-slate-500 font-mono">Loading dataset registry...</div>
            ) : datasetsData?.datasets ? (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {Object.entries(datasetsData.datasets).map(([key, ds]) => (
                  <div key={key} className="bg-slate-900 border border-slate-800 rounded-lg p-4 space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="font-semibold text-sm text-slate-200 uppercase tracking-wide flex items-center gap-1.5">
                        <Layers className="w-4 h-4 text-blue-400" />
                        {key}
                      </span>
                      {getStatusBadge(
                        (key === 'population' || key === 'satellite') && (!ds.status || ds.status.toLowerCase() === 'not_configured')
                          ? 'optional'
                          : ds.status
                      )}
                    </div>
                    <div className="text-xs space-y-1 text-slate-400 font-mono">
                      <div>Source: <span className="text-slate-200">{ds.source || 'Pending authoritative source'}</span></div>
                      {(ds.resolution_m || ds.resolution) && (
                        <div>Resolution: <span className="text-slate-200">{ds.resolution_m ? `${ds.resolution_m} m` : ds.resolution}</span></div>
                      )}
                      {ds.crs && <div>CRS: <span className="text-slate-200">{ds.crs}</span></div>}
                      {(ds.feature_count != null || ds.count != null) && (
                        <div>Features: <span className="text-slate-200">{ds.feature_count ?? ds.count}</span></div>
                      )}
                      {ds.coverage && <div>Coverage: <span className="text-slate-300 font-sans text-[11px]">{ds.coverage}</span></div>}
                      {ds.total_km != null && <div>Network: <span className="text-slate-200">{ds.total_km} km</span></div>}
                      {ds.notes && <div className="text-[11px] text-slate-500 italic font-sans">{ds.notes}</div>}
                    </div>
                  </div>
                ))}
              </div>
            ) : null}
          </div>
        )}

        {/* Section 2: General Open Data Attribution */}
        <div className="space-y-4 pt-6 border-t border-slate-800">
          <div>
            <h2 className="text-lg font-bold text-white flex items-center gap-2">
              <FileText className="w-5 h-5 text-blue-400" />
              <span>Standard Data Specifications & Provenance</span>
            </h2>
            <p className="text-xs text-slate-400 mt-0.5">
              Authoritative open sources planned or integrated for the five dam study sites.
            </p>
          </div>

          <div className="grid grid-cols-1 gap-4">
            {generalSources.map((s, idx) => (
              <div key={idx} className="bg-slate-900 border border-slate-800 rounded-xl p-5 hover:border-slate-700 transition">
                <div className="flex items-center justify-between">
                  <div className="font-bold text-base text-white flex items-center gap-2">
                    <CheckCircle className="w-4 h-4 text-blue-400" />
                    <span>{s.domain}</span>
                  </div>
                  <span className="text-[11px] font-mono px-2.5 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700">
                    {s.resolution}
                  </span>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-3 text-xs">
                  <div>
                    <span className="text-slate-400 font-medium">Primary Source: </span>
                    <span className="text-slate-200">{s.source}</span>
                  </div>
                  <div>
                    <span className="text-slate-400 font-medium">Coordinate System: </span>
                    <span className="text-slate-200 font-mono">{s.crs}</span>
                  </div>
                  <div>
                    <span className="text-slate-400 font-medium">License / Terms: </span>
                    <span className="text-slate-300">{s.license}</span>
                  </div>
                  <div>
                    <span className="text-slate-400 font-medium">Coverage: </span>
                    <span className="text-slate-300">{s.coverage}</span>
                  </div>
                </div>

                <div className="mt-3 pt-3 border-t border-slate-800/80 text-xs text-slate-400 leading-relaxed">
                  <strong className="text-slate-300">Methodology: </strong> {s.notes}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};
