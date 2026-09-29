import React from 'react';
import { Scenario, SimulationResult } from '../types';
import { X, GitCompare } from 'lucide-react';

interface ScenarioCompareModalProps {
  isOpen: boolean;
  onClose: () => void;
  scenarios: Scenario[];
  simulation?: SimulationResult | null;
}

export const ScenarioCompareModal: React.FC<ScenarioCompareModalProps> = ({
  isOpen,
  onClose,
  scenarios,
  simulation: _simulation
}) => {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
      <div className="bg-slate-900 border border-slate-700 rounded-xl max-w-4xl w-full p-6 text-slate-200 shadow-2xl flex flex-col max-h-[90vh]">
        {/* Header */}
        <div className="flex items-center justify-between pb-4 border-b border-slate-800">
          <div>
            <h2 className="text-lg font-bold text-white flex items-center gap-2">
              <GitCompare className="w-5 h-5 text-indigo-400" />
              <span>Multi-Scenario Hydrodynamic Comparison</span>
            </h2>
            <p className="text-xs text-slate-400 mt-1">
              Side-by-side parametric comparison across dam-break breach scenarios.
            </p>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-white transition">
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content Table */}
        <div className="py-4 overflow-x-auto">
          <table className="w-full text-xs border-collapse">
            <thead>
              <tr className="border-b border-slate-800 bg-slate-950/60 text-slate-400">
                <th className="p-3 text-left font-medium">Metric / Parameter</th>
                {scenarios.map(s => (
                  <th key={s.id} className="p-3 text-left font-semibold text-white">
                    {s.name}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60 font-mono">
              <tr>
                <td className="p-3 text-slate-400 font-sans">Breach Formulation</td>
                {scenarios.map(s => (
                  <td key={s.id} className="p-3 text-blue-400">{s.breach_formulation}</td>
                ))}
              </tr>
              <tr>
                <td className="p-3 text-slate-400 font-sans">Breach Type / Mode</td>
                {scenarios.map(s => (
                  <td key={s.id} className="p-3 text-slate-300">{s.breach_type}</td>
                ))}
              </tr>
              <tr>
                <td className="p-3 text-slate-400 font-sans">Average Breach Width</td>
                {scenarios.map(s => (
                  <td key={s.id} className="p-3 text-white font-bold">{s.breach_width?.toFixed(1)} m</td>
                ))}
              </tr>
              <tr>
                <td className="p-3 text-slate-400 font-sans">Formation Time (tf)</td>
                {scenarios.map(s => (
                  <td key={s.id} className="p-3 text-slate-300">{(s.breach_time / 60.0).toFixed(1)} min</td>
                ))}
              </tr>
              <tr>
                <td className="p-3 text-slate-400 font-sans">Breach Side Slope (z)</td>
                {scenarios.map(s => (
                  <td key={s.id} className="p-3 text-slate-300">
                    {s.breach_side_slope != null ? `${s.breach_side_slope}:1 (H:V)` : '—'}
                  </td>
                ))}
              </tr>
              <tr>
                <td className="p-3 text-slate-400 font-sans">Reservoir Active Storage</td>
                {scenarios.map(s => (
                  <td key={s.id} className="p-3 text-slate-300">
                    {s.reservoir_volume != null ? `${(s.reservoir_volume / 1e6).toFixed(1)} MCM` : '—'}
                  </td>
                ))}
              </tr>
              <tr className="bg-blue-950/20">
                <td className="p-3 text-slate-300 font-sans font-semibold">Peak Outflow Discharge</td>
                {scenarios.map(s => (
                  <td key={s.id} className="p-3 text-amber-400 font-bold">
                    {s.peak_discharge_m3s ? `${s.peak_discharge_m3s.toLocaleString()} m³/s` : '—'}
                  </td>
                ))}
              </tr>
            </tbody>
          </table>
        </div>

        {/* Footer */}
        <div className="pt-4 border-t border-slate-800 flex justify-end">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-xs font-medium text-slate-300 transition"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
};
