/**
 * Markers.ts — floating canvas-text name labels above each settlement, with a
 * ground ring + pole. Labels billboard (Sprites) and scale to stay legible.
 * pick() raycasts labels+rings and returns the hit settlement (drag-guarded by caller).
 */
import {
  Group,
  Sprite,
  SpriteMaterial,
  CanvasTexture,
  Mesh,
  RingGeometry,
  CylinderGeometry,
  MeshBasicMaterial,
  Raycaster,
  Vector2,
  Vector3,
  Camera,
  DoubleSide,
  SRGBColorSpace,
  Object3D,
} from 'three';
import { SettlementRuntime } from './Settlements';

interface Marker {
  s: SettlementRuntime;
  sprite: Sprite;
  ring: Mesh;
  pole: Mesh;
  labelY: number;
  redraw: (flooded: boolean) => void;
  flooded: boolean;
}

export class Markers {
  readonly group = new Group();
  private markers: Marker[] = [];
  private ray = new Raycaster();
  private pickables: Object3D[] = [];

  constructor(settlements: SettlementRuntime[]) {
    for (const s of settlements) {
      this.addMarker(s);
    }
  }

  private makeLabelTexture(text: string, sub: string, flooded: boolean): CanvasTexture {
    const canvas = document.createElement('canvas');
    canvas.width = 512;
    canvas.height = 160;
    const ctx = canvas.getContext('2d')!;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    // pill background
    const bg = flooded ? 'rgba(150, 40, 32, 0.92)' : 'rgba(14, 22, 34, 0.9)';
    const border = flooded ? '#ff7a68' : '#3fa9f5';
    const r = 34;
    ctx.beginPath();
    ctx.moveTo(r, 6);
    ctx.arcTo(canvas.width - 6, 6, canvas.width - 6, canvas.height - 34, r);
    ctx.arcTo(canvas.width - 6, canvas.height - 34, 6, canvas.height - 34, r);
    ctx.arcTo(6, canvas.height - 34, 6, 6, r);
    ctx.arcTo(6, 6, canvas.width - 6, 6, r);
    ctx.closePath();
    ctx.fillStyle = bg;
    ctx.fill();
    ctx.lineWidth = 5;
    ctx.strokeStyle = border;
    ctx.stroke();
    // pointer triangle
    ctx.beginPath();
    ctx.moveTo(canvas.width / 2 - 22, canvas.height - 34);
    ctx.lineTo(canvas.width / 2 + 22, canvas.height - 34);
    ctx.lineTo(canvas.width / 2, canvas.height - 6);
    ctx.closePath();
    ctx.fillStyle = bg;
    ctx.fill();
    // text
    ctx.fillStyle = '#eef5ff';
    ctx.font = 'bold 54px -apple-system, Segoe UI, Roboto, sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(text, canvas.width / 2, 58);
    ctx.font = '600 26px -apple-system, Segoe UI, Roboto, sans-serif';
    ctx.fillStyle = flooded ? '#ffd9d2' : '#8ea3ba';
    ctx.fillText(flooded ? '⚠ FLOODED' : sub.toUpperCase(), canvas.width / 2, 104);
    const tex = new CanvasTexture(canvas);
    tex.colorSpace = SRGBColorSpace;
    tex.needsUpdate = true;
    return tex;
  }

  private addMarker(s: SettlementRuntime): void {
    const labelY = s.groundY + (s.type === 'town' ? 110 : 66);
    const spriteMat = new SpriteMaterial({
      map: this.makeLabelTexture(s.name, s.type, false),
      transparent: true,
      depthTest: true,
      depthWrite: false,
    });
    const sprite = new Sprite(spriteMat);
    sprite.position.set(s.center.x, labelY, s.center.z);
    sprite.scale.set(64, 20, 1);
    sprite.userData.id = s.id;
    this.group.add(sprite);
    this.pickables.push(sprite);

    // ground ring
    const ringGeo = new RingGeometry(s.radius * 0.9, s.radius * 1.02, 48);
    ringGeo.rotateX(-Math.PI / 2);
    const ringMat = new MeshBasicMaterial({ color: s.color, transparent: true, opacity: 0.5, side: DoubleSide });
    const ring = new Mesh(ringGeo, ringMat);
    ring.position.set(s.center.x, s.groundY + 0.6, s.center.z);
    ring.userData.id = s.id;
    this.group.add(ring);
    this.pickables.push(ring);

    // pole
    const poleGeo = new CylinderGeometry(0.7, 0.7, labelY - s.groundY, 6);
    const poleMat = new MeshBasicMaterial({ color: s.color, transparent: true, opacity: 0.55 });
    const pole = new Mesh(poleGeo, poleMat);
    pole.position.set(s.center.x, (labelY + s.groundY) / 2, s.center.z);
    this.group.add(pole);

    const redraw = (flooded: boolean) => {
      spriteMat.map?.dispose();
      spriteMat.map = this.makeLabelTexture(s.name, s.type, flooded);
      spriteMat.needsUpdate = true;
      (ringMat.color as any).set(flooded ? 0xff5a48 : s.color);
      (poleMat.color as any).set(flooded ? 0xff5a48 : s.color);
    };

    this.markers.push({ s, sprite, ring, pole, labelY, redraw, flooded: false });
  }

  /** keep labels a legible on-screen size + refresh flooded state. */
  update(camera: Camera): void {
    const camPos = (camera as any).position as Vector3;
    for (const m of this.markers) {
      const dist = camPos.distanceTo(m.sprite.position);
      const scale = Math.min(180, Math.max(46, dist * 0.09));
      m.sprite.scale.set(scale, scale * 0.3125, 1);
      if (m.s.isFlooded !== m.flooded) {
        m.flooded = m.s.isFlooded;
        m.redraw(m.flooded);
      }
    }
  }

  /** ndc pointer -> settlement hit (or null). */
  pick(ndc: Vector2, camera: Camera): SettlementRuntime | null {
    this.ray.setFromCamera(ndc, camera);
    const hits = this.ray.intersectObjects(this.pickables, false);
    if (hits.length === 0) return null;
    const id = hits[0].object.userData.id as string;
    const m = this.markers.find((mm) => mm.s.id === id);
    return m ? m.s : null;
  }

  resetFlooded(): void {
    for (const m of this.markers) {
      if (m.flooded) {
        m.flooded = false;
        m.redraw(false);
      }
    }
  }
}
