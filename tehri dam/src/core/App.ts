// ============================================================
// App.ts — Main application: Map view → 3D Dam simulation
// Loads wowdam.glb, generates terrain, water sim, dam break
// ============================================================

import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { DamInfo } from '../map/DamData';

// ---- Water surface shaders ------------------------------------------------
// The plane samples a baked terrain heightmap, so the surface hugs the real
// ground: it only appears where water actually sits (upstream reservoir, and a
// thin advancing sheet downstream once the dam is breached). No glass volume.
const WATER_VERT = /* glsl */ `
  uniform float uTime, uWaterY, uFloodZ, uDamZ, uHalf, uSeed, uToeZ, uBaseFlow, uDamX;
  uniform sampler2D uHeightMap;
  varying vec3 vWorld;
  varying vec3 vNormal;
  varying float vDepth;
  varying float vFoam;

  float terrainAt(vec2 p){
    vec2 uv = (p + uHalf) / (2.0 * uHalf);
    return texture2D(uHeightMap, uv).r;
  }

  float surfAt(vec2 p, out float depth, out float foam){
    float th = terrainAt(p);
    float surf;
    if (p.y <= uDamZ) {                 // p.y is world z: reservoir side
      surf = uWaterY;
      depth = surf - th;
      foam = 0.0;
    } else {                            // downstream flood sheet + steady tailrace
      float front = uFloodZ - p.y;
      float fd = clamp(front / 8.0, 0.0, 1.0) * min(uWaterY - th, 10.0);
      fd = max(fd, 0.0);
      // A working dam always releases a little water: a steady, shallow river
      // runs from the toe downstream, anchored at the dam centre then rejoining
      // the natural channel. Independent of the (post-breach) flood sheet.
      float river = 0.0;
      if (p.y > uToeZ) {
        float cx = sin(p.y * 0.012 + uSeed) * 16.0 + sin(p.y * 0.045 + uSeed * 1.7) * 5.0;
        float blend = clamp((p.y - uToeZ) / 40.0, 0.0, 1.0);
        float rc = mix(uDamX, cx, blend);
        river = (1.0 - smoothstep(7.0, 17.0, abs(p.x - rc))) * uBaseFlow;
      }
      float d = max(fd, river);
      surf = th + d;
      depth = d;
      foam = max(clamp(1.0 - front / 7.0, 0.0, 1.0), river > 0.15 ? 0.22 : 0.0);
    }
    float amp = clamp(depth * 0.4, 0.0, 1.0);
    float w = sin(p.x * 0.25 + uTime * 1.6) * 0.18
            + sin(p.y * 0.19 + uTime * 1.3) * 0.13
            + sin((p.x + p.y) * 0.12 + uTime * 0.9) * 0.09;
    return surf + w * amp;
  }

  void main(){
    vec2 p = position.xz;
    float depth, foam;
    float y = surfAt(p, depth, foam);
    float e = 1.5, dd, ff;
    float yL = surfAt(p + vec2(-e, 0.0), dd, ff);
    float yR = surfAt(p + vec2( e, 0.0), dd, ff);
    float yD = surfAt(p + vec2(0.0, -e), dd, ff);
    float yU = surfAt(p + vec2(0.0,  e), dd, ff);
    vNormal = normalize(vec3(yL - yR, 2.0 * e, yD - yU));
    vec3 wp = vec3(p.x, y, p.y);
    vWorld = wp; vDepth = depth; vFoam = foam;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(wp, 1.0);
  }
`;
// __WATER_FRAG__
const WATER_FRAG = /* glsl */ `
  uniform vec3 uSunDir, uShallow, uDeep, uSky;
  varying vec3 vWorld;
  varying vec3 vNormal;
  varying float vDepth;
  varying float vFoam;

  void main(){
    if (vDepth <= 0.03) discard;
    vec3 N = normalize(vNormal);
    vec3 V = normalize(cameraPosition - vWorld);
    float fres = pow(1.0 - max(dot(N, V), 0.0), 3.0);

    vec3 base = mix(uShallow, uDeep, clamp(vDepth / 12.0, 0.0, 1.0));
    vec3 col = mix(base, uSky, fres * 0.55);

    vec3 H = normalize(uSunDir + V);
    float spec = pow(max(dot(N, H), 0.0), 220.0);
    col += vec3(1.0, 0.97, 0.9) * spec * 1.3;

    float shore = 1.0 - smoothstep(0.0, 1.3, vDepth);
    float foam = max(shore * 0.55, vFoam);
    col = mix(col, vec3(0.92, 0.96, 1.0), foam * 0.5);

    float alpha = mix(0.55, 0.94, clamp(vDepth / 2.5, 0.0, 1.0));
    gl_FragColor = vec4(col, alpha);
  }
`;

interface DamBlock {
  mesh: THREE.Mesh;
  velocity: THREE.Vector3;
  angularVelocity: THREE.Vector3;
  broken: boolean;
  settled: boolean;      // true when block has stopped moving
  originalPosition: THREE.Vector3;
  mass: number;
  health: number;       // 0-1, when 0 the block breaks off
  distFromCenter: number; // distance from dam center (for staged breaking)
  heightRatio: number;   // normalized height position
  breakDelay: number;    // seconds after breach when this piece lets go (staggered fall)
}

type ZoneKind = 'town' | 'farm';

interface FloodZone {
  z: number; x: number; gy: number; radius: number;
  name: string; kind: ZoneKind; flooded: boolean;
  disc: THREE.Mesh; ring: THREE.Mesh; sprite: THREE.Sprite;
  canvas: HTMLCanvasElement; tex: THREE.CanvasTexture;
  bStart: number; bCount: number;   // instance range in the settlement InstancedMesh
}

export class App {
  private renderer!: THREE.WebGLRenderer;
  private scene!: THREE.Scene;
  private camera!: THREE.PerspectiveCamera;
  private controls!: OrbitControls;
  private clock = new THREE.Clock();

  // Dam
  private damGroup: THREE.Group | null = null;
  private damBlocks: DamBlock[] = [];
  private damBoundingBox = new THREE.Box3();

  // Water
  private waterMesh!: THREE.Mesh;
  private waterLevel = 0;
  private waterTarget = 0;
  private breakThreshold = 65; // % water level to trigger break
  private isBreaking = false;
  private breakProgress = 0;
  private waterParticles: { mesh: THREE.InstancedMesh; data: { pos: THREE.Vector3; vel: THREE.Vector3; life: number }[] } | null = null;

  // Terrain
  private terrainMesh!: THREE.Mesh;
  private terrainHeightCache = new Map<string, number>();
  private frameCount = 0;

  // UI
  private uiContainer!: HTMLElement;
  private waterSlider!: HTMLInputElement;
  private waterLevelDisplay!: HTMLElement;
  private simulateBtn!: HTMLButtonElement;
  private resetBtn!: HTMLButtonElement;
  private statusText!: HTMLElement;
  private damInfo: DamInfo | null = null;

  // Animation
  private animationId: number = 0;
  private isRunning = false;

  // Post-break water flood
  private floodParticles: { pos: THREE.Vector3; vel: THREE.Vector3; life: number }[] = [];
  private floodMesh: THREE.InstancedMesh | null = null;

  // Analytic terrain
  private tSeed = 0;
  private tHalf = 200;                 // half of the terrain extent (full = 400)
  private terrainHeightTex: THREE.DataTexture | null = null;

  // Earthen abutment shoulders sculpted into the terrain at the dam's flanks, so
  // the natural hillside — not a concrete wall — seals the reservoir at the dam
  // ends. Off until the dam metrics are known (see sculptAbutmentTerrain()).
  private sculptShoulders = false;
  private sCx = 0;         // dam centre X (world)
  private sCz = 0;         // dam plane Z (world)
  private sGapHalf = 0;    // terrain stays natural within this |x-cx| (dam body/channel)
  private sRamp = 10;      // width over which the shoulder climbs to the crest
  private sBandHalf = 12;  // |z-cz| the shoulder spans fully (≈ dam thickness)
  private sFade = 10;      // shoulder fades to nothing over this, beyond the band
  private sTop = 0;        // shoulder crest height (world Y)

  // Water shader
  private waterUniforms: Record<string, { value: any }> | null = null;
  private currentWaterY = -20;
  private floodZ = 0;                  // downstream flood-front position (world z)

  // Dam metrics (filled after model loads)
  private damCenter = new THREE.Vector3();
  private damHalfWidthX = 20;
  private damCrestY = 0;
  private damBaseY = 0;
  private damUpstreamZ = 0;
  private reservoirMinY = -20;
  private reservoirMaxY = 0;

  // Flood-affected-area markers
  private floodZoneGroup: THREE.Group | null = null;
  private floodZones: FloodZone[] = [];

  // Settlements (cities + farmland) laid out beside the dam, downstream.
  private settlementMesh: THREE.InstancedMesh | null = null;
  private settlementBaseColors: THREE.Color[] = [];

  // Abutments/wing-walls that seal the dam's ends into the valley walls.
  private abutmentGroup: THREE.Group | null = null;
  private damToeZ = 0;                  // downstream toe (world z)

  // Continuous tailrace outflow — a working dam always releasing some water.
  private outflowParticles: { pos: THREE.Vector3; vel: THREE.Vector3; life: number }[] = [];
  private outflowMesh: THREE.InstancedMesh | null = null;

  // Ambient valley houses (scenery beyond the flood-zone towns; no trees).
  private scatterMesh: THREE.InstancedMesh | null = null;
  private scatterBaseColors: THREE.Color[] = [];
  private scatterInfo: { z: number; gy: number }[] = [];
  private scatterFlooded: boolean[] = [];

  // Flat "town district" terraces sculpted into the meandering valley — one
  // level shelf on each bank for a tidy, colourful little town (the canyon is
  // too curved to lay a grid on otherwise). Empty until the pads are sited; a
  // town + safe-zone marker is built per pad, and the pads are mirrored across
  // the river so the downstream valley reads symmetric.
  private townPads: {
    cx: number;    // pad centre X (world)
    cz: number;    // pad centre Z (world)
    r: number;     // flat radius
    fade: number;  // width the terrace grades back into natural ground
    y: number;     // the single level height of the shelf (world Y)
    name: string;  // town name shown on its safe-zone placard
  }[] = [];

  // Colourful mini-towns on the pads (one group holds every town's plaza,
  // buildings and safe-zone marker), plus a visible sun.
  private townGroup: THREE.Group | null = null;
  private sunGroup: THREE.Group | null = null;

  // Underwater camera tint.
  private underwater = false;
  private underwaterTint: HTMLElement | null = null;
  private baseFog: THREE.FogExp2 | null = null;

  // GLB skeletal animation (spillway gates)
  private mixer: THREE.AnimationMixer | null = null;
  private gateActions: THREE.AnimationAction[] = [];

  // Marker picking + camera fly-to
  private raycaster = new THREE.Raycaster();
  private pointer = new THREE.Vector2();
  private pickTargets: THREE.Object3D[] = [];
  private focusedZone = -1;
  private damOverview = { pos: new THREE.Vector3(60, 50, 80), target: new THREE.Vector3(0, 10, 0) };
  private camTween: {
    t: number; dur: number;
    fromPos: THREE.Vector3; toPos: THREE.Vector3;
    fromTar: THREE.Vector3; toTar: THREE.Vector3;
  } | null = null;

  // Progressive breach: only a small, pre-selected cluster of crest pieces lets
  // go (natural crumble) — not the whole dam disintegrating.
  private breachPieces: DamBlock[] = [];

  async start(dam: DamInfo): Promise<void> {
    this.damInfo = dam;
    this.createRenderer();
    this.createScene();
    this.createCamera();
    this.generateTerrain(dam);
    await this.loadDamModel();
    this.createWater();
    this.createFloodSystem();
    this.createOutflowSystem();
    this.sculptAbutmentTerrain();
    this.createFloodZones();
    this.createSettlements();
    this.createScatterHouses();
    this.createTownDistrict();
    this.createUI(dam);
    this.setupPicking();
    this.setupResize();
    this.isRunning = true;
    this.animate();
  }

  private createRenderer(): void {
    const canvas = document.createElement('canvas');
    canvas.id = 'sim-canvas';
    document.body.appendChild(canvas);

    this.renderer = new THREE.WebGLRenderer({
      canvas,
      antialias: true,
      alpha: false,
      powerPreference: 'high-performance',
    });
    this.renderer.setSize(window.innerWidth, window.innerHeight);
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.renderer.shadowMap.enabled = true;
    this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = 1.2;
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
  }

  private createScene(): void {
    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color(0x1a2a3a);
    this.baseFog = new THREE.FogExp2(0x1a2a3a, 0.0016);
    this.scene.fog = this.baseFog;

    // Sky dome
    const skyGeo = new THREE.SphereGeometry(900, 32, 32);
    const skyMat = new THREE.ShaderMaterial({
      uniforms: {
        topColor: { value: new THREE.Color(0x2c5f8a) },
        bottomColor: { value: new THREE.Color(0x8ec3d8) },
        offset: { value: 10 },
        exponent: { value: 0.5 },
      },
      vertexShader: `
        varying vec3 vWorldPosition;
        void main() {
          vec4 worldPosition = modelMatrix * vec4(position, 1.0);
          vWorldPosition = worldPosition.xyz;
          gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
        }
      `,
      fragmentShader: `
        uniform vec3 topColor;
        uniform vec3 bottomColor;
        uniform float offset;
        uniform float exponent;
        varying vec3 vWorldPosition;
        void main() {
          float h = normalize(vWorldPosition + offset).y;
          gl_FragColor = vec4(mix(bottomColor, topColor, max(pow(max(h, 0.0), exponent), 0.0)), 1.0);
        }
      `,
      side: THREE.BackSide,
      depthWrite: false,
    });
    const sky = new THREE.Mesh(skyGeo, skyMat);
    this.scene.add(sky);

    // Lighting
    const sun = new THREE.DirectionalLight(0xfff5e6, 3.0);
    sun.position.set(80, 120, 60);
    sun.castShadow = true;
    sun.shadow.mapSize.width = 4096;
    sun.shadow.mapSize.height = 4096;
    sun.shadow.camera.near = 1;
    sun.shadow.camera.far = 700;
    sun.shadow.camera.left = -140;
    sun.shadow.camera.right = 140;
    sun.shadow.camera.top = 140;
    sun.shadow.camera.bottom = -140;
    sun.shadow.bias = -0.0002;
    this.scene.add(sun);
    sun.target.position.set(0, 0, 0);
    this.scene.add(sun.target);

    const ambient = new THREE.AmbientLight(0x4a6b80, 0.6);
    this.scene.add(ambient);

    const hemi = new THREE.HemisphereLight(0x87CEEB, 0x5b4332, 0.5);
    this.scene.add(hemi);

    // Rim light
    const rimLight = new THREE.DirectionalLight(0x4fc3f7, 0.8);
    rimLight.position.set(-60, 40, -40);
    this.scene.add(rimLight);

    // A real sun disc in the sky, aligned with the key light above.
    this.createSun(sun.position.clone());
  }

  // A visible sun: a bright core disc with a soft additive halo, parked far out
  // along the key light's direction (inside the sky dome) so it reads as the
  // actual source of the scene's light and shadows. fog is disabled on both so
  // the atmosphere doesn't wash the sun out at that distance.
  private createSun(lightPos: THREE.Vector3): void {
    const dir = lightPos.clone().normalize();
    const pos = dir.multiplyScalar(760);

    this.sunGroup = new THREE.Group();
    this.sunGroup.name = 'Sun';

    const core = new THREE.Mesh(
      new THREE.SphereGeometry(30, 32, 24),
      new THREE.MeshBasicMaterial({ color: 0xfff3cf, fog: false, toneMapped: false }),
    );
    core.position.copy(pos);
    this.sunGroup.add(core);

    // Radial-gradient halo texture (bright warm centre → transparent edge).
    const s = 128;
    const cv = document.createElement('canvas');
    cv.width = cv.height = s;
    const ctx = cv.getContext('2d')!;
    const g = ctx.createRadialGradient(s / 2, s / 2, 0, s / 2, s / 2, s / 2);
    g.addColorStop(0.0, 'rgba(255,247,214,1.0)');
    g.addColorStop(0.25, 'rgba(255,232,160,0.75)');
    g.addColorStop(0.55, 'rgba(255,206,120,0.25)');
    g.addColorStop(1.0, 'rgba(255,196,110,0.0)');
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, s, s);
    const halo = new THREE.CanvasTexture(cv);
    halo.colorSpace = THREE.SRGBColorSpace;

    const glow = new THREE.Sprite(new THREE.SpriteMaterial({
      map: halo, transparent: true, blending: THREE.AdditiveBlending,
      depthWrite: false, fog: false, toneMapped: false,
    }));
    glow.position.copy(pos);
    glow.scale.set(320, 320, 1);
    this.sunGroup.add(glow);

    this.scene.add(this.sunGroup);
  }

  private createCamera(): void {
    this.camera = new THREE.PerspectiveCamera(50, window.innerWidth / window.innerHeight, 0.5, 3000);
    this.camera.position.set(60, 50, 80);

    const canvas = this.renderer.domElement;
    this.controls = new OrbitControls(this.camera, canvas);
    this.controls.enableDamping = true;
    this.controls.dampingFactor = 0.08;
    this.controls.target.set(0, 10, 0);
    this.controls.minDistance = 12;
    this.controls.maxDistance = 500;
    this.controls.maxPolarAngle = Math.PI * 0.49;
    this.controls.update();
  }

  private generateTerrain(dam: DamInfo): void {
    // Seed terrain shape from the dam's coordinates so each site is distinct.
    this.tSeed = (dam.lat * 12.9898 + dam.lng * 78.233) % 6.2831853;

    const full = this.tHalf * 2;      // 400 units across
    const segments = 220;
    const geometry = new THREE.PlaneGeometry(full, full, segments, segments);
    geometry.rotateX(-Math.PI / 2);

    const material = new THREE.MeshStandardMaterial({
      vertexColors: true,
      roughness: 0.95,
      metalness: 0.02,
      flatShading: false,
    });

    this.terrainMesh = new THREE.Mesh(geometry, material);
    this.terrainMesh.receiveShadow = true;
    this.terrainMesh.name = 'Terrain';
    this.scene.add(this.terrainMesh);

    // Fill heights + vertex colours from the analytic field, then bake it into a
    // texture the water shader samples so the reservoir surface hugs the ground.
    this.fillTerrain(geometry);
    this.bakeHeightMap();
  }

  // Write per-vertex height + colour from terrainHeightAt() onto a terrain grid.
  // Split out so the abutment sculpt can re-run it after the dam metrics land.
  private fillTerrain(geometry: THREE.BufferGeometry): void {
    const positions = geometry.attributes.position as THREE.BufferAttribute;
    let colorAttr = geometry.attributes.color as THREE.BufferAttribute | undefined;
    if (!colorAttr) {
      colorAttr = new THREE.BufferAttribute(new Float32Array(positions.count * 3), 3);
      geometry.setAttribute('color', colorAttr);
    }
    const colors = colorAttr.array as Float32Array;
    const tmpN = new THREE.Vector3();

    for (let i = 0; i < positions.count; i++) {
      const x = positions.getX(i);
      const z = positions.getZ(i);
      const h = this.terrainHeightAt(x, z);
      positions.setY(i, h);

      // Local slope from finite differences (rock vs. vegetation).
      const e = 2.0;
      const hx = this.terrainHeightAt(x + e, z) - this.terrainHeightAt(x - e, z);
      const hz = this.terrainHeightAt(x, z + e) - this.terrainHeightAt(x, z - e);
      tmpN.set(-hx, 2 * e, -hz).normalize();
      const slope = 1 - tmpN.y;

      const jitter = (Math.sin((x * 12.9 + z * 4.1 + this.tSeed) * 43.75) % 1) * 0.06;
      let r: number, g: number, b: number;
      // Lush game-style valley: bright greens on the slopes, brown-orange
      // exposed soil along steep faces and the reservoir shoreline.
      if (h < -12)           { r = 0.15; g = 0.15; b = 0.14; }   // deep river bed
      else if (h < -2)       { r = 0.46; g = 0.33; b = 0.20; }   // shoreline soil
      else if (slope > 0.52) { r = 0.44; g = 0.31; b = 0.20; }   // exposed steep slope
      else if (h < 8)        { r = 0.33; g = 0.53; b = 0.24; }   // lush valley green
      else if (h < 24)       { r = 0.27; g = 0.47; b = 0.21; }   // hillside green
      else                   { r = 0.34; g = 0.44; b = 0.29; }   // high green-grey

      colors[i * 3]     = Math.max(0, r + jitter);
      colors[i * 3 + 1] = Math.max(0, g + jitter);
      colors[i * 3 + 2] = Math.max(0, b + jitter);
    }

    positions.needsUpdate = true;
    colorAttr.needsUpdate = true;
    geometry.computeVertexNormals();
  }

  // Re-run the terrain build after terrainHeightAt() has changed (abutment
  // shoulders), and refresh the height texture the water surface samples.
  private refreshTerrain(): void {
    if (!this.terrainMesh) return;
    this.fillTerrain(this.terrainMesh.geometry as THREE.BufferGeometry);
    this.bakeHeightMap();
  }

  private lerp(a: number, b: number, t: number): number { return a + (b - a) * t; }
  private smooth(t: number): number { t = Math.min(1, Math.max(0, t)); return t * t * (3 - 2 * t); }

  // Analytic terrain height — a meandering canyon that pinches to a gorge at the
  // dam (z≈0), holds a deep reservoir basin upstream (z<0) and opens to a
  // descending valley downstream (z>0).
  private terrainHeightAt(x: number, z: number): number {
    const s = this.tSeed;

    // Meandering channel centreline.
    const cx = Math.sin(z * 0.012 + s) * 16 + Math.sin(z * 0.045 + s * 1.7) * 5;
    const d = Math.abs(x - cx);

    // Canyon half-width: tight gorge at the dam, wider up/downstream.
    const halfW = 26 + Math.max(0, -z) * 0.16 + Math.max(0, z) * 0.11;

    // Longitudinal channel-floor profile.
    let floor: number;
    if (z <= 0) {
      floor = this.lerp(-8, -26, this.smooth(-z / 55));   // toe → deep basin
    } else {
      floor = -8 - z * 0.05;                              // descends downstream
    }

    // Cross-section: U-shaped bed inside halfW, climbing walls beyond it.
    let h: number;
    if (d < halfW) {
      const t = d / halfW;
      h = floor + t * t * 6;
    } else {
      const wd = d - halfW;
      h = floor + 6 + wd * 0.55 + wd * wd * 0.012;
    }

    // Rolling detail, damped inside the channel so the bed stays clean.
    const wall = Math.min(1, d / (halfW + 1));
    const detail =
      Math.sin(x * 0.03 + s) * Math.cos(z * 0.025 + s * 0.6) * 5 +
      Math.sin(x * 0.09 + s * 2.1) * Math.sin(z * 0.075 + s * 1.3) * 2.2 +
      Math.sin(x * 0.21 + z * 0.17 + s) * 0.9;
    h += detail * (0.35 + 0.65 * wall);
    h = Math.min(h, 75);

    // Earthen abutments: near the dam plane, raise the flanks (beyond the dam
    // body) up to the crest so the hillside embeds the dam ends and the pool
    // can't slip around them. Tapered along the river so the rest of the valley
    // is untouched and the channel/spillway gap stays open.
    if (this.sculptShoulders) {
      const along = 1 - this.smooth((Math.abs(z - this.sCz) - this.sBandHalf) / this.sFade);
      if (along > 0.001) {
        const across = this.smooth((Math.abs(x - this.sCx) - this.sGapHalf) / this.sRamp);
        const k = across * along;
        if (k > 0.001) h = this.lerp(h, Math.max(h, this.sTop), k);
      }
    }

    // Flat town terraces: inside each disc, pull the surface to that pad's
    // level, grading back into the natural ground over its fade width so a
    // curved-valley bank becomes a buildable shelf. One pad per bank gives the
    // downstream valley a symmetric pair of towns. (Empty ⇒ natural ground.)
    for (const p of this.townPads) {
      const dd = Math.hypot(x - p.cx, z - p.cz);
      const t = 1 - this.smooth((dd - p.r) / p.fade);
      if (t > 0.001) h = this.lerp(h, p.y, t);
    }

    return h;
  }
  // __HEIGHTMAP_AND_GET__
  private bakeHeightMap(): void {
    const N = 256;
    // Reuse the same texture object across re-bakes so the water shader's
    // uHeightMap uniform (bound once in createWater) keeps pointing at live data.
    if (!this.terrainHeightTex) {
      const tex = new THREE.DataTexture(
        new Float32Array(N * N * 4), N, N, THREE.RGBAFormat, THREE.FloatType);
      tex.minFilter = THREE.LinearFilter;
      tex.magFilter = THREE.LinearFilter;
      tex.wrapS = THREE.ClampToEdgeWrapping;
      tex.wrapT = THREE.ClampToEdgeWrapping;
      this.terrainHeightTex = tex;
    }
    const data = this.terrainHeightTex.image.data as Float32Array;
    const half = this.tHalf;
    for (let j = 0; j < N; j++) {
      for (let i = 0; i < N; i++) {
        const x = -half + (i / (N - 1)) * 2 * half;
        const z = -half + (j / (N - 1)) * 2 * half;
        const idx = (j * N + i) * 4;
        data[idx] = this.terrainHeightAt(x, z);
        data[idx + 3] = 1;
      }
    }
    this.terrainHeightTex.needsUpdate = true;
  }

  private getTerrainHeight(x: number, z: number): number {
    return this.terrainHeightAt(x, z);
  }

  private async loadDamModel(): Promise<void> {
    const loader = new GLTFLoader();
    
    return new Promise((resolve, reject) => {
      loader.load(
        '/wowdam.glb',
        (gltf) => {
          this.damGroup = gltf.scene;

          // Recolour shared materials to real concrete/steel and drop the GLB's
          // own baked terrain/water so they don't fight our scene.
          this.prepareDamMaterials(this.damGroup);

          const size = new THREE.Vector3();
          const center = new THREE.Vector3();

          // Orient the dam so its long axis spans the river channel (world X).
          this.damBoundingBox.setFromObject(this.damGroup);
          this.damBoundingBox.getSize(size);
          if (size.z > size.x) this.damGroup.rotateY(Math.PI / 2);

          // Turn the dam around so its retaining face points at the reservoir
          // (upstream, −z) instead of downstream — "the water is on the other
          // side". 180° about the vertical (Blender-Z / three-Y) axis.
          this.damGroup.rotateY(Math.PI);

          // Scale so the dam spans the gorge (bigger than before → fills view).
          this.damBoundingBox.setFromObject(this.damGroup);
          this.damBoundingBox.getSize(size);
          const targetWidth = 60;
          const scaleFactor = targetWidth / Math.max(size.x, size.z, 1);
          this.damGroup.scale.setScalar(scaleFactor);
          // __DAM_SEAT__
          this.damBoundingBox.setFromObject(this.damGroup);
          this.damBoundingBox.getSize(size);
          this.damBoundingBox.getCenter(center);

          // Seat the dam over the gorge (centred on origin, base on the bed).
          const terrainY = this.getTerrainHeight(0, 0);
          this.damGroup.position.set(
            this.damGroup.position.x - center.x,
            terrainY - this.damBoundingBox.min.y + 0.1,
            this.damGroup.position.z - center.z
          );

          this.damBoundingBox.setFromObject(this.damGroup);
          this.damBoundingBox.getSize(size);
          this.damBoundingBox.getCenter(center);

          // Cache dam metrics used by the water + break systems.
          this.damCenter.copy(center);
          this.damHalfWidthX = size.x / 2;
          this.damCrestY = this.damBoundingBox.max.y;
          this.damBaseY = this.damBoundingBox.min.y;
          this.damUpstreamZ = this.damBoundingBox.min.z + 0.5;
          this.reservoirMinY = this.damBaseY - 2;
          this.reservoirMaxY = this.damCrestY - 1;
          this.floodZ = this.damUpstreamZ;
          this.damToeZ = this.damBoundingBox.max.z;

          this.scene.add(this.damGroup);
          this.extractDamBlocks();
          this.setupDamAnimations(gltf.animations);
          this.frameCameraOnDam(size, center);

          console.log(`[Dam] Loaded wowdam.glb: ${this.damBlocks.length} blocks`);
          resolve();

        },
        (progress) => {
          const pct = progress.total > 0 ? (progress.loaded / progress.total * 100).toFixed(0) : '?';
          console.log(`[Dam] Loading: ${pct}%`);
        },
        (error) => {
          console.error('[Dam] Failed to load wowdam.glb:', error);
          // Create fallback dam
          this.createFallbackDam();
          resolve();
        }
      );
    });
  }

  private prepareDamMaterials(group: THREE.Object3D): void {
    const seen = new Set<THREE.Material>();
    group.traverse((child) => {
      if (!(child instanceof THREE.Mesh)) return;
      // Drop the Blender fluid-sim helper geometry baked into the GLB: the
      // Mantaflow domain box, the inflow-source box and the effector snapshots.
      // They carry no PBR material (so the material-name test below misses them)
      // and otherwise render as stray grey boxes beside the dam.
      if (/domain|effector|inflow|mantaflow|^cube(\.|_|$)/i.test(child.name)) {
        child.visible = false;
        return;
      }
      const mats = Array.isArray(child.material) ? child.material : [child.material];
      for (const m of mats) {
        if (!m) continue;
        const name = (m.name || '').toLowerCase();
        // Hide the model's own baked terrain and fluid — we supply our own.
        if (/terrain|soil|grass|water|mantaflow/.test(name)) { child.visible = false; continue; }
        if (seen.has(m) || !(m instanceof THREE.MeshStandardMaterial)) continue;
        seen.add(m);
        if (/joint/.test(name))             { m.color.setHex(0x6f6c66); m.roughness = 0.90; m.metalness = 0.0; }
        else if (/weather/.test(name))      { m.color.setHex(0x8f8b80); m.roughness = 0.95; m.metalness = 0.0; }
        else if (/concrete/.test(name))     { m.color.setHex(0xbdb9ae); m.roughness = 0.82; m.metalness = 0.0; }
        else if (/gate|steel/.test(name))   { m.color.setHex(0x6b7078); m.roughness = 0.45; m.metalness = 0.85; }
        else if (/metal|machin/.test(name)) { m.color.setHex(0x8a8f96); m.roughness = 0.40; m.metalness = 0.90; }
        else                                { m.color.setHex(0xb0ada4); m.roughness = 0.85; m.metalness = 0.05; }
        m.needsUpdate = true;
      }
    });
  }

  private setupDamAnimations(clips: THREE.AnimationClip[]): void {
    this.mixer = null;
    this.gateActions = [];
    if (!this.damGroup || !clips || clips.length === 0) return;

    this.mixer = new THREE.AnimationMixer(this.damGroup);
    for (const clip of clips) {
      // The spillway-gate clips are the only visible ones — the Water_Effector
      // clips drive hidden Mantaflow domain meshes. Play the gates on breach.
      if (!/gate/i.test(clip.name)) continue;
      const action = this.mixer.clipAction(clip);
      action.loop = THREE.LoopOnce;
      action.clampWhenFinished = true;   // gates stay open once lifted
      action.enabled = true;
      this.gateActions.push(action);
    }
  }

  private openSpillwayGates(): void {
    if (!this.mixer) return;
    for (const action of this.gateActions) {
      action.reset();
      action.timeScale = 0.6;   // slow, mechanical lift
      action.play();
    }
  }

  private frameCameraOnDam(size: THREE.Vector3, center: THREE.Vector3): void {
    const maxDim = Math.max(size.x, size.y, size.z);
    this.camera.position.set(
      center.x + maxDim * 0.85,
      center.y + maxDim * 0.55,
      center.z + maxDim * 1.15,
    );
    this.controls.target.set(center.x, center.y - size.y * 0.1, center.z);
    this.controls.minDistance = maxDim * 0.4;
    this.controls.maxDistance = maxDim * 5;
    this.controls.update();
    // Remember this framing so a "Dam overview" button can fly back to it.
    this.damOverview.pos.copy(this.camera.position);
    this.damOverview.target.copy(this.controls.target);
  }

  private extractDamBlocks(): void {
    if (!this.damGroup) return;
    
    const center = new THREE.Vector3();
    this.damBoundingBox.getCenter(center);
    const size = new THREE.Vector3();
    this.damBoundingBox.getSize(size);

    this.damGroup.traverse((child) => {
      if (child instanceof THREE.Mesh && child.geometry) {
        // Skip the hidden baked terrain/water meshes — they aren't breakable.
        if (!child.visible) return;

        // Enable shadows
        child.castShadow = true;
        child.receiveShadow = true;

        // Get world position
        const worldPos = new THREE.Vector3();
        child.getWorldPosition(worldPos);

        // Calculate distance from center and height ratio
        const dx = worldPos.x - center.x;
        const dz = worldPos.z - center.z;
        const distFromCenter = Math.sqrt(dx * dx + dz * dz);
        const heightRatio = size.y > 0 ? (worldPos.y - this.damBoundingBox.min.y) / size.y : 0.5;

        this.damBlocks.push({
          mesh: child,
          velocity: new THREE.Vector3(),
          angularVelocity: new THREE.Vector3(
            (Math.random() - 0.5) * 2,
            (Math.random() - 0.5) * 2,
            (Math.random() - 0.5) * 2
          ),
          broken: false,
          settled: false,
          originalPosition: worldPos.clone(),
          mass: 1 + Math.random() * 2,
          health: 1.0,
          distFromCenter,
          heightRatio,
          breakDelay: 0,
        });
      }
    });

    // Sort by distance from center so center blocks break first
    this.damBlocks.sort((a, b) => a.distFromCenter - b.distFromCenter);
  }

  private createFallbackDam(): void {
    // Fallback: create a simple block dam if GLB fails
    this.damGroup = new THREE.Group();
    const concreteMat = new THREE.MeshStandardMaterial({
      color: 0xa8a8a2,
      roughness: 0.88,
      metalness: 0.0,
    });

    const blocksX = 12;
    const blocksY = 8;
    const blocksZ = 3;
    const blockSize = 2.5;

    for (let x = 0; x < blocksX; x++) {
      for (let y = 0; y < blocksY; y++) {
        for (let z = 0; z < blocksZ; z++) {
          const geo = new THREE.BoxGeometry(
            blockSize * (0.8 + Math.random() * 0.4),
            blockSize * (0.8 + Math.random() * 0.4),
            blockSize * (0.8 + Math.random() * 0.4)
          );
          const mesh = new THREE.Mesh(geo, concreteMat.clone());
          const px = (x - blocksX / 2) * blockSize;
          const py = y * blockSize;
          const pz = (z - blocksZ / 2) * blockSize;
          mesh.position.set(px, py, pz);
          mesh.castShadow = true;
          mesh.receiveShadow = true;
          this.damGroup.add(mesh);
        }
      }
    }

    const terrainY = this.getTerrainHeight(0, 0);
    this.damGroup.position.y = terrainY;
    this.scene.add(this.damGroup);
    this.damBoundingBox.setFromObject(this.damGroup);
    const size = new THREE.Vector3();
    const center = new THREE.Vector3();
    this.damBoundingBox.getSize(size);
    this.damBoundingBox.getCenter(center);
    this.damCenter.copy(center);
    this.damHalfWidthX = size.x / 2;
    this.damCrestY = this.damBoundingBox.max.y;
    this.damBaseY = this.damBoundingBox.min.y;
    this.damUpstreamZ = this.damBoundingBox.min.z + 0.5;
    this.reservoirMinY = this.damBaseY - 2;
    this.reservoirMaxY = this.damCrestY - 1;
    this.floodZ = this.damUpstreamZ;
    this.damToeZ = this.damBoundingBox.max.z;
    this.extractDamBlocks();
    this.frameCameraOnDam(size, center);
  }

  private createWater(): void {
    const full = this.tHalf * 2;
    const geo = new THREE.PlaneGeometry(full, full, 240, 240);
    geo.rotateX(-Math.PI / 2);

    const sun = new THREE.Vector3(80, 120, 60).normalize();
    this.waterUniforms = {
      uTime:      { value: 0 },
      uWaterY:    { value: this.reservoirMinY },
      uFloodZ:    { value: this.damUpstreamZ },
      uDamZ:      { value: this.damUpstreamZ },
      uHalf:      { value: this.tHalf },
      uHeightMap: { value: this.terrainHeightTex },
      uSeed:      { value: this.tSeed },
      uToeZ:      { value: this.damToeZ },
      uDamX:      { value: this.damCenter.x },
      uBaseFlow:  { value: 1.1 },
      uSunDir:    { value: sun },
      uShallow:   { value: new THREE.Color(0x3f93a3) },
      uDeep:      { value: new THREE.Color(0x0c2b40) },
      uSky:       { value: new THREE.Color(0x8ec3d8) },
    };

    const mat = new THREE.ShaderMaterial({
      uniforms: this.waterUniforms,
      vertexShader: WATER_VERT,
      fragmentShader: WATER_FRAG,
      transparent: true,
      side: THREE.DoubleSide,
    });

    this.waterMesh = new THREE.Mesh(geo, mat);
    this.waterMesh.name = 'Water';
    this.waterMesh.frustumCulled = false;
    this.scene.add(this.waterMesh);
  }

  private createFloodSystem(): void {
    // Instanced foam/spray droplets — white churning water, not glassy beads.
    const sphereGeo = new THREE.SphereGeometry(0.5, 6, 5);
    const foamMat = new THREE.MeshStandardMaterial({
      color: 0xeaf1f5,
      roughness: 0.7,
      metalness: 0.0,
      transparent: true,
      opacity: 0.9,
    });

    const maxParticles = 2000;
    this.floodMesh = new THREE.InstancedMesh(sphereGeo, foamMat, maxParticles);
    this.floodMesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
    this.floodMesh.count = 0;
    this.floodMesh.frustumCulled = false;
    this.floodMesh.name = 'FloodParticles';
    this.scene.add(this.floodMesh);
  }

  private createFloodZones(): void {
    this.floodZoneGroup = new THREE.Group();
    this.floodZoneGroup.name = 'FloodZones';
    const defs: { name: string; kind: ZoneKind }[] = [
      { name: 'New Tehri', kind: 'town' },
      { name: 'Doiwala Farms', kind: 'farm' },
      { name: 'Bhagirathipuram', kind: 'town' },
      { name: 'Koteshwar', kind: 'town' },
      { name: 'Shivpuri', kind: 'town' },
    ];
    const count = defs.length;
    const rand = (a: number, b: number) => a + Math.random() * (b - a);
    const chanAt = (zz: number) =>
      Math.sin(zz * 0.012 + this.tSeed) * 16 + Math.sin(zz * 0.045 + this.tSeed * 1.7) * 5;
    const placed: { x: number; z: number; r: number }[] = [];

    for (let i = 0; i < count; i++) {
      const def = defs[i];
      const radius = def.kind === 'farm' ? rand(16, 22) : rand(10, 16);
      // Keep the settlement off the river's flowing path. Normal (un-breached)
      // flow spans ≈±17 of the channel centre, so push the disc onto one bank
      // clear of the water; alternate banks where the channel runs near the axis.
      const riverHalf = 17;
      const off = riverHalf + radius + rand(6, 11);
      const z0 = 34 + (i / (count - 1)) * (this.tHalf - 70) + rand(-8, 8);
      let side0 = chanAt(z0) >= 0 ? 1 : -1;
      if (Math.abs(chanAt(z0)) < 4) side0 = (i % 2 === 0) ? 1 : -1;
      const banked = (zz: number, sd: number) =>
        THREE.MathUtils.clamp(chanAt(zz) + sd * off, -(this.tHalf - 40), this.tHalf - 40);
      // A spot is valid when it clears every colourful town terrace (one per
      // bank) and every settlement already placed. Try the preferred bank first,
      // then widen the search along the valley (both banks) until one clears —
      // so two mirrored towns can't crowd the downstream settlements off the map.
      const clearOf = (xx: number, zz: number) => {
        for (const p of this.townPads)
          if (Math.hypot(xx - p.cx, zz - p.cz) < radius + p.r + 8) return false;
        for (const q of placed)
          if (Math.hypot(xx - q.x, zz - q.z) < radius + q.r + 6) return false;
        return true;
      };
      let z = z0, x = banked(z0, side0);
      if (!clearOf(x, z)) {
        search:
        for (let dz = 0; dz <= 96; dz += 6) {
          for (const zz of dz === 0 ? [z0] : [z0 + dz, z0 - dz]) {
            const zc = THREE.MathUtils.clamp(zz, this.damToeZ + 12, this.tHalf - 45);
            for (const sd of [side0, -side0]) {
              const xc = banked(zc, sd);
              if (clearOf(xc, zc)) { x = xc; z = zc; break search; }
            }
          }
        }
      }
      placed.push({ x, z, r: radius });
      const gy = this.getTerrainHeight(x, z);

      const zone = new THREE.Group();
      zone.position.set(x, 0, z);

      const discMat = new THREE.MeshBasicMaterial({ color: 0xe0a955, transparent: true, opacity: 0.16, side: THREE.DoubleSide, depthWrite: false });
      const disc = new THREE.Mesh(new THREE.CircleGeometry(radius, 40), discMat);
      disc.rotation.x = -Math.PI / 2; disc.position.y = gy + 0.25;

      const ringMat = new THREE.MeshBasicMaterial({ color: 0xe0a955, transparent: true, opacity: 0.7, side: THREE.DoubleSide, depthWrite: false });
      const ring = new THREE.Mesh(new THREE.RingGeometry(radius - 0.5, radius, 48), ringMat);
      ring.rotation.x = -Math.PI / 2; ring.position.y = gy + 0.3;

      const pole = new THREE.Mesh(new THREE.CylinderGeometry(0.18, 0.18, 7, 6), new THREE.MeshBasicMaterial({ color: 0xe0a955 }));
      pole.position.set(0, gy + 3.5, 0);

      const canvas = document.createElement('canvas');
      const tex = new THREE.CanvasTexture(canvas);
      tex.colorSpace = THREE.SRGBColorSpace;
      this.drawZoneLabel(canvas, tex, def.name, false);
      const sprite = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, transparent: true, depthTest: true }));
      sprite.scale.set(24, 11, 1); sprite.position.set(0, gy + 9.5, 0);

      // Tag the marker parts so the raycaster can map a click back to this zone.
      disc.userData.zoneIndex = i;
      ring.userData.zoneIndex = i;
      pole.userData.zoneIndex = i;
      sprite.userData.zoneIndex = i;
      this.pickTargets.push(disc, ring, pole, sprite);

      zone.add(disc, ring, pole, sprite);
      this.floodZoneGroup.add(zone);
      this.floodZones.push({
        z, x, gy, radius, name: def.name, kind: def.kind, flooded: false,
        disc, ring, sprite, canvas, tex, bStart: 0, bCount: 0,
      });
    }
    this.scene.add(this.floodZoneGroup);
  }

  // Lay out small towns and farmland downstream of the dam: cuboid buildings of
  // varied size with street gaps between them, sized in realistic proportion to
  // the dam (a few metres tall against a ~150 m dam). One InstancedMesh holds
  // every structure so hundreds of buildings cost a single draw call.
  private createSettlements(): void {
    const damH = Math.max(6, this.damCrestY - this.damBaseY);
    const storey = damH / 18;                    // ≈ one 4 m floor in scene units
    const dummy = new THREE.Object3D();
    const mats: THREE.Matrix4[] = [];
    const cols: THREE.Color[] = [];

    const rand = (a: number, b: number) => a + Math.random() * (b - a);
    const wallTones = [0xcfc7ba, 0xbfae97, 0xc9b7a0, 0xa7b0b5, 0xd8cdbb, 0xb59d86];
    const roofTones = [0x8a4b3a, 0x7d5b45, 0x556169, 0x8f8578];
    const fieldTones = [0x6f8f3f, 0x88a24d, 0x9c8a4a, 0xb0a25c, 0x5e7b39, 0xa98f52];

    const place = (wx: number, wz: number, fx: number, fy: number, fz: number, color: number) => {
      const gy = this.getTerrainHeight(wx, wz);
      dummy.position.set(wx, gy + fy / 2, wz);
      dummy.rotation.set(0, rand(-0.35, 0.35), 0);
      dummy.scale.set(fx, fy, fz);
      dummy.updateMatrix();
      mats.push(dummy.matrix.clone());
      cols.push(new THREE.Color(color));
    };

    for (const zone of this.floodZones) {
      zone.bStart = mats.length;
      const R = zone.radius;

      if (zone.kind === 'farm') {
        // Patchwork fields (flat plots) with dirt-road gaps, plus a few farmhouses.
        const cell = storey * 4.2;
        const n = Math.floor((R * 2) / cell);
        for (let ix = -n; ix <= n; ix++) {
          for (let iz = -n; iz <= n; iz++) {
            const lx = ix * cell + rand(-0.3, 0.3);
            const lz = iz * cell + rand(-0.3, 0.3);
            if (Math.hypot(lx, lz) > R) continue;
            const plot = cell * rand(0.72, 0.86);          // gap = dirt track
            place(zone.x + lx, zone.z + lz, plot, storey * 0.12, plot,
                  fieldTones[(Math.random() * fieldTones.length) | 0]);
            if (Math.random() < 0.08) {                     // occasional farmhouse
              place(zone.x + lx + rand(-cell * 0.2, cell * 0.2),
                    zone.z + lz + rand(-cell * 0.2, cell * 0.2),
                    storey * 1.4, storey * rand(1.0, 1.6), storey * 1.6,
                    wallTones[(Math.random() * wallTones.length) | 0]);
            }
          }
        }
      } else {
        // Town: a grid of lots; a building fills most of each lot, the rest is
        // street. Denser and taller toward the centre.
        const cell = storey * 3.2;
        const n = Math.ceil(R / cell) + 1;
        for (let ix = -n; ix <= n; ix++) {
          for (let iz = -n; iz <= n; iz++) {
            const lx = ix * cell;
            const lz = iz * cell;
            const d = Math.hypot(lx, lz);
            if (d > R * 0.98) continue;
            const centrality = 1 - d / R;                   // 0 edge → 1 centre
            if (Math.random() > 0.55 + centrality * 0.4) continue;  // plazas / empty lots
            const foot = cell * rand(0.5, 0.72);            // footprint < lot ⇒ street gap
            const floors = 1 + Math.floor(centrality * rand(1.5, 5) + Math.random() * 1.5);
            const bh = storey * floors;
            const bx = zone.x + lx + rand(-0.25, 0.25) * cell;
            const bz = zone.z + lz + rand(-0.25, 0.25) * cell;
            place(bx, bz, foot * rand(0.85, 1.0), bh, foot * rand(0.85, 1.0),
                  wallTones[(Math.random() * wallTones.length) | 0]);
            if (Math.random() < 0.5) {                       // flat roof cap / parapet
              place(bx, bz, foot * 0.6, storey * 0.18, foot * 0.6,
                    roofTones[(Math.random() * roofTones.length) | 0]);
            }
          }
        }
      }
      zone.bCount = mats.length - zone.bStart;
    }

    if (mats.length === 0) return;

    const geo = new THREE.BoxGeometry(1, 1, 1);
    const mat = new THREE.MeshStandardMaterial({ roughness: 0.9, metalness: 0.0 });
    const mesh = new THREE.InstancedMesh(geo, mat, mats.length);
    mesh.name = 'Settlements';
    mesh.castShadow = true;
    mesh.receiveShadow = true;
    for (let i = 0; i < mats.length; i++) {
      mesh.setMatrixAt(i, mats[i]);
      mesh.setColorAt(i, cols[i]);
    }
    mesh.instanceMatrix.needsUpdate = true;
    if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
    this.settlementMesh = mesh;
    this.settlementBaseColors = cols;
    this.scene.add(mesh);
  }

  // Seal each end of the dam into the valley with the terrain itself: instead of
  // a concrete wing-wall, we raise earthen shoulders in the heightfield at the
  // dam's flanks up to the crest, so the natural hillside embeds the dam ends.
  // The GLB dam doesn't reach the banks, so without this the reservoir reads as
  // spilling around its sides.
  private sculptAbutmentTerrain(): void {
    // Drop any old concrete abutment (e.g. from a previous build).
    if (this.abutmentGroup) { this.abutmentGroup.removeFromParent(); this.abutmentGroup = null; }

    this.sCx = this.damCenter.x;
    this.sCz = this.damCenter.z;
    // Keep terrain natural across the dam body/channel; start climbing a touch
    // inside the ends so the earth tucks behind them, and reach full crest by
    // the dam ends (±damHalfWidthX).
    this.sGapHalf = Math.max(6, this.damHalfWidthX - 10);
    this.sRamp = 10;
    // Span the dam's thickness fully, then fade out — but keep the whole reach
    // clear of the downstream settlements (nearest at z ≈ 34).
    const zHalf = (this.damBoundingBox.max.z - this.damBoundingBox.min.z) / 2;
    this.sBandHalf = Math.min(zHalf + 2, 22);
    this.sFade = 10;
    this.sTop = this.damCrestY + 2;   // seal a touch above the crest
    this.sculptShoulders = true;

    // Site a flat town terrace on each downstream bank, clear of the river's
    // normal ±17 flow and the dam footprint, so a symmetric pair of colourful
    // towns can share one level shelf per side.
    const tSeed = this.tSeed;
    this.townPads = [];                               // empty while we sample ground
    const pz = this.damToeZ + 48;
    const chan = Math.sin(pz * 0.012 + tSeed) * 16
               + Math.sin(pz * 0.045 + tSeed * 1.7) * 5;
    const padR = 26, padFade = 14;
    const off = 17 + padR + 10;                       // push each shelf off the water
    // One shelf per bank, mirrored about the channel centre so the two towns sit
    // symmetric across the river. Take each shelf's level from the natural
    // ground (averaged around its centre) BEFORE any pad flattens the field, so
    // it sits at a believable bank height (townPads is empty during sampling).
    const sitePad = (side: 1 | -1, name: string) => {
      const cx = THREE.MathUtils.clamp(chan + side * off, -(this.tHalf - 50), this.tHalf - 50);
      let sum = this.terrainHeightAt(cx, pz);
      let cnt = 1;
      for (const [dx, dz] of [[0.6, 0], [-0.6, 0], [0, 0.6], [0, -0.6]] as const) {
        sum += this.terrainHeightAt(cx + dx * padR, pz + dz * padR);
        cnt++;
      }
      return { cx, cz: pz, r: padR, fade: padFade, y: Math.max(1.5, sum / cnt), name };
    };
    const right = sitePad(1, 'Rishikesh');
    const left = sitePad(-1, 'Devprayag');
    this.townPads.push(right, left);

    // Rebuild the terrain mesh + height texture with the shoulders + pads in place.
    this.refreshTerrain();
  }
  // Build the colourful mini-towns: one warm ground plaza + rotated grid of
  // brightly painted buildings (varied heights, street gaps, a central landmark)
  // + a named green "safe zone" marker per flat terrace, mirrored across the
  // river. Pure scenery for appeal — each sits on an elevated shelf clear of the
  // normal river, so it isn't wired into the flood system.
  private createTownDistrict(): void {
    if (!this.townPads.length) return;
    if (this.townGroup) { this.townGroup.removeFromParent(); this.townGroup = null; }
    this.townGroup = new THREE.Group();
    this.townGroup.name = 'TownDistricts';
    this.scene.add(this.townGroup);
    for (const pad of this.townPads) this.buildTownOnPad(pad);
  }

  // One colourful town + safe-zone marker on a single flat terrace.
  private buildTownOnPad(pad: {
    cx: number; cz: number; r: number; fade: number; y: number; name: string;
  }): void {
    const group = this.townGroup!;
    const damH = Math.max(6, this.damCrestY - this.damBaseY);
    const storey = damH / 18;
    const cx = pad.cx, cz = pad.cz, gy = pad.y;
    const rand = (a: number, b: number) => a + Math.random() * (b - a);

    // Ground plaza — a warm paved shelf the streets read against.
    const plazaR = pad.r * 0.9;
    const plaza = new THREE.Mesh(
      new THREE.CircleGeometry(plazaR, 48),
      new THREE.MeshStandardMaterial({ color: 0xcdbd9a, roughness: 0.96, metalness: 0 }),
    );
    plaza.rotation.x = -Math.PI / 2;
    plaza.position.set(cx, gy + 0.06, cz);
    plaza.receiveShadow = true;
    group.add(plaza);

    // Bright, saturated wall palette + contrasting roof caps.
    const wallTones = [
      0xe74c3c, 0xff7043, 0xf39c12, 0xf1c40f, 0x7cb342, 0x2ecc71,
      0x1abc9c, 0x29b6f6, 0x3498db, 0x5c6bc0, 0x9b59b6, 0xec407a,
      0xff8a65, 0x26c6da, 0x66bb6a, 0xffca28,
    ];
    const roofTones = [0x37474f, 0x8d3b2e, 0x4e342e, 0x263238, 0x5d4037, 0x455a64];

    const dummy = new THREE.Object3D();
    const mats: THREE.Matrix4[] = [];
    const cols: THREE.Color[] = [];
    const place = (wx: number, wz: number, w: number, h: number, d: number,
                   rot: number, color: number) => {
      dummy.position.set(wx, gy + h / 2, wz);
      dummy.rotation.set(0, rot, 0);
      dummy.scale.set(w, h, d);
      dummy.updateMatrix();
      mats.push(dummy.matrix.clone());
      cols.push(new THREE.Color(color));
    };
    // __TOWN_LAYOUT__
    // Grid of lots inside the plaza; footprint < lot so the plaza shows through
    // as streets. The grid is rotated so the town has a deliberate orientation,
    // and buildings grow taller toward the centre.
    const buildR = plazaR - storey * 1.5;
    const cell = storey * 3.0;
    const rot = rand(-0.5, 0.5);
    const ca = Math.cos(rot), sa = Math.sin(rot);
    const n = Math.ceil(buildR / cell) + 1;
    for (let ix = -n; ix <= n; ix++) {
      for (let iz = -n; iz <= n; iz++) {
        const gxl = ix * cell, gzl = iz * cell;
        const dd = Math.hypot(gxl, gzl);
        if (dd > buildR) continue;
        if (Math.random() < 0.14) continue;                // empty lot / square
        const lx = gxl * ca - gzl * sa;                    // rotate grid → world
        const lz = gxl * sa + gzl * ca;
        const centrality = 1 - dd / buildR;                // 0 edge → 1 centre
        const floors = 1 + Math.floor(centrality * rand(2, 6) + Math.random() * 1.5);
        const bh = storey * floors;
        const foot = cell * rand(0.5, 0.72);
        const wx = cx + lx + rand(-0.18, 0.18) * cell;
        const wz = cz + lz + rand(-0.18, 0.18) * cell;
        place(wx, wz, foot * rand(0.85, 1.0), bh, foot * rand(0.85, 1.0), rot,
              wallTones[(Math.random() * wallTones.length) | 0]);
        place(wx, wz, foot * 0.66, storey * 0.22, foot * 0.66, rot,
              roofTones[(Math.random() * roofTones.length) | 0]);
      }
    }

    // A central landmark tower so the little skyline has a focal point.
    place(cx, cz, storey * 1.6, storey * rand(8, 11), storey * 1.6, rot,
          wallTones[(Math.random() * wallTones.length) | 0]);
    place(cx, cz, storey * 1.1, storey * 1.4, storey * 1.1, rot, 0xffca28);

    if (mats.length === 0) return;
    const mesh = new THREE.InstancedMesh(
      new THREE.BoxGeometry(1, 1, 1),
      new THREE.MeshStandardMaterial({ roughness: 0.7, metalness: 0.0 }),
      mats.length,
    );
    mesh.name = 'TownBuildings';
    mesh.castShadow = true;
    mesh.receiveShadow = true;
    for (let i = 0; i < mats.length; i++) {
      mesh.setMatrixAt(i, mats[i]);
      mesh.setColorAt(i, cols[i]);
    }
    mesh.instanceMatrix.needsUpdate = true;
    if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
    group.add(mesh);

    // Named, green "safe zone" marker: the town sits on high ground and stays
    // dry when the dam lets go, unlike the downstream flood-zone settlements.
    // Purely informational — not wired into the click-to-inspect flood markers.
    const gcol = 0x3ddc84;
    const disc = new THREE.Mesh(
      new THREE.CircleGeometry(plazaR + 1, 44),
      new THREE.MeshBasicMaterial({ color: gcol, transparent: true, opacity: 0.1, side: THREE.DoubleSide, depthWrite: false }));
    disc.rotation.x = -Math.PI / 2; disc.position.set(cx, gy + 0.14, cz);
    const ring = new THREE.Mesh(
      new THREE.RingGeometry(plazaR + 0.4, plazaR + 1.3, 52),
      new THREE.MeshBasicMaterial({ color: gcol, transparent: true, opacity: 0.6, side: THREE.DoubleSide, depthWrite: false }));
    ring.rotation.x = -Math.PI / 2; ring.position.set(cx, gy + 0.18, cz);
    const poleH = Math.max(8, storey * 3);
    const pole = new THREE.Mesh(
      new THREE.CylinderGeometry(0.16, 0.16, poleH, 6),
      new THREE.MeshBasicMaterial({ color: gcol }));
    pole.position.set(cx, gy + poleH / 2, cz);
    const canvas = document.createElement('canvas');
    const tex = new THREE.CanvasTexture(canvas);
    tex.colorSpace = THREE.SRGBColorSpace;
    this.drawSafeLabel(canvas, tex, pad.name);
    const sprite = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, transparent: true, depthTest: true }));
    sprite.scale.set(27, 13.5, 1);
    sprite.position.set(cx, gy + poleH + 6, cz);
    group.add(disc, ring, pole, sprite);
  }

  // Green "safe zone" placard for the hilltop town (mirror of drawZoneLabel).
  private drawSafeLabel(canvas: HTMLCanvasElement, tex: THREE.CanvasTexture, name: string): void {
    canvas.width = 256; canvas.height = 128;
    const g = canvas.getContext('2d')!;
    g.clearRect(0, 0, 256, 128);
    const accent = '#3ddc84';
    g.fillStyle = 'rgba(14,18,25,0.86)';
    g.strokeStyle = accent; g.lineWidth = 2;
    this.roundRect(g, 4, 4, 248, 74, 8); g.fill(); g.stroke();
    g.fillStyle = '#e6e9ee'; g.textAlign = 'center';
    g.font = '600 22px "IBM Plex Sans", sans-serif';
    g.fillText(name, 128, 33);
    g.fillStyle = accent;
    g.font = '500 15px "IBM Plex Mono", monospace';
    g.fillText('✓ SAFE ZONE', 128, 57);
    g.fillStyle = '#9fb2c2';
    g.font = '500 12px "IBM Plex Mono", monospace';
    g.fillText('HIGH GROUND · ABOVE FLOOD LINE', 128, 98);
    tex.needsUpdate = true;
  }
  // __NEW_SCENERY_METHODS__

  // Ambient low-poly houses scattered through the valley (bright white/beige/
  // orange/pastel), on gentle ground off the river and clear of the dam and the
  // labelled towns. No trees, per the brief.
  private createScatterHouses(): void {
    const damH = Math.max(6, this.damCrestY - this.damBaseY);
    const storey = damH / 18;
    const dummy = new THREE.Object3D();
    const mats: THREE.Matrix4[] = [];
    const cols: THREE.Color[] = [];
    const info: { z: number; gy: number }[] = [];
    const rand = (a: number, b: number) => a + Math.random() * (b - a);
    const wallTones = [0xf0ece4, 0xe8d9c3, 0xe0a066, 0xd98b52, 0xcfd6d8, 0xf2c9a0, 0xbfe0d0, 0xf0d9e0,
                       0xef9a9a, 0x90caf9, 0xa5d6a7, 0xfff59d, 0xffcc80];
    const roofTones = [0x9c4f3a, 0x7d5b45, 0x556169, 0xb5703f, 0x8f8578];

    const chanAt = (zz: number) =>
      Math.sin(zz * 0.012 + this.tSeed) * 16 + Math.sin(zz * 0.045 + this.tSeed * 1.7) * 5;

    const isBuildable = (x: number, zz: number, gy: number): boolean => {
      if (gy > 36) return false;                             // not high on the peaks
      const e = 2.0;
      const hx = this.getTerrainHeight(x + e, zz) - this.getTerrainHeight(x - e, zz);
      const hz = this.getTerrainHeight(x, zz + e) - this.getTerrainHeight(x, zz - e);
      if (Math.hypot(hx, hz) / (2 * e) > 0.55) return false; // too steep
      if (Math.abs(zz - this.damCenter.z) < 22 &&
          Math.abs(x - this.damCenter.x) < this.damHalfWidthX + 10) return false; // dam footprint
      if (Math.abs(x - chanAt(zz)) < 12) return false;       // off the river channel
      if (zz <= this.damUpstreamZ) {
        if (gy < this.reservoirMaxY + 1.5) return false;     // above full-pool line (reservoir side)
      } else if (gy < 1.0) return false;                     // above the downstream river
      for (const zn of this.floodZones) {
        if (Math.hypot(x - zn.x, zz - zn.z) < zn.radius + 4) return false; // clear of towns
      }
      for (const p of this.townPads) {
        if (Math.hypot(x - p.cx, zz - p.cz) < p.r + 6) return false; // colourful towns own the pads
      }
      return true;
    };

    const placeHouse = (x: number, zz: number, gy: number) => {
      const w = storey * rand(1.1, 2.0), h = storey * rand(0.9, 1.8), d = storey * rand(1.1, 2.0);
      dummy.position.set(x, gy + h / 2, zz);
      dummy.rotation.set(0, rand(-Math.PI, Math.PI), 0);
      dummy.scale.set(w, h, d);
      dummy.updateMatrix();
      mats.push(dummy.matrix.clone());
      cols.push(new THREE.Color(wallTones[(Math.random() * wallTones.length) | 0]));
      info.push({ z: zz, gy });
      dummy.position.set(x, gy + h + storey * 0.12, zz);     // flat roof cap
      dummy.scale.set(w * 0.72, storey * 0.28, d * 0.72);
      dummy.updateMatrix();
      mats.push(dummy.matrix.clone());
      cols.push(new THREE.Color(roofTones[(Math.random() * roofTones.length) | 0]));
      info.push({ z: zz, gy });
    };
    // __SCATTER_LOOPS__
    // Hamlets clustered along the valley — mostly downstream (the developed
    // lower valley from the reference), a few on the high upstream banks.
    const hamlet = (cz: number, minOff: number, maxOff: number, min: number, max: number) => {
      const cxc = chanAt(cz) + (Math.random() < 0.5 ? -1 : 1) * rand(minOff, maxOff);
      const houses = min + ((Math.random() * (max - min)) | 0);
      let placed = 0, tries = 0;
      while (placed < houses && tries < houses * 6) {
        tries++;
        const x = cxc + rand(-16, 16);
        const zz = cz + rand(-16, 16);
        const gy = this.getTerrainHeight(x, zz);
        if (!isBuildable(x, zz, gy)) continue;
        placeHouse(x, zz, gy);
        placed++;
      }
    };
    for (let c = 0; c < 9; c++) hamlet(rand(this.damToeZ + 30, this.tHalf - 25), 20, 40, 8, 22);
    for (let c = 0; c < 3; c++) hamlet(rand(-this.tHalf + 40, this.damUpstreamZ - 30), 30, 46, 5, 13);

    if (mats.length === 0) return;
    const mesh = new THREE.InstancedMesh(
      new THREE.BoxGeometry(1, 1, 1),
      new THREE.MeshStandardMaterial({ roughness: 0.85, metalness: 0.0 }),
      mats.length,
    );
    mesh.name = 'ScatterHouses';
    mesh.castShadow = true;
    mesh.receiveShadow = true;
    for (let i = 0; i < mats.length; i++) {
      mesh.setMatrixAt(i, mats[i]);
      mesh.setColorAt(i, cols[i]);
    }
    mesh.instanceMatrix.needsUpdate = true;
    if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
    this.scatterMesh = mesh;
    this.scatterBaseColors = cols;
    this.scatterInfo = info;
    this.scatterFlooded = new Array(mats.length).fill(false);
    this.scene.add(mesh);
  }
  // __UNDERWATER_AND_FLOOD_METHODS__

  private smooth01(x: number, a: number, b: number): number {
    const t = Math.max(0, Math.min(1, (x - a) / (b - a)));
    return t * t * (3 - 2 * t);
  }

  // Darken ambient houses the flood front has reached (low-lying ones only),
  // matching the flood-zone town submersion tint.
  private updateScatterFlood(): void {
    if (!this.isBreaking || !this.scatterMesh) return;
    const wet = new THREE.Color(0x1b3a4a);
    const c = new THREE.Color();
    let changed = false;
    for (let i = 0; i < this.scatterInfo.length; i++) {
      if (this.scatterFlooded[i]) continue;
      const s = this.scatterInfo[i];
      if (this.floodZ < s.z) continue;
      if (s.gy > this.currentWaterY + 4) continue;
      this.scatterFlooded[i] = true;
      c.copy(this.scatterBaseColors[i]).multiplyScalar(0.5).lerp(wet, 0.4);
      this.scatterMesh.setColorAt(i, c);
      changed = true;
    }
    if (changed && this.scatterMesh.instanceColor) this.scatterMesh.instanceColor.needsUpdate = true;
  }

  // Blue "submerged" shade + denser fog whenever the camera dips below the
  // water surface at its own position; restores the normal look above it.
  private updateUnderwater(): void {
    const cam = this.camera.position;
    const th = this.getTerrainHeight(cam.x, cam.z);
    let surf: number;
    if (cam.z <= this.damUpstreamZ) {
      surf = this.currentWaterY;                              // reservoir side
    } else {
      let d = 0;
      if (cam.z > this.damToeZ) {                             // steady tailrace
        const cx = Math.sin(cam.z * 0.012 + this.tSeed) * 16 + Math.sin(cam.z * 0.045 + this.tSeed * 1.7) * 5;
        const blend = Math.max(0, Math.min(1, (cam.z - this.damToeZ) / 40));
        const rc = this.damCenter.x + (cx - this.damCenter.x) * blend;
        const baseFlow = this.waterUniforms ? this.waterUniforms.uBaseFlow.value : 1.1;
        d = (1 - this.smooth01(Math.abs(cam.x - rc), 7, 17)) * baseFlow;
      }
      const front = this.floodZ - cam.z;                      // post-breach flood sheet
      if (front > 0) d = Math.max(d, Math.min(1, front / 8) * Math.min(this.currentWaterY - th, 10));
      surf = th + Math.max(0, d);
    }
    const submerged = cam.y < surf && surf - th > 0.05;
    if (submerged === this.underwater) return;
    this.underwater = submerged;
    if (this.underwaterTint) this.underwaterTint.style.opacity = submerged ? '1' : '0';
    if (submerged) {
      this.scene.background = new THREE.Color(0x0d3f5c);
      this.scene.fog = new THREE.FogExp2(0x0d4b6b, 0.045);
    } else {
      this.scene.background = new THREE.Color(0x1a2a3a);
      this.scene.fog = this.baseFog ?? new THREE.FogExp2(0x1a2a3a, 0.0016);
    }
  }

  // ---- Marker picking + camera fly-to -------------------------------------
  private setupPicking(): void {
    const el = this.renderer.domElement;
    let downX = 0, downY = 0, downT = 0;
    el.addEventListener('pointerdown', (e) => {
      downX = e.clientX; downY = e.clientY; downT = performance.now();
    });
    el.addEventListener('pointerup', (e) => {
      const moved = Math.hypot(e.clientX - downX, e.clientY - downY);
      if (moved > 6 || performance.now() - downT > 500) return;  // it was an orbit drag
      const zi = this.pickZoneAt(e.clientX, e.clientY);
      if (zi >= 0) this.focusOnZone(zi);
    });
    el.addEventListener('pointermove', (e) => {
      el.style.cursor = this.pickZoneAt(e.clientX, e.clientY) >= 0 ? 'pointer' : '';
    });
  }

  private pickZoneAt(clientX: number, clientY: number): number {
    if (this.pickTargets.length === 0) return -1;
    const rect = this.renderer.domElement.getBoundingClientRect();
    this.pointer.set(
      ((clientX - rect.left) / rect.width) * 2 - 1,
      -((clientY - rect.top) / rect.height) * 2 + 1
    );
    this.raycaster.setFromCamera(this.pointer, this.camera);
    const hits = this.raycaster.intersectObjects(this.pickTargets, false);
    for (const h of hits) {
      const zi = h.object.userData.zoneIndex;
      if (typeof zi === 'number') return zi;
    }
    return -1;
  }

  private focusOnZone(i: number): void {
    const z = this.floodZones[i];
    if (!z) return;
    this.focusedZone = i;
    const r = Math.max(z.radius, 12);
    const toTar = new THREE.Vector3(z.x, z.gy + 2, z.z);
    // Look at the town from upstream + above, so the flood front sweeps into view.
    const toPos = new THREE.Vector3(z.x + r * 1.3, z.gy + r * 2.0, z.z - r * 2.3);
    this.startCamTween(toPos, toTar, 1.1);
    this.setStatus(
      z.flooded ? 'danger' : 'active',
      z.flooded ? `${z.name} — inundated.` : `Inspecting ${z.name} — watching for the flood front.`
    );
    const ov = document.getElementById('overview-btn');
    if (ov) ov.style.display = 'inline-flex';
  }

  private focusOnDam(animated = true): void {
    this.focusedZone = -1;
    if (animated) {
      this.startCamTween(this.damOverview.pos.clone(), this.damOverview.target.clone(), 1.0);
    } else {
      this.camera.position.copy(this.damOverview.pos);
      this.controls.target.copy(this.damOverview.target);
      this.controls.update();
    }
    const ov = document.getElementById('overview-btn');
    if (ov) ov.style.display = 'none';
  }

  private startCamTween(toPos: THREE.Vector3, toTar: THREE.Vector3, dur: number): void {
    this.camTween = {
      t: 0, dur,
      fromPos: this.camera.position.clone(),
      toPos,
      fromTar: this.controls.target.clone(),
      toTar,
    };
    this.controls.enabled = false;   // don't fight the fly-to with orbit input
  }

  private updateCameraTween(dt: number): void {
    if (!this.camTween) return;
    const tw = this.camTween;
    tw.t += dt;
    const k = Math.min(1, tw.t / tw.dur);
    const s = k * k * (3 - 2 * k);   // smoothstep easing
    this.camera.position.lerpVectors(tw.fromPos, tw.toPos, s);
    this.controls.target.lerpVectors(tw.fromTar, tw.toTar, s);
    if (k >= 1) {
      this.camTween = null;
      this.controls.enabled = true;
    }
  }

  private drawZoneLabel(canvas: HTMLCanvasElement, tex: THREE.CanvasTexture, name: string, flooded: boolean): void {
    canvas.width = 256; canvas.height = 128;
    const g = canvas.getContext('2d')!;
    g.clearRect(0, 0, 256, 128);
    const accent = flooded ? '#d1543f' : '#e0a955';
    g.fillStyle = 'rgba(14,18,25,0.86)';
    g.strokeStyle = accent; g.lineWidth = 2;
    this.roundRect(g, 4, 4, 248, 74, 8); g.fill(); g.stroke();
    g.fillStyle = '#e6e9ee'; g.textAlign = 'center';
    g.font = '600 22px "IBM Plex Sans", sans-serif';
    g.fillText(name, 128, 33);
    g.fillStyle = accent;
    g.font = '500 15px "IBM Plex Mono", monospace';
    g.fillText(flooded ? 'INUNDATED' : 'INUNDATION RISK', 128, 56);
    // Click affordance below the card.
    g.fillStyle = '#9fb2c2';
    g.font = '500 13px "IBM Plex Mono", monospace';
    g.fillText('▸ CLICK TO INSPECT', 128, 98);
    tex.needsUpdate = true;
  }

  private roundRect(g: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number): void {
    g.beginPath();
    g.moveTo(x + r, y);
    g.arcTo(x + w, y, x + w, y + h, r);
    g.arcTo(x + w, y + h, x, y + h, r);
    g.arcTo(x, y + h, x, y, r);
    g.arcTo(x, y, x + w, y, r);
    g.closePath();
  }

  private updateFloodZones(): void {
    if (!this.isBreaking) return;
    let tinted = false;
    const wet = new THREE.Color(0x1b3a4a);
    for (const z of this.floodZones) {
      if (z.flooded || this.floodZ < z.z) continue;
      z.flooded = true;
      (z.disc.material as THREE.MeshBasicMaterial).color.setHex(0xd1543f);
      (z.disc.material as THREE.MeshBasicMaterial).opacity = 0.28;
      (z.ring.material as THREE.MeshBasicMaterial).color.setHex(0xd1543f);
      this.drawZoneLabel(z.canvas, z.tex, z.name, true);

      // Darken this settlement's structures to read as water-logged / submerged.
      if (this.settlementMesh) {
        const c = new THREE.Color();
        for (let i = z.bStart; i < z.bStart + z.bCount; i++) {
          c.copy(this.settlementBaseColors[i]).multiplyScalar(0.5).lerp(wet, 0.4);
          this.settlementMesh.setColorAt(i, c);
        }
        tinted = true;
      }
    }
    if (tinted && this.settlementMesh?.instanceColor) {
      this.settlementMesh.instanceColor.needsUpdate = true;
    }
  }

  // Build the "dam dossier" panel — a professional-looking fact sheet: a spec
  // grid, purpose/operator line, and a built → rehabilitated → notable-event →
  // safety-record timeline, all derived from the dam's public data.
  private buildDossierHTML(dam: DamInfo): string {
    const now = 2026;
    const age = Math.max(0, now - dam.year);
    const esc = (s: string) =>
      s.replace(/[&<>]/g, (c) => (c === '&' ? '&amp;' : c === '<' ? '&lt;' : '&gt;'));

    const rows: string[] = [];
    const row = (label: string, val: string) =>
      rows.push(`<div class="spec"><dt>${label}</dt><dd>${val}</dd></div>`);
    row('Commissioned', `${dam.year}`);
    row('In service', `${age}<em> yrs</em>`);
    row('Structural height', `${dam.height}<em> m</em>`);
    row('Gross storage', dam.capacity != null ? `${dam.capacity.toLocaleString()}<em> MCM</em>` : '—');
    row('River', esc(dam.river));
    row('State', esc(dam.state));
    if (dam.type) row('Type', esc(dam.type));
    if (dam.length != null) row('Crest length', `${dam.length.toLocaleString()}<em> m</em>`);
    if (dam.installedMW != null) row('Installed power', `${dam.installedMW.toLocaleString()}<em> MW</em>`);

    const tl: string[] = [];
    const item = (cls: string, year: string, title: string, desc: string) =>
      tl.push(
        `<div class="tl-item ${cls}">` +
          `<div class="tl-rail"><span class="tl-line"></span><span class="tl-dot"></span></div>` +
          `<div class="tl-body"><div class="tl-head"><span class="tl-year mono">${year}</span>` +
          `<span class="tl-title">${title}</span></div><p class="tl-desc">${desc}</p></div>` +
        `</div>`);
    item('', `${dam.year}`, 'Commissioned', `Entered service on the ${esc(dam.river)} in ${esc(dam.state)}.`);
    if (dam.renovated != null)
      item('', `${dam.renovated}`, 'Rehabilitated', 'Last major strengthening / rehabilitation on public record.');
    if (dam.event)
      item('event', `${dam.event.year}`, 'Notable event', esc(dam.event.text));
    item('safe', 'Now', dam.event ? 'In operation' : 'No failure on record',
      dam.event
        ? `Repaired and in continuous operation — ${age} years since commissioning.`
        : `No structural failure on record — ${age} years in continuous service.`);

    const note = dam.purpose
      ? `<div class="dsr-purpose"><b>Purpose.</b> ${esc(dam.purpose)}.` +
        (dam.authority ? ` Operated by ${esc(dam.authority)}.` : '') + `</div>`
      : (dam.authority ? `<div class="dsr-purpose"><b>Operator.</b> ${esc(dam.authority)}.</div>` : '');

    return `
      <div class="panel dossier">
        <div class="dossier-head">
          <div class="dsr-id">
            <span class="dsr-kicker">Dam dossier</span>
            <h3 class="dsr-title">${esc(dam.name)}</h3>
          </div>
          <span class="dsr-badge ok">In service</span>
        </div>
        <div class="dossier-body">
          <dl class="spec-grid">${rows.join('')}</dl>
          ${note}
          <div class="timeline">
            <div class="tl-sec-label">Record &amp; history</div>
            ${tl.join('')}
          </div>
          <p class="dsr-foot">Technical &amp; historical details are indicative, compiled from public sources.</p>
        </div>
      </div>`;
  }

  private createUI(dam: DamInfo): void {
    this.uiContainer = document.createElement('div');
    this.uiContainer.id = 'sim-ui';
    this.uiContainer.innerHTML = `
      <div class="sim-topbar">
        <button class="back-btn" id="back-btn" style="display: none;">← Index</button>
        <div class="sim-ident">
          <span class="sim-name">${dam.name}</span>
          <span class="sim-loc">${dam.river} · ${dam.state} · ${dam.height} m</span>
        </div>
      </div>

      ${this.buildDossierHTML(dam)}

      <div class="panel">
        <div class="panel-sec">
          <div class="sec-head">
            <span>Reservoir loading</span>
            <span class="mono" id="water-level-value">0%</span>
          </div>
          <input type="range" class="slider" id="water-slider" min="0" max="100" value="0" step="1">
          <div class="gauge">
            <div class="gauge-fill" id="water-bar-fill"></div>
            <div class="gauge-mark" style="left: ${this.breakThreshold}%">
              <span class="mark-label">Breach threshold</span>
            </div>
          </div>
          <p class="sec-note" id="load-note">Reservoir empty — structure nominal.</p>
        </div>

        <div class="panel-sec btns">
          <button class="btn primary" id="simulate-btn" style="width: 100%;">Fill reservoir</button>
          <button class="btn danger" id="break-btn" disabled style="display: none;"></button>
          <button class="btn ghost" id="reset-btn">Reset</button>
        </div>
      </div>

      <div class="panel">
        <div class="status" id="sim-status">
          <span class="status-dot idle"></span>
          <span class="status-text">Ready — set reservoir level and load.</span>
        </div>
        <div class="metrics" id="sim-metrics">
          <div class="metric"><span class="metric-label">Monoliths</span><span class="metric-value" id="m-blocks">0</span></div>
          <div class="metric"><span class="metric-label">Failed</span><span class="metric-value" id="m-broken">0</span></div>
          <div class="metric"><span class="metric-label">Head</span><span class="metric-value" id="m-water">0%</span></div>
          <div class="metric"><span class="metric-label">Debris</span><span class="metric-value" id="m-particles">0</span></div>
        </div>
      </div>

      <div class="sim-hint">Drag to orbit · scroll to zoom · orange ▸ markers are flood-risk towns (click to inspect) · green is the safe high-ground town</div>
    `;
    document.body.appendChild(this.uiContainer);

    // Floating "back to the dam" button — shown only while inspecting a town.
    const overviewBtn = document.createElement('button');
    overviewBtn.id = 'overview-btn';
    overviewBtn.textContent = '◀ Dam overview';
    overviewBtn.style.cssText =
      'position:fixed;left:16px;bottom:16px;z-index:60;display:none;align-items:center;gap:6px;' +
      'padding:9px 15px;font-family:var(--sans);font-size:0.8rem;font-weight:600;color:var(--accent-b);' +
      'background:var(--panel);border:1px solid var(--accent);border-radius:7px;cursor:pointer;';
    overviewBtn.addEventListener('click', () => this.focusOnDam());
    document.body.appendChild(overviewBtn);

    // Full-screen blue wash shown only while the camera is below the water.
    const tint = document.createElement('div');
    tint.id = 'underwater-tint';
    tint.style.cssText =
      'position:fixed;inset:0;z-index:20;pointer-events:none;opacity:0;' +
      'transition:opacity 0.28s ease;' +
      'background:linear-gradient(180deg, rgba(30,120,165,0.30), rgba(6,52,82,0.66));';
    document.body.appendChild(tint);
    this.underwaterTint = tint;

    // Wire up controls
    this.waterSlider = this.uiContainer.querySelector('#water-slider') as HTMLInputElement;
    this.waterLevelDisplay = this.uiContainer.querySelector('#water-level-value') as HTMLElement;
    this.statusText = this.uiContainer.querySelector('#sim-status') as HTMLElement;

    this.waterSlider.addEventListener('input', () => {
      this.waterTarget = parseInt(this.waterSlider.value);
      this.waterLevelDisplay.textContent = `${this.waterTarget}%`;
      const fill = this.uiContainer.querySelector('#water-bar-fill') as HTMLElement;
      fill.style.width = `${this.waterTarget}%`;
      
      if (this.waterTarget >= this.breakThreshold) {
        fill.classList.add('danger');
      } else {
        fill.classList.remove('danger');
      }
    });

    // Simulate button - smoothly raises water
    const simBtn = this.uiContainer.querySelector('#simulate-btn') as HTMLButtonElement;
    simBtn.addEventListener('click', () => {
      this.waterTarget = parseInt(this.waterSlider.value);
      if (this.waterTarget > 0) {
        this.setStatus('warn', `Filling reservoir to ${this.waterTarget}% of dam head…`);
      }
    });

    // Force break button
    const breakBtn = this.uiContainer.querySelector('#break-btn') as HTMLButtonElement;
    breakBtn.addEventListener('click', () => {
      if (!this.isBreaking) {
        this.triggerDamBreak();
      }
    });

    // Enable break button when water is high enough
    this.waterSlider.addEventListener('input', () => {
      breakBtn.disabled = parseInt(this.waterSlider.value) < this.breakThreshold;
    });

    // Reset button
    const resetBtn = this.uiContainer.querySelector('#reset-btn') as HTMLButtonElement;
    resetBtn.addEventListener('click', () => this.resetSimulation());

    // Back button
    const backBtn = this.uiContainer.querySelector('#back-btn') as HTMLButtonElement;
    backBtn.addEventListener('click', () => {
      this.destroy();
      // Dispatch event to show map again
      window.dispatchEvent(new CustomEvent('back-to-map'));
    });

    // Update metrics
    this.updateMetrics();
  }

  private setStatus(type: 'idle' | 'warn' | 'danger' | 'active', message: string): void {
    this.statusText.innerHTML = `
      <span class="status-dot ${type}"></span>
      <span class="status-text">${message}</span>
    `;
  }

  private updateMetrics(): void {
    const totalBlocks = this.damBlocks.length;
    const brokenBlocks = this.damBlocks.filter(b => b.broken).length;
    
    const el = (id: string) => document.getElementById(id);
    const mBlocks = el('m-blocks');
    const mBroken = el('m-broken');
    const mWater = el('m-water');
    const mParticles = el('m-particles');
    
    if (mBlocks) mBlocks.textContent = String(totalBlocks);
    if (mBroken) mBroken.textContent = String(brokenBlocks);
    if (mWater) mWater.textContent = `${Math.round(this.waterLevel)}%`;
    if (mParticles) mParticles.textContent = String(this.floodParticles.length);
  }

  private triggerDamBreak(): void {
    this.isBreaking = true;
    this.breakProgress = 0;
    this.setStatus('danger', 'Spillway gates opening — crest overtopping and failing.');

    // Play the GLB's spillway-gate animation (the dam's baked animation).
    this.openSpillwayGates();

    // Pick a small cluster of crest-centre pieces to let go — a natural crumble,
    // not the whole face disintegrating. Others stay put.
    this.selectBreachPieces();

    // Shake camera
    this.shakeCamera(2.0, 3);
  }

  // Choose only the most vulnerable pieces (near the dam centre and crest) and
  // stagger when each lets go, so a handful topples and falls under gravity.
  private selectBreachPieces(): void {
    const cx = this.damCenter.x;
    const halfW = Math.max(1, this.damHalfWidthX);
    const candidates = this.damBlocks.filter(b =>
      !b.broken &&
      b.heightRatio > 0.5 &&                              // upper half only
      Math.abs(b.originalPosition.x - cx) < halfW * 0.42  // centred on the dam
    );
    // Top-centre pieces score lowest → go first.
    candidates.sort((a, b) =>
      (Math.abs(a.originalPosition.x - cx) / halfW + (1 - a.heightRatio)) -
      (Math.abs(b.originalPosition.x - cx) / halfW + (1 - b.heightRatio))
    );
    const cap = Math.min(candidates.length, Math.max(50, Math.round(this.damBlocks.length * 0.018)));
    this.breachPieces = candidates.slice(0, cap);
    for (let i = 0; i < this.breachPieces.length; i++) {
      // Cascade over ~2.6 s from the crest centre outward, with a little jitter.
      this.breachPieces[i].breakDelay = (i / cap) * 2.6 + Math.random() * 0.35;
    }
  }

  private shakeCamera(intensity: number, duration: number): void {
    const startTime = performance.now();
    const originalPos = this.camera.position.clone();
    
    const shake = () => {
      const elapsed = (performance.now() - startTime) / 1000;
      if (elapsed > duration) {
        return;
      }
      const decay = 1 - elapsed / duration;
      const shakeX = (Math.random() - 0.5) * intensity * decay;
      const shakeY = (Math.random() - 0.5) * intensity * decay;
      this.camera.position.x = originalPos.x + shakeX;
      this.camera.position.y = originalPos.y + shakeY;
      requestAnimationFrame(shake);
    };
    shake();
  }

  private updateWater(dt: number): void {
    // Smoothly approach target reservoir level.
    const diff = this.waterTarget - this.waterLevel;
    this.waterLevel += Math.abs(diff) > 0.1 ? diff * dt * 0.8 : diff;

    // Fill fraction → reservoir surface height between base and crest.
    const frac = Math.max(0, Math.min(1, this.waterLevel / 100));
    let waterY = this.reservoirMinY + frac * (this.reservoirMaxY - this.reservoirMinY);

    if (this.isBreaking) {
      // Reservoir draws down as the breach releases the head downstream.
      const drainTo = this.reservoirMinY + 0.14 * (this.reservoirMaxY - this.reservoirMinY);
      waterY += (drainTo - waterY) * Math.min(1, this.breakProgress * 0.11);
      // Flood front races downstream — faster with more head behind it.
      const head = Math.max(0, this.currentWaterY - this.damBaseY);
      this.floodZ = Math.min(this.floodZ + (16 + head * 1.4) * dt, this.tHalf);
    }
    this.currentWaterY = waterY;

    if (this.waterUniforms) {
      this.waterUniforms.uWaterY.value = waterY;
      this.waterUniforms.uFloodZ.value = this.floodZ;
      this.waterUniforms.uBaseFlow.value = 1.1 + frac * 1.3;   // release grows with head
    }

    // Auto-trigger breach at threshold.
    if (this.waterLevel >= this.breakThreshold && !this.isBreaking) {
      this.triggerDamBreak();
    }

    // Load note reflects structural stress.
    const note = document.getElementById('load-note');
    if (note && !this.isBreaking) {
      if (this.waterLevel < 30) note.innerHTML = 'Reservoir low — structure nominal.';
      else if (this.waterLevel < this.breakThreshold) note.innerHTML = 'Hydrostatic load rising on the upstream face.';
      else note.innerHTML = 'Load past <b>breach threshold</b> — failure imminent.';
    }

    const fill = document.getElementById('water-bar-fill');
    if (fill) {
      fill.style.width = `${this.waterLevel}%`;
      fill.classList.toggle('danger', this.waterLevel >= this.breakThreshold);
    }
    const display = document.getElementById('water-level-value');
    if (display) display.textContent = `${Math.round(this.waterLevel)}%`;
  }


  private updateDamBreak(dt: number): void {
    if (!this.isBreaking) return;

    this.breakProgress += dt;                 // seconds since breach began
    const elapsed = this.breakProgress;
    const gravity = -20;
    const cx = this.damCenter.x;

    // Only the pre-selected crest cluster moves — the rest of the dam holds.
    for (const block of this.breachPieces) {
      if (block.broken) {
        if (block.settled) continue;

        block.velocity.y += gravity * dt;

        // Mild downstream wash while riding the flood sheet (a drift, not a blast).
        const inFlood =
          block.mesh.position.z > this.damCenter.z &&
          block.mesh.position.z < this.floodZ + 6 &&
          block.mesh.position.y < this.currentWaterY + 3;
        if (inFlood) {
          block.velocity.z += 5 * dt;
          block.velocity.y += 1.2 * dt;
        }
        block.velocity.multiplyScalar(0.992);

        block.mesh.position.addScaledVector(block.velocity, dt);
        block.mesh.rotation.x += block.angularVelocity.x * dt;
        block.mesh.rotation.y += block.angularVelocity.y * dt;
        block.mesh.rotation.z += block.angularVelocity.z * dt;

        const groundY = this.getTerrainHeight(block.mesh.position.x, block.mesh.position.z);
        if (block.mesh.position.y < groundY) {
          block.mesh.position.y = groundY;
          block.velocity.y = -block.velocity.y * 0.2;   // small bounce, then rest
          block.velocity.x *= 0.6;
          block.velocity.z *= 0.7;
          block.angularVelocity.multiplyScalar(0.5);
          if (block.velocity.length() < 0.5 && block.angularVelocity.length() < 0.5) {
            block.settled = true;
          }
        }
        if (block.mesh.position.y < -60) { block.mesh.visible = false; block.settled = true; }
        continue;
      }

      if (elapsed < block.breakDelay) {
        // A slight tremble just before this piece lets go.
        if (elapsed > block.breakDelay - 0.4) {
          block.mesh.position.x += (Math.random() - 0.5) * 0.03;
          block.mesh.position.y += (Math.random() - 0.5) * 0.02;
        }
        continue;
      }

      // Release: detach to world space and let gravity drop it (gentle topple).
      block.broken = true;
      if (block.mesh.parent && block.mesh.parent !== this.scene) {
        const wp = new THREE.Vector3(), wq = new THREE.Quaternion(), ws = new THREE.Vector3();
        block.mesh.getWorldPosition(wp);
        block.mesh.getWorldQuaternion(wq);
        block.mesh.getWorldScale(ws);
        block.mesh.removeFromParent();
        this.scene.add(block.mesh);
        block.mesh.position.copy(wp);
        block.mesh.quaternion.copy(wq);
        block.mesh.scale.copy(ws);
      }
      // Almost no launch impulse — just a small forward lean; gravity does the rest.
      block.velocity.set(
        (block.originalPosition.x - cx) * 0.05 + (Math.random() - 0.5) * 0.8,
        0.2 + Math.random() * 0.5,
        1.2 + Math.random() * 1.8
      );
      block.angularVelocity.set(
        (Math.random() - 0.5) * 2.4,
        (Math.random() - 0.5) * 2.4,
        (Math.random() - 0.5) * 2.4
      );
      this.spawnFloodParticles(block.mesh.position, 2 + Math.floor(Math.random() * 3));
    }

    // Whitewater gushing through the opened breach/gates (water, not debris).
    if (elapsed > 0.15 && this.floodParticles.length < 1200) {
      const rate = Math.min(3 + Math.floor(elapsed * 3), 10);
      const openHalf = this.damHalfWidthX * 0.35;
      for (let i = 0; i < rate; i++) {
        this.spawnFloodParticles(new THREE.Vector3(
          cx + (Math.random() - 0.5) * openHalf * 2,
          this.currentWaterY - Math.random() * 3,
          this.damCenter.z + Math.random() * 2
        ), 1);
      }
    }

    if (this.frameCount % 10 === 0) {
      const broken = this.breachPieces.filter(b => b.broken).length;
      if (broken > 0) {
        this.setStatus('danger', `Breach released — ${broken} crest blocks down · flood advancing downstream.`);
      }
    }
  }

  private spawnFloodParticles(pos: THREE.Vector3, count: number): void {
    for (let i = 0; i < count; i++) {
      this.floodParticles.push({
        pos: new THREE.Vector3(
          pos.x + (Math.random() - 0.5) * 4,
          pos.y + Math.random() * 1.5,
          pos.z + (Math.random() - 0.5) * 2
        ),
        vel: new THREE.Vector3(
          (Math.random() - 0.5) * 6,
          2 + Math.random() * 5,
          10 + Math.random() * 16 // strong downstream jet
        ),
        life: 3 + Math.random() * 5,
      });
    }
  }

  private updateFloodParticles(dt: number): void {
    this.stepParticles(this.floodParticles, this.floodMesh, 2000, dt);
  }

  // Shared particle integrator: gravity, channel steering, ground bounce, and
  // packing survivors into the instanced mesh. Used by both the breach flood
  // and the continuous tailrace outflow.
  private stepParticles(
    list: { pos: THREE.Vector3; vel: THREE.Vector3; life: number }[],
    mesh: THREE.InstancedMesh | null,
    maxDisplay: number,
    dt: number,
  ): void {
    if (!mesh) return;

    const gravity = -15;
    const dummy = new THREE.Object3D();
    let alive = 0;

    for (let i = 0; i < list.length; i++) {
      const p = list[i];
      p.life -= dt;
      if (p.life <= 0) continue;

      // Physics
      p.vel.y += gravity * dt;
      p.vel.x *= 0.995;
      p.vel.z *= 0.995;

      // Steer toward the valley centreline so the flow follows the channel.
      const cxLine = Math.sin(p.pos.z * 0.012 + this.tSeed) * 16 + Math.sin(p.pos.z * 0.045 + this.tSeed * 1.7) * 5;
      p.vel.x += (cxLine - p.pos.x) * 1.5 * dt;

      p.pos.x += p.vel.x * dt;
      p.pos.y += p.vel.y * dt;
      p.pos.z += p.vel.z * dt;

      // Ground collision
      const groundY = this.getTerrainHeight(p.pos.x, p.pos.z);
      if (p.pos.y < groundY + 0.3) {
        p.pos.y = groundY + 0.3;
        p.vel.y = -p.vel.y * 0.2;
        p.vel.x *= 0.9;
        p.vel.z *= 0.9;
      }

      // Keep alive particle
      if (alive < i) {
        list[alive] = p;
      }

      if (alive < maxDisplay) {
        dummy.position.copy(p.pos);
        const scale = 0.3 + (p.life / 8) * 0.7;
        dummy.scale.setScalar(scale);
        dummy.updateMatrix();
        mesh.setMatrixAt(alive, dummy.matrix);
      }
      alive++;
    }

    list.length = alive;
    mesh.count = Math.min(alive, maxDisplay);
    mesh.instanceMatrix.needsUpdate = true;
  }

  // A dedicated foam system for the steady base outflow, so it stays separate
  // from the breach debris/flood budget and metrics.
  private createOutflowSystem(): void {
    const sphereGeo = new THREE.SphereGeometry(0.42, 6, 5);
    const foamMat = new THREE.MeshStandardMaterial({
      color: 0xdfeef5,
      roughness: 0.65,
      metalness: 0.0,
      transparent: true,
      opacity: 0.9,
    });
    this.outflowMesh = new THREE.InstancedMesh(sphereGeo, foamMat, 500);
    this.outflowMesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
    this.outflowMesh.count = 0;
    this.outflowMesh.frustumCulled = false;
    this.outflowMesh.name = 'OutflowSpray';
    this.scene.add(this.outflowMesh);
  }

  // Spawn whitewater at the base gap every frame so a river visibly pours out
  // of the dam downstream — even at rest — not just when it breaks.
  private emitOutflow(dt: number): void {
    void dt;
    const frac = Math.max(0, Math.min(1, this.waterLevel / 100));
    const budget = Math.round(90 + frac * 210);
    if (this.outflowParticles.length >= budget) return;
    const spawn = Math.min(budget - this.outflowParticles.length, 5);
    const cx = this.damCenter.x;
    const y = this.damBaseY + 1.2;
    const z = this.damToeZ + 0.5;
    const speed = 9 + frac * 8;
    for (let i = 0; i < spawn; i++) {
      this.outflowParticles.push({
        pos: new THREE.Vector3(
          cx + (Math.random() - 0.5) * this.damHalfWidthX * 0.28,
          y + Math.random() * 1.2,
          z + Math.random() * 1.5,
        ),
        vel: new THREE.Vector3(
          (Math.random() - 0.5) * 3,
          1 + Math.random() * 2,
          speed + Math.random() * 6,
        ),
        life: 2 + Math.random() * 2.5,
      });
    }
  }

  private updateOutflow(dt: number): void {
    this.stepParticles(this.outflowParticles, this.outflowMesh, 500, dt);
  }

  private resetSimulation(): void {
    this.isBreaking = false;
    this.breakProgress = 0;
    this.waterLevel = 0;
    this.waterTarget = 0;
    this.floodParticles.length = 0;
    this.terrainHeightCache.clear();

    if (this.floodMesh) {
      this.floodMesh.count = 0;
    }

    // Reset slider
    if (this.waterSlider) {
      this.waterSlider.value = '0';
    }
    const fill = document.getElementById('water-bar-fill');
    if (fill) {
      fill.style.width = '0%';
      fill.classList.remove('danger');
    }
    const note = document.getElementById('load-note');
    if (note) note.innerHTML = 'Reservoir empty — structure nominal.';

    // Reset water surface + flood front to the drained reservoir state.
    this.currentWaterY = this.reservoirMinY;
    this.floodZ = this.damUpstreamZ;
    if (this.waterUniforms) {
      this.waterUniforms.uWaterY.value = this.reservoirMinY;
      this.waterUniforms.uFloodZ.value = this.damUpstreamZ;
    }

    // Un-flood the affected-area markers.
    for (const z of this.floodZones) {
      z.flooded = false;
      (z.disc.material as THREE.MeshBasicMaterial).color.setHex(0xe0a955);
      (z.disc.material as THREE.MeshBasicMaterial).opacity = 0.16;
      (z.ring.material as THREE.MeshBasicMaterial).color.setHex(0xe0a955);
      this.drawZoneLabel(z.canvas, z.tex, z.name, false);
    }

    // Restore the (un-flooded) settlement colours.
    if (this.settlementMesh) {
      for (let i = 0; i < this.settlementBaseColors.length; i++) {
        this.settlementMesh.setColorAt(i, this.settlementBaseColors[i]);
      }
      if (this.settlementMesh.instanceColor) this.settlementMesh.instanceColor.needsUpdate = true;
    }

    // Restore ambient house colours and clear the steady-outflow spray.
    if (this.scatterMesh) {
      for (let i = 0; i < this.scatterBaseColors.length; i++) {
        this.scatterMesh.setColorAt(i, this.scatterBaseColors[i]);
        this.scatterFlooded[i] = false;
      }
      if (this.scatterMesh.instanceColor) this.scatterMesh.instanceColor.needsUpdate = true;
    }
    this.outflowParticles.length = 0;
    if (this.outflowMesh) this.outflowMesh.count = 0;

    // Reset dam blocks
    this.breachPieces = [];
    for (const block of this.damBlocks) {
      if (block.broken) {
        block.mesh.visible = true;
        block.mesh.removeFromParent();
      }
      block.broken = false;
      block.settled = false;
      block.health = 1.0;
      block.breakDelay = 0;
      block.velocity.set(0, 0, 0);
    }

    // Reload dam model in original state
    if (this.damGroup) {
      this.damGroup.removeFromParent();
    }
    this.damBlocks = [];
    this.loadDamModel().then(() => {
      this.focusOnDam(false);   // gates are closed again on the fresh model
      this.setStatus('idle', 'Ready — Adjust water level and simulate');
      this.updateMetrics();
    });

    this.setStatus('idle', 'Resetting...');

    const breakBtn = document.getElementById('break-btn') as HTMLButtonElement;
    if (breakBtn) breakBtn.disabled = true;
  }

  private animate = (): void => {
    if (!this.isRunning) return;
    this.animationId = requestAnimationFrame(this.animate);
    this.frameCount++;

    const dt = Math.min(this.clock.getDelta(), 0.05);

    if (this.waterUniforms) this.waterUniforms.uTime.value = this.clock.elapsedTime;
    if (this.mixer) this.mixer.update(dt);

    this.updateWater(dt);
    this.emitOutflow(dt);
    this.updateDamBreak(dt);
    this.updateFloodZones();
    this.updateScatterFlood();
    this.updateFloodParticles(dt);
    this.updateOutflow(dt);
    this.updateUnderwater();
    this.updateCameraTween(dt);
    this.controls.update();
    
    // Throttle metrics to every 10 frames
    if (this.frameCount % 10 === 0) {
      this.updateMetrics();
    }

    this.renderer.render(this.scene, this.camera);
  };

  private setupResize(): void {
    window.addEventListener('resize', () => {
      if (!this.isRunning) return;
      this.renderer.setSize(window.innerWidth, window.innerHeight);
      this.camera.aspect = window.innerWidth / window.innerHeight;
      this.camera.updateProjectionMatrix();
    });
  }

  destroy(): void {
    this.isRunning = false;
    cancelAnimationFrame(this.animationId);

    // Stop any running GLB gate animations
    this.mixer?.stopAllAction();

    // Remove canvas
    const canvas = document.getElementById('sim-canvas');
    if (canvas) canvas.remove();

    // Remove UI
    if (this.uiContainer) this.uiContainer.remove();
    document.getElementById('overview-btn')?.remove();
    document.getElementById('underwater-tint')?.remove();
    this.underwaterTint = null;

    // Dispose
    this.renderer?.dispose();
    this.scene?.clear();
  }
}
