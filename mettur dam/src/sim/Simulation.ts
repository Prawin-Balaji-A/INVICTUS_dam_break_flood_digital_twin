/**
 * Simulation.ts — state machine wiring the whole sim together.
 * IDLE -> FILLING -> SPILLING (gates open) -> BREACHING -> FLOODED (+ RESET).
 * Owns water level / flood front; ticks dam, water, spray, settlements, markers,
 * minimap and the control panel each frame.
 */
import { Dam } from '../dam/Dam';
import { Water } from '../water/Water';
import { Spray } from '../water/Spray';
import { Settlements, SettlementRuntime } from '../world/Settlements';
import { Markers } from '../world/Markers';
import { CameraRig } from '../camera/CameraRig';
import { ControlPanel } from '../ui/ControlPanel';
import { Minimap } from '../ui/Minimap';
import { WATER, SPRAY, DAM } from '../config';

type State = 'IDLE' | 'FILLING' | 'SPILLING' | 'BREACHING' | 'FLOODED';
const SPILL_REF = 40;
const clamp = (v: number, a: number, b: number) => (v < a ? a : v > b ? b : v);

export class Simulation {
  state: State = 'IDLE';
  private levelFrac = WATER.startLevel;
  private targetFrac = WATER.startLevel;
  private threshold = WATER.thresholdLevel;

  private floodReach = -1e5;
  private floodMix = 0;
  private floodSheetY = WATER.reservoirFloorY;
  private breached = false;
  private userTouched = false;

  private prevFlooded = new Map<string, boolean>();

  constructor(
    private dam: Dam,
    private water: Water,
    private spray: Spray,
    private settlements: Settlements,
    private markers: Markers,
    private rig: CameraRig,
    private panel: ControlPanel,
    private minimap: Minimap,
  ) {
    this.panel.setThreshold(this.threshold);
    this.panel.setLevel(this.levelFrac);
    this.panel.setStatus('Idle', '');
    this.panel.setBreachEnabled(false);
    for (const s of this.settlements.settlements) this.prevFlooded.set(s.id, false);
    // apply the initial reservoir level immediately so the site opens "full"
    this.water.setReservoirLevel(this.levelToY(this.levelFrac));
  }

  private levelToY(frac: number): number {
    return WATER.reservoirFloorY + (WATER.reservoirMaxY - WATER.reservoirFloorY) * frac;
  }
  // ---------------- public API (wired to the panel in main.ts) ----------------
  setLevel(frac: number, fromUser = false): void {
    this.targetFrac = frac;
    if (fromUser) this.userTouched = true;
    if (this.state === 'IDLE' && !this.breached) this.state = 'FILLING';
  }

  play(): void {
    if (this.breached) return;
    this.dam.openGates();
    if (this.state !== 'BREACHING' && this.state !== 'FLOODED') this.state = 'SPILLING';
    this.panel.setPlayLabel('Gates Opening…', true);
    this.panel.setStatus('Spilling', 'spill');
    this.panel.showHint('Gates opening — water spills through the spillway into the river below.');
  }

  forceBreach(): void {
    if (this.breached) return;
    this.triggerBreach();
  }

  overview(): void {
    this.rig.overview();
    this.panel.hideFocus();
  }

  focusById(id: string): void {
    const s = this.settlements.settlements.find((x) => x.id === id);
    if (s) this.focusSettlement(s);
  }

  focusSettlement(s: SettlementRuntime): void {
    this.rig.focus(s);
    this.panel.showFocus(s.name);
    this.panel.showHint(`Flying to <b>${s.name}</b>.`);
  }

  private headNorm(): number {
    const head = this.water.reservoirY - SPILL_REF;
    return clamp(head / (WATER.reservoirMaxY - SPILL_REF), 0, 1);
  }

  private triggerBreach(): void {
    if (this.breached) return;
    this.breached = true;
    this.state = 'BREACHING';
    const hn = this.headNorm();
    this.dam.startBreach(hn);
    this.spray.burst(this.dam.breachCenter, SPRAY.breachBurstCount, 130);
    this.rig.shake(7, 1.3);
    this.floodReach = 0;
    this.panel.setStatus('DAM BREACHED', 'breach');
    this.panel.setBreachEnabled(false);
    this.panel.showHint('<b>The dam has breached!</b> Flood surging downstream — watch the villages.', 5200);
  }

  update(dt: number): void {
    // reservoir fill
    this.levelFrac += (this.targetFrac - this.levelFrac) * Math.min(1, WATER.fillLerp * dt);
    if (Math.abs(this.levelFrac - this.targetFrac) < 0.001) this.levelFrac = this.targetFrac;
    const resY = this.levelToY(this.levelFrac);
    this.water.setReservoirLevel(resY);
    if (!this.userTouched) this.panel.setLevel(this.levelFrac);

    if (this.state === 'FILLING' && this.levelFrac >= this.targetFrac - 0.005 && !this.breached) {
      this.state = this.dam.gatesOpenFraction() > 0.01 ? 'SPILLING' : 'IDLE';
      if (this.state === 'IDLE') this.panel.setStatus('Holding', '');
    }

    // gates + jet spray
    const gf = this.dam.gatesOpenFraction();
    const hn = this.headNorm();
    if (gf > 0.99 && this.state === 'SPILLING') this.panel.setPlayLabel('Gates Open', true);
    this.spray.emitJets(this.dam.jetPoints, gf * Math.min(1, 0.25 + hn), dt);

    // breach triggers
    if (!this.breached && this.levelFrac >= this.threshold) this.triggerBreach();
    this.panel.setBreachEnabled(!this.breached && this.levelFrac >= 0.6);

    // flood advance — radial spread fanning out from the breach toward the towns
    if (this.breached) {
      const speed = WATER.floodBaseSpeed + WATER.floodHeadSpeed * hn;
      this.floodReach = Math.min(WATER.floodMaxReach, this.floodReach + speed * dt);
      this.floodMix = Math.min(1, this.floodMix + dt * 0.5);
      this.floodSheetY = Math.min(20, this.floodSheetY + dt * 6);
      this.water.setFlood(this.floodReach, Math.max(this.floodSheetY, WATER.reservoirFloorY), this.floodMix);
      this.settlements.setFlood(this.floodReach, this.floodSheetY, DAM.axisX, DAM.wallZ);
      if (this.floodReach >= WATER.floodMaxReach && this.state === 'BREACHING') {
        this.state = 'FLOODED';
        this.panel.setStatus('Flooded', 'breach');
      }
    }

    // tick actors
    this.dam.update(dt);
    this.water.update(dt);
    this.spray.update(dt);
    this.markers.update(this.rig.camera);

    // village flood transitions
    let flooded = 0;
    for (const s of this.settlements.settlements) {
      const f = s.isFlooded;
      if (f) flooded++;
      if (f !== this.prevFlooded.get(s.id)) {
        this.prevFlooded.set(s.id, f);
        this.panel.setVillageState(s.id, f);
        if (f) this.panel.showHint(`⚠ <b>${s.name}</b> is being flooded!`, 3200);
      }
    }

    // metrics + minimap
    const head = Math.max(0, resY - SPILL_REF);
    const flow = this.breached ? 300 + hn * 900 : gf * (120 + hn * 480);
    this.panel.setMetrics({ head, gates: gf * 100, flow, flooded });
    this.minimap.update(this.rig.camera.position, this.rig.controls.target, this.levelFrac, this.floodReach, this.floodMix);
  }

  reset(): void {
    this.state = 'IDLE';
    this.breached = false;
    this.userTouched = false;
    this.floodReach = -1e5;
    this.floodMix = 0;
    this.floodSheetY = WATER.reservoirFloorY;
    this.levelFrac = this.targetFrac = WATER.startLevel;
    this.dam.reset();
    this.spray.reset();
    this.settlements.reset();
    this.markers.resetFlooded();
    this.water.setFlood(-1e5, WATER.reservoirFloorY, 0);
    this.water.setReservoirLevel(this.levelToY(this.levelFrac));
    this.panel.setLevel(this.levelFrac);
    this.panel.setStatus('Idle', '');
    this.panel.setPlayLabel('▶ Open Gates', false);
    this.panel.setBreachEnabled(false);
    this.panel.hideFocus();
    for (const s of this.settlements.settlements) {
      this.prevFlooded.set(s.id, false);
      this.panel.setVillageState(s.id, false);
    }
    this.rig.overview();
    this.panel.showHint('Reset — reservoir refilled, dam restored.');
  }
}
