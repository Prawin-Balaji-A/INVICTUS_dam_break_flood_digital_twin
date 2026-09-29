import React, { useState, useEffect } from 'react';
import { 
  Satellite, 
  X, 
  CloudRain, 
  RefreshCw, 
  Globe, 
  ShieldAlert
} from 'lucide-react';
import { Project } from '../types';
import { api } from '../services/api';

interface GEEFloodAnalysisModalProps {
  isOpen: boolean;
  onClose: () => void;
  project: Project | null;
}

export const GEEFloodAnalysisModal: React.FC<GEEFloodAnalysisModalProps> = ({
  isOpen,
  onClose,
  project
}) => {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [selectedSensor, setSelectedSensor] = useState<'SAR' | 'OPTICAL'>('SAR');
  const [preDate, setPreDate] = useState('2024-06-15');
  const [postDate, setPostDate] = useState('2024-07-28');
  const [thresholdDb, setThresholdDb] = useState(-3.2);
  const [isProcessing, setIsProcessing] = useState(false);
  const [processResult, setProcessResult] = useState<any>(null);

  useEffect(() => {
    if (!isOpen || !project?.id) return;
    setLoading(true);
    api.getGEERealtimeAnalysis(project.id)
      .then(res => setData(res))
      .catch(err => console.error('Failed to fetch GEE data:', err))
      .finally(() => setLoading(false));
  }, [isOpen, project?.id]);

  const handleRunCustomGEE = async () => {
    if (!project?.id) return;
    setIsProcessing(true);
    try {
      const res = await api.triggerGEEAnalysis({
        project_id: project.id,
        sensor: selectedSensor === 'SAR' ? 'COPERNICUS/S1_GRD' : 'COPERNICUS/S2_SR_HARMONIZED',
        pre_date: preDate,
        post_date: postDate,
        threshold_db: thresholdDb
      });
      setProcessResult(res);
    } catch (err) {
      console.error('GEE processing error:', err);
    } finally {
      setIsProcessing(false);
    }
  };

  if (!isOpen) return null;

  const nrt = data?.near_realtime_metrics;
  const hydro = data?.hydrometeorological_telemetry;
  const hadr = data?.hadr_rapid_impact_scoping;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-sm p-3 md:p-6 overflow-hidden">
      <div className="bg-slate-900 border border-slate-700/80 rounded-2xl max-w-5xl w-full max-h-[92vh] flex flex-col text-slate-200 shadow-2xl overflow-hidden animate-in fade-in zoom-in-95 duration-200">
        
        {/* Header */}
        <div className="px-6 py-4 bg-slate-950/80 border-b border-slate-800 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-cyan-500/20 border border-cyan-500/40 flex items-center justify-center text-cyan-400">
              <Satellite className="w-5 h-5 animate-pulse" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-base font-bold text-white tracking-wide">
                  Google Earth Engine (GEE) • Near Real-Time Flood Analysis
                </h2>
                <span className="text-[10px] px-2 py-0.5 rounded bg-cyan-500/20 text-cyan-300 font-mono border border-cyan-500/30">
                  OPEN-SOURCE SATELLITE
                </span>
              </div>
              <p className="text-xs text-slate-400 mt-0.5">
                {project ? `${project.dam_name} Basin (${project.river_name}) • Copernicus Sentinel-1 SAR & Sentinel-2 MSI` : 'Near Real-Time Earth Observation Framework'}
              </p>
            </div>
          </div>

          <button 
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content */}
        <div className="p-6 overflow-y-auto flex-1 space-y-6">
          {loading ? (
            <div className="py-16 text-center text-slate-400 text-sm flex flex-col items-center justify-center gap-3">
              <div className="w-8 h-8 rounded-full border-2 border-cyan-500 border-t-transparent animate-spin" />
              <span>Connecting to Google Earth Engine satellite pipelines...</span>
            </div>
          ) : (
            <>
              {/* Top KPI Cards */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <div className="bg-slate-950/70 p-3.5 rounded-xl border border-slate-800">
                  <div className="text-[11px] text-slate-400 uppercase tracking-wider font-semibold">Satellite Flood Extent</div>
                  <div className="text-xl font-bold text-cyan-400 font-mono mt-0.5">
                    {nrt?.satellite_flood_extent_km2 ?? '—'} <span className="text-xs text-slate-400 font-normal">km²</span>
                  </div>
                  <div className="text-[10px] text-slate-500 mt-1">Copernicus Sentinel-1 SAR GRD</div>
                </div>

                <div className="bg-slate-950/70 p-3.5 rounded-xl border border-slate-800">
                  <div className="text-[11px] text-slate-400 uppercase tracking-wider font-semibold">Inundation Anomaly</div>
                  <div className="text-xl font-bold text-amber-400 font-mono mt-0.5">
                    +{nrt?.inundation_anomaly_km2 ?? '—'} <span className="text-xs text-slate-400 font-normal">km²</span>
                  </div>
                  <div className="text-[10px] text-slate-500 mt-1">Net expanded flood zone</div>
                </div>

                <div className="bg-slate-950/70 p-3.5 rounded-xl border border-slate-800">
                  <div className="text-[11px] text-slate-400 uppercase tracking-wider font-semibold">24h Basin Rainfall</div>
                  <div className="text-xl font-bold text-blue-400 font-mono mt-0.5">
                    {hydro?.catchment_rainfall_24h_mm ?? '—'} <span className="text-xs text-slate-400 font-normal">mm</span>
                  </div>
                  <div className="text-[10px] text-slate-500 mt-1">JAXA GPM IMERG Hourly</div>
                </div>

                <div className="bg-slate-950/70 p-3.5 rounded-xl border border-slate-800">
                  <div className="text-[11px] text-slate-400 uppercase tracking-wider font-semibold">Radar Cloud Penetration</div>
                  <div className="text-xl font-bold text-emerald-400 font-mono mt-0.5">
                    100%
                  </div>
                  <div className="text-[10px] text-slate-500 mt-1">0% monsoon cloud attenuation</div>
                </div>
              </div>

              {/* GEE Satellite Control Panel */}
              <div className="bg-slate-950/80 rounded-xl border border-slate-800 p-4 space-y-4">
                <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800/80 pb-3">
                  <div className="font-bold text-sm text-white flex items-center gap-2">
                    <Globe className="w-4 h-4 text-cyan-400" />
                    <span>Google Earth Engine Automated Change Detection Pipeline</span>
                  </div>
                  <div className="flex items-center gap-2 bg-slate-900 p-1 rounded-lg border border-slate-700 text-xs">
                    <button
                      onClick={() => setSelectedSensor('SAR')}
                      className={`px-3 py-1 rounded-md transition font-medium ${
                        selectedSensor === 'SAR' ? 'bg-cyan-600 text-white' : 'text-slate-400 hover:text-white'
                      }`}
                    >
                      Sentinel-1 SAR (Radar)
                    </button>
                    <button
                      onClick={() => setSelectedSensor('OPTICAL')}
                      className={`px-3 py-1 rounded-md transition font-medium ${
                        selectedSensor === 'OPTICAL' ? 'bg-cyan-600 text-white' : 'text-slate-400 hover:text-white'
                      }`}
                    >
                      Sentinel-2 MSI (MNDWI)
                    </button>
                  </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-4 gap-3 text-xs">
                  <div>
                    <label className="text-slate-400 block mb-1">Pre-Event Baseline Date</label>
                    <input
                      type="date"
                      value={preDate}
                      onChange={e => setPreDate(e.target.value)}
                      className="w-full bg-slate-900 border border-slate-700 rounded-lg px-2.5 py-1.5 text-slate-200 font-mono text-xs"
                    />
                  </div>
                  <div>
                    <label className="text-slate-400 block mb-1">Post-Event Near Real-Time Date</label>
                    <input
                      type="date"
                      value={postDate}
                      onChange={e => setPostDate(e.target.value)}
                      className="w-full bg-slate-900 border border-slate-700 rounded-lg px-2.5 py-1.5 text-slate-200 font-mono text-xs"
                    />
                  </div>
                  <div>
                    <label className="text-slate-400 block mb-1">SAR Threshold Δσ° (dB)</label>
                    <input
                      type="number"
                      step="0.1"
                      value={thresholdDb}
                      onChange={e => setThresholdDb(parseFloat(e.target.value) || -3.2)}
                      className="w-full bg-slate-900 border border-slate-700 rounded-lg px-2.5 py-1.5 text-slate-200 font-mono text-xs"
                    />
                  </div>
                  <div className="flex items-end">
                    <button
                      onClick={handleRunCustomGEE}
                      disabled={isProcessing}
                      className="w-full py-1.5 px-3 bg-gradient-to-r from-cyan-600 to-blue-600 hover:from-cyan-500 hover:to-blue-500 text-white font-semibold rounded-lg text-xs flex items-center justify-center gap-1.5 transition shadow"
                    >
                      <RefreshCw className={`w-3.5 h-3.5 ${isProcessing ? 'animate-spin' : ''}`} />
                      <span>{isProcessing ? 'Processing GEE...' : 'Execute GEE Pipeline'}</span>
                    </button>
                  </div>
                </div>

                {processResult && (
                  <div className="p-3 bg-cyan-950/40 border border-cyan-500/40 rounded-lg text-xs text-cyan-200 flex items-center justify-between">
                    <span>{processResult.message}</span>
                    <span className="font-mono font-bold text-white">Detected: {processResult.detected_flood_km2} km² ({processResult.gee_execution_time_sec}s)</span>
                  </div>
                )}
              </div>

              {/* Two Column Layout: Telemetry vs HADR Impact */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {/* Hydrometeorological & Basin Telemetry */}
                <div className="bg-slate-950/70 p-4 rounded-xl border border-slate-800 space-y-3">
                  <div className="font-semibold text-xs text-white flex items-center gap-1.5 border-b border-slate-800 pb-2">
                    <CloudRain className="w-4 h-4 text-blue-400" />
                    <span>Near Real-Time Basin Hydrology & CWC Telemetry</span>
                  </div>

                  <div className="space-y-2 text-xs font-mono">
                    <div className="flex justify-between p-2 rounded bg-slate-900/60 border border-slate-800">
                      <span className="text-slate-400 font-sans">Gauge Stage (CWC)</span>
                      <span className="text-white font-bold">{hydro?.cwc_gauge_stage_m ?? '—'} m MSL</span>
                    </div>
                    <div className="flex justify-between p-2 rounded bg-slate-900/60 border border-slate-800">
                      <span className="text-slate-400 font-sans">Measured Inflow Rate</span>
                      <span className="text-amber-400 font-bold">{hydro?.cwc_inflow_discharge_m3s?.toLocaleString() ?? '—'} m³/s</span>
                    </div>
                    <div className="flex justify-between p-2 rounded bg-slate-900/60 border border-slate-800">
                      <span className="text-slate-400 font-sans">7-Day Cumulative Basin Rainfall</span>
                      <span className="text-cyan-300 font-bold">{hydro?.catchment_rainfall_7d_mm ?? '—'} mm</span>
                    </div>
                    <div className="flex justify-between p-2 rounded bg-slate-900/60 border border-slate-800">
                      <span className="text-slate-400 font-sans">Basin Warning Status</span>
                      <span className="text-red-400 font-bold uppercase">{hydro?.river_basin_status ?? 'WATCH'}</span>
                    </div>
                  </div>

                  <div className="text-[10px] text-slate-500 font-sans">
                    Source: {hydro?.data_source}
                  </div>
                </div>

                {/* HADR Emergency Relief Scoping */}
                <div className="bg-slate-950/70 p-4 rounded-xl border border-slate-800 space-y-3">
                  <div className="font-semibold text-xs text-white flex items-center gap-1.5 border-b border-slate-800 pb-2">
                    <ShieldAlert className="w-4 h-4 text-rose-400" />
                    <span>HADR Rapid Impact Scoping (Humanitarian Assistance)</span>
                  </div>

                  <div className="space-y-2 text-xs font-mono">
                    <div className="flex justify-between p-2 rounded bg-slate-900/60 border border-slate-800">
                      <span className="text-slate-400 font-sans">Estimated At-Risk Population</span>
                      <span className="text-rose-400 font-bold">~{hadr?.estimated_affected_population?.toLocaleString() ?? '—'}</span>
                    </div>
                    <div className="flex justify-between p-2 rounded bg-slate-900/60 border border-slate-800">
                      <span className="text-slate-400 font-sans">Threatened Habitations / Villages</span>
                      <span className="text-amber-300 font-bold">{hadr?.threatened_villages_count ?? '—'} villages</span>
                    </div>
                    <div className="flex justify-between p-2 rounded bg-slate-900/60 border border-slate-800">
                      <span className="text-slate-400 font-sans">Submerged Agricultural Land</span>
                      <span className="text-emerald-400 font-bold">{hadr?.submerged_cropland_ha?.toLocaleString() ?? '—'} ha</span>
                    </div>
                    <div className="flex justify-between p-2 rounded bg-slate-900/60 border border-slate-800">
                      <span className="text-slate-400 font-sans">Evacuation Urgency</span>
                      <span className="text-rose-300 font-bold font-sans">{hadr?.evacuation_urgency ?? 'Standard'}</span>
                    </div>
                  </div>

                  <div className="text-[10px] text-slate-500 font-sans">
                    Adheres to NDMA / HADR emergency response protocols.
                  </div>
                </div>
              </div>
            </>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-3.5 bg-slate-950 border-t border-slate-800 flex items-center justify-between">
          <div className="text-[11px] text-slate-500 font-mono">
            Platform: Google Earth Engine Python API • Copernicus Open Access Hub • JAXA Earth API
          </div>
          <button
            onClick={onClose}
            className="px-4 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-xs font-medium text-slate-200 transition"
          >
            Close GEE Analysis
          </button>
        </div>

      </div>
    </div>
  );
};
