/**
 * Spray.ts — additive droplet/foam particles at the gate jets and the breach.
 * One InstancedMesh pool; particles are spawned from jet points (scaled by gate
 * opening x head) and in a big burst at breach, then fall under gravity and fade.
 */
import {
  InstancedMesh,
  IcosahedronGeometry,
  MeshBasicMaterial,
  Object3D,
  Vector3,
  AdditiveBlending,
  Color,
} from 'three';
import { SPRAY } from '../config';

export class Spray {
  readonly mesh: InstancedMesh;
  private max: number;
  private pos: Float32Array;
  private vel: Float32Array;
  private life: Float32Array;
  private ttl: Float32Array;
  private dummy = new Object3D();
  private cursor = 0;

  constructor() {
    this.max = SPRAY.gateJetCount + SPRAY.breachBurstCount;
    const geo = new IcosahedronGeometry(SPRAY.dropSize, 0);
    const mat = new MeshBasicMaterial({
      color: new Color(0xeaf4ff),
      transparent: true,
      opacity: 0.85,
      blending: AdditiveBlending,
      depthWrite: false,
    });
    this.mesh = new InstancedMesh(geo, mat, this.max);
    this.mesh.frustumCulled = false;
    this.mesh.renderOrder = 3;
    this.pos = new Float32Array(this.max * 3);
    this.vel = new Float32Array(this.max * 3);
    this.life = new Float32Array(this.max);
    this.ttl = new Float32Array(this.max);
    // park all instances off-screen initially
    this.dummy.position.set(0, -100000, 0);
    this.dummy.updateMatrix();
    for (let i = 0; i < this.max; i++) this.mesh.setMatrixAt(i, this.dummy.matrix);
    this.mesh.instanceMatrix.needsUpdate = true;
  }

  private spawn(x: number, y: number, z: number, vx: number, vy: number, vz: number, ttl: number): void {
    // find a slot (round-robin; overwrite oldest if none dead)
    let idx = -1;
    for (let k = 0; k < this.max; k++) {
      const c = (this.cursor + k) % this.max;
      if (this.life[c] <= 0) { idx = c; break; }
    }
    if (idx < 0) { idx = this.cursor; }
    this.cursor = (idx + 1) % this.max;
    const i3 = idx * 3;
    this.pos[i3] = x; this.pos[i3 + 1] = y; this.pos[i3 + 2] = z;
    this.vel[i3] = vx; this.vel[i3 + 1] = vy; this.vel[i3 + 2] = vz;
    this.life[idx] = ttl;
    this.ttl[idx] = ttl;
  }

  /** continuous jets at the spillway gates; intensity 0..1 (gatesOpen * head). */
  emitJets(points: Vector3[], intensity: number, dt: number): void {
    if (intensity <= 0.001 || points.length === 0) return;
    const perFrame = Math.min(90, Math.floor(SPRAY.gateJetCount * 0.06 * intensity * (dt * 60)));
    for (let i = 0; i < perFrame; i++) {
      const p = points[(Math.random() * points.length) | 0];
      const speed = 20 + 55 * intensity;
      this.spawn(
        p.x + (Math.random() - 0.5) * 26,
        p.y + Math.random() * 6,
        p.z + (Math.random() - 0.5) * 8,
        (Math.random() - 0.5) * 14,
        6 + Math.random() * 10,
        speed * (0.6 + Math.random() * 0.7), // downstream +Z
        1.0 + Math.random() * 1.2,
      );
    }
  }

  /** one-off burst (breach). */
  burst(center: Vector3, count: number, spread: number): void {
    for (let i = 0; i < count; i++) {
      const ang = Math.random() * Math.PI * 2;
      const r = Math.random() * spread;
      this.spawn(
        center.x + Math.cos(ang) * r * 0.5,
        center.y + Math.random() * 20,
        center.z + (Math.random() - 0.2) * spread * 0.4,
        Math.cos(ang) * (10 + Math.random() * 30),
        20 + Math.random() * 40,
        Math.abs(Math.sin(ang)) * 30 + Math.random() * 60, // biased downstream
        1.4 + Math.random() * 1.6,
      );
    }
  }

  update(dt: number): void {
    let anyAlive = false;
    for (let i = 0; i < this.max; i++) {
      if (this.life[i] <= 0) continue;
      anyAlive = true;
      this.life[i] -= dt;
      const i3 = i * 3;
      this.vel[i3 + 1] += SPRAY.gravity * dt;
      this.pos[i3] += this.vel[i3] * dt;
      this.pos[i3 + 1] += this.vel[i3 + 1] * dt;
      this.pos[i3 + 2] += this.vel[i3 + 2] * dt;
      if (this.pos[i3 + 1] < 0) { this.life[i] = 0; }
      const f = Math.max(0, this.life[i] / this.ttl[i]);
      if (this.life[i] <= 0) {
        this.dummy.position.set(0, -100000, 0);
        this.dummy.scale.setScalar(0.001);
      } else {
        this.dummy.position.set(this.pos[i3], this.pos[i3 + 1], this.pos[i3 + 2]);
        this.dummy.scale.setScalar(0.4 + f * 0.9);
      }
      this.dummy.updateMatrix();
      this.mesh.setMatrixAt(i, this.dummy.matrix);
    }
    if (anyAlive) this.mesh.instanceMatrix.needsUpdate = true;
  }

  reset(): void {
    for (let i = 0; i < this.max; i++) this.life[i] = 0;
    this.dummy.position.set(0, -100000, 0);
    this.dummy.scale.setScalar(0.001);
    this.dummy.updateMatrix();
    for (let i = 0; i < this.max; i++) this.mesh.setMatrixAt(i, this.dummy.matrix);
    this.mesh.instanceMatrix.needsUpdate = true;
  }
}
