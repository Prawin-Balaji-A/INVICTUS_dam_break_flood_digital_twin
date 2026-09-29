// ============================================================
// SimulationConfig.ts — Central configuration for all physics
// constants and simulation parameters. SI units throughout.
// ============================================================

export interface SimConfig {
  // --- Physics ---
  gravity: number;            // m/s²
  waterDensity: number;       // kg/m³  (rest density ρ₀)
  viscosity: number;          // XSPH viscosity coefficient c
  surfaceTension: number;     // artificial pressure coefficient k
  
  // --- PBF Solver ---
  particleRadius: number;     // m  (visual radius)
  particleSpacing: number;    // m  (initial spacing between particles)
  smoothingRadius: number;    // m  (h — SPH kernel support radius)
  solverIterations: number;   // constraint solver iterations per step
  simulationDt: number;       // s  (fixed timestep)
  maxSubsteps: number;        // max physics substeps per frame
  timeScale: number;          // simulation speed multiplier
  cfmRegularization: number;  // ε for constraint force mixing
  
  // --- Spatial Hash ---
  hashGridCellSize: number;   // m  (= smoothingRadius)
  hashTableSize: number;      // prime number for hash table
  
  // --- Particles ---
  maxParticles: number;       // maximum particle count
  initialParticles: number;   // starting particle count
  particleMass: number;       // kg  (computed from spacing & density)
  
  // --- Dam Dimensions (from generate.py) ---
  damLengthHalf: number;      // m  (half-length, 210)
  crestZ: number;             // m  (crest elevation, 120)
  foundationZ: number;        // m  (foundation bottom, -18)
  upstreamYTop: number;       // m  (upstream face at crest)
  upstreamYBot: number;       // m  (upstream face at foundation)
  downstreamYTop: number;     // m  (downstream face at crest)
  downstreamYToe: number;     // m  (downstream toe)
  spillCrestZ: number;        // m  (ogee crest elevation, 108)
  spillHalf: number;          // m  (half-length of spillway, 60)
  nBays: number;              // number of spillway bays
  reservoirWaterZ: number;    // m  (initial water level)
  
  // --- Visualization ---
  debugMode: boolean;
  showParticles: boolean;
  showFoam: boolean;
  showSpray: boolean;
  showVelocityField: boolean;
  showFloodDepth: boolean;
  showPressure: boolean;
}

export function createDefaultConfig(): SimConfig {
  const particleSpacing = 4.0;  // 4m spacing for CPU-based solver
  const smoothingRadius = particleSpacing * 2.0;
  const waterDensity = 1000.0;
  const particleMass = waterDensity * Math.pow(particleSpacing, 3);

  return {
    // Physics
    gravity: 9.81,
    waterDensity,
    viscosity: 0.01,
    surfaceTension: 0.0001,
    
    // PBF Solver
    particleRadius: particleSpacing * 0.5,
    particleSpacing,
    smoothingRadius,
    solverIterations: 4,
    simulationDt: 1.0 / 60.0,
    maxSubsteps: 4,
    timeScale: 1.0,
    cfmRegularization: 600.0,
    
    // Spatial Hash
    hashGridCellSize: smoothingRadius,
    hashTableSize: 262144,  // 2^18
    
    // Particles
    maxParticles: 15000,
    initialParticles: 8000,
    particleMass,
    
    // Dam Dimensions (from generate.py)
    damLengthHalf: 210.0,
    crestZ: 120.0,
    foundationZ: -18.0,
    upstreamYTop: -6.0,
    upstreamYBot: -14.0,
    downstreamYTop: 6.0,
    downstreamYToe: 104.0,
    spillCrestZ: 108.0,
    spillHalf: 60.0,
    nBays: 5,
    reservoirWaterZ: 110.5,
    
    // Visualization
    debugMode: false,
    showParticles: false,
    showFoam: true,
    showSpray: true,
    showVelocityField: false,
    showFloodDepth: false,
    showPressure: false,
  };
}

/** Singleton config instance */
export const CONFIG = createDefaultConfig();
