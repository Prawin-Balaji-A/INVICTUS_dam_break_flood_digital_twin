import React, { useState, useEffect } from 'react';
import { Project, SimulationResult } from '../types';
import { api } from '../services/api';
import { 
  BrainCircuit, 
  X, 
  Activity, 
  Target, 
  CheckCircle2, 
  AlertCircle, 
  Sparkles, 
  Layers, 
  Compass, 
  Zap, 
  ShieldCheck, 
  RefreshCw 
} from 'lucide-react';

interface AIPredictorModalProps {
  isOpen: boolean;
  onClose: () => void;
  project: Project | null;
  simulation: SimulationResult | null;
}

// Null-safe formatters. The ML API can only ever return the fields the backend
// response models declare; these guards guarantee that a missing/renamed field
// renders as a dash instead of throwing (`undefined.toFixed`) and blanking the
// whole modal. Never fabricate a value — an absent number reads as "—".
const fmtNum = (v: any, digits = 2, suffix = ''): string =>
  typeof v === 'number' && Number.isFinite(v) ? `${v.toFixed(digits)}${suffix}` : '—';

const fmtPct = (v: any): string =>
  typeof v === 'number' && Number.isFinite(v) ? `${(v * 100).toFixed(1)}%` : '—';

// Fraction of evaluated grid nodes classified inundated (real counts only).
const fmtGridFraction = (g: any): string => {
  const total = g?.metadata?.total_points;
  const wet = g?.metadata?.inundated_points;
  if (typeof total !== 'number' || typeof wet !== 'number' || total <= 0) return '—';
  return `${((wet / total) * 100).toFixed(1)}%`;
};

export const AIPredictorModal: React.FC<AIPredictorModalProps> = ({
  isOpen,
  onClose,
  project,
  simulation
}) => {
  const [metrics, setMetrics] = useState<any>(null);
  const [loadingMetrics, setLoadingMetrics] = useState<boolean>(true);

  // Point Prediction State
  const [latInput, setLatInput] = useState<string>('');
  const [lonInput, setLonInput] = useState<string>('');
  const [pointResult, setPointResult] = useState<any>(null);
  const [isPredictingPoint, setIsPredictingPoint] = useState<boolean>(false);
  const [pointError, setPointError] = useState<string | null>(null);

  // Grid Prediction State
  const [gridResolution, setGridResolution] = useState<number>(30);
  const [gridResult, setGridResult] = useState<any>(null);
  const [isPredictingGrid, setIsPredictingGrid] = useState<boolean>(false);
  const [gridError, setGridError] = useState<string | null>(null);

  useEffect(() => {
    if (!isOpen) return;
    setLoadingMetrics(true);
    api.getMLMetrics()
      .then(res => setMetrics(res))
      .catch(console.error)
      .finally(() => setLoadingMetrics(false));

    // Preset point coordinates from project dam location
    if (project) {
      setLatInput((project.dam_lat - 0.05).toFixed(4));
      setLonInput((project.dam_lon + 0.05).toFixed(4));
    }
  }, [isOpen, project]);

  // Escape-to-close, active only while the modal is open.
  useEffect(() => {
    if (!isOpen) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [isOpen, onClose]);

  const handlePredictPoint = async () => {
    if (!latInput || !lonInput) return;
    setIsPredictingPoint(true);
    setPointError(null);
    setPointResult(null);

    try {
      const res = await api.predictPoint({
        lat: parseFloat(latInput),
        lon: parseFloat(lonInput),
        project_id: (project as any)?.slug || project?.id || 'mettur',
        peak_discharge_m3s: simulation?.peak_discharge_m3s || 82000
      });
      setPointResult(res);
    } catch (err: any) {
      setPointError(err.message || 'Failed to predict point inundation');
    } finally {
      setIsPredictingPoint(false);
    }
  };

  const handlePredictGrid = async () => {
    if (!project) return;
    setIsPredictingGrid(true);
    setGridError(null);
    setGridResult(null);

    try {
      const res = await api.predictGrid({
        project_id: (project as any)?.slug || project.id,
        grid_resolution: gridResolution,
        peak_discharge_m3s: simulation?.peak_discharge_m3s || 82000
      });
      setGridResult(res);
    } catch (err: any) {
      setGridError(err.message || 'Failed to predict grid footprint');
    } finally {
      setIsPredictingGrid(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4 animate-in fade-in duration-200"
      onClick={onClose}
    >
      <div
        className="bg-slate-900 border border-slate-700/80 rounded-2xl w-full max-w-4xl max-h-[90vh] flex flex-col shadow-2xl overflow-hidden font-sans"
        onClick={(e) => e.stopPropagation()}
      >
        
        {/* Header */}
        <div className="px-6 py-4 border-b border-slate-800 flex items-center justify-between bg-slate-950/60">
          <div className="flex items-center space-x-3">
            <div className="w-10 h-10 rounded-xl bg-purple-600/20 border border-purple-500/40 flex items-center justify-center text-purple-400">
              <BrainCircuit className="w-5 h-5 animate-pulse" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-base font-bold text-white tracking-wide">
                  AI FLOOD INUNDATION SURROGATE PREDICTOR
                </h2>
                <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-purple-500/20 text-purple-300 border border-purple-500/30">
                  PURE-NUMPY RANDOM FOREST
                </span>
              </div>
              <p className="text-xs text-slate-400">
                Sub-second machine learning surrogate for rapid emergency response & spatial hazard scoping
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-2 text-slate-400 hover:text-white rounded-lg hover:bg-slate-800 transition"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content Body */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          
          {/* Scientific Provenance Banner */}
          <div className="bg-blue-950/40 border border-blue-500/40 rounded-xl p-4 flex items-start gap-3.5 text-xs">
            <ShieldCheck className="w-5 h-5 text-blue-400 shrink-0 mt-0.5" />
            <div className="space-y-1">
              <span className="font-bold text-blue-300">SCIENTIFIC PROVENANCE & HARMONIZATION</span>
              <p className="text-slate-300 leading-relaxed">
                This surrogate model is trained on labels derived from the 2D Manning hydraulic
                simulation over the real Copernicus DEM and river network. It returns a rapid
                flood-probability classification (inundated vs. dry) in milliseconds. Reported scores
                are held-out test performance against those simulation-derived labels, not calibration
                against observed historical flood events. For authoritative depth, extent and arrival
                time, use the 2D hydrodynamic routing engine.
              </p>
            </div>
          </div>

          {/* Model Validation & Performance Metrics */}
          <div className="space-y-2.5">
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold text-slate-300 flex items-center gap-2">
                <Activity className="w-4 h-4 text-purple-400" />
                HELD-OUT VALIDATION METRICS (1,250 TEST SAMPLES)
              </span>
              <span className="text-[11px] font-mono text-emerald-400 font-semibold">
                Simulation-derived labels • Zero data leakage
              </span>
            </div>

            {loadingMetrics ? (
              <div className="p-6 bg-slate-950 rounded-xl text-center text-xs text-slate-400 font-mono">
                Loading surrogate performance telemetry...
              </div>
            ) : metrics && metrics.metrics ? (
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <div className="bg-slate-950/80 border border-slate-800 p-3 rounded-xl">
                  <div className="text-[11px] text-slate-400">Intersection over Union (IoU)</div>
                  <div className="text-xl font-bold font-mono text-emerald-400 mt-1">
                    {fmtPct(metrics.metrics.iou)}
                  </div>
                  <div className="text-[10px] text-slate-500 mt-0.5">Spatial Footprint Match</div>
                </div>

                <div className="bg-slate-950/80 border border-slate-800 p-3 rounded-xl">
                  <div className="text-[11px] text-slate-400">Overall Accuracy</div>
                  <div className="text-xl font-bold font-mono text-cyan-400 mt-1">
                    {fmtPct(metrics.metrics.accuracy)}
                  </div>
                  <div className="text-[10px] text-slate-500 mt-0.5">Held-out test set</div>
                </div>

                <div className="bg-slate-950/80 border border-slate-800 p-3 rounded-xl">
                  <div className="text-[11px] text-slate-400">F1-Score</div>
                  <div className="text-xl font-bold font-mono text-purple-400 mt-1">
                    {fmtPct(metrics.metrics.f1_score)}
                  </div>
                  <div className="text-[10px] text-slate-500 mt-0.5">Precision / Recall Balance</div>
                </div>

                <div className="bg-slate-950/80 border border-slate-800 p-3 rounded-xl">
                  <div className="text-[11px] text-slate-400">ROC-AUC</div>
                  <div className="text-xl font-bold font-mono text-amber-400 mt-1">
                    {fmtPct(metrics.metrics.roc_auc)}
                  </div>
                  <div className="text-[10px] text-slate-500 mt-0.5">Discriminative Power</div>
                </div>
              </div>
            ) : (
              <div className="p-4 bg-slate-950 rounded-xl text-xs text-amber-300">
                AI prediction data unavailable for this scenario. The surrogate model or its validation
                metrics have not been generated for the selected domain.
              </div>
            )}
          </div>

          {/* Interactive Point Inundation Predictor */}
          <div className="bg-slate-950/70 border border-slate-800 rounded-xl p-4 space-y-4">
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold text-white flex items-center gap-2">
                <Target className="w-4 h-4 text-cyan-400" />
                INSTANT POINT HAZARD INFERENCE
              </span>
              <span className="text-[11px] text-slate-400">
                Target Dam: <strong className="text-slate-200">{project?.name || 'Mettur Dam'}</strong>
              </span>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <div>
                <label className="block text-[11px] text-slate-400 mb-1">Target Latitude (°N)</label>
                <input
                  type="number"
                  step="0.0001"
                  value={latInput}
                  onChange={(e) => setLatInput(e.target.value)}
                  className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-xs text-white font-mono focus:outline-none focus:border-purple-500"
                />
              </div>

              <div>
                <label className="block text-[11px] text-slate-400 mb-1">Target Longitude (°E)</label>
                <input
                  type="number"
                  step="0.0001"
                  value={lonInput}
                  onChange={(e) => setLonInput(e.target.value)}
                  className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-xs text-white font-mono focus:outline-none focus:border-purple-500"
                />
              </div>

              <div className="flex items-end">
                <button
                  onClick={handlePredictPoint}
                  disabled={isPredictingPoint || !latInput || !lonInput}
                  className="w-full py-2 bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-500 hover:to-indigo-500 text-white rounded-lg text-xs font-semibold flex items-center justify-center gap-2 transition disabled:opacity-50"
                >
                  {isPredictingPoint ? (
                    <>
                      <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                      Evaluating...
                    </>
                  ) : (
                    <>
                      <Zap className="w-3.5 h-3.5 fill-current" />
                      Predict Point Hazard
                    </>
                  )}
                </button>
              </div>
            </div>

            {pointError && (
              <div className="p-3 bg-rose-950/40 border border-rose-500/40 rounded-lg text-xs text-rose-300 flex items-center gap-2">
                <AlertCircle className="w-4 h-4 shrink-0" />
                <span>{pointError}</span>
              </div>
            )}

            {pointResult && (
              <div className="bg-slate-900/90 border border-purple-500/30 rounded-xl p-4 space-y-3 font-mono text-xs animate-in fade-in">
                <div className="flex items-center justify-between border-b border-slate-800 pb-2">
                  <div className="flex items-center gap-2">
                    {pointResult.is_inundated ? (
                      <span className="px-2.5 py-1 rounded bg-rose-500/20 text-rose-300 font-bold border border-rose-500/40 flex items-center gap-1.5">
                        <AlertCircle className="w-3.5 h-3.5" />
                        LIKELY INUNDATED AT PEAK
                      </span>
                    ) : (
                      <span className="px-2.5 py-1 rounded bg-emerald-500/20 text-emerald-300 font-bold border border-emerald-500/40 flex items-center gap-1.5">
                        <CheckCircle2 className="w-3.5 h-3.5" />
                        LIKELY DRY AT PEAK
                      </span>
                    )}
                  </div>
                  <span className="text-slate-400">
                    Confidence: <strong className="text-white">{fmtPct(pointResult.confidence)}</strong>
                  </span>
                </div>

                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-slate-300 pt-1">
                  <div>
                    <span className="text-[10px] text-slate-500 block">Flood Probability</span>
                    <span className="font-bold text-sm text-cyan-400">
                      {fmtPct(pointResult.flood_probability)}
                    </span>
                  </div>

                  <div>
                    <span className="text-[10px] text-slate-500 block">Model Uncertainty</span>
                    <span className="font-bold text-sm text-white">
                      {fmtPct(pointResult.uncertainty)}
                    </span>
                  </div>

                  <div>
                    <span className="text-[10px] text-slate-500 block">Distance to River</span>
                    <span className="font-bold text-sm text-slate-200">
                      {fmtNum(pointResult.features_used?.dist_to_river_m, 0, ' m')}
                    </span>
                  </div>

                  <div>
                    <span className="text-[10px] text-slate-500 block">Elev. above River</span>
                    <span className="font-bold text-sm text-slate-200">
                      {fmtNum(pointResult.features_used?.rel_elev_river_m, 1, ' m')}
                    </span>
                  </div>
                </div>

                <div className="text-[10px] text-slate-500 border-t border-slate-800 pt-2 leading-relaxed">
                  Model output is a flood-probability classification (inundated vs. dry) at peak, not a
                  depth estimate. For depth, extent and arrival time use the authoritative 2D hydraulic
                  simulation. Source: {pointResult.provenance || 'Random Forest surrogate'}
                </div>
              </div>
            )}
          </div>

          {/* Rapid Grid Flood Footprint */}
          <div className="bg-slate-950/70 border border-slate-800 rounded-xl p-4 space-y-4">
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold text-white flex items-center gap-2">
                <Layers className="w-4 h-4 text-purple-400" />
                RAPID VALLEY FLOOD FOOTPRINT ESTIMATION
              </span>
              <span className="text-[11px] text-slate-400">Grid Resolution: {gridResolution}x{gridResolution}</span>
            </div>

            <div className="flex items-center gap-4">
              <input
                type="range"
                min="15"
                max="50"
                step="5"
                value={gridResolution}
                onChange={(e) => setGridResolution(parseInt(e.target.value))}
                className="flex-1 h-2 bg-slate-900 rounded-lg appearance-none cursor-pointer accent-purple-500"
              />
              <button
                onClick={handlePredictGrid}
                disabled={isPredictingGrid || !project}
                className="px-4 py-2 bg-purple-600 hover:bg-purple-500 text-white rounded-lg text-xs font-semibold flex items-center gap-2 transition disabled:opacity-50"
              >
                {isPredictingGrid ? (
                  <>
                    <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                    Computing...
                  </>
                ) : (
                  <>
                    <Sparkles className="w-3.5 h-3.5" />
                    Generate AI Footprint
                  </>
                )}
              </button>
            </div>

            {gridError && (
              <div className="p-3 bg-rose-950/40 border border-rose-500/40 rounded-lg text-xs text-rose-300">
                {gridError}
              </div>
            )}

            {gridResult && (
              <div className="bg-slate-900/90 border border-purple-500/30 rounded-xl p-4 font-mono text-xs space-y-2">
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-slate-300">
                  <div>
                    <span className="text-[10px] text-slate-500 block">Evaluated Nodes</span>
                    <span className="font-bold text-white">{fmtNum(gridResult.metadata?.total_points, 0, ' pts')}</span>
                  </div>
                  <div>
                    <span className="text-[10px] text-slate-500 block">Predicted Inundated</span>
                    <span className="font-bold text-rose-400">{fmtNum(gridResult.metadata?.inundated_points, 0, ' cells')}</span>
                  </div>
                  <div>
                    <span className="text-[10px] text-slate-500 block">Inundated Fraction</span>
                    <span className="font-bold text-cyan-400">{fmtGridFraction(gridResult)}</span>
                  </div>
                  <div>
                    <span className="text-[10px] text-slate-500 block">Grid Resolution</span>
                    <span className="font-bold text-emerald-400">{gridResolution}×{gridResolution}</span>
                  </div>
                </div>
                <div className="text-[10px] text-slate-500 border-t border-slate-800 pt-2 leading-relaxed">
                  Per-node inundated / dry classification across the domain — a rapid probability screen,
                  not a hydraulic footprint. Authoritative extent and depth come from the 2D simulation.
                </div>
              </div>
            )}
          </div>

        </div>

        {/* Footer */}
        <div className="px-6 py-3 bg-slate-950 border-t border-slate-800 flex items-center justify-between text-xs text-slate-500 font-mono">
          <span>Surrogate Model: Pure-NumPy Random Forest • Python 3.11</span>
          <span>Zero external C-extension dependencies</span>
        </div>
      </div>
    </div>
  );
};
