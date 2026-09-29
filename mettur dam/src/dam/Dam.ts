/**
 * Dam.ts — loads mettur-dam-only.glb, seats/scales it into world space,
 * recolours materials, drives the baked spillway-gate animation, and performs
 * the breach crumble.
 */
import {
  Group,
  Box3,
  Vector3,
  AnimationMixer,
  AnimationAction,
  LoopOnce,
  Mesh,
  Object3D,
  Quaternion,
  MeshStandardMaterial,
  Material,
} from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { DAM, GATES, BREACH } from '../config';

interface BreachBlock {
  obj: Object3D;
  vel: Vector3;
  ang: Vector3;
  origPos: Vector3;
  origQuat: Quaternion;
}

const OPEN_GATE_RE = /GATE_CTRL_(02|03|06|07|08|11|12)\b/;

export class Dam {
  readonly root = new Group();
  private mixer?: AnimationMixer;
  private gateActions: AnimationAction[] = [];
  private gateDuration = 1;
  private gatesPlaying = false;

  jetPoints: Vector3[] = [];
  crestY = DAM.crestY;
  breachCenter = new Vector3(0, 30, 0);
  private toeZ = DAM.toeZ;

  private blocks: BreachBlock[] = [];
  private breaching = false;
  private floorY = 1;

  async load(url: string): Promise<void> {
    const loader = new GLTFLoader();
    const gltf = await loader.loadAsync(url);
    const model = gltf.scene;

    this.seat(model);
    this.recolor(model);
    this.root.add(model);

    // ---- gate animation ----
    const gateClips = gltf.animations.filter((c) => GATES.openClipRegex.test(c.name));
    if (gateClips.length) {
      this.mixer = new AnimationMixer(model);
      for (const clip of gateClips) {
        this.gateDuration = Math.max(this.gateDuration, clip.duration);
        const action = this.mixer.clipAction(clip);
        action.loop = LoopOnce;
        action.clampWhenFinished = true;
        action.timeScale = GATES.timeScale;
        action.enabled = true;
        action.paused = true; // primed at t=0, closed
        action.play();
        this.gateActions.push(action);
      }
      this.mixer.update(0);
    }

    this.collectJetPoints(model);
    this.collectBlocks(model);
  }

  /** scale + orient + seat so the crest spans ~targetCrestLength on X and the toe rests at y=0. */
  private seat(model: Object3D): void {
    model.updateMatrixWorld(true);
    const box = new Box3().setFromObject(model);
    const size = new Vector3();
    box.getSize(size);
    const scale = DAM.targetCrestLength / Math.max(size.x, 1e-3);
    model.scale.setScalar(scale);
    model.updateMatrixWorld(true);

    box.setFromObject(model);
    const center = new Vector3();
    box.getCenter(center);
    model.position.x += DAM.axisX - center.x;
    model.position.y += DAM.seatBaseY - box.min.y;
    model.position.z += -40 - box.min.z; // upstream face near z=-40, apron extends +Z
    model.updateMatrixWorld(true);

    box.setFromObject(model);
    this.crestY = box.max.y;
    this.toeZ = box.max.z;
    this.breachCenter.set(DAM.axisX, box.max.y * 0.45, (box.min.z + box.max.z) * 0.5);
    if (import.meta.env?.DEV) {
      console.log('[Dam] seated bbox', box.min.toArray().map((n) => n.toFixed(1)), box.max.toArray().map((n) => n.toFixed(1)), 'scale', scale.toFixed(3));
    }
  }
  private recolor(model: Object3D): void {
    model.traverse((o) => {
      if (!(o as Mesh).isMesh) return;
      const mesh = o as Mesh;
      // hide any stray mantaflow helper geometry (safety; harmless here)
      if (/domain|effector|inflow|mantaflow|^cube(\.|_|$)/i.test(mesh.name)) {
        mesh.visible = false;
        return;
      }
      mesh.castShadow = true;
      mesh.receiveShadow = true;
      const mats: Material[] = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
      for (const m of mats) {
        const std = m as MeshStandardMaterial;
        const name = (m.name || '').toLowerCase();
        if (!std.color) continue;
        if (name.includes('gate') || name.includes('steel')) {
          std.color.setHex(0x8a9099);
          std.metalness = 0.85;
          std.roughness = 0.34;
        } else if (name.includes('dark')) {
          std.color.setHex(0x646a70);
          std.metalness = 0.0;
          std.roughness = 0.88;
        } else {
          // concrete (default)
          std.color.setHex(0xb7bac0);
          std.metalness = 0.0;
          std.roughness = 0.92;
        }
        std.needsUpdate = true;
      }
    });
  }

  /** world-space spill jet origins at the opening gates (fallback: spread across crest). */
  private collectJetPoints(model: Object3D): void {
    const pts: Vector3[] = [];
    model.updateMatrixWorld(true);
    model.traverse((o) => {
      if (OPEN_GATE_RE.test(o.name)) {
        const p = new Vector3();
        o.getWorldPosition(p);
        // nudge to the downstream sill and a touch below the crest
        p.z = Math.max(p.z, this.toeZ - 20);
        p.y = this.crestY * 0.5;
        pts.push(p);
      }
    });
    if (pts.length === 0) {
      const n = 7;
      for (let i = 0; i < n; i++) {
        const t = (i + 0.5) / n - 0.5;
        pts.push(new Vector3(DAM.axisX + t * DAM.targetCrestLength * 0.6, this.crestY * 0.5, this.toeZ - 10));
      }
    }
    this.jetPoints = pts;
  }

  /** select a few localized central pieces that shed on breach — the dam stays intact. */
  private collectBlocks(model: Object3D): void {
    const skipRe = /Foundation|Abutment|GATE|Baffle|Terrain|Ground/i;
    const cand: { obj: Object3D; d: number }[] = [];
    const bb = new Box3();
    const sz = new Vector3();
    const p = new Vector3();
    model.updateMatrixWorld(true);
    model.traverse((o) => {
      if (!(o as Mesh).isMesh) return;
      if (skipRe.test(o.name)) return;
      o.getWorldPosition(p);
      if (Math.abs(p.x - DAM.axisX) > BREACH.notchHalfWidth) return;
      if (p.y < this.crestY * 0.28) return; // only upper crest-region pieces detach
      bb.setFromObject(o);
      bb.getSize(sz);
      const vol = sz.x * sz.y * sz.z;
      // never fling a monolithic main-body slab — that would destroy the whole dam
      if (vol > BREACH.maxChunkVol || sz.x > BREACH.notchHalfWidth * 1.7) return;
      cand.push({ obj: o, d: p.distanceTo(this.breachCenter) });
    });
    cand.sort((a, b) => a.d - b.d);
    let keep = cand.slice(0, BREACH.maxChunks);
    // fallback: if the filters matched nothing, take the closest few meshes to the notch
    if (keep.length === 0) {
      const any: { obj: Object3D; d: number }[] = [];
      model.traverse((o) => {
        if (!(o as Mesh).isMesh || skipRe.test(o.name)) return;
        o.getWorldPosition(p);
        if (Math.abs(p.x - DAM.axisX) > BREACH.notchHalfWidth) return;
        any.push({ obj: o, d: p.distanceTo(this.breachCenter) });
      });
      any.sort((a, b) => a.d - b.d);
      keep = any.slice(0, Math.min(6, any.length));
    }
    for (const c of keep) {
      this.blocks.push({
        obj: c.obj,
        vel: new Vector3(),
        ang: new Vector3(),
        origPos: c.obj.position.clone(),
        origQuat: c.obj.quaternion.clone(),
      });
    }
    if (import.meta.env?.DEV) console.log('[Dam] breach chunks (localized):', this.blocks.length);
  }

  /** true once the localized breach has shed its chunks. */
  get isDamaged(): boolean {
    return this.breaching;
  }

  openGates(): void {
    if (!this.mixer || this.gatesPlaying) return;
    this.gatesPlaying = true;
    for (const a of this.gateActions) {
      a.paused = false;
      a.reset();
      a.timeScale = GATES.timeScale;
      a.play();
    }
  }

  /** 0 (closed) .. 1 (fully open). */
  gatesOpenFraction(): number {
    if (!this.mixer || !this.gatesPlaying || this.gateActions.length === 0) return 0;
    const a = this.gateActions[0];
    return Math.min(1, a.time / this.gateDuration);
  }

  startBreach(headNorm: number): void {
    if (this.breaching) return;
    this.breaching = true;
    const wash = BREACH.downstreamWash * (0.6 + headNorm);
    for (const b of this.blocks) {
      const p = new Vector3();
      b.obj.getWorldPosition(p);
      const lateral = (p.x - DAM.axisX) / Math.max(BREACH.notchHalfWidth, 1);
      b.vel.set(
        lateral * 10 + (Math.random() - 0.5) * 8,
        4 + Math.random() * 10,
        wash * (0.5 + Math.random() * 0.8),
      );
      b.ang.set(
        (Math.random() - 0.5) * BREACH.spinRate,
        (Math.random() - 0.5) * BREACH.spinRate,
        (Math.random() - 0.5) * BREACH.spinRate,
      );
    }
  }

  update(dt: number): void {
    if (this.mixer) this.mixer.update(dt);
    if (!this.breaching) return;
    for (const b of this.blocks) {
      b.vel.y += BREACH.gravity * dt;
      b.obj.position.x += b.vel.x * dt;
      b.obj.position.y += b.vel.y * dt;
      b.obj.position.z += b.vel.z * dt;
      b.obj.rotateX(b.ang.x * dt);
      b.obj.rotateY(b.ang.y * dt);
      b.obj.rotateZ(b.ang.z * dt);
      if (b.obj.position.y < this.floorY && b.vel.y < 0) {
        b.obj.position.y = this.floorY;
        b.vel.y = -b.vel.y * BREACH.groundBounce;
        b.vel.x *= 0.7;
        b.vel.z *= 0.82;
        b.ang.multiplyScalar(0.6);
      }
    }
  }

  reset(): void {
    this.breaching = false;
    this.gatesPlaying = false;
    for (const b of this.blocks) {
      b.obj.position.copy(b.origPos);
      b.obj.quaternion.copy(b.origQuat);
    }
    if (this.mixer) {
      for (const a of this.gateActions) {
        a.reset();
        a.paused = true;
      }
      this.mixer.update(0);
    }
  }
}
