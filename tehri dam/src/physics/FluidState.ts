// ============================================================
// FluidState.ts — Particle buffer management and fluid metrics
// ============================================================

import { CONFIG } from '../core/SimulationConfig';

export interface FluidMetrics {
  particleCount: number;
  totalVolume: number;       // m³
  initialVolume: number;     // m³
  volumeDiff: number;        // %
  maxVelocity: number;       // m/s
  avgVelocity: number;       // m/s
  maxDepth: number;          // m
  reservoirLevel: number;    // m
  discharge: number;         // m³/s
  simTime: number;           // s
  solverTimeMs: number;      // ms per step
}

export class FluidState {
  // Particle data arrays (AoS layout for GPU)
  positions: Float32Array;     // [x,y,z,w] × maxParticles
  velocities: Float32Array;    // [vx,vy,vz,w] × maxParticles
  predictedPos: Float32Array;  // [px,py,pz,w] × maxParticles
  densities: Float32Array;     // [ρ] × maxParticles
  lambdas: Float32Array;       // [λ] × maxParticles
  
  particleCount: number = 0;
  initialVolume: number = 0;
  simTime: number = 0;
  solverTimeMs: number = 0;

  constructor(public maxParticles: number) {
    this.positions = new Float32Array(maxParticles * 4);
    this.velocities = new Float32Array(maxParticles * 4);
    this.predictedPos = new Float32Array(maxParticles * 4);
    this.densities = new Float32Array(maxParticles);
    this.lambdas = new Float32Array(maxParticles);
  }

  /** Add a particle at position with zero velocity */
  addParticle(x: number, y: number, z: number): boolean {
    if (this.particleCount >= this.maxParticles) return false;
    const i = this.particleCount;
    const i4 = i * 4;
    this.positions[i4] = x;
    this.positions[i4 + 1] = y;
    this.positions[i4 + 2] = z;
    this.positions[i4 + 3] = 1.0; // w = active
    this.velocities[i4] = 0;
    this.velocities[i4 + 1] = 0;
    this.velocities[i4 + 2] = 0;
    this.velocities[i4 + 3] = 0;
    this.particleCount++;
    return true;
  }

  /** Initialize a block of particles for the reservoir */
  initReservoir(
    xMin: number, xMax: number,
    yMin: number, yMax: number,
    zMin: number, zMax: number,
    spacing: number
  ): number {
    let count = 0;
    const jitter = spacing * 0.1;
    for (let x = xMin; x <= xMax; x += spacing) {
      for (let y = yMin; y <= yMax; y += spacing) {
        for (let z = zMin; z <= zMax; z += spacing) {
          const jx = x + (Math.random() - 0.5) * jitter;
          const jy = y + (Math.random() - 0.5) * jitter;
          const jz = z + (Math.random() - 0.5) * jitter;
          if (this.addParticle(jx, jy, jz)) count++;
        }
      }
    }
    this.initialVolume = count * Math.pow(spacing, 3);
    return count;
  }

  /** Reset all particles */
  reset(): void {
    this.positions.fill(0);
    this.velocities.fill(0);
    this.predictedPos.fill(0);
    this.densities.fill(0);
    this.lambdas.fill(0);
    this.particleCount = 0;
    this.initialVolume = 0;
    this.simTime = 0;
  }

  /** Compute current metrics */
  getMetrics(): FluidMetrics {
    let maxVel = 0, sumVel = 0, maxDepth = 0;
    let minReservoirZ = Infinity, maxReservoirZ = -Infinity;
    
    for (let i = 0; i < this.particleCount; i++) {
      const i4 = i * 4;
      const vx = this.velocities[i4];
      const vy = this.velocities[i4 + 1];
      const vz = this.velocities[i4 + 2];
      const vel = Math.sqrt(vx * vx + vy * vy + vz * vz);
      if (vel > maxVel) maxVel = vel;
      sumVel += vel;
      
      const z = this.positions[i4 + 2];
      const y = this.positions[i4 + 1];
      
      // Track reservoir particles (upstream of dam)
      if (y < CONFIG.upstreamYTop) {
        if (z > maxReservoirZ) maxReservoirZ = z;
      }
    }

    const spacing = CONFIG.particleSpacing;
    const particleVol = Math.pow(spacing, 3);
    const totalVolume = this.particleCount * particleVol;

    return {
      particleCount: this.particleCount,
      totalVolume,
      initialVolume: this.initialVolume,
      volumeDiff: this.initialVolume > 0 
        ? ((totalVolume - this.initialVolume) / this.initialVolume) * 100 
        : 0,
      maxVelocity: maxVel,
      avgVelocity: this.particleCount > 0 ? sumVel / this.particleCount : 0,
      maxDepth,
      reservoirLevel: maxReservoirZ > -Infinity ? maxReservoirZ : CONFIG.reservoirWaterZ,
      discharge: 0, // computed externally
      simTime: this.simTime,
      solverTimeMs: this.solverTimeMs,
    };
  }
}
