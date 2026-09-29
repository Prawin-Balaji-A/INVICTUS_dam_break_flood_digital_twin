/**
 * CameraRig.ts — perspective camera + OrbitControls with a smoothstep fly-to tween,
 * focus(settlement) / overview(), and a decaying breach shake.
 */
import { PerspectiveCamera, Vector3, MathUtils } from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { CAMERA } from '../config';
import { SettlementRuntime } from '../world/Settlements';

export class CameraRig {
  readonly camera: PerspectiveCamera;
  readonly controls: OrbitControls;

  private flying = false;
  private t = 0;
  private dur = 1;
  private fromPos = new Vector3();
  private toPos = new Vector3();
  private fromTgt = new Vector3();
  private toTgt = new Vector3();

  private shakeMag = 0;
  private shakeT = 0;
  private prevShake = new Vector3();

  constructor(dom: HTMLElement) {
    this.camera = new PerspectiveCamera(CAMERA.fov, window.innerWidth / window.innerHeight, CAMERA.near, CAMERA.far);
    this.camera.position.set(...CAMERA.overviewPos);

    this.controls = new OrbitControls(this.camera, dom);
    this.controls.enableDamping = true;
    this.controls.dampingFactor = 0.06;
    this.controls.maxPolarAngle = Math.PI * 0.495; // don't go under the ground
    this.controls.minDistance = 40;
    this.controls.maxDistance = 3000;
    this.controls.target.set(...CAMERA.overviewTarget);
    this.controls.update();
  }

  private flyTween(pos: Vector3, tgt: Vector3, duration = CAMERA.flyDuration): void {
    this.fromPos.copy(this.camera.position);
    this.toPos.copy(pos);
    this.fromTgt.copy(this.controls.target);
    this.toTgt.copy(tgt);
    this.t = 0;
    this.dur = Math.max(0.001, duration);
    this.flying = true;
    this.controls.enabled = false;
  }

  focus(s: SettlementRuntime): void {
    const center = new Vector3(s.center.x, s.center.y + 12, s.center.z);
    const side = s.x >= 0 ? 1 : -1;
    const pos = new Vector3(
      s.center.x + side * CAMERA.focusDist * 0.55,
      s.center.y + CAMERA.focusHeight,
      s.center.z + CAMERA.focusDist,
    );
    this.flyTween(pos, center);
  }

  overview(): void {
    this.flyTween(new Vector3(...CAMERA.overviewPos), new Vector3(...CAMERA.overviewTarget));
  }

  shake(magnitude: number, duration: number): void {
    this.shakeMag = magnitude;
    this.shakeT = duration;
  }

  update(dt: number): void {
    // remove last frame's shake offset before any control/tween math
    this.camera.position.sub(this.prevShake);

    if (this.flying) {
      this.t += dt / this.dur;
      const k = MathUtils.smoothstep(Math.min(this.t, 1), 0, 1);
      this.camera.position.lerpVectors(this.fromPos, this.toPos, k);
      this.controls.target.lerpVectors(this.fromTgt, this.toTgt, k);
      if (this.t >= 1) {
        this.flying = false;
        this.controls.enabled = true;
      }
    }
    this.controls.update();

    // apply fresh shake
    this.prevShake.set(0, 0, 0);
    if (this.shakeT > 0) {
      this.shakeT -= dt;
      const amp = this.shakeMag * Math.max(0, this.shakeT);
      this.prevShake.set(
        (Math.random() - 0.5) * amp,
        (Math.random() - 0.5) * amp,
        (Math.random() - 0.5) * amp,
      );
      this.camera.position.add(this.prevShake);
    }
  }

  resize(): void {
    this.camera.aspect = window.innerWidth / window.innerHeight;
    this.camera.updateProjectionMatrix();
  }
}
