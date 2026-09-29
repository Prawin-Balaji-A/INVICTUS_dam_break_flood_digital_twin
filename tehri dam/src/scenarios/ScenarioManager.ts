// ============================================================
// ScenarioManager.ts — Manages simulation scenarios and presets
// ============================================================

import { CONFIG } from '../core/SimulationConfig';
import { FluidState } from '../physics/FluidState';
import { BoundaryParams, createDefaultBoundaryParams, TerrainHeightfield } from '../physics/BoundarySystem';
import { DamComponents, setGateOpening } from '../dam/DamGeometry';

export type ScenarioType = 'controlled_release' | 'dam_break' | 'river_blockage';

export interface ScenarioPreset {
  name: string;
  type: ScenarioType;
  description: string;
  reservoirLevel: number;     // m (initial water level)
  gateOpenings: number[];     // 0–1 per gate
  particleSpacing: number;    // m
  breachActive: boolean;
  breachWidth: number;
  breachHeight: number;
  breachGrowthRate: number;   // m/s
  landslideActive: boolean;
  landslideDelay: number;     // s (delay before triggering)
}

export const PRESETS: ScenarioPreset[] = [
  {
    name: "Normal Reservoir — Low Flow",
    type: 'controlled_release',
    description: "Calm reservoir with gates closed. Open gates to begin controlled release.",
    reservoirLevel: 105,
    gateOpenings: [0, 0, 0, 0, 0],
    particleSpacing: 3.0,
    breachActive: false, breachWidth: 0, breachHeight: 0, breachGrowthRate: 0,
    landslideActive: false, landslideDelay: 0,
  },
  {
    name: "High Reservoir — Gate Release",
    type: 'controlled_release',
    description: "High water level. Two gates partially open for flood discharge.",
    reservoirLevel: 112,
    gateOpenings: [0, 0.4, 0.6, 0.4, 0],
    particleSpacing: 2.5,
    breachActive: false, breachWidth: 0, breachHeight: 0, breachGrowthRate: 0,
    landslideActive: false, landslideDelay: 0,
  },
  {
    name: "Emergency Spillway Release",
    type: 'controlled_release',
    description: "All gates fully open under emergency discharge conditions.",
    reservoirLevel: 115,
    gateOpenings: [1, 1, 1, 1, 1],
    particleSpacing: 2.5,
    breachActive: false, breachWidth: 0, breachHeight: 0, breachGrowthRate: 0,
    landslideActive: false, landslideDelay: 0,
  },
  {
    name: "Central Dam Breach",
    type: 'dam_break',
    description: "Sudden central breach of the dam. Catastrophic flood release.",
    reservoirLevel: 115,
    gateOpenings: [0, 0, 0, 0, 0],
    particleSpacing: 2.5,
    breachActive: true, breachWidth: 60, breachHeight: 80, breachGrowthRate: 0,
    landslideActive: false, landslideDelay: 0,
  },
  {
    name: "Progressive Dam Failure",
    type: 'dam_break',
    description: "Breach starts small and grows progressively over time.",
    reservoirLevel: 112,
    gateOpenings: [0, 0, 0, 0, 0],
    particleSpacing: 2.5,
    breachActive: true, breachWidth: 10, breachHeight: 15, breachGrowthRate: 2.0,
    landslideActive: false, landslideDelay: 0,
  },
  {
    name: "Landslide Blockage",
    type: 'river_blockage',
    description: "Downstream landslide blocks the river. Water accumulates upstream.",
    reservoirLevel: 108,
    gateOpenings: [0, 0.3, 0.5, 0.3, 0],
    particleSpacing: 3.0,
    breachActive: false, breachWidth: 0, breachHeight: 0, breachGrowthRate: 0,
    landslideActive: true, landslideDelay: 5,
  },
  {
    name: "Blockage Overtopping",
    type: 'river_blockage',
    description: "Landslide blocks river, water rises and overtops the blockage.",
    reservoirLevel: 112,
    gateOpenings: [0.2, 0.5, 0.8, 0.5, 0.2],
    particleSpacing: 2.5,
    breachActive: false, breachWidth: 0, breachHeight: 0, breachGrowthRate: 0,
    landslideActive: true, landslideDelay: 3,
  },
];

export class ScenarioManager {
  private currentPreset: number = 0;
  private boundaryParams: BoundaryParams;
  private simTime: number = 0;
  private breachGrowthRate: number = 0;
  private landslideDelay: number = 0;
  private landslideTriggered: boolean = false;
  
  constructor() {
    this.boundaryParams = createDefaultBoundaryParams();
  }

  /** Load a preset scenario */
  loadPreset(index: number, fluidState: FluidState, terrain: TerrainHeightfield, damComponents: DamComponents): void {
    this.currentPreset = index;
    const preset = PRESETS[index];
    
    // Reset fluid
    fluidState.reset();
    this.simTime = 0;
    this.landslideTriggered = false;

    // Apply boundary params
    this.boundaryParams.gateOpenings = [...preset.gateOpenings];
    this.boundaryParams.breachActive = preset.breachActive;
    this.boundaryParams.breachCenterX = 0;
    this.boundaryParams.breachWidth = preset.breachWidth;
    this.boundaryParams.breachHeight = preset.breachHeight;
    this.breachGrowthRate = preset.breachGrowthRate;
    this.boundaryParams.landslideActive = false; // activated after delay
    this.landslideDelay = preset.landslideDelay;

    // Update gate visuals
    for (let i = 0; i < damComponents.gatePivots.length; i++) {
      setGateOpening(damComponents.gatePivots, i, preset.gateOpenings[i]);
    }

    // Update config
    CONFIG.particleSpacing = preset.particleSpacing;
    CONFIG.smoothingRadius = preset.particleSpacing * 2.0;
    CONFIG.hashGridCellSize = CONFIG.smoothingRadius;
    CONFIG.particleMass = CONFIG.waterDensity * Math.pow(preset.particleSpacing, 3);
    CONFIG.particleRadius = preset.particleSpacing * 0.5;

    // Initialize reservoir particles
    const spacing = preset.particleSpacing;
    const waterZ = preset.reservoirLevel;
    
    // Reservoir volume: upstream of dam
    fluidState.initReservoir(
      -CONFIG.damLengthHalf + 20,  // xMin
      CONFIG.damLengthHalf - 20,   // xMax
      -250,                         // yMin (far upstream)
      CONFIG.upstreamYTop - 5,      // yMax (just before dam face)
      terrain.getHeight(0, -100) + spacing, // zMin (above terrain)
      waterZ,                       // zMax (water level)
      spacing
    );

    // Add some water in the downstream channel for controlled release scenarios
    if (preset.type === 'controlled_release') {
      const channelZMax = -10;
      const channelZMin = terrain.getHeight(0, 300) + spacing;
      for (let x = -30; x <= 30; x += spacing) {
        for (let y = 190; y <= 400; y += spacing) {
          const terrH = terrain.getHeight(x, y);
          for (let z = terrH + spacing; z <= channelZMax; z += spacing) {
            fluidState.addParticle(x, y, z);
          }
        }
      }
    }

    console.log(`[Scenario] Loaded "${preset.name}" with ${fluidState.particleCount} particles`);
  }

  /** Update scenario state (breach growth, landslide triggering) */
  update(dt: number, fluidState: FluidState): void {
    this.simTime += dt;
    const preset = PRESETS[this.currentPreset];

    // Progressive breach growth
    if (this.breachGrowthRate > 0 && this.boundaryParams.breachActive) {
      this.boundaryParams.breachWidth += this.breachGrowthRate * dt;
      this.boundaryParams.breachHeight += this.breachGrowthRate * 0.8 * dt;
      this.boundaryParams.breachWidth = Math.min(this.boundaryParams.breachWidth, 200);
      this.boundaryParams.breachHeight = Math.min(this.boundaryParams.breachHeight, CONFIG.crestZ - CONFIG.foundationZ);
    }

    // Landslide trigger after delay
    if (preset.landslideActive && !this.landslideTriggered && this.simTime >= this.landslideDelay) {
      this.landslideTriggered = true;
      this.boundaryParams.landslideActive = true;
      this.boundaryParams.landslideY = 300;
      this.boundaryParams.landslideRadius = 40;
      this.boundaryParams.landslideHeight = 25;
      console.log('[Scenario] Landslide triggered!');
    }
  }

  getBoundaryParams(): BoundaryParams { return this.boundaryParams; }
  getCurrentPreset(): ScenarioPreset { return PRESETS[this.currentPreset]; }
  getCurrentIndex(): number { return this.currentPreset; }
  getSimTime(): number { return this.simTime; }

  /** User-triggered gate change */
  setGateOpening(index: number, opening: number, damComponents: DamComponents): void {
    if (index >= 0 && index < this.boundaryParams.gateOpenings.length) {
      this.boundaryParams.gateOpenings[index] = opening;
      setGateOpening(damComponents.gatePivots, index, opening);
    }
  }

  /** User-triggered breach */
  triggerBreach(width: number, height: number, growthRate: number): void {
    this.boundaryParams.breachActive = true;
    this.boundaryParams.breachWidth = width;
    this.boundaryParams.breachHeight = height;
    this.breachGrowthRate = growthRate;
  }

  /** User-triggered landslide */
  triggerLandslide(): void {
    this.landslideTriggered = true;
    this.boundaryParams.landslideActive = true;
    this.boundaryParams.landslideY = 300;
    this.boundaryParams.landslideRadius = 40;
    this.boundaryParams.landslideHeight = 25;
  }
}
