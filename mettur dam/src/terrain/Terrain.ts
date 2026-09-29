/**
 * Terrain.ts — one big fixed procedurally-generated valley.
 *  - getHeight(x,z): analytic height field (reservoir basin, meandering downstream
 *    river channel + flood plain, dam abutment gap, flattened village pads).
 *  - builds a vertex-coloured mesh.
 *  - bakeHeightMap(): a Float DataTexture the water shader samples for depth/discard.
 */
import {
  BufferGeometry,
  BufferAttribute,
  Mesh,
  MeshStandardMaterial,
  DataTexture,
  RedFormat,
  FloatType,
  LinearFilter,
  ClampToEdgeWrapping,
  DoubleSide,
} from 'three';
import { Noise } from './Noise';
import { WORLD, WATER, DAM, SETTLEMENTS } from '../config';

const clamp = (v: number, a: number, b: number) => (v < a ? a : v > b ? b : v);
function smoothstep(e0: number, e1: number, x: number): number {
  const t = clamp((x - e0) / (e1 - e0), 0, 1);
  return t * t * (3 - 2 * t);
}
function smootherstep(e0: number, e1: number, x: number): number {
  const t = clamp((x - e0) / (e1 - e0), 0, 1);
  return t * t * t * (t * (t * 6 - 15) + 10);
}
const lerp = (a: number, b: number, t: number) => a + (b - a) * t;

export interface HeightMapInfo {
  texture: DataTexture;
  minX: number;
  minZ: number;
  sizeX: number;
  sizeZ: number;
  minH: number;
  maxH: number;
}

export class Terrain {
  readonly mesh: Mesh;
  readonly noise: Noise;
  heightMap!: HeightMapInfo;

  // tunables
  private hf = 1 / 900; // hill frequency
  private hillAmp = 62;
  private channelHalf = 62;
  private valleyHalf = 820;
  private riverAmp = 240;
  private riverF1 = 1 / 520;
  private riverF2 = 1 / 210;
  private damHalfLen = 380;

  private padCache: { x: number; z: number; r: number; y: number }[] = [];

  constructor() {
    this.noise = new Noise(WORLD.seed);
    // precompute flat village pad heights (from the pad-free field, no recursion)
    for (const s of SETTLEMENTS) {
      const y = this.heightBase(s.x, s.z);
      this.padCache.push({ x: s.x, z: s.z, r: s.radius, y });
    }
    this.mesh = this.buildMesh();
    this.bakeHeightMap();
  }

  /** meandering river-centre X as a function of Z (straightens to x=0 at the dam). */
  riverCenterX(z: number): number {
    const meander = this.riverAmp * Math.sin(z * this.riverF1) + 0.32 * this.riverAmp * Math.sin(z * this.riverF2 + 1.3);
    const damp = smoothstep(0, 520, z); // 0 at dam, 1 downstream
    return meander * damp;
  }

  /** baseflow river surface Y at a given z (gently descends downstream). */
  riverSurfaceY(z: number): number {
    return WATER.riverBedY + WATER.baseflowDepth - Math.max(0, z) * 0.004;
  }

  /** height field WITHOUT village pads (used to seed pad heights). */
  private heightBase(x: number, z: number): number {
    const cx = this.riverCenterX(z);
    const adx = Math.abs(x - cx);

    // rolling hills baseline
    const hills =
      46 +
      this.hillAmp * this.noise.fbm(x * this.hf, z * this.hf, 5) +
      26 * this.noise.ridged(x * this.hf * 0.5 + 11, z * this.hf * 0.5 - 7, 4);

    // ---- downstream valley + river channel ----
    const vWall = smootherstep(this.channelHalf, this.valleyHalf, adx); // 0 near river, 1 far
    const plain = 15 - z * 0.004 + 7 * this.noise.fbm(x * 0.004 + 3, z * 0.004 + 9, 3);
    let downstreamH = lerp(plain, hills, vWall);
    const chFloor = 2 - z * 0.004;
    const chT = 1 - smoothstep(this.channelHalf * 0.55, this.channelHalf * 1.5, adx);
    downstreamH = lerp(downstreamH, chFloor, chT);

    // ---- reservoir basin (upstream, z<0) — irregular, terrain-contained lake ----
    // distance upstream from the dam line (grows toward -Z)
    const up = Math.max(0, -z);
    const lakeLen = 1560;
    // lake half-width in X: widest just behind the dam, tapering upstream, with a
    // noisy shoreline so the water body never reads as a rectangle or an ellipse.
    const taper = 1 - smoothstep(0, lakeLen, up);
    const wobble =
      0.74 +
      0.34 * (this.noise.fbm(z * 0.0027 + 12, 4.0, 3) * 0.5 + 0.5) +
      0.2 * this.noise.fbm(x * 0.004 - 3, z * 0.004 + 5, 2);
    const lakeHalf = (250 + 790 * taper) * wobble;
    // raised highland that physically contains the reservoir on the sides + back
    const resHills =
      88 +
      this.hillAmp * this.noise.fbm(x * this.hf + 2, z * this.hf - 4, 5) +
      30 * this.noise.ridged(x * this.hf * 0.5 - 6, z * this.hf * 0.5 + 3, 4);
    // bed: deepest at the dam & lake centre, rising toward the shore and the far end
    const shoreT = smootherstep(lakeHalf * 0.68, lakeHalf, adx); // 0 centre .. 1 past shore
    const backClose = smootherstep(lakeLen * 0.7, lakeLen, up); // seal the far end before the map edge
    const bedCentre = lerp(-74, -10, smoothstep(0, lakeLen, up)) + 6 * this.noise.fbm(x * 0.01, z * 0.011, 3);
    const reservoirH = lerp(bedCentre, resHills, Math.max(shoreT, backClose));

    // blend upstream / downstream across the dam line
    const uw = smoothstep(60, -60, z); // 1 upstream, 0 downstream
    let h = lerp(downstreamH, reservoirH, uw);

    // ---- dam abutment gap ----
    const nearDam = 1 - smoothstep(0, 260, Math.abs(z));
    if (nearDam > 0) {
      const ax = Math.abs(x - DAM.axisX);
      const inSpan = 1 - smoothstep(this.damHalfLen * 0.8, this.damHalfLen * 1.15, ax);
      h = lerp(h, 1.0, nearDam * inSpan); // riverbed under the dam body
      const abut = smoothstep(this.damHalfLen * 1.0, this.damHalfLen * 1.45, ax);
      const abutY = 70 + 20 * this.noise.fbm(x * 0.01, z * 0.01, 3);
      h = lerp(h, Math.max(h, abutY), nearDam * abut);
    }

    return h;
  }

  /** flatten terrain onto flood-plain pads under each settlement. */
  private applyPads(x: number, z: number, h: number): number {
    for (const p of this.padCache) {
      const d = Math.hypot(x - p.x, z - p.z);
      if (d < p.r * 1.35) {
        const t = 1 - smoothstep(p.r * 0.75, p.r * 1.35, d);
        // keep pad just above the local river so buildings sit on a bank, then flood
        h = lerp(h, Math.max(p.y, this.riverSurfaceY(p.z) + 4), t * 0.85);
      }
    }
    return h;
  }

  /** public analytic height (with pads). */
  getHeight(x: number, z: number): number {
    return this.applyPads(x, z, this.heightBase(x, z));
  }
  /** per-vertex terrain colour — full grass green everywhere, gently varied. */
  private colorAt(x: number, z: number, _y: number, slope: number, out: number[]): void {
    const n = this.noise.fbm(x * 0.03 + 5, z * 0.03 - 3, 3) * 0.5 + 0.5;   // fine mottle
    const p = this.noise.fbm(x * 0.006 - 2, z * 0.006 + 4, 3) * 0.5 + 0.5; // broad patches
    // grass green with subtle variation (no tan/rock/mud bands)
    let r = lerp(0.16, 0.30, n) * (0.9 + 0.2 * p);
    let g = lerp(0.44, 0.62, n) * (0.9 + 0.15 * p);
    let b = lerp(0.11, 0.20, n);
    // steeper faces read as shaded grass, still green
    const steep = smoothstep(0.5, 1.3, slope);
    r = lerp(r, r * 0.55, steep);
    g = lerp(g, g * 0.62, steep);
    b = lerp(b, b * 0.55, steep);
    out[0] = r; out[1] = g; out[2] = b;
  }

  private buildMesh(): Mesh {
    const segX = WORLD.terrainSegments;
    const segZ = Math.round((WORLD.terrainSegments * WORLD.terrainSizeZ) / WORLD.terrainSizeX);
    const halfX = WORLD.terrainSizeX / 2;
    const halfZ = WORLD.terrainSizeZ / 2;
    const dx = WORLD.terrainSizeX / segX;
    const dz = WORLD.terrainSizeZ / segZ;
    const nx = segX + 1;
    const nz = segZ + 1;

    const positions = new Float32Array(nx * nz * 3);
    const colors = new Float32Array(nx * nz * 3);
    const eps = 4;
    const tmp: number[] = [0, 0, 0];

    for (let iz = 0; iz < nz; iz++) {
      const z = -halfZ + iz * dz;
      for (let ix = 0; ix < nx; ix++) {
        const x = -halfX + ix * dx;
        const y = this.getHeight(x, z);
        const idx = (iz * nx + ix) * 3;
        positions[idx] = x;
        positions[idx + 1] = y;
        positions[idx + 2] = z;
        // slope from finite differences
        const hxp = this.getHeight(x + eps, z);
        const hzp = this.getHeight(x, z + eps);
        const slope = (Math.abs(hxp - y) + Math.abs(hzp - y)) / eps;
        this.colorAt(x, z, y, slope, tmp);
        colors[idx] = tmp[0]; colors[idx + 1] = tmp[1]; colors[idx + 2] = tmp[2];
      }
    }

    const indices = new Uint32Array(segX * segZ * 6);
    let o = 0;
    for (let iz = 0; iz < segZ; iz++) {
      for (let ix = 0; ix < segX; ix++) {
        const a = iz * nx + ix;
        const b = a + 1;
        const c = a + nx;
        const d = c + 1;
        indices[o++] = a; indices[o++] = c; indices[o++] = b;
        indices[o++] = b; indices[o++] = c; indices[o++] = d;
      }
    }

    const geo = new BufferGeometry();
    geo.setAttribute('position', new BufferAttribute(positions, 3));
    geo.setAttribute('color', new BufferAttribute(colors, 3));
    geo.setIndex(new BufferAttribute(indices, 1));
    geo.computeVertexNormals();

    const mat = new MeshStandardMaterial({
      vertexColors: true,
      roughness: 0.96,
      metalness: 0.0,
      side: DoubleSide,
    });
    const mesh = new Mesh(geo, mat);
    mesh.receiveShadow = true;
    mesh.name = 'Terrain';
    return mesh;
  }

  private bakeHeightMap(): void {
    const res = WORLD.heightmapRes;
    const data = new Float32Array(res * res);
    const halfX = WORLD.terrainSizeX / 2;
    const halfZ = WORLD.terrainSizeZ / 2;
    let minH = Infinity, maxH = -Infinity;
    for (let iz = 0; iz < res; iz++) {
      const z = -halfZ + (iz / (res - 1)) * WORLD.terrainSizeZ;
      for (let ix = 0; ix < res; ix++) {
        const x = -halfX + (ix / (res - 1)) * WORLD.terrainSizeX;
        const h = this.getHeight(x, z);
        data[iz * res + ix] = h;
        if (h < minH) minH = h;
        if (h > maxH) maxH = h;
      }
    }
    const tex = new DataTexture(data, res, res, RedFormat, FloatType);
    tex.minFilter = LinearFilter;
    tex.magFilter = LinearFilter;
    tex.wrapS = ClampToEdgeWrapping;
    tex.wrapT = ClampToEdgeWrapping;
    tex.needsUpdate = true;
    this.heightMap = {
      texture: tex,
      minX: -halfX,
      minZ: -halfZ,
      sizeX: WORLD.terrainSizeX,
      sizeZ: WORLD.terrainSizeZ,
      minH,
      maxH,
    };
  }
}
