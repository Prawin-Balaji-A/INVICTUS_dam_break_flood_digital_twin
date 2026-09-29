// ============================================================
// main.ts — Application entry point: Map → 3D Simulation
// ============================================================

import { IndiaMapUI } from './map/IndiaMap';
import { App } from './core/App';
import { DamInfo, INDIAN_DAMS } from './map/DamData';

let mapUI: IndiaMapUI | null = null;
let simApp: App | null = null;

function showMap(): void {
  if (mapUI) {
    mapUI.show();
  } else {
    mapUI = new IndiaMapUI({
      onDamSelected: (dam: DamInfo) => {
        // Transition from map to 3D simulation
        if (mapUI) mapUI.hide();
        launchSimulation(dam);
      }
    });
  }
}

async function launchSimulation(dam: DamInfo): Promise<void> {
  // Remove loading screen if present
  const loadingScreen = document.getElementById('loading-screen');
  if (loadingScreen) loadingScreen.remove();

  simApp = new App();
  try {
    await simApp.start(dam);
  } catch (err) {
    console.error('[Dam Simulator] Error:', err);
    alert(`Failed to load simulation: ${(err as Error).message}`);
    if (simApp) simApp.destroy();
    // showMap();
  }
}

// Listen for back-to-map event
window.addEventListener('back-to-map', () => {
  // showMap();
});

// Hide loading screen, show map
const loadingScreen = document.getElementById('loading-screen');
if (loadingScreen) {
  loadingScreen.classList.add('hidden');
  setTimeout(() => loadingScreen.remove(), 600);
}

// Launch directly with Tehri Dam
const tehriDam = INDIAN_DAMS.find(d => d.name === "Tehri Dam") || INDIAN_DAMS[0];
launchSimulation(tehriDam);
