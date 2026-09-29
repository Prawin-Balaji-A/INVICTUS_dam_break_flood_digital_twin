/**
 * Settlements.ts — hand-placed town / villages / farmland as instanced boxes,
 * scattered on the terrain along the downstream valley. Buildings flood-tint (and
 * sink slightly) as the flood front passes and the sheet rises over their base.
 */
import {
  InstancedMesh,
  BoxGeometry,
  MeshStandardMaterial,
  Object3D,
  Color,
  Vector3,
  Matrix4,
  DynamicDrawUsage,
} from 'three';
import { Terrain } from '../terrain/Terrain';
import { SETTLEMENTS, SettlementDef, WORLD, WATER, BUILD } from '../config';

export interface SettlementRuntime extends SettlementDef {
  center: Vector3; // world centre (on terrain)
  groundY: number;
  count: number;
  floodedCount: number;
  get floodedFraction(): number;
  get isFlooded(): boolean;
}

const WET = new Color(0x2f3d44);
const BUILDING_PALETTE = [0xd9d2c4, 0xc7b299, 0xb4c0cc, 0xd8b4a0, 0xa9b3a0, 0xe0e0e0];
const ROOF_PALETTE = [0x9a4a3a, 0x8a5a3a, 0x556070, 0x6a6a6a];

export class Settlements {
  readonly mesh: InstancedMesh;
  readonly settlements: SettlementRuntime[] = [];

  private terrain: Terrain;
  private baseColor: Color[] = [];
  private instX: number[] = [];
  private instZ: number[] = [];
  private instBaseY: number[] = [];
  private instSettle: number[] = [];
  private instHeight: number[] = [];
  private instFlooded: Uint8Array;
  private origMatrix: Float32Array;
  private total = 0;

  constructor(terrain: Terrain) {
    this.terrain = terrain;

    // build instance list first (need total count)
    const specs: { m: Object3D; color: Color; z: number; baseY: number; h: number; si: number }[] = [];
    SETTLEMENTS.forEach((def, si) => {
      const gy = terrain.getHeight(def.x, def.z);
      const rt: SettlementRuntime = {
        ...def,
        center: new Vector3(def.x, gy, def.z),
        groundY: gy,
        count: 0,
        floodedCount: 0,
        get floodedFraction() { return this.count ? this.floodedCount / this.count : 0; },
        get isFlooded() { return this.count ? this.floodedCount / this.count > 0.35 : false; },
      };
      this.settlements.push(rt);
      this.scatter(def, si, rt, specs);
    });

    // a lot of standalone random houses across the whole green terrain
    this.scatterRandom(specs);

    this.total = specs.length;
    const geo = new BoxGeometry(1, 1, 1);
    const mat = new MeshStandardMaterial({ roughness: 0.85, metalness: 0.0 });
    this.mesh = new InstancedMesh(geo, mat, this.total);
    this.mesh.castShadow = true;
    this.mesh.receiveShadow = true;
    this.mesh.instanceMatrix.setUsage(DynamicDrawUsage);
    this.instFlooded = new Uint8Array(this.total);
    this.origMatrix = new Float32Array(this.total * 16);

    for (let i = 0; i < this.total; i++) {
      const sp = specs[i];
      sp.m.updateMatrix();
      this.mesh.setMatrixAt(i, sp.m.matrix);
      sp.m.matrix.toArray(this.origMatrix, i * 16);
      this.mesh.setColorAt(i, sp.color);
      this.baseColor.push(sp.color.clone());
      this.instX.push(sp.m.position.x);
      this.instZ.push(sp.z);
      this.instBaseY.push(sp.baseY);
      this.instSettle.push(sp.si);
      this.instHeight.push(sp.h);
    }
    this.mesh.instanceMatrix.needsUpdate = true;
    if (this.mesh.instanceColor) this.mesh.instanceColor.needsUpdate = true;
    this.mesh.name = 'Settlements';
  }
  private scatter(
    def: SettlementDef,
    si: number,
    rt: SettlementRuntime,
    specs: { m: Object3D; color: Color; z: number; baseY: number; h: number; si: number }[],
  ): void {
    let a = (971 + si * 7919) >>> 0;
    const rng = () => {
      a = (a + 0x6d2b79f5) | 0;
      let t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
    for (let k = 0; k < def.buildings; k++) {
      let x = def.x, z = def.z, ok = false;
      for (let tries = 0; tries < 10 && !ok; tries++) {
        const ang = rng() * Math.PI * 2;
        const r = Math.sqrt(rng()) * def.radius;
        x = def.x + Math.cos(ang) * r;
        z = def.z + Math.sin(ang) * r;
        if (Math.abs(x - this.terrain.riverCenterX(z)) > 56) ok = true;
      }
      const gy = this.terrain.getHeight(x, z);
      const distC = Math.hypot(x - def.x, z - def.z) / Math.max(def.radius, 1);
      let w: number, d: number, h: number, color: Color;

      if (def.type === 'farmland') {
        if (rng() < 0.18) {
          w = 8 + rng() * 6; d = 8 + rng() * 6; h = 5 + rng() * 4; // barn
          color = new Color(ROOF_PALETTE[(rng() * ROOF_PALETTE.length) | 0]);
        } else {
          w = 20 + rng() * 26; d = 20 + rng() * 26; h = 0.6 + rng() * 0.9; // field plot
          color = new Color().setHSL(0.22 + rng() * 0.08, 0.4, 0.34 + rng() * 0.1);
        }
      } else if (def.type === 'town') {
        if (distC < 0.35) { h = 34 + rng() * 48; w = 14 + rng() * 8; d = 14 + rng() * 8; }
        else if (distC < 0.7) { h = 16 + rng() * 22; w = 12 + rng() * 8; d = 12 + rng() * 8; }
        else { h = 6 + rng() * 8; w = 8 + rng() * 6; d = 8 + rng() * 6; }
        color = new Color(BUILDING_PALETTE[(rng() * BUILDING_PALETTE.length) | 0]);
      } else {
        h = 5 + rng() * 8; w = 7 + rng() * 6; d = 7 + rng() * 6;
        color = new Color(BUILDING_PALETTE[(rng() * BUILDING_PALETTE.length) | 0]);
      }
      color.multiplyScalar(0.82 + rng() * 0.3);
      w *= BUILD.homeScale; d *= BUILD.homeScale; h *= BUILD.homeScale;

      const m = new Object3D();
      m.position.set(x, gy + h / 2, z);
      m.scale.set(w, h, d);
      m.rotation.y = (Math.round(rng() * 3) * Math.PI) / 2 + (rng() - 0.5) * 0.12;
      specs.push({ m, color, z, baseY: gy, h, si });
      rt.count++;
    }
  }

  /** scatter many standalone houses over the whole terrain (si = -1, not counted
   *  toward any named settlement, but they still flood-tint + sink). */
  private scatterRandom(
    specs: { m: Object3D; color: Color; z: number; baseY: number; h: number; si: number }[],
  ): void {
    let a = 0x9e3779b9 >>> 0;
    const rng = () => {
      a = (a + 0x6d2b79f5) | 0;
      let t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
    const halfX = WORLD.terrainSizeX * 0.46;
    const halfZ = WORLD.terrainSizeZ * 0.46;
    const target = BUILD.randomHouses;
    let placed = 0;
    for (let tries = 0; tries < target * 8 && placed < target; tries++) {
      const x = (rng() * 2 - 1) * halfX;
      const z = (rng() * 2 - 1) * halfZ;
      // keep clear of the river channel + the dam body
      if (Math.abs(x - this.terrain.riverCenterX(z)) < 80) continue;
      if (Math.abs(z) < 130 && Math.abs(x) < 480) continue;
      const gy = this.terrain.getHeight(x, z);
      // upstream (reservoir side): only on the hills above the high-water line
      if (z < 0 && gy < WATER.reservoirMaxY + 6) continue;
      // avoid steep faces
      const sx = this.terrain.getHeight(x + 4, z);
      const sz = this.terrain.getHeight(x, z + 4);
      if ((Math.abs(sx - gy) + Math.abs(sz - gy)) / 4 > 1.1) continue;
      // don't pile onto the named settlements
      let clash = false;
      for (const s of this.settlements) {
        if (Math.hypot(x - s.x, z - s.z) < s.radius * 1.1) { clash = true; break; }
      }
      if (clash) continue;

      let w = (6 + rng() * 8) * BUILD.homeScale;
      let d = (6 + rng() * 8) * BUILD.homeScale;
      let h = (5 + rng() * 11) * BUILD.homeScale;
      if (rng() < 0.12) h *= 1.6; // the occasional taller block
      const color = new Color(BUILDING_PALETTE[(rng() * BUILDING_PALETTE.length) | 0]);
      color.multiplyScalar(0.8 + rng() * 0.32);

      const m = new Object3D();
      m.position.set(x, gy + h / 2, z);
      m.scale.set(w, h, d);
      m.rotation.y = (Math.round(rng() * 3) * Math.PI) / 2 + (rng() - 0.5) * 0.18;
      specs.push({ m, color, z, baseY: gy, h, si: -1 });
      placed++;
    }
  }

  /** advance the flood: recolour + sink buildings the spreading water has reached.
   *  Coverage matches the water shader's radial front (origin at the breach), so
   *  towns off to the side go under as the flood fans outward — not just straight down. */
  setFlood(reach: number, sheetY: number, originX: number, originZ: number): void {
    for (const s of this.settlements) s.floodedCount = 0;
    let colorDirty = false;
    let matrixDirty = false;
    const tmpC = new Color();
    const m4 = new Matrix4();
    for (let i = 0; i < this.total; i++) {
      const dz = this.instZ[i] - originZ;
      const dx = this.instX[i] - originX;
      const ds = Math.max(dz, 0);
      const us = Math.max(-dz, 0);
      const lat = Math.abs(dx);
      const rad = Math.sqrt(ds * ds * 0.30 + lat * lat * 1.15 + us * us * 6.0);
      const inund = rad <= reach && sheetY > this.instBaseY[i] + 0.4;
      const cur = inund ? 1 : 0;
      if (cur !== this.instFlooded[i]) {
        this.instFlooded[i] = cur;
        if (cur) {
          tmpC.copy(this.baseColor[i]).lerp(WET, 0.7);
          this.mesh.setColorAt(i, tmpC);
          const sink = Math.min(this.instHeight[i] * 0.4, 4.5);
          m4.fromArray(this.origMatrix, i * 16);
          m4.premultiply(new Matrix4().makeTranslation(0, -sink, 0));
          this.mesh.setMatrixAt(i, m4);
        } else {
          this.mesh.setColorAt(i, this.baseColor[i]);
          m4.fromArray(this.origMatrix, i * 16);
          this.mesh.setMatrixAt(i, m4);
        }
        colorDirty = true;
        matrixDirty = true;
      }
      const si = this.instSettle[i];
      if (cur && si >= 0) this.settlements[si].floodedCount++;
    }
    if (colorDirty && this.mesh.instanceColor) this.mesh.instanceColor.needsUpdate = true;
    if (matrixDirty) this.mesh.instanceMatrix.needsUpdate = true;
  }

  floodedTotal(): number {
    let n = 0;
    for (const s of this.settlements) if (s.isFlooded) n++;
    return n;
  }

  reset(): void {
    const m4 = new Matrix4();
    for (let i = 0; i < this.total; i++) {
      this.instFlooded[i] = 0;
      m4.fromArray(this.origMatrix, i * 16);
      this.mesh.setMatrixAt(i, m4);
      this.mesh.setColorAt(i, this.baseColor[i]);
    }
    for (const s of this.settlements) s.floodedCount = 0;
    this.mesh.instanceMatrix.needsUpdate = true;
    if (this.mesh.instanceColor) this.mesh.instanceColor.needsUpdate = true;
  }
}
