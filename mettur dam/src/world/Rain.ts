/**
 * Rain.ts — GPU-instanced rainfall + an overcast cloud ceiling for the storm.
 * The falling streaks animate entirely in the vertex shader (per-instance offset +
 * time), so the CPU only nudges a couple of uniforms per frame. A big translucent
 * cloud plane drifts overhead. Both fade with setActive(strength 0..1).
 */
import {
  Group,
  Mesh,
  BoxGeometry,
  InstancedBufferGeometry,
  InstancedBufferAttribute,
  ShaderMaterial,
  PlaneGeometry,
  MeshBasicMaterial,
  CanvasTexture,
  RepeatWrapping,
  DoubleSide,
  Color,
  PerspectiveCamera,
} from 'three';
import { RAIN } from '../config';

const RAIN_VERT = /* glsl */ `
  attribute vec3 iOffset;   // x,z within the volume; y = fall phase
  attribute float iSpeed;
  uniform float uTime;
  uniform vec3 uCenter;     // volume centre (follows camera in xz)
  uniform float uTop;       // spawn height above centre
  uniform float uRange;     // total vertical fall span (wraps)
  void main() {
    float d = mod(iSpeed * uTime + iOffset.y, uRange);
    float cy = uCenter.y + uTop - d;
    vec3 wp = vec3(uCenter.x + iOffset.x, cy, uCenter.z + iOffset.z) + position;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(wp, 1.0);
  }
`;

const RAIN_FRAG = /* glsl */ `
  precision mediump float;
  uniform vec3 uColor;
  uniform float uOpacity;
  void main() {
    gl_FragColor = vec4(uColor, uOpacity);
  }
`;

export class Rain {
  readonly group = new Group();
  private mat: ShaderMaterial;
  private cloud: Mesh;
  private cloudMat: MeshBasicMaterial;
  private cloudTex: CanvasTexture;
  private mesh: Mesh;
  private time = 0;
  private strength = 0;
  private range: number;

  constructor() {
    this.range = RAIN.top + 260;

    // ---- instanced rain streaks ----
    const box = new BoxGeometry(0.5, RAIN.streakLen, 0.5);
    const geo = new InstancedBufferGeometry();
    geo.index = box.index;
    geo.attributes.position = box.attributes.position;
    const offsets = new Float32Array(RAIN.count * 3);
    const speeds = new Float32Array(RAIN.count);
    for (let i = 0; i < RAIN.count; i++) {
      offsets[i * 3] = (Math.random() * 2 - 1) * RAIN.area;
      offsets[i * 3 + 1] = Math.random() * this.range; // fall phase
      offsets[i * 3 + 2] = (Math.random() * 2 - 1) * RAIN.area;
      speeds[i] = RAIN.fallSpeed * (0.82 + Math.random() * 0.36);
    }
    geo.setAttribute('iOffset', new InstancedBufferAttribute(offsets, 3));
    geo.setAttribute('iSpeed', new InstancedBufferAttribute(speeds, 1));
    geo.instanceCount = RAIN.count;

    this.mat = new ShaderMaterial({
      vertexShader: RAIN_VERT,
      fragmentShader: RAIN_FRAG,
      transparent: true,
      depthWrite: false,
      uniforms: {
        uTime: { value: 0 },
        uCenter: { value: [0, 40, 0] as unknown as number[] },
        uTop: { value: RAIN.top },
        uRange: { value: this.range },
        uColor: { value: new Color(0xaecbe6) },
        uOpacity: { value: 0 },
      },
    });
    this.mesh = new Mesh(geo, this.mat);
    this.mesh.frustumCulled = false;
    this.mesh.renderOrder = 4;
    this.mesh.visible = false;
    this.group.add(this.mesh);

    // ---- overcast cloud ceiling ----
    this.cloudTex = this.makeCloudTexture();
    this.cloudMat = new MeshBasicMaterial({
      map: this.cloudTex,
      transparent: true,
      opacity: 0,
      depthWrite: false,
      side: DoubleSide,
      fog: false,
    });
    const cgeo = new PlaneGeometry(9000, 9000);
    cgeo.rotateX(Math.PI / 2); // lie flat overhead
    this.cloud = new Mesh(cgeo, this.cloudMat);
    this.cloud.position.set(0, 900, 0);
    this.cloud.frustumCulled = false;
    this.cloud.renderOrder = 1;
    this.cloud.visible = false;
    this.group.add(this.cloud);
  }

  private makeCloudTexture(): CanvasTexture {
    const c = document.createElement('canvas');
    c.width = c.height = 512;
    const ctx = c.getContext('2d')!;
    ctx.fillStyle = '#2c313a';
    ctx.fillRect(0, 0, 512, 512);
    for (let i = 0; i < 220; i++) {
      const x = Math.random() * 512;
      const y = Math.random() * 512;
      const r = 30 + Math.random() * 120;
      const g = ctx.createRadialGradient(x, y, 0, x, y, r);
      const shade = 40 + Math.floor(Math.random() * 70);
      g.addColorStop(0, `rgba(${shade},${shade + 6},${shade + 14},${0.12 + Math.random() * 0.18})`);
      g.addColorStop(1, 'rgba(0,0,0,0)');
      ctx.fillStyle = g;
      ctx.beginPath();
      ctx.arc(x, y, r, 0, Math.PI * 2);
      ctx.fill();
    }
    const tex = new CanvasTexture(c);
    tex.wrapS = tex.wrapT = RepeatWrapping;
    tex.repeat.set(3, 3);
    tex.needsUpdate = true;
    return tex;
  }

  /** target storm strength 0..1 (Simulation ramps this each frame). */
  setActive(strength: number): void {
    this.strength = strength;
    const on = strength > 0.002;
    this.mesh.visible = on;
    this.cloud.visible = on;
    this.mat.uniforms.uOpacity.value = 0.42 * strength;
    this.cloudMat.opacity = 0.82 * strength;
  }

  update(dt: number, camera: PerspectiveCamera): void {
    if (this.strength <= 0.002) return;
    this.time += dt;
    this.mat.uniforms.uTime.value = this.time;
    const c = this.mat.uniforms.uCenter.value as number[];
    c[0] = camera.position.x;
    c[1] = 40;
    c[2] = camera.position.z;
    this.cloud.position.x = camera.position.x;
    this.cloud.position.z = camera.position.z;
    this.cloudTex.offset.x = (this.cloudTex.offset.x + dt * 0.006) % 1;
    this.cloudTex.offset.y = (this.cloudTex.offset.y + dt * 0.003) % 1;
  }

  reset(): void {
    this.setActive(0);
    this.time = 0;
  }
}
