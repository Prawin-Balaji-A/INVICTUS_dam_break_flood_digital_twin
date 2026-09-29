import React from 'react';
import { Project, Scenario, BenchmarkStatus } from '../types';
import { 
  Waves, 
  Layers, 
  Box, 
  Play, 
  FileText, 
  Download, 
  Database, 
  PlusCircle, 
  GitCompare,
  ShieldCheck,
  Search,
  Sparkles,
  MapPin,
  Sliders,
  Sun,
  Moon,
  Satellite,
  Cpu
} from 'lucide-react';
import { useTheme } from '../context/ThemeContext';

interface NavbarProps {
  projects: Project[];
  selectedProject: Project | null;
  onSelectProject: (p: Project) => void;
  scenarios: Scenario[];
  selectedScenario: Scenario | null;
  onSelectScenario: (s: Scenario) => void;
  benchmarkStatus: BenchmarkStatus | null;
  viewMode: 'MAP' | '2D' | '3D' | 'SOURCES' | 'REPORT' | 'VALIDATION';
  onChangeViewMode: (mode: 'MAP' | '2D' | '3D' | 'SOURCES' | 'REPORT' | 'VALIDATION') => void;
  onOpenNewProject: () => void;
  onOpenDamSearch: () => void;
  onOpenAIPredictor: () => void;
  onOpenBenchmarks: () => void;
  onOpenCompare: () => void;
  onOpenExport: () => void;
  onRunSimulation: () => void;
  isSimulating: boolean;
  simulationMode?: 'REAL_TIME' | 'MANUAL';
  onOpenManualModal?: () => void;
  onOpenSPHDelft3D?: () => void;
  onOpenGEE?: () => void;
}

export const Navbar: React.FC<NavbarProps> = ({
  projects,
  selectedProject,
  scenarios,
  selectedScenario,
  onSelectScenario,
  benchmarkStatus,
  viewMode,
  onChangeViewMode,
  onOpenNewProject,
  onOpenDamSearch,
  onOpenAIPredictor,
  onOpenBenchmarks,
  onOpenCompare,
  onOpenExport,
  onRunSimulation,
  isSimulating,
  simulationMode = 'REAL_TIME',
  onOpenManualModal,
  onOpenSPHDelft3D,
  onOpenGEE
}) => {
  const { theme, toggleTheme } = useTheme();

  return (
    <header className="bg-slate-900 border-b border-slate-800 text-slate-200 px-4 py-2.5 flex flex-wrap items-center justify-between gap-4 sticky top-0 z-50">
      {/* Brand */}
      <div className="flex items-center space-x-3">
        <div className="w-9 h-9 rounded-lg bg-blue-600/20 border border-blue-500/40 flex items-center justify-center text-blue-400 shadow-inner">
          <Waves className="w-5 h-5 animate-pulse" />
        </div>
        <div>
          <div className="font-bold text-sm text-white tracking-wide flex items-center gap-2">
            DAM BREAK INUNDATION TWIN
            <span className="text-[10px] px-2 py-0.5 rounded bg-blue-500/20 text-blue-300 font-mono border border-blue-500/30">
              HYDRODYNAMIC v1.0
            </span>
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-indigo-500/20 text-indigo-300 font-mono border border-indigo-500/30 hidden sm:inline-block">
              SIH PS 26161
            </span>
          </div>
          <div className="text-[11px] text-slate-400">
            {selectedProject ? `${selectedProject.river_name} • ${selectedProject.dam_name}` : 'Generalized Hydrodynamic Framework'}
          </div>
        </div>
      </div>

      {/* Primary selector: the dam SEARCH is now the main way to choose a dam.
          The large project dropdown was removed — this button surfaces the
          active dam and opens the searchable registry (DamSearchModal), which
          already fires onSelectProject. The scenario dropdown is retained
          because running a simulation requires an explicit scenario. */}
      <div className="flex items-center space-x-2 bg-slate-950/70 p-1 rounded-lg border border-slate-800 text-xs">
        <button
          onClick={onOpenDamSearch}
          title="Search the national dam registry to select a dam"
          className="flex items-center gap-2 bg-slate-900 hover:bg-slate-800 text-slate-200 border border-slate-700/60 hover:border-cyan-500/60 rounded px-3 py-1.5 focus:outline-none focus:border-cyan-500 font-medium transition min-w-[220px] text-left"
        >
          <Search className="w-4 h-4 text-cyan-400 shrink-0" />
          <span className="flex-1 min-w-0">
            {selectedProject ? (
              <span className="block truncate">{selectedProject.name}</span>
            ) : (
              <span className="text-slate-400">Search dams to begin…</span>
            )}
          </span>
          <span className="text-[9px] font-mono text-slate-500 border border-slate-700 rounded px-1 py-0.5 shrink-0">
            {projects.length} REG
          </span>
        </button>

        <select
          aria-label="Select Scenario"
          value={selectedScenario?.id || ''}
          onChange={(e) => {
            const s = scenarios.find(x => x.id === e.target.value);
            if (s) onSelectScenario(s);
          }}
          className="bg-slate-900 text-slate-200 border border-slate-700/60 rounded px-2.5 py-1.5 focus:outline-none focus:border-blue-500 font-medium max-w-[200px] truncate"
        >
          {scenarios.length > 0 ? (
            scenarios.map(s => (
              <option key={s.id} value={s.id}>{s.name}</option>
            ))
          ) : (
            <option value="">Default Scenario</option>
          )}
        </select>

        <button
          onClick={onOpenNewProject}
          title="Create New Project"
          className="p-1.5 text-slate-400 hover:text-blue-400 transition"
        >
          <PlusCircle className="w-4 h-4" />
        </button>
      </div>

      {/* Actions / Controls */}
      <div className="flex items-center gap-2">

        {/* Two Options: Real-Time Baseline vs Manual Slider Input */}
        <button
          onClick={onOpenManualModal}
          className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-xs font-medium border transition ${
            simulationMode === 'MANUAL'
              ? 'bg-cyan-950/80 text-cyan-300 border-cyan-500/50 hover:bg-cyan-900/60 shadow-sm font-semibold'
              : 'bg-slate-900 text-slate-300 border-slate-700/80 hover:bg-slate-800'
          }`}
          title="Configure manual simulation parameters (water levels, breach width, volume, Manning n) in slider format"
        >
          <Sliders className={`w-3.5 h-3.5 ${simulationMode === 'MANUAL' ? 'text-cyan-400' : 'text-slate-400'}`} />
          <span>{simulationMode === 'MANUAL' ? 'Manual: Active' : 'Sliders / Parameters'}</span>
        </button>

        {/* Compute Hydrodynamic Simulation Button */}
        <button
          onClick={onRunSimulation}
          disabled={isSimulating}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-semibold shadow-lg transition ${
            isSimulating 
              ? 'bg-blue-600/50 text-slate-300 cursor-not-allowed'
              : 'bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white shadow-blue-900/30'
          }`}
          title="Compute numerical hydrodynamic simulation (Saint-Venant 2D flood solver)"
        >
          <Cpu className={`w-3.5 h-3.5 ${isSimulating ? 'animate-spin' : ''}`} />
          <span>
            {isSimulating 
              ? 'Computing Physics...' 
              : 'Compute Simulation'}
          </span>
        </button>
      </div>

      {/* Views Navigation */}
      <div className="flex items-center space-x-1 bg-slate-950 p-1 rounded-lg border border-slate-800 text-xs">
        <button
          onClick={() => onChangeViewMode('MAP')}
          className={`flex items-center gap-1 px-2.5 py-1 rounded transition ${
            viewMode === 'MAP' ? 'bg-blue-600 text-white font-medium' : 'text-slate-400 hover:text-white'
          }`}
        >
          <MapPin className="w-3.5 h-3.5" />
          <span>Dam Map</span>
        </button>

        <button
          onClick={() => onChangeViewMode('2D')}
          className={`flex items-center gap-1 px-2.5 py-1 rounded transition ${
            viewMode === '2D' ? 'bg-blue-600 text-white font-medium' : 'text-slate-400 hover:text-white'
          }`}
        >
          <Layers className="w-3.5 h-3.5" />
          <span>2D Map</span>
        </button>

        <button
          onClick={() => onChangeViewMode('3D')}
          className={`flex items-center gap-1 px-2.5 py-1 rounded transition ${
            viewMode === '3D' ? 'bg-blue-600 text-white font-medium' : 'text-slate-400 hover:text-white'
          }`}
        >
          <Box className="w-3.5 h-3.5" />
          <span>3D Twin</span>
        </button>

        <button
          onClick={onOpenAIPredictor}
          className="flex items-center gap-1.5 px-2.5 py-1 rounded text-purple-300 hover:text-white hover:bg-purple-950/70 border border-purple-500/40 bg-purple-950/30 transition shadow-sm"
          title="Machine Learning AI Rapid Inundation Surrogate"
        >
          <Sparkles className="w-3.5 h-3.5 text-purple-400 animate-pulse" />
          <span className="font-semibold">AI Predictor</span>
        </button>


        <button
          onClick={onOpenGEE}
          className="flex items-center gap-1.5 px-2.5 py-1 rounded text-cyan-300 hover:text-white hover:bg-cyan-950/70 border border-cyan-500/40 bg-cyan-950/30 transition shadow-sm"
          title="Google Earth Engine Near Real-Time Satellite Analysis"
        >
          <Satellite className="w-3.5 h-3.5 text-cyan-400" />
          <span className="font-semibold">GEE Real-Time</span>
        </button>

        <button
          onClick={onOpenCompare}
          className="flex items-center gap-1 px-2.5 py-1 rounded text-slate-400 hover:text-white transition"
          title="Compare scenarios"
        >
          <GitCompare className="w-3.5 h-3.5" />
          <span>Scenarios</span>
        </button>

        {onOpenSPHDelft3D && (
          <button
            onClick={onOpenSPHDelft3D}
            className="flex items-center gap-1.5 px-2.5 py-1 rounded text-cyan-300 hover:text-white hover:bg-cyan-950/70 border border-cyan-500/40 bg-cyan-950/30 transition shadow-sm"
            title="SPH 3D Near-Field vs Delft3D-FLOW Multiphysics Benchmark & Comparison"
          >
            <Waves className="w-3.5 h-3.5 text-cyan-400" />
            <span className="font-semibold">SPH vs Delft3D</span>
          </button>
        )}

        <button
          onClick={() => onChangeViewMode('REPORT')}
          className={`flex items-center gap-1 px-2.5 py-1 rounded transition ${
            viewMode === 'REPORT' ? 'bg-blue-600 text-white font-medium' : 'text-slate-400 hover:text-white'
          }`}
        >
          <FileText className="w-3.5 h-3.5" />
          <span>Report</span>
        </button>

        <button
          onClick={() => onChangeViewMode('VALIDATION')}
          className={`flex items-center gap-1 px-2.5 py-1 rounded transition ${
            viewMode === 'VALIDATION' ? 'bg-blue-600 text-white font-medium' : 'text-slate-400 hover:text-white'
          }`}
          title="Scientific validation dashboard and consistency audit"
        >
          <ShieldCheck className="w-3.5 h-3.5" />
          <span>Validation</span>
        </button>

        <button
          onClick={onOpenExport}
          className="flex items-center gap-1 px-2.5 py-1 rounded text-slate-400 hover:text-white transition"
          title="Export Shapefile, GeoTIFF, GeoJSON"
        >
          <Download className="w-3.5 h-3.5" />
          <span>Export</span>
        </button>

        <button
          onClick={() => onChangeViewMode('SOURCES')}
          className={`flex items-center gap-1 px-2.5 py-1 rounded transition ${
            viewMode === 'SOURCES' ? 'bg-blue-600 text-white font-medium' : 'text-slate-400 hover:text-white'
          }`}
          title="Data source transparency"
        >
          <Database className="w-3.5 h-3.5" />
          <span>Sources</span>
        </button>
      </div>

      {/* Light / Dark Mode Toggle Button */}
      <button
        onClick={toggleTheme}
        className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-slate-700 bg-slate-900 hover:bg-slate-800 text-amber-300 hover:text-amber-200 transition text-xs font-semibold shadow-sm ml-auto sm:ml-0"
        title={theme === 'dark' ? "Switch to Light Mode" : "Switch to Dark Mode"}
      >
        {theme === 'dark' ? (
          <>
            <Sun className="w-4 h-4 text-amber-400" />
            <span className="hidden md:inline text-slate-200">Light Mode</span>
          </>
        ) : (
          <>
            <Moon className="w-4 h-4 text-indigo-600" />
            <span className="hidden md:inline text-slate-800 font-bold">Dark Mode</span>
          </>
        )}
      </button>
    </header>
  );
};
