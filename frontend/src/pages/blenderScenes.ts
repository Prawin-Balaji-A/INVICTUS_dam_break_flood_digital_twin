import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';

// ---------------------------------------------------------------------------
// Dam-specific Blender scene boundary.
//
// Some dams ship a hand-built, georeferenced Blender digital-twin scene (real
// DEM terrain + real OSM buildings/roads/waterways + a dimensioned dam model)
// exported to GLB. When a dam has such a scene, the 3D twin loads it INSTEAD of
// the procedural terrain/props — but the authoritative flood (water surface +
// mask-locked particles, driven by the simulation raster) is always rendered on
// top, in the SAME coordinate frame. This keeps the flood extent 100%
// authoritative while the static world reads as the real place.
//
// This is a config map, not hardcoded rendering: adding a dam means adding a GLB
// + one descriptor entry, with no Tehri-specific branches in the renderer.
//
// The GLB is exported (Blender headless) EXCLUDING the fabricated flood/effects
// collections — only real static assets are imported; the flood comes solely
// from the authoritative simulation.
// ---------------------------------------------------------------------------

export interface BlenderSceneDescriptor {
  /** Public URL of the exported GLB (real static assets only, no flood). */
  url: string;
  /**
   * Blender local-meter origin is the dam location; terrain Z is stored
   * relative to this base elevation (metres). Used to align the GLB's vertical
   * datum with the authoritative DEM's own elevation range.
   */
  damBaseElevationM: number;
  /** Dam location in WGS84 — the anchor shared by the GLB origin and the sim grid. */
  damLat: number;
  damLon: number;
}

// Keyed by simRef (project slug / id, lower-cased). Only dams with a real,
// georeferenced Blender scene appear here; every other dam keeps the procedural
// twin unchanged.
const SCENES: Record<string, BlenderSceneDescriptor> = {
  tehri: {
    url: '/models/tehri/tehri_scene.glb',
    damBaseElevationM: 700.2715258225659,
    damLat: 30.3761751,
    damLon: 78.4803102,
  },
};

/** Return the Blender scene descriptor for a dam, or null if it has none. */
export function getBlenderScene(simRef: string | null | undefined): BlenderSceneDescriptor | null {
  if (!simRef) return null;
  return SCENES[String(simRef).toLowerCase()] ?? null;
}

// Minimal shape of the fields this loader needs from the authoritative terrain
// grid (already fetched by the twin). Kept local to avoid a circular import.
interface TerrainLike {
  grid: { cols: number; rows: number };
  bounds: { west: number; south: number; east: number; north: number };
  elevation_m: { min: number; max: number };
}

export interface BlenderLoadResult {
  group: THREE.Group;
}

/**
 * Load a dam's Blender GLB and align it into the twin's normalised scene frame
 * so it registers cell-for-cell with the authoritative flood built by
 * DigitalTwin3D (same TERRAIN_SPAN / VERTICAL_UNITS convention).
 *
 * Alignment is anchored on the dam (Blender local origin === dam lon/lat) and
 * scaled by REAL metres, so the imported terrain/dam/buildings/roads sit exactly
 * under the simulation's wet cells. No geometry is fabricated or moved off its
 * real position — only a rigid scale + translate into scene units.
 *
 * @param terrainSpan  DigitalTwin3D's TERRAIN_SPAN (scene units across E–W).
 * @param verticalUnits DigitalTwin3D's VERTICAL_UNITS (units over full relief).
 */
export function loadBlenderScene(
  scene: THREE.Scene,
  terrain: TerrainLike,
  desc: BlenderSceneDescriptor,
  terrainSpan: number,
  verticalUnits: number,
): Promise<BlenderLoadResult> {
  const { west, south, east, north } = terrain.bounds;
  const cols = terrain.grid.cols, rows = terrain.grid.rows;
  const spanX = terrainSpan;
  const spanZ = terrainSpan * (rows / cols);

  const eMin = terrain.elevation_m.min;
  const relief = Math.max(terrain.elevation_m.max - eMin, 1e-3);
  const mToUnit = verticalUnits / relief; // metres -> scene units (vertical)

  // Real E–W ground width of the authoritative domain, in metres.
  const midLat = (north + south) / 2;
  const widthM = Math.max((east - west) * 111320 * Math.cos((midLat * Math.PI) / 180), 1);
  const sHoriz = spanX / widthM; // scene units per metre (horizontal)

  // Where the dam (Blender local origin) falls in the normalised scene frame.
  // Raster row 0 == north, so north maps to the most-negative z.
  const fx = (desc.damLon - west) / Math.max(east - west, 1e-9);
  const fz = (north - desc.damLat) / Math.max(north - south, 1e-9);
  const xDam = (fx - 0.5) * spanX;
  const zDam = (fz - 0.5) * spanZ;

  // Vertical datum: GLB Y (Blender Z) is metres relative to the dam base; the
  // procedural terrain measures metres above the DEM minimum. Offset bridges them.
  const yOffset = (desc.damBaseElevationM - eMin) * mToUnit;

  const loader = new GLTFLoader();
  return new Promise<BlenderLoadResult>((resolve, reject) => {
    loader.load(
      desc.url,
      (gltf) => {
        const group = gltf.scene;
        // GLB is Y-up in Blender local metres (dam at origin). Non-uniform scale
        // maps metres -> scene units independently on the horizontal plane and
        // the vertical axis, matching the procedural terrain's exaggeration.
        group.scale.set(sHoriz, mToUnit, sHoriz);
        group.position.set(xDam, yOffset, zDam);
        group.updateWorldMatrix(true, true);

        group.traverse((o) => {
          const m = o as THREE.Mesh;
          // A debug origin marker authored in the .blend — not real geometry.
          if (/ORIGIN_MARKER/i.test(o.name)) { o.visible = false; return; }
          // The .blend terrain uses a PROCEDURAL (node-based) material that glTF
          // cannot export — it arrives as flat, blown-out white which hides the
          // flood. The twin's own procedural mesh is the SAME real DEM (identical
          // metres->units mapping) and is correctly hypsometric-shaded, so we
          // hide the GLB terrain and let the procedural DEM be the flood-bearing
          // surface. The GLB's real dam/buildings/roads/reservoir sit on it at
          // their true elevations (same datum), so alignment is exact.
          if (/terrain/i.test(o.name)) { o.visible = false; return; }
          if ((m as any).isMesh) {
            m.castShadow = true;
            m.receiveShadow = true;
          }
          // Cameras/lights authored in the .blend are decorative here; the twin
          // drives its own camera + lighting. A leftover Blender Sun lamp would
          // ADD to the twin's sun and blow the whole scene out to white, so
          // suppress both to avoid conflicts.
          if ((o as any).isCamera || (o as any).isLight) o.visible = false;
        });

        scene.add(group);
        resolve({ group });
      },
      undefined,
      (err) => reject(err),
    );
  });
}
