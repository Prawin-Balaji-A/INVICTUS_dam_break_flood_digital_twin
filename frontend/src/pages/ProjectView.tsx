import React, { useState, useEffect } from 'react';
import { Project, Scenario, SimulationResult } from '../types';
import { api } from '../services/api';
import { MapLibreMap } from '../map/MapLibreMap';
import { MetricCards } from '../components/MetricCards';
import { TimelineSlider } from '../components/TimelineSlider';
import { Sliders, Satellite, X, PanelRightOpen, AlertTriangle } from 'lucide-react';

interface ProjectViewProps {
  project: Project | null;
  scenario: Scenario | null;
  simulation: SimulationResult | null;
  onRefreshSimulation?: () => void;
  // The ONE simulation clock lives in App.selectedProject's sibling state and is
  // shared with the 3D twin, so scrubbing here and in 3D move the same flood.
  currentTimeMin: number;
  maxTimeMin: number;
  onChangeTime: (t: number) => void;
  isPlaying: boolean;
  onTogglePlay: () => void;
  onOpenManualModal?: () => void;
  simulationMode?: 'REAL_TIME' | 'MANUAL';
}

export const ProjectView: React.FC<ProjectViewProps> = ({
  project,
  scenario,
  simulation,
  onRefreshSimulation: _onRefreshSimulation,
  currentTimeMin,
  maxTimeMin,
  onChangeTime,
  isPlaying,
  onTogglePlay,
  onOpenManualModal,
  simulationMode: _simulationMode = 'REAL_TIME'
}) => {
  const [riverGeojson, setRiverGeojson] = useState<any>(null);
  const [buildingsGeojson, setBuildingsGeojson] = useState<any>(null);
  const [roadsGeojson, setRoadsGeojson] = useState<any>(null);

  const [satelliteModalOpen, setSatelliteModalOpen] = useState(false);
  const [satelliteData, setSatelliteData] = useState<any>(null);
  const [isComparingSat, setIsComparingSat] = useState(false);
  // The floating breach/hydrograph panel is closeable so the flood view is
  // unobstructed; a small reopen control restores it.
  const [detailsPanelOpen, setDetailsPanelOpen] = useState(true);

  // Load vector layers when project changes
  useEffect(() => {
    if (!project?.id) return;
    api.fetchGeojson('river', project.id).then(setRiverGeojson).catch(console.error);
    api.fetchGeojson('buildings', project.id).then(setBuildingsGeojson).catch(console.error);
    api.fetchGeojson('roads', project.id).then(setRoadsGeojson).catch(console.error);
  }, [project?.id]);

  // Timeline Animation Loop — advances the SHARED App clock (same clock the 3D
  // twin drives), so 2D and 3D always agree on the current flood time. Only one
  // view is mounted at a time, so only one loop runs.
  useEffect(() => {
    if (!isPlaying) return;
    const timer = window.setInterval(() => {
      const next = currentTimeMin + maxTimeMin / 120;
      if (next >= maxTimeMin) { onChangeTime(maxTimeMin); onTogglePlay(); }
      else onChangeTime(next);
    }, 250);
    return () => window.clearInterval(timer);
  }, [isPlaying, currentTimeMin, maxTimeMin, onChangeTime, onTogglePlay]);

  // Current timeline step metrics
  const currentStepData = simulation?.timesteps?.find(
    s => Math.abs(s.time_min - currentTimeMin) <= 5
  );

  const handleRunSatelliteComparison = async () => {
    if (!simulation?.id) return;
    setIsComparingSat(true);
    try {
      const res = await api.compareSatellite(simulation.id);
      setSatelliteData(res);
      setSatelliteModalOpen(true);
    } catch (e) {
      console.error(e);
      alert('Failed to execute satellite comparison');
    } finally {
      setIsComparingSat(false);
    }
  };

  // Dynamic hydrograph data
  const hydroPoints = (simulation?.timesteps && simulation.timesteps.length > 0)
    ? simulation.timesteps.map(s => ({ time_min: s.time_min, discharge_m3s: s.discharge_m3s }))
    : (scenario?.hydrograph && scenario.hydrograph.length > 0)
      ? scenario.hydrograph.map(h => ({ time_min: h.time_min, discharge_m3s: h.discharge_m3s }))
      : [];

  const hydroMaxQ = hydroPoints.length > 0
    ? Math.max(...hydroPoints.map(p => p.discharge_m3s), 1)
    : (scenario?.peak_discharge_m3s || 1);

  const hydroMaxT = hydroPoints.length > 0
    ? Math.max(...hydroPoints.map(p => p.time_min), 1)
    : (maxTimeMin || 360);

  const displayPeakQ = simulation?.peak_discharge_m3s
    || (hydroPoints.length > 0 ? Math.max(...hydroPoints.map(p => p.discharge_m3s)) : scenario?.peak_discharge_m3s)
    || 0;

  const svgPolyline = hydroPoints.length > 1
    ? hydroPoints.map(p => {
        const x = Math.min(100, Math.max(0, (p.time_min / hydroMaxT) * 100));
        const y = Math.min(38, Math.max(2, 38 - (p.discharge_m3s / hydroMaxQ) * 34));
        return `${x.toFixed(1)},${y.toFixed(1)}`;
      }).join(' ')
    : '';

  const svgArea = hydroPoints.length > 1
    ? `M 0,38 L ${svgPolyline.split(' ').join(' L ')} L 100,38 Z`
    : '';

  return (
    <div className="flex-1 flex flex-col h-full bg-slate-950 overflow-hidden relative">
      {/* 1. HUD Metric Cards */}
      <MetricCards simulation={simulation} />

      {/* Scenario Type Banner */}
      <div className="bg-amber-950/40 border-b border-amber-800/50 px-4 py-1.5 flex items-center justify-between text-[11px] text-amber-200/90 font-mono">
        <div className="flex items-center gap-2">
          <span className="px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-300 font-bold border border-amber-500/40">
            SCENARIO TYPE: HYPOTHETICAL DAM-BREAK
          </span>
          <span className="text-slate-300">
            Baseline Overtopping Simulation (Froehlich 2008) · Emergency Planning & Inundation Risk Modeling
          </span>
        </div>
        <div className="text-[10px] text-slate-400">
          Does not represent observed historical failure or current structural distress of {project?.dam_name || 'the dam'}
        </div>
      </div>

      {/* 2. Main Middle View: Map + Right Panel */}
      <div className="flex-1 flex relative overflow-hidden">
        {/* Map Container */}
        <MapLibreMap
          project={project}
          riverGeojson={riverGeojson}
          buildingsGeojson={buildingsGeojson}
          roadsGeojson={roadsGeojson}
          simulation={simulation}
          currentTimeMin={currentTimeMin}
        />

        {/* Floating Right HUD Panel: Breach & Hydrograph Details (closeable) */}
        {detailsPanelOpen ? (
        <div className="absolute top-4 right-4 z-20 w-80 max-w-[calc(100vw-2rem)] bg-slate-900/90 backdrop-blur-md border border-slate-800 rounded-xl p-3.5 text-xs text-slate-200 shadow-2xl space-y-2.5 font-sans max-h-[calc(100vh-230px)] overflow-y-auto scrollbar-thin scrollbar-thumb-slate-700">
          <div className="flex items-center justify-between pb-2 border-b border-slate-800">
            <span className="font-bold text-white flex items-center gap-1.5">
              <Sliders className="w-4 h-4 text-blue-400" />
              <span>Breach Hydrodynamics</span>
            </span>
            <div className="flex items-center gap-1.5">
              <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-amber-500/20 text-amber-300 font-semibold border border-amber-500/30">
                HYPOTHETICAL DAM-BREAK
              </span>
              <button
                onClick={() => setDetailsPanelOpen(false)}
                title="Close panel"
                className="text-slate-400 hover:text-white p-0.5 rounded hover:bg-slate-800 transition"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
          </div>

          {/* Scenario Details */}
          {scenario && (
            <div className="space-y-1.5 font-mono text-[11px]">
              <div className="flex justify-between">
                <span className="text-slate-400">Formulation:</span>
                <span className="text-blue-300 font-medium">{scenario.breach_formulation || 'Froehlich_2008'}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Breach Width (Bavg):</span>
                <span className="text-white font-bold">
                  {scenario.breach_width != null ? `${scenario.breach_width.toFixed(1)} m` : '—'}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Formation Time (tf):</span>
                <span className="text-white">
                  {scenario.breach_time != null ? `${(scenario.breach_time / 60.0).toFixed(1)} min` : '—'}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Breach Depth:</span>
                <span className="text-white">
                  {scenario.breach_depth != null ? `${scenario.breach_depth.toFixed(1)} m` : '—'}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Initial Reservoir Head:</span>
                <span className="text-white">
                  {scenario.reservoir_level != null ? `${scenario.reservoir_level} m MSL` : '—'}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Reservoir Capacity:</span>
                <span className="text-white font-mono">
                  {project?.reservoir_capacity_m3 ? `${(project.reservoir_capacity_m3 / 1e6).toFixed(1)} MCM` : '—'}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Active Breach Storage:</span>
                <span className="text-amber-300 font-bold font-mono">
                  {scenario.reservoir_volume != null ? `${(scenario.reservoir_volume / 1e6).toFixed(1)} MCM` : '—'}
                </span>
              </div>
            </div>
          )}

          {/* Model & Solver Provenance */}
          <div className="pt-2 border-t border-slate-800 space-y-1 font-mono text-[10px]">
            <div className="text-slate-400 font-sans font-semibold text-[11px] mb-0.5">Hydrodynamic Solver:</div>
            <div className="flex justify-between">
              <span className="text-slate-500">Active Solver:</span>
              <span className="text-emerald-400 font-semibold">Manning 2D Wave</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500">SPH Status:</span>
              <span className="text-slate-400">NOT YET COUPLED</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500">Delft3D Status:</span>
              <span className="text-slate-400">EXPORTER ONLY</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500">Terrain DEM:</span>
              <span className="text-cyan-400">Copernicus 30m</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500">River Network:</span>
              <span className="text-cyan-400">{project?.river_name ? `${project.river_name.replace(' River', '')} Vectors` : 'River Vectors'}</span>
            </div>
          </div>

          {/* Mini Discharge Hydrograph Preview */}
          <div className="pt-2 border-t border-slate-800">
            <div className="flex items-center justify-between text-[11px] font-semibold text-slate-300 mb-1.5">
              <span>Outflow Hydrograph Q(t)</span>
              <span className="text-amber-400 font-mono">
                Peak: {displayPeakQ > 0 ? `${Math.round(displayPeakQ).toLocaleString()} m³/s` : '—'}
              </span>
            </div>
            
            {/* SVG Hydrograph Curve */}
            <div className="h-20 w-full bg-slate-950 rounded p-1 border border-slate-800/80 relative flex items-center justify-center">
              {hydroPoints.length > 1 ? (
                <svg className="w-full h-full overflow-visible" viewBox="0 0 100 40" preserveAspectRatio="none">
                  {svgArea && (
                    <path
                      d={svgArea}
                      fill="rgba(56, 189, 248, 0.15)"
                    />
                  )}
                  <polyline
                    points={svgPolyline}
                    fill="none"
                    stroke="#38bdf8"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                  {/* Current Time Cursor Line */}
                  <line
                    x1={Math.min(100, (currentTimeMin / hydroMaxT) * 100)}
                    y1="0"
                    x2={Math.min(100, (currentTimeMin / hydroMaxT) * 100)}
                    y2="40"
                    stroke="#f59e0b"
                    strokeWidth="1.5"
                    strokeDasharray="2,2"
                  />
                </svg>
              ) : (
                <div className="text-[10px] text-slate-500 font-mono text-center">
                  Hydrograph awaiting verified dam & reservoir inputs
                </div>
              )}
              <div className="absolute bottom-1 left-2 text-[9px] text-slate-500 font-mono">00:00</div>
              <div className="absolute bottom-1 right-2 text-[9px] text-slate-500 font-mono">
                {`T+${Math.floor(hydroMaxT / 60).toString().padStart(2, '0')}:${(Math.floor(hydroMaxT) % 60).toString().padStart(2, '0')}`}
              </div>
            </div>
          </div>

          {/* Sentinel-1 Satellite Comparison Button */}
          {simulation && (
            <div className="pt-2 border-t border-slate-800">
              <button
                onClick={handleRunSatelliteComparison}
                disabled={isComparingSat}
                className="w-full py-2 px-3 rounded-lg bg-indigo-600/20 hover:bg-indigo-600/30 text-indigo-300 border border-indigo-500/40 font-semibold text-xs flex items-center justify-center gap-1.5 transition shadow"
              >
                <Satellite className={`w-3.5 h-3.5 ${isComparingSat ? 'animate-spin' : ''}`} />
                <span>{isComparingSat ? 'Evaluating SAR...' : 'Compare with Sentinel-1 SAR'}</span>
              </button>
            </div>
          )}
          {/* Manual Parameters Sliders Button */}
          {onOpenManualModal && (
            <div className="pt-2 border-t border-slate-800">
              <button
                onClick={onOpenManualModal}
                className="w-full py-2 px-3 rounded-lg bg-cyan-950/70 hover:bg-cyan-900 text-cyan-200 border border-cyan-500/40 font-semibold text-xs flex items-center justify-center gap-1.5 transition shadow"
              >
                <Sliders className="w-3.5 h-3.5 text-cyan-400" />
                <span>Adjust Parameters (Sliders)</span>
              </button>
            </div>
          )}
        </div>
        ) : (
          <div className="absolute top-4 right-4 z-20 flex items-center gap-2">
            {onOpenManualModal && (
              <button
                onClick={onOpenManualModal}
                title="Configure manual simulation parameters"
                className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-slate-900/90 backdrop-blur-md border border-slate-700 text-xs font-semibold text-cyan-300 hover:text-white hover:border-cyan-500 shadow-xl transition"
              >
                <Sliders className="w-3.5 h-3.5 text-cyan-400" />
                <span>Parameters</span>
              </button>
            )}
            <button
              onClick={() => setDetailsPanelOpen(true)}
              title="Show breach hydrodynamics panel"
              className="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-slate-900/90 backdrop-blur-md border border-slate-700 text-xs font-semibold text-slate-200 hover:text-white hover:border-slate-500 shadow-xl transition"
            >
              <PanelRightOpen className="w-4 h-4 text-blue-400" />
              <span>Hydrodynamics</span>
            </button>
          </div>
        )}
      </div>

      {/* 3. Bottom Timeline Slider */}
      <TimelineSlider
        currentTimeMin={currentTimeMin}
        maxTimeMin={maxTimeMin}
        onChangeTime={onChangeTime}
        isPlaying={isPlaying}
        onTogglePlay={onTogglePlay}
        currentDischarge={currentStepData?.discharge_m3s || 0}
        currentFloodedArea={currentStepData?.inundated_area_sqkm || 0}
      />

      {/* Sentinel-1 SAR Comparison Modal */}
      {satelliteModalOpen && satelliteData && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
          <div className="bg-slate-900 border border-slate-700 rounded-xl max-w-xl w-full p-6 text-slate-200 shadow-2xl flex flex-col space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-slate-800">
              <h2 className="text-base font-bold text-white flex items-center gap-2">
                <Satellite className="w-5 h-5 text-indigo-400" />
                <span>Model vs Sentinel-1 SAR Validation</span>
              </h2>
              <button onClick={() => setSatelliteModalOpen(false)} className="text-slate-400 hover:text-white">
                ✕
              </button>
            </div>

            {satelliteData.metrics ? (
              <div className="bg-slate-950 p-4 rounded-lg border border-slate-800 space-y-3 font-mono text-xs">
                <div className="text-slate-300 font-sans font-semibold">Quantitative Overlap Metrics:</div>
                <div className="grid grid-cols-4 gap-2 text-center">
                  <div className="bg-slate-900 p-2 rounded border border-slate-800">
                    <div className="text-[10px] text-slate-500">IoU (JACCARD)</div>
                    <div className="text-sm font-bold text-blue-400">
                      {typeof satelliteData.metrics.iou_jaccard === 'number' ? satelliteData.metrics.iou_jaccard.toFixed(3) : (satelliteData.metrics.iou_jaccard ?? 'N/A')}
                    </div>
                  </div>
                  <div className="bg-slate-900 p-2 rounded border border-slate-800">
                    <div className="text-[10px] text-slate-500">F1-SCORE</div>
                    <div className="text-sm font-bold text-emerald-400">
                      {typeof satelliteData.metrics.f1_score === 'number' ? satelliteData.metrics.f1_score.toFixed(3) : (satelliteData.metrics.f1_score ?? 'N/A')}
                    </div>
                  </div>
                  <div className="bg-slate-900 p-2 rounded border border-slate-800">
                    <div className="text-[10px] text-slate-500">PRECISION</div>
                    <div className="text-sm font-bold text-indigo-400">
                      {typeof satelliteData.metrics.precision === 'number' ? satelliteData.metrics.precision.toFixed(3) : (satelliteData.metrics.precision ?? 'N/A')}
                    </div>
                  </div>
                  <div className="bg-slate-900 p-2 rounded border border-slate-800">
                    <div className="text-[10px] text-slate-500">RECALL</div>
                    <div className="text-sm font-bold text-amber-400">
                      {typeof satelliteData.metrics.recall === 'number' ? satelliteData.metrics.recall.toFixed(3) : (satelliteData.metrics.recall ?? 'N/A')}
                    </div>
                  </div>
                </div>

                <div className="grid grid-cols-3 gap-2 text-center pt-2 border-t border-slate-800/80">
                  <div className="bg-slate-900/60 p-2 rounded border border-slate-800">
                    <div className="text-[10px] text-slate-500">MODEL AREA</div>
                    <div className="text-xs font-semibold text-slate-300">
                      {satelliteData.metrics.model_flooded_area_sqkm != null ? `${Number(satelliteData.metrics.model_flooded_area_sqkm).toFixed(2)} km²` : 'N/A'}
                    </div>
                  </div>
                  <div className="bg-slate-900/60 p-2 rounded border border-slate-800">
                    <div className="text-[10px] text-slate-500">SAR AREA</div>
                    <div className="text-xs font-semibold text-slate-300">
                      {satelliteData.metrics.satellite_flooded_area_sqkm != null ? `${Number(satelliteData.metrics.satellite_flooded_area_sqkm).toFixed(2)} km²` : 'N/A'}
                    </div>
                  </div>
                  <div className="bg-slate-900/60 p-2 rounded border border-slate-800">
                    <div className="text-[10px] text-slate-500">OVERLAP</div>
                    <div className="text-xs font-semibold text-cyan-300">
                      {satelliteData.metrics.overlap_area_sqkm != null ? `${Number(satelliteData.metrics.overlap_area_sqkm).toFixed(2)} km²` : 'N/A'}
                    </div>
                  </div>
                </div>

                {satelliteData.metrics.summary && (
                  <div className="text-slate-400 font-sans pt-2 leading-relaxed">
                    {satelliteData.metrics.summary}
                  </div>
                )}
                {satelliteData.metrics.spatial_notes && (
                  <div className="text-[11px] text-slate-500 font-sans italic pt-1 border-t border-slate-900">
                    {satelliteData.metrics.spatial_notes}
                  </div>
                )}
              </div>
            ) : (
              <div className="bg-slate-950 p-4 rounded-lg border border-slate-800 space-y-3 font-sans text-xs">
                <div className="text-amber-400 font-semibold flex items-center gap-1.5">
                  <AlertTriangle className="w-4 h-4 text-amber-400" />
                  <span>Observation Alignment Notice</span>
                </div>
                <p className="text-slate-300 leading-relaxed">
                  {satelliteData.message || 'Satellite SAR observations for this specific flood time-window are currently awaiting cloud API credentials or local baseline SAR footprints.'}
                </p>
                <div className="text-[11px] text-slate-400 border-t border-slate-800 pt-2 font-mono">
                  Sensor Target: {satelliteData.sensor || 'Sentinel-1 C-Band SAR (IW, VV+VH)'}
                </div>
              </div>
            )}

            <div className="flex justify-end">
              <button
                onClick={() => setSatelliteModalOpen(false)}
                className="px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-xs font-semibold text-white transition"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
