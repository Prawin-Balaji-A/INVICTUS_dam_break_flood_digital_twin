// ============================================================
// PBFSolver.ts — Position Based Fluids solver (CPU version)
// 
// Implements the Macklin & Müller 2013 PBF algorithm:
//   1. Apply gravity, predict positions
//   2. Build spatial hash grid
//   3. Iterative density constraint solve (λ + Δp)
//   4. Update velocities, apply XSPH viscosity
//   5. Enforce boundary collisions
//
// This is the CPU reference implementation. The GPU version
// runs identically but on WebGPU compute shaders.
// ============================================================

import { CONFIG } from '../core/SimulationConfig';
import { FluidState } from './FluidState';
import { TerrainHeightfield, BoundaryParams, enforceBoundaries } from './BoundarySystem';
import { poly6Constant, spikyGradConstant } from '../utils/MathUtils';

/** Spatial hash grid for O(N) neighbor search */
class SpatialGrid {
  private cellStart: Int32Array;
  private cellEnd: Int32Array;
  private sortedIndices: Int32Array;
  private particleCells: Int32Array;
  
  private tableSize: number;
  private cellSize: number;

  constructor(maxParticles: number) {
    this.tableSize = CONFIG.hashTableSize;
    this.cellSize = CONFIG.hashGridCellSize;
    this.cellStart = new Int32Array(this.tableSize);
    this.cellEnd = new Int32Array(this.tableSize);
    this.sortedIndices = new Int32Array(maxParticles);
    this.particleCells = new Int32Array(maxParticles);
  }

  /** Hash function for cell coordinates */
  private hash(cx: number, cy: number, cz: number): number {
    return ((cx * 73856093 ^ cy * 19349663 ^ cz * 83492791) & 0x7FFFFFFF) % this.tableSize;
  }

  /** Build the grid from current predicted positions */
  build(positions: Float32Array, count: number): void {
    // Reset
    this.cellStart.fill(-1);
    this.cellEnd.fill(-1);

    // 1. Compute cell hash for each particle
    const invCell = 1.0 / this.cellSize;
    for (let i = 0; i < count; i++) {
      const i4 = i * 4;
      const cx = Math.floor(positions[i4] * invCell);
      const cy = Math.floor(positions[i4 + 1] * invCell);
      const cz = Math.floor(positions[i4 + 2] * invCell);
      this.particleCells[i] = this.hash(cx, cy, cz);
    }

    // 2. Sort particles by cell hash (counting sort)
    const counts = new Int32Array(this.tableSize);
    for (let i = 0; i < count; i++) {
      counts[this.particleCells[i]]++;
    }
    
    // Prefix sum
    const offsets = new Int32Array(this.tableSize);
    let sum = 0;
    for (let i = 0; i < this.tableSize; i++) {
      offsets[i] = sum;
      if (counts[i] > 0) {
        this.cellStart[i] = sum;
        this.cellEnd[i] = sum + counts[i];
      }
      sum += counts[i];
    }

    // Place particles
    for (let i = 0; i < count; i++) {
      const cell = this.particleCells[i];
      this.sortedIndices[offsets[cell]] = i;
      offsets[cell]++;
    }
  }

  /** Iterate over neighbors of a particle within radius h */
  forEachNeighbor(
    px: number, py: number, pz: number,
    h: number,
    positions: Float32Array,
    callback: (j: number, dx: number, dy: number, dz: number, distSq: number) => void
  ): void {
    const invCell = 1.0 / this.cellSize;
    const cx = Math.floor(px * invCell);
    const cy = Math.floor(py * invCell);
    const cz = Math.floor(pz * invCell);
    const hSq = h * h;

    // Check 3×3×3 neighboring cells
    for (let dz = -1; dz <= 1; dz++) {
      for (let dy = -1; dy <= 1; dy++) {
        for (let dx = -1; dx <= 1; dx++) {
          const cellHash = this.hash(cx + dx, cy + dy, cz + dz);
          const start = this.cellStart[cellHash];
          if (start < 0) continue;
          const end = this.cellEnd[cellHash];
          
          for (let s = start; s < end; s++) {
            const j = this.sortedIndices[s];
            const j4 = j * 4;
            const ddx = px - positions[j4];
            const ddy = py - positions[j4 + 1];
            const ddz = pz - positions[j4 + 2];
            const dSq = ddx * ddx + ddy * ddy + ddz * ddz;
            
            if (dSq < hSq) {
              callback(j, ddx, ddy, ddz, dSq);
            }
          }
        }
      }
    }
  }
}

export class PBFSolver {
  private grid: SpatialGrid;
  private terrain: TerrainHeightfield;
  private boundaryParams: BoundaryParams;

  // Precomputed kernel constants
  private poly6K: number;
  private spikyGradK: number;
  private h: number;
  private hSq: number;
  private restDensity: number;
  private epsilon: number;

  // Temp buffer for boundary enforcement
  private boundaryOut = { px: 0, py: 0, pz: 0, vx: 0, vy: 0, vz: 0 };

  constructor(terrain: TerrainHeightfield, boundaryParams: BoundaryParams) {
    this.terrain = terrain;
    this.boundaryParams = boundaryParams;
    this.grid = new SpatialGrid(CONFIG.maxParticles);

    this.h = CONFIG.smoothingRadius;
    this.hSq = this.h * this.h;
    this.restDensity = CONFIG.waterDensity;
    this.epsilon = CONFIG.cfmRegularization;
    this.poly6K = poly6Constant(this.h);
    this.spikyGradK = spikyGradConstant(this.h);
  }

  /** Run one complete PBF simulation step */
  step(state: FluidState, dt: number): void {
    const t0 = performance.now();
    const n = state.particleCount;
    if (n === 0) return;

    const pos = state.positions;
    const vel = state.velocities;
    const pred = state.predictedPos;
    const dens = state.densities;
    const lam = state.lambdas;

    const gravity = -CONFIG.gravity;

    // ============================================================
    // STEP 1: Apply external forces + predict positions
    // ============================================================
    for (let i = 0; i < n; i++) {
      const i4 = i * 4;
      // Apply gravity to velocity
      vel[i4 + 2] += gravity * dt; // vz += g * dt

      // Predict position
      pred[i4]     = pos[i4]     + vel[i4]     * dt;
      pred[i4 + 1] = pos[i4 + 1] + vel[i4 + 1] * dt;
      pred[i4 + 2] = pos[i4 + 2] + vel[i4 + 2] * dt;
      pred[i4 + 3] = 1.0;
    }

    // ============================================================
    // STEP 2: Build spatial hash grid on predicted positions
    // ============================================================
    this.grid.build(pred, n);

    // ============================================================
    // STEP 3: Iterative constraint solver
    // ============================================================
    const h = this.h;
    const hSq = this.hSq;
    const poly6K = this.poly6K;
    const spikyGradK = this.spikyGradK;
    const rho0 = this.restDensity;
    const eps = this.epsilon;
    const mass = CONFIG.particleMass;

    // Surface tension artificial pressure
    const kSurfTension = CONFIG.surfaceTension;
    const deltaqMag = 0.3 * h; // |Δq| for artificial pressure
    const deltaqSq = deltaqMag * deltaqMag;
    const wDeltaQ = poly6K * Math.pow(hSq - deltaqSq, 3);

    for (let iter = 0; iter < CONFIG.solverIterations; iter++) {
      // 3a. Compute density and lambda for each particle
      for (let i = 0; i < n; i++) {
        const i4 = i * 4;
        const px = pred[i4], py = pred[i4 + 1], pz = pred[i4 + 2];
        
        let density = 0;
        let gradSumSq = 0;    // Σ|∇_pk C_i|² for k ≠ i
        let gradSelfX = 0, gradSelfY = 0, gradSelfZ = 0; // ∇_pi C_i

        this.grid.forEachNeighbor(px, py, pz, h, pred, (j, dx, dy, dz, dSq) => {
          // Poly6 density
          const diff = hSq - dSq;
          density += mass * poly6K * diff * diff * diff;

          // Spiky gradient for constraint
          if (dSq > 1e-6) {
            const r = Math.sqrt(dSq);
            const rDiff = h - r;
            const gradMag = spikyGradK * rDiff * rDiff / r;
            const gx = gradMag * dx / rho0;
            const gy = gradMag * dy / rho0;
            const gz = gradMag * dz / rho0;

            if (j !== i) {
              gradSumSq += gx * gx + gy * gy + gz * gz;
              gradSelfX -= gx;
              gradSelfY -= gy;
              gradSelfZ -= gz;
            }
          }
        });

        dens[i] = density;
        
        // Constraint value
        const constraint = density / rho0 - 1.0;
        
        // Total gradient squared (including self)
        const selfGradSq = gradSelfX * gradSelfX + gradSelfY * gradSelfY + gradSelfZ * gradSelfZ;
        const totalGradSq = gradSumSq + selfGradSq;

        // Lambda with CFM regularization
        lam[i] = -constraint / (totalGradSq + eps);
      }

      // 3b. Compute position correction Δp
      for (let i = 0; i < n; i++) {
        const i4 = i * 4;
        const px = pred[i4], py = pred[i4 + 1], pz = pred[i4 + 2];
        
        let dpx = 0, dpy = 0, dpz = 0;

        this.grid.forEachNeighbor(px, py, pz, h, pred, (j, dx, dy, dz, dSq) => {
          if (j === i) return;
          if (dSq < 1e-6) return;

          const r = Math.sqrt(dSq);
          const rDiff = h - r;

          // Artificial pressure (surface tension correction)
          const wij = poly6K * Math.pow(hSq - dSq, 3);
          const sCorr = -kSurfTension * Math.pow(wij / (wDeltaQ + 1e-10), 4);

          // Spiky gradient
          const gradMag = spikyGradK * rDiff * rDiff / r;
          const scale = (lam[i] + lam[j] + sCorr) / rho0;
          
          dpx += scale * gradMag * dx;
          dpy += scale * gradMag * dy;
          dpz += scale * gradMag * dz;
        });

        // Apply correction
        pred[i4]     += dpx;
        pred[i4 + 1] += dpy;
        pred[i4 + 2] += dpz;
      }
    }

    // ============================================================
    // STEP 4: Update velocities + XSPH viscosity
    // ============================================================
    const invDt = 1.0 / dt;
    const xsphC = CONFIG.viscosity;

    for (let i = 0; i < n; i++) {
      const i4 = i * 4;
      
      // New velocity from position difference
      vel[i4]     = (pred[i4]     - pos[i4])     * invDt;
      vel[i4 + 1] = (pred[i4 + 1] - pos[i4 + 1]) * invDt;
      vel[i4 + 2] = (pred[i4 + 2] - pos[i4 + 2]) * invDt;
    }

    // XSPH viscosity smoothing
    if (xsphC > 0) {
      // We need a separate buffer for XSPH (read old velocities)
      const tempVel = new Float32Array(n * 4);
      tempVel.set(vel.subarray(0, n * 4));

      for (let i = 0; i < n; i++) {
        const i4 = i * 4;
        const px = pred[i4], py = pred[i4 + 1], pz = pred[i4 + 2];
        
        let dvx = 0, dvy = 0, dvz = 0;

        this.grid.forEachNeighbor(px, py, pz, h, pred, (j, dx, dy, dz, dSq) => {
          if (j === i) return;
          const diff = hSq - dSq;
          if (diff <= 0) return;
          const w = poly6K * diff * diff * diff;
          const rhoJ = Math.max(dens[j], 1.0);
          
          const j4 = j * 4;
          dvx += (tempVel[j4]     - tempVel[i4])     * w / rhoJ;
          dvy += (tempVel[j4 + 1] - tempVel[i4 + 1]) * w / rhoJ;
          dvz += (tempVel[j4 + 2] - tempVel[i4 + 2]) * w / rhoJ;
        });

        vel[i4]     += xsphC * dvx;
        vel[i4 + 1] += xsphC * dvy;
        vel[i4 + 2] += xsphC * dvz;
      }
    }

    // ============================================================
    // STEP 5: Update positions + enforce boundaries
    // ============================================================
    for (let i = 0; i < n; i++) {
      const i4 = i * 4;
      
      // Update position to predicted
      pos[i4]     = pred[i4];
      pos[i4 + 1] = pred[i4 + 1];
      pos[i4 + 2] = pred[i4 + 2];

      // Boundary enforcement
      enforceBoundaries(
        pos[i4], pos[i4 + 1], pos[i4 + 2],
        vel[i4], vel[i4 + 1], vel[i4 + 2],
        this.terrain, this.boundaryParams,
        this.boundaryOut
      );

      pos[i4]     = this.boundaryOut.px;
      pos[i4 + 1] = this.boundaryOut.py;
      pos[i4 + 2] = this.boundaryOut.pz;
      vel[i4]     = this.boundaryOut.vx;
      vel[i4 + 1] = this.boundaryOut.vy;
      vel[i4 + 2] = this.boundaryOut.vz;

      // Velocity damping (numerical stability)
      const speed = Math.sqrt(vel[i4] * vel[i4] + vel[i4+1] * vel[i4+1] + vel[i4+2] * vel[i4+2]);
      if (speed > 80) {
        const scale = 80 / speed;
        vel[i4] *= scale;
        vel[i4+1] *= scale;
        vel[i4+2] *= scale;
      }
    }

    state.simTime += dt;
    state.solverTimeMs = performance.now() - t0;
  }

  /** Update boundary parameters (called when user changes gates, triggers breach, etc.) */
  setBoundaryParams(params: BoundaryParams): void {
    this.boundaryParams = params;
  }

  getTerrain(): TerrainHeightfield {
    return this.terrain;
  }
}
