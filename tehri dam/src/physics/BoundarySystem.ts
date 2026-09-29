// ============================================================
// BoundarySystem.ts — Collision boundaries for terrain, dam,
// gates, and dynamic obstacles (landslide)
// ============================================================

import { CONFIG } from '../core/SimulationConfig';
import { clamp } from '../utils/MathUtils';

export interface BoundaryParams {
  gateOpenings: number[];      // 0–1 per gate
  breachActive: boolean;
  breachCenterX: number;       // m
  breachWidth: number;         // m
  breachHeight: number;        // m (measured from crest down)
  landslideActive: boolean;
  landslideY: number;          // m (position along river)
  landslideRadius: number;     // m
  landslideHeight: number;     // m
}

export function createDefaultBoundaryParams(): BoundaryParams {
  return {
    gateOpenings: [0, 0, 0, 0, 0],
    breachActive: false,
    breachCenterX: 0,
    breachWidth: 30,
    breachHeight: 40,
    landslideActive: false,
    landslideY: 300,
    landslideRadius: 40,
    landslideHeight: 25,
  };
}

/** Terrain heightfield — procedural valley with reservoir basin */
export class TerrainHeightfield {
  private data: Float32Array;
  private resX: number;
  private resZ: number; // Z in heightfield = Y in world (downstream direction)
  
  public xMin: number;
  public xMax: number;
  public yMin: number;  // world Y min (upstream)
  public yMax: number;  // world Y max (downstream)
  public cellSize: number;

  constructor() {
    this.xMin = -350;
    this.xMax = 350;
    this.yMin = -400;
    this.yMax = 600;
    this.cellSize = 4.0;
    
    this.resX = Math.ceil((this.xMax - this.xMin) / this.cellSize) + 1;
    this.resZ = Math.ceil((this.yMax - this.yMin) / this.cellSize) + 1;
    this.data = new Float32Array(this.resX * this.resZ);
    
    this.generateTerrain();
  }

  private generateTerrain(): void {
    for (let iz = 0; iz < this.resZ; iz++) {
      for (let ix = 0; ix < this.resX; ix++) {
        const x = this.xMin + ix * this.cellSize;
        const y = this.yMin + iz * this.cellSize;
        this.data[iz * this.resX + ix] = this.computeHeight(x, y);
      }
    }
  }

  /** Procedural terrain height function */
  computeHeight(x: number, y: number): number {
    // Reservoir basin (upstream, y < -14)
    // Valley sides rise with distance from centerline
    // River channel runs along x=0 downstream

    const absX = Math.abs(x);
    const damY = CONFIG.upstreamYTop; // -6
    
    // Base elevation: river bed slopes downstream
    let h: number;
    
    if (y < damY - 10) {
      // UPSTREAM RESERVOIR BASIN
      // Flat basin floor with rising valley walls
      const basinFloor = CONFIG.foundationZ + 5; // -13m
      const valleySlope = Math.max(0, (absX - 80) * 0.6);
      const bankRise = Math.max(0, (absX - 40) * 0.3);
      h = basinFloor + bankRise + valleySlope;
      
      // Gentle upstream slope
      const upstreamDist = Math.max(0, -(y + 50));
      h += upstreamDist * 0.02;
    } else if (y >= damY - 10 && y <= CONFIG.downstreamYToe + 20) {
      // DAM FOUNDATION ZONE — very low floor
      h = CONFIG.foundationZ - 30; // deep foundation
    } else {
      // DOWNSTREAM VALLEY
      const downDist = y - CONFIG.downstreamYToe;
      
      // River channel: V-shaped in cross section
      const channelHalfWidth = 35 + downDist * 0.08; // widening downstream
      const channelDepth = 15;
      
      let riverBed: number;
      if (absX < channelHalfWidth) {
        // Inside channel — parabolic cross-section
        const t = absX / channelHalfWidth;
        riverBed = -20 + channelDepth * t * t;
      } else {
        // Valley walls
        const wallDist = absX - channelHalfWidth;
        riverBed = -20 + channelDepth + wallDist * 0.5;
      }
      
      // Downstream slope (river drops)
      h = riverBed - downDist * 0.01;
      
      // Add some terrain irregularity
      const noiseX = Math.sin(x * 0.03) * Math.cos(y * 0.02) * 3;
      const noiseY = Math.sin(x * 0.07 + 1.5) * Math.sin(y * 0.05 + 0.8) * 2;
      h += noiseX + noiseY;
    }
    
    // Clamp minimum
    return Math.max(h, -50);
  }

  /** Get terrain height at world position (x, y) via bilinear interpolation */
  getHeight(x: number, y: number): number {
    const fx = (x - this.xMin) / this.cellSize;
    const fy = (y - this.yMin) / this.cellSize;
    
    const ix = clamp(Math.floor(fx), 0, this.resX - 2);
    const iy = clamp(Math.floor(fy), 0, this.resZ - 2);
    
    const tx = fx - ix;
    const ty = fy - iy;
    
    const h00 = this.data[iy * this.resX + ix];
    const h10 = this.data[iy * this.resX + ix + 1];
    const h01 = this.data[(iy + 1) * this.resX + ix];
    const h11 = this.data[(iy + 1) * this.resX + ix + 1];
    
    return (1 - tx) * (1 - ty) * h00 + tx * (1 - ty) * h10 +
           (1 - tx) * ty * h01 + tx * ty * h11;
  }

  /** Get the raw heightfield data for GPU upload / terrain mesh */
  getData(): Float32Array { return this.data; }
  getResX(): number { return this.resX; }
  getResZ(): number { return this.resZ; }
}

/** 
 * Enforce all boundary collisions on a particle.
 * Returns true if particle was modified.
 */
export function enforceBoundaries(
  px: number, py: number, pz: number,
  vx: number, vy: number, vz: number,
  terrain: TerrainHeightfield,
  params: BoundaryParams,
  out: { px: number; py: number; pz: number; vx: number; vy: number; vz: number }
): boolean {
  out.px = px; out.py = py; out.pz = pz;
  out.vx = vx; out.vy = vy; out.vz = vz;
  
  let modified = false;
  const restitution = 0.3;
  const friction = 0.95;

  // 1. TERRAIN COLLISION
  if (px >= terrain.xMin && px <= terrain.xMax && py >= terrain.yMin && py <= terrain.yMax) {
    const terrainH = terrain.getHeight(px, py);
    if (pz < terrainH + CONFIG.particleRadius) {
      out.pz = terrainH + CONFIG.particleRadius;
      if (vz < 0) {
        out.vz = -vz * restitution;
        out.vx *= friction;
        out.vy *= friction;
      }
      modified = true;
    }
  }

  // 2. DAM COLLISION
  // Dam body: upstream face (y = upstreamYBot..upstreamYTop) to downstream face
  // Only blocks particles if gates are closed and no breach
  const damXMin = -CONFIG.damLengthHalf;
  const damXMax = CONFIG.damLengthHalf;
  
  if (px >= damXMin && px <= damXMax) {
    // Check if in dam Y range
    const zFrac = clamp((pz - CONFIG.foundationZ) / (CONFIG.crestZ - CONFIG.foundationZ), 0, 1);
    const upstreamY = CONFIG.upstreamYBot + zFrac * (CONFIG.upstreamYTop - CONFIG.upstreamYBot);
    const downstreamY = CONFIG.downstreamYTop + (1 - zFrac) * (CONFIG.downstreamYToe - CONFIG.downstreamYTop);
    
    // Check if within spillway region
    const inSpillway = Math.abs(px) < CONFIG.spillHalf;
    
    // Check gate openings
    let gateOpen = false;
    if (inSpillway) {
      const bayWidth = (CONFIG.spillHalf * 2 - 8 * 2 - (CONFIG.nBays - 1) * 3.5) / CONFIG.nBays;
      const innerHalf = CONFIG.spillHalf - 8;
      let bx = -innerHalf;
      for (let g = 0; g < CONFIG.nBays; g++) {
        const bayCenter = bx + bayWidth * 0.5;
        if (Math.abs(px - bayCenter) < bayWidth * 0.4) {
          const opening = params.gateOpenings[g] || 0;
          // Gate opens from spillway crest downward
          const gateTop = CONFIG.spillCrestZ;
          const gateOpenHeight = opening * 15; // max 15m opening
          if (pz < gateTop && pz > gateTop - gateOpenHeight) {
            gateOpen = true;
          }
        }
        bx += bayWidth + 3.5;
      }
    }
    
    // Check breach
    let inBreach = false;
    if (params.breachActive) {
      const bx = params.breachCenterX;
      const bw = params.breachWidth * 0.5;
      const breachTop = CONFIG.crestZ;
      const breachBot = CONFIG.crestZ - params.breachHeight;
      if (px > bx - bw && px < bx + bw && pz < breachTop && pz > breachBot) {
        inBreach = true;
      }
    }
    
    // If not through a gate or breach, block
    if (!gateOpen && !inBreach) {
      if (pz >= CONFIG.foundationZ && pz <= CONFIG.crestZ) {
        // Block at upstream face
        if (py > upstreamY - 2 && py < upstreamY + 2) {
          out.py = upstreamY - CONFIG.particleRadius;
          if (vy > 0) {
            out.vy = -vy * restitution;
          }
          modified = true;
        }
        // Block at downstream face (for reverse flow)
        if (py > downstreamY - 2 && py < downstreamY + 2 && vy < 0) {
          out.py = downstreamY + CONFIG.particleRadius;
          out.vy = -vy * restitution;
          modified = true;
        }
      }
    }
  }

  // 3. LANDSLIDE BLOCKAGE
  if (params.landslideActive) {
    const dx = px - 0; // landslide centered on x=0
    const dy = py - params.landslideY;
    const distSq = dx * dx + dy * dy;
    const r = params.landslideRadius;
    if (distSq < r * r) {
      const dist = Math.sqrt(distSq);
      const blockageTop = terrain.getHeight(px, py) + params.landslideHeight * (1 - dist / r);
      if (pz < blockageTop) {
        out.pz = blockageTop + CONFIG.particleRadius;
        if (vz < 0) out.vz = -vz * restitution;
        out.vx *= friction;
        out.vy *= friction;
        modified = true;
      }
    }
  }

  // 4. WORLD BOUNDS (keep particles in simulation domain)
  const margin = CONFIG.particleRadius;
  if (out.px < terrain.xMin + margin) { out.px = terrain.xMin + margin; out.vx = Math.abs(out.vx) * restitution; modified = true; }
  if (out.px > terrain.xMax - margin) { out.px = terrain.xMax - margin; out.vx = -Math.abs(out.vx) * restitution; modified = true; }
  if (out.py < terrain.yMin + margin) { out.py = terrain.yMin + margin; out.vy = Math.abs(out.vy) * restitution; modified = true; }
  if (out.py > terrain.yMax - margin) { out.py = terrain.yMax - margin; out.vy = -Math.abs(out.vy) * restitution; modified = true; }
  if (out.pz < -45) { out.pz = -45; out.vz = Math.abs(out.vz) * restitution; modified = true; }

  return modified;
}
