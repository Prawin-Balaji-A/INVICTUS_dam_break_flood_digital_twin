/**
 * main.ts — bootstrap + single rAF loop.
 */
import { Clock, Vector2 } from 'three';
import { Stage } from './core/Stage';
import { CameraRig } from './camera/CameraRig';
import { Terrain } from './terrain/Terrain';
import { Water } from './water/Water';
import { Dam } from './dam/Dam';
import { Spray } from './water/Spray';
import { Settlements } from './world/Settlements';
import { Markers } from './world/Markers';
import { Minimap } from './ui/Minimap';
import { ControlPanel } from './ui/ControlPanel';
import { Simulation } from './sim/Simulation';

const canvas = document.getElementById('scene') as HTMLCanvasElement;
const stage = new Stage(canvas);
const rig = new CameraRig(canvas);

// world
const terrain = new Terrain();
stage.scene.add(terrain.mesh);
stage.sun.target.position.set(0, 0, 300);
stage.sun.target.updateMatrixWorld();

const water = new Water(terrain.heightMap);
stage.scene.add(water.reservoir, water.downstream);

const spray = new Spray();
stage.scene.add(spray.mesh);

const settlements = new Settlements(terrain);
stage.scene.add(settlements.mesh);

const markers = new Markers(settlements.settlements);
stage.scene.add(markers.group);

const minimap = new Minimap(document.getElementById('minimap') as HTMLCanvasElement, terrain, settlements.settlements);

const dam = new Dam();
stage.scene.add(dam.root);

// panel callbacks delegate to the (soon-to-exist) simulation
let sim: Simulation;
const panel = new ControlPanel({
  onLevel: (f) => sim.setLevel(f, true),
  onPlay: () => sim.play(),
  onBreach: () => sim.forceBreach(),
  onOverview: () => sim.overview(),
  onReset: () => sim.reset(),
  onFocus: (id) => sim.focusById(id),
});

sim = new Simulation(dam, water, spray, settlements, markers, rig, panel, minimap);

// ---- marker picking (drag-guarded) ----
const pointer = new Vector2();
let down = { x: 0, y: 0, t: 0 };
canvas.addEventListener('pointerdown', (e) => {
  down = { x: e.clientX, y: e.clientY, t: performance.now() };
});
canvas.addEventListener('pointerup', (e) => {
  const dist = Math.hypot(e.clientX - down.x, e.clientY - down.y);
  if (dist > 6 || performance.now() - down.t > 450) return; // was a drag
  pointer.set((e.clientX / window.innerWidth) * 2 - 1, -(e.clientY / window.innerHeight) * 2 + 1);
  const hit = markers.pick(pointer, rig.camera);
  if (hit) sim.focusSettlement(hit);
});

// ---- resize ----
window.addEventListener('resize', () => {
  stage.resize();
  rig.resize();
});

// ---- load dam, then reveal + run ----
const loadingEl = document.getElementById('loading')!;
dam
  .load('/mettur-dam-only.glb')
  .then(() => {
    loadingEl.classList.add('hidden');
    panel.showHint('Drag to orbit • Raise the reservoir past the red line to breach • Click a name to fly in', 6000);
  })
  .catch((err) => {
    console.error('Failed to load dam GLB:', err);
    (loadingEl.querySelector('.ltext') as HTMLElement).textContent = 'Failed to load dam model — see console.';
  });

// ---- single loop ----
const clock = new Clock();
function tick(): void {
  const dt = Math.min(clock.getDelta(), 0.05);
  rig.update(dt);
  sim.update(dt);
  stage.renderer.render(stage.scene, rig.camera);
  requestAnimationFrame(tick);
}
requestAnimationFrame(tick);
