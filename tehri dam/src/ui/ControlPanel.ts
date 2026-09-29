// ============================================================
// ControlPanel.ts — lil-gui based control interface
// ============================================================

import GUI from 'lil-gui';
import { CONFIG } from '../core/SimulationConfig';
import { ScenarioManager, PRESETS } from '../scenarios/ScenarioManager';
import { DamComponents } from '../dam/DamGeometry';
import { WaterRenderer } from '../rendering/WaterRenderer';
import { CameraSystem, CameraMode } from '../scene/CameraSystem';
import { FluidState } from '../physics/FluidState';
import { TerrainHeightfield } from '../physics/BoundarySystem';

export interface SimControls {
  playing: boolean;
  timeScale: number;
  scenario: number;
  // Gate controls
  gate1: number;
  gate2: number;
  gate3: number;
  gate4: number;
  gate5: number;
  // Breach
  breachWidth: number;
  breachHeight: number;
  breachGrowthRate: number;
  // Visualization
  debugMode: boolean;
  showFoam: boolean;
  camera: string;
}

export function createControlPanel(
  scenarioManager: ScenarioManager,
  damComponents: DamComponents,
  waterRenderer: WaterRenderer,
  cameraSystem: CameraSystem,
  fluidState: FluidState,
  terrain: TerrainHeightfield,
  onReset: () => void,
): { gui: GUI; controls: SimControls } {
  
  const controls: SimControls = {
    playing: false,
    timeScale: 1.0,
    scenario: 0,
    gate1: 0, gate2: 0, gate3: 0, gate4: 0, gate5: 0,
    breachWidth: 30,
    breachHeight: 40,
    breachGrowthRate: 0,
    debugMode: false,
    showFoam: true,
    camera: 'free',
  };

  const gui = new GUI({ title: '⚙ Dam Simulator', width: 300 });
  gui.domElement.style.fontFamily = "'Inter', sans-serif";

  // === SCENARIO ===
  const scenarioFolder = gui.addFolder('📋 Scenario');
  const presetNames = PRESETS.map((p, i) => `${i + 1}. ${p.name}`);
  scenarioFolder.add(controls, 'scenario', Object.fromEntries(presetNames.map((n, i) => [n, i])))
    .name('Preset')
    .onChange((v: number) => {
      scenarioManager.loadPreset(v, fluidState, terrain, damComponents);
      controls.gate1 = PRESETS[v].gateOpenings[0];
      controls.gate2 = PRESETS[v].gateOpenings[1];
      controls.gate3 = PRESETS[v].gateOpenings[2];
      controls.gate4 = PRESETS[v].gateOpenings[3];
      controls.gate5 = PRESETS[v].gateOpenings[4];
      gui.controllersRecursive().forEach(c => c.updateDisplay());
    });

  // === SIMULATION ===
  const simFolder = gui.addFolder('▶ Simulation');
  simFolder.add(controls, 'playing').name('Play').listen();
  simFolder.add(controls, 'timeScale', 0.1, 5, 0.1).name('Time Scale');
  simFolder.add({ reset: () => {
    scenarioManager.loadPreset(controls.scenario, fluidState, terrain, damComponents);
    onReset();
  }}, 'reset').name('🔄 Reset');
  simFolder.add({ step: () => { controls.playing = false; /* single step handled in main loop */ }}, 'step').name('⏭ Step');

  // === WATER PHYSICS ===
  const waterFolder = gui.addFolder('💧 Water Physics');
  waterFolder.add(CONFIG, 'gravity', 1, 20, 0.1).name('Gravity (m/s²)');
  waterFolder.add(CONFIG, 'waterDensity', 500, 2000, 10).name('Density (kg/m³)');
  waterFolder.add(CONFIG, 'viscosity', 0, 0.1, 0.001).name('Viscosity');
  waterFolder.add(CONFIG, 'solverIterations', 1, 10, 1).name('Solver Iters');
  waterFolder.close();

  // === DAM GATES ===
  const gateFolder = gui.addFolder('🚪 Dam Gates');
  const gateProps = ['gate1', 'gate2', 'gate3', 'gate4', 'gate5'] as const;
  gateProps.forEach((prop, i) => {
    gateFolder.add(controls, prop, 0, 1, 0.01)
      .name(`Gate ${i + 1}`)
      .onChange((v: number) => {
        scenarioManager.setGateOpening(i, v, damComponents);
      });
  });
  const openAll = { openAll: () => {
    gateProps.forEach((p, i) => {
      controls[p] = 1;
      scenarioManager.setGateOpening(i, 1, damComponents);
    });
    gui.controllersRecursive().forEach(c => c.updateDisplay());
  }};
  gateFolder.add(openAll, 'openAll').name('Open All Gates');

  // === DAM BREACH ===
  const breachFolder = gui.addFolder('💥 Dam Breach');
  breachFolder.add(controls, 'breachWidth', 5, 200, 1).name('Width (m)');
  breachFolder.add(controls, 'breachHeight', 5, 138, 1).name('Height (m)');
  breachFolder.add(controls, 'breachGrowthRate', 0, 10, 0.1).name('Growth Rate (m/s)');
  breachFolder.add({
    trigger: () => {
      scenarioManager.triggerBreach(controls.breachWidth, controls.breachHeight, controls.breachGrowthRate);
    }
  }, 'trigger').name('🔴 Trigger Breach');
  breachFolder.close();

  // === LANDSLIDE ===
  const slideFolder = gui.addFolder('⛰ Landslide');
  slideFolder.add({
    trigger: () => { scenarioManager.triggerLandslide(); }
  }, 'trigger').name('🔴 Trigger Landslide');
  slideFolder.close();

  // === VISUALIZATION ===
  const visFolder = gui.addFolder('👁 Visualization');
  visFolder.add(controls, 'debugMode').name('Debug Particles')
    .onChange((v: boolean) => waterRenderer.setDebugMode(v));
  visFolder.add(controls, 'showFoam').name('Show Foam')
    .onChange((v: boolean) => waterRenderer.setFoamVisible(v));
  
  // Camera modes
  const cameraModes: Record<string, CameraMode> = {
    'Free Orbit': 'free',
    'Dam View': 'dam',
    'Downstream': 'downstream',
    'Overhead': 'overhead',
    'Cinematic': 'cinematic',
    'Follow Water': 'followWater',
  };
  visFolder.add(controls, 'camera', Object.keys(cameraModes)).name('Camera')
    .onChange((v: string) => {
      cameraSystem.setMode(cameraModes[v]);
    });

  return { gui, controls };
}
