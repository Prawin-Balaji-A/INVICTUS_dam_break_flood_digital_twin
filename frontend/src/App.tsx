import React, { useState, useEffect } from 'react';
import { Project, Scenario, SimulationResult, BenchmarkStatus } from './types';
import { api } from './services/api';
import { Navbar } from './components/Navbar';
import { ProjectView } from './pages/ProjectView';
import { DigitalTwin3D } from './pages/DigitalTwin3D';
import { DataSourcesView } from './pages/DataSourcesView';
import { ReportView } from './pages/ReportView';
import { ValidationView } from './pages/ValidationView';
import { SPHBenchmarkModal } from './components/SPHBenchmarkModal';
import { ScenarioCompareModal } from './components/ScenarioCompareModal';
import { ExportModal } from './components/ExportModal';
import { NewProjectModal } from './components/NewProjectModal';
import { DamSearchModal } from './components/DamSearchModal';
import { AIPredictorModal } from './components/AIPredictorModal';
import { ManualSimulationModal, SimulationMode } from './components/ManualSimulationModal';
import { SPHDelft3DCompareModal } from './components/SPHDelft3DCompareModal';
import { GEEFloodAnalysisModal } from './components/GEEFloodAnalysisModal';
import { IndiaDamMap, DamRegistryRecord } from './map/IndiaDamMap';
import { ErrorBoundary } from './components/ErrorBoundary';

export const App: React.FC = () => {
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProject, setSelectedProject] = useState<Project | null>(null);

  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [selectedScenario, setSelectedScenario] = useState<Scenario | null>(null);

  const [simulation, setSimulation] = useState<SimulationResult | null>(null);
  const [isSimulating, setIsSimulating] = useState(false);
  const [simProgress, setSimProgress] = useState(0);

  const [benchmarkStatus, setBenchmarkStatus] = useState<BenchmarkStatus | null>(null);
  const [viewMode, setViewMode] = useState<'MAP' | '2D' | '3D' | 'SOURCES' | 'REPORT' | 'VALIDATION'>('MAP');

  // Simulation Source Mode (Authoritative Real-Time vs Manual Sliders)
  const [simulationMode, setSimulationMode] = useState<SimulationMode>('REAL_TIME');
  const [isManualModalOpen, setIsManualModalOpen] = useState(false);

  // Modals
  const [isNewProjectOpen, setIsNewProjectOpen] = useState(false);
  const [isDamSearchOpen, setIsDamSearchOpen] = useState(false);
  const [isAIPredictorOpen, setIsAIPredictorOpen] = useState(false);
  const [isBenchmarksOpen, setIsBenchmarksOpen] = useState(false);
  const [isCompareOpen, setIsCompareOpen] = useState(false);
  const [isExportOpen, setIsExportOpen] = useState(false);
  const [isSPHDelft3DOpen, setIsSPHDelft3DOpen] = useState(false);
  const [isGEEModalOpen, setIsGEEModalOpen] = useState(false);

  // 3D Timeline Sync
  const [currentTimeMin, setCurrentTimeMin] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  // The ONE global simulation clock's upper bound. Defaults to 360 but is
  // replaced by the selected dam's REAL authoritative arrival-time window
  // (timeline.t_max_min) so the slider spans exactly the simulated flood, not a
  // padded 6 h. Shared by the 2D map and the 3D twin (single source of truth).
  const [maxTimeMin, setMaxTimeMin] = useState(360);

  // Initial Load: Projects & Benchmark status
  useEffect(() => {
    api.getProjects().then(projs => {
      setProjects(projs);
      if (projs.length > 0) {
        setSelectedProject(projs[0]);
      }
    }).catch(console.error);

    api.getBenchmarkStatus().then(setBenchmarkStatus).catch(console.error);
  }, []);

  // Handle switching dam projects with strict state isolation.
  // selectedScenario MUST be cleared here: it belongs to the OUTGOING project.
  // If left set, the scenario-details effect re-applies the stale scenario id
  // against the new project and handleRunSimulation then POSTs a
  // new-project-uuid + foreign-scenario-uuid pair, which the backend correctly
  // rejects ("Scenario X does not belong to project Y"). Clearing it lets the
  // scenarios-load effect pick the new project's own scenarios[0] (or null).
  const handleSelectProject = (project: Project) => {
    setSelectedProject(project);
    setSelectedScenario(null);
    setSimulation(null);
    setCurrentTimeMin(0);
    setIsPlaying(false);
    setSimProgress(0);
  };

  // Launch the Digital Twin from the India map. The registry record is mapped
  // to the existing Project shape (the twin resolves its authoritative data by
  // slug). If a matching DB project exists, prefer it so scenarios/simulation
  // wiring stays intact; otherwise a minimal registry-backed project is used.
  // Normalize ANY registry-shaped record (from the map or DamSearchModal) into
  // the single Project object that the whole app uses. This is the ONLY place a
  // registry record becomes the active project, so every surface (Navbar, map,
  // scenario selector, 2D/3D/Report/Validation/Sources) reads the same identity.
  // If a matching DB project exists we reuse it (keeps scenarios/simulation
  // wiring intact); otherwise we build a minimal, field-normalized project so
  // Navbar's river_name/dam_name and the sim gate never read as blank.
  const resolveProject = (rec: any): Project => {
    const ref = String(rec.slug || rec.id || '').toLowerCase();
    const existing = projects.find(
      p => (p.slug || '').toLowerCase() === ref || p.id.toLowerCase() === ref
    );
    if (existing) return existing;
    return {
      id: rec.id,
      slug: rec.slug || rec.id,
      name: rec.name || rec.dam_name,
      dam_name: rec.dam_name || rec.name,
      river_name: rec.river_name || rec.river,
      state: rec.state,
      district: rec.district,
      dam_lat: rec.dam_lat ?? rec.latitude,
      dam_lon: rec.dam_lon ?? rec.longitude,
      dam_type: rec.dam_type || rec.type,
      simulation_enabled: rec.simulation_enabled ?? rec.has_simulation,
    } as unknown as Project;
  };

  // Single entry point for selecting a dam from any registry surface (map marker,
  // map search, or the Navbar DamSearchModal). Always flows into handleSelectProject.
  const handleSelectFromRegistry = (rec: any) => {
    handleSelectProject(resolveProject(rec));
  };

  const handleLaunchTwinFromMap = (dam: DamRegistryRecord) => {
    handleSelectFromRegistry(dam);
    setViewMode('3D');
  };

  // Load Scenarios when selected project changes
  useEffect(() => {
    if (!selectedProject?.id) return;
    api.getScenarios(selectedProject.id).then(scens => {
      setScenarios(scens);
      if (scens.length > 0) {
        setSelectedScenario(scens[0]);
      } else {
        setSelectedScenario(null);
      }
    }).catch(console.error);
  }, [selectedProject?.id]);

  // Resolve the REAL simulated time window for the selected dam from the
  // authoritative arrival_time raster (timeline.t_max_min). This drives the ONE
  // shared slider so 2D + 3D scrub over exactly the simulated flood duration.
  // Falls back to 360 when no verified timeline exists for the domain.
  useEffect(() => {
    const ref = selectedProject ? ((selectedProject as any).slug || selectedProject.id) : null;
    if (!ref) { setMaxTimeMin(360); return; }
    let cancelled = false;
    api.getTwinTimeline(ref, 40)
      .then(tl => {
        if (cancelled) return;
        const tmax = tl?.t_max_min;
        setMaxTimeMin(Number.isFinite(tmax) && tmax > 0 ? Math.ceil(tmax) : 360);
      })
      .catch(() => { if (!cancelled) setMaxTimeMin(360); });
    return () => { cancelled = true; };
  }, [selectedProject?.id]);

  // Load Scenario Details & Latest Simulation when scenario changes
  useEffect(() => {
    if (!selectedScenario?.id) return;
    api.getScenarioDetails(selectedScenario.id).then(scenFull => {
      setSelectedScenario(scenFull);
    }).catch(console.error);

    if (selectedProject?.id) {
      api.getLatestSimulation(selectedProject.id, selectedScenario.id).then(latestSim => {
        setSimulation(latestSim);
      }).catch(() => {
        setSimulation(null);
      });
    }
  }, [selectedScenario?.id, selectedProject?.id]);

  // Run Simulation Handler
  const handleRunSimulation = async () => {
    if (!selectedProject || !selectedScenario) return;
    setIsSimulating(true);
    setSimProgress(5);

    try {
      const runRes = await api.runSimulation(
        selectedProject.id,
        selectedScenario.id,
        'Hydrodynamic 2D Solver'
      );
      const simId = runRes.simulation_id;

      // Poll status
      const poll = setInterval(async () => {
        try {
          const statusRes = await api.getSimulationStatus(simId);
          setSimProgress(statusRes.progress);

          if (statusRes.status === 'COMPLETED') {
            clearInterval(poll);
            setIsSimulating(false);
            const fullResults = await api.getSimulationResults(simId);
            setSimulation(fullResults);
          } else if (statusRes.status === 'FAILED') {
            clearInterval(poll);
            setIsSimulating(false);
            alert(`Simulation Failed: ${statusRes.error_message}`);
          }
        } catch (err) {
          console.error('Polling error:', err);
        }
      }, 1000);
    } catch (err: any) {
      console.error(err);
      setIsSimulating(false);
      const msg = err.message || 'Failed to trigger simulation';
      alert(`Simulation unavailable:\n${msg}`);
    }
  };

  return (
    <div className="h-screen w-screen flex flex-col bg-slate-950 overflow-hidden font-sans select-none">
      {/* Top Navbar */}
      <Navbar
        projects={projects}
        selectedProject={selectedProject}
        onSelectProject={handleSelectProject}
        scenarios={scenarios}
        selectedScenario={selectedScenario}
        onSelectScenario={setSelectedScenario}
        benchmarkStatus={benchmarkStatus}
        viewMode={viewMode}
        onChangeViewMode={setViewMode}
        onOpenNewProject={() => setIsNewProjectOpen(true)}
        onOpenDamSearch={() => setIsDamSearchOpen(true)}
        onOpenAIPredictor={() => setIsAIPredictorOpen(true)}
        onOpenBenchmarks={() => setIsBenchmarksOpen(true)}
        onOpenCompare={() => setIsCompareOpen(true)}
        onOpenExport={() => setIsExportOpen(true)}
        onRunSimulation={handleRunSimulation}
        isSimulating={isSimulating}
        simulationMode={simulationMode}
        onOpenManualModal={() => setIsManualModalOpen(true)}
        onOpenSPHDelft3D={() => setIsSPHDelft3DOpen(true)}
        onOpenGEE={() => setIsGEEModalOpen(true)}
      />

      {/* Progress Bar when Simulating */}
      {isSimulating && (
        <div className="w-full bg-slate-900 h-1 overflow-hidden">
          <div
            className="bg-gradient-to-r from-blue-500 via-indigo-500 to-cyan-400 h-full transition-all duration-300"
            style={{ width: `${simProgress}%` }}
          />
        </div>
      )}

      {/* Main View Area */}
      <main className="flex-1 flex flex-col overflow-hidden relative">
        {viewMode === 'MAP' && (
          <IndiaDamMap
            selectedProject={selectedProject}
            onSelectDam={handleSelectFromRegistry}
            onLaunchTwin={handleLaunchTwinFromMap}
          />
        )}

        {viewMode === '2D' && (
          <ProjectView
            project={selectedProject}
            scenario={selectedScenario}
            simulation={simulation}
            onRefreshSimulation={() => {}}
            currentTimeMin={currentTimeMin}
            maxTimeMin={maxTimeMin}
            onChangeTime={setCurrentTimeMin}
            isPlaying={isPlaying}
            onTogglePlay={() => setIsPlaying(!isPlaying)}
            onOpenManualModal={() => setIsManualModalOpen(true)}
            simulationMode={simulationMode}
          />
        )}

        {viewMode === '3D' && (
          <DigitalTwin3D
            project={selectedProject}
            simulation={simulation}
            currentTimeMin={currentTimeMin}
            maxTimeMin={maxTimeMin}
            onChangeTime={setCurrentTimeMin}
            isPlaying={isPlaying}
            onTogglePlay={() => setIsPlaying(!isPlaying)}
            onOpenManualModal={() => setIsManualModalOpen(true)}
            simulationMode={simulationMode}
          />
        )}

        {viewMode === 'REPORT' && (
          <ReportView simulation={simulation} />
        )}

        {viewMode === 'VALIDATION' && (
          <ValidationView 
            simulation={simulation} 
            benchmarkStatus={benchmarkStatus}
            project={selectedProject}
          />
        )}

        {viewMode === 'SOURCES' && (
          <DataSourcesView project={selectedProject} />
        )}
      </main>

      {/* Modals */}
      <ManualSimulationModal
        isOpen={isManualModalOpen}
        onClose={() => setIsManualModalOpen(false)}
        project={selectedProject}
        selectedScenario={selectedScenario}
        onSelectScenario={(scen) => {
          setSelectedScenario(scen);
          if (!scenarios.some(s => s.id === scen.id)) {
            setScenarios(prev => [scen, ...prev]);
          }
        }}
        onRunSimulation={handleRunSimulation}
        simulationMode={simulationMode}
        onSetSimulationMode={(mode) => {
          setSimulationMode(mode);
          if (mode === 'REAL_TIME') {
            const baseline = scenarios.find(s => s.is_baseline) || scenarios[0];
            if (baseline) setSelectedScenario(baseline);
          }
        }}
        currentSimulation={simulation}
        isSimulating={isSimulating}
      />

      <NewProjectModal
        isOpen={isNewProjectOpen}
        onClose={() => setIsNewProjectOpen(false)}
        onProjectCreated={(p) => {
          setProjects(prev => [p, ...prev]);
          setSelectedProject(p);
        }}
      />

      <DamSearchModal
        isOpen={isDamSearchOpen}
        onClose={() => setIsDamSearchOpen(false)}
        onSelectProject={handleSelectFromRegistry}
        currentProjectId={selectedProject?.id}
      />

      <ErrorBoundary onError={() => setIsAIPredictorOpen(false)}>
        <AIPredictorModal
          isOpen={isAIPredictorOpen}
          onClose={() => setIsAIPredictorOpen(false)}
          project={selectedProject}
          simulation={simulation}
        />
      </ErrorBoundary>

      <SPHBenchmarkModal
        isOpen={isBenchmarksOpen}
        onClose={() => setIsBenchmarksOpen(false)}
        status={benchmarkStatus}
        onUpdateStatus={setBenchmarkStatus}
      />

      <ScenarioCompareModal
        isOpen={isCompareOpen}
        onClose={() => setIsCompareOpen(false)}
        scenarios={scenarios}
        simulation={simulation}
      />

      <ExportModal
        isOpen={isExportOpen}
        onClose={() => setIsExportOpen(false)}
        simulation={simulation}
      />

      <SPHDelft3DCompareModal
        isOpen={isSPHDelft3DOpen}
        onClose={() => setIsSPHDelft3DOpen(false)}
        project={selectedProject}
        simulation={simulation}
      />

      <GEEFloodAnalysisModal
        isOpen={isGEEModalOpen}
        onClose={() => setIsGEEModalOpen(false)}
        project={selectedProject}
      />
    </div>
  );
};

export default App;
