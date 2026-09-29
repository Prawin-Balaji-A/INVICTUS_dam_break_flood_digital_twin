import React, { useState, useEffect } from 'react';
import { 
  GitCompare, 
  X, 
  Layers, 
  Activity, 
  Timer, 
  TrendingUp, 
  Info,
  Waves,
  Cpu
} from 'lucide-react';
import { Project, SimulationResult } from '../types';
import { api } from '../services/api';

interface SPHDelft3DCompareModalProps {
  isOpen: boolean;
  onClose: () => void;
  project: Project | null;
  simulation: SimulationResult | null;
}

export const SPHDelft3DCompareModal: React.FC<SPHDelft3DCompareModalProps> = ({
  isOpen,
  onClose,
  project,
  simulation
}) => {
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<any>(null);
  const [activeTab, setActiveTab] = useState<'overview' | 'stations' | 'hydrograph' | 'cross_sections'>('overview');

  useEffect(() => {
    if (!isOpen) return;
    const targetRef = simulation?.id || project?.id;
    if (!targetRef) return;

    setLoading(true);
    const isProject = !simulation?.id;
    api.getSPHDelft3DComparison(targetRef, isProject)
      .then(res => setData(res))
      .catch(err => {
        console.error('Failed to load SPH vs Delft3D comparison:', err);
      })
      .finally(() => setLoading(false));
  }, [isOpen, simulation?.id, project?.id]);

  if (!isOpen) return null;

  const sphModel = data?.models_compared?.find((m: any) => m.model_id === 'SPH');
  const d3dModel = data?.models_compared?.find((m: any) => m.model_id === 'DELFT3D');
  const metrics = data?.correlation_metrics;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-sm p-3 md:p-6 overflow-hidden">
      <div className="bg-slate-900 border border-slate-700/80 rounded-2xl max-w-5xl w-full max-h-[92vh] flex flex-col text-slate-200 shadow-2xl overflow-hidden animate-in fade-in zoom-in-95 duration-200">
        
        {/* Header */}
        <div className="px-6 py-4 bg-slate-950/80 border-b border-slate-800 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-indigo-500/20 border border-indigo-500/40 flex items-center justify-center text-indigo-400">
              <GitCompare className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-base font-bold text-white tracking-wide">
                  Hydrodynamic Model Comparison: SPH vs Delft3D-FLOW
                </h2>
                <span className="text-[10px] px-2 py-0.5 rounded bg-indigo-500/20 text-indigo-300 font-mono border border-indigo-500/30">
                  HADR BENCHMARK
                </span>
              </div>
              <p className="text-xs text-slate-400 mt-0.5">
                {project ? `${project.dam_name} • ${project.river_name}` : 'Rigorous Multi-Model Hydraulic Verification'}
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

        {/* Tab Navigation */}
        <div className="flex items-center px-6 bg-slate-950/50 border-b border-slate-800/80 gap-2 overflow-x-auto text-xs font-medium">
          <button
            onClick={() => setActiveTab('overview')}
            className={`py-2.5 px-3 border-b-2 transition flex items-center gap-1.5 ${
              activeTab === 'overview'
                ? 'border-indigo-500 text-indigo-300 font-semibold'
                : 'border-transparent text-slate-400 hover:text-slate-200'
            }`}
          >
            <Layers className="w-3.5 h-3.5" />
            <span>Architecture & Metrics</span>
          </button>

          <button
            onClick={() => setActiveTab('stations')}
            className={`py-2.5 px-3 border-b-2 transition flex items-center gap-1.5 ${
              activeTab === 'stations'
                ? 'border-indigo-500 text-indigo-300 font-semibold'
                : 'border-transparent text-slate-400 hover:text-slate-200'
            }`}
          >
            <Timer className="w-3.5 h-3.5" />
            <span>Downstream Arrival Stations</span>
          </button>

          <button
            onClick={() => setActiveTab('hydrograph')}
            className={`py-2.5 px-3 border-b-2 transition flex items-center gap-1.5 ${
              activeTab === 'hydrograph'
                ? 'border-indigo-500 text-indigo-300 font-semibold'
                : 'border-transparent text-slate-400 hover:text-slate-200'
            }`}
          >
            <TrendingUp className="w-3.5 h-3.5" />
            <span>Discharge Hydrographs Q(t)</span>
          </button>

          <button
            onClick={() => setActiveTab('cross_sections')}
            className={`py-2.5 px-3 border-b-2 transition flex items-center gap-1.5 ${
              activeTab === 'cross_sections'
                ? 'border-indigo-500 text-indigo-300 font-semibold'
                : 'border-transparent text-slate-400 hover:text-slate-200'
            }`}
          >
            <Activity className="w-3.5 h-3.5" />
            <span>Cross-Section Profiles</span>
          </button>
        </div>

        {/* Content Body */}
        <div className="p-6 overflow-y-auto flex-1 space-y-6">
          {loading ? (
            <div className="py-16 text-center text-slate-400 text-sm flex flex-col items-center justify-center gap-3">
              <div className="w-8 h-8 rounded-full border-2 border-indigo-500 border-t-transparent animate-spin" />
              <span>Synthesizing multi-model hydrodynamic comparison...</span>
            </div>
          ) : !data ? (
            <div className="py-12 text-center text-slate-400 text-xs">
              No comparison metrics available. Select a dam project with scenario data.
            </div>
          ) : (
            <>
              {/* Correlation Summary KPI Bar */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <div className="bg-slate-950/70 p-3.5 rounded-xl border border-slate-800">
                  <div className="text-[11px] text-slate-400 uppercase tracking-wider font-semibold">Spatial Agreement</div>
                  <div className="text-xl font-bold text-emerald-400 font-mono mt-0.5">
                    {metrics?.spatial_overlap_iou_pct}% <span className="text-xs text-slate-400 font-normal">IoU</span>
                  </div>
                  <div className="text-[10px] text-slate-500 mt-1">Flood footprint overlap</div>
                </div>

                <div className="bg-slate-950/70 p-3.5 rounded-xl border border-slate-800">
                  <div className="text-[11px] text-slate-400 uppercase tracking-wider font-semibold">Peak Discharge Δ</div>
                  <div className="text-xl font-bold text-amber-400 font-mono mt-0.5">
                    {metrics?.peak_discharge_relative_diff_pct}%
                  </div>
                  <div className="text-[10px] text-slate-500 mt-1">SPH higher in near-plunge pool</div>
                </div>

                <div className="bg-slate-950/70 p-3.5 rounded-xl border border-slate-800">
                  <div className="text-[11px] text-slate-400 uppercase tracking-wider font-semibold">Arrival Time MAE</div>
                  <div className="text-xl font-bold text-cyan-400 font-mono mt-0.5">
                    {metrics?.arrival_time_mae_min} <span className="text-xs text-slate-400 font-normal">min</span>
                  </div>
                  <div className="text-[10px] text-slate-500 mt-1">Mean absolute wavefront error</div>
                </div>

                <div className="bg-slate-950/70 p-3.5 rounded-xl border border-slate-800">
                  <div className="text-[11px] text-slate-400 uppercase tracking-wider font-semibold">Nash-Sutcliffe (NSE)</div>
                  <div className="text-xl font-bold text-purple-400 font-mono mt-0.5">
                    {metrics?.depth_nash_sutcliffe_efficiency}
                  </div>
                  <div className="text-[10px] text-slate-500 mt-1">Depth hydrograph correlation</div>
                </div>
              </div>

              {/* TAB 1: OVERVIEW & ARCHITECTURE */}
              {activeTab === 'overview' && (
                <div className="space-y-6">
                  {/* Side-by-side Model Cards */}
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {/* SPH Card */}
                    <div className="bg-gradient-to-b from-blue-950/30 to-slate-950/70 border border-blue-500/30 rounded-xl p-4 space-y-3">
                      <div className="flex items-center justify-between border-b border-blue-500/20 pb-2.5">
                        <div className="flex items-center gap-2">
                          <Waves className="w-4 h-4 text-blue-400" />
                          <div className="font-bold text-sm text-white">SPH (Smooth Particle Hydrodynamics)</div>
                        </div>
                        <span className="text-[10px] px-2 py-0.5 rounded bg-blue-500/20 text-blue-300 font-mono">
                          LAGRANGIAN 3D
                        </span>
                      </div>

                      <div className="grid grid-cols-2 gap-2 text-xs font-mono">
                        <div>
                          <div className="text-slate-400 text-[10px] font-sans">Discretization</div>
                          <div className="text-slate-200 font-semibold">{sphModel?.discretization}</div>
                        </div>
                        <div>
                          <div className="text-slate-400 text-[10px] font-sans">Peak Outflow Q</div>
                          <div className="text-blue-400 font-bold">{sphModel?.peak_discharge_m3s?.toLocaleString()} m³/s</div>
                        </div>
                        <div>
                          <div className="text-slate-400 text-[10px] font-sans">Max Plunge Depth</div>
                          <div className="text-slate-200 font-semibold">{sphModel?.max_depth_m} m</div>
                        </div>
                        <div>
                          <div className="text-slate-400 text-[10px] font-sans">Inundated Area</div>
                          <div className="text-slate-200 font-semibold">{sphModel?.inundated_area_km2} km²</div>
                        </div>
                        <div>
                          <div className="text-slate-400 text-[10px] font-sans">Compute Runtime</div>
                          <div className="text-slate-200 font-semibold">{sphModel?.runtime_sec} s</div>
                        </div>
                        <div>
                          <div className="text-slate-400 text-[10px] font-sans">Mass Balance Error</div>
                          <div className="text-emerald-400 font-semibold">{sphModel?.mass_balance_error_pct}%</div>
                        </div>
                      </div>

                      <div className="pt-2 border-t border-slate-800 text-[11px] space-y-1">
                        <div className="text-slate-300 font-semibold">Key Physical Strengths:</div>
                        {sphModel?.strengths?.map((s: string, idx: number) => (
                          <div key={idx} className="text-slate-400 flex items-start gap-1.5">
                            <span className="text-blue-400">•</span>
                            <span>{s}</span>
                          </div>
                        ))}
                      </div>
                    </div>

                    {/* Delft3D Card */}
                    <div className="bg-gradient-to-b from-teal-950/30 to-slate-950/70 border border-teal-500/30 rounded-xl p-4 space-y-3">
                      <div className="flex items-center justify-between border-b border-teal-500/20 pb-2.5">
                        <div className="flex items-center gap-2">
                          <Cpu className="w-4 h-4 text-teal-400" />
                          <div className="font-bold text-sm text-white">Delft3D-FLOW (Deltares Suite)</div>
                        </div>
                        <span className="text-[10px] px-2 py-0.5 rounded bg-teal-500/20 text-teal-300 font-mono">
                          EULERIAN 2D/3D
                        </span>
                      </div>

                      <div className="grid grid-cols-2 gap-2 text-xs font-mono">
                        <div>
                          <div className="text-slate-400 text-[10px] font-sans">Discretization</div>
                          <div className="text-slate-200 font-semibold">{d3dModel?.discretization}</div>
                        </div>
                        <div>
                          <div className="text-slate-400 text-[10px] font-sans">Peak Outflow Q</div>
                          <div className="text-teal-400 font-bold">{d3dModel?.peak_discharge_m3s?.toLocaleString()} m³/s</div>
                        </div>
                        <div>
                          <div className="text-slate-400 text-[10px] font-sans">Max Plunge Depth</div>
                          <div className="text-slate-200 font-semibold">{d3dModel?.max_depth_m} m</div>
                        </div>
                        <div>
                          <div className="text-slate-400 text-[10px] font-sans">Inundated Area</div>
                          <div className="text-slate-200 font-semibold">{d3dModel?.inundated_area_km2} km²</div>
                        </div>
                        <div>
                          <div className="text-slate-400 text-[10px] font-sans">Compute Runtime</div>
                          <div className="text-slate-200 font-semibold">{d3dModel?.runtime_sec} s</div>
                        </div>
                        <div>
                          <div className="text-slate-400 text-[10px] font-sans">Mass Balance Error</div>
                          <div className="text-emerald-400 font-semibold">{d3dModel?.mass_balance_error_pct}%</div>
                        </div>
                      </div>

                      <div className="pt-2 border-t border-slate-800 text-[11px] space-y-1">
                        <div className="text-slate-300 font-semibold">Key Physical Strengths:</div>
                        {d3dModel?.strengths?.map((s: string, idx: number) => (
                          <div key={idx} className="text-slate-400 flex items-start gap-1.5">
                            <span className="text-teal-400">•</span>
                            <span>{s}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>

                  {/* Scientific Synthesis Banner */}
                  <div className="bg-slate-950/80 p-4 rounded-xl border border-slate-800 text-xs text-slate-300 leading-relaxed flex items-start gap-3">
                    <Info className="w-5 h-5 text-indigo-400 shrink-0 mt-0.5" />
                    <div>
                      <div className="font-semibold text-white mb-1">HADR Operational Deployment Recommendation:</div>
                      {data?.scientific_synthesis}
                    </div>
                  </div>
                </div>
              )}

              {/* TAB 2: DOWNSTREAM ARRIVAL STATIONS */}
              {activeTab === 'stations' && (
                <div className="space-y-4">
                  <div className="text-xs text-slate-400">
                    Comparative flood arrival time and peak stage progression along key downstream chainage checkpoints.
                  </div>
                  <div className="overflow-x-auto rounded-xl border border-slate-800">
                    <table className="w-full text-xs text-left border-collapse">
                      <thead>
                        <tr className="bg-slate-950 text-slate-400 font-semibold border-b border-slate-800">
                          <th className="p-3">Station / Checkpoint</th>
                          <th className="p-3">Chainage</th>
                          <th className="p-3 text-blue-400">SPH Arrival</th>
                          <th className="p-3 text-teal-400">Delft3D Arrival</th>
                          <th className="p-3 text-blue-400">SPH Depth</th>
                          <th className="p-3 text-teal-400">Delft3D Depth</th>
                          <th className="p-3">Regime / Froude</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-800/60 font-mono">
                        {data?.stations?.map((st: any, i: number) => (
                          <tr key={i} className="hover:bg-slate-850/50">
                            <td className="p-3 font-sans font-medium text-white">{st.name}</td>
                            <td className="p-3 text-slate-300">{st.chainage_km} km</td>
                            <td className="p-3 text-blue-300 font-bold">{st.sph_arrival_min} min</td>
                            <td className="p-3 text-teal-300 font-bold">{st.delft3d_arrival_min} min</td>
                            <td className="p-3 text-blue-300">{st.sph_peak_depth_m} m</td>
                            <td className="p-3 text-teal-300">{st.delft3d_peak_depth_m} m</td>
                            <td className="p-3 font-sans text-[11px] text-slate-400">
                              <span className="px-1.5 py-0.5 rounded bg-slate-800 text-slate-300 mr-1.5 font-mono">
                                Fr: {st.froude_sph}
                              </span>
                              {st.dominant_regime}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* TAB 3: HYDROGRAPH COMPARISON Q(t) */}
              {activeTab === 'hydrograph' && (
                <div className="space-y-4">
                  <div className="flex items-center justify-between text-xs text-slate-400">
                    <div>Outflow Discharge Hydrographs Q(t) at Breach Section (m³/s vs Time)</div>
                    <div className="flex items-center gap-4 text-[11px] font-mono">
                      <span className="flex items-center gap-1.5 text-blue-400">
                        <span className="w-3 h-0.5 bg-blue-400 inline-block" /> SPH Lagrangian
                      </span>
                      <span className="flex items-center gap-1.5 text-teal-400">
                        <span className="w-3 h-0.5 bg-teal-400 inline-block" /> Delft3D-FLOW
                      </span>
                    </div>
                  </div>

                  {/* SVG Chart */}
                  <div className="bg-slate-950 p-4 rounded-xl border border-slate-800 h-64 flex flex-col justify-end relative">
                    <svg viewBox="0 0 600 200" className="w-full h-full overflow-visible">
                      {/* Grid lines */}
                      <line x1="40" y1="20" x2="580" y2="20" stroke="#334155" strokeDasharray="3 3" />
                      <line x1="40" y1="80" x2="580" y2="80" stroke="#334155" strokeDasharray="3 3" />
                      <line x1="40" y1="140" x2="580" y2="140" stroke="#334155" strokeDasharray="3 3" />
                      <line x1="40" y1="180" x2="580" y2="180" stroke="#475569" />

                      {/* Points mapping */}
                      {(() => {
                        const pts = data?.hydrograph_comparison || [];
                        if (pts.length === 0) return null;
                        const maxQ = Math.max(...pts.map((p: any) => p.sph_discharge_m3s), 1000);
                        const maxT = Math.max(...pts.map((p: any) => p.time_min), 60);

                        const toX = (t: number) => 40 + (t / maxT) * 540;
                        const toY = (q: number) => 180 - (q / maxQ) * 160;

                        const sphPath = pts.map((p: any, idx: number) => 
                          `${idx === 0 ? 'M' : 'L'} ${toX(p.time_min)} ${toY(p.sph_discharge_m3s)}`
                        ).join(' ');

                        const d3dPath = pts.map((p: any, idx: number) => 
                          `${idx === 0 ? 'M' : 'L'} ${toX(p.time_min)} ${toY(p.delft3d_discharge_m3s)}`
                        ).join(' ');

                        return (
                          <>
                            {/* Delft3D Path */}
                            <path d={d3dPath} fill="none" stroke="#2dd4bf" strokeWidth="2.5" />
                            {/* SPH Path */}
                            <path d={sphPath} fill="none" stroke="#60a5fa" strokeWidth="2.5" strokeDasharray="4 2" />

                            {/* Labels */}
                            <text x="35" y="25" fill="#94a3b8" fontSize="10" textAnchor="end">{Math.round(maxQ).toLocaleString()}</text>
                            <text x="35" y="105" fill="#94a3b8" fontSize="10" textAnchor="end">{Math.round(maxQ/2).toLocaleString()}</text>
                            <text x="35" y="185" fill="#94a3b8" fontSize="10" textAnchor="end">0</text>

                            <text x="40" y="195" fill="#94a3b8" fontSize="10">0m</text>
                            <text x="310" y="195" fill="#94a3b8" fontSize="10">{Math.round(maxT/2)}m</text>
                            <text x="580" y="195" fill="#94a3b8" fontSize="10" textAnchor="end">{Math.round(maxT)}m</text>
                          </>
                        );
                      })()}
                    </svg>
                  </div>

                  <div className="text-[11px] text-slate-500 font-mono text-center">
                    Time (minutes) vs Instantaneous Breach Discharge Q (m³/s)
                  </div>
                </div>
              )}

              {/* TAB 4: CROSS-SECTIONS */}
              {activeTab === 'cross_sections' && (
                <div className="space-y-4">
                  <div className="text-xs text-slate-400">
                    Transverse water surface elevations and bed bathymetry across critical downstream canyon and valley transects.
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    {data?.cross_sections?.map((cs: any, idx: number) => (
                      <div key={idx} className="bg-slate-950 p-4 rounded-xl border border-slate-800 space-y-3">
                        <div className="font-semibold text-xs text-white border-b border-slate-800 pb-1.5">
                          {cs.label}
                        </div>
                        <div className="h-36 flex items-center justify-center">
                          <svg viewBox="0 0 200 120" className="w-full h-full">
                            {/* Bed line */}
                            <path
                              d={`M 10 30 Q 100 100 190 30`}
                              fill="none"
                              stroke="#64748b"
                              strokeWidth="2.5"
                            />
                            {/* Delft3D water surface */}
                            <line x1="35" y1="48" x2="165" y2="48" stroke="#2dd4bf" strokeWidth="2" strokeDasharray="3 3" />
                            {/* SPH water surface (higher free-surface crest) */}
                            <path d="M 30 45 Q 100 42 170 45" fill="none" stroke="#60a5fa" strokeWidth="2" />
                            {/* Legend */}
                            <text x="100" y="112" fill="#94a3b8" fontSize="8" textAnchor="middle">Transverse Width (m)</text>
                          </svg>
                        </div>
                        <div className="grid grid-cols-2 gap-2 text-[11px] font-mono pt-2 border-t border-slate-800">
                          <div>
                            <span className="text-blue-400 font-semibold">SPH Depth: </span>
                            <span>{cs.sph_depth_m} m</span>
                          </div>
                          <div>
                            <span className="text-teal-400 font-semibold">Delft3D: </span>
                            <span>{cs.delft3d_depth_m} m</span>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-3.5 bg-slate-950 border-t border-slate-800 flex items-center justify-between">
          <div className="text-[11px] text-slate-500 font-mono">
            Coupled Model Framework • SPH Lagrangian + Delft3D-FLOW Eulerian
          </div>
          <button
            onClick={onClose}
            className="px-4 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-xs font-medium text-slate-200 transition"
          >
            Close Comparison
          </button>
        </div>

      </div>
    </div>
  );
};
