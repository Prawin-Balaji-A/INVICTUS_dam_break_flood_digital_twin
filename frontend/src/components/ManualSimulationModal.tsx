import React, { useState, useEffect } from 'react';
import { 
  Sliders, 
  X, 
  Play, 
  Waves, 
  CheckCircle2, 
  RefreshCw, 
  Zap, 
  ShieldCheck, 
  Layers, 
  Activity
} from 'lucide-react';
import { Project, Scenario, SimulationResult } from '../types';
import { api } from '../services/api';

export type SimulationMode = 'REAL_TIME' | 'MANUAL';

interface ManualSimulationModalProps {
  isOpen: boolean;
  onClose: () => void;
  project: Project | null;
  selectedScenario: Scenario | null;
  onSelectScenario: (scenario: Scenario) => void;
  onRunSimulation: () => void;
  simulationMode: SimulationMode;
  onSetSimulationMode: (mode: SimulationMode) => void;
  currentSimulation: SimulationResult | null;
  isSimulating: boolean;
}

export const ManualSimulationModal: React.FC<ManualSimulationModalProps> = ({
  isOpen,
  onClose,
  project,
  selectedScenario,
  onSelectScenario,
  onRunSimulation,
  simulationMode,
  onSetSimulationMode,
  currentSimulation,
  isSimulating,
}) => {
  const [activeTab, setActiveTab] = useState<'authoritative' | 'manual'>(
    simulationMode === 'MANUAL' ? 'manual' : 'authoritative'
  );

  // Dam base physical properties (defaults adapted to domain)
  const damHeight = project?.dam_height_m || 65.23;
  const damLength = project?.crest_length_m || 1600.0;
  const crestElev = project?.crest_elevation_m || 240.0;
  const baseVolumeMcm = project?.reservoir_capacity_m3 
    ? project.reservoir_capacity_m3 / 1e6 
    : 500.0;

  // Manual Slider States
  const [waterLevel, setWaterLevel] = useState<number>(damHeight);
  const [reservoirVolumeMcm, setReservoirVolumeMcm] = useState<number>(baseVolumeMcm);
  const [breachWidth, setBreachWidth] = useState<number>(85.0);
  const [breachTimeMin, setBreachTimeMin] = useState<number>(120.0);
  const [manningN, setManningN] = useState<number>(0.035);
  const [failureMode, setFailureMode] = useState<'Overtopping' | 'Piping'>('Overtopping');
  const [formulation, setFormulation] = useState<string>('Froehlich_2008');

  // Preview Hydrograph State
  const [previewData, setPreviewData] = useState<{
    peak_discharge_m3s: number;
    time_to_peak_min: number;
    hydrograph: Array<{ time_min: number; discharge_m3s: number; stage_m: number }>;
  } | null>(null);
  const [isCalculatingPreview, setIsCalculatingPreview] = useState(false);
  const [isApplying, setIsApplying] = useState(false);

  // Initialize sliders from current scenario or dam project
  useEffect(() => {
    if (selectedScenario) {
      if (selectedScenario.reservoir_level) setWaterLevel(selectedScenario.reservoir_level);
      if (selectedScenario.reservoir_volume) setReservoirVolumeMcm(selectedScenario.reservoir_volume / 1e6);
      if (selectedScenario.breach_width) setBreachWidth(selectedScenario.breach_width);
      if (selectedScenario.breach_time) setBreachTimeMin(selectedScenario.breach_time / 60.0);
      if (selectedScenario.breach_type) {
        setFailureMode(selectedScenario.breach_type.toLowerCase().includes('pipe') ? 'Piping' : 'Overtopping');
      }
      if (selectedScenario.breach_formulation) setFormulation(selectedScenario.breach_formulation);
      if (selectedScenario.manning_n) setManningN(selectedScenario.manning_n);
    } else {
      setWaterLevel(damHeight);
      setReservoirVolumeMcm(baseVolumeMcm);
    }
  }, [selectedScenario, damHeight, baseVolumeMcm, isOpen]);

  // Sync tab with external simulationMode
  useEffect(() => {
    setActiveTab(simulationMode === 'MANUAL' ? 'manual' : 'authoritative');
  }, [simulationMode]);

  // Live recalculate preview hydrograph with debounce
  useEffect(() => {
    if (!isOpen || !project) return;
    const timer = setTimeout(() => {
      setIsCalculatingPreview(true);
      api.previewScenario({
        project_id: project.id,
        name: 'Preview',
        dam_height: damHeight,
        dam_length: damLength,
        dam_crest_elev: crestElev,
        reservoir_volume: reservoirVolumeMcm * 1e6,
        reservoir_level: waterLevel,
        breach_width: breachWidth,
        breach_time: breachTimeMin * 60.0,
        breach_type: failureMode,
        breach_formulation: formulation,
        manning_n: manningN,
      })
        .then((res) => {
          setPreviewData(res);
        })
        .catch(console.error)
        .finally(() => setIsCalculatingPreview(false));
    }, 150);

    return () => clearTimeout(timer);
  }, [
    isOpen,
    project,
    waterLevel,
    reservoirVolumeMcm,
    breachWidth,
    breachTimeMin,
    failureMode,
    formulation,
    manningN,
    damHeight,
    damLength,
    crestElev,
  ]);

  // Preset Configurations
  const handleApplyPreset = (type: 'PMF' | 'PIPING' | 'RAPID' | 'RISHI_GANGA' | 'RIVER_BLOCKAGE' | 'DEFAULT') => {
    if (type === 'PMF') {
      setWaterLevel(damHeight + 2.5);
      setReservoirVolumeMcm(Math.round(baseVolumeMcm * 1.25));
      setBreachWidth(120.0);
      setBreachTimeMin(90.0);
      setFailureMode('Overtopping');
      setManningN(0.038);
    } else if (type === 'PIPING') {
      setWaterLevel(Math.round(damHeight * 0.92 * 10) / 10);
      setReservoirVolumeMcm(baseVolumeMcm);
      setBreachWidth(75.0);
      setBreachTimeMin(150.0);
      setFailureMode('Piping');
      setManningN(0.035);
    } else if (type === 'RAPID') {
      setWaterLevel(damHeight);
      setReservoirVolumeMcm(baseVolumeMcm);
      setBreachWidth(140.0);
      setBreachTimeMin(45.0);
      setFailureMode('Overtopping');
      setManningN(0.032);
    } else if (type === 'RISHI_GANGA') {
      setWaterLevel(Math.round(damHeight * 0.95));
      setReservoirVolumeMcm(Math.round(baseVolumeMcm * 0.70));
      setBreachWidth(95.0);
      setBreachTimeMin(30.0);
      setFailureMode('Overtopping');
      setManningN(0.042);
      setFormulation('Froehlich_2008');
    } else if (type === 'RIVER_BLOCKAGE') {
      setWaterLevel(damHeight + 1.5);
      setReservoirVolumeMcm(Math.round(baseVolumeMcm * 1.35));
      setBreachWidth(140.0);
      setBreachTimeMin(60.0);
      setFailureMode('Overtopping');
      setManningN(0.036);
      setFormulation('MacDonald_1984');
    } else {
      // Default
      setWaterLevel(damHeight);
      setReservoirVolumeMcm(baseVolumeMcm);
      setBreachWidth(85.0);
      setBreachTimeMin(120.0);
      setFailureMode('Overtopping');
      setManningN(0.035);
      setFormulation('Froehlich_2008');
    }
  };

  // Submit and simulate custom parameters
  const handleSimulateCustom = async () => {
    if (!project) return;
    setIsApplying(true);
    try {
      // 1. Create or update custom scenario
      const customScen = await api.createOrUpdateCustomScenario({
        project_id: project.id,
        name: 'Scenario — Custom Manual Simulation',
        dam_height: damHeight,
        dam_length: damLength,
        dam_crest_elev: crestElev,
        reservoir_volume: reservoirVolumeMcm * 1e6,
        reservoir_level: waterLevel,
        breach_width: breachWidth,
        breach_time: breachTimeMin * 60.0,
        breach_type: failureMode,
        breach_side_slope: 0.5,
        breach_formulation: formulation,
        manning_n: manningN,
      });

      // 2. Select this scenario
      onSelectScenario(customScen);
      onSetSimulationMode('MANUAL');
      onClose();

      // 3. Trigger simulation execution
      onRunSimulation();
    } catch (err: any) {
      alert(`Failed to apply custom scenario: ${err.message || err}`);
    } finally {
      setIsApplying(false);
    }
  };

  // Switch to authoritative baseline
  const handleSwitchToAuthoritative = () => {
    onSetSimulationMode('REAL_TIME');
    onClose();
  };

  // Calculate percentage vs baseline peak Q
  const baselineQ = currentSimulation?.peak_discharge_m3s || 88699;
  const currentPreviewQ = previewData?.peak_discharge_m3s || 0;
  const deltaPercent = baselineQ > 0 && currentPreviewQ > 0
    ? ((currentPreviewQ - baselineQ) / baselineQ) * 100
    : 0;

  if (!isOpen) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4 animate-in fade-in duration-200"
      onClick={onClose}
    >
      <div
        className="bg-slate-900 border border-slate-700/80 rounded-2xl w-full max-w-4xl max-h-[92vh] flex flex-col shadow-2xl overflow-hidden font-sans text-slate-100"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header with Mode Tabs */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-800 bg-slate-950/70">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-xl bg-gradient-to-br from-cyan-500/20 to-blue-600/30 border border-cyan-500/30">
              <Sliders className="w-5 h-5 text-cyan-400" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-sm font-bold text-white tracking-wide">
                  DAM SIMULATION CONFIGURATOR
                </span>
                <span className="text-[10px] px-2 py-0.5 rounded-full font-mono bg-cyan-950 text-cyan-300 border border-cyan-500/40">
                  {project?.name || 'Selected Dam'}
                </span>
              </div>
              <div className="text-xs text-slate-400">
                Choose between real-time authoritative baseline data or customize physical parameters.
              </div>
            </div>
          </div>

          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition"
            title="Close Configurator"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Mode Selector Pill Bar */}
        <div className="px-6 pt-3 pb-2 bg-slate-900/60 border-b border-slate-800 flex items-center justify-between">
          <div className="flex items-center bg-slate-950 p-1 rounded-xl border border-slate-800 text-xs font-semibold">
            <button
              onClick={() => setActiveTab('authoritative')}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg transition ${
                activeTab === 'authoritative'
                  ? 'bg-blue-600 text-white shadow-md shadow-blue-900/40 font-bold'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              <ShieldCheck className="w-4 h-4 text-emerald-400" />
              <span>Real-Time / Baseline Data</span>
            </button>

            <button
              onClick={() => setActiveTab('manual')}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg transition ${
                activeTab === 'manual'
                  ? 'bg-cyan-600 text-white shadow-md shadow-cyan-900/40 font-bold'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              <Sliders className="w-4 h-4 text-cyan-300" />
              <span>Custom Manual Simulation</span>
            </button>
          </div>

          <div className="text-xs text-slate-400 flex items-center gap-2">
            <span>Active Mode:</span>
            <span
              className={`px-2.5 py-0.5 rounded-md font-mono text-[11px] font-bold border ${
                simulationMode === 'REAL_TIME'
                  ? 'bg-emerald-950/80 text-emerald-300 border-emerald-500/40'
                  : 'bg-cyan-950/80 text-cyan-300 border-cyan-500/40'
              }`}
            >
              {simulationMode === 'REAL_TIME' ? 'REAL-TIME BASELINE' : 'USER CUSTOM SIMULATION'}
            </span>
          </div>
        </div>

        {/* Tab 1: Authoritative Real-Time Data */}
        {activeTab === 'authoritative' && (
          <div className="p-6 overflow-y-auto space-y-5 text-xs text-slate-300">
            <div className="bg-emerald-950/30 border border-emerald-500/30 rounded-2xl p-4 flex items-start gap-3">
              <ShieldCheck className="w-5 h-5 text-emerald-400 shrink-0 mt-0.5" />
              <div>
                <div className="font-bold text-sm text-emerald-300 mb-1">
                  Authoritative Hydrodynamic Baseline
                </div>
                <div className="text-slate-300 text-xs leading-relaxed">
                  This mode uses verified engineering values from official dam safety reports and Copernicus 30m DEM terrain routing. All breach hydrodynamics, arrival times, and flood extents are authoritative.
                </div>
              </div>
            </div>

            {/* Baseline Parameters Grid */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <div className="bg-slate-950/80 border border-slate-800 rounded-xl p-3">
                <div className="text-slate-400 text-[11px]">Dam Height</div>
                <div className="text-white text-base font-bold font-mono mt-1">
                  {damHeight.toFixed(1)} m
                </div>
                <div className="text-[10px] text-slate-500 mt-0.5">Physical structural height</div>
              </div>

              <div className="bg-slate-950/80 border border-slate-800 rounded-xl p-3">
                <div className="text-slate-400 text-[11px]">Full Pool Level (FRL)</div>
                <div className="text-cyan-300 text-base font-bold font-mono mt-1">
                  {damHeight.toFixed(1)} m
                </div>
                <div className="text-[10px] text-slate-500 mt-0.5">Max reservoir pool stage</div>
              </div>

              <div className="bg-slate-950/80 border border-slate-800 rounded-xl p-3">
                <div className="text-slate-400 text-[11px]">Reservoir Capacity</div>
                <div className="text-amber-400 text-base font-bold font-mono mt-1">
                  {baseVolumeMcm.toLocaleString()} MCM
                </div>
                <div className="text-[10px] text-slate-500 mt-0.5">Active breach storage volume</div>
              </div>

              <div className="bg-slate-950/80 border border-slate-800 rounded-xl p-3">
                <div className="text-slate-400 text-[11px]">Baseline Peak Inflow</div>
                <div className="text-red-400 text-base font-bold font-mono mt-1">
                  {baselineQ.toLocaleString()} m³/s
                </div>
                <div className="text-[10px] text-slate-500 mt-0.5">Hydrodynamic peak discharge</div>
              </div>
            </div>

            <div className="bg-slate-950/60 border border-slate-800 rounded-xl p-4 space-y-2">
              <div className="font-bold text-white text-xs uppercase tracking-wide">
                Hydrodynamic Routing Engine Details
              </div>
              <div className="grid grid-cols-2 gap-2 text-slate-300 text-[11px]">
                <div>• Solver: 2D Manning kinematic/diffusion-wave</div>
                <div>• Elevation Model: Copernicus 30m DEM</div>
                <div>• River Thalweg: Authoritative GeoJSON Alignment</div>
                <div>• Time Step: Synchronized dt = 60s hydrograph</div>
              </div>
            </div>

            {/* Switch Action */}
            <div className="flex items-center justify-between pt-4 border-t border-slate-800">
              <div className="text-xs text-slate-400">
                Want to test what-if scenarios? Switch to Custom Manual Simulation to adjust water levels and breach sizes.
              </div>
              <button
                onClick={handleSwitchToAuthoritative}
                className="flex items-center gap-2 bg-emerald-600 hover:bg-emerald-500 text-white font-bold text-xs px-5 py-2.5 rounded-xl shadow-lg shadow-emerald-900/30 transition"
              >
                <CheckCircle2 className="w-4 h-4" />
                <span>Use Real-Time Baseline</span>
              </button>
            </div>
          </div>
        )}

        {/* Tab 2: Custom Manual Parameters (Sliders & Inputs) */}
        {activeTab === 'manual' && (
          <div className="p-6 overflow-y-auto space-y-6 text-xs text-slate-300">
            {/* Quick Presets Bar */}
            <div className="flex items-center justify-between pb-3 border-b border-slate-800">
              <span className="text-xs font-bold text-slate-300 flex items-center gap-1.5">
                <Zap className="w-3.5 h-3.5 text-amber-400" />
                <span>QUICK SCENARIO PRESETS:</span>
              </span>
              <div className="flex items-center gap-1.5">
                <button
                  onClick={() => handleApplyPreset('PMF')}
                  className="px-2.5 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium transition border border-slate-700"
                >
                  PMF Overtopping (+2.5m)
                </button>
                <button
                  onClick={() => handleApplyPreset('PIPING')}
                  className="px-2.5 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium transition border border-slate-700"
                >
                  Piping Erosion (Normal Pool)
                </button>
                <button
                  onClick={() => handleApplyPreset('RAPID')}
                  className="px-2.5 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium transition border border-slate-700"
                >
                  Rapid Breach (45m)
                </button>
                <button
                  onClick={() => handleApplyPreset('RISHI_GANGA')}
                  className="px-2.5 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-blue-300 text-xs font-medium transition border border-blue-500/30"
                  title="Uttarakhand 2021 Rock-ice avalanche & landslide lake outburst surge"
                >
                  Rishi Ganga Landslide Surge
                </button>
                <button
                  onClick={() => handleApplyPreset('RIVER_BLOCKAGE')}
                  className="px-2.5 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-emerald-300 text-xs font-medium transition border border-emerald-500/30"
                  title="Channel blockage collapse & extreme inflow sudden surge"
                >
                  River Blockage Burst
                </button>
                <button
                  onClick={() => handleApplyPreset('DEFAULT')}
                  className="px-2.5 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-400 hover:text-white text-xs font-medium transition"
                  title="Reset to dam baseline"
                >
                  <RefreshCw className="w-3 h-3" />
                </button>
              </div>
            </div>

            {/* Sliders Grid */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {/* 1. Water Level (Hw) */}
              <div className="space-y-2 bg-slate-950/60 p-3.5 rounded-xl border border-slate-800">
                <div className="flex justify-between items-center">
                  <label className="font-semibold text-white flex items-center gap-1.5">
                    <Waves className="w-3.5 h-3.5 text-cyan-400" />
                    <span>Reservoir Water Level (Hw)</span>
                  </label>
                  <div className="flex items-center gap-1">
                    <input
                      type="number"
                      step="0.5"
                      min={10}
                      max={Math.round(damHeight * 1.3)}
                      value={waterLevel}
                      onChange={(e) => setWaterLevel(Math.max(5, parseFloat(e.target.value) || 5))}
                      className="w-20 px-2 py-1 bg-slate-900 border border-slate-700 rounded text-right font-mono font-bold text-cyan-300 text-xs"
                    />
                    <span className="text-slate-400 text-xs">m</span>
                  </div>
                </div>
                <input
                  type="range"
                  min={10}
                  max={Math.round(damHeight * 1.3)}
                  step={0.5}
                  value={waterLevel}
                  onChange={(e) => setWaterLevel(parseFloat(e.target.value))}
                  className="w-full accent-cyan-400 h-1.5 bg-slate-800 rounded-lg cursor-pointer"
                />
                <div className="flex justify-between text-[10px] text-slate-500 font-mono">
                  <span>Min: 10 m</span>
                  <span>Crest: {damHeight.toFixed(1)} m</span>
                  <span>Max: {Math.round(damHeight * 1.3)} m</span>
                </div>
              </div>

              {/* 2. Active Reservoir Volume (Vw) */}
              <div className="space-y-2 bg-slate-950/60 p-3.5 rounded-xl border border-slate-800">
                <div className="flex justify-between items-center">
                  <label className="font-semibold text-white flex items-center gap-1.5">
                    <Layers className="w-3.5 h-3.5 text-blue-400" />
                    <span>Active Reservoir Storage (Vw)</span>
                  </label>
                  <div className="flex items-center gap-1">
                    <input
                      type="number"
                      step="10"
                      min={50}
                      max={Math.round(baseVolumeMcm * 2.5)}
                      value={reservoirVolumeMcm}
                      onChange={(e) => setReservoirVolumeMcm(Math.max(10, parseFloat(e.target.value) || 10))}
                      className="w-24 px-2 py-1 bg-slate-900 border border-slate-700 rounded text-right font-mono font-bold text-blue-300 text-xs"
                    />
                    <span className="text-slate-400 text-xs">MCM</span>
                  </div>
                </div>
                <input
                  type="range"
                  min={50}
                  max={Math.round(baseVolumeMcm * 2.5)}
                  step={10}
                  value={reservoirVolumeMcm}
                  onChange={(e) => setReservoirVolumeMcm(parseFloat(e.target.value))}
                  className="w-full accent-blue-400 h-1.5 bg-slate-800 rounded-lg cursor-pointer"
                />
                <div className="flex justify-between text-[10px] text-slate-500 font-mono">
                  <span>50 MCM</span>
                  <span>Base: {baseVolumeMcm} MCM</span>
                  <span>{Math.round(baseVolumeMcm * 2.5)} MCM</span>
                </div>
              </div>

              {/* 3. Breach Bottom Width (Bw) */}
              <div className="space-y-2 bg-slate-950/60 p-3.5 rounded-xl border border-slate-800">
                <div className="flex justify-between items-center">
                  <label className="font-semibold text-white">
                    Breach Bottom Width (Bw)
                  </label>
                  <div className="flex items-center gap-1">
                    <input
                      type="number"
                      step="5"
                      min={20}
                      max={350}
                      value={breachWidth}
                      onChange={(e) => setBreachWidth(Math.max(10, parseFloat(e.target.value) || 10))}
                      className="w-20 px-2 py-1 bg-slate-900 border border-slate-700 rounded text-right font-mono font-bold text-amber-300 text-xs"
                    />
                    <span className="text-slate-400 text-xs">m</span>
                  </div>
                </div>
                <input
                  type="range"
                  min={20}
                  max={350}
                  step={5}
                  value={breachWidth}
                  onChange={(e) => setBreachWidth(parseFloat(e.target.value))}
                  className="w-full accent-amber-400 h-1.5 bg-slate-800 rounded-lg cursor-pointer"
                />
                <div className="flex justify-between text-[10px] text-slate-500 font-mono">
                  <span>Narrow: 20 m</span>
                  <span>Standard: 85 m</span>
                  <span>Wide: 350 m</span>
                </div>
              </div>

              {/* 4. Formation Time (tf) */}
              <div className="space-y-2 bg-slate-950/60 p-3.5 rounded-xl border border-slate-800">
                <div className="flex justify-between items-center">
                  <label className="font-semibold text-white">
                    Breach Formation Time (tf)
                  </label>
                  <div className="flex items-center gap-1">
                    <input
                      type="number"
                      step="5"
                      min={15}
                      max={360}
                      value={breachTimeMin}
                      onChange={(e) => setBreachTimeMin(Math.max(15, parseFloat(e.target.value) || 15))}
                      className="w-20 px-2 py-1 bg-slate-900 border border-slate-700 rounded text-right font-mono font-bold text-orange-300 text-xs"
                    />
                    <span className="text-slate-400 text-xs">min</span>
                  </div>
                </div>
                <input
                  type="range"
                  min={15}
                  max={360}
                  step={5}
                  value={breachTimeMin}
                  onChange={(e) => setBreachTimeMin(parseFloat(e.target.value))}
                  className="w-full accent-orange-400 h-1.5 bg-slate-800 rounded-lg cursor-pointer"
                />
                <div className="flex justify-between text-[10px] text-slate-500 font-mono">
                  <span>Rapid: 15 min</span>
                  <span>Moderate: 120 min</span>
                  <span>Gradual: 360 min</span>
                </div>
              </div>

              {/* 5. Manning Roughness n */}
              <div className="space-y-2 bg-slate-950/60 p-3.5 rounded-xl border border-slate-800">
                <div className="flex justify-between items-center">
                  <label className="font-semibold text-white">
                    Manning Roughness Coefficient (n)
                  </label>
                  <div className="flex items-center gap-1">
                    <input
                      type="number"
                      step="0.005"
                      min={0.020}
                      max={0.080}
                      value={manningN}
                      onChange={(e) => setManningN(parseFloat(e.target.value) || 0.035)}
                      className="w-20 px-2 py-1 bg-slate-900 border border-slate-700 rounded text-right font-mono font-bold text-emerald-300 text-xs"
                    />
                  </div>
                </div>
                <input
                  type="range"
                  min={0.020}
                  max={0.080}
                  step={0.005}
                  value={manningN}
                  onChange={(e) => setManningN(parseFloat(e.target.value))}
                  className="w-full accent-emerald-400 h-1.5 bg-slate-800 rounded-lg cursor-pointer"
                />
                <div className="flex justify-between text-[10px] text-slate-500 font-mono">
                  <span>0.020 (Clean Rock)</span>
                  <span>0.035 (Natural Bed)</span>
                  <span>0.080 (Dense Veg)</span>
                </div>
              </div>

              {/* 6. Failure Mode & Formulation */}
              <div className="grid grid-cols-2 gap-3 bg-slate-950/60 p-3.5 rounded-xl border border-slate-800">
                <div>
                  <label className="font-semibold text-white block mb-1.5">Failure Mode</label>
                  <div className="grid grid-cols-2 gap-1 bg-slate-900 p-1 rounded-lg border border-slate-700">
                    <button
                      type="button"
                      onClick={() => setFailureMode('Overtopping')}
                      className={`py-1 text-center rounded font-semibold text-[11px] transition ${
                        failureMode === 'Overtopping'
                          ? 'bg-blue-600 text-white shadow'
                          : 'text-slate-400 hover:text-white'
                      }`}
                    >
                      Overtopping
                    </button>
                    <button
                      type="button"
                      onClick={() => setFailureMode('Piping')}
                      className={`py-1 text-center rounded font-semibold text-[11px] transition ${
                        failureMode === 'Piping'
                          ? 'bg-blue-600 text-white shadow'
                          : 'text-slate-400 hover:text-white'
                      }`}
                    >
                      Piping
                    </button>
                  </div>
                </div>

                <div>
                  <label className="font-semibold text-white block mb-1.5">Breach Formulation</label>
                  <select
                    value={formulation}
                    onChange={(e) => setFormulation(e.target.value)}
                    className="w-full px-2 py-1.5 bg-slate-900 border border-slate-700 rounded-lg text-slate-200 text-xs font-medium focus:ring-1 focus:ring-cyan-400 outline-none"
                  >
                    <option value="Froehlich_2008">Froehlich (2008)</option>
                    <option value="MacDonald_1984">MacDonald (1984)</option>
                    <option value="VonThun_1990">Von Thun & Gillette (1990)</option>
                  </select>
                </div>
              </div>
            </div>

            {/* Real-Time Hydrograph & Peak Discharge Preview Card */}
            <div className="bg-slate-950/90 border border-slate-800 rounded-2xl p-4 space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Activity className="w-4 h-4 text-cyan-400" />
                  <span className="font-bold text-white text-xs">
                    INSTANT HYDROGRAPH & PEAK DISCHARGE PREVIEW
                  </span>
                  {isCalculatingPreview && (
                    <span className="text-[10px] text-cyan-400 animate-pulse">Calculating…</span>
                  )}
                </div>

                <div className="flex items-center gap-3">
                  <div className="text-right">
                    <div className="text-[10px] text-slate-400">Peak Discharge (Qp)</div>
                    <div className="text-cyan-400 font-bold font-mono text-base">
                      {previewData ? `${previewData.peak_discharge_m3s.toLocaleString()} m³/s` : '—'}
                    </div>
                  </div>

                  <div className="text-right pl-3 border-l border-slate-800">
                    <div className="text-[10px] text-slate-400">Time to Peak</div>
                    <div className="text-amber-400 font-bold font-mono text-base">
                      {previewData ? `${previewData.time_to_peak_min.toFixed(0)} min` : '—'}
                    </div>
                  </div>
                </div>
              </div>

              {/* Peak comparison banner */}
              {previewData && (
                <div className="flex items-center justify-between text-xs px-3 py-2 rounded-xl bg-slate-900 border border-slate-800">
                  <span className="text-slate-400">
                    Comparison with Authoritative Baseline ({baselineQ.toLocaleString()} m³/s):
                  </span>
                  <span
                    className={`font-mono font-bold ${
                      deltaPercent > 0 ? 'text-red-400' : 'text-emerald-400'
                    }`}
                  >
                    {deltaPercent > 0 ? `+${deltaPercent.toFixed(1)}% higher` : `${deltaPercent.toFixed(1)}% lower`}
                  </span>
                </div>
              )}

              {/* Dynamic Mini SVG Hydrograph */}
              {previewData?.hydrograph && previewData.hydrograph.length > 0 && (
                <div className="pt-2">
                  <svg className="w-full h-24 overflow-visible" viewBox="0 0 500 100" preserveAspectRatio="none">
                    <defs>
                      <linearGradient id="qGradient" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="#06b6d4" stopOpacity="0.5" />
                        <stop offset="100%" stopColor="#06b6d4" stopOpacity="0.0" />
                      </linearGradient>
                    </defs>

                    {/* Generate path coordinates */}
                    {(() => {
                      const pts = previewData.hydrograph;
                      const maxQ = Math.max(...pts.map((p) => p.discharge_m3s), 100);
                      const maxT = Math.max(...pts.map((p) => p.time_min), 60);

                      const pointsStr = pts
                        .map((p) => {
                          const x = (p.time_min / maxT) * 490 + 5;
                          const y = 95 - (p.discharge_m3s / maxQ) * 85;
                          return `${x},${y}`;
                        })
                        .join(' ');

                      const areaStr = `5,95 ${pointsStr} 495,95`;

                      return (
                        <>
                          <polygon points={areaStr} fill="url(#qGradient)" />
                          <polyline points={pointsStr} fill="none" stroke="#22d3ee" strokeWidth="2.5" />
                        </>
                      );
                    })()}
                  </svg>
                  <div className="flex justify-between text-[10px] text-slate-500 font-mono mt-1">
                    <span>T+00 hr</span>
                    <span>T+03 hr</span>
                    <span>T+06 hr</span>
                  </div>
                </div>
              )}
            </div>

            {/* Action Bar */}
            <div className="flex items-center justify-between pt-4 border-t border-slate-800">
              <button
                type="button"
                onClick={onClose}
                className="px-4 py-2 rounded-xl text-slate-400 hover:text-white hover:bg-slate-800 text-xs transition"
              >
                Cancel
              </button>

              <button
                type="button"
                onClick={handleSimulateCustom}
                disabled={isApplying || isSimulating}
                className="flex items-center gap-2 bg-gradient-to-r from-cyan-600 to-blue-600 hover:from-cyan-500 hover:to-blue-500 text-white font-bold text-xs px-6 py-2.5 rounded-xl shadow-lg shadow-cyan-900/40 transition disabled:opacity-50"
              >
                <Play className="w-4 h-4 fill-current" />
                <span>{isApplying ? 'Configuring Scenario…' : 'Simulate with Custom Parameters'}</span>
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
