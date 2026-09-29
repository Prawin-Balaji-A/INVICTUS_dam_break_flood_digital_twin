/**
 * Stage.ts — renderer + scene + sky dome + fog + lights.
 */
import {
  WebGLRenderer,
  Scene,
  Fog,
  ACESFilmicToneMapping,
  SRGBColorSpace,
  PCFSoftShadowMap,
  DirectionalLight,
  AmbientLight,
  HemisphereLight,
  Mesh,
  SphereGeometry,
  BackSide,
  ShaderMaterial,
  Vector3,
  Color,
} from 'three';
import { SKY, RAIN_SKY } from '../config';

const lerp = (a: number, b: number, t: number) => a + (b - a) * t;

export class Stage {
  readonly renderer: WebGLRenderer;
  readonly scene: Scene;
  readonly sun: DirectionalLight;

  private fog!: Fog;
  private skyMat!: ShaderMaterial;
  private ambient!: AmbientLight;
  private hemi!: HemisphereLight;

  constructor(canvas: HTMLCanvasElement) {
    this.renderer = new WebGLRenderer({ canvas, antialias: true, powerPreference: 'high-performance' });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.renderer.setSize(window.innerWidth, window.innerHeight);
    this.renderer.toneMapping = ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = 1.05;
    this.renderer.outputColorSpace = SRGBColorSpace;
    this.renderer.shadowMap.enabled = true;
    this.renderer.shadowMap.type = PCFSoftShadowMap;

    this.scene = new Scene();
    this.fog = new Fog(SKY.fogColor, SKY.fogNear, SKY.fogFar);
    this.scene.fog = this.fog;

    this.addSky();
    this.sun = this.addLights();
  }

  /** blend the whole atmosphere between clear (0) and stormy overcast (1). */
  setWeather(t: number): void {
    const clearTop = SKY.topColor, clearBot = SKY.bottomColor;
    this.skyMat.uniforms.topColor.value.copy(clearTop).lerp(RAIN_SKY.topColor, t);
    this.skyMat.uniforms.bottomColor.value.copy(clearBot).lerp(RAIN_SKY.bottomColor, t);
    this.fog.color.copy(new Color(SKY.fogColor)).lerp(RAIN_SKY.fogColor, t);
    this.fog.near = lerp(SKY.fogNear, RAIN_SKY.fogNear, t);
    this.fog.far = lerp(SKY.fogFar, RAIN_SKY.fogFar, t);
    this.sun.intensity = lerp(SKY.sunIntensity, RAIN_SKY.sunIntensity, t);
    this.ambient.intensity = lerp(SKY.ambientIntensity, RAIN_SKY.ambientIntensity, t);
    this.hemi.intensity = lerp(SKY.hemiIntensity, 0.5, t);
    this.renderer.toneMappingExposure = lerp(1.05, RAIN_SKY.exposure, t);
  }

  private addSky(): void {
    const geo = new SphereGeometry(9000, 32, 16);
    const mat = new ShaderMaterial({
      side: BackSide,
      depthWrite: false,
      uniforms: {
        topColor: { value: SKY.topColor.clone() },
        bottomColor: { value: SKY.bottomColor.clone() },
        offset: { value: 400 },
        exponent: { value: 0.7 },
      },
      vertexShader: /* glsl */ `
        varying vec3 vWorld;
        void main() {
          vec4 wp = modelMatrix * vec4(position, 1.0);
          vWorld = wp.xyz;
          gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
        }
      `,
      fragmentShader: /* glsl */ `
        uniform vec3 topColor;
        uniform vec3 bottomColor;
        uniform float offset;
        uniform float exponent;
        varying vec3 vWorld;
        void main() {
          float h = normalize(vWorld + vec3(0.0, offset, 0.0)).y;
          float t = pow(clamp(h, 0.0, 1.0), exponent);
          gl_FragColor = vec4(mix(bottomColor, topColor, t), 1.0);
        }
      `,
    });
    const sky = new Mesh(geo, mat);
    sky.name = 'Sky';
    this.skyMat = mat;
    this.scene.add(sky);
  }

  private addLights(): DirectionalLight {
    const sun = new DirectionalLight(SKY.sunColor, SKY.sunIntensity);
    const d = new Vector3(...SKY.sunDir).normalize().multiplyScalar(1800);
    sun.position.copy(d);
    sun.castShadow = true;
    sun.shadow.mapSize.set(2048, 2048);
    const cam = sun.shadow.camera;
    cam.near = 100;
    cam.far = 5000;
    const s = 1600;
    cam.left = -s; cam.right = s; cam.top = s; cam.bottom = -s;
    sun.shadow.bias = -0.0004;
    sun.shadow.normalBias = 2.0;
    this.scene.add(sun);
    this.scene.add(sun.target);

    const amb = new AmbientLight(SKY.ambientColor, SKY.ambientIntensity);
    this.ambient = amb;
    this.scene.add(amb);

    const hemi = new HemisphereLight(SKY.hemiSky, SKY.hemiGround, SKY.hemiIntensity);
    this.hemi = hemi;
    this.scene.add(hemi);

    // subtle cool rim light from downstream
    const rim = new DirectionalLight(new Color(0x8fb6ff), 0.4);
    rim.position.set(-600, 300, -900);
    this.scene.add(rim);

    return sun;
  }

  resize(): void {
    this.renderer.setSize(window.innerWidth, window.innerHeight);
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  }
}
