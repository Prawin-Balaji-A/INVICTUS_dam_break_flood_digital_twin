/**
 * Water.ts — stylized GLSL water over the baked terrain heightmap.
 *   Reservoir plane (mode 0): flat surface at a controllable level, fills the -Z basin.
 *   Downstream plane (mode 1): always-on baseflow river + a breach flood that spreads
 *   radially from the breach — downstream-biased but fanning out sideways over the
 *   valley towns (see floodEdge below), not a straight advancing sheet.
 * Fragment discards dry cells (terrain above the surface); colour is depth based with
 * Fresnel sky reflection, sun specular, wave normals, shore + flood-front foam.
 */
import {
  Mesh,
  PlaneGeometry,
  ShaderMaterial,
  DoubleSide,
  Vector2,
  Vector3,
  Color,
  Texture,
} from 'three';
import type { HeightMapInfo } from '../terrain/Terrain';
import { WATER, SKY, DAM } from '../config';

// Shared GLSL: how far a world cell sits inside the spreading breach flood.
// Returns >0 inside the flood, ~0 on the advancing edge, <0 outside. The front
// grows radially from the breach origin but is heavily downstream-biased and only
// barely backs upstream, so the water fans out sideways toward the valley towns
// (organic finger wobble keeps the edge from reading as a clean arc).
const FLOOD_GLSL = /* glsl */ `
  float floodEdge(vec2 wxz, vec2 origin, float reach, float t) {
    vec2 fd = wxz - origin;
    float ds = max(fd.y, 0.0);   // downstream (+Z): spreads far
    float us = max(-fd.y, 0.0);  // upstream (-Z): barely backs up
    float lat = abs(fd.x);       // lateral: fans toward the towns on either bank
    float ang = atan(fd.x, fd.y + 0.001);
    float wob = 90.0 * sin(ang * 4.0 + t * 0.5) + 46.0 * sin(ang * 9.0 - t * 0.35 + 1.7);
    float rad = sqrt(ds * ds * 0.30 + lat * lat * 1.15 + us * us * 6.0);
    return reach + wob - rad;
  }
`;

const VERT = /* glsl */ `
  uniform float uTime;
  uniform float uMode;        // 0 reservoir, 1 downstream
  uniform float uLevel;       // reservoir surface Y
  uniform vec2 uFloodOrigin;  // breach origin (x,z) the flood spreads from
  uniform float uFloodReach;  // radial spread distance (grows after breach)
  uniform float uFloodLevel;  // flood sheet Y
  uniform float uBaseSurf;    // riverBed + baseflowDepth
  uniform float uWaveAmp;
  varying vec3 vWorld;
  varying float vSurf;
  varying float vWave;

  ${FLOOD_GLSL}

  float waveH(vec2 p, float t) {
    return sin(p.x * 0.06 + t * 1.1) * 0.5
         + sin(p.y * 0.045 - t * 0.9) * 0.5
         + sin((p.x + p.y) * 0.03 + t * 1.7) * 0.3;
  }

  void main() {
    vec4 wp = modelMatrix * vec4(position, 1.0);
    vWorld = wp.xyz;
    float surf;
    if (uMode < 0.5) {
      surf = uLevel;
    } else {
      float base = uBaseSurf - max(wp.z, 0.0) * 0.004;   // descending baseflow (straight river)
      float flood = (floodEdge(wp.xz, uFloodOrigin, uFloodReach, uTime) >= 0.0) ? uFloodLevel : -1e5;
      surf = max(base, flood);
    }
    float w = waveH(wp.xz, uTime) * uWaveAmp;
    vWave = w;
    vSurf = surf;
    wp.y = surf + w;
    vWorld.y = wp.y;
    gl_Position = projectionMatrix * viewMatrix * wp;
  }
`;

const FRAG = /* glsl */ `
  precision highp float;
  uniform sampler2D uHeight;
  uniform vec2 uHMin;      // heightmap world min (x,z)
  uniform vec2 uHSize;     // heightmap world size (x,z)
  uniform float uTime;
  uniform float uMode;
  uniform vec2 uFloodOrigin;
  uniform float uFloodReach;
  uniform float uFloodMix;   // 0..1 muddy flood tint ramp
  uniform vec3 uSun;
  uniform vec3 uShallow;
  uniform vec3 uDeep;
  uniform vec3 uFoam;
  uniform vec3 uFlood;
  uniform vec3 uSky;
  uniform float uWaveAmp;
  uniform float uDepthScale;  // depth over which shallow->deep saturates
  uniform float uRipple;      // 0..1 rain agitation
  varying vec3 vWorld;
  varying float vSurf;
  varying float vWave;

  ${FLOOD_GLSL}

  float waveH(vec2 p, float t) {
    return sin(p.x * 0.06 + t * 1.1) * 0.5
         + sin(p.y * 0.045 - t * 0.9) * 0.5
         + sin((p.x + p.y) * 0.03 + t * 1.7) * 0.3;
  }

  void main() {
    vec2 uv = (vWorld.xz - uHMin) / uHSize;
    if (uv.x < 0.0 || uv.x > 1.0 || uv.y < 0.0 || uv.y > 1.0) discard;
    float terr = texture2D(uHeight, uv).r;
    float depth = vSurf - terr;
    if (depth <= 0.03) discard;

    // wave normal (finite diff of waveH)
    float e = 1.5;
    float h0 = waveH(vWorld.xz, uTime) * uWaveAmp;
    float hx = waveH(vWorld.xz + vec2(e, 0.0), uTime) * uWaveAmp;
    float hz = waveH(vWorld.xz + vec2(0.0, e), uTime) * uWaveAmp;
    vec3 nrm = normalize(vec3(h0 - hx, e, h0 - hz));

    // rain ripples: fine, fast cross-hatched perturbation while the storm is on
    if (uRipple > 0.001) {
      float rx = sin(vWorld.x * 0.95 + uTime * 7.3) + sin(vWorld.z * 0.7 - uTime * 5.1);
      float rz = sin(vWorld.z * 1.05 - uTime * 6.4) + sin(vWorld.x * 0.8 + uTime * 4.7);
      nrm = normalize(nrm + vec3(rx, 0.0, rz) * 0.09 * uRipple);
    }

    vec3 viewDir = normalize(cameraPosition - vWorld);
    vec3 sun = normalize(uSun);

    // depth colour (gradient scaled per body: shallow river vs very deep reservoir)
    float dt = clamp(depth / uDepthScale, 0.0, 1.0);
    vec3 col = mix(uShallow, uDeep, dt);

    // flood muddiness (downstream, near the advancing radial front)
    float fe = floodEdge(vWorld.xz, uFloodOrigin, uFloodReach, uTime);
    if (uMode > 0.5) {
      float frontProx = clamp(1.0 - fe / 400.0, 0.0, 1.0);   // 1 at the leading edge
      col = mix(col, uFlood, uFloodMix * (0.35 + 0.4 * frontProx));
    }

    // Fresnel sky reflection
    float fres = pow(1.0 - max(dot(viewDir, nrm), 0.0), 3.0);
    col = mix(col, uSky, clamp(fres * 0.6, 0.0, 0.6));

    // Blinn-Phong sun specular (dimmed under overcast rain)
    vec3 hlf = normalize(sun + viewDir);
    float spec = pow(max(dot(nrm, hlf), 0.0), 120.0);
    col += vec3(1.0, 0.96, 0.86) * spec * 0.9 * (1.0 - 0.7 * uRipple);

    // shore foam (shallow) + wave-crest sparkle
    float shore = smoothstep(1.6, 0.05, depth);
    float crest = smoothstep(0.55, 0.95, (vWave / max(uWaveAmp, 0.001)) * 0.5 + 0.5);
    float foam = max(shore, crest * 0.25);
    // flood-front foam band (rings the spreading edge)
    if (uMode > 0.5) {
      float band = smoothstep(60.0, 0.0, abs(fe));
      foam = max(foam, band * uFloodMix);
    }
    col = mix(col, uFoam, clamp(foam, 0.0, 0.9));

    // overcast dimming while raining
    col *= (1.0 - 0.16 * uRipple);

    float alpha = mix(0.62, 0.95, dt);
    gl_FragColor = vec4(col, alpha);
  }
`;

export class Water {
  readonly reservoir: Mesh;
  readonly downstream: Mesh;
  private matRes: ShaderMaterial;
  private matDown: ShaderMaterial;
  private time = 0;

  /** current reservoir surface world-Y. */
  reservoirY = WATER.reservoirFloorY;

  setReservoirLevel(y: number): void {
    this.reservoirY = y;
    this.matRes.uniforms.uLevel.value = y;
  }

  /** reach = radial spread distance from the breach; sheetY = flood surface Y; mix = muddy tint 0..1. */
  setFlood(reach: number, sheetY: number, mix: number): void {
    this.matDown.uniforms.uFloodReach.value = reach;
    this.matDown.uniforms.uFloodLevel.value = sheetY;
    this.matDown.uniforms.uFloodMix.value = mix;
  }

  update(dt: number): void {
    this.time += dt;
    this.matRes.uniforms.uTime.value = this.time;
    this.matDown.uniforms.uTime.value = this.time;
  }

  /** rain agitation 0..1 — adds ripples + dulls specular on both water bodies. */
  setRain(v: number): void {
    this.matRes.uniforms.uRipple.value = v;
    this.matDown.uniforms.uRipple.value = v;
  }

  constructor(hm: HeightMapInfo) {
    this.matRes = this.makeMaterial(hm, 0, hm.texture);
    this.matDown = this.makeMaterial(hm, 1, hm.texture);

    // reservoir covers the upstream basin, stopping at the dam's upstream face
    this.reservoir = this.makePlane(hm.minX, hm.minX + hm.sizeX, hm.minZ, -35, 220, 140, this.matRes);
    // downstream corridor starts just below the dam and runs to the edge of the map
    this.downstream = this.makePlane(hm.minX, hm.minX + hm.sizeX, 20, hm.minZ + hm.sizeZ, 240, 260, this.matDown);

    this.setReservoirLevel(WATER.reservoirFloorY + (WATER.reservoirMaxY - WATER.reservoirFloorY) * WATER.startLevel);
    this.setFlood(-1e5, WATER.reservoirFloorY, 0);
  }

  private makeMaterial(hm: HeightMapInfo, mode: number, tex: Texture): ShaderMaterial {
    return new ShaderMaterial({
      transparent: true,
      side: DoubleSide,
      depthWrite: false,
      uniforms: {
        uTime: { value: 0 },
        uMode: { value: mode },
        uLevel: { value: WATER.reservoirFloorY },
        uFloodOrigin: { value: new Vector2(DAM.axisX, DAM.wallZ) },
        uFloodReach: { value: -1e5 },
        uFloodLevel: { value: WATER.reservoirFloorY },
        uFloodMix: { value: 0 },
        uBaseSurf: { value: WATER.riverBedY + WATER.baseflowDepth },
        uWaveAmp: { value: mode < 0.5 ? 0.9 : 0.6 },
        uDepthScale: { value: mode < 0.5 ? WATER.reservoirDepthScale : WATER.riverDepthScale },
        uRipple: { value: 0 },
        uHeight: { value: tex },
        uHMin: { value: new Vector2(hm.minX, hm.minZ) },
        uHSize: { value: new Vector2(hm.sizeX, hm.sizeZ) },
        uSun: { value: new Vector3(...SKY.sunDir) },
        uShallow: { value: WATER.shallowColor.clone() },
        uDeep: { value: (mode < 0.5 ? WATER.reservoirDeep : WATER.deepColor).clone() },
        uFoam: { value: WATER.foamColor.clone() },
        uFlood: { value: WATER.floodColor.clone() },
        uSky: { value: new Color(SKY.topColor.getHex()).lerp(new Color(0xffffff), 0.3) },
      },
      vertexShader: VERT,
      fragmentShader: FRAG,
    });
  }

  private makePlane(x0: number, x1: number, z0: number, z1: number, sx: number, sz: number, mat: ShaderMaterial): Mesh {
    const geo = new PlaneGeometry(x1 - x0, z1 - z0, sx, sz);
    geo.rotateX(-Math.PI / 2); // lie in XZ, normal +Y
    geo.translate((x0 + x1) / 2, 0, (z0 + z1) / 2);
    const mesh = new Mesh(geo, mat);
    mesh.renderOrder = 2;
    mesh.frustumCulled = false;
    return mesh;
  }
}
