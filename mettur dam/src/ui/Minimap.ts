/**
 * Minimap.ts — top-down 2D canvas. Reservoir at top (-Z), downstream valley at
 * bottom (+Z). Shows the dam line, reservoir (scaled by level), meander river,
 * an advancing flood fill, village dots (red when flooded) and the camera.
 */
import { Vector3 } from 'three';
import { Terrain } from '../terrain/Terrain';
import { SettlementRuntime } from '../world/Settlements';
import { WORLD, DAM, WATER } from '../config';

export class Minimap {
  private ctx: CanvasRenderingContext2D;
  private w: number;
  private h: number;
  private terrain: Terrain;
  private settlements: SettlementRuntime[];
  private minX: number;
  private minZ: number;
  private sizeX: number;
  private sizeZ: number;

  constructor(canvas: HTMLCanvasElement, terrain: Terrain, settlements: SettlementRuntime[]) {
    this.ctx = canvas.getContext('2d')!;
    this.w = canvas.width;
    this.h = canvas.height;
    this.terrain = terrain;
    this.settlements = settlements;
    this.minX = -WORLD.terrainSizeX / 2;
    this.minZ = -WORLD.terrainSizeZ / 2;
    this.sizeX = WORLD.terrainSizeX;
    this.sizeZ = WORLD.terrainSizeZ;
  }

  private cx(x: number): number {
    return ((x - this.minX) / this.sizeX) * this.w;
  }
  private cy(z: number): number {
    return ((z - this.minZ) / this.sizeZ) * this.h;
  }

  update(camPos: Vector3, camTarget: Vector3, reservoirFrac: number, floodReach: number, floodMix: number): void {
    const ctx = this.ctx;
    ctx.clearRect(0, 0, this.w, this.h);

    // land background
    const g = ctx.createLinearGradient(0, 0, 0, this.h);
    g.addColorStop(0, '#25331f');
    g.addColorStop(0.5, '#2f3f26');
    g.addColorStop(1, '#39482c');
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, this.w, this.h);

    // reservoir (upstream, z<0) — width + reach scale with level
    const resTop = this.cy(-WORLD.terrainSizeZ / 2 + 100);
    const resBottom = this.cy(DAM.wallZ);
    const resW = (0.35 + 0.5 * reservoirFrac) * this.w;
    ctx.fillStyle = '#1c6fd0';
    ctx.globalAlpha = 0.85;
    ctx.beginPath();
    ctx.ellipse(this.w / 2, (resTop + resBottom) / 2, resW / 2, (resBottom - resTop) / 2, 0, 0, Math.PI * 2);
    ctx.fill();
    ctx.globalAlpha = 1;

    // downstream meander river
    ctx.strokeStyle = '#3fa9f5';
    ctx.lineWidth = 3;
    ctx.beginPath();
    for (let z = 0; z <= this.sizeZ / 2; z += 40) {
      const x = this.terrain.riverCenterX(z);
      const px = this.cx(x);
      const py = this.cy(z);
      if (z === 0) ctx.moveTo(px, py);
      else ctx.lineTo(px, py);
    }
    ctx.stroke();

    // flood — radial spread fanning out from the breach (downstream-biased blob)
    if (floodReach > 0 && floodMix > 0.01) {
      const reach = Math.min(floodReach, WATER.floodMaxReach);
      const downR = reach * 1.83; // +Z extent
      const upR = reach * 0.41; // -Z extent (barely backs up)
      const latR = reach * 0.93; // lateral extent
      const czWorld = DAM.wallZ + (downR - upR) / 2;
      const rzWorld = (downR + upR) / 2;
      const rxPx = this.cx(DAM.axisX + latR) - this.cx(DAM.axisX);
      const ryPx = this.cy(DAM.wallZ + rzWorld) - this.cy(DAM.wallZ);
      ctx.beginPath();
      ctx.ellipse(this.cx(DAM.axisX), this.cy(czWorld), rxPx, ryPx, 0, 0, Math.PI * 2);
      ctx.fillStyle = `rgba(120, 150, 200, ${0.26 + 0.28 * floodMix})`;
      ctx.fill();
      ctx.strokeStyle = `rgba(150, 110, 70, ${0.6 * floodMix})`;
      ctx.lineWidth = 3;
      ctx.stroke();
    }

    // dam line
    const damHalf = this.cx(DAM.axisX + DAM.targetCrestLength / 2) - this.cx(DAM.axisX);
    ctx.strokeStyle = '#e6e6e6';
    ctx.lineWidth = 4;
    ctx.beginPath();
    ctx.moveTo(this.cx(DAM.axisX) - damHalf, this.cy(DAM.wallZ));
    ctx.lineTo(this.cx(DAM.axisX) + damHalf, this.cy(DAM.wallZ));
    ctx.stroke();

    // settlement dots + labels
    ctx.font = '9px -apple-system, Segoe UI, sans-serif';
    ctx.textAlign = 'center';
    for (const s of this.settlements) {
      const px = this.cx(s.center.x);
      const py = this.cy(s.center.z);
      const flooded = s.isFlooded;
      ctx.beginPath();
      ctx.arc(px, py, s.type === 'town' ? 6 : 4, 0, Math.PI * 2);
      ctx.fillStyle = flooded ? '#ff5a48' : `#${s.color.toString(16).padStart(6, '0')}`;
      ctx.fill();
      ctx.lineWidth = 1.5;
      ctx.strokeStyle = 'rgba(0,0,0,0.5)';
      ctx.stroke();
      ctx.fillStyle = flooded ? '#ffb0a6' : '#d8e4f0';
      ctx.fillText(s.name, px, py - 8);
    }

    // camera marker + view direction
    const cpx = this.cx(camPos.x);
    const cpy = this.cy(camPos.z);
    const dx = camTarget.x - camPos.x;
    const dz = camTarget.z - camPos.z;
    const len = Math.hypot(dx, dz) || 1;
    ctx.strokeStyle = '#ffd54a';
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(cpx, cpy);
    ctx.lineTo(cpx + (dx / len) * 22, cpy + (dz / len) * 22);
    ctx.stroke();
    ctx.beginPath();
    ctx.arc(cpx, cpy, 4, 0, Math.PI * 2);
    ctx.fillStyle = '#ffd54a';
    ctx.fill();
  }
}
