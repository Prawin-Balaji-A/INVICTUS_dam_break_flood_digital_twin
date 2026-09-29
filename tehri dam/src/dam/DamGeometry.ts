// ============================================================
// DamGeometry.ts — Realistic concrete gravity dam structure
// Dimensions adapted from generate.py (420m × 138m)
// ============================================================

import * as THREE from 'three';
import { MeshBuilder } from '../utils/MeshBuilder';
import { CONFIG } from '../core/SimulationConfig';

// Dam dimensions from generate.py
const DAM_LEN_HALF = CONFIG.damLengthHalf;     // 210m
const CREST_Z = CONFIG.crestZ;                  // 120m
const FOUNDATION_Z = CONFIG.foundationZ;        // -18m
const UP_Y_TOP = CONFIG.upstreamYTop;           // -6m
const UP_Y_BOT = CONFIG.upstreamYBot;           // -14m
const DOWN_Y_TOP = CONFIG.downstreamYTop;       // 6m
const DOWN_Y_TOE = CONFIG.downstreamYToe;       // 104m
const SPILL_CREST_Z = CONFIG.spillCrestZ;       // 108m
const SPILL_HALF = CONFIG.spillHalf;            // 60m
const N_BAYS = CONFIG.nBays;                    // 5
const FLANK_W = 8.0;
const PIER_W = 3.5;
const SPILL_INNER_HALF = SPILL_HALF - FLANK_W;
const BAY_W = (2.0 * SPILL_INNER_HALF - (N_BAYS - 1) * PIER_W) / N_BAYS;

// Non-overflow cross-section profile (Y-Z plane)
const NON_OVERFLOW_PROFILE: [number, number][] = [
  [UP_Y_BOT, FOUNDATION_Z],
  [UP_Y_TOP, CREST_Z],
  [DOWN_Y_TOP, CREST_Z],
  [DOWN_Y_TOE, FOUNDATION_Z],
];

/** Generate the ogee spillway profile */
function spillwayProfile(): [number, number][] {
  const apexY = -2.0;
  const Hd = 10.0; // design head
  const K = 2.0 * Math.pow(Hd, 0.85);

  const pts: [number, number][] = [
    [UP_Y_BOT, FOUNDATION_Z],
    [UP_Y_TOP, SPILL_CREST_Z],
    [apexY, SPILL_CREST_Z],
  ];

  const xEnd = 14.15;
  const steps = 16;
  for (let i = 1; i <= steps; i++) {
    const x = xEnd * i / steps;
    const y = apexY + x;
    const z = SPILL_CREST_Z - Math.pow(x, 1.85) / K;
    pts.push([y, z]);
  }

  pts.push([DOWN_Y_TOE, FOUNDATION_Z]);
  return pts;
}

/** Compute bay center X positions */
function bayCentres(): number[] {
  const centres: number[] = [];
  let x = -SPILL_INNER_HALF;
  for (let i = 0; i < N_BAYS; i++) {
    centres.push(x + BAY_W * 0.5);
    x += BAY_W + PIER_W;
  }
  return centres;
}

/** Compute pier X ranges */
function pierRanges(): [number, number][] {
  const ranges: [number, number][] = [[-SPILL_HALF, -SPILL_INNER_HALF]];
  let x = -SPILL_INNER_HALF;
  for (let i = 0; i < N_BAYS - 1; i++) {
    const x0 = x + BAY_W;
    ranges.push([x0, x0 + PIER_W]);
    x = x0 + PIER_W;
  }
  ranges.push([SPILL_INNER_HALF, SPILL_HALF]);
  return ranges;
}

/** Create the concrete material */
function createConcreteMaterial(): THREE.MeshStandardMaterial {
  return new THREE.MeshStandardMaterial({
    color: 0xa8a8a2,
    roughness: 0.88,
    metalness: 0.0,
    flatShading: false,
  });
}

/** Create weathered concrete material */
function createWeatheredConcreteMaterial(): THREE.MeshStandardMaterial {
  return new THREE.MeshStandardMaterial({
    color: 0x8e8d89,
    roughness: 0.93,
    metalness: 0.0,
  });
}

/** Create steel material for gates */
function createSteelMaterial(): THREE.MeshStandardMaterial {
  return new THREE.MeshStandardMaterial({
    color: 0x424547,
    roughness: 0.40,
    metalness: 0.95,
  });
}

export interface DamComponents {
  group: THREE.Group;
  gates: THREE.Mesh[];
  gatePivots: THREE.Group[];  // pivot groups for gate rotation
  breachableSections: THREE.Mesh[];
}

export function createDamGeometry(): DamComponents {
  const group = new THREE.Group();
  group.name = 'Dam';

  const concreteMat = createConcreteMaterial();
  const weatheredMat = createWeatheredConcreteMaterial();
  const steelMat = createSteelMaterial();

  // ====== 1. NON-OVERFLOW DAM BODY (left + right flanks) ======
  const bodyBuilder = new MeshBuilder();
  bodyBuilder.addPrism(NON_OVERFLOW_PROFILE, -DAM_LEN_HALF, -SPILL_HALF);
  bodyBuilder.addPrism(NON_OVERFLOW_PROFILE, SPILL_HALF, DAM_LEN_HALF);
  const bodyMesh = bodyBuilder.buildMesh(concreteMat);
  bodyMesh.castShadow = true;
  bodyMesh.receiveShadow = true;
  bodyMesh.name = 'Dam_Body';
  group.add(bodyMesh);

  // ====== 2. SPILLWAY SECTION ======
  const spillProfile = spillwayProfile();
  const spillBuilder = new MeshBuilder();
  spillBuilder.addPrism(spillProfile, -SPILL_HALF, SPILL_HALF);
  const spillMesh = spillBuilder.buildMesh(concreteMat);
  spillMesh.castShadow = true;
  spillMesh.receiveShadow = true;
  spillMesh.name = 'Spillway_Chute';
  group.add(spillMesh);

  // ====== 3. SPILLWAY PIERS ======
  const pierProfile: [number, number][] = [
    [UP_Y_TOP, SPILL_CREST_Z],
    ...spillProfile.slice(2),
  ];
  // Add top cap for pier
  pierProfile.push([DOWN_Y_TOE, CREST_Z - 2]);
  pierProfile.push([4.0, CREST_Z + 2]);
  pierProfile.push([UP_Y_TOP, CREST_Z + 2]);

  for (const [x0, x1] of pierRanges()) {
    const pb = new MeshBuilder();
    pb.addPrism(pierProfile, x0, x1);
    const pierMesh = pb.buildMesh(concreteMat);
    pierMesh.castShadow = true;
    pierMesh.receiveShadow = true;
    pierMesh.name = `Pier_${x0.toFixed(0)}`;
    group.add(pierMesh);
  }

  // ====== 4. FOUNDATION MAT ======
  const foundBuilder = new MeshBuilder();
  foundBuilder.addBox(
    -DAM_LEN_HALF - 8, DAM_LEN_HALF + 8,
    UP_Y_BOT - 14, DOWN_Y_TOE + 14,
    -30, FOUNDATION_Z
  );
  const foundMesh = foundBuilder.buildMesh(weatheredMat);
  foundMesh.receiveShadow = true;
  foundMesh.name = 'Foundation';
  group.add(foundMesh);

  // ====== 5. STILLING BASIN ======
  const basinBuilder = new MeshBuilder();
  // Apron slab
  basinBuilder.addBox(-68, 68, 104, 182, -30, -20);
  // End sill
  basinBuilder.addBox(-68, 68, 172, 182, -20, -13);
  // Side training walls
  basinBuilder.addBox(-78, -68, 104, 182, -30, 6);
  basinBuilder.addBox(68, 78, 104, 182, -30, 6);
  // Baffle blocks
  for (let row = 0; row < 4; row++) {
    const yy = 126 + row * 12;
    let xx = -60 + (row % 2 ? 4 : 0);
    while (xx < 58) {
      basinBuilder.addBox(xx, xx + 5, yy, yy + 5, -20, -14.5);
      xx += 10;
    }
  }
  const basinMesh = basinBuilder.buildMesh(weatheredMat);
  basinMesh.receiveShadow = true;
  basinMesh.castShadow = true;
  basinMesh.name = 'Stilling_Basin';
  group.add(basinMesh);

  // ====== 6. CREST ROADWAY + PARAPETS ======
  const crestBuilder = new MeshBuilder();
  for (const [x0, x1] of [[-DAM_LEN_HALF, -SPILL_HALF], [SPILL_HALF, DAM_LEN_HALF]] as [number,number][]) {
    crestBuilder.addBox(x0, x1, -5.2, 5.2, CREST_Z, CREST_Z + 0.25);
    crestBuilder.addBox(x0, x1, -6.2, -5.2, CREST_Z, CREST_Z + 1.35);
    crestBuilder.addBox(x0, x1, 5.2, 6.2, CREST_Z, CREST_Z + 1.35);
  }
  const crestMesh = crestBuilder.buildMesh(concreteMat);
  crestMesh.castShadow = true;
  crestMesh.name = 'Crest';
  group.add(crestMesh);

  // ====== 7. EXPANSION JOINTS (visual strips on downstream face) ======
  const jointMat = new THREE.MeshStandardMaterial({
    color: 0x555550,
    roughness: 0.95,
    metalness: 0.0,
  });
  const jointBuilder = new MeshBuilder();
  for (let xPos = -DAM_LEN_HALF + 18; xPos < DAM_LEN_HALF; xPos += 18) {
    if (Math.abs(xPos) < SPILL_HALF + 1) continue;
    // Thin strip on downstream face
    jointBuilder.addBox(xPos - 0.15, xPos + 0.15, DOWN_Y_TOP - 0.1, DOWN_Y_TOP + 0.1, FOUNDATION_Z, CREST_Z);
  }
  const jointMesh = jointBuilder.buildMesh(jointMat);
  jointMesh.name = 'Expansion_Joints';
  group.add(jointMesh);

  // ====== 8. RADIAL GATES ======
  const gates: THREE.Mesh[] = [];
  const gatePivots: THREE.Group[] = [];
  const GATE_TRUNNION_Y = 14.0;
  const GATE_TRUNNION_Z = 112.0;
  const GATE_R = Math.hypot(GATE_TRUNNION_Y - (-2), GATE_TRUNNION_Z - SPILL_CREST_Z);
  const phiBot = Math.atan2(SPILL_CREST_Z - GATE_TRUNNION_Z, -2 - GATE_TRUNNION_Y);
  const phiTop = phiBot - Math.PI / 3;
  const GATE_WIDTH = BAY_W - 0.4;

  for (const cx of bayCentres()) {
    // Gate skin plate (curved arc)
    const gateBuilder = new MeshBuilder();
    const arcSegments = 20;
    const thickness = 0.75;
    
    const outerProfile: [number, number][] = [];
    const innerProfile: [number, number][] = [];
    
    for (let s = 0; s <= arcSegments; s++) {
      const a = phiTop + (phiBot - phiTop) * s / arcSegments;
      outerProfile.push([
        (GATE_R + thickness * 0.5) * Math.cos(a),
        (GATE_R + thickness * 0.5) * Math.sin(a)
      ]);
      innerProfile.push([
        (GATE_R - thickness * 0.5) * Math.cos(a),
        (GATE_R - thickness * 0.5) * Math.sin(a)
      ]);
    }

    const gateProfile = [...outerProfile, ...innerProfile.reverse()];
    gateBuilder.addPrism(gateProfile, -GATE_WIDTH * 0.5, GATE_WIDTH * 0.5);
    
    // Trunnion shaft
    gateBuilder.addCylinderX(0.8, -GATE_WIDTH * 0.5, GATE_WIDTH * 0.5, 0, 0, 12);

    const gateMesh = gateBuilder.buildMesh(steelMat);
    gateMesh.castShadow = true;
    gateMesh.name = `Gate_${cx.toFixed(0)}`;
    
    // Create pivot group at trunnion position for rotation
    const pivot = new THREE.Group();
    pivot.position.set(cx, GATE_TRUNNION_Y, GATE_TRUNNION_Z);
    pivot.name = `GatePivot_${cx.toFixed(0)}`;
    pivot.add(gateMesh);
    
    group.add(pivot);
    gates.push(gateMesh);
    gatePivots.push(pivot);
  }

  // ====== 9. SERVICE BUILDINGS ======
  const svcBuilder = new MeshBuilder();
  for (const [x0, x1] of [[-168, -146], [146, 168]] as [number,number][]) {
    svcBuilder.addBox(x0, x1, -4, 4.5, CREST_Z, CREST_Z + 7);
    svcBuilder.addBox(x0 - 0.8, x1 + 0.8, -4.8, 5.3, CREST_Z + 7, CREST_Z + 7.8);
  }
  const svcMesh = svcBuilder.buildMesh(weatheredMat);
  svcMesh.castShadow = true;
  svcMesh.name = 'Service_Buildings';
  group.add(svcMesh);

  // Breachable sections (simple placeholders for dam-break visualization)
  const breachableSections: THREE.Mesh[] = [];

  return { group, gates, gatePivots, breachableSections };
}

/** Set gate opening angle (0 = closed, 1 = fully open) */
export function setGateOpening(gatePivots: THREE.Group[], gateIndex: number, opening: number): void {
  if (gateIndex < 0 || gateIndex >= gatePivots.length) return;
  const maxAngle = Math.PI * 40 / 180; // 40 degrees max opening
  gatePivots[gateIndex].rotation.x = -opening * maxAngle;
}

/** Bay center positions (exported for scenario use) */
export function getBayCentres(): number[] {
  return bayCentres();
}

export function getBayWidth(): number {
  return BAY_W;
}
