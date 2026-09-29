/**
 * config.ts — all tunables for the Mettur dam flood simulator.
 * World convention: +Y up, dam long axis = X, reservoir = -Z, downstream/villages = +Z.
 * 1 unit ~= 1 metre.
 */
import { Color } from 'three';

/* ------------------------------------------------------------------ *
 *  World / terrain
 * ------------------------------------------------------------------ */
export const WORLD = {
  terrainSizeX: 4000,
  terrainSizeZ: 4400,
  // mesh grid resolution (segments per side). Higher = crisper river channel, more verts.
  terrainSegments: 480,
  // baked heightmap resolution sampled by the water shader.
  heightmapRes: 512,
  seed: 1337,
};

/* Dam sits at origin. These describe where the GLB lands after seating. */
export const DAM = {
  targetCrestLength: 900, // metres along X after scaling (bigger dam)
  seatBaseY: 0, // dam toe/foundation rests at y=0
  crestY: 60, // approximate crest height (matches DAM_HEIGHT)
  // river axis (X) where the valley + spillway are centred
  axisX: 0,
  // Z of the dam wall (upstream face ~ -20, downstream toe ~ +30)
  wallZ: 0,
  toeZ: 60, // downstream toe / start of the river below the dam
};

/* ------------------------------------------------------------------ *
 *  Water levels (reservoir surface Y is lerped between floor..max)
 * ------------------------------------------------------------------ */
export const WATER = {
  reservoirFloorY: 6, // y at 0% level (dead pool)
  reservoirMaxY: 74, // y at 100% level (well over the 60 m crest = overtopping)
  startLevel: 0.55, // initial slider fraction -> "full-looking" reservoir
  thresholdLevel: 0.82, // breach trigger fraction
  fillLerp: 0.9, // per-second lerp toward target level
  // downstream river baseflow (always-on shallow river below the dam)
  riverBedY: 2, // channel-floor reference downstream
  baseflowDepth: 5, // shallow river surface above bed at the toe
  // flood-front advance downstream after breach
  floodBaseSpeed: 60, // units/sec baseline front speed
  floodHeadSpeed: 240, // extra units/sec scaled by normalized head
  floodMaxZ: 2200, // front stops here (edge of map)
  floodMaxReach: 1500, // max radial spread distance of the breach flood (covers the valley + towns)
  floodSheetDepth: 14, // apparent depth of the flood sheet
  // shader look
  shallowColor: new Color(0x3f97cf),
  deepColor: new Color(0x0a2b45),
  reservoirDeep: new Color(0x134a73), // lighter deep-lake blue (depth gradient does the rest)
  foamColor: new Color(0xdfeefc),
  floodColor: new Color(0x5b4a32), // muddy flood tint
  // depth over which shallow->deep colour saturates (reservoir is far deeper than the river)
  reservoirDepthScale: 95,
  riverDepthScale: 26,
};

/* ------------------------------------------------------------------ *
 *  Gates (baked GLB clips) — which nodes actually open, from binary decode
 * ------------------------------------------------------------------ */
export const GATES = {
  openClipRegex: /gate/i,
  timeScale: 3.0, // speed up the ~14.6 s baked animation
};

/* ------------------------------------------------------------------ *
 *  Dam breach crumble
 * ------------------------------------------------------------------ */
export const BREACH = {
  // central fraction of the dam wall (in X) that can shed chunks — the dam stays intact,
  // only a few localized pieces near the spillway detach.
  notchHalfWidth: 120, // metres either side of axisX to look for loose chunks
  maxChunks: 12, // hard cap on detaching pieces (keeps the main dam recognizable)
  maxChunkVol: 120000, // skip monolithic main-body meshes larger than this (m^3)
  gravity: -34, // m/s^2 (exaggerated for punch)
  downstreamWash: 30, // +Z shove on freed blocks (kept modest → chunks land in the river below)
  groundBounce: 0.28,
  spinRate: 2.0,
};

/* ------------------------------------------------------------------ *
 *  Spray / foam particles
 * ------------------------------------------------------------------ */
export const SPRAY = {
  gateJetCount: 900,
  breachBurstCount: 1400,
  dropSize: 1.6,
  gravity: -30,
};

/* ------------------------------------------------------------------ *
 *  Settlements — hand placed downstream (+Z). type drives look + size.
 *  Flood reaches a settlement when the flood front Z passes its z.
 * ------------------------------------------------------------------ */
export type SettlementType = 'town' | 'village' | 'farmland';

export interface SettlementDef {
  id: string;
  name: string;
  type: SettlementType;
  x: number;
  z: number;
  radius: number; // footprint radius
  buildings: number; // instance count
  color: number; // marker/dot color
}

export const SETTLEMENTS: SettlementDef[] = [
  { id: 'mettur', name: 'Mettur Town', type: 'town', x: -150, z: 360, radius: 140, buildings: 150, color: 0x6fd3ff },
  { id: 'bhavani', name: 'Bhavani', type: 'village', x: 210, z: 610, radius: 78, buildings: 46, color: 0x8be0a0 },
  { id: 'erodefarms', name: 'Erode Farmlands', type: 'farmland', x: -360, z: 900, radius: 180, buildings: 30, color: 0xd6c46a },
  { id: 'komara', name: 'Komarapalayam', type: 'village', x: 190, z: 1090, radius: 80, buildings: 50, color: 0x8be0a0 },
  { id: 'palli', name: 'Pallipalayam', type: 'village', x: -210, z: 1360, radius: 78, buildings: 48, color: 0x8be0a0 },
  { id: 'kaveri', name: 'Kaveri Village', type: 'village', x: 150, z: 1650, radius: 66, buildings: 38, color: 0x8be0a0 },
  { id: 'anthiyur', name: 'Anthiyur', type: 'village', x: -280, z: 1880, radius: 82, buildings: 52, color: 0x8be0a0 },
];

/* ------------------------------------------------------------------ *
 *  Buildings — home size scale (kept proportional to the dam) + how many
 *  extra random houses to scatter across the whole terrain.
 * ------------------------------------------------------------------ */
export const BUILD = {
  homeScale: 1.25, // multiplies every building's footprint + height
  randomHouses: 900, // standalone houses scattered over the green terrain
};

/* ------------------------------------------------------------------ *
 *  Camera
 * ------------------------------------------------------------------ */
export const CAMERA = {
  fov: 55,
  near: 1,
  far: 12000,
  // opening overview: elevated, angled down toward the dam so the reservoir behind it,
  // the river below and the downstream valley are all in frame.
  overviewPos: [780, 600, 1420] as [number, number, number],
  overviewTarget: [0, 24, 120] as [number, number, number],
  flyDuration: 1.6, // seconds
  focusHeight: 120, // camera height when focusing a village
  focusDist: 240, // camera pullback from a village
};

/* ------------------------------------------------------------------ *
 *  Lighting / sky
 * ------------------------------------------------------------------ */
export const SKY = {
  sunDir: [0.55, 0.7, 0.35] as [number, number, number],
  sunColor: 0xfff2dc,
  sunIntensity: 2.4,
  ambientColor: 0x5b6b82,
  ambientIntensity: 0.55,
  hemiSky: 0x9fc3ff,
  hemiGround: 0x3a3226,
  hemiIntensity: 0.75,
  fogColor: 0xbcd0e8,
  fogNear: 1600,
  fogFar: 6500,
  topColor: new Color(0x2b6fb0),
  bottomColor: new Color(0xcfe2f5),
};

/* ------------------------------------------------------------------ *
 *  Rain / storm weather (Simulate Rain)
 * ------------------------------------------------------------------ */
export const RAIN = {
  count: 7000, // instanced falling streaks
  area: 2200, // horizontal half-extent of the rain volume (follows the camera)
  top: 850, // spawn height above the camera focus
  fallSpeed: 620, // units/sec downward
  streakLen: 24, // visual length of each drop
  rampSeconds: 2.6, // seconds to fade the storm fully in / out
  // rain -> water coupling (gradual, approximate)
  reservoirRisePerSec: 0.010, // level fraction added per second while raining
  dischargeBoost: 260, // extra downstream discharge shown while raining
};

/* Storm atmosphere the scene lerps toward while raining (vs the clear SKY above). */
export const RAIN_SKY = {
  topColor: new Color(0x39414c),
  bottomColor: new Color(0x707a86),
  fogColor: new Color(0x5b636e),
  fogNear: 700,
  fogFar: 3600,
  sunIntensity: 0.55,
  ambientIntensity: 0.95,
  exposure: 0.8,
};

/* ------------------------------------------------------------------ *
 *  Downstream bridge (breakable) — one crossing far below the dam
 * ------------------------------------------------------------------ */
export const BRIDGE = {
  z: 1500, // downstream Z (between Pallipalayam and Kaveri), far from the dam
  spanHalf: 165, // half length across the river (X)
  deckSegments: 9, // deck pieces (fail progressively)
  deckW: 26, // deck width along Z
  clearance: 15, // deck height above the local river surface
  pierCount: 4,
  failFloodMix: 0.3, // flood strength needed before pieces start to go
  releaseInterval: 0.35, // seconds between successive pieces failing
  gravity: -28,
  downstreamWash: 34,
};
