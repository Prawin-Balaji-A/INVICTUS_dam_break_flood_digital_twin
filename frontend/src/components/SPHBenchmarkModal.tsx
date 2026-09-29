import React, { useState } from 'react';
import { BenchmarkStatus } from '../types';
import { api } from '../services/api';
import { X, Play, CheckCircle2, AlertTriangle } from 'lucide-react';

interface SPHBenchmarkModalProps {
  isOpen: boolean;
  onClose: () => void;
  status: BenchmarkStatus | null;
  onUpdateStatus: (s: BenchmarkStatus) => void;
}

export const SPHBenchmarkModal: React.FC<SPHBenchmarkModalProps> = ({
  isOpen,
  onClose,
  status,
  onUpdateStatus
}) => {
  const [selectedBench, setSelectedBench] = useState('Ritter_1892');
  const [isRunning, setIsRunning] = useState(false);
  const [latestResult, setLatestResult] = useState<any>(status?.latest_result || null);

  if (!isOpen) return null;

  const handleRun = async () => {
    setIsRunning(true);
    try {
      const res = await api.runBenchmark(selectedBench, 1.5);
      setLatestResult(res);
      const updatedStatus = await api.getBenchmarkStatus();
      onUpdateStatus(updatedStatus);
    } catch (e) {
      console.error(e);
    } finally {
      setIsRunning(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
      <div className="bg-slate-900 border border-slate-700 rounded-xl max-w-2xl w-full p-6 text-slate-200 shadow-2xl overflow-hidden flex flex-col max-h-[90vh]">
        {/* Header */}
        <div className="flex items-center justify-between pb-4 border-b border-slate-800">
          <div>
            <h2 className="text-lg font-bold text-white flex items-center gap-2">
              <span>SPH Hydrodynamic Benchmark Suite</span>
              <span className="text-xs px-2 py-0.5 rounded bg-amber-500/20 text-amber-300 border border-amber-500/40 font-mono">
                Mandatory Scientific Validation
              </span>
            </h2>
            <p className="text-xs text-slate-400 mt-1">
              Internal SPH solver is labeled <strong className="text-amber-300">Experimental SPH Solver</strong> and results are marked <strong className="text-amber-300">Unvalidated</strong> until passing analytical benchmark criteria.
            </p>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-white transition">
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content */}
        <div className="py-4 space-y-4 overflow-y-auto flex-1">
          {/* Benchmark Selector */}
          <div className="grid grid-cols-2 gap-3">
            <button
              onClick={() => setSelectedBench('Ritter_1892')}
              className={`p-3 rounded-lg border text-left transition ${
                selectedBench === 'Ritter_1892'
                  ? 'bg-blue-950/60 border-blue-500 text-blue-200'
                  : 'bg-slate-950 border-slate-800 text-slate-400 hover:border-slate-700'
              }`}
            >
              <div className="font-semibold text-sm text-white">Ritter (1892) Benchmark</div>
              <div className="text-xs text-slate-400 mt-1">
                Frictionless 1D dam-break against analytical wavefront celerity c = 2√(g·h₀) and parabolic free-surface depth curve.
              </div>
            </button>

            <button
              onClick={() => setSelectedBench('Martin_Moyce_1952')}
              className={`p-3 rounded-lg border text-left transition ${
                selectedBench === 'Martin_Moyce_1952'
                  ? 'bg-blue-950/60 border-blue-500 text-blue-200'
                  : 'bg-slate-950 border-slate-800 text-slate-400 hover:border-slate-700'
              }`}
            >
              <div className="font-semibold text-sm text-white">Martin & Moyce (1952)</div>
              <div className="text-xs text-slate-400 mt-1">
                Physical 2D water column collapse in air comparing surge front non-dimensional position Z(T) against experimental records.
              </div>
            </button>
          </div>

          {/* Verification Criteria Card */}
          <div className="bg-slate-950 p-3 rounded-lg border border-slate-800 text-xs">
            <div className="font-semibold text-slate-300 mb-2">Automated Verification Pass Criteria:</div>
            <div className="grid grid-cols-3 gap-2 text-slate-400 font-mono">
              <div>• Mass Error: &le; 1.5%</div>
              <div>• Depth R²: &ge; 0.70</div>
              <div>• Max CFL: &le; 1.00</div>
            </div>
          </div>

          {/* Benchmark Results Display */}
          {latestResult && (
            <div className="bg-slate-950 p-4 rounded-lg border border-slate-800 space-y-3">
              <div className="flex items-center justify-between">
                <div className="font-bold text-sm text-white">{latestResult.benchmark_name}</div>
                <div className={`px-2.5 py-1 rounded text-xs font-mono font-semibold flex items-center gap-1.5 ${
                  latestResult.status === 'Benchmark Verified'
                    ? 'bg-emerald-950 text-emerald-300 border border-emerald-500/40'
                    : 'bg-amber-950 text-amber-300 border border-amber-500/40'
                }`}>
                  {latestResult.status === 'Benchmark Verified' ? (
                    <CheckCircle2 className="w-3.5 h-3.5" />
                  ) : (
                    <AlertTriangle className="w-3.5 h-3.5" />
                  )}
                  <span>{latestResult.status}</span>
                </div>
              </div>

              {/* Metrics Grid */}
              <div className="grid grid-cols-4 gap-2 font-mono text-center">
                <div className="bg-slate-900 p-2 rounded border border-slate-800">
                  <div className="text-[10px] text-slate-500">MASS ERROR</div>
                  <div className="text-sm font-bold text-emerald-400">{latestResult.mass_conservation_error_pct}%</div>
                </div>
                <div className="bg-slate-900 p-2 rounded border border-slate-800">
                  <div className="text-[10px] text-slate-500">FRONT RMSE</div>
                  <div className="text-sm font-bold text-blue-400">{latestResult.wavefront_rmse_meters} m</div>
                </div>
                <div className="bg-slate-900 p-2 rounded border border-slate-800">
                  <div className="text-[10px] text-slate-500">DEPTH R²</div>
                  <div className="text-sm font-bold text-indigo-400">{latestResult.depth_r2_score}</div>
                </div>
                <div className="bg-slate-900 p-2 rounded border border-slate-800">
                  <div className="text-[10px] text-slate-500">MAX CFL</div>
                  <div className="text-sm font-bold text-amber-400">{latestResult.max_cfl_ratio}</div>
                </div>
              </div>

              <p className="text-xs text-slate-400 bg-slate-900/50 p-2.5 rounded border border-slate-800/60 leading-relaxed">
                {latestResult.summary}
              </p>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="pt-4 border-t border-slate-800 flex justify-end gap-3">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-xs font-medium text-slate-300 transition"
          >
            Close
          </button>
          <button
            onClick={handleRun}
            disabled={isRunning}
            className="px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-xs font-semibold text-white flex items-center gap-1.5 transition shadow-lg shadow-blue-900/30 disabled:opacity-50"
          >
            <Play className={`w-3.5 h-3.5 fill-current ${isRunning ? 'animate-spin' : ''}`} />
            <span>{isRunning ? 'Running Benchmark...' : 'Execute Benchmark Test'}</span>
          </button>
        </div>
      </div>
    </div>
  );
};
